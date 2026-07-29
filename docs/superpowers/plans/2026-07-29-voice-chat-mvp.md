# 한국어 음성 일상대화 MVP (M0~M2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MuJoCo 시뮬레이터의 Reachy Mini와 노트북 마이크/스피커로 한국어 일상대화를 한다 — 발화 종료 후 0.8초 안에 감정 모션, 2.0초 안에 음성 응답 시작. 내일 오전 경영진 시연용.

**Architecture:** STT 직후 두 경로가 병렬로 갈라진다 — ① 로컬 키워드 규칙분류 → 감정 모션 즉시 재생, ② LLM 스트리밍 → 절(節) 단위로 잘라 TTS 큐에 밀어넣기. 대화는 자유 텍스트 생성(JSON 스키마 없음), 이력 3쌍 유지. 재생 중 마이크 게이팅으로 에코를 막는다(half-duplex).

**Tech Stack:** Python 3.12 (`.venv/bin/python` 전용) · llama.cpp `llama-server` :8080 (gemma-E4B, `--reasoning off`) · 로컬 STT 서버 :8090 (`stt_server.py`, mlx-whisper) · macOS `say -v Yuna` TTS · GStreamer(PyGObject) 마이크 캡처 · reachy_mini SDK (`RecordedMoves` + `play_move`)

**설계 근거:** `docs/superpowers/specs/2026-07-29-reachy-mini-local-llm-voice-app-design.md` + 이후 재검토 합의(토폴로지=앱은 로봇/추론은 PC, 대화·모션 분리, 모션은 STT 직후, default 템플릿). 이 계획은 그중 시뮬 최소구현(M0~M2)만 다룬다.

## Global Constraints

- 인터프리터는 `.venv/bin/python` 하나뿐이다. 시스템 `python3` 금지.
- 데몬은 `./run-sim.sh`로만 기동한다(별도 터미널, 사용자가 실행). 앱 코드는 데몬을 띄우지 않는다.
- LLM 서버는 `llama reach-llm`으로 기동돼 있어야 한다(`--reasoning off` 포함). `llama start e4b` 금지.
- STT 서버: `.venv/bin/python stt_server.py` (:8090). 응답은 `{"text": "..."}`.
- 앱 위치: `apps/voice_chat/voice_chat/` (앱 어시스턴트로 생성 — Task 0).
- 모든 사용자 대면 문자열·로그는 한국어.
- 모션 화이트리스트 출처: `pollen-robotics/reachy-mini-emotions-library` (85개 캐시 확인됨). 아래 매핑의 이름은 전부 실재 확인됨.
- SLO: 발화 종료→모션 0.8s, →첫 오디오 2.0s. `demo.py`가 구간 타임스탬프를 로그로 남긴다.
- 테스트는 서버 없이 돌 수 있어야 한다(LLM/STT/데몬 필요한 것은 수동 확인 단계로 분리).

## 검증된 환경 사실 (2026-07-29 실측)

| 사실 | 근거 |
|---|---|
| `requests` 2.34.2 설치됨, `pytest` 없음 | import 확인 |
| git 저장소 아님 | `git rev-parse` 실패 — Task 0에서 init |
| PyGObject+GStreamer import 정상 | `import gi` 확인 |
| `say -v Yuna`(ko_KR) 존재 | `say -v '?'` 확인 |
| SDK: `RecordedMoves(dataset).get(name)` → `mini.play_move(move, initial_goto_duration=...)` (동기) | `examples/recorded_moves.py` |
| 감정 모션 85개 이름 | `RecordedMoves('pollen-robotics/reachy-mini-emotions-library').list_moves()` 실행 확인 |
| 데몬 경유 마이크는 시뮬에서 열화(webrtcdsp) — 직접 캡처 사용 | 설계문서 §9 실측 |

## File Structure

```
apps/voice_chat/voice_chat/
  clauses.py     절 분할 버퍼 (순수 로직)
  llm.py         LLMClient — 스트리밍 채팅 + 이력 3쌍
  motion.py      classify() 규칙 + MotionPlayer (비차단 재생)
  tts.py         Speaker — say 큐 워커 + speaking 플래그
  audio_in.py    EnergyVAD (순수 로직) + MicCapture (GStreamer)
  stt.py         transcribe() — WAV 조립 + HTTP
  prompt.md      시스템 프롬프트
  demo.py        CLI 진입점 (--text / 음성 모드), 지연 계측
tests/
  test_clauses.py  test_motion.py  test_tts.py  test_vad.py  test_llm.py
scripts/
  measure_latency.py   M0 실측
docs/
  latency-m0.md        M0 결과 기록
  demo-runbook.md      시연 리허설·복구 절차
```

모듈 간 의존은 `demo.py`에서만 만난다. 각 모듈은 같은 디렉토리의 형제를 import하지 않는다(단독 실행·교체 가능).

---

### Task 0: 스캐폴드 — git, pytest, 앱 폴더, 헬스체크

**Files:**
- Create: `apps/voice_chat/` (앱 어시스턴트), `scripts/check_env.sh`, `tests/__init__.py`

**Interfaces:**
- Produces: 이후 모든 태스크의 작업 위치 `apps/voice_chat/voice_chat/`, 테스트 러너 `.venv/bin/python -m pytest`

- [ ] **Step 1: git 초기화 + 첫 커밋**

```bash
cd /Users/bcchung81/workspace/reach-mini
git init -b main
git add -A
git commit -m "chore: 프로젝트 초기 상태 (설계문서·하네스·STT서버)"
```

`.gitignore`는 이미 있다(`.venv` 등). `harness/`도 커밋한다 — v1.9.0 고정 참조본.

- [ ] **Step 2: pytest 설치**

```bash
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest --version
```

Expected: `pytest 8.x` 출력.

- [ ] **Step 3: 앱 폴더 생성 (어시스턴트, 비대화식)**

```bash
.venv/bin/reachy-mini-app-assistant create voice_chat apps
```

