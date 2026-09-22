# 팟캐스트 다채롭게 — 파일럿 2큐 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** 큐 하나당 도슨트 해설을 수준별 N개 포인트로 쪼개 사회자↔도슨트가 순서대로 주고받게
하는 기능을, 큐 2개(`02-history`, `06-bands`)에 먼저 저작·검증한다.

**Architecture:** `stage/machine.py`의 `TurnMachine`은 손대지 않는다. `Director.on_speaking_ended`
에 라벨 매칭 갈래를 추가해 가변 개수 라운드를 라우팅한다. **핵심 아이디어**: 마지막 포인트의
도슨트 답에는 항상 기존과 똑같은 종단 라벨 `f"{cue.id}:docent"`를 붙인다 — 그러면 기존
"받아치기"(`elif cue_id == f"{cue.id}:docent" and cue.mc_after:`) 분기가 **한 글자도 안 바뀐 채**
그 도착을 그대로 받는다. 중간 포인트(마지막이 아닌)는 `f"{cue.id}:pt{i}:docent"` 라벨을 쓴다.
사회자 다리 대사는 오프라인 사전생성(`data/mc_lines.yaml` 재사용), 도슨트 답은 기존 실시간
생성 경로를 재사용하되 포인트 전용 분량 상한을 얹는다.

**Tech Stack:** Python 3.12, pytest, PyYAML — 새 의존성 없음.

**Spec:** `docs/superpowers/specs/2026-09-22-podcast-turns-design.md` (2단계 설계),
선행: `docs/superpowers/specs/2026-09-21-launch-and-modes-design.md` (1단계)

## Global Constraints

- 총 발화 분량은 지금과 비슷하게 유지한다 — 포인트로 잘게 나눌 뿐 늘리지 않는다(1단계 결정).
- 사회자 분량은 수준과 무관하게 고정(`stage/prompts.py::_MC_MIN/MAX_CHARS`) — 포인트 다리
  대사도 이 규칙을 그대로 쓴다, 새 규칙을 만들지 않는다.
- `points`가 없는 큐(아직 안 옮긴 17개)는 지금 동작 그대로 폴백한다 — 기존 elif 갈래는
  한 글자도 바꾸지 않는다. **모든 태스크의 마지막 단언은 "기존 테스트 전부 PASS"다.**
- `Director` 생성자는 `Level` 객체 전체가 아니라 **필요한 수 하나씩만** 받는다
  (`_docent_min_chars`/`level_min_chars`가 이미 그런 이유 — 생성자를 객체로 바꾸면 테스트
  수십 곳이 같이 흔들린다, `stage/director.py:189-193` 주석). 포인트 분량도 같은 결로
  `level_point_min_chars: dict[str, int]`, `level_point_max: dict[str, tuple[int, int]]`
  두 개의 작은 dict로만 받는다.
- 포인트 왕복 중에는 마이크가 열리지 않는다(`machine.py` 불변식 ①) — 이 계획은 그 불변식을
  건드리지 않는다.
- 새 파이썬 의존성을 추가하지 않는다. 로봇 재배포가 필요 없다(전부 `stage/`·PC 쪽).

---

### Task 1: 수준 프로필에 포인트 분량 필드

**Files:**
- Modify: `stage/levels.py`
- Modify: `data/levels.yaml`
- Test: `tests/test_levels.py`

**Interfaces:**
- Produces: `Level.point_min_sentences: int`, `Level.point_max_sentences: int`,
  `Level.point_min_chars: int`, `Level.point_max_chars: int` — Task 4가 소비한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_levels.py`의 `_valid_raw()` 바로 아래에 헬퍼를 추가하고, 기존
`test_수준_넷이_모두_있다` 아래에 테스트를 추가한다:

```python
def _valid_raw_with_points() -> dict:
    raw = _valid_raw()
    for name in raw:
        raw[name].update(
            point_min_sentences=1, point_max_sentences=1,
            point_min_chars=30, point_max_chars=60,
        )
    return raw


def test_포인트_분량_필드가_있다(tmp_path):
    p = _write(tmp_path, _valid_raw_with_points())
    lv = load_levels(p)
    assert lv["초등"].point_min_chars == 30
    assert lv["초등"].point_max_chars == 60
    assert lv["초등"].point_min_sentences == 1
    assert lv["초등"].point_max_sentences == 1


def test_포인트_분량_필드가_없으면_거절한다(tmp_path):
    p = _write(tmp_path, _valid_raw())  # 포인트 필드 없는 옛 데이터
    with pytest.raises(LevelError, match="point_min_chars"):
        load_levels(p)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_levels.py -k 포인트 -v`
Expected: FAIL — `TypeError`(필드가 아직 없다) 또는 `LevelError`가 안 남(검증이 아직 없다).

- [ ] **Step 3: `stage/levels.py`에 필드를 추가한다**

`_INT_FIELDS`에 네 필드를 더한다:

```python
_INT_FIELDS = (
    "min_sentences", "max_sentences", "min_chars", "max_chars",
    "point_min_sentences", "point_max_sentences", "point_min_chars", "point_max_chars",
)
```

`Level` 데이터클래스에 필드를 더한다(`vocabulary` 앞에 끼워 넣는다):

```python
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
```

(`load_levels`의 나머지 검증 로직은 `_FIELDS = _INT_FIELDS + _STR_FIELDS`와
`Level(name=name, **{f: item[f] for f in _FIELDS})`를 그대로 쓰므로 안 고쳐도 된다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_levels.py -v`
Expected: 새 테스트 PASS. **기존 테스트 중 `load_levels()`를 인자 없이 부르는 것들
(진짜 `data/levels.yaml`을 읽는 것)은 Step 5 전까지 FAIL한다 — 정상이다, 계속 진행한다.**

