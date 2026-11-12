"""발화 라벨 해석 — 감독이 `say` 에 싣는 `cue_id`(발화 라벨)를 "어느 큐의 어느 대목"으로 푼다.

라벨을 **만드는 쪽**은 `stage/director.py` 다. 읽는 쪽(`stage/say_label.py`)이 어긋나면 교육자료가 엉뚱한
카드를 켠다 — 그래서 실제 감독을 큐시트 끝까지 돌려 받은 라벨을 읽어 본다(아래 마지막 세 테스트).
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet, Turn, load_cues
from stage.director import Director
from stage.levels import LEVEL_NAMES
from stage.say_label import QA_TURNS, SayRef, parse_say_label


def _n(count):
    """큐 `c` 만 있는 큐시트(포인트 `count` 개)."""
    return lambda cid: {"c": count}.get(cid)


def test_여는_말_라벨은_큐_id_그대로다():
    assert parse_say_label("c", _n(3)) == SayRef("c", "open")


def test_사회자_질문은_ask_번호다():
    assert parse_say_label("c:pt1", _n(3)) == SayRef("c", "ask1")
    assert parse_say_label("c:pt2", _n(3)) == SayRef("c", "ask2")


def test_첫_포인트에는_질문이_없어_pt0_는_모르는_라벨이다():
    """첫 턴에는 ask 를 두지 않는다(오프닝이 묻는다 — `stage/cues.py::_load_turns`)."""
    assert parse_say_label("c:pt0", _n(3)) is None


def test_마지막이_아닌_도슨트_설명은_docent_번호다():
    assert parse_say_label("c:pt0:docent", _n(3)) == SayRef("c", "docent0")
    assert parse_say_label("c:pt1:docent", _n(3)) == SayRef("c", "docent1")


@pytest.mark.parametrize("n", [1, 2, 3])
def test_마지막_도슨트는_항상_종단_라벨이고_마지막_번호가_된다(n):
    assert parse_say_label("c:docent", _n(n)) == SayRef("c", f"docent{n - 1}")


def test_마지막_설명이_pt_라벨로_오면_모르는_라벨이다():
    """감독은 마지막 설명에 늘 `:docent` 를 쓴다(`Director._point_label`) — 이 모양이 오면 규칙이 바뀐 것이다."""
    assert parse_say_label("c:pt2:docent", _n(3)) is None


def test_받아치기와_질문_흐름_라벨():
    assert parse_say_label("c:after", _n(3)) == SayRef("c", "after")
    for turn in sorted(QA_TURNS):
        assert parse_say_label(f"c:{turn}", _n(3)) == SayRef("c", turn)


@pytest.mark.parametrize(
    "label",
    ["solo:qa", "solo:ack", "", None, 7, "zzz:docent", "c:pt9", "c:docent:x", "c:pt1:docent:x", ":docent", "c:"],
)
def test_큐시트에_없거나_규칙에_안_맞는_라벨은_None_이다(label):
    assert parse_say_label(label, _n(3)) is None


def _구동(cues, level="일반"):
    """실제 감독을 큐시트 끝까지 돌려 `say` 의 발화 라벨을 모은다.

    로봇은 말이 끝났다고 곧장 보고하는 가짜이고, 질문 창이 열리면(LISTENING) 관람객이 "다음" 이라고 말한다.
    """
    sent = []
    d = Director(
        CueSheet(cues),
        generate=lambda role, brief, history: "생성 안 함",
        send=lambda role, cmd: sent.append((role, cmd.type, dict(cmd.fields))),
        warn=lambda m: None,
        level_name=level,
    )
    for role in ("mc", "docent"):
        d.on_hello(role, None, "test", ["emotion", "react", "gaze"])
        d.on_connect(role)
    d.start()
    labels, seen_seq = [], 0
    for _ in range(400):
        says = [(r, f) for r, t, f in sent if t == "say"]
        if not says:
            break
        role, f = says[-1]
        if f["seq"] != seen_seq:
            seen_seq = f["seq"]
            labels.append(f["cue_id"])
        d.on_speaking_ended(role, f["cue_id"], f["seq"])
        if d.state.value == "listening":
            before = sum(1 for _, t, _ in sent if t == "say")
            d.on_heard("다음")
            if sum(1 for _, t, _ in sent if t == "say") == before:
                break
    else:
        pytest.fail("감독이 400걸음 안에 끝나지 않았다 — 구동 도구가 무한히 돈다")
    return labels


def test_실제_큐시트의_모든_큐가_기대한_턴_순서로_읽힌다():
    """감독이 라벨 규칙을 바꾸면 여기서 실패한다 — 교육자료가 엉뚱한 카드를 켜기 전에."""
    cues = load_cues()
    points = {c.id: len(c.points) for c in cues}
    got = {}
    for label in _구동(cues):
        ref = parse_say_label(label, points.get)
        assert ref is not None, f"읽을 수 없는 라벨: {label!r}"
        got.setdefault(ref.cue, []).append(ref.turn)
    for c in cues:
        want = ["open"]
        for i, t in enumerate(c.points):
            if t.ask:
                want.append(f"ask{i}")
            want.append(f"docent{i}")
        want.append("after")
        assert got.get(c.id) == want, c.id


def test_한_턴_큐는_여는_말과_마지막_도슨트만_있다():
    answers = {lv: f"{lv} 설명" for lv in LEVEL_NAMES}
    cue = Cue("c1", "첫째", "사회자 대사", "지시", "partner", points=(Turn("", answers),))
    labels = _구동([cue])
    assert labels == ["c1", "c1:docent"]
    assert [parse_say_label(l, {"c1": 1}.get) for l in labels] == [SayRef("c1", "open"), SayRef("c1", "docent0")]


def test_두_턴_큐의_라벨_순서():
    answers = {lv: f"{lv} 설명" for lv in LEVEL_NAMES}
    cue = Cue(
        "c2", "둘째", "사회자 대사", "지시", "partner",
        mc_after="질문 있으세요? '다음'이라고 해 주세요.",
        points=(Turn("", answers), Turn("그럼요?", answers)),
    )
    labels = _구동([cue])
    assert labels == ["c2", "c2:pt0:docent", "c2:pt1", "c2:docent", "c2:after"]
    refs = [parse_say_label(l, {"c2": 2}.get) for l in labels]
    assert [r.turn for r in refs] == ["open", "docent0", "ask1", "docent1", "after"]
