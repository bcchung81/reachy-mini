"""대시보드 이벤트 허브 — 감독 쪽에서 일어난 일을 모아 구독자에게 나눠 준다.

**쌓기만 하고 되부르지 않는다.** `publish` 는 감독이 `Director._lock` 을 쥔 채
부르는 자리(`StageServer._send`, 경고 콜백)에서 불린다. 여기서 감독 상태를 읽거나
네트워크를 기다리면 교착이거나 시연 진행이 멈춘다 — 그래서 deque 에 넣고 구독자
큐에 `put_nowait` 만 한다. 감독 상태는 대시보드 서버가 락 밖에서 따로 읽는다.
"""

import collections
import queue
import threading
import time
from typing import Callable

HISTORY = 200
SUB_QUEUE = 1000


class Subscription:
    def __init__(self, maxsize: int) -> None:
        self.queue: queue.Queue[dict] = queue.Queue(maxsize=maxsize)
        # 넘쳐서 버린 개수. 페이지는 다음 스냅샷으로 다시 맞춰지지만, 이벤트
        # (대사·경고)가 빠진 사실은 셀 수 있어야 한다 — 조용히 잃지 않는다.
        self.dropped = 0


class DashboardHub:
    def __init__(self, now: Callable[[], float] = time.time, history: int = HISTORY) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._history: collections.deque[dict] = collections.deque(maxlen=history)
        self._subs: list[Subscription] = []

    def publish(self, kind: str, **fields) -> None:
        ev = {"kind": kind, "t": self._now(), **fields}
        with self._lock:
            self._history.append(ev)
            subs = list(self._subs)
        for s in subs:
            try:
                s.queue.put_nowait(ev)
            except queue.Full:
                s.dropped += 1

    def subscribe(self, maxsize: int = SUB_QUEUE) -> Subscription:
        s = Subscription(maxsize)
        with self._lock:
            self._subs.append(s)
        return s

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def history(self) -> list[dict]:
        with self._lock:
            return list(self._history)


def tee(*sinks: Callable[[str], None]) -> Callable[[str], None]:
    """경고를 여러 곳에 동시에. **한 곳이 터져도 나머지는 받는다** — 대시보드가
    망가져도 터미널 경고는 살아야 하고, 그 반대도 마찬가지다. 터진 예외는 삼키지
    않고 끝에 다시 던진다(기존 `print` 경고와 같은 실패 모양)."""

    def warn(msg: str) -> None:
        first: Exception | None = None
        for sink in sinks:
            try:
                sink(msg)
            except Exception as exc:  # noqa: BLE001
                first = first or exc
        if first is not None:
            raise first

    return warn
