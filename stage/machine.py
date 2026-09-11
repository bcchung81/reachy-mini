"""턴 상태기계 — 네트워크도 LLM도 모른다. 불변식 2개가 전부다.

① `*_SPEAKING` 상태에서는 어느 로봇의 마이크도 열리지 않는다.
   게이트 개방은 `LISTENING` 진입 시점 단 한 곳이다.
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

    def speak(
        self, role: str, cue_id: str, text: str, gaze: str | None = None
    ) -> list[Command]:
        """지정한 로봇에게 대사를 준다."""
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

        # 마이크부터 닫는다. say 보다 먼저 나가야 발화 첫머리가 새지 않는다.
        cmds = [
            Command(to="mc", type="mic", fields={"open": False}),
            Command(to="docent", type="mic", fields={"open": False}),
        ]
        if gaze is not None:
            cmds.append(Command(to=role, type="gaze", fields={"target": gaze}))
        cmds.append(
            Command(to=role, type="say", fields={"cue_id": cue_id, "text": text})
        )
        return cmds

    def on_speaking_ended(self, role: str, cue_id: str) -> list[Command]:
        """발화 종료 보고. 지금 말하는 로봇·큐가 아니면 무시한다."""
        if role != self.speaking_role or cue_id != self.cue_id:
            return []  # 늦게 도착한 유령 메시지 — 상태를 건드리지 않는다
        return self._to_listening()

    def force_listening(self) -> list[Command]:
        """타임아웃 복구. 호출부가 반드시 경고를 남긴다."""
        return self._to_listening()

    def abort(self) -> list[Command]:
        """즉시 중단. 마이크는 열지 않는다 — 사람이 다시 시작시킨다."""
        self.state = State.IDLE
        self.speaking_role = None
        self.cue_id = None
        return [
            Command(to="mc", type="abort"),
            Command(to="docent", type="abort"),
        ]

    def _to_listening(self) -> list[Command]:
        self.state = State.LISTENING
        self.speaking_role = None
        self.cue_id = None
        # **사회자 마이크만 연다.** 관람객 창구는 하나뿐이다(설계 §2).
        return [Command(to="mc", type="mic", fields={"open": True})]


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
