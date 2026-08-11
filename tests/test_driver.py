"""단일 컨트롤 루프 — 공식 `skills/control-loops.md` 규칙의 박제.

> One control loop, one place calling `set_target()` … **Never call `set_target()`
> from multiple threads.**

예전 구조는 이걸 어겼다: `Animator` 스레드가 50 Hz 로 `set_target` 을 쓰고,
`MotionPlayer` 스레드가 `play_move`(내부 100 Hz `set_target_*`)를 돌렸다.
막는 것은 `if self._is_busy()` 한 줄이었는데 검사와 쓰기가 원자적이 아니었다.
"""

import pathlib
import sys
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from driver import RobotDriver, _blend_pose, _minjerk  # noqa: E402


class RecordingMini:
    """set_target 호출을 **어느 스레드에서 왔는지와 함께** 기록한다."""

    def __init__(self):
        self.calls: list[tuple[int, object, object, object]] = []
        self._lock = threading.Lock()

    def set_target(self, head=None, antennas=None, body_yaw=None):
        with self._lock:
            self.calls.append((threading.get_ident(), head, antennas, body_yaw))

    @property
    def threads(self) -> set[int]:
        with self._lock:
            return {t for t, *_ in self.calls}

    def snapshot(self):
        with self._lock:
            return list(self.calls)


class FakeMove:
    """머리를 pitch 로 크게 기울인 채 유지하는 모션 — sway 와 확실히 구분된다."""

    def __init__(self, duration=0.4, pitch_deg=20.0):
        self.duration = duration
        self.sound_path = None
        self._pitch = np.deg2rad(pitch_deg)

    def evaluate(self, t):
        c, s = np.cos(self._pitch), np.sin(self._pitch)
        head = np.eye(4)
        head[:3, :3] = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        return head, np.array([1.0, -1.0]), 0.5


def _pitch_of(head) -> float:
    """4x4 에서 pitch(도)를 뽑는다 — 위 FakeMove 의 형태 기준."""
    return float(np.rad2deg(np.arcsin(np.clip(head[0, 2], -1.0, 1.0))))


def _run(driver, seconds: float):
    driver.start()
    try:
        time.sleep(seconds)
    finally:
        driver.stop()


# ── 규칙: 쓰는 스레드는 하나 ────────────────────────────────────


def test_모션_중에도_로봇에_쓰는_스레드는_하나뿐이다():
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: False, rate_hz=200.0)
    d.start()
    try:
        time.sleep(0.1)          # sway 만 도는 구간
        d.play(FakeMove(duration=0.2))
        time.sleep(0.35)         # 모션 + 복귀 구간
    finally:
        d.stop()
    assert len(mini.threads) == 1, f"쓰는 스레드가 {len(mini.threads)}개다"
    assert mini.calls, "루프가 아무것도 쓰지 않았다"


def test_계속_목표를_보낸다():
    """'illusion of life' — 유휴에도 목표 송신이 끊기면 안 된다."""
    mini = RecordingMini()
    _run(RobotDriver(mini, lambda: False, rate_hz=100.0), 0.3)
    assert len(mini.calls) > 15, f"100Hz 인데 0.3초에 {len(mini.calls)}회뿐"


# ── primary / secondary 합성 ────────────────────────────────────


def test_모션이_sway_를_이긴다():
    """모션이 도는 동안에는 sway 가 얹히지 않는다 — 겹치면 서로 밀어낸다."""
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: True, rate_hz=200.0)  # 말하는 중 = sway 최대
    d.start()
    try:
        d.play(FakeMove(duration=0.5), blend_s=0.05)
        time.sleep(0.3)
        mid = mini.snapshot()[-1]
    finally:
        d.stop()
    assert abs(_pitch_of(mid[1]) - 20.0) < 1.0, "모션 자세가 안 나온다(sway 가 이겼다)"
    assert np.allclose(mid[2], [1.0, -1.0], atol=0.05)
    assert abs(mid[3] - 0.5) < 0.05


