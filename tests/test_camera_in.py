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


def test_기본은_매번_닫는다(monkeypatch):
    """CM4 콜드 스타트를 아직 안 쟀다. 재기 전까지는 유휴 비용 0 쪽으로 둔다 —
    상시 켜두면 부하 2.4 에서 데몬 연결(5초)이 실패한 전례가 있다."""
    _linux(monkeypatch)
    closed = []
    monkeypatch.setattr(camera_in, "_open", lambda: "PIPE")
    monkeypatch.setattr(camera_in, "_pull", lambda: JPEG)
    monkeypatch.setattr(camera_in, "_shutdown", lambda: closed.append(1))
    camera_in.grab_jpeg()
    assert closed == [1]


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
