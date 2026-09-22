"""로봇 카메라 → 브라우저 WebRTC(H.264). `camera_in.py`(JPEG 스냅샷)와 파이프라인을
나눠 쓰지 않는다 — 배타는 `camera_in.note_rtc_active` 가 맡는다.

**파이프라인 하나를 시청자가 나눠 쓴다.** 첫 시청자에서 소스·인코더·페이로더·`tee` 를
세우고, 시청자마다 `tee → queue → webrtcbin` 분기를 붙인다. 마지막 시청자가 나가면
파이프라인을 NULL 로 내린다.

**PyGObject 함정**(`docs/lessons.md`, 스파이크 실측): offer 를 만들 때 `reply =
promise.get_reply()` 로 **붙잡고**, SDP 텍스트는 `set-local-description` 을 부르기
**전에** 뽑는다. 한 줄로 꺼내면 SDP 가 비거나(`t=0 0`) 프로세스가 로그 없이 죽는다.

기본값(스파이크 실측, 사회자 로봇 640x480@15fps 에서 전체 CPU +4.2%p):
`REACHY_CAMERA_STREAM_WIDTH/HEIGHT/FPS/KBPS` = 640/480/15/2000.
"""

import threading
from typing import Callable

import config

_ENCODER_LADDER = ("v4l2h264enc", "x264enc", "openh264enc")
_REQUIRED = ("rtph264pay", "h264parse", "webrtcbin")


def _default_find(name: str) -> bool:
    """실제 GStreamer 요소 조회 — 기본 구현. 테스트는 가짜 `find` 를 주입한다."""
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    if not Gst.is_initialized():
        Gst.init(None)
    return Gst.ElementFactory.find(name) is not None


