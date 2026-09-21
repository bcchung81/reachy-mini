# 무대감독 컨트롤러 대시보드 (시안 B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m stage` 가 도는 동안 브라우저(기본 `http://127.0.0.1:8778/`)에서 두 로봇의 상태·발화 문구·런다운·이벤트 로그를 보고, 시작·이전·다시·다음·즉시 중단·큐 이동을 할 수 있게 한다. 카메라는 자리표시자.

**Architecture:** 무대감독 프로세스 안에 이벤트 허브(`DashboardHub`)를 두고, 로봇 서버(`StageServer`)의 송수신과 경고를 허브에 흘린다. 별도 포트의 `websockets` sync 서버(`DashboardServer`)가 페이지와 `/ws` 를 서비스하고, 허브 이벤트 + 락 밖에서 읽은 감독 스냅샷을 페이지로 보낸다. 버튼 명령은 콘솔과 같은 `console.dispatch` 로 실행한다.

**Tech Stack:** Python 3.12(`.venv`), `websockets` 15 sync API(이미 의존성), 순수 HTML/CSS/JS(빌드·외부 리소스 없음), pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-stage-dashboard-design.md` (시안 사본 `docs/design/dashboard-B.dc.html`)

## Global Constraints

- 인터프리터는 저장소의 `.venv/bin/python` 하나뿐이다. **워크트리에서 일할 때는 절대경로** `/Users/bcchung81/workspace/reachy-mini/.venv/bin/python` 을 쓴다. 테스트: `PYTHONDONTWRITEBYTECODE=1 <python> -m pytest tests/ -q` (저장소 루트 또는 워크트리 루트에서).
- 락 순서는 `Director._lock` → `_gen_lock` 한 방향뿐이다. **감독이 락을 쥔 채 부르는 자리(`StageServer._send`, 경고 콜백)에서 감독 상태를 읽거나 블로킹하지 않는다.** `DashboardHub.publish` 는 deque 추가와 `put_nowait` 만 한다.
- 대시보드 기본 바인드는 `127.0.0.1:8778`. `REACHY_DASHBOARD_HOST` / `REACHY_DASHBOARD_PORT` 로만 바꾼다.
- 페이지는 **외부 리소스를 하나도 부르지 않는다**(시연장 오프라인). 폰트는 시스템 스택.
- 페이지는 서버에서 온 문자열(관람객 STT, 경고, 대사)을 **`textContent` 로만** 넣는다. `innerHTML` 금지.
- 로봇 앱(`apps/`)과 로봇 프로토콜(`stage/protocol.py`)은 바꾸지 않는다. `harness/` 수정 금지.
- **폴백·실패는 반드시 경고를 남긴다.** 대시보드가 실패해도 감독·콘솔은 계속 돈다.
- 주석에는 **왜** 그렇게 짰는지. 기존 주석은 지우지 말고 갱신, 사라진 제약은 취소선.
- 새 테스트는 먼저 실패를 본다(TDD). 뮤테이션은 `PYTHONDONTWRITEBYTECODE=1`.
- 테스트 함정 다섯을 재발시키지 않는다: ① `match=` 가 tmp_path(테스트명)에 걸림 ② 서로 다른 두 인자에 같은 값 ③ 기본값과 같은 값으로 단언 ④ 부정 단언만 ⑤ 기대값을 피검 코드에서 import.
- 커밋 메시지는 한국어 `type(scope): 요약`, 끝에 `Co-Authored-By: Claude <작성 모델명> <noreply@anthropic.com>`.

## 병렬 실행 계획

| 차수 | 태스크 | 모델 | 건드리는 파일(서로 겹치지 않는다) |
|---|---|---|---|
| 1차(동시) | Task 1 감독 조회·이동 | opus | `stage/cues.py`, `stage/director.py`, `stage/console.py`, `tests/test_stage_cues.py`, `tests/test_stage_director.py`, `tests/test_stage_console.py` |
| 1차(동시) | Task 2 이벤트 허브 | sonnet | `stage/dashboard_hub.py`, `tests/test_dashboard_hub.py` |
| 1차(동시) | Task 3 서버 탭 | sonnet | `stage/server.py`, `tests/test_stage_server.py` |
| 1차(동시) | Task 4 페이지 | sonnet | `stage/dashboard_page.html`, `tests/test_dashboard_page.py` |
| 2차 | Task 5 대시보드 서버 | opus | `stage/dashboard.py`, `tests/test_dashboard.py` |
| 3차 | Task 6 기동 배선 + 문서 | sonnet | `stage/__main__.py`, `tests/test_stage_main.py`, `docs/two-robot-offline-test.md` |

1차 네 태스크는 **각자 워크트리**에서 커밋하고, 컨트롤러가 리뷰 후 `voice-chat-mvp` 로 체리픽한다.

---

### Task 1: 감독 조회·이동 — `CueSheet.find/seek/cues`, `Director.snapshot/cue_list/goto`, `console.dispatch` + `g`

**모델:** opus (감독 락·불변식을 건드린다)

**Files:**
- Modify: `stage/cues.py` (`class CueSheet`, 283~322행 근처)
- Modify: `stage/director.py` (공개 메서드 영역 — `start`/`next`/`previous` 옆)
- Modify: `stage/console.py`
- Test: `tests/test_stage_cues.py`, `tests/test_stage_director.py`, `tests/test_stage_console.py`

**Interfaces:**
- Produces:
  - `CueSheet.cues() -> tuple[Cue, ...]`, `CueSheet.find(cue_id: str) -> int | None`, `CueSheet.seek(index: int) -> Cue` (범위 밖 `IndexError`, 커서 불변)
  - `Director.snapshot() -> dict` — 키: `cue_index, cue_id, cue_count, state, speaking_role, question_wait_s, question_wait_total_s, connected, solo_role, rejected, level` (값 형식은 스펙 표)
  - `Director.cue_list() -> list[dict]` — `[{"id": str, "topic": str}]`
  - `Director.goto(cue_id: str) -> None` — 발화 중이면 `TurnError`(커서 불변), 모르는 id 면 경고만
  - `console.dispatch(director, cmd: str, out) -> None` — 기존 `_dispatch` 를 공개로. `"g <큐id>"` → `abort()` 후 `goto(<큐id>)`
- Task 5 가 `snapshot()`·`cue_list()`·`console.dispatch` 를 소비한다.

- [ ] **Step 1: 실패하는 테스트**

`tests/test_stage_cues.py` 끝에 (`Cue` 위치 인자는 `Cue(id, topic, mc, docent_brief, gaze)`):

```python
def _시트3():
    return CueSheet([
        Cue("a", "가", "m", "d", "partner"),
        Cue("b", "나", "m", "d", "partner"),
        Cue("c", "다", "m", "d", "partner"),
    ])


