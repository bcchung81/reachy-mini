# 기동 통합과 운영 모드 — 1단계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `./reachy.sh start --sim | --robot` 한 줄로 전부 띄우고, 무대감독·대시보드에 운영 모드(팟캐스트/단독) 상태와 화면 토글을 둔다(단독은 사회자 로봇이 지원을 알릴 때만 켜진다).

**Architecture:** 감독(`stage/director.py`)에 `mode` 상태와 로봇 능력(`caps`, hello 의 선택 필드)을 더하고, 명령 `m <모드>` 를 콘솔·대시보드 공통 경로(`console.dispatch`)로 받는다. 페이지는 스냅샷의 `mode`/`solo_available` 로 토글을 그린다. 기동은 `reachy.sh` 에 `start` 하위 명령을 더해 추론 3종·로봇(시뮬 2대/실기 2대)·감독을 순서대로 띄우고 `--dry-run` 으로 계획만 찍는다. 세 태스크는 파일이 겹치지 않아 병렬로 간다.

**Tech Stack:** Python 3.12(`.venv`), websockets 15 sync, 순수 HTML/JS 페이지, bash **3.2**(macOS 기본).

**Spec:** `docs/superpowers/specs/2026-09-21-launch-and-modes-design.md` (1단계 절)

## Global Constraints

- 인터프리터는 `.venv/bin/python` 하나. 워크트리에서는 절대경로 `/Users/bcchung81/workspace/reachy-mini/.venv/bin/python`. 테스트: `PYTHONDONTWRITEBYTECODE=1 <python> -m pytest tests/ -q`(기존 `cgi` DeprecationWarning 하나만 허용).
- 락 순서는 `Director._lock` → `_gen_lock` 한 방향. `Director._lock` 은 재진입이 안 된다 — 락 안에서 공개 메서드(`abort()` 등)를 다시 부르지 않는다. 감독이 락을 쥔 채 부르는 자리(경고 콜백·`_send`)에서 감독 상태를 읽거나 블로킹하지 않는다.
- 로봇 앱(`apps/`)·`stage/protocol.py` 의 **로봇이 보내는 형식**은 바꾸지 않는다(hello 의 `caps` 는 감독이 **받을 수만** 있게 넓힌다 — 없으면 빈 목록). `harness/` 수정 금지.
- 폴백·거절·실패는 반드시 경고를 남긴다(소리 내서 실패). 주석은 "왜". 기존 주석은 지우지 말고 갱신, 사라진 제약은 취소선.
- 페이지: 외부 리소스 금지, 서버 문자열은 `textContent` 로만(`innerHTML`·`outerHTML`·`insertAdjacentHTML`·`document.write` 금지). 헤더 56px, 창 높이 맞춤(페이지 세로 스크롤 없음), 1024/1280/1440px 에서 헤더 겹침 없음 유지.
- bash 는 **3.2 호환**: 연관 배열·`;;&`·`${v,,}`·`mapfile`·`readarray` 금지.
- 새 테스트는 먼저 실패를 본다(TDD). 함정 다섯 금지: ① `match=` 가 tmp_path 에 걸림 ② 서로 다른 두 인자에 같은 값 ③ 기본값과 같은 값으로 단언 ④ 부정 단언만 ⑤ 기대값을 피검 코드에서 import. 뮤테이션은 `PYTHONDONTWRITEBYTECODE=1`, 되돌림은 바이트 단위.
- 커밋은 한국어 `type(scope): 요약`, 끝에 `Co-Authored-By: Claude <모델명> <noreply@anthropic.com>`.

## 계약 (Task 1 ↔ Task 2, 병렬 구현의 기준)

