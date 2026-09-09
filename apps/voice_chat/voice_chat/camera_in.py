"""카메라 프레임 한 장 → JPEG 바이트. `audio_in.MicCapture` 와 대칭이다.

**GStreamer 로 인코딩까지 끝낸다.** 로봇 앱 venv 에는 `cv2`·`PIL`·`picamera2` 가
없다(실측 2026-09-09). `jpegenc` 가 파이프라인 안에서 JPEG 를 만들어 주므로
**의존성을 하나도 더하지 않는다** — `gi` 는 오디오 때문에 이미 있다.

**이걸 열 수 있는 이유는 `main.py` 의 `request_media_backend = "no_media"` 다.**
데몬이 카메라를 놓았기 때문에 우리가 직접 연다(§8). 누가 그 값을 되돌리면
데몬이 카메라를 쥐고 여기가 **조용히 깨진다** — 그때는 SDK 의 `media.camera` 를
쓰도록 갈아타야 한다.

수명: **기본은 요청마다 열고 닫는다.** CM4 콜드 스타트를 아직 안 쟀고, 상시
켜두면 인코딩 부하를 계속 문다 — 실측으로 부하 2.4 에서 데몬 연결(타임아웃 5초)이
실패한 적이 있다. 연속 질문("이건? 저건?")이 잦으면 `REACHY_CAMERA_IDLE_S` 를
올려 열어 둔다. **콜드 스타트를 잰 뒤에 기본값을 정한다.**
"""

import platform
import threading
import time

import config

_pipe = None
_last = 0.0
_lock = threading.Lock()
_watcher = None


def _enabled() -> bool:
    return config.get("REACHY_VISION", "1").lower() not in ("0", "false", "no")


def _idle_s() -> float:
    """파이프라인을 열어 두는 시간(초). 0 이면 매 요청마다 닫는다.

    **실측(2026-09-09, CM4)으로 정한 값이다.** 열고 닫으면 캡처가 1.13s,
    열어 두면 0.03s 다(35배). 대신 열어 둔 채로는 부하가 약 반 코어 오른다
    (1.69 → 2.07) — 부하 2.4 에서 데몬 연결(타임아웃 5초)이 실패한 전례가 있어
    시연 내내 열어 둘 수는 없다. 그래서 **연속 질문 동안만 열고 유휴면 닫는다.**
    """
    return float(config.get("REACHY_CAMERA_IDLE_S", "20"))


def _open():
    """파이프라인을 세우고 **PLAYING 까지 갔는지 확인한다.**

    확인이 핵심이다. PLAYING 에 못 가면 appsink 의 pull 이 영영 반환하지 않아
    앱이 통째로 굳는다 — 마이크 쪽에서 이미 겪은 실패 방식이다(`audio_in._start`).
    """
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    Gst.init(None)
    src = config.get("REACHY_CAMERA_SRC", "libcamerasrc")
    w = config.get("REACHY_CAMERA_WIDTH", "320")
    q = config.get("REACHY_CAMERA_JPEG_QUALITY", "80")
    chain = (
        f"{src} ! videoconvert ! videoscale"
        f" ! video/x-raw,width={w} ! jpegenc quality={q}"
        f" ! appsink name=sink max-buffers=1 drop=true sync=false"
    )
    pipe = Gst.parse_launch(chain)
    pipe.set_state(Gst.State.PLAYING)
    if pipe.get_state(5 * Gst.SECOND)[1] != Gst.State.PLAYING:
        pipe.set_state(Gst.State.NULL)
        raise RuntimeError(f"PLAYING 에 도달하지 못했다: {chain}")
    return pipe


def _pull() -> bytes | None:
    """최신 프레임 한 장. 타임아웃을 둔다 — 여기서 막히면 대화가 멈춘다."""
    from gi.repository import Gst

    sink = _pipe.get_by_name("sink")
    timeout_ns = int(float(config.get("REACHY_CAMERA_TIMEOUT_S", "2.0")) * Gst.SECOND)
    sample = sink.emit("try-pull-sample", timeout_ns)
    if sample is None:
        raise RuntimeError("프레임이 오지 않았다(타임아웃)")
    buf = sample.get_buffer()
    ok, info = buf.map(Gst.MapFlags.READ)
    if not ok:
        raise RuntimeError("버퍼를 매핑하지 못했다")
    try:
        return bytes(info.data)
    finally:
        buf.unmap(info)


def _shutdown() -> None:
    global _pipe
    if _pipe is None:
        return
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        _pipe.set_state(Gst.State.NULL)
    except Exception:  # noqa: BLE001
        pass
    _pipe = None


def _watch() -> None:
    """유휴 감시. 마지막 사용에서 `_idle_s()` 가 지나면 닫고 스레드를 끝낸다."""
    while True:
        idle = _idle_s()
        time.sleep(min(1.0, max(0.05, idle / 4)))
        with _lock:
            if _pipe is None:
                return
            if idle > 0 and time.monotonic() - _last > idle:
                _shutdown()
                print("  [카메라] 유휴로 닫았다", flush=True)
                return


def close() -> None:
    """앱 종료 경로에서 부른다. 안 닫으면 장치를 쥔 채 남아 다음 기동이 깨진다."""
    with _lock:
        _shutdown()


def _arm_watcher() -> None:
    global _watcher
    if _watcher is not None and _watcher.is_alive():
        return
    _watcher = threading.Thread(target=_watch, name="camera-idle", daemon=True)
    _watcher.start()


def grab_jpeg() -> bytes | None:
    """프레임 한 장을 JPEG 로. 실패하면 **None** — 대화는 계속된다."""
    global _pipe, _last
    if not _enabled():
        return None
    if platform.system() != "Linux":
        # 시뮬(macOS)에는 libcamerasrc 가 없다. 여기서 경고를 쏟으면 시끄럽다.
        return None
    try:
        if _pipe is None:
            _pipe = _open()
        data = _pull()
    except Exception as e:  # noqa: BLE001
        print(
            f"  [카메라 경고] 프레임을 못 얻었다({type(e).__name__}: {e})"
            " — 시각 없이 답한다",
            flush=True,
        )
        _shutdown()
        return None
    _last = time.monotonic()
    if _idle_s() <= 0:
        _shutdown()
    else:
        _arm_watcher()
    return data