def test_큐_id_로_위치를_찾는다():
    s = _시트3()
    assert s.find("c") == 2
    assert s.find("없음") is None


def test_seek_는_커서를_옮기고_그_큐를_준다():
    s = _시트3()
    assert s.seek(2).id == "c"
    assert s.index == 2 and s.current().id == "c"


def test_seek_범위_밖이면_소리_내서_실패하고_커서는_그대로다():
    s = _시트3()
    s.seek(1)
    with pytest.raises(IndexError):
        s.seek(3)
    assert s.index == 1


def test_cues_는_전체를_순서대로_준다():
    assert [c.id for c in _시트3().cues()] == ["a", "b", "c"]
```

`tests/test_stage_director.py` 끝에 (`TurnError` 는 `from stage.machine import TurnError`):

```python
def test_스냅샷은_현재_큐와_상태와_수준을_준다():
    h = Harness(level_name="초등")          # 기본값 "일반" 이 아닌 값 — 함정 3
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.start()
    s = h.d.snapshot()
    assert (s["cue_id"], s["cue_index"], s["cue_count"]) == ("c1", 0, 2)
    assert (s["state"], s["speaking_role"]) == ("mc_speaking", "mc")
    assert s["connected"] == ["docent", "mc"] and s["solo_role"] is None
    assert s["level"] == "초등"
    assert s["question_wait_s"] is None      # 말하는 중에는 침묵 기한이 없다
    assert s["rejected"] == []


def test_스냅샷의_침묵_남은_시간은_듣는_중에만_센다():
    """`test_침묵이_한도를_넘으면_다음_큐로_간다` 의 준비 과정을 그대로 따라
    LISTENING + 침묵 기한이 걸린 상태를 만든 뒤, 시계를 3초 민다.
    기대값은 리터럴(8.0 - 3.0) — QUESTION_WAIT_S 를 import 하지 않는다(함정 5)."""
    # (그 테스트의 셋업을 복사해 LISTENING 까지 간다)
    ...
    h.clock.t += 3.0
    s = h.d.snapshot()
    assert s["state"] == "listening"
    assert s["question_wait_s"] == pytest.approx(5.0)
    assert s["question_wait_total_s"] == pytest.approx(8.0)


def test_큐_목록은_id_와_주제를_순서대로_준다():
    h = Harness()
    assert h.d.cue_list() == [{"id": "c1", "topic": "첫째"}, {"id": "c2", "topic": "둘째"}]


def test_goto_는_그_큐의_여는_대사부터_다시_시작한다():
    h = Harness()
    h.d.start()
    h.d.abort()
    h.clear()
    h.d.goto("c2")
    assert h.says() == [("mc", "사회자 둘째 대사")]
    assert h.d.snapshot()["cue_id"] == "c2"


def test_goto_는_말하는_중이면_커서를_옮기기_전에_거절한다():
    h = Harness()
    h.d.start()                              # 사회자가 c1 을 말하는 중
    with pytest.raises(TurnError):
        h.d.goto("c2")
    assert h.d.snapshot()["cue_id"] == "c1"  # 커서가 안 움직였다


def test_goto_모르는_큐는_경고하고_아무것도_하지_않는다():
    h = Harness()
    h.d.start()
    h.d.abort()
    h.clear()
    h.warnings.clear()
    h.d.goto("없는큐")
    assert h.says() == []
    assert any("모르는 큐" in w for w in h.warnings), h.warnings
```

(`test_스냅샷의_침묵_남은_시간은_듣는_중에만_센다` 의 `...` 는 **그대로 두지 않는다** — 같은 파일의 `test_침묵이_한도를_넘으면_다음_큐로_간다` 를 읽고 LISTENING + `_question_deadline` 이 걸리는 지점까지의 셋업을 복사해 채운다. 시계는 `h.clock.t` 다.)

`tests/test_stage_console.py` 끝에:

```python
def test_g_는_먼저_멈추고_그_큐로_간다():
    import stage.console as console
    calls = []

    class 가짜감독:
        def abort(self):
            calls.append("abort")

        def goto(self, cue_id):
            calls.append(("goto", cue_id))

    console.dispatch(가짜감독(), "g 07-maritime", out=lambda m: None)
    assert calls == ["abort", ("goto", "07-maritime")]


def test_dispatch_는_콘솔과_같은_n_경로다():
    import stage.console as console
    calls = []

    class 가짜감독:
        def abort(self):
            calls.append("abort")

        def next(self):
            calls.append("next")

    console.dispatch(가짜감독(), "n", out=lambda m: None)
    assert calls == ["abort", "next"]
```

- [ ] **Step 2: 실패 확인** — `PYTHONDONTWRITEBYTECODE=1 <python> -m pytest tests/test_stage_cues.py tests/test_stage_director.py tests/test_stage_console.py -q` → 새 테스트들이 `AttributeError`(find/seek/cues/snapshot/cue_list/goto/dispatch 없음)로 실패.

- [ ] **Step 3: 구현**

`stage/cues.py` `CueSheet` 에:

```python
    def cues(self) -> tuple[Cue, ...]:
        """전체 큐 — 대시보드 런다운이 목록을 그린다. 바깥에서 못 바꾸게 튜플로 준다."""
        return tuple(self._cues)

    def find(self, cue_id: str) -> int | None:
        """큐 id 의 위치. 없으면 None — 호출자가 경고한다."""
        for i, c in enumerate(self._cues):
            if c.id == cue_id:
                return i
        return None

    def seek(self, index: int) -> Cue:
        """커서를 옮긴다. 범위 밖이면 IndexError 이고 **커서는 그대로다** — 조용히
        끝에 붙이면 엉뚱한 섹션이 시작돼도 아무도 모른다."""
        if not 0 <= index < len(self._cues):
            raise IndexError(f"큐 위치 {index} 는 0..{len(self._cues) - 1} 밖이다")
        self._i = index
        return self._cues[index]
