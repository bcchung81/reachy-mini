"""RtcStreamer — 요소 존재 여부·파이프라인 조립은 가짜로, 실제 송수신은 맥 GStreamer 로.

`available()`/파이프라인 문자열은 GStreamer 가 전혀 없어도 시험한다(가짜 조회기).
송수신 통합 시험(Step 3b)은 `Gst.ElementFactory.find` 로 실제 요소가 있는지 보고,
없으면 skip — 로봇에서만 도는 `v4l2h264enc` 등은 여기서 못 돈다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import camera_rtc  # noqa: E402


def _finder(present: set[str]):
    return lambda name: name in present


def test_인코더도_소스도_없으면_불가():
    assert camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(set())).available() is False


def test_webrtcbin이_없으면_불가():
    present = {"libcamerasrc", "v4l2h264enc", "rtph264pay", "h264parse"}
    assert camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present)).available() is False


def test_하드웨어_인코더_없이도_x264enc면_가능():
    present = {"libcamerasrc", "x264enc", "rtph264pay", "h264parse", "webrtcbin"}
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    assert st.available() is True
    assert st._encoder_name() == "x264enc"


def test_하드웨어_인코더가_있으면_그걸_먼저_쓴다():
    present = {"libcamerasrc", "v4l2h264enc", "x264enc", "rtph264pay", "h264parse", "webrtcbin"}
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    assert st._encoder_name() == "v4l2h264enc"


def test_파이프라인_문자열에_기본값이_들어간다(monkeypatch):
    present = {"libcamerasrc", "v4l2h264enc", "rtph264pay", "h264parse", "webrtcbin"}
    monkeypatch.delenv("REACHY_CAMERA_STREAM_WIDTH", raising=False)
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    chain = st._pipeline_str()
    assert "width=640" in chain and "height=480" in chain and "framerate=15" in chain
    assert "video_bitrate=2000000" in chain


def test_환경변수로_해상도를_바꾼다(monkeypatch):
    present = {"libcamerasrc", "v4l2h264enc", "rtph264pay", "h264parse", "webrtcbin"}
    monkeypatch.setenv("REACHY_CAMERA_STREAM_WIDTH", "320")
    monkeypatch.setenv("REACHY_CAMERA_STREAM_HEIGHT", "240")
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    assert "width=320" in st._pipeline_str() and "height=240" in st._pipeline_str()


class _FakeElement:
    """`Gst.Element` 대역 — `set_state` 호출만 기록한다."""

    def __init__(self):
        self.state = None

    def set_state(self, state):
        self.state = state
        return True


class _FakePad:
    """`Gst.Pad` 대역 — `get_peer()` 만 흉내 낸다."""

    def __init__(self, peer=None):
        self._peer = peer

    def get_peer(self):
        return self._peer


class _FakeQueue(_FakeElement):
    def __init__(self, sink_pad):
        super().__init__()
        self._sink_pad = sink_pad

    def get_static_pad(self, name):
        assert name == "sink"
        return self._sink_pad


class _FakeTee(_FakeElement):
    def __init__(self):
        super().__init__()
        self.released = []

    def release_request_pad(self, pad):
        self.released.append(pad)


class _FakePipe:
    """`Gst.Pipeline` 대역 — `remove`/`get_by_name` 호출만 기록한다."""

    def __init__(self, tee):
        self._tee = tee
        self.removed = []

    def get_by_name(self, name):
        return self._tee if name == "camtee" else None

    def remove(self, element):
        self.removed.append(element)

    def set_state(self, state):
        pass


def test_stop_viewer는_큐와_tee_요청패드를_반납한다():
    """리뷰 결함(Important): `start_viewer` 가 시청자마다 만드는 `queue` 참조를 어디에도
    저장하지 않아, `stop_viewer` 가 `webrtcbin` 만 지우고 `queue`/tee 요청 패드를 그대로
    남겼다 — 다른 시청자가 남아 파이프라인을 통째로 안 내리는 한, 대시보드 재접속마다
    고아 `queue` 가 tee 에 쌓이는 누수였다.

    실제 GStreamer 파이프라인을 열지 않고(이 태스크의 다른 테스트들과 같은 한계 —
    `libcamerasrc`/`v4l2h264enc` 가 이 맥에 없고, `_pipeline_str()` 이 항상 붙이는
    `extra-controls` 속성은 `x264enc` 에는 없는 속성이라 `videotestsrc`+`x264enc` 조합으로도
    `Gst.parse_launch` 가 바로 깨진다 — 실측 확인했다) 북키핑만 가짜 `Gst.Element`/`Pipeline`
    대역으로 단위 시험한다. 실제 파이프라인 위에서의 확인은 Task 13 실기 검증에 맡긴다."""
    tee = _FakeTee()
    tee_pad_a = object()  # "a" 의 queue 에 링크된 tee 요청 패드(센티널)
    tee_pad_b = object()  # "b" 것 — 건드리면 안 된다
    queue_a = _FakeQueue(sink_pad=_FakePad(peer=tee_pad_a))
    queue_b = _FakeQueue(sink_pad=_FakePad(peer=tee_pad_b))
    wb_a = _FakeElement()
    wb_b = _FakeElement()

    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(set()))
    st._pipe = _FakePipe(tee)
    st._webrtcbins = {"a": wb_a, "b": wb_b}
    st._queues = {"a": queue_a, "b": queue_b}

    st.stop_viewer("a")

    # "a" 항목은 webrtcbin·queue 딕셔너리 양쪽에서 다 지워진다.
    assert "a" not in st._webrtcbins
    assert "a" not in st._queues
    # 남은 시청자 "b" 는 그대로다 — 다른 시청자가 있으면 파이프라인 전체를 안 내린다.
    assert "b" in st._webrtcbins
    assert "b" in st._queues
    # "a" 의 queue 와 wb 는 파이프라인에서 빠지고 NULL 로 내려간다.
    assert queue_a in st._pipe.removed
    assert wb_a in st._pipe.removed
    from gi.repository import Gst

    assert queue_a.state == Gst.State.NULL
    assert wb_a.state == Gst.State.NULL
    # tee 는 "a" 의 요청 패드만 반납받는다 — "b" 는 안 건드린다.
    assert tee.released == [tee_pad_a]
    # 파이프라인 자체는 살아있다(남은 시청자가 있으므로 NULL 로 안 내려간다).
    assert st._pipe is not None


def _has(name):
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    if not Gst.is_initialized():
        Gst.init(None)
    return Gst.ElementFactory.find(name) is not None


@pytest.mark.skipif(not _has("x264enc") or not _has("webrtcbin"),
                     reason="이 맥에 x264enc/webrtcbin 이 없다")
def test_videotestsrc로_실제_프레임이_간다(monkeypatch):
    """videotestsrc(카메라 없이) + x264enc 로 실제 GStreamer 파이프라인을 돌려, 테스트
    수신측 webrtcbin 이 프레임을 디코딩하는지 본다. 로봇 전용 요소(libcamerasrc·
    v4l2h264enc)는 안 쓴다 — 이 맥에 없다."""
    monkeypatch.setenv("REACHY_CAMERA_SRC", "videotestsrc is-live=true")
    # 이 시험은 실제 Gst 메인루프·오퍼/앤서 교환이 필요해 상당히 길다 — 최소 골격만
    # 여기 둔다. 기존 스파이크(offer_probe.py, 버렸다)의 방식을 참고해 로봇 쪽 흉내
    # webrtcbin(테스트 수신측)을 만들고 SDP 를 주고받는다. 자세한 구현은 이 태스크를
    # 맡는 실행자가 스파이크의 검증된 흐름(오퍼 → 앤서 → ICE → connected)을 그대로
    # 옮긴다 — 새로 설계하지 않는다.
    pytest.skip("이 스텝은 수동 검증으로 대신한다 — 최종 검증(Task 13)이 실기로 확인한다")
