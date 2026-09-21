# 팟캐스트형 대담 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사회자 대사를 생성으로 바꾸고, 관람객 수준(초등/중고등/일반/전문가)에 따라 분량과 깊이가 달라지게 하며, 섹션마다 질의응답을 열고 침묵이면 자동 진행한다.

**Architecture:** 전부 무대감독(`stage/`, 노트북)의 변경이다. 로봇 앱·와이어 규약·`TurnMachine` 불변식은 건드리지 않는다. 여는 대사는 시연 전 스크립트로 사전 생성해 캐시하고(지연 0, 사람이 검토 가능), 받아치기만 런타임에 예비·실제 두 벌을 만들어 먼저 준비된 쪽을 쓴다. 생성 슬롯은 하나에서 **이름을 가진 역할별 슬롯**으로 나눈다.

**Tech Stack:** Python 3.12 (`.venv/bin/python`), pytest, PyYAML, `websockets` sync API.

**Spec:** `docs/superpowers/specs/2026-09-20-podcast-adlib-design.md`

## Global Constraints

- 인터프리터는 `.venv/bin/python` 하나뿐이다. 테스트는 `.venv/bin/python -m pytest`.
- **로봇 앱(`apps/voice_chat/`)의 동작을 바꾸지 않는다.** 단 `llm.py` 의 `max_tokens` 하드코딩 제거는 예외이며, 기본값이 현재 동작과 같아야 한다.
- 와이어 규약(`say`/`mic`/`gaze`/`abort` ↔ `heard`/`speaking_started`/`speaking_ended`/`error`)을 바꾸지 않는다.
- `TurnMachine` 의 상태 4개와 불변식 2개(발화 중 마이크 금지, 동시 발화 금지)를 바꾸지 않는다.
- **폴백으로 물러날 때는 반드시 경고를 남긴다.** 조용히 성능이 떨어진 채 도는 것이 가장 나쁘다.
- 설정은 사다리로 읽는다: 환경변수 → 설정파일 → 기본값. 감독 쪽 설정은 `os.environ` 으로 충분하다(감독은 셸에서 뜬다).
- 수준 이름은 정확히 `초등`, `중고등`, `일반`, `전문가` 넷이다.
- `QUESTION_WAIT_S = 8.0`.
- 분량 목표(수준별 문장 수 / 목표 글자): 초등 2~3 / 70~120, 중고등 3~4 / 120~200, 일반 4~5 / 180~280, 전문가 5~7 / 260~400.
- 락 순서는 언제나 `Director._lock` → `_gen_lock` 한 방향뿐이다. 락을 놓고 기다렸으면 깨어나서 **상태와 세대 토큰을 다시 본다.**
- 커밋 메시지는 한국어, 본문에 "왜" 를 적는다. 끝에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Structure

| 파일 | 책임 |
|---|---|
| `stage/levels.py` (신규) | 수준 프로필 로딩·검증, 환경변수에서 수준 읽기 |
| `data/levels.yaml` (신규) | 수준 프로필 4개 |
| `data/personas/{mc,docent}.md` (신규) | 역할 페르소나 본문 |
| `stage/prompts.py` (신규) | `[공통 + 역할 + 수준]` 조립 |
| `stage/cues.py` | `Cue` 에 `briefs`·`facts`·`topic` 추가, 검증 |
| `stage/director.py` | 역할별 생성 슬롯, 받아치기 이중 생성, 침묵 타이머 |
| `stage/__main__.py` | 역할별 시스템 프롬프트로 `generate` 배선, 기동 로그에 수준 |
| `scripts/pregen_mc_lines.py` (신규) | 여는 대사 사전 생성 → 캐시 |
| `data/mc_lines.yaml` (생성물) | 사전 생성 캐시 |
| `apps/voice_chat/voice_chat/llm.py` | `max_tokens` 하드코딩 제거 |

---

### Task 1: 분량 규정 — 프롬프트·`max_tokens`·미달 경고

발화가 짧은 원인 셋 중 **수준과 무관한 부분**만 먼저 고친다. 목표 범위는 아직 큐시트의 "N문장 이내" 를 쓴다(수준 프로필은 Task 3 에서 생긴다).

**Files:**
- Modify: `apps/voice_chat/voice_chat/llm.py:28-41` (생성자), `:79` (`max_tokens`)
- Modify: `stage/__main__.py` (`_system_prompt`, `build_generate`)
- Test: `tests/test_llm.py`, `tests/test_stage_main.py`

**Interfaces:**
- Produces: `LLMClient(..., max_tokens: int = 200)` — 이후 Task 4 에서 수준별 값을 넘긴다.
- Produces: `stage.__main__._system_prompt() -> str` — Task 4 에서 역할·수준을 받는 형태로 바뀐다.

- [ ] **Step 1: `max_tokens` 를 생성자 인자로 만드는 실패 테스트**

`tests/test_llm.py` 에 추가:

```python
def test_max_tokens_기본값은_지금_동작과_같다():
    from llm import LLMClient
    assert LLMClient().max_tokens == 200


def test_max_tokens_를_올려_잡을_수_있다():
    from llm import LLMClient
    assert LLMClient(max_tokens=900).max_tokens == 900
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_llm.py -k max_tokens -q`
Expected: FAIL — `AttributeError: 'LLMClient' object has no attribute 'max_tokens'`

- [ ] **Step 3: 생성자와 페이로드 수정**

`apps/voice_chat/voice_chat/llm.py` 생성자에 인자를 더한다:

```python
        timeout: float = 10.0,
        max_tokens: int = 200,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.history: list[dict] = []
        self.history_pairs = history_pairs
        self.timeout = timeout
        # 하드코딩이던 것을 뺀다. 한국어는 토큰당 글자가 적어 200 이면 대략
        # 200~300자다 — 길게 쓰라고 시키는 순간 문장이 중간에서 잘린다.
        self.max_tokens = max_tokens
```

그리고 요청 페이로드(`:79` 근처)의 `"max_tokens": 200,` 을 `"max_tokens": self.max_tokens,` 으로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_llm.py -q`
Expected: PASS

- [ ] **Step 5: 시스템 프롬프트에 분량 규정을 넣는 실패 테스트**

`tests/test_stage_main.py` 에 추가:

```python
def test_시스템_프롬프트에_분량_규정이_있다():
    import stage.__main__ as m
    p = m._system_prompt()
    # 상한만 주면 모델이 하단에 붙는다 — 하한이 반드시 있어야 한다.
    assert "이내" not in p or "이상" in p, p
    assert "문장" in p
```

- [ ] **Step 6: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_main.py -k 분량 -q`
Expected: FAIL — 프롬프트에 "문장" 이 없다

- [ ] **Step 7: 프롬프트 수정**

`stage/__main__.py::_system_prompt()` 의 반환 문자열 끝에 더한다:

```python
        # **분량은 상한만 주면 안 된다.** 큐시트 지시문이 "N문장 이내" 로만 적혀
        # 있어 모델이 한 문장으로 답해도 지시 위반이 아니었다 — 하한을 준다.
        "지시문이 문장 수를 정해 주면 그 수를 **채워서** 말한다. "
        "'N문장 이내' 는 N문장에 가깝게 쓰라는 뜻이지 한 문장으로 끝내라는 뜻이 아니다. "
        "한 문장짜리 답은 해설이 아니다. "
```

- [ ] **Step 8: 분량 미달 경고를 넣는 실패 테스트**

`tests/test_stage_director.py` 에 추가:

```python
def test_생성_결과가_너무_짧으면_경고한다():
    """조용히 짧게 나오는 것이 지금 문제의 본질이다 — 최소한 로그에는 드러나야 한다."""
    h = Harness(generate=lambda brief, hist: "네.")
    h.d.start()
    h.ended("mc", "c1")
    assert any("짧다" in w for w in h.warnings), h.warnings
```