```

`stage/director.py` 공개 메서드 영역(`previous` 뒤)에:

```python
    def goto(self, cue_id: str) -> None:
        """지정한 큐로 가서 처음부터 진행한다 — 대시보드 런다운의 이동(수동 오버라이드).

        콘솔 `g` 가 `n`·`p`·`r` 처럼 먼저 `abort()` 한다. **커서를 옮기기 전에
        거절한다**: `previous()` 는 커서를 먼저 옮긴 뒤 `_begin_cue` 에서 거절당해
        커서만 움직인 채 남을 수 있는데, 이 메서드에는 그 틈을 만들지 않는다.
        """
        with self._lock:
            if self._machine.state in SPEAKING:
                raise TurnError(
                    f"{self._machine.speaking_role} 가 아직 말하는 중이다 — 먼저 a 로 멈춘다"
                )
            i = self._sheet.find(cue_id)
            if i is None:
                self._warn(f"모르는 큐다: {cue_id!r} — 이동하지 않는다")
                return
            self._begin_cue(self._sheet.seek(i))

    def cue_list(self) -> list[dict]:
        """런다운용 큐 목록. 큐시트는 기동 뒤 바뀌지 않으므로 락이 필요 없다."""
        return [{"id": c.id, "topic": c.topic} for c in self._sheet.cues()]

    def snapshot(self) -> dict:
        """대시보드가 그릴 현재 상태 — **락을 잠깐 쥐고** 한 시점의 값을 모은다.

        ⚠️ 감독이 락을 쥔 채 부르는 자리(`StageServer._send`, 경고 콜백)에서
        부르면 교착이다(`threading.Lock` 은 재진입이 안 된다). 대시보드 서버의
        펌프 스레드가 락 밖에서 주기적으로 부른다.

        침묵 남은 시간은 **LISTENING 일 때만** 준다 — `abort()` 는 발화 기한만
        끄므로 멈춘 뒤에도 `_question_deadline` 이 남을 수 있는데, 그 값은
        `tick()` 이 LISTENING 에서만 보므로 실제로는 안 걸린 기한이다.
        """
        with self._lock:
            wait = None
            if (
                self._question_deadline is not None
                and self._machine.state is State.LISTENING
            ):
                wait = max(0.0, self._question_deadline - self._now())
            return {
                "cue_index": self._sheet.index,
                "cue_id": self._sheet.current().id,
                "cue_count": len(self._sheet.cues()),
                "state": self._machine.state.value,
                "speaking_role": self._machine.speaking_role,
                "question_wait_s": wait,
                "question_wait_total_s": QUESTION_WAIT_S,
                "connected": sorted(self._connected),
                "solo_role": self.solo_role,
                "rejected": sorted(self._rejected),
                "level": self._level_name,
            }
```

`stage/console.py`: `_dispatch` 를 `dispatch` 로 이름을 바꾸고(`run_console` 호출부도), 맨 앞에 docstring 한 줄("콘솔 명령 하나 — **대시보드도 이 함수를 부른다**, 명령 경로를 하나로 둔다")과 `g` 갈래를 더한다. `HELP` 에 `g <큐id>  그 큐로 이동` 을 더한다:

```python
    elif cmd.startswith("g "):
        # 대시보드 런다운의 이동. `n`·`p`·`r` 과 같은 모양으로 먼저 멈춘다.
        director.abort()
        director.goto(cmd[2:].strip())
```

- [ ] **Step 4: 통과 확인** — 같은 명령 → PASS. 전체 스위트도 통과.
- [ ] **Step 5: 뮤테이션** — ① `goto` 의 SPEAKING 검사를 지운다 → `…커서를_옮기기_전에_거절한다` 실패 ② `snapshot` 의 LISTENING 조건을 지운다 → 침묵 테스트 또는 첫 스냅샷 테스트 실패 여부 확인(안 잡히면 abort 뒤 스냅샷 단언을 더한다) ③ `dispatch` 의 `g` 갈래에서 `abort()` 를 지운다 → `test_g_는_먼저_멈추고_그_큐로_간다` 실패. 각각 되돌리고 `git diff` 확인.
- [ ] **Step 6: 커밋** — `feat(stage): 감독 상태 스냅샷과 큐 이동(g) — 대시보드가 쓸 조회·명령 경로`

---

### Task 2: 이벤트 허브 — `stage/dashboard_hub.py`

**모델:** sonnet

**Files:** Create `stage/dashboard_hub.py`, Test `tests/test_dashboard_hub.py`

**Interfaces (Produces):**
- `class DashboardHub(now: Callable[[], float] = time.time, history: int = 200)`
  - `publish(kind: str, **fields) -> None` — 이벤트 `{"kind": kind, "t": now(), **fields}`. **절대 블로킹·예외 없음.**
  - `subscribe(maxsize: int = 1000) -> Subscription`, `unsubscribe(sub) -> None`, `history() -> list[dict]`
- `class Subscription` — `.queue: queue.Queue[dict]`, `.dropped: int`
- `tee(*sinks) -> Callable[[str], None]` — 경고를 여러 곳으로. 한 곳이 터져도 나머지는 받고, 끝에 첫 예외를 다시 던진다.

- [ ] **Step 1: 실패하는 테스트** — `tests/test_dashboard_hub.py`:

```python
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.dashboard_hub import DashboardHub, tee


class 시계:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_발행한_이벤트는_시각과_함께_이력에_남는다():
    h = DashboardHub(now=시계())
    h.publish("warn", text="경고 하나")
    assert h.history() == [{"kind": "warn", "t": 100.0, "text": "경고 하나"}]


def test_이력은_상한을_넘으면_앞에서_버린다():
    h = DashboardHub(now=시계(), history=3)
    for i in range(5):
        h.publish("n", i=i)
    assert [e["i"] for e in h.history()] == [2, 3, 4]


def test_구독자는_구독한_뒤의_이벤트만_받는다():
    h = DashboardHub(now=시계())
    h.publish("before")
    sub = h.subscribe()
    h.publish("after", x=1)
    assert sub.queue.get_nowait() == {"kind": "after", "t": 100.0, "x": 1}
    assert sub.queue.empty()


def test_구독을_끊으면_더_받지_않는다():
    h = DashboardHub(now=시계())
    sub = h.subscribe()
    h.unsubscribe(sub)
    h.publish("x")
    assert sub.queue.empty()


