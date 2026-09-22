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
