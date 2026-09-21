# 무대감독 발화 위생 — 이름표 누출·분량 초과·STT 상용구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실기 2대 리허설에서 드러난 세 결함 — 생성문에 "사회자:"/"도슨트:" 이름표가 섞여 소리로 나가는 것, 생성 분량이 목표의 1.3~1.8배로 넘치는 것, Whisper 무음 상용구가 관람객 질문으로 처리되는 것 — 을 고친다.

**Architecture:** LLM 호출은 전부 `stage/__main__.py::build_generate` 한 곳을 지난다. 그 안에서 (1) 감독의 공용 이력을 **생성하는 역할의 시점**(자기 말=assistant, 남의 말=user)으로 바꿔 싣고, (2) 생성 직후 이름표를 걷고 상대 턴 이어쓰기를 자르고, (3) 문장 경계에서 분량 상한을 건다. 텍스트가 TTS 와 이력으로 갈라지기 **전**이라 두 갈래가 함께 깨끗해지고 `Director` 는 한 줄도 안 바뀐다. 순수 함수는 새 모듈 `stage/speech_text.py` 에 둔다. STT 상용구는 로봇 앱의 기존 차단 목록(`voice_loop._filler`)을 넓힌다.

**Tech Stack:** Python 3.12(`.venv`), pytest, 정규식(`re`). 새 의존성 없음.

**Spec:** 이 문서 §0 배경 — 2026-09-21 실기 2대 리허설 로그 분석(대화 중 정리한 원인 분석을 여기 옮겼다).

## Global Constraints

- 인터프리터는 `.venv/bin/python` 하나뿐이다. 테스트: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q`
- 시뮬에서 검증한 것이 **코드 수정 없이** 실기에 배포돼야 한다. 플랫폼 전용을 기본 경로에 박지 않는다. 주소는 전부 환경변수다.
- **폴백·보정으로 물러날 때는 반드시 경고를 남긴다.** 조용히 성능이 떨어진 채 도는 것이 가장 나쁘다.
- 락 순서는 `Director._lock` → `_gen_lock` 한 방향뿐이다. 이 계획은 `Director` 의 락을 건드리지 않는다.
- 주석에는 **왜 그렇게 짰는지**("이렇게 안 하면 무엇이 깨지는지")를 남긴다. 기존 주석은 지우지 말고 갱신한다. 고쳐서 사라진 제약은 취소선으로 남긴다.
- `harness/` 는 수정하지 않는다.
- 새 테스트는 **먼저 실패하는 것을 보고** 나서 고친다(TDD). 뮤테이션을 직접 돌릴 때는 반드시 `PYTHONDONTWRITEBYTECODE=1`.
- 이 브랜치가 반복해서 밟은 테스트 함정 다섯 — 재발시키지 않는다:
  1. `pytest.raises(match=...)` 가 `tmp_path`(=테스트 함수명)에 우연히 걸린다
  2. 서로 다른 두 인자에 **같은 값**을 넘겨 배선이 끊겨도 통과한다
  3. 기본값이 있는 인자를 **기본값과 같은 값**으로 단언한다
  4. 부정 단언(`not in`)만 있어 내용이 통째로 비어도 통과한다 — 짝이 되는 긍정 단언을 둔다
  5. 기대값을 **피검 코드에서 import** 해 자기참조가 된다 — 기대값은 리터럴로 쓴다
- 새 단언마다 스스로 답한다: **이 테스트를 실패시키는 프로덕션 변경이 무엇인가.**
- 커밋 메시지는 한국어 `type(scope): 요약` 형식, 끝에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- 버그를 하나 잡을 때마다 `docs/lessons.md` 에 증상 → 원인 → 규칙 → 박제(테스트 이름) 순으로 남긴다. **파일 끝**(무대감독 절의 마지막)에 붙인다.

---

## §0 배경 — 실측 근거

리허설: 2026-09-21, 사회자 192.168.0.4 / 도슨트 192.168.0.5, 관람객 수준 "일반", 19큐 전체 진행 시도. 로그 발췌 파일(원본은 로봇 journalctl): `mc_final_run.log`, `docent_final_run.log`, 맥 `.demo-logs/tts.log`.

### 결함 1 — 화자 이름표 누출

- 사회자: `미니> 사회자: 한국방송통신전파진흥원이 운영하는 곳이군요...` (mc:42), `미니> 사회자: 사회자: 전자기파라는 개념과...` (mc:74)
- 도슨트: `미니> 도슨트: 사물인터넷은...` (docent:96), `미니> 도슨트: 도슨트: 이동통신의 역사는...` (docent:122)
- **상대 턴 이어쓰기**: 도슨트 한 발화 안에 `...시각을 얻으실 수 있을 것입니다.사회자: 사회자: 방송통신 진흥과 관련된 콘텐츠를...` (docent:106)
- 원인:
  - `stage/director.py:582` `self._remember(f"{SPEAKER_LABEL[pending.role]}: {text}")` — 이름표가 이력 **내용 문자열에** 박힌다.
  - `stage/director.py:1134` `role = "user" if line.startswith("관람객:") else "assistant"` — 사회자·도슨트 줄이 **전부 `assistant`** 다.
  - `stage/__main__.py:55` `c.history = list(history)` — 그대로 LLM 에 실린다. 모델은 상대의 말까지 "내가 했던 말"로 보고, 그 말들이 전부 "이름표: 텍스트" 모양이라 흉내 낸다.
  - 되먹임: 생성문이 이미 "사회자:" 로 시작하면 이력에 "사회자: 사회자: …" 가 쌓이고, 다음 생성이 그 이중 이름표를 또 흉내 낸다.
- 웹소켓 라우팅(어느 로봇에게 보내는가)은 매번 정확했다 — `hardware_id` 검증이 계속 통과했고 "거부됨"이 한 번도 없었다. **배선이 아니라 콘텐츠 문제다.**

### 결함 2 — 생성 분량 초과

| | 목표(프롬프트가 준 수) | 실측 |
|---|---|---|
| 도슨트 해설 | 4~5문장, 180~280자(`data/levels.yaml` 일반) | 5~10문장, **235~517자**(13개 중 11개 초과) |
| 사회자 받아치기 | 1~3문장, 40~120자(`stage/prompts.py` `_MC_*`) | 5~6문장, **147~195자** |

- 원인: `max_tokens=624`(`level.max_tokens`)가 280자 목표의 두 배 넘는 여유라 하드 스톱이 못 되고, 프롬프트의 분량 지시를 모델이 지키지 않는다(이력이 길수록 더).
- 영향: 한 큐의 음성 합계가 75~120초. 합성이 느린 게 아니다 — `tts.log` 의 샘플 수로 계산한 RTF 는 0.65~0.80(실시간보다 빠름)이고, **오디오 자체가** 도슨트 45~87초였다.
- 짧은 발화(6~8초 분량)가 18~32초 걸린 것이 3건(RTF 3~4) — TTS 서버 직렬 대기로 보이는 **가설**이다. 이 계획의 범위 밖이고 최종 검증에서 관찰만 한다.

### 결함 3 — STT 무음 상용구가 질문으로 처리됨

- `[대기 중] 마이크 최대 0.002 / VAD 임계 0.005` → `나(STT +0.59s)> 다음 영상에서 만나요.` → 사회자 `좋은 질문이네요. 도슨트, 답해 줄래요?` → 도슨트 `관람객 여러분께서 다음 영상에서 다시 만나 뵙기를 희망하시는군요…` (mc:150-155, docent:86)
- `나(STT +1.75s)> Come.` → 사회자 `오, 그건 저도 궁금했어요. 도슨트?` (mc:179-183)
- 원인: `apps/voice_chat/voice_chat/voice_loop.py:88-96` `_WHISPER_FILLER` 가 공백만 걷고 **정확 일치**로 본다. 두 문구 모두 목록에 없다. 구두점 차이("감사합니다"/"감사합니다.")는 항목을 두 번 적어 막고 있었다.

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `stage/speech_text.py` | 생성문 정리 순수 함수: 이름표 제거·상대 턴 절단, 문장 분리, 분량 상한 | **신규** |
| `tests/test_speech_text.py` | 위 순수 함수 단위 테스트 | **신규** |
| `stage/__main__.py` | `build_generate`: 이력 시점 변환·병합, 생성 후 정리·상한·경고 배선 | 수정 |
| `tests/test_stage_main.py` | `build_generate` 배선 테스트(기존 이력 테스트는 **계약 변경**) | 수정 |
| `stage/prompts.py` | `_COMMON` 에 "이름표 없이 네 말만" 규칙 | 수정 |
| `tests/test_prompts.py` | 조립된 프롬프트 전수(2역할 × 4수준)에 그 규칙 | 수정 |
| `apps/voice_chat/voice_chat/voice_loop.py` | `_filler`: 구두점까지 걷고 비교, 실측 상용구 추가 | 수정 |
| `tests/test_stt_filler.py` | 상용구 판정 테스트 | **신규** |
| `docs/lessons.md` | 결함마다 증상→원인→규칙→박제 | 수정 |

`stage/director.py` 는 **바꾸지 않는다.** 생성문이 깨끗해지면 `_remember` 의 이름표 한 번만 남는다.

---

### Task 0: 워킹트리의 I1 변경 마무리 — 기준선 정리

**모델:** sonnet (테스트 인덱스 한 줄 + 커밋)

워킹트리에 전체 리뷰 I1("도슨트 분량 미달 경고가 수준 하한을 따른다") 변경이 커밋되지 않은 채 있고, 테스트 1건이 실패한다(645 passed, 1 failed). 실패 원인은 **테스트 버그**다 — `h.says()` 의 사회자 발화 중 `[0]` 은 여는 대사(`"사회자 첫 대사"`)이고, 검사하려던 받아치기는 마지막이다. Task 2 가 같은 파일(`stage/__main__.py`)을 건드리므로 먼저 커밋해 기준선을 깨끗이 한다.

**Files:**
- Modify: `tests/test_stage_director.py:1163`
- Commit(이미 수정돼 있음): `stage/__main__.py`, `stage/director.py`, `stage/server.py`, `tests/test_stage_director.py`, `tests/test_stage_main.py`, `tests/test_stage_server.py`

**Interfaces:**
- Consumes: 없음
- Produces: `Director(docent_min_chars: int = MIN_CHARS)`, `StageServer(docent_min_chars: int = MIN_CHARS)` — 이미 워킹트리에 있다. 이 계획의 다른 태스크는 이것을 쓰지 않는다.

- [ ] **Step 1: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_stage_director.py::test_사회자_받아치기는_수준_하한이_아니라_고정_하한을_쓴다 -q`
Expected: FAIL — `'사회자 첫 대사'.startswith(...)` 가 False

