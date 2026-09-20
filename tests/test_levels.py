"""관람객 수준 프로필(`stage/levels.py`).

분량은 섹션이 아니라 수준의 함수다 — 이 규약이 어긋나면 큐시트 하단이나
TTS 문장 잘림으로 시연장에서만 드러난다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.levels import LevelError, level_of_env, load_levels


def test_수준_넷이_모두_있다():
    lv = load_levels()
    assert set(lv) == {"초등", "중고등", "일반", "전문가"}


def test_분량이_수준을_따라_커진다():
    lv = load_levels()
    assert lv["초등"].max_chars < lv["일반"].max_chars < lv["전문가"].max_chars
    assert lv["초등"].min_sentences >= 1


def test_max_tokens_는_상한_글자에서_계산된다():
    # 잘리면 TTS 가 끊긴 문장을 읽는다 — 분량 미달보다 나쁘다. 넉넉히 잡는다.
    lv = load_levels()
    assert lv["전문가"].max_tokens == 400 * 2 + 64


def test_기본_수준은_일반이다(monkeypatch):
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    assert level_of_env(load_levels()).name == "일반"


def test_모르는_수준은_소리_내서_실패한다(monkeypatch):
    # 조용히 기본값으로 흘리면 엉뚱한 수준으로 시연이 돌고 아무도 모른다.
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "고급")
    with pytest.raises(LevelError, match="REACHY_AUDIENCE_LEVEL"):
        level_of_env(load_levels())
