"""무대감독의 전송 계층. 로직은 `director.py` 에 있다.

`websockets` 의 **sync API** 를 쓴다 — SDK 자신이 `io/ws_client.py` 에서 쓰는
것과 같은 방식이고, 이 저장소에는 `pytest-asyncio` 가 없어 asyncio 테스트를
쓸 수 없다.
"""

import threading
import time
from typing import Callable

from websockets.sync.server import serve as _ws_serve

from stage.cues import CueSheet
from stage.director import Director
from stage.machine import Command
from stage.protocol import ROLES, ProtocolError, decode, encode


class StageServer:
    def __init__(
        self,
        sheet: CueSheet,
        generate: Callable[[str, list[dict]], str],
        expect_units: dict[str, str] | None = None,
        warn: Callable[[str], None] = print,
    ) -> None:
        self._warn = warn
        self._conns: dict[str, object] = {}
        self._lock = threading.Lock()
        self.director = Director(
            sheet, generate=generate, send=self._send,
            expect_units=expect_units, warn=warn,
        )

    # ── 전송 ──────────────────────────────────────────────────────
    def _send(self, role: str, cmd: Command) -> None:
        with self._lock:
            ws = self._conns.get(role)
        if ws is None:
            # 조용히 삼키면 한쪽만 말하는 시연이 된다.
            self._warn(f"[{role}] 아직 붙지 않았다 — {cmd.type} 를 버린다")
            return
        try:
            ws.send(encode(cmd.type, **cmd.fields))
        except Exception as exc:
            self._warn(f"[{role}] 전송 실패({type(exc).__name__}: {exc})")

    # ── 연결 ──────────────────────────────────────────────────────
    def handler(self, ws) -> None:
        """연결 하나. 첫 메시지는 반드시 hello 여야 한다."""
        role: str | None = None
        try:
            for raw in ws:
                try:
                    msg = decode(raw)
                except ProtocolError as exc:
                    self._warn(f"[{role or '미등록'}] 메시지가 규약에 안 맞는다: {exc}")
                    continue

                if role is None:
                    if msg["type"] != "hello":
                        self._warn(
                            f"첫 메시지가 hello 가 아니다({msg['type']}) — 연결을 끊는다"
                        )
                        return
                    role = msg.get("role")
                    if role not in ROLES:
                        self._warn(f"모르는 역할이다: {role!r} — 연결을 끊는다")
                        return
                    self.director.on_hello(
                        role, msg.get("unit_id"), msg.get("version", "")
                    )
                    with self._lock:
                        self._conns[role] = ws
                    self._warn(f"[{role}] 붙었다 (version={msg.get('version')})")
                    self.director.on_connect(role)
                    continue

                self._dispatch(role, msg)
        finally:
            if role is not None:
                # 한 번만 계산해서 삭제와 on_disconnect 둘 다 이 값으로 문을
                # 잠근다. 빠른 재연결에서 새 연결이 이미 이 role 을 차지한
                # 뒤에야 stale 한 옛 핸들러의 finally 가 뒤늦게 실행되면,
                # `self._conns.get(role)` 는 이미 새 ws 를 가리킨다 — 그때도
                # `on_disconnect` 를 부르면 실제로는 붙어 있는 role 을 감독이
                # "끊겼다"고 오판해 조용히 1인 모드로 내려간다(review finding 2).
                with self._lock:
                    is_current = self._conns.get(role) is ws
                    if is_current:
                        del self._conns[role]
                if is_current:
                    self.director.on_disconnect(role)
                self._warn(f"[{role}] 연결이 끊어졌다")

    def _dispatch(self, role: str, msg: dict) -> None:
        t = msg["type"]
        if t == "heard":
            self.director.on_heard(msg.get("text", ""))
        elif t == "speaking_ended":
            self.director.on_speaking_ended(role, msg.get("cue_id", ""))
        elif t == "speaking_started":
            # 상태는 say 를 보낼 때 이미 옮겼다(불변식 ②). 여기서 하는 일은
            # **타임아웃 데드라인을 발화 시작 시점으로 다시 거는 것**이다 —
            # 예전에는 `pass` 라, say 를 보낸 뒤 로봇이 실제로 말을 시작하기까지
            # 든 시간이 전부 발화 예산에서 깎였다(리뷰 I3).
            self.director.on_speaking_started(role, msg.get("cue_id", ""))
        elif t == "error":
            self.director.on_error(role, msg.get("where", ""), msg.get("detail", ""))
        else:
            self._warn(f"[{role}] 로봇이 보낼 수 없는 메시지다: {t}")

    # ── 기동 ──────────────────────────────────────────────────────
    def serve(self, host: str, port: int):
        """블로킹. 반환값은 websockets 서버 객체(테스트에서 shutdown 용)."""
        return _ws_serve(self.handler, host, port)

    def tick_forever(self, interval_s: float, should_stop: Callable[[], bool]) -> None:
        while not should_stop():
            self.director.tick()
            time.sleep(interval_s)