- 명령: `{"cmd": "m podcast"}` / `{"cmd": "m solo"}` (콘솔도 `m podcast` / `m solo`).
- hello: `modes: ["podcast", "solo"]` (이 순서).
- snapshot: `mode` = `"podcast"` | `"solo"`, `solo_available` = bool(사회자가 붙어 있고 그 hello 의 `caps` 에 `"solo"` 가 있다).
- 감독 경고 문구(페이지 로그에 그대로 뜬다):
  - 모르는 이름: `모르는 모드다: '<이름>' — 바꾸지 않는다(고를 수 있는 것: podcast, solo)`
  - 이미 그 모드: `이미 <이름> 모드다 — 바꿀 것이 없다`
  - 사회자 없음: `단독 모드를 켤 수 없다 — 사회자 로봇이 붙어 있지 않다`
  - caps 없음: `단독 모드를 켤 수 없다 — 사회자 로봇 앱이 단독 모드를 아직 모른다(로봇 앱 업데이트 뒤에 켜진다)`
  - 전환: `모드를 <옛> → <새> 로 바꿨다`
  - 단독에서 진행 명령: `단독 모드에서는 팟캐스트 진행(<무엇>)을 하지 않는다 — 먼저 m podcast`

## 판정 (스펙 보완)

- 스펙 1-2 의 `REACHY_MODE` 는 1단계에서 **넣지 않는다** — 사용자 결정이 "처음 모드 = 팟캐스트" 이고, 1단계에서는 단독을 켤 로봇이 없어 처음부터 단독이면 아무것도 안 하는 감독이 된다. 4단계에서 필요하면 넣는다. (스펙에서 해당 줄을 취소선 처리 — Task 3 의 문서 단계에서)

## 파일 구조

| 파일 | 태스크 | 책임 |
|---|---|---|
| `stage/director.py` | 1 | `mode`·`caps` 상태, `set_mode`, `mode_names`, 진행 명령 가드, 스냅샷 키 |
| `stage/server.py` | 1 | hello 의 `caps` 검증·전달 |
| `stage/console.py` | 1 | `m <모드>` 명령, HELP |
| `stage/dashboard.py` | 1 | hello `modes` |
| `tests/test_stage_director.py`, `test_stage_console.py`, `test_stage_server.py`, `test_dashboard.py`, `test_dashboard_e2e.py` | 1 | |
| `stage/dashboard_page.html`, `tests/test_dashboard_page.py` | 2 | 헤더 모드 토글, 단독일 때 진행 UI 비활성·안내 |
| `reachy.sh`, `tests/test_reachy_start.py`(새), `scripts/sim2.sh`(삭제), `CLAUDE.md`, `docs/two-robot-setup.md`, `docs/two-robot-offline-test.md`, 스펙 | 3 | `start` 하위 명령·`--dry-run`·정리, 문서 |

---

### Task 1: 감독의 운영 모드 (opus)

**Files:**
- Modify: `stage/director.py`, `stage/server.py`, `stage/console.py`, `stage/dashboard.py`
- Test: `tests/test_stage_director.py`, `tests/test_stage_console.py`, `tests/test_stage_server.py`, `tests/test_dashboard.py`, `tests/test_dashboard_e2e.py`

**Interfaces:**
- Consumes: 기존 `Director.on_hello(role, unit_id, version)`, `Director.on_connect/on_disconnect`, `Director.abort()`, `Director.snapshot()`, `console.dispatch(director, cmd, out)`, `DashboardServer.handler` 의 hello.
- Produces:
  - `Director.on_hello(role, unit_id, version, caps: list[str] | None = None) -> None` — `caps` 를 역할별로 기억(끊기면 지운다).
  - `Director.set_mode(name: str) -> None`, `Director.mode_names() -> list[str]` (`["podcast", "solo"]`), `Director.mode` 속성(읽기 전용 문자열).
  - `snapshot()` 에 `mode`, `solo_available` 추가.
  - `console.dispatch` 가 `m <모드>` 처리, HELP 에 `m <모드>  운영 모드 바꾸기(podcast/solo)` 줄.
  - DashboardServer hello 에 `"modes": director.mode_names()`.

