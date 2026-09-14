# 2대 팟캐스트 시연 강화 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-09-14 리뷰에서 확인된 "시연을 멈추게 하는 버그" 전부(A)와 팟캐스트 진행 품질 셋(B1 모션·B2 관람객 창구 멘트·B3 질문 지연 은닉)을 고치고, 큐시트를 책상 위 두 로봇의 대담 프레임으로 다시 쓴다.

**Architecture:** 무대감독(`stage/`)은 노트북, 앱(`apps/voice_chat`)은 로봇에 올라간다. 발화마다 감독이 `seq` 를 붙이고 로봇이 되돌려 유령 종료 보고를 가른다. 사회자 청취 게이트는 STT 결과 시점이 아니라 **캡처 시점**에서 닫는다. 관람객 창구와 질문 응답은 사회자 고정 멘트로 열고, 그 멘트가 흐르는 동안 LLM 이 돈다(락 밖).

**Tech Stack:** Python 3.12 (`.venv/bin/python`) / `websockets` sync API / PyYAML / pytest. 추론 3종은 PC 에 남는다.

**Spec:** `docs/superpowers/specs/2026-09-11-two-robot-mc-docent-design.md` + 리뷰 통합본(이 계획 §0). 사용자 결정(2026-09-14 Q&A): 범위 A 전부 + B1~B3, A1 은 캡처 단 게이팅, 관람객 창구는 사회자 고정 멘트, 큐시트는 대담 프레임.

## Global Constraints

- **인터프리터는 `.venv/bin/python`(3.12.13) 하나뿐이다.** 시스템 `python3`(3.14)를 쓰지 않는다.
- **테스트 명령은 `.venv/bin/python -m pytest tests/ -q`** 다. 착수 시점 **445 passed**. 회귀를 내면 안 된다.
- **진입점은 `main.py`(`ReachyMiniApp`) 하나. 대화 로직은 `session.py` 하나.** 진입점에 복사하지 않는다.
- **앱이 읽는 운영 설정은 `config.get()` 사다리를 탄다.** `os.environ` 직독은 시뮬에서만 동작한다.
- **실패는 소리 내서 실패한다.** 폴백·강등·거부는 반드시 경고 한 줄을 남긴다.
- **`stage_client.py` 는 `stage/` 를 import 하지 않는다.** 규약을 바꾸면 `stage/protocol.py` 와 짝으로 고친다 (`tests/test_deployment_contract.py` 가 고정).
- **새 서드파티 의존성을 추가하지 않는다.**
- **테스트 함수 이름은 한국어.** `@pytest.mark.parametrize` 는 케이스 수만큼 센다.
- **버그를 하나 잡을 때마다 `docs/lessons.md` 에 증상 → 원인 → 규칙 + 박제 테스트 이름을 적는다.** 각 태스크의 커밋에 포함한다.
- **커밋 메시지 끝에** `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` 를 붙인다.
- 실기에 없는 것(시뮬 좌표·mjpython)에 기대지 않는다. 시선(`gaze`)은 이번 범위 밖(no-op 유지).

---

## §0 이번 라운드가 잡는 것 (리뷰 통합본 요약)

| # | 증상 | 자리 | 태스크 |
|---|---|---|---|
| A2 | 콘솔 `r`/`a→s` 가 같은 cue_id 를 재발행 → 중단된 발화의 늦은 `speaking_ended` 가 통과 → 두 로봇 동시 발화 | machine/director/client | 1 |
| A7a | `_begin_cue` 가 `speak()` 검증 전에 이력·생성 스레드를 건드림 (`s` 두 번) | director | 2 |
| A7b | 콘솔 `n` 이 `on_heard("다음")` 경유라 IDLE/발화 중 거부 | console/director | 2 |
| A4 | `UnitMismatch` 가 핸들러 밖으로 새어 traceback 폭풍, 시연은 시작됨 | server/director | 3 |
| A5a | 재접속 뒤 마이크 상태 재동기화 없음 → 청취 사망 | director | 3 |
| A8b | 와이어 필드 타입 무검증 (`text: null`, `role: [..]`) → 연결 1011 → 1인 모드 강등 | server | 3 |
| A8a | 큐시트 `mc: 123`/`mc:` 가 통과 → `_estimate` TypeError → 감독 wedge | cues | 4 |
| A7c | `stage-env.sh` 의 `set -eu` 가 source 한 셸을 죽임 | scripts | 4 |
| A9 | 클라이언트가 핸들러 예외를 연결 끊김으로 오판 → 재접속 → 1인 모드 강등 | stage_client | 5 |
| A10 | `on_abort` 가 `player.cancel()` 을 안 함 | main | 5 |
| A1 | 사회자 STT 지연 구멍 → 도슨트 마지막 문장을 관람객 발화로 → 자기목소리 루프 | voice_loop/main | 6 |
| A5b | 청취 스레드가 죽어도 `has_listener()` True / 제너레이터 예외 후 조용히 종료 | main/voice_loop | 6 |
| A6 | 10초 넘는 발화가 오면 VAD 임계가 음성×3 으로 튀어 다음 질문 못 들음 | audio_in | 7 |
| A3 | 발화 뒤 모션 사운드 → `task_done()` 2회 → TTS 워커 사망 → 마이크 영구 닫힘 | tts | 8 |
| B1 | 2대 모드 `say` 의 category `'neutral'` 이 모션 표에 없어 모션 None | session/motion | 9 |
| B2 | 관람객에게 "말해도 된다" 신호 없음 — 사회자 받아치기(`mc_after`) | cues/director | 10 |
| B3 | 질문 뒤 정적 + `_answer` 가 락 쥔 채 LLM — 사회자 확인 멘트로 은닉 | director/__main__ | 11 |
| B4 | 사회자 대사 8/19 위치 지시어, 전부 한 틀 → 대담 프레임 재작성 + `mc_after` | data/cues.yaml | 12 |
| 문서 | 설계·운영 문서를 코드와 맞춘다 | docs | 13 |

---

## File Structure

**수정 — 무대감독(노트북)**

| 파일 | 변경 |
|---|---|
| `stage/machine.py` | `seq` 발급·대조. `speak()` 이 `say` 에 `seq` 를 싣고, `on_speaking_ended(..., seq=)` 가 대조한다 |
| `stage/director.py` | `on_speaking_started/ended(role, cue_id, seq)`, `next()`, `reject()`, `on_connect` 재동기화, `_begin_cue` 순서, `mc_after` 받아치기, 질문 확인 멘트 + 락 밖 생성 |
| `stage/server.py` | `UnitMismatch` 포착, `role`/`text`/`cue_id`/`seq` 타입 검증 |
| `stage/console.py` | `n` → `abort()`+`next()` |
| `stage/cues.py` | 필드 타입 검증, 선택 필드 `mc_after`, `QA_ACK_LINES` |
| `stage/__main__.py` | 시스템 프롬프트에 음성 출력 규칙 |
| `data/cues.yaml` | 대담 프레임 사회자 대사 19개 + `mc_after` 19개 |
| `scripts/stage-env.sh` | `set -eu` 제거 |

**수정 — 로봇 앱**

| 파일 | 변경 |
|---|---|
| `apps/voice_chat/voice_chat/stage_client.py` | `say.seq` 전달, `speaking_started/ended(cue_id, seq)`, 핸들러 예외 분리 |
| `apps/voice_chat/voice_chat/main.py` | `SayRunner`/`speak_one` 에 `seq`, `mic_open` 을 `voice_loop` 에 전달, 청취 스레드 생존 감시, `on_abort` 가 모션도 끊음 |
| `apps/voice_chat/voice_chat/voice_loop.py` | `mic_open` 게이트(캡처 단), 제너레이터 재생성 |
| `apps/voice_chat/voice_chat/audio_in.py` | 과길이 발화: 바닥이 부트스트랩됐으면 STT 로 넘긴다 |
| `apps/voice_chat/voice_chat/tts.py` | 워커 `task_done` 이중 호출 제거 |
| `apps/voice_chat/voice_chat/session.py` | `speak()` 기본 category 를 `classify(text)` 로 |
| `apps/voice_chat/voice_chat/motion.py` | 모르는 category 는 경고 |

**테스트** — 기존 파일에 더한다: `tests/test_stage_machine.py`, `test_stage_director.py`, `test_stage_console.py`, `test_stage_server.py`, `test_stage_client.py`, `test_stage_cues.py`, `test_stage_env_script.py`, `test_stage_role.py`, `test_barge_in.py`, `test_vad.py`, `test_session_speak.py`, `test_motion.py`, `test_deployment_contract.py`.

---

### Task 1: 발화 시퀀스(`seq`) — 콘솔 `r`/`a→s` 동시 발화를 막는다

**Files:**
- Modify: `stage/machine.py:52-80` (`speak`), `:82-95` (`on_speaking_ended`)
- Modify: `stage/director.py:203-260` (`on_speaking_started`, `on_speaking_ended`)
- Modify: `stage/server.py:126-134` (`_dispatch`)
- Modify: `apps/voice_chat/voice_chat/stage_client.py:60-66, 150-152`
- Modify: `apps/voice_chat/voice_chat/main.py:184-228` (`SayRunner`), `:251-270` (`speak_one`)
- Test: `tests/test_stage_machine.py`, `tests/test_stage_director.py`, `tests/test_stage_console.py`, `tests/test_stage_server.py`, `tests/test_stage_client.py`, `tests/test_stage_role.py`, `tests/test_deployment_contract.py`

**Interfaces:**
- Produces: `TurnMachine.seq: int` (마지막 `speak()` 의 번호, 시작 0), `TurnMachine.speak(role, cue_id, text, gaze=None) -> list[Command]` 의 `say` 필드에 `seq: int`, `TurnMachine.on_speaking_ended(role, cue_id, listener="mc", seq=None) -> list[Command]` (seq 불일치는 유령), `Director.on_speaking_started(role, cue_id, seq)`, `Director.on_speaking_ended(role, cue_id, seq)`, `Handlers.on_say(cue_id: str, text: str, seq: int | None)`, `StageClient.speaking_started(cue_id, seq)`, `StageClient.speaking_ended(cue_id, seq)`.
- 이후 태스크는 전부 이 시그니처를 쓴다. 로봇 → 감독 `speaking_started`/`speaking_ended` 메시지에 `seq` 필드가 추가된다(메시지 종류 9종은 그대로).

- [x] **Step 1: 상태기계 실패 테스트**

`tests/test_stage_machine.py` 끝에 추가:

```python
def test_say_마다_seq_가_하나씩_오른다():
    m = TurnMachine()
    a = [c for c in m.speak("mc", "c1", "…") if c.type == "say"][0]
    m.on_speaking_ended("mc", "c1", seq=a.fields["seq"])
    b = [c for c in m.speak("mc", "c1", "…") if c.type == "say"][0]
    assert b.fields["seq"] == a.fields["seq"] + 1
    assert m.seq == b.fields["seq"]


def test_같은_큐라도_낡은_seq_의_종료_보고는_유령이다():
    """콘솔 `r`(abort→start) 뒤에 중단된 발화의 늦은 종료 보고가 온다.
    cue_id 는 같으므로 seq 로만 가른다 — 못 가르면 사회자가 다시 말하는
    중에 도슨트가 시작해 두 로봇이 동시에 말한다(리뷰 A2)."""
    m = TurnMachine()
    old = [c for c in m.speak("mc", "c1", "…") if c.type == "say"][0].fields["seq"]
    m.abort()
    m.speak("mc", "c1", "…")   # 같은 cue_id 재발행
    assert m.on_speaking_ended("mc", "c1", seq=old) == []
    assert m.state is State.MC_SPEAKING
    assert m.on_speaking_ended("mc", "c1", seq=m.seq) != []
    assert m.state is State.LISTENING


def test_seq_없는_종료_보고는_유령이다():
    m = TurnMachine()
    m.speak("mc", "c1", "…")
    assert m.on_speaking_ended("mc", "c1") == []
```

기존 테스트 중 `on_speaking_ended` 를 부르는 곳(66·78·99·107·141행 근처)은 `seq=m.seq` 를 넘기도록 고친다. 무작위 테스트(141행)는 `ended` 분기를 다음으로 바꾼다:

```python
            elif op == "ended":
                cmds = m.on_speaking_ended(
                    rng.choice(["mc", "docent"]), f"c{rng.randint(0, 3)}", listener,
                    seq=rng.choice([m.seq, m.seq - 1]),
                )
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_machine.py -q`
Expected: 새 테스트 3개 FAIL (`KeyError: 'seq'` / `TypeError: unexpected keyword 'seq'`)

- [x] **Step 3: 상태기계 구현**

`stage/machine.py` — `__init__` 에 `self.seq = 0` 추가. `speak()` 에서 상태를 옮긴 뒤:

```python
        self.state = _SPEAKING_STATE[role]
        self.speaking_role = role
        self.cue_id = cue_id
        # 발화마다 번호를 매긴다. 콘솔 `r`(abort→start)은 **같은 cue_id** 를
        # 다시 발행하므로 (role, cue_id) 만으로는 중단된 발화의 늦은 종료 보고와
        # 새 발화의 종료 보고를 못 가른다 — 그 유령이 통과하면 사회자가 다시
        # 말하는 중에 도슨트가 시작한다(리뷰 A2, 불변식 ② 위반).
        self.seq += 1
```