app_name과 path를 둘 다 주면 비대화식으로 돈다(harness/skills/create-app.md). 로컬 전용(`--publish` 없음) — 시연용이며 HF 로그인 전제를 만들지 않는다.
**멈추거나 프롬프트가 뜨면**: 사용자에게 터미널에서 `! .venv/bin/reachy-mini-app-assistant create voice_chat apps` 실행을 요청하고 대기한다. 손으로 디렉토리를 만들지 않는다(CLAUDE.md 절대 규칙).

- [ ] **Step 4: 생성 구조 확인**

```bash
ls apps/voice_chat/voice_chat/   # __init__.py, main.py 등이 보여야 한다
mkdir -p tests scripts && touch tests/__init__.py
```

- [ ] **Step 5: 헬스체크 스크립트**

`scripts/check_env.sh` 생성:

```bash
#!/bin/bash
# 시연 전 환경 점검 — 전부 OK여야 데모 가능
ok=0; fail=0
chk() { if eval "$2" >/dev/null 2>&1; then echo "OK   $1"; ok=$((ok+1)); else echo "FAIL $1  ← $3"; fail=$((fail+1)); fi }
chk "데몬(:8000)"  "curl -sf --max-time 2 localhost:8000/api/state/full"          "./run-sim.sh 실행"
chk "LLM(:8080)"   "curl -sf --max-time 2 localhost:8080/health"                  "llama reach-llm 실행"
chk "STT(:8090)"   "curl -sf --max-time 2 localhost:8090/health"                  ".venv/bin/python stt_server.py 실행"
chk "TTS(Yuna)"    "say -v '?' | grep -q Yuna"                                    "macOS 한국어 음성 설치"
echo "---- $ok OK / $fail FAIL"
exit $fail
```

```bash
chmod +x scripts/check_env.sh && ./scripts/check_env.sh
```

Expected: 서버가 안 떠 있으면 FAIL이 나오는 것 자체가 정상 동작 확인.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: voice_chat 앱 스캐폴드 + 환경 점검 스크립트"
```

---

### Task 1: M0 — 지연 실측 (2초 SLO 판정)

**Files:**
- Create: `scripts/measure_latency.py`, `docs/latency-m0.md`

**Interfaces:**
- Consumes: LLM :8080 (떠 있어야 함), `say`
- Produces: `docs/latency-m0.md`의 실측표 — Task 6/8의 SLO 판정 기준

**선행:** 사용자에게 `llama reach-llm` 기동을 요청한다(`! curl -s localhost:8080/health`로 확인).

- [ ] **Step 1: 계측 스크립트 작성**

`scripts/measure_latency.py`:

```python
"""M0: TTFT / 첫 절 생성 / 첫 절 say 합성을 실측한다. LLM 서버(:8080) 필요."""
import json, subprocess, time
import requests

BASE = "http://127.0.0.1:8080"
SYSTEM = "너는 데스크톱 로봇 '미니'야. 한국어로 짧고 다정하게 1~2문장으로 답해. 사용자 말을 그대로 반복하지 마."
QUESTIONS = ["안녕, 오늘 기분 어때?", "점심에 뭐 먹을지 고민이야.", "재밌는 얘기 하나 해줘."]
BOUNDARY = ".!?…。"