- [ ] **Step 1: 실패하는 테스트 (감독)** — `tests/test_stage_director.py` 끝에. 기존 파일의 감독 생성 헬퍼(가짜 generate·송신 기록·`_now` 주입)를 그대로 쓴다. 기대값은 전부 리터럴.

```python
def test_모드는_팟캐스트로_시작하고_고를_수_있는_것은_둘이다():
    d, _ = _감독()                      # 기존 헬퍼 이름에 맞춘다
    assert d.snapshot()["mode"] == "podcast"
    assert d.mode_names() == ["podcast", "solo"]


def test_사회자가_단독을_알리지_않으면_단독을_거절한다():
    d, h = _감독()
    d.on_connect("mc"); d.on_hello("mc", None, "1.9.0")          # caps 없음(지금 앱)
    d.set_mode("solo")
    assert d.snapshot()["mode"] == "podcast"
    assert d.snapshot()["solo_available"] is False
    assert "단독 모드를 켤 수 없다 — 사회자 로봇 앱이 단독 모드를 아직 모른다(로봇 앱 업데이트 뒤에 켜진다)" in h.warned


def test_사회자가_없으면_단독을_거절한다():
    d, h = _감독()
    d.on_connect("docent"); d.on_hello("docent", None, "1.9.0", caps=["solo"])
    d.set_mode("solo")
    assert d.snapshot()["mode"] == "podcast"
    assert "단독 모드를 켤 수 없다 — 사회자 로봇이 붙어 있지 않다" in h.warned


def test_사회자가_단독을_알리면_전환하고_말하던_것을_멈춘다():
    d, h = _감독()
    for r in ("mc", "docent"):
        d.on_connect(r)
    d.on_hello("mc", None, "2.0.0", caps=["solo"])
    d.start()                                             # 사회자가 말하는 중
    assert d.snapshot()["state"] == "mc_speaking"
    assert d.snapshot()["solo_available"] is True
    d.set_mode("solo")
    s = d.snapshot()
    assert (s["mode"], s["state"]) == ("solo", "idle")
    assert "모드를 podcast → solo 로 바꿨다" in h.warned
    assert ("mc", "abort") in [(r, t) for r, t, _ in h.sent]   # 기존 송신 기록 형식에 맞춘다


def test_단독에서는_진행_명령을_거절한다():
    d, h = _감독()
    d.on_connect("mc"); d.on_hello("mc", None, "2.0.0", caps=["solo"])
    d.set_mode("solo")
    d.start(); d.next(); d.goto("c2")
    s = d.snapshot()
    assert (s["mode"], s["state"], s["cue_index"]) == ("solo", "idle", 0)
    assert "단독 모드에서는 팟캐스트 진행(시작)을 하지 않는다 — 먼저 m podcast" in h.warned
    assert "단독 모드에서는 팟캐스트 진행(다음)을 하지 않는다 — 먼저 m podcast" in h.warned
    assert "단독 모드에서는 팟캐스트 진행(이동)을 하지 않는다 — 먼저 m podcast" in h.warned


def test_모르는_모드와_같은_모드는_경고만():
    d, h = _감독()
    d.set_mode("karaoke"); d.set_mode("podcast")
    assert d.snapshot()["mode"] == "podcast"
    assert "모르는 모드다: 'karaoke' — 바꾸지 않는다(고를 수 있는 것: podcast, solo)" in h.warned
    assert "이미 podcast 모드다 — 바꿀 것이 없다" in h.warned


def test_단독에서_팟캐스트로_돌아오면_다시_진행할_수_있다():
    d, h = _감독()
    for r in ("mc", "docent"):
        d.on_connect(r)
    d.on_hello("mc", None, "2.0.0", caps=["solo"])
    d.set_mode("solo"); d.set_mode("podcast")
    d.start()
    assert (d.snapshot()["mode"], d.snapshot()["state"]) == ("podcast", "mc_speaking")


def test_사회자가_끊기면_단독_가능이_꺼진다():
    d, _ = _감독()
    d.on_connect("mc"); d.on_hello("mc", None, "2.0.0", caps=["solo"])
    assert d.snapshot()["solo_available"] is True
    d.on_disconnect("mc")
    assert d.snapshot()["solo_available"] is False
```