- [ ] **Step 2: 인덱스를 고친다**

`tests/test_stage_director.py:1163` 을 이렇게 바꾼다(받아치기는 사회자의 **마지막** 발화다 — 여는 대사가 먼저 나간다):

```python
    assert [t for r, t in h.says() if r == "mc"][-1].startswith(_50자), h.says()
```

- [ ] **Step 3: 통과를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q`
Expected: `646 passed`

- [ ] **Step 4: 뮤테이션으로 배선을 확인한다**

`stage/director.py` 의 `_warn_if_short` 안 `limit = self._docent_min_chars if role == "docent" else MIN_CHARS` 를 `limit = MIN_CHARS` 로 **임시로** 바꾸고:

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_stage_director.py -q -k "분량_경고는_수준의_하한"`
Expected: FAIL. 확인 후 **원래대로 되돌리고** `git diff stage/director.py` 로 되돌림을 확인한다.

- [ ] **Step 5: 커밋**

```bash
git add stage/__main__.py stage/director.py stage/server.py tests/test_stage_director.py tests/test_stage_main.py tests/test_stage_server.py
git commit -m "$(cat <<'EOF'
fix(stage): 도슨트 분량 미달 경고가 수준 하한을 따른다 (전체 리뷰 I1)

MIN_CHARS(40) 고정이라 일반(180자)·전문가(260자)에서 50자짜리 해설이 나와도
경고가 없었다. docent_min_chars 를 main → StageServer → Director 로 흘리고,
하한을 역할의 함수로 둔다 — 사회자 몫은 프롬프트가 수준과 무관하게 40~120자를
주므로 40 고정이다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1: 생성문 정리 순수 함수 — `stage/speech_text.py`

**모델:** sonnet (명세가 코드로 다 주어진다)

**Files:**
- Create: `stage/speech_text.py`
- Test: `tests/test_speech_text.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `strip_speaker_labels(text: str) -> tuple[str, bool]` — (정리된 텍스트, 이름표를 걷거나 잘랐는지)
  - `split_sentences(text: str) -> list[str]`
  - `cap_length(text: str, max_sentences: int, max_chars: int) -> tuple[str, bool]` — (상한 적용 텍스트, 잘랐는지)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_speech_text.py`:

```python
"""생성문 정리 순수 함수(`stage/speech_text.py`).

실측 근거는 `docs/superpowers/plans/2026-09-21-stage-speech-hygiene.md` §0.
기대값은 전부 **리터럴**이다 — 피검 함수로 기대값을 만들면 자기참조가 된다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.speech_text import cap_length, split_sentences, strip_speaker_labels


# ── 이름표 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    # 실측 mc:42 — 앞머리 이름표 하나
    ("사회자: 한국방송통신전파진흥원이 운영하는 곳이군요.", "한국방송통신전파진흥원이 운영하는 곳이군요."),
    # 실측 mc:74 — 이름표가 두 번(되먹임 고리의 결과)
    ("사회자: 사회자: 전자기파라는 개념과 주파수를 설명해 주셨네요.", "전자기파라는 개념과 주파수를 설명해 주셨네요."),
    # 실측 docent:122
    ("도슨트: 도슨트: 이동통신의 역사는 깁니다.", "이동통신의 역사는 깁니다."),
    # 마크다운 강조·전각 콜론도 이름표다
    ("**사회자:** 좋은 질문이네요.", "좋은 질문이네요."),
    ("도슨트：전파는 파동입니다.", "전파는 파동입니다."),
])
def test_앞머리_이름표를_걷는다(raw, expected):
    assert strip_speaker_labels(raw) == (expected, True)


def test_상대_턴까지_이어_쓴_생성문은_그_이름표_앞에서_자른다():
    """실측 docent:106 — 도슨트 한 발화 안에 사회자 반응이 이어 붙었다."""
    raw = ("시각을 얻으실 수 있을 것입니다.사회자: 사회자: 방송통신 진흥과 관련된 "
           "콘텐츠를 볼 수 있다는 설명이네요.")
    assert strip_speaker_labels(raw) == ("시각을 얻으실 수 있을 것입니다.", True)


def test_이름표만_있으면_빈_문자열이_된다():
    """비면 감독의 기존 빈 생성 폴백(경고 + 큐시트 원문)을 탄다."""
    assert strip_speaker_labels("사회자: ") == ("", True)


@pytest.mark.parametrize("clean", [
    "전파는 눈에 보이지 않습니다.",
    # 콜론이 없으면 이름표가 아니다 — 정상 문장을 건드리면 안 된다
    "사회자님 말씀처럼 전파는 보이지 않습니다.",
    "도슨트가 설명한 대로 주파수는 진동 횟수입니다.",
])
def test_이름표가_없으면_그대로_둔다(clean):
    assert strip_speaker_labels(clean) == (clean, False)


def test_앞뒤_공백만_다른_것은_바뀐_것으로_치지_않는다():
    assert strip_speaker_labels("  전파는 파동입니다.  ") == ("전파는 파동입니다.", False)


# ── 문장 분리 ─────────────────────────────────────────────────────────

def test_공백_없이_붙은_문장도_나눈다():
    """`build_generate` 가 절을 `"".join` 해서 문장 사이 공백이 없다(실측)."""
    assert split_sentences("첫째입니다.둘째입니까?셋째!") == ["첫째입니다.", "둘째입니까?", "셋째!"]


def test_소수점에서는_나누지_않는다():
    """체험관 대역 설명에 "2.4GHz" 같은 수가 자주 나온다."""
    assert split_sentences("주파수는 2.4GHz입니다. 파장은 12.5센티미터입니다.") == [
        "주파수는 2.4GHz입니다.", "파장은 12.5센티미터입니다.",
    ]


def test_연속된_종결부호는_한_문장_끝이다():
    assert split_sentences("정말요?! 그렇군요... 좋네요.") == ["정말요?!", "그렇군요...", "좋네요."]


def test_종결부호가_없으면_한_문장이다():
    assert split_sentences("끝맺음 없는 말") == ["끝맺음 없는 말"]


# ── 분량 상한 ─────────────────────────────────────────────────────────

def test_문장_수_상한에서_문장_경계로_자른다():
    raw = "하나입니다.둘입니다.셋입니다.넷입니다."
    assert cap_length(raw, max_sentences=2, max_chars=1000) == ("하나입니다.둘입니다.", True)


def test_글자_수_상한을_넘기_전_문장까지만_남긴다():
    raw = "가나다라마.바사아자차.카타파하."   # 6자 + 6자 + 5자 = 17자
    assert cap_length(raw, max_sentences=10, max_chars=12) == ("가나다라마.바사아자차.", True)


def test_첫_문장은_상한을_넘어도_통째로_남긴다():
    """문장 중간에서 자르면 TTS 가 말을 뚝 끊는다 — 그게 조금 긴 것보다 나쁘다."""
    raw = "이 문장은 상한보다 훨씬 길지만 잘리면 안 됩니다.다음 문장은 버린다."
    assert cap_length(raw, max_sentences=5, max_chars=10) == (
        "이 문장은 상한보다 훨씬 길지만 잘리면 안 됩니다.", True,
    )


def test_상한_안이면_원문_그대로다():
    raw = "하나입니다. 둘입니다."
    assert cap_length(raw, max_sentences=5, max_chars=280) == ("하나입니다. 둘입니다.", False)


def test_자른_뒤에도_원문의_간격을_보존한다():
    raw = "하나입니다. 둘입니다. 셋입니다."
    assert cap_length(raw, max_sentences=2, max_chars=280) == ("하나입니다. 둘입니다.", True)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_speech_text.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.speech_text'`

- [ ] **Step 3: 구현한다**

`stage/speech_text.py`:

```python
"""생성된 대사를 말할 수 있는 모양으로 다듬는다 — 순수 함수만.