def one_round(q: str) -> dict:
    t0 = time.time()
    r = requests.post(f"{BASE}/v1/chat/completions", stream=True, timeout=15, json={
        "model": "local", "stream": True, "temperature": 0.7, "max_tokens": 200,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": q}]})
    r.raise_for_status()
    ttft = first_clause_t = None
    buf, full = "", []
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        delta = json.loads(data)["choices"][0].get("delta", {}).get("content") or ""
        if not delta:
            continue
        if ttft is None:
            ttft = time.time() - t0
        full.append(delta)
        if first_clause_t is None:
            buf += delta
            if any(c in buf for c in BOUNDARY) or len(buf) > 30:
                first_clause = buf
                first_clause_t = time.time() - t0
    total = time.time() - t0
    t1 = time.time()
    subprocess.run(["say", "-v", "Yuna", first_clause])          # 합성+재생
    say_s = time.time() - t1
    return {"q": q, "ttft": ttft, "first_clause_s": first_clause_t,
            "llm_total": total, "say_first_clause": say_s,
            "clause": first_clause, "answer": "".join(full)}

if __name__ == "__main__":
    print(f"{'TTFT':>6} {'첫절':>6} {'전체':>6} {'say':>6}  질문")
    worst_first_audio = 0.0
    for q in QUESTIONS:
        m = one_round(q)
        # say는 스트리밍 재생이라 발화 시작≈호출 직후로 본다. 보수적으로 0.3s 가산.
        first_audio = m["first_clause_s"] + 0.3
        worst_first_audio = max(worst_first_audio, first_audio)
        print(f"{m['ttft']:6.2f} {m['first_clause_s']:6.2f} {m['llm_total']:6.2f} "
              f"{m['say_first_clause']:6.2f}  {m['q']}  → {m['clause']!r}")
    budget = 0.30 + 0.25 + worst_first_audio   # VAD hangover + STT + LLM첫절+발화개시
    print(f"\n예상 '발화 종료→첫 오디오' 최악치: {budget:.2f}s  (SLO 2.0s {'만족' if budget <= 2.0 else '초과!'})")
```

- [ ] **Step 2: 실행·기록**

```bash
.venv/bin/python scripts/measure_latency.py
```

Expected: 표 3행 + 최악치 판정 출력. 결과 숫자를 `docs/latency-m0.md`에 그대로 붙여넣는다(날짜·모델명 포함).

- [ ] **Step 3: 판정 분기**

- **만족(≤2.0s)**: 그대로 진행.
- **초과**: `max_tokens`를 120으로 내리고 재실측 → 그래도 초과면 사용자에게 보고하고 SLO 조정 판단을 받는다. 이후 태스크는 계속 진행(구조는 동일).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(M0): 지연 실측 스크립트 + 결과 기록"
```

---

### Task 2: 절 분할 버퍼 (순수 로직, TDD)

**Files:**
- Create: `apps/voice_chat/voice_chat/clauses.py`, `tests/test_clauses.py`

**Interfaces:**
- Produces: `ClauseBuffer(soft_limit=30)` — `.feed(delta: str) -> list[str]`, `.flush() -> str | None`. Task 3 `llm.py`가 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_clauses.py`:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from clauses import ClauseBuffer

def test_구두점에서_절이_끊긴다():
    cb = ClauseBuffer()
    assert cb.feed("안녕! 반가") == ["안녕!"]
    assert cb.feed("워. 오늘 어때?") == ["워.", "오늘 어때?"]

def test_구두점_없이_길면_공백에서_끊는다():
    cb = ClauseBuffer(soft_limit=10)
    out = cb.feed("가나다라마바사아자차 카타파하 그리고")
    assert out and all(len(c) >= 10 for c in out[:1])

def test_잔여분은_flush로_나온다():
    cb = ClauseBuffer()
    assert cb.feed("끝맺음 없는 말") == []
    assert cb.flush() == "끝맺음 없는 말"
    assert cb.flush() is None

def test_토큰_단위_공급에도_동작한다():
    cb = ClauseBuffer()
    out = []
    for tok in ["오", "늘", " 날씨", "가 좋", "네요", ".", " 산책 갈까요?"]:
        out += cb.feed(tok)
    out += [c for c in [cb.flush()] if c]
    assert out == ["오늘 날씨가 좋네요.", "산책 갈까요?"]
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_clauses.py -v
```

Expected: FAIL (`ModuleNotFoundError: clauses`)

- [ ] **Step 3: 구현**

`apps/voice_chat/voice_chat/clauses.py`:

```python
"""LLM 스트림 델타를 절(節) 단위로 자른다 — 절이 완성되는 즉시 TTS로 보내기 위함."""

_BOUNDARY = ".!?…。"


class ClauseBuffer:
    def __init__(self, soft_limit: int = 30):
        self._buf = ""
        self._soft_limit = soft_limit

    def feed(self, delta: str) -> list[str]:
        """델타를 누적하고, 완성된 절이 있으면 순서대로 반환한다."""
        self._buf += delta
        out: list[str] = []
        while True:
            cut = -1
            for i, ch in enumerate(self._buf):
                if ch in _BOUNDARY:
                    cut = i
                    break
                if i >= self._soft_limit and ch == " ":
                    cut = i
                    break
            if cut < 0:
                break
            clause = self._buf[: cut + 1].strip()
            self._buf = self._buf[cut + 1 :]
            if clause:
                out.append(clause)
        return out

    def flush(self) -> str | None:
        """스트림 종료 시 잔여분을 내보낸다."""
        s = self._buf.strip()
        self._buf = ""
        return s or None
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_clauses.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: 절 분할 버퍼 — 스트리밍 델타를 TTS 단위로 절단"
```

---

### Task 3: LLM 클라이언트 — 스트리밍 + 이력 3쌍 (TDD, 가짜 서버)

**Files:**
- Create: `apps/voice_chat/voice_chat/llm.py`, `apps/voice_chat/voice_chat/prompt.md`, `tests/test_llm.py`

**Interfaces:**
- Consumes: `ClauseBuffer` (Task 2)
- Produces: `LLMClient(base_url, model="local", system_prompt, history_pairs=3, timeout=10.0)` — `.chat_stream(user_text: str) -> Iterator[str]` (절 단위 yield, 종료 후 이력 자동 반영), `.history: list[dict]`. Task 6 `demo.py`가 사용.

- [ ] **Step 1: 시스템 프롬프트 작성**

`apps/voice_chat/voice_chat/prompt.md`:

```markdown
너는 책상 위에 사는 작은 로봇 '미니'야. 성격은 다정하고 호기심 많음.

규칙:
- 한국어 반말 섞인 친근한 존댓말. 1~2문장, 짧게.
- 사용자가 한 말을 그대로 되풀이하지 마.
- 모르는 건 모른다고 솔직하게.
- 이모지·특수문자·목록 쓰지 마 — 네 말은 음성으로 읽힌다.
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_llm.py` — SSE를 흉내내는 로컬 HTTP 스텁으로 실제 서버 없이 검증:

```python
import json, threading, sys, pathlib
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from llm import LLMClient

CHUNKS = ["오늘", " 기분", " 최고예요", ".", " 당신은요?"]

class Stub(BaseHTTPRequestHandler):
    last_body = None
    def do_POST(self):
        Stub.last_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in CHUNKS:
            ev = {"choices": [{"delta": {"content": c}}]}
            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
    def log_message(self, *a): pass

def _serve():
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"

def test_절_단위로_yield하고_이력을_남긴다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    out = list(c.chat_stream("안녕"))
    assert out == ["오늘 기분 최고예요.", "당신은요?"]
    assert c.history == [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "오늘 기분 최고예요. 당신은요?"},
    ]

def test_이력이_3쌍을_넘으면_2쌍씩_잘린다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템", history_pairs=3)
    for i in range(4):
        list(c.chat_stream(f"질문{i}"))
    assert len(c.history) == 4                       # 4쌍 → 앞 2쌍 삭제 → 2쌍
    assert c.history[0]["content"] == "질문2"

def test_요청에_시스템과_이력이_순서대로_실린다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    list(c.chat_stream("첫질문"))
    list(c.chat_stream("둘째질문"))
    roles = [m["role"] for m in Stub.last_body["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
```

- [ ] **Step 3: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_llm.py -v
```

Expected: FAIL (`ModuleNotFoundError: llm`)

- [ ] **Step 4: 구현**

`apps/voice_chat/voice_chat/llm.py`:

```python
"""LLM 스트리밍 채팅 — OpenAI 호환. 절 단위 yield + 대화 이력 유지.

이력은 3쌍 유지, 넘치면 2쌍씩 뭉텅이로 잘라 llama.cpp 프리픽스 캐시
파손 빈도를 낮춘다(매 턴 1쌍씩 자르면 매번 깨진다).
"""
import json
from collections.abc import Iterator

import requests

from clauses import ClauseBuffer


class LLMClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", model: str = "local",
                 system_prompt: str = "", history_pairs: int = 3, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.history: list[dict] = []
        self.history_pairs = history_pairs
        self.timeout = timeout

    def chat_stream(self, user_text: str) -> Iterator[str]:
        """사용자 발화 → 절 단위 스트림. 정상 종료 시 이력에 한 쌍 추가."""
        messages = ([{"role": "system", "content": self.system_prompt}]
                    + self.history
                    + [{"role": "user", "content": user_text}])
        r = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={"model": self.model, "messages": messages, "stream": True,
                  "temperature": 0.7, "max_tokens": 200},
            stream=True, timeout=self.timeout)
        r.raise_for_status()

        cb = ClauseBuffer()
        parts: list[str] = []
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data == "[DONE]":
                break
            delta = json.loads(data)["choices"][0].get("delta", {}).get("content") or ""
            if not delta:
                continue
            parts.append(delta)
            yield from cb.feed(delta)
        tail = cb.flush()
        if tail:
            yield tail

        self.history += [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": "".join(parts)}]
        if len(self.history) > self.history_pairs * 2:
            del self.history[:4]          # 2쌍씩 절단
```

- [ ] **Step 5: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_llm.py tests/test_clauses.py -v
```

Expected: 7 passed

- [ ] **Step 6: 실서버 수동 확인 (LLM 떠 있을 때)**

```bash
cd apps/voice_chat/voice_chat && ../../../.venv/bin/python -c "
from pathlib import Path
from llm import LLMClient
c = LLMClient(system_prompt=Path('prompt.md').read_text())
for clause in c.chat_stream('안녕! 오늘 기분 어때?'):
    print('절:', clause)"
cd -
```

Expected: 한국어 절 1~3개 출력, 사고 텍스트(`<think>` 류) 없음.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: LLM 스트리밍 클라이언트 — 절 yield + 이력 3쌍"
```

---

### Task 4: 모션 — 규칙 분류 + 비차단 재생 (TDD)

**Files:**
- Create: `apps/voice_chat/voice_chat/motion.py`, `tests/test_motion.py`

**Interfaces:**
- Consumes: reachy_mini SDK (`ReachyMini`, `RecordedMoves`)
- Produces: `classify(text: str) -> str` (범주명), `CATEGORY_MOVES: dict[str, list[str]]`, `MotionPlayer(mini, moves)` — `.play_for(category: str) -> str | None` (비차단, 재생 중이면 None), `.busy: bool`. Task 6/8이 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_motion.py`:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from motion import CATEGORY_MOVES, classify

KNOWN_MOVES = {  # 2026-07-29 RecordedMoves.list_moves() 실측 85개 중 사용분
    "welcoming1", "cheerful1", "laughing1", "enthusiastic1", "success1",
    "surprised1", "amazed1", "curious1", "inquiring1", "thoughtful1",
    "no1", "sad1", "yes1", "understanding1", "attentive1",
}

def test_모든_매핑_모션이_실재한다():
    for moves in CATEGORY_MOVES.values():
        for m in moves:
            assert m in KNOWN_MOVES, f"{m}: 데이터셋에 없는 모션"

def test_범주_분류():
    assert classify("안녕! 오늘 처음 보네") == "greet"
    assert classify("와 진짜 최고다 너무 좋아") == "joy"
    assert classify("헐 대박 말도 안 돼") == "surprise"
    assert classify("그건 좀 싫어") == "no"
    assert classify("이건 왜 이렇게 되는 거야") == "curious"

def test_물음표는_궁금으로():
    assert classify("내일 비 올까?") == "curious"

def test_매칭_실패는_수긍으로():
    assert classify("음 그렇군") == "ack"
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_motion.py -v
```

Expected: FAIL (`ModuleNotFoundError: motion`)

- [ ] **Step 3: 구현**

`apps/voice_chat/voice_chat/motion.py`:

```python
"""사용자 발화 → 감정 범주 → 모션 재생. STT 직후 LLM을 기다리지 않고 즉시 반응한다.

classify()는 교체 지점이다 — 시그니처(str -> str)만 지키면
임베딩·소형 분류기로 통째로 갈아끼울 수 있다.
"""
import random
import threading

# 이름은 전부 pollen-robotics/reachy-mini-emotions-library 실측(85개)에서 확인함
CATEGORY_MOVES: dict[str, list[str]] = {
    "greet":    ["welcoming1", "cheerful1"],
    "joy":      ["laughing1", "enthusiastic1", "success1"],
    "surprise": ["surprised1", "amazed1"],
    "curious":  ["curious1", "inquiring1", "thoughtful1"],
    "no":       ["no1", "sad1"],
    "ack":      ["yes1", "understanding1", "attentive1"],
}

# 위에서부터 먼저 맞는 규칙이 이긴다 — 인사·감정이 의문사보다 우선
_RULES: list[tuple[str, list[str]]] = [
    ("greet",    ["안녕", "반가", "하이", "헬로", "좋은 아침", "잘 잤"]),
    ("joy",      ["좋아", "신나", "재밌", "기뻐", "최고", "축하", "고마", "ㅋㅋ", "하하", "웃"]),
    ("surprise", ["헐", "대박", "진짜", "정말", "놀랐", "말도 안", "세상에"]),
    ("no",       ["싫어", "아니", "안 돼", "안돼", "못 해", "슬퍼", "우울", "힘들", "짜증"]),
    ("curious",  ["뭐", "왜", "어떻게", "궁금", "알려", "설명", "누구", "언제", "어디", "얼마"]),
]


def classify(text: str) -> str:
    for category, keywords in _RULES:
        if any(k in text for k in keywords):
            return category
    if text.rstrip().endswith("?"):
        return "curious"
    return "ack"     # 아무 반응 없는 것이 제일 어색하다 — 가벼운 끄덕임


class MotionPlayer:
    """감정 모션을 백그라운드 스레드에서 재생한다. 재생 중 요청은 버린다."""

    def __init__(self, mini, moves):
        self._mini = mini
        self._moves = moves                        # RecordedMoves
        self._available = set(moves.list_moves())  # 기동 시 1회
        self._busy = threading.Event()

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def play_for(self, category: str) -> str | None:
        """범주에 맞는 모션을 골라 비차단 재생. 시작했으면 모션 이름을 돌려준다."""
        if self._busy.is_set():
            return None
        candidates = [n for n in CATEGORY_MOVES.get(category, []) if n in self._available]
        if not candidates:
            return None
        name = random.choice(candidates)
        move = self._moves.get(name)
        self._busy.set()

        def _run() -> None:
            try:
                self._mini.play_move(move, initial_goto_duration=0.3)
            except Exception:
                pass                                # 시연 중 모션 실패로 앱이 죽지 않게
            finally:
                self._busy.clear()

        threading.Thread(target=_run, daemon=True).start()
        return name
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_motion.py -v
```

Expected: 4 passed

- [ ] **Step 5: 데몬 연동 수동 확인 (시뮬 떠 있을 때)**

```bash
cd apps/voice_chat/voice_chat && ../../../.venv/bin/python -c "
import time
from reachy_mini import ReachyMini
from reachy_mini.motion.recorded_move import RecordedMoves
from motion import MotionPlayer, classify
moves = RecordedMoves('pollen-robotics/reachy-mini-emotions-library')
with ReachyMini() as mini:
    p = MotionPlayer(mini, moves)
    name = p.play_for(classify('안녕!'))
    print('재생:', name); time.sleep(4)
    print('busy 해제:', not p.busy)"
cd -
```

Expected: 시뮬 뷰어에서 환영 모션 재생, `busy 해제: True`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: 발화 규칙분류 + 비차단 감정모션 재생"
```

---

### Task 5: TTS — say 큐 워커 (TDD)

**Files:**
- Create: `apps/voice_chat/voice_chat/tts.py`, `tests/test_tts.py`

**Interfaces:**
- Produces: `Speaker(voice="Yuna", cmd=None)` — `.speak(text: str)` (큐 적재, 즉시 반환), `.speaking: bool` (큐 적재 순간부터 True), `.wait_idle(timeout=None)`. `cmd` 주입은 테스트용(기본 `["say", "-v", voice]`). Task 6/8이 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_tts.py` — 실제 소리 없이 `cmd` 주입으로 검증:

```python
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from tts import Speaker

def test_speak은_즉시_반환하고_순차_실행된다(tmp_path):
    out = tmp_path / "log"
    # 한 줄씩 기록하는 가짜 TTS — 0.1초 걸린다
    fake = ["/bin/sh", "-c", f'sleep 0.1; echo "$0" >> {out}']
    s = Speaker(cmd=fake)
    t0 = time.time()
    s.speak("첫째"); s.speak("둘째")
    assert time.time() - t0 < 0.05          # 비차단
    assert s.speaking                        # 적재 직후부터 True (게이팅용)
    s.wait_idle(timeout=3)
    assert not s.speaking
    assert out.read_text().splitlines() == ["첫째", "둘째"]

def test_빈_문자열은_무시():
    s = Speaker(cmd=["/usr/bin/true"])
    s.speak("   ")
    assert not s.speaking
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_tts.py -v
```

Expected: FAIL (`ModuleNotFoundError: tts`)

- [ ] **Step 3: 구현**

`apps/voice_chat/voice_chat/tts.py`:

```python
"""TTS 큐 워커 — speak()는 즉시 반환, 백그라운드에서 순차 발화.

speaking 플래그는 큐 적재 순간 켜진다 — 마이크 게이팅이 소리보다
늦게 걸리면 에코가 새기 때문이다.
"""
import queue
import subprocess
import threading


class Speaker:
    def __init__(self, voice: str = "Yuna", cmd: list[str] | None = None):
        self._cmd = cmd or ["say", "-v", voice]
        self._q: queue.Queue[str] = queue.Queue()
        self._speaking = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._speaking.set()          # 적재 즉시 — 워커 시작 전에 게이팅부터
        self._q.put(text)

    @property
    def speaking(self) -> bool:
        return self._speaking.is_set()

    def wait_idle(self, timeout: float | None = None) -> None:
        """큐가 빌 때까지 대기(시연 루프의 half-duplex 동기화점)."""
        self._q.join() if timeout is None else self._join_with_timeout(timeout)

    def _join_with_timeout(self, timeout: float) -> None:
        import time
        deadline = time.time() + timeout
        while self._speaking.is_set() and time.time() < deadline:
            time.sleep(0.05)

    def _worker(self) -> None:
        while True:
            text = self._q.get()
            try:
                subprocess.run(self._cmd + [text], check=False)
            finally:
                self._q.task_done()
                if self._q.empty():
                    self._speaking.clear()
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_tts.py -v
```

Expected: 2 passed

- [ ] **Step 5: 실발화 수동 확인**

```bash
cd apps/voice_chat/voice_chat && ../../../.venv/bin/python -c "
from tts import Speaker
s = Speaker()
s.speak('안녕하세요.'); s.speak('저는 미니예요.')
s.wait_idle()"
cd -
```

Expected: 유나 음성으로 두 문장이 끊김 없이 이어진다.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: say TTS 큐 워커 — 비차단 speak + speaking 플래그"
```

---

### Task 6: 텍스트 모드 조립 — 첫 시연 가능 지점

**Files:**
- Create: `apps/voice_chat/voice_chat/demo.py`

**Interfaces:**
- Consumes: `classify`/`MotionPlayer` (Task 4), `LLMClient` (Task 3), `Speaker` (Task 5)
- Produces: `.venv/bin/python apps/voice_chat/voice_chat/demo.py --text` — 키보드 대화 데모. Task 8이 음성 모드를 추가.

- [ ] **Step 1: 구현**

`apps/voice_chat/voice_chat/demo.py`:

```python
"""음성 일상대화 데모. --text: 키보드 입력(오디오 없음, 안전 폴백)."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import LLMClient
from motion import MotionPlayer, classify
from tts import Speaker

HERE = Path(__file__).parent
FALLBACK_LINES = ["음, 잠깐 생각이 안 나요.", "다시 한 번 말해 줄래요?"]


def build(no_robot: bool = False):
    llm = LLMClient(system_prompt=(HERE / "prompt.md").read_text())
    speaker = Speaker()
    player = None
    if not no_robot:
        from reachy_mini import ReachyMini
        from reachy_mini.motion.recorded_move import RecordedMoves
        moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
        mini = ReachyMini()
        player = MotionPlayer(mini, moves)
    return llm, speaker, player


def respond(user: str, llm: LLMClient, speaker: Speaker, player) -> None:
    """한 턴: 모션 즉시 + LLM 스트림 → 절 단위 TTS. 구간 지연을 로그로 남긴다."""
    t0 = time.time()
    category = classify(user)
    name = player.play_for(category) if player else None
    print(f"  [모션 {category}/{name} +{time.time() - t0:.2f}s]")

    first_audio_logged = False
    try:
        for clause in llm.chat_stream(user):
            if not first_audio_logged:
                print(f"  [첫 절 +{time.time() - t0:.2f}s]")
                first_audio_logged = True
            print(f"미니> {clause}")
            speaker.speak(clause)
    except Exception as exc:
        print(f"  [LLM 실패: {type(exc).__name__} — 폴백]")
        speaker.speak(FALLBACK_LINES[0])
    speaker.wait_idle(timeout=30)


def text_loop(llm, speaker, player) -> None:
    print("텍스트 모드 — 빈 줄 또는 q 로 종료")
    while True:
        try:
            user = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user in ("", "q", "quit"):
            break
        respond(user, llm, speaker, player)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true", help="키보드 입력 모드")
    ap.add_argument("--no-robot", action="store_true", help="데몬 없이 (대화·TTS만)")
    args = ap.parse_args()
    llm, speaker, player = build(no_robot=args.no_robot)
    if args.text:
        text_loop(llm, speaker, player)
    else:
        try:
            from voice_loop import voice_loop      # Task 8에서 추가
        except ImportError:
            print("음성 모드는 아직 없다 — --text 를 쓰세요.")
            sys.exit(1)
        voice_loop(llm, speaker, player)
```

- [ ] **Step 2: 데몬 없이 동작 확인**

```bash
echo "안녕!" | .venv/bin/python apps/voice_chat/voice_chat/demo.py --text --no-robot
```

Expected: `[모션 greet/None ...]` → 한국어 응답 절 출력 → 유나 발화. (LLM 필요)

- [ ] **Step 3: 시뮬 통합 확인 — 3턴 대화**

시뮬(`./run-sim.sh --scene minimal`)과 LLM이 떠 있는 상태에서:

```bash
.venv/bin/python apps/voice_chat/voice_chat/demo.py --text
```

수동 3턴: `안녕!` → `요즘 뭐가 재밌어?` → `아까 내가 처음에 뭐라고 했지?`
Expected: ① 매 턴 모션 로그 +0.3s 이내 ② 3턴째에 "인사했다"류 답변(이력 동작 증명) ③ 시뮬 뷰어에서 모션 확인.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: 텍스트 모드 데모 — 모션+스트리밍 대화 조립 (M1)"
```

---

### Task 7: 에너지 VAD + 마이크 캡처 (VAD는 TDD)

**Files:**
- Create: `apps/voice_chat/voice_chat/audio_in.py`, `tests/test_vad.py`

**Interfaces:**
- Produces: `EnergyVAD(rate=16000, threshold=0.010, hangover_s=0.30, min_speech_s=0.25, pre_roll_s=0.2)` — `.feed(frame: np.ndarray) -> np.ndarray | None` (발화 종료 시 전체 발화 반환); `MicCapture(rate=16000, chunk_s=0.03)` — `.frames() -> Iterator[np.ndarray]` (float32 mono), `.close()`. Task 8이 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_vad.py` — 합성 신호만 사용, GStreamer 불필요:

```python
import sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from audio_in import EnergyVAD

RATE = 16000
FRAME = int(RATE * 0.03)            # 30ms

def frames_of(kind: str, seconds: float):
    n = int(seconds / 0.03)
    for _ in range(n):
        if kind == "silence":
            yield (np.random.randn(FRAME) * 0.001).astype(np.float32)   # 노이즈 바닥
        else:
            yield (np.random.randn(FRAME) * 0.05).astype(np.float32)    # 발화 수준

def run(vad, sequence):
    outs = []
    for kind, sec in sequence:
        for f in frames_of(kind, sec):
            r = vad.feed(f)
            if r is not None:
                outs.append(r)
    return outs

def test_발화가_한_덩어리로_잘린다():
    outs = run(EnergyVAD(), [("silence", 0.5), ("speech", 1.0), ("silence", 0.5)])
    assert len(outs) == 1
    assert len(outs[0]) >= RATE * 0.9        # 프리롤 포함 대략 1초 이상

def test_짧은_잡음은_무시된다():
    outs = run(EnergyVAD(), [("silence", 0.5), ("speech", 0.1), ("silence", 0.6)])
    assert outs == []

def test_두_발화는_두_덩어리():
    outs = run(EnergyVAD(), [("speech", 0.8), ("silence", 0.6), ("speech", 0.8), ("silence", 0.6)])
    assert len(outs) == 2
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_vad.py -v
```

Expected: FAIL (`ModuleNotFoundError: audio_in`)

- [ ] **Step 3: 구현**

`apps/voice_chat/voice_chat/audio_in.py`:

```python
"""마이크 캡처(GStreamer) + 에너지 VAD.

임계 RMS 0.010은 실측 기반 — 노이즈 바닥 0.0014, 음성 0.068 (설계문서 §2).
데몬 마이크를 쓰지 않고 직접 캡처한다 — 시뮬의 webrtcdsp가 음성을 깎는다(§9).
실기 배포 시 이 파일 전체가 SDK 미디어 백엔드로 교체된다.
"""
import collections

import numpy as np


class EnergyVAD:
    """프레임 흐름에서 발화 구간을 잘라낸다. feed()가 발화 종료 시 전체 발화를 반환."""

    def __init__(self, rate: int = 16000, threshold: float = 0.010,
                 hangover_s: float = 0.30, min_speech_s: float = 0.25,
                 pre_roll_s: float = 0.2):
        self._rate = rate
        self._threshold = threshold
        self._hangover_s = hangover_s
        self._min_speech_s = min_speech_s
        self._pre_roll: collections.deque = collections.deque(
            maxlen=max(1, int(pre_roll_s / 0.03)))
        self._voiced: list[np.ndarray] = []
        self._silence_s = 0.0

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        frame_s = len(frame) / self._rate
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))

        if not self._voiced:                       # 대기 상태
            if rms >= self._threshold:
                self._voiced = list(self._pre_roll) + [frame]   # 프리롤로 어두 보존
                self._silence_s = 0.0
            else:
                self._pre_roll.append(frame)
            return None

        self._voiced.append(frame)                 # 발화 중
        if rms >= self._threshold:
            self._silence_s = 0.0
            return None
        self._silence_s += frame_s
        if self._silence_s < self._hangover_s:
            return None

        utterance = np.concatenate(self._voiced)   # 발화 종료
        self._voiced = []
        self._pre_roll.clear()
        speech_len = len(utterance) / self._rate - self._hangover_s
        return utterance if speech_len >= self._min_speech_s else None


class MicCapture:
    """GStreamer osxaudiosrc → 16kHz mono float32 프레임 이터레이터."""

    def __init__(self, rate: int = 16000, chunk_s: float = 0.03):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        self._Gst = Gst
        self._rate = rate
        self._chunk = int(rate * chunk_s)
        self._pipe = Gst.parse_launch(
            "osxaudiosrc ! audioconvert ! audioresample "
            f"! audio/x-raw,format=F32LE,channels=1,rate={rate} "
            "! appsink name=sink max-buffers=64 drop=true sync=false")
        self._sink = self._pipe.get_by_name("sink")
        self._sink.set_property("emit-signals", False)
        self._pipe.set_state(Gst.State.PLAYING)

    def frames(self):
        """블로킹 이터레이터 — chunk_s 간격의 float32 배열을 낸다."""
        leftover = np.empty(0, dtype=np.float32)
        while True:
            sample = self._sink.emit("pull-sample")
            if sample is None:                     # EOS/종료
                return
            buf = sample.get_buffer()
            ok, info = buf.map(self._Gst.MapFlags.READ)
            if not ok:
                continue
            try:
                data = np.frombuffer(info.data, dtype=np.float32).copy()
            finally:
                buf.unmap(info)
            data = np.concatenate([leftover, data])
            while len(data) >= self._chunk:
                yield data[: self._chunk]
                data = data[self._chunk :]
            leftover = data

    def close(self) -> None:
        self._pipe.set_state(self._Gst.State.NULL)
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_vad.py -v
```

Expected: 3 passed

- [ ] **Step 5: 실마이크 수동 확인**

```bash
cd apps/voice_chat/voice_chat && ../../../.venv/bin/python -c "
import numpy as np
from audio_in import MicCapture, EnergyVAD
mic, vad = MicCapture(), EnergyVAD()
print('말해보세요 (한 문장, 자동 종료)...')
for f in mic.frames():
    utt = vad.feed(f)
    if utt is not None:
        print(f'발화 감지: {len(utt)/16000:.1f}초, 최대 진폭 {np.abs(utt).max():.3f}')
        break
mic.close()"
cd -
```

Expected: 한 문장 말하면 1~3초 발화가 감지되고 종료. (첫 실행 시 macOS 마이크 권한 팝업 가능 — 허용)

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: 에너지 VAD + GStreamer 마이크 캡처"
```

---

### Task 8: STT 클라이언트 + 음성 루프 (M2 완성)

**Files:**
- Create: `apps/voice_chat/voice_chat/stt.py`, `apps/voice_chat/voice_chat/voice_loop.py`

**Interfaces:**
- Consumes: `MicCapture`/`EnergyVAD` (Task 7), `respond()`/`build()` (Task 6), `Speaker.speaking` (Task 5), `MotionPlayer.busy` (Task 4)
- Produces: `transcribe(audio: np.ndarray, rate=16000, url=...) -> str`; `voice_loop(llm, speaker, player)` — `demo.py`가 인자 없이 실행 시 진입.

- [ ] **Step 1: STT 클라이언트 구현**

`apps/voice_chat/voice_chat/stt.py`:

```python
"""발화 오디오 → 텍스트. 로컬 STT 서버(:8090, OpenAI 호환)를 호출한다."""
import io
import wave

import numpy as np
import requests

DEFAULT_URL = "http://127.0.0.1:8090/v1/audio/transcriptions"


def transcribe(audio: np.ndarray, rate: int = 16000, url: str = DEFAULT_URL) -> str:
    """float32 mono 배열을 16-bit WAV로 조립해 전사한다. 실패·침묵이면 빈 문자열."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    try:
        r = requests.post(url, files={"file": ("utt.wav", buf.getvalue(), "audio/wav")},
                          data={"language": "ko"}, timeout=15)
        r.raise_for_status()
        return (r.json().get("text") or "").strip()
    except requests.RequestException:
        return ""
```

- [ ] **Step 2: STT 왕복 수동 확인 (STT 서버 떠 있을 때)**

```bash
cd apps/voice_chat/voice_chat && ../../../.venv/bin/python -c "
from audio_in import MicCapture, EnergyVAD
from stt import transcribe
mic, vad = MicCapture(), EnergyVAD()
print('말해보세요...')
for f in mic.frames():
    utt = vad.feed(f)
    if utt is not None:
        print('전사:', transcribe(utt)); break
mic.close()"
cd -
```

Expected: 말한 문장이 한국어로 전사되어 출력.

- [ ] **Step 3: 음성 루프 구현**

`apps/voice_chat/voice_chat/voice_loop.py`:

```python
"""음성 모드 — VAD 발화 검출 → STT → respond(). half-duplex 게이팅 포함."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audio_in import EnergyVAD, MicCapture
from demo import respond
from stt import transcribe

POST_PLAYBACK_GUARD_S = 0.3     # 재생 종료 후 잔향이 VAD에 잡히지 않게


def voice_loop(llm, speaker, player) -> None:
    mic, vad = MicCapture(), EnergyVAD()
    print("음성 모드 — 말을 걸어보세요 (Ctrl-C 종료)")
    guard_until = 0.0
    try:
        for frame in mic.frames():
            # 게이팅: TTS 재생 중, 모션(자체 사운드) 중, 직후 가드 동안 버린다
            if speaker.speaking or (player and player.busy) or time.time() < guard_until:
                vad.feed(frame * 0.0)       # 상태기계는 굴리되 무음 취급
                guard_until = max(guard_until, time.time())
                continue
            utterance = vad.feed(frame)
            if utterance is None:
                continue
            t0 = time.time()
            text = transcribe(utterance)
            print(f"나(STT +{time.time() - t0:.2f}s)> {text}")
            if not text:
                continue                     # 침묵·잡음 — 다시 듣기
            respond(text, llm, speaker, player)
            guard_until = time.time() + POST_PLAYBACK_GUARD_S
    except KeyboardInterrupt:
        pass
    finally:
        mic.close()
```

- [ ] **Step 4: E2E 수동 확인 — SLO 판정**

데몬·LLM·STT 세 서버가 다 떠 있는 상태에서(`./scripts/check_env.sh` 전부 OK):

```bash
.venv/bin/python apps/voice_chat/voice_chat/demo.py
```

낭독 5문장: `안녕!` / `오늘 날씨 어때?` / `재밌는 얘기 해줘` / `헐 진짜?` / `고마워, 잘 있어`
Expected: ① 5회 모두 전사·응답·모션 동작 ② 로그의 `[모션 +N s]` ≤ 0.8, `[첫 절 +N s]` + say 개시 ≤ 2.0 ③ 로봇 발화가 재전사되는 에코 루프 없음.
SLO 초과 시: `docs/latency-m0.md`에 실측치 추가 기록하고 사용자에게 보고(시연은 텍스트 모드 폴백 가능).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: STT 클라이언트 + 음성 루프 — M2 완성"
```

---

### Task 9: 시연 런북 — 내일 오전용

**Files:**
- Create: `docs/demo-runbook.md`

**Interfaces:**
- Consumes: 전체 앱, `scripts/check_env.sh`
- Produces: 시연 절차 문서 (사용자가 아침에 그대로 따라 하는 체크리스트)

- [ ] **Step 1: 런북 작성**

`docs/demo-runbook.md`:

```markdown
# 경영진 시연 런북 (Reachy Mini 음성 일상대화)

## 시작 30분 전 — 기동 순서 (터미널 3개)

1. `llama reach-llm`                      # LLM :8080 + 예열
2. `.venv/bin/python stt_server.py`       # STT :8090 (예열 로그 READY 확인)
3. `./run-sim.sh --scene minimal`         # 시뮬 데몬 :8000 (뷰어 창 확인)
4. `./scripts/check_env.sh`               # ← 4개 전부 OK 확인
5. 리허설 1회: `.venv/bin/python apps/voice_chat/voice_chat/demo.py` 로 2~3문장

주의: 시스템 볼륨 70% 이상, 조용한 방(에너지 VAD는 소음에 민감), 전원 연결.

## 시연 시나리오 (3분)

| 순서 | 말할 것 | 보여주는 것 |
|---|---|---|
| 1 | "안녕!" | 즉시 환영 모션(≤0.8s) + 음성 인사 — **반응 속도** |
| 2 | "요즘 뭐가 재밌어?" | 자유 대화 — **sLLM 일상대화** |
| 3 | "아까 내가 처음에 뭐라고 했지?" | 이력 회상 — **문맥 유지** |
| 4 | "헐 대박!" | 놀람 모션 — **감정 표현** |
| 5 | "고마워, 잘 있어" | 마무리 |

## 확장성·기대효과 멘트 (질문 대비)

- 전 구간 로컬(사내망 밖으로 데이터 0) — 프라이버시·비용 통제.
- 클라우드 LLM 전환은 base_url 교체 하나 — 품질/비용을 운영 중 선택.
- 모션·성격·능력이 각각 독립 교체 지점 — MCP 도구 연결로 사내 시스템 조작 확장.
- 시뮬→실기 배포는 환경변수 3개(오디오 백엔드·TTS·서버 IP) — 검증 자산 그대로 이전.
- 실측 지연: docs/latency-m0.md 참조 (발화 종료→응답 시작 N초).

## 장애 대응 사다리

| 증상 | 대응 |
|---|---|
| 마이크 인식 불량·소음 | `demo.py --text` 로 전환 (키보드 입력, 나머지 동일) |
| LLM 다운 | 모션+폴백 대사는 계속 동작 — 재기동 `llama reach-llm` |
| 데몬 다운 | `demo.py --text --no-robot` (대화·음성만) + 시뮬 재기동 |
| 에코로 자기 말 인식 | 볼륨 낮추기 (게이팅 가드 0.3s 내장) |
```

- [ ] **Step 2: 런북 전체 리허설**

런북 순서 그대로 콜드 스타트에서 1회 통주. 막히는 지점을 런북에 반영.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "docs: 경영진 시연 런북"
```

---

## Self-Review 결과

- **스펙 커버리지**: M0(Task 1)·M1(Task 2~6)·M2(Task 7~8) 모두 태스크 존재. 시연 요구(확장성·기대효과 제시)는 Task 9 런북이 담당. MCP·스킬팩·Piper·원격 어댑터는 합의대로 범위 밖(인터페이스 자리만 유지).
- **플레이스홀더**: 전 코드 블록 실행 가능한 완성 코드. 모션 이름·API 시그니처는 실측/실파일 확인값.
- **타입 일관성**: `classify(str)->str`, `play_for(str)->str|None`, `chat_stream(str)->Iterator[str]`, `feed(ndarray)->ndarray|None`, `transcribe(ndarray)->str` — Task 간 시그니처 상호 참조 일치 확인.
- **리스크 잔존**: ① 앱 어시스턴트 비대화식 실행이 막히면 사용자 터미널 실행으로 우회(Task 0 Step 3에 명시) ② M0 실측이 2초를 넘으면 Task 1 Step 3 분기 적용.
