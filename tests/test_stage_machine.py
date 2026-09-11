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