`say` Command 필드에 `"seq": self.seq` 추가. `on_speaking_ended` 시그니처와 판정:

```python
    def on_speaking_ended(
        self, role: str, cue_id: str, listener: str = "mc", seq: int | None = None
    ) -> list[Command]:
        if role != self.speaking_role or cue_id != self.cue_id or seq != self.seq:
            return []  # 늦게 도착한 유령 메시지 — 상태를 건드리지 않는다
        return self._to_listening(listener)
```

`is_current(role, cue_id, seq) -> bool` 를 추가해 같은 조건을 돌려주고, `on_speaking_ended` 가 이것을 쓴다(감독의 `on_speaking_started` 도 같은 규칙을 써야 한다 — 두 파일에 규칙을 두 번 적지 않는다).

- [x] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_machine.py -q`
Expected: 전부 PASS

- [x] **Step 5: 감독·콘솔·서버 실패 테스트**

`tests/test_stage_director.py` 의 `Harness` 에 헬퍼를 넣는다:

```python
    def seq_of(self, cue_id):
        """마지막으로 보낸 그 큐의 say 가 받은 seq."""
        return [f["seq"] for _, t, f in self.sent if t == "say" and f["cue_id"] == cue_id][-1]

    def ended(self, role, cue_id):
        self.d.on_speaking_ended(role, cue_id, self.seq_of(cue_id))

    def started(self, role, cue_id):
        self.d.on_speaking_started(role, cue_id, self.seq_of(cue_id))
```

기존 호출을 기계적으로 바꾼다 (`clear()` 뒤에 호출하는 테스트가 있으므로 `seq_of` 는 `sent` 가 아니라 **누적 목록**을 봐야 한다 — `Harness.__init__` 에 `self.all_sent = []` 를 두고 `send` 람다가 둘 다에 append, `seq_of` 는 `all_sent` 를 본다):

```bash
sed -i '' -E 's/h\.d\.on_speaking_ended\(("[a-z]+"), ("[^"]+")\)/h.ended(\1, \2)/g; s/h\.d\.on_speaking_started\(("[a-z]+"), ("[^"]+")\)/h.started(\1, \2)/g' tests/test_stage_director.py tests/test_stage_console.py
```

(콘솔 테스트의 `Harness` 에도 같은 `all_sent`/`seq_of`/`ended` 를 넣는다.) 유령 테스트(`test_유령_발화_시작_보고는…`, `test_유령_발화_종료는…`)는 seq 를 일부러 틀리게 준다: `h.d.on_speaking_ended("mc", "c1", 999)`.

새 테스트 — `tests/test_stage_console.py`:

```python
def test_r_로_다시_시작한_뒤_중단된_발화의_늦은_종료_보고는_도슨트를_깨우지_않는다():
    """리뷰 A2 — 예전에는 여기서 도슨트 say 가 나가 두 로봇이 동시에 말했다."""
    h = Harness()
    h.run(["s", "r", "q"])
    old_seq = [f["seq"] for _, t, f in h.all_sent if t == "say"][0]
    n_before = len(h.says())
    h.d.on_speaking_ended("mc", "c1", old_seq)     # 중단된 발화의 늦은 보고
    assert len(h.says()) == n_before, "유령 종료로 도슨트가 시작됐다"
    assert any("유령" in w for w in h.warnings)
    h.ended("mc", "c1")                              # 진짜 보고
    assert h.says()[-1][0] == "docent"
```

`tests/test_stage_server.py` — `ended()` 헬퍼에 seq 를 넣고, 호출부는 받은 `say` 의 seq 를 쓴다:

```python
def ended(ws, cue_id="c1", seq=None):
    ws.send(json.dumps({"type": "speaking_ended", "cue_id": cue_id, "seq": seq}))


def seq_in(msgs):
    return [m for m in msgs if m["type"] == "say"][0]["seq"]
```

기존 `ended(mc)` 호출은 `ended(mc, seq=seq_in(mc_msgs))` 로 바꾼다(`start_and_drain` 의 반환값 이름을 확인해 그 변수를 쓴다). `tests/test_deployment_contract.py` 의 왕복 테스트(`speaking_started/ended` 를 `protocol.decode` + `server._dispatch` 로 미는 곳)는 `client.speaking_ended("c1", 1)` 로 seq 를 실어 보내고 감독 상태가 LISTENING 으로 바뀌는지 단언한다 — 필드 이름이 한쪽에서만 바뀌면 여기서 깨진다.

- [x] **Step 6: 클라이언트·앱 실패 테스트**

`tests/test_stage_client.py` — `collector()` 의 `on_say` 람다를 `lambda cue_id, text, seq: got.append(("say", cue_id, text, seq))` 로 바꾸고, 기존 `gaze` 를 단언하던 두 테스트를 seq 로 바꾼다:

```python
def test_say_를_받으면_seq_와_함께_핸들러로_넘긴다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕", "seq": 7}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", 7) in got


def test_seq_가_없는_say_도_받는다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕"}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", None) in got


def test_발성_경계_보고에_seq_를_되돌려준다():
    ws = FakeWS(close_when_empty=False)
    c = StageClient("ws://x", "mc", collector()[1], warn=lambda m: None)
    c._ws = ws
    c.speaking_started("c1", 7)
    c.speaking_ended("c1", 7)
    assert ws.sent[-2:] == [
        {"type": "speaking_started", "cue_id": "c1", "seq": 7},
        {"type": "speaking_ended", "cue_id": "c1", "seq": 7},
    ]
```

`tests/test_stage_role.py` 의 `SayRunner` 테스트들은 `speak_one(cue_id, text, gaze)` 를 `speak_one(cue_id, text, seq)` 로, `r.on_say("c1", "긴 대사", None)` 은 그대로 둔다(셋째 인자가 seq 가 됐을 뿐이다).

- [x] **Step 7: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py tests/test_stage_console.py tests/test_stage_server.py tests/test_stage_client.py tests/test_stage_role.py tests/test_deployment_contract.py -q`
Expected: seq 관련 테스트 FAIL, 나머지는 시그니처 오류로 FAIL 가능

- [x] **Step 8: 감독·서버·클라이언트·앱 구현**

`stage/director.py`:

```python
    def on_speaking_started(self, role: str, cue_id: str, seq: int | None) -> None:
        with self._lock:
            if not self._machine.is_current(role, cue_id, seq):
                self._warn_ghost("speaking_started", role, cue_id, seq)
                return
            self._deadline = self._now() + self._speak_budget

    def on_speaking_ended(self, role: str, cue_id: str, seq: int | None) -> None:
        with self._lock:
            cmds = self._machine.on_speaking_ended(role, cue_id, self._who("mc"), seq=seq)
            if not cmds:
                self._warn_ghost("speaking_ended", role, cue_id, seq)
                return
            ...  # 이하 기존 그대로

    def _warn_ghost(self, kind: str, role: str, cue_id: str, seq) -> None:
        self._warn(
            f"[{role}] 유령 {kind}({cue_id!r}, seq={seq}) — 지금 말하는 것은 "
            f"{self._machine.speaking_role}/{self._machine.cue_id!r}/seq={self._machine.seq} 다. 버린다"
        )
```

`stage/server.py::_dispatch` — `speaking_started`/`speaking_ended` 분기에 `msg.get("seq")` 를 셋째 인자로 넘긴다.

`apps/voice_chat/voice_chat/stage_client.py`:

```python
    def speaking_started(self, cue_id: str, seq: int | None) -> None:
        self._send("speaking_started", cue_id=cue_id, seq=seq)

    def speaking_ended(self, cue_id: str, seq: int | None) -> None:
        self._send("speaking_ended", cue_id=cue_id, seq=seq)
```

`_on_raw` 의 `say` 분기: `self._h.on_say(msg.get("cue_id", ""), msg.get("text", ""), msg.get("seq"))`. `Handlers.on_say` 주석을 `(cue_id, text, seq)` 로 고친다 — `gaze` 는 `say` 에 실려 온 적이 없다(감독은 별도 `gaze` 지시를 보낸다).

`apps/voice_chat/voice_chat/main.py` — `SayRunner.on_say(self, cue_id, text, seq=None)` 이 워커에 `(cue_id, text, seq)` 를 넘기고, `speak_one(cue_id, text, seq)` 의 finally 는 `client.speaking_started(cue_id, seq)` / `client.speaking_ended(cue_id, seq)` 를 부른다.

- [x] **Step 9: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures, 445 + 새 테스트 수

- [x] **Step 10: lessons.md + 커밋**

`docs/lessons.md` 「무대감독」 절에 추가:

```markdown
### 유령 판정의 열쇠는 **발화 단위**여야 한다 — 큐 id 는 재발행된다
- **증상**(리뷰 A2, 2026-09-14): 콘솔 `r`(abort→start) 뒤 중단된 발화의 늦은 `speaking_ended` 가
  통과해 사회자가 같은 대사를 다시 말하는 중에 도슨트가 시작했다 — 두 로봇이 동시에 말한다.
- **원인**: 유령 필터가 `(role, cue_id)` 만 봤는데 `r` 은 **같은 cue_id** 를 다시 발행한다.
- **규칙**: 재시도가 있는 곳의 상관관계 키는 요청 단위 번호(`seq`)다. 이름·id 는 재사용된다.
- 박제: `tests/test_stage_machine.py::test_같은_큐라도_낡은_seq_의_종료_보고는_유령이다`,
  `tests/test_stage_console.py::test_r_로_다시_시작한_뒤_중단된_발화의_늦은_종료_보고는_도슨트를_깨우지_않는다`.
```

```bash
git add stage/machine.py stage/director.py stage/server.py apps/voice_chat/voice_chat/stage_client.py apps/voice_chat/voice_chat/main.py tests/ docs/lessons.md
git commit -m "fix(stage): 발화마다 seq 를 붙여 r/a→s 뒤의 유령 종료 보고를 가른다"
```

---

### Task 2: `_begin_cue` 부작용 순서 + 콘솔 `n`

**Files:**
- Modify: `stage/director.py:302-330` (`_begin_cue`), `:188-200` (`on_heard`), `previous()` 옆
- Modify: `stage/console.py:59-63`
- Test: `tests/test_stage_director.py`, `tests/test_stage_console.py`

**Interfaces:**
- Produces: `Director.next() -> None` (IDLE/LISTENING 에서 다음 큐 시작, 마지막이면 경고; 발화 중이면 `TurnError`). `on_heard` 의 진행 분기는 내부적으로 같은 `_next_locked()` 를 쓴다.

- [x] **Step 1: 실패 테스트**

`tests/test_stage_director.py`:

```python
def test_발화_중에_start_를_다시_불러도_이력과_생성이_오염되지_않는다():
    """운영자의 `s` 두 번. 거절은 하되 **부작용이 없어야** 한다(리뷰 A7a)."""
    from stage.machine import TurnError
    h = Harness()
    h.d.start()
    with pytest.raises(TurnError):
        h.d.start()
    assert [l["content"] for l in h.d.history] == ["사회자: 사회자 첫 대사"]
    assert len(h.gen_calls) == 1
    assert not any("버려졌다" in w for w in h.warnings)


def test_next_는_IDLE_에서도_다음_큐로_간다():
    h = Harness()
    h.d.start()
    h.d.abort()
    h.clear()
    h.d.next()
    assert h.says() == [("mc", "사회자 둘째 대사")]


def test_next_는_발화_중이면_거절한다():
    from stage.machine import TurnError
    h = Harness()
    h.d.start()
    with pytest.raises(TurnError):
        h.d.next()
```

`tests/test_stage_console.py`:

```python
def test_a_뒤에_n_을_누르면_다음_큐로_간다():
    """리뷰 A7b — 예전엔 `n` 이 on_heard("다음") 경유라 IDLE 에서 버려졌다."""
    h = Harness()
    h.run(["s", "a", "n", "q"])
    assert h.says()[-1] == ("mc", "사회자 둘째 대사")


def test_발화_중_n_은_중단하고_다음으로_간다():
    h = Harness()
    h.run(["s", "n", "q"])
    assert h.says()[-1] == ("mc", "사회자 둘째 대사")
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py tests/test_stage_console.py -q -k "start_를_다시\|next\|n_을_누르면\|발화_중_n"`
Expected: FAIL

- [x] **Step 3: 구현**

`stage/director.py`:

```python
    def _begin_cue(self, cue: Cue) -> None:
        # **먼저 거절한다.** 발화 중이면 speak() 가 TurnError 를 던지는데, 그 전에
        # 이력에 사회자 대사를 넣고 생성 스레드를 갈아끼우면 거절된 start() 가
        # 부작용을 남긴다 — 운영자의 `s` 두 번이 이력을 오염시키고 진행 중인
        # 도슨트 생성을 버린 뒤 LLM 을 다시 불렀다(리뷰 A7a).
        if self._machine.state in SPEAKING:
            raise TurnError(
                f"{self._machine.speaking_role} 가 아직 말하는 중이다(큐 {self._machine.cue_id})"
            )
        self._remember(f"사회자: {cue.mc}")
        ...  # 이하 기존 그대로

    def next(self) -> None:
        """다음 큐로 간다 — 콘솔 `n` 과 관람객의 진행 신호가 같은 길을 탄다."""
        with self._lock:
            self._next_locked()

    def _next_locked(self) -> None:
        if self._machine.state in SPEAKING:
            raise TurnError(f"{self._machine.speaking_role} 가 아직 말하는 중이다 — 먼저 a 로 멈춘다")
        nxt = self._sheet.advance()
        if nxt is None:
            self._warn("마지막 큐다 — 더 진행할 곳이 없다")
            return
        self._begin_cue(nxt)
```