def test_모션이_끝나면_sway_로_돌아온다():
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: False, rate_hz=200.0)
    d.start()
    try:
        d.play(FakeMove(duration=0.1), blend_s=0.02)
        time.sleep(0.5)  # 모션 + 복귀 블렌드가 끝나기에 충분
        assert d.playing is False
        last = mini.snapshot()[-1]
    finally:
        d.stop()
    # 호흡만 남는다 — 모션의 20도와는 확실히 다르다
    assert abs(_pitch_of(last[1])) < 3.0


def test_취소_직후에도_한_틱에_튀지_않는다():
    """cancel() 이 primary 만 지우면 다음 틱(10ms)에 sway 원점이 그대로 꽂힌다 —
    ±20도 모션 자세에서의 스냅이고 실기에서는 눈에 보이는 경련이다(리뷰 확인:
    자연 종료 경로만 복귀 블렌드를 무장하고 있었다). 취소도 같은 블렌드를 타야 한다.
    """
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: False, rate_hz=200.0)
    d.start()
    try:
        d.play(FakeMove(duration=5.0, pitch_deg=20.0), blend_s=0.02)
        time.sleep(0.2)  # 모션 자세(+20도)에 도달
        d.cancel()
        time.sleep(0.35)  # 복귀 블렌드 구간 전체를 관찰
        seq = [_pitch_of(c[1]) for c in mini.snapshot()[-60:]]
    finally:
        d.stop()
    jump = max(abs(b - a) for a, b in zip(seq, seq[1:]))
    assert jump < 5.0, f"취소 직후 한 틱에 {jump:.1f}도가 튀었다(복귀 블렌드 없음)"
    assert abs(seq[-1]) < 3.0, "블렌드가 끝났는데 sway 로 돌아오지 않았다"


def test_취소하면_다음_틱부터_모션이_사라진다():
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: False, rate_hz=200.0)
    d.start()
    try:
        d.play(FakeMove(duration=5.0), blend_s=0.02)
        time.sleep(0.15)
        assert d.playing is True
        d.cancel()
        assert d.playing is False
        time.sleep(0.4)  # 복귀 블렌드
        last = mini.snapshot()[-1]
    finally:
        d.stop()
    assert abs(_pitch_of(last[1])) < 3.0, "취소했는데 모션 자세가 남아 있다"


def test_대기_모션_여부를_알려준다():
    """응답 모션이 대기 모션을 밀어낼지 판단하는 근거."""
    d = RobotDriver(RecordingMini(), lambda: False, rate_hz=200.0)
    d.play(FakeMove(), idle=True)
    assert d.playing and d.playing_idle
    d.play(FakeMove(), idle=False)
    assert d.playing and not d.playing_idle


# ── 블렌드 ─────────────────────────────────────────────────────


def test_블렌드가_유효한_회전행렬을_유지한다():
    """행렬을 그냥 선형보간하면 회전행렬이 아니게 돼 IK 가 엉뚱한 자세를 낸다."""
    a = np.eye(4)
    b = FakeMove(pitch_deg=35.0).evaluate(0.0)[0]
    for s in np.linspace(0, 1, 11):
        R = _blend_pose(a, b, float(s))[:3, :3]
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-9), f"s={s}: 직교하지 않는다"
        assert abs(np.linalg.det(R) - 1.0) < 1e-9, f"s={s}: det != 1"


def test_블렌드_양끝이_정확하다():
    a = np.eye(4)
    b = FakeMove(pitch_deg=35.0).evaluate(0.0)[0]
    assert np.allclose(_blend_pose(a, b, 0.0), a, atol=1e-9)
    assert np.allclose(_blend_pose(a, b, 1.0), b, atol=1e-9)