LLM 이 낸 텍스트는 두 갈래로 간다: 로봇의 TTS(`say`)와 감독의 대화 이력
(`Director._remember`). `stage/__main__.py::build_generate` 가 생성 직후 여기를
한 번 지나게 해서 두 갈래가 **함께** 깨끗해진다. 한쪽만 고치면 다른 쪽이
다음 생성을 다시 오염시킨다 — 이력에 "사회자: 사회자:" 가 쌓이면 모델이 그
이중 이름표를 따라 말한 것이 실측이다(2026-09-21 실기 리허설, mc:74).
"""

import re

# 이력의 화자 접두(`stage/director.py::SPEAKER_LABEL` + 관람객). **콜론이 붙은
# 경우만** 이름표다 — "사회자님 말씀처럼" 같은 정상 문장은 건드리지 않는다.
# 마크다운 강조(`**사회자:**`)와 전각 콜론도 모델이 실제로 낸다.
_NAMES = r"(?:사회자|도슨트|관람객)"
_LEADING = re.compile(rf"^(?:[*\s]*{_NAMES}[*\s]*[:：])+[*\s]*")
_INNER = re.compile(rf"\**{_NAMES}[*\s]*[:：]")

# 문장 끝: 종결부호 묶음 뒤에 **숫자가 아닌 것**이 오거나 끝. `build_generate`
# 가 절을 `"".join` 하므로 문장 사이에 공백이 없다("입니다.이 기관은") —
# 공백에 기대면 못 나눈다. 숫자를 빼는 이유는 "2.4GHz"·"12.5센티미터" 같은
# 소수점이 체험관 설명에 자주 나오기 때문이다.
_SENT_END = re.compile(r"[.?!…]+(?![0-9])")


def strip_speaker_labels(text: str) -> tuple[str, bool]:
    """앞머리 이름표를 걷고, 본문 안에 이름표가 또 나오면 그 앞에서 자른다.

    본문 안의 이름표는 **상대 턴을 이어 쓴 것**이다(실측 docent:106 — 도슨트
    한 발화 안에 "…것입니다.사회자: 사회자: …" 로 사회자 반응이 붙었다). 그
    뒤는 이 로봇의 대사가 아니므로 버린다.

    돌려주는 bool 은 "이름표 때문에 바뀌었나" 다 — 앞뒤 공백 차이는 치지 않는다.
    """
    s = text.strip()
    body = _LEADING.sub("", s, count=1)
    m = _INNER.search(body)
    if m:
        body = body[: m.start()]
    body = body.strip()
    return body, body != s


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENT_END.finditer(text):
        if text[start : m.end()].strip():
            spans.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def split_sentences(text: str) -> list[str]:
    return [text[a:b].strip() for a, b in _sentence_spans(text)]


def cap_length(text: str, max_sentences: int, max_chars: int) -> tuple[str, bool]:
    """문장 경계에서 분량 상한을 건다. (결과, 잘랐는지).

    프롬프트의 분량 지시만으로는 안 지켜진다 — 실측 도슨트 235~517자(목표
    180~280자), 사회자 147~195자(목표 40~120자). `max_tokens` 는 문장 중간을
    자르므로 상한 역할을 못 한다.

    - 문장을 앞에서부터 담다가 문장 수가 `max_sentences` 에 닿거나 누적 길이가
      `max_chars` 를 넘으면 멈춘다. 길이는 원문 앞에서부터의 글자 수다.
    - **첫 문장은 길어도 통째로 남긴다.** 문장 중간 절단은 TTS 가 말을 뚝 끊어
      조금 긴 것보다 나쁘다.
    - 잘라도 원문의 간격을 그대로 둔다 — 새로 이어 붙이지 않는다.
    """
    s = text.strip()
    spans = _sentence_spans(s)
    if not spans:
        return s, False
    cut_end = spans[0][1]
    kept = 1
    for _, end in spans[1:]:
        if kept >= max_sentences or end > max_chars:
            break
        cut_end = end
        kept += 1
    if kept == len(spans):
        return s, False
    return s[:cut_end].strip(), True
```

- [ ] **Step 4: 통과를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_speech_text.py -q`
Expected: 전부 PASS

- [ ] **Step 5: 뮤테이션 두 개를 직접 돌린다**

(a) `_SENT_END` 의 `(?![0-9])` 를 지운다 → `test_소수점에서는_나누지_않는다` 가 FAIL 해야 한다.
(b) `strip_speaker_labels` 에서 `if m: body = body[: m.start()]` 두 줄을 지운다 → `test_상대_턴까지_이어_쓴_생성문은_그_이름표_앞에서_자른다` 가 FAIL 해야 한다.
둘 다 `PYTHONDONTWRITEBYTECODE=1` 로 돌린다. 확인 후 되돌리고, 파일 내용이 Step 3 의 코드와 같은지 다시 읽어 확인한다(신규 파일이라 `git diff` 로는 되돌림이 안 보인다).

- [ ] **Step 6: 전체 테스트**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q`
Expected: 이전 통과 수 + 이 파일의 테스트 수, 실패 0

- [ ] **Step 7: 커밋**

```bash
git add stage/speech_text.py tests/test_speech_text.py
git commit -m "$(cat <<'EOF'
feat(stage): 생성문 정리 함수 — 이름표 제거·상대 턴 절단·문장 경계 분량 상한

실기 리허설에서 생성문에 "사회자:"/"도슨트:" 가 섞여 소리로 나갔고, 도슨트가
목표(180~280자)의 두 배 가까이 말했다. 배선은 다음 커밋에서 한다 — 여기는
순수 함수와 그 테스트뿐이다. 소수점("2.4GHz")에서 문장을 나누지 않는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `build_generate` 배선 — 이력 시점 변환·생성문 정리·분량 상한 + 프롬프트 규칙

**모델:** opus (LLM 메시지 구조, 기존 테스트 계약 변경, 경고 규약이 얽힌다)

**Files:**
- Modify: `stage/__main__.py:32-58` (`build_generate`) 와 그 위에 `history_for` 추가
- Modify: `stage/prompts.py:19-22` (`_COMMON`)
- Modify: `tests/test_stage_main.py:70-93` (`test_이력을_호출마다_갈아끼운다` — **계약이 바뀐다**), 테스트 추가
- Modify: `tests/test_prompts.py` (테스트 추가)
- Modify: `docs/lessons.md` (파일 끝에 세 항목)

**Interfaces:**
- Consumes: Task 1 의 `strip_speaker_labels(text) -> tuple[str, bool]`, `cap_length(text, max_sentences, max_chars) -> tuple[str, bool]`; `stage.director.SPEAKER_LABEL: dict[str, str]`(`{"mc": "사회자", "docent": "도슨트"}`); `stage.prompts._MC_MAX_SENTENCES`(3), `_MC_MAX_CHARS`(120); `Level.max_sentences`, `Level.max_chars`
- Produces:
  - `history_for(role: str, history: list[dict]) -> list[dict]`
  - `build_generate(level, warn: Callable[[str], None] = print) -> Callable[[str, str, list[dict]], str]` — 호출부(`main()`, `scripts/pregen_mc_lines.py`)는 `build_generate(level)` 그대로 둔다

**설계(왜 이렇게 하는가):**

1. **이력을 생성하는 역할의 시점으로 바꾼다.** 자기 줄은 `assistant`(이름표 떼고), 남의 줄(상대 역할·관람객)은 `user`(이름표 유지 — 누가 한 말인지 알아야 한다). 지금은 사회자·도슨트 줄이 전부 `assistant` 라 모델이 상대의 말을 자기 말로 보고, 그 말들이 전부 "이름표: 텍스트" 라 따라 한다.
2. **같은 역할이 연달아 오면 한 메시지로 합치고(줄바꿈), 이력 끝이 `user` 면 그 내용을 이번 지시문 앞에 붙인다.** Gemma 계열 채팅 템플릿은 역할 교대를 강제하는 경우가 있다. 서버가 거절하면 모든 생성이 큐시트 폴백으로 떨어진다(경고는 나지만 시연 품질이 통째로 무너진다). 지금 서버가 연속 `assistant` 를 받아 준 것은 실측했지만, 연속 `user` 는 확인 못 했다 — 합쳐 두면 템플릿의 엄격성과 무관하게 안전하다.
3. **생성 직후 이름표 정리 → 분량 상한 순으로 걸고, 바뀌면 경고한다.** 순서가 중요하다: 이름표·상대 턴을 먼저 걷어야 문장 수를 바르게 센다. 사회자 받아치기의 질문 유도는 `Director` 가 생성 **뒤에** 보강한다(`stage/director.py:937` `invites_question`) — 상한으로 질문 문장이 잘려도 기존 가드가 고정 문구로 채운다.
4. 한도는 **프롬프트가 모델에게 준 바로 그 수**를 쓴다 — 도슨트 `level.max_sentences`/`level.max_chars`, 사회자 `stage.prompts._MC_MAX_SENTENCES`/`_MC_MAX_CHARS`. 두 곳에 따로 적으면 한쪽이 먼저 썩는다.

- [ ] **Step 1: 기존 이력 테스트를 새 계약으로 바꾸고, 배선 테스트를 더한다 (먼저 실패시킨다)**

`tests/test_stage_main.py` 의 `test_이력을_호출마다_갈아끼운다`(70~93행)를 **통째로** 아래로 바꾸고, 같은 자리에 나머지 테스트를 이어 붙인다:

```python
class _기록LLM:
    """`build_generate` 가 LLM 에 실제로 무엇을 싣는지 기록한다."""
    본것: list[tuple[str, list[dict]]] = []
    답: list[str] = ["답"]

    def __init__(self, **kw):
        self.history: list[dict] = []

    def chat_stream(self, brief, image):
        type(self).본것.append((brief, list(self.history)))
        return iter(type(self).답)


@pytest.fixture
def 기록LLM(monkeypatch):
    _기록LLM.본것 = []
    _기록LLM.답 = ["답"]
    monkeypatch.setattr(stage_main, "LLMClient", _기록LLM)
    return _기록LLM


def test_이력은_생성하는_역할의_시점으로_바꿔_싣는다(기록LLM):
    """자기 말은 assistant(이름표 없이), 남의 말은 user(이름표 유지).

    예전에는 받은 이력을 그대로 실었고, 사회자·도슨트 줄이 **전부 assistant**
    였다 — 모델이 상대의 말을 자기 말로 보고 "이름표: 텍스트" 모양을 따라 해
    실기에서 "사회자:" 를 소리 내 읽었다(2026-09-21, mc:42). 이력 끝의 남의 말은
    이번 지시문 앞으로 옮긴다 — user 가 연달아 가지 않게.
    """
    generate = stage_main.build_generate(_레벨)
    이력 = [
        {"role": "assistant", "content": "사회자: 첫 질문"},
        {"role": "assistant", "content": "도슨트: 첫 해설"},
        {"role": "assistant", "content": "사회자: 다음 질문"},
    ]
    assert generate("docent", "지시", 이력) == "답"
    assert 기록LLM.본것 == [(
        "사회자: 다음 질문\n\n지시",
        [
            {"role": "user", "content": "사회자: 첫 질문"},
            {"role": "assistant", "content": "첫 해설"},
        ],
    )]


def test_같은_역할이_연달아_오면_한_메시지로_합친다(기록LLM):
    """역할 교대를 강제하는 채팅 템플릿이 있다 — 거절당하면 모든 생성이 폴백으로 떨어진다."""
    generate = stage_main.build_generate(_레벨)
    이력 = [
        {"role": "assistant", "content": "사회자: 여는 말"},
        {"role": "assistant", "content": "사회자: 덧붙임"},
        {"role": "user", "content": "관람객: 질문 하나"},
        {"role": "assistant", "content": "도슨트: 답"},
    ]
    generate("mc", "지시", 이력)
    assert 기록LLM.본것 == [(
        "관람객: 질문 하나\n도슨트: 답\n\n지시",
        [{"role": "assistant", "content": "여는 말\n덧붙임"}],
    )]


def test_생성문의_화자_이름표를_걷고_경고한다(기록LLM):
    기록LLM.답 = ["사회자: 사회자: ", "좋은 설명이네요."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("mc", "지시", []) == "좋은 설명이네요."
    assert any("이름표" in w for w in 경고), 경고


def test_상대_턴까지_이어_쓴_생성문은_그_앞에서_자른다(기록LLM):
    """실측 docent:106 — 도슨트 한 발화 안에 사회자 반응이 이어 붙었다."""
    기록LLM.답 = ["설명을 마칩니다.", "사회자: 반응입니다."]
    generate = stage_main.build_generate(_레벨, warn=lambda m: None)
    assert generate("docent", "지시", []) == "설명을 마칩니다."


def test_도슨트_생성문은_수준_상한_5문장에서_자르고_경고한다(기록LLM):
    """일반 수준은 4~5문장 / 180~280자(`data/levels.yaml`). 수는 리터럴로 박는다."""
    기록LLM.답 = ["하나.", "둘.", "셋.", "넷.", "다섯.", "여섯.", "일곱."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("docent", "지시", []) == "하나.둘.셋.넷.다섯."
    assert any("5문장/280자" in w for w in 경고), 경고


def test_사회자_생성문은_고정_상한_3문장에서_자른다(기록LLM):
    """사회자는 수준과 무관하게 1~3문장 / 40~120자(`stage/prompts.py`)."""
    기록LLM.답 = ["하나.", "둘.", "셋.", "넷.", "다섯."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("mc", "지시", []) == "하나.둘.셋."
    assert any("3문장/120자" in w for w in 경고), 경고


def test_깨끗하고_상한_안인_생성문은_그대로이고_경고하지_않는다(기록LLM):
    """위 두 경고 테스트의 짝 — 이것이 없으면 "늘 경고한다" 도 통과한다."""
    기록LLM.답 = ["전파는 파동입니다.", "눈에 보이지 않습니다."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("docent", "지시", []) == "전파는 파동입니다.눈에 보이지 않습니다."
    assert 경고 == []
```

`tests/test_prompts.py` 끝에 더한다:

```python
def test_조립된_프롬프트_전부에_이름표_금지_규칙이_있다():
    """모델이 "사회자:" 를 붙여 말하면 TTS 가 그대로 읽는다(2026-09-21 실기).
    두 역할 × 네 수준 전수. "이름표" 는 리터럴로 본다."""
    for name, lv in load_levels().items():
        for role in ("mc", "docent"):
            p = build_system_prompt(role, lv)
            assert "이름표" in p, (role, name)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_stage_main.py tests/test_prompts.py -q`
Expected: 새 테스트들 FAIL — `build_generate() got an unexpected keyword argument 'warn'`, 이력 단언 불일치, `"이름표" in p` False

- [ ] **Step 3: `_COMMON` 에 규칙을 더한다**

`stage/prompts.py:19-22` 를 바꾼다(주석 규약: 이 조각은 `**`·목록 기호를 쓰지 않는다):

```python
_COMMON = (
    "네 말은 음성으로 읽힌다. 목록·이모지·특수문자·마크다운을 쓰지 않고 "
    "문장은 마침표로 끝낸다. 대사 앞에 사회자나 도슨트 같은 화자 이름표를 "
    "붙이지 않고, 상대의 말을 이어 쓰지 않고, 네가 할 말만 한다."
)
```

그리고 바로 위 주석 블록(14~18행) 끝에 한 줄을 더한다:

```python
# 이름표 금지는 2026-09-21 실기에서 모델이 "사회자:" 를 붙여 말해 TTS 가 그대로
# 읽은 뒤 들어갔다. 프롬프트만으로는 못 막아서 `stage/speech_text.py` 가 생성
# 직후에 한 번 더 걷는다 — 이 문장은 그 빈도를 낮추는 몫이다.
```

- [ ] **Step 4: `build_generate` 를 고친다**

`stage/__main__.py` 머리의 import 에 더한다(`from llm import LLMClient` 줄 **아래**, `# noqa: E402` 유지):

```python
from typing import Callable  # noqa: E402

from stage.director import SPEAKER_LABEL  # noqa: E402
from stage.prompts import _MC_MAX_CHARS, _MC_MAX_SENTENCES  # noqa: E402
from stage.speech_text import cap_length, strip_speaker_labels  # noqa: E402
```

`build_generate` 바로 위에 추가한다:

```python
def history_for(role: str, history: list[dict]) -> list[dict]:
    """감독의 공용 이력을 **생성하는 역할의 시점**으로 바꾼다.

    감독의 이력은 하나이고 내용 앞에 "사회자:"/"도슨트:"/"관람객:" 이 붙는다
    (`Director._remember`, 설계 §5.2). 그대로 실으면 사회자·도슨트 줄이 전부
    `assistant` 라 모델이 **상대의 말을 자기 말로** 보고, 그 말들이 전부
    "이름표: 텍스트" 모양이라 따라 한다 — 2026-09-21 실기에서 사회자가 "사회자:"
    를 소리 내 읽었다(mc:42).

    - 자기 줄 → `assistant`, 이름표를 뗀다(모델이 흉내 낼 원본을 없앤다)
    - 남의 줄 → `user`, 이름표를 둔다(누가 한 말인지는 알아야 한다)
    - 같은 역할이 연달아 오면 한 메시지로 합친다 — 역할 교대를 강제하는 채팅
      템플릿에 거절당하면 모든 생성이 큐시트 폴백으로 떨어진다
    """
    own = SPEAKER_LABEL[role] + ":"
    out: list[dict] = []
    for h in history:
        content = h["content"]
        if content.startswith(own):
            msg = {"role": "assistant", "content": content[len(own):].strip()}
        else:
            msg = {"role": "user", "content": content}
        if out and out[-1]["role"] == msg["role"]:
            out[-1] = {
                "role": msg["role"],
                "content": out[-1]["content"] + "\n" + msg["content"],
            }
        else:
            out.append(msg)
    return out
```

`build_generate` 를 통째로 바꾼다(docstring 의 기존 두 문단은 **유지**하고 뒤에 이어 쓴다):

```python
def build_generate(level, warn: Callable[[str], None] = print) -> "callable":
    """LLM 호출 하나. **직렬화한다.**

    두 화자가 **하나의 대화 이력**을 봐야 말이 이어진다 — B 의 대사는 A 가
    정해진 뒤에야 만들 수 있으므로 병렬이 아니라 파이프라인이다. 그래서
    클라이언트를 역할별로 둬도 락은 하나다.

    페르소나는 이제 역할·수준의 함수다(`stage/prompts.py`) — 도슨트만
    기술하던 문자열 하나(`_system_prompt`, 이 함수가 지웠다) 대신
    [공통 규약 + 역할 + 수준] 세 조각을 역할별로 조립한다.

    **모든 생성이 여기를 지나므로 생성문 정리도 여기서 한다**(도슨트 해설·질문
    응답·사회자 받아치기·예비·사전 생성 여는 대사). 텍스트가 TTS 와 감독 이력으로
    갈라지기 전이라 두 갈래가 함께 깨끗해진다. 순서는 이름표 정리 → 분량 상한 —
    상대 턴을 먼저 걷어야 문장 수를 바르게 센다. 바뀌면 반드시 경고한다.
    분량 한도는 프롬프트가 모델에게 준 바로 그 수다(두 곳에 따로 적으면 썩는다).
    """
    from stage.prompts import ROLES, build_system_prompt

    clients = {
        r: LLMClient(system_prompt=build_system_prompt(r, level),
                     max_tokens=level.max_tokens)
        for r in ROLES
    }
    limits = {
        "docent": (level.max_sentences, level.max_chars),
        "mc": (_MC_MAX_SENTENCES, _MC_MAX_CHARS),
    }
    lock = threading.Lock()

    def generate(role: str, brief: str, history: list[dict]) -> str:
        with lock:
            c = clients[role]
            hist = history_for(role, history)
            # 이력 끝의 남의 말은 이번 지시문 앞으로 옮긴다 — `chat_stream` 이
            # 지시문을 user 로 붙이므로 그대로 두면 user 가 연달아 간다.
            if hist and hist[-1]["role"] == "user":
                brief = hist.pop()["content"] + "\n\n" + brief
            c.history = hist
            raw = "".join(c.chat_stream(brief, None))
        text, stripped = strip_speaker_labels(raw)
        if stripped:
            warn(f"[{role}] 생성문에 화자 이름표/상대 턴이 섞여 걷어냈다: {raw[:60]!r}")
        max_sentences, max_chars = limits[role]
        text, capped = cap_length(text, max_sentences, max_chars)
        if capped:
            warn(
                f"[{role}] 생성문이 분량 상한({max_sentences}문장/{max_chars}자)을 "
                "넘어 문장 경계에서 잘랐다"
            )
        return text

    return generate
```

- [ ] **Step 5: 통과를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_stage_main.py tests/test_prompts.py tests/test_pregen.py -q`
Expected: 전부 PASS

- [ ] **Step 6: 뮤테이션 세 개를 직접 돌린다 (`PYTHONDONTWRITEBYTECODE=1`)**

(a) `history_for` 에서 남의 줄을 `"user"` 대신 `"assistant"` 로 → `test_이력은_생성하는_역할의_시점으로_바꿔_싣는다` FAIL
(b) `limits` 의 `"docent"` 를 `(_MC_MAX_SENTENCES, _MC_MAX_CHARS)` 로(두 역할에 같은 값 — 함정 2) → `test_도슨트_생성문은_수준_상한_5문장에서_자르고_경고한다` FAIL
(c) `if capped:` 블록을 지운다 → 같은 테스트의 경고 단언 FAIL
각각 확인 후 되돌리고 `git diff` 로 되돌림을 확인한다.

- [ ] **Step 7: `docs/lessons.md` 파일 끝에 세 항목을 붙인다**

```markdown
### 이력 내용에 화자 이름표를 박으면 모델이 그 이름표를 따라 말한다

- **증상**(실기 2대 리허설, 2026-09-21): 사회자가 `사회자: 한국방송통신전파진흥원이…`
  를 **소리 내 읽었다**(mc:42). 뒤로 갈수록 `사회자: 사회자: …`(mc:74),
  `도슨트: 도슨트: …`(docent:122)로 이름표가 겹쳤고, 도슨트 한 발화 안에
  `…것입니다.사회자: 사회자: 방송통신 진흥과…` 로 **사회자 반응까지 이어 썼다**
  (docent:106). 듣는 사람에게는 "역할이 바뀐 것" 처럼 들렸다. 웹소켓 라우팅은
  매번 정확했다 — 배선이 아니라 콘텐츠 문제다.
- **원인**: `Director._remember` 가 이름표를 이력 **내용 문자열에** 박고
  (`f"{SPEAKER_LABEL[role]}: {text}"`), 관람객 외 모든 줄을 `assistant` 로
  넣었다. `build_generate` 는 그대로 실었다. 모델은 상대의 말까지 자기 말로 보고
  "이름표: 텍스트" 모양을 흉내 냈다. 생성문이 이미 이름표로 시작하면 이력에
  이중 이름표가 쌓여 다음 생성이 그것을 또 흉내 내는 **되먹임 고리**였다.
- **규칙**: 공용 이력을 LLM 에 실을 때는 **생성하는 역할의 시점**으로 바꾼다 —
  자기 말은 assistant(이름표 없이), 남의 말은 user(이름표 유지). 생성문은
  TTS 와 이력으로 갈라지기 **전** 한 곳(`build_generate`)에서 정리한다. 한쪽만
  고치면 다른 쪽이 다음 생성을 다시 오염시킨다. 프롬프트 지시("이름표 없이")는
  빈도를 낮출 뿐 막지 못한다.
- **박제**: `tests/test_stage_main.py::test_이력은_생성하는_역할의_시점으로_바꿔_싣는다`,
  `::test_생성문의_화자_이름표를_걷고_경고한다`,
  `::test_상대_턴까지_이어_쓴_생성문은_그_앞에서_자른다`,
  `tests/test_speech_text.py`.

### 생성 분량은 프롬프트 지시만으로 지켜지지 않는다 — 문장 경계에서 상한을 건다

- **증상**(같은 리허설): 도슨트 해설 235~517자(목표 180~280자, 13개 중 11개
  초과), 사회자 받아치기 147~195자(목표 40~120자). 한 큐의 음성이 75~120초였다.
- **원인**: `max_tokens=624` 는 280자 목표의 두 배가 넘는 여유라 하드 스톱이
  못 되고, 걸린다 해도 문장 중간을 자른다. 모델은 이력이 길수록 분량 지시를 덜
  지킨다.
- **규칙**: 분량은 생성 **뒤에** 문장 경계에서 자른다. 한도는 프롬프트가 모델에게
  준 바로 그 수를 한 곳에서 읽는다. 첫 문장은 길어도 남긴다. 잘랐으면 경고한다.
  문장 분리는 공백에 기대지 않는다(`"".join` 된 절에는 공백이 없다) — 소수점
  ("2.4GHz")에서 나누지 않도록 종결부호 뒤 숫자를 뺀다.
- **박제**: `tests/test_stage_main.py::test_도슨트_생성문은_수준_상한_5문장에서_자르고_경고한다`,
  `::test_사회자_생성문은_고정_상한_3문장에서_자른다`,
  `tests/test_speech_text.py::test_소수점에서는_나누지_않는다`.

### "합성이 오래 걸린다" ≠ "TTS 가 느리다" — RTF 로 판단한다

- **증상**(같은 리허설, 분석 단계의 오진): `tts.log` 의 `synthesis finished in
  51.56s` 를 보고 "TTS 가 문장당 30~60초라 실시간 대화가 안 된다" 고 결론 냈다.
  틀렸다.
- **원인**: 합성 시간만 보고 **만들어진 오디오 길이**를 안 봤다. 같은 로그의
  `produced … → N samples` 를 24000 으로 나누면 오디오가 45~87초였고, RTF 는
  0.65~0.80 — 실시간보다 빨랐다. 문제는 분량(위 항목)이었다.
- **규칙**: 속도를 판단할 때는 **RTF(합성 시간 ÷ 오디오 길이)** 로 본다. 짧은
  오디오인데 RTF 가 3~4 로 튀는 것(실측 3건)만이 대기열·경합의 신호다 — 그건
  별개로 검증한다(TTS 서버 직렬 처리 가설, 미검증).
```

- [ ] **Step 8: 전체 테스트**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q`
Expected: 실패 0

- [ ] **Step 9: 커밋**

```bash
git add stage/__main__.py stage/prompts.py tests/test_stage_main.py tests/test_prompts.py docs/lessons.md
git commit -m "$(cat <<'EOF'
fix(stage): 생성문에서 화자 이름표를 걷고 분량 상한을 건다

실기 리허설에서 사회자가 "사회자:" 를 소리 내 읽고, 도슨트가 사회자 반응까지
이어 썼다. 공용 이력이 사회자·도슨트 줄을 전부 assistant 로, 이름표를 내용에
박은 채 실어서 모델이 그 모양을 흉내 냈다. 이력을 생성하는 역할의 시점으로
바꿔 싣고(자기 말 assistant, 남의 말 user, 같은 역할 연속은 합침), 생성 직후
이름표 정리 → 문장 경계 분량 상한을 건다. 바뀌면 경고한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: STT 무음 상용구 — 구두점까지 걷고 비교, 실측 문구 추가

**모델:** sonnet

**Files:**
- Modify: `apps/voice_chat/voice_chat/voice_loop.py:87-96` (`_WHISPER_FILLER`, `_filler`)
- Create: `tests/test_stt_filler.py`
- Modify: `docs/lessons.md` (파일 끝에 한 항목)

**Interfaces:**
- Consumes: 없음
- Produces: `voice_loop._filler(text: str) -> bool` — 시그니처 그대로, 판정만 넓어진다

⚠️ **"다음" 은 진행 키워드다**(`stage/cues.py::is_advance`). "다음 영상에서 만나요" 를 막으면서 "다음" 을 막으면 관람객이 진행을 못 시킨다 — 테스트로 박는다.

⚠️ 이 파일은 **로봇에 올라가는 앱**이다. 실기 반영은 `./reachy.sh robot deploy` 가 필요하다(최종 검증에서 한다). 1대 모드도 같은 경로라 함께 좋아진다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stt_filler.py`:

```python
"""STT 무음 상용구 판정(`apps/voice_chat/voice_chat/voice_loop.py::_filler`).