(헬퍼 이름·경고 기록 필드(`warned`)·송신 기록 모양은 **파일의 기존 테스트에 맞춘다**. 2대 큐시트가 필요하면 기존 `_시트3()` 등을 쓴다. `goto("c2")` 는 그 시트의 두 번째 큐 id 로.)

- [ ] **Step 2: 실패 확인** — `PYTHONDONTWRITEBYTECODE=1 <python> -m pytest tests/test_stage_director.py -q -k "모드 or 단독"` → FAIL(`set_mode`/`mode_names` 없음, `on_hello` 가 `caps` 를 모름).

- [ ] **Step 3: 구현 (감독)** — `stage/director.py`:
  - 모듈 상수 `MODES = ("podcast", "solo")`.
  - `__init__`: `self._mode = "podcast"`, `self._caps: dict[str, set[str]] = {}`.
  - `on_hello(..., caps=None)`: 락 안에서 `self._caps[role] = set(caps or ())` — **기존 unit 검증 반환 경로보다 앞에** 둔다(검증이 일찍 `return` 해도 caps 는 기억해야 한다; 단 `UnitMismatch` 로 거절되는 로봇은 기억하지 않는다 — 검증 뒤에 두되 `expected is None`/`unit_id is None` 의 조기 반환 갈래 **모두**에서 기억되게 구조를 잡는다).
  - `on_disconnect`: `self._caps.pop(role, None)`.
  - `mode` 프로퍼티(락 불필요 — 문자열 대입은 원자적; 스냅샷은 락 안에서 읽는다), `mode_names()` → `list(MODES)`.
  - `set_mode(name)`: 락 안에서 위 계약의 경고 문구 그대로 갈래. 전환이 받아들여지면 **락 안에서** 중단 내부 구현을 호출한다 — 공개 `abort()` 를 다시 부르지 않는다(재진입 불가). 기존 `abort()` 본문이 락을 잡은 뒤 하는 일을 `_abort_locked()` 로 빼고 `abort()` 는 `with self._lock: self._abort_locked()` 로 둔다(이미 그 모양이면 그대로 쓴다). 로봇에게 `mode` 를 보내는 자리에는 주석만: `# 4단계: 여기서 로봇에게 mode 를 보낸다(앱이 단독 루프로 전환)`.
  - 진행 가드: `start()`·`next()`·`previous()`·`goto()` 맨 앞(락 안, 기존 검사보다 먼저)에서 `self._mode == "solo"` 면 경고(`시작`/`다음`/`이전`/`이동`) 후 반환. 관람객의 "다음"(`on_heard`)·침묵 자동 진행(`tick`)은 단독에서 LISTENING 이 될 일이 없으므로 따로 가드하지 않는다 — 주석으로 그 이유를 남긴다.
  - `snapshot()` 에 `"mode": self._mode`, `"solo_available": "mc" in self._connected and "solo" in self._caps.get("mc", ())`.

- [ ] **Step 4: 실패하는 테스트 (서버·콘솔·대시보드·e2e)**
  - `tests/test_stage_server.py`: 가짜 로봇이 `hello` 에 `caps: ["solo"]` 를 보내면 감독 스냅샷 `solo_available is True`(사회자 역할로), `caps: "solo"`(문자열·리스트 아님) 이면 경고 `[mc] hello 의 caps 가 문자열 목록이 아니다 — 무시한다: 'solo'` 가 찍히고 `solo_available is False`. 기존 실소켓 테스트 방식을 따른다.
  - `tests/test_stage_console.py`: `dispatch(d, "m solo", out)` 가 가짜 감독의 `set_mode("solo")` 를 부른다(기록 리터럴), HELP 에 `m <모드>` 줄이 있다.
  - `tests/test_dashboard.py`: hello 에 `"modes": ["podcast", "solo"]` — 가짜 감독에 `mode_names()` 를 더한다.
  - `tests/test_dashboard_e2e.py`: 진짜 서버·감독 + `caps: ["solo"]` 로 hello 한 가짜 사회자 → 페이지 소켓이 `{"cmd":"m solo"}` → 경고 `모드를 podcast → solo 로 바꿨다` 이벤트와 이어지는 스냅샷 `mode == "solo"`.