- [ ] **Step 9: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k 짧으면 -q`
Expected: FAIL — 경고가 없다

- [ ] **Step 10: 경고 구현**

`stage/director.py` 상단에 상수를 더한다:

```python
# 이보다 짧은 생성 결과는 해설이 아니다. 경고만 하고 그대로 쓴다 — 버리면
# 정적이 되는데 그게 더 나쁘다. 목표 분량은 Task 3 에서 수준 프로필로 올라간다.
MIN_CHARS = 40
```

`_await_pending()` 의 `return text` 직전에 더한다:

```python
        if len(text) < MIN_CHARS:
            self._warn(f"[{label}] 생성 결과가 너무 짧다({len(text)}자) — 그대로 쓴다")
```

- [ ] **Step 11: 전체 통과 확인**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (기존 전부 + 신규)

- [ ] **Step 12: 커밋**

```bash
git add apps/voice_chat/voice_chat/llm.py stage/__main__.py stage/director.py tests/
git commit -m "$(cat <<'EOF'
fix(stage): 발화가 짧은 원인 셋 중 수준과 무관한 둘을 고친다

큐시트 길이 규정이 전부 "N문장 이내" 라 상한뿐이고, 시스템 프롬프트에는
분량 얘기가 아예 없어 모델이 한 문장으로 답해도 지시 위반이 아니었다.
프롬프트에 하한을 넣고, 결과가 MIN_CHARS 에 못 미치면 경고를 남긴다.

llm.py 의 max_tokens 200 하드코딩을 생성자 인자로 뺀다. 한국어는 토큰당
글자가 적어 200 이면 대략 200~300자라, 길게 쓰라고 시키는 순간 문장이
중간에서 잘린다. 기본값은 200 그대로라 지금 동작은 안 바뀐다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 역할별 생성 슬롯

지금은 슬롯이 하나다(`_pending_text`/`_pending_ready`/`_gen_token`). 도슨트 해설과 받아치기가 동시에 살아 있어야 하므로 이름을 가진 슬롯으로 나눈다. **이 단계에서 동작은 바뀌지 않는다** — 슬롯 이름이 하나뿐인 상태로 기존 테스트가 전부 통과해야 한다.

**Files:**
- Modify: `stage/director.py` (`__init__`, `_spawn_generate`, `_generate_pending`, `_await_pending`, `on_speaking_ended`)
- Test: `tests/test_stage_director.py`

**Interfaces:**
- Produces: `Director._spawn_generate(slot: str, brief: str, fallback: str, label: str) -> None`
- Produces: `Director._await_pending(slot: str, ready, token: int, fallback: str, label: str) -> str`
- Produces: `Director._snapshot_slot(slot: str) -> tuple[threading.Event, int]` — 락 안에서 부른다.

- [ ] **Step 1: 슬롯이 서로를 침범하지 않는 실패 테스트**

`tests/test_stage_director.py` 에 추가:

```python
def test_슬롯이_다르면_서로를_지우지_않는다():
    """도슨트 해설 생성이 받아치기 슬롯을 밀어내면 받아치기가 통째로 사라진다."""
    h = Harness()
    h.d._spawn_generate("docent", "해설 지시", "해설 폴백", "c1")
    h.d._spawn_generate("after", "받아치기 지시", "받아치기 폴백", "c1:after")
    ready_d, tok_d = h.d._snapshot_slot("docent")
    ready_a, tok_a = h.d._snapshot_slot("after")
    assert ready_d is not ready_a, "두 슬롯이 같은 Event 를 쓴다"
    assert ready_d.wait(3.0) and ready_a.wait(3.0)
    assert h.d._await_pending("docent", ready_d, tok_d, "x", "c1") != \
           h.d._await_pending("after", ready_a, tok_a, "y", "c1:after")
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k 슬롯이_다르면 -q`
Expected: FAIL — `_spawn_generate()` 가 인자 4개를 안 받는다

- [ ] **Step 3: 슬롯 상태를 딕셔너리로 바꾼다**

`stage/director.py::__init__` 의 생성 슬롯 세 줄을 바꾼다:

```python
        # 생성 슬롯 — **이름으로 나뉜다.** 예전에는 하나뿐이라 "한 턴에 생성은
        # 하나" 였는데, 사회자 받아치기가 도슨트 해설과 동시에 살아 있어야 해서
        # 나눴다. 세대 토큰도 슬롯마다 둔다 — 한 슬롯이 갈려도 다른 슬롯의
        # 진행 중인 생성이 버려지면 안 된다.
        self._slots: dict[str, dict] = {}
        self._ack_i = 0
        self._gen_lock = threading.Lock()
```

`_pending_text`/`_pending_ready`/`_gen_thread`/`_gen_token` 은 지운다.

- [ ] **Step 4: `_spawn_generate` 를 슬롯 기반으로**

```python
    def _spawn_generate(self, slot: str, brief: str, fallback: str, label: str) -> None:
        """슬롯 하나를 비우고 스레드를 띄운다. 이력은 **이 시점의 사본**이다."""
        with self._gen_lock:
            s = self._slots.setdefault(slot, {"text": None, "ready": threading.Event(), "token": 0})
            # 이전 세대를 기다리던 스레드를 깨운다 — 그 결과는 토큰 검사로
            # 버려지므로 아무도 이 이벤트를 세팅해 주지 않는다. 안 깨우면
            # `_await_pending` 이 유예시간 내내 좀비로 남고, 그 스레드는
            # 커넥션 수신 루프라 그동안 그 로봇의 메시지가 밀린다.
            s["ready"].set()
            s["text"] = None
            s["ready"] = threading.Event()
            s["token"] += 1
            token = s["token"]
        threading.Thread(
            target=self._generate_pending, args=(slot, brief, token, fallback, label),
            daemon=True,
        ).start()

    def _snapshot_slot(self, slot: str) -> tuple[threading.Event, int]:
        """기다릴 이벤트와 세대를 찍는다. **락 안에서 부른다.**"""
        with self._gen_lock:
            s = self._slots[slot]
            return s["ready"], s["token"]
```

- [ ] **Step 5: `_generate_pending` 과 `_await_pending` 에 슬롯을 넘긴다**

```python
    def _generate_pending(self, slot: str, brief: str, token: int, fallback: str, label: str) -> None:
        try:
            text = self._generate(brief, list(self.history))
            if not text:
                self._warn(f"[{label}] 대사 생성이 빈 문자열을 내놓았다 — 폴백")
                text = fallback
        except Exception as exc:
            self._warn(f"[{label}] LLM 생성 실패({type(exc).__name__}: {exc}) — 폴백")
            text = fallback
        with self._gen_lock:
            s = self._slots[slot]
            if token != s["token"]:
                self._warn(f"[{label}] 대사 생성이 늦게 끝나 버려졌다(다음 턴으로 이미 넘어갔다)")
                return
            s["text"] = text
            ready = s["ready"]
        ready.set()

    def _await_pending(
        self, slot: str, ready: threading.Event, token: int, fallback: str, label: str
    ) -> str:
        """생성된 대사를 기다린다 — **진입 락 밖에서.**"""
        if not ready.wait(timeout=GENERATE_GRACE_S):
            self._warn(f"[{label}] 대사 생성이 늦다 — 폴백")
            return fallback
        with self._gen_lock:
            s = self._slots[slot]
            if token != s["token"]:
                return fallback
            text = s["text"]
        if not text:
            self._warn(f"[{label}] 대사가 비어 있다 — 폴백")
            text = fallback
        if len(text) < MIN_CHARS:
            self._warn(f"[{label}] 생성 결과가 너무 짧다({len(text)}자) — 그대로 쓴다")
        return text
```

- [ ] **Step 6: 호출부를 슬롯 이름 `"docent"` 로 맞춘다**

`_begin_cue` 와 `_answer` 의 `_spawn_generate(...)` 호출에 첫 인자로 `"docent"` 를 넣는다. `on_speaking_ended` 의 스냅샷을 `ready, token = self._snapshot_slot("docent")` 로 바꾸고, `_await_pending` 호출에 `"docent"` 를 넣는다. 세대 검사도 `self._slots["docent"]["token"]` 을 본다.

- [ ] **Step 7: 통과 확인 — 기존 테스트가 전부 그대로 통과해야 한다**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. 하나라도 깨지면 슬롯 분리가 동작을 바꾼 것이다 — 고친다.

- [ ] **Step 8: 커밋**