`on_heard` 의 `is_advance` 분기는 `self._next_locked(); return` 으로 바꾼다. `from stage.machine import SPEAKING, TurnError` 를 import 한다. `stage/console.py` 의 `n`:

```python
    elif cmd == "n":
        director.abort()
        director.next()
```

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 5: lessons.md + 커밋**

```markdown
### 거절할 요청은 **부작용 전에** 거절한다
- **증상**(리뷰 A7a): `s` 두 번 → 두 번째는 거절되는데 이력에 사회자 대사가 두 번 들어가고
  진행 중이던 도슨트 생성이 "다음 큐로 넘어갔다" 는 엉뚱한 경고와 함께 버려졌다.
- **원인**: `_begin_cue` 가 이력 추가·세대 증가·스레드 기동을 한 뒤에야 `speak()` 가 검증했다.
- **규칙**: 검증 → 부작용. 거절 경로는 상태를 건드리지 않는다. 콘솔 명령은 STT 판정기를
  거치지 않는다(`n` 이 `on_heard("다음")` 을 타면 판정기 조정이 콘솔을 끊는다 — A7b).
- 박제: `tests/test_stage_director.py::test_발화_중에_start_를_다시_불러도_이력과_생성이_오염되지_않는다`,
  `tests/test_stage_console.py::test_a_뒤에_n_을_누르면_다음_큐로_간다`.
```

```bash
git add stage/director.py stage/console.py tests/test_stage_director.py tests/test_stage_console.py docs/lessons.md
git commit -m "fix(stage): start 를 부작용 전에 거절하고 콘솔 n 이 IDLE 에서도 진행하게 한다"
```

---

### Task 3: 역할 검증 실패·재접속·와이어 타입 — 서버와 감독의 방어선

**Files:**
- Modify: `stage/server.py:52-95` (`handler`), `:112-140` (`_dispatch`)
- Modify: `stage/director.py:146-168` (`on_connect`/`on_disconnect`), `on_hello`, `start`
- Test: `tests/test_stage_server.py`, `tests/test_stage_director.py`

**Interfaces:**
- Produces: `Director.reject(role: str, reason: str)` (그 역할을 거부 목록에 넣고 경고), `Director.rejected: set[str]`, `Director.start()` 는 거부 목록이 비어 있지 않으면 `TurnError`. `Director.on_connect(role)` 가 현재 상태에 맞는 `mic` 지시를 그 로봇에게 다시 보낸다. `Director.on_disconnect(role)` 가 LISTENING 이면 남은 리스너의 마이크를 연다.

- [x] **Step 1: 실패 테스트 — 감독**

`tests/test_stage_director.py`:

```python
def test_거부된_역할이_있으면_start_가_거절한다():
    from stage.machine import TurnError
    h = Harness(expect_units={"mc": "AAA"})
    with pytest.raises(UnitMismatch):
        h.d.on_hello("mc", "BBB", "1.9.0")
    h.d.reject("mc", "뒤바뀜")
    with pytest.raises(TurnError, match="mc"):
        h.d.start()
    h.d.on_hello("mc", "AAA", "1.9.0")   # 맞는 로봇이 붙으면 풀린다
    h.d.start()
    assert h.says() == [("mc", "사회자 첫 대사")]


def test_듣는_중에_다시_붙은_리스너에게_마이크를_다시_연다():
    """리뷰 A5a — 앱 재기동/WiFi 순단 뒤 mic_open 이 비어 있는 채로 남아 청취가 죽었다."""
    h = Harness()
    h.d.on_connect("mc"); h.d.on_connect("docent")
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    assert h.d.state is State.LISTENING
    h.d.on_disconnect("mc")
    h.clear()
    h.d.on_connect("mc")
    assert h.mics() == [("mc", True)]


def test_말하는_중에_다시_붙은_로봇에게는_마이크를_닫는다():
    h = Harness()
    h.d.on_connect("mc"); h.d.on_connect("docent")
    h.d.start()
    h.clear()
    h.d.on_disconnect("docent"); h.d.on_connect("docent")
    assert ("docent", False) in h.mics()
    assert ("docent", True) not in h.mics()


def test_듣는_중에_리스너가_끊기면_남은_로봇의_마이크를_연다():
    h = Harness()
    h.d.on_connect("mc"); h.d.on_connect("docent")
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    h.clear()
    h.d.on_disconnect("mc")
    assert h.mics() == [("docent", True)]
```

- [x] **Step 2: 실패 테스트 — 서버(실제 소켓)**

`tests/test_stage_server.py`:

```python
@pytest.fixture
def strict_server():
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner")])
    warnings: list[str] = []
    s = StageServer(sheet, generate=lambda b, h: "도슨트 대사",
                    expect_units={"mc": "AAA"}, warn=warnings.append)
    s.warnings = warnings
    from websockets.sync.server import serve as ws_serve
    srv = ws_serve(s.handler, "127.0.0.1", 0)
    s.port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield s
    srv.shutdown()
    t.join(timeout=2)


def test_뒤바뀐_로봇은_경고_한_줄로_거부되고_감독은_살아_있다(strict_server):
    """리뷰 A4 — 예전엔 UnitMismatch 가 핸들러 밖으로 새어 traceback 만 남고
    시연은 그냥 시작됐다."""
    with connect(url_of(strict_server)) as mc:
        hello(mc, "mc", unit_id="BBB")
        with pytest.raises(Exception):
            mc.recv(timeout=2)          # 감독이 연결을 닫는다
    time.sleep(0.2)
    assert any("뒤바뀌었는지" in w for w in strict_server.warnings)
    assert "mc" in strict_server.director.rejected
    from stage.machine import TurnError
    with pytest.raises(TurnError):
        strict_server.director.start()


def test_text_가_null_인_heard_는_경고하고_연결을_유지한다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        mc_msgs, _ = start_and_drain(server, mc, docent)
        ended(mc, seq=seq_in(mc_msgs))
        drain(mc, 1); drain(docent, 3)        # mic / mic·gaze·say
        ended(docent, "c1:docent", seq=seq_in(drain_last_say(docent)))  # 아래 주석
        drain(mc, 1)                           # mic open
        mc.send(json.dumps({"type": "heard", "text": None}))
        time.sleep(0.2)
        assert any("규약" in w for w in server.warnings)
        assert server.director.solo_role is None, "타입 오류로 연결이 끊겨 1인 모드가 됐다"


def test_role_이_문자열이_아닌_hello_는_경고하고_끊는다(server):
    with connect(url_of(server)) as ws:
        ws.send(json.dumps({"type": "hello", "role": ["mc"], "unit_id": None, "version": ""}))
        with pytest.raises(Exception):
            ws.recv(timeout=2)
    time.sleep(0.2)
    assert any("모르는 역할" in w for w in server.warnings)
```

> `test_text_가_null_…` 의 도슨트 seq 는 도슨트가 받은 3통 중 `say` 의 seq 다. `drain(docent, 3)` 의 반환값을 변수에 받아 `seq_in(...)` 에 넘긴다 — 위 코드의 `drain_last_say` 는 그 변수를 뜻하는 자리표시가 아니라 **그 변수로 바꿔 쓴다**.

- [x] **Step 3: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py tests/test_stage_server.py -q`
Expected: 새 테스트 FAIL

- [x] **Step 4: 구현**

`stage/director.py`:

```python
        self._rejected: set[str] = set()

    @property
    def rejected(self) -> frozenset[str]:
        return frozenset(self._rejected)

    def reject(self, role: str, reason: str) -> None:
        """역할 검증에 실패한 로봇. 풀릴 때까지 시연을 시작하지 않는다."""
        with self._lock:
            self._rejected.add(role)
            self._warn(f"[{role}] 거부됨 — {reason}. 맞는 로봇이 붙기 전에는 시작하지 않는다")

    def on_hello(...):
        with self._lock:
            ...  # 기존 검증. 통과하면:
            self._rejected.discard(role)

    def start(self) -> None:
        with self._lock:
            if self._rejected:
                raise TurnError(f"거부된 역할이 있다: {sorted(self._rejected)} — 로봇을 바꿔 걸고 다시 붙인다")
            self._begin_cue(self._sheet.current())

    def on_connect(self, role: str) -> None:
        with self._lock:
            self._connected.add(role)
            # **마이크 상태를 다시 준다.** 갓 붙은 앱의 게이트는 닫혀 있다. 감독이
            # LISTENING 인데 리스너가 다시 붙었으면 마이크를 열어 줘야 관람객
            # 창구가 산다 — 안 그러면 앱 재기동/WiFi 순단 뒤 아무도 안 듣는다(리뷰 A5a).
            self._emit(self._resync_mic(role))

    def on_disconnect(self, role: str) -> None:
        with self._lock:
            self._connected.discard(role)
            if self.solo_role is not None:
                self._warn(...)  # 기존
                if self._machine.state is State.LISTENING:
                    # 리스너가 끊겼을 수 있다 — 남은 로봇에게 창구를 넘긴다
                    self._emit(self._machine.force_listening(self._who("mc")))

    def _resync_mic(self, role: str) -> list[Command]:
        open_ = self._machine.state is State.LISTENING and role == self._who("mc")
        return [Command(to=role, type="mic", fields={"open": open_})]
```

`stage/server.py::handler` — hello 분기:

```python
                    r = msg.get("role")
                    if not isinstance(r, str) or r not in ROLES:
                        self._warn(f"모르는 역할이다: {r!r} — 연결을 끊는다")
                        return
                    role = r
                    try:
                        self.director.on_hello(role, msg.get("unit_id"), msg.get("version", ""))
                    except UnitMismatch as exc:
                        # 사람이 읽을 한 줄로 남기고 이 연결만 닫는다. 예전에는 여기서
                        # 새어 나가 websockets 로거의 traceback 만 2초마다 반복됐고,
                        # 콘솔 `s` 는 뒤바뀐 로봇으로 시연을 시작했다(리뷰 A4).
                        self.director.reject(role, str(exc))
                        role = None   # finally 가 "끊어졌다" 로 오해하지 않게
                        return
```

`_dispatch` — 필드 타입 검증 헬퍼:

```python
    def _str_field(self, role: str, msg: dict, key: str) -> str | None:
        v = msg.get(key, "")
        if v is None:
            v = ""
        if not isinstance(v, str):
            self._warn(f"[{role}] {msg['type']}.{key} 가 규약에 안 맞는다({type(v).__name__}) — 버린다")
            return None
        return v
```

`heard` 는 `text = self._str_field(role, msg, "text")`, `None` 이면 return. `speaking_*` 는 `cue_id` 같은 방식, `seq` 는 `int` 또는 `None` 만 받고 아니면 경고 후 버린다. `error` 는 `where`/`detail` 을 `str()` 로 감싼다.

- [x] **Step 5: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 6: lessons.md + 커밋**

```markdown
### 검증 실패는 **경고 채널**로 나가야 검증이다
- **증상**(리뷰 A4): 두 로봇을 바꿔 걸면 `UnitMismatch` 가 핸들러 밖으로 새어 websockets 로거의
  traceback 만 2초마다 반복됐다. 감독의 경고 채널에는 아무것도 없었고 `s` 는 시연을 시작했다.
- **원인**: 검증은 `Director.on_hello` 에 있었는데 그 예외를 받는 곳이 서버에 없었다.
- **규칙**: 예외로 검증하면 **그 예외를 받아 사람이 읽을 한 줄로 바꾸는 자리**까지가 검증이다.
  그리고 거부는 상태로 남겨(`rejected`) 다음 행동(`start`)을 막아야 한다.
- 박제: `tests/test_stage_server.py::test_뒤바뀐_로봇은_경고_한_줄로_거부되고_감독은_살아_있다`.

### 재접속한 쪽은 **상태를 모른다** — 붙을 때 다시 준다
- **증상**(리뷰 A5a): 사회자 앱을 재기동하면 감독은 LISTENING 인데 새 앱의 게이트는 닫힌 채라
  관람객 발화가 전부 `[마이크 닫힘 — 버림]` 으로 떨어졌다. 경고는 없었다.
