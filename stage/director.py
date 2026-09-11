"""무대감독 — 턴·대사·마이크를 중계한다.

**전송을 모른다.** `send(role, command)` 콜러블만 받는다. 그래서 종단 흐름
전체가 소켓 없이 테스트된다. WebSocket 배선은 `stage/__main__.py` 가 한다.

LLM 호출을 여기서 독점한다 — 사회자와 도슨트가 **하나의 대화 이력**을 봐야
말이 이어지기 때문이다. TTS 는 로봇에 남는다(목소리가 달라야 한다).
"""

import threading
import time
from typing import Callable

from stage.cues import Cue, CueSheet, is_advance
from stage.machine import Command, State, TurnMachine, coalesce

# 발화 길이 추정치. 실측(2026-09-11, Qwen3-TTS 1.7B CustomVoice, 배속 1.0):
#   34자 → 7.04초 (4.8자/초),  57자 → 10.64초 (5.4자/초),  25자 → 4.00초 (6.3자/초)
# 타임아웃은 **일찍 터지면 안 되므로** 가장 느린 쪽보다 더 보수적으로 잡는다.
CHARS_PER_SEC = 4.0
TIMEOUT_MARGIN_S = 5.0

# 도슨트 대사 생성이 사회자 발화보다 늦어질 때 더 기다려 줄 한도.
GENERATE_GRACE_S = 8.0


class UnitMismatch(RuntimeError):
    """로봇이 신고한 hardware id 가 기대값과 다르다 — 두 대가 뒤바뀌었다."""


