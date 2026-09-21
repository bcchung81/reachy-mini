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
from stage.director import Director, UnitMismatch
from stage.machine import Command
from stage.protocol import ROLES, ProtocolError, decode, encode


class StageServer:
    def __init__(
        self,
        sheet: CueSheet,
        generate: Callable[[str, str, list[dict]], str],
        expect_units: dict[str, str] | None = None,
        warn: Callable[[str], None] = print,
        mc_lines: dict[str, str] | None = None,
        level_name: str = "일반",
    ) -> None:
        self._warn = warn
        self._conns: dict[str, object] = {}
        self._lock = threading.Lock()
        # `mc_lines`/`level_name` 을 그대로 `Director` 로 흘려보낸다 — 여기서
        # 기본값으로 삼키면(예: 인자를 받고 안 넘기면) `Director` 는 늘
        # 기본값(빈 캐시·"일반")으로 돌고, `main()` 이 아무리 제대로 읽어도
        # 이 자리에서 끊긴다. `stage/__main__.py::main()` 이 이 값을 채워
        # 넘긴다.
        self.director = Director(
            sheet, generate=generate, send=self._send,
            expect_units=expect_units, warn=warn,
            mc_lines=mc_lines, level_name=level_name,
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
                    r = msg.get("role")
                    # 검증 전에 `role` 에 대입하지 않는다 — 비해시 값(list)이면
                    # `in ROLES` 가 TypeError 를 내고 finally 가 또 한 번 터져
                    # 경고 한 줄 없이 끝났다(리뷰 A8b).
                    if not isinstance(r, str) or r not in ROLES:
                        self._warn(f"모르는 역할이다: {r!r} — 연결을 끊는다")
                        return
                    role = r
                    try:
                        self.director.on_hello(
                            role, msg.get("unit_id"), msg.get("version", "")
                        )
                    except UnitMismatch as exc:
                        # 사람이 읽을 한 줄로 남기고 이 연결만 닫는다. 예전에는
                        # 여기서 새어 나가 websockets 로거의 traceback 만 2초마다
                        # 반복됐고, 콘솔 `s` 는 뒤바뀐 로봇으로 시연을 시작했다
                        # (리뷰 A4). `role` 을 되돌려 finally 가 "끊어졌다" 로
                        # 오해하게 적지 않게 한다 — 붙은 적이 없다.
                        self.director.reject(role, str(exc))
                        role = None
                        return
                    with self._lock:
                        old = self._conns.get(role)
                        self._conns[role] = ws
                    if old is not None and old is not ws:
                        # 같은 역할로 두 번 붙었다. 예전에는 옛 소켓이 **열린
                        # 채로 버려져** 감독이 보내는 것을 아무도 안 받는
                        # 유령 연결로 남았다(그쪽 핸들러 스레드도 계속 돈다).
                        # 로봇 두 대에 같은 역할을 준 사고일 수도 있으므로
                        # 조용히 넘기지 않는다.
                        self._warn(
                            f"[{role}] 자리에 이미 다른 연결이 있었다 — 옛 연결을 "
                            "닫는다. 두 로봇에 같은 역할을 주지 않았는지 확인한다"
                        )
                        try:
                            old.close()
                        except Exception as exc:  # noqa: BLE001
                            self._warn(f"[{role}] 옛 연결을 닫지 못했다: {exc}")
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

    def _str_field(self, role: str, msg: dict, key: str) -> str | None:
        """와이어 필드를 문자열로 검증한다. 아니면 경고하고 None.

        `protocol.decode` 는 `type` 만 본다. `text: null` 이 그대로 내려오면
        `is_advance(None)` 에서 AttributeError 가 나 연결이 1011 로 닫히고, 감독은
        그것을 끊김으로 봐 **1인 모드로 내려갔다**(리뷰 A8b). 규약 위반은 그
        메시지만 버린다 — 연결을 잃을 이유가 아니다.
        """
        v = msg.get(key)
        if not isinstance(v, str):
            self._warn(
                f"[{role}] {msg['type']}.{key} 가 규약에 안 맞는다"
                f"({type(v).__name__}) — 이 메시지를 버린다"
            )
            return None
        return v

    def _seq_field(self, role: str, msg: dict) -> tuple[int | None, bool]:
        v = msg.get("seq")
        if v is None or (isinstance(v, int) and not isinstance(v, bool)):
            return v, True
        self._warn(
            f"[{role}] {msg['type']}.seq 가 규약에 안 맞는다({type(v).__name__}) — 이 메시지를 버린다"
        )
        return None, False

    def _dispatch(self, role: str, msg: dict) -> None:
        t = msg["type"]
        if t == "heard":
            # **관람객 창구는 하나다**(설계 §2). 사회자만, 1인 모드에서는
            # 남은 한 대만 올릴 수 있다. 도슨트에 청취 루프가 생기거나
            # 로봇 쪽 게이트(`make_heard_sink`)가 새면 상대 로봇의 목소리가
            # 관람객 발화로 올라온다 — 여기서 한 줄로 더 막는다.
            listener = self.director.solo_role or "mc"
            if role != listener:
                self._warn(
                    f"[{role}] 는 관람객 창구가 아니다(지금은 {listener}) — "
                    f"heard 를 버린다: {msg.get('text', '')!r}"
                )
                return
            text = self._str_field(role, msg, "text")
            if text is None:
                return
            self.director.on_heard(text)
        elif t in ("speaking_ended", "speaking_started"):
            cue_id = self._str_field(role, msg, "cue_id")
            seq, ok = self._seq_field(role, msg)
            if cue_id is None or not ok:
                return
            if t == "speaking_ended":
                self.director.on_speaking_ended(role, cue_id, seq)
            else:
                # 상태는 say 를 보낼 때 이미 옮겼다(불변식 ②). 여기서 하는 일은
                # **타임아웃 데드라인을 발화 시작 시점으로 다시 거는 것**이다 —
                # 예전에는 `pass` 라, say 를 보낸 뒤 로봇이 실제로 말을 시작하기까지
                # 든 시간이 전부 발화 예산에서 깎였다(리뷰 I3).
                self.director.on_speaking_started(role, cue_id, seq)
        elif t == "error":
            self.director.on_error(role, str(msg.get("where", "")), str(msg.get("detail", "")))
        else:
            self._warn(f"[{role}] 로봇이 보낼 수 없는 메시지다: {t}")

    # ── 기동 ──────────────────────────────────────────────────────
    def serve(self, host: str, port: int):
        """블로킹. 반환값은 websockets 서버 객체(테스트에서 shutdown 용)."""
        return _ws_serve(self.handler, host, port)

    def tick_forever(self, interval_s: float, should_stop: Callable[[], bool]) -> None:
        """감시 루프. **한 번 터졌다고 죽지 않는다.**

        예전에는 무방비였다. `director.tick()` 이 하는 일이 `force_listening` +
        `_emit` 뿐이던 동안에는 잃는 것이 타임아웃 복구 하나였는데, 침묵 자동
        진행이 들어오면서 이 루프가 **진행의 임계경로**가 됐다 — 침묵 갈래는
        `_next_locked()` → `_begin_cue()` 까지 돌며 캐시 조회, `_warn`(기본값이
        `print` 라 stdout 이 닫히면 `ValueError`), `_remember`,
        `_spawn_generate` → `Thread().start()`(`RuntimeError: can't start new
        thread`), `_emit` 을 거친다.

        여기서 예외가 새면 스레드가 죽고 **타임아웃 복구와 자동 진행이 동시에
        영구 정지한다.** 관람객은 "다음" 이라는 낱말을 모르므로 시연이 그 자리에서
        굳는다 — 자동 진행이 없애려던 바로 그 상태다. 그래서 삼키되 **반드시
        소리 낸다**: 조용히 성능이 떨어진 채 도는 것이 가장 나쁘다.
        """
        while not should_stop():
            try:
                self.director.tick()
            except Exception as exc:
                self._warn(
                    f"tick 에서 오류({type(exc).__name__}: {exc}) — "
                    "감시 루프는 계속 돈다(타임아웃 복구·침묵 진행을 잃지 않는다)"
                )
            time.sleep(interval_s)