- **원인**: `mic` 지시는 전이 순간에만 나간다. 그 순간을 못 본 연결은 영영 모른다.
- **규칙**: 연결 이벤트에서 현재 상태를 **다시 전송**한다(idempotent 한 지시라 안전하다).
- 박제: `tests/test_stage_director.py::test_듣는_중에_다시_붙은_리스너에게_마이크를_다시_연다`.
```

```bash
git add stage/server.py stage/director.py tests/test_stage_server.py tests/test_stage_director.py docs/lessons.md
git commit -m "fix(stage): 역할 검증 실패를 경고로 받고, 재접속에 마이크 상태를 다시 주고, 와이어 타입을 검증한다"
```

---

### Task 4: 큐시트 타입 검증 + `stage-env.sh` 의 `set -eu` 제거

**Files:**
- Modify: `stage/cues.py:58-82` (`load_cues`)
- Modify: `scripts/stage-env.sh:9-16`
- Test: `tests/test_stage_cues.py`, `tests/test_stage_env_script.py`

**Interfaces:**
- Produces: `load_cues()` 는 필수 필드가 `str` 이 아니면(`None`·숫자 포함) `CueError`. `stage-env.sh` 는 인자가 없으면 `return 1`(source) / `exit 1`(실행) 하고 셸 옵션을 바꾸지 않는다.

- [x] **Step 1: 실패 테스트**

`tests/test_stage_cues.py`:

```python
@pytest.mark.parametrize("bad", ["mc: 123", "mc:", "id: 07"])
def test_문자열이_아닌_필드는_거절한다(tmp_path, bad):
    """리뷰 A8a — `mc: 123` 이 통과해 `_estimate` 의 len() 에서 TypeError 가 났고,
    감독은 MC_SPEAKING 에 데드라인 없이 굳었다."""
    p = write(tmp_path, f"""
- {{id: "a", title: "t", mc: "m", docent_brief: "b", gaze: partner, {bad}}}
""".replace('mc: "m", ', "") if bad.startswith("mc") else write(tmp_path, f"""
- {{title: "t", mc: "m", docent_brief: "b", gaze: partner, {bad}}}
"""))
    with pytest.raises(CueError, match="문자열"):
        load_cues(p)
```

> 위 parametrize 는 읽기 어렵다. 구현자는 세 케이스를 **세 개의 테스트 함수**로 풀어 쓴다: (1) `mc: 123` (2) `mc:` (값 없음 → `None`) (3) `id: 07` (YAML 정수). 각각 `pytest.raises(CueError, match="문자열")`.

`tests/test_stage_env_script.py`:

```python
def test_source_해도_셸_옵션이_바뀌지_않는다():
    """리뷰 A7c — `set -eu` 가 source 한 운영자 셸에 남아, 다음 실패 명령에서
    SSH 세션이 죽었다."""
    result = subprocess.run(
        ["bash", "-c",
         f"source {SCRIPT} mc >/dev/null; case $- in *e*) echo ERREXIT;; esac; "
         f"case $- in *u*) echo NOUNSET;; esac; false; echo alive"],
        capture_output=True, text=True, timeout=10,
    )
    assert "alive" in result.stdout, result.stderr
    assert "ERREXIT" not in result.stdout and "NOUNSET" not in result.stdout


def test_source_에서_인자가_없으면_셸을_죽이지_않고_실패를_알린다():
    result = subprocess.run(
        ["bash", "-c", f"source {SCRIPT}; echo alive"],
        capture_output=True, text=True, timeout=10,
    )
    assert "alive" in result.stdout
    assert "stage-env.sh" in result.stderr
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py tests/test_stage_env_script.py -q`
Expected: 새 테스트 FAIL

- [x] **Step 3: 구현**

`stage/cues.py::load_cues` 의 필수 필드 검사:

```python
        for key in _REQUIRED:
            v = item.get(key)
            # str() 로 감싸면 `mc: 123`·`mc:`(None) 이 통과한다 — 그 값이 `_estimate`
            # 의 len() 에서 터져 감독이 데드라인 없이 굳는다(리뷰 A8a).
            if not isinstance(v, str) or not v.strip():
                raise CueError(f"{p} {i}번째 항목의 {key} 가 비어 있거나 문자열이 아니다")
```

`scripts/stage-env.sh` — `set -eu` 줄과 그 위 주석을 지우고 `ROLE=` 줄을 다음으로 바꾼다:

```bash
# `set -eu` 를 쓰지 않는다. 이 파일은 **source** 되므로 셸 옵션이 운영자의 세션에
# 그대로 남고, 그 뒤 실패하는 명령 하나(`grep` 불일치, 오타)에 SSH 세션이 끊긴다
# (리뷰 A7c, 실측). 인자 검사는 return/exit 로 한다.
if [ -z "${1:-}" ]; then
  echo "사용법: source scripts/stage-env.sh mc 또는 docent" >&2
  return 1 2>/dev/null || exit 1
fi
ROLE="$1"
```

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures (기존 `test_인자가_없으면_소리_내서_실패한다` 는 `bash SCRIPT` 실행이라 `exit 1` 로 그대로 통과)

- [x] **Step 5: lessons.md + 커밋**

```markdown
### source 되는 스크립트에 `set -e` 를 두지 않는다
- **증상**(리뷰 A7c): `source scripts/stage-env.sh mc` 뒤 실패하는 명령 하나에 SSH 세션이 끊겼다.
- **원인**: `set -eu` 가 호출자 셸에 남는다. 기존 테스트는 `bash -c` 서브셸이라 못 봤다.
- **규칙**: source 용 스크립트는 셸 옵션을 건드리지 않고 `return` 으로 실패한다.
  테스트는 **source 한 뒤의 셸**에서 `$-` 를 본다.
- 박제: `tests/test_stage_env_script.py::test_source_해도_셸_옵션이_바뀌지_않는다`.

### 검증에서 `str()` 로 감싸면 검증이 아니다
- **증상**(리뷰 A8a): `mc: 123`/`mc:` 가 로더를 통과해 `_estimate` 의 `len()` 이 터지고
  감독이 MC_SPEAKING 에 데드라인 없이 굳었다.
- **규칙**: 타입을 요구하는 자리는 `isinstance` 로 거절한다. 강제 변환은 검증을 지운다.
- 박제: `tests/test_stage_cues.py::test_문자열이_아닌_필드는_거절한다` (세 케이스).
```

```bash
git add stage/cues.py scripts/stage-env.sh tests/test_stage_cues.py tests/test_stage_env_script.py docs/lessons.md
git commit -m "fix(stage): 큐시트 필드 타입을 검증하고 stage-env.sh 가 셸 옵션을 남기지 않게 한다"
```

---

### Task 5: 클라이언트 핸들러 예외 분리 + `abort` 가 모션도 끊는다

**Files:**
- Modify: `apps/voice_chat/voice_chat/stage_client.py:141-158` (`_on_raw`)
- Modify: `apps/voice_chat/voice_chat/main.py:275-284` (`Handlers(... on_abort=...)`)
- Test: `tests/test_stage_client.py`, `tests/test_stage_role.py`

**Interfaces:**
- Produces: `main.make_abort(speaker, player, log=print) -> Callable[[], None]` — `speaker.stop()` 뒤 `player.cancel()`(player 가 있으면). `StageClient._on_raw` 는 핸들러 예외를 `warn` 하고 **연결을 유지**한다.

- [x] **Step 1: 실패 테스트**

`tests/test_stage_client.py`:

```python
def test_핸들러_예외는_연결을_끊지_않는다():
    """리뷰 A9 — 핸들러 안의 버그 하나가 재접속을 일으키고, 감독은 그것을
    끊김으로 봐 1인 모드로 내려갔다가 2초 뒤 돌아왔다."""
    warns: list[str] = []
    ws = FakeWS([{"type": "abort"}, {"type": "mic", "open": True}])
    got: list = []
    handlers = Handlers(
        on_say=lambda c, t, s: None,
        on_mic=lambda o: got.append(("mic", o)),
        on_gaze=lambda t: None,
        on_abort=lambda: (_ for _ in ()).throw(RuntimeError("speaker.stop() 가 터졌다")),
    )
    c = StageClient("ws://x", "mc", handlers, warn=warns.append)
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    c.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert calls["n"] == 1, "핸들러 예외로 재접속했다"
    assert ("mic", True) in got, "예외 뒤의 지시가 처리되지 않았다"
    assert any("지시 처리" in w for w in warns)
    assert not any("끊어졌다" in w and "RuntimeError" in w for w in warns)


def test_객체가_아닌_JSON_은_경고하고_넘어간다():
    warns: list[str] = []
    ws = FakeWS(close_when_empty=False)
    c = StageClient("ws://x", "mc", collector()[1], warn=warns.append)
    c._on_raw("[1, 2]")
    assert any("규약" in w or "객체" in w for w in warns)
```

`tests/test_stage_role.py`:

```python
def test_abort_는_소리와_모션을_함께_끊는다():
    """리뷰 A10 — 소리만 끊고 몸은 계속 추면 끊긴 게 아니다(lessons.md 게이팅 항목)."""
    calls: list[str] = []

    class Sp:
        def stop(self): calls.append("stop")

    class Pl:
        def cancel(self): calls.append("cancel")

    main_mod.make_abort(Sp(), Pl(), log=lambda m: None)()
    assert calls == ["stop", "cancel"]
    calls.clear()
    main_mod.make_abort(Sp(), None, log=lambda m: None)()
    assert calls == ["stop"]
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_client.py tests/test_stage_role.py -q -k "핸들러_예외\|객체가_아닌\|abort_는_소리"`
Expected: FAIL

- [x] **Step 3: 구현**

`stage_client.py::_on_raw`:

```python
    def _on_raw(self, raw) -> None:
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            self._warn(f"무대감독 메시지가 JSON 이 아니다: {exc}")
            return
        if not isinstance(msg, dict):
            self._warn(f"무대감독 메시지가 객체가 아니다 — 규약 위반: {raw[:80]!r}")
            return
        t = msg.get("type")
        if t not in _DIRECTOR_MSGS:
            self._warn(f"감독이 보낼 수 없는 메시지다: {t!r}")
            return
        try:
            if t == "say":
                self._h.on_say(msg.get("cue_id", ""), msg.get("text", ""), msg.get("seq"))
            elif t == "mic":
                self._h.on_mic(bool(msg.get("open")))
            elif t == "gaze":
                self._h.on_gaze(msg.get("target", "audience"))
            elif t == "abort":
                self._h.on_abort()
        except Exception as exc:  # noqa: BLE001
            # **핸들러의 예외는 연결 문제가 아니다.** 여기서 새면 run() 의 바깥
            # except 가 "연결이 끊어졌다" 로 오판해 소켓을 닫고 재접속하고, 감독은
            # 그것을 끊김으로 봐 1인 모드로 내려간다(리뷰 A9). 알리고 계속 받는다.
            self._warn(f"감독 지시 처리 중 오류({t}: {type(exc).__name__}: {exc}) — 연결은 유지한다")
```

`main.py`:

```python
def make_abort(speaker, player, log=print):
    """감독의 `abort`. **소리와 몸을 같이 끊는다** — 끼어들기와 같은 규칙이다
    (voice_loop 의 두 stop 자리가 `player.cancel()` 을 짝으로 부른다)."""

    def on_abort() -> None:
        speaker.stop()
        if player is not None:
            player.cancel()
        log("  [감독 abort — 발화·모션 중단]")

    return on_abort
```

`stage_run` 의 `Handlers(... on_abort=make_abort(speaker, player))`.

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 5: lessons.md + 커밋**

```markdown
### 전송 오류와 처리 오류를 **한 except 로 묶지 않는다**
- **증상**(리뷰 A9): 핸들러 버그 하나에 클라이언트가 "연결이 끊어졌다" 며 재접속했고, 감독은
  1인 모드로 내려갔다가 2초 뒤 돌아왔다 — 도슨트가 사회자 대사를 읽기 시작할 수 있는 창이다.
- **규칙**: 수신 루프의 except 는 전송 예외만 받는다. 핸들러 호출은 따로 감싸 경고 후 계속.
- 박제: `tests/test_stage_client.py::test_핸들러_예외는_연결을_끊지_않는다`.
```

```bash
git add apps/voice_chat/voice_chat/stage_client.py apps/voice_chat/voice_chat/main.py tests/test_stage_client.py tests/test_stage_role.py docs/lessons.md
git commit -m "fix(app): 감독 지시 처리 예외를 연결 끊김과 가르고 abort 가 모션도 끊게 한다"
```

---

### Task 6: 사회자 청취 게이트를 캡처 단으로 — 자기목소리 루프(A1) + 청취 스레드 생존(A5b)

**Files:**
- Modify: `apps/voice_chat/voice_chat/voice_loop.py:258-300` (시그니처·루프 머리), `:580-598` (예외 복구)
- Modify: `apps/voice_chat/voice_chat/main.py:56-92` (`make_heard_sink`/`make_mic_sink`), `:286-299` (스레드 기동)
- Test: `tests/test_barge_in.py`, `tests/test_stage_role.py`

**Interfaces:**
- Produces: `voice_loop(llm, speaker, player, respond, should_stop=None, mic_open=None)` — `mic_open: Callable[[], bool] | None`. `False` 를 주는 동안은 프레임을 버리고 VAD 를 리셋하며 STT 를 부르지 않는다(끼어들기 판정도 돌지 않는다). `main.listener_alive(thread) -> bool`. `main.run_listener(voice_loop_fn, args, kwargs, client, log) -> None` — 청취 루프를 감싸 예외를 로그·감독에 보고한다.

- [x] **Step 1: 실패 테스트 — 게이트**

`tests/test_barge_in.py` 의 `_run_loop` 를 확장한다 — `gate=None` 인자를 받아 `vl.voice_loop(..., mic_open=gate)` 로 넘기고, `transcribe` 호출을 세는 리스트를 돌려준다:

```python
def _run_loop(monkeypatch, frames, barge_in, speaking_frames, gate=None):
    ...  # 기존 FakeMic/FakeSpeaker 그대로
    calls: list = []
    monkeypatch.setattr(vl, "transcribe", lambda utt: (calls.append(len(utt)), "")[1])
    ...
    vl.voice_loop(None, spk, None, lambda *a: None, mic_open=gate)
    spk.stt_calls = calls
    return spk


