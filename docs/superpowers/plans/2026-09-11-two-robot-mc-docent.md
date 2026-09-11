# 사회자 + 도슨트 2대 구성 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전파체험관 큐시트를 사회자 로봇과 도슨트 로봇이 주고받으며 진행하고, 관람객은 사회자에게만 말을 건다.

**Architecture:** 로봇 2대가 각자 기존 `main.py`(`ReachyMiniApp`)를 돌리고 오디오는 로컬에 유지한다. 노트북의 무대감독(stage director)이 WebSocket으로 두 로봇을 묶어 턴·대사·마이크 게이팅을 중계한다. LLM 호출은 감독이 독점하고(대화 이력이 하나여야 하므로) TTS만 로봇에 남긴다(목소리가 달라야 하므로).

**Tech Stack:** Python 3.12 / `websockets`(sync API) / PyYAML / pytest. 추론 3종(LLM·STT·TTS)은 기존 그대로 PC에 남는다.

**Spec:** `docs/superpowers/specs/2026-09-11-two-robot-mc-docent-design.md`

## Global Constraints

모든 태스크의 요구사항에 아래가 암묵적으로 포함된다.

- **인터프리터는 `.venv/bin/python`(3.12.13) 하나뿐이다.** 시스템 `python3`(3.14)를 쓰지 않는다.
- **테스트 명령은 `.venv/bin/python -m pytest tests/ -q`** 다. 착수 시점 기준 **235개가 통과**한다 — 회귀를 내면 안 된다.
- **진입점은 `main.py`(`ReachyMiniApp`) 하나다.** 실기가 실행하는 것과 시연에서 돌리는 것이 같아야 한다.
- **대화 로직은 `session.py` 하나뿐이다.** 진입점에 복사하지 않는다.
- **주소는 전부 환경변수다.** 하드코딩한 IP·포트를 코드에 두지 않는다.
- **플랫폼 전용 요소(`say`·`afplay`·`osxaudiosrc`)는 폴백 사다리 안에만 둔다.** 기본 경로는 중립이어야 한다.
- **실패는 소리 내서 실패한다.** 폴백으로 물러날 때 반드시 경고를 남긴다. 조용한 성능저하가 가장 나쁘다.
- **새 서드파티 의존성을 추가하지 않는다.** `websockets<16,>=12` 와 `pyyaml>=6.0` 은 `reachy-mini` SDK가 이미 선언하므로 로봇에서도 쓸 수 있다. 앱이 직접 import 하면 `apps/voice_chat/pyproject.toml` 에 선언한다(선언 누락은 이 저장소가 이미 밟은 지뢰다).
- **`pytest-asyncio` 가 설치돼 있지 않다.** `websockets.sync.server` / `websockets.sync.client` 만 쓴다. asyncio 테스트를 쓰지 않는다.
- **테스트 함수 이름은 한국어로 쓴다** — 이 저장소의 관행이다(`tests/test_deployment_contract.py` 참고).
- **도슨트 마이크는 상시 닫혀 있다.** 관람객 창구는 사회자 하나뿐이다.
- **기대 테스트 개수는 지표다.** 각 단계의 `Expected: N passed` 는 계획이 명시한
  테스트를 그대로 썼을 때의 값이다. 케이스를 더 넣어 숫자가 커지는 것은 정상이고,
  **0 failures 와 기존 235개 무회귀**가 진짜 기준이다. 숫자가 작아지면 빠뜨린 것이다.
- **`@pytest.mark.parametrize` 는 케이스 수만큼 테스트로 센다** — 개수를 셀 때 주의한다.
- **음성 배정은 고정이다**: 사회자 `serena` / 도슨트 `sohee`. 배속은 **1.2 기준 환산값**(사회자 1.27, 도슨트 1.13) — `TTS_QWEN_SPEED` 기본값이 1.0이 아니라 1.2다(`tts.py:46`).

---

## File Structure

**신규 — 노트북에서만 도는 무대감독 (로봇에 올라가지 않는다)**

| 파일 | 책임 |
|---|---|
| `stage/__init__.py` | 패키지 표시 |
| `stage/protocol.py` | 메시지 8종의 인코딩·디코딩·검증. 네트워크를 모른다 |
| `stage/machine.py` | 턴 상태기계. 불변식 2개. 네트워크도 LLM도 모른다 |
| `stage/cues.py` | `cues.yaml` 로더, 진행 신호 키워드 판정, 큐 커서 |
| `stage/director.py` | WS 서버. machine·cues·LLM 을 묶고 타임아웃을 감시한다 |
| `stage/console.py` | 비상 수동 오버라이드(표준입력) |
| `stage/__main__.py` | 기동 진입점 (`python -m stage`) |
| `data/cues.yaml` | 큐시트의 기계 판독 계층 |

**수정 — 로봇 앱**

| 파일 | 변경 |
|---|---|
| `apps/voice_chat/voice_chat/stage_client.py` | 신규. 감독 WS 클라이언트 |
| `apps/voice_chat/voice_chat/session.py` | `respond()` 에서 `speak()` 를 뽑아낸다 |
| `apps/voice_chat/voice_chat/main.py` | `REACHY_ROLE` 로 1대 모드 / 2대 모드 분기 |
| `apps/voice_chat/pyproject.toml` | `websockets` 선언 추가 |

**테스트**

`tests/test_stage_protocol.py` · `tests/test_stage_machine.py` · `tests/test_stage_cues.py` · `tests/test_stage_director.py` · `tests/test_stage_client.py` · `tests/test_session_speak.py` · `tests/test_deployment_contract.py`(확장)

**단계 구분**: Task 1–4 를 끝내면 **로봇 없이 도는 무대감독**이 완성된다(가짜 로봇으로 종단 테스트까지). Task 5–8 이 실제 로봇을 붙인다.

---

## Task 1: 프로토콜

**Files:**
- Create: `stage/__init__.py`
- Create: `stage/protocol.py`
- Test: `tests/test_stage_protocol.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `stage.protocol.ROBOT_MSGS: frozenset[str]` = `{"hello","heard","speaking_started","speaking_ended","error"}`
  - `stage.protocol.DIRECTOR_MSGS: frozenset[str]` = `{"say","mic","gaze","abort"}`
  - `stage.protocol.ROLES: frozenset[str]` = `{"mc","docent"}`
  - `stage.protocol.ProtocolError(ValueError)`
  - `stage.protocol.encode(type_: str, **fields) -> str`
  - `stage.protocol.decode(raw: str) -> dict`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_protocol.py`:

```python
"""무대감독 ↔ 로봇 메시지 규약.

알 수 없는 메시지를 조용히 흘려보내지 않는 것이 이 모듈의 존재 이유다 —
프로토콜이 어긋난 채 도는 것이 시연장에서 가장 찾기 어려운 고장이다.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage import protocol


def test_인코딩과_디코딩이_왕복한다():
    raw = protocol.encode("say", cue_id="02-history", text="맥스웰부터 봅니다")
    msg = protocol.decode(raw)
    assert msg == {"type": "say", "cue_id": "02-history", "text": "맥스웰부터 봅니다"}


def test_한글을_이스케이프하지_않는다():
    # 로그를 사람이 읽어야 한다. \uXXXX 로 새어 나가면 시연장에서 못 읽는다.
    raw = protocol.encode("heard", text="다음으로 넘어가요")
    assert "다음으로 넘어가요" in raw
    assert "\\u" not in raw


def test_알_수_없는_메시지_종류는_인코딩에서_막는다():
    with pytest.raises(protocol.ProtocolError, match="알 수 없는"):
        protocol.encode("셀프토크", text="…")


def test_알_수_없는_메시지_종류는_디코딩에서도_막는다():
    with pytest.raises(protocol.ProtocolError, match="알 수 없는"):
        protocol.decode(json.dumps({"type": "셀프토크"}))


def test_JSON_이_아니면_거절한다():
    with pytest.raises(protocol.ProtocolError, match="JSON"):
        protocol.decode("이건 JSON 이 아니다")


def test_객체가_아니면_거절한다():
    with pytest.raises(protocol.ProtocolError, match="객체"):
        protocol.decode("[1, 2, 3]")


def test_type_이_없으면_거절한다():
    with pytest.raises(protocol.ProtocolError, match="알 수 없는"):
        protocol.decode(json.dumps({"text": "type 이 빠졌다"}))


def test_메시지_종류는_9종뿐이다():
    # 규약이 늘어나면 여기서 먼저 깨져야 한다 — 설계 문서 §4 와 짝이다.
    assert len(protocol.ROBOT_MSGS | protocol.DIRECTOR_MSGS) == 9
    assert protocol.ROLES == {"mc", "docent"}
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_protocol.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage'`

- [ ] **Step 3: 최소 구현을 쓴다**

`stage/__init__.py`:

```python
"""무대감독 — 로봇 2대(사회자·도슨트)의 턴을 중계한다.

이 패키지는 **노트북에서만 돈다.** 로봇에 올라가지 않는다.
로봇 쪽 코드는 `apps/voice_chat/` 에 있다.
"""
```

`stage/protocol.py`:

```python
"""무대감독 ↔ 로봇 메시지. 한 줄 JSON.

메시지는 9종뿐이고, **모르는 것은 즉시 거절한다.** 조용히 무시하면
프로토콜이 어긋난 채로 계속 돌고, 시연장에서 원인을 찾을 수 없다.
설계 문서 §4 의 표와 짝이다 — 한쪽만 고치지 않는다.
"""

import json

ROBOT_MSGS = frozenset(
    {"hello", "heard", "speaking_started", "speaking_ended", "error"}
)
DIRECTOR_MSGS = frozenset({"say", "mic", "gaze", "abort"})
KNOWN_MSGS = ROBOT_MSGS | DIRECTOR_MSGS
ROLES = frozenset({"mc", "docent"})


class ProtocolError(ValueError):
    """메시지가 규약에 맞지 않는다."""


def encode(type_: str, **fields) -> str:
    """메시지 한 줄을 만든다.

    `ensure_ascii=False` 는 취향이 아니라 요구사항이다 — 로그를 사람이 읽는다.
    """
    if type_ not in KNOWN_MSGS:
        raise ProtocolError(f"알 수 없는 메시지 종류: {type_!r}")
    return json.dumps({"type": type_, **fields}, ensure_ascii=False)


def decode(raw: str) -> dict:
    """메시지 한 줄을 읽는다. 규약에 안 맞으면 ProtocolError."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"JSON 이 아니다: {raw[:80]!r}") from exc
    if not isinstance(msg, dict):
        raise ProtocolError(f"객체가 아니다: {type(msg).__name__}")
    if msg.get("type") not in KNOWN_MSGS:
        raise ProtocolError(f"알 수 없는 메시지 종류: {msg.get('type')!r}")
    return msg
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_protocol.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 전체 회귀를 확인한다**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 243 passed (기존 235 + 신규 8)

- [ ] **Step 6: 커밋**

```bash
git add stage/__init__.py stage/protocol.py tests/test_stage_protocol.py
git commit -m "feat(stage): 무대감독 ↔ 로봇 메시지 규약

모르는 메시지를 조용히 흘려보내지 않는다 — 프로토콜이 어긋난 채 도는 것이
시연장에서 가장 찾기 어려운 고장이다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 2: 턴 상태기계

설계의 심장이다. 네트워크도 LLM도 모르는 순수 로직이라 로봇 없이 전부 테스트된다.

**Files:**
- Create: `stage/machine.py`
- Test: `tests/test_stage_machine.py`

**Interfaces:**
- Consumes: `stage.protocol.ROLES`
- Produces:
  - `stage.machine.State(str, Enum)` — 멤버 `IDLE`/`MC_SPEAKING`/`DOCENT_SPEAKING`/`LISTENING`
  - `stage.machine.SPEAKING: tuple[State, State]`
  - `stage.machine.Command` — `frozen dataclass(to: str, type: str, fields: dict)`
  - `stage.machine.TurnError(RuntimeError)`
  - `stage.machine.TurnMachine` — 속성 `state: State`, `speaking_role: str | None`, `cue_id: str | None`
    - `speak(role: str, cue_id: str, text: str, gaze: str | None = None) -> list[Command]`
    - `on_speaking_ended(role: str, cue_id: str) -> list[Command]`
    - `force_listening() -> list[Command]`
    - `abort() -> list[Command]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_machine.py`:

