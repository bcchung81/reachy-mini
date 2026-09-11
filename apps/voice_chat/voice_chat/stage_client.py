"""무대감독 클라이언트 — 로봇 쪽.

**`stage/` 를 import 하지 않는다.** 그 패키지는 노트북에만 있고 로봇에는
앱만 올라간다. 그래서 메시지 규약을 여기 다시 적는다. 한쪽만 고치면 어긋나므로
`stage/protocol.py` 와 짝으로 관리한다 — 설계 문서 §4 가 정본이다.
"""

import json
import time
from dataclasses import dataclass
from typing import Callable

_ROBOT_MSGS = frozenset({"hello", "heard", "speaking_started", "speaking_ended", "error"})
_DIRECTOR_MSGS = frozenset({"say", "mic", "gaze", "abort"})

RETRY_S = 2.0


@dataclass
class Handlers:
    """감독의 지시를 받는 곳. 전부 채워야 한다."""

    on_say: Callable[[str, str, str | None], None]
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

    def speaking_started(self, cue_id: str) -> None:
        self._send("speaking_started", cue_id=cue_id)

    def speaking_ended(self, cue_id: str) -> None:
        self._send("speaking_ended", cue_id=cue_id)

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
                    for raw in ws:
                        self._on_raw(raw)
                        if should_stop():
                            break
                except Exception as exc:
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
            self._h.on_say(msg.get("cue_id", ""), msg.get("text", ""), msg.get("gaze"))
        elif t == "mic":
            self._h.on_mic(bool(msg.get("open")))
        elif t == "gaze":
            self._h.on_gaze(msg.get("target", "audience"))
        elif t == "abort":
            self._h.on_abort()