- [ ] **Step 5: 구현 (서버·콘솔·대시보드)**
  - `stage/server.py` hello 처리: `caps = msg.get("caps")`; `None` 이면 `None`, 문자열 목록이면 그대로, 그 밖이면 위 경고 후 `None`. `self.director.on_hello(role, msg.get("unit_id"), msg.get("version", ""), caps)`.
  - `stage/console.py`: `elif cmd.startswith("m "): director.set_mode(cmd[2:].strip())` + 주석(검증·문구는 `set_mode` 한 곳), HELP 한 줄.
  - `stage/dashboard.py` hello: `"modes": self._director.mode_names()`.

- [ ] **Step 6: 통과·전체·뮤테이션** — 전체 스위트. 뮤테이션(각각 해당 테스트가 실패해야 하고 되돌린다): ① `solo_available` 식에서 `"mc" in self._connected and` 삭제 ② 전환 시 `_abort_locked()` 호출 삭제 ③ `start()` 의 단독 가드 삭제 ④ server 의 caps 전달을 `None` 으로 고정 ⑤ `on_disconnect` 의 `caps.pop` 삭제.

- [ ] **Step 7: 커밋** — `feat(stage): 감독에 운영 모드(팟캐스트/단독)와 로봇 능력 알림(caps)을 둔다`

---

### Task 2: 대시보드 헤더 모드 토글 (sonnet)

**Files:**
- Modify: `stage/dashboard_page.html`
- Test: `tests/test_dashboard_page.py`

**Interfaces:**
- Consumes (계약): hello `modes`, snapshot `mode`·`solo_available`, 명령 `m <모드>`, 감독 경고 문구.
- Produces: 요소 id — `mode`(컨테이너), 버튼은 컨테이너 안에 `data-mode="podcast"|"solo"`, `mode-note`(단독 불가 안내), `solo-banner`(단독일 때 안내).

- [ ] **Step 1: 실패하는 정적 테스트** — `tests/test_dashboard_page.py` 에:

```python
def test_모드_토글이_있고_m_명령을_보낸다():
    src = _src()
    for i in ("mode", "mode-note", "solo-banner"):
        assert f'id="{i}"' in src, i
    assert '"m "' in src          # sendCmd("m " + name)
    assert "solo_available" in src
    assert "msg.modes" in src
```
각 줄을 잠시 지워 실패를 보고 되돌린다.

- [ ] **Step 2: 구현**
  - 헤더 **왼쪽**(제목 옆)에 [팟캐스트][단독] 세그먼트 — `hello.modes` 로 짓는다(재접속마다 비우고 다시, 중복 없이). 라벨: `podcast`→"팟캐스트", `solo`→"단독". `modes` 가 없으면(옛 서버) 토글을 숨긴다(던지지 않는다).
  - 스냅샷마다: 적용된 모드 버튼은 채운 색. 단독 버튼은 `solo_available` 이 거짓이고 지금 모드가 solo 가 아니면 `disabled` + `mode-note` 에 "단독: 로봇 앱 업데이트 후" (textContent). 참이면 note 를 비운다.
  - 클릭 → `sendCmd("m " + name)`(지금 모드와 같으면 보내지 않는다). 확인 단계 없음 — 전환이 발화를 멈추므로, **팟캐스트 → 단독** 클릭만 기존 두 단계 이동과 같은 확인 바 패턴을 쓸지 검토: 쓰지 않는다(판정: 단독 버튼은 로봇이 지원할 때만 켜지고, 되돌리기가 한 번의 클릭이다 — 결정 2 의 "실수 한 번이 진행을 깨지 않게" 를 해치는 정도가 런다운 이동보다 작다). 주석에 이 이유를 남긴다.
  - `mode === "solo"` 일 때: 런다운 행·진행 버튼(`btn-prev/restart/next/start`)과 확인 바를 `disabled`, `btn-abort` 는 살린다. `solo-banner` 에 "단독 모드 — 사회자 로봇이 관람객 질문에 답합니다" 를 보인다(팟캐스트면 숨긴다).
  - 헤더 56px·창 높이 맞춤·1024px 겹침 없음 유지(모드 토글 폭 때문에 cue-label/topic 이 더 줄어드는 것은 괜찮다 — 이미 말줄임).
