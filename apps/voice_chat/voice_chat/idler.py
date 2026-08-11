"""아무도 말을 걸지 않을 때 혼자 감정 표현을 한다.

가만히 서 있는 로봇은 꺼진 것처럼 보인다. 애니메이터의 호흡만으로는 약해서,
가끔 커뮤니티 감정 라이브러리의 모션을 하나씩 재생한다.

두 가지를 지킨다.
· **소리를 내지 않는다**(`idle=True` → `sound=False`). 소리를 내면 마이크를
  막아야 하고, 그러면 사용자가 말을 걸 수 없는 구간이 무작위로 생긴다.
· **응답에 항상 밀려난다.** MotionPlayer 가 대기 모션을 응답 모션으로 덮어쓴다.
"""

from __future__ import annotations

import random
import threading
import time

import emotions

MIN_GAP_S = 12.0
MAX_GAP_S = 25.0


class Idler:
    def __init__(
        self,
        player,
        is_speaking,
        min_gap: float = MIN_GAP_S,
        max_gap: float = MAX_GAP_S,
        on_play=None,
    ):
        self._player = player
        self._is_speaking = is_speaking
        self._min_gap, self._max_gap = min_gap, max_gap
        self._on_play = on_play
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _next_gap(self) -> float:
        return random.uniform(self._min_gap, self._max_gap)

    def _run(self) -> None:
        # 기동 직후에는 한 박자 쉰다 — 앱이 뜨자마자 움직이면 어수선하다
        if self._stop.wait(self._next_gap()):
            return
        while not self._stop.is_set():
            # 사용자가 말하는 중이면 혼자 놀지 않는다 — 서보 소음이 STT 를
            # 오염시킨다(§12 모터 정숙. getattr: 테스트 더블 호환).
            if (
                not self._is_speaking()
                and not self._player.moving
                and not getattr(self._player, "user_speaking", False)
            ):
                name = emotions.pick_idle(self._player.available)
                if name and self._player.play(name, idle=True) and self._on_play:
                    self._on_play(name)
            if self._stop.wait(self._next_gap()):
                return