class Director:
    def __init__(
        self,
        sheet: CueSheet,
        generate: Callable[[str, list[dict]], str],
        send: Callable[[str, Command], None],
        now: Callable[[], float] = time.monotonic,
        expect_units: dict[str, str] | None = None,
        warn: Callable[[str], None] = print,
    ) -> None:
        self._sheet = sheet
        self._generate = generate
        self._send = send
        self._now = now
        self._expect_units = expect_units or {}
        self._warn = warn

        self._machine = TurnMachine()
        self.history: list[dict] = []

        self._deadline: float | None = None
        self._docent_text: str | None = None
        self._docent_ready = threading.Event()
        self._gen_thread: threading.Thread | None = None
        # 세대 번호 — `_begin_cue` 가 부를 때마다 하나씩 올라간다. 늦게 끝난
        # 생성 스레드가 이미 다음 큐로 넘어간 뒤에 결과를 들고 오면, 세대가
        # 안 맞으므로 버린다. 락은 "세대 확인 + 결과 반영"을 한 번에 묶어
        # 그 사이에 `_begin_cue` 가 끼어드는 경합을 막는다.
        self._gen_lock = threading.Lock()
        self._gen_token = 0

        # 진입점 직렬화. `stage/server.py` 가 붙은 뒤로는 `tick()` 이 타이머
        # 스레드에서, 나머지는 커넥션마다 다른 스레드에서 불린다. 이 락이
        # 없으면: tick() 이 데드라인 만료를 판정한 직후(`_deadline`/
        # `speaking_role` 을 아직 안 건드린 시점), 커넥션 스레드가
        # 사회자→도슨트 핸드오프를 통째로 끝내 상태를 옮긴 뒤, tick() 이
        # 이어서 `force_listening()` 을 불러 **도슨트가 말하는 도중** 사회자
        # 마이크를 강제로 연다 — 불변식 ① 위반이다. `force_listening()` 이
        # 부르는 `TurnMachine._to_listening()` 은 현재 상태를 재확인하지
        # 않는 무조건 전이라 이 경합을 스스로 막지 못한다. 게다가 그 강제
        # 전이가 `speaking_role`/`cue_id` 를 리셋해 버려서, 도슨트의 진짜
        # `speaking_ended` 가 나중에 도착하면 유령 메시지로 조용히 버려진다
        # — 도슨트 발화가 타임아웃 보호를 통째로 잃는다.
        #
        # 공개 진입점(`start`/`on_hello`/`on_heard`/`on_speaking_ended`/
        # `on_error`/`tick`/`abort`) 을 전부 이 락으로 직렬화하면 "만료 판정
        # → 강제 전이"가 원자적이 된다 — 세 문제(마이크 오픈, 엉뚱한 로봇을
        # 지목하는 경고, 유령 처리된 진짜 종료)가 한 번에 없어진다. 어느
        # 공개 메서드도 다른 공개 메서드를 부르지 않으므로(전부 `_begin_cue`
        # 등 내부 헬퍼만 거친다) 재진입이 필요 없어 일반 Lock 으로 충분하다.
        #
        # `_speak_docent()` 의 유예시간(`GENERATE_GRACE_S`, 최대 8초) 대기는
        # 이 락을 쥔 채로 일어난다 — 그동안 tick() 은 막힌다. 의도한
        # 동작이다: 사회자→도슨트 핸드오프가 진행 중일 때는 애초에 아무것도
        # 타임아웃돼서는 안 된다. 생성 스레드(`_generate_docent`)는 이 락을
        # 절대 요구하지 않는다 — `_gen_lock` 만 짧게 쥐었다 놓으므로, 진입
        # 락을 쥔 스레드가 생성 완료를 기다리는 동안에도 생성 스레드는
        # 막히지 않는다(교착 없음).
        self._lock = threading.Lock()

        self._connected: set[str] = set()

    # ── 상태 ──────────────────────────────────────────────────────
    @property
    def state(self) -> State:
        return self._machine.state

    @property
    def solo_role(self) -> str | None:
        """한 대만 붙어 있으면 그 역할. 둘 다거나 둘 다 없으면 None."""
        if len(self._connected) == 1:
            return next(iter(self._connected))
        return None

    def on_connect(self, role: str) -> None:
        # `server.py::handler` 가 커넥션 스레드에서 부르는 새 공개 진입점이다.
        # 다른 공개 메서드 안에서(`_who()` 를 통해서든) 이걸 부르지 않으므로
        # `self._lock` 을 또 쥐어도 재진입 걱정이 없다 — `_connected` 를
        # 커넥션 스레드 여럿이 동시에 건드리는 경합만 막으면 된다.
        with self._lock:
            self._connected.add(role)

    def on_disconnect(self, role: str) -> None:
        with self._lock:
            self._connected.discard(role)
            if self.solo_role is not None:
                self._warn(
                    f"[{role}] 이 끊겼다 — 1인 모드로 내려간다. "
                    f"{self.solo_role} 가 양쪽 대사를 읽는다"
                )

    def _who(self, preferred: str) -> str:
        """대사를 읽을 로봇. 1인 모드면 남은 한 대가 전부 읽는다."""
        solo = self.solo_role
        return solo if solo is not None else preferred

    # ── 로봇에게서 오는 것 ────────────────────────────────────────
    def on_hello(self, role: str, unit_id: str | None, version: str) -> None:
        """역할 자기신고. 두 대가 뒤바뀐 채 시연을 시작하는 것을 여기서 막는다."""
        with self._lock:
            expected = self._expect_units.get(role)
            if expected is None:
                return
            if unit_id is None:
                # 시뮬(macOS)에서는 언제나 None 이다 — get_hardware_id() 가 리눅스
                # sysfs 를 읽는다. 여기서 막으면 실기 없이 개발할 수 없다.
                self._warn(f"[{role}] unit_id 가 없다 — 실기라면 확인할 것 (시뮬은 정상)")
                return
            if unit_id != expected:
                raise UnitMismatch(
                    f"{role} 자리에 다른 로봇이 있다: 기대 {expected!r}, 신고 {unit_id!r}. "
                    "사회자와 도슨트가 뒤바뀌었는지 확인한다."
                )

    def on_heard(self, text: str) -> None:
        with self._lock:
            if self._machine.state is not State.LISTENING:
                self._warn(f"발화 중({self._machine.state.value})에 들린 말을 버린다: {text!r}")
                return
            if is_advance(text):
                nxt = self._sheet.advance()
                if nxt is None:
                    self._warn("마지막 큐다 — 더 진행할 곳이 없다")
                    return
                self._begin_cue(nxt)
                return
            self._answer(text)

    def on_speaking_ended(self, role: str, cue_id: str) -> None:
        with self._lock:
            cmds = self._machine.on_speaking_ended(role, cue_id)
            if not cmds:
                return  # 유령 메시지 — 상태를 건드리지 않는다
            self._deadline = None

            # 큐 id 만으로 "사회자 몫이 방금 끝났다" 를 판정한다 — role 은
            # 안 본다. `_speak_docent` 가 도슨트 몫에는 `f"{cue.id}:docent"`
            # 처럼 구분되는 id 를 쓰므로(§ 리뷰 finding 1), 맨 cue.id 는
            # 두 모드 어디서든 사회자 몫에만 붙는다. 1인 모드에서는 같은
            # 로봇이 두 몫을 연달아 말하므로 role 로는 구분이 안 된다 —
            # role 로 갈랐다가 도슨트 몫이 끝난 뒤에도 다시 도슨트 몫을
            # 트리거해 자기 대사를 무한 반복하는 버그가 났었다.
            cue = self._sheet.current()
            if cue_id == cue.id:
                cmds = cmds + self._speak_docent(cue)
            self._emit(cmds)

    def on_error(self, role: str, where: str, detail: str) -> None:
        with self._lock:
            self._warn(f"[{role}] {where} 에서 오류: {detail}")

    # ── 바깥에서 부르는 것 ────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            self._begin_cue(self._sheet.current())

    def tick(self) -> None:
        """타임아웃 감시. 서버 루프가 주기적으로 부른다.

        진입 락 아래에서 판정과 강제 전이를 한 번에 묶는다 — 그렇지 않으면
        판정 직후 다른 스레드가 핸드오프를 끝내고, 그 뒤에야 이 메서드가
        옛 데드라인을 근거로 방금 말을 시작한 로봇의 마이크를 강제로 연다
        (불변식 ① 위반. `__init__` 의 `self._lock` 주석 참고).
        """
        with self._lock:
            if self._deadline is None or self._now() < self._deadline:
                return
            role = self._machine.speaking_role
            self._warn(f"[{role}] 발화 종료 응답이 없다 — 강제로 듣기 상태로 되돌린다")
            self._deadline = None
            self._emit(self._machine.force_listening())

    def abort(self) -> None:
        with self._lock:
            self._deadline = None
            self._emit(self._machine.abort())

    # ── 내부 ──────────────────────────────────────────────────────
    def _begin_cue(self, cue: Cue) -> None:
        # **도슨트 대사를 미리 만든다.** 사회자가 고정 대사를 말하는 3~5초 동안
        # 생성이 끝나므로 LLM 지연이 섹션 전환에 실리지 않는다.
        with self._gen_lock:
            self._docent_text = None
            self._docent_ready = threading.Event()
            self._gen_token += 1
            token = self._gen_token
        self._gen_thread = threading.Thread(
            target=self._generate_docent, args=(cue, token), daemon=True
        )
        self._gen_thread.start()
        self._emit(
            self._machine.speak(self._who("mc"), cue.id, cue.mc, gaze=cue.gaze)
        )

    def _generate_docent(self, cue: Cue, token: int) -> None:
        try:
            text = self._generate(cue.docent_brief, list(self.history))
            if not text:
                # 빈 문자열도 "아무 말도 안 하는 것"과 같다 — 조용히 넘기지 않는다.
                self._warn(f"[{cue.id}] 도슨트 대사 생성이 빈 문자열을 내놓았다 — 지시문으로 폴백")
                text = cue.docent_brief
        except Exception as exc:
            # 조용히 벙어리가 되지 않는다. 지시문을 그대로 읽는 것이
            # 아무 말도 안 하는 것보다 낫다.
            self._warn(f"LLM 생성 실패({type(exc).__name__}: {exc}) — 지시문으로 폴백")
            text = cue.docent_brief

        with self._gen_lock:
            if token != self._gen_token:
                # 이 결과가 나올 즈음 이미 다음 큐가 시작됐다. 그대로 반영하면
                # 엉뚱한 큐의 대사가 조용히 새어 들어간다 — 버리고 소리 낸다.
                self._warn(f"[{cue.id}] 도슨트 대사 생성이 늦게 끝나 버려졌다(다음 큐로 이미 넘어갔다)")
                return
            self._docent_text = text
            ready = self._docent_ready
        ready.set()

    def _speak_docent(self, cue: Cue) -> list[Command]:
        if not self._docent_ready.wait(timeout=GENERATE_GRACE_S):
            self._warn("도슨트 대사 생성이 늦다 — 지시문으로 폴백")
            self._docent_text = cue.docent_brief
        text = self._docent_text
        if not text:
            self._warn(f"[{cue.id}] 도슨트 대사가 비어 있다 — 지시문으로 폴백")
            text = cue.docent_brief
        self.history.append({"role": "assistant", "content": f"도슨트: {text}"})
        # 사회자 몫과 구분되는 id 를 쓴다 — `_answer` 의 `:qa` 와 같은 이유다.
        # 맨 `cue.id` 는 "사회자 몫이 끝났다" 판정에 `on_speaking_ended` 가
        # 그대로 쓰므로, 도슨트 몫까지 같은 id 를 쓰면(리뷰 finding 1) 1인
        # 모드에서 같은 로봇이 도슨트 몫을 끝낸 speaking_ended 가 다시
        # "사회자 몫이 끝났다" 로 오판돼 도슨트 몫을 무한히 반복한다.
        return self._machine.speak(
            self._who("docent"), f"{cue.id}:docent", text, gaze="audience"
        )

    def _answer(self, question: str) -> None:
        cue = self._sheet.current()
        self.history.append({"role": "user", "content": f"관람객: {question}"})
        brief = (
            f"관람객이 '{question}' 라고 물었다. 지금 섹션은 '{cue.title}' 이다. "
            "도슨트로서 3문장 이내로 답한다."
        )
        try:
            text = self._generate(brief, list(self.history))
            if not text:
                self._warn("도슨트 응답 생성이 빈 문자열을 내놓았다 — 폴백")
                text = "죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?"
        except Exception as exc:
            self._warn(f"LLM 응답 실패({type(exc).__name__}: {exc}) — 폴백")
            text = "죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?"
        self.history.append({"role": "assistant", "content": f"도슨트: {text}"})
        self._emit(
            self._machine.speak(
                self._who("docent"), f"{cue.id}:qa", text, gaze="audience"
            )
        )

    def _emit(self, cmds: list[Command]) -> None:
        for cmd in coalesce(cmds):
            if cmd.type == "say":
                self._deadline = self._now() + self._estimate(cmd.fields["text"])
            self._send(cmd.to, cmd)

    @staticmethod
    def _estimate(text: str) -> float:
        return len(text) / CHARS_PER_SEC + TIMEOUT_MARGIN_S