실기 2대 리허설(2026-09-21)에서 두 문구가 관람객 질문으로 처리됐다:
"다음 영상에서 만나요."(마이크 최대 0.002, 사실상 무음) → 도슨트가 "다음 영상에서
다시 만나 뵙기를 희망하시는군요" 라고 답했다. "Come." 도 질문이 됐다.

`voice_loop` 는 다른 테스트처럼 **함수 안에서** import 한다 — 모듈 수준의
환경변수 읽기가 테스트 간에 섞이지 않게.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))


@pytest.mark.parametrize("text", [
    "다음 영상에서 만나요.",   # 실측
    "다음 영상에서 만나요",
    "Come.",                  # 실측
    "come",
    "감사합니다.",             # 기존 항목 — 구두점 차이를 두 번 적던 것을 한 번으로
    "감사합니다",
    "Thank you.",
    "!",                      # 구두점만 남는 전사(2026-09-09 실기 `!` 전례)
    " 。 ",
])
def test_무음_상용구는_버린다(text):
    import voice_loop as vl
    assert vl._filler(text) is True


@pytest.mark.parametrize("text", [
    "다음",                   # 진행 키워드 — 막으면 관람객이 진행을 못 시킨다
    "다음으로 넘어가 주세요",
    "전파는 어떻게 이동하나요?",
    "감사합니다 그런데 질문이 있어요",
    "Come here please",
])
def test_말이_되는_전사는_살린다(text):
    import voice_loop as vl
    assert vl._filler(text) is False
