"""코스 — 큐시트에서 이번 공연이 도는 큐들(2026-09-25 결정 문서 「코스」).

데이터는 `data/courses.yaml`(사람이 고친다). 이 모듈은 읽고 **기동에서** 검증만 한다 — 모르는 큐 id·중복·순서
어긋남을 시연 중에 발견하면 그 자리에서 코스가 조용히 짧아지거나 이야기 순서가 뒤집힌다. 레벨 파일
(`stage/levels.py`)과 같은 원칙: 틀린 데이터는 소리 내서 기동을 막는다.
"""

import os
import pathlib

import yaml

from stage.cues import Cue

ALL = "all"


class CourseError(ValueError):
    """코스 파일이 규약에 맞지 않는다."""


def courses_path() -> pathlib.Path:
    """코스 파일 경로. `REACHY_COURSES_PATH` 가 있으면 그것을 쓴다(큐시트의 `REACHY_CUES_PATH` 와 같다)."""
    override = os.environ.get("REACHY_COURSES_PATH")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "courses.yaml"


def load_courses(cues: tuple[Cue, ...] | list[Cue],
                 path: pathlib.Path | None = None) -> dict[str, tuple[str, ...] | None]:
    """코스 이름 → 큐 id 들(`None` 이면 전체). 순서는 파일 순서 — 첫째가 기동 코스, 페이지 버튼 순서다."""
    path = path or courses_path()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CourseError(f"코스 파일이 없다: {path}") from exc
    items = (raw or {}).get("courses") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        raise CourseError(f"{path}: courses 가 비어 있다")
    order = {c.id: i for i, c in enumerate(cues)}
    out: dict[str, tuple[str, ...] | None] = {}
    for n, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise CourseError(f"{path}: {n}번째 코스가 객체가 아니다")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CourseError(f"{path}: {n}번째 코스에 이름이 없다")
        name = name.strip()
        if name in out:
            raise CourseError(f"{path}: 코스 이름이 겹친다: {name!r}")
        ids = item.get("cues")
        if ids == ALL:
            out[name] = None
            continue
        if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids):
            raise CourseError(f"{path}: 코스 {name!r} 의 cues 는 'all' 이거나 큐 id 목록이어야 한다")
        unknown = [x for x in ids if x not in order]
        if unknown:
            raise CourseError(f"{path}: 코스 {name!r} 에 큐시트에 없는 큐가 있다: {unknown}")
        if len(set(ids)) != len(ids):
            raise CourseError(f"{path}: 코스 {name!r} 에 같은 큐가 두 번 있다")
        positions = [order[x] for x in ids]
        if positions != sorted(positions):
            # 커서는 큐시트 순서로만 움직인다(`CueSheet.advance`) — 순서를 바꿔 적으면 적은 대로 돌지 않는다.
            raise CourseError(f"{path}: 코스 {name!r} 의 큐는 큐시트 순서대로 적는다: {ids}")
        out[name] = tuple(ids)
    return out
