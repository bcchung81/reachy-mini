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
# 선택 문자열 필드 — 있으면 문자열이어야 한다.
_OPTIONAL_STR = ("mc_after",)

# 진행 신호로 볼 낱말의 어근.
_ADVANCE_WORDS = ("다음", "계속", "넘어가", "진행")

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
    # 도슨트 뒤 사회자의 받아치기. 관람객 창구가 열린다는 것을 **말로** 알린다 —
    # 마이크가 열려도 관람객은 모른다(리뷰 B2). 비면 곧장 듣기로 간다.
    mc_after: str = ""


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
            v = item.get(key)
            # `str()` 로 감싸면 `mc: 123`·`mc:`(None) 이 통과한다 — 그 값이
            # `_estimate` 의 len() 에서 터져 감독이 데드라인 없이 굳는다(리뷰 A8a).
            # 타입을 요구하는 자리는 강제 변환이 아니라 거절이다.
            if not isinstance(v, str) or not v.strip():
                raise CueError(
                    f"{p} {i}번째 항목의 {key} 가 비어 있거나 문자열이 아니다"
                    f"({type(v).__name__})"
                )
        if item["gaze"] not in GAZE_TARGETS:
            raise CueError(
                f"{p} {item['id']}: 모르는 gaze {item['gaze']!r} "
                f"(쓸 수 있는 값: {sorted(GAZE_TARGETS)})"
            )
        if item["id"] in seen:
            raise CueError(f"{p}: 큐 id 가 중복이다 — {item['id']!r}")
        seen.add(item["id"])
        extra = {}
        for key in _OPTIONAL_STR:
            v = item.get(key, "")
            if v is None:
                v = ""
            if not isinstance(v, str):
                raise CueError(f"{p} {item['id']}: {key} 는 문자열이어야 한다({type(v).__name__})")
            extra[key] = v.strip()
        out.append(Cue(**{k: item[k] for k in _REQUIRED}, **extra))
    return out


def is_advance(text: str) -> bool:
    """관람객 발화가 '다음으로' 라는 뜻인가.

    규칙은 하나다: 비어 있지 않고, 길이 가드 이내이고, 물음표가 없고,
    마지막 낱말이 전환어 어근으로 시작하되 그 뒤에 붙은 글자가 2자
    이하일 때만 진행 신호로 본다. 그 외에는 전부 아니다.

    **왜 "마지막 낱말 + 접미 길이"인가.** 한국어 전환 발화는 전환어로
    끝나고("...다음", "...계속"), 전환어 어근으로 시작하는 질문의 서술어도
    있다("다음이에요?", "계속되나요"). 마지막 낱말이 전환어로 "시작한다"는
    것만으로는 이 둘을 못 가른다 — 조사·짧은 어미(-으로, -하죠, -해)는
    어근 뒤에 2자 이내로 붙지만, 서술어는 그보다 길게 붙는다. 그 길이
    차이가 경계선이다.

    **왜 "?" 는 따로, 가장 먼저 보는가.** 이 함수 안에서 유일하게
    모호하지 않은 신호이기 때문이다. 관람객이 직접 물음표로 표시한
    질문이면, 마지막 낱말의 접미가 2자 이내라도(예: "다음?", "계속?")
    전환으로 읽으면 안 된다 — 접미 길이 경계는 접미의 *길이*만 보고
    *내용*은 안 보므로, "?" 검사를 위치+접미 판정 뒤에 두거나 그 판정과
    같은 자격으로 묶으면 다시 밀려난다.

    **판정 오류의 방향은 의도적으로 비대칭이다.** 전환을 놓치면(예:
    "다음 걸로 진행해주세요"처럼 전환어가 문장 중간에 낀 요청) LLM 이
    답을 만들고, 관람객이 다시 "다음"이라 말하거나 운영자 콘솔로 복구
    할 수 있다 — 싼 손실이다. 질문을 전환으로 잘못 먹으면 관람객의
    물음이 통째로 사라진다 — 비싼 손실이다. 이 함수를 다음에 고칠 때도
    이 방향을 지켜야 한다: 애매하면 전환이 아니라고 판정한다.
    """
    t = text.strip()
    if not t or len(t) > _ADVANCE_MAX_CHARS or "?" in t:
        return False

    last_word = t.split()[-1]
    return any(
        last_word.startswith(w) and len(last_word) - len(w) <= 2
        for w in _ADVANCE_WORDS
    )


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

    def back(self) -> Cue | None:
        """이전 큐로 되돌린다. 첫 큐면 None 을 주고 커서는 머문다.

        `is_advance` 의 오판(설계 §7 "STT 오인식으로 진행 폭주")을 사람이
        되돌리는 유일한 길이다. 커서를 앞으로만 옮길 수 있으면 수동
        오버라이드가 반쪽이다 — 넘어가 버린 섹션을 되찾을 방법이 없었다.
        """
        if self._i <= 0:
            return None
        self._i -= 1
        return self._cues[self._i]

    def reset(self) -> None:
        self._i = 0