```python
"""턴 상태기계 — 불변식 2개가 이 모듈의 전부다.

① `*_SPEAKING` 상태에서는 어느 로봇의 마이크도 열리지 않는다.
② `say` 는 직전 `speaking_ended` 를 받기 전에 다시 보내지 않는다.

①이 자기목소리 루프를 **음향이 아니라 구조로** 막는다. 도슨트 목소리는 사회자
입장에서 진짜 외부 소리라 XMOS AEC 가 지워주지 않는다 — AEC 에 기대는 설계는
여기서 반드시 깨진다. 이 저장소는 1대 구성에서 이미 자기목소리 루프를 밟았다.
"""

import pathlib
import random
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.machine import Command, State, TurnError, TurnMachine


def mic_opens(cmds):
    return [c for c in cmds if c.type == "mic" and c.fields.get("open") is True]


def test_시작은_IDLE_이다():
    assert TurnMachine().state is State.IDLE


def test_사회자에게_대사를_주면_MC_SPEAKING_이_된다():
    m = TurnMachine()
    cmds = m.speak("mc", "01-intro", "안녕하세요")
    assert m.state is State.MC_SPEAKING
    assert m.speaking_role == "mc"
    assert m.cue_id == "01-intro"
    says = [c for c in cmds if c.type == "say"]
    assert len(says) == 1
    assert says[0].to == "mc"
    assert says[0].fields["text"] == "안녕하세요"
    assert says[0].fields["cue_id"] == "01-intro"


def test_발화를_시작하면_양쪽_마이크를_닫는다():
    # 불변식 ① — 도슨트가 말할 때 사회자가 그 말을 받아적으면 안 된다.
    m = TurnMachine()
    cmds = m.speak("docent", "02-history", "1864년 맥스웰이…")
    closed = {c.to for c in cmds if c.type == "mic" and c.fields["open"] is False}
    assert closed == {"mc", "docent"}
    assert mic_opens(cmds) == []


def test_gaze_를_주면_그_로봇에게_함께_보낸다():
    m = TurnMachine()
    cmds = m.speak("mc", "02-history", "도슨트, 부탁해요", gaze="partner")
    gazes = [c for c in cmds if c.type == "gaze"]
    assert len(gazes) == 1
    assert gazes[0].to == "mc"
    assert gazes[0].fields["target"] == "partner"


def test_gaze_가_없으면_gaze_를_보내지_않는다():
    m = TurnMachine()
    cmds = m.speak("mc", "01-intro", "안녕하세요")
    assert [c for c in cmds if c.type == "gaze"] == []


def test_발화가_끝나면_LISTENING_이_되고_사회자_마이크만_연다():
    # 관람객 창구는 사회자 하나뿐이다 — 도슨트 마이크는 상시 닫힘.
    m = TurnMachine()
    m.speak("docent", "02-history", "1864년 맥스웰이…")
    cmds = m.on_speaking_ended("docent", "02-history")
    assert m.state is State.LISTENING
    assert m.speaking_role is None
    opened = mic_opens(cmds)
    assert len(opened) == 1
    assert opened[0].to == "mc"


def test_발화_중에_또_말하라고_하면_거절한다():
    # 불변식 ② — 두 로봇이 동시에 말하는 사고를 여기서 막는다.
    m = TurnMachine()
    m.speak("mc", "01-intro", "안녕하세요")
    with pytest.raises(TurnError, match="mc"):
        m.speak("docent", "02-history", "끼어들기")
    assert m.state is State.MC_SPEAKING


def test_다른_로봇의_종료_보고는_무시한다():
    # 늦게 도착한 유령 메시지가 상태를 무너뜨리면 안 된다.
    m = TurnMachine()
    m.speak("mc", "01-intro", "안녕하세요")
    assert m.on_speaking_ended("docent", "01-intro") == []
    assert m.state is State.MC_SPEAKING


def test_다른_큐의_종료_보고는_무시한다():
    m = TurnMachine()
    m.speak("mc", "01-intro", "안녕하세요")
    assert m.on_speaking_ended("mc", "99-없는큐") == []
    assert m.state is State.MC_SPEAKING


def test_타임아웃_복구는_무조건_LISTENING_으로_되돌린다():
    m = TurnMachine()
    m.speak("mc", "01-intro", "안녕하세요")
    cmds = m.force_listening()
    assert m.state is State.LISTENING
    assert [c.to for c in mic_opens(cmds)] == ["mc"]


def test_abort_는_양쪽을_멈추고_IDLE_로_간다():
    m = TurnMachine()
    m.speak("docent", "02-history", "1864년 맥스웰이…")
    cmds = m.abort()
    assert m.state is State.IDLE
    assert {c.to for c in cmds if c.type == "abort"} == {"mc", "docent"}
    assert mic_opens(cmds) == []


def test_무작위_사건_열에서도_불변식이_깨지지_않는다():
    """생성 테스트 — 손으로 못 떠올린 순서를 기계가 떠올리게 한다."""
    rng = random.Random(20260911)
    for _ in range(500):
        m = TurnMachine()
        for _ in range(40):
            op = rng.choice(["speak", "ended", "force", "abort"])
            if op == "speak":
                role = rng.choice(["mc", "docent"])
                try:
                    cmds = m.speak(role, f"c{rng.randint(0, 3)}", "…")
                except TurnError:
                    assert m.state in (State.MC_SPEAKING, State.DOCENT_SPEAKING)
                    continue
            elif op == "ended":
                cmds = m.on_speaking_ended(
                    rng.choice(["mc", "docent"]), f"c{rng.randint(0, 3)}"
                )
            elif op == "force":
                cmds = m.force_listening()
            else:
                cmds = m.abort()

            # 불변식 ① — 발화 중에는 어떤 마이크도 열리지 않는다
            if m.state in (State.MC_SPEAKING, State.DOCENT_SPEAKING):
                assert mic_opens(cmds) == [], f"{m.state} 에서 마이크가 열렸다"
            # 열리는 마이크는 언제나 사회자 것뿐이다
            assert all(c.to == "mc" for c in mic_opens(cmds))
            # 발화 중인 로봇은 최대 하나다
            assert (m.speaking_role is None) == (
                m.state not in (State.MC_SPEAKING, State.DOCENT_SPEAKING)
            )


def test_Command_는_불변이다():
    c = Command(to="mc", type="mic", fields={"open": True})
    with pytest.raises(Exception):
        c.to = "docent"
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_machine.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.machine'`

- [ ] **Step 3: 최소 구현을 쓴다**

`stage/machine.py`:

```python
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
```

- [ ] **Step 4: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_machine.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: 전체 회귀를 확인한다**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 256 passed

- [ ] **Step 6: 커밋**

```bash
git add stage/machine.py tests/test_stage_machine.py
git commit -m "feat(stage): 턴 상태기계 — 불변식 2개를 테스트로 박는다

자기목소리 루프를 음향(AEC)이 아니라 구조로 막는다. 도슨트 목소리는 사회자
입장에서 진짜 외부 소리라 XMOS AEC 가 지워주지 않는다.

생성 테스트로 500개 무작위 사건 열에서 불변식을 확인한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 3: 큐시트 로더와 진행 신호 판정

`docs/exhibit-guide.md` 는 산문 원장이라 기계가 진행 단위로 못 읽는다. 그 위에 한 겹 얹는다.

**이 태스크는 앞 4개 섹션만 채운다.** 나머지 15개는 Task 9 에서 채우고, 그때 커버리지 테스트를 켠다.

**Files:**
- Create: `data/cues.yaml`
- Create: `stage/cues.py`
- Test: `tests/test_stage_cues.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `stage.cues.Cue` — `frozen dataclass(id: str, title: str, mc: str, docent_brief: str, gaze: str)`
  - `stage.cues.CueError(ValueError)`
  - `stage.cues.GAZE_TARGETS: frozenset[str]` = `{"partner","audience"}`
  - `stage.cues.cues_path() -> pathlib.Path` — `REACHY_CUES_PATH` 우선, 없으면 `data/cues.yaml`
  - `stage.cues.load_cues(path: pathlib.Path | None = None) -> list[Cue]`
  - `stage.cues.is_advance(text: str) -> bool`
  - `stage.cues.CueSheet` — `__init__(cues: list[Cue])`, `current() -> Cue`, `advance() -> Cue | None`, `reset() -> None`, 속성 `index: int`, `done: bool`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_cues.py`:

```python
"""큐시트 — 진행의 뼈대.

`mc` 는 고정 대사이고 `docent_brief` 는 LLM 에게 주는 **지시**다(대사가 아니다).
사회자를 고정하는 이유는 두 가지다: 진행이 결정적이어야 시연이 안 무너지고,
사회자가 고정 대사를 말하는 3~5초 동안 도슨트 대사를 생성해 **LLM 지연을 숨긴다**.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage import cues as cues_mod
from stage.cues import Cue, CueError, CueSheet, is_advance, load_cues


def write(tmp_path, text):
    p = tmp_path / "cues.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_저장소의_큐시트가_읽힌다():
    loaded = load_cues()
    assert len(loaded) >= 4
    assert loaded[0].id == "01-intro"
    assert all(isinstance(c, Cue) for c in loaded)


def test_모든_큐가_필수_필드를_채우고_있다():
    for c in load_cues():
        assert c.id and c.title and c.mc and c.docent_brief, c.id
        assert c.gaze in cues_mod.GAZE_TARGETS, c.id


def test_큐_id_가_중복되면_거절한다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: partner}
- {id: "a", title: "t2", mc: "m2", docent_brief: "b2", gaze: partner}
""")
    with pytest.raises(CueError, match="중복"):
        load_cues(p)


def test_필수_필드가_비면_거절한다(tmp_path):
    # 조용히 빈 대사를 말하는 로봇이 되는 것이 최악이다.
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "", docent_brief: "b", gaze: partner}
""")
    with pytest.raises(CueError, match="mc"):
        load_cues(p)


def test_모르는_gaze_는_거절한다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: 하늘}
""")
    with pytest.raises(CueError, match="gaze"):
        load_cues(p)


def test_빈_큐시트는_거절한다(tmp_path):
    with pytest.raises(CueError, match="비어"):
        load_cues(write(tmp_path, "[]"))


def test_환경변수로_큐시트_경로를_바꾼다(tmp_path, monkeypatch):
    p = write(tmp_path, """
- {id: "z", title: "t", mc: "m", docent_brief: "b", gaze: partner}
""")
    monkeypatch.setenv("REACHY_CUES_PATH", str(p))
    assert load_cues()[0].id == "z"


# ── 진행 신호 판정 ────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["다음", "계속", "계속하죠", "다음으로", "넘어가요", "진행해"])
def test_진행_신호를_알아본다(text):
    assert is_advance(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "그 다음에 헤르츠는 뭘 했나요?",   # 질문이다 — LLM 으로 넘긴다
        "다음은 뭔가요?",                  # 질문 표지가 있으면 넘기지 않는다
        "마르코니가 누구예요",
        "전파가 뭐예요",
    ],
)
def test_진행_신호가_아닌_것을_넘기지_않는다(text):
    assert not is_advance(text)


# ── 커서 ──────────────────────────────────────────────────────────

def sheet():
    return CueSheet([
        Cue("a", "A", "m1", "b1", "partner"),
        Cue("b", "B", "m2", "b2", "audience"),
    ])


def test_처음에는_첫_큐를_가리킨다():
    s = sheet()
    assert s.index == 0
    assert s.current().id == "a"
    assert not s.done


def test_advance_는_다음_큐를_준다():
    s = sheet()
    assert s.advance().id == "b"
    assert s.index == 1


def test_마지막_다음은_None_이고_done_이_된다():
    s = sheet()
    s.advance()
    assert s.advance() is None
    assert s.done
    assert s.current().id == "b"   # 커서는 마지막에 머문다


def test_reset_은_처음으로_되돌린다():
    s = sheet()
    s.advance()
    s.reset()
    assert s.index == 0
    assert not s.done