```

- [ ] **Step 2: 실패를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_stt_filler.py -q`
Expected: `다음 영상에서 만나요.`/`다음 영상에서 만나요`/`Come.`/`come`/`!` 케이스 FAIL. (`감사합니다.`·`Thank you.`·` 。 ` 는 옛 목록에 구두점째 적혀 있어 **이미 통과한다** — 구두점 제거로 항목을 줄여도 계속 걸리는지 지키는 회귀 케이스다.)

- [ ] **Step 3: 구현한다**

`apps/voice_chat/voice_chat/voice_loop.py:87-96` 을 바꾼다(`re` 는 이 파일에서 이미 import 돼 있다 — `_has_wake` 가 쓴다):

```python
# Whisper 가 무음·잡음에서 습관적으로 뱉는 말들. 반복 토막 검사로는 안 걸린다.
# 비교는 `_flatten()` 한 모양(공백·구두점 제거, 소문자)으로 한다 — 항목도 그
# 모양으로 적는다. ~~"감사합니다" 와 "감사합니다." 를 따로 적는다~~ — 구두점을
# 걷고 비교하면서 중복 항목과 "。"/"." 항목이 필요 없어졌다(빈 문자열이 된다).
_WHISPER_FILLER = {
    "감사합니다", "시청해주셔서감사합니다", "구독과좋아요부탁드립니다",
    "thankyou", "thanksforwatching", "you",
    # 실기 2대 리허설(2026-09-21): 마이크 최대 0.002(사실상 무음)에서 나와 관람객
    # 질문으로 처리됐다 — 도슨트가 "다음 영상에서 다시 만나 뵙기를…" 로 답했다.
    # "다음" 이 들어 있지만 진행 키워드 "다음" 자체는 이 목록과 **정확 일치**해야
    # 걸리므로 막히지 않는다(tests/test_stt_filler.py).
    "다음영상에서만나요",
    # 같은 리허설: 한국어 관람객 앞에서 영어 한 단어로 나와 질문이 됐다.
    "come",
}


def _flatten(text: str) -> str:
    """공백·구두점을 걷고 소문자로 — 상용구 비교용. 한글은 `\\w` 라 남는다."""
    return re.sub(r"[\W_]+", "", text.lower())


def _filler(text: str) -> bool:
    """내용 없는 상용구 — 무음에 가까운 입력에서 나오는 환각이다.

    구두점만 남는 전사(`!`, `.`)도 여기서 버린다 — 2026-09-09 실기에서 `!` 가
    그대로 통과해 로봇이 엉뚱한 답을 했다.
    """
    flat = _flatten(text)
    return not flat or flat in _WHISPER_FILLER
```

