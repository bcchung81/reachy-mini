"""카메라 프레임 캡처 — GStreamer 로 잡고 JPEG 까지 만든다(cv2·PIL 불필요).

시뮬(macOS)에는 `libcamerasrc` 가 없다. **조용히** 시각 없이 진행해야 한다 —
시뮬에서 카메라를 못 여는 것은 정상이라 경고를 쏟으면 개발이 시끄러워진다.
반대로 실기(Linux)에서 실패하면 소리 내서 알린다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import camera_in  # noqa: E402
import config  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0frame"


@pytest.fixture(autouse=True)
def _reset():
    camera_in._pipe = None
    yield
    camera_in._pipe = None


def _linux(monkeypatch):
    monkeypatch.setattr(camera_in.platform, "system", lambda: "Linux")


def test_비리눅스에서는_조용히_없음(monkeypatch, capsys):
    monkeypatch.setattr(camera_in.platform, "system", lambda: "Darwin")
    assert camera_in.grab_jpeg() is None
    assert capsys.readouterr().out == "", "시뮬에서 경고를 쏟으면 안 된다"


def test_스위치를_끄면_열지도_않는다(monkeypatch):
    _linux(monkeypatch)
    monkeypatch.setattr(config, "get", lambda n, d: "0" if n == "REACHY_VISION" else d)
    opened = []
    monkeypatch.setattr(camera_in, "_open", lambda: opened.append(1))
    assert camera_in.grab_jpeg() is None
    assert opened == []


def test_프레임을_돌려준다(monkeypatch):
    _linux(monkeypatch)
    monkeypatch.setattr(camera_in, "_open", lambda: "PIPE")
    monkeypatch.setattr(camera_in, "_pull", lambda: JPEG)
    assert camera_in.grab_jpeg() == JPEG


def test_실기에서_실패하면_경고하고_시각없이_간다(monkeypatch, capsys):
    """대화를 끊지 않는다 — 폴백 사다리 원칙. 다만 조용히 물러나지 않는다."""
    _linux(monkeypatch)

    def boom():
        raise RuntimeError("libcamerasrc 없음")

    monkeypatch.setattr(camera_in, "_open", boom)
    assert camera_in.grab_jpeg() is None
    assert "카메라" in capsys.readouterr().out


def test_유휴_0이면_매번_닫는다(monkeypatch):
    """부하가 걱정되는 환경을 위한 탈출구. 대신 매 질문이 1.13s 를 문다."""
    _linux(monkeypatch)
    monkeypatch.setattr(config, "get",
                        lambda n, d: "0" if n == "REACHY_CAMERA_IDLE_S" else d)
    closed = []
    monkeypatch.setattr(camera_in, "_open", lambda: "PIPE")
    monkeypatch.setattr(camera_in, "_pull", lambda: JPEG)
    monkeypatch.setattr(camera_in, "_shutdown", lambda: closed.append(1))
    camera_in.grab_jpeg()
    assert closed == [1]


def test_기본값은_열어_둔다(monkeypatch):
    """실측(2026-09-09, CM4): 열고 닫으면 1.13s, 열어 두면 0.03s 다. 기본은
    연속 질문이 빠른 쪽이고, 유휴 감시가 20초 뒤에 닫아 부하를 되돌린다."""
    _linux(monkeypatch)
    closed = []
    monkeypatch.setattr(camera_in, "_open", lambda: "PIPE")
    monkeypatch.setattr(camera_in, "_pull", lambda: JPEG)
    monkeypatch.setattr(camera_in, "_shutdown", lambda: closed.append(1))
    camera_in.grab_jpeg()
    assert closed == [], "기본값에서 매번 닫으면 연속 질문이 매번 1.13s 를 문다"


def test_유휴시간을_주면_열어_둔다(monkeypatch):
    _linux(monkeypatch)
    monkeypatch.setattr(config, "get",
                        lambda n, d: "60" if n == "REACHY_CAMERA_IDLE_S" else d)
    opened, closed = [], []
    monkeypatch.setattr(camera_in, "_open", lambda: opened.append(1) or "PIPE")
    monkeypatch.setattr(camera_in, "_pull", lambda: JPEG)
    monkeypatch.setattr(camera_in, "_shutdown", lambda: closed.append(1))
    camera_in.grab_jpeg()
    camera_in.grab_jpeg()
    assert closed == [], "유휴시간 안에서는 닫지 않는다"
    assert opened == [1], "두 번째 호출은 열려 있는 것을 재사용한다"


def test_유휴시간이_지나면_스스로_닫는다(monkeypatch):
    """열어두면 캡처가 1.13s → 0.03s 로 빨라지지만(실측 2026-09-09) CM4 부하가
    약 반 코어 오른다(1.69 → 2.07). 부하 2.4 에서 데몬 연결(5초)이 실패한 전례가
    있어 **계속 열어둘 수 없다.** 유휴 시간이 지나면 스스로 닫아야 한다."""
    import time as _t
    _linux(monkeypatch)
    monkeypatch.setattr(config, "get",
                        lambda n, d: "0.2" if n == "REACHY_CAMERA_IDLE_S" else d)
    closed = []
    monkeypatch.setattr(camera_in, "_open", lambda: "PIPE")
    monkeypatch.setattr(camera_in, "_pull", lambda: JPEG)
    monkeypatch.setattr(camera_in, "_shutdown", lambda: closed.append(1))
    camera_in.grab_jpeg()
    end = _t.time() + 5
    while not closed and _t.time() < end:
        _t.sleep(0.05)
    assert closed == [1], "유휴 시간이 지났는데 닫히지 않았다"
