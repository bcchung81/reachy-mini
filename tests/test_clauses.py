import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from clauses import ClauseBuffer


def test_구두점에서_절이_끊긴다():
    cb = ClauseBuffer()
    assert cb.feed("안녕! 반가") == ["안녕!"]
    # 미완성 조각 " 반가"는 버퍼에 이월돼 다음 델타와 이어붙는다 — 글자가 유실되면 안 된다
    assert cb.feed("워. 오늘 어때?") == ["반가워.", "오늘 어때?"]


def test_문장_중간_공백에서는_끊지_않는다():
    # 회귀 방지: 예전 soft_limit 규칙은 30자 넘는 공백에서 잘라
    # "…바탕으로 대화하고" / "있습니다." 처럼 보조용언을 쪼갰다.
    cb = ClauseBuffer()
    long_sentence = "저는 제가 학습한 방대한 양의 정보들을 바탕으로 대화하고 있습니다."
    assert cb.feed(long_sentence) == [long_sentence]


def test_첫_절은_쉼표에서_끊긴다():
    # 첫 소리를 빨리 내기 위한 예외. 쉼표는 원래 쉬는 자리라 어색하지 않다.
    cb = ClauseBuffer()
    assert cb.feed("좋아요, 보여드릴게요.") == ["좋아요,", "보여드릴게요."]


def test_두번째_절부터는_쉼표에서_끊지_않는다():
    cb = ClauseBuffer()
    cb.feed("네.")  # 첫 절 소진
    assert cb.feed("그리고 오늘은, 날씨가 좋네요.") == ["그리고 오늘은, 날씨가 좋네요."]


def test_구두점이_없이_길어지면_안전장치가_끊는다():
    cb = ClauseBuffer(runaway_limit=20)
    out = cb.feed("가나다라마바사아자차카타파하 그리고 더 이어지는 말들이 계속")
    assert out and len(out[0]) >= 20


def test_잔여분은_flush로_나온다():
    cb = ClauseBuffer()
    assert cb.feed("끝맺음 없는 말") == []
    assert cb.flush() == "끝맺음 없는 말"
    assert cb.flush() is None


def test_토큰_단위_공급에도_동작한다():
    cb = ClauseBuffer()
    out = []
    for tok in ["오", "늘", " 날씨", "가 좋", "네요", ".", " 산책 갈까요?"]:
        out += cb.feed(tok)
    out += [c for c in [cb.flush()] if c]
    assert out == ["오늘 날씨가 좋네요.", "산책 갈까요?"]
