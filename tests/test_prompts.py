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
    """**순서·인접까지 본다.** 예전에는 `"5" in p and "7" in p and "260" in p
    and "400" in p` 였는데, 네 수가 어디에 어떤 순서로 박혀도 통과했다 —
    `stage/prompts.py::_amount_for` 의 min/max 를 **뒤집어**
    "7~5문장으로, 400~260자 사이로" 라는 말이 안 되는 지시를 내보내도
    잡히지 않았다(전체 리뷰). 전문가 수준의 수치는 리터럴로 박는다
    (`data/levels.yaml` 전문가: 5~7문장 / 260~400자)."""
    lv = load_levels()["전문가"]
    p = build_system_prompt("docent", lv)
    assert "5~7문장으로" in p, p
    assert "260~400자 사이로" in p, p
    assert "7~5문장" not in p and "400~260자" not in p, p


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
    #    **min~max 순서로 붙어 있는지까지** 본다. 네 수가 따로 `in p` 인지만
    #    보면 min/max 를 뒤집어도 통과한다(전체 리뷰) — 뒤집힌 "5~4문장으로"
    #    는 모델에게 범위가 아니라 헛소리다.
    assert f"{lv.min_sentences}~{lv.max_sentences}문장으로" in p, p
    assert f"{lv.min_chars}~{lv.max_chars}자 사이로" in p, p
    assert f"{lv.max_sentences}~{lv.min_sentences}문장" not in p, p
    assert f"{lv.max_chars}~{lv.min_chars}자" not in p, p
    # 2) 하한을 동사로 명시하는 문장 — 수치 범위만으로는 "N문장 이내" 로
    #    오독될 수 있어 이 문구가 그것을 막는다(원래 테스트의 관심사).
    assert "채워" in p, p
    assert "이상" in p, p
    assert "한 문장" in p and "아니다" in p, p


def test_사회자_분량은_수준과_무관하게_고정된_수치를_쓴다():
    """리뷰 Important 2 — 사회자는 해설하지 않는다(`data/personas/mc.md`).
    도슨트처럼 분량을 수준의 수치로 두면 전문가 수준에서 사회자가
    "5~7문장 260~400자를 채워서" 라는, 자기 페르소나와 모순되는 지시를
    받는다. 사회자 분량은 수준이 바뀌어도(초등 ↔ 전문가) 그대로여야 한다.
    """
    from stage.prompts import (
        _MC_MAX_CHARS,
        _MC_MAX_SENTENCES,
        _MC_MIN_CHARS,
        _MC_MIN_SENTENCES,
    )

    고정_문장 = f"{_MC_MIN_SENTENCES}~{_MC_MAX_SENTENCES}문장"
    고정_글자 = f"{_MC_MIN_CHARS}~{_MC_MAX_CHARS}자"
    for name in ("초등", "전문가"):
        lv = load_levels()[name]
        p = build_system_prompt("mc", lv)
        assert 고정_문장 in p and 고정_글자 in p, p
        # 그 수준의 도슨트 분량 문구가 사회자 프롬프트로 새면 안 된다.
        assert f"{lv.min_sentences}~{lv.max_sentences}문장으로" not in p, p
        assert f"{lv.min_chars}~{lv.max_chars}자 사이로 말한다" not in p, p


def test_사회자_프롬프트에는_해설_문구가_없다():
    """"채워서"/"해설이 아니다" 는 도슨트용이다 — 사회자에게 붙이면 자기
    페르소나("해설은 네 몫이 아니다")와 모순되는 거짓 지시가 된다."""
    lv = load_levels()["일반"]
    mc_p = build_system_prompt("mc", lv)
    docent_p = build_system_prompt("docent", lv)
    assert "해설이 아니다" not in mc_p, mc_p
    assert "해설이 아니다" in docent_p


def test_페르소나_파일이_없으면_거절한다(tmp_path, monkeypatch):
    """리뷰 Minor 3 — `stage/levels.py::LevelError` 와 같은 기준: 프롬프트에
    그대로 얹히는 지시문(페르소나)이 없으면 조용히 넘기지 않는다."""
    import stage.prompts as prompts_mod

    monkeypatch.setattr(prompts_mod, "personas_dir", lambda: tmp_path)
    with pytest.raises(prompts_mod.PromptError, match="없다"):
        prompts_mod.build_system_prompt("docent", load_levels()["일반"])


def test_페르소나_파일이_비어있으면_거절한다(tmp_path, monkeypatch):
    """빈 페르소나로 조용히 돌면 "역할 없는 프롬프트" 가 되는데, 그 증상은
    시연장에서 대사가 밋밋해지는 것으로만 나타나 원인을 못 찾는다."""
    import stage.prompts as prompts_mod

    (tmp_path / "docent.md").write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(prompts_mod, "personas_dir", lambda: tmp_path)
    with pytest.raises(prompts_mod.PromptError, match="비어"):
        prompts_mod.build_system_prompt("docent", load_levels()["일반"])


def test_프롬프트에_마크다운_강조가_새지_않는다():
    """리뷰 Minor 5 — `_COMMON` 은 "마크다운을 쓰지 않고" 를 지시하는데, 그
    프롬프트 본문 자체가 `**` 를 쓰면 모델이 시스템 프롬프트의 서식을 출력
    스타일로 따라 해 별표가 그대로 새어 TTS 가 읽을 수 있다(리뷰 B5가
    막으려던 것과 같은 증상). 역할·수준을 모두 돌며 확인한다."""
    for role in ("mc", "docent"):
        for name in ("초등", "중고등", "일반", "전문가"):
            p = build_system_prompt(role, load_levels()[name])
            assert "**" not in p, (role, name, p)
