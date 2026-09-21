import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from clauses import ClauseBuffer, split_sentences


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


# ── split_sentences — 무대 발화 텍스트 문장 분리기(브리프 V1) ──────────────
#
# ClauseBuffer 와 다른 문제다: ClauseBuffer 는 LLM 스트림 델타를 "지금까지 온
# 만큼"에서 자르는 누적기고, split_sentences 는 이미 완성된 문자열 하나를
# 한 번에 문장 리스트로 쪼갠다(무대감독 대사 40~90초 분량을 TTS 요청 단위로
# 잘게 쪼개기 위함). 감독 대사는 문장 사이에 공백이 없다("…입니다.주파수란…").


def test_공백_없는_문장을_경계에서_나눈다():
    text = "빛은 초당 30만km를 이동합니다.주파수란 초당 진동수를 말합니다."
    assert split_sentences(text) == [
        "빛은 초당 30만km를 이동합니다.",
        "주파수란 초당 진동수를 말합니다.",
    ]


def test_소수점은_문장_경계가_아니다():
    # 마침표 앞이 ASCII 영숫자이고 뒤가 숫자일 때만 소수점으로 본다.
    assert split_sentences("이 신호는 2.4GHz 대역을 씁니다.") == [
        "이 신호는 2.4GHz 대역을 씁니다."
    ]
    assert split_sentences("속도가 1.5배로 빨라집니다.") == ["속도가 1.5배로 빨라집니다."]


def test_한글_문장_끝_뒤_연도는_문장_경계다():
    # 마침표 앞이 한글이면 영숫자가 아니므로 뒤가 숫자여도 소수점 예외에 안 걸린다.
    text = "무선통신을 실용화했습니다.1901년에는 대서양을 건넜습니다."
    assert split_sentences(text) == [
        "무선통신을 실용화했습니다.",
        "1901년에는 대서양을 건넜습니다.",
    ]


def test_종결부호가_없으면_한_문장이다():
    assert split_sentences("종결부호 없는 말") == ["종결부호 없는 말"]


def test_빈_조각은_버린다():
    # 종결부호가 연달아 오거나(...) 끝에 붙으면 빈 조각이 생길 수 있다 — 버려야 한다.
    assert split_sentences("정말요?! 그렇군요.") == ["정말요?!", "그렇군요."]


def test_빈_문자열은_빈_리스트다():
    assert split_sentences("") == []