def test_빈_큐시트로는_만들_수_없다():
    with pytest.raises(CueError, match="비어"):
        CueSheet([])
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.cues'`

- [ ] **Step 3: 큐시트를 만든다**

`data/cues.yaml` — 내용은 `docs/exhibit-guide.md` §1~§4 에서 가져왔다:

```yaml
# 전파체험관 큐시트 — 기계 판독 계층.
#
# 정본은 docs/exhibit-guide.md 다. 이 파일은 그 위에 얹은 **진행 단위**다.
#   mc            고정 대사. 사회자가 화제를 열고 넘긴다. 결정적이어야 한다
#   docent_brief  LLM 에게 주는 지시이지 대사가 아니다. 여기서 살이 붙는다
#   gaze          partner(상대를 본다) | audience(관람객을 본다)
#
# 사회자 대사가 고정이라 관람객이 "다음"이라 말한 즉시 받아칠 수 있고,
# 그 3~5초 동안 도슨트 대사를 생성한다 — LLM 지연이 전환에 실리지 않는다.

- id: "01-intro"
  title: "체험관 개요"
  mc: "안녕하세요, 전파체험관에 오신 것을 환영합니다. 오늘 진행은 제가 맡고, 해설은 옆에 있는 도슨트가 맡습니다. 도슨트, 이곳이 어떤 곳인지 소개해 줄래요?"
  docent_brief: "KCA가 방송·통신·전파 분야의 교육·홍보, 자료 보존, 연구를 위해 세운 곳이고 2020년 11월에 개관했다는 것. 3문장 이내. 상대연도('몇 년 전')를 쓰지 말고 절대연도로만 말한다."
  gaze: partner

- id: "02-history"
  title: "전파의 발견 역사"
  mc: "자, 다음은 전파의 발견 역사입니다. 도슨트, 전파는 발명일까요 발견일까요?"
  docent_brief: "전파는 발명이 아니라 발견이라는 대비가 핵심 훅. 1785년에 존재가 처음 발견됐고, 1901년 마르코니가 영국에서 캐나다까지 1600마일 떨어진 곳으로 모스 신호를 보내 장거리 무선전신에 성공했다는 것. 4문장 이내."
  gaze: partner

- id: "03-theory"
  title: "전파 이론 — 주파수와 파장"
  mc: "이번에는 전파가 무엇인지 원리를 보겠습니다. 도슨트, 주파수와 파장을 쉽게 풀어 주세요."
  docent_brief: "전파는 전기와 자기가 파동의 형태로 퍼져나가는 것이고 볼 수도 만질 수도 없다는 것. '퐁당퐁당'처럼 돌로 일으킨 물결이 건너편 손등에 닿는 비유를 쓴다. 단위는 주파수, 표기는 헤르츠 — 1초에 1회 진동하면 1헤르츠, 1000회면 1킬로헤르츠. 4문장 이내."
  gaze: partner

- id: "04-morse"
  title: "전파이야기 체험 — 모스부호·헤르츠 실험·라이덴 병"
  mc: "여기서부터는 직접 만져볼 수 있는 것들이 있습니다. 도슨트, 무엇을 해볼 수 있나요?"
  docent_brief: "모스부호 변환기(문구를 넣으면 부호가 표시되고 송신키로 직접 쳐볼 수 있음), 헤르츠 실험 도구(스위치를 켜면 구리판으로 고전압이 흘러 전파가 발사되고 원형 고리에서 검출돼 네온전구가 켜짐), 라이덴 병(정전기를 저장하는 최초의 축전지). 4문장 이내."
  gaze: audience
```

- [ ] **Step 4: 로더를 쓴다**

`stage/cues.py`:

```python
"""큐시트 로더와 진행 신호 판정.

정본은 `docs/exhibit-guide.md` 이고 이 모듈이 읽는 `data/cues.yaml` 은 그 위에
얹은 진행 단위다. 둘이 어긋나면 큐시트를 고친다 — 반대가 아니다.
"""

import os
import pathlib
from dataclasses import dataclass

import yaml

GAZE_TARGETS = frozenset({"partner", "audience"})

_REQUIRED = ("id", "title", "mc", "docent_brief", "gaze")

# 진행 신호로 볼 낱말.
_ADVANCE_WORDS = ("다음", "계속", "넘어가", "진행")

# 질문 표지. 하나라도 있으면 진행 신호로 보지 않고 LLM 에 넘긴다 —
# "다음은 뭔가요?" 를 전환으로 먹으면 관람객의 질문이 통째로 사라진다.
_QUESTION_MARKS = ("?", "뭐", "무엇", "어떻게", "왜", "누구", "언제", "어디", "얼마")

# 긴 문장은 질문일 확률이 높다. 전환 지시는 짧다.
_ADVANCE_MAX_CHARS = 15


class CueError(ValueError):
    """큐시트가 규약에 맞지 않는다."""


@dataclass(frozen=True)
class Cue:
    """진행 단위 하나."""

    id: str
    title: str
    mc: str
    docent_brief: str
    gaze: str


def cues_path() -> pathlib.Path:
    """큐시트 경로. `REACHY_CUES_PATH` 가 있으면 그것을 쓴다."""
    override = os.environ.get("REACHY_CUES_PATH")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "cues.yaml"


def load_cues(path: pathlib.Path | None = None) -> list[Cue]:
    """큐시트를 읽는다. 어긋나면 **소리 내서 실패한다.**"""
    p = pathlib.Path(path) if path is not None else cues_path()
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CueError(f"큐시트가 없다: {p}") from exc
    except yaml.YAMLError as exc:
        raise CueError(f"큐시트가 YAML 이 아니다: {p} — {exc}") from exc

    if not raw:
        raise CueError(f"큐시트가 비어 있다: {p}")
    if not isinstance(raw, list):
        raise CueError(f"큐시트는 목록이어야 한다: {p} (지금은 {type(raw).__name__})")

    out: list[Cue] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CueError(f"{p} {i}번째 항목이 매핑이 아니다")
        for key in _REQUIRED:
            if not str(item.get(key, "")).strip():
                raise CueError(f"{p} {i}번째 항목에 {key} 가 비어 있다")
        if item["gaze"] not in GAZE_TARGETS:
            raise CueError(
                f"{p} {item['id']}: 모르는 gaze {item['gaze']!r} "
                f"(쓸 수 있는 값: {sorted(GAZE_TARGETS)})"
            )
        if item["id"] in seen:
            raise CueError(f"{p}: 큐 id 가 중복이다 — {item['id']!r}")
        seen.add(item["id"])
        out.append(Cue(**{k: item[k] for k in _REQUIRED}))
    return out


def is_advance(text: str) -> bool:
    """관람객 발화가 '다음으로' 라는 뜻인가.

    보수적으로 판정한다. 놓치면 LLM 이 답을 만들어 주지만, 질문을 전환으로
    잘못 먹으면 관람객의 물음이 통째로 사라진다.
    """
    t = text.strip()
    if not t or len(t) > _ADVANCE_MAX_CHARS:
        return False
    if any(q in t for q in _QUESTION_MARKS):
        return False
    return any(w in t for w in _ADVANCE_WORDS)


class CueSheet:
    """큐 커서. 어디까지 진행했는지만 안다."""

    def __init__(self, cues: list[Cue]) -> None:
        if not cues:
            raise CueError("큐시트가 비어 있다")
        self._cues = list(cues)
        self._i = 0

    @property
    def index(self) -> int:
        return self._i

    @property
    def done(self) -> bool:
        return self._i >= len(self._cues) - 1

    def current(self) -> Cue:
        return self._cues[self._i]

    def advance(self) -> Cue | None:
        """다음 큐로 간다. 마지막이면 None 을 주고 커서는 머문다."""
        if self._i >= len(self._cues) - 1:
            return None
        self._i += 1
        return self._cues[self._i]

    def reset(self) -> None:
        self._i = 0
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -q`
Expected: PASS (24 passed)

- [ ] **Step 6: 전체 회귀를 확인한다**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 280 passed

- [ ] **Step 7: 커밋**

```bash
git add data/cues.yaml stage/cues.py tests/test_stage_cues.py
git commit -m "feat(stage): 큐시트 로더와 진행 신호 판정

사회자 대사는 고정, 도슨트는 지시(docent_brief)로 생성한다. 사회자가 고정
대사를 말하는 3~5초 동안 도슨트 대사를 만들어 LLM 지연을 숨긴다.

진행 신호는 보수적으로 본다 — 질문을 전환으로 잘못 먹으면 관람객의 물음이
통째로 사라진다. 놓치는 쪽은 LLM 이 받아준다.

큐시트 19섹션 중 4개. 나머지는 후속.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 4: 무대감독

machine·cues·LLM 을 묶는다. **전송(WebSocket)과 로직을 분리한다** — `Director` 는 `send` 콜러블만 알고 소켓을 모른다. 그래야 종단 흐름 전체가 소켓 없이 테스트된다.

**Files:**
- Create: `stage/director.py`
- Modify: `stage/machine.py` (끝에 `coalesce()` 추가)
- Test: `tests/test_stage_director.py`

**Interfaces:**
- Consumes: `stage.machine.{Command, State, TurnMachine, TurnError}`, `stage.cues.{Cue, CueSheet, is_advance}`, `stage.protocol.ROLES`
- Produces:
  - `stage.machine.coalesce(cmds: list[Command]) -> list[Command]`
  - `stage.director.UnitMismatch(RuntimeError)`
  - `stage.director.CHARS_PER_SEC: float` = `4.0`
  - `stage.director.TIMEOUT_MARGIN_S: float` = `5.0`
  - `stage.director.Director` —
    `__init__(sheet: CueSheet, generate: Callable[[str, list[dict]], str], send: Callable[[str, Command], None], now: Callable[[], float] = time.monotonic, expect_units: dict[str, str] | None = None, warn: Callable[[str], None] = print)`
    - `start() -> None` · `on_hello(role, unit_id, version) -> None` · `on_heard(text) -> None` · `on_speaking_ended(role, cue_id) -> None` · `on_error(role, where, detail) -> None` · `tick() -> None` · `abort() -> None`
    - 속성 `state: State`, `history: list[dict]`

- [ ] **Step 1: `coalesce` 의 실패하는 테스트를 쓴다**

`tests/test_stage_machine.py` 끝에 덧붙인다:

```python
from stage.machine import coalesce


def test_coalesce_는_같은_로봇의_낡은_마이크_지시를_버린다():
    # MC 발화 종료(열기) 직후 도슨트 발화 시작(닫기)이 이어지면
    # 마이크가 깜빡 열렸다 닫힌다. 마지막 것만 남긴다.
    cmds = [
        Command(to="mc", type="mic", fields={"open": True}),
        Command(to="mc", type="mic", fields={"open": False}),
        Command(to="docent", type="mic", fields={"open": False}),
        Command(to="docent", type="say", fields={"cue_id": "c1", "text": "…"}),
    ]
    out = coalesce(cmds)
    mics = [c for c in out if c.type == "mic"]
    assert len(mics) == 2
    assert {(c.to, c.fields["open"]) for c in mics} == {("mc", False), ("docent", False)}


def test_coalesce_는_마이크가_아닌_지시의_순서를_지킨다():
    cmds = [
        Command(to="mc", type="gaze", fields={"target": "partner"}),
        Command(to="mc", type="say", fields={"cue_id": "c1", "text": "가"}),
        Command(to="docent", type="say", fields={"cue_id": "c1", "text": "나"}),
    ]
    assert coalesce(cmds) == cmds


