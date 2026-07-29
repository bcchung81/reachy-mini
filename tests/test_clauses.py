import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from clauses import ClauseBuffer


def test_구두점에서_절이_끊긴다():
    cb = ClauseBuffer()
    assert cb.feed("안녕! 반가") == ["안녕!"]
    # 미완성 조각 " 반가"는 버퍼에 이월돼 다음 델타와 이어붙는다 — 글자가 유실되면 안 된다
    assert cb.feed("워. 오늘 어때?") == ["반가워.", "오늘 어때?"]


def test_구두점_없이_길면_공백에서_끊는다():
    cb = ClauseBuffer(soft_limit=10)
    out = cb.feed("가나다라마바사아자차 카타파하 그리고")
    assert out and len(out[0]) >= 10


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
