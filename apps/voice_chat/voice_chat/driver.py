"""로봇에 목표를 쓰는 **유일한** 스레드.

공식 `harness/skills/control-loops.md` 의 규칙이다:

> One control loop, one place calling `set_target()` … **Never call `set_target()`
> from multiple threads.**

예전에는 그 규칙을 어기고 있었다. `Animator` 스레드가 50 Hz 로 `set_target()` 을
쓰고, `MotionPlayer` 스레드가 `play_move()` 를 돌렸는데 그 안에서 SDK 가 다시
100 Hz 로 `set_target_*` 을 쓴다(`reachy_mini.py:1067`). 막는 것은 애니메이터의
`if self._is_busy()` 한 줄뿐이었는데 **검사와 쓰기가 원자적이 아니다** — 검사를
통과한 직후 모션이 시작되면 낡은 sway 프레임이 모션 위에 얹힌다.

지금은 한 스레드가 두 층을 합성한다(공식 레퍼런스 `moves.py` 와 같은 모델):

  · **primary**  — 녹화 모션. 있으면 그것이 포즈를 결정한다.
  · **secondary** — sway·호흡(`animator.SwayState`). primary 가 없을 때만 쓴다.

`play_move()` 를 안 쓰고 `move.evaluate(t)` 를 직접 부르는 이유도 여기 있다.
`play_move` 는 자기 스레드에서 로봇을 몰기 때문에, 그걸 쓰는 한 쓰는 주체가 둘이
된다. 사운드 재생도 `play_move` 가 겸하던 일인데 그건 `motion.py` 가 우리 Speaker 로
넘긴다 — 근거는 `sound.py` 참조.

**시계는 `time.monotonic()` 이다.** 벽시계를 쓰면 NTP 동기·절전 복귀에서 점프한다.
실기 CM4 에는 배터리 백업 RTC 가 없어 부팅 후 NTP 가 붙는 순간 시각이 크게 튄다.
"""

from __future__ import annotations

import math
import threading
import time

import numpy as np

from animator import SwayState

# 모션에 들어가고 나올 때 섞는 시간(초). SDK `play_move` 의 initial_goto_duration
# 기본 사용값과 같게 뒀다 — 갑자기 튀지 않을 만큼만.
BLEND_S = 0.3


def _minjerk(a: float) -> float:
    """0..1 을 부드럽게 — 시작·끝에서 속도가 0 이다(SDK 기본 보간과 같은 성격)."""
    return a * a * a * (10.0 + a * (-15.0 + 6.0 * a))


def _blend_pose(a: np.ndarray, b: np.ndarray, s: float) -> np.ndarray:
    """4x4 동차변환 둘을 섞는다 — SDK 의 slerp+lerp 를 **clamp 해서** 쓴다.

    기하는 `reachy_mini.utils.interpolation.linear_pose_interpolation` 그대로다
    (직접 구현했다가 수치까지 동일함이 확인돼 위임했다 — 중복 제거).

    단 `s` 는 반드시 여기서 clamp 한다. SDK 판은 범위 밖 t 를 **외삽**하는데,
    호출부가 `(release_until - now) / release_s` 나눗셈으로 s 를 만들어
    부동소수 오차로 1e-17 만큼 범위를 벗어난다(실측 재현) — 외삽은 그 오차를
    자세 오버슈트로 바꾼다. 우리는 끝값에 고정한다.
    """
    from reachy_mini.utils.interpolation import linear_pose_interpolation

    return linear_pose_interpolation(a, b, min(1.0, max(0.0, s)))


class _Primary:
    """재생 중인 녹화 모션 하나."""

    __slots__ = ("move", "t0", "blend_s", "idle", "entry")

    def __init__(self, move, t0: float, blend_s: float, idle: bool):
        self.move = move
        self.t0 = t0
        self.blend_s = blend_s
        self.idle = idle
        # 진입 블렌드의 출발 자세 — **첫 틱에 한 번 찍어 고정한다**(루프 스레드).
        # 매 틱 "직전 실제 자세"에서 섞으면 그 자세가 이미 목표 쪽으로 움직인
        # 값이라 복리로 겹쳐, 실효 블렌드가 blend_s 보다 짧아진다. 이탈 블렌드
        # (release_from)는 처음부터 스냅샷 고정이었다 — 진입만 비대칭이었다.
        self.entry = None