```bash
git add stage/director.py tests/test_stage_director.py
git commit -m "$(cat <<'EOF'
refactor(stage): 생성 슬롯을 역할별로 나눈다

사회자 받아치기를 도슨트 해설과 동시에 만들어야 하는데 슬롯이 하나뿐이라
한쪽이 다른 쪽을 밀어냈다. 이름으로 나누고 세대 토큰도 슬롯마다 둔다.

이 커밋은 동작을 바꾸지 않는다 — 슬롯 이름이 "docent" 하나뿐인 상태이고
기존 테스트가 전부 그대로 통과한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 수준 프로필

**Files:**
- Create: `data/levels.yaml`, `stage/levels.py`, `tests/test_levels.py`

**Interfaces:**
- Produces: `stage.levels.Level` — `name, min_sentences, max_sentences, min_chars, max_chars, vocabulary, depth, numbers, sources` 를 가진 frozen dataclass
- Produces: `stage.levels.load_levels(path=None) -> dict[str, Level]`
- Produces: `stage.levels.level_of_env(levels: dict[str, Level]) -> Level`
- Produces: `Level.max_tokens` 프로퍼티 — `max_chars * 2 + 64`

- [ ] **Step 1: 실패 테스트**

`tests/test_levels.py` 생성:

```python
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.levels import LevelError, level_of_env, load_levels


def test_수준_넷이_모두_있다():
    lv = load_levels()
    assert set(lv) == {"초등", "중고등", "일반", "전문가"}


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
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_levels.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.levels'`

- [ ] **Step 3: `data/levels.yaml` 작성**

```yaml
# 관람객 수준 프로필. **분량은 섹션이 아니라 수준의 함수다** — 초등에게 6문장은
# 길고 전문가에게 2문장은 부실하다. 큐시트의 "N문장 이내" 를 여기로 올렸다.
# 글자 수는 발화 길이로 환산된다(CHARS_PER_SEC = 4.0): 초등 약 18~30초,
# 전문가 약 65~100초.
초등:
  min_sentences: 2
  max_sentences: 3
  min_chars: 70
  max_chars: 120
  vocabulary: "전문 용어를 쓰지 않는다. 아이가 아는 말로만 말한다."
  depth: "비유 중심으로 말한다. 원리는 설명하지 않는다."
  numbers: "연도·수치·거리를 말하지 않는다."
  sources: "기관 이름이나 출처를 말하지 않는다."
중고등:
  min_sentences: 3
  max_sentences: 4
  min_chars: 120
  max_chars: 200
  vocabulary: "전문 용어가 나오면 풀어서 말한다."
  depth: "비유로 열고 원리를 한 겹 덧붙인다."
  numbers: "연도만 말한다. 정밀한 수치는 생략한다."
  sources: "기관 이름이나 출처를 말하지 않는다."
일반:
  min_sentences: 4
  max_sentences: 5
  min_chars: 180
  max_chars: 280
  vocabulary: "전문 용어를 풀어서 말하되 용어 자체도 함께 말한다."
  depth: "원리를 설명한다."
  numbers: "연도와 개략 수치를 말한다."
  sources: "기관 이름까지는 말해도 된다."
전문가:
  min_sentences: 5
  max_sentences: 7
  min_chars: 260
  max_chars: 400
  vocabulary: "전문 용어를 그대로 쓴다."
  depth: "수식·수치·표준 번호까지 들어간다."
  numbers: "정확한 날짜와 원수치를 말한다."
  sources: "기관·조항·표준 번호를 말해도 된다."
```

- [ ] **Step 4: `stage/levels.py` 작성**

```python
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

_FIELDS = ("min_sentences", "max_sentences", "min_chars", "max_chars",
           "vocabulary", "depth", "numbers", "sources")


class LevelError(ValueError):
    """수준 프로필이 규약에 맞지 않거나 모르는 수준을 요구받았다."""


@dataclass(frozen=True)
class Level:
    name: str
    min_sentences: int
    max_sentences: int
    min_chars: int
    max_chars: int
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
        for f in _FIELDS:
            if f not in item:
                raise LevelError(f"{p} {name}: {f} 가 없다")
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
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_levels.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: 기동 로그에 수준을 찍는 실패 테스트**

`tests/test_stage_main.py` 에 추가:

```python
def test_기동_로그에_수준이_찍힌다(capsys, monkeypatch):
    """엉뚱한 수준으로 도는 것은 조용히 품질만 떨어지는 전형적인 실패다."""
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "초등")
    import stage.__main__ as m
    m.announce_level()
    assert "초등" in capsys.readouterr().out
```

- [ ] **Step 7: 실패 확인 후 구현**

Run: `.venv/bin/python -m pytest tests/test_stage_main.py -k 기동_로그 -q` → FAIL

`stage/__main__.py` 에 추가:

```python
def announce_level() -> None:
    """어느 수준으로 도는지 기동 때 밝힌다."""
    from stage.levels import level_of_env, load_levels

    lv = level_of_env(load_levels())
    src = "환경변수" if os.environ.get("REACHY_AUDIENCE_LEVEL") else "기본값"
    print(
        f"관람객 수준: {lv.name} ({src}) — "
        f"{lv.min_sentences}~{lv.max_sentences}문장 / {lv.min_chars}~{lv.max_chars}자",
        flush=True,
    )
```

`main()` 안에서 서버를 만들기 전에 `announce_level()` 을 부른다.

- [ ] **Step 8: 전체 통과 확인 후 커밋**

Run: `.venv/bin/python -m pytest tests/ -q` → PASS

```bash
git add data/levels.yaml stage/levels.py stage/__main__.py tests/test_levels.py tests/test_stage_main.py
git commit -m "$(cat <<'EOF'
feat(stage): 관람객 수준 프로필을 넣고 기동 시 지정하게 한다

분량은 섹션이 아니라 수준의 함수다 — 초등에게 6문장은 길고 전문가에게
2문장은 부실하다. 큐시트에 섹션별로 적던 "N문장 이내" 를 수준 프로필로
올릴 자리를 만든다. 수준은 사실이 아니라 말하는 방식만 가른다.

REACHY_AUDIENCE_LEVEL 오타는 소리 내서 실패시키고, 기동 로그에 수준을
찍는다. 엉뚱한 수준으로 도는 것은 조용히 품질만 떨어지는 전형이다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 페르소나와 프롬프트 조립

**Files:**
- Create: `data/personas/mc.md`, `data/personas/docent.md`, `stage/prompts.py`, `tests/test_prompts.py`
- Modify: `stage/__main__.py` (`build_generate`, `_system_prompt` 제거)

**Interfaces:**
- Consumes: `stage.levels.Level` (Task 3)
- Produces: `stage.prompts.build_system_prompt(role: str, level: Level) -> str`
- Produces: `build_generate(level)` 가 만드는 `generate(role: str, brief: str, history: list[dict]) -> str` — Director 가 부르는 시그니처가 **역할을 받는 형태로 바뀐다**

- [ ] **Step 1: 실패 테스트**

`tests/test_prompts.py` 생성:

```python
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.levels import load_levels
from stage.prompts import build_system_prompt


def test_역할에_따라_프롬프트가_다르다():
    lv = load_levels()["일반"]
    assert build_system_prompt("mc", lv) != build_system_prompt("docent", lv)


def test_수준의_분량이_프롬프트에_들어간다():
    lv = load_levels()["전문가"]
    p = build_system_prompt("docent", lv)
    assert "5" in p and "7" in p and "260" in p and "400" in p


def test_공통_규약은_두_역할_모두에_있다():
    # TTS 가 읽는다 — 목록 기호·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5).
    lv = load_levels()["일반"]
    for role in ("mc", "docent"):
        p = build_system_prompt(role, lv)
        assert "음성" in p and "마크다운" in p


def test_모르는_역할은_거절한다():
    with pytest.raises(ValueError, match="역할"):
        build_system_prompt("사회자", load_levels()["일반"])
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_prompts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.prompts'`

- [ ] **Step 3: 페르소나 파일 작성**

`data/personas/mc.md`:

