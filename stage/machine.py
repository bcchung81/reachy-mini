"""턴 상태기계 — 네트워크도 LLM도 모른다. 불변식 2개가 전부다.

① `*_SPEAKING` 상태에서는 어느 로봇의 마이크도 열리지 않는다.
   게이트 개방은 `LISTENING` 진입 시점 단 한 곳이다. **`IDLE` 에서도 닫혀 있다** —
   `abort()` 가 양쪽을 닫는다(2026-09-24, 아래 `abort` 주석).
② `speak()` 는 직전 `on_speaking_ended()` 를 받기 전에 다시 부를 수 없다.

①이 자기목소리 루프를 **음향이 아니라 구조로** 막는다. 도슨트 목소리는 사회자
입장에서 진짜 외부 소리라 XMOS AEC 가 지워주지 않는다.
②가 동시 발화를 막는다.

상태 전이를 `speak()` 시점에 **낙관적으로** 한다(`speaking_started` 를 기다리지
않는다). 기다리면 그 사이에 두 번째 `say` 가 새어 들어갈 수 있어 ②가 무너진다.
"""

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    """감독이 보는 진행 상태."""

    IDLE = "idle"
    MC_SPEAKING = "mc_speaking"
    DOCENT_SPEAKING = "docent_speaking"
    LISTENING = "listening"


SPEAKING = (State.MC_SPEAKING, State.DOCENT_SPEAKING)
_SPEAKING_STATE = {"mc": State.MC_SPEAKING, "docent": State.DOCENT_SPEAKING}


@dataclass(frozen=True)
class Command:
    """감독이 로봇 하나에게 내보낼 지시 하나."""

    to: str
    type: str
    fields: dict = field(default_factory=dict)


class TurnError(RuntimeError):
    """불변식을 깨는 요청."""


