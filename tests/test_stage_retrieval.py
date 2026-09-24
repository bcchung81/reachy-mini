"""관람객 질문과 가까운 **다른** 섹션 찾기(`stage/retrieval.py`, 2026-09-24).

기대값은 실제 큐시트에서 잰 것이다 — 큐시트가 바뀌면 여기가 먼저 알려 준다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import load_cues
from stage.retrieval import CueIndex


@pytest.fixture(scope="module")
def idx():
    return CueIndex(tuple(load_cues()))


@pytest.mark.parametrize("current,question,expected", [
    ("07-maritime", "아까 마르코니가 누구라고 했죠?", "02-history"),
    ("15-emf", "타이타닉은 왜 가라앉았어요?", "07-maritime"),
    ("03-theory", "테레민은 어떻게 소리가 나요?", "18-science"),
    ("18-science", "무선국 검사는 누가 해요?", "16-inspection"),
    ("08-aviation", "모스 부호는 누가 만들었어요?", "04-morse"),
])
def test_앞에서_들은_것을_되물으면_그_섹션을_찾는다(idx, current, question, expected):
    assert idx.related(question, "일반", current).id == expected


@pytest.mark.parametrize("current,question", [
    ("03-theory", "주파수가 높으면 파장은 어떻게 돼요?"),   # 지금 섹션 질문 — 다른 근거를 붙이지 않는다
    ("14-mobile", "5G는 언제 시작됐어요?"),
    ("14-mobile", "그건 왜 그런가요?"),                  # 흔한 말끝만 겹친다
    ("01-intro", "왜요?"),
    ("06-bands", "질문 있어요"),
])
def test_지금_섹션_질문이나_흔한_말에는_아무것도_붙이지_않는다(idx, current, question):
    """엉뚱한 근거는 없는 근거보다 나쁘다 — 모델이 그것을 답에 섞는다."""
    assert idx.related(question, "일반", current) is None


def test_띄어쓰기가_달라도_같은_섹션을_찾는다(idx):
    """STT 는 띄어쓰기가 흔들린다 — 2-gram 을 낱말을 붙인 뒤 자르는 이유."""
    a = idx.related("모스부호는 누가 만들었어요", "일반", "08-aviation")
    b = idx.related("모스 부호는 누가 만들었 어요", "일반", "08-aviation")
    assert a is not None and b is not None and a.id == b.id == "04-morse"


def test_문턱은_큐_수에_따라_흔들리지_않는다():
    """IDF 는 큐 수의 함수다 — 절대 문턱이면 큐가 적은 시트에서 검색이 영영 안 켜진다."""
    from stage.cues import Cue, Turn

    def cue(cid, text):
        return Cue(cid, cid, "오프닝", "옛", "partner", mc_after="다음",
                   briefs={"일반": {"mc_brief": "m", "docent_brief": text}},
                   points=(Turn("", {"일반": text}),))

    two = CueIndex((cue("a", "마르코니가 무선전신을 실용화했어요."), cue("b", "배는 조난 신호를 보내요.")))
    assert two.related("마르코니가 누구예요?", "일반", "b").id == "a"
    assert two.related("그건 왜 그런가요?", "일반", "b") is None