- [ ] **Step 5: `data/levels.yaml`에 실제 값을 채운다**

설계 문서 §3 표의 수치. 각 수준 블록 끝(`sources:` 줄 다음)에 추가:

```yaml
초등:
  point_min_sentences: 1
  point_max_sentences: 1
  point_min_chars: 35
  point_max_chars: 60
중고등:
  point_min_sentences: 1
  point_max_sentences: 1
  point_min_chars: 40
  point_max_chars: 65
일반:
  point_min_sentences: 1
  point_max_sentences: 2
  point_min_chars: 60
  point_max_chars: 95
전문가:
  point_min_sentences: 1
  point_max_sentences: 2
  point_min_chars: 65
  point_max_chars: 100
```

- [ ] **Step 6: 전체 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_levels.py -v`
Expected: 전부 PASS.

- [ ] **Step 7: 커밋**

```bash
git add stage/levels.py data/levels.yaml tests/test_levels.py
git commit -m "feat(stage): 수준 프로필에 포인트 라운드 분량 필드를 더한다"
```

---

### Task 2: 큐 데이터에 `points` 필드

**Files:**
- Modify: `stage/cues.py`
- Test: `tests/test_stage_cues.py`

**Interfaces:**
- Produces: `Cue.points_for(level_name: str) -> list[str]` — 없으면 빈 리스트. Task 5가 소비한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_cues.py` 상단에 `import pytest`와
`from stage.cues import Cue, CueError, load_cues`가 있는지 확인하고(없으면 추가), 끝에
추가한다:

```python
def _briefs(points=None):
    b = {}
    for name in ("초등", "중고등", "일반", "전문가"):
        entry = {"mc_brief": "mb", "docent_brief": "db"}
        if points is not None:
            entry["points"] = list(points)
        b[name] = entry
    return b


def test_points가_있으면_읽힌다(tmp_path):
    raw = [{
        "id": "c1", "title": "t", "mc": "m", "docent_brief": "d",
        "gaze": "partner", "mc_after": "받아치기 다음",
        "briefs": _briefs(["포인트1", "포인트2"]),
    }]
    p = tmp_path / "cues.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    cues = load_cues(p)
    assert cues[0].points_for("일반") == ["포인트1", "포인트2"]


def test_points가_없으면_빈_목록이다(tmp_path):
    raw = [{
        "id": "c1", "title": "t", "mc": "m", "docent_brief": "d",
        "gaze": "partner", "mc_after": "받아치기 다음",
    }]
    p = tmp_path / "cues.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    cues = load_cues(p)
    assert cues[0].points_for("일반") == []


def test_points가_빈_목록이면_거절한다(tmp_path):
    raw = [{
        "id": "c1", "title": "t", "mc": "m", "docent_brief": "d",
        "gaze": "partner", "mc_after": "받아치기 다음",
        "briefs": _briefs([]),
    }]
    p = tmp_path / "cues.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(CueError, match="points"):
        load_cues(p)


def test_points가_있는데_mc_after가_없으면_거절한다(tmp_path):
    raw = [{
        "id": "c1", "title": "t", "mc": "m", "docent_brief": "d",
        "gaze": "partner",  # mc_after 없음
        "briefs": _briefs(["p1"]),
    }]
    p = tmp_path / "cues.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(CueError, match="mc_after"):
        load_cues(p)
```

(`yaml` 모듈도 파일 상단 import에 있는지 확인 — 이미 다른 테스트가 쓰고 있을 가능성이 크다.)

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -k points -v`
Expected: FAIL — `AttributeError: 'Cue' object has no attribute 'points_for'`.

- [ ] **Step 3: `stage/cues.py`를 고친다**

`Cue.brief_for` 메서드 뒤(같은 클래스 안)에 추가:

```python
    def points_for(self, level_name: str) -> list[str]:
        """이 수준의 포인트 목록. 없으면(폴백 큐) 빈 목록."""
        b = self.briefs.get(level_name)
        if not b:
            return []
        return list(b.get("points", []))
```

`load_cues`의 수준별 `briefs` 검증 루프 안, 기존 `for field_name in ("mc_brief",
"docent_brief"):` 블록 **다음**(들여쓰기가 `for name, b in briefs.items():` 블록 안, 그
루프와 같은 레벨)에 추가:

```python
                points = b.get("points")
                if points is not None:
                    if not isinstance(points, list) or not points:
                        raise CueError(
                            f"{p} {item['id']} {name}: points 는 비어 있지 않은 "
                            f"목록이어야 한다 — 지금은 {type(points).__name__}({points!r})"
                        )
                    for pi, pt in enumerate(points):
                        if not isinstance(pt, str) or not pt.strip():
                            raise CueError(
                                f"{p} {item['id']} {name}: points[{pi}] 는 비어 있지 "
                                f"않은 문자열이어야 한다 — 지금은 {type(pt).__name__}({pt!r})"
                            )
```

`out.append(Cue(**{k: item[k] for k in _REQUIRED}, **extra))` **바로 앞**에 큐 단위 검사를
추가한다(이 시점에 `extra["mc_after"]`·`extra["briefs"]`가 이미 채워져 있다):

```python
        if extra["briefs"] and any(
            b.get("points") for b in extra["briefs"].values()
        ) and not extra["mc_after"]:
            raise CueError(
                f"{p} {item['id']}: points 가 있는데 mc_after 가 없다 — "
                "마지막 라운드 뒤 받아치기로 합류할 자리가 없다"
            )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add stage/cues.py tests/test_stage_cues.py