class TurnMachine:
    """턴 하나를 소유한다. 대사 내용은 호출부가 정한다."""

    def __init__(self) -> None:
        self.state = State.IDLE
        self.speaking_role: str | None = None
        self.cue_id: str | None = None
        # 마지막 `speak()` 의 발화 번호. 종료 보고는 이 번호까지 맞아야 진짜다.
        self.seq = 0

    def speak(
        self, role: str, cue_id: str, text: str, gaze: str | None = None,
        emotion: str | None = None,
    ) -> list[Command]:
        """지정한 로봇에게 대사를 준다.

        `emotion` 은 대본에 적힌 감정 태그다(`stage/cues.py::EMOTIONS`). 로봇이 그
        태그로 모션과 목소리 어조를 고른다 — 없으면 로봇이 문장 속 키워드로 추측한다.
        **안 주면 필드를 넣지 않는다**: 빈 값을 실으면 "감정이 없는 대사" 와
        "감정을 안 보낸 감독" 을 로그에서 못 가른다.
        """
        if role not in _SPEAKING_STATE:
            raise TurnError(f"알 수 없는 역할: {role!r}")
        if self.state in SPEAKING:
            raise TurnError(
                f"{self.speaking_role} 가 아직 말하는 중이다"
                f"(큐 {self.cue_id}) — 동시 발화를 막는다"
            )

        self.state = _SPEAKING_STATE[role]
        self.speaking_role = role
        self.cue_id = cue_id
        # 발화마다 번호를 매긴다. 콘솔 `r`(abort→start)은 **같은 cue_id** 를
        # 다시 발행하므로 (role, cue_id) 만으로는 중단된 발화의 늦은 종료 보고와
        # 새 발화의 종료 보고를 못 가른다 — 그 유령이 통과하면 사회자가 다시
        # 말하는 중에 도슨트가 시작한다(리뷰 A2, 불변식 ② 위반). 로봇은 `say` 에
        # 실려 온 seq 를 `speaking_started`/`speaking_ended` 에 그대로 되돌려준다.
        self.seq += 1

        # 마이크부터 닫는다. say 보다 먼저 나가야 발화 첫머리가 새지 않는다.
        cmds = [
            Command(to="mc", type="mic", fields={"open": False}),
            Command(to="docent", type="mic", fields={"open": False}),
        ]
        if gaze is not None:
            cmds.append(Command(to=role, type="gaze", fields={"target": gaze}))
        say_fields = {"cue_id": cue_id, "seq": self.seq, "text": text}
        if emotion:
            say_fields["emotion"] = emotion
        cmds.append(Command(to=role, type="say", fields=say_fields))
        return cmds

    def is_current(self, role: str, cue_id: str, seq: int | None) -> bool:
        """이 (role, cue_id, seq) 가 지금 말하는 발화인가 — 유령 판정의 유일한 규칙.

        감독의 `on_speaking_started` 와 여기의 `on_speaking_ended` 가 같은 규칙을
        써야 한다. 두 파일에 두 번 적으면 cue id 체계가 바뀔 때 한쪽만 고쳐진다.
        """
        return role == self.speaking_role and cue_id == self.cue_id and seq == self.seq

    def on_speaking_ended(
        self, role: str, cue_id: str, listener: str = "mc", seq: int | None = None
    ) -> list[Command]:
        """발화 종료 보고. 지금 말하는 로봇·큐·발화 번호가 아니면 무시한다.

        `listener` 는 관람객 창구를 열어 줄 로봇이다 — 보통 사회자지만,
        1인 모드에서는 남은 한 대가 그 역할도 겸한다(`Director._who()`).
        `seq` 가 없으면(옛 규약) 유령으로 본다 — 같은 큐가 재발행되는
        콘솔 `r` 경로에서 seq 없이는 진짜와 유령을 가를 수 없기 때문이다.
        """
        if not self.is_current(role, cue_id, seq):
            return []  # 늦게 도착한 유령 메시지 — 상태를 건드리지 않는다
        return self._to_listening(listener)

    def force_listening(self, listener: str = "mc") -> list[Command]:
        """타임아웃 복구. 호출부가 반드시 경고를 남긴다."""
        return self._to_listening(listener)

    def abort(self) -> list[Command]:
        """즉시 중단. **양쪽 마이크를 닫는다** — 사람이 다시 시작시킨다.

        ~~마이크는 열지 않는다~~ 만으로는 모자랐다. LISTENING 에서 멈추면 열려 있던
        리스너 마이크가 IDLE 내내 그대로 남아, 사회자 STT 가 전시장 소음을 계속
        올렸다(감독 로그에 IDLE 전사 221건 — `'아'`·`'omeome…'` 등). 감독이 버리긴
        하지만 STT 서버가 헛돌고 로그가 진짜 신호를 덮는다. 닫는 쪽이 불변식 ①과도
        맞다 — 마이크가 열리는 상태는 LISTENING 하나뿐이다.
        """
        self.state = State.IDLE
        self.speaking_role = None
        self.cue_id = None
        return [
            Command(to="mc", type="mic", fields={"open": False}),
            Command(to="docent", type="mic", fields={"open": False}),
            Command(to="mc", type="abort"),
            Command(to="docent", type="abort"),
        ]

    def _to_listening(self, listener: str) -> list[Command]:
        self.state = State.LISTENING
        self.speaking_role = None
        self.cue_id = None
        # **리스너의 마이크만, 정확히 하나만 연다.** 관람객 창구는 하나뿐이다
        # (설계 §2). 보통은 사회자가 리스너다 — 도슨트는 평소 절대 듣지
        # 않는다. 하지만 사회자가 없으면(1인 모드, 설계 §7) 남은 로봇이
        # 관람객 창구 자체를 겸한다. 그래서 "사회자 마이크" 가 아니라
        # "리스너의 마이크" 가 불변이다 — 누가 리스너인지는 호출부
        # (`Director._who("mc")`) 가 정한다, 이 클래스는 로봇 배치를 모른다.
        return [Command(to=listener, type="mic", fields={"open": True})]


def coalesce(cmds: list[Command]) -> list[Command]:
    """한 번에 내보낼 지시 묶음을 정리한다.

    두 가지를 한다:
    1. 같은 로봇의 마이크 지시는 **마지막 것만** 남긴다. MC 발화 종료(열기)
       직후 도슨트 발화 시작(닫기)이 이어지면 마이크가 깜빡 열렸다 닫히는데,
       그 사이에 들어온 소리가 STT 로 새면 유령 발화가 된다.
    2. 마이크 지시를 앞으로 보낸다. 닫기 전에 말하기 시작하면 발화 첫머리가
       자기 마이크로 들어간다.
    """
    last_mic: dict[str, Command] = {}
    rest: list[Command] = []
    for c in cmds:
        if c.type == "mic":
            last_mic[c.to] = c
        else:
            rest.append(c)
    return list(last_mic.values()) + rest