class RobotDriver:
    """로봇 출력의 단일 소유자. 다른 스레드는 목표만 바꾸고 절대 쓰지 않는다."""

    def __init__(self, mini, is_speaking, rate_hz: float = 100.0):
        self._mini = mini
        self._is_speaking = is_speaking
        self._dt = 1.0 / rate_hz
        self._sway = SwayState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._primary: _Primary | None = None
        # 마지막으로 **실제로 명령한** 자세. 모션에 들어가고 나올 때 여기서 섞는다.
        self._last_head: np.ndarray | None = None
        self._last_ant = np.zeros(2)
        self._last_yaw = 0.0
        self._release_until = 0.0   # 모션에서 빠져나오며 sway 로 섞는 구간
        self._release_s = BLEND_S
        self._release_from: tuple[np.ndarray, np.ndarray, float] | None = None
        self._errors = 0

    # ── 다른 스레드가 부르는 것 ────────────────────────────────

    def play(self, move, idle: bool = False, blend_s: float = BLEND_S) -> None:
        """이 모션을 primary 로 건다. 진행 중이던 것은 대체된다(호출부가 우선순위 판단)."""
        with self._lock:
            self._primary = _Primary(move, time.monotonic(), blend_s, idle)

    def cancel(self) -> None:
        """재생 중인 모션을 끊는다. **복귀 블렌드를 무장하고** 끊는다.

        primary 만 지우면 다음 틱(10ms)에 sway 원점 자세가 그대로 꽂힌다 —
        ±20~40도짜리 모션 자세에서 한 틱에 튀는 스냅이고, 실기에서는 눈에 보이는
        경련이자 기계 부하다(리뷰 확인 — 자연 종료 경로만 블렌드를 무장하고
        있었다). 종료 경로와 같은 블렌드를 여기서도 건다.
        """
        with self._lock:
            if self._primary is None:
                return
            self._primary = None
            self._release_from = (self._last_head, self._last_ant, self._last_yaw)
            self._release_s = BLEND_S
            self._release_until = time.monotonic() + BLEND_S

    @property
    def playing(self) -> bool:
        with self._lock:
            return self._primary is not None

    @property
    def playing_idle(self) -> bool:
        """지금 도는 것이 대기 모션인가 — 응답 모션이 밀어낼 수 있는지 판단용."""
        with self._lock:
            return self._primary is not None and self._primary.idle

    # ── 루프 ───────────────────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        from reachy_mini.utils import create_head_pose

        self._last_head = create_head_pose()
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                head, ant, yaw = self._tick(t0, create_head_pose)
                self._mini.set_target(head=head, antennas=ant, body_yaw=yaw)
                self._last_head, self._last_ant, self._last_yaw = head, ant, yaw
            except Exception as exc:  # noqa: BLE001
                # 한 프레임 실패로 스레드를 잃지 않는다. 다만 **조용히 넘기지도**
                # 않는다 — 예전에는 통째로 삼켜서 로봇이 굳어도 이유를 몰랐다.
                self._errors += 1
                if self._errors <= 3 or self._errors % 500 == 0:
                    print(
                        f"  [로봇 루프 오류 #{self._errors}: {type(exc).__name__}: {exc}]",
                        flush=True,
                    )
            slept = time.monotonic() - t0
            if slept < self._dt:
                time.sleep(self._dt - slept)

    def _tick(self, now: float, create_head_pose):
        with self._lock:
            prim = self._primary

        if prim is not None:
            pose = self._eval_primary(prim, now)
            if pose is not None:
                # 모션이 도는 동안에도 위상은 굴려 둔다 — 끝났을 때 sway 가
                # 0 에서 다시 시작하지 않고 이어진다.
                self._sway.step(self._dt, speaking=False)
                return pose
            # 모션이 끝났다 — sway 로 되돌아가는 구간을 연다.
            # 릴리스 필드는 cancel()(다른 스레드)도 쓰므로 같은 잠금 안에서 만진다.
            with self._lock:
                if self._primary is prim:
                    self._primary = None
                    self._release_from = (self._last_head, self._last_ant, self._last_yaw)
                    self._release_s = prim.blend_s
                    self._release_until = now + prim.blend_s

        return self._secondary(now, create_head_pose)

    def _eval_primary(self, prim: _Primary, now: float):
        """모션 포즈. 끝났으면 None."""
        since = now - prim.t0
        if since < prim.blend_s:
            # 들어가는 구간 — SDK 의 initial_goto_duration 에 해당한다.
            if prim.entry is None:
                prim.entry = (self._last_head, self._last_ant, self._last_yaw)
            target = prim.move.evaluate(0.0)
            return self._mix(prim.entry, target, _minjerk(since / prim.blend_s))
        t = since - prim.blend_s
        if t >= prim.move.duration:
            return None
        # 끝에서 아주 살짝 물러나 평가한다 — SDK 가 같은 이유로 그렇게 한다
        # (마지막 샘플 경계에서 보간이 범위를 벗어나는 것을 막는다).
        return self._as_target(prim.move.evaluate(min(t, prim.move.duration - 1e-2)))

    @staticmethod
    def _as_target(evaluated):
        """`evaluate()` 는 항목별로 None 을 줄 수 있다 — 기본값으로 메운다."""
        head, ant, yaw = evaluated
        return (
            head,
            np.zeros(2) if ant is None else np.asarray(ant, dtype=float),
            0.0 if yaw is None else float(yaw),
        )

    def _mix(self, a, b, s: float):
        """a → b 를 s(0..1) 만큼 섞는다. 양쪽 다 `(head, antennas, body_yaw)`."""
        head_a, ant_a, yaw_a = self._as_target(a)
        head_b, ant_b, yaw_b = self._as_target(b)
        head = head_a if head_b is None else (
            head_b if head_a is None else _blend_pose(head_a, head_b, s)
        )
        return (
            head,
            (1.0 - s) * np.asarray(ant_a, dtype=float) + s * ant_b,
            (1.0 - s) * yaw_a + s * yaw_b,
        )

    def _secondary(self, now: float, create_head_pose):
        """sway·호흡. 모션이 없을 때의 기본 층이다."""
        self._sway.step(self._dt, speaking=self._is_speaking())
        o = self._sway.offsets()
        target = (
            create_head_pose(
                x=o.x_mm, y=o.y_mm, z=o.z_mm,
                roll=o.roll_deg, pitch=o.pitch_deg, yaw=o.yaw_deg,
                mm=True, degrees=True,
            ),
            np.array([math.radians(o.antenna_deg), math.radians(-o.antenna_deg)]),
            0.0,
        )
        with self._lock:  # cancel() 이 다른 스레드에서 릴리스 필드를 쓴다
            r_until, r_from, r_s = self._release_until, self._release_from, self._release_s
        if now < r_until and r_from is not None:
            # 모션에서 막 빠져나왔다 — 갑자기 튀지 않게 섞어 준다
            s = _minjerk(1.0 - (r_until - now) / r_s)
            return self._mix(r_from, target, s)
        return target