def test_구독자_큐가_넘치면_버리고_세되_예외는_없다():
    """publish 는 감독이 락을 쥔 채 부르는 자리에서 불린다 — 블로킹·예외 금지."""
    h = DashboardHub(now=시계())
    sub = h.subscribe(maxsize=2)
    for i in range(3):
        h.publish("n", i=i)
    assert sub.dropped == 1
    assert [sub.queue.get_nowait()["i"] for _ in range(2)] == [0, 1]


def test_tee_는_모든_곳에_보내고_터진_곳이_있어도_나머지는_받는다():
    got_a, got_c = [], []

    def 터짐(msg):
        raise ValueError("닫힌 stdout")

    w = tee(got_a.append, 터짐, got_c.append)
    with pytest.raises(ValueError):
        w("경고")
    assert got_a == ["경고"] and got_c == ["경고"]
```

- [ ] **Step 2: 실패 확인** (`ModuleNotFoundError`)
- [ ] **Step 3: 구현** — `stage/dashboard_hub.py`:

```python
"""대시보드 이벤트 허브 — 감독 쪽에서 일어난 일을 모아 구독자에게 나눠 준다.

**쌓기만 하고 되부르지 않는다.** `publish` 는 감독이 `Director._lock` 을 쥔 채
부르는 자리(`StageServer._send`, 경고 콜백)에서 불린다. 여기서 감독 상태를 읽거나
네트워크를 기다리면 교착이거나 시연 진행이 멈춘다 — 그래서 deque 에 넣고 구독자
큐에 `put_nowait` 만 한다. 감독 상태는 대시보드 서버가 락 밖에서 따로 읽는다.
"""

import collections
import queue
import threading
import time
from typing import Callable

HISTORY = 200
SUB_QUEUE = 1000


class Subscription:
    def __init__(self, maxsize: int) -> None:
        self.queue: queue.Queue[dict] = queue.Queue(maxsize=maxsize)
        # 넘쳐서 버린 개수. 페이지는 다음 스냅샷으로 다시 맞춰지지만, 이벤트
        # (대사·경고)가 빠진 사실은 셀 수 있어야 한다 — 조용히 잃지 않는다.
        self.dropped = 0


class DashboardHub:
    def __init__(self, now: Callable[[], float] = time.time, history: int = HISTORY) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._history: collections.deque[dict] = collections.deque(maxlen=history)
        self._subs: list[Subscription] = []

    def publish(self, kind: str, **fields) -> None:
        ev = {"kind": kind, "t": self._now(), **fields}
        with self._lock:
            self._history.append(ev)
            subs = list(self._subs)
        for s in subs:
            try:
                s.queue.put_nowait(ev)
            except queue.Full:
                s.dropped += 1

    def subscribe(self, maxsize: int = SUB_QUEUE) -> Subscription:
        s = Subscription(maxsize)
        with self._lock:
            self._subs.append(s)
        return s

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def history(self) -> list[dict]:
        with self._lock:
            return list(self._history)


def tee(*sinks: Callable[[str], None]) -> Callable[[str], None]:
    """경고를 여러 곳에 동시에. **한 곳이 터져도 나머지는 받는다** — 대시보드가
    망가져도 터미널 경고는 살아야 하고, 그 반대도 마찬가지다. 터진 예외는 삼키지
    않고 끝에 다시 던진다(기존 `print` 경고와 같은 실패 모양)."""

    def warn(msg: str) -> None:
        first: Exception | None = None
        for sink in sinks:
            try:
                sink(msg)
            except Exception as exc:  # noqa: BLE001
                first = first or exc
        if first is not None:
            raise first

    return warn
```

- [ ] **Step 4: 통과 확인**, **Step 5: 뮤테이션** — `put_nowait` 를 `put` 으로 바꾸면 넘침 테스트가 멈추거나 실패하는지(`timeout` 걸린 pytest 로) 확인, `tee` 의 try 를 지우면 tee 테스트 실패. 되돌리고 확인.
- [ ] **Step 6: 커밋** — `feat(stage): 대시보드 이벤트 허브 — 쌓기만 하고 되부르지 않는다`

---

### Task 3: 로봇 서버 탭 — `StageServer(hub=None)`

**모델:** sonnet

**Files:** Modify `stage/server.py`, Test `tests/test_stage_server.py`

**Interfaces:**
- Consumes: 허브는 **덕 타이핑** — `publish(kind: str, **fields)` 만 있으면 된다(Task 2 의 `DashboardHub` 와 같은 모양). 테스트는 기록용 가짜를 쓴다.
- Produces: `StageServer.__init__(..., hub=None)`. 이벤트:
  - `_send` 에서 `ws.send` **성공 뒤**: `publish("sent", role=role, type=cmd.type, fields=dict(cmd.fields))`
  - 접속 등록 직후(`self.director.on_connect(role)` 바로 앞): `publish("connect", role=role, version=msg.get("version"))`
  - `finally` 에서 `is_current` 일 때: `publish("disconnect", role=role)`
  - `_dispatch`: 검증을 통과해 감독에게 넘기기 **직전** — heard: `publish("recv", role=role, type="heard", fields={"text": text})`; speaking_started/ended: `fields={"cue_id": cue_id, "seq": seq}`; error: `fields={"where": ..., "detail": ...}`
- 허브가 `None` 이면 아무것도 안 한다(기존 테스트·호출부 그대로).

- [ ] **Step 1: 실패하는 테스트** — `tests/test_stage_server.py` 에 fixture 와 테스트를 더한다. 기존 `server` fixture 를 본떠 `hub` 인자를 받는 `server_hub` fixture 를 만든다:

```python
class 기록허브:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish(self, kind, **fields):
        self.events.append((kind, fields))

    def kinds(self):
        return [k for k, _ in self.events]


@pytest.fixture
def server_hub():
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner")])
    hub = 기록허브()
    s = StageServer(sheet, generate=lambda role, brief, history: "도슨트 대사",
                    warn=lambda m: None, hub=hub)
    s.hub = hub
    from websockets.sync.server import serve as ws_serve
    srv = ws_serve(s.handler, "127.0.0.1", 0)
    s.port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield s
    srv.shutdown()
    t.join(timeout=2)


def test_허브에_접속과_보낸_지시가_남는다(server_hub):
    with connect(url_of(server_hub)) as ws:
        hello(ws, "mc")                       # 접속 직후 mic 재동기화 한 통
        assert ("connect", {"role": "mc", "version": "1.9.0"}) in server_hub.hub.events
        sent = [f for k, f in server_hub.hub.events if k == "sent"]
        assert sent and sent[-1]["role"] == "mc" and sent[-1]["type"] == "mic"
        assert sent[-1]["fields"] == {"open": False}


