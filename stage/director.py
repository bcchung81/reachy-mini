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

    # ── 상태 ──────────────────────────────────────────────────────
    @property
    def state(self) -> State:
        return self._machine.state

    # ── 로봇에게서 오는 것 ────────────────────────────────────────
    def on_hello(self, role: str, unit_id: str | None, version: str) -> None:
        """역할 자기신고. 두 대가 뒤바뀐 채 시연을 시작하는 것을 여기서 막는다."""
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
        cmds = self._machine.on_speaking_ended(role, cue_id)
        if not cmds:
            return  # 유령 메시지 — 상태를 건드리지 않는다
        self._deadline = None

        cue = self._sheet.current()
        if role == "mc" and cue_id == cue.id:
            cmds = cmds + self._speak_docent(cue)
        self._emit(cmds)

    def on_error(self, role: str, where: str, detail: str) -> None:
        self._warn(f"[{role}] {where} 에서 오류: {detail}")

    # ── 바깥에서 부르는 것 ────────────────────────────────────────
    def start(self) -> None:
        self._begin_cue(self._sheet.current())

    def tick(self) -> None:
        """타임아웃 감시. 서버 루프가 주기적으로 부른다."""
        if self._deadline is None or self._now() < self._deadline:
            return
        role = self._machine.speaking_role
        self._warn(f"[{role}] 발화 종료 응답이 없다 — 강제로 듣기 상태로 되돌린다")
        self._deadline = None
        self._emit(self._machine.force_listening())

    def abort(self) -> None:
        self._deadline = None
        self._emit(self._machine.abort())

    # ── 내부 ──────────────────────────────────────────────────────
    def _begin_cue(self, cue: Cue) -> None:
        # **도슨트 대사를 미리 만든다.** 사회자가 고정 대사를 말하는 3~5초 동안
        # 생성이 끝나므로 LLM 지연이 섹션 전환에 실리지 않는다.
        self._docent_text = None
        self._docent_ready.clear()
        self._gen_thread = threading.Thread(
            target=self._generate_docent, args=(cue,), daemon=True
        )
        self._gen_thread.start()
        self._emit(self._machine.speak("mc", cue.id, cue.mc, gaze=cue.gaze))

    def _generate_docent(self, cue: Cue) -> None:
        try:
            self._docent_text = self._generate(cue.docent_brief, list(self.history))
        except Exception as exc:
            # 조용히 벙어리가 되지 않는다. 지시문을 그대로 읽는 것이
            # 아무 말도 안 하는 것보다 낫다.
            self._warn(f"LLM 생성 실패({type(exc).__name__}: {exc}) — 지시문으로 폴백")
            self._docent_text = cue.docent_brief
        finally:
            self._docent_ready.set()

    def _speak_docent(self, cue: Cue) -> list[Command]:
        if not self._docent_ready.wait(timeout=GENERATE_GRACE_S):
            self._warn("도슨트 대사 생성이 늦다 — 지시문으로 폴백")
            self._docent_text = cue.docent_brief
        text = self._docent_text or cue.docent_brief
        self.history.append({"role": "assistant", "content": f"도슨트: {text}"})
        return self._machine.speak("docent", cue.id, text, gaze="audience")

    def _answer(self, question: str) -> None:
        cue = self._sheet.current()
        self.history.append({"role": "user", "content": f"관람객: {question}"})
        brief = (
            f"관람객이 '{question}' 라고 물었다. 지금 섹션은 '{cue.title}' 이다. "
            "도슨트로서 3문장 이내로 답한다."
        )
        try:
            text = self._generate(brief, list(self.history))
        except Exception as exc:
            self._warn(f"LLM 응답 실패({type(exc).__name__}: {exc}) — 폴백")
            text = "죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?"
        self.history.append({"role": "assistant", "content": f"도슨트: {text}"})
        self._emit(self._machine.speak("docent", f"{cue.id}:qa", text, gaze="audience"))

    def _emit(self, cmds: list[Command]) -> None:
        for cmd in coalesce(cmds):
            if cmd.type == "say":
                self._deadline = self._now() + self._estimate(cmd.fields["text"])
            self._send(cmd.to, cmd)

    @staticmethod
    def _estimate(text: str) -> float:
        return len(text) / CHARS_PER_SEC + TIMEOUT_MARGIN_S
