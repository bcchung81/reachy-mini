"""감정 모션의 자체 사운드(`.ogg`)를 우리 재생 경로로 가져온다.

**왜 SDK 에 안 맡기나.** `play_move(sound=True)` 는 `media_manager.play_sound()` 로
사운드를 내는데, 우리는 마이크를 직접 열려고 `request_media_backend="no_media"` 를
쓴다(`main.py`). 그러면 `MediaManager.audio` 가 None 이라 사운드가 **경고 한 줄만
남기고 조용히 사라진다** — 감정 라이브러리 85개 중 84개, 우리가 쓰는 17개 전부가
사운드를 갖고 있으므로 전부 무음이 된다.

옮기는 편이 원래보다 낫다. 우리 `Speaker` 를 타면 사운드가
  · 에코 프로브(`tts.EchoProbeTap`)와 출력 레벨 기록(`_note_output`)을 지나고
  · `speaker.speaking` 으로 정확히 사운드 길이만큼 마이크 게이팅을 잡는다
전에는 게이팅이 **모션 길이**를 따라가서, 사운드가 모션보다 긴 9개 모션에서
(최대 `welcoming1` +1.43초) 마이크가 자기 발성 꼬리를 주웠다.

**길이 정책.** 리액션 발성은 2~12초라 답변 앞에 통째로 붙이면 대화가 그만큼 늦는다.
발성의 원래 역할은 LLM 지연 구간을 메우는 것이므로 앞부분만 쓰고 페이드아웃한다.
공연(춤)은 요청 자체가 목적이라 전체를 재생한다.
"""

import os
import threading

import numpy as np

# 리액션 발성을 이만큼만 쓴다(초). LLM 첫 절이 도착하는 시간과 맞춰 둔 값이다.
REACTION_S = float(os.environ.get("REACHY_MOTION_SOUND_S", "1.2"))
# 자른 끝을 페이드아웃한다 — 발성이 뚝 끊기면 고장난 것처럼 들린다.
FADE_S = float(os.environ.get("REACHY_MOTION_SOUND_FADE", "0.25"))
# 통째로 끄는 스위치. 모터 소음 실험 등에서 소리를 완전히 죽이고 싶을 때.
ENABLED = os.environ.get("REACHY_MOTION_SOUND", "1").lower() not in ("0", "false", "no")

_cache: dict[tuple[str, int, float], bytes] = {}
_lock = threading.Lock()


def _decode(path: str, rate: int) -> bytes | None:
    """`.ogg` → s16le mono PCM. GStreamer 가 이미 있으므로 새 의존성이 없다.

    실패하면 None — 사운드가 없다고 앱이 죽으면 안 된다.
    """
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        # **경로를 파이프라인 문자열에 넣지 않는다.** 공백·따옴표가 섞이면
        # `parse_launch` 의 인용 규칙에 걸려 조용히 기동에 실패한다(실측).
        # 속성으로 넘기면 그런 문제가 없다.
        pipe = Gst.parse_launch(
            "filesrc name=src ! decodebin ! audioconvert ! audioresample "
            f"! audio/x-raw,format=S16LE,channels=1,rate={rate},layout=interleaved "
            "! appsink name=sink sync=false max-buffers=0"
        )
        pipe.get_by_name("src").set_property("location", str(path))
    except Exception as e:  # noqa: BLE001
        print(f"  [모션 사운드] 디코딩 파이프라인 실패: {e}", flush=True)
        return None

    sink = pipe.get_by_name("sink")
    sink.set_property("emit-signals", False)
    # decodebin 은 pad 가 늦게 붙어 ASYNC 를 돌려준다 — 그건 정상이다.
    if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        pipe.set_state(Gst.State.NULL)
        print(f"  [모션 사운드] 디코딩을 시작하지 못했다: {path}", flush=True)
        return None

    out: list[bytes] = []
    try:
        while True:
            sample = sink.emit("pull-sample")
            if sample is None:  # EOS
                break
            buf = sample.get_buffer()
            ok, info = buf.map(Gst.MapFlags.READ)
            if not ok:
                continue
            try:
                out.append(bytes(info.data))
            finally:
                buf.unmap(info)
    finally:
        pipe.set_state(Gst.State.NULL)
    return b"".join(out)


def _trim(pcm: bytes, rate: int, seconds: float) -> bytes:
    """앞 `seconds` 만 남기고 끝을 페이드아웃한다. 0 이하면 자르지 않는다."""
    if seconds <= 0:
        return pcm
    keep = int(seconds * rate) * 2
    if keep >= len(pcm):
        return pcm
    a = np.frombuffer(pcm[:keep], dtype=np.int16).astype(np.float32)
    n = min(int(FADE_S * rate), a.size)
    if n > 0:
        a[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    return a.astype(np.int16).tobytes()


def load(path, rate: int, full: bool = False) -> bytes | None:
    """모션 사운드를 재생 가능한 PCM 으로 준다. 없거나 실패하면 None.

    `full=True` 면 자르지 않는다(공연). 결과는 캐시한다 — 같은 모션이 반복돼도
    디코딩은 한 번뿐이다.
    """
    if not ENABLED or path is None:
        return None
    seconds = 0.0 if full else REACTION_S
    key = (str(path), rate, seconds)
    with _lock:
        if key in _cache:
            return _cache[key]
    pcm = _decode(str(path), rate)
    if not pcm:
        return None
    trimmed = _trim(pcm, rate, seconds)
    with _lock:
        _cache[key] = trimmed
    return trimmed
