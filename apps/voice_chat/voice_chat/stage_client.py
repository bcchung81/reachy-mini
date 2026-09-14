"""무대감독 클라이언트 — 로봇 쪽.

**`stage/` 를 import 하지 않는다.** 그 패키지는 노트북에만 있고 로봇에는
앱만 올라간다. 그래서 메시지 규약을 여기 다시 적는다. 한쪽만 고치면 어긋나므로
`stage/protocol.py` 와 짝으로 관리한다 — 설계 문서 §4 가 정본이다.
"""

import json
import time
from dataclasses import dataclass
from typing import Callable

from websockets.exceptions import ConnectionClosed

_ROBOT_MSGS = frozenset({"hello", "heard", "speaking_started", "speaking_ended", "error"})
_DIRECTOR_MSGS = frozenset({"say", "mic", "gaze", "abort"})

RETRY_S = 2.0
# `ws.recv(timeout=...)` 폴링 주기.
#
# 실제 `websockets.sync.connection.Connection.recv()` 는 `timeout=None` 이면
# 메시지가 올 때까지 무한정 블록된다 — 예전에는 `for raw in ws:` 로 이 recv 를
# 감쌌는데, 그 이터레이터도 내부적으로 `recv()` 를 타임아웃 없이 호출하므로
# 감독이 조용한 구간(큐 사이, 정상 상황)에는 `should_stop()` 을 다시 볼 기회가
# 없었다. 셧다운 이벤트가 서서 있어도 로봇 프로세스가 끝나지 않는 버그였다 —
# 데몬의 앱 슬롯이 영영 반환되지 않는다. 그래서 짧은 타임아웃으로 반복 폴링한다.
# 0.5초는 종료 지연(최악 0.5초 — 무대에서 체감되지 않는다)과 깨어나는 횟수
# (초당 2회 — 유휴 CPU 비용이 무시할 만하다) 사이의 절충이다.
POLL_S = 0.5


@dataclass
class Handlers:
    """감독의 지시를 받는 곳. 전부 채워야 한다.

    `on_say(cue_id, text, seq)` — `seq` 는 감독이 발화마다 매기는 번호다.
    `speaking_started`/`speaking_ended` 에 **그대로 되돌려 준다.** 그래야 감독이
    콘솔 `r` 로 같은 큐를 다시 발행했을 때 중단된 발화의 늦은 종료 보고를
    가릴 수 있다(설계 §4, 리뷰 A2). `gaze` 는 `say` 에 실려 온 적이 없다 —
    감독은 별도 `gaze` 지시를 보낸다.
    """

    on_say: Callable[[str, str, int | None], None]
    on_mic: Callable[[bool], None]
    on_gaze: Callable[[str], None]
    on_abort: Callable[[], None]


class StageClient:
    def __init__(
        self,
        url: str,
        role: str,
        handlers: Handlers,
        unit_id: str | None = None,
        version: str = "",
        warn: Callable[[str], None] = print,
    ) -> None:
        self._url = url
        self._role = role
        self._h = handlers
        self._unit_id = unit_id
        self._version = version
        self._warn = warn
        self._ws = None

    # ── 보내기 ────────────────────────────────────────────────────
    def heard(self, text: str) -> None:
        self._send("heard", text=text)

    def speaking_started(self, cue_id: str, seq: int | None) -> None:
        self._send("speaking_started", cue_id=cue_id, seq=seq)

    def speaking_ended(self, cue_id: str, seq: int | None) -> None:
        self._send("speaking_ended", cue_id=cue_id, seq=seq)

    def error(self, where: str, detail: str) -> None:
        self._send("error", where=where, detail=detail)

    def _send(self, type_: str, **fields) -> None:
        assert type_ in _ROBOT_MSGS, type_
        ws = self._ws
        if ws is None:
            # 조용히 버리면 감독이 영원히 기다린다.
            self._warn(f"무대감독에 연결되지 않았다 — {type_} 를 버린다")
            return
        try:
            ws.send(json.dumps({"type": type_, **fields}, ensure_ascii=False))
        except Exception as exc:
            self._warn(f"무대감독에 보내기 실패({type(exc).__name__}: {exc})")

    # ── 받기 ──────────────────────────────────────────────────────
    def run(
        self,
        should_stop: Callable[[], bool],
        connect_fn: Callable[[str], object] | None = None,
        retry_s: float = RETRY_S,
    ) -> None:
        """블로킹. 끊기면 다시 붙는다."""
        if connect_fn is None:
            from websockets.sync.client import connect as connect_fn  # noqa: N806

        while not should_stop():
            try:
                ws = connect_fn(self._url)
            except Exception as exc:
                self._warn(
                    f"무대감독 접속 실패({type(exc).__name__}: {exc}) — "
                    f"{retry_s}초 뒤 다시 시도"
                )
                if should_stop():
                    return
                time.sleep(retry_s)
                continue

            with ws:
                self._ws = ws
                self._send(
                    "hello", role=self._role, unit_id=self._unit_id,
                    version=self._version,
                )
                try:
                    while not should_stop():
                        try:
                            raw = ws.recv(timeout=POLL_S)
                        except TimeoutError:
                            # 메시지가 없을 뿐 — 연결은 살아 있다. should_stop 만
                            # 다시 보고 계속 기다린다. 여기서 끊긴 걸로 오판하면
                            # 감독이 조용할 때마다 재접속 폭풍이 난다.
                            continue
                        except ConnectionClosed as exc:
                            self._warn(
                                f"무대감독 연결이 끊어졌다({type(exc).__name__}: {exc})"
                            )
                            break
                        self._on_raw(raw)
                except Exception as exc:
                    # 그 외 예상 못한 오류(프로토콜 위반, 네트워크 단절 등)도
                    # 끊어진 걸로 보고 재접속을 시도한다.
                    self._warn(f"무대감독 연결이 끊어졌다({type(exc).__name__}: {exc})")
                finally:
                    self._ws = None

            if not should_stop():
                self._warn(f"무대감독에 다시 붙는다 ({retry_s}초 뒤)")
                time.sleep(retry_s)

    def _on_raw(self, raw) -> None:
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            self._warn(f"무대감독 메시지가 JSON 이 아니다: {exc}")
            return
        t = msg.get("type")
        if t not in _DIRECTOR_MSGS:
            self._warn(f"감독이 보낼 수 없는 메시지다: {t!r}")
            return
        if t == "say":
            self._h.on_say(msg.get("cue_id", ""), msg.get("text", ""), msg.get("seq"))
        elif t == "mic":
            self._h.on_mic(bool(msg.get("open")))
        elif t == "gaze":
            self._h.on_gaze(msg.get("target", "audience"))
        elif t == "abort":
            self._h.on_abort()