- [ ] **Step 4: 통과를 확인한다**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_stt_filler.py tests/test_barge_in.py -q`
Expected: 전부 PASS

- [ ] **Step 5: 뮤테이션 (`PYTHONDONTWRITEBYTECODE=1`)**

`_filler` 의 `return not flat or flat in _WHISPER_FILLER` 를 `return flat in _WHISPER_FILLER` 로 → `test_무음_상용구는_버린다[!]` FAIL. 확인 후 되돌린다.

- [ ] **Step 6: `docs/lessons.md` 파일 끝에 붙인다**

```markdown
### Whisper 무음 상용구는 구두점까지 걷고 비교한다 — 목록은 실측으로 는다

- **증상**(실기 2대 리허설, 2026-09-21): 마이크 최대 0.002(사실상 무음)에서
  `다음 영상에서 만나요.` 가 전사돼 관람객 질문으로 처리됐다 — 사회자가 "좋은
  질문이네요" 로 받고 도슨트가 "다음 영상에서 다시 만나 뵙기를 희망하시는군요"
  라고 답했다(mc:151, docent:86). `Come.` 도 같은 길로 질문이 됐다(mc:179).
- **원인**: `_filler` 가 공백만 걷고 차단 목록과 **정확 일치**로 봤다. 두 문구 다
  목록에 없었다. 구두점 차이는 항목을 두 번 적어 막고 있었다("감사합니다"/
  "감사합니다.").