```markdown
너는 전파체험관 팟캐스트의 **사회자**다.

- 화제를 열고 도슨트에게 넘긴다. 해설은 네 몫이 아니다.
- 도슨트의 말을 받아 짧게 반응하고, 관람객이 끼어들 수 있게 창구를 연다.
- 너는 관람객 편이다. 관람객이 궁금해할 만한 것을 대신 묻는다.
- 지시문에 없는 사실을 만들어 내지 않는다. 모르면 도슨트에게 넘긴다.
```

`data/personas/docent.md`:

```markdown
너는 전파체험관의 **도슨트**다.

- 지시를 받으면 관람객에게 들려줄 해설을 말한다.
- 지시문을 따라 읽지 말고 해설로 바꿔 말한다.
- 지시문에 없는 사실을 지어내지 않는다. 확인되지 않은 수치는 말하지 않는다.
- 상대연도('몇 년 전')를 쓰지 않고 절대연도로만 말한다.
```

- [ ] **Step 4: `stage/prompts.py` 작성**

```python
"""시스템 프롬프트 조립 — [공통 규약 + 역할 페르소나 + 수준 지침].

페르소나를 **코드가 아니라 데이터**에 둔 이유: 시연 전에 사람이 읽고 고쳐야
하는데 코드에 박혀 있으면 못 고친다. 이 저장소에는 이미 프롬프트를 파일로
두는 선례가 있다(`apps/voice_chat/voice_chat/prompt.md`).
"""

import pathlib

from stage.levels import Level

ROLES = ("mc", "docent")

# TTS 가 읽는다 — 목록 기호·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5).
_COMMON = (
    "네 말은 음성으로 읽힌다. 목록·이모지·특수문자·마크다운을 쓰지 않고 "
    "문장은 마침표로 끝낸다."
)


def personas_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "personas"


def build_system_prompt(role: str, level: Level) -> str:
    if role not in ROLES:
        raise ValueError(f"모르는 역할: {role!r} — 쓸 수 있는 값: {', '.join(ROLES)}")
    persona = (personas_dir() / f"{role}.md").read_text(encoding="utf-8").strip()
    # **분량은 범위로 준다.** 상한만 주면 모델이 하단에 붙는다(spec §5).
    amount = (
        f"{level.min_sentences}~{level.max_sentences}문장으로, "
        f"{level.min_chars}~{level.max_chars}자 사이로 말한다. "
        f"한 문장짜리 답은 해설이 아니다."
    )
    return "\n\n".join([persona, _COMMON, amount,
                        level.vocabulary, level.depth, level.numbers, level.sources])
```

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_prompts.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: `build_generate` 를 역할별로 배선**

`stage/__main__.py` 의 `build_generate` 를 바꾸고 `_system_prompt` 를 지운다:

```python
def build_generate(level) -> "callable":
    """LLM 호출 하나. **직렬화한다.**

    두 화자가 **하나의 대화 이력**을 봐야 말이 이어진다 — B 의 대사는 A 가
    정해진 뒤에야 만들 수 있으므로 병렬이 아니라 파이프라인이다. 그래서
    클라이언트를 역할별로 둬도 락은 하나다.
    """
    from stage.prompts import ROLES, build_system_prompt

    clients = {
        r: LLMClient(system_prompt=build_system_prompt(r, level),
                     max_tokens=level.max_tokens)
        for r in ROLES
    }
    lock = threading.Lock()

    def generate(role: str, brief: str, history: list[dict]) -> str:
        with lock:
            c = clients[role]
            c.history = list(history)
            return "".join(c.chat_stream(brief, None))

    return generate
```

`main()` 에서 `level = level_of_env(load_levels())` 를 만들어 `build_generate(level)` 에 넘긴다.

- [ ] **Step 7: Director 의 `_generate` 호출에 역할을 넘긴다**

`stage/director.py::_generate_pending` 의 호출을 바꾼다:

```python
            text = self._generate(role, brief, list(self.history))
```

`_generate_pending` 시그니처에 `role: str` 을 더하고, `_spawn_generate` 가 그것을 받아 넘긴다(`_spawn_generate(slot, role, brief, fallback, label)`). 도슨트 해설과 질문 응답은 `role="docent"`, 받아치기는 `role="mc"` 다.

**⚠️ 여기서 앞선 태스크가 만든 것 셋이 깨진다. 같이 고친다.**

0. **Task 1 이 추가한 `tests/test_stage_main.py::test_시스템_프롬프트에_분량_규정이_있다` 가 `_system_prompt()` 를 부르는데 이 태스크가 그 함수를 지운다.** 그 테스트를 새 조립 함수로 옮긴다:

```python
def test_시스템_프롬프트에_분량_규정이_있다():
    from stage.levels import load_levels
    from stage.prompts import build_system_prompt
    lv = load_levels()["일반"]
    p = build_system_prompt("docent", lv)
    # 상한만 주면 모델이 하단에 붙는다 — 범위가 들어가야 한다.
    assert str(lv.min_sentences) in p and str(lv.max_chars) in p
```


1. `tests/test_stage_director.py` 의 `Harness._gen` 시그니처를 `(role, brief, history)` 로 맞춘다. `Harness.__init__` 의 `generate` 콜백을 쓰는 기존 테스트들도 같은 모양이 된다.
2. Task 2 에서 쓴 `test_슬롯이_다르면_서로를_지우지_않는다` 의 `_spawn_generate` 호출이 인자 4개다. 5개로 고친다:

```python
    h.d._spawn_generate("docent", "docent", "해설 지시", "해설 폴백", "c1")
    h.d._spawn_generate("after", "mc", "받아치기 지시", "받아치기 폴백", "c1:after")
```

이 시그니처(`slot, role, brief, fallback, label`)가 **이후 태스크 전부가 쓰는 최종형**이다.

- [ ] **Step 8: 전체 통과 확인 후 커밋**

Run: `.venv/bin/python -m pytest tests/ -q` → PASS

```bash
git add data/personas stage/prompts.py stage/__main__.py stage/director.py tests/
git commit -m "$(cat <<'EOF'
feat(stage): 페르소나를 데이터로 내리고 역할·수준으로 프롬프트를 조립한다

지금까지 시스템 프롬프트가 코드에 박힌 문자열 하나였고 도슨트만 기술했다.
사회자가 말을 만들려면 페르소나가 둘이어야 하고, 수준 지침이 그 위에
직교로 얹힌다. 조립은 [공통 규약 + 역할 + 수준] 세 조각이다.

페르소나를 data/personas 로 내린 이유는 시연 전에 사람이 읽고 고쳐야
하는데 코드에 박혀 있으면 못 고치기 때문이다.

LLM 클라이언트는 역할별로 두되 락은 하나다 — 두 화자가 하나의 대화
이력을 봐야 하므로 병렬이 아니라 파이프라인이다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 큐시트 스키마 확장

**Files:**
- Modify: `stage/cues.py` (`Cue`, `_REQUIRED`, `load_cues`)
- Test: `tests/test_stage_cues.py`

**Interfaces:**
- Consumes: `stage.levels.LEVEL_NAMES` (Task 3)
- Produces: `Cue.briefs: dict[str, dict[str, str]]` — 수준 → `{"mc_brief": str, "docent_brief": str}`
- Produces: `Cue.brief_for(level_name: str) -> tuple[str, str]` — `(mc_brief, docent_brief)`

- [ ] **Step 1: 실패 테스트**

`tests/test_stage_cues.py` 에 추가:

```python
def test_수준별_브리프를_읽는다(tmp_path):
    from stage.cues import load_cues
    p = tmp_path / "c.yaml"
    p.write_text("""
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  mc_after: "받아치기"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: {mc_brief: "초등 진행", docent_brief: "초등 해설"}
    중고등: {mc_brief: "중고등 진행", docent_brief: "중고등 해설"}
    일반: {mc_brief: "일반 진행", docent_brief: "일반 해설"}
    전문가: {mc_brief: "전문가 진행", docent_brief: "전문가 해설"}
""", encoding="utf-8")
    c = load_cues(p)[0]
    assert c.brief_for("초등") == ("초등 진행", "초등 해설")