def test_블렌드가_범위를_살짝_벗어난_s_를_견딘다():
    """호출부가 나눗셈으로 s 를 만들어 1e-17 만큼 범위를 벗어난다 — 실측으로
    `Interpolation times must be within the range [0.0, 1.0]` 를 재현했고,
    그 프레임이 통째로 날아갔다."""
    a = np.eye(4)
    b = FakeMove(pitch_deg=35.0).evaluate(0.0)[0]
    assert np.allclose(_blend_pose(a, b, -1e-17), a, atol=1e-9)
    assert np.allclose(_blend_pose(a, b, 1.0 + 1e-16), b, atol=1e-9)
    # 확실히 벗어난 값도 외삽하지 않고 끝값으로 눌린다
    assert np.allclose(_blend_pose(a, b, -0.5), a, atol=1e-9)
    assert np.allclose(_blend_pose(a, b, 1.5), b, atol=1e-9)


def test_minjerk_는_양끝에서_속도가_0():
    assert _minjerk(0.0) == 0.0
    assert abs(_minjerk(1.0) - 1.0) < 1e-12
    assert _minjerk(0.001) < 1e-7   # 시작에서 거의 안 움직인다
    assert 1.0 - _minjerk(0.999) < 1e-7
    # 단조 증가
    xs = [_minjerk(x) for x in np.linspace(0, 1, 50)]
    assert all(b >= a for a, b in zip(xs, xs[1:]))


def test_진입_블렌드의_출발_자세는_첫_틱에_고정된다():
    """매 틱 '직전 실제 자세'에서 섞으면 그 자세가 이미 목표 쪽으로 움직인 값이라
    복리로 겹쳐 실효 블렌드가 blend_s 보다 짧아진다. 출발 자세는 스냅샷이어야
    한다 — 이탈 블렌드(release_from)와 대칭으로."""
    from driver import _Primary

    d = RobotDriver(RecordingMini(), lambda: False)  # start 하지 않는다 — 직접 평가
    d._last_head = np.eye(4)
    prim = _Primary(FakeMove(duration=1.0, pitch_deg=20.0), t0=0.0, blend_s=1.0, idle=False)

    first = d._eval_primary(prim, now=0.25)
    # 루프가 흘러 직전 자세가 목표 근처까지 움직인 상황을 흉내낸다
    d._last_head = FakeMove(pitch_deg=19.0).evaluate(0.0)[0]
    again = d._eval_primary(prim, now=0.25)

    assert np.allclose(first[0], again[0], atol=1e-12), (
        "같은 시각의 진입 블렌드가 직전 자세에 따라 달라진다 — 출발점이 고정되지 않았다"
    )
    # 그리고 그 출발점은 실제 진행률을 따른다(중간쯤에서 목표의 절반 근처)
    mid = d._eval_primary(prim, now=0.5)
    pitch_mid = np.rad2deg(np.arcsin(np.clip(mid[0][0, 2], -1, 1)))
    assert 7.0 < pitch_mid < 13.0, f"블렌드 중간인데 pitch {pitch_mid:.1f}도"


def test_모션_진입이_갑자기_튀지_않는다():
    """블렌드 구간 동안 pitch 가 단조롭게 목표로 다가가야 한다."""
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: False, rate_hz=200.0)
    d.start()
    try:
        time.sleep(0.05)
        d.play(FakeMove(duration=1.0), blend_s=0.3)
        time.sleep(0.28)
        seq = [_pitch_of(c[1]) for c in mini.snapshot()[-40:]]
    finally:
        d.stop()
    # 한 틱에 20도를 뛰지 않는다(블렌드 없이 바로 꽂으면 첫 틱에 20도가 튄다)
    assert max(abs(b - a) for a, b in zip(seq, seq[1:])) < 5.0


# ── 모터 정숙 (§12) ────────────────────────────────────────────


def _movement(calls, last_n=30) -> float:
    """최근 프레임들의 안테나 각 변동 폭(도) — 0 이면 서보가 그 자리에 서 있다.

    pitch 로 재면 안 된다: sway 는 roll·yaw 를 함께 섞으므로 합성 회전행렬의
    [0,2] 성분에서 pitch 만 깨끗이 안 나온다(위상에 따라 0.1도까지 떨어졌다).
    안테나는 목표값이 그대로 기록돼 측정이 정확하다(진폭 12도 x env).
    """
    seq = [np.degrees(float(np.asarray(c[2])[0])) for c in calls[-last_n:]]
    return max(seq) - min(seq)