def test_coalesce_는_마이크_지시를_say_앞에_둔다():
    # 마이크를 닫기 전에 말하기 시작하면 발화 첫머리가 마이크로 샌다.
    cmds = [
        Command(to="mc", type="say", fields={"cue_id": "c1", "text": "가"}),
        Command(to="mc", type="mic", fields={"open": False}),
    ]
    out = coalesce(cmds)
    assert out[0].type == "mic"
    assert out[1].type == "say"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_machine.py -q`
Expected: FAIL — `ImportError: cannot import name 'coalesce'`

- [ ] **Step 3: `coalesce` 를 구현한다**

`stage/machine.py` 끝에 덧붙인다:

```python
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
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_machine.py -q`
Expected: PASS (16 passed)

- [ ] **Step 5: 무대감독의 실패하는 테스트를 쓴다**

`tests/test_stage_director.py`:

```python
"""무대감독 — machine·cues·LLM 을 묶는다.

전송을 모르므로 소켓 없이 종단 흐름을 전부 돌린다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet
from stage.director import CHARS_PER_SEC, TIMEOUT_MARGIN_S, Director, UnitMismatch
from stage.machine import State


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Harness:
    """감독 하나와 그가 내보낸 지시를 모으는 그릇."""

    def __init__(self, generate=None, expect_units=None):
        self.sent: list[tuple[str, str, dict]] = []
        self.warnings: list[str] = []
        self.clock = Clock()
        self.gen_calls: list[tuple[str, int]] = []
        sheet = CueSheet([
            Cue("c1", "첫째", "사회자 첫 대사", "첫 지시", "partner"),
            Cue("c2", "둘째", "사회자 둘째 대사", "둘째 지시", "audience"),
        ])

        def _gen(brief, history):
            self.gen_calls.append((brief, len(history)))
            if generate is not None:
                return generate(brief, history)
            return f"[{brief} 로 만든 대사]"

        self.d = Director(
            sheet,
            generate=_gen,
            send=lambda role, cmd: self.sent.append((role, cmd.type, cmd.fields)),
            now=self.clock,
            expect_units=expect_units,
            warn=self.warnings.append,
        )

    def types(self, role=None):
        return [(r, t) for r, t, _ in self.sent if role is None or r == role]

    def says(self):
        return [(r, f["text"]) for r, t, f in self.sent if t == "say"]

    def mics(self):
        return [(r, f["open"]) for r, t, f in self.sent if t == "mic"]

    def clear(self):
        self.sent.clear()


def test_시작하면_사회자가_첫_큐를_말한다():
    h = Harness()
    h.d.start()
    assert h.says() == [("mc", "사회자 첫 대사")]
    assert h.d.state is State.MC_SPEAKING


def test_시작할_때_양쪽_마이크를_닫는다():
    h = Harness()
    h.d.start()
    assert sorted(h.mics()) == [("docent", False), ("mc", False)]


def test_사회자가_말하는_동안_도슨트_대사를_미리_만든다():
    """지연 은닉 — 이게 하이브리드의 진짜 이득이다.

    생성은 별도 스레드에서 돈다. `start()` 직후에 `gen_calls` 를 보면
    스레드가 아직 안 돌아 **간헐적으로 실패한다** — 생성 쪽에서 신호를
    받아 결정적으로 기다린다.
    """
    import threading as _t

    started = _t.Event()
    seen: list[str] = []

    def gen(brief, history):
        seen.append(brief)
        started.set()
        return "미리 만든 대사"

    h = Harness(generate=gen)
    h.d.start()
    assert started.wait(2.0), "사회자 발화 시작 시점에 생성이 걸려 있지 않다"
    assert seen == ["첫 지시"]


def test_사회자_발화가_끝나면_도슨트가_바로_받는다():
    h = Harness()
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert h.says() == [("docent", "[첫 지시 로 만든 대사]")]
    assert h.d.state is State.DOCENT_SPEAKING


def test_사회자에서_도슨트로_넘어갈_때_마이크가_열리지_않는다():
    # coalesce 가 하는 일 — 깜빡 열린 사이로 들어온 소리가 유령 발화가 된다.
    h = Harness()
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert all(open_ is False for _, open_ in h.mics())


def test_도슨트_발화가_끝나면_사회자_마이크가_열린다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.clear()
    h.d.on_speaking_ended("docent", "c1")
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]


def test_진행_신호를_들으면_다음_큐로_간다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1")
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == [("mc", "사회자 둘째 대사")]


def test_질문을_들으면_도슨트가_답한다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1")
    h.clear()
    h.d.on_heard("마르코니가 누구예요")
    answered = h.says()
    assert len(answered) == 1
    assert answered[0][0] == "docent"
    assert h.d.state is State.DOCENT_SPEAKING


def test_질문과_답이_대화_이력에_쌓인다():
    # 사회자와 도슨트가 하나의 이력을 본다 — 그래서 말이 이어진다.
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1")
    h.d.on_heard("마르코니가 누구예요")
    roles = [m["role"] for m in h.d.history]
    assert roles[-2:] == ["user", "assistant"]


def test_발화_중에_들린_말은_버리고_경고한다():
    h = Harness()
    h.d.start()          # MC_SPEAKING
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == []
    assert any("발화 중" in w for w in h.warnings)


def test_마지막_큐에서_진행_신호를_받으면_끝내고_경고한다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1")
    h.d.on_heard("다음")                      # c2 로
    h.d.on_speaking_ended("mc", "c2")
    h.d.on_speaking_ended("docent", "c2")
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == []
    assert any("마지막" in w for w in h.warnings)


def test_발화_종료가_안_오면_타임아웃으로_복구하고_경고한다():
    h = Harness()
    h.d.start()
    h.clear()
    h.clock.t = len("사회자 첫 대사") / CHARS_PER_SEC + TIMEOUT_MARGIN_S + 0.1
    h.d.tick()
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]
    assert any("응답이 없다" in w for w in h.warnings)


def test_타임아웃_전에는_복구하지_않는다():
    h = Harness()
    h.d.start()
    h.clear()
    h.clock.t = 1.0
    h.d.tick()
    assert h.d.state is State.MC_SPEAKING
    assert h.sent == []


def test_LLM_이_실패하면_지시문을_읽고_경고한다():
    def boom(brief, history):
        raise RuntimeError("추론 서버가 죽었다")

    h = Harness(generate=boom)
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    said = h.says()
    assert len(said) == 1 and said[0][0] == "docent"
    assert said[0][1]                      # 빈 대사를 말하지 않는다
    assert any("LLM" in w for w in h.warnings)


def test_unit_id_가_다르면_기동에서_실패한다():
    # 사회자와 도슨트가 뒤바뀐 채 시연을 시작하는 것을 여기서 막는다.
    h = Harness(expect_units={"mc": "aaaa", "docent": "bbbb"})
    with pytest.raises(UnitMismatch, match="mc"):
        h.d.on_hello("mc", "bbbb", "1.9.0")


def test_unit_id_가_맞으면_통과한다():
    h = Harness(expect_units={"mc": "aaaa", "docent": "bbbb"})
    h.d.on_hello("mc", "aaaa", "1.9.0")
    assert h.warnings == []


def test_unit_id_가_없으면_경고하고_통과한다():
    # 시뮬(macOS)에서는 언제나 None 이다 — 여기서 막으면 개발이 멈춘다.
    h = Harness(expect_units={"mc": "aaaa", "docent": "bbbb"})
    h.d.on_hello("mc", None, "1.9.0")
    assert any("unit_id" in w for w in h.warnings)


def test_로봇이_보낸_오류는_경고로_남는다():
    h = Harness()
    h.d.on_error("docent", "tts", "합성 서버 연결 실패")
    assert any("docent" in w and "tts" in w for w in h.warnings)


def test_abort_는_양쪽을_멈춘다():
    h = Harness()
    h.d.start()
    h.clear()
    h.d.abort()
    assert sorted(h.types()) == [("docent", "abort"), ("mc", "abort")]
    assert h.d.state is State.IDLE
```

- [ ] **Step 6: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.director'`

- [ ] **Step 7: 무대감독을 구현한다**

`stage/director.py`:

```python
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
```

- [ ] **Step 8: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -q`
Expected: PASS (19 passed)

- [ ] **Step 9: 전체 회귀를 확인한다**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 302 passed

- [ ] **Step 10: 커밋**

```bash
git add stage/director.py stage/machine.py tests/test_stage_director.py tests/test_stage_machine.py
git commit -m "feat(stage): 무대감독 — 턴·대사·마이크 중계

전송을 모른다. send 콜러블만 받아 종단 흐름 전체를 소켓 없이 테스트한다.

LLM 호출을 감독이 독점한다 — 사회자와 도슨트가 하나의 대화 이력을 봐야
말이 이어진다. 사회자가 고정 대사를 말하는 동안 도슨트 대사를 미리 만들어
LLM 지연을 섹션 전환에서 걷어낸다.

타임아웃 추정은 실측 기반(4.8~6.3자/초)이되 일찍 터지지 않도록 4.0자/초로
보수적으로 잡았다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 5: WebSocket 서버 배선

Task 1–4 의 로직에 전송을 붙인다. 여기까지 끝내면 **로봇 없이 도는 무대감독**이 완성된다.

**Files:**
- Create: `stage/server.py`
- Create: `stage/__main__.py`
- Test: `tests/test_stage_server.py`

**Interfaces:**
- Consumes: `stage.director.Director`, `stage.protocol.{encode, decode, ProtocolError, ROLES}`, `stage.cues.{CueSheet, load_cues}`
- Produces:
  - `stage.server.StageServer` — `__init__(sheet, generate, expect_units=None, warn=print)`, 속성 `director`, 메서드 `handler(ws) -> None`, `serve(host: str, port: int)` (블로킹), `tick_forever(interval_s: float, should_stop: Callable[[], bool])`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_server.py`:

```python
"""무대감독 WS 서버 — 실제 소켓으로 도는 종단 테스트.

pytest-asyncio 가 없으므로 websockets 의 **sync API** 만 쓴다.