- [ ] **Step 3: node 스모크(스크래치, 저장소 밖)** — hello(modes)→2버튼, snapshot(mode=podcast, solo_available=false)→단독 disabled+note, true→enabled, 클릭→`{"cmd":"m solo"}`, snapshot(mode=solo)→진행 버튼 disabled·abort enabled·banner 보임, 재접속 두 번→버튼 2개 그대로, modes 없는 hello→던지지 않음. `node --check`.
- [ ] **Step 4: 전체 스위트, 커밋** — `feat(stage): 대시보드 헤더에 운영 모드 토글(팟캐스트/단독)을 단다`

---

### Task 3: `./reachy.sh start --sim | --robot` (opus)

**Files:**
- Modify: `reachy.sh`, `CLAUDE.md`(명령 블록), `docs/two-robot-setup.md`, `docs/two-robot-offline-test.md`, `docs/superpowers/specs/2026-09-21-launch-and-modes-design.md`(REACHY_MODE 줄 취소선)
- Create: `tests/test_reachy_start.py`
- Delete: `scripts/sim2.sh`

**Interfaces:**
- Consumes: 기존 `start_llm_stt`, `start_tts`, `BIND_HOST`, `lan_ip`, `robot_reachable`, `robot_fix`, `robot_sync_config`, `rget`/`rpost`/`rssh`, `robot_status`, `scripts/warmup.py`, `scripts/sim2.sh` 의 시뮬 기동 절차(출력 장치 분리 `REACHY_MC_AUDIO_OUT`/`REACHY_DOCENT_AUDIO_OUT` 와 경고 포함).
- Produces: `./reachy.sh start --sim|--robot [--dry-run]`. dry-run 출력 줄 형식(테스트 계약, 줄마다 `PLAN ` 접두):
  - `--sim`: `PLAN infer bind=127.0.0.1 ports=8080,8090,8099` / `PLAN robot role=mc target=sim port=8000` / `PLAN robot role=docent target=sim port=8001` / `PLAN director bind=127.0.0.1 port=8777 dashboard=http://127.0.0.1:8778/`
  - `--robot`: `PLAN infer bind=0.0.0.0 ports=8080,8090,8099` / `PLAN robot role=mc target=<REACHY_MC_HOST 또는 192.168.0.4>` / `PLAN robot role=docent target=<REACHY_DOCENT_HOST 또는 192.168.0.5>` / `PLAN director bind=0.0.0.0 port=8777 dashboard=http://127.0.0.1:8778/`

- [ ] **Step 1: 실패하는 테스트** — `tests/test_reachy_start.py`:

