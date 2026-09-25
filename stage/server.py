"""무대감독의 전송 계층. 로직은 `director.py` 에 있다.

`websockets` 의 **sync API** 를 쓴다 — SDK 자신이 `io/ws_client.py` 에서 쓰는
것과 같은 방식이고, 이 저장소에는 `pytest-asyncio` 가 없어 asyncio 테스트를
쓸 수 없다.
"""

import threading
import time
from typing import Callable

from websockets.sync.server import serve as _ws_serve

from stage.camera import CameraRelay
from stage.cues import CueSheet
from stage.director import MIN_CHARS, Director, UnitMismatch
from stage.machine import Command
from stage.protocol import ROLES, ProtocolError, decode, encode


class StageServer:
    def __init__(
        self,
        sheet: CueSheet,
        generate: Callable[[str, str, list[dict]], str],
        expect_units: dict[str, str] | None = None,
        warn: Callable[[str], None] = print,
        level_name: str = "일반",
        docent_min_chars: int = MIN_CHARS,
        hub=None,
        level_min_chars: dict[str, int] | None = None,
        on_level_change: Callable[[str], None] | None = None,
        camera: CameraRelay | None = None,
    ) -> None:
        self._warn = warn
        self._conns: dict[str, object] = {}
        self._lock = threading.Lock()
        # 대시보드 허브 — **덕 타이핑**(`publish(kind, **fields)`만 있으면 된다).
        # `None`(기본값)이면 아무것도 안 한다 — 허브 도입 전 호출부·테스트가
        # 그대로 통과해야 한다.
        self._hub = hub
        # `level_name`/`docent_min_chars` 를 그대로 `Director` 로 흘려보낸다 —
        # 여기서 기본값으로 삼키면(예: 인자를 받고 안 넘기면) `Director` 는 늘
        # 기본값("일반"·40자)으로 돌고, `main()` 이 아무리 제대로 읽어도 이 자리에서
        # 끊긴다. (~~`mc_lines`~~ 는 고정 대본 전환으로 없앴다.) `stage/__main__.py::main()`
        # 이 이 값들을 채워 넘긴다.
        #
        # `level_min_chars`/`on_level_change`(관람객 수준 실시간 전환)도 같은 길이다.
        # 둘 중 목록만 닿고 훅이 빠지면 `Director` 가 기동에서 ValueError 로 막는다 —
        # 반쯤 끊긴 배선으로 도는 것보다 낫다. `main()` → 여기 → `Director` 한 줄은
        # `tests/test_stage_main.py::test_main_에서_감독까지_수준_전환이_끝까지_이어진다`
        # 가 지킨다.
        self.director = Director(
            sheet, generate=generate, send=self._send,
            expect_units=expect_units, warn=warn,
            level_name=level_name,
            docent_min_chars=docent_min_chars,
            level_min_chars=level_min_chars,
            on_level_change=on_level_change,
        )
        self.camera = camera if camera is not None else CameraRelay(
            send_robot=self._send_raw, warn=warn,
        )

    def _publish(self, kind: str, **fields) -> None:
        """대시보드 허브로 흘린다. **감독이 락을 쥔 채 부르는 자리**(`_send`)에서도
        불리므로 허브는 쌓기만 한다(`stage/dashboard_hub.py`). 허브가 없으면 아무것도 안 한다."""
        if self._hub is not None:
            self._hub.publish(kind, **fields)

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
            # 성공한 뒤에만 흘린다 — 실패하면 위 경고가 이미 남고, 허브에 "보냈다"고
            # 잘못 남기지 않는다(감독이 락을 쥔 채 부르는 자리라 여기서는 publish 만 한다).
            self._publish("sent", role=role, type=cmd.type, fields=dict(cmd.fields))
        except Exception as exc:
            self._warn(f"[{role}] 전송 실패({type(exc).__name__}: {exc})")

    def _send_raw(self, role: str, type_: str, fields: dict) -> None:
        """`CameraRelay` 가 로봇에게 camera/rtc 를 보낼 때 쓴다. `_send` 와 달리 허브에
        싣지 않는다 — ICE·SDP 는 초당 수십 개·수 KB 라 이력 200칸을 밀어낸다."""
        with self._lock:
            ws = self._conns.get(role)
        if ws is None:
            self._warn(f"[{role}] 아직 붙지 않았다 — {type_} 를 버린다")
            return
        try:
            ws.send(encode(type_, **fields))
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
                    caps = self._caps_field(role, msg)
                    try:
                        self.director.on_hello(
                            role, msg.get("unit_id"), msg.get("version", ""), caps
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
                    # `director.on_hello` 가 던지지 않은 뒤에만 이 블록에 온다 —
                    # `director.on_hello` 자신이 거절 검사를 caps 기록보다 먼저
                    # 두는 것과 같은 이유다. 거꾸로 이 블록 전체를 더 앞에 두면
                    # (리뷰 Important 1) `UnitMismatch` 로 거절된 사칭 로봇(이
                    # 역할로 붙은 적이 없다)의 caps 가 정상 로봇의 카메라를
                    # 경고 한 줄 없이 꺼 버린다.
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
                    # `self._conns[role] = ws` **뒤에만** 부른다(최종 전체 브랜치
                    # 리뷰 C1). `CameraRelay.on_robot_hello` → `_recompute` →
                    # `_set_pair(on=True)` 가 곧바로 `_send_raw` 로 이 role 에게
                    # `camera{on:true}` 를 보내려 하는데, `_send_raw` 는
                    # `self._conns` 에서 소켓을 찾는다. 등록보다 먼저 부르면
                    # (예전 순서) 대시보드 시청자가 이미 붙어 있을 때 그 송신이
                    # "아직 붙지 않았다" 로 조용히 버려지고, `CameraRelay._active`
                    # 는 이미 True 로 찍혀 있어 재계산해도 다시 안 보낸다 —
                    # 화면은 빈 채 사유 문구도 없다. 이 세션에서 두 로봇의
                    # **첫 hello** 에서 실기로 그대로 재현됐다(스테일 브라우저
                    # 탭이 로봇보다 먼저 시청자로 붙어 있었다). `_conns[role]=ws`
                    # 를 늦게 두는 이 순서 실수는 이 파일에서 **두 번째**다 —
                    # 첫 번째는 바로 위 `UnitMismatch` 검사(커밋 195d3f6) — "자원을
                    # 등록하기 전에 그 자원을 쓸 줄 아는 컴포넌트부터 깨운다" 는
                    # 같은 실수가 다른 자원(`_conns`)을 상대로 또 났다.
                    self.camera.on_robot_hello(role, caps)
                    self._warn(f"[{role}] 붙었다 (version={msg.get('version')})")
                    self._publish("connect", role=role, version=msg.get("version"))
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
                    self._publish("disconnect", role=role)
                    self.director.on_disconnect(role)
                    self.camera.on_robot_disconnect(role)
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

    def _caps_field(self, role: str, msg: dict) -> list[str] | None:
        """hello 의 선택 필드 `caps`(로봇 앱이 할 줄 아는 것, 예: `["emotion", "react", "gaze"]`).

        **없으면 None** — 옛 로봇 앱은 보내지 않는다. 감독은 None 을 빈 목록으로 본다. 로봇이
        보내는 형식은 넓히기만 하고 바꾸지 않는다. ~~`["solo"]`~~ 는 2026-09-25 단독을 감독이 맡으면서 안 쓴다.

        문자열 목록이 아니면 경고하고 None(능력 없음). 연결은 끊지 않는다 — 규약 위반은
        그 필드만 버린다(`_str_field` 와 같은 원칙). 특히 `"react"` 처럼 목록 대신 문자열이
        오면 그대로 넘겼을 때 `set("react")` 가 글자 집합이 되어 **아무 말 없이** 반응이 안
        나간다 — 운영자는 "이 앱은 react 를 모른다" 경고만 보고 원인을 앱에서 찾게 된다.
        """
        caps = msg.get("caps")
        if caps is None:
            return None
        if isinstance(caps, list) and all(isinstance(c, str) for c in caps):
            return caps
        self._warn(f"[{role}] hello 의 caps 가 문자열 목록이 아니다 — 무시한다: {caps!r}")
        return None

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
            # 검증을 통과해 감독에게 넘기기 **직전**에 남긴다 — 사회자가
            # LISTENING 이 아니어서 감독이 이 heard 를 버리더라도(위 listener
            # 게이트는 이미 통과했다) 운영자는 무엇이 들렸는지 대시보드에서
            # 봐야 한다.
            self._publish("recv", role=role, type="heard", fields={"text": text})
            self.director.on_heard(text)
        elif t in ("speaking_ended", "speaking_started"):
            cue_id = self._str_field(role, msg, "cue_id")
            seq, ok = self._seq_field(role, msg)
            if cue_id is None or not ok:
                return
            self._publish("recv", role=role, type=t, fields={"cue_id": cue_id, "seq": seq})
            if t == "speaking_ended":
                self.director.on_speaking_ended(role, cue_id, seq)
            else:
                # 상태는 say 를 보낼 때 이미 옮겼다(불변식 ②). 여기서 하는 일은
                # **타임아웃 데드라인을 발화 시작 시점으로 다시 거는 것**이다 —
                # 예전에는 `pass` 라, say 를 보낸 뒤 로봇이 실제로 말을 시작하기까지
                # 든 시간이 전부 발화 예산에서 깎였다(리뷰 I3).
                self.director.on_speaking_started(role, cue_id, seq)
        elif t == "error":
            where, detail = str(msg.get("where", "")), str(msg.get("detail", ""))
            self._publish("recv", role=role, type="error", fields={"where": where, "detail": detail})
            self.director.on_error(role, where, detail)
            if where == "camera":
                self.camera.on_robot_error(role, detail)
        elif t == "rtc":
            self.camera.on_robot_rtc(role, msg)
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