**메시지 개수 주의.** 감독은 큐의 gaze 를 대사와 함께 보낸다. 그래서 말할 차례가
된 로봇은 `mic`·`gaze`·`say` **3통**을 받고 상대는 `mic` 1통만 받는다. 덜 읽으면
남은 것이 다음 단언으로 새어 들어가 **엉뚱한 이유로 통과하는 테스트**가 된다 —
그래서 매 단계 정확한 통수를 걷어낸다.
"""

import json
import pathlib
import sys
import threading
import time

import pytest
from websockets.sync.client import connect

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet
from stage.server import StageServer


@pytest.fixture
def server():
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner")])
    warnings: list[str] = []
    s = StageServer(
        sheet,
        generate=lambda brief, history: "도슨트 대사",
        warn=warnings.append,
    )
    s.warnings = warnings

    from websockets.sync.server import serve as ws_serve

    srv = ws_serve(s.handler, "127.0.0.1", 0)
    s.port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield s
    srv.shutdown()
    t.join(timeout=2)


def url_of(server_):
    return f"ws://127.0.0.1:{server_.port}"


def hello(ws, role, unit_id=None):
    ws.send(json.dumps({"type": "hello", "role": role, "unit_id": unit_id,
                        "version": "1.9.0"}))


def recv(ws, timeout=3.0):
    return json.loads(ws.recv(timeout=timeout))


def drain(ws, n, timeout=3.0):
    """정확히 n 통을 읽는다. 남기면 다음 단언으로 샌다."""
    return [recv(ws, timeout) for _ in range(n)]


def ended(ws, cue_id="c1"):
    ws.send(json.dumps({"type": "speaking_ended", "cue_id": cue_id}))


def start_and_drain(server_, mc, docent):
    """두 로봇을 붙이고 첫 큐를 시작한 뒤 그 메시지를 남김없이 걷어낸다."""
    hello(mc, "mc")
    hello(docent, "docent")
    time.sleep(0.2)                      # 등록이 끝나기를 기다린다
    server_.director.start()
    return drain(mc, 3), drain(docent, 1)   # mic·gaze·say / mic


def test_두_로봇이_붙고_시작하면_사회자가_대사를_받는다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        mc_msgs, doc_msgs = start_and_drain(server, mc, docent)
        assert {m["type"] for m in mc_msgs} == {"mic", "gaze", "say"}
        said = next(m for m in mc_msgs if m["type"] == "say")
        assert said["text"] == "사회자 대사"
        # 도슨트는 마이크만 닫힌다 — 불변식 ①
        assert [m["type"] for m in doc_msgs] == ["mic"]
        assert doc_msgs[0]["open"] is False


def test_사회자_발화가_끝나면_도슨트가_대사를_받는다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        ended(mc)
        doc_msgs = drain(docent, 3)      # mic·gaze·say
        assert any(m["type"] == "say" and m["text"] == "도슨트 대사"
                   for m in doc_msgs)
        # 전환 중 사회자 마이크는 열리지 않는다 — coalesce 가 하는 일
        mc_msgs = drain(mc, 1)
        assert mc_msgs[0]["type"] == "mic" and mc_msgs[0]["open"] is False


def test_들은_말이_감독에_닿는다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        ended(mc)
        drain(docent, 3)
        drain(mc, 1)
        ended(docent)
        opened = drain(mc, 1)            # 이제서야 사회자 마이크가 열린다
        assert opened[0]["type"] == "mic" and opened[0]["open"] is True

        mc.send(json.dumps({"type": "heard", "text": "마르코니가 누구예요"}))
        doc_msgs = drain(docent, 3)
        assert any(m["type"] == "say" for m in doc_msgs)


def test_hello_없이_보낸_메시지는_거절하고_끊는다(server):
    with connect(url_of(server)) as ws:
        ws.send(json.dumps({"type": "heard", "text": "안녕"}))
        time.sleep(0.3)
        assert any("hello" in w for w in server.warnings)


def test_모르는_역할은_거절한다(server):
    with connect(url_of(server)) as ws:
        hello(ws, "감독")
        time.sleep(0.3)
        assert any("역할" in w for w in server.warnings)


def test_망가진_메시지는_경고하고_연결을_유지한다(server):
    with connect(url_of(server)) as mc:
        hello(mc, "mc")
        time.sleep(0.2)
        mc.send("이건 JSON 이 아니다")
        time.sleep(0.3)
        assert any("JSON" in w for w in server.warnings)
        mc.send(json.dumps({"type": "heard", "text": "다음"}))   # 아직 살아 있다
        time.sleep(0.2)


def test_붙지_않은_로봇에게_보내면_경고한다(server):
    with connect(url_of(server)) as mc:
        hello(mc, "mc")
        time.sleep(0.2)
        server.director.start()           # 도슨트가 없다
        drain(mc, 3)
        assert any("docent" in w and "붙지" in w for w in server.warnings)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_server.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.server'`

- [ ] **Step 3: 서버를 구현한다**

`stage/server.py`:

```python
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
                    continue

                self._dispatch(role, msg)
        finally:
            if role is not None:
                with self._lock:
                    if self._conns.get(role) is ws:
                        del self._conns[role]
                self._warn(f"[{role}] 연결이 끊어졌다")

    def _dispatch(self, role: str, msg: dict) -> None:
        t = msg["type"]
        if t == "heard":
            self.director.on_heard(msg.get("text", ""))
        elif t == "speaking_ended":
            self.director.on_speaking_ended(role, msg.get("cue_id", ""))
        elif t == "speaking_started":
            pass  # 기록용. 상태는 say 를 보낼 때 이미 옮겼다(불변식 ②)
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
```

`stage/__main__.py`:

```python
"""무대감독 기동 — `python -m stage`.

주소는 전부 환경변수다:
    REACHY_DIRECTOR_HOST   기본 0.0.0.0
    REACHY_DIRECTOR_PORT   기본 8777
    REACHY_MC_UNIT         사회자 로봇의 hardware id (없으면 검증 생략)
    REACHY_DOCENT_UNIT     도슨트 로봇의 hardware id
    REACHY_LLM_URL         추론 서버 (llm.py 의 기본값을 따른다)
    REACHY_CUES_PATH       큐시트 경로 (기본 data/cues.yaml)
"""

import os
import pathlib
import sys
import threading

from stage.cues import CueSheet, load_cues
from stage.server import StageServer

# 대화 로직은 앱 하나에만 둔다 — LLM 클라이언트를 다시 쓰지 않고 그것을 가져온다.
# tests/ 가 쓰는 것과 같은 경로 삽입 방식이다.
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parent.parent / "apps/voice_chat/voice_chat")
)
from llm import LLMClient  # noqa: E402


def build_generate() -> "callable":
    client = LLMClient(system_prompt=_system_prompt())

    def generate(brief: str, history: list[dict]) -> str:
        client.history = list(history)
        return "".join(client.chat_stream(brief, None))

    return generate


def _system_prompt() -> str:
    return (
        "너는 전파체험관의 도슨트다. 지시를 받으면 관람객에게 들려줄 해설을 "
        "말한다. 지시문을 따라 읽지 말고 해설로 바꿔 말한다. "
        "상대연도('몇 년 전')를 쓰지 않고 절대연도로만 말한다. "
        "모르는 것은 지어내지 않는다."
    )


def main() -> None:
    host = os.environ.get("REACHY_DIRECTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("REACHY_DIRECTOR_PORT", "8777"))
    expect = {
        k: v
        for k, v in (
            ("mc", os.environ.get("REACHY_MC_UNIT")),
            ("docent", os.environ.get("REACHY_DOCENT_UNIT")),
        )
        if v
    }
    if not expect:
        print("⚠ REACHY_MC_UNIT / REACHY_DOCENT_UNIT 이 없다 — 역할 검증을 건너뛴다")

    server = StageServer(CueSheet(load_cues()), build_generate(), expect_units=expect)
    stop = threading.Event()
    threading.Thread(
        target=server.tick_forever, args=(0.5, stop.is_set), daemon=True
    ).start()

    from stage.console import run_console

    srv = server.serve(host, port)
    print(f"무대감독 대기 중 — ws://{host}:{port}")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        run_console(server.director)
    finally:
        stop.set()
        srv.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 콘솔을 만든다**

`stage/console.py`:

```python
"""비상 수동 오버라이드.

진행의 정본은 관람객 발화다. 이 콘솔은 **전시장 소음으로 오인식이 나거나
진행이 멈췄을 때 사람이 되돌리기 위한 폴백**이다 — 기본 경로가 아니다.
"""

from stage.director import Director

HELP = """
  n  다음 큐로   |  r  현재 큐 다시  |  s  시작
  a  즉시 중단   |  ?  도움말        |  q  종료
"""


def run_console(director: Director) -> None:
    print(HELP)
    while True:
        try:
            cmd = input("무대감독> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if cmd in ("q", "quit"):
            return
        if cmd == "s":
            director.start()
        elif cmd == "n":
            director.on_heard("다음")
        elif cmd == "r":
            director.abort()
            director.start()
        elif cmd == "a":
            director.abort()
        elif cmd == "?":
            print(HELP)
        elif cmd:
            print(f"모르는 명령: {cmd!r}  — ? 로 도움말")
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_server.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 313 passed

- [ ] **Step 7: 커밋**

```bash
git add stage/server.py stage/__main__.py stage/console.py tests/test_stage_server.py
git commit -m "feat(stage): WebSocket 서버 배선과 비상 콘솔

여기까지로 로봇 없이 도는 무대감독이 완성된다.

websockets 의 sync API 를 쓴다 — SDK 가 io/ws_client.py 에서 쓰는 것과 같고,
이 저장소에는 pytest-asyncio 가 없다.

붙지 않은 로봇에게 보내는 지시를 조용히 삼키지 않는다 — 한쪽만 말하는
시연이 되고 원인을 못 찾는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 6: 로봇 측 무대감독 클라이언트

여기서부터 실제 로봇을 붙인다.

**Files:**
- Create: `apps/voice_chat/voice_chat/stage_client.py`
- Modify: `apps/voice_chat/pyproject.toml` (`dependencies` 에 `websockets` 추가)
- Test: `tests/test_stage_client.py`

**Interfaces:**
- Consumes: `stage.protocol.{encode, decode}` 와 **같은 규약**이지만 `stage/` 를 import 하지 않는다 — `stage/` 는 노트북에만 있고 로봇에는 올라가지 않는다. 규약을 이 파일에 다시 적는다(9종 상수와 encode/decode 최소본).
- Produces:
  - `stage_client.Handlers` — `dataclass(on_say, on_mic, on_gaze, on_abort)`; 각각 `on_say(cue_id: str, text: str, gaze: str | None) -> None`, `on_mic(open_: bool) -> None`, `on_gaze(target: str) -> None`, `on_abort() -> None`
  - `stage_client.StageClient` — `__init__(url: str, role: str, handlers: Handlers, unit_id: str | None = None, version: str = "", warn: Callable[[str], None] = print)`
    - `run(should_stop: Callable[[], bool], connect_fn=None) -> None` (블로킹, 끊기면 재접속)
    - `heard(text)` · `speaking_started(cue_id)` · `speaking_ended(cue_id)` · `error(where, detail)`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_client.py`:

```python
"""로봇 측 무대감독 클라이언트.

가짜 연결을 주입해 소켓 없이 시험한다 — `run(connect_fn=...)`.
"""

import json
import pathlib
import queue
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from stage_client import Handlers, StageClient


class FakeWS:
    """서버가 보낼 메시지를 미리 넣어 두는 가짜 연결."""

    def __init__(self, inbox=()):
        self.sent: list[dict] = []
        self._inbox = queue.Queue()
        for m in inbox:
            self._inbox.put(json.dumps(m))
        self.closed = False

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def __iter__(self):
        while True:
            try:
                yield self._inbox.get(timeout=0.3)
            except queue.Empty:
                return

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def collector():
    got = []
    return got, Handlers(
        on_say=lambda cue_id, text, gaze: got.append(("say", cue_id, text, gaze)),
        on_mic=lambda open_: got.append(("mic", open_)),
        on_gaze=lambda target: got.append(("gaze", target)),
        on_abort=lambda: got.append(("abort",)),
    )


def run_once(ws, role="mc", unit_id="abc", warn=None):
    got, handlers = collector()
    c = StageClient("ws://x", role, handlers, unit_id=unit_id,
                    version="1.9.0", warn=warn or (lambda m: None))
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    c.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    return c, got, calls


def test_붙으면_hello_를_먼저_보낸다():
    ws = FakeWS()
    run_once(ws)
    assert ws.sent[0] == {"type": "hello", "role": "mc",
                          "unit_id": "abc", "version": "1.9.0"}


def test_say_를_받으면_핸들러로_넘긴다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕", "gaze": "partner"}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", "partner") in got


def test_gaze_가_없는_say_도_받는다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕"}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", None) in got


def test_mic_과_gaze_와_abort_를_넘긴다():
    ws = FakeWS([
        {"type": "mic", "open": False},
        {"type": "gaze", "target": "audience"},
        {"type": "abort"},
    ])
    _, got, _ = run_once(ws)
    assert ("mic", False) in got
    assert ("gaze", "audience") in got
    assert ("abort",) in got


def test_로봇이_보낼_수_있는_메시지를_보낸다():
    ws = FakeWS()
    c, _, _ = run_once(ws)
    c._ws = ws                     # run 이 끝난 뒤에도 직접 확인한다
    c.heard("다음")
    c.speaking_started("c1")
    c.speaking_ended("c1")
    c.error("tts", "합성 실패")
    types = [m["type"] for m in ws.sent[1:]]
    assert types == ["heard", "speaking_started", "speaking_ended", "error"]
    assert ws.sent[1]["text"] == "다음"
    assert ws.sent[-1] == {"type": "error", "where": "tts", "detail": "합성 실패"}


def test_감독이_보낼_수_없는_메시지는_경고하고_무시한다():
    warns = []
    ws = FakeWS([{"type": "heard", "text": "감독이 이걸 보내면 안 된다"}])
    _, got, _ = run_once(ws, warn=warns.append)
    assert got == []
    assert any("heard" in w for w in warns)


def test_망가진_메시지는_경고하고_연결을_유지한다():
    warns = []
    ws = FakeWS()
    ws._inbox.put("이건 JSON 이 아니다")
    ws._inbox.put(json.dumps({"type": "mic", "open": True}))
    _, got, _ = run_once(ws, warn=warns.append)
    assert ("mic", True) in got
    assert any("JSON" in w for w in warns)


def test_연결이_끊기면_다시_붙는다():
    got, handlers = collector()
    warns = []
    c = StageClient("ws://x", "mc", handlers, unit_id=None, version="1.9.0",
                    warn=warns.append)
    boxes = [FakeWS(), FakeWS([{"type": "mic", "open": True}])]
    calls = {"n": 0}

    def connect_fn(url):
        i = calls["n"]
        calls["n"] += 1
        if i >= len(boxes):
            raise RuntimeError("그만")
        return boxes[i]

    c.run(should_stop=lambda: calls["n"] >= 2 and boxes[1].closed,
          connect_fn=connect_fn, retry_s=0.0)
    assert calls["n"] >= 2
    assert ("mic", True) in got
    assert any("다시" in w or "재접속" in w for w in warns)


def test_연결_전에_보내면_경고하고_버린다():
    warns = []
    got, handlers = collector()
    c = StageClient("ws://x", "mc", handlers, warn=warns.append)
    c.heard("다음")
    assert any("연결" in w for w in warns)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage_client'`

- [ ] **Step 3: 구현한다**

`apps/voice_chat/voice_chat/stage_client.py`:

```python
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
```

- [ ] **Step 4: 의존성을 선언한다**

`apps/voice_chat/pyproject.toml` 의 `dependencies` 에 추가한다(기존 항목 뒤, `PyGObject` 줄 앞):

```toml
    # stage_client.py 가 무대감독에 붙는 데 쓴다. reachy-mini 가 이미
    # `websockets<16,>=12` 로 끌어오지만, **우리가 직접 import 하는 것은
    # 우리가 선언한다** — 선언 누락은 이 저장소가 이미 밟은 지뢰다
    # (docs/real-robot-deployment.md §3).
    "websockets>=12,<16",
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_client.py -q`
Expected: PASS (9 passed)

- [ ] **Step 6: 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 324 passed

- [ ] **Step 7: 커밋**

```bash
git add apps/voice_chat/voice_chat/stage_client.py apps/voice_chat/pyproject.toml tests/test_stage_client.py
git commit -m "feat(app): 로봇 측 무대감독 클라이언트

stage/ 를 import 하지 않는다 — 그 패키지는 노트북에만 있고 로봇에는 앱만
올라간다. 규약을 다시 적되 설계 문서 §4 를 정본으로 짝지어 관리한다.

연결 전에 보낸 메시지를 조용히 버리지 않는다 — 감독이 영원히 기다린다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 7: `session.py` 를 쪼갠다

`respond()` 가 **LLM 호출 → TTS → 모션**을 한 덩어리로 묶고 있다. 2대 구성에서 로봇은 LLM 을 부르지 않고 텍스트를 받으므로, 말하고 움직이는 부분만 뽑아낸다.

**Files:**
- Modify: `apps/voice_chat/voice_chat/session.py`
- Test: `tests/test_session_speak.py`

**Interfaces:**
- Consumes: 기존 `session.build`
- Produces: `session.speak(text: str, speaker, player, category: str = "neutral") -> None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_session_speak.py`:

```python
"""speak() — 받은 텍스트를 말하고 움직인다. LLM 을 부르지 않는다.

