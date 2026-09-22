"""CameraRelay — 순수 로직. 네트워크·감독 없이 콜백만으로 시험한다."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.camera import CameraRelay


def _relay():
    sent = []  # (role, type, fields)
    return CameraRelay(send_robot=lambda role, t, f: sent.append((role, t, f)), warn=lambda m: None), sent


def test_시청자도_로봇도_없으면_꺼진_상태다():
    relay, sent = _relay()
    assert relay.snapshot()["mc"] == {"available": False, "enabled": True, "reason": "OFFLINE"}


def test_로봇이_hello로_카메라_능력을_알리면_available이_된다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    assert relay.snapshot()["mc"]["available"] is True
    assert relay.snapshot()["mc"]["reason"] == ""


def test_caps에_camera가_없으면_사유를_보인다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", [])
    assert "카메라 없음" in relay.snapshot()["mc"]["reason"]


def test_시청자가_붙으면_가능한_로봇에게만_camera_on을_보낸다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.on_robot_hello("docent", [])  # 능력 없음
    vid = relay.add_viewer(lambda ev: None)
    assert ("mc", "camera", {"viewer": vid, "on": True}) in sent
    assert not any(r == "docent" and t == "camera" for r, t, f in sent)


def test_같은_상태로는_다시_보내지_않는다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.add_viewer(lambda ev: None)
    n = len(sent)
    relay.on_robot_hello("mc", ["camera"])  # 다시 hello — 상태는 이미 on
    assert len(sent) == n


def test_운영자가_끄면_on을_끄고_시청자에게_bye를_보낸다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    events = []
    vid = relay.add_viewer(events.append)
    relay.toggle("mc")  # 끔
    assert ("mc", "camera", {"viewer": vid, "on": False}) in sent
    assert {"kind": "rtc", "role": "mc", "bye": True} in events
    assert relay.snapshot()["mc"]["reason"] == "카메라 꺼짐"


def test_로봇_offer가_그_시청자에게만_간다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    a_events, b_events = [], []
    va = relay.add_viewer(a_events.append)
    vb = relay.add_viewer(b_events.append)
    relay.on_robot_rtc("mc", {"viewer": va, "sdp": {"type": "offer", "sdp": "v=0"}})
    assert {"kind": "rtc", "role": "mc", "sdp": {"type": "offer", "sdp": "v=0"}} in a_events
    assert not any(e.get("sdp") for e in b_events)


def test_모르는_시청자에게_온_rtc는_버린다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.on_robot_rtc("mc", {"viewer": "없는id", "sdp": {"type": "offer", "sdp": "v=0"}})  # 죽지 않는다


def test_시청자의_answer는_그_로봇에게만_간다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.on_robot_hello("docent", ["camera"])
    vid = relay.add_viewer(lambda ev: None)
    sent.clear()
    relay.on_viewer_rtc(vid, {"role": "mc", "sdp": {"type": "answer", "sdp": "v=0"}})
    assert sent == [("mc", "rtc", {"viewer": vid, "sdp": {"type": "answer", "sdp": "v=0"}})]


def test_너무_큰_sdp는_버린다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    vid = relay.add_viewer(lambda ev: None)
    sent.clear()
    relay.on_viewer_rtc(vid, {"role": "mc", "sdp": {"type": "answer", "sdp": "x" * 70000}})
    assert sent == []


def test_시청자가_떠나면_로봇의_그_분기를_끈다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    vid = relay.add_viewer(lambda ev: None)
    sent.clear()
    relay.remove_viewer(vid)
    assert ("mc", "camera", {"viewer": vid, "on": False}) in sent


def test_로봇이_끊기면_시청자에게_bye를_보낸다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    events = []
    relay.add_viewer(events.append)
    relay.on_robot_disconnect("mc")
    assert {"kind": "rtc", "role": "mc", "bye": True} in events
    assert relay.snapshot()["mc"]["available"] is False


def test_오류는_다음에_켤_때까지_사유에_남는다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.add_viewer(lambda ev: None)
    relay.on_robot_error("mc", "파이프라인 실패")
    assert "파이프라인 실패" in relay.snapshot()["mc"]["reason"]
    relay.toggle("mc")   # 끔
    relay.toggle("mc")   # 다시 켬
    assert "파이프라인 실패" not in relay.snapshot()["mc"]["reason"]
