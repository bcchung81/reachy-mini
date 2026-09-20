import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.levels import load_levels
from stage.prompts import build_system_prompt


def test_역할에_따라_프롬프트가_다르다():
    lv = load_levels()["일반"]
    assert build_system_prompt("mc", lv) != build_system_prompt("docent", lv)


def test_수준의_분량이_프롬프트에_들어간다():
    lv = load_levels()["전문가"]
    p = build_system_prompt("docent", lv)
    assert "5" in p and "7" in p and "260" in p and "400" in p


def test_공통_규약은_두_역할_모두에_있다():
    # TTS 가 읽는다 — 목록 기호·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5).
    lv = load_levels()["일반"]
    for role in ("mc", "docent"):
        p = build_system_prompt(role, lv)
        assert "음성" in p and "마크다운" in p


def test_모르는_역할은_거절한다():
    with pytest.raises(ValueError, match="역할"):
        build_system_prompt("사회자", load_levels()["일반"])


def test_시스템_프롬프트에_분량_규정이_있다():
    """`tests/test_stage_main.py::test_시스템_프롬프트에_분량_규정이_있다` 를
    여기로 옮긴 것이다. `stage/__main__.py::_system_prompt()` 가 이 태스크에서
    지워지고 `build_system_prompt()` 가 그 자리를 대신하기 때문이다.

    옮기면서 원래 있던 두 단언을 **둘 다** 지킨다 — 브리프의 교체본은 수치
    (`min_sentences`/`max_chars`)만 보는데, 원래 테스트는 문구("채워"/"이상"/
    "한 문장"+"아니다")를 봤다. 수치만 남기면, 직전 태스크가 리뷰로 넣은 하한
    강제 문구("N문장 이내" 를 상한으로만 읽지 말라는 지시)가 조립 함수로
    옮겨오면서 조용히 빠져도 이 테스트는 계속 통과한다 — 그게 바로 이 리팩터가
    실제로 저지르기 쉬운 실수다. 그래서 둘 다 본다.
    """
    lv = load_levels()["일반"]
    p = build_system_prompt("docent", lv)
    # 1) 수치 범위 — 상한만 주면 모델이 하단에 붙는다(브리프 교체본의 관심사).
    assert str(lv.min_sentences) in p and str(lv.max_sentences) in p
    assert str(lv.min_chars) in p and str(lv.max_chars) in p
    # 2) 하한을 동사로 명시하는 문장 — 수치 범위만으로는 "N문장 이내" 로
    #    오독될 수 있어 이 문구가 그것을 막는다(원래 테스트의 관심사).
    assert "채워" in p, p
    assert "이상" in p, p
    assert "한 문장" in p and "아니다" in p, p