git commit -m "feat(stage): 큐 데이터에 수준별 points 필드와 검증을 더한다"
```

---

### Task 3: `_Pending`에 분량 하한 오버라이드

**Files:**
- Modify: `stage/director.py` (`_Pending` 클래스, `_warn_if_short`, `_await_pending`의 두
  호출부)
- Test: `tests/test_stage_director.py`

**Interfaces:**
- Produces: `_Pending.min_chars: int | None = None`(기본값 `None` = 지금처럼
  `self._docent_min_chars`/`MIN_CHARS` 사용). Task 5가 포인트 라운드에서 채워 넘긴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_director.py`의 기존 `test_생성_결과가_너무_짧으면_경고한다`(1113번 줄
근방) 바로 아래에 추가한다 — 같은 `Harness` 패턴을 쓴다:

```python
def test_min_chars_오버라이드가_있으면_그것으로_짧음을_잰다():
    """받아치기 슬롯이 아니라 도슨트 슬롯이라도, pending.min_chars 가 있으면
    self._docent_min_chars(수십~수백자) 대신 그 값으로 짧음을 잰다 — 포인트
    라운드가 의도적으로 짧게 답해도 "너무 짧다" 오탐이 안 나야 한다."""
    h = Harness(generate=lambda role, brief, hist: "한 문장짜리 짧은 답입니다.")
    h.d._warn_if_short("한 문장짜리 짧은 답입니다.", "테스트", "docent", min_chars=5)
    assert not any("너무 짧다" in w for w in h.warnings)
    h.d._warn_if_short("한 문장짜리 짧은 답입니다.", "테스트", "docent", min_chars=500)
    assert any("너무 짧다" in w for w in h.warnings)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k min_chars_오버라이드 -v`
Expected: FAIL — `TypeError: _warn_if_short() got an unexpected keyword argument 'min_chars'`.

- [ ] **Step 3: `_Pending`과 `_warn_if_short`를 고친다**

`_Pending`에 필드를 더한다(NamedTuple 마지막 필드라 기본값을 줄 수 있다):

```python
class _Pending(NamedTuple):
    slot: str
    role: str
    cue_id: str
    fallback: str
    fallback_kind: str
    label: str
    min_chars: int | None = None   # 있으면 이 값으로 짧음을 잰다(포인트 라운드용)
```

`_warn_if_short`의 시그니처와 첫 판정 줄을 바꾼다:

```python
    def _warn_if_short(self, text: str, label: str, role: str,
                        min_chars: int | None = None) -> None:
        ...
        limit = min_chars if min_chars is not None else (
            self._docent_min_chars if role == "docent" else MIN_CHARS
        )
```

`_await_pending`의 두 호출부(§4.·4.2 부근)를 고친다:

```python
        self._warn_if_short(text, label, pending.role, pending.min_chars)
```

```python
            self._warn_if_short(pending.fallback, pending.label, pending.role, pending.min_chars)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -v`
Expected: 전부 PASS(기존 `_Pending(...)` 위치 인자 생성 테스트는 6개 인자 그대로 통과 —
7번째는 기본값이 채운다).

- [ ] **Step 5: 커밋**

```bash
git add stage/director.py tests/test_stage_director.py
git commit -m "feat(stage): _Pending에 분량 하한 오버라이드를 더한다(포인트 라운드 대비)"
```

---

### Task 4: 생성자 배선 — 포인트 분량을 감독까지 흘린다

**Files:**
- Modify: `stage/director.py` (`Director.__init__`)
- Modify: `stage/server.py` (`StageServer.__init__`)
- Modify: `stage/__main__.py` (`StageServer(...)` 호출부)
- Test: `tests/test_stage_director.py`, `tests/test_stage_main.py`

기존 `level_min_chars: dict[str, int]`(수준 이름 → 도슨트 하한 **하나만**)와 정확히 같은
결로, 포인트용 두 dict를 추가한다. `Level` 객체 전체를 넘기지 않는다(Global Constraints 참고).

**Interfaces:**
- Produces: `Director._level_point_min_chars: dict[str, int]`,
  `Director._level_point_max: dict[str, tuple[int, int]]`(수준별 (max_sentences, max_chars)).
  Task 5가 `self._level_point_min_chars[self._level_name]` 등으로 읽는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_director.py`에서 `Harness.__init__`이 `levels=` 인자를 이미 받는지
확인한다(위에서 읽은 시그니처에는 없었다 — 새로 추가한다). `Harness.__init__`의 `kw = {}
if docent_min_chars is None else ...` 다음에 추가:

```python
        if level_point_min_chars is not None:
            kw["level_point_min_chars"] = level_point_min_chars
        if level_point_max is not None:
            kw["level_point_max"] = level_point_max
```

그리고 `Harness.__init__` 시그니처에 두 인자를 추가한다(`levels=None` 대신, 기존 인자
이름과 결을 맞춘다):

```python
    def __init__(
        self, generate=None, expect_units=None, after=("", ""),
        sheet=None, level_name="일반", mc_lines=None, docent_min_chars=None,
        levels=None, on_level_change=None,
        level_point_min_chars=None, level_point_max=None,
    ):