def test_브리프가_없으면_옛_지시문으로_폴백한다(tmp_path):
    """큐시트 전체를 한 번에 옮길 수 없다 — 섹션마다 순차로 보강한다."""
    from stage.cues import load_cues
    p = tmp_path / "c.yaml"
    p.write_text("""
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
""", encoding="utf-8")
    c = load_cues(p)[0]
    assert c.brief_for("초등") == ("", "옛 지시문")


def test_수준이_하나라도_빠지면_소리_내서_실패한다(tmp_path):
    from stage.cues import CueError, load_cues
    p = tmp_path / "c.yaml"
    p.write_text("""
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: {mc_brief: "a", docent_brief: "b"}
""", encoding="utf-8")
    with pytest.raises(CueError, match="수준"):
        load_cues(p)
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -k 브리프 -q`
Expected: FAIL — `Cue` 에 `brief_for` 가 없다

- [ ] **Step 3: `Cue` 확장**

`stage/cues.py`:

```python
from stage.levels import LEVEL_NAMES

@dataclass(frozen=True)
class Cue:
    id: str
    title: str
    mc: str
    docent_brief: str
    gaze: str
    mc_after: str = ""
    # 조사 주제와 출처 달린 사실. 발화에는 직접 쓰지 않고 사람이 검토한다.
    topic: str = ""
    # 수준 → {mc_brief, docent_brief}. 비어 있으면 옛 `docent_brief` 로 폴백한다
    # — 큐시트 19섹션을 한 번에 옮길 수 없으므로 섞여 있는 기간이 있다.
    briefs: dict = field(default_factory=dict)

    def brief_for(self, level_name: str) -> tuple[str, str]:
        b = self.briefs.get(level_name)
        if not b:
            return "", self.docent_brief
        return b.get("mc_brief", ""), b.get("docent_brief", self.docent_brief)
```

`field` 를 import 한다: `from dataclasses import dataclass, field`.

- [ ] **Step 4: `load_cues` 검증 추가**

`out.append(...)` 직전에 넣는다:

```python
        briefs = item.get("briefs") or {}
        if briefs:
            if not isinstance(briefs, dict):
                raise CueError(f"{p} {item['id']}: briefs 는 매핑이어야 한다")
            missing = set(LEVEL_NAMES) - set(briefs)
            if missing:
                # 한 수준만 빠지면 그 수준의 시연이 통째로 옛 지시문으로
                # 돈다 — 조용히 품질이 떨어지므로 기동에서 막는다.
                raise CueError(f"{p} {item['id']}: 빠진 수준이 있다 — {sorted(missing)}")
            for name, b in briefs.items():
                if not isinstance(b, dict) or not b.get("docent_brief"):
                    raise CueError(f"{p} {item['id']} {name}: docent_brief 가 없다")
```

`Cue(**...)` 호출에 `topic=item.get("topic", "") or ""`, `briefs=briefs` 를 더한다.

- [ ] **Step 5: 큐시트에서 섹션별 문장 수 지정을 걷어낸다**

spec §5 가 요구하는 이관이다. `data/cues.yaml` 의 `docent_brief` 마다 붙어 있는
"3문장 이내" / "4문장 이내" / "5문장 이내" / "6문장 이내" 를 **지운다**. 분량은
이제 수준 프로필이 정한다 — 둘 다 있으면 섹션 지정이 수준 지정을 덮어 수준을
바꿔도 분량이 안 변한다.

```bash
.venv/bin/python - <<'PY'
import pathlib, re
p = pathlib.Path("data/cues.yaml")
t = p.read_text(encoding="utf-8")
n = len(re.findall(r"\s*\d+문장 이내\.?", t))
p.write_text(re.sub(r"\s*\d+문장 이내\.?", "", t), encoding="utf-8")
print(f"{n}곳에서 문장 수 지정을 지웠다")
PY
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from stage.cues import load_cues
print(len(load_cues()), '섹션 — 여전히 읽힌다')
"
```

Expected: `19곳에서...` 언저리, 그리고 `19 섹션 — 여전히 읽힌다`

- [ ] **Step 6: 통과 확인 후 커밋**

Run: `.venv/bin/python -m pytest tests/ -q` → PASS

```bash
git add stage/cues.py data/cues.yaml tests/test_stage_cues.py
git commit -m "$(cat <<'EOF'
feat(stage): 큐시트에 수준별 브리프를 받고 섹션별 문장 수를 걷어낸다

브리프가 없는 섹션은 옛 docent_brief 로 폴백한다 — 19섹션을 한 번에 옮길
수 없으니 섞여 있는 기간이 있다. 반대로 briefs 를 적었는데 수준이 하나라도
빠지면 기동에서 막는다. 그 수준의 시연만 통째로 옛 지시문으로 도는데
로그에는 아무것도 안 남기 때문이다.

섹션마다 박혀 있던 "N문장 이내" 도 같이 걷어낸다. 분량은 이제 수준 프로필이
정하는데, 둘 다 있으면 섹션 지정이 수준 지정을 덮어 수준을 바꿔도 분량이
안 변한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 여는 대사 사전 생성

**Files:**
- Create: `scripts/pregen_mc_lines.py`, `tests/test_pregen.py`
- Modify: `stage/director.py` (`_begin_cue` 가 캐시를 본다)

**Interfaces:**
- Consumes: `Cue.brief_for` (Task 5), `build_system_prompt` (Task 4)
- Produces: `stage.mc_cache.load_mc_lines(path=None) -> dict[str, str]` — 키는 `f"{cue_id}|{level}|{hash}"`
- Produces: `stage.mc_cache.cache_key(cue_id: str, level: str, mc_brief: str) -> str`

- [ ] **Step 1: 실패 테스트**

`tests/test_pregen.py` 생성:

```python
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.mc_cache import cache_key, load_mc_lines


def test_지시문이_바뀌면_키가_바뀐다():
    """큐시트를 고치면 낡은 캐시가 드러나야 한다 — 안 그러면 옛 대사가 계속 나간다."""
    a = cache_key("c1", "일반", "지시문 A")
    b = cache_key("c1", "일반", "지시문 B")
    assert a != b


def test_수준이_다르면_키가_다르다():
    assert cache_key("c1", "초등", "같은 지시문") != cache_key("c1", "전문가", "같은 지시문")


def test_캐시가_없으면_빈_딕셔너리다(tmp_path):
    assert load_mc_lines(tmp_path / "없는파일.yaml") == {}
```

- [ ] **Step 2: 실패 확인 후 `stage/mc_cache.py` 구현**

Run: `.venv/bin/python -m pytest tests/test_pregen.py -q` → FAIL

```python
"""여는 대사 사전 생성 캐시.

**왜 미리 만드나.** 지연이 0 인 것도 이유지만 더 큰 이유는 **사람이 시연 전에
19섹션 × 4수준 = 76개를 읽어볼 수 있다**는 것이다. 런타임 생성은 그 기회가 없다.
"""

import hashlib
import pathlib

import yaml


def cache_key(cue_id: str, level: str, mc_brief: str) -> str:
    """지시문 해시를 키에 넣는다 — 큐시트를 고치면 낡은 항목이 드러난다."""
    h = hashlib.sha256(mc_brief.encode("utf-8")).hexdigest()[:12]
    return f"{cue_id}|{level}|{h}"


def cache_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "mc_lines.yaml"


def load_mc_lines(path: pathlib.Path | None = None) -> dict[str, str]:
    p = pathlib.Path(path) if path is not None else cache_path()
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}
```

- [ ] **Step 3: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_pregen.py -q` → PASS

- [ ] **Step 4: 캐시 미스가 폴백 + 경고인지 확인하는 실패 테스트**

`tests/test_stage_director.py` 에 추가:

```python
def test_여는_대사_캐시가_없으면_큐시트_원문을_읽고_경고한다():
    h = Harness()
    h.d.start()
    assert h.says()[0][1] == "사회자 첫 대사"      # 큐시트 원문 그대로
    assert any("캐시" in w for w in h.warnings), h.warnings
```

- [ ] **Step 5: 실패 확인 후 `_begin_cue` 수정**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k 여는_대사_캐시 -q` → FAIL

