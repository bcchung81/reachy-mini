import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from animator import SwayState


def _envelope(st: SwayState, speaking: bool, steps: int) -> float:
    for _ in range(steps):
        st.step(dt=0.02, speaking=speaking)
    return st.env


def test_말할때_포락선이_올라간다():
    st = SwayState()
    assert st.env == 0.0
    assert _envelope(st, speaking=True, steps=50) > 0.8


def test_멈추면_포락선이_내려간다():
    st = SwayState()
    _envelope(st, speaking=True, steps=50)
    assert _envelope(st, speaking=False, steps=100) < 0.05


def test_조용할때는_움직임이_거의_없다():
    st = SwayState()
    for _ in range(200):
        st.step(dt=0.02, speaking=False)
    off = st.offsets()
    # 호흡만 남는다 — 회전은 1도 미만, 병진은 2mm 미만
    assert abs(off.pitch_deg) < 1.0
    assert abs(off.yaw_deg) < 1.0
    assert abs(off.roll_deg) < 1.0
    assert abs(off.z_mm) < 2.0


def test_말할때는_눈에_띄게_움직인다():
    st = SwayState()
    seen = {"yaw": 0.0, "pitch": 0.0}
    for _ in range(400):  # 8초
        st.step(dt=0.02, speaking=True)
        off = st.offsets()
        seen["yaw"] = max(seen["yaw"], abs(off.yaw_deg))
        seen["pitch"] = max(seen["pitch"], abs(off.pitch_deg))
    assert seen["yaw"] > 2.0
    assert seen["pitch"] > 1.5


def test_안전_한계를_넘지_않는다():
    # 머리 pitch/roll 은 ±40도에서 클램프된다. 근처에도 가지 않아야 한다.
    st = SwayState()
    for _ in range(2000):
        st.step(dt=0.02, speaking=True)
        off = st.offsets()
        assert abs(off.pitch_deg) < 15.0
        assert abs(off.roll_deg) < 15.0
        assert abs(off.yaw_deg) < 20.0
        assert abs(off.antenna_deg) < 30.0