def test_마이크_게이트가_닫혀_있으면_상대_로봇의_말을_STT_에_넘기지_않는다():
    """리뷰 A1 — 게이트를 STT **결과** 시점에만 걸면, 도슨트 마지막 문장을 캡처한
    뒤 게이트가 열리고 나서 전사가 도착해 관람객 발화로 올라간다(자기목소리 루프).
    캡처 단에서 막아야 한다."""
    speech = _frames([0.05], n_each=40) + _frames([0.001], n_each=40)   # 1.2초 말 + 1.2초 침묵
    spk = _run_loop(monkeypatch, speech, barge_in=False, speaking_frames=0, gate=lambda: False)
    assert spk.stt_calls == []


def test_마이크_게이트가_열리면_듣는다(monkeypatch):
    speech = _frames([0.05], n_each=40) + _frames([0.001], n_each=40)
    spk = _run_loop(monkeypatch, speech, barge_in=False, speaking_frames=0, gate=lambda: True)
    assert len(spk.stt_calls) == 1


def test_게이트가_닫힌_동안_모은_발화는_열린_뒤에도_넘어가지_않는다(monkeypatch):
    """닫혀 있는 동안 VAD 가 담아 둔 것이 열리는 순간 발화로 튀어나오면 안 된다 —
    그것이 정확히 도슨트의 마지막 문장이다."""
    state = {"open": False}
    frames = _frames([0.05], n_each=40) + _frames([0.001], n_each=40)
    seen = {"n": 0}

    def gate():
        seen["n"] += 1
        if seen["n"] == 40:      # 말이 끝나는 프레임에서 열린다
            state["open"] = True
        return state["open"]

    spk = _run_loop(monkeypatch, frames, barge_in=False, speaking_frames=0, gate=gate)
    assert spk.stt_calls == []
```

- [x] **Step 2: 실패 테스트 — 청취 스레드 생존**

`tests/test_stage_role.py`:

```python
def test_죽은_청취_스레드는_리스너로_치지_않는다():
    """리뷰 A5b — MicCapture 가 못 뜨면 스레드가 곧장 죽는데 `voice_thread is not None`
    은 True 라 사회자가 귀먹은 채 진행됐고 경고가 없었다."""
    import threading
    t = threading.Thread(target=lambda: None)
    assert main_mod.listener_alive(None) is False
    assert main_mod.listener_alive(t) is False        # 아직 안 시작
    t.start(); t.join()
    assert main_mod.listener_alive(t) is False        # 끝났다


def test_청취_루프가_죽으면_감독과_로그에_알린다():
    logs: list[str] = []
    errors: list[tuple[str, str]] = []

    class C:
        def error(self, where, detail): errors.append((where, detail))

    def boom(*a, **k):
        raise RuntimeError("마이크 파이프라인을 기동하지 못했다")

    main_mod.run_listener(boom, (), {}, C(), log=logs.append)
    assert errors and errors[0][0] == "voice_loop"
    assert any("청취 루프가 죽었다" in m for m in logs)