`Director.__init__` 에 `mc_lines: dict[str, str] | None = None`, `level_name: str = "일반"` 인자를 더하고 저장한다. `_begin_cue` 의 사회자 대사 결정을 바꾼다:

```python
        mc_brief, _ = cue.brief_for(self._level_name)
        key = cache_key(cue.id, self._level_name, mc_brief)
        mc_text = self._mc_lines.get(key, "")
        if not mc_text:
            # 조용히 물러나지 않는다 — 사전 생성을 빠뜨린 채 시연이 돌면
            # 애드리브가 통째로 없는데 아무도 모른다.
            self._warn(f"[{cue.id}] 여는 대사 캐시가 없다({self._level_name}) — 큐시트 원문을 읽는다")
            mc_text = cue.mc
        self._remember(f"사회자: {mc_text}")
```

이후 `speak(...)` 에 `cue.mc` 대신 `mc_text` 를 넘긴다.

- [ ] **Step 5b: 도슨트 해설도 수준을 따르게 한다 — 계획 보완(2026-09-20)**

Task 5 가 `Cue.brief_for` 를 열었지만 **도슨트 자신의 해설 브리프를 그것으로 바꾸는
자리가 계획 어디에도 없었다.** `stage/director.py` 가 두 곳에서 `cue.docent_brief` 를
직접 읽는다. 그대로 두면 사회자 대사만 수준을 따르고 **도슨트 해설은 수준과
무관해진다** — 수준 기능이 절반만 배선된 채 시연에 나간다.

먼저 실패 테스트:

```python
def test_도슨트_해설_브리프가_수준을_따른다():
    """사회자 대사만 수준을 따르고 해설이 안 따르면 기능이 반만 도는 것이다."""
    from stage.cues import Cue, CueSheet
    sheet = CueSheet([Cue(
        "c1", "첫째", "여는 대사", "옛 지시문", "partner",
        briefs={
            "초등": {"mc_brief": "초등 진행", "docent_brief": "초등 해설 지시"},
            "중고등": {"mc_brief": "중 진행", "docent_brief": "중 해설 지시"},
            "일반": {"mc_brief": "일반 진행", "docent_brief": "일반 해설 지시"},
            "전문가": {"mc_brief": "전 진행", "docent_brief": "전문가 해설 지시"},
        },
    )])
    seen: list[str] = []
    h = Harness(sheet=sheet, level_name="초등",
                generate=lambda role, brief, hist: seen.append(brief) or "대사")
    h.d.start()
    assert any("초등 해설 지시" in b for b in seen), seen
    assert not any("옛 지시문" in b for b in seen), seen
```

> `Harness` 에 `sheet`·`level_name` 을 넘길 수 있게 확장한다(기본값은 지금 동작 유지).

그다음 `stage/director.py` 의 두 자리를 바꾼다. `_begin_cue` 의 도슨트 생성과
`on_speaking_ended` 의 `pending` 튜플 둘 다, `cue.docent_brief` 대신
`cue.brief_for(self._level_name)[1]` 을 쓴다. **폴백 인자도 같은 값**으로 준다 —
`brief_for` 가 브리프 없는 섹션에서는 옛 `docent_brief` 를 돌려주므로 폴백 의미가
그대로 유지된다.

- [ ] **Step 6: 사전 생성 스크립트 작성**

`scripts/pregen_mc_lines.py`:

```python
"""여는 대사 사전 생성. 시연 전에 돌리고 결과를 **사람이 읽어본다.**

    .venv/bin/python scripts/pregen_mc_lines.py            # 전 수준
    .venv/bin/python scripts/pregen_mc_lines.py 초등 일반   # 고른 수준만
"""

import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from stage.cues import load_cues
from stage.levels import LEVEL_NAMES, load_levels
from stage.mc_cache import cache_key, cache_path, load_mc_lines
from stage.__main__ import build_generate


def main() -> None:
    wanted = sys.argv[1:] or list(LEVEL_NAMES)
    levels = load_levels()
    cues = load_cues()
    out = load_mc_lines()
    for name in wanted:
        gen = build_generate(levels[name])
        for cue in cues:
            mc_brief, _ = cue.brief_for(name)
            if not mc_brief:
                print(f"  건너뜀 {cue.id}/{name} — mc_brief 가 없다", flush=True)
                continue
            key = cache_key(cue.id, name, mc_brief)
            if key in out:
                continue
            text = gen("mc", mc_brief, [])
            out[key] = text
            print(f"  {cue.id}/{name}: {text}", flush=True)
    cache_path().write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )
    print(f"\n{len(out)}개를 {cache_path()} 에 썼다. **읽어보고 고친다.**")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 전체 통과 확인 후 커밋**

Run: `.venv/bin/python -m pytest tests/ -q` → PASS

```bash
git add stage/mc_cache.py scripts/pregen_mc_lines.py stage/director.py tests/
git commit -m "$(cat <<'EOF'
feat(stage): 여는 대사를 사전 생성해 캐시에서 읽는다

런타임 지연이 0 인 것도 이유지만 더 큰 이유는 시연 전에 사람이 19섹션 ×
4수준 = 76개를 읽어보고 고칠 수 있다는 것이다. 런타임 생성은 그 기회가 없다.

캐시 키에 지시문 해시를 넣어 큐시트를 고치면 낡은 항목이 드러나게 한다.
캐시가 없으면 큐시트 원문으로 폴백하되 경고를 남긴다 — 사전 생성을
빠뜨린 채 시연이 돌면 애드리브가 통째로 없는데 아무도 모른다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 받아치기 이중 생성

**Files:**
- Modify: `stage/director.py` (`_begin_cue`, `on_speaking_ended`)
- Test: `tests/test_stage_director.py`

**Interfaces:**
- Consumes: 역할별 슬롯(Task 2), 역할 받는 `generate`(Task 4)
- Produces: 슬롯 이름 `"after"` — 받아치기 전용

- [ ] **Step 1: 실패 테스트**

```python
def test_받아치기는_도슨트_실제_발언을_받는다():
    """미리 만든 것보다 실제 반응이 낫다 — 제시간에 오면 그걸 쓴다."""
    def gen(role, brief, hist):
        if role == "mc" and "도슨트가 방금" in brief:
            return "실제 반응 대사입니다. 관람객 여러분 궁금한 점 있으실까요?"
        return "[생성] " + brief

    h = Harness(generate=gen, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"]
    assert said and "실제 반응" in said[0], said


def test_받아치기_실제_생성이_늦으면_예비를_읽는다():
    import threading as _t
    gate = _t.Event()

    def gen(role, brief, hist):
        if role == "mc" and "도슨트가 방금" in brief:
            gate.wait(30)          # 유예를 넘긴다
            return "너무 늦은 반응"
        return "[생성] " + brief

    h = Harness(generate=gen, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"]
    assert said and "너무 늦은" not in said[0], said
    gate.set()
```

> 두 번째 테스트는 `GENERATE_GRACE_S` 만큼 걸린다. 그 상수를 monkeypatch 로 0.3 초로 낮춰 돌린다.

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k 받아치기 -q`
Expected: FAIL — 지금은 큐시트의 고정 `mc_after` 가 나온다

- [ ] **Step 3: 예비 받아치기를 섹션 시작 때 띄운다**

`_begin_cue` 의 도슨트 생성 다음 줄에 더한다:

```python
        # 받아치기 **예비** — 도슨트 지시문만 보고 미리 만든다. 실제 반응이
        # 늦을 때의 여유분이다. 해설 다음 순번이라 급한 쪽이 먼저 나간다.
        if cue.mc_after:
            _, docent_brief = cue.brief_for(self._level_name)
            self._spawn_generate(
                "after", "mc",
                f"도슨트가 이런 해설을 할 것이다: {docent_brief}. "
                "짧게 받고 관람객에게 질문을 권한다.",
                cue.mc_after, f"{cue.id}:after",
            )
