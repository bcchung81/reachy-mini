"""관람객 수준 프로필(`stage/levels.py`).

분량은 섹션이 아니라 수준의 함수다 — 이 규약이 어긋나면 큐시트 하단이나
TTS 문장 잘림으로 시연장에서만 드러난다.
"""

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.levels import LevelError, level_of_env, load_levels


def _valid_raw() -> dict:
    """규약을 통과하는 최소 데이터. 각 테스트는 이걸 복사해 필드 하나만 깨뜨린다 —
    통째로 다시 쓰면 무엇을 깨뜨렸는지 diff 로 못 읽는다."""
    return {
        name: {
            "min_sentences": 2,
            "max_sentences": 3,
            "min_chars": 70,
            "max_chars": 120,
            "point_min_sentences": 1,
            "point_max_sentences": 1,
            "point_min_chars": 30,
            "point_max_chars": 60,
            "vocabulary": "말",
            "depth": "말",
            "numbers": "말",
            "sources": "말",
        }
        for name in ("초등", "중고등", "일반", "전문가")
    }


def _valid_raw_without_points() -> dict:
    """포인트 필드를 뺀 옛 데이터. 포인트 필드 검증 테스트 용."""
    return {
        name: {
            "min_sentences": 2,
            "max_sentences": 3,
            "min_chars": 70,
            "max_chars": 120,
            "vocabulary": "말",
            "depth": "말",
            "numbers": "말",
            "sources": "말",
        }
        for name in ("초등", "중고등", "일반", "전문가")
    }


def _valid_raw_with_points() -> dict:
    raw = _valid_raw()
    for name in raw:
        raw[name].update(
            point_min_sentences=1, point_max_sentences=1,
            point_min_chars=30, point_max_chars=60,
        )
    return raw


def _write(tmp_path: pathlib.Path, raw: dict) -> pathlib.Path:
    p = tmp_path / "levels.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return p


def test_수준_넷이_모두_있다():
    lv = load_levels()
    assert set(lv) == {"초등", "중고등", "일반", "전문가"}


def test_포인트_분량_필드가_있다(tmp_path):
    p = _write(tmp_path, _valid_raw_with_points())
    lv = load_levels(p)
    assert lv["초등"].point_min_chars == 30
    assert lv["초등"].point_max_chars == 60
    assert lv["초등"].point_min_sentences == 1
    assert lv["초등"].point_max_sentences == 1


def test_턴_문장_수는_모든_수준이_같다():
    """수준은 설명의 난이도만 바꾼다 — 턴 구조(턴 수·턴당 문장 수)는 같다.
    하한이 2인 이유: 1문장이면 설명이 들어갈 자리가 없어 사회자 질문을 확인만
    하는 답이 된다(docs/lessons.md). 글자 수는 어휘 밀도 차이라 수준별로 둔다."""
    lv = load_levels()
    assert {(l.point_min_sentences, l.point_max_sentences) for l in lv.values()} == {(2, 3)}
    for l in lv.values():
        assert l.point_min_chars < l.point_max_chars, l.name


def test_포인트_분량_필드가_없으면_거절한다(tmp_path):
    p = _write(tmp_path, _valid_raw_without_points())  # 포인트 필드 없는 옛 데이터
    with pytest.raises(LevelError, match="point_min"):
        load_levels(p)


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


def test_숫자_필드가_문자열이면_소리_내서_실패한다(tmp_path):
    # `min_chars` 는 max_tokens 계산에 안 쓰여서 즉시 안 터진다 — 그대로
    # 로그·프롬프트로 흘러가 분량 규정 전체가 조용히 무의미해진다(리뷰 지적).
    raw = _valid_raw()
    raw["초등"]["min_chars"] = "칠십"
    p = _write(tmp_path, raw)
    with pytest.raises(LevelError, match="min_chars"):
        load_levels(p)


def test_숫자_필드가_참거짓이면_소리_내서_실패한다(tmp_path):
    # bool 은 int 의 하위형이라 `isinstance(v, int)` 만으로는 안 걸린다
    # (stage/server.py::_seq_field 가 이미 겪은 함정). YAML 의 `true`/`false` 가
    # 그대로 문장 수로 실리면 안 된다.
    raw = _valid_raw()
    raw["초등"]["max_sentences"] = True
    p = _write(tmp_path, raw)
    with pytest.raises(LevelError, match="max_sentences"):
        load_levels(p)


def test_문자열_필드가_비어있으면_소리_내서_실패한다(tmp_path):
    # 빈 문자열은 "말하는 방식을 안 가른" 채로 프롬프트에 실린다 — 수준 프로필의
    # 존재 의의(사실이 아니라 말하는 방식만 가른다)를 무의미하게 만든다.
    raw = _valid_raw()
    raw["일반"]["vocabulary"] = "   "
    p = _write(tmp_path, raw)
    with pytest.raises(LevelError, match="vocabulary"):
        load_levels(p)


def test_문자열_필드가_숫자면_소리_내서_실패한다(tmp_path):
    raw = _valid_raw()
    raw["전문가"]["depth"] = 3
    p = _write(tmp_path, raw)
    with pytest.raises(LevelError, match="depth"):
        load_levels(p)


def test_수준_항목이_매핑이_아니면_소리_내서_실패한다(tmp_path):
    # YAML 에서 `초등:` 아래를 비우면(null) 원래는 어느 파일·어느 수준인지 말
    # 없는 TypeError 가 그대로 튀어나왔다.
    raw = _valid_raw()
    raw["초등"] = None
    p = _write(tmp_path, raw)
    with pytest.raises(LevelError, match="초등"):
        load_levels(p)