- **규칙**: 비교 전에 **구두점까지** 걷는다(`_flatten`). 구두점만 남으면 상용구로
  본다. 목록은 실측으로만 늘린다 — "영어 한 단어는 전부 버린다" 같은 넓은 규칙은
  근거가 없다. 진행 키워드("다음")가 목록 항목에 **포함**돼 있어도 정확 일치라
  막히지 않는다는 것을 테스트로 박는다.
- **박제**: `tests/test_stt_filler.py::test_무음_상용구는_버린다`,
  `::test_말이_되는_전사는_살린다`.
```

- [ ] **Step 7: 전체 테스트 후 커밋**

Run: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q`
Expected: 실패 0

```bash
git add apps/voice_chat/voice_chat/voice_loop.py tests/test_stt_filler.py docs/lessons.md
git commit -m "$(cat <<'EOF'
fix(voice): STT 무음 상용구를 구두점까지 걷고 비교한다

실기 리허설에서 무음 구간의 Whisper 환각 "다음 영상에서 만나요." 와 "Come." 이
관람객 질문으로 처리돼 도슨트가 그 말에 답했다. 차단 목록이 공백만 걷고 정확
일치로 봐서 두 문구가 빠져나갔다. 구두점까지 걷고, 구두점만 남으면 상용구로
보고, 실측 두 문구를 더한다. 진행 키워드 "다음" 은 막히지 않는다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## 최종 검증 (컨트롤러가 직접 — 서브에이전트 아님)

1. **전체 테스트**: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q` — 실패 0.
2. **실서버 스모크**(추론 서버 필요 — `REACHY_BIND_HOST=127.0.0.1 ./reachy.sh serve || true`): `build_generate(load_levels()["일반"])` 로 이력 `[사회자, 도슨트, 사회자]` 를 넣어 `docent` 한 번, `mc` 한 번 생성한다. 확인: HTTP 오류 없음(역할 병합이 템플릿에 받아들여지는지), 결과에 `사회자:`/`도슨트:` 없음, 도슨트 ≤5문장·사회자 ≤3문장.
3. **실기 반영**: 앱 변경(Task 3)이 있으므로 두 대 모두 배포한다. **`REACHY_ROLE` 을 반드시 준다** — 빠뜨리면 `robot_config_merge.py` 가 역할을 지워 1대 모드로 뜬다(이번 세션에서 실제로 밟았다):
   ```bash
   REACHY_ROLE=mc     REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh robot deploy
   REACHY_ROLE=docent REACHY_ROBOT_HOST=192.168.0.5 ./reachy.sh robot deploy
   ```