1대 구성에서는 respond() 가 LLM 을 부른 뒤 이것을 쓰고,
2대 구성에서는 무대감독이 만든 텍스트로 이것만 쓴다.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import session


class FakeSpeaker:
    def __init__(self):
        self.spoken: list[str] = []
        self.many: list[list[str]] = []
        self.speaking = False

    def speak(self, text, seed=None):
        self.spoken.append(text)

    def speak_many(self, texts):
        self.many.append(list(texts))


class FakePlayer:
    def __init__(self):
        self.played: list[tuple[str, bool]] = []

    def play_for(self, category, force=False):
        self.played.append((category, force))
        return f"move_{category}"

    def play(self, name, force=False):
        self.played.append((name, force))
        return name


def test_텍스트를_말한다():
    sp = FakeSpeaker()
    session.speak("안녕하세요", sp, None)
    assert sp.spoken == ["안녕하세요"]


def test_로봇이_없으면_말만_한다():
    sp = FakeSpeaker()
    session.speak("안녕하세요", sp, None)      # player=None
    assert sp.spoken == ["안녕하세요"]


def test_모션을_함께_낸다():
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("안녕하세요", sp, pl, category="greet")
    assert pl.played == [("greet", False)]


def test_빈_텍스트는_말하지도_움직이지도_않는다():
    # 감독이 빈 대사를 보내는 사고가 나도 로봇이 헛돌지 않는다.
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("   ", sp, pl)
    assert sp.spoken == [] and pl.played == []


def test_재생_완료를_기다리지_않는다():
    # 기다리면 마이크 루프가 멈춰 끼어들기 판정이 한 번도 돌지 않는다.
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("안녕하세요", sp, pl)
    assert not hasattr(sp, "waited")


def test_respond_는_여전히_동작한다():
    # 1대 구성 회귀 방지 — speak() 를 뽑아내도 기존 경로가 살아 있어야 한다.
    assert callable(session.respond)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_session_speak.py -q`
Expected: FAIL — `AttributeError: module 'session' has no attribute 'speak'`

- [ ] **Step 3: `speak()` 를 뽑아낸다**

`session.py` 의 `respond()` 정의 **바로 앞**에 추가한다:

```python
def speak(text: str, speaker, player, category: str = "neutral") -> None:
    """받은 텍스트를 말하고 그에 맞는 모션을 낸다. **LLM 을 부르지 않는다.**

    1대 구성에서는 `respond()` 가 LLM 스트림을 받은 뒤 이 경로로 말하고,
    2대 구성에서는 무대감독이 만든 텍스트로 이것만 쓴다.

    **재생 완료를 기다리지 않는다.** 기다리면 그동안 마이크 루프가 멈춰
    끼어들기 판정이 한 번도 돌지 않는다 — 재생 중 마이크를 어떻게 다룰지는
    호출부가 정한다(`voice_loop` 의 게이팅, `stage_client` 의 mic 지시).
    """
    text = (text or "").strip()
    if not text:
        # 빈 대사를 말하는 로봇이 되지 않는다. 감독 쪽 사고를 여기서 흡수한다.
        return
    if player is not None:
        name = player.play_for(category)
        print(f"  [모션 {category}/{name}]")
    print(f"미니> {text}")
    speaker.speak(text)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_session_speak.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: 전체 회귀 — 1대 구성이 안 깨졌는지 본다**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 330 passed

- [ ] **Step 6: 커밋**

```bash
git add apps/voice_chat/voice_chat/session.py tests/test_session_speak.py
git commit -m "refactor(app): session.speak() 를 뽑아낸다

2대 구성에서 로봇은 LLM 을 부르지 않고 무대감독이 만든 텍스트를 받는다.
말하고 움직이는 부분만 분리한다. 대화 로직은 여전히 session.py 하나다.

빈 대사를 흡수한다 — 감독 쪽 사고로 로봇이 헛돌지 않게.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 8: 역할 배선과 음성 설정

`main.py` 가 `REACHY_ROLE` 로 1대 모드와 2대 모드를 가른다. **진입점은 여전히 하나다.**

**Files:**
- Modify: `apps/voice_chat/voice_chat/main.py`
- Modify: `tests/test_deployment_contract.py` (확장)
- Create: `scripts/stage-env.sh`
- Test: `tests/test_stage_role.py`

**Interfaces:**
- Consumes: `stage_client.{Handlers, StageClient}`, `session.{build, speak, announce_endpoints, announce_voice}`, `voice_loop.voice_loop`
- Produces: `main.stage_run(reachy_mini, stop_event, role: str) -> None` (`VoiceChat.run` 이 역할이 있으면 이쪽으로 간다)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_role.py`:

```python
"""역할 배선 — 1대 모드와 2대 모드는 같은 진입점에서 갈린다."""

import pathlib
import sys

import pytest

APP = pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"
sys.path.insert(0, str(APP))
import main as main_mod

_VOICE_ENV = ("TTS_QWEN_VOICE", "TTS_QWEN_SPEED", "TTS_QWEN_INSTRUCT")


class _FakeClient:
    """StageClient 대역 — heard() 로 올라온 것만 모은다."""

    def __init__(self, sink: list):
        self._sink = sink

    def heard(self, text: str) -> None:
        self._sink.append(text)


@pytest.fixture(autouse=True)
def 음성_환경변수_원복():
    """`apply_role_voice` 는 `os.environ.setdefault` 를 쓴다 — monkeypatch 가
    추적하지 못해 다음 테스트로 값이 샌다. 직접 스냅샷하고 되돌린다."""
    import os

    saved = {k: os.environ.get(k) for k in _VOICE_ENV}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_ROLE_이_없으면_1대_모드다(monkeypatch):
    monkeypatch.delenv("REACHY_ROLE", raising=False)
    assert main_mod.role_of_env() is None


@pytest.mark.parametrize("role", ["mc", "docent"])
def test_ROLE_을_알아본다(monkeypatch, role):
    monkeypatch.setenv("REACHY_ROLE", role)
    assert main_mod.role_of_env() == role


def test_모르는_ROLE_은_소리_내서_실패한다(monkeypatch):
    # 오타 하나로 조용히 1대 모드가 되면 시연장에서 못 찾는다.
    monkeypatch.setenv("REACHY_ROLE", "사회자")
    with pytest.raises(ValueError, match="REACHY_ROLE"):
        main_mod.role_of_env()


def test_대문자와_공백을_받아준다(monkeypatch):
    monkeypatch.setenv("REACHY_ROLE", "  MC ")
    assert main_mod.role_of_env() == "mc"


def test_stage_run_이_있다():
    assert callable(main_mod.stage_run)


def test_마이크가_닫혀_있으면_감독에_올리지_않는다():
    """불변식 ① 이 로봇 쪽에서 실제로 성립하는지 — 장부가 아니라 동작으로."""
    import threading

    sent: list[str] = []
    gate = threading.Event()          # 닫힌 상태
    sink = main_mod.make_heard_sink(
        _FakeClient(sent), gate, log=lambda m: None
    )
    sink("상대 로봇이 말한 내용")
    assert sent == []


def test_마이크가_열려_있으면_감독에_올린다():
    import threading

    sent: list[str] = []
    gate = threading.Event()
    gate.set()
    sink = main_mod.make_heard_sink(
        _FakeClient(sent), gate, log=lambda m: None
    )
    sink("다음")
    assert sent == ["다음"]


def test_버릴_때_소리_내서_남긴다():
    """조용히 버리면 시연장에서 '왜 안 듣지' 를 추적할 수 없다."""
    import threading

    logs: list[str] = []
    sink = main_mod.make_heard_sink(
        _FakeClient([]), threading.Event(), log=logs.append
    )
    sink("버려질 말")
    assert any("버림" in m for m in logs)


def test_역할별_음성이_문서와_일치한다():
    # 설계 §11. 배속은 1.0 이 아니라 **1.2 기준 환산값**이다(tts.py:46).
    assert main_mod.ROLE_VOICE == {
        "mc": {"voice": "serena", "speed": "1.27",
               "instruct": "밝고 또렷하게, 진행자처럼 활기차게"},
        "docent": {"voice": "sohee", "speed": "1.13",
                   "instruct": "차분하고 낮게, 설명하듯 또박또박"},
    }


def test_역할_음성이_환경변수로_들어간다(monkeypatch):
    monkeypatch.delenv("TTS_QWEN_VOICE", raising=False)
    monkeypatch.delenv("TTS_QWEN_SPEED", raising=False)
    monkeypatch.delenv("TTS_QWEN_INSTRUCT", raising=False)
    import os

    main_mod.apply_role_voice("docent")
    assert os.environ["TTS_QWEN_VOICE"] == "sohee"
    assert os.environ["TTS_QWEN_SPEED"] == "1.13"
    assert "차분하고" in os.environ["TTS_QWEN_INSTRUCT"]


def test_운영자가_지정한_음성을_덮어쓰지_않는다(monkeypatch):
    # 현장에서 손으로 바꾼 값이 코드에 밀려나면 안 된다.
    monkeypatch.setenv("TTS_QWEN_VOICE", "ono_anna")
    main_mod.apply_role_voice("mc")
    import os

    assert os.environ["TTS_QWEN_VOICE"] == "ono_anna"
```