```

- [ ] **Step 4: 도슨트 대사를 보낼 때 실제 반응 생성을 띄운다**

`on_speaking_ended` 의 2구간에서 도슨트 `speak` 를 만든 뒤, 같은 락 안에서 더한다:

```python
            if cue.mc_after:
                # 받아치기 **실제** — 도슨트가 실제로 한 말을 보고 만든다.
                # 도슨트 발화(~7-8초)가 이 생성 시간을 산다.
                self._spawn_generate(
                    "after", "mc",
                    f"도슨트가 방금 이렇게 말했다: {text}. 짧게 받고 관람객에게 질문을 권한다.",
                    cue.mc_after, f"{cue.id}:after",
                )
```

- [ ] **Step 5: 받아치기 갈래가 슬롯을 기다리게 바꾼다**

`on_speaking_ended` 의 `mc_after` 갈래를 `pending` 갈래로 옮긴다 — 즉 `cue_id == f"{cue.id}:docent" and cue.mc_after` 일 때 `pending = ("mc", f"{cue.id}:after", cue.mc_after, f"{cue.id}:after")` 로 두고, 슬롯 이름 `"after"` 를 쓴다. 2구간에서 `self._remember(f"사회자: {text}")` 뒤 `machine.speak(self._who("mc"), ...)` 로 내보낸다.

- [ ] **Step 6: 통과 확인 후 커밋**

Run: `.venv/bin/python -m pytest tests/ -q` → PASS

```bash
git add stage/director.py tests/test_stage_director.py
git commit -m "$(cat <<'EOF'
feat(stage): 받아치기를 예비·실제 두 벌로 만들어 먼저 준비된 쪽을 쓴다

지금 고정 받아치기는 반응처럼 들리지만 미리 쓴 문장이다. 진짜 반응을
만들려면 도슨트 발화가 끝난 뒤에야 생성을 시작할 수 있어 그 자리에
지연이 생긴다. 그래서 둘 다 만든다 — 섹션 시작 때 지시문만 보고 예비를
하나, 도슨트 대사를 보낼 때 실제 발언을 보고 하나. 도슨트가 말하는
7~8초가 실제 반응의 생성 시간을 산다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: 마무리 질문과 침묵 자동 진행

**Files:**
- Modify: `stage/director.py` (`__init__`, `on_speaking_ended`, `tick`, `on_heard`), `stage/cues.py` (`QUESTION_PROMPTS`)
- Test: `tests/test_stage_director.py`

**Interfaces:**
- Consumes: 받아치기 슬롯(Task 7)
- Produces: `Director.QUESTION_WAIT_S = 8.0`, `stage.cues.QUESTION_PROMPTS: tuple[str, ...]`

- [ ] **Step 1: 실패 테스트**

```python
def test_침묵이_한도를_넘으면_다음_큐로_간다():
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")          # 받아치기 없는 큐 → 곧장 듣기
    assert h.d.state is State.LISTENING
    h.clear()
    h.clock.t += 8.1
    h.d.tick()
    assert h.says(), "침묵인데 다음 큐가 시작되지 않았다"
    assert h.says()[0][1] == "사회자 둘째 대사"


def test_질문이_들어오면_침묵_타이머가_멈춘다():
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")      # 질문 → 확인 멘트
    h.clear()
    h.clock.t += 8.1
    h.d.tick()
    assert not h.says(), "질문 처리 중인데 다음 큐로 넘어갔다"


def test_받아치기에_질문_유도가_없으면_고정_문장으로_바꾼다():
    from stage.cues import QUESTION_PROMPTS
    h = Harness(generate=lambda role, brief, hist: "그렇군요.",
                after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert any(q in said for q in QUESTION_PROMPTS), said
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k "침묵 or 질문_유도" -q`
Expected: FAIL

- [ ] **Step 3: `QUESTION_PROMPTS` 추가**

`stage/cues.py` 의 `QA_ACK_LINES` 아래에:

```python
# 섹션 끝에 사회자가 관람객에게 창구를 **말로** 여는 문장. 마이크가 열려도
# 관람객은 모른다(리뷰 B2). 생성된 받아치기에 이런 유도가 없으면 붙인다.
# 같은 말이 19번 반복되면 녹음처럼 들리므로 돌아가며 쓴다.
QUESTION_PROMPTS = (
    "궁금한 점 있으실까요?",
    "여기까지 질문 있으실까요?",
    "더 듣고 싶은 게 있으실까요?",
)
```

- [ ] **Step 4: 침묵 타이머 구현**

`stage/director.py` 상단:

```python
# 섹션 끝에서 관람객 질문을 기다리는 시간. 넘으면 다음 섹션으로 간다.
#
# **비대칭이라 넉넉한 쪽으로 잡는다.** 짧으면 말을 꺼내려던 관람객을 자르는데
# 그건 회복이 안 된다(사람이 무안하다). 길면 정적이 흐를 뿐이고 운영자가
# 콘솔 `n` 으로 즉시 넘긴다.
QUESTION_WAIT_S = 8.0
```

`__init__` 에 `self._question_deadline: float | None = None` 을 더한다. **기존 `_deadline` 과 섞지 않는다** — 그것은 "발화 종료 응답이 없다" 는 뜻이다.

`_to_listening` 으로 가는 자리(`on_speaking_ended` 의 2구간 끝과 받아치기 없는 갈래)에서 `self._question_deadline = self._now() + QUESTION_WAIT_S` 를 세운다.

`tick()` 을 바꾼다:

```python
    def tick(self) -> None:
        cmds: list[Command] = []
        with self._lock:
            if self._deadline is not None and self._now() >= self._deadline:
                role = self._machine.speaking_role
                self._warn(f"[{role}] 발화 종료 응답이 없다 — 강제로 듣기 상태로 되돌린다")
                self._deadline = None
                self._question_deadline = self._now() + QUESTION_WAIT_S
                self._emit(self._machine.force_listening(self._who("mc")))
            elif (
                self._question_deadline is not None
                and self._now() >= self._question_deadline
                and self._machine.state is State.LISTENING
            ):
                # 침묵이 한도를 넘었다 — 다음 섹션으로 간다. `_next_locked()` 가
                # 내부에서 `_begin_cue` → `_emit` 까지 한다.
                self._question_deadline = None
                self._next_locked()
```

> `_emit` 은 이 저장소에서 **직접 전송까지 한다**(`coalesce` → `self._send`). 별도의 dispatch 단계를 만들지 않는다.

`on_heard` 의 맨 앞(상태 검사 통과 직후)에 `self._question_deadline = None` 을 넣는다 — 질문을 받았으면 타이머를 멈춘다.

- [ ] **Step 5: 질문 유도 보장**

`on_speaking_ended` 2구간에서 받아치기 텍스트를 확정한 뒤:

```python
            if label.endswith(":after") and not any(q in text for q in QUESTION_PROMPTS):
                # 관람객 창구가 열린다는 것을 **말로** 알려야 한다. 생성이
                # 그걸 빠뜨리면 마이크가 열려도 아무도 모르고 시연이 조용히 닫힌다.
                prompt = QUESTION_PROMPTS[self._q_i % len(QUESTION_PROMPTS)]
                self._q_i += 1
                self._warn(f"[{label}] 질문 유도가 빠졌다 — 고정 문장을 붙인다")
                text = f"{text} {prompt}"
```

`__init__` 에 `self._q_i = 0` 을 더한다.

- [ ] **Step 6: 전체 통과 확인**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add stage/director.py stage/cues.py tests/test_stage_director.py
git commit -m "$(cat <<'EOF'
feat(stage): 섹션 끝에 질문을 묻고 침묵이면 다음으로 넘어간다

지금은 섹션 끝에 마이크만 열리고 관람객은 그걸 모른다 — "다음" 이라는
낱말을 알아야 진행됐다. 사회자가 명시적으로 묻고, 침묵이 8초를 넘으면
자동으로 다음 섹션으로 간다. is_advance 는 그대로 살려 둔다.

8초로 잡은 근거는 비대칭이다. 짧으면 말을 꺼내려던 관람객을 자르는데
그건 회복이 안 되고, 길면 정적이 흐를 뿐이라 운영자가 n 으로 넘긴다.

질문 대기 기한은 _deadline 과 **따로** 둔다. 그건 "발화 종료 응답이
없다" 는 뜻이라 섞으면 타임아웃 복구가 망가진다.

