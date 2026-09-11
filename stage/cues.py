"""큐시트 로더와 진행 신호 판정.

정본은 `docs/exhibit-guide.md` 이고 이 모듈이 읽는 `data/cues.yaml` 은 그 위에
얹은 진행 단위다. 둘이 어긋나면 큐시트를 고친다 — 반대가 아니다.
"""

import os
import pathlib
from dataclasses import dataclass

import yaml

GAZE_TARGETS = frozenset({"partner", "audience"})

_REQUIRED = ("id", "title", "mc", "docent_brief", "gaze")

# 진행 신호로 볼 낱말.
_ADVANCE_WORDS = ("다음", "계속", "넘어가", "진행")

# 질문 표지. 하나라도 있으면 진행 신호로 보지 않고 LLM 에 넘긴다 —
# "다음은 뭔가요?" 를 전환으로 먹으면 관람객의 질문이 통째로 사라진다.
_QUESTION_MARKS = ("?", "뭐", "무엇", "어떻게", "왜", "누구", "언제", "어디", "얼마")

# 긴 문장은 질문일 확률이 높다. 전환 지시는 짧다.
_ADVANCE_MAX_CHARS = 15


class CueError(ValueError):
    """큐시트가 규약에 맞지 않는다."""


@dataclass(frozen=True)
class Cue:
    """진행 단위 하나."""

    id: str
    title: str
    mc: str
    docent_brief: str
    gaze: str


def cues_path() -> pathlib.Path:
    """큐시트 경로. `REACHY_CUES_PATH` 가 있으면 그것을 쓴다."""
    override = os.environ.get("REACHY_CUES_PATH")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "cues.yaml"


def load_cues(path: pathlib.Path | None = None) -> list[Cue]:
    """큐시트를 읽는다. 어긋나면 **소리 내서 실패한다.**"""
    p = pathlib.Path(path) if path is not None else cues_path()
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CueError(f"큐시트가 없다: {p}") from exc
    except yaml.YAMLError as exc:
        raise CueError(f"큐시트가 YAML 이 아니다: {p} — {exc}") from exc

    if not raw:
        raise CueError(f"큐시트가 비어 있다: {p}")
    if not isinstance(raw, list):
        raise CueError(f"큐시트는 목록이어야 한다: {p} (지금은 {type(raw).__name__})")

    out: list[Cue] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CueError(f"{p} {i}번째 항목이 매핑이 아니다")
        for key in _REQUIRED:
            if not str(item.get(key, "")).strip():
                raise CueError(f"{p} {i}번째 항목에 {key} 가 비어 있다")
        if item["gaze"] not in GAZE_TARGETS:
            raise CueError(
                f"{p} {item['id']}: 모르는 gaze {item['gaze']!r} "
                f"(쓸 수 있는 값: {sorted(GAZE_TARGETS)})"
            )
        if item["id"] in seen:
            raise CueError(f"{p}: 큐 id 가 중복이다 — {item['id']!r}")
        seen.add(item["id"])
        out.append(Cue(**{k: item[k] for k in _REQUIRED}))
    return out


def is_advance(text: str) -> bool:
    """관람객 발화가 '다음으로' 라는 뜻인가.

    보수적으로 판정한다. 놓치면 LLM 이 답을 만들어 주지만, 질문을 전환으로
    잘못 먹으면 관람객의 물음이 통째로 사라진다.
    """
    t = text.strip()
    if not t or len(t) > _ADVANCE_MAX_CHARS:
        return False
    if any(q in t for q in _QUESTION_MARKS):
        return False
    return any(w in t for w in _ADVANCE_WORDS)


class CueSheet:
    """큐 커서. 어디까지 진행했는지만 안다."""

    def __init__(self, cues: list[Cue]) -> None:
        if not cues:
            raise CueError("큐시트가 비어 있다")
        self._cues = list(cues)
        self._i = 0

    @property
    def index(self) -> int:
        return self._i

    @property
    def done(self) -> bool:
        return self._i >= len(self._cues) - 1

    def current(self) -> Cue:
        return self._cues[self._i]

    def advance(self) -> Cue | None:
        """다음 큐로 간다. 마지막이면 None 을 주고 커서는 머문다."""
        if self._i >= len(self._cues) - 1:
            return None
        self._i += 1
        return self._cues[self._i]

    def reset(self) -> None:
        self._i = 0