```

`tests/test_barge_in.py` — 제너레이터 예외 뒤 재진입:

```python
def test_마이크_이터레이터_안의_예외_뒤에도_계속_듣는다(monkeypatch):
    """리뷰 A5b(L1) — 제너레이터는 예외 한 번에 죽는다. 재진입하면 StopIteration 이라
    루프가 조용히 끝났다. 새 이터레이터를 다시 만들어야 한다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "0")
    import voice_loop as vl
    importlib.reload(vl)
    made = {"n": 0}
    quiet = _frames([0.001], n_each=5)

    class Mic:
        def frames(self):
            made["n"] += 1
            if made["n"] == 1:
                yield quiet[0]
                raise ValueError("프레임 10에서 터짐")
            for f in quiet:
                yield f

        def close(self): pass

    class Spk:
        speaking = False
        def output_level(self, w=0.35): return 0.0

    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: Mic())
    monkeypatch.setattr(vl, "transcribe", lambda u: "")
    vl.voice_loop(None, Spk(), None, lambda *a: None)
    assert made["n"] == 2, "예외 뒤 이터레이터를 다시 만들지 않았다"
```

- [x] **Step 3: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_barge_in.py tests/test_stage_role.py -q -k "게이트\|청취\|이터레이터"`
Expected: FAIL (`TypeError: unexpected keyword 'mic_open'`, `AttributeError: listener_alive`)

- [x] **Step 4: 구현 — voice_loop**

시그니처: `def voice_loop(llm, speaker, player, respond, should_stop=None, mic_open=None) -> None:`. 루프 머리, `busy = speaker.speaking` 바로 뒤에:

```python
                    if mic_open is not None and not mic_open():
                        # **캡처 단 게이트.** 감독이 마이크를 닫은 동안(상대 로봇이
                        # 말하는 동안)은 프레임을 통째로 버린다. STT 결과 시점에서만
                        # 버리면 상대의 마지막 문장을 VAD 가 담아 두었다가, 게이트가
                        # 열린 뒤 전사가 도착해 관람객 발화로 올라간다 — 도슨트가
                        # 자기 말에 답하는 무한 루프(리뷰 A1, 실기 §15.2-4 정정).
                        # 여기서 리셋하면 그 버퍼가 사라지고 STT 낭비도 없어진다.
                        recent.clear(); loud.clear(); heard.clear(); heard_speech.clear()
                        vad.reset()
                        guard_until = now + POST_PLAYBACK_GUARD_S
                        continue
```

예외 복구(`except Exception as exc:` 블록 끝):

```python
                vad.reset()
                recent.clear(); loud.clear(); heard.clear(); heard_speech.clear()
                # 제너레이터는 안에서 예외가 나면 끝난다 — 같은 객체로 재진입하면
                # StopIteration 이라 루프가 "EOS" 로 조용히 끝났다(리뷰 A5b). 다시 만든다.
                frames = mic.frames()
```

- [x] **Step 5: 구현 — main.py**

```python
def listener_alive(thread) -> bool:
    """청취 루프가 **실제로 돌고 있는가.** `is not None` 은 기동 직후 죽은 스레드도
    True 다 — 그러면 사회자가 귀먹은 채 진행되고 경고가 없다(리뷰 A5b)."""
    return thread is not None and thread.is_alive()


def run_listener(loop_fn, args, kwargs, client, log=print) -> None:
    """청취 루프를 감싼다. 죽으면 **소리 내서** 죽는다 — 로그와 감독 양쪽에."""
    try:
        loop_fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        log(f"  [경고] 청취 루프가 죽었다({type(exc).__name__}: {exc}) — 관람객 발화로는 진행되지 않는다. 콘솔 n/p 로 진행한다")
        if client is not None:
            client.error("voice_loop", f"{type(exc).__name__}: {exc}")
```

`stage_run`:

```python
        on_mic = make_mic_sink(mic_open, has_listener=lambda: listener_alive(voice_thread))
        ...
        if role == "mc":
            voice_thread = threading.Thread(
                target=run_listener,
                args=(voice_loop, (llm, speaker, player, make_heard_sink(client, mic_open)),
                      {"should_stop": stop_event.is_set, "mic_open": mic_open.is_set}, client),
                daemon=True,
            )
            voice_thread.start()
```

`make_heard_sink` 는 그대로 둔다(두 번째 방어선). 주석에 "일차 방어선은 `voice_loop(mic_open=)` 이다" 를 적는다.

- [x] **Step 6: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 7: 문서·lessons.md + 커밋**

`docs/real-robot-deployment.md` §15.2-4 를 고친다: "안전에는 문제가 없다(구조로 막힌다)" → "**틀렸다(2026-09-14)** — 게이트가 STT 결과 시점에만 있어 도슨트 마지막 문장이 관람객 발화로 올라갔다. 지금은 `voice_loop(mic_open=)` 이 캡처 단에서 막고, STT 낭비도 같이 사라졌다." `docs/lessons.md`:

```markdown
### 게이트는 **입력이 들어오는 자리**에 둔다 — 결과가 나오는 자리가 아니라
- **증상**(리뷰 A1, 2026-09-14): 도슨트가 말을 끝내면 감독이 즉시 사회자 마이크를 연다. 그런데
  사회자 VAD 는 게이트가 닫힌 동안에도 도슨트 목소리를 담고 있었고, hangover 0.7초 + STT 왕복
  뒤에야 전사가 도착하니 그때는 이미 게이트가 열려 있었다 → 도슨트 마지막 문장이 관람객
  발화로 올라가 도슨트가 자기 말에 답하고, 그 끝에 또 마이크가 열린다. 무한 루프.
- **원인**: `make_heard_sink` 가 **STT 결과**에 게이트를 걸었다. 입력(프레임)은 계속 흘렀다.
- **규칙**: 게이트는 파이프라인의 **가장 앞**(캡처)에 건다. 뒤에 걸면 게이트가 닫힌 동안 들어온
  것이 열린 뒤에 튀어나온다. 결과 단의 검사는 이중 방어선일 뿐 게이트가 아니다.
- 박제: `tests/test_barge_in.py::test_게이트가_닫힌_동안_모은_발화는_열린_뒤에도_넘어가지_않는다`.

### "스레드가 있다" 와 "스레드가 산다" 는 다르다
- **증상**(리뷰 A5b): 마이크 파이프라인이 못 떠 청취 스레드가 곧장 죽어도 `voice_thread is not None`
  이라 감독의 `mic(open)` 에 아무 경고도 없었다 — 사회자가 귀먹은 채 진행됐다.
- **규칙**: 생존 판정은 `is_alive()`. 백그라운드 루프는 감싸서 죽을 때 로그와 감독에 보고한다.
- 박제: `tests/test_stage_role.py::test_죽은_청취_스레드는_리스너로_치지_않는다`,
  `tests/test_barge_in.py::test_마이크_이터레이터_안의_예외_뒤에도_계속_듣는다`.
```

```bash
git add apps/voice_chat/voice_chat/voice_loop.py apps/voice_chat/voice_chat/main.py tests/test_barge_in.py tests/test_stage_role.py docs/lessons.md docs/real-robot-deployment.md
git commit -m "fix(app): 사회자 청취 게이트를 캡처 단으로 옮겨 자기목소리 루프를 막고 청취 스레드 사망을 알린다"
```

---

### Task 7: 과길이 발화 — 바닥이 잡혀 있으면 STT 로 넘긴다

**Files:**
- Modify: `apps/voice_chat/voice_chat/audio_in.py:94-108` (`feed` 의 과길이 분기)
- Test: `tests/test_vad.py`

**Interfaces:**
- Produces: `EnergyVAD.feed()` 는 과길이 발화에서 (a) 적응 바닥이 부트스트랩됐으면(`len(_noise) >= 30`) 버퍼를 **발화로 반환**하고 바닥을 건드리지 않는다, (b) 아니면 기존대로 바닥을 재파종하고 버린다. 두 경우 모두 로그 한 줄. `EnergyVAD.overlong_resets` 는 (b) 만 센다, 새 속성 `overlong_passed` 가 (a) 를 센다.

- [x] **Step 1: 실패 테스트**

`tests/test_vad.py`:

```python
def test_바닥이_잡힌_뒤의_긴_질문은_버리지_않는다(capsys):
    """리뷰 A6 — 관람객이 10초 넘게 물으면 버퍼로 바닥을 재파종해 임계가 음성×3 으로
    튀었고, 1.5초 침묵 전까지 다음 질문을 못 들었다. 바닥이 이미 잡혀 있으면 그 위의
    긴 소리는 잡음이 아니라 말이다."""
    vad = EnergyVAD()
    for f in frames_of("silence", 3.0):        # 바닥 부트스트랩(표본 ≥30)
        vad.feed(f)
    th_before = vad.threshold
    outs = [vad.feed(f) for f in frames_of("speech", 11.0)]
    got = [o for o in outs if o is not None]
    assert len(got) == 1, "긴 발화가 통째로 버려졌다"
    assert len(got[0]) >= RATE * 9
    assert vad.threshold == th_before, "발화 버퍼로 바닥이 재파종됐다"
    assert vad.overlong_passed == 1 and vad.overlong_resets == 0
    assert "과길이" in capsys.readouterr().out
    # 곧바로 이어지는 보통 길이 질문도 들린다
    outs = run(vad, [("silence", 0.3), ("speech", 1.0), ("silence", SILENCE)])
    assert len(outs) == 1


def test_바닥이_안_잡혔을_때의_과길이는_여전히_버린다(capsys):
    vad = EnergyVAD()
    outs = [vad.feed(_floor()) for _ in range(int(12 / 0.03))]
    assert all(o is None for o in outs)
    assert vad.overlong_resets == 1
    assert "과길이" in capsys.readouterr().out
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_vad.py -q -k 과길이`
Expected: 첫 테스트 FAIL (`len(got) == 0`), 둘째는 `overlong_passed` 없음 또는 로그 없음으로 FAIL

- [x] **Step 3: 구현**

`audio_in.py` — `__init__` 에 `self._overlong_passed = 0`, 속성 `overlong_passed`. `feed()` 의 과길이 분기:

```python
        if self.buffered_s > self._max_utterance_s:
            if self._adaptive and len(self._noise) >= 30:
                # 바닥이 **이미 잡혀 있다**. 그 위로 10초 넘게 이어진 소리는 잡음이 아니라
                # 긴 질문이다 — 버퍼로 바닥을 재파종하면 임계가 음성×3 으로 튀어 다음
                # 질문을 1.5초 침묵 전까지 못 듣는다(리뷰 A6). 발화로 넘기고 바닥은 둔다.
                self._overlong_passed += 1
                print(f"  [VAD] 과길이 발화({self.buffered_s:.1f}s) — 바닥이 잡혀 있어 STT 로 넘긴다", flush=True)
                utterance = np.concatenate(self._voiced)
                self.reset()
                return utterance
            # 바닥이 안 잡혔다 — 닫힌 고리(바닥 > 임계)를 여기서 끊는다. (기존 주석 유지)
            self._seed_noise(self._voiced)
            self._overlong += 1
            print(f"  [VAD] 과길이 강제종료({self.buffered_s:.1f}s) — 바닥 재파종, STT 로 넘기지 않는다", flush=True)
            self.reset()
            return None
```

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures (기존 `test_소음_바닥이_초기_임계보다_높아도_스스로_빠져나온다`·`test_과길이_발화는_STT로_넘기지_않는다` 는 부트스트랩 전 케이스라 그대로 통과)

- [x] **Step 5: lessons.md + 커밋**

```markdown
### 같은 신호라도 **바닥이 잡혔는가**에 따라 뜻이 다르다
- **증상**(리뷰 A6): 10초 넘는 관람객 질문이 통째로 버려지고, 그 버퍼로 바닥을 재파종해 임계가
  음성×3 으로 튀어 다음 질문까지 못 들었다. 로그도 없었다.
- **원인**: 과길이 처리가 "바닥 > 임계 부트스트랩 탈출" 하나만 염두에 뒀다.
- **규칙**: 탈출 로직은 탈출이 필요한 상태(바닥 미확보)에서만 돈다. 상태가 정상이면 같은 입력은
  정상 데이터다. 그리고 버리든 넘기든 **한 줄 남긴다**.
- 박제: `tests/test_vad.py::test_바닥이_잡힌_뒤의_긴_질문은_버리지_않는다`.
```

```bash
git add apps/voice_chat/voice_chat/audio_in.py tests/test_vad.py docs/lessons.md
git commit -m "fix(vad): 바닥이 잡힌 뒤의 과길이 발화는 버리지 않고 STT 로 넘긴다"
```

---

### Task 8: TTS 워커 `task_done` 이중 호출 — 발화 뒤 모션 사운드가 워커를 죽인다

**Files:**
- Modify: `apps/voice_chat/voice_chat/tts.py:1022-1035` (`_worker` 머리), `:1083-1090` (finally)
- Test: `tests/test_barge_in.py` (SlowStream 서버 픽스처가 있는 곳)

**Interfaces:**
- Produces: `_worker` 는 항목을 미리 꺼냈는지를 `prefetched: bool` 로 기억하고, finally 에서 그 값으로만 `task_done()` 을 부른다. 외부 시그니처 변경 없음.

- [x] **Step 1: 실패 테스트**

`tests/test_barge_in.py`:

```python
def test_발화_뒤에_모션_사운드가_와도_워커가_죽지_않는다(stream_url):
    """리뷰 A3 — 워커가 다음 항목을 미리 꺼낼 때 task_done() 을 한 번 부르고,
    그 항목이 모션 사운드면(`ahead=None`) finally 의 `mine is None` 판정이 또
    task_done() 을 불러 ValueError 로 워커가 죽었다. 그 뒤 speaking 이 영영 True 라
    마이크 게이트가 닫힌 채 굳는다. "답변 + 감정 모션" 은 1대 모드의 보통 경로다."""
    got = []
    s = tts_mod.Speaker(play_pcm=lambda chunks, rate: [got.append(c) for c in chunks])
    s.speak("첫 문장입니다.")
    time.sleep(0.3)                                  # 워커가 첫 문장을 여는 중
    s.play_sound((np.zeros(2400, dtype=np.int16)).tobytes(), 24000)
    s.speak("둘째 문장입니다.")
    s.wait_idle(timeout=15)
    assert not s.speaking, "워커가 죽어 speaking 이 내려가지 않았다"
    assert s._q.unfinished_tasks == 0
    # 죽지 않았다면 그 뒤의 발화도 나온다
    got.clear()
    s.speak("셋째 문장입니다.")
    time.sleep(0.8)
    assert got, "워커가 죽어 이후 발화가 나오지 않았다"
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_barge_in.py -q -k 모션_사운드가_와도`
Expected: FAIL (`speaking` 이 True 로 남거나 `unfinished_tasks` 가 0 이 아님; stderr 에 `ValueError: task_done() called too many times`)

- [x] **Step 3: 구현**

`tts.py::_worker`:

```python
        while True:
            if held is not None:
                item = held
                held, self._held = None, None
                prefetched = True   # 꺼낼 때 이미 task_done 했다
            else:
                item = self._q.get()
                ahead = None
                prefetched = False
            voice, text, seed, gen = item.voice, item.text, item.seed, item.gen
            mine, ahead = ahead, None
            ...
            finally:
                with self._lock:
                    self._pending -= 1
                    if self._pending == 0 and self._held is None:
                        self._speaking.clear()
                # **`mine is None` 으로 판정하지 않는다.** 미리 꺼낸 항목이 모션
                # 사운드면 선요청 핸들이 없어(`ahead=None`) mine 도 None 이라
                # task_done 을 두 번 불렀고, ValueError 로 워커가 죽었다(리뷰 A3).
                if not prefetched:
                    self._q.task_done()
```

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 5: lessons.md + 커밋**

```markdown
### 회계 플래그는 **그 사실**을 기록한다 — 다른 사실에서 유도하지 않는다
- **증상**(리뷰 A3): 발화 뒤 감정 모션 사운드가 오면 TTS 워커가 `task_done() called too many times`
  로 죽고, `speaking` 이 영영 True 라 마이크가 닫힌 채 굳었다. 1대 모드의 보통 경로다.
- **원인**: "미리 꺼냈는가" 를 `mine is None`(선요청 핸들 유무)에서 유도했는데, 모션 사운드는
  미리 꺼내도 선요청이 없다 — 두 사실이 어긋나는 경우가 있었다.
- **규칙**: 큐 회계처럼 정확히 한 번이어야 하는 것은 **그 행위를 했는지** 를 따로 기록한다.
- 박제: `tests/test_barge_in.py::test_발화_뒤에_모션_사운드가_와도_워커가_죽지_않는다`.
```

```bash
git add apps/voice_chat/voice_chat/tts.py tests/test_barge_in.py docs/lessons.md
git commit -m "fix(tts): 미리 꺼낸 모션 사운드에서 task_done 을 두 번 불러 워커가 죽던 것을 고친다"
```

---

### Task 9: 2대 모드 발화에 모션을 붙인다 (B1)

**Files:**
- Modify: `apps/voice_chat/voice_chat/session.py:140-159` (`speak`)
- Modify: `apps/voice_chat/voice_chat/motion.py:113-122` (`play_for`)
- Test: `tests/test_session_speak.py`, `tests/test_motion.py`

**Interfaces:**
- Produces: `session.speak(text, speaker, player, category: str | None = None)` — `None` 이면 `motion.classify(text)` 로 고른다. `MotionPlayer.play_for(category)` 는 표에 없는 category 면 `print` 로 경고하고 `None`.

- [x] **Step 1: 실패 테스트**

`tests/test_session_speak.py`:

```python
def test_category_를_안_주면_문장으로_고른다():
    """리뷰 B1 — 2대 모드의 say 는 category 를 안 주는데 기본값 'neutral' 은 모션 표에
    없어 언제나 None 이었다. 로봇이 말하는 내내 몸이 가만히 있었다."""
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("도슨트, 햄이 뭔가요?", sp, pl)
    assert pl.played == [("curious", False)]
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("1912년 4월 타이타닉호가 침몰할 때 잭 필립스가 구조를 요청했습니다.", sp, pl)
    assert pl.played == [("no", False)]
```

`tests/test_motion.py` 끝에:

```python
def test_모르는_category_는_경고하고_None_이다(capsys):
    from motion import MotionPlayer

    class Drv:
        playing = False
        playing_idle = False
        def set_quiet(self, a): pass

    class Moves:
        def list_moves(self): return ["yes1"]
        def get(self, n): return object()

    p = MotionPlayer(Drv(), Moves(), None)
    assert p.play_for("neutral") is None
    assert "모션 범주" in capsys.readouterr().out
```

> `MotionPlayer.__init__` 의 실제 시그니처와 `_available` 계산은 `motion.py:60-100` 을 읽고 맞춘다. `tests/test_motion.py` 에 이미 가짜 드라이버/무브 헬퍼가 있으면 그것을 쓴다.

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_session_speak.py tests/test_motion.py -q -k "category"`
Expected: FAIL (`pl.played == [("neutral", False)]`)

- [x] **Step 3: 구현**

`session.py::speak`:

```python
def speak(text: str, speaker, player, category: str | None = None) -> None:
    """...(기존 docstring 유지)...

    `category` 를 안 주면 **문장으로 고른다**(`motion.classify`). 예전 기본값 'neutral'
    은 모션 표에 없는 이름이라 2대 모드의 모든 발화가 모션 없이 나갔다(리뷰 B1).
    """
    text = (text or "").strip()
    if not text:
        return
    if player is not None:
        name = player.play_for(category or classify(text))
        print(f"  [모션 {category or classify(text)}/{name}]")
    ...
```

`motion.py::play_for` 첫 줄:

```python
        if category not in CATEGORY_MOVES:
            # 조용히 None 을 주면 "왜 안 움직이지" 를 못 찾는다(리뷰 B1 — 'neutral').
            print(f"  [모션 경고] 모션 범주가 아니다: {category!r} (쓸 수 있는 것: {', '.join(CATEGORY_MOVES)})", flush=True)
            return None
```

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 5: 커밋**

```bash
git add apps/voice_chat/voice_chat/session.py apps/voice_chat/voice_chat/motion.py tests/test_session_speak.py tests/test_motion.py
git commit -m "feat(app): 2대 모드 발화에도 문장으로 고른 모션을 붙인다"
```

---

### Task 10: 사회자 받아치기 `mc_after` — 관람객 창구를 말로 연다 (B2)

**Files:**
- Modify: `stage/cues.py:22-40` (`Cue`), `:58-82` (`load_cues`)
- Modify: `stage/director.py:226-260` (`on_speaking_ended`), `_speak_docent` 옆
- Test: `tests/test_stage_cues.py`, `tests/test_stage_director.py`

**Interfaces:**
- Produces: `Cue.mc_after: str = ""` (선택. 있으면 문자열이어야 한다). 감독은 `f"{cue.id}:docent"` 가 끝나면 `mc_after` 가 있을 때 사회자에게 `say(cue_id=f"{cue.id}:after", gaze="audience")` 를 보내고, 그것이 끝나야 LISTENING 이다. 없으면 기존대로 곧장 LISTENING.

- [x] **Step 1: 실패 테스트**

`tests/test_stage_cues.py`:

```python
def test_mc_after_는_선택이고_없으면_빈_문자열이다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: partner}
- {id: "b", title: "t", mc: "m", docent_brief: "b", gaze: partner, mc_after: "네, 그렇군요."}
""")
    a, b = load_cues(p)
    assert a.mc_after == "" and b.mc_after == "네, 그렇군요."