`tests/test_deployment_contract.py` 끝에 덧붙인다:

```python
def test_stage_client_는_stage_패키지를_import_하지_않는다():
    """`stage/` 는 노트북에만 있다. 로봇에는 앱만 올라간다.

    여기서 import 하면 실기에서 ModuleNotFoundError 로 죽는다 — 시뮬에서는
    저장소 루트가 경로에 있어 절대 드러나지 않는다.
    """
    import pathlib

    src = (
        pathlib.Path(__file__).parent.parent
        / "apps/voice_chat/voice_chat/stage_client.py"
    ).read_text()
    assert "import stage" not in src
    assert "from stage" not in src


def test_로봇과_감독의_메시지_규약이_같다():
    """`stage_client.py` 는 `stage/protocol.py` 를 import 하지 않는다 —
    로봇에는 `stage/` 가 올라가지 않기 때문이다(위 테스트가 그걸 고정한다).

    대가로 **두 곳이 조용히 어긋날 수 있다.** 한쪽에 메시지를 더하고 다른
    쪽을 잊으면 시연장에서 "감독은 보냈는데 로봇이 무시한다" 가 된다.
    여기서 묶어 둔다.
    """
    import pathlib
    import sys

    root = pathlib.Path(__file__).parent.parent
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "apps/voice_chat/voice_chat"))
    import stage_client
    from stage import protocol

    assert stage_client._ROBOT_MSGS == protocol.ROBOT_MSGS
    assert stage_client._DIRECTOR_MSGS == protocol.DIRECTOR_MSGS


def test_websockets_가_앱_의존성에_선언돼_있다():
    import pathlib
    import tomllib

    p = pathlib.Path(__file__).parent.parent / "apps/voice_chat/pyproject.toml"
    deps = tomllib.loads(p.read_text())["project"]["dependencies"]
    assert any(d.startswith("websockets") for d in deps)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_role.py tests/test_deployment_contract.py -q`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'role_of_env'`

- [ ] **Step 3: `main.py` 를 고친다**

`main.py` 의 import 아래에 추가한다:

```python
import os

from stage_client import Handlers, StageClient  # noqa: E402

ROLES = ("mc", "docent")

# 설계 §11. 배속은 **1.2 기준 환산값**이다 — TTS_QWEN_SPEED 기본이 1.2 라
# (tts.py:46) 1.06/0.94 를 그대로 넣으면 시연 전체가 지금보다 느려진다.
ROLE_VOICE = {
    "mc": {
        "voice": "serena",
        "speed": "1.27",
        "instruct": "밝고 또렷하게, 진행자처럼 활기차게",
    },
    "docent": {
        "voice": "sohee",
        "speed": "1.13",
        "instruct": "차분하고 낮게, 설명하듯 또박또박",
    },
}


def make_heard_sink(client, mic_open: threading.Event, log=print):
    """STT 결과를 감독에게 올리는 함수를 만든다. **마이크가 닫혀 있으면 버린다.**

    감독은 발화 중 `mic(open=False)` 를 보내지만 `voice_loop` 는 그걸 모르고
    계속 듣는다. 여기서 막지 않으면 로봇이 **상대 로봇의 목소리를 받아적어**
    감독에 올리고, 그것이 이 저장소가 이미 밟은 자기목소리 루프다.
    설계 §4.2 불변식 ① 이 로봇 쪽에서 실제로 성립하는 지점이 여기다.
    """

    def on_heard(text: str, *args, **kwargs) -> None:
        if not mic_open.is_set():
            log(f"  [마이크 닫힘 — 버림: {text!r}]")
            return
        client.heard(text)

    return on_heard


def role_of_env() -> str | None:
    """`REACHY_ROLE` 을 읽는다. 없으면 1대 모드.

    오타를 조용히 1대 모드로 흘려보내지 않는다 — 시연장에서 "왜 한 대만
    말하지" 를 추적하는 데 드는 시간이 가장 비싸다.
    """
    raw = os.environ.get("REACHY_ROLE")
    if raw is None or not raw.strip():
        return None
    role = raw.strip().lower()
    if role not in ROLES:
        raise ValueError(
            f"REACHY_ROLE 이 {raw!r} 다 — 쓸 수 있는 값: {', '.join(ROLES)}"
        )
    return role


def apply_role_voice(role: str) -> None:
    """역할별 음성을 환경변수로 넣는다. **이미 있으면 덮어쓰지 않는다** —
    현장에서 손으로 바꾼 값이 코드에 밀려나면 안 된다."""
    cfg = ROLE_VOICE[role]
    for env, key in (
        ("TTS_QWEN_VOICE", "voice"),
        ("TTS_QWEN_SPEED", "speed"),
        ("TTS_QWEN_INSTRUCT", "instruct"),
    ):
        os.environ.setdefault(env, cfg[key])


def stage_run(reachy_mini, stop_event: threading.Event, role: str) -> None:
    """2대 모드 — 무대감독의 지시로 말하고 움직인다.

    마이크는 감독이 연다. 사회자만 열리고 도슨트는 상시 닫혀 있다(설계 §2).
    """
    from session import announce_endpoints, announce_voice, build, speak

    apply_role_voice(role)
    announce_endpoints()
    announce_voice()

    url = os.environ.get("REACHY_DIRECTOR_URL", "ws://127.0.0.1:8777")
    print(f"무대감독: {url}  역할: {role}")

    with contextlib.ExitStack() as stack:
        llm, speaker, player = build(stack, mini=reachy_mini)
        mic_open = threading.Event()
        client: StageClient | None = None

        def on_say(cue_id: str, text: str, gaze: str | None) -> None:
            try:
                speak(text, speaker, player)
            except Exception as exc:
                if client:
                    client.error("speak", f"{type(exc).__name__}: {exc}")
                raise
            finally:
                # **발성 경계는 여기서만 보고한다.** 감독의 게이팅이 이 값을
                # 믿는다 — 빠뜨리면 감독이 타임아웃까지 멈춰 있는다.
                if client:
                    client.speaking_started(cue_id)
                    speaker.wait_idle()
                    client.speaking_ended(cue_id)

        def on_mic(open_: bool) -> None:
            mic_open.set() if open_ else mic_open.clear()
            print(f"  [마이크 {'열림' if open_ else '닫힘'}]")

        client = StageClient(
            url,
            role,
            Handlers(
                on_say=on_say,
                on_mic=on_mic,
                on_gaze=lambda target: print(f"  [시선 {target}]"),
                on_abort=lambda: speaker.stop(),
            ),
            unit_id=_unit_id(reachy_mini),
            version=_sdk_version(),
        )

        # 사회자만 듣는다. 도슨트는 감독의 지시만 받는다.
        if role == "mc":
            threading.Thread(
                target=voice_loop,
                args=(llm, speaker, player, make_heard_sink(client, mic_open)),
                kwargs={"should_stop": stop_event.is_set},
                daemon=True,
            ).start()

        client.run(should_stop=stop_event.is_set)


def _unit_id(mini) -> str | None:
    """로봇의 hardware id. 시뮬(macOS)에서는 언제나 None 이다."""
    try:
        return mini.client.get_status().hardware_id
    except Exception:
        return None


def _sdk_version() -> str:
    try:
        from importlib.metadata import version

        return version("reachy_mini")
    except Exception:
        return "unknown"
```

`VoiceChat.run` 을 이렇게 바꾼다:

```python
    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        role = role_of_env()
        if role is not None:
            stage_run(reachy_mini, stop_event, role)
            print("종료했습니다.")
            return

        # 1대 모드 — 기존 경로를 그대로 둔다.
        with contextlib.ExitStack() as stack:
            announce_endpoints()
            announce_voice()
            llm, speaker, player = build(stack, mini=reachy_mini)
            voice_loop(llm, speaker, player, respond, should_stop=stop_event.is_set)
        print("종료했습니다.")
```

- [ ] **Step 4: 기동 스크립트를 만든다**

`scripts/stage-env.sh`:

```bash
#!/usr/bin/env bash
# 2대 시연 환경변수. 로봇에 올리기 전에 이 값들을 채운다.
#
#   사회자 로봇에서:  source scripts/stage-env.sh mc
#   도슨트 로봇에서:  source scripts/stage-env.sh docent
#
# 주소는 **고정 IP** 를 쓴다. 두 로봇 모두 hostname 이 reachy-mini 라
# reachy-mini.local 이 어느 쪽을 가리키는지 보장되지 않는다(설계 §6.1).
set -eu

ROLE="${1:?사용법: source scripts/stage-env.sh {mc|docent}}"
PC_IP="${PC_IP:-192.168.0.10}"

export REACHY_ROLE="$ROLE"
export REACHY_DIRECTOR_URL="ws://${PC_IP}:8777"
export REACHY_LLM_URL="http://${PC_IP}:8080"
export REACHY_STT_URL="http://${PC_IP}:8090/v1/audio/transcriptions"
export TTS_QWEN_URL="http://${PC_IP}:8099/v1/audio/speech"

# 실기는 XMOS 하드웨어 AEC 가 그 자리를 대신한다 — 시뮬 전용 우회를 켜지 않는다.
export REACHY_AEC="${REACHY_AEC:-0}"

echo "역할=$ROLE  무대감독=$REACHY_DIRECTOR_URL  추론=$PC_IP"
echo "음성은 main.py 가 역할에 맞춰 넣는다(TTS_QWEN_VOICE 를 여기서 정하면 그것이 이긴다)"
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_role.py tests/test_deployment_contract.py -q`
Expected: PASS (12 + 7 passed)

- [ ] **Step 6: 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 350 passed

- [ ] **Step 7: 커밋**

```bash
chmod +x scripts/stage-env.sh
git add apps/voice_chat/voice_chat/main.py scripts/stage-env.sh tests/test_stage_role.py tests/test_deployment_contract.py
git commit -m "feat(app): REACHY_ROLE 로 1대/2대 모드를 가른다

진입점은 여전히 main.py 하나다. 역할 오타를 조용히 1대 모드로 흘려보내지
않는다 — 시연장에서 '왜 한 대만 말하지' 를 추적하는 시간이 가장 비싸다.

역할별 음성(serena/sohee)은 환경변수로 넣되 이미 있으면 덮어쓰지 않는다.
배속은 1.2 기준 환산값(1.27/1.13)이다 — TTS_QWEN_SPEED 기본이 1.0 이 아니다.

배포 계약 테스트 2개 추가: stage_client 가 stage/ 를 import 하지 않는 것,
websockets 가 앱 의존성에 선언된 것.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 9: 큐시트 19섹션 완성

Task 3 에서 4개만 채웠다. 나머지 15개를 채우고 커버리지 테스트를 켠다.

**이 태스크의 산출물은 코드가 아니라 대본이다 — 사람의 검토가 필요하다.**

**Files:**
- Modify: `data/cues.yaml`
- Test: `tests/test_stage_cues.py` (커버리지 테스트 추가)

- [ ] **Step 1: 커버리지 테스트를 먼저 쓴다(실패한다)**

`tests/test_stage_cues.py` 끝에 덧붙인다:

