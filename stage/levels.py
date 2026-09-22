"""관람객 수준 프로필. **사실이 아니라 말하는 방식만** 가른다.

분량이 여기 있는 이유는 `docs/superpowers/specs/2026-09-20-podcast-adlib-design.md`
§5 에 있다 — 큐시트에 섹션별로 "N문장 이내" 를 적던 것이 상한만 주는 구조라
모델이 하단에 붙었고, 애초에 분량은 섹션이 아니라 수준의 함수였다.
"""

import os
import pathlib
from dataclasses import dataclass

import yaml

LEVEL_NAMES = ("초등", "중고등", "일반", "전문가")
DEFAULT_LEVEL = "일반"

# 숫자 네 필드와 문자열 네 필드를 나눠 둔다 — `load_levels` 가 타입별로 다른
# 검사를 하기 때문이다(리뷰: 존재만 보고 타입을 안 봤다).
_INT_FIELDS = (
    "min_sentences", "max_sentences", "min_chars", "max_chars",
    "point_min_sentences", "point_max_sentences", "point_min_chars", "point_max_chars",
)
_STR_FIELDS = ("vocabulary", "depth", "numbers", "sources")
_FIELDS = _INT_FIELDS + _STR_FIELDS


class LevelError(ValueError):
    """수준 프로필이 규약에 맞지 않거나 모르는 수준을 요구받았다."""


@dataclass(frozen=True)
class Level:
    name: str
    min_sentences: int
    max_sentences: int
    min_chars: int
    max_chars: int
    point_min_sentences: int
    point_max_sentences: int
    point_min_chars: int
    point_max_chars: int
    vocabulary: str
    depth: str
    numbers: str
    sources: str

    @property
    def max_tokens(self) -> int:
        """한국어는 토큰당 글자가 적다. 잘리면 TTS 가 끊긴 문장을 읽는데
        그건 분량 미달보다 나쁘므로 넉넉히 잡는다."""
        return self.max_chars * 2 + 64


def levels_path() -> pathlib.Path:
    override = os.environ.get("REACHY_LEVELS_PATH")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "levels.yaml"


def load_levels(path: pathlib.Path | None = None) -> dict[str, Level]:
    p = pathlib.Path(path) if path is not None else levels_path()
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LevelError(f"수준 프로필이 없다: {p}") from exc
    except yaml.YAMLError as exc:
        raise LevelError(f"수준 프로필이 YAML 이 아니다: {p} — {exc}") from exc
    if not isinstance(raw, dict):
        raise LevelError(f"수준 프로필은 매핑이어야 한다: {p}")
    missing = set(LEVEL_NAMES) - set(raw)
    if missing:
        raise LevelError(f"{p}: 빠진 수준이 있다 — {sorted(missing)}")
    out: dict[str, Level] = {}
    for name in LEVEL_NAMES:
        item = raw[name]
        # YAML 에서 `초등:` 아래를 비우면(`null`) item 이 None 이 된다 — 그대로
        # `f not in item` 을 돌리면 `TypeError: argument of type 'NoneType' is
        # not iterable` 이 어느 파일·어느 수준인지 말 없이 튀어나온다.
        if not isinstance(item, dict):
            raise LevelError(
                f"{p} {name}: 항목이 매핑이어야 한다 — 지금은 {type(item).__name__}"
            )
        for f in _FIELDS:
            if f not in item:
                raise LevelError(f"{p} {name}: {f} 가 없다")
        for f in _INT_FIELDS:
            v = item[f]
            # bool 은 int 의 하위형이라 `isinstance(v, int)` 만으로는 `true`/`false`
            # 를 못 거른다(stage/server.py::_seq_field 와 같은 함정). 여기서
            # 놓치면 `min_chars: true` 같은 오타가 조용히 실려 분량 계산이
            # 엉뚱한 수로 돈다 — "실패는 소리 내서 실패한다" 위반이다.
            if not isinstance(v, int) or isinstance(v, bool):
                raise LevelError(
                    f"{p} {name}.{f} 는 정수여야 한다 — "
                    f"지금은 {type(v).__name__}({v!r})"
                )
        for f in _STR_FIELDS:
            v = item[f]
            # 빈 문자열도 거절한다 — 프롬프트에 그대로 얹히는 지시문이라 비면
            # "말하는 방식을 안 가른" 채로 조용히 넘어간다.
            if not isinstance(v, str) or not v.strip():
                raise LevelError(
                    f"{p} {name}.{f} 는 비어 있지 않은 문자열이어야 한다 — "
                    f"지금은 {type(v).__name__}({v!r})"
                )
        out[name] = Level(name=name, **{f: item[f] for f in _FIELDS})
    return out


def level_of_env(levels: dict[str, Level]) -> Level:
    """기동 시 지정한 수준. 오타는 **소리 내서 실패**시킨다 — 조용히 기본값으로
    흘리면 엉뚱한 수준으로 시연이 돌고 로그에 아무것도 없다."""
    raw = os.environ.get("REACHY_AUDIENCE_LEVEL", "").strip()
    if not raw:
        return levels[DEFAULT_LEVEL]
    if raw not in levels:
        raise LevelError(
            f"REACHY_AUDIENCE_LEVEL 이 {raw!r} 다 — 쓸 수 있는 값: {', '.join(LEVEL_NAMES)}"
        )
    return levels[raw]