def test_사용자가_말하면_몸이_접힌다():
    """XVF3800 AEC 는 스피커 반향만 지운다 — 서보 소음은 우리가 멈춰야 한다."""
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: True, rate_hz=200.0)  # 로봇 발화 중 = sway 최대
    d.start()
    try:
        time.sleep(0.3)
        moving = _movement(mini.snapshot())
        d.set_quiet(True)
        # 포락선은 지수 감쇠다(tau=0.15s) — 0.6초로는 1.8% 가 남아 0.5도까지
        # 나온다(실측). 충분히 수렴시키고, 판정도 절대값이 아니라 잔여율로 한다.
        time.sleep(1.0)
        quiet = _movement(mini.snapshot())
        n_before = len(mini.calls)
        time.sleep(0.1)
        n_after = len(mini.calls)
    finally:
        d.stop()
    assert moving > 0.5, "정숙 전에는 움직여야 비교가 된다"
    assert quiet < 0.05 * moving, f"정숙인데 안테나가 {quiet:.3f}도 움직인다(전 {moving:.3f})"
    assert n_after > n_before, "정숙이어도 목표 송신은 계속돼야 한다(루프 생존)"


def test_정숙_해제는_부드럽다():
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: True, rate_hz=200.0)
    d.start()
    try:
        d.set_quiet(True)
        time.sleep(0.4)
        d.set_quiet(False)
        time.sleep(0.6)
        seq = [np.degrees(float(np.asarray(c[2])[0])) for c in mini.snapshot()[-150:]]
    finally:
        d.stop()
    jump = max(abs(b - a) for a, b in zip(seq, seq[1:]))
    assert jump < 3.0, f"정숙을 풀 때 한 틱에 {jump:.1f}도가 튀었다"
    assert max(seq) - min(seq) > 0.5, "풀렸는데 움직임이 돌아오지 않았다"


def test_정숙은_스위치로_끌_수_있다(monkeypatch):
    import driver as driver_mod

    monkeypatch.setattr(driver_mod, "MOTOR_QUIET", False)
    d = RobotDriver(RecordingMini(), lambda: False)
    d.set_quiet(True)
    assert d._quiet is False, "REACHY_MOTOR_QUIET=0 이면 무시돼야 한다"


def test_정숙은_모션에는_손대지_않는다():
    """primary(응답 모션)는 로봇 발화 턴의 정당한 동작이다 — 접지 않는다."""
    mini = RecordingMini()
    d = RobotDriver(mini, lambda: False, rate_hz=200.0)
    d.start()
    try:
        d.play(FakeMove(duration=1.0, pitch_deg=20.0), blend_s=0.05)
        d.set_quiet(True)
        time.sleep(0.3)
        pitch = _pitch_of(mini.snapshot()[-1][1])
    finally:
        d.stop()
    assert abs(pitch - 20.0) < 1.0, "정숙이 응답 모션까지 접었다"


# ── 견고성 ─────────────────────────────────────────────────────


def test_한_프레임이_터져도_루프가_살아남는다(capsys):
    class Flaky(RecordingMini):
        def __init__(self):
            super().__init__()
            self.n = 0

        def set_target(self, head=None, antennas=None, body_yaw=None):
            self.n += 1
            if self.n == 3:
                raise RuntimeError("한 프레임 실패")
            super().set_target(head, antennas, body_yaw)

    mini = Flaky()
    _run(RobotDriver(mini, lambda: False, rate_hz=200.0), 0.2)
    assert len(mini.calls) > 10, "예외 하나로 루프가 죽었다"
    assert "로봇 루프 오류" in capsys.readouterr().out, "조용히 넘어가면 안 된다"


def test_벽시계가_아니라_단조시계를_쓴다():
    """CM4 에는 RTC 가 없어 부팅 후 NTP 가 붙으면 벽시계가 크게 튄다."""
    import driver as driver_mod

    src = pathlib.Path(driver_mod.__file__).read_text()
    assert "time.monotonic()" in src
    assert "time.time()" not in src, "driver 는 벽시계를 쓰면 안 된다"
