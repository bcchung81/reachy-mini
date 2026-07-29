"""말할 때 자연스럽게 흔들리고, 조용할 때는 숨 쉬는 동작.

답변이 길어지면 감정 모션(3초 남짓)이 끝난 뒤 로봇이 굳어 보인다.
그 구간을 채운다.

오실레이터 상수는 SDK의 `reachy_mini.motion.speech_tapper` 에서 그대로 가져왔다.
공식 대화 앱이 음성에 맞춰 흔드는 데 쓰는 값이라 움직임의 성격이 같다.
다만 우리 TTS(`say`)는 데몬 오디오 파이프라인을 거치지 않아 PCM 을 먹일 수 없으므로,
음량 포락선 대신 **발화 중인지 여부**로 포락선을 만든다. 로봇에 입이 없어
음절 단위 동기화는 어차피 지각되지 않는다.

녹화 모션이 재생 중일 때는 절대 개입하지 않는다 — play_move 가 같은
set_target 을 100Hz 로 쓰고 있어서 겹치면 서로 밀어낸다.
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass

# ── speech_tapper 에서 가져온 상수 ────────────────────────────────
SWAY_F_PITCH, SWAY_A_PITCH_DEG = 2.2, 4.5
SWAY_F_YAW, SWAY_A_YAW_DEG = 0.6, 7.5
SWAY_F_ROLL, SWAY_A_ROLL_DEG = 1.3, 2.25
SWAY_F_X, SWAY_A_X_MM = 0.35, 4.5
SWAY_F_Y, SWAY_A_Y_MM = 0.45, 3.75
SWAY_F_Z, SWAY_A_Z_MM = 0.25, 2.25

# 포락선 상승·하강 시간(초). speech_tapper 의 attack 50ms / release 250ms 를
# 발화 단위로 늘려 잡았다 — 절 사이의 짧은 공백에 움직임이 툭 끊기지 않게.
ENV_ATTACK_S = 0.25
ENV_RELEASE_S = 0.60

# 조용할 때의 호흡 — 아주 느리고 작게. "살아 있다"는 느낌만 준다.
BREATH_F = 0.22
BREATH_Z_MM = 1.2
BREATH_PITCH_DEG = 0.5

ANTENNA_F = 1.1
ANTENNA_A_DEG = 12.0
ANTENNA_IDLE_DEG = 2.0


@dataclass(frozen=True)
class Offsets:
    x_mm: float
    y_mm: float
    z_mm: float
    roll_deg: float
    pitch_deg: float
    yaw_deg: float
    antenna_deg: float


class SwayState:
    """시간에 따른 흔들림 값을 계산한다. 로봇 없이 테스트할 수 있는 순수 상태기계."""

    def __init__(self, seed: int = 7):
        rng = random.Random(seed)
        self._ph = {k: rng.random() * 2 * math.pi
                    for k in ("pitch", "yaw", "roll", "x", "y", "z", "ant")}
        self.t = 0.0
        self.env = 0.0

    def step(self, dt: float, speaking: bool) -> None:
        self.t += dt
        target = 1.0 if speaking else 0.0
        tau = ENV_ATTACK_S if speaking else ENV_RELEASE_S
        # 1차 저역통과 — 포락선이 계단처럼 튀지 않게 한다
        self.env += (target - self.env) * min(1.0, dt / tau)
        self.env = max(0.0, min(1.0, self.env))

    def _osc(self, freq: float, phase_key: str) -> float:
        return math.sin(2 * math.pi * freq * self.t + self._ph[phase_key])

    def offsets(self) -> Offsets:
        e = self.env
        breath = self._osc(BREATH_F, "z")
        idle = 1.0 - e  # 말할 때는 호흡을 접고 sway 로 넘긴다
        return Offsets(
            x_mm=SWAY_A_X_MM * e * self._osc(SWAY_F_X, "x"),
            y_mm=SWAY_A_Y_MM * e * self._osc(SWAY_F_Y, "y"),
            z_mm=SWAY_A_Z_MM * e * self._osc(SWAY_F_Z, "z") + BREATH_Z_MM * idle * breath,
            roll_deg=SWAY_A_ROLL_DEG * e * self._osc(SWAY_F_ROLL, "roll"),
            pitch_deg=(SWAY_A_PITCH_DEG * e * self._osc(SWAY_F_PITCH, "pitch")
                       + BREATH_PITCH_DEG * idle * breath),
            yaw_deg=SWAY_A_YAW_DEG * e * self._osc(SWAY_F_YAW, "yaw"),
            antenna_deg=(ANTENNA_A_DEG * e * self._osc(ANTENNA_F, "ant")
                         + ANTENNA_IDLE_DEG * idle * breath),
        )


class Animator:
    """백그라운드에서 흔들림을 로봇에 적용한다.

    is_speaking / is_busy 는 각각 Speaker.speaking, MotionPlayer.busy 를 넘긴다.
    busy 인 동안에는 손을 떼서 녹화 모션과 충돌하지 않게 한다.
    """

    def __init__(self, mini, is_speaking, is_busy, rate_hz: float = 50.0):
        self._mini = mini
        self._is_speaking = is_speaking
        self._is_busy = is_busy
        self._dt = 1.0 / rate_hz
        self._state = SwayState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        from reachy_mini.utils import create_head_pose

        while not self._stop.is_set():
            t0 = time.time()
            try:
                if self._is_busy():
                    # 녹화 모션이 몰고 있다 — 개입하지 않되 위상은 계속 굴려
                    # 모션이 끝났을 때 갑자기 튀지 않게 한다.
                    self._state.step(self._dt, speaking=False)
                else:
                    self._state.step(self._dt, speaking=self._is_speaking())
                    o = self._state.offsets()
                    self._mini.set_target(
                        head=create_head_pose(
                            x=o.x_mm, y=o.y_mm, z=o.z_mm,
                            roll=o.roll_deg, pitch=o.pitch_deg, yaw=o.yaw_deg,
                            mm=True, degrees=True,
                        ),
                        antennas=[math.radians(o.antenna_deg), math.radians(-o.antenna_deg)],
                    )
            except Exception:
                pass  # 시연 중 한 프레임 실패로 스레드가 죽지 않게

            slept = time.time() - t0
            if slept < self._dt:
                time.sleep(self._dt - slept)