def test_mc_after_가_문자열이_아니면_거절한다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: partner, mc_after: 3}
""")
    with pytest.raises(CueError, match="mc_after"):
        load_cues(p)
```

`tests/test_stage_director.py` — `Harness.__init__` 에 `after=("", "")` 인자를 받아 두 큐의 `mc_after` 로 넣는다:

```python
        sheet = CueSheet([
            Cue("c1", "첫째", "사회자 첫 대사", "첫 지시", "partner", mc_after=after[0]),
            Cue("c2", "둘째", "사회자 둘째 대사", "둘째 지시", "audience", mc_after=after[1]),
        ])
```

```python
def test_도슨트가_끝나면_사회자가_받아치고_그_뒤에야_마이크가_열린다():
    """B2 — 관람객은 마이크가 언제 열렸는지 모른다. 사회자가 말로 창구를 연다."""
    h = Harness(after=("네, 그렇군요. 궁금한 점 있으면 말씀해 주세요.", ""))
    h.d.start(); h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")
    assert h.says() == [("mc", "네, 그렇군요. 궁금한 점 있으면 말씀해 주세요.")]
    assert h.d.state is State.MC_SPEAKING
    assert all(open_ is False for _, open_ in h.mics())
    h.clear()
    h.ended("mc", "c1:after")
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]


def test_받아치기가_없는_큐는_도슨트_뒤_곧장_듣는다():
    h = Harness()
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    assert h.d.state is State.LISTENING


def test_받아치기도_이력에_남는다():
    h = Harness(after=("받아치기", ""))
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    assert h.d.history[-1]["content"] == "사회자: 받아치기"
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py tests/test_stage_director.py -q -k "mc_after\|받아치"`
Expected: FAIL (`TypeError: unexpected keyword 'mc_after'`)

- [x] **Step 3: 구현**

`stage/cues.py`:

```python
_OPTIONAL_STR = ("mc_after",)

@dataclass(frozen=True)
class Cue:
    id: str
    title: str
    mc: str
    docent_brief: str
    gaze: str
    # 도슨트 뒤 사회자의 받아치기. 관람객 창구가 열린다는 것을 **말로** 알린다 —
    # 마이크가 열려도 관람객은 모른다(리뷰 B2). 비면 곧장 듣기로 간다.
    mc_after: str = ""
```

`load_cues` 의 항목 검사 뒤:

```python
        extra = {}
        for key in _OPTIONAL_STR:
            v = item.get(key, "")
            if v is None:
                v = ""
            if not isinstance(v, str):
                raise CueError(f"{p} {item['id']}: {key} 는 문자열이어야 한다")
            extra[key] = v.strip()
        out.append(Cue(**{k: item[k] for k in _REQUIRED}, **extra))
```

`stage/director.py::on_speaking_ended` — 기존 `if cue_id == cue.id:` 분기 아래에:

```python
            cue = self._sheet.current()
            if cue_id == cue.id:
                cmds = cmds + self._speak_docent(cue)
            elif cue_id == f"{cue.id}:docent" and cue.mc_after:
                # 받아치기 — coalesce 가 방금 열린 마이크를 도로 닫는다(사회자
                # → 도슨트 전환과 같은 모양이다).
                self._remember(f"사회자: {cue.mc_after}")
                cmds = cmds + self._machine.speak(
                    self._who("mc"), f"{cue.id}:after", cue.mc_after, gaze="audience"
                )
            self._emit(cmds)
```

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 5: 커밋**

```bash
git add stage/cues.py stage/director.py tests/test_stage_cues.py tests/test_stage_director.py
git commit -m "feat(stage): 도슨트 뒤 사회자 받아치기(mc_after)로 관람객 창구를 말로 연다"
```

---

### Task 11: 질문 응답 — 사회자 확인 멘트로 LLM 지연을 숨기고 생성을 락 밖으로 (B3)

**Files:**
- Modify: `stage/cues.py` (`QA_ACK_LINES`)
- Modify: `stage/director.py:300-392` (`_begin_cue`/`_generate_docent`/`_speak_docent`/`_answer`), `on_speaking_ended`
- Modify: `stage/__main__.py:49-56` (`_system_prompt`)
- Test: `tests/test_stage_director.py`, `tests/test_stage_main.py`

**Interfaces:**
- Produces: `stage.cues.QA_ACK_LINES: tuple[str, ...]`, `stage.director.QA_FALLBACK: str`. 관람객 질문이 들어오면 감독은 **즉시** 사회자에게 `say(cue_id=f"{cue.id}:ack")` 를 보내고(LLM 대기 없음), 생성은 스레드에서 돈다. `:ack` 가 끝나면 도슨트 `say(cue_id=f"{cue.id}:qa")`. 내부 생성 슬롯은 `_pending_text/_pending_ready/_gen_token` 하나로 도슨트 해설과 질문 응답이 같이 쓴다(한 턴에 생성은 하나뿐이다).

- [x] **Step 1: 실패 테스트**

`tests/test_stage_director.py` — 기존 두 테스트를 새 흐름으로 고친다:

```python
def test_질문을_들으면_사회자가_먼저_받고_도슨트가_답한다():
    """B3 — 질문 뒤 LLM 이 도는 동안 정적이 흐르지 않는다. 큐 전환과 같은 수법이다:
    사회자 고정 멘트가 흐르는 동안 생성한다. 그래서 `on_heard` 는 LLM 을 기다리지 않는다."""
    from stage.cues import QA_ACK_LINES
    h = Harness()
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    h.clear()
    h.d.on_heard("마르코니가 누구예요")
    assert len(h.says()) == 1 and h.says()[0][0] == "mc"
    assert h.says()[0][1] in QA_ACK_LINES
    assert h.d.state is State.MC_SPEAKING
    h.clear()
    h.ended("mc", "c1:ack")
    assert h.says() == [("docent", "[관람객이 '마르코니가 누구예요' 라고 물었다. 지금 섹션은 '첫째' 이다. 도슨트로서 3문장 이내로 답한다. 로 만든 대사]")]
    assert h.d.state is State.DOCENT_SPEAKING


def test_질문과_확인_멘트와_답이_대화_이력에_쌓인다():
    h = Harness()
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    roles = [l["content"].split(":")[0] for l in h.d.history[-3:]]
    assert roles == ["관람객", "사회자", "도슨트"]


def test_질문_응답_생성은_on_heard_를_막지_않는다():
    """`_answer` 가 락을 쥔 채 LLM 을 기다리면 콘솔 `a` 가 그동안 먹지 않는다(리뷰 C1)."""
    import time
    gate = threading.Event()

    def slow(brief, history):
        gate.wait(5)
        return "답"

    h = Harness(generate=slow)
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    t0 = time.monotonic()
    h.d.on_heard("질문")
    assert time.monotonic() - t0 < 1.0, "on_heard 가 LLM 을 기다렸다"
    h.d.abort()                      # 락이 자유로워야 즉시 돌아온다
    assert time.monotonic() - t0 < 1.0
    gate.set()


def test_확인_멘트는_돌아가며_쓴다():
    from stage.cues import QA_ACK_LINES
    h = Harness()
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    seen = []
    for _ in range(len(QA_ACK_LINES)):
        h.clear()
        h.d.on_heard("질문")
        seen.append(h.says()[0][1])
        h.ended("mc", "c1:ack"); h.ended("docent", "c1:qa")
    assert len(set(seen)) == len(QA_ACK_LINES)
```

기존 `test_질문_응답이_빈_문자열이면_경고하고_폴백한다` 는 `h.d.on_heard(...)` 뒤에 `h.ended("mc", "c1:ack")` 를 넣고 폴백 문장이 도슨트 say 로 나오는지 본다. `test_늦게_끝난_생성_스레드는_다음_큐로_새지_않고_버려진다` 가 `_docent_ready`/`_gen_thread` 를 직접 만지면 `_pending_ready` 로 이름을 맞춘다.

`tests/test_stage_main.py`:

```python
def test_도슨트_프롬프트에_음성_출력_규칙이_있다():
    p = stage_main._system_prompt()
    assert "음성" in p and "목록" in p and "이모지" in p
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py tests/test_stage_main.py -q -k "질문\|확인_멘트\|음성_출력"`
Expected: FAIL

- [x] **Step 3: 구현**

`stage/cues.py`:

```python
# 관람객 질문을 받았을 때 사회자가 **즉시** 하는 말. 이 멘트가 흐르는 3~4초 동안 도슨트
# 답을 생성한다 — 큐 전환의 "고정 대사로 지연 은닉" 과 같은 수법이다(리뷰 B3).
# 돌아가며 쓴다. 같은 말이 반복되면 녹음처럼 들린다.
QA_ACK_LINES = (
    "좋은 질문이네요. 도슨트, 답해 줄래요?",
    "오, 그건 저도 궁금했어요. 도슨트?",
    "네, 그건 도슨트가 잘 알 거예요. 도슨트, 부탁해요.",
)
```

`stage/director.py` — 생성 슬롯을 일반화한다:

```python
QA_FALLBACK = "죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?"

    # __init__: self._docent_text/_docent_ready → self._pending_text/_pending_ready, self._ack_i = 0

    def _spawn_generate(self, brief: str, fallback: str, label: str) -> None:
        """생성 슬롯을 비우고 스레드를 띄운다. 이력은 **이 시점의 사본**이다."""
        with self._gen_lock:
            self._pending_text = None
            self._pending_ready = threading.Event()
            self._gen_token += 1
            token = self._gen_token
        self._gen_thread = threading.Thread(
            target=self._generate_pending, args=(brief, token, fallback, label), daemon=True
        )
        self._gen_thread.start()

    def _generate_pending(self, brief, token, fallback, label) -> None:
        # 기존 _generate_docent 본문. cue.docent_brief → fallback, f"[{cue.id}]" → f"[{label}]"

    def _speak_pending(self, role_pref: str, cue_id: str, fallback: str, label: str) -> list[Command]:
        # 기존 _speak_docent 본문. 유예 대기·빈 문자열 폴백은 그대로, cue.docent_brief → fallback.
        self._remember(f"도슨트: {text}")
        return self._machine.speak(self._who(role_pref), cue_id, text, gaze="audience")
```

`_begin_cue` 는 `self._spawn_generate(cue.docent_brief, cue.docent_brief, cue.id)` 를 부르고, `on_speaking_ended` 의 `cue_id == cue.id` 분기는 `self._speak_pending("docent", f"{cue.id}:docent", cue.docent_brief, cue.id)` 를 쓴다. `_answer`:

```python
    def _answer(self, question: str) -> None:
        cue = self._sheet.current()
        self._remember(f"관람객: {question}")
        brief = (
            f"관람객이 '{question}' 라고 물었다. 지금 섹션은 '{cue.title}' 이다. "
            "도슨트로서 3문장 이내로 답한다."
        )
        # **여기서 LLM 을 기다리지 않는다.** 예전에는 락을 쥔 채 왕복 전체를 기다려
        # 콘솔 `a` 와 tick() 이 그동안 멈췄다(리뷰 C1). 사회자의 확인 멘트가 흐르는
        # 동안 스레드에서 만든다 — 관람객에게도 정적 대신 반응이 먼저 간다(B3).
        self._spawn_generate(brief, QA_FALLBACK, f"{cue.id}:qa")
        ack = QA_ACK_LINES[self._ack_i % len(QA_ACK_LINES)]
        self._ack_i += 1
        self._remember(f"사회자: {ack}")
        self._emit(self._machine.speak(self._who("mc"), f"{cue.id}:ack", ack, gaze="audience"))
```

`on_speaking_ended` 에 분기 추가: `elif cue_id == f"{cue.id}:ack": cmds = cmds + self._speak_pending("docent", f"{cue.id}:qa", QA_FALLBACK, f"{cue.id}:qa")`. 받아치기 분기(Task 10)는 `:docent` 에만 걸리므로 `:qa` 가 끝나면 곧장 LISTENING 이다 — 질문 뒤에 또 받아치지 않는다(관람객이 이미 창구를 안다).

`stage/__main__.py::_system_prompt` 에 한 줄 추가: `"네 말은 음성으로 읽힌다. 목록·이모지·특수문자·마크다운을 쓰지 않고 문장은 마침표로 끝낸다. "`

- [x] **Step 4: 통과 확인 + 전체 회귀**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 0 failures

- [x] **Step 5: lessons.md + 커밋**

```markdown
### 락을 쥔 채 네트워크를 기다리지 않는다 — 고정 멘트가 그 시간을 산다
- **증상**(리뷰 C1/B3): 관람객 질문 뒤 LLM 왕복 동안 감독 전체가 락에 묶여 콘솔 `a` 가 먹지
  않았고, 관람객에게는 정적만 흘렀다.
- **규칙**: 느린 왕복은 스레드 + 세대 토큰으로 락 밖에 둔다. 사람에게는 그 시간에 **고정 멘트**를
  들려준다 — 큐 전환의 지연 은닉과 같은 수법이다.
- 박제: `tests/test_stage_director.py::test_질문_응답_생성은_on_heard_를_막지_않는다`.
```

```bash
git add stage/cues.py stage/director.py stage/__main__.py tests/test_stage_director.py tests/test_stage_main.py docs/lessons.md
git commit -m "feat(stage): 질문에 사회자 확인 멘트로 먼저 답하고 도슨트 답은 락 밖에서 만든다"
```

---

### Task 12: 큐시트를 대담 프레임으로 다시 쓴다 + `mc_after` 19개 (B4)

**Files:**
- Modify: `data/cues.yaml` (mc 19개 교체, mc_after 19개 추가; id·title·docent_brief·gaze 는 그대로)
- Test: `tests/test_stage_cues.py`

**Interfaces:**
- 소비: Task 10 의 `Cue.mc_after`. 큐 id 는 바꾸지 않는다(`test_큐시트가_해설_원장의_모든_섹션을_덮는다`).

- [x] **Step 1: 실패 테스트**

`tests/test_stage_cues.py`:

```python
_DEIXIS = ("여기", "이곳", "저기", "이쪽", "저쪽", "여기서")


def test_사회자_대사에_위치_지시어가_없다():
    """두 로봇은 책상 위에 고정돼 있고 관람객이 움직인다(원장 「걷어낸 것」).
    "여기는 ~존입니다" 는 로봇이 그 자리에 있다는 거짓말이다(리뷰 B4)."""
    for c in load_cues():
        for w in _DEIXIS:
            assert w not in c.mc, f"{c.id} mc: {w!r}"
            assert w not in c.mc_after, f"{c.id} mc_after: {w!r}"


def test_모든_큐에_받아치기가_있고_다음을_안내한다():
    cues = load_cues()
    for c in cues:
        assert c.mc_after, f"{c.id} 에 mc_after 가 없다"
    for c in cues[:-1]:                 # 마지막 큐는 '다음' 이 없다
        assert "다음" in c.mc_after, f"{c.id} 받아치기가 진행 신호를 안내하지 않는다"


def test_사회자_대사_길이가_예산_안이다():
    # CHARS_PER_SEC=4 → 130자면 32초 + 여유 15초. 이보다 길면 한 큐가 늘어진다.
    for c in load_cues():
        assert len(c.mc) <= 130, f"{c.id} mc {len(c.mc)}자"
        assert len(c.mc_after) <= 90, f"{c.id} mc_after {len(c.mc_after)}자"


def test_사회자_대사가_한_틀로_반복되지_않는다():
    firsts = [c.mc.split(" ")[0] for c in load_cues()]
    assert len(set(firsts)) >= 8, f"첫 낱말이 너무 겹친다: {firsts}"
```

- [x] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py -q -k "위치_지시어\|받아치기가\|길이가\|한_틀"`
Expected: FAIL

- [x] **Step 3: 큐시트 교체**

`data/cues.yaml` 머리말에 한 줄 더한다: `#   mc_after      도슨트 뒤 사회자의 받아치기 + 관람객 창구 안내. 고정 대사`. 그리고 19개의 `mc` 를 아래로 바꾸고 `mc_after` 를 각 큐의 `gaze` 앞에 넣는다(`docent_brief`·`gaze` 는 손대지 않는다):

```yaml
# 01-intro
  mc: "안녕하세요, 전파체험관 이야기 시간에 오신 것을 환영합니다. 오늘 진행은 제가, 해설은 제 옆의 도슨트가 맡습니다. 도슨트, 먼저 이 체험관이 어떤 곳인지 소개해 줄래요?"
  mc_after: "네, 소개 고마워요. 궁금한 점은 언제든 저에게 말씀해 주세요. 다음 주제로 가려면 '다음'이라고 말씀해 주시면 됩니다."
# 02-history
  mc: "첫 주제는 전파의 발견 역사입니다. 도슨트, 전파는 발명일까요, 발견일까요?"
  mc_after: "발명이 아니라 발견이라니, 저도 처음엔 헷갈렸어요. 질문 있으시면 말씀해 주시고, 이어가려면 '다음'이라고 해 주세요."
# 03-theory
  mc: "그럼 전파가 정확히 무엇인지 원리로 들어가 보죠. 도슨트, 주파수와 파장을 쉽게 풀어 주세요."
  mc_after: "퐁당퐁당 물결 비유가 쏙 들어오네요. 궁금한 게 있으면 지금 물어보셔도 좋습니다. 아니면 '다음'이요."
# 04-morse
  mc: "체험관에는 직접 만져볼 수 있는 장치들도 있다고 들었어요. 도슨트, 전파이야기 체험존에서는 무엇을 해볼 수 있나요?"
  mc_after: "모스부호를 직접 쳐볼 수 있다니 재미있겠어요. 질문 있으신가요? 없으면 '다음'이라고 말씀해 주세요."
# 05-donor
  mc: "이 체험관 정식 이름에는 사람 이름이 하나 들어 있습니다. 도슨트, 장황남 박사가 누구인지 소개해 주세요."
  mc_after: "의학박사가 통신 장비를 모았다는 게 뜻밖이죠. 궁금한 점 있으시면 말씀해 주시고, 이어가려면 '다음'이요."
# 06-bands
  mc: "그 기증품을 주파수 대역별로 둘러볼 차례입니다. 도슨트, 어떤 대역의 장비들이 전시돼 있나요?"
  mc_after: "초장파부터 밀리미터파까지, 범위가 정말 넓네요. 질문 있으면 말씀해 주세요. 다음으로 가려면 '다음'입니다."
# 07-maritime
  mc: "이번 주제는 바다 위의 무선통신입니다. 도슨트, 타이타닉호 이야기를 들려주세요."
  mc_after: "마지막까지 구조 신호를 보낸 전신기사 이야기가 뭉클하네요. 궁금한 점 있으신가요? 없으면 '다음'이라고 해 주세요."
# 08-aviation
  mc: "바다 다음은 하늘입니다. 도슨트, 항공무선통신 코너와 시뮬레이터에서는 무엇을 해볼 수 있나요?"
  mc_after: "조종석에 앉아 이륙까지 해볼 수 있다니 인기가 많겠어요. 질문 있으시면 말씀해 주시고, 이어가려면 '다음'이요."
# 09-special-exhibit
  mc: "특별교류전시라는 코너도 있다고 들었습니다. 도슨트, 지금은 어떤 것이 전시돼 있나요?"
  mc_after: "군용 장비는 튼튼한 대신 무겁다는 점이 인상적이네요. 궁금한 점은 말씀해 주시고, 다음 주제로 가려면 '다음'입니다."
# 10-ham
  mc: "이번엔 취미로 즐기는 무선통신, 아마추어 무선입니다. 도슨트, 햄이 뭔가요?"
  mc_after: "취미가 재난 때는 통신망이 된다는 게 멋지네요. 질문 있으신가요? 없으면 '다음'이라고 말씀해 주세요."
# 11-iot
  mc: "다음 주제는 사물인터넷입니다. 도슨트, 체험관에서는 무엇을 해볼 수 있나요?"
  mc_after: "태블릿으로 전구 색을 바꾸는 체험, 아이들이 좋아하겠어요. 궁금한 점 있으면 말씀해 주시고, 이어가려면 '다음'이요."
# 12-multimedia
  mc: "KCA가 방송 콘텐츠도 지원한다고 하던데요. 도슨트, 멀티미디어실에서는 어떤 콘텐츠를 볼 수 있나요?"
  mc_after: "아마존의 눈물이 KCA 지원작이었군요. 질문 있으시면 말씀해 주세요. 다음으로 가려면 '다음'입니다."
# 13-chromakey
  mc: "크로마키 체험 코너 이야기도 해 보죠. 도슨트, 크로마키가 뭔가요?"
  mc_after: "찍은 사진을 메일로 받을 수 있다니 기념이 되겠네요. 궁금한 점 있으신가요? 없으면 '다음'이라고 해 주세요."
# 14-mobile
  mc: "이번 주제는 휴대폰의 발전, 이동통신입니다. 도슨트, 1세대부터 5세대까지 어떻게 달라졌나요?"
  mc_after: "카폰이 아파트 한 채 값이었다니 놀랍네요. 질문 있으시면 말씀해 주시고, 이어가려면 '다음'이요."
# 15-emf
  mc: "지금부터는 KCA가 정부에서 위탁받은 전파품질 관리 업무 이야기입니다. 도슨트, 전자파는 안전한가요?"
  mc_after: "거리를 조금만 두면 괜찮다는 게 핵심이군요. 이 주제는 질문이 많을 것 같아요. 말씀해 주시고, 아니면 '다음'입니다."
# 16-inspection
  mc: "전파품질 관리의 또 다른 축, 무선국 검사입니다. 도슨트, 무선국 검사가 뭔가요?"
  mc_after: "전파가 한정된 자원이라 관리가 필요하다는 말이 와닿네요. 궁금한 점 있으신가요? 없으면 '다음'이라고 해 주세요."
# 17-rover
  mc: "체험관에는 행성 탐사 체험도 있다고 들었어요. 도슨트, 원격 무선조종 차량 코너는 무엇을 하는 곳인가요?"
  mc_after: "월면차를 몰고 미션을 수행한다니 게임 같네요. 질문 있으시면 말씀해 주시고, 이어가려면 '다음'이요."
# 18-science
  mc: "마지막 주제는 전파와 관련된 기초 과학 실험 도구들입니다. 도슨트, 무엇이 있나요?"
  mc_after: "손을 대지 않고 연주하는 테레민, 꼭 들어보고 싶네요. 마지막으로 궁금한 점 있으신가요? 없으면 '다음'이라고 해 주세요."
# 19-closing
  mc: "오늘의 전파체험관 이야기는 여기까지입니다. 도슨트, 마무리 인사 부탁해요."
  mc_after: "저도 감사드립니다. 질문이 남았다면 지금 말씀해 주세요. 즐거운 관람 되시길 바랍니다."
```

> 19-closing 의 mc 에 "여기까지" 가 있다 — `_DEIXIS` 의 "여기" 에 걸린다. **"오늘의 전파체험관 이야기는 이것으로 마칩니다."** 로 쓴다. 마찬가지로 각 줄을 넣은 뒤 테스트가 지목하는 낱말을 고친다.

- [x] **Step 4: 통과 확인 + 눈으로 검토**

Run: `.venv/bin/python -m pytest tests/test_stage_cues.py tests/test_stage_director.py -q`
Expected: 전부 PASS. 그리고 `docs/exhibit-guide.md` 「정본」 표와 대조해 사실(연도·숫자)이 mc/mc_after 에 새로 들어가지 않았는지 본다 — 받아치기는 감상이지 사실 진술이 아니어야 한다.

- [x] **Step 5: 커밋**

```bash
git add data/cues.yaml tests/test_stage_cues.py
git commit -m "feat(cues): 사회자 대사를 대담 프레임으로 다시 쓰고 받아치기 19개를 넣는다"
```

---

### Task 13: 문서를 코드와 맞춘다 + 실기 2대 오프라인 테스트 절차

**Files:**
- Modify: `docs/superpowers/specs/2026-09-11-two-robot-mc-docent-design.md` §4 (메시지 표에 `seq`, `mc_after`, `:ack`/`:qa` 흐름), §4.1 상태 전이
- Modify: `docs/two-robot-setup.md` §7 (콘솔 `n` 이 IDLE 에서도 됨, 관람객 안내가 사회자 멘트로 나감, 질문 흐름), §8 체크리스트에 "한 큐를 끝까지: 사회자 → 도슨트 → 받아치기 → '다음'", "질문 하나: 확인 멘트 → 답"
- Modify: `docs/real-robot-deployment.md` §15.2 (1·2·3 항목 상태 갱신: 2 는 해결, 1·3 은 그대로)
- Modify: `docs/lessons.md` — 이전 라운드에 빠진 5건을 짧게 등재: `fa8b068`(발화 워커로 abort 즉시), `f9fa6c5`(콘솔 EOF/TurnError), `32b86ce`(데드라인을 발화 시작 시점부터), `925d163`/`69e636a`(1인 모드 cue id 구분·리스너 마이크), `3ea7e35`(이력 상한). 각각 증상 → 원인 → 규칙 3줄.
- Create: `docs/two-robot-offline-test.md` — 사용자가 요청한 **실기 2대 오프라인 테스트 순서**(`two-robot-setup.md` 를 절차 순서로 압축: ① 공유기 ② 로봇 한 대씩 WiFi ③ 고정 IP·hardware_id ④ startup-app 비움 ⑤ 노트북 `serve`+`warmup` ⑥ `python -m stage` ⑦ `robot up` ×2 ⑧ 확인 항목 ⑨ 고장 시 콘솔 키). 코드에 없는 절차는 적지 않는다.

- [x] **Step 1: 문서 수정**

각 파일을 위 목록대로 고친다. 설계 §4 표의 `speaking_started`/`speaking_ended` 행을 `{cue_id, seq}` 로, `say` 행을 `{cue_id, seq, text}` 로. §4.1 에 `DOCENT_SPEAKING ──ended──▶ MC_SPEAKING(mc_after) ──ended──▶ LISTENING` 과 `LISTENING ──heard(질문)──▶ MC_SPEAKING(:ack) ──ended──▶ DOCENT_SPEAKING(:qa)` 를 넣는다.

- [x] **Step 2: 문서-코드 대조 테스트**

`tests/test_deployment_contract.py` 에:

```python
def test_설계_문서의_메시지_필드가_코드와_맞는다():
    doc = (pathlib.Path(__file__).parent.parent
           / "docs/superpowers/specs/2026-09-11-two-robot-mc-docent-design.md").read_text()
    assert "`speaking_started` / `speaking_ended` | `{cue_id, seq}`" in doc
    assert "mc_after" in doc
```

Run: `.venv/bin/python -m pytest tests/ -q` → 0 failures

- [x] **Step 3: 커밋**

```bash
git add docs/ tests/test_deployment_contract.py
git commit -m "docs: 2대 구성 문서를 seq·받아치기·질문 흐름에 맞추고 실기 오프라인 테스트 절차를 적는다"
```

---

## Self-Review (작성자 확인)

- **범위 대조**: A1(6) A2(1) A3(8) A4(3) A5a(3) A5b(6) A6(7) A7a/b(2) A7c(4) A8a(4) A8b(3) A9(5) A10(5) B1(9) B2(10) B3(11) B4(12) — 전부 태스크가 있다. C-계열 락 문제 중 `_answer` 는 11 이 풀고, `_speak_docent` 8초 대기·`_emit` 의 send·`old.close()` 10초는 **이번 범위 밖**(사용자 결정 A+B1~B3) — Task 13 의 §15.2 갱신에 "그대로" 라고 적는다.
- **이름 일치**: `seq`(1→3·10·11 의 `h.ended` 헬퍼), `listener_alive`/`run_listener`(6), `make_abort`(5), `mc_after`(10→12), `QA_ACK_LINES`/`QA_FALLBACK`/`_spawn_generate`/`_speak_pending`(11), `overlong_passed`(7). Task 11 이 `_docent_ready` 를 `_pending_ready` 로 바꾸므로 Task 10 까지는 옛 이름을 쓴다 — 순서대로 실행한다.
- **순서 의존**: 1 → 2 → 3 (감독 시그니처), 10 → 11 → 12 (큐 필드). 4·5·6·7·8·9 는 서로 독립이다.