def test_허브에_받은_관람객_발화와_발화_종료가_남는다(server_hub):
    """발화 흐름은 이 파일의 기존 종단 테스트(시작 → 사회자 say → ended)를 따라 만든다.
    heard 는 사회자가 LISTENING 일 때만 감독에게 가지만, **허브에는 검증을 통과한
    순간 남는다**(감독이 버려도 운영자는 무엇이 들렸는지 봐야 한다)."""
    ...  # 기존 테스트의 셋업으로 사회자 say 를 받고 ended 를 보낸 뒤
    recv_ = [f for k, f in server_hub.hub.events if k == "recv"]
    assert {"role": "mc", "type": "speaking_ended", "fields": {"cue_id": "c1", "seq": ...}} in recv_


def test_허브에_끊김이_남는다(server_hub):
    with connect(url_of(server_hub)) as ws:
        hello(ws, "mc")
    for _ in range(50):
        if "disconnect" in server_hub.hub.kinds():
            break
        time.sleep(0.02)
    assert ("disconnect", {"role": "mc"}) in server_hub.hub.events


def test_허브가_없어도_지금처럼_돈다(server):
    """`hub=None`(기본값) — 기존 fixture 그대로. 한 번 붙었다 떨어져도 예외가 없다."""
    with connect(url_of(server)) as ws:
        hello(ws, "mc")
```

(`...` 두 곳은 **그대로 두지 않는다** — 같은 파일에서 사회자가 say 를 받고 `ended()` 를 보내는 기존 테스트를 찾아 그 셋업을 복사하고, `seq` 는 그 연결이 마지막으로 받은 say 의 seq(`_LAST_SAY_SEQ`)로 채운다. heard 도 한 건 넣을 수 있으면 넣는다.)

- [ ] **Step 2: 실패 확인** (`unexpected keyword argument 'hub'`)
- [ ] **Step 3: 구현** — `__init__` 에 `hub=None` 인자와 `self._hub = hub`, 헬퍼:

```python
    def _publish(self, kind: str, **fields) -> None:
        """대시보드 허브로 흘린다. **감독이 락을 쥔 채 부르는 자리**(`_send`)에서도
        불리므로 허브는 쌓기만 한다(`stage/dashboard_hub.py`). 허브가 없으면 아무것도 안 한다."""
        if self._hub is not None:
            self._hub.publish(kind, **fields)
```

그리고 Interfaces 의 네 자리에 한 줄씩. `_send` 의 `publish` 는 `ws.send(...)` 가 **성공한 뒤** try 블록 안에 둔다(실패하면 기존 경고가 허브로도 간다 — Task 6 의 tee).

- [ ] **Step 4: 통과 확인**, **Step 5: 뮤테이션** — `_send` 의 publish 를 지우면 첫 테스트 실패, `finally` 의 publish 를 지우면 끊김 테스트 실패. 되돌리고 확인.
- [ ] **Step 6: 커밋** — `feat(stage): 로봇 서버의 송수신·접속을 대시보드 허브로 흘린다`

---

### Task 4: 대시보드 페이지 — `stage/dashboard_page.html`

**모델:** sonnet

**Files:** Create `stage/dashboard_page.html`, Test `tests/test_dashboard_page.py`

**시각 기준:** `docs/design/dashboard-B.dc.html`(시안 B). 레이아웃·색·글자 크기를 그대로 옮기되 `.dc.html` 문법(`<x-dc>`, `{{ }}`, `<sc-for>`)은 쓰지 않는다 — 순수 HTML + `<style>` + `<script>` 한 파일. **외부 리소스 없음**: 폰트는 `-apple-system, "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif` / 고정폭 `ui-monospace, SFMono-Regular, Menlo, monospace`. 아이콘은 인라인 SVG.

**계약 (Task 5 서버가 보내는 메시지 — 스펙 표 그대로):**
- 접속: `new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws")`. 끊기면 2초마다 재접속하고 상단에 상태 표시.
- `hello` → 런다운을 `cues` 로 그리고, `history` 를 로그에 채우고, `snapshot` 을 반영.
- `snapshot` → 상단 큐 라벨(`CUE 07 / 19 · <topic>`), 수준, 각 모니터의 탤리(말하는 역할은 ON AIR 빨간 테두리, 아니면 STANDBY, 연결 안 됐으면 `OFFLINE`), 런다운 현재 줄, 자동 진행 바(`question_wait_s` 가 null 이면 "대기 전", 아니면 "침묵 N초 뒤 다음 큐로" + 진행 바 `(1 - wait/total)`).
- `sent` + `type === "say"` → 그 역할의 자막 칸에 `fields.text`. `sent` + `mic` → 그 역할 모니터에 `MIC ON/OFF`.
- 모든 이벤트 → 로그 한 줄(시각 `HH:MM:SS`, 최신이 아래, 최대 200줄, 자동 스크롤). `warn`·`command(ok:false)` 는 주황.
  - sent say: `say {role} {cue_id} seq={seq}` / sent mic: `mic {role} on|off` / sent abort: `abort {role}`
  - recv heard: `관람객> {text}` / speaking_started·ended: `[{role}] 발화 시작|종료 seq={seq}`
  - connect/disconnect: `[{role}] 붙었다|끊겼다` / warn: `{text}` / command: `명령 {cmd} — {ok ? "실행" : "거절됨"} {lines.join(" ")}`
- 버튼 → `ws.send(JSON.stringify({cmd}))`: 이전 `p`, 이 큐 다시 `r`, 다음 `n`, 처음부터 시작 `s`, 즉시 중단 `a`. 같은 키보드 단축키(P/R/N/S/A, 수정키 없을 때만).
- 런다운 줄 클릭 → **선택만** 하고 확인 바(`#goto-bar`)에 "07 타이타닉… 으로 이동" + "이 큐로 이동"(`#goto-confirm`) + "취소"(`#goto-cancel`). 확인하면 `{cmd: "g " + id}`. 현재 큐를 누르면 확인 바에 "이 큐 다시(r)" 를 권한다.
- 서버에서 온 문자열은 **전부 `textContent`**. `innerHTML` 을 쓰지 않는다(관람객 STT 가 그대로 온다).
- 카메라 칸: `[사회자 카메라 영상 — 실기 연결 후]` 자리표시자.

