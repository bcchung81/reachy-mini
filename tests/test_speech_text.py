"""생성문 정리 순수 함수(`stage/speech_text.py`).

실측 근거는 `docs/superpowers/plans/2026-09-21-stage-speech-hygiene.md` §0.
기대값은 전부 **리터럴**이다 — 피검 함수로 기대값을 만들면 자기참조가 된다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.speech_text import cap_length, split_sentences, strip_speaker_labels


# ── 이름표 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    # 실측 mc:42 — 앞머리 이름표 하나
    ("사회자: 한국방송통신전파진흥원이 운영하는 곳이군요.", "한국방송통신전파진흥원이 운영하는 곳이군요."),
    # 실측 mc:74 — 이름표가 두 번(되먹임 고리의 결과)
    ("사회자: 사회자: 전자기파라는 개념과 주파수를 설명해 주셨네요.", "전자기파라는 개념과 주파수를 설명해 주셨네요."),
    # 실측 docent:122
    ("도슨트: 도슨트: 이동통신의 역사는 깁니다.", "이동통신의 역사는 깁니다."),
    # 마크다운 강조·전각 콜론도 이름표다
    ("**사회자:** 좋은 질문이네요.", "좋은 질문이네요."),
    ("도슨트：전파는 파동입니다.", "전파는 파동입니다."),
])
def test_앞머리_이름표를_걷는다(raw, expected):
    assert strip_speaker_labels(raw) == (expected, True)


def test_상대_턴까지_이어_쓴_생성문은_그_이름표_앞에서_자른다():
    """실측 docent:106 — 도슨트 한 발화 안에 사회자 반응이 이어 붙었다."""
    raw = ("시각을 얻으실 수 있을 것입니다.사회자: 사회자: 방송통신 진흥과 관련된 "
           "콘텐츠를 볼 수 있다는 설명이네요.")
    assert strip_speaker_labels(raw) == ("시각을 얻으실 수 있을 것입니다.", True)


def test_이름표만_있으면_빈_문자열이_된다():
    """비면 감독의 기존 빈 생성 폴백(경고 + 큐시트 원문)을 탄다."""
    assert strip_speaker_labels("사회자: ") == ("", True)


@pytest.mark.parametrize("clean", [
    "전파는 눈에 보이지 않습니다.",
    # 콜론이 없으면 이름표가 아니다 — 정상 문장을 건드리면 안 된다
    "사회자님 말씀처럼 전파는 보이지 않습니다.",
    "도슨트가 설명한 대로 주파수는 진동 횟수입니다.",
])
def test_이름표가_없으면_그대로_둔다(clean):
    assert strip_speaker_labels(clean) == (clean, False)


def test_앞뒤_공백만_다른_것은_바뀐_것으로_치지_않는다():
    assert strip_speaker_labels("  전파는 파동입니다.  ") == ("전파는 파동입니다.", False)


# ── 문장 분리 ─────────────────────────────────────────────────────────

def test_공백_없이_붙은_문장도_나눈다():
    """`build_generate` 가 절을 `"".join` 해서 문장 사이 공백이 없다(실측)."""
    assert split_sentences("첫째입니다.둘째입니까?셋째!") == ["첫째입니다.", "둘째입니까?", "셋째!"]


def test_소수점에서는_나누지_않는다():
    """체험관 대역 설명에 "2.4GHz" 같은 수가 자주 나온다."""
    assert split_sentences("주파수는 2.4GHz입니다. 파장은 12.5센티미터입니다.") == [
        "주파수는 2.4GHz입니다.", "파장은 12.5센티미터입니다.",
    ]


def test_연속된_종결부호는_한_문장_끝이다():
    assert split_sentences("정말요?! 그렇군요... 좋네요.") == ["정말요?!", "그렇군요...", "좋네요."]


def test_종결부호가_없으면_한_문장이다():
    assert split_sentences("끝맺음 없는 말") == ["끝맺음 없는 말"]


# ── 분량 상한 ─────────────────────────────────────────────────────────

def test_문장_수_상한에서_문장_경계로_자른다():
    raw = "하나입니다.둘입니다.셋입니다.넷입니다."
    assert cap_length(raw, max_sentences=2, max_chars=1000) == ("하나입니다.둘입니다.", True)


def test_글자_수_상한을_넘기_전_문장까지만_남긴다():
    raw = "가나다라마.바사아자차.카타파하."   # 6자 + 6자 + 5자 = 17자
    assert cap_length(raw, max_sentences=10, max_chars=12) == ("가나다라마.바사아자차.", True)


def test_첫_문장은_상한을_넘어도_통째로_남긴다():
    """문장 중간에서 자르면 TTS 가 말을 뚝 끊는다 — 그게 조금 긴 것보다 나쁘다."""
    raw = "이 문장은 상한보다 훨씬 길지만 잘리면 안 됩니다.다음 문장은 버린다."
    assert cap_length(raw, max_sentences=5, max_chars=10) == (
        "이 문장은 상한보다 훨씬 길지만 잘리면 안 됩니다.", True,
    )


def test_상한_안이면_원문_그대로다():
    raw = "하나입니다. 둘입니다."
    assert cap_length(raw, max_sentences=5, max_chars=280) == ("하나입니다. 둘입니다.", False)


def test_자른_뒤에도_원문의_간격을_보존한다():
    raw = "하나입니다. 둘입니다. 셋입니다."
    assert cap_length(raw, max_sentences=2, max_chars=280) == ("하나입니다. 둘입니다.", True)
