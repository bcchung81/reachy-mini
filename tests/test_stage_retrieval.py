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


@pytest.mark.parametrize("question,expected", [
    ("마르코니가 누구예요?", "02-history"),
    ("타이타닉은 왜 가라앉았어요?", "07-maritime"),
    ("테레민은 어떻게 소리가 나요?", "18-science"),
    ("모스 부호는 누가 만들었어요?", "04-morse"),
])
def test_단독은_큐시트_전체에서_가장_가까운_섹션을_먼저_준다(idx, question, expected):
    """단독(2026-09-25)에는 "지금 섹션" 이 없다 — 전체에서 고른다."""
    assert idx.nearest(question, "일반")[0].id == expected


# 관람객이 할 법한 질문 28개 중 **하나만 주면 틀리던** 것들(실측 2026-09-25). 둘째까지 주면 정답이 근거 안에 든다.
@pytest.mark.parametrize("question,expected", [
    ("전자파는 몸에 해로워요?", "15-emf"),        # 1.5 개 분량 문턱 바로 아래(4.3/4.4)라 근거 없이 "모른다" 였다
    ("헤르츠가 뭐예요?", "03-theory"),            # 헤르츠 실험을 체험하는 모스 섹션이 먼저 걸린다
    ("SOS는 언제부터 썼어요?", "07-maritime"),
    ("1세대 이동통신은 언제예요?", "14-mobile"),   # 사물인터넷이 먼저 걸린다
    ("이 체험관은 언제 생겼어요?", "01-intro"),     # 이동통신이 먼저 걸린다
])
def test_단독_근거는_둘까지라_하나만_주면_틀리던_질문도_정답_섹션을_싣는다(idx, question, expected):
    near = idx.nearest(question, "일반")
    assert len(near) <= 2
    assert expected in [c.id for c in near], [c.id for c in near]


@pytest.mark.parametrize("question", ["반가워요", "그건 왜 그런가요?", "왜요?", "좋아요", "또 뭐 있어요?"])
def test_단독에서_흔한_말에는_섹션을_붙이지_않는다(idx, question):
    """엉뚱한 섹션을 근거로 주면 가벼운 말에 전시 해설이 나온다."""
    assert idx.nearest(question, "일반") == []


@pytest.mark.parametrize("question,expected", [
    ("안녕하세요", "01-intro"), ("고마워요", "01-intro"), ("감사합니다", "15-emf"),
])
def test_단독에서_인사말은_사회자_대사_때문에_섹션에_걸린다(idx, question, expected):
    """**알려진 한계를 못박는다**(실측 2026-09-25). 색인이 사회자 대사("안녕하세요, 여러분!"·"감사드립니다")도
    보므로 인사가 섹션에 걸린다. 내용 필드만 색인하면 인사는 빠지지만 진짜 질문을 놓쳐서(전자파·모스) 그대로
    둔다 — 인사에 해설을 얹지 않는 일은 지시문("인사나 가벼운 말이면 위 내용은 꺼내지 않고")이 맡는다
    (`Director._solo_brief`). 값이 바뀌면 큐시트가 바뀐 것이니 이 한계를 다시 잰다."""
    assert idx.nearest(question, "일반")[0].id == expected


def test_단독_둘째_근거는_첫째에_견줄_만할_때만_붙는다():
    """멀리 떨어진 둘째는 근거가 아니라 소음이다 — 첫째 점수의 절반 이상일 때만."""
    from stage.cues import Cue, Turn

    def cue(cid, text):
        return Cue(cid, cid, "오프닝", "옛", "partner", mc_after="다음",
                   briefs={"일반": {"mc_brief": "m", "docent_brief": text}},
                   points=(Turn("", {"일반": text}),))

    idx3 = CueIndex((
        cue("a", "마르코니가 대서양 너머로 무선전신을 보냈어요."),
        cue("b", "타이타닉은 무선으로 구조를 요청했어요."),
        cue("c", "크로마키는 파란 배경을 지우는 합성이에요."),
    ))
    assert [c.id for c in idx3.nearest("마르코니가 대서양 너머로 보낸 무선전신이 뭐예요?", "일반")] == ["a"]