**필수 id**(정적 테스트가 본다): `conn`, `cue-label`, `level`, `mon-mc`, `mon-docent`, `tag-mc`, `tag-docent`, `cap-mc`, `cap-docent`, `rundown`, `goto-bar`, `goto-confirm`, `goto-cancel`, `btn-prev`, `btn-restart`, `btn-next`, `btn-start`, `btn-abort`, `auto-text`, `auto-bar`, `log`.

- [ ] **Step 1: 실패하는 정적 테스트** — `tests/test_dashboard_page.py`:

```python
import pathlib
import re

PAGE = pathlib.Path(__file__).parent.parent / "stage" / "dashboard_page.html"
IDS = ["conn", "cue-label", "level", "mon-mc", "mon-docent", "tag-mc", "tag-docent",
       "cap-mc", "cap-docent", "rundown", "goto-bar", "goto-confirm", "goto-cancel",
       "btn-prev", "btn-restart", "btn-next", "btn-start", "btn-abort",
       "auto-text", "auto-bar", "log"]


def _src():
    return PAGE.read_text(encoding="utf-8")


def test_필수_요소가_전부_있다():
    src = _src()
    missing = [i for i in IDS if f'id="{i}"' not in src]
    assert missing == []


def test_같은_호스트의_ws_로_붙는다():
    assert '"/ws"' in _src() or "'/ws'" in _src()


def test_외부_리소스를_부르지_않는다():
    """시연장은 인터넷이 없다 — 외부 폰트·스크립트 하나가 페이지를 멈춘다."""
    assert re.findall(r'(?:src|href)\s*=\s*["\']https?://', _src()) == []
    assert "fonts.googleapis" not in _src()


def test_innerHTML_을_쓰지_않는다():
    """관람객 STT·경고 문자열이 그대로 온다 — textContent 로만 넣는다."""
    assert "innerHTML" not in _src()


def test_콘솔과_같은_명령_문자열을_보낸다():
    src = _src()
    for c in ['"p"', '"r"', '"n"', '"s"', '"a"', '"g "']:
        assert c in src, c
```

- [ ] **Step 2: 실패 확인**, **Step 3: 페이지 작성**, **Step 4: 통과 확인**
- [ ] **Step 5: 브라우저 수동 확인(가능하면)** — `python3 -m http.server` 로는 `/ws` 가 없으니, 페이지를 파일로 열어 레이아웃만 본다(연결 끊김 표시가 떠야 정상). 스크린샷은 선택.
- [ ] **Step 6: 커밋** — `feat(stage): 대시보드 페이지 — 시안 B 를 오프라인 한 장으로`

---

### Task 5: 대시보드 서버 — `stage/dashboard.py`

**모델:** opus  **선행:** Task 1·2·4 가 `voice-chat-mvp` 에 들어와 있어야 한다.

**Files:** Create `stage/dashboard.py`, Test `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `DashboardHub`(Task 2), `Director.snapshot()/cue_list()`(Task 1), `console.dispatch`(Task 1), `stage/dashboard_page.html`(Task 4)
- Produces:
  - `DEFAULT_HOST = "127.0.0.1"`, `DEFAULT_PORT = 8778`, `SNAPSHOT_INTERVAL_S = 0.5`, `PAGE` (페이지 경로)
  - `class DashboardServer(hub, director, dispatch=console.dispatch, page=PAGE, interval=SNAPSHOT_INTERVAL_S, warn=print)` — `.process_request(connection, request)`, `.handler(ws)`
  - `start_dashboard(hub, director, host=DEFAULT_HOST, port=DEFAULT_PORT, warn=print) -> Server | None` — 포트가 막히면 경고하고 `None`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_dashboard.py`:

```python
import json
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from websockets.sync.client import connect
from websockets.sync.server import serve as ws_serve

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.dashboard import DashboardServer, start_dashboard
from stage.dashboard_hub import DashboardHub
from stage.machine import TurnError


class 가짜감독:
    def __init__(self):
        self.calls = []
        self.fail_next = False

    def snapshot(self):
        return {"cue_id": "07-maritime", "cue_index": 6, "cue_count": 19, "state": "listening"}

    def cue_list(self):
        return [{"id": "07-maritime", "topic": "타이타닉"}]

    def abort(self):
        self.calls.append("abort")

    def next(self):
        if self.fail_next:
            raise TurnError("사회자 가 아직 말하는 중이다")
        self.calls.append("next")

    def goto(self, cue_id):
        self.calls.append(("goto", cue_id))


@pytest.fixture
def dash(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>t</title>", encoding="utf-8")
    hub, d, warned = DashboardHub(), 가짜감독(), []
    ds = DashboardServer(hub, d, page=page, interval=0.05, warn=warned.append)
    srv = ws_serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield {"hub": hub, "d": d, "warned": warned, "port": port, "page": page}
    srv.shutdown()
    t.join(timeout=2)


def _recv_until(ws, kind, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        m = json.loads(ws.recv(timeout=timeout))
        if m["kind"] == kind:
            return m
    raise AssertionError(f"{kind} 가 안 왔다")


def test_루트는_페이지를_html_로_준다(dash):
    with urllib.request.urlopen(f"http://127.0.0.1:{dash['port']}/") as r:
        assert r.status == 200
        assert r.headers["Content-Type"].startswith("text/html")
        assert "<title>t</title>" in r.read().decode("utf-8")


def test_모르는_경로는_404(dash):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://127.0.0.1:{dash['port']}/nope")
    assert e.value.code == 404


def test_접속하면_큐목록_이력_스냅샷을_한번에_준다(dash):
    dash["hub"].publish("warn", text="먼저 난 경고")
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        m = json.loads(ws.recv(timeout=3))
        assert m["kind"] == "hello"
        assert m["cues"] == [{"id": "07-maritime", "topic": "타이타닉"}]
        assert m["snapshot"]["cue_id"] == "07-maritime"
        assert [e["text"] for e in m["history"] if e["kind"] == "warn"] == ["먼저 난 경고"]


def test_접속_뒤_이벤트와_주기_스냅샷이_온다(dash):
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))                 # hello
        dash["hub"].publish("sent", role="mc", type="say", fields={"text": "안녕"})
        assert _recv_until(ws, "sent")["fields"] == {"text": "안녕"}
        assert _recv_until(ws, "snapshot")["cue_index"] == 6


def test_버튼_명령은_콘솔과_같은_경로로_실행되고_결과가_모두에게_보인다(dash):
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "N"}))              # 대문자도 콘솔처럼 소문자로
        r = _recv_until(ws, "command")
        assert (r["cmd"], r["ok"]) == ("n", True)
        ws.send(json.dumps({"cmd": "g 07-maritime"}))
        _recv_until(ws, "command")
    assert dash["d"].calls == ["abort", "next", "abort", ("goto", "07-maritime")]


def test_거절된_명령은_ok_false_와_사유로_보인다(dash):
    dash["d"].fail_next = True
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "n"}))
        r = _recv_until(ws, "command")
        assert r["ok"] is False
        assert any("말하는 중" in line for line in r["lines"])


def test_규약에_안_맞는_명령은_경고하고_연결은_산다(dash):
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send("이건 JSON 이 아니다")
        ws.send(json.dumps({"cmd": "n"}))
        assert _recv_until(ws, "command")["ok"] is True
    assert any("규약" in w for w in dash["warned"]), dash["warned"]


def test_페이지_파일이_없으면_500_과_경고(dash):
    dash["page"].unlink()
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://127.0.0.1:{dash['port']}/")
    assert e.value.code == 500
    assert any("페이지" in w for w in dash["warned"])


def test_포트가_막혀_있으면_경고하고_None(dash):
    warned = []
    assert start_dashboard(DashboardHub(), 가짜감독(), "127.0.0.1", dash["port"], warn=warned.append) is None
    assert any("띄우지 못했다" in w for w in warned), warned


def test_기본_페이지_파일이_있다():
    from stage.dashboard import PAGE
    assert PAGE.exists()
```