```python
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _run(*args, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(["bash", str(ROOT / "reachy.sh"), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=30)


def _plan(stdout):
    return [l for l in stdout.splitlines() if l.startswith("PLAN ")]


def test_start_sim_dry_run_은_시뮬_두_대와_루프백_계획을_찍는다():
    r = _run("start", "--sim", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert _plan(r.stdout) == [
        "PLAN infer bind=127.0.0.1 ports=8080,8090,8099",
        "PLAN robot role=mc target=sim port=8000",
        "PLAN robot role=docent target=sim port=8001",
        "PLAN director bind=127.0.0.1 port=8777 dashboard=http://127.0.0.1:8778/",
    ]


def test_start_robot_dry_run_은_환경변수의_로봇_주소를_쓴다():
    """기본값(192.168.0.4/.5)이 아닌 주소로 본다 — 함정 ③."""
    r = _run("start", "--robot", "--dry-run",
             env_extra={"REACHY_MC_HOST": "10.9.8.21", "REACHY_DOCENT_HOST": "10.9.8.22"})
    assert r.returncode == 0, r.stderr
    assert _plan(r.stdout) == [
        "PLAN infer bind=0.0.0.0 ports=8080,8090,8099",
        "PLAN robot role=mc target=10.9.8.21",
        "PLAN robot role=docent target=10.9.8.22",
        "PLAN director bind=0.0.0.0 port=8777 dashboard=http://127.0.0.1:8778/",
    ]


def test_start_는_대상_없이_부르면_쓰임새를_찍고_2로_끝난다():
    r = _run("start", "--dry-run")
    assert r.returncode == 2
    assert "--sim" in (r.stdout + r.stderr) and "--robot" in (r.stdout + r.stderr)
    assert _plan(r.stdout) == []


def test_start_는_두_대상을_함께_받지_않는다():
    r = _run("start", "--sim", "--robot", "--dry-run")
    assert r.returncode == 2
    assert _plan(r.stdout) == []


def test_dry_run_은_아무것도_띄우지_않는다(tmp_path):
    """`PY` 를 없는 인터프리터로 바꿔도 dry-run 은 성공해야 한다 — 파이썬·네트워크를 안 건드린다는 증거."""
    r = _run("start", "--sim", "--dry-run", env_extra={"REACHY_PY": str(tmp_path / "없음")})
    assert r.returncode == 0, r.stderr
```
(마지막 테스트가 성립하도록 `reachy.sh` 의 `PY` 를 `PY="${REACHY_PY:-.venv/bin/python}"` 로 바꾼다 — 기존 동작은 그대로.)

- [ ] **Step 2: 실패 확인** — `... -m pytest tests/test_reachy_start.py -q` → FAIL(모르는 명령 `start`).