4. **재리허설**: 콘솔은 `s` 한 번만 — **`n` 으로 강제하지 않는다**(강제 진행이 이전 두 번의 끊김을 만들었다). 침묵 8초 자동 진행으로 최소 3큐를 본다. 로그에서 확인:
   - `미니>` 줄에 `사회자:`/`도슨트:` 가 없다
   - 도슨트 발화 ≤5문장, 사회자 받아치기 ≤3문장(+ 감독이 보강한 질문 유도·"다음" 안내)
   - `[상용구 무시 — 환각]` 이 찍히고, 그 문구가 질문으로 처리되지 않는다
   - `[감독 abort — 발화·모션 중단]` 이 자연 진행 구간에서 나오지 않는다
   - (관찰만) 짧은 발화의 RTF 가 3 이상으로 튀는지 — TTS 서버 직렬 대기 가설

## 범위 밖 (후속)

- **TTS 서버 직렬 대기**(§0 결함 2의 가설): 긴 요청을 보내고 몇 초 뒤 끊은 다음 곧바로 짧은 요청을 보내 지연을 잰다. 서버가 중단된 요청을 끝까지 합성하면 확정. 이 계획의 분량 상한이 긴 합성 자체를 줄여 영향이 크게 줄 것으로 본다.
- **여는 대사 캐시 0개**: 매 큐 "여는 대사 캐시가 없다" 경고 — `scripts/pregen_mc_lines.py` 를 돌리면 된다. 이 계획이 생성문 정리를 `build_generate` 에 넣었으므로 사전 생성 대사도 함께 정리된다.
- **전체 리뷰의 남은 항목**: B3(문서 네 곳), B4(큐시트·페르소나 마크다운), I2~I5 — `.superpowers/sdd/2026-09-20-podcast-adlib/final-fix-brief.md`.
- **감독 컨트롤러 대시보드**(두 로봇 카메라·발화 문구를 좌우로, 중단·큐별 진행 컨트롤): 신규 기능 — brainstorming 과 디자인 시안 5개가 먼저다.
