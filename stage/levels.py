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

# **공연에서 고르는 수준은 셋이다 — 초등·중고등을 '초중등' 하나로 합쳤다**(2026-11-16 사용자 결정, 실기 리허설 중).
# 합친 수준은 **중고등 대본**으로 말한다(용어를 풀어 말하고 비유로 열어 원리를 한 겹 — 고학년 초등에게도 통하고
# 중고등에게 유치하지 않다). 데이터(대본·교육자료 카드·조사 자료·웹툰·구운 음성)는 `LEVEL_NAMES` 네 수준 그대로 둔다 —
# 고르는 자리(조정실 버튼·콘솔 `l`·기동 수준·교육자료 주소)만 합친다. 그래서 다시 굽지 않고, 되돌릴 때도 아래 세 줄만
# 고친다(`OFFERED_LEVELS` 에 "초등" 을 다시 넣고 `LEVEL_LABELS`·`LEVEL_ALIASES` 를 비운다).
#   OFFERED_LEVELS — 감독이 받아들이고 조정실이 버튼으로 보이는 수준(이 순서가 버튼 순서).
#   LEVEL_LABELS   — 사람에게 보이는 이름. 내부 이름(대본·캐시·화면 선택의 열쇠)은 그대로 "중고등" 이다.
#   LEVEL_ALIASES  — 쳐도 받아 주는 다른 이름. 운영자가 습관대로 `l 초등` 을 쳐도, 교사가 옛 `/handout?level=초등`
#                    주소를 열어도 거절하지 않고 합친 수준으로 간다(바뀐 것은 감독 경고 줄에 이름으로 남는다).
OFFERED_LEVELS = ("중고등", "일반", "전문가")
LEVEL_LABELS = {"중고등": "초중등"}
LEVEL_ALIASES = {"초중등": "중고등", "초등": "중고등"}


def canonical_level(name: str) -> str:
    """사람이 친 수준 이름 → 내부 이름(별칭이면 바꾸고, 아니면 그대로 — 모르는 이름의 판정은 받는 쪽이 한다)."""
    name = (name or "").strip()
    return LEVEL_ALIASES.get(name, name)


def level_label(name: str) -> str:
    """내부 수준 이름 → 사람에게 보이는 이름."""
    return LEVEL_LABELS.get(name, name)

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
    # 별칭(`초등`·`초중등` → 중고등)을 먼저 푼다. 고르는 수준이 셋이 된 뒤(2026-11-16)에도 데이터는 네 수준이라
    # `levels` 에는 초등이 있다 — 별칭을 안 풀면 `REACHY_AUDIENCE_LEVEL=초등` 이 조정실에 버튼이 없는 수준으로 기동한다.
    name = canonical_level(raw)
    if name not in levels or name not in OFFERED_LEVELS:
        offered = ", ".join(f"{level_label(n)}" for n in OFFERED_LEVELS)
        raise LevelError(f"REACHY_AUDIENCE_LEVEL 이 {raw!r} 다 — 쓸 수 있는 값: {offered}")
    return levels[name]