```

테스트를 추가한다(파일 끝, 또는 Task 3에서 추가한 테스트 근처):

```python
def test_포인트_분량_dict가_감독까지_닿는다():
    h = Harness(level_point_min_chars={"일반": 60}, level_point_max={"일반": (2, 95)})
    assert h.d._level_point_min_chars["일반"] == 60
    assert h.d._level_point_max["일반"] == (2, 95)


def test_포인트_분량_dict를_안_주면_빈_dict다():
    h = Harness()
    assert h.d._level_point_min_chars == {}
    assert h.d._level_point_max == {}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k 포인트_분량_dict -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'level_point_min_chars'`.

- [ ] **Step 3: `Director.__init__`을 고친다**

시그니처에 두 인자를 추가한다(`on_level_change` 다음):

```python
        on_level_change: Callable[[str], None] | None = None,
        level_point_min_chars: dict[str, int] | None = None,
        level_point_max: dict[str, tuple[int, int]] | None = None,
    ) -> None:
```

본문에서 `self._level_pending: str | None = None` 다음 줄에 추가:

```python
        # 포인트 라운드 도슨트 답의 분량(하한·상한) — `_level_min_chars`와 같은 결
        # (Level 객체 전체가 아니라 쓰는 수만 받는다). 없으면 빈 dict — 포인트가
        # 없는 큐만 쓰는 감독(대부분의 기존 테스트)은 이 값을 아예 안 본다.
        self._level_point_min_chars = dict(level_point_min_chars or {})
        self._level_point_max = dict(level_point_max or {})
        self._points: list[str] = []
        self._point_i: int = 0
```

- [ ] **Step 4: `StageServer.__init__`을 고친다**

시그니처에 같은 두 인자를 추가하고(`camera: CameraRelay | None = None,` 앞), `Director(...)`
호출에 그대로 넘긴다:

```python
        level_min_chars: dict[str, int] | None = None,
        on_level_change: Callable[[str], None] | None = None,
        level_point_min_chars: dict[str, int] | None = None,
        level_point_max: dict[str, tuple[int, int]] | None = None,
        camera: CameraRelay | None = None,
    ) -> None:
        ...
        self.director = Director(
            sheet, generate=generate, send=self._send,
            expect_units=expect_units, warn=warn,
            mc_lines=mc_lines, level_name=level_name,
            docent_min_chars=docent_min_chars,
            level_min_chars=level_min_chars,
            on_level_change=on_level_change,
            level_point_min_chars=level_point_min_chars,
            level_point_max=level_point_max,
        )
```

- [ ] **Step 5: `stage/__main__.py`의 `StageServer(...)` 호출을 고친다**

`level_min_chars={name: lv.min_chars for name, lv in levels.items()},` 다음 줄에 추가:

```python
        level_point_min_chars={name: lv.point_min_chars for name, lv in levels.items()},
        level_point_max={
            name: (lv.point_max_sentences, lv.point_max_chars) for name, lv in levels.items()
        },
```

- [ ] **Step 6: 배선 테스트 확인**

`tests/test_stage_main.py`에서 `test_main_에서_감독까지_수준_전환이_끝까지_이어진다`를 찾아
읽는다 — 그 테스트가 `level_min_chars`의 값이 `main()` → `StageServer` → `Director`까지
정확히 닿는지 확인하는 것과 같은 방식으로, 포인트 배선도 확인하는 단언을 그 테스트에
추가한다(새 테스트를 만들지 않는다 — 이미 같은 배선 경로를 검증하는 테스트가 있으므로
거기 단언만 더한다):

```python
    assert server.director._level_point_min_chars["일반"] == levels["일반"].point_min_chars
```

(정확한 변수명 `server`/`levels`는 그 테스트의 기존 지역 변수를 그대로 쓴다.)

- [ ] **Step 7: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py tests/test_stage_main.py -v`
Expected: 전부 PASS.

- [ ] **Step 8: 커밋**

```bash
git add stage/director.py stage/server.py stage/__main__.py tests/test_stage_director.py tests/test_stage_main.py
git commit -m "feat(stage): 포인트 라운드 분량 dict를 main→StageServer→Director로 배선한다"
```

---

### Task 5: 포인트 라운드 라우팅

**Files:**
- Modify: `stage/director.py` (`_begin_cue`, `on_speaking_ended`)
- Test: `tests/test_stage_director.py`

**Interfaces:**
- Consumes: `Cue.points_for`(Task 2), `_Pending.min_chars`(Task 3),
  `self._level_point_min_chars`/`self._level_point_max`(Task 4).
- Produces: 큐가 `points`를 가지면 N회 왕복 후 기존 받아치기로 합류. 없으면 지금과 동일.

**핵심 규칙(구현 전에 정확히 이해한다)**: 마지막 포인트의 도슨트 답은 항상 라벨
`f"{cue.id}:docent"`를 쓴다(포인트가 1개뿐이면 그 하나가 곧 마지막이다) — 그래야 기존
`elif cue_id == f"{cue.id}:docent" and cue.mc_after:` 받아치기 분기가 안 바뀐 채로 그걸
받는다. 마지막이 아닌 포인트는 `f"{cue.id}:pt{i}:docent"`를 쓴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_director.py`에 추가한다(`Harness`가 이미 임포트한 `Cue`/`CueSheet`를
그대로 쓴다):

```python
def _포인트_큐(points, mc_after="받아치기"):
    return Cue(
        "c1", "제목", "사회자 오프닝", "옛 지시문(폴백용)", "partner",
        mc_after=mc_after,
        briefs={
            "일반": {"mc_brief": "mb", "docent_brief": "옛 지시문(폴백용)", "points": points},
        },
    )


