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
#
# 의문사만으로는 부족하다(2026-09-11 리뷰). "다음 얘기 궁금해요" 는 의문사도
# 물음표도 없지만 명백한 질문이다. 묻는 **의도**를 드러내는 낱말을 함께 본다.
_QUESTION_MARKS = (
    "?", "뭐", "무엇", "어떻게", "왜", "누구", "언제", "어디", "얼마",
    "궁금", "알려", "설명", "알고",
)

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

    # 위치 + 접미 길이 판정: 마지막 낱말이 전환어 어근으로 **시작**하고,
    # 그 뒤에 붙은 게 2자 이하일 때만 진행 신호로 본다.
    #
    # 순수 위치 규칙(먼저 시도한 버전)은 또 다른 사각지대를 열었다
    # (2026-09-11 재리뷰) — "언제 다음이에요", "얼마나 계속되나요"처럼
    # 질문의 서술어가 우연히 전환어 어근으로 시작하면, 위치만으로는
    # "궁금한 거 없어요 다음"(진짜 전환)과 구별이 안 된다. 두 문장 모두
    # "마지막 낱말이 전환어 어근으로 시작한다"는 조건은 같이 만족하기
    # 때문이다 — 마지막 낱말 자체의 생김새가 갈라야 한다.
    #
    # 조사·짧은 어미는 어근 뒤에 2자 이내로 붙는다("다음으로", "계속하죠",
    # "넘어가요", "진행해"). 서술어는 그보다 길게 붙는다("다음이에요"
    # +3자, "계속되나요" +4자). 그 길이 차이가 전환과 질문을 가르는
    # 경계선이다 — 2자라는 값이 근거 없이 보이지 않게 이유를 남긴다.
    last_word = t.split()[-1]
    for advance_word in _ADVANCE_WORDS:
        if last_word.startswith(advance_word) and len(last_word) - len(advance_word) <= 2:
            return True

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