- [ ] **Step 2: 실패 확인** (`ModuleNotFoundError: stage.dashboard`)
- [ ] **Step 3: 구현** — `stage/dashboard.py`:

```python
"""무대감독 대시보드 서버 — 시안 B(방송 조정실) 페이지 한 장과 실시간 소켓 하나.

설계: `docs/superpowers/specs/2026-09-21-stage-dashboard-design.md`.

- **로봇용 포트(8777)와 다른 포트**(기본 `127.0.0.1:8778`)다. 로봇 포트는 로봇 때문에
  `0.0.0.0` 이어야 하는데, 이 화면은 인증 없이 시연을 멈추고 건너뛸 수 있다 — 위험한
  쪽을 기본으로 두지 않는다. 망에 열려면 `REACHY_DASHBOARD_HOST`.
- **연결 하나에 보내는 스레드는 하나**(펌프)다. 명령 결과도 허브 이벤트로 흘려 같은
  펌프가 보낸다 — 두 스레드가 한 소켓에 동시에 쓰지 않게.
- 감독 상태(`Director.snapshot()`)는 펌프가 **락 밖에서** 읽는다. 허브 이벤트를 받는
  자리(감독이 락을 쥔 자리)에서 읽으면 교착이다.
- 경고는 **터미널로만** 낸다(`warn=print`). 허브로 되돌리면 이 서버가 자기 경고를 다시
  페이지로 흘리고, 그 경로가 망가졌을 때 끝없이 되돌아온다.
"""

import json
import pathlib
import queue
import threading
import time
from typing import Callable

from websockets.sync.server import serve as _ws_serve

from stage.console import dispatch as console_dispatch

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8778
SNAPSHOT_INTERVAL_S = 0.5
PAGE = pathlib.Path(__file__).with_name("dashboard_page.html")


class DashboardServer:
    def __init__(self, hub, director, dispatch: Callable = console_dispatch,
                 page: pathlib.Path = PAGE, interval: float = SNAPSHOT_INTERVAL_S,
                 warn: Callable[[str], None] = print) -> None:
        self._hub = hub
        self._director = director
        self._dispatch = dispatch
        self._page = page
        self._interval = interval
        self._warn = warn

    # ── HTTP ──────────────────────────────────────────────────────
    def process_request(self, connection, request):
        if request.path == "/ws":
            return None  # 웹소켓 핸드셰이크로 넘어간다
        if request.path in ("/", "/index.html"):
            try:
                body = self._page.read_text(encoding="utf-8")
            except OSError as exc:
                self._warn(f"대시보드 페이지를 못 읽었다({self._page}: {exc})")
                return connection.respond(500, "dashboard page missing")
            resp = connection.respond(200, body)
            # `respond` 는 text/plain 을 붙인다 — 브라우저가 HTML 로 그리게 바꾼다.
            del resp.headers["Content-Type"]
            resp.headers["Content-Type"] = "text/html; charset=utf-8"
            return resp
        return connection.respond(404, "not found")

    # ── WebSocket ─────────────────────────────────────────────────
    def handler(self, ws) -> None:
        sub = self._hub.subscribe()
        stop = threading.Event()
        try:
            ws.send(self._dumps({
                "kind": "hello",
                "cues": self._director.cue_list(),
                "history": self._hub.history(),
                "snapshot": self._safe_snapshot(),
            }))
            threading.Thread(target=self._pump, args=(ws, sub, stop), daemon=True).start()
            for raw in ws:
                self._on_command(raw)
        finally:
            stop.set()
            self._hub.unsubscribe(sub)

    def _pump(self, ws, sub, stop: threading.Event) -> None:
        """이 연결의 유일한 송신자. 이벤트는 오는 대로, 스냅샷은 `interval` 마다."""
        last = 0.0
        while not stop.is_set():
            try:
                ev = sub.queue.get(timeout=self._interval)
            except queue.Empty:
                ev = None
            try:
                if ev is not None:
                    ws.send(self._dumps(ev))
                if time.monotonic() - last >= self._interval:
                    snap = self._safe_snapshot()
                    if snap is not None:
                        ws.send(self._dumps({"kind": "snapshot", **snap}))
                    last = time.monotonic()
            except Exception:  # noqa: BLE001 — 연결이 닫혔다. 핸들러가 정리한다.
                return

    def _safe_snapshot(self) -> dict | None:
        try:
            return self._director.snapshot()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"대시보드 스냅샷 실패({type(exc).__name__}: {exc}) — 다음 주기에 다시 읽는다")
            return None

    def _on_command(self, raw) -> None:
        try:
            cmd = str(json.loads(raw)["cmd"]).strip().lower()
        except (ValueError, KeyError, TypeError):
            self._warn(f"대시보드 명령이 규약에 안 맞는다 — 버린다: {str(raw)[:80]!r}")
            return
        lines: list[str] = []
        ok = True
        try:
            self._dispatch(self._director, cmd, lines.append)
        except Exception as exc:  # noqa: BLE001 — 콘솔과 같다: 거절은 보여주고 계속
            ok = False
            lines.append(f"거절됨: {exc}")
        self._hub.publish("command", cmd=cmd, ok=ok, lines=lines)

    @staticmethod
    def _dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)


def start_dashboard(hub, director, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                    warn: Callable[[str], None] = print):
    """대시보드를 띄운다. **실패해도 감독·콘솔은 그대로 돈다** — 경고하고 None."""
    ds = DashboardServer(hub, director, warn=warn)
    try:
        srv = _ws_serve(ds.handler, host, port, process_request=ds.process_request)
    except OSError as exc:
        warn(f"대시보드를 띄우지 못했다({host}:{port} — {exc}) — 감독과 콘솔은 그대로 돈다")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    warn(f"대시보드 — http://{host}:{port}/")
    return srv
```