- [ ] **Step 3: 구현** — `reachy.sh`:
  - 머리 사용법(주석 2~23행, `usage()` 가 `sed -n '2,23p'` 로 찍는다)에 **맨 위** 한 줄 `./reachy.sh start --sim|--robot   시연 전부 기동(추론 3종·로봇 2대·무대감독+대시보드). --dry-run 은 계획만` 을 넣고, `usage()` 의 줄 범위를 새 길이에 맞춘다(범위를 하드코딩하지 말고 첫 빈 주석줄까지 찍게 바꾸면 더 좋다 — 선택).
  - `run_start()`: 인자 파싱(`--sim`/`--robot` 정확히 하나, `--dry-run` 선택). 잘못되면 쓰임새 + `exit 2`.
  - dry-run: 위 PLAN 줄만 찍고 `exit 0`(파이썬·ping·curl·lsof 호출 금지).
  - 실제 기동 `--sim`: ① 포트 8000/8001/8777/8778 이 비어 있는지(`lsof -nP -iTCP:<p> -sTCP:LISTEN`) — 쥔 게 있으면 무엇인지 찍고 `exit 1` ② `BIND_HOST=127.0.0.1` 로 `start_llm_stt`·`start_tts`(없는 것만), 실패면 로그 안내 후 `exit 1` ③ 예열 ④ 모의 데몬 2대(`--mockup-sim --headless --no-media --fastapi-port <p> --robot-name <역할>`, 로그 `.demo-logs/start-daemon-<역할>.log`, pid 기록) + 대기 ⑤ 앱 2대(`REACHY_ROLE`·`REACHY_DAEMON_PORT`·`REACHY_DIRECTOR_URL=ws://127.0.0.1:8777`·출력 장치 분리 변수, 로그 `.demo-logs/start-app-<역할>.log`) ⑥ 대시보드가 뜨면 브라우저를 여는 백그라운드 대기자(`open` 또는 `xdg-open` 이 있을 때만, 없으면 주소만) ⑦ `REACHY_DIRECTOR_HOST=127.0.0.1` 로 `"$PY" -m stage` 를 **전면**에서 실행(콘솔 키가 산다 — `exec` 하지 않는다, 아래 trap 이 돌아야 한다). `trap` 으로 EXIT/INT/TERM 에 **이 실행이 띄운 데몬·앱만** 내린다(추론 3종은 남긴다 — 안내 한 줄).
  - 실제 기동 `--robot`: 기존 `robot_up` 의 로봇별 단계(0 백엔드 상태/복구, 2 config 동기화, 3 로봇→맥 도달, 4 기상, 6 앱 기동, 모터 재확인)를 `robot_bringup_one <host> <role> <mac_ip>` 로 떼고(`ROBOT_HOST`·`ROBOT_API` 를 그 안에서 지역적으로 바꾼다 — 끝나면 원래 값으로), `robot_up` 은 그 함수를 한 번 부르게 고쳐 **기존 `robot up` 동작을 그대로 유지**한다. `run_start --robot` 은 추론 3종(LAN)·예열을 한 번 하고, 사회자·도슨트 각각 `robot_bringup_one` — **닿지 않는 로봇은 경고하고 건너뛴다**. 감독은 `REACHY_DIRECTOR_HOST=0.0.0.0` 전면, 대시보드는 기본(127.0.0.1). trap 은 두 로봇의 **앱만** 정지(`/api/apps/stop-current-app` — 기존 `robot_down` 이 쓰는 호출을 그대로).
  - `case` 분기에 `start) run_start "$@" ;;`.
  - `scripts/sim2.sh` 삭제(참조 없음 — `grep -rn sim2 --include=*.md --include=*.sh --include=*.py .` 로 확인, `.claude/`·`.venv/` 제외).
  - bash 3.2 호환(연관 배열 금지 — 역할/호스트 쌍은 위치 인자로).

- [ ] **Step 4: 통과·정적 검사** — 새 테스트 통과, `bash -n reachy.sh`, `shellcheck reachy.sh` 가 있으면 새로 생긴 경고가 없는지. **실제 스택은 띄우지 않는다**(컨트롤러가 최종 검증에서 돌린다).

- [ ] **Step 5: 문서**
  - `CLAUDE.md` 명령 블록 맨 위에 `./reachy.sh start --sim   # 시연 전부(추론 3종·시뮬 2대·무대감독+대시보드)` 와 `--robot` 줄. 나머지 줄은 둔다.
  - `docs/two-robot-offline-test.md`, `docs/two-robot-setup.md`: 여러 단계로 띄우던 절차 앞에 `./reachy.sh start --robot` 한 줄(로봇 주소 변수 `REACHY_MC_HOST`/`REACHY_DOCENT_HOST`)을 두고, 기존 수동 절차는 "부품별로 띄울 때" 로 남긴다.
  - 스펙 1-2 의 `REACHY_MODE` 줄을 취소선 + "(1단계에서 넣지 않음 — 계획 판정)".

- [ ] **Step 6: 전체 스위트, 커밋** — `feat(reachy): start --sim|--robot 한 줄로 시연 전부를 띄운다` (문서는 같은 커밋 또는 `docs(…)` 로 분리)

---

## 최종 검증 (컨트롤러가 직접)

1. 전체 테스트.
2. `./reachy.sh start --sim` 을 실제로 돌려: 포트 8080/8090/8099/8000/8001/8777/8778, 로봇 2대 접속, 브라우저 대시보드에 모드 토글(단독 비활성 + 안내), `m solo` 거절 경고가 로그에, 팟캐스트 `s` 로 시연 시작, 콘솔 `q` 로 끝내면 데몬·앱이 내려가고 추론 3종은 남는다.
3. 1024/1280/1440px 에서 헤더 겹침 없음(모드 토글 + 수준 버튼 + 연결 배지).