def test_포인트가_2개면_두_라운드_뒤_받아치기로_합류한다():
    sheet = CueSheet([_포인트_큐(["p1", "p2"])])
    h = Harness(
        sheet=sheet,
        mc_lines={cache_key("c1", "일반", "p2"): "다리대사(p2로)"},
        generate=lambda role, brief, hist: f"[{brief} 답]",
    )
    h.d.start()
    assert h.says() == [("mc", "사회자 오프닝")]

    h.ended("mc", "c1")  # 오프닝 끝 — point0(p1) 도슨트 답을 기다렸다 보낸다
    assert h.says()[-1] == ("docent", "[p1 답]")
    assert h.d._machine.cue_id == "c1:pt0:docent"

    h.ended("docent", "c1:pt0:docent")  # point0 답 끝 — 다리대사(p2)로 넘어간다
    assert h.says()[-1] == ("mc", "다리대사(p2로)")
    assert h.d._machine.cue_id == "c1:pt1"

    h.ended("mc", "c1:pt1")  # 다리대사 끝 — point1(p2, 마지막) 도슨트 답을 기다린다
    assert h.says()[-1] == ("docent", "[p2 답]")
    assert h.d._machine.cue_id == "c1:docent"  # 종단 라벨 — 기존 받아치기 분기가 받는다

    h.ended("docent", "c1:docent")  # 마지막 포인트 끝 — 기존 받아치기 분기가 그대로 돈다
    assert h.says()[-1][0] == "mc"  # 받아치기(mc_after 계열)
    assert h.d.state is State.LISTENING


def test_포인트가_1개면_기존_단일_라운드와_같은_모양이다():
    sheet = CueSheet([_포인트_큐(["p1"])])
    h = Harness(sheet=sheet, generate=lambda role, brief, hist: f"[{brief} 답]")
    h.d.start()
    h.ended("mc", "c1")
    assert h.d._machine.cue_id == "c1:docent"  # 포인트 1개는 바로 종단 라벨
    h.ended("docent", "c1:docent")
    assert h.says()[-1][0] == "mc"