- [ ] **Step 4: 통과 확인**, **Step 5: 뮤테이션** — ① Content-Type 교체를 지우면 루트 테스트 실패 ② `_on_command` 의 `.lower()` 를 지우면 대문자 명령 테스트 실패 ③ `start_dashboard` 의 OSError 처리를 지우면 포트 테스트 실패. 되돌리고 확인.
- [ ] **Step 6: 커밋** — `feat(stage): 대시보드 서버 — 페이지·실시간 소켓·콘솔과 같은 명령 경로`

---

### Task 6: 기동 배선 + 문서

**모델:** sonnet  **선행:** Task 3·5 가 들어와 있어야 한다.

**Files:** Modify `stage/__main__.py`, `tests/test_stage_main.py`, `docs/two-robot-offline-test.md`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_stage_main.py` 끝에. `main()` 이 무거운 것(로봇 포트 바인드, 콘솔)을 부르기 전에 멈추게 가짜를 끼운다:

```python
def test_main_은_허브를_서버에_넘기고_환경변수_주소로_대시보드를_띄운다(monkeypatch):
    """REACHY_DASHBOARD_HOST/PORT 가 그대로 닿는지 — 기본값(127.0.0.1:8778)이
    아닌 값으로 본다(함정 3)."""
    monkeypatch.setenv("REACHY_DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setenv("REACHY_DASHBOARD_PORT", "9911")
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    seen = {}

    class 멈춤(Exception):
        pass

    class 가짜서버:
        def __init__(self, *a, **kw):
            seen["hub"] = kw.get("hub")
            self.director = object()

        def serve(self, host, port):
            class S:
                def serve_forever(self): pass
                def shutdown(self): pass
            return S()

        def tick_forever(self, *a): pass

    def 가짜대시보드(hub, director, host, port, warn):
        seen.update(dash_hub=hub, host=host, port=port)
        raise 멈춤()

    monkeypatch.setattr(stage_main, "build_generate", lambda level: (lambda r, b, h: "x"))
    monkeypatch.setattr(stage_main, "StageServer", 가짜서버)
    monkeypatch.setattr(stage_main, "start_dashboard", 가짜대시보드)
    with pytest.raises(멈춤):
        stage_main.main()
    assert seen["hub"] is not None and seen["dash_hub"] is seen["hub"]
    assert (seen["host"], seen["port"]) == ("0.0.0.0", 9911)
```

(`main()` 의 순서상 `start_dashboard` 가 `run_console` 보다 앞이어야 이 테스트가 멈춘다 — 구현을 그 순서로 둔다.)

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — `stage/__main__.py`:
  - 머리 docstring 의 환경변수 목록에 `REACHY_DASHBOARD_HOST  기본 127.0.0.1 (망에 열려면 0.0.0.0 — 전용 공유기에서만)`, `REACHY_DASHBOARD_PORT  기본 8778` 추가
  - import: `from stage.dashboard import DEFAULT_HOST as DASH_HOST, DEFAULT_PORT as DASH_PORT, start_dashboard`, `from stage.dashboard_hub import DashboardHub, tee`
  - `main()` 에서 서버를 만들기 전에 `hub = DashboardHub()` 와 `warn = tee(lambda m: print(m, flush=True), lambda m: hub.publish("warn", text=m))`, `StageServer(..., warn=warn, hub=hub)`. 주석: 경고가 터미널과 대시보드 양쪽으로 가는 이유, 허브는 쌓기만 한다는 것.
  - `srv = server.serve(host, port)` 와 그 스레드 기동 뒤, `run_console` **앞에**: 
    ```python
    dash = start_dashboard(
        hub, server.director,
        os.environ.get("REACHY_DASHBOARD_HOST", DASH_HOST),
        int(os.environ.get("REACHY_DASHBOARD_PORT", str(DASH_PORT))),
        warn=lambda m: print(m, flush=True),
    )
    ```
    `finally` 에서 `if dash is not None: dash.shutdown()`.
- [ ] **Step 4: 통과 확인**(전체 스위트)
- [ ] **Step 5: 문서** — `docs/two-robot-offline-test.md` ⑥(무대감독 기동)에 한 단락: 기동하면 `대시보드 — http://127.0.0.1:8778/` 이 찍힌다, 노트북 브라우저로 연다, 다른 기기(태블릿)에서 열려면 `REACHY_DASHBOARD_HOST=0.0.0.0` 으로 기동(전용 공유기에서만 — 인증 없는 제어 화면), 콘솔 키는 그대로 산다.
- [ ] **Step 6: 커밋** — `feat(stage): 무대감독 기동 때 대시보드를 함께 띄운다`

---

## 최종 검증 (컨트롤러가 직접)

1. 전체 테스트 통과.
2. 시뮬 2대(mockup-sim) + 추론 서버 + `python -m stage` 를 띄우고 **실제 브라우저로** `http://127.0.0.1:8778/` 을 연다:
   - 두 로봇 `붙었다` 가 로그에, 탤리가 STANDBY
   - "처음부터 시작" → 사회자 탤리 ON AIR, 자막에 여는 대사, 로그에 `say mc 01-intro …`
   - 도슨트 해설 중 도슨트 탤리, 자막 갱신
   - 런다운에서 03 선택 → 확인 바 → 이동 → 03 여는 대사
   - 즉시 중단 → 탤리 모두 STANDBY, 로그에 `명령 a — 실행`
   - 대시보드 새로고침 → 이력이 다시 채워진다
3. 콘솔 `n` 도 여전히 먹는다.