```python
def test_큐시트가_해설_원장의_모든_섹션을_덮는다():
    """`docs/exhibit-guide.md` 의 `## N.` 섹션마다 큐가 하나씩 있어야 한다.

    원장에 섹션을 더하고 큐를 안 만들면 그 구간을 로봇이 통째로 건너뛴다.
    """
    import re

    guide = (
        pathlib.Path(__file__).parent.parent / "docs/exhibit-guide.md"
    ).read_text(encoding="utf-8")
    sections = re.findall(r"^## (\d+)\.", guide, flags=re.MULTILINE)
    assert sections, "원장에서 섹션을 못 찾았다 — 형식이 바뀌었는지 확인한다"

    numbers = {c.id.split("-")[0] for c in load_cues()}
    missing = [n for n in sections if f"{int(n):02d}" not in numbers]
    assert not missing, f"큐가 없는 섹션: {missing}"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -k 덮는다 -q`
Expected: FAIL — `큐가 없는 섹션: ['5', '6', ... '19']`

- [ ] **Step 3: 나머지 15개를 채운다**

`docs/exhibit-guide.md` 의 §5~§19 를 하나씩 읽고 `data/cues.yaml` 에 항목을 더한다. 각 항목마다:

1. `id` 는 `NN-슬러그` 형식(원장 섹션 번호를 두 자리로). 예: `05-donor`, `06-bands`
2. `title` 은 원장의 `## N.` 제목을 그대로 쓴다
3. `mc` 는 **고정 대사**다. 화제를 열고 도슨트에게 넘기는 2~3문장. 반드시 도슨트를 부르는 말로 끝낸다
4. `docent_brief` 는 **지시**다. 원장의 사실(연도·수치·고유명사)을 그대로 옮기고 문장 수 상한을 적는다. 대사를 쓰지 않는다
5. `gaze` 는 넘길 때 `partner`, 관람객에게 권할 때 `audience`

예시 — `docs/exhibit-guide.md` §5(기증자 장황남)를 옮기면 이런 모양이다:

```yaml
- id: "05-donor"
  title: "기증자 — 장황남 박사"
  mc: "이 체험관에는 이름이 하나 더 붙어 있습니다. 도슨트, 장황남 박사가 누구인지 소개해 주세요."
  docent_brief: "체험관 정식 명칭에 이름이 들어간 기증자라는 것과, 원장 §5 에 적힌 생애·기증 내역을 그대로 옮긴다. 3문장 이내. 상대연도('몇 년 전')를 쓰지 않고 절대연도로만 말한다. 원장에 없는 사실을 덧붙이지 않는다."
  gaze: partner
```

**원장 §1 "걷어낸 것"의 규칙을 지킨다** — 상대연도(`몇 년 전`)를 쓰지 않고 절대연도로만 적는다. 이 규칙을 `docent_brief` 안에도 반복해 적는다(LLM 이 프롬프트 안에서만 본다).

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -q`
Expected: PASS (25 passed)

- [ ] **Step 5: 큐시트를 눈으로 검토한다**

Run: `.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from stage.cues import load_cues
for c in load_cues():
    print(f'[{c.id}] {c.title}')
    print(f'  사회자: {c.mc}')
    print(f'  지시  : {c.docent_brief[:60]}…')
    print()
"`

사람이 읽고 확인한다: 사회자 대사가 자연스럽게 이어지는가, 도슨트를 부르는 말로 끝나는가, 지시에 원장에 없는 사실이 섞이지 않았는가.

- [ ] **Step 6: 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 351 passed

- [ ] **Step 7: 커밋**

```bash
git add data/cues.yaml tests/test_stage_cues.py
git commit -m "feat(stage): 큐시트 19섹션 완성

원장에 섹션을 더하고 큐를 안 만들면 그 구간을 로봇이 통째로 건너뛴다 —
커버리지 테스트로 막는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## Task 10: 1인 모드 강등 (설계 §7)

로봇 한 대가 끊겨도 **시연이 멈추지 않게** 한다. 남은 한 대가 양쪽 대사를 읽는다.

이것이 없으면 도슨트가 끊긴 순간 감독이 `_speak_docent` 에서 "붙지 않았다" 경고만 남기고 진행이 그대로 죽는다.

**Files:**
- Modify: `stage/director.py`
- Modify: `stage/server.py`
- Test: `tests/test_stage_director.py` (추가), `tests/test_stage_server.py` (추가)

**Interfaces:**
- Consumes: `stage.director.Director`
- Produces:
  - `Director.on_connect(role: str) -> None`
  - `Director.on_disconnect(role: str) -> None`
  - `Director.solo_role: str | None` — 한 대만 붙어 있으면 그 역할, 아니면 `None`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_director.py` 끝에 덧붙인다:

```python
def test_둘_다_붙어_있으면_1인_모드가_아니다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    assert h.d.solo_role is None


def test_도슨트가_끊기면_사회자가_양쪽을_읽는다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.start()
    h.d.on_disconnect("docent")
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    said = h.says()
    assert len(said) == 1
    assert said[0][0] == "mc"                      # 도슨트 대사를 사회자가 읽는다
    assert said[0][1] == "[첫 지시 로 만든 대사]"
    assert any("1인 모드" in w for w in h.warnings)


def test_사회자가_끊기면_도슨트가_양쪽을_읽는다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.on_disconnect("mc")
    h.clear()
    h.d.start()
    assert [r for r, _ in h.says()] == ["docent"]
    assert any("1인 모드" in w for w in h.warnings)


def test_다시_붙으면_2인_모드로_돌아온다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.on_disconnect("docent")
    assert h.d.solo_role == "mc"
    h.d.on_connect("docent")
    assert h.d.solo_role is None


def test_1인_모드에서도_불변식은_지켜진다():
    # 한 대가 연달아 두 대사를 읽으므로 발화 종료를 기다려야 한다.
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_disconnect("docent")
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert h.d.state is State.MC_SPEAKING       # 두 번째 대사를 말하는 중
    assert all(open_ is False for _, open_ in h.mics())
```

`tests/test_stage_server.py` 끝에 덧붙인다:

```python
def test_연결이_끊기면_감독이_1인_모드로_내려간다(server):
    url = f"ws://127.0.0.1:{server.port}"
    with connect(url) as mc:
        hello(mc, "mc")
        time.sleep(0.2)
        with connect(url) as docent:
            hello(docent, "docent")
            time.sleep(0.2)
            assert server.director.solo_role is None
        time.sleep(0.4)                          # 도슨트가 나갔다
        assert server.director.solo_role == "mc"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k "1인 모드 or 붙어 or 끊기면" -q`
Expected: FAIL — `AttributeError: 'Director' object has no attribute 'on_connect'`

- [ ] **Step 3: 감독에 1인 모드를 넣는다**

`stage/director.py` — `__init__` 끝에 추가:

```python
        self._connected: set[str] = set()
```

속성과 메서드를 `state` 프로퍼티 아래에 추가:

```python
    @property
    def solo_role(self) -> str | None:
        """한 대만 붙어 있으면 그 역할. 둘 다거나 둘 다 없으면 None."""
        if len(self._connected) == 1:
            return next(iter(self._connected))
        return None

    def on_connect(self, role: str) -> None:
        self._connected.add(role)

    def on_disconnect(self, role: str) -> None:
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
```

`_begin_cue` 의 마지막 줄을 바꾼다:

```python
        self._emit(
            self._machine.speak(self._who("mc"), cue.id, cue.mc, gaze=cue.gaze)
        )
```

`_speak_docent` 의 마지막 줄을 바꾼다:

```python
        return self._machine.speak(
            self._who("docent"), cue.id, text, gaze="audience"
        )
```

`_answer` 의 마지막 줄을 바꾼다:

```python
        self._emit(
            self._machine.speak(
                self._who("docent"), f"{cue.id}:qa", text, gaze="audience"
            )
        )
```

`on_speaking_ended` 의 분기 조건을 바꾼다 — 1인 모드에서는 사회자 대사와 도슨트 대사를 **같은 로봇**이 연달아 읽으므로 역할이 아니라 큐로 판정한다:

```python
        cue = self._sheet.current()
        if cue_id == cue.id and role == self._who("mc"):
            cmds = cmds + self._speak_docent(cue)
        self._emit(cmds)
```

- [ ] **Step 4: 서버에 연결 알림을 붙인다**

`stage/server.py` — `handler` 안 등록 직후(`self._warn(f"[{role}] 붙었다 …")` 바로 뒤)에 추가:

```python
                    self.director.on_connect(role)
```

`finally` 블록의 연결 해제 직후(`self._warn(f"[{role}] 연결이 끊어졌다")` 바로 앞)에 추가:

```python
                self.director.on_disconnect(role)
```

- [ ] **Step 5: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py tests/test_stage_server.py -q`
Expected: PASS (24 + 8 passed)

- [ ] **Step 6: 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 357 passed

- [ ] **Step 7: 커밋**

```bash
git add stage/director.py stage/server.py tests/test_stage_director.py tests/test_stage_server.py
git commit -m "feat(stage): 로봇 한 대가 끊기면 1인 모드로 강등한다

없으면 도슨트가 끊긴 순간 진행이 그대로 죽는다 — 경고만 남기고.
남은 한 대가 양쪽 대사를 읽고, 시연은 계속된다.

1인 모드에서는 같은 로봇이 두 대사를 연달아 읽으므로 발화 종료 판정을
역할이 아니라 큐로 한다. 불변식 2개는 그대로 지켜진다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VAebqsSLo4nL4PoQPUKSs4"
```

---

## 마지막 확인 (구현 완료 후)

### 코드

- [ ] `.venv/bin/python -m pytest tests/ -q` → **357 passed** (착수 시점 235 + 122)
- [ ] 시뮬 2대로 종단 시연 (설계 §8 에서 실측 검증한 구성):
  ```bash
  # 터미널 1·2 — 로봇 2대 대역 (mjpython/Cocoa 제약을 우회하는 구성, 실측 검증됨)
  .venv/bin/python -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
    --fastapi-port 8000 --robot-name mc
  .venv/bin/python -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
    --fastapi-port 8001 --robot-name docent
  # 터미널 3 — 무대감독
  .venv/bin/python -m stage
  ```
  콘솔에서 `s` → 사회자 대사 → 도슨트 대사 → `n` 으로 다음 큐가 흐르는지 본다.
  한 로봇을 Ctrl-C 로 죽여 **1인 모드로 내려가는지**도 본다.

### 실기 운영 (설계 §6·§9 — 코드가 아니라 절차다)

- [ ] **WiFi 온보딩을 한 대씩 한다.** 두 로봇 AP 의 SSID 가 `reachy-mini-ap` 로 같아
      동시에 켜면 어느 쪽에 붙었는지 알 수 없다. A 설정 → **A 끄고** → B 설정 → 둘 다 켠다
- [ ] 공유기에서 **DHCP 고정 IP** 배정. `reachy-mini.local` 은 둘 다 같은 hostname 이라
      어느 쪽을 가리키는지 보장되지 않는다
- [ ] **전용 라우터(5GHz)** 를 쓴다. 시연장 공용 WiFi 는 AP isolation 으로 통신이 막히고,
      데몬 API 에는 인증이 없다
- [ ] 두 로봇 대시보드의 **startup-app 을 비운다.** LAN SDK 클라이언트는 앱 락을
      우회하므로 온보드 앱이 켜져 있으면 모터를 두고 싸운다
- [ ] `unit_id` 채취 → `REACHY_MC_UNIT` / `REACHY_DOCENT_UNIT` 에 기록 → 기동 검증 통과 확인
- [ ] 기동 로그로 추론 3종 주소가 PC 를 가리키는지 확인 (`announce_endpoints()`)
- [ ] `REACHY_AEC` **끔** — 실기는 XMOS AEC 가 그 자리를 대신한다
- [ ] 두 로봇 스피커 음량 균형, 물리 배치(시선 상수) 실측
- [ ] **1.2 배속 기준으로 음성 연출을 다시 들어본다** — 1.27/1.13 의 청감 대비는 미실측이다

### 문서

- [ ] `docs/lessons.md` 에 항목 추가 (증상 → 원인 → 규칙):
  - `DiscoveredRobot.host` 가 `.local.local.` 로 중복된다 → `r.addresses[0]` 를 쓴다
  - macOS `dns-sd` 경로에서 TXT 값이 공백에서 잘린다(`model` → `"Reachy\"`) → `model` 로 기종을 판별하지 않는다
  - `get_hardware_id()` 는 리눅스 sysfs 를 읽는다 → 시뮬에서 `unit_id` 는 언제나 `None`
  - `--tts-speed` 는 `--help` 표기와 달리 qwen3-tts 에서도 동작한다
  - `TTS_QWEN_SPEED` 기본값은 1.0 이 아니라 **1.2** 다 → 배속 연출은 환산해서 넣는다
  - Qwen3-TTS 남성 화자는 **한국어에서 음색이 무너진다**(aiden 영어 116 Hz → 한국어 177 Hz)
- [ ] `docs/real-robot-deployment.md` 에 2대 구성 절 추가 (설계 §10 미검증 항목 포함)