def test_points가_없는_큐는_기존_경로_그대로다():
    """회귀 방지 — 이 계획의 가장 중요한 단언."""
    h = Harness(after=("받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    assert h.d._machine.cue_id == "c1:docent"
    h.ended("docent", "c1:docent")
    assert h.d.state is State.LISTENING
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k "포인트가_2개 or 포인트가_1개" -v`
Expected: FAIL — 포인트 라우팅이 아직 없어 `cue_id`가 기대와 다르다(`c1:docent`로 곧장
가거나 `KeyError` 등).

- [ ] **Step 3: `_begin_cue`를 고친다**

`self._spawn_generate("docent", "docent", docent_brief, docent_brief, cue.id)` 줄을
찾아 그 줄을 포함해 아래로 바꾼다:

```python
        points = cue.points_for(self._level_name)
        self._points = points
        self._point_i = 0
        if points:
            label0 = self._point_label(cue, 0)
            self._spawn_generate("docent", "docent", points[0], points[0], label0)
        else:
            self._spawn_generate("docent", "docent", docent_brief, docent_brief, cue.id)
```

`Director` 클래스 안에 헬퍼 메서드를 더한다(`_begin_cue` 바로 앞이나 뒤, 들여쓰기는
메서드와 같게):

```python
    def _point_label(self, cue: Cue, i: int) -> str:
        """포인트 i 도슨트 답의 발화 id. **마지막 포인트는 항상 종단 라벨**
        (`f"{cue.id}:docent"`)을 써서 기존 받아치기 분기가 그대로 받게 한다."""
        if i == len(self._points) - 1:
            return f"{cue.id}:docent"
        return f"{cue.id}:pt{i}:docent"

    def _point_budget(self) -> tuple[int, int, int]:
        """(min_chars, max_sentences, max_chars) — 지금 수준의 포인트 분량.
        배선이 안 됐으면(빈 dict) 도슨트 전체 하한/상한으로 물러난다 — 안전한 기본값."""
        min_chars = self._level_point_min_chars.get(self._level_name, self._docent_min_chars)
        max_sentences, max_chars = self._level_point_max.get(
            self._level_name, (10**9, 10**9)  # 사실상 무제한 — 배선 전 테스트를 안 깬다
        )
        return min_chars, max_sentences, max_chars
```

- [ ] **Step 4: `on_speaking_ended`의 첫 분기를 가른다**

기존 `if cue_id == cue.id:` 줄을 찾아 그 블록 전체를 아래로 바꾼다:

```python
            if cue_id == cue.id and not self._points:
                pending = _Pending(
                    "docent", "docent", f"{cue.id}:docent",
                    cue.brief_for(self._level_name)[1], FB_BRIEF, cue.id,
                )
                if cue.mc_after:
                    after_of = cue
            elif cue_id == cue.id and self._points:
                # 오프닝이 끝났다 — point0 답(이미 `_begin_cue`가 스폰해 둔 슬롯)을 기다린다.
                min_chars, _, _ = self._point_budget()
                label0 = self._point_label(cue, 0)
                pending = _Pending(
                    "docent", "docent", label0, self._points[0], FB_BRIEF, label0,
                    min_chars=min_chars,
                )
                if label0 == f"{cue.id}:docent" and cue.mc_after:
                    after_of = cue  # 포인트가 1개뿐이면 이게 곧 마지막이다
```

- [ ] **Step 5: 포인트 왕복 갈래 둘을 추가한다**

기존 `elif cue_id == f"{cue.id}:ack":` 줄 **바로 앞**에 두 분기를 끼운다:

```python
            elif (
                cue_id.startswith(f"{cue.id}:pt")
                and cue_id.endswith(":docent")
                and cue_id != f"{cue.id}:docent"
            ):
                # 포인트 i(마지막 아님)의 도슨트 답이 끝났다 — 다음 포인트로 넘어간다.
                i = self._point_i
                next_i = i + 1
                next_point = self._points[next_i]
                bridge_key = cache_key(cue.id, self._level_name, next_point)
                bridge_text = self._mc_lines.get(bridge_key, "")
                if not bridge_text:
                    self._warn(
                        f"[{cue.id}:pt{next_i}] 다리 대사 캐시가 없다"
                        f"({self._level_name}, key={bridge_key!r}) — 포인트 원문으로 잇는다"
                    )
                    bridge_text = next_point
                self._point_i = next_i
                self._remember(f"사회자: {bridge_text}")
                next_label = self._point_label(cue, next_i)
                self._spawn_generate("docent", "docent", next_point, next_point, next_label)
                self._emit(
                    cmds
                    + self._machine.speak(
                        self._who("mc"), f"{cue.id}:pt{next_i}", bridge_text, gaze="audience",
                    )
                )
                return
            elif cue_id.startswith(f"{cue.id}:pt") and not cue_id.endswith(":docent"):
                # 사회자의 다리 대사(포인트 i, i>=1)가 끝났다 — 이미 스폰된 포인트 i
                # 도슨트 답을 기다린다.
                i = self._point_i
                min_chars, _, _ = self._point_budget()
                label_i = self._point_label(cue, i)
                pending = _Pending(
                    "docent", "docent", label_i, self._points[i], FB_BRIEF, label_i,
                    min_chars=min_chars,
                )
                if label_i == f"{cue.id}:docent" and cue.mc_after:
                    after_of = cue  # 이 포인트가 마지막이다
```

(`from stage.mc_cache import cache_key`가 이미 파일 상단에 import돼 있는지 확인 —
`_begin_cue`가 이미 `cache_key`를 쓰므로 있을 것이다.)

- [ ] **Step 6: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -v`
Expected: **전부 PASS** — 새 테스트 3개뿐 아니라 기존 받아치기·유령·세대 검사 테스트가
하나도 안 깨져야 한다. 하나라도 깨지면 Step 4의 조건 분기(`and not self._points`)가
잘못 들어가 기존 폴백 경로를 가린 것이다 — `git diff stage/director.py`로 기존
`elif cue_id == f"{cue.id}:docent"`류 줄의 조건이 실수로 바뀌지 않았는지 확인한다.

- [ ] **Step 7: 커밋**

```bash
git add stage/director.py tests/test_stage_director.py
git commit -m "feat(stage): 큐당 N회 포인트 왕복 라우팅 — 마지막 포인트는 기존 받아치기로 합류"
```

---

### Task 6: 사회자 다리 대사 프롬프트

**Files:**
- Modify: `stage/prompts.py`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Produces: `build_bridge_prompt(next_point: str) -> str` — Task 7이 이 결과를
  `gen("mc", build_bridge_prompt(point), [])`의 브리프 인자로 쓴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_prompts.py` 끝에:

```python
def test_다리_대사_프롬프트에_포인트_문구가_들어간다():
    from stage.prompts import build_bridge_prompt
    out = build_bridge_prompt("패러데이가 1831년에 무엇을 실험했는지")
    assert "패러데이가 1831년에 무엇을 실험했는지" in out
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_prompts.py -k 다리_대사 -v`
Expected: FAIL — `ImportError: cannot import name 'build_bridge_prompt'`.

- [ ] **Step 3: `stage/prompts.py`에 함수를 더한다**

파일 끝(`build_system_prompt` 뒤)에 추가:

```python
# 다리 대사 생성에 심는 톤 예시(설계 §5 "사회자 말투 카드"). 라운드마다 포인트
# 내용이 달라 고정 문구는 못 쓰지만, 톤은 few-shot 으로 통제한다.
_BRIDGE_TONE_EXAMPLES = (
    "오, 그런데 이런 것도 있다면서요?",
    "잠깐, 그거 말고 다른 것도 궁금한데요.",
    "그렇군요. 그럼 이건 어때요?",
)


def build_bridge_prompt(next_point: str) -> str:
    """다음 포인트로 자연스럽게 넘어가는 사회자 다리 대사를 만들라는 지시문.

    `stage/__main__.py::build_generate` 의 `gen("mc", 이 결과, [])` 로 호출된다 —
    분량은 시스템 프롬프트의 사회자 고정 규칙(`_amount_for` role="mc")이 이미 준다.
    """
    examples = "\n".join(f"- {e}" for e in _BRIDGE_TONE_EXAMPLES)
    return (
        f"도슨트에게 다음 소주제를 물어볼 차례다: {next_point}. "
        "직전 답을 짧게 받지 말고, 새 소주제로 자연스럽게 넘어가는 한두 마디를 만든다. "
        f"예시 톤(그대로 베끼지 말고 참고만 한다):\n{examples}"
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_prompts.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add stage/prompts.py tests/test_prompts.py
git commit -m "feat(stage): 포인트 다리 대사 생성 프롬프트 — 사회자 말투 카드"
```

---

### Task 7: 다리 대사 사전생성

**Files:**
- Modify: `scripts/pregen_mc_lines.py`
- Test: `tests/test_pregen.py`

**Interfaces:**
- Consumes: `Cue.points_for`(Task 2), `build_bridge_prompt`(Task 6),
  `mc_cache.cache_key`/`_append_entry`(기존, 안 바꿈).
- Produces: `data/mc_lines.yaml`에 다리 대사 항목 추가(오프닝 대사와 같은 파일·같은 키 형식).

- [ ] **Step 1: 기존 테스트의 격리 방식을 읽는다**

Run: `sed -n '1,60p' tests/test_pregen.py`

가짜 `build_generate`(또는 `gen`)를 어떻게 주입하는지, 캐시 경로를 `tmp_path`로 어떻게
격리하는지 확인한다 — 다음 스텝의 테스트가 **그 정확한 방식**을 그대로 쓴다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

Step 1에서 확인한 몽키패치/격리 패턴을 그대로 써서(정확한 대상은 그 파일의 기존 테스트
하나를 복사해 만든다), 다음 시나리오를 검증하는 테스트를 추가한다: 큐 하나가
`points_for("일반") == ["p1", "p2"]`를 돌려주도록 준비하고 `main()`을 실행한 뒤,
`cache_key(cue.id, "일반", "p1")`과 `cache_key(cue.id, "일반", "p2")` 두 키가 모두
결과 dict(또는 다시 읽은 캐시 파일)에 있는지 확인한다.

- [ ] **Step 3: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_pregen.py -k points -v`
Expected: FAIL(다리 대사 생성 루프가 아직 없다).

- [ ] **Step 4: `scripts/pregen_mc_lines.py`를 고친다**

파일 상단 import에 추가:

```python
from stage.prompts import build_bridge_prompt
```

`_valid_keys`를 고쳐 다리 대사 키도 포함시킨다(안 그러면 "고아"로 오판된다):

```python
def _valid_keys(cues) -> set[str]:
    keys = set()
    for cue in cues:
        for name in LEVEL_NAMES:
            mc_brief, _ = cue.brief_for(name)
            if mc_brief:
                keys.add(cache_key(cue.id, name, mc_brief))
            for point_text in cue.points_for(name):
                keys.add(cache_key(cue.id, name, point_text))
    return keys
```

`main()`의 `for cue in cues:` 루프 안, `_append_entry(p, key, text)` 다음 줄에 추가:

```python
                for point_i, point_text in enumerate(cue.points_for(name)):
                    pkey = cache_key(cue.id, name, point_text)
                    if pkey in out:
                        continue
                    ptext = gen("mc", build_bridge_prompt(point_text), [])
                    out[pkey] = ptext
                    _append_entry(p, pkey, ptext)
                    print(f"  {cue.id}/{name}/pt{point_i} 다리대사: {ptext}", flush=True)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_pregen.py -v`
Expected: 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add scripts/pregen_mc_lines.py tests/test_pregen.py
git commit -m "feat(scripts): 다리 대사도 여는 대사와 같은 캐시에 사전 생성한다"
```

---

### Task 8: 파일럿 큐 2개 저작 — `02-history`, `06-bands`

**Files:**
- Modify: `data/cues.yaml`

기존 `docent_brief`(사람이 이미 검수한 문장)를 소주제 단위로 쪼갠 것이다 — 새 사실을
조사하지 않는다, 원문 재배열만 한다.

- [ ] **Step 1: `02-history`의 네 수준에 `points`를 추가한다**

`data/cues.yaml`의 `02-history` 큐, `briefs` 아래 각 수준 블록(`docent_brief:` 다음 줄,
기존 들여쓰기와 맞춘다)에 추가:

```yaml
    초등:
      points:
        - 전파는 사람이 만든 게 아니라 원래 있었는데 사람이 찾아낸 것
        - 먼저 머리로 '있을 거야' 라고 알아낸 사람이 있었고, 나중에 실험으로 진짜 있다는 걸 보여준 사람이 있었다는 것
    중고등:
      points:
        - 전파는 발명이 아니라 발견이라는 대비
        - 맥스웰이 수식으로 존재를 예언하고 헤르츠가 실험으로 증명했으며, 마르코니가 그것을 통신에 써먹었다는 세 단계
        - 1901년 마르코니의 대서양 횡단 수신, 거리는 약 3,500km
    일반:
      points:
        - 전파는 발명이 아니라 발견이라는 대비
        - 맥스웰의 이론적 예언 → 헤르츠의 실험적 증명 → 마르코니의 실용화라는 세 단계
        - 1901년 12월 12일 마르코니가 폴듀에서 보낸 모스 부호를 대서양 건너 약 3,500km 떨어진 곳(당시 영국 식민지 뉴펀들랜드)에서 수신했다는 것
    전문가:
      points:
        - 맥스웰 방정식의 예언과 헤르츠의 결정적 실험 증명
        - 마르코니의 실용 무선전신과 1909년 노벨상(브라운 공동 수상)
        - 1901년 12월 12일 연 안테나로 폴듀에서 세인트존스까지 약 2,200마일(3,500km) 수신 보고, 그 진위가 지금도 기술적 논쟁의 대상이라는 것
        - 1785년 쿨롱 법칙은 전자기학의 출발점이지 전파의 발견이 아니라는 구분
```

- [ ] **Step 2: `06-bands`의 네 수준에 `points`를 추가한다**

```yaml
    초등:
      points:
        - 전파에는 아주 길게 출렁이는 것부터 아주 짧게 떨리는 것까지 여러 종류가 있고, 길이가 다르면 잘하는 일도 다르다는 것
        - 이 코너에 놓인 기계들은 서로 다른 종류의 전파를 쓰던 옛날 기계라는 것
    중고등:
      points:
        - 주파수가 낮을수록 파장이 길고 장애물을 돌아 멀리 가며, 높을수록 파장이 짧고 곧게 나아간다는 대비
        - 성질이 다르니 국제기구가 구간을 나누고 쓰임새를 정해 뒀다는 것
        - 전시된 기계들이 그 서로 다른 구간을 쓰던 것들이라는 것
    일반:
      points:
        - 국제전기통신연합(ITU)이 전파를 주파수 순서로 구간을 나누고 이름을 붙였다는 것
        - 이 전시의 낮은 쪽 끝이 초장파(VLF)이고 높은 쪽 끝이 밀리미터파(EHF), 그 사이가 파장으로 100킬로미터에서 1밀리미터까지라는 것
        - 파장이 길수록 멀리 돌아가고 짧을수록 직진한다는 것
    전문가:
      points:
        - ITU-R 권고 V.431-8 Table 1이 대역번호 3(ULF, 300~3,000 Hz)부터 15(300~3,000 THz)까지를 정의하고, 무선규칙(RR) No. 2.1의 표는 4번(VLF)부터 12번(300~3,000 GHz)까지를 싣는다는 것
        - 전시 범위인 VLF(4번)~EHF(11번)는 8개 대역, 주파수 3 kHz~300 GHz, 파장 100 km~1 mm 라는 것
        - 명명 체계가 둘이라는 점 — VLF/LF/MF/HF/VHF/UHF/SHF/EHF 는 주파수 기준 기호이고, 미리어미터파부터 밀리미터파까지는 파장 기준 이름이라는 것
        - 한국어 중파·단파·초단파의 주파수 범위는 전파법 시행령 제2조에 그대로 있다는 것
```

(`mc_brief`/`docent_brief`는 그대로 둔다 — 폴백 경로가 여전히 그걸 쓴다.)

- [ ] **Step 3: 데이터 검증**

Run:
```bash
.venv/bin/python -c "
from stage.cues import load_cues
cues = {c.id: c for c in load_cues()}
for cid in ('02-history', '06-bands'):
    for name in ('초등', '중고등', '일반', '전문가'):
        pts = cues[cid].points_for(name)
        print(cid, name, len(pts), pts)
"
```

Expected: 8줄(2큐×4수준) 전부 출력되고 예외 없음. 개수가 초등2/중고등3/일반3/전문가4와
맞는지 확인한다.

- [ ] **Step 4: 전체 테스트 회귀 확인**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 PASS(특히 `tests/test_stage_cues.py`의 기존 "모든 큐에 받아치기가
있다"류 정적 검증 — points를 추가해도 안 깨져야 한다).

- [ ] **Step 5: 커밋**

```bash
git add data/cues.yaml
git commit -m "content(cues): 02-history·06-bands 파일럿 큐에 points 저작"
```

---

### Task 9: 사전생성 실행 + 사람 검수 + 시뮬레이터 통합 검증

**Files:** 없음(운영 단계) — `data/mc_lines.yaml`이 갱신된다.

- [ ] **Step 1: LLM 서버를 띄운다**(안 떠 있으면)

Run: `curl -s -m 2 localhost:8080/health -o /dev/null -w "%{http_code}\n"` — 200이
아니면 `./reachy.sh serve`.

- [ ] **Step 2: 사전생성을 돌린다**

Run: `.venv/bin/python scripts/pregen_mc_lines.py 초등 중고등 일반 전문가`

(19큐 전체를 돌지만 이미 있는 캐시 항목은 `_append_entry`가 건드리지 않으므로 새로
만드는 것은 `02-history`·`06-bands`의 다리 대사뿐이다.)

Expected: `02-history/일반/pt1 다리대사: ...`류 줄이 큐당 (포인트수-1)개씩(첫 포인트는
다리 대사가 없다 — 오프닝 뒤 곧장 도슨트로 넘어간다) 찍힌다. 끝에 "N개를 새로 만들어
이어 붙였다" 안내가 뜬다.

- [ ] **Step 3: 사람이 읽는다**

`data/mc_lines.yaml`에서 방금 추가된 `02-history`·`06-bands` 항목을 읽는다 — 톤이
"오, 그런데 이런 것도 있다면서요?" 류 예시와 비슷한지, 다음 포인트 내용과 자연스럽게
이어지는지 확인한다. 어색하면 그 줄만 손으로 고친다.

- [ ] **Step 4: 시뮬레이터로 실제 왕복을 확인한다**

```bash
./reachy.sh sim &
./reachy.sh start --sim
```

콘솔에서 `g 02-history` → `s`(또는 `r`)로 재생. 사회자 오프닝 → 도슨트 포인트1 →
사회자 다리대사 → 도슨트 포인트2 → 도슨트 포인트3 → 사회자 받아치기 순으로 도는지 귀로
확인한다. `g 06-bands`도 같은 방식으로 확인한다.

- [ ] **Step 5: 최종 회귀 확인**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 전부 PASS.

- [ ] **Step 6: 커밋**

```bash
git add data/mc_lines.yaml
git commit -m "content(mc_lines): 02-history·06-bands 다리 대사 사전생성 결과"
```

---

## 다음 큐로 확장하려면

Task 8의 패턴(기존 `docent_brief`를 소주제로 쪼개기)을 나머지 17개 큐 × 4수준에 반복하고,
매번 Task 9의 Step 2~5(사전생성 → 검수 → 시뮬 확인 → 회귀)를 돌린다. 코드는 이 계획에서
전부 끝났으므로 이후는 순수 저작·검수 작업이다.