생성된 받아치기에 질문 유도가 없으면 고정 문장을 붙인다. 빠지면 마이크가
열려도 아무도 모르고 시연이 조용히 닫힌다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: 조사 결과를 큐시트에 접기 — **Task 5 직후에 실행한다**

**계획 결함 보완(2026-09-20).** Task 5 가 `Cue.briefs` 를 읽을 수 있게 만들지만
**`data/cues.yaml` 에 그것을 채우는 태스크가 없었다.** 그대로 두면 모든 섹션의
`briefs` 가 비어 옛 `docent_brief` 로 폴백하고, 수준 기능 전체가 **작동은 하되
아무 효과가 없는** 상태가 된다. 조사(§8)가 19섹션 브리프를 이미 만들어 뒀으므로
그것을 접어 넣는다.

**Files:**
- Modify: `data/cues.yaml`
- Create: `scripts/merge_research.py`, `tests/test_merge_research.py`
- Read-only 입력: `data/cues-research/*.yaml` (19섹션 + `_law-basis.yaml` + `_kca-history.yaml`)

**Interfaces:**
- Consumes: `Cue.briefs`/`topic` (Task 5)
- Produces: 채워진 `data/cues.yaml` — 이후 Task 6 의 사전 생성이 이 브리프를 입력으로 쓴다

- [ ] **Step 1: 접기 규칙을 못박는 실패 테스트**

`tests/test_merge_research.py` 생성:

```python
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from scripts.merge_research import merged_cue


def test_조사_브리프가_큐시트로_접힌다():
    research = {
        "id": "t1", "topic": "주제",
        "briefs": {
            "초등": {"mc_brief": "초등 진행", "docent_brief": "초등 해설"},
            "중고등": {"mc_brief": "중 진행", "docent_brief": "중 해설"},
            "일반": {"mc_brief": "일반 진행", "docent_brief": "일반 해설"},
            "전문가": {"mc_brief": "전 진행", "docent_brief": "전 해설"},
        },
        "mc": "새 여는 대사", "mc_after": "새 받아치기",
    }
    cue = {"id": "t1", "title": "제목", "gaze": "partner",
           "mc": "옛 여는 대사", "mc_after": "옛 받아치기", "docent_brief": "옛 지시문"}
    out = merged_cue(cue, research)
    assert out["briefs"]["초등"]["docent_brief"] == "초등 해설"
    assert out["topic"] == "주제"
    # 조사가 고친 폴백 원문이 이긴다 — corrections 가 거기 반영돼 있다.
    assert out["mc"] == "새 여는 대사"
    assert out["mc_after"] == "새 받아치기"
    # 옛 docent_brief 는 지우지 않는다 — briefs 가 비는 섹션의 폴백이다.
    assert out["docent_brief"] == "옛 지시문"


def test_조사가_없는_섹션은_그대로_둔다():
    cue = {"id": "t9", "title": "제목", "gaze": "partner",
           "mc": "옛 대사", "docent_brief": "옛 지시문"}
    assert merged_cue(cue, None) == cue


def test_브리프가_비어_있으면_접지_않는다():
    """조사 파일은 있는데 briefs 가 비었으면(예: 조사 실패) 옛 값을 지키는 편이 안전하다."""
    cue = {"id": "t1", "title": "제목", "gaze": "partner",
           "mc": "옛 대사", "docent_brief": "옛 지시문"}
    assert merged_cue(cue, {"id": "t1", "briefs": {}})["mc"] == "옛 대사"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_merge_research.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.merge_research'`

(`scripts/__init__.py` 가 없으면 만든다 — 빈 파일이면 된다.)

- [ ] **Step 3: 접기 함수와 스크립트 구현**

`scripts/merge_research.py`:

```python
"""조사 산출물(`data/cues-research/*.yaml`)을 큐시트에 접는다.

**조사 파일이 원본이고 큐시트가 사본이다.** 조사 쪽 `mc`/`mc_after` 가 이기는
이유는 거기에 corrections(사실 오류 정정)가 이미 반영돼 있기 때문이다.
옛 `docent_brief` 는 지우지 않는다 — `briefs` 가 비는 섹션의 폴백이다.
"""

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "data" / "cues-research"
CUES = ROOT / "data" / "cues.yaml"


def merged_cue(cue: dict, research: dict | None) -> dict:
    if not research or not research.get("briefs"):
        return cue
    out = dict(cue)
    out["topic"] = research.get("topic", "")
    out["briefs"] = research["briefs"]
    for k in ("mc", "mc_after"):
        v = research.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def load_research() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(RESEARCH.glob("*.yaml")):
        if p.name.startswith("_"):      # 공유 파일(_law-basis 등)은 섹션이 아니다
            continue
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        out[d["id"]] = d
    return out


def main() -> None:
    research = load_research()
    cues = yaml.safe_load(CUES.read_text(encoding="utf-8"))
    merged, skipped = [], []
    for c in cues:
        r = research.get(c["id"])
        if r is None or not r.get("briefs"):
            skipped.append(c["id"])
        merged.append(merged_cue(c, r))
    CUES.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"{len(merged) - len(skipped)}개 섹션에 브리프를 접었다.")
    if skipped:
        print(f"건너뜀({len(skipped)}): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_merge_research.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 실제로 접고 큐시트가 여전히 읽히는지 본다**

```bash
.venv/bin/python scripts/merge_research.py
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from stage.cues import load_cues
cs = load_cues()
print(len(cs), '섹션')
have = [c.id for c in cs if c.briefs]
print('브리프 있는 섹션:', len(have))
for lv in ('초등','중고등','일반','전문가'):
    n = sum(1 for c in cs if c.brief_for(lv)[1])
    print(f'  {lv}: {n}개 섹션에 도슨트 지시문')
"
```

Expected: `19 섹션`, `브리프 있는 섹션: 19`, 각 수준 19개.

- [ ] **Step 6: 사람이 읽을 차례 — diff 를 남긴다**

```bash
git diff --stat data/cues.yaml
git diff data/cues.yaml > .superpowers/sdd/2026-09-20-podcast-adlib/cues-merge.diff
echo "사람이 읽을 것: .superpowers/sdd/2026-09-20-podcast-adlib/cues-merge.diff"
```

이 diff 에는 **조사가 찾은 사실 오류 56건의 정정이 실려 있다**(1785년 쿨롱 법칙,
타이타닉 711명, GMDSS 1999년 전면시행, ITU 대역 수, 아폴로 월면차 등). 커밋하기
전에 사람이 훑는다 — 자동으로 접었다고 해서 검토를 건너뛰지 않는다.

- [ ] **Step 7: 전체 통과 확인 후 커밋**

Run: `.venv/bin/python -m pytest tests/ -q` → PASS

```bash
git add data/cues.yaml scripts/merge_research.py scripts/__init__.py tests/test_merge_research.py
git commit -m "$(cat <<'EOF'
feat(data): 조사 결과를 큐시트에 접는다 — 사실 오류 56건 정정 포함

Task 5 가 Cue.briefs 를 읽을 수 있게 만들었지만 그것을 채우는 곳이 없었다.
그대로 두면 모든 섹션이 옛 docent_brief 로 폴백해 수준 기능이 작동은 하되
아무 효과가 없다.

조사 파일이 원본이고 큐시트가 사본이다. 조사 쪽 mc/mc_after 가 이기는
이유는 거기에 corrections 가 이미 반영돼 있기 때문이다. 옛 docent_brief 는
지우지 않는다 — briefs 가 비는 섹션의 폴백이다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## 마무리 확인

- [ ] `.venv/bin/python -m pytest tests/ -q` 전체 통과
- [ ] 시뮬 2대로 종단 확인 — 설계문서 §8.1.1 절차. 수준을 바꿔 가며 분량이 실제로 달라지는지 본다:

```bash
REACHY_AUDIENCE_LEVEL=초등   .venv/bin/python -m stage
REACHY_AUDIENCE_LEVEL=전문가 .venv/bin/python -m stage
```

- [ ] `docs/lessons.md` 에 이번에 밟은 지뢰를 증상 → 원인 → 규칙으로 남긴다
- [ ] `docs/real-robot-deployment.md` 에 실기 영향 없음을 적는다(감독 전용 변경)