class RtcStreamer:
    def __init__(self, send_rtc: Callable[[str, dict], None],
                 find: Callable[[str], bool] = _default_find,
                 warn: Callable[[str], None] = print,
                 on_error: Callable[[str], None] | None = None) -> None:
        self._send_rtc = send_rtc
        self._find = find
        self._warn = warn
        # 로봇→감독 `error{where:"camera"}` 를 보내는 자리(리뷰 I2). `warn` 은 터미널
        # 로그만 남기고 감독·대시보드에는 안 닿는다 — 이 콜백이 없으면
        # `CameraRelay.on_robot_error`(테스트도 있는 멀쩡한 경로)가 프로덕션에서
        # **한 번도** 안 불려, 대시보드 카메라 칸의 "사유" 가 실패해도 영원히
        # `reason: ""` 로 남는다(C1 과 같은 부류의 조용한 실패). 기본은 아무것도
        # 안 한다 — `main.py::make_camera_handlers` 가 `client.error("camera", …)`
        # 로 채운다.
        self._on_error = on_error or (lambda detail: None)
        self._pipe = None
        self._webrtcbins: dict[str, object] = {}
        self._queues: dict[str, object] = {}
        self._lock = threading.Lock()

    # ── 가능 여부 ─────────────────────────────────────────────────
    def available(self) -> bool:
        if config.get("REACHY_VISION", "1").lower() in ("0", "false", "no"):
            return False
        try:
            if not self._find(config.get("REACHY_CAMERA_SRC", "libcamerasrc").split()[0]):
                return False
            if self._encoder_name() is None:
                return False
            return all(self._find(n) for n in _REQUIRED)
        except Exception as exc:
            # `_find`(기본 `_default_find`)는 `import gi`·`Gst.init` 을 부른다 — 이
            # 저장소의 `pyproject.toml` 은 PyGObject 를 **Linux 전용**으로 선언한다,
            # 그러니 비-Linux/오설정 환경에서는 여기서 예외가 나는 게 실제로
            # 일어날 수 있는 일이다(리뷰 I4). `main.py` 의 caps 프로브
            # (`RtcStreamer(...).available()`)는 try/except 없이 이 값을 직접
            # 부르므로, 여기서 삼키지 않으면 **앱 기동 전체**가 죽는다 — 오디오
            # 경로가 장치를 못 찾으면 리스너 스레드 하나만 접는 것과 달리 훨씬
            # 나쁜 실패 모양이다. "카메라 없음" 으로 물러나는 것이 맞다.
            self._warn(
                f"  [카메라] available() 확인 중 오류({type(exc).__name__}: {exc}) "
                "— 카메라 없음으로 처리한다"
            )
            return False

    def _encoder_name(self) -> str | None:
        for name in _ENCODER_LADDER:
            if self._find(name):
                if name != "v4l2h264enc":
                    self._warn(
                        f"  [카메라] 하드웨어 H264 인코더가 없다 — {name} 로 물러난다(CPU 를 문다)"
                    )
                return name
        return None

    def _encoder_clause(self, encoder: str, fps: str, kbps: str) -> str:
        """인코더별 gst-launch 절. **`extra-controls` 는 V4L2 전용 속성이다** — 다른
        인코더에 붙이면 `Gst.parse_launch()` 가 그 자리에서 `no property "extra-controls"`
        로 깨진다(리뷰 실측, 이 맥에서 `x264enc` 로 재현됨). 속성 이름·단위는 이 맥에서
        `Gst.ElementFactory.make(name).list_properties()` 로 실측했다(`gst-inspect-1.0`
        바이너리가 이 venv 에 없어 PyGObject introspection 으로 대신함, gst-inspect 와
        같은 API):

            x264enc:     bitrate(kbit/sec, guint) · key-int-max(프레임 수, 0=자동)
            openh264enc: bitrate(bit/sec, guint)  · gop-size(프레임 수)
            v4l2h264enc: extra-controls 로만 노출(V4L2 컨트롤 문자열) — 그대로 둔다.

        목표는 인코더 사이에 정확히 같은 숫자가 아니라 **같은 결과**(해상도·fps·대략 같은
        비트레이트·1초 안팎의 키프레임 간격)다.
        """
        if encoder == "v4l2h264enc":
            return (
                f'{encoder} extra-controls="controls,repeat_sequence_header=1,'
                f'video_bitrate={int(kbps) * 1000},h264_i_frame_period={fps}"'
            )
        if encoder == "x264enc":
            # bitrate 는 x264enc 에서 kbit/sec 다 — REACHY_CAMERA_STREAM_KBPS 와 단위가 같다.
            return f"{encoder} bitrate={int(kbps)} key-int-max={fps}"
        if encoder == "openh264enc":
            # bitrate 는 openh264enc 에서 bit/sec 다 — v4l2h264enc 의 video_bitrate 와 같은 단위.
            return f"{encoder} bitrate={int(kbps) * 1000} gop-size={fps}"
        # 사다리에 없는 이름이 오면(방어적) V4L2 절 모양을 기본값으로 쓴다 — 여기 오면 이미
        # _encoder_name() 이 알려진 이름만 돌려주므로 실제로는 닿지 않는다.
        return (
            f'{encoder} extra-controls="controls,repeat_sequence_header=1,'
            f'video_bitrate={int(kbps) * 1000},h264_i_frame_period={fps}"'
        )

    # ── 파이프라인 조립 ───────────────────────────────────────────
    def _pipeline_str(self) -> str:
        src = config.get("REACHY_CAMERA_SRC", "libcamerasrc")
        w = config.get("REACHY_CAMERA_STREAM_WIDTH", "640")
        h = config.get("REACHY_CAMERA_STREAM_HEIGHT", "480")
        fps = config.get("REACHY_CAMERA_STREAM_FPS", "15")
        kbps = config.get("REACHY_CAMERA_STREAM_KBPS", "2000")
        encoder = self._encoder_name()
        source = (
            f"{src} ! video/x-raw,width={w},height={h},framerate={fps}/1,format=YUY2,"
            f"colorimetry=bt709,interlace-mode=progressive"
            if src.split()[0] == "libcamerasrc"
            else f"{src} ! video/x-raw,width={w},height={h},framerate={fps}/1"
        )
        return (
            f"{source} "
            f"! {self._encoder_clause(encoder, fps, kbps)} "
            f"! video/x-h264,stream-format=byte-stream,alignment=au,"
            f"level=(string)3.1,profile=(string)constrained-baseline "
            f"! h264parse ! rtph264pay config-interval=-1 pt=96 aggregate-mode=zero-latency "
            f"! application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000 "
            f"! tee name=camtee"
        )

    # ── 시청자 ────────────────────────────────────────────────────
    def start_viewer(self, viewer: str) -> None:
        import camera_in
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstWebRTC", "1.0")
        from gi.repository import Gst, GstWebRTC  # noqa: F401

        with self._lock:
            if viewer in self._webrtcbins:
                return
            if self._pipe is None:
                if not self.available():
                    msg = "카메라를 쓸 수 없다(available()=False)"
                    self._warn(f"  [카메라] 스트림을 열 수 없다({msg})")
                    self._on_error(msg)   # 리뷰 I2 — 감독/대시보드에도 사유를 준다
                    return
                try:
                    camera_in.close()
                    camera_in.note_rtc_active(True)
                    if not Gst.is_initialized():
                        Gst.init(None)
                    self._pipe = Gst.parse_launch(self._pipeline_str())
                    self._pipe.set_state(Gst.State.PLAYING)
                except Exception as exc:
                    # `Gst.parse_launch()` 가 이 인코더에 없는 속성을 만나면 여기서
                    # 터진다(`_encoder_clause` 의 `extra-controls` 결함이 실제로
                    # 났던 자리, 이제는 방어선이 하나 더 붙는다 — 리뷰 I2). 이미
                    # 켠 배타 플래그를 되돌린다 — 안 그러면 `camera_in` 의 JPEG
                    # 스냅샷 경로가 실패한 스트림 때문에 영영 막힌다.
                    self._warn(
                        f"  [카메라] 파이프라인을 못 열었다({type(exc).__name__}: {exc})"
                    )
                    self._on_error(f"파이프라인 실패: {type(exc).__name__}: {exc}")
                    self._pipe = None
                    camera_in.note_rtc_active(False)
                    return
            tee = self._pipe.get_by_name("camtee")
            queue = Gst.ElementFactory.make("queue")
            queue.set_property("leaky", 2)  # downstream — 느린 시청자가 다른 시청자를 안 막는다
            wb = Gst.ElementFactory.make("webrtcbin")
            wb.set_property("bundle-policy", "max-bundle")
            self._pipe.add(queue)
            self._pipe.add(wb)
            queue.link(wb)
            tee.link(queue)
            queue.sync_state_with_parent()
            wb.sync_state_with_parent()
            wb.connect("on-negotiation-needed", lambda e, v=viewer: self._make_offer(v, e))
            wb.connect("on-ice-candidate", lambda e, m, c, v=viewer: self._send_rtc(
                v, {"candidate": c, "sdpMLineIndex": m}))
            self._webrtcbins[viewer] = wb
            self._queues[viewer] = queue

    def stop_viewer(self, viewer: str) -> None:
        import camera_in
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        with self._lock:
            wb = self._webrtcbins.pop(viewer, None)
            if wb is None:
                return
            wb.set_state(Gst.State.NULL)
            self._pipe.remove(wb)
            queue = self._queues.pop(viewer, None)
            if queue is not None:
                # queue 의 sink 패드에 링크된 tee 의 요청(src) 패드 — 풀어주지 않으면
                # 남은 시청자가 있어 파이프라인을 통째로 내리지 않을 때 tee 에 고아로
                # 남는다(자원 누수 — 대시보드 재접속마다 쌓인다).
                sink_pad = queue.get_static_pad("sink")
                tee_pad = sink_pad.get_peer() if sink_pad is not None else None
                queue.set_state(Gst.State.NULL)
                self._pipe.remove(queue)
                if tee_pad is not None:
                    tee = self._pipe.get_by_name("camtee") if self._pipe is not None else None
                    if tee is not None:
                        tee.release_request_pad(tee_pad)
            if not self._webrtcbins:
                self._pipe.set_state(Gst.State.NULL)
                self._pipe = None
                camera_in.note_rtc_active(False)

    def stop_all(self) -> None:
        for viewer in list(self._webrtcbins):
            self.stop_viewer(viewer)

    def on_remote(self, viewer: str, payload: dict) -> None:
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstSdp", "1.0")
        gi.require_version("GstWebRTC", "1.0")
        from gi.repository import Gst, GstSdp, GstWebRTC

        wb = self._webrtcbins.get(viewer)
        if wb is None:
            return
        if "sdp" in payload:
            ok, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(payload["sdp"]["sdp"].encode(), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            wb.emit("set-remote-description", answer, Gst.Promise.new())
        elif "candidate" in payload and payload["candidate"]:
            wb.emit("add-ice-candidate", payload.get("sdpMLineIndex") or 0, payload["candidate"])

    # ── 내부 ──────────────────────────────────────────────────────
    def _make_offer(self, viewer: str, webrtcbin) -> None:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        def on_offer(promise, _):
            try:
                # **reply 를 붙잡는다.** 한 줄로 꺼내면 SDP 메모리가 풀린다(PyGObject 함정).
                reply = promise.get_reply()
                offer = reply.get_value("offer")
                text = offer.sdp.as_text()   # set-local-description **전에** 뽑는다.
                webrtcbin.emit("set-local-description", offer, Gst.Promise.new())
                self._send_rtc(viewer, {"sdp": {"type": "offer", "sdp": text}})
            except Exception as exc:
                # GStreamer 시그널 콜백 안의 예외는 GLib 메인루프가 삼키고 stderr 에만
                # 찍는다 — 감독/대시보드는 절대 못 본다(리뷰 I2, "negotiation exception").
                self._warn(f"  [카메라] offer 협상 실패({viewer}): {type(exc).__name__}: {exc}")
                self._on_error(f"offer 협상 실패: {type(exc).__name__}: {exc}")

        webrtcbin.emit("create-offer", None, Gst.Promise.new_with_change_func(on_offer, None))
