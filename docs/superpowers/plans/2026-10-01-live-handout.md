# 교육자료 "공연 따라가기" 라이브 모드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공연 중 관람객 기기의 교육자료(`/handout`)가 감독이 말하게 한 대사를 따라 **지금 이야기 중인 큐의 장을 저절로 고르고**, 도슨트가 말하는 대목에 맞춰 카드를 켜고 그림(신호 보내기·주파수 다이얼)을 **저절로 움직이게** 한다. 로봇 재배포·프로토콜 변경 없이 PC(무대감독) 쪽만 바꾼다.

**Architecture:** 감독은 이미 `say` 지시의 `cue_id` 필드에 **발화 라벨**(`02-history:pt1:docent` 등)을 싣고 있고, 이 라벨이 큐와 대목을 모두 담는다(실제 감독을 19큐 끝까지 돌려 확인했다). 읽는 쪽 `stage/say_label.py` 가 라벨을 `{cue, turn}` 으로 풀어 기존 읽기 전용 소켓 `/ws/audience` 의 `say` 메시지에 싣고, `/handout` 한 페이지(모든 수준 포함)가 같은 오리진의 그 소켓에 붙어 따라간다. 카드·시각화는 `data/handout.yaml`(검수한 카드)과 이름 붙은 시각화 부품(`stage/handout_viz.py`/`.js`)으로 **점진 강화**한다 — 카드가 없는 큐도 자막·말풍선 강조만으로 따라간다.

**Tech Stack:** Python 3.12(`.venv/bin/python`), `websockets` sync API, PyYAML, 순수 HTML/CSS/JS(외부 리소스 없음), pytest, 브라우저 테스트는 헤드리스 Chrome + DevTools 프로토콜(`websockets` 로 직접, 크롬이 없으면 건너뜀).

**Spec:** 별도 설계 문서는 없다. 승인된 시안 `docs/design/handout-mock-2sheets.html`(Task 1 에서 커밋)이 사양이고, 설계 결정은 아래 「설계 결정」에 적었다. 시안은 02·03 두 장을 손으로 만든 것이라 **그대로 배포하지 않는다** — 이 계획이 그것을 데이터·부품으로 일반화한다.

## 설계 결정 (사용자와의 Q&A, 2026-10-01)

1. **퀴즈는 넣지 않는다.** 현재 큐 데이터(`data/cues.yaml` 19큐)에는 퀴즈 필드가 없고(키: `id,title,mc,mc_after,docent_brief,gaze,topic,briefs,points,*_emotion`), 공연 중 실시간으로 풀기도 어렵다. 시안의 `확인해 보기`는 이 계획에서 뺀다.
2. **따라가기 신호는 기존 `say` 의 발화 라벨이다.** 아래 표가 실제 Director 에서 확인한 전부다(`tests/test_say_label.py` 가 박제한다).

   | 라벨 | 뜻 | `turn` |
   |---|---|---|
   | `<큐>` | 사회자 여는 말 | `open` |
   | `<큐>:pt<i>` | 사회자 질문(i ≥ 1) | `ask<i>` |
   | `<큐>:pt<i>:docent` | 도슨트 설명(마지막이 아닌 것) | `docent<i>` |
   | `<큐>:docent` | **마지막** 도슨트 설명 | `docent<포인트 수-1>` |
   | `<큐>:after` | 사회자 받아치기 | `after` |
   | `<큐>:ack` · `:qa` · `:reask` | 관람객 질문 흐름 | 같은 이름 |
   | `solo:ack` · `solo:qa` | 단독 모드 | (읽지 않는다 — `cue`·`turn` 은 `null`) |

3. **한 페이지에 모든 수준을 싣고** CSS 라디오 탭으로 고른다 — 공연 중 감독 수준이 바뀌어도 새로고침 없이 따라가야 한다. 수준은 **감독을 따르되, 관람객이 직접 고르면(탭·`?level=`·저장된 선택) 그쪽이 이긴다.**
4. **점진 강화.** 카드(`data/handout.yaml`)와 시각화는 데이터가 있는 큐만 쓴다(지금은 02·03). 없는 큐는 말풍선 대화가 펼쳐진 채 보이고, 말하는 말풍선만 강조된다.
5. **"어느 대목에서 무엇을 움직일지"는 데이터**(`live:`), **그림·도구는 코드**(이름으로 등록)다. 데이터에는 이름만 적고, 모르는 이름은 기동에서 거절한다.
6. **관람객 폰이 닿으려면** 지금은 대시보드를 `0.0.0.0` 에 열어야 하고, 그러면 **인증 없는 조정실도 같이 열린다**(`docs/two-robot-offline-test.md`의 기존 경고). Task 7 이 관람객 경로(`/audience`·`/handout`·`/ws/audience`)만 여는 **별도 읽기 전용 포트**를 제안한다 — 기본 꺼짐이고 **사용자 승인이 필요하다**(건너뛰어도 Task 1~6·8 은 독립적으로 동작한다).
7. **범위 밖**(따로 결정): 폰에 주소를 알리는 QR 안내, 나머지 17큐의 카드·시각화 저작(콘텐츠 작업), 관람객 질문 답을 교육자료에 싣기(검수 전 생성 답이라 싣지 않는다는 기존 결정 유지), 공연 후 복습용 퀴즈.

## Global Constraints

- **모든 작업은 `main` 브랜치에서 한다.** 기능 브랜치·git 워크트리·서브에이전트 `isolation: "worktree"` 금지. 푸시는 사용자가 요청할 때만(CLAUDE.md 작업 규약, 2026-09-24).
- **로봇 재배포 없음.** `stage/protocol.py`·`apps/voice_chat/` 는 건드리지 않는다. 바뀌는 것은 `stage/`·`data/`·`tests/`·`docs/` 뿐이다.
- **관람객 소켓은 읽기 전용이고 운영 정보를 흘리지 않는다.** 소켓에 새로 싣는 칸은 허용 목록(`audience_event`·`AUDIENCE_SNAPSHOT_KEYS`)에 이름을 올린 것만이다. 경고·거부 사유·관람객 STT 원문·연결/카메라 상태는 나가지 않는다.
- **페이지는 외부 리소스를 부르지 않는다**(CDN·웹폰트·이미지 URL 금지 — 전용 공유기는 인터넷이 없다). 글자는 `textContent` 로만 쓴다(`innerHTML`·`outerHTML`·`insertAdjacentHTML`·`document.write` 금지). 소켓으로 `send` 하지 않는다.
- **교육자료의 문장은 검수한 고정 대본과 `data/handout.yaml` 의 검수한 카드뿐이다.** LLM 으로 새로 쓰지 않는다. 카드 속 숫자·연도는 대본 또는 `data/cues-research/<큐>.yaml` 의 `facts` 에 있어야 한다(테스트가 지킨다).
- **교육자료가 깨져도 감독은 산다.** `/handout` 의 실패는 500 + 터미널 경고(`DashboardServer._serve_handout` 의 기존 규칙)이고, 대시보드 import 가 자산 파일 부재로 죽으면 안 된다(자산은 호출 때 읽는다).
- **실패는 소리 내서 실패한다.** 서버는 경고를 남기고(한 번), 페이지는 연결 상태를 화면에 보인다("다시 연결하는 중…"). 조용히 흐려진 채 도는 것이 가장 나쁘다.
- 사용자에게 보이는 글자는 한국어. 테스트 이름은 한국어 문장. 인터프리터는 `.venv/bin/python`. 테스트는 `tests/` 에만 둔다(`pytest.ini`). pytest-asyncio 는 없다 — `websockets` sync API 로 쓴다.
- 커밋은 `main` 에 바로, 제목은 `feat(stage): …`/`fix(stage): …`/`docs: …` 한국어, 끝에 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- 버그를 하나 잡을 때마다 `docs/lessons.md` 에 증상 → 원인 → 규칙 → `tests/…::이름` 을 적는다(Task 8 이 이번 작업의 것을 모은다).

## Review Focus

스펙(시안·설계 결정)이 침묵하지만 관람객·운영자가 실제로 밟을 입력과 조건이다. 각 줄의 테스트가 소유 Task 에 들어 있다.

1. **공연 중간에 폰을 켜거나 새로고침한다** — 처음부터 보던 사람과 같은 장·같은 대목에 서야 하고, 이미 지나간 대목은 "본 것"으로 보여야 한다. (Task 4 `test_공연_중간에_접속하면_지금_큐와_대목에_선다`)
2. **운영자가 되감기·`이 큐 다시`·큐 점프·코스 밖 큐로 간다** — 강조가 처음으로 돌아가고, 코스 밖 큐의 대사는 장을 바꾸지 않고 자막만 띄운다. (Task 4 `test_이_큐_다시와_공연_종료는_강조를_되돌린다`, `test_코스_밖_큐의_대사는_자막만_띄운다`)
3. **와이파이가 끊기거나 감독이 재시작한다** — 끊김을 화면에 보이고, 다시 붙으면 현재 상태로 맞춘다. (Task 4 `test_연결이_끊기면_표시하고_다시_붙으면_맞춘다`)
4. **턴이 1개뿐인 큐, 큐시트에 없는 라벨(단독 모드)** — 마지막 도슨트(`:docent`)가 `docent0` 로 읽히고, 모르는 라벨은 자막만 흐른다. (Task 1 `test_한_턴_큐는_…`, `test_큐시트에_없거나_규칙에_안_맞는_라벨은_None_이다`; Task 2 `test_모르는_라벨은_자막만_흐르고_큐_대목은_None_이다`)
5. **관람객 폰이 수십 대 붙는다 / 페이지가 무거워진다** — 감독은 느린 폰을 기다리지 않고, 4수준 19큐 한 페이지가 400KB 안이다(측정치: 말풍선 마크업 147KB + 자산). (Task 2 `test_여러_관람객_기기가_동시에_붙어도_모두_같은_대사를_받는다`; Task 3 `test_실제_큐시트_한_페이지는_400KB_안이다`)

## File Structure

| 파일 | 하는 일 | Task |
|---|---|---|
| `docs/design/handout-mock-2sheets.html` | 승인된 시안(참고용, 배포 안 함) | 1 |
| `stage/say_label.py` | 발화 라벨 → `{cue, turn}` (읽는 쪽) | 1 |
| `stage/dashboard.py` | `/ws/audience` `say` 에 `cue`·`turn`, 스냅샷에 `level`, `/handout` 인자, (7) 읽기 전용 모드 | 2·3·4·5·7 |
| `stage/handout.py` | 한 페이지·전 수준 렌더러(순수 함수) | 3·4·5·6 |
| `stage/handout.css` | 교육자료 스타일(자산) | 3·4·5·6 |
| `stage/handout_live.js` | 따라가기 핵심(소켓·장 선택·강조·자막 막대·따라가기 끊기) | 4 |
| `stage/handout_data.py` | `data/handout.yaml` 로더·검증 | 5 |
| `data/handout.yaml` | 검수한 카드(02·03)와 시각화·자동 동작 지정 | 5·6 |
| `stage/handout_viz.py` / `stage/handout_viz.js` | 시각화 부품(신호 보내기·주파수 다이얼) | 6 |
| `stage/__main__.py` | 카드 로드 배선, (7) 읽기 전용 리스너 | 5·7 |
| `tests/_cdp.py`, `tests/_handout_support.py` | 브라우저 테스트 도구·공용 가짜 감독 | 4 |
| `tests/test_say_label.py`, `tests/test_handout_data.py`, `tests/test_handout_live.py`, `tests/test_handout_browser.py` | 새 테스트 | 1·4·5·6 |
| `tests/test_audience.py` | 기존 교육자료·보조 소켓 테스트 갱신 | 2·3·7 |
| `docs/two-robot-offline-test.md`, `docs/lessons.md` | 운영 문서·교훈 | 8 |

---

### Task 1: 발화 라벨을 큐·턴으로 읽는다

**Files:**
- Create: `stage/say_label.py`
- Create: `tests/test_say_label.py`
- Add (참고용 시안 커밋): `docs/design/handout-mock-2sheets.html`

**Interfaces:**
- Consumes: 없음(라벨 문자열과 `points_of: Callable[[str], int | None]`).
- Produces: `SayRef(cue: str, turn: str)` NamedTuple, `QA_TURNS: frozenset[str]` = `{"ack","qa","reask"}`, `parse_say_label(label, points_of) -> SayRef | None`. `points_of(cue_id)` 는 그 큐의 포인트 수(턴 수)를 주고, 큐시트에 없으면 `None`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_say_label.py`:

```python
"""발화 라벨 해석 — 감독이 `say` 에 싣는 `cue_id`(발화 라벨)를 "어느 큐의 어느 대목"으로 푼다.

라벨을 **만드는 쪽**은 `stage/director.py` 다. 읽는 쪽(`stage/say_label.py`)이 어긋나면 교육자료가 엉뚱한
카드를 켠다 — 그래서 실제 감독을 큐시트 끝까지 돌려 받은 라벨을 읽어 본다(아래 마지막 세 테스트).
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet, Turn, load_cues
from stage.director import Director
from stage.levels import LEVEL_NAMES
from stage.say_label import QA_TURNS, SayRef, parse_say_label


def _n(count):
    """큐 `c` 만 있는 큐시트(포인트 `count` 개)."""
    return lambda cid: {"c": count}.get(cid)


def test_여는_말_라벨은_큐_id_그대로다():
    assert parse_say_label("c", _n(3)) == SayRef("c", "open")


def test_사회자_질문은_ask_번호다():
    assert parse_say_label("c:pt1", _n(3)) == SayRef("c", "ask1")
    assert parse_say_label("c:pt2", _n(3)) == SayRef("c", "ask2")


def test_첫_포인트에는_질문이_없어_pt0_는_모르는_라벨이다():
    """첫 턴에는 ask 를 두지 않는다(오프닝이 묻는다 — `stage/cues.py::_load_turns`)."""
    assert parse_say_label("c:pt0", _n(3)) is None


def test_마지막이_아닌_도슨트_설명은_docent_번호다():
    assert parse_say_label("c:pt0:docent", _n(3)) == SayRef("c", "docent0")
    assert parse_say_label("c:pt1:docent", _n(3)) == SayRef("c", "docent1")


@pytest.mark.parametrize("n", [1, 2, 3])
def test_마지막_도슨트는_항상_종단_라벨이고_마지막_번호가_된다(n):
    assert parse_say_label("c:docent", _n(n)) == SayRef("c", f"docent{n - 1}")


def test_마지막_설명이_pt_라벨로_오면_모르는_라벨이다():
    """감독은 마지막 설명에 늘 `:docent` 를 쓴다(`Director._point_label`) — 이 모양이 오면 규칙이 바뀐 것이다."""
    assert parse_say_label("c:pt2:docent", _n(3)) is None


def test_받아치기와_질문_흐름_라벨():
    assert parse_say_label("c:after", _n(3)) == SayRef("c", "after")
    for turn in sorted(QA_TURNS):
        assert parse_say_label(f"c:{turn}", _n(3)) == SayRef("c", turn)


@pytest.mark.parametrize(
    "label",
    ["solo:qa", "solo:ack", "", None, 7, "zzz:docent", "c:pt9", "c:docent:x", "c:pt1:docent:x", ":docent", "c:"],
)
def test_큐시트에_없거나_규칙에_안_맞는_라벨은_None_이다(label):
    assert parse_say_label(label, _n(3)) is None


def _구동(cues, level="일반"):
    """실제 감독을 큐시트 끝까지 돌려 `say` 의 발화 라벨을 모은다.

    로봇은 말이 끝났다고 곧장 보고하는 가짜이고, 질문 창이 열리면(LISTENING) 관람객이 "다음" 이라고 말한다.
    """
    sent = []
    d = Director(
        CueSheet(cues),
        generate=lambda role, brief, history: "생성 안 함",
        send=lambda role, cmd: sent.append((role, cmd.type, dict(cmd.fields))),
        warn=lambda m: None,
        level_name=level,
    )
    for role in ("mc", "docent"):
        d.on_hello(role, None, "test", ["emotion", "react", "gaze"])
        d.on_connect(role)
    d.start()
    labels, seen_seq = [], 0
    for _ in range(400):
        says = [(r, f) for r, t, f in sent if t == "say"]
        if not says:
            break
        role, f = says[-1]
        if f["seq"] != seen_seq:
            seen_seq = f["seq"]
            labels.append(f["cue_id"])
        d.on_speaking_ended(role, f["cue_id"], f["seq"])
        if d.state.value == "listening":
            before = sum(1 for _, t, _ in sent if t == "say")
            d.on_heard("다음")
            if sum(1 for _, t, _ in sent if t == "say") == before:
                break
    else:
        pytest.fail("감독이 400걸음 안에 끝나지 않았다 — 구동 도구가 무한히 돈다")
    return labels


def test_실제_큐시트의_모든_큐가_기대한_턴_순서로_읽힌다():
    """감독이 라벨 규칙을 바꾸면 여기서 실패한다 — 교육자료가 엉뚱한 카드를 켜기 전에."""
    cues = load_cues()
    points = {c.id: len(c.points) for c in cues}
    got = {}
    for label in _구동(cues):
        ref = parse_say_label(label, points.get)
        assert ref is not None, f"읽을 수 없는 라벨: {label!r}"
        got.setdefault(ref.cue, []).append(ref.turn)
    for c in cues:
        want = ["open"]
        for i, t in enumerate(c.points):
            if t.ask:
                want.append(f"ask{i}")
            want.append(f"docent{i}")
        want.append("after")
        assert got.get(c.id) == want, c.id


def test_한_턴_큐는_여는_말과_마지막_도슨트만_있다():
    answers = {lv: f"{lv} 설명" for lv in LEVEL_NAMES}
    cue = Cue("c1", "첫째", "사회자 대사", "지시", "partner", points=(Turn("", answers),))
    labels = _구동([cue])
    assert labels == ["c1", "c1:docent"]
    assert [parse_say_label(l, {"c1": 1}.get) for l in labels] == [SayRef("c1", "open"), SayRef("c1", "docent0")]


def test_두_턴_큐의_라벨_순서():
    answers = {lv: f"{lv} 설명" for lv in LEVEL_NAMES}
    cue = Cue(
        "c2", "둘째", "사회자 대사", "지시", "partner",
        mc_after="질문 있으세요? '다음'이라고 해 주세요.",
        points=(Turn("", answers), Turn("그럼요?", answers)),
    )
    labels = _구동([cue])
    assert labels == ["c2", "c2:pt0:docent", "c2:pt1", "c2:docent", "c2:after"]
    refs = [parse_say_label(l, {"c2": 2}.get) for l in labels]
    assert [r.turn for r in refs] == ["open", "docent0", "ask1", "docent1", "after"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_say_label.py -v`
Expected: 수집 단계에서 `ModuleNotFoundError: No module named 'stage.say_label'`.

- [ ] **Step 3: 최소 구현을 쓴다**

`stage/say_label.py`:

```python
"""감독이 로봇에게 보내는 `say` 의 발화 라벨(`cue_id` 필드)을 읽는다.

교육자료·보조 화면이 "지금 어느 큐의 어느 대목을 말하는가"를 알려면 이것이 필요하다. 라벨을 **만드는 쪽**은
`stage/director.py`(`_begin_cue`·`_say_answer`·`_point_label`·`on_speaking_ended`)이고 이 모듈은 **읽는 쪽**이다 —
둘이 어긋나지 않게 `tests/test_say_label.py` 가 실제 감독을 큐시트 끝까지 돌려 박제한다.

  <큐>                 사회자 여는 말                 → open
  <큐>:pt<i>           사회자 질문(i ≥ 1)             → ask<i>
  <큐>:pt<i>:docent    도슨트 설명(마지막이 아닌 것)   → docent<i>
  <큐>:docent          **마지막** 도슨트 설명          → docent<포인트 수 - 1>
  <큐>:after           사회자 받아치기                → after
  <큐>:ack|qa|reask    관람객 질문 흐름               → 같은 이름
  solo:ack|solo:qa     단독 모드(큐시트에 없는 이름)   → 읽지 않는다(None)

마지막 설명이 `:pt<n-1>:docent` 로 오면 규칙이 바뀐 것이라 **모르는 라벨(None)** 로 둔다 — 조용히 엉뚱한 대목으로
읽는 것보다 낫다. None 은 호출부가 "자막만 흘린다" 로 받는다.
"""

import re
from typing import Callable, NamedTuple

# 관람객 질문 흐름의 대목 — 큐의 해설 흐름(open → … → after)이 아니라 곁가지다.
QA_TURNS = frozenset({"ack", "qa", "reask"})

_ASK = re.compile(r"^pt(\d+)$")
_DOCENT = re.compile(r"^pt(\d+):docent$")


class SayRef(NamedTuple):
    cue: str    # 큐 id
    turn: str   # open | ask<i> | docent<i> | after | ack | qa | reask


def parse_say_label(label, points_of: Callable[[str], int | None]) -> SayRef | None:
    """발화 라벨을 `SayRef` 로 푼다. 큐시트에 없거나 규칙에 안 맞으면 None.

    `points_of(큐 id)` 는 그 큐의 포인트 수(없으면 None) — 마지막 도슨트가 `docent<n-1>` 로 풀리려면 n 이 필요하다.
    """
    if not isinstance(label, str) or not label:
        return None
    cue, sep, rest = label.partition(":")
    n = points_of(cue)
    if not n:
        return None
    if not sep:
        return SayRef(cue, "open")
    if rest == "after" or rest in QA_TURNS:
        return SayRef(cue, rest)
    if rest == "docent":
        return SayRef(cue, f"docent{n - 1}")
    m = _ASK.match(rest)
    if m and 0 < int(m.group(1)) < n:
        return SayRef(cue, f"ask{m.group(1)}")
    m = _DOCENT.match(rest)
    if m and int(m.group(1)) < n - 1:
        return SayRef(cue, f"docent{m.group(1)}")
    return None
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_say_label.py -v`
Expected: 전부 PASS (파라미터 테스트 포함 23건).

- [ ] **Step 5: 시안을 참고용으로 커밋하고 전체 구성을 확인한다**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
git add stage/say_label.py tests/test_say_label.py docs/design/handout-mock-2sheets.html
git commit -m "feat(stage): 발화 라벨을 큐·턴으로 읽는다 — 교육자료가 말하는 대목을 알게" \
  -m "감독의 say 라벨(02-history:pt1:docent 등)을 {cue, turn} 으로 푼다. 실제 Director 를 19큐 끝까지 돌려 라벨 순서를 박제하고, 1·2턴 큐와 큐시트에 없는 라벨(단독 모드)도 본다. 승인된 교육자료 시안(docs/design)을 참고용으로 함께 둔다." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Expected: 전체 pytest 통과(이번 작업 전 기준 1270건 + 새 테스트).

---

### Task 2: 관람객 소켓의 `say` 에 큐·턴을 싣고 스냅샷에 수준을 싣는다

**Files:**
- Modify: `stage/dashboard.py:36-60`(허용 목록·`audience_event`), `stage/dashboard.py:66-80`(`__init__`), `stage/dashboard.py:258`·`:317`(호출부)
- Modify: `tests/test_audience.py`(기존 두 기대값 갱신 + 새 테스트)

**Interfaces:**
- Consumes: `stage.say_label.parse_say_label` (Task 1).
- Produces: `/ws/audience` 의 `say` 메시지 = `{"kind":"say","role":…,"text":…,"cue_id":<라벨>,"cue":<큐 id|null>,"turn":<턴|null>}`; 스냅샷 허용 칸에 `"level"`(관람객 수준 이름) 추가. `audience_event(ev, points_of=None)`, `DashboardServer._points_of(cue_id) -> int | None`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_audience.py` 의 기존 두 기대값을 고친다.

`test_보조_소켓_hello_에는_이력_경고가_없고_허용_칸만_있다` 안의

```python
    assert hello["say"] == {"kind": "say", "role": "mc", "text": "마지막 대사", "cue_id": "01-intro"}
```
를 아래로 바꾼다.
```python
    assert hello["say"] == {"kind": "say", "role": "mc", "text": "마지막 대사", "cue_id": "01-intro",
                            "cue": "01-intro", "turn": "open"}
```

`test_보조_소켓은_대사만_흘리고_경고와_마이크는_흘리지_않는다` 안의

```python
        assert got == {"kind": "say", "role": "docent", "text": "도슨트 대사", "cue_id": "01-intro:docent"}
```
를 아래로 바꾼다(`_시트()` 의 `01-intro` 는 포인트 2개라 마지막 도슨트는 `docent1`).
```python
        assert got == {"kind": "say", "role": "docent", "text": "도슨트 대사", "cue_id": "01-intro:docent",
                       "cue": "01-intro", "turn": "docent1"}
```

그리고 파일의 "서버: 보조 화면·교육자료 경로" 절 끝(`test_보조_화면은_코스_안_위치로_번호를_그린다` 뒤)에 새 테스트를 붙인다.

```python
# ── 서버: 따라가기용 큐·턴 필드 ───────────────────────────────────────


def test_보조_소켓의_say_에_큐와_턴이_실린다(aud):
    with connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", open_timeout=3) as ws:
        json.loads(ws.recv(timeout=3))                                               # hello
        for seq, (label, want) in enumerate([
            ("01-intro", ("01-intro", "open")),
            ("01-intro:pt1", ("01-intro", "ask1")),
            ("01-intro:pt0:docent", ("01-intro", "docent0")),
            ("01-intro:docent", ("01-intro", "docent1")),                           # 마지막 도슨트 = 포인트 수 - 1
            ("01-intro:after", ("01-intro", "after")),
            ("01-intro:qa", ("01-intro", "qa")),
            ("02-x:docent", ("02-x", "docent0")),                                   # 포인트 1개 큐
        ], start=1):
            aud["hub"].publish("sent", role="docent", type="say", fields={"cue_id": label, "seq": seq, "text": label})
            got = _recv_until(ws, lambda m: m["kind"] == "say")
            assert (got["cue"], got["turn"]) == want, label


def test_모르는_라벨은_자막만_흐르고_큐_대목은_None_이다(aud):
    """단독 모드(`solo:qa`)나 규칙에 안 맞는 라벨 — 자막(text)은 그대로 흐르고 교육자료는 장을 바꾸지 않는다."""
    with connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", open_timeout=3) as ws:
        json.loads(ws.recv(timeout=3))
        aud["hub"].publish("sent", role="mc", type="say", fields={"cue_id": "solo:qa", "seq": 1, "text": "단독 답"})
        got = _recv_until(ws, lambda m: m["kind"] == "say")
    assert got == {"kind": "say", "role": "mc", "text": "단독 답", "cue_id": "solo:qa", "cue": None, "turn": None}


def test_스냅샷에_관람객_수준이_실린다(aud):
    with connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", open_timeout=3) as ws:
        hello = json.loads(ws.recv(timeout=3))
        snap = _recv_until(ws, lambda m: m["kind"] == "snapshot")
    assert hello["snapshot"]["level"] == "초등" and snap["level"] == "초등"      # 가짜감독의 스냅샷 level


def test_감독이_큐시트를_못_주면_경고하고_자막은_계속_흐른다(tmp_path):
    """연결이 여럿이어도 경고는 **한 번**이다 — 연결마다 송신 스레드가 있어 같은 순간에 `_points_of` 를 부른다."""
    class 큐시트못주는감독(가짜감독):
        def cues(self):
            time.sleep(0.2)                                      # 여러 스레드가 겹치게 느리게 실패한다
            raise RuntimeError("큐시트 없음")

    page = tmp_path / "p.html"
    page.write_text("x", encoding="utf-8")
    hub, warned = DashboardHub(), []
    ds = DashboardServer(hub, 큐시트못주는감독(), page=page, interval=0.05, warn=warned.append)
    with _served(ds) as port:
        socks = [connect(f"ws://127.0.0.1:{port}/ws/audience", open_timeout=3) for _ in range(6)]
        try:
            for ws in socks:
                json.loads(ws.recv(timeout=3))
            hub.publish("sent", role="mc", type="say", fields={"cue_id": "01-intro", "seq": 1, "text": "그래도 자막"})
            for ws in socks:
                got = _recv_until(ws, lambda m: m["kind"] == "say")
                assert got["text"] == "그래도 자막" and got["cue"] is None and got["turn"] is None
        finally:
            for ws in socks:
                ws.close()
    assert sum("큐시트" in w for w in warned) == 1, warned                            # 한 번만 알린다


def test_여러_관람객_기기가_동시에_붙어도_모두_같은_대사를_받는다(aud):
    """감독은 느린 폰을 기다리지 않는다 — 허브는 쌓기만 하고 연결마다 송신 스레드가 따로다."""
    socks = [connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", open_timeout=3) for _ in range(20)]
    try:
        for ws in socks:
            json.loads(ws.recv(timeout=3))                                           # hello
        t0 = time.monotonic()
        aud["hub"].publish("sent", role="mc", type="say", fields={"cue_id": "01-intro", "seq": 1, "text": "다 같이"})
        assert time.monotonic() - t0 < 0.5
        for ws in socks:
            got = _recv_until(ws, lambda m: m["kind"] == "say")
            assert got["text"] == "다 같이" and got["turn"] == "open"
    finally:
        for ws in socks:
            ws.close()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_audience.py -v -k "보조_소켓 or 스냅샷에_관람객 or 큐시트를_못 or 여러_관람객"`
Expected: 갱신한 두 테스트와 새 테스트가 `KeyError: 'cue'`·dict 불일치로 FAIL.

- [ ] **Step 3: 구현한다**

`stage/dashboard.py` 의 import 블록에 추가(다른 `from stage…` 줄 옆):

```python
from stage.say_label import parse_say_label
```

`AUDIENCE_SNAPSHOT_KEYS` 와 `audience_event` 를 아래로 바꾼다.

```python
AUDIENCE_SNAPSHOT_KEYS = (
    "cue_index", "cue_id", "cue_count", "state", "speaking_role",
    "question_wait_s", "question_wait_total_s", "mode", "show_running", "course_position",
    # 관람객 수준 이름 — 교육자료가 감독의 수준을 따라간다(2026-10-01). 수준은 관람객 화면에 내보내도 되는 값이다.
    "level",
)


def audience_event(ev: dict, points_of: Callable[[str], int | None] | None = None) -> dict | None:
    """허브 이벤트 → 보조 화면 이벤트. **로봇에게 실제로 보낸 대사(`sent`/`say`)만** 넘긴다 — 나머지는 None.

    `cue`·`turn` 은 발화 라벨(`cue_id`)을 푼 것이다(`stage/say_label.py`) — 교육자료가 지금 말하는 대목을
    따라가는 데 쓴다. 풀 수 없으면(`points_of` 가 없거나 큐시트에 없는 라벨, 단독 모드) 둘 다 None 이고
    자막(`text`)은 그대로 흐른다.
    """
    if ev.get("kind") != "sent" or ev.get("type") != "say":
        return None
    fields = ev.get("fields") or {}
    label = str(fields.get("cue_id", ""))
    ref = parse_say_label(label, points_of) if points_of is not None else None
    return {"kind": "say", "role": ev.get("role"), "text": str(fields.get("text", "")), "cue_id": label,
            "cue": ref.cue if ref else None, "turn": ref.turn if ref else None}
```

`DashboardServer.__init__` 끝(`self._warn = warn` 다음 줄)에 추가:

```python
        # 큐 id → 포인트 수. 라벨을 풀 때 처음 한 번 감독에게 묻는다(큐시트는 기동 뒤 안 바뀐다).
        self._points: dict[str, int] | None = None
        # 연결마다 송신 스레드가 있어 같은 순간에 `_points_of` 를 부른다 — 잠그지 않으면 실패 경고가 연결 수만큼 난다.
        self._points_lock = threading.Lock()
```

`DashboardServer` 에 메서드를 추가한다(`_safe_snapshot` 바로 위가 좋다).

```python
    def _points_of(self, cue_id: str) -> int | None:
        """그 큐의 포인트 수 — 발화 라벨의 마지막 도슨트(`:docent`)를 몇 번째로 읽을지 정한다.

        감독이 큐시트를 못 주면 **한 번만 알리고** 라벨을 못 읽을 뿐 자막은 계속 흐른다(교육자료·보조 화면이
        죽을 이유가 아니다).
        """
        with self._points_lock:
            if self._points is None:
                try:
                    self._points = {c.id: len(c.points) for c in self._director.cues()}
                except Exception as exc:  # noqa: BLE001
                    self._warn(
                        f"라벨을 읽으려 감독에게 큐시트를 물었으나 실패했다({type(exc).__name__}: {exc}) — "
                        "자막은 그대로 흐르고 큐·대목 정보만 빠진다"
                    )
                    self._points = {}
            points = self._points
        return points.get(cue_id)
```

호출부 두 곳의 `audience_event(ev)` 에 `self._points_of` 를 더한다. `_audience()` 안(hello 에 싣는 마지막 대사)은 `last_say = audience_event(ev)` 를 아래로, `_pump()` 안은 `ev = audience_event(ev)` 를 아래로 바꾼다.

```python
                last_say = audience_event(ev, self._points_of)
```
```python
                ev = audience_event(ev, self._points_of)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_audience.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋한다**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
git add stage/dashboard.py tests/test_audience.py
git commit -m "feat(stage): 관람객 소켓의 say 에 큐·턴을, 스냅샷에 수준을 싣는다" \
  -m "발화 라벨을 풀어 cue·turn 을 허용 칸으로 내보낸다(모르는 라벨·큐시트 실패는 None 이고 자막은 그대로). 감독이 큐시트를 못 주면 한 번만 경고. 스냅샷 허용 목록에 level 추가. 폰 20대 동시 접속에서 감독이 기다리지 않음을 박제." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 교육자료를 한 페이지·전 수준으로 재구성한다 (정적)

**Files:**
- Rewrite: `stage/handout.py`
- Create: `stage/handout.css`
- Modify: `stage/dashboard.py:114-145`(`_serve_handout`)
- Modify: `tests/test_audience.py`(교육자료 테스트 갱신)

**Interfaces:**
- Consumes: `stage.cues.Cue`(`.points_for(level)`, `.mc`, `.mc_emotion`, `.id`, `.title`, `.points`).
- Produces: `render_handout(cues, level, levels, title="전파체험관 해설", course=None, *, cards=None, live=False, level_locked=False) -> str`. 페이지 구조(이후 Task 가 기대한다):
  - `<body data-level-locked="1"?, data-live="1"?>` 아래 `<input type=radio id="lvr<i>" data-name="<수준 이름>">`(수준마다 하나, 지금 수준이 `checked`) → `<div class="top">`(수준 탭 `label[for=lvr<i>]`) → `<main>`.
  - 큐마다 `<section class="sheet" id="<큐 id>" data-points="<포인트 수>">` 안에 수준마다 `<div class="chat lv L<i>">`, 그 안에 말풍선 `<div class="row mc|docent" data-t="<턴>">`(턴: `open`·`ask<i>`·`docent<i>`).
  - 수준별 묶음은 클래스 `lv L<i>`(i = `levels` 안의 위치)이고 CSS 가 선택된 수준만 보인다.
- `cards`·`live` 인자는 이 Task 에서 받기만 하고 쓰지 않는다(Task 4·5 가 채운다) — 기본값이라 기존 호출부가 그대로 돈다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_audience.py` 상단 import 에 `import re` 를 추가한다. 그리고 기존 교육자료 테스트를 아래처럼 정리한다.

**삭제:** `test_교육자료는_그_수준의_대화를_그대로_옮긴다`, `test_교육자료는_수준을_바꾸는_링크와_지금_수준_표시가_있다`, 서버 쪽 `test_교육자료는_수준을_주면_그_수준으로_안_주면_감독의_지금_수준으로`, `test_교육자료는_코스의_큐만_싣고_수준_링크가_코스를_유지한다` (모두 "수준별 링크·한 수준만" 을 전제로 했다 — 한 페이지 전 수준으로 바뀌어 전제가 사라졌다).

**유지:** `test_교육자료에는_내부_지시문과_저작_메모와_진행_안내가_없다`, `test_교육자료는_모든_글자를_이스케이프한다`, `test_모르는_수준의_교육자료는_만들지_않는다`, `test_모르는_수준의_교육자료는_400으로_거절한다`, `test_모르는_코스의_교육자료는_400으로_거절한다`.

**교체·추가:** `test_실제_큐시트로_네_수준_교육자료가_만들어진다` 바로 아래에 붙인다.

```python
def test_교육자료는_모든_수준의_대화를_수준별_묶음으로_싣는다():
    page = render_handout(_시트(), "초등", _수준들)
    chunks = page.split('<div class="chat lv L')[1:]            # 큐 × 수준 순서
    assert len(chunks) == len(_시트()) * len(_수준들)
    assert chunks[0].startswith('0">') and "초등 첫 설명이에요." in chunks[0] and "일반 첫 설명이에요." not in chunks[0]
    assert chunks[1].startswith('1">') and "일반 첫 설명이에요." in chunks[1] and "초등 첫 설명이에요." not in chunks[1]
    for want in ("안녕하세요! 도슨트, 소개해 줄래요?", "그럼 누가 만들었어요?", "체험관 개요"):
        assert want in page, want


def test_말풍선은_턴_표지를_달고_있다():
    """따라가기가 "지금 말하는 말풍선" 을 찾는 표지다 — 여는 말·질문·설명이 `open`·`ask<i>`·`docent<i>`."""
    page = render_handout(_시트(), "일반", _수준들)
    first = page.split('<div class="chat lv L')[1]
    assert re.findall(r'data-t="([^"]+)"', first.split("</section>")[0]) == ["open", "docent0", "ask1", "docent1"]


def test_교육자료에는_수준_탭과_지금_수준의_라디오가_있다():
    page = render_handout(_시트(), "일반", _수준들)
    assert '<label for="lvr0">초등</label>' in page and '<label for="lvr1">일반</label>' in page
    assert 'data-name="일반" aria-label="일반" checked' in page
    assert 'data-name="초등" aria-label="초등" checked' not in page


def test_수준이_주소에_적혔으면_감독을_따라가지_않는_표지가_붙는다():
    assert 'data-level-locked="1"' in render_handout(_시트(), "일반", _수준들, level_locked=True)
    assert 'data-level-locked="1"' not in render_handout(_시트(), "일반", _수준들)


def test_큐마다_포인트_수를_장에_싣는다():
    page = render_handout(_시트(), "일반", _수준들)
    assert 'id="01-intro" data-points="2"' in page and 'id="02-x" data-points="1"' in page


def test_교육자료_머리는_파비콘_요청을_없앤다():
    assert '<link rel="icon" href="data:,">' in render_handout(_시트(), "일반", _수준들)


def test_교육자료는_코스를_머리에_적는다():
    page = render_handout(_시트(), "일반", _수준들, course="하이라이트")
    assert "코스: <strong>하이라이트</strong>" in page


def test_실제_큐시트_한_페이지는_400KB_안이다():
    """19큐 × 4수준을 한 페이지에 싣는다 — 폰 수십 대가 받아 간다. 측정치: 말풍선 마크업 147KB + 자산."""
    from stage.cues import load_cues
    from stage.levels import load_levels

    cues = tuple(load_cues())
    levels = list(load_levels())
    page = render_handout(cues, levels[0], levels, live=True)
    assert len(page.encode("utf-8")) < 400_000
```

그리고 서버 테스트(`test_모르는_코스의_교육자료는_400으로_거절한다` 위)에 아래를 붙인다.

```python
def test_교육자료는_수준을_주면_잠그고_안_주면_감독의_지금_수준으로_연다(aud):
    _, ctype, body = _get(aud["port"], "/handout?level=%EC%9D%BC%EB%B0%98")          # 일반
    assert ctype.startswith("text/html")
    assert 'data-name="일반" aria-label="일반" checked' in body and 'data-level-locked="1"' in body
    _, _, body = _get(aud["port"], "/handout")
    assert 'data-name="초등" aria-label="초등" checked' in body                        # 스냅샷의 level
    assert 'data-level-locked="1"' not in body                          # 따옴표까지 — Task 4 의 스크립트가 이름만 담고 있다


def test_교육자료는_코스의_큐만_싣고_머리에_코스를_적는다(aud):
    """"오늘 들은 이야기" 다 — 하이라이트면 하이라이트 큐만."""
    _, _, body = _get(aud["port"], "/handout?level=%EC%B4%88%EB%93%B1&course=%EC%B2%AB%ED%81%90%EB%A7%8C")
    assert body.count("<section ") == 1 and "체험관 개요" in body
    assert "코스: <strong>첫큐만</strong>" in body
    _, _, body = _get(aud["port"], "/handout?level=%EC%B4%88%EB%93%B1")
    assert body.count("<section ") == 2                                               # 스냅샷의 코스(전체)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_audience.py -v -k "교육자료 or 큐마다 or 말풍선 or 수준_탭 or 400KB or 수준이_주소에"`
Expected: 새 테스트가 `chat lv L` 부재·`level_locked` 인자 부재(`TypeError`)로 FAIL.

- [ ] **Step 3: 구현한다**

`stage/handout.py` 를 통째로 아래로 바꾼다.

```python
"""수준별 교육자료 — 오늘 들은 해설을 읽기 자료로 옮긴다(2026-09-25). 공연을 따라가는 한 페이지로 확장(2026-10-01).

**큐시트의 고정 대본만 쓴다.** 해설은 조사 파일로 사실을 검증한 대본이고(교훈 대장 「정해진 해설을 공연 때마다
생성하면…」), 여기서 LLM 으로 요약하면 검증된 문장이 매번 새로 쓰인다 — 교육자료에 환각이 섞이는 것이 가장
나쁘다. 그래서 대화를 **그대로** 옮긴다: 사회자의 여는 말·턴 질문, 도슨트의 설명.

싣지 않는 것과 이유:
- 브리프·금지 규칙(`briefs`·`guard`) — 모델에게 주는 내부 지시문이다("인명·연도는 말하지 않는다" 등).
- 한 줄 주제(`topic`) — 일부가 저작 메모다("해설 종료 인사와 되짚기 — 새 정보 없이 닫는다").
- 받아치기(`mc_after`) — "질문 있으세요? '다음'이라고 말해 주세요" 같은 진행 안내라 읽기 자료에 맞지 않는다.

**한 페이지에 모든 수준을 싣는다**(`lv L<번호>` 묶음 + CSS 라디오 탭). 공연 중 감독 수준이 바뀌어도 새로고침 없이
따라가야 해서다(`stage/handout_live.js`). 같은 큐의 대화를 수준마다 따로 싣고, 보이는 것은 고른 수준뿐이다.

순수 함수다(네트워크 없음). 자산(CSS·JS)은 **호출 때** 읽는다 — 파일이 없으면 OSError 가
`DashboardServer._serve_handout` 의 500 + 경고로 드러난다(교육자료가 깨져도 감독은 산다). 모든 텍스트는
`html.escape` 를 거친다 — 대본은 사람이 쓰지만 이 페이지는 관람객 기기에서 열릴 수 있다.
"""

import html
import pathlib

from stage.cues import Cue

_DIR = pathlib.Path(__file__).parent

# 감정 → 얼굴. `설명` 은 대본의 기본값("특별한 감정 없음")이라 중립 얼굴이다.
_FACE = {
    "happy": {"뿌듯", "기쁨", "신남", "반가움", "감탄", "감사", "안도", "안심"},
    "surprised": {"놀람"},
    "curious": {"궁금", "골똘"},
}

_FACES_SVG = """<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <symbol id="face-neutral" viewBox="0 0 48 48"><g fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
    <path d="M17 12 L14 5 M31 12 L34 5"/><rect x="6" y="12" width="36" height="28" rx="12"/></g>
    <circle cx="14" cy="4.5" r="2.4" fill="currentColor"/><circle cx="34" cy="4.5" r="2.4" fill="currentColor"/>
    <circle cx="18" cy="26" r="3" fill="currentColor"/><circle cx="30" cy="26" r="3" fill="currentColor"/></symbol>
  <symbol id="face-happy" viewBox="0 0 48 48"><g fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
    <path d="M17 12 L14 5 M31 12 L34 5"/><rect x="6" y="12" width="36" height="28" rx="12"/>
    <path d="M13.5 28 q4.5 -7 9 0 M25.5 28 q4.5 -7 9 0"/></g>
    <circle cx="14" cy="4.5" r="2.4" fill="currentColor"/><circle cx="34" cy="4.5" r="2.4" fill="currentColor"/></symbol>
  <symbol id="face-surprised" viewBox="0 0 48 48"><g fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
    <path d="M17 12 L14 3 M31 12 L34 3"/><rect x="6" y="12" width="36" height="28" rx="12"/>
    <circle cx="18" cy="26" r="4.4"/><circle cx="30" cy="26" r="4.4"/></g>
    <circle cx="14" cy="2.5" r="2.4" fill="currentColor"/><circle cx="34" cy="2.5" r="2.4" fill="currentColor"/></symbol>
  <symbol id="face-curious" viewBox="0 0 48 48"><g fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
    <path d="M17 12 L14 5 M31 12 L37 7"/><rect x="6" y="12" width="36" height="28" rx="12"/>
    <circle cx="30" cy="26" r="4.4"/></g>
    <circle cx="14" cy="4.5" r="2.4" fill="currentColor"/><circle cx="37.5" cy="6.5" r="2.4" fill="currentColor"/>
    <circle cx="18" cy="26" r="3" fill="currentColor"/></symbol>
</defs></svg>"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _asset(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")


def _face_kind(emotion: str | None) -> str:
    for kind, names in _FACE.items():
        if emotion in names:
            return kind
    return "neutral"


def _bubble(role: str, text: str, emotion: str | None, turn: str) -> str:
    who = "사회자" if role == "mc" else "도슨트"
    emo = f'<span class="emo">{_esc(emotion)}</span>' if emotion else ""
    return (
        f'<div class="row {role}" data-t="{turn}"><div class="av {role}">'
        f'<svg viewBox="0 0 48 48" aria-hidden="true"><use href="#face-{_face_kind(emotion)}"/></svg>'
        f'<span class="who">{who}</span>{emo}</div><p class="bub">{_esc(text)}</p></div>'
    )


def _chat_rows(cue: Cue, level: str) -> str:
    """사회자의 여는 말 → (질문 → 설명) 턴들. 턴 표지는 감독의 발화 라벨과 같은 이름이다(`stage/say_label.py`)."""
    rows = [_bubble("mc", cue.mc, cue.mc_emotion, "open")]
    for i, p in enumerate(cue.points_for(level)):
        if p.ask:
            rows.append(_bubble("mc", p.ask, p.ask_emotion, f"ask{i}"))
        rows.append(_bubble("docent", p.answer, p.answer_emotion, f"docent{i}"))
    return "".join(rows)


def _level_css(n: int) -> str:
    """고른 수준만 보이게 하는 규칙 — 수준 수에 따라 달라져 생성한다(`levels.yaml` 이 수준 목록의 정본이다)."""
    vis = ",".join(f"#lvr{i}:checked~main .lv.L{i}" for i in range(n))
    tab = ",".join(f"#lvr{i}:checked~.top label[for=lvr{i}]" for i in range(n))
    foc = ",".join(f"#lvr{i}:focus-visible~.top label[for=lvr{i}]" for i in range(n))
    return (
        f"{vis}{{display:var(--d,block)}}\n"
        f"{tab}{{background:#fff;color:var(--ink);font-weight:700}}\n"
        f"{foc}{{outline:3px solid #7FD3F5;outline-offset:-3px}}\n"
    )


def _section(number: int, cue: Cue, levels: list[str]) -> str:
    chats = "".join(
        f'<div class="chat lv L{k}">{_chat_rows(cue, lv)}</div>' for k, lv in enumerate(levels)
    )
    return (
        f'<section class="sheet" id="{_esc(cue.id)}" data-points="{len(cue.points)}">'
        f'<header class="sheet-h"><span class="no">{number:02d}</span><h2>{_esc(cue.title)}</h2>'
        '<span class="livebadge">● 지금 이야기 중</span></header>'
        f'<div class="ruler" aria-hidden="true"></div>'
        f'<div class="talk plain">{chats}</div></section>'
    )


def render_handout(cues: tuple[Cue, ...] | list[Cue], level: str, levels: list[str],
                   title: str = "전파체험관 해설", course: str | None = None, *,
                   cards=None, live: bool = False, level_locked: bool = False) -> str:
    """교육자료 한 장(HTML). `level` 은 `levels` 안에 있어야 한다 — 없으면 ValueError(부른 쪽이 가른다).

    `cues` 는 부른 쪽이 코스로 거른 것이다(오늘 들은 이야기). `course` 를 주면 머리에 코스를 적는다.
    `level_locked` 는 관람객이 수준을 직접 골랐다는 표지다(주소의 `?level=`) — 공연을 따라가는 스크립트가 감독의
    수준을 따라가지 않는다. `cards`(Task 5)·`live`(Task 4)는 아직 쓰지 않는다.
    """
    if level not in levels:
        raise ValueError(f"모르는 관람객 수준이다: {level!r} (고를 수 있는 것: {', '.join(levels)})")
    radios = "".join(
        f'<input class="vh" type="radio" name="lv" id="lvr{i}" data-name="{_esc(lv)}" aria-label="{_esc(lv)}"'
        f'{" checked" if lv == level else ""}>'
        for i, lv in enumerate(levels)
    )
    tabs = "".join(f'<label for="lvr{i}">{_esc(lv)}</label>' for i, lv in enumerate(levels))
    sections = "".join(_section(n, cue, levels) for n, cue in enumerate(cues, start=1))
    course_html = f" · 코스: <strong>{_esc(course)}</strong>" if course else ""
    body_attrs = (' data-level-locked="1"' if level_locked else "") + (' data-live="1"' if live else "")
    return (
        "<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        # 파비콘 요청을 없앤다 — 서버가 `/favicon.ico` 에 404 를 주는 것이 관람객 폰 로그와 브라우저 콘솔에 오류로 남는다.
        '<link rel="icon" href="data:,">'
        f"<title>{_esc(title)} — 교육자료</title>"
        f"<style>{_asset('handout.css')}{_level_css(len(levels))}</style></head>"
        f"<body{body_attrs}>{_FACES_SVG}{radios}"
        '<div class="top"><p>관람객 수준</p>'
        f'<nav class="levels" aria-label="관람객 수준">{tabs}</nav>'
        '<button type="button" onclick="window.print()">인쇄하기</button></div>'
        f'<main><header class="doc-h"><h1>{_esc(title)} — 오늘 들은 이야기</h1>'
        f"<p>사회자와 도슨트 로봇이 나눈 해설을 그대로 옮겼습니다{course_html}</p></header>"
        f"{sections}"
        '<p class="foot">이 자료는 체험관 해설 대본(사실 확인을 거친 고정 대본)에서 옮겼습니다. '
        "관람 중 나눈 질문과 답은 담기지 않습니다.</p></main></body></html>\n"
    )
```

`stage/handout.css` 를 만든다(이후 Task 가 아래에 이어 붙인다).

```css
:root{--ink:#0E2433;--sig:#0B7FB5;--mist:#E8F3F8;--rule:#C3D9E6;--paper:#fff;--bg:#E6EDF2;
  --mc:#0A6F84;--mcbg:#DDF1F5;--doc:#8F5300;--docbg:#FFEFD6;--amber:#B96F00;--muted:#52636F}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);word-break:keep-all;overflow-wrap:anywhere;line-height:1.7;
  font-family:-apple-system,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif}
.vh{position:absolute;opacity:0;pointer-events:none}
.top{position:sticky;top:0;z-index:5;background:var(--ink);color:#fff;padding:10px 16px;display:flex;flex-wrap:wrap;
  gap:10px 18px;align-items:center;justify-content:center}
.top p{margin:0;font-size:14px;opacity:.9}
.levels{display:flex;border:1px solid rgba(255,255,255,.45);border-radius:999px;overflow:hidden}
.levels label{padding:6px 16px;font-size:15px;cursor:pointer;user-select:none}
.levels label+label{border-left:1px solid rgba(255,255,255,.3)}
.top button{font:inherit;font-size:14px;padding:6px 14px;border-radius:6px;border:1px solid #fff;background:transparent;color:#fff;cursor:pointer}
main .lv{display:none}
main{max-width:780px;margin:0 auto;padding:22px 14px 60px}
.doc-h{margin:0 0 16px}
.doc-h h1{font-size:22px;margin:0 0 4px}
.doc-h p{margin:0;font-size:13px;color:var(--muted)}
.sheet{background:var(--paper);border:1px solid var(--rule);padding:26px 30px 28px;margin:0 0 26px}
.sheet-h{display:flex;align-items:baseline;gap:14px}
.no{font-size:15px;font-weight:700;color:var(--sig);font-variant-numeric:tabular-nums}
h2{font-size:17px;margin:0;font-weight:700;color:var(--muted)}
.ruler{height:14px;margin:8px 0 14px;opacity:.5;
  background:repeating-linear-gradient(90deg,var(--ink) 0 1px,transparent 1px 9px) left bottom/100% 7px no-repeat,
             repeating-linear-gradient(90deg,var(--ink) 0 2px,transparent 2px 45px) left bottom/100% 14px no-repeat}
.talk{margin-top:18px}
.talk.plain{margin-top:6px}
.chat{margin-top:14px}
.row{display:flex;gap:10px;align-items:flex-start;margin:0 0 12px}
.row.docent{flex-direction:row-reverse}
.av{flex:0 0 58px;text-align:center;line-height:1.25}
.av svg{width:44px;height:44px;display:block;margin:0 auto 2px}
.av .who{display:block;font-size:12px;font-weight:700}
.av .emo{display:block;font-size:12px;color:var(--muted)}
.av.mc svg{color:var(--mc)} .av.docent svg{color:var(--amber)}
.bub{margin:0;padding:10px 14px;font-size:15px;max-width:min(560px,calc(100% - 70px));border-radius:14px}
.row.mc .bub{background:var(--mcbg);border-top-left-radius:3px}
.row.docent .bub{background:var(--docbg);border-top-right-radius:3px;margin-left:auto}
.foot{font-size:13px;color:var(--muted);margin:6px 2px 0}
@media (max-width:640px){.sheet{padding:20px 16px}}
@media print{
  @page{size:A4;margin:14mm}
  body{background:#fff}
  .top,.foot{display:none}
  main{padding:0;max-width:none}
  .sheet{border:none;padding:0;margin:0;break-after:page;page-break-after:always}
  .sheet:last-of-type{break-after:auto;page-break-after:auto}
}
```

`stage/dashboard.py` 의 `_serve_handout` 을 고친다 — `course = …` 줄과 `if not asked or not course:` 줄 **사이**에 아래 두 줄(주석 한 줄·대입 한 줄)을 넣는다. 그 뒤에 `asked` 가 감독 수준으로 덮어써지므로 잠금 판정은 반드시 그 전에 해야 한다. 그리고 `render_handout` 호출에 인자를 더한다.

```python
        asked = (q.get("level") or [""])[0].strip()
        course = (q.get("course") or [""])[0].strip()
        # 주소에 수준을 적었다 = 관람객이 고른 것 — 공연을 따라가는 페이지가 감독의 수준을 따라가지 않는다.
        level_locked = bool(asked)
```
```python
            body = render_handout(cues, asked, levels, course=course if len(courses) > 1 else None,
                                  level_locked=level_locked)
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_audience.py -v`
Expected: 전부 PASS (삭제한 테스트는 더 이상 없고 새 테스트가 통과).

- [ ] **Step 5: 눈으로 확인하고 커밋한다**

```bash
.venv/bin/python - <<'EOF'
import pathlib, sys
sys.path.insert(0, ".")
from stage.cues import load_cues
from stage.levels import load_levels
from stage.handout import render_handout
levels = list(load_levels())
pathlib.Path("/tmp/handout-check.html").write_text(render_handout(tuple(load_cues()), "일반", levels), encoding="utf-8")
EOF
open /tmp/handout-check.html   # 수준 탭을 눌러 본다 — 말풍선이 수준마다 바뀌고 인쇄 미리보기가 큐마다 쪽을 나눈다
.venv/bin/python -m pytest -q -p no:cacheprovider
git add stage/handout.py stage/handout.css stage/dashboard.py tests/test_audience.py
git commit -m "feat(stage): 교육자료를 한 페이지·전 수준으로 — 수준 탭, 말풍선, 턴 표지" \
  -m "공연 중 감독 수준이 바뀌어도 새로고침 없이 따라가려면 모든 수준이 한 페이지에 있어야 한다. 수준마다 lv L<i> 묶음과 CSS 라디오 탭, 말풍선마다 data-t 턴 표지(감독의 발화 라벨과 같은 이름). 주소의 ?level= 은 관람객이 고른 것이라 잠금 표지. 자산(CSS)은 호출 때 읽어 파일 부재가 감독을 죽이지 않게 했다. 19큐×4수준 한 페이지 400KB 상한 테스트." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
(`/tmp/handout-check.html` 은 눈 확인용 임시 파일이다 — 저장소 밖이라 커밋되지 않는다.)

---

### Task 4: 공연 따라가기 — 소켓·장 자동 선택·말풍선 강조·자막 막대

**Files:**
- Create: `stage/handout_live.js`, `tests/_cdp.py`, `tests/_handout_support.py`, `tests/test_handout_live.py`, `tests/test_handout_browser.py`
- Modify: `stage/handout.py`(`_DOCK` 상수·`live` 처리), `stage/handout.css`(끝에 이어 붙임), `stage/dashboard.py`(`render_handout(…, live=True)`)

**Interfaces:**
- Consumes: Task 2 의 `/ws/audience` 메시지(`hello{cues,say,snapshot}`·`say{role,text,cue_id,cue,turn}`·`snapshot{…,level,show_running,mode,cue_id}`), Task 3 의 페이지 구조(`.sheet#<큐>`, `.chat`, `.row[data-t]`, `input[name=lv][data-name]`, `.levels label`, `body[data-level-locked|data-live]`).
- Produces: `window.handout = { onSay(m), onSnapshot(s), register(이름, fn(장, 어림ms)), onReset(fn(장|null)), onLevel(fn(수준 이름)), level(), reduceMotion, estMs(text), _socket() }` — Task 6 의 `stage/handout_viz.js` 가 `register`·`onReset`·`onLevel`·`level`·`reduceMotion` 을 쓴다. 강조 규칙: 장에 `.live`, 카드·말풍선(`[data-turns]`·`.row[data-t]`)에 `.now`(지금)·`.seen`(이미 지나감).
- 테스트 도구: `tests/_cdp.py` 의 `find_chrome()`·`Chrome(exe)`(`.call/.js/.goto/.wait_for/.errors/.close`), `tests/_handout_support.py` 의 `served(**dashboard_kwargs)` 컨텍스트 매니저(`Session`: `.port .hub .director .warned .url(path) .say(label, text, role) .set(**snap)`).

- [ ] **Step 1: 테스트 도구를 만든다**

`tests/_cdp.py`:

```python
"""헤드리스 크롬을 DevTools 프로토콜로 몬다 — 브라우저 테스트용 최소 도구(`websockets` sync 클라이언트만 쓴다).

크롬이 없으면 `find_chrome()` 이 None 이다 — 브라우저 테스트는 그때 건너뛴다. `REACHY_CHROME` 으로 실행 파일을 직접
줄 수 있다. 가시성은 `getClientRects().length > 0` 으로 가른다 — 숨긴 부모 안의 자식은 `display` 가 그대로라
`getComputedStyle(e).display` 로는 못 가른다(docs/lessons.md).
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

_MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
VISIBLE = "(e => e.getClientRects().length > 0)"


def find_chrome() -> str | None:
    for cand in (os.environ.get("REACHY_CHROME"), _MAC):
        if cand and os.path.exists(cand):
            return cand
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


class Chrome:
    def __init__(self, exe: str) -> None:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        sock.close()
        self._profile = tempfile.mkdtemp(prefix="reachy-chrome-")
        self._proc = subprocess.Popen(
            [exe, "--headless=new", "--disable-gpu", f"--remote-debugging-port={self.port}",
             f"--user-data-dir={self._profile}", "--window-size=900,1000", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        tabs = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
                break
            except Exception:
                time.sleep(0.1)
        if tabs is None:
            self.close()
            raise RuntimeError("크롬 디버그 포트가 열리지 않았다")
        page = next(t for t in tabs if t["type"] == "page")
        self._ws = connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
        self._n = 0
        self.events: list[dict] = []
        for method in ("Page.enable", "Runtime.enable", "Log.enable"):
            self.call(method)
        self.call("Emulation.setDeviceMetricsOverride", width=900, height=1000, deviceScaleFactor=1, mobile=False)

    def call(self, method: str, **params):
        self._n += 1
        self._ws.send(json.dumps({"id": self._n, "method": method, "params": params}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == self._n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self.events.append(msg)

    def js(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"], ensure_ascii=False)[:600])
        return r["result"].get("value")

    def goto(self, url: str) -> None:
        self.events.clear()
        self.call("Page.navigate", url=url)
        self.wait_for("document.readyState === 'complete'")

    def wait_for(self, expr: str, timeout: float = 5.0, step: float = 0.05):
        """식이 참이 될 때까지 기다린다 — 고정 sleep 을 쓰지 않는다(전환·재접속 타이밍에 흔들리지 않게)."""
        end = time.monotonic() + timeout
        while True:
            try:
                val = self.js(expr)
            except RuntimeError:
                val = None
            if val:
                return val
            if time.monotonic() >= end:
                raise AssertionError(f"제한 시간 안에 참이 되지 않았다: {expr}")
            time.sleep(step)

    def errors(self) -> list[str]:
        """페이지의 JS 예외·콘솔 오류. 도착해 있는 이벤트를 먼저 비운다."""
        try:
            while True:
                self.events.append(json.loads(self._ws.recv(timeout=0.2)))
        except TimeoutError:
            pass
        out = []
        for e in self.events:
            if e.get("method") == "Runtime.exceptionThrown":
                out.append(e["params"]["exceptionDetails"].get("text", "예외"))
            elif e.get("method") == "Log.entryAdded" and e["params"]["entry"]["level"] == "error":
                out.append(e["params"]["entry"].get("text", "오류"))
        return out

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass
        self._proc.terminate()
        shutil.rmtree(self._profile, ignore_errors=True)
```

`tests/_handout_support.py`:

```python
"""브라우저 테스트용 — 진짜 대시보드 서버 + 진짜 큐시트 + 가짜 감독. 허브에 `say` 를 흘려 넣으면 페이지가 받는다."""

import contextlib
import pathlib
import sys
import threading

from websockets.sync.server import serve as ws_serve

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import load_cues
from stage.dashboard import DashboardServer
from stage.dashboard_hub import DashboardHub
from stage.levels import LEVEL_NAMES

COURSES = {"전체": None, "둘만": ("02-history", "03-theory")}


class FakeDirector:
    mode = "podcast"

    def __init__(self) -> None:
        self._cues = tuple(load_cues())
        self.snap = {
            "cue_id": self._cues[0].id, "cue_index": 0, "cue_count": len(self._cues), "state": "idle",
            "speaking_role": None, "question_wait_s": None, "question_wait_total_s": None,
            "mode": "podcast", "show_running": False, "level": "일반", "course": "전체",
            "course_position": [1, len(self._cues)], "course_cue_ids": None,
            "connected": ["mc", "docent"], "rejected": [], "standby": [], "solo_role": None,
        }

    def snapshot(self):
        return dict(self.snap)

    def cue_list(self):
        return [{"id": c.id, "title": c.title, "topic": c.title} for c in self._cues]

    def cues(self):
        return self._cues

    def level_names(self):
        return list(LEVEL_NAMES)

    def mode_names(self):
        return ["podcast", "solo"]

    def course_names(self):
        return list(COURSES)

    def course_ids(self, name):
        return COURSES[name]


class Session:
    def __init__(self, port, hub, director, warned) -> None:
        self.port, self.hub, self.director, self.warned = port, hub, director, warned
        self._seq = 0
        self._ids = {c.id for c in director.cues()}

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def set(self, **snap) -> None:
        self.director.snap.update(snap)

    def say(self, label: str, text: str = "테스트 발화", role: str = "docent") -> None:
        """감독이 로봇에게 `say` 를 보낸 것처럼 허브에 흘린다. 큐시트에 있는 큐면 스냅샷도 그 큐로 옮긴다
        (실제 감독은 큐를 옮긴 뒤 말한다 — 스냅샷이 거꾸로 장을 되돌리지 않게)."""
        cue = label.split(":")[0]
        if cue in self._ids:
            self.set(cue_id=cue, show_running=True)
        self._seq += 1
        self.hub.publish("sent", role=role, type="say", fields={"cue_id": label, "seq": self._seq, "text": text})


@contextlib.contextmanager
def served(**dashboard_kwargs):
    hub, director, warned = DashboardHub(), FakeDirector(), []
    ds = DashboardServer(hub, director, interval=0.05, warn=warned.append, **dashboard_kwargs)
    srv = ws_serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield Session(srv.socket.getsockname()[1], hub, director, warned)
    finally:
        srv.shutdown()
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_handout_live.py`(정적 계약 — 브라우저 없이 돈다):

```python
"""교육자료 따라가기 스크립트의 정적 계약 — 읽기 전용이고 외부로 안 나가며 글자를 텍스트로만 쓴다."""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

STAGE = pathlib.Path(__file__).parent.parent / "stage"
ASSETS = ("handout.css", "handout_live.js")


def _src(name):
    return (STAGE / name).read_text(encoding="utf-8")


def test_따라가기_스크립트는_아무것도_보내지_않는다():
    """읽기 전용 — 소켓 송신도 명령 문자열도 없다(서버도 받은 것을 버린다)."""
    src = _src("handout_live.js")
    assert ".send(" not in src
    assert "cmd" not in src
    assert "/ws/audience" in src


def test_따라가기_스크립트는_textContent_로만_쓴다():
    src = _src("handout_live.js")
    for token in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert token not in src, token


def test_교육자료_자산은_외부_리소스를_부르지_않는다():
    """전용 공유기는 인터넷이 없다 — CDN·웹폰트·이미지 주소가 있으면 현장에서 안 그려진다."""
    for name in ASSETS:
        src = _src(name)
        assert re.findall(r'(?:src|href|url\()\s*["\']?https?://', src) == [], name
        assert "@import" not in src, name
```

`tests/test_handout_browser.py`:

```python
"""교육자료 "공연 따라가기"를 **실제 브라우저**에서 본다 — 진짜 대시보드 서버·진짜 큐시트·가짜 감독이고, 허브에
`say` 를 흘리면 페이지가 같은 오리진의 `/ws/audience` 로 받는다. 크롬이 없으면 건너뛴다."""

import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _cdp import VISIBLE, Chrome, find_chrome
from _handout_support import served

_CHROME = find_chrome()
pytestmark = pytest.mark.skipif(_CHROME is None, reason="크롬이 없어 브라우저 테스트를 건너뛴다(REACHY_CHROME 로 지정)")


@pytest.fixture(scope="module")
def chrome():
    c = Chrome(_CHROME)
    yield c
    c.close()


def _open(chrome, url):
    """페이지를 열고 읽기 전용 소켓이 붙을 때까지 기다린다 — 그 전에 흘린 말은 hello 의 마지막 대사로만 닿는다."""
    chrome.goto(url)
    chrome.wait_for("typeof handout !== 'undefined' && !!handout._socket() && handout._socket().readyState === 1")


@pytest.fixture
def live(chrome):
    with served() as s:
        _open(chrome, s.url("/handout"))
        yield s


def _live_id(chrome):
    return chrome.js("[...document.querySelectorAll('.sheet.live')].map(e => e.id).join()")


def _rows(chrome, cue="02-history"):
    """보이는 말풍선의 `턴:상태` 목록 — 상태는 now·seen·빈칸."""
    return chrome.js(
        f"[...document.getElementById('{cue}').querySelectorAll('.row')].filter({VISIBLE})"
        ".map(e => e.dataset.t + ':' + (e.classList.contains('now') ? 'now' : e.classList.contains('seen') ? 'seen' : ''))"
    )


def test_공연이_시작되면_그_큐의_장이_저절로_선택된다(chrome, live):
    live.say("02-history", "자, 첫 번째 이야기는", role="mc")
    chrome.wait_for("document.querySelector('.sheet.live')?.id === '02-history'")
    assert chrome.js("getComputedStyle(document.querySelector('.sheet.live .livebadge')).display") != "none"
    assert chrome.errors() == []


def test_말하는_말풍선이_강조되고_지난_말풍선은_본_것으로_표시된다(chrome, live):
    live.say("02-history", "여는 말", role="mc")
    live.say("02-history:pt0:docent")
    live.say("02-history:pt1", "질문", role="mc")
    chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'ask1'")
    assert _rows(chrome) == ["open:seen", "docent0:seen", "ask1:now", "docent1:", "ask2:", "docent2:"]


def test_마지막_도슨트는_마지막_번호의_말풍선을_켠다(chrome, live):
    live.say("02-history", "여는 말", role="mc")
    live.say("02-history:docent", "마지막 설명")
    chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'docent2'")
    assert _rows(chrome)[:5] == ["open:seen", "docent0:seen", "ask1:seen", "docent1:seen", "ask2:seen"]


def test_현재_대사_막대에_지금_말하는_문장이_뜬다(chrome, live):
    live.say("02-history:pt0:docent", "도슨트가 이렇게 말한다")
    chrome.wait_for("document.getElementById('nb-text').textContent === '도슨트가 이렇게 말한다'")
    assert chrome.js("document.getElementById('nb-who').textContent") == "도슨트"
    assert chrome.js("document.getElementById('nowbar').hidden") is False


def test_질문_시간_라벨은_장을_안_바꾸고_배지만_띄운다(chrome, live):
    live.say("02-history:pt0:docent", "설명")
    chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'docent0'")
    live.say("02-history:qa", "관람객 질문에 답하는 말")
    chrome.wait_for("document.getElementById('nb-badge').textContent.includes('질문')")
    assert _live_id(chrome) == "02-history" and "docent0:now" in _rows(chrome)


def test_공연_중간에_접속하면_지금_큐와_대목에_선다(chrome):
    with served() as s:
        s.say("03-theory", "여는 말", role="mc")
        s.say("03-theory:pt0:docent")
        s.say("03-theory:pt1", "주파수는 뭐예요?", role="mc")
        _open(chrome, s.url("/handout"))                                # 늦게 켠 폰
        chrome.wait_for("document.querySelector('.sheet.live')?.id === '03-theory'")
        chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'ask1'")
        assert _rows(chrome, "03-theory") == ["open:seen", "docent0:seen", "ask1:now", "docent1:", "ask2:", "docent2:"]


def test_공연이_끝난_뒤_접속하면_지난_공연의_마지막_대사로_장을_켜지_않는다(chrome):
    with served() as s:
        s.say("02-history:docent", "지난 공연의 마지막 말")
        s.set(show_running=False)                                       # 공연 종료(되감기)
        _open(chrome, s.url("/handout"))
        time.sleep(0.3)                                                 # 스냅샷이 몇 번 오고도 켜지지 않는다
        assert _live_id(chrome) == "" and chrome.js("document.getElementById('nowbar').hidden") is True


def test_이_큐_다시와_공연_종료는_강조를_되돌린다(chrome, live):
    live.say("02-history", "여는 말", role="mc")
    live.say("02-history:pt0:docent")
    live.say("02-history:pt1", "질문", role="mc")
    chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'ask1'")
    live.say("02-history", "여는 말", role="mc")                            # r — 이 큐 다시
    chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'open'")
    assert _rows(chrome) == ["open:now", "docent0:", "ask1:", "docent1:", "ask2:", "docent2:"]
    live.set(show_running=False)                                        # e — 공연 종료
    chrome.wait_for("document.querySelectorAll('.sheet.live, .now, .seen').length === 0")
    assert chrome.js("document.getElementById('nowbar').hidden") is True


def test_코스_밖_큐의_대사는_자막만_띄운다(chrome):
    with served() as s:
        _open(chrome, s.url("/handout?course=%EB%91%98%EB%A7%8C"))      # 코스: 둘만(02·03)
        s.say("05-donor", "코스 밖 큐의 말", role="mc")
        chrome.wait_for("document.getElementById('nb-text').textContent === '코스 밖 큐의 말'")
        assert _live_id(chrome) == ""


def test_모르는_라벨과_단독_모드_대사는_자막만_띄운다(chrome, live):
    live.say("solo:qa", "단독 답", role="mc")
    chrome.wait_for("document.getElementById('nb-text').textContent === '단독 답'")
    assert _live_id(chrome) == "" and chrome.errors() == []


def test_직접_스크롤하면_따라가기가_멈추고_다시_누르면_돌아온다(chrome, live):
    top = "Math.round(document.getElementById('%s').getBoundingClientRect().top)"
    live.say("02-history", "여는 말", role="mc")
    chrome.wait_for(f"{top % '02-history'} === 76")                          # 스무스 스크롤이 끝나 정확히 정착한 뒤 — 도중에 읽으면 y 가 더 움직인다
    chrome.js("window.dispatchEvent(new WheelEvent('wheel', {deltaY: 120}))")
    chrome.wait_for("document.getElementById('fstate').textContent === '일시정지됨'")
    y = chrome.js("window.scrollY")
    live.say("03-theory", "다음 큐", role="mc")
    chrome.wait_for("document.querySelector('.sheet.live')?.id === '03-theory'")
    time.sleep(0.5)
    assert chrome.js("window.scrollY") == y                              # 일시정지 중에는 스크롤을 빼앗지 않는다
    chrome.js("document.getElementById('ftoggle').click()")
    chrome.wait_for(f"Math.abs({top % '03-theory'} - 76) < 60")


def test_수준은_감독을_따르다가_관람객이_직접_고르면_잠긴다(chrome, live):
    chrome.wait_for("document.querySelector('input[data-name=일반]').checked")
    live.set(level="초등")
    chrome.wait_for("document.querySelector('input[data-name=초등]').checked")          # 감독을 따른다
    chrome.js("document.querySelector('label[for=lvr2]').click()")                       # 관람객이 일반을 고른다
    chrome.wait_for("document.querySelector('input[data-name=일반]').checked")
    live.set(level="전문가")
    time.sleep(0.4)
    assert chrome.js("document.querySelector('input[data-name=일반]').checked") is True   # 잠겼다


def test_주소에_수준을_적으면_감독_수준을_따라가지_않는다(chrome):
    with served() as s:
        _open(chrome, s.url("/handout?level=%EC%B4%88%EB%93%B1"))                       # 초등
        s.set(level="전문가")
        time.sleep(0.4)
        assert chrome.js("document.querySelector('input[data-name=초등]').checked") is True


def test_연결이_끊기면_표시하고_다시_붙으면_맞춘다(chrome, live):
    live.say("02-history:pt0:docent", "끊기기 전")
    chrome.wait_for("document.querySelector('.sheet.live')?.id === '02-history'")
    chrome.js("handout._socket().close()")                               # 와이파이가 끊겼다
    chrome.wait_for("document.getElementById('conn').textContent.includes('다시 연결')")
    chrome.wait_for("document.getElementById('conn').textContent === ''", timeout=6)  # 다시 붙었다
    live.say("03-theory:pt0:docent", "다시 붙은 뒤")
    chrome.wait_for("document.querySelector('.sheet.live')?.id === '03-theory'")
    assert chrome.errors() == []


def test_저장한_파일로_열면_연결_없음을_알린다(chrome, tmp_path):
    """공연이 끝난 뒤 폰에 저장한 자료 — 소켓 없이도 오류 없이 읽힌다."""
    from stage.cues import load_cues
    from stage.handout import render_handout
    from stage.levels import LEVEL_NAMES

    f = tmp_path / "saved.html"
    f.write_text(render_handout(tuple(load_cues()), "일반", list(LEVEL_NAMES), live=True), encoding="utf-8")
    chrome.goto(f.as_uri())
    assert "연결 없음" in chrome.js("document.getElementById('conn').textContent")
    assert chrome.errors() == []
```

Run: `.venv/bin/python -m pytest tests/test_handout_live.py tests/test_handout_browser.py -v`
Expected: 정적 테스트는 `FileNotFoundError: handout_live.js` 로 FAIL. 브라우저 테스트는 `live` 픽스처를 쓰는 것이 setup ERROR(`typeof handout !== 'undefined' …` 가 5초 안에 참이 되지 않음 — 페이지에 스크립트가 아직 없다)이고 나머지는 FAIL(크롬이 없으면 SKIPPED). 실패 목록이 길고 느린 것(약 80초)이 정상이다.

- [ ] **Step 3: 구현한다**

`stage/handout_live.js`:

```javascript
// 교육자료 "공연 따라가기" — 감독이 로봇에게 보낸 말(`say`)을 읽기 전용 소켓 `/ws/audience` 로 받아, 지금 이야기 중인
// 큐의 장을 켜고 말하는 대목을 강조한다. **이 파일은 소켓으로 아무것도 보내지 않는다**(서버도 받은 것을 버린다).
//
// 서버가 발화 라벨을 풀어 `say` 에 `cue`·`turn` 을 실어 준다(stage/say_label.py). 턴 이름은 페이지의 말풍선
// (`.row[data-t]`)·카드(`[data-turns]`)와 같다: open · ask<i> · docent<i> · after.
// 확장 지점(시각화 부품이 쓴다): window.handout.register(이름, fn(장, 어림ms)) · onReset(fn(장|null)) · onLevel(fn(수준)).
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var body = document.body;
  var radios = $$('input[name=lv]');
  var reduce = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var RECONNECT_MS = 1500;
  var CPS = 4.0;                          // 감독의 CHARS_PER_SEC — 글자 수로 발화 길이를 어림한다
  var follow = true, activeCue = null, ws = null;
  var locked = body.getAttribute('data-level-locked') === '1';
  var actions = {}, resets = [], levelListeners = [];

  var estMs = function (t) { return Math.max(1200, (t || '').length / CPS * 1000); };
  var sheetOf = function (id) { return document.getElementById(id); };
  var radioOf = function (name) { return radios.filter(function (r) { return r.getAttribute('data-name') === name; })[0]; };
  var levelName = function () {
    var r = radios.filter(function (x) { return x.checked; })[0];
    return r ? r.getAttribute('data-name') : '';
  };
  var fireLevel = function () { levelListeners.forEach(function (f) { f(levelName()); }); };

  // ── 수준: 감독을 따르되, 관람객이 직접 고른 것(탭·주소의 ?level=·저장된 선택)이 이긴다 ──
  try {
    var saved = !locked && localStorage.getItem('handout-level'), savedRadio = saved && radioOf(saved);
    if (savedRadio) { savedRadio.checked = true; locked = true; }
  } catch (e) { /* 저장소가 막힌 창 — 기억만 못 할 뿐이다 */ }
  $$('.levels label').forEach(function (l) {
    l.addEventListener('click', function () {
      locked = true;
      var r = document.getElementById(l.getAttribute('for'));
      try { if (r) localStorage.setItem('handout-level', r.getAttribute('data-name')); } catch (e) { /* 위와 같다 */ }
    });
  });
  radios.forEach(function (r) { r.addEventListener('change', fireLevel); });

  // ── 강조 ─────────────────────────────────────────────────────────
  // 이미 지나간 대목은 **저장하지 않고 대화 순서에서 구한다** — 되감기·큐 다시·중간 접속이 같은 규칙으로 맞는다.
  function turnOrder(sh) {
    var chat = $('.chat', sh);
    return chat ? $$('.row[data-t]', chat).map(function (el) { return el.getAttribute('data-t'); }) : [];
  }
  function apply(sh, turn) {
    var ord = turnOrder(sh), at = turn === 'after' ? ord.length : ord.indexOf(turn), done = {};
    ord.slice(0, Math.max(at, 0)).forEach(function (t) { done[t] = true; });
    $$('[data-turns]', sh).forEach(function (el) {
      var toks = el.getAttribute('data-turns').split(' '), now = !!turn && toks.indexOf(turn) >= 0;
      el.classList.toggle('now', now);
      el.classList.toggle('seen', !now && toks.every(function (t) { return done[t]; }));
    });
    $$('.row[data-t]', sh).forEach(function (el) {
      var t = el.getAttribute('data-t');
      el.classList.toggle('now', t === turn);
      el.classList.toggle('seen', t !== turn && !!done[t]);
    });
  }
  function scrollToSheet(id) {
    var sh = sheetOf(id);
    if (sh) sh.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }
  function activate(id) {
    $$('.sheet').forEach(function (s) { s.classList.toggle('live', s.id === id); });
    if (activeCue !== id) {
      var prev = activeCue && sheetOf(activeCue);       // 떠나는 장의 '지금' 강조는 걷는다(본 것 표시는 남긴다)
      if (prev) $$('.now', prev).forEach(function (e) { e.classList.remove('now'); });
      activeCue = id;
      if (follow) scrollToSheet(id);
    }
  }
  function resetCue(sh) { resets.forEach(function (f) { f(sh); }); }
  function runLive(sh, turn, text) {
    var raw = sh.getAttribute('data-live');
    if (!raw) return;
    var spec;
    try { spec = JSON.parse(raw); } catch (e) { console.warn('handout: data-live 를 못 읽었다', raw); return; }
    (spec[turn] || []).forEach(function (name) {
      var f = actions[name];
      if (f) f(sh, estMs(text)); else console.warn('handout: 모르는 동작 ' + name);
    });
  }

  // ── 지금 말하는 대사 막대 ─────────────────────────────────────────
  var nb = $('#nowbar'), nbWho = $('#nb-who'), nbBadge = $('#nb-badge'), nbText = $('#nb-text');
  function showNow(role, text, badge) {
    nb.hidden = false;
    nb.className = 'nowbar ' + (role === 'docent' ? 'docent' : 'mc');
    nbWho.textContent = role === 'docent' ? '도슨트' : '사회자';
    nbBadge.textContent = badge || '';
    nbText.textContent = text || '';
  }

  // ── 서버에서 온 것 ───────────────────────────────────────────────
  function onSay(m) {
    if (!m || typeof m.text !== 'string') return;
    var turn = m.turn, cue = m.cue, qa = turn === 'ack' || turn === 'qa' || turn === 'reask';
    showNow(m.role, m.text, qa ? '관람객 질문 시간' : '');
    if (qa || !cue || !turn) return;           // 질문 답은 큐의 해설 흐름이 아니고, 모르는 라벨은 자막만이다
    var sh = sheetOf(cue);
    if (!sh) return;                           // 이 페이지(코스)에 없는 큐 — 자막만 띄운다
    if (turn === 'open') resetCue(sh);
    activate(cue);
    apply(sh, turn);
    runLive(sh, turn, m.text);
  }
  function clearLive() {
    if (!activeCue && nb.hidden) return;       // 이미 깨끗하다 — 스냅샷이 매초 오므로 되풀이·깜박임을 막는다
    activeCue = null;
    $$('.sheet.live').forEach(function (s) { s.classList.remove('live'); });
    $$('.now,.seen').forEach(function (e) { e.classList.remove('now', 'seen'); });
    nb.hidden = true;
    resets.forEach(function (f) { f(null); });
  }
  function onSnapshot(s) {
    if (!s) return;
    if (s.level && !locked) {
      var r = radioOf(s.level);
      if (r && !r.checked) { r.checked = true; fireLevel(); }
    }
    if (s.show_running === false && s.mode !== 'solo') { clearLive(); return; }
    if (s.cue_id && s.cue_id !== activeCue && sheetOf(s.cue_id)) { activate(s.cue_id); apply(sheetOf(s.cue_id), null); }
  }
  function handle(msg) {
    if (!msg || typeof msg.kind !== 'string') return;
    if (msg.kind === 'hello') {
      if (msg.snapshot) onSnapshot(msg.snapshot);
      // 공연이 끝난 뒤(쉬는 동안) 접속하면 이력의 마지막 대사는 지난 공연의 것이다 — 장을 켜지 않는다.
      var running = msg.snapshot && (msg.snapshot.show_running || msg.snapshot.mode === 'solo');
      if (msg.say && running) onSay(msg.say);
    } else if (msg.kind === 'say') {
      onSay(msg);
    } else if (msg.kind === 'snapshot') {
      onSnapshot(msg);
    }
  }

  // ── 따라가기를 관람객이 끊을 수 있다 — 스크롤을 빼앗지 않는다. 다시 켜면 지금 이야기로 돌아온다 ──
  var ftoggle = $('#ftoggle'), fstate = $('#fstate'), conn = $('#conn');
  function setFollow(on) {
    follow = on;
    fstate.textContent = on ? '공연 따라가기 켜짐' : '일시정지됨';
    ftoggle.textContent = on ? '일시정지' : '지금 이야기로';
    if (on && activeCue) scrollToSheet(activeCue);
  }
  ftoggle.addEventListener('click', function () { setFollow(!follow); });
  ['wheel', 'touchmove'].forEach(function (ev) {
    window.addEventListener(ev, function () { if (follow && activeCue) setFollow(false); }, { passive: true });
  });
  window.addEventListener('keydown', function (e) {
    if (follow && activeCue && ['PageUp', 'PageDown', 'ArrowUp', 'ArrowDown', 'Home', 'End', ' '].indexOf(e.key) >= 0
        && !/INPUT|BUTTON|SELECT/.test(e.target.tagName)) setFollow(false);
  });

  // ── 연결 — 끊기면 화면에 보이고 다시 붙는다(실패는 소리 내서) ──────────
  function setConn(t) { if (conn) conn.textContent = t; }
  function connect() {
    if (!/^https?:$/.test(location.protocol)) { setConn('공연 연결 없음 — 저장된 자료예요'); return; }
    try {
      ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/audience');
    } catch (e) { setConn('공연에 연결하지 못했어요'); return; }
    ws.addEventListener('open', function () { setConn(''); });
    ws.addEventListener('close', function () { setConn('다시 연결하는 중…'); setTimeout(connect, RECONNECT_MS); });
    ws.addEventListener('error', function () { ws.close(); });
    ws.addEventListener('message', function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      handle(msg);
    });
    // 이 페이지는 보내지 않는다 — 읽기 전용이다(서버도 받은 것을 버린다).
  }

  window.handout = {
    onSay: onSay, onSnapshot: onSnapshot,
    register: function (name, fn) { actions[name] = fn; },
    onReset: function (fn) { resets.push(fn); },
    onLevel: function (fn) { levelListeners.push(fn); },
    level: levelName, reduceMotion: reduce, estMs: estMs,
    _socket: function () { return ws; }
  };
  if (body.getAttribute('data-live') === '1') connect();
})();
```

`stage/handout.css` 끝에 이어 붙인다.

```css
.sheet{scroll-margin-top:76px}
.livebadge{display:none;margin-left:auto;font-size:12px;font-weight:700;color:#fff;background:#C23B2E;border-radius:999px;padding:2px 10px}
.sheet.live .livebadge{display:inline-block}
.sheet.live{border-color:var(--sig);box-shadow:0 0 0 3px rgba(11,127,181,.22)}
.row.now .bub{outline:2px solid var(--sig)}
.row.now .av svg{animation:talk 1s ease-in-out infinite alternate}
@keyframes talk{to{transform:translateY(-2px)}}
@media (prefers-reduced-motion:reduce){.row.now .av svg{animation:none}}
body[data-live="1"] main{padding-bottom:210px}
.dock{position:fixed;left:0;right:0;bottom:0;z-index:6;display:flex;flex-direction:column;align-items:center;pointer-events:none}
.dock>*{pointer-events:auto}
.nowbar{width:min(780px,100%);display:flex;gap:12px;align-items:flex-start;padding:10px 16px;background:#fff;
  border-top:3px solid var(--mc);box-shadow:0 -4px 14px rgba(14,36,51,.12)}
.nowbar[hidden]{display:none}
.nowbar.docent{border-top-color:var(--amber)}
.nowbar svg{flex:0 0 40px;width:40px;height:40px;color:var(--mc)}
.nowbar.docent svg{color:var(--amber)}
.nb-h{margin:0;font-size:12px;color:var(--muted);display:flex;gap:10px}
.nb-h b{color:var(--ink)}
#nb-text{margin:0;font-size:16px;font-weight:700;line-height:1.5;max-height:4.6em;overflow:auto}
.follow{width:min(780px,100%);display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;padding:8px 16px;background:var(--ink);color:#fff;font-size:13px}
.follow .mini{font:inherit;font-size:13px;font-weight:700;padding:5px 14px;min-height:44px;border-radius:999px;border:1px solid #fff;background:transparent;color:#fff;cursor:pointer}
.follow .mini:focus-visible{outline:3px solid #7FD3F5;outline-offset:3px}
.rec{width:9px;height:9px;border-radius:50%;background:#E5534B}
#conn{color:#FFD58A}
@media (max-width:640px){.sheet{scroll-margin-top:120px}}
@media print{.dock,.livebadge{display:none !important}.sheet.live{box-shadow:none}}
```

`stage/handout.py` 에 독 상수를 추가하고(`_FACES_SVG` 아래) 렌더러가 `live` 를 쓰게 한다.

```python
_DOCK = """<div class="dock">
  <div class="nowbar" id="nowbar" hidden aria-live="polite">
    <svg viewBox="0 0 48 48" aria-hidden="true"><use href="#face-neutral"/></svg>
    <div><p class="nb-h"><b id="nb-who"></b><span id="nb-badge"></span></p><p id="nb-text"></p></div>
  </div>
  <div class="follow"><span class="rec" aria-hidden="true"></span><span id="fstate">공연 따라가기 켜짐</span>
    <button type="button" id="ftoggle" class="mini">일시정지</button><span id="conn"></span></div>
</div>"""
```

`render_handout` 의 마지막 반환 문자열에서 `"관람 중 나눈 질문과 답은 담기지 않습니다.</p></main></body></html>\n"` 를 아래 세 조각으로 바꾼다.

```python
        "관람 중 나눈 질문과 답은 담기지 않습니다.</p></main>"
        f"{_DOCK if live else ''}"
        f"{'<script>' + _asset('handout_live.js') + '</script>' if live else ''}"
        "</body></html>\n"
```
그리고 docstring 의 "`cards`(Task 5)·`live`(Task 4)는 아직 쓰지 않는다." 를 "`live` 면 따라가기 막대와 스크립트를 싣는다. `cards`(Task 5)는 아직 쓰지 않는다." 로 고친다.

`stage/dashboard.py` 의 `_serve_handout` 호출에 `live=True` 를 더한다.

```python
            body = render_handout(cues, asked, levels, course=course if len(courses) > 1 else None,
                                  level_locked=level_locked, live=True)
```

그리고 `tests/test_audience.py` 에 한 줄 계약을 더한다.

```python
def test_교육자료_페이지는_읽기_전용_소켓에_붙는_스크립트를_싣는다(aud):
    _, _, body = _get(aud["port"], "/handout")
    assert 'data-live="1"' in body and "/ws/audience" in body and 'id="nowbar"' in body
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_handout_live.py tests/test_handout_browser.py tests/test_audience.py -v`
Expected: 전부 PASS(크롬이 없으면 브라우저 테스트만 SKIPPED — 이 맥에는 크롬이 있으므로 실제로 돈다).

- [ ] **Step 5: 눈으로 확인하고 커밋한다**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
git add stage/handout_live.js stage/handout.py stage/handout.css stage/dashboard.py \
  tests/_cdp.py tests/_handout_support.py tests/test_handout_live.py tests/test_handout_browser.py tests/test_audience.py
git commit -m "feat(stage): 교육자료가 공연을 따라간다 — 장 자동 선택·말풍선 강조·자막 막대" \
  -m "/handout 이 같은 오리진의 읽기 전용 /ws/audience 로 say 를 받아 지금 큐의 장을 켜고 말하는 말풍선을 강조한다. 지나간 대목은 대화 순서에서 구해(저장 안 함) 되감기·이 큐 다시·중간 접속이 같은 규칙으로 맞는다. 코스 밖 큐·단독 모드·모르는 라벨은 자막만. 스크롤하면 따라가기가 멈추고, 수준은 감독을 따르되 관람객이 고르면 잠긴다. 끊김은 화면에 보이고 다시 붙는다. 실제 크롬 + 진짜 대시보드 서버로 검증." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 핵심 카드 — 데이터 파일·검증·렌더 (02·03)

**Files:**
- Create: `data/handout.yaml`, `stage/handout_data.py`, `stage/handout_viz.py`(이 Task 에서는 빈 등록표), `tests/test_handout_data.py`
- Modify: `stage/handout.py`(`_section`·`render_handout`), `stage/handout.css`(끝에 이어 붙임), `stage/dashboard.py`(`DashboardServer.__init__`·`_serve_handout`·`start_dashboard`), `tests/test_handout_browser.py`(카드 강조 테스트 추가)

**Interfaces:**
- Consumes: Task 3 의 `render_handout`/`_section`, Task 4 의 `.now`·`.seen` 강조 규칙(`[data-turns]`), `stage.cues.Cue`·`load_cues`, `stage.levels.LEVEL_NAMES`.
- Produces:
  - `stage.handout_data`: `CardError`, `LevelCard(headline, items, remember, formula="", sources="")`, `CueCard(sequence, headline_turns, item_turns, remember_turns, levels, viz="", live={})`, `cards_path()`, `valid_turns(cue)`, `load_cards(cues, path=None) -> dict[str, CueCard]`, `load_cards_or_warn(cues, warn, path=None) -> dict[str, CueCard]`.
  - `stage.handout_viz.VIZ_ACTIONS: dict[str, frozenset[str]]` — 이 Task 에서는 `{}`(Task 6 이 채운다). 비어 있으므로 이 Task 의 YAML 은 `viz`·`live` 를 쓰지 않는다.
  - `render_handout(…, cards=Mapping[str, CueCard])` — 카드가 있는 큐는 한 줄 요약·핵심 3개·기억해 두기 + 접힌 대화 전문(`<details class="talk">`), 없는 큐는 펼쳐진 말풍선(`<div class="talk plain">`). 카드 요소는 `data-turns="<턴> <턴>"` 표지를 단다(Task 4 가 켠다).
  - `DashboardServer(…, cards=None)`; `start_dashboard` 가 감독에게 큐시트를 받을 수 있으면 `load_cards_or_warn` 으로 카드를 읽어 넘긴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_handout_data.py`:

```python
"""교육자료 카드 데이터(`data/handout.yaml`) — 구조 검증, 숫자 근거, 렌더."""

import pathlib
import re
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, Turn, load_cues
from stage.handout import render_handout
from stage.handout_data import CardError, CueCard, LevelCard, load_cards, load_cards_or_warn, valid_turns
from stage.levels import LEVEL_NAMES

ROOT = pathlib.Path(__file__).parent.parent


def _큐():
    ans = {lv: f"{lv} 설명" for lv in LEVEL_NAMES}
    return Cue("c1", "첫째", "사회자 대사", "지시", "partner", mc_after="질문 있으세요? '다음'이라고 해 주세요.",
               points=(Turn("", ans), Turn("그럼요?", ans)))


def _수준카드(**kw):
    base = {"headline": "한 줄", "items": [{"term": "낱말", "gloss": "풀이"}, {"term": "낱말2", "gloss": "풀이2"}],
            "remember": "기억"}
    base.update(kw)
    return base


def _카드(**kw):
    base = {"sequence": True,
            "turns": {"headline": ["open"], "items": [["docent0"], ["ask1", "docent1"]], "remember": ["after"]},
            "levels": {lv: _수준카드() for lv in LEVEL_NAMES}}
    base.update(kw)
    return base


def _쓴다(tmp_path, data):
    p = tmp_path / "handout.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


# ── 구조 검증 ─────────────────────────────────────────────────────────


def test_이_큐의_유효한_턴은_여는_말_받아치기_설명_질문이다():
    assert valid_turns(_큐()) == {"open", "after", "docent0", "docent1", "ask1"}   # 첫 턴에는 질문이 없다


def test_올바른_카드는_읽힌다(tmp_path):
    cards = load_cards([_큐()], _쓴다(tmp_path, {"c1": _카드()}))
    card = cards["c1"]
    assert card.sequence is True and card.item_turns == (("docent0",), ("ask1", "docent1"))
    assert card.levels["초등"].items == (("낱말", "풀이"), ("낱말2", "풀이2"))


def test_빈_파일은_카드_없음이다(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text("", encoding="utf-8")
    assert load_cards([_큐()], p) == {}


@pytest.mark.parametrize("고침, 말", [
    (lambda d: {"zzz": d["c1"]}, "큐시트에 없는 큐"),
    (lambda d: {"c1": {**d["c1"], "levels": {k: v for k, v in d["c1"]["levels"].items() if k != "전문가"}}}, "빠진 수준"),
    (lambda d: {"c1": {**d["c1"], "levels": {**d["c1"]["levels"], "유치원": _수준카드()}}}, "모르는 수준"),
    (lambda d: {"c1": {**d["c1"], "turns": {**d["c1"]["turns"], "headline": ["docent9"]}}}, "이 큐에 없는 턴"),
    (lambda d: {"c1": {**d["c1"], "turns": {**d["c1"]["turns"], "items": [["docent0"], ["docent1"], ["after"]]}}}, "같은 3개"),
    (lambda d: {"c1": {**d["c1"], "levels": {**d["c1"]["levels"], "초등": _수준카드(headline="")}}}, "headline"),
    (lambda d: {"c1": {**d["c1"], "sequence": "yes"}}, "sequence"),
    (lambda d: {"c1": {**d["c1"], "viz": "없는부품"}}, "모르는 시각화"),
    (lambda d: {"c1": {**d["c1"], "live": {"docent0": ["pulse"]}}}, "live 는 viz"),
])
def test_규약에_안_맞는_카드는_기동에서_거절한다(tmp_path, 고침, 말):
    with pytest.raises(CardError, match=말):
        load_cards([_큐()], _쓴다(tmp_path, 고침({"c1": _카드()})))


def test_큐시트를_바꿔_쓰면_그_큐시트에_없는_큐의_카드는_조용히_건너뛴다(tmp_path):
    """맞춤 큐시트(`REACHY_CUES_PATH`)에서 표준 카드 파일이 통째로 거절되거나 경고가 늘어나면 안 된다."""
    p = _쓴다(tmp_path, {"c1": _카드(), "zzz": _카드()})
    warned = []
    assert set(load_cards_or_warn([_큐()], warned.append, p)) == {"c1"} and warned == []
    with pytest.raises(CardError, match="큐시트에 없는 큐"):
        load_cards([_큐()], p)                                           # strict(데이터 테스트)는 오타를 잡는다


def test_카드_파일이_깨지면_경고하고_카드_없이_간다(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text("c1: [깨진", encoding="utf-8")
    warned = []
    assert load_cards_or_warn([_큐()], warned.append, p) == {}
    assert len(warned) == 1 and "카드 없이 말풍선만" in warned[0]


# ── 실제 데이터 ──────────────────────────────────────────────────────


def test_실제_카드_파일이_실제_큐시트로_읽힌다():
    cards = load_cards(load_cues())
    assert {"02-history", "03-theory"} <= set(cards)
    for card in cards.values():
        assert set(card.levels) == set(LEVEL_NAMES)


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _수(text):
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUM.finditer(text)}


def test_카드의_숫자는_대본이나_조사_사실에_있다():
    """교육자료에 환각이 섞이는 것이 가장 나쁘다 — 카드(사람이 저작)가 새 숫자·연도를 만들지 못하게 한다.
    `sources` 는 출처 표기라 뺀다. 계산해서 보여 주는 값(다이얼 읽기값)은 카드가 아니라 코드가 만든다."""
    cues = {c.id: c for c in load_cues()}
    for cid, card in load_cards(load_cues()).items():
        cue = cues[cid]
        blob = cue.mc + cue.mc_after + "".join(t.ask + "".join(t.answers.values()) for t in cue.points)
        research = yaml.safe_load((ROOT / "data" / "cues-research" / f"{cid}.yaml").read_text(encoding="utf-8"))
        blob += "".join(f["claim"] for f in research["facts"])
        known = _수(blob)
        for lv, lc in card.levels.items():
            texts = [lc.headline, lc.remember, lc.formula] + [t + " " + g for t, g in lc.items]
            for text in texts:
                assert _수(text) <= known, f"{cid} {lv}: 근거에 없는 숫자 {_수(text) - known} — {text!r}"


# ── 렌더 ─────────────────────────────────────────────────────────────


def _렌더(cards, level="일반"):
    return render_handout([_큐()], level, list(LEVEL_NAMES), cards=cards)


def _카드객체():
    return CueCard(
        sequence=True, headline_turns=("open",), item_turns=(("docent0",), ("ask1", "docent1")), remember_turns=("after",),
        levels={lv: LevelCard("한 줄 <b>", (("낱말", "풀이"), ("낱말2", "풀이2")), "기억", formula="공식" if lv == "일반" else "")
                for lv in LEVEL_NAMES})


def test_카드가_있는_큐는_요약_카드와_접힌_대화_전문이_있다():
    page = _렌더({"c1": _카드객체()})
    assert 'class="headline lv L2" data-turns="open"' in page
    assert '<ol class="chain lv L0">' in page and 'data-turns="ask1 docent1"' in page
    assert 'class="remember lv L2" data-turns="after"' in page
    assert '<details class="talk"><summary>해설 전문 보기' in page and 'class="talk plain"' not in page
    assert '<p class="formula lv L2">공식</p>' in page and page.count('class="formula') == 1   # 있는 수준만


def test_카드가_없는_큐는_말풍선이_펼쳐져_있다():
    page = _렌더(None)
    assert 'class="talk plain"' in page and "<details" not in page


def test_카드에_없는_수준이_있으면_그_큐는_카드_없이_그린다():
    """카드가 한 수준을 못 덮으면 KeyError 로 페이지가 죽지 않고 말풍선만 보인다."""
    from dataclasses import replace

    카드 = _카드객체()
    일부 = replace(카드, levels={lv: c for lv, c in 카드.levels.items() if lv != "전문가"})
    page = _렌더({"c1": 일부})
    assert 'class="talk plain"' in page and 'class="headline' not in page


def test_카드의_글자는_이스케이프된다():
    page = _렌더({"c1": _카드객체()})
    assert "한 줄 &lt;b&gt;" in page and "한 줄 <b>" not in page


def test_번호가_없는_이야기는_defs_로_그린다():
    from dataclasses import replace

    page = _렌더({"c1": replace(_카드객체(), sequence=False)})
    assert '<ol class="defs lv L0">' in page and 'class="chain' not in page
```

`tests/test_audience.py` 맨 아래에 서버 배선 테스트를 더한다(`DashboardServer` 가 카드를 `/handout` 에 싣는지).

```python
def test_교육자료는_서버가_받은_카드를_싣는다(tmp_path):
    from stage.handout_data import CueCard, LevelCard

    카드 = CueCard(sequence=False, headline_turns=("open",), item_turns=(("docent0",),), remember_turns=("after",),
                   levels={lv: LevelCard("요약", (("낱말", "풀이"),), "기억") for lv in _수준들})
    page = tmp_path / "page.html"
    page.write_text("x", encoding="utf-8")
    ds = DashboardServer(DashboardHub(), 가짜감독(), page=page, interval=0.05, cards={"01-intro": 카드})
    with _served(ds) as port:
        _, _, body = _get(port, "/handout")
    assert 'data-turns="open"' in body and "요약" in body
```
(`가짜감독` 의 수준이 `_수준들` = 초등·일반 두 개라 카드의 `levels` 를 같은 두 개로 만든다 — 렌더러는 `levels` 에 있는 수준이 카드에 다 있을 때만 카드를 쓴다.)

그리고 `tests/test_dashboard_e2e.py` 가 아니라 `tests/test_audience.py` 맨 아래에 `start_dashboard` 배선 테스트도 더한다.

```python
def test_start_dashboard_는_큐시트를_줄_수_있는_감독이면_실제_카드를_읽어_싣는다():
    import sys as _sys
    _sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from _handout_support import FakeDirector
    from stage.dashboard import start_dashboard

    warned = []
    srv = start_dashboard(DashboardHub(), FakeDirector(), "127.0.0.1", 0, warn=warned.append)
    try:
        _, _, body = _get(srv.socket.getsockname()[1], "/handout")
    finally:
        srv.shutdown()
    assert 'class="headline lv L0"' in body and "02-history" in body        # data/handout.yaml 의 02 카드
    assert not [w for w in warned if "카드" in w], warned
```

`tests/test_handout_browser.py` 끝에 카드 강조 브라우저 테스트를 더한다.

```python
@pytest.fixture
def live_cards(chrome):
    from stage.cues import load_cues
    from stage.handout_data import load_cards

    with served(cards=load_cards(load_cues())) as s:
        _open(chrome, s.url("/handout"))
        yield s


def _items(chrome, cue="02-history"):
    return chrome.js(
        f"[...document.getElementById('{cue}').querySelectorAll('.chain li, .defs li')].filter({VISIBLE})"
        ".map(e => e.classList.contains('now') ? 'now' : e.classList.contains('seen') ? 'seen' : '')"
    )


def test_도슨트가_말하는_대목의_카드가_켜지고_지난_카드는_본_것이_된다(chrome, live_cards):
    s = live_cards
    s.say("02-history", "여는 말", role="mc")
    s.say("02-history:pt0:docent")
    s.say("02-history:pt1", "질문", role="mc")
    chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'ask1'")
    assert _items(chrome) == ["now", "now", ""]                          # 맥스웰·헤르츠 카드
    s.say("02-history:pt2", "다음 질문", role="mc")
    chrome.wait_for("document.querySelector('.sheet.live .row.now')?.dataset.t === 'ask2'")
    assert _items(chrome) == ["seen", "seen", "now"]
    s.say("02-history:after", "받아치기", role="mc")
    chrome.wait_for("!!document.querySelector('.sheet.live .remember.now')")      # 요소를 그대로 돌려주면 {} 라 거짓이다
    assert _items(chrome) == ["seen", "seen", "seen"]


def test_카드가_있는_큐의_대화_전문은_접혀_있고_없는_큐는_펼쳐져_있다(chrome, live_cards):
    assert chrome.js("document.getElementById('02-history').querySelector('details.talk').open") is False
    assert chrome.js("document.getElementById('01-intro').querySelectorAll('details').length") == 0
    assert chrome.js(f"[...document.getElementById('01-intro').querySelectorAll('.row')].filter({VISIBLE}).length") > 0


def test_수준을_바꾸면_카드_문구가_그_수준으로_바뀐다(chrome, live_cards):
    chrome.js("document.querySelector('label[for=lvr0]').click()")      # 초등
    chrome.wait_for(
        f"[...document.getElementById('02-history').querySelectorAll('.headline')].filter({VISIBLE})"
        ".map(e => e.textContent).join().includes('찾아낸')")
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_handout_data.py tests/test_audience.py -v -k "카드 or 핸드 or start_dashboard or valid_turns or 유효한_턴"`
Expected: `ModuleNotFoundError: No module named 'stage.handout_data'`.

- [ ] **Step 3: 구현한다**

`stage/handout_viz.py`(이 Task 에서는 등록표만 둔다 — 시각화 부품은 Task 6):

```python
"""교육자료 시각화 부품 — 이름으로 부른다(`data/handout.yaml` 의 `viz`). 이 Task 에서는 등록표가 비어 있다.

`VIZ_ACTIONS[이름]` 은 그 부품이 받을 수 있는 자동 동작 이름의 집합이다(`live` 가 이 이름을 적는다). 데이터가
모르는 이름을 쓰면 기동에서 거절한다 — 오타가 조용히 "아무 일도 안 일어남" 이 되지 않게.
"""

VIZ_ACTIONS: dict[str, frozenset[str]] = {}
```

`stage/handout_data.py`:

```python
"""교육자료 카드 데이터(`data/handout.yaml`) — 큐마다 수준별 "핵심 카드"(한 줄 요약·핵심 낱말 풀이·기억해 두기)와
시각화·자동 동작 지정. 카드가 없는 큐는 말풍선 대화만으로 그려진다(점진 강화).

**여기 적는 글은 사람이 검수한 문장이다**(LLM 생성 금지 — `stage/handout.py` 머리 docstring 과 같은 이유).
카드 속 숫자·연도는 대본이나 조사 파일 사실에 있는 것만 쓴다 — `tests/test_handout_data.py` 가 지킨다.
틀리면 **기동에서 소리 내서 거절한다**: 조용히 흐려진 채 도는 것이 가장 나쁘다. 다만 카드가 깨져도 교육자료와
감독은 산다 — `load_cards_or_warn` 이 경고하고 카드 없이(말풍선만) 간다.
"""

import os
import pathlib
from dataclasses import dataclass, field
from typing import Callable

import yaml

from stage.cues import Cue
from stage.levels import LEVEL_NAMES


class CardError(ValueError):
    """교육자료 카드 데이터가 규약에 맞지 않는다."""


@dataclass(frozen=True)
class LevelCard:
    headline: str
    items: tuple[tuple[str, str], ...]      # (낱말, 풀이)
    remember: str
    formula: str = ""
    sources: str = ""


@dataclass(frozen=True)
class CueCard:
    sequence: bool                          # 항목에 번호를 붙이는가(순서가 있는 이야기일 때만)
    headline_turns: tuple[str, ...]
    item_turns: tuple[tuple[str, ...], ...]   # 항목과 같은 길이 — 각 항목이 켜지는 턴
    remember_turns: tuple[str, ...]
    levels: dict[str, LevelCard]
    viz: str = ""                           # `stage.handout_viz.VIZ_ACTIONS` 의 이름
    live: dict[str, tuple[str, ...]] = field(default_factory=dict)   # 턴 → 자동 동작 이름들


def cards_path() -> pathlib.Path:
    """카드 파일 경로. `REACHY_HANDOUT_PATH` 가 있으면 그것을 쓴다."""
    override = os.environ.get("REACHY_HANDOUT_PATH")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "handout.yaml"


def valid_turns(cue: Cue) -> frozenset[str]:
    """이 큐에서 말풍선·카드가 가리킬 수 있는 턴 이름(`stage/say_label.py` 가 푸는 이름과 같다)."""
    turns = {"open", "after"}
    for i, t in enumerate(cue.points):
        turns.add(f"docent{i}")
        if t.ask:
            turns.add(f"ask{i}")
    return frozenset(turns)


def _text(where: str, v) -> str:
    if not isinstance(v, str) or not v.strip():
        raise CardError(f"{where} 는 비어 있지 않은 문자열이어야 한다 — 지금은 {type(v).__name__}({v!r})")
    return v.strip()


def _optional_text(where: str, v) -> str:
    return "" if v is None else _text(where, v)


def _turns(where: str, v, valid: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(v, list) or not v or not all(isinstance(t, str) for t in v):
        raise CardError(f"{where} 는 턴 이름의 비어 있지 않은 목록이어야 한다 — 지금은 {v!r}")
    bad = [t for t in v if t not in valid]
    if bad:
        raise CardError(f"{where}: 이 큐에 없는 턴이다 — {bad} (있는 것: {sorted(valid)})")
    return tuple(v)


def load_cards(cues, path: pathlib.Path | None = None, *, strict: bool = True) -> dict[str, CueCard]:
    """카드 파일을 읽는다. 어긋나면 **소리 내서 실패한다**(`CardError`).

    `strict=False` 는 **큐시트에 없는 큐의 카드를 건너뛴다** — 큐시트를 바꿔 쓰는 운영(`REACHY_CUES_PATH`)이나 큐 수가 적은
    큐시트에서 표준 카드 파일이 통째로 거절되지 않게 한다. 구조 오류(빠진 수준·없는 턴 등)는 여전히 거절한다. 큐 id 오타는
    기본값(`strict=True`)으로 도는 데이터 테스트(`test_실제_카드_파일이_실제_큐시트로_읽힌다`)가 잡는다.
    """
    from stage.handout_viz import VIZ_ACTIONS   # 늦게 가져온다 — 부품 모듈이 이 모듈을 부르지 않는다

    p = pathlib.Path(path) if path is not None else cards_path()
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CardError(f"교육자료 카드 파일이 없다: {p}") from exc
    except yaml.YAMLError as exc:
        raise CardError(f"교육자료 카드 파일이 YAML 이 아니다: {p} — {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CardError(f"{p}: 큐 id 를 키로 하는 매핑이어야 한다 — 지금은 {type(raw).__name__}")

    by_id = {c.id: c for c in cues}
    out: dict[str, CueCard] = {}
    for cid, item in raw.items():
        where = f"{p} {cid}"
        cue = by_id.get(cid)
        if cue is None:
            if strict:
                raise CardError(f"{where}: 큐시트에 없는 큐다")
            continue
        if not isinstance(item, dict):
            raise CardError(f"{where}: 매핑이어야 한다 — 지금은 {type(item).__name__}")
        valid = valid_turns(cue)

        sequence = item.get("sequence", False)
        if not isinstance(sequence, bool):
            raise CardError(f"{where}: sequence 는 true/false 여야 한다 — 지금은 {sequence!r}")
        turns = item.get("turns")
        if not isinstance(turns, dict):
            raise CardError(f"{where}: turns({{headline, items, remember}})가 필요하다")
        headline_turns = _turns(f"{where} turns.headline", turns.get("headline"), valid)
        remember_turns = _turns(f"{where} turns.remember", turns.get("remember"), valid)
        raw_items = turns.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise CardError(f"{where}: turns.items 는 항목마다 턴 목록을 담은 비어 있지 않은 목록이어야 한다")
        item_turns = tuple(_turns(f"{where} turns.items[{j}]", t, valid) for j, t in enumerate(raw_items))

        levels_raw = item.get("levels")
        if not isinstance(levels_raw, dict):
            raise CardError(f"{where}: levels 가 필요하다")
        missing = set(LEVEL_NAMES) - set(levels_raw)
        if missing:
            # 한 수준만 빠지면 그 수준 관람객이 카드 없이 본다 — 조용히 품질이 떨어지므로 기동에서 막는다.
            raise CardError(f"{where}: 빠진 수준이 있다 — {sorted(missing)}")
        unknown = set(levels_raw) - set(LEVEL_NAMES)
        if unknown:
            raise CardError(f"{where}: 모르는 수준이다 — {sorted(unknown)} (쓸 수 있는 값: {', '.join(LEVEL_NAMES)})")
        levels: dict[str, LevelCard] = {}
        for name in LEVEL_NAMES:
            lw = f"{where} {name}"
            lv = levels_raw[name]
            if not isinstance(lv, dict):
                raise CardError(f"{lw}: 매핑이어야 한다")
            items_raw = lv.get("items")
            if not isinstance(items_raw, list) or len(items_raw) != len(item_turns):
                raise CardError(f"{lw}: items 는 turns.items 와 같은 {len(item_turns)}개여야 한다")
            items = []
            for j, it in enumerate(items_raw):
                if not isinstance(it, dict):
                    raise CardError(f"{lw} items[{j}]: {{term, gloss}} 매핑이어야 한다")
                items.append((_text(f"{lw} items[{j}].term", it.get("term")),
                              _text(f"{lw} items[{j}].gloss", it.get("gloss"))))
            levels[name] = LevelCard(
                headline=_text(f"{lw}.headline", lv.get("headline")),
                items=tuple(items),
                remember=_text(f"{lw}.remember", lv.get("remember")),
                formula=_optional_text(f"{lw}.formula", lv.get("formula")),
                sources=_optional_text(f"{lw}.sources", lv.get("sources")),
            )

        viz = item.get("viz") or ""
        live_raw = item.get("live") or {}
        if viz and viz not in VIZ_ACTIONS:
            raise CardError(f"{where}: 모르는 시각화다 — {viz!r} (있는 것: {sorted(VIZ_ACTIONS)})")
        if live_raw and not viz:
            raise CardError(f"{where}: live 는 viz 가 있어야 쓴다")
        if not isinstance(live_raw, dict):
            raise CardError(f"{where}: live 는 턴 → 동작 이름 목록의 매핑이어야 한다")
        live: dict[str, tuple[str, ...]] = {}
        for turn, names in live_raw.items():
            if turn not in valid:
                raise CardError(f"{where} live: 이 큐에 없는 턴이다 — {turn!r}")
            if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
                raise CardError(f"{where} live.{turn}: 동작 이름의 비어 있지 않은 목록이어야 한다")
            bad = [n for n in names if n not in VIZ_ACTIONS[viz]]
            if bad:
                raise CardError(f"{where} live.{turn}: {viz} 가 모르는 동작이다 — {bad} (있는 것: {sorted(VIZ_ACTIONS[viz])})")
            live[turn] = tuple(names)

        out[cid] = CueCard(sequence, headline_turns, item_turns, remember_turns, levels, viz, live)
    return out


def load_cards_or_warn(cues, warn: Callable[[str], None], path: pathlib.Path | None = None) -> dict[str, CueCard]:
    """카드가 깨져도 교육자료와 감독은 산다 — 경고하고 카드 없이(말풍선만) 간다."""
    try:
        return load_cards(cues, path, strict=False)
    except CardError as exc:
        warn(f"⚠ 교육자료 카드를 못 읽었다 — 카드 없이 말풍선만 보여 준다: {exc}")
        return {}
```

`data/handout.yaml`(02·03 두 큐 — 시안의 검수 문구를 옮긴 것이다):

```yaml
# 교육자료 카드 — 큐마다 수준별 "핵심 카드"(한 줄 요약·핵심 낱말 풀이·기억해 두기).
# 여기 적는 글은 사람이 검수한 문장이다(LLM 생성 금지). 숫자·연도는 대본이나 data/cues-research/<큐>.yaml 의
# facts 에 있는 것만 쓴다 — tests/test_handout_data.py::test_카드의_숫자는_대본이나_조사_사실에_있다 가 지킨다.
# 카드가 없는 큐는 말풍선 대화만으로 그려진다(점진 강화) — 나머지 17큐는 저작되는 대로 여기에 더한다.
#
# turns: 어느 대목에서 이 카드가 켜지는가. 이름은 발화 라벨에서 온다(stage/say_label.py):
#   open(사회자 여는 말) · ask<i>(사회자 질문, i≥1) · docent<i>(도슨트 i번 설명, 마지막 포함) · after(받아치기)
# sequence: true 면 항목에 번호를 붙인다 — 순서가 있는 이야기(예언 → 증명 → 활용)일 때만.

02-history:
  sequence: true
  turns:
    headline: [open, docent0]
    items: [[ask1, docent1], [ask1, docent1], [ask2, docent2]]
    remember: [after]
  levels:
    초등:
      headline: "전파는 누가 만든 게 아니라, 원래 있던 걸 찾아낸 거예요"
      items:
        - {term: "계산", gloss: "한 과학자가 계산해 보고 ‘이런 게 있을 거야!’ 하고 알아냈어요."}
        - {term: "실험", gloss: "다른 과학자가 실험으로 진짜 있다는 걸 보여 줬어요."}
        - {term: "신호 보내기", gloss: "전파에 신호를 실어 넓은 바다 건너편까지 보냈어요."}
      remember: "눈에 안 보여도 전파는 원래 있었고, 과학자들이 찾아냈어요."
    중고등:
      headline: "전파는 발명이 아니라 발견이에요"
      items:
        - {term: "맥스웰 · 예언", gloss: "수식만으로 이런 파동이 있을 거라고 내다봤어요."}
        - {term: "헤르츠 · 증명", gloss: "실험으로 처음 증명했어요."}
        - {term: "마르코니 · 실용화", gloss: "무선전신을 실용화했어요. 1901년에는 대서양 건너 약 3,500km에서 모스 부호를 받았다고 발표했어요."}
      remember: "발명은 없던 걸 새로 만드는 것, 발견은 원래 있던 걸 알아내는 것이에요."
    일반:
      headline: "예언한 사람, 증명한 사람, 써먹은 사람이 따로 있었어요"
      items:
        - {term: "맥스웰 · 이론", gloss: "전기·자기·빛이 한 가지 현상이라는 이론을 세웠고, 그 방정식이 전자기파를 예언했어요."}
        - {term: "헤르츠 · 증명", gloss: "그 전자기파를 실험으로 처음 확실하게 증명했어요."}
        - {term: "마르코니 · 무선전신", gloss: "1901년 12월 12일, 영국 폴듀에서 보낸 모스 부호를 약 3,500km 떨어진 대서양 건너 뉴펀들랜드에서 받았대요. 그때 뉴펀들랜드는 영국 식민지였어요."}
      remember: "전파는 발명이 아니라 발견이에요."
    전문가:
      headline: "전파를 발견한 사람을 한 명으로 꼽기는 어렵다"
      items:
        - {term: "맥스웰 방정식 · 이론적 예언", gloss: "전자기파의 존재를 예언했다."}
        - {term: "헤르츠 · 실험적 증명", gloss: "처음으로 결정적인 실험으로 증명했다. 흔히 드는 1785년은 쿨롱 법칙이 나온 해로, 전자기학의 출발점이지 전파의 발견은 아니다."}
        - {term: "마르코니 · 실용화", gloss: "1909년 브라운과 노벨 물리학상을 공동 수상했다. 1901년 폴듀에서 세인트존스까지 약 3,500km 수신은 지금도 논쟁거리다."}
      remember: "이론적 예언, 실험적 증명, 실용화는 각각 다른 사람의 일이었다."
      sources: "Wikipedia — James Clerk Maxwell · Heinrich Hertz · Guglielmo Marconi · Coulomb’s law (신뢰 등급 B)"

03-theory:
  sequence: false
  turns:
    headline: [open]
    items: [[docent0], [ask1, docent1], [ask2, docent2]]
    remember: [after]
  levels:
    초등:
      headline: "전파는 눈에 안 보이는 물결이에요"
      items:
        - {term: "물결", gloss: "연못의 물결처럼 멀리 퍼져 가요. 전파는 물이 없는 텅 빈 곳도 지나가요."}
        - {term: "주파수", gloss: "물결이 얼마나 빠르게 출렁이는지예요."}
        - {term: "파장", gloss: "물결 하나의 길이예요. 빠르게 출렁일수록 짧아져요."}
      remember: "빠르게 출렁일수록 물결 하나는 짧아져요."
    중고등:
      headline: "주파수가 높을수록 파장은 짧아져요"
      items:
        - {term: "전자기파", gloss: "전기와 자기가 서로를 밀어 주며 퍼져 나가요. 소리와 달리 텅 빈 우주 공간에서도 가요."}
        - {term: "주파수 (Hz)", gloss: "1초에 몇 번 출렁이는지예요. 단위 헤르츠는 전파를 처음 증명한 헤르츠에서 왔어요."}
        - {term: "파장", gloss: "한 번 출렁이는 동안 나아간 거리예요. 주파수와 반비례해요."}
      remember: "주파수가 높아지면 파장은 짧아져요. 둘은 반비례예요."
      formula: "주파수 ↑ → 파장 ↓ (반비례)"
    일반:
      headline: "파장은 빛의 속도를 주파수로 나눈 값이에요"
      items:
        - {term: "전파", gloss: "빛과 같은 전자기파의 한 갈래예요. 진공에서도 가고, 그때는 빛의 속도로 달려요."}
        - {term: "주파수", gloss: "1초 동안 진동하는 횟수예요. 1회가 1헤르츠, 1,000회가 1킬로헤르츠예요."}
        - {term: "파장", gloss: "빛의 속도 ÷ 주파수예요. 100메가헤르츠 FM 라디오 전파의 파장은 약 3m예요."}
      remember: "주파수가 높을수록 파장은 짧아져요."
      formula: "파장 = 빛의 속도 ÷ 주파수 · 예) 100MHz FM 라디오 → 약 3m"
    전문가:
      headline: "전파는 3,000GHz보다 낮은 주파수의 전자기파다"
      items:
        - {term: "전파법상 정의", gloss: "인공적인 유도 없이 공간에 퍼져 나가는 전자파로서 국제전기통신연합이 정한 범위의 주파수를 가진 것."}
        - {term: "ITU 전파규칙", gloss: "그 범위를 3,000GHz보다 낮은 주파수로 잡는다."}
        - {term: "빛의 속도 c", gloss: "299,792,458m/s. 측정값이 아니라 미터의 정의가 고정한 값이라 정확하다."}
      remember: "λ = c ÷ f 이고, c 는 근삿값이 아니라 정의로 고정된 정확한 값이다."
      formula: "λ = c ÷ f · c = 299,792,458 m/s (정확값)"
      sources: "전파법 제2조제1항제1호(A) · ITU 전파규칙 No. 1.5(A) · Wikipedia — Speed of light(B)"
```

`stage/handout.py` 를 고친다. `_section` 과 아래 두 함수를 바꿔 넣는다(`_usable`·`_card_html` 은 새로).

```python
def _usable(card, levels: list[str]) -> bool:
    """카드가 이 페이지의 모든 수준을 갖고 있을 때만 쓴다 — 아니면 말풍선만(KeyError 로 페이지가 죽지 않게)."""
    return card is not None and all(lv in card.levels for lv in levels)


def _card_html(card, levels: list[str], viz_html: str = "") -> str:
    """한 줄 요약 → (그림) → 공식 → 핵심 낱말 풀이 → 기억해 두기. `data-turns` 는 켜지는 대목이다(Task 4)."""
    heads = "".join(
        f'<h3 class="headline lv L{k}" data-turns="{" ".join(card.headline_turns)}">{_esc(card.levels[lv].headline)}</h3>'
        for k, lv in enumerate(levels)
    )
    formula = "".join(
        f'<p class="formula lv L{k}">{_esc(card.levels[lv].formula)}</p>'
        for k, lv in enumerate(levels) if card.levels[lv].formula
    )
    kind = "chain" if card.sequence else "defs"
    lists = ""
    for k, lv in enumerate(levels):
        lis = "".join(
            f'<li data-turns="{" ".join(card.item_turns[j])}"><strong>{_esc(term)}</strong><span>{_esc(gloss)}</span></li>'
            for j, (term, gloss) in enumerate(card.levels[lv].items)
        )
        lists += f'<ol class="{kind} lv L{k}">{lis}</ol>'
    remember = "".join(
        f'<p class="remember lv L{k}" data-turns="{" ".join(card.remember_turns)}">'
        f'<span class="tag">기억해 두기</span>{_esc(card.levels[lv].remember)}</p>'
        for k, lv in enumerate(levels)
    )
    return f"{heads}{viz_html}{formula}{lists}{remember}"


def _section(number: int, cue: Cue, levels: list[str], card=None) -> str:
    chats = "".join(
        f'<div class="chat lv L{k}">{_chat_rows(cue, lv)}</div>' for k, lv in enumerate(levels)
    )
    if card is None:
        # 카드가 없는 큐 — 말풍선 대화가 펼쳐져 있다(접어 두면 이 장에 읽을 것이 없다).
        inner = f'<div class="talk plain">{chats}</div>'
    else:
        src = "".join(
            f'<p class="src lv L{k}">근거 · {_esc(card.levels[lv].sources)}</p>'
            for k, lv in enumerate(levels) if card.levels[lv].sources
        )
        inner = (
            f"{_card_html(card, levels)}"
            f'<details class="talk"><summary>해설 전문 보기 — 사회자와 도슨트의 대화</summary>{chats}</details>{src}'
        )
    return (
        f'<section class="sheet" id="{_esc(cue.id)}" data-points="{len(cue.points)}">'
        f'<header class="sheet-h"><span class="no">{number:02d}</span><h2>{_esc(cue.title)}</h2>'
        '<span class="livebadge">● 지금 이야기 중</span></header>'
        f'<div class="ruler" aria-hidden="true"></div>{inner}</section>'
    )
```
`render_handout` 의 `sections = …` 줄을 아래로 바꾸고 docstring 의 "`cards`(Task 5)는 아직 쓰지 않는다." 를 "`cards` 가 있는 큐는 요약 카드를 앞에 두고 대화 전문을 접는다." 로 고친다.

```python
    cards = cards or {}
    sections = "".join(
        _section(n, cue, levels, cards.get(cue.id) if _usable(cards.get(cue.id), levels) else None)
        for n, cue in enumerate(cues, start=1)
    )
```

`stage/handout.css` 끝에 카드 스타일을 이어 붙인다.

```css
.headline{font-size:30px;line-height:1.3;font-weight:800;letter-spacing:-.025em;margin:0 0 6px;max-width:19em;text-wrap:balance}
.formula{margin:2px 0 14px;font-size:16px;font-weight:700;font-variant-numeric:tabular-nums;padding:8px 14px;background:var(--mist);--d:inline-block}
.chain,.defs{list-style:none;margin:18px 0 6px;padding:0;--d:grid}
.chain{grid-template-columns:repeat(3,1fr);counter-reset:s}
.chain li{counter-increment:s;position:relative;border-top:3px solid var(--sig);padding:22px 18px 4px 0}
.chain li::before{content:counter(s);position:absolute;top:-15px;left:0;width:27px;height:27px;border-radius:50%;
  background:var(--ink);color:#fff;font-size:14px;font-weight:700;display:grid;place-items:center}
.defs{grid-template-columns:repeat(3,1fr)}
.defs li{border-left:1px solid var(--rule);padding:0 16px}
.defs li:first-child{border-left:none;padding-left:0}
.chain strong,.defs strong{display:block;font-size:19px;line-height:1.35;font-weight:800;margin-bottom:5px}
.chain span,.defs span{font-size:15px;color:#27394A;display:block}
.remember{margin:20px 0 4px;padding:13px 18px;background:var(--mist);border-left:6px solid var(--sig);font-size:18px;font-weight:700;line-height:1.55}
.tag{display:inline-block;font-size:12px;font-weight:700;background:var(--ink);color:#fff;border-radius:999px;padding:1px 10px;margin-right:10px;vertical-align:2px}
details.talk{border-top:1px solid var(--rule);padding-top:12px}
details.talk summary{cursor:pointer;font-size:15px;font-weight:700;color:var(--sig)}
.src{margin:14px 0 0;font-size:13px;color:var(--muted)}
[data-turns]{transition:background-color .35s,opacity .35s}
.sheet.live [data-turns]:not(.now):not(.seen){opacity:.72}
.chain li.now,.defs li.now{background:var(--mist)}
.chain li.now strong,.defs li.now strong{color:var(--sig)}
.headline.now{box-shadow:inset 0 -8px 0 rgba(11,127,181,.22)}
.remember.now{outline:2px solid var(--sig)}
@media (max-width:640px){
  .headline{font-size:25px}
  .chain,.defs{grid-template-columns:1fr}
  .chain li{border-top:none;border-left:3px solid var(--sig);padding:0 0 18px 26px}
  .chain li::before{top:0;left:-15px}
  .defs li{border-left:none;border-top:1px solid var(--rule);padding:12px 0}
  .defs li:first-child{border-top:none;padding-top:0}
}
@media print{details.talk{display:none}[data-turns]{opacity:1 !important;background:none !important}}
```

`stage/dashboard.py` 를 고친다.

`DashboardServer.__init__` 를 두 군데 고친다. 시그니처의 마지막 매개변수 `audience_page: pathlib.Path = AUDIENCE_PAGE) -> None:` 를 아래로 바꾸고,

```python
                 audience_page: pathlib.Path = AUDIENCE_PAGE, cards=None) -> None:
```
본문의 `self._warn = warn` 줄 아래(Task 2 가 더한 `self._points` 줄 위)에 한 줄을 더한다.

```python
        # 교육자료 카드(`data/handout.yaml`, Task 5) — 큐 id → CueCard. 없으면 모든 큐가 말풍선만으로 그려진다.
        self._cards = cards or {}
```
`_serve_handout` 의 `render_handout` 호출에 `cards=self._cards` 를 더한다.

```python
            body = render_handout(cues, asked, levels, course=course if len(courses) > 1 else None,
                                  level_locked=level_locked, live=True, cards=self._cards)
```
`start_dashboard` 를 아래로 바꾼다 — **시그니처는 그대로**다(`tests/test_stage_main.py` 의 가짜 `start_dashboard` 들이 같은 시그니처다).

```python
def start_dashboard(hub, director, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                    camera=None, warn: Callable[[str], None] = print):
    """대시보드를 띄운다. **실패해도 감독·콘솔은 그대로 돈다** — 경고하고 None."""
    # 교육자료 카드는 여기서 읽는다 — 카드가 깨져도 경고하고 말풍선만으로 간다(감독은 산다). 큐시트를 줄 수 없는
    # 감독(테스트의 가짜)은 카드 없이 간다.
    cards = None
    cues_of = getattr(director, "cues", None)
    if callable(cues_of):
        cards = load_cards_or_warn(cues_of(), warn)
    ds = DashboardServer(hub, director, camera=camera, warn=warn, cards=cards)
```
(나머지 본문은 그대로.) import 에 `from stage.handout_data import load_cards_or_warn` 를 더한다.

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_handout_data.py tests/test_audience.py tests/test_handout_browser.py tests/test_dashboard.py tests/test_dashboard_e2e.py tests/test_stage_main.py -v`
Expected: 전부 PASS. 특히 `test_카드의_숫자는_대본이나_조사_사실에_있다` 가 통과해야 한다 — 실패하면 카드 문구가 근거 없는 숫자를 만든 것이니 YAML 을 고친다(테스트를 고치지 않는다).

- [ ] **Step 5: 눈으로 확인하고 커밋한다**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
git add data/handout.yaml stage/handout_data.py stage/handout_viz.py stage/handout.py stage/handout.css stage/dashboard.py \
  tests/test_handout_data.py tests/test_audience.py tests/test_handout_browser.py
git commit -m "feat(stage): 교육자료 핵심 카드 — 한 줄 요약·핵심 낱말·기억해 두기를 데이터로(02·03)" \
  -m "data/handout.yaml 에 수준별 검수 카드를 두고 기동에서 구조(수준·턴·항목 수)를 검증한다. 카드 속 숫자는 대본이나 조사 사실에 있어야 한다는 테스트로 환각을 막는다. 카드가 있는 큐는 요약이 앞에, 대화 전문은 접힌다. 없는 큐는 말풍선이 펼쳐진 채다(점진 강화). 카드가 깨지면 경고하고 말풍선만으로 간다." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 시각화 부품과 자동 인터랙션 — 신호 보내기(02)·주파수 다이얼(03)

**Files:**
- Rewrite: `stage/handout_viz.py`(Task 5 의 빈 등록표를 채운다)
- Create: `stage/handout_viz.js`, `tests/test_handout_viz.py`
- Modify: `data/handout.yaml`(`viz`·`live` 추가), `stage/handout.py`(`_section`·`render_handout`), `stage/handout.css`(끝에 이어 붙임), `tests/test_handout_live.py`(자산 목록 확장), `tests/test_handout_browser.py`(브라우저 테스트 추가)

**Interfaces:**
- Consumes: Task 4 의 `window.handout.register/onReset/onLevel/level/reduceMotion`, Task 5 의 `CueCard.viz/.live`·`VIZ_ACTIONS` 검증·`_card_html(card, levels, viz_html)`.
- Produces: `stage.handout_viz`: `VIZ_ACTIONS = {"history-atlantic": {"pulse"}, "frequency-dial": {"dial-sweep", "dial-fm"}}`, `Viz(hero, tool)`, `render_viz(name, levels) -> Viz`(모르는 이름은 `KeyError`). 페이지에는 `<div class="viz" data-viz="<이름>">` 이 생기고, 장에는 `data-live='{"<턴>":["<동작>"]}'` 이 실린다. 시각화 요소는 `data-role`(`send`·`arrive`·`pulse`·`ping`·`freq`·`wave`·`bracket`·`label`·`out-f`·`out-l`·`dyn`·`fm`)로 찾는다 — 한 페이지에 같은 부품이 둘 이상 있어도 서로 안 섞이게 id 를 쓰지 않는다.
- 수준별 모양은 수준 **이름**으로 가른다: 초등은 숫자 없이 "천천히/빠르게 출렁여요", 중고등은 어림값(`약 3 m`), 일반은 어림값 + FM 100MHz 바로 맞추기, 전문가는 정확한 c(`299,792,458`)로 계산 + 3,000GHz 이상 경고.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_handout_viz.py`:

```python
"""교육자료 시각화 부품 — 수준별 글자, 모르는 이름, 글자 속 숫자의 근거."""

import pathlib
import re
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import load_cues
from stage.handout_data import load_cards
from stage.handout_viz import VIZ_ACTIONS, render_viz
from stage.levels import LEVEL_NAMES

ROOT = pathlib.Path(__file__).parent.parent
LEVELS = list(LEVEL_NAMES)


def test_부품마다_받을_수_있는_자동_동작이_정해져_있다():
    assert VIZ_ACTIONS == {
        "history-atlantic": frozenset({"pulse"}),
        "frequency-dial": frozenset({"dial-sweep", "dial-fm"}),
    }


def test_모르는_부품은_KeyError_다():
    with pytest.raises(KeyError):
        render_viz("없는부품", LEVELS)


def test_신호_보내기는_버튼과_수준별_도착_문구를_가진다():
    v = render_viz("history-atlantic", LEVELS)
    assert 'data-role="send"' in v.tool and 'data-role="arrive"' in v.tool and "hidden" in v.tool
    assert re.search(r'<p class="lv L0">받았어요! 전파가 넓은 바다를 건너갔어요\.</p>', v.tool)
    assert re.search(r'<p class="lv L2">받았어요 — 1901년 12월 12일, 약 3,500km', v.tool)
    assert 'data-role="pulse"' in v.hero and 'data-role="ping"' in v.hero and "개념도" in v.hero    # 지도가 아님을 밝힌다


def test_주파수_다이얼은_수준마다_눈금과_버튼이_다르다():
    v = render_viz("frequency-dial", LEVELS)
    assert 'type="range"' in v.tool and 'data-role="freq"' in v.tool
    assert re.search(r'class="tick lv L3 row2 hl"[^>]*>3,000GHz<', v.tool)                    # 전문가만
    assert re.search(r'class="tick lv L2 L3 row2 hl"[^>]*>FM 라디오 100MHz<', v.tool)         # 일반·전문가
    assert re.search(r'class="tick lv L0 "[^>]*>느리게<', v.tool)                              # 초등은 말로
    assert re.search(r'class="tool lv L2 L3"><button[^>]*data-role="fm"', v.tool)


def _글자_조각(markup):
    """`lv` 클래스가 달린 요소의 (클래스 목록, 글자) — 수준별로 보이는 글자다."""
    return re.findall(r'<(?:text|span|p)[^>]*class="([^"]*\blv\b[^"]*)"[^>]*>([^<]*)<', markup)


@pytest.mark.parametrize("name", sorted(VIZ_ACTIONS))
def test_초등에게_보이는_글자에는_숫자가_없다(name):
    """초등은 연도·수치·거리를 말하지 않는다(`data/levels.yaml` 초등.numbers) — 그림 글자도 같다."""
    v = render_viz(name, LEVELS)
    for classes, text in _글자_조각(v.hero + v.tool):
        if "L0" in classes.split():
            assert not re.search(r"\d", text), (classes, text)


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _수(text):
    return {m.group(0).replace(",", "").rstrip(".") for m in _NUM.finditer(text)}


def test_그림_글자_속_숫자도_대본이나_조사_사실에_있다():
    """카드의 숫자와 같은 규칙이다 — 그림 속 "약 3,500km"·"3,000GHz" 도 근거 없이 만들지 않는다."""
    cues = {c.id: c for c in load_cues()}
    for cid, card in load_cards(load_cues()).items():
        if not card.viz:
            continue
        cue = cues[cid]
        blob = cue.mc + cue.mc_after + "".join(t.ask + "".join(t.answers.values()) for t in cue.points)
        research = yaml.safe_load((ROOT / "data" / "cues-research" / f"{cid}.yaml").read_text(encoding="utf-8"))
        blob += "".join(f["claim"] for f in research["facts"])
        v = render_viz(card.viz, LEVELS)
        text = re.sub(r"<[^>]+>", " ", v.hero + v.tool)
        assert _수(text) <= _수(blob), f"{cid}/{card.viz}: 근거에 없는 숫자 {_수(text) - _수(blob)}"


def test_실제_카드에_시각화와_자동_동작이_지정돼_있다():
    cards = load_cards(load_cues())
    assert cards["02-history"].viz == "history-atlantic" and cards["02-history"].live == {"docent2": ("pulse",)}
    assert cards["03-theory"].viz == "frequency-dial"
    assert cards["03-theory"].live == {"docent1": ("dial-sweep",), "docent2": ("dial-fm",)}
```

`tests/test_handout_data.py` 의 `test_규약에_안_맞는_카드는_기동에서_거절한다` 파라미터 목록에 아래 두 줄을 더한다(첫째가 모르는 동작, 둘째가 없는 턴의 거절이다 — 별도 테스트는 없다).

```python
    (lambda d: {"c1": {**d["c1"], "viz": "frequency-dial", "live": {"docent0": ["pulse"]}}}, "모르는 동작"),
    (lambda d: {"c1": {**d["c1"], "viz": "frequency-dial", "live": {"docent9": ["dial-fm"]}}}, "이 큐에 없는 턴"),
```
(이 Task 에서 `VIZ_ACTIONS` 가 채워져 앞 Task 의 `"viz": "없는부품"` 케이스는 그대로 "모르는 시각화" 로 거절된다.)

`tests/test_handout_live.py` 의 자산 목록과 첫 두 테스트를 두 스크립트 모두에 걸게 고친다.

```python
ASSETS = ("handout.css", "handout_live.js", "handout_viz.js")
SCRIPTS = ("handout_live.js", "handout_viz.js")


def test_따라가기_스크립트는_아무것도_보내지_않는다():
    """읽기 전용 — 소켓 송신도 명령 문자열도 없다(서버도 받은 것을 버린다)."""
    for name in SCRIPTS:
        src = _src(name)
        assert ".send(" not in src, name
        assert "cmd" not in src, name
    assert "/ws/audience" in _src("handout_live.js")


def test_따라가기_스크립트는_textContent_로만_쓴다():
    for name in SCRIPTS:
        src = _src(name)
        for token in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            assert token not in src, (name, token)
```

`tests/test_handout_browser.py` 상단 import 에 `import re` 를 더하고, 끝에 브라우저 테스트를 더한다.

```python
_ATL = "document.querySelector('[data-viz=history-atlantic]')"
_DIAL = "document.querySelector('[data-viz=frequency-dial]')"


def _dial_value(chrome):
    return chrome.js(f"parseFloat({_DIAL}.querySelector('[data-role=freq]').value)")


def _arrive_js(root=_ATL):
    """보이는 도착 문구(고른 수준의 것)만 — 숨은 수준의 문구까지 합치면 어떤 수준에서도 참이 된다."""
    return f"[...{root}.querySelectorAll('[data-role=arrive] p')].filter({VISIBLE}).map(e => e.textContent).join('')"


def test_마지막_도슨트_설명에서_신호가_저절로_출발해_도착한다(chrome, live_cards):
    s = live_cards
    s.say("02-history", "여는 말", role="mc")
    s.say("02-history:docent", "마르코니가 만든 무선전신이에요.")
    chrome.wait_for(f"{_ATL}.querySelector('[data-role=pulse]').classList.contains('go')", timeout=3)
    chrome.wait_for(f"!{_ATL}.querySelector('[data-role=arrive]').hidden", timeout=6)
    assert "1901년 12월 12일" in chrome.js(_arrive_js())
    assert chrome.errors() == []


def test_도착_문구는_수준을_바꾸면_그_수준의_말이_된다(chrome, live_cards):
    s = live_cards
    s.say("02-history:docent", "마르코니가 만든 무선전신이에요.")
    chrome.wait_for(f"!{_ATL}.querySelector('[data-role=arrive]').hidden", timeout=6)
    chrome.js("document.querySelector('label[for=lvr0]').click()")            # 초등
    chrome.wait_for(f"{_arrive_js()}.includes('넓은 바다')")
    assert "1901" not in chrome.js(_arrive_js())


def test_큐를_다시_시작하면_신호_보내기가_처음으로_돌아간다(chrome, live_cards):
    s = live_cards
    s.say("02-history:docent", "마르코니가 만든 무선전신이에요.")
    chrome.wait_for(f"!{_ATL}.querySelector('[data-role=arrive]').hidden", timeout=6)
    s.say("02-history", "여는 말", role="mc")                                  # r — 이 큐 다시
    chrome.wait_for(f"{_ATL}.querySelector('[data-role=arrive]').hidden")
    assert chrome.js(f"{_ATL}.querySelector('[data-role=send]').textContent") == "신호 보내 보기"


def test_주파수_대목에서_다이얼이_저절로_올라가고_파장_대목에서_FM_100MHz_에_선다(chrome, live_cards):
    s = live_cards
    s.say("03-theory", "여는 말", role="mc")
    chrome.wait_for(f"{_DIAL} && parseFloat({_DIAL}.querySelector('[data-role=freq]').value) === 3")   # 큐 시작 = 낮은 쪽
    s.say("03-theory:pt1:docent", "주파수예요.")                                # 짧은 문장 = 어림 1.2초 → 스윕 약 1초
    chrome.wait_for(f"parseFloat({_DIAL}.querySelector('[data-role=freq]').value) > 12.5", timeout=4)
    s.say("03-theory:docent", "파장이에요.")
    chrome.wait_for(f"Math.abs(parseFloat({_DIAL}.querySelector('[data-role=freq]').value) - 8) < 0.02", timeout=5)
    assert "약 3미터" in chrome.js(f"{_DIAL}.querySelector('[data-role=dyn]').textContent")
    assert chrome.errors() == []


def test_관람객이_다이얼을_직접_돌리면_자동_스윕이_멈춘다(chrome, live_cards):
    s = live_cards
    s.say("03-theory", "여는 말", role="mc")
    chrome.wait_for(f"{_DIAL} && parseFloat({_DIAL}.querySelector('[data-role=freq]').value) === 3")
    s.say("03-theory:pt1:docent", "가" * 60)                                    # 어림 15초 — 천천히 올라간다
    chrome.wait_for(f"parseFloat({_DIAL}.querySelector('[data-role=freq]').value) > 3.001", timeout=4)
    chrome.js(f"(() => {{ const f = {_DIAL}.querySelector('[data-role=freq]'); f.value = 5; f.dispatchEvent(new Event('input')); }})()")
    time.sleep(0.6)
    assert _dial_value(chrome) == 5.0


@pytest.mark.parametrize("라벨, 포함, 불포함", [
    ("lvr0", ["빠르게 출렁여요", "짧아요"], []),                              # 초등: 말로(숫자 없음 — 아래에서 따로 본다)
    ("lvr1", ["주파수 100 MHz", "파장 약 3 m"], ["=", "λ"]),                 # 중고등: 어림값
    ("lvr2", ["주파수 100 MHz", "파장 = 약 3 m"], ["λ"]),                    # 일반: 어림값 + 식
    ("lvr3", ["f = 100 MHz", "λ = c ÷ f = 2.998 m"], ["약"]),               # 전문가: 정확한 c
])
def test_다이얼_읽기값은_수준마다_다른_모양이다(chrome, live_cards, 라벨, 포함, 불포함):
    chrome.js(f"document.querySelector('label[for={라벨}]').click()")
    chrome.js(f"(() => {{ const f = {_DIAL}.querySelector('[data-role=freq]'); f.value = 8; f.dispatchEvent(new Event('input')); }})()")
    out = chrome.js(f"{_DIAL}.querySelector('[data-role=out-f]').textContent + ' | ' + {_DIAL}.querySelector('[data-role=out-l]').textContent")
    for want in 포함:
        assert want in out, out
    for nope in 불포함:
        assert nope not in out, out
    if 라벨 == "lvr0":
        assert not re.search(r"\d", out), out                             # 초등은 숫자가 없다


def test_전문가는_3000GHz_이상에서_전파_범위_밖이라고_알린다(chrome, live_cards):
    chrome.js("document.querySelector('label[for=lvr3]').click()")
    chrome.js(f"(() => {{ const f = {_DIAL}.querySelector('[data-role=freq]'); f.value = 12.6; f.dispatchEvent(new Event('input')); }})()")
    assert "3,000GHz 이상" in chrome.js(f"{_DIAL}.querySelector('[data-role=dyn]').textContent")
    chrome.js(f"(() => {{ const f = {_DIAL}.querySelector('[data-role=freq]'); f.value = 12.4; f.dispatchEvent(new Event('input')); }})()")
    assert "3,000GHz 이상" not in chrome.js(f"{_DIAL}.querySelector('[data-role=dyn]').textContent")


def test_모션_줄이기_설정이면_신호가_움직임_없이_바로_도착한다(chrome):
    chrome.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    try:
        from stage.cues import load_cues
        from stage.handout_data import load_cards

        with served(cards=load_cards(load_cues())) as s:
            _open(chrome, s.url("/handout"))
            s.say("02-history:docent", "마르코니가 만든 무선전신이에요.")
            chrome.wait_for(f"!{_ATL}.querySelector('[data-role=arrive]').hidden", timeout=2)
            assert chrome.js(f"{_ATL}.querySelector('[data-role=pulse]').classList.contains('go')") is False
    finally:
        chrome.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "no-preference"}])


def test_인쇄에서는_인터랙션이_빠지고_그림만_남는다(chrome, live_cards):
    chrome.call("Emulation.setEmulatedMedia", media="print")
    try:
        assert chrome.js("[...document.querySelectorAll('.interact')].every(e => getComputedStyle(e).display === 'none')") is True
        assert chrome.js(f"{_DIAL}.querySelector('svg') !== null") is True
    finally:
        chrome.call("Emulation.setEmulatedMedia", media="screen")
```

Run: `.venv/bin/python -m pytest tests/test_handout_viz.py tests/test_handout_live.py -v`
Expected: `ImportError: cannot import name 'render_viz'` / `FileNotFoundError: handout_viz.js` 로 FAIL.

- [ ] **Step 2: 시각화 부품(Python)을 구현한다**

`stage/handout_viz.py` 를 통째로 아래로 바꾼다.

```python
"""교육자료 시각화 부품 — 이름으로 부른다(`data/handout.yaml` 의 `viz`). 그림(SVG)과 도구(버튼·다이얼) HTML 을 만들고,
자동 동작의 이름(`live`)은 `stage/handout_viz.js` 가 등록한 것과 짝이다.

`VIZ_ACTIONS[이름]` 은 그 부품이 받을 수 있는 자동 동작 이름의 집합이다 — 데이터가 모르는 이름을 쓰면 기동에서
거절한다(오타가 조용히 "아무 일도 안 일어남" 이 되지 않게).

모두 **인라인 SVG/CSS** 다 — 관람객 기기가 인터넷 없는 전용 공유기에 붙어도 그려져야 한다. 수준마다 달라지는 글자는
수준 **이름**으로 가른다(초등은 숫자 없이, 전문가는 정확한 값으로). 글자 속 숫자는 대본이나 조사 사실에 있는 것만
쓴다(`tests/test_handout_viz.py::test_그림_글자_속_숫자도_대본이나_조사_사실에_있다`). 한 페이지에 같은 부품이 둘 이상
있어도 섞이지 않게 id 를 쓰지 않고 `data-role` 로 찾는다.
"""

import html
import math
from dataclasses import dataclass

VIZ_ACTIONS: dict[str, frozenset[str]] = {
    "history-atlantic": frozenset({"pulse"}),
    "frequency-dial": frozenset({"dial-sweep", "dial-fm"}),
}

EL, MID, GEN, EXP = ("초등",), ("중고등",), ("일반",), ("전문가",)
NUM = ("중고등", "일반", "전문가")            # 숫자를 보여 주는 수준
GEN_EXP = ("일반", "전문가")


@dataclass(frozen=True)
class Viz:
    hero: str    # 그림(SVG)
    tool: str    # 버튼·다이얼 같은 도구(화면에서만 — 인쇄에서는 `.interact` 로 빠진다)


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _cls(levels: list[str], names: tuple[str, ...]) -> str:
    """이 수준들에서만 보이게 하는 클래스(`L<번호>`). 페이지의 수준 목록에 없는 이름은 건너뛴다."""
    return " ".join(f"L{i}" for i, lv in enumerate(levels) if lv in names)


def _t(levels, texts: dict, x, y, extra: str = "", cls: str = "") -> str:
    """수준마다 다른 SVG 글자. `texts` 의 키는 수준 이름의 튜플이다."""
    out = []
    for names, text in texts.items():
        c = _cls(levels, names)
        if c:
            out.append(f'<text class="lv {c} {cls}" x="{x}" y="{y}" style="--d:inline" {extra}>{_esc(text)}</text>')
    return "".join(out)


def _sine(x0: float, x1: float, cy: float, amp: float, period: float) -> str:
    n = int((x1 - x0) * 2)
    pts = []
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        pts.append(f"{x:.1f},{cy - amp * math.sin(2 * math.pi * (x - x0) / period):.1f}")
    return "M" + " L".join(pts)


# ── 02 신호 보내기 ────────────────────────────────────────────────────

_ARRIVE = {
    EL: "받았어요! 전파가 넓은 바다를 건너갔어요.",
    MID: "수신! 대서양 건너 약 3,500km에서 모스 부호를 받았다고 발표했어요.",
    GEN: "받았어요 — 1901년 12월 12일, 약 3,500km 떨어진 뉴펀들랜드에서요.",
    EXP: "수신 보고 — 약 3,500km. 이 수신은 지금도 기술적 논쟁의 대상이다.",
}


def _atlantic(levels: list[str]) -> Viz:
    ox, oy, dx, dy = 78, 132, 600, 104
    ripples = ""
    for r in (20, 34, 48):
        a = math.radians(48)
        x1, y1 = ox + r * math.cos(-a), oy + r * math.sin(-a)
        x2, y2 = ox + r * math.cos(a), oy + r * math.sin(a)
        ripples += (f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 0 1 {x2:.1f} {y2:.1f}" class="rip" '
                    f'style="animation-delay:{(r - 20) / 14 * 0.12:.2f}s"/>')
    sea = _sine(0, 680, 186, 5, 170) + " L680,210 L0,210 Z"
    labels = (
        _t(levels, {EL: "여기서 보내면", MID: "송신", GEN: "폴듀 (영국)", EXP: "폴듀 (영국 콘월)"}, ox - 30, oy - 52)
        + _t(levels, {EL: "저기서 받았어요", MID: "수신", GEN: "뉴펀들랜드", EXP: "세인트존스 (뉴펀들랜드)"},
             dx + 30, dy + 36, 'text-anchor="end"')
        + _t(levels, {EL: "넓은 바다 건너편까지", MID: "대서양 건너 약 3,500km", GEN: "약 3,500km · 1901년 12월 12일",
                      EXP: "약 3,500km (2,200마일)"}, 339, 42, 'text-anchor="middle"', cls="cap")
    )
    hero = (
        '<svg data-role="svg" class="hero-svg" viewBox="0 0 680 210" role="img" '
        'aria-label="영국에서 대서양 건너편으로 신호를 보내는 개념도">'
        f'<path d="{sea}" class="sea"/><path d="M{ox} {oy} Q339 8 {dx} {dy}" class="route"/>{ripples}'
        f'<circle data-role="ping" class="ping" cx="{dx}" cy="{dy}" r="9"/>'
        f'<circle data-role="pulse" class="pulse" cx="{ox}" cy="{oy}" r="7"/>'
        f'<circle cx="{ox}" cy="{oy}" r="8" class="node"/><circle cx="{dx}" cy="{dy}" r="8" class="node end"/>'
        f'{labels}<text x="676" y="204" text-anchor="end" class="note">개념도 — 실제 지도·축척이 아니에요</text></svg>'
    )
    arrive = "".join(f'<p class="lv {c}">{_esc(t)}</p>' for names, t in _ARRIVE.items() if (c := _cls(levels, names)))
    tool = (
        '<div class="tool interact"><button type="button" class="btn" data-role="send">신호 보내 보기</button>'
        f'<div class="arrive" data-role="arrive" hidden aria-live="polite">{arrive}</div></div>'
    )
    return Viz(hero, tool)


# ── 03 주파수 다이얼 ──────────────────────────────────────────────────


def _tick(levels, label: str, pct: float, names: tuple[str, ...], extra: str = "") -> str:
    c = _cls(levels, names)
    return f'<span class="tick lv {c} {extra}" style="left:{pct}%;--d:block">{_esc(label)}</span>' if c else ""


def _theory(levels: list[str]) -> Viz:
    x0, x1 = 8, 668
    low, high = _sine(x0, x1, 62, 22, 330), _sine(x0, x1, 170, 22, 82.5)
    hero = (
        '<svg class="hero-svg" viewBox="0 0 680 228" role="img" '
        'aria-label="주파수가 낮으면 파장이 길고, 높으면 파장이 짧다는 비교 그림">'
        + _t(levels, {EL: "천천히 출렁여요", NUM: "주파수 낮음"}, x0, 20, cls="cap")
        + f'<path d="{low}" class="wave a"/><path d="M{x0} 94 v8 M{x0} 98 H{x0 + 330} M{x0 + 330} 94 v8" class="br"/>'
        + _t(levels, {EL: "물결 하나 — 길어요", NUM: "파장 길다"}, x0 + 342, 103)
        + _t(levels, {EL: "빠르게 출렁여요", NUM: "주파수 높음"}, x0, 134, cls="cap")
        + f'<path d="{high}" class="wave b"/><path d="M{x0} 206 v8 M{x0} 210 H{x0 + 82.5} M{x0 + 82.5} 206 v8" class="br b"/>'
        + _t(levels, {EL: "물결 하나 — 짧아요", NUM: "파장 짧다"}, x0 + 94, 215)
        + "</svg>"
    )
    ticks = (
        _tick(levels, "느리게", 0, EL) + _tick(levels, "빠르게", 100, EL)
        + _tick(levels, "1kHz", 0, NUM) + _tick(levels, "1MHz", 30, NUM)
        + _tick(levels, "1GHz", 60, NUM) + _tick(levels, "1THz", 90, NUM)
        + _tick(levels, "FM 라디오 100MHz", 50, GEN_EXP, "row2 hl") + _tick(levels, "3,000GHz", 94.77, EXP, "row2 hl")
    )
    young, rest = _cls(levels, EL), _cls(levels, NUM)
    heading = (
        (f'<span class="lv {young}">다이얼을 돌려 보세요. 물결이 어떻게 바뀔까요?</span>' if young else "")
        + (f'<span class="lv {rest}">주파수 다이얼 — 돌려서 파장을 확인해 보세요</span>' if rest else "")
    )
    note = (
        (f'<span class="lv {young}">그림은 느낌만 보여 줘요.</span>' if young else "")
        + (f'<span class="lv {rest}">그림의 물결 수는 느낌을 보여 주려고 줄여 그렸어요(실제 비율 아님). '
           '숫자는 파장 = 빛의 속도 ÷ 주파수로 계산했어요.</span>' if rest else "")
    )
    fm_cls = _cls(levels, GEN_EXP)
    fm = (f'<div class="tool lv {fm_cls}"><button type="button" class="btn ghost" data-role="fm">'
          'FM 라디오 100MHz 로 맞추기</button></div>') if fm_cls else ""
    tool = (
        f'<div class="dialbox interact"><p class="dh">{heading}</p>'
        '<svg class="hero-svg dw" viewBox="0 0 680 132" role="img" aria-label="다이얼 값에 따라 달라지는 물결 그림">'
        '<path data-role="wave" class="wave"/><path data-role="bracket" class="br"/><text data-role="label" x="0" y="0"></text></svg>'
        '<input class="freq" data-role="freq" type="range" min="3" max="13" step="0.01" value="8" aria-label="주파수 다이얼">'
        f'<div class="ticks">{ticks}</div>'
        '<p class="out" aria-live="polite"><span data-role="out-f"></span><span data-role="out-l"></span></p>'
        f'<p class="dyn" data-role="dyn" role="status"></p>{fm}<p class="dnote">{note}</p></div>'
    )
    return Viz(hero, tool)


_PARTS = {"history-atlantic": _atlantic, "frequency-dial": _theory}


def render_viz(name: str, levels: list[str]) -> Viz:
    """부품 이름 → 그림과 도구. 모르는 이름은 KeyError(`load_cards` 가 기동에서 이미 거절한다)."""
    return _PARTS[name](levels)
```

- [ ] **Step 3: 렌더러·데이터·CSS·스크립트를 잇는다**

`data/handout.yaml` 의 두 큐에 각각 `turns:` 블록 바로 아래 줄을 더한다. 먼저 `02-history`(마지막 설명 = 마르코니에서 신호가 출발) —

```yaml
  viz: history-atlantic
  live:
    docent2: [pulse]            # 마지막 도슨트 설명(마르코니) — 신호가 저절로 출발한다
```
다음 `03-theory` —

```yaml
  viz: frequency-dial
  live:
    docent1: [dial-sweep]       # 주파수를 설명하는 동안 다이얼이 낮은 쪽에서 높은 쪽으로
    docent2: [dial-fm]          # 파장을 설명할 때 FM 라디오 100MHz 에 선다
```

`stage/handout.py` 를 고친다. import 에 `import json` 과 `from stage.handout_viz import render_viz` 를 더하고, `_viz_html` 을 새로 두고 `_section` 을 아래로 **통째로** 바꾼다.

```python
def _viz_html(card, levels: list[str]) -> str:
    if not card.viz:
        return ""
    v = render_viz(card.viz, levels)
    return f'<div class="viz" data-viz="{_esc(card.viz)}"><figure class="hero">{v.hero}</figure>{v.tool}</div>'


def _section(number: int, cue: Cue, levels: list[str], card=None) -> str:
    chats = "".join(
        f'<div class="chat lv L{k}">{_chat_rows(cue, lv)}</div>' for k, lv in enumerate(levels)
    )
    live_attr = ""
    if card is None:
        # 카드가 없는 큐 — 말풍선 대화가 펼쳐져 있다(접어 두면 이 장에 읽을 것이 없다).
        inner = f'<div class="talk plain">{chats}</div>'
    else:
        src = "".join(
            f'<p class="src lv L{k}">근거 · {_esc(card.levels[lv].sources)}</p>'
            for k, lv in enumerate(levels) if card.levels[lv].sources
        )
        inner = (
            f"{_card_html(card, levels, _viz_html(card, levels))}"
            f'<details class="talk"><summary>해설 전문 보기 — 사회자와 도슨트의 대화</summary>{chats}</details>{src}'
        )
        if card.live:   # 어느 대목에서 무엇을 움직일지 — `handout_live.js` 가 읽는다
            live_attr = f' data-live="{_esc(json.dumps(card.live, ensure_ascii=False))}"'
    return (
        f'<section class="sheet" id="{_esc(cue.id)}" data-points="{len(cue.points)}"{live_attr}>'
        f'<header class="sheet-h"><span class="no">{number:02d}</span><h2>{_esc(cue.title)}</h2>'
        '<span class="livebadge">● 지금 이야기 중</span></header>'
        f'<div class="ruler" aria-hidden="true"></div>{inner}</section>'
    )
```
`render_handout` 의 마지막 반환에서 스크립트 조각을 둘로 늘린다.

```python
        f"{'<script>' + _asset('handout_live.js') + '</script>' if live else ''}"
        f"{'<script>' + _asset('handout_viz.js') + '</script>' if live else ''}"
```

`stage/handout.css` 끝에 이어 붙인다.

```css
.viz{margin:8px 0 6px}
.hero{margin:8px 0 6px}
.hero-svg{display:block;width:100%;height:auto}
.hero-svg text{font-size:15px;fill:var(--ink)}
.hero-svg text.cap{font-weight:700;font-size:15px}
.hero-svg text.note{font-size:11px;fill:var(--muted)}
.hero-svg .sea{fill:#DCEDF5}
.hero-svg .route{fill:none;stroke:var(--sig);stroke-width:2.5;stroke-dasharray:3 7;stroke-linecap:round}
.hero-svg .rip{fill:none;stroke:var(--sig);stroke-width:2;opacity:.7}
.hero-svg .node{fill:var(--ink);stroke:#fff;stroke-width:3}
.hero-svg .node.end{fill:var(--amber)}
.hero-svg .wave{fill:none;stroke-width:3.2;stroke-linejoin:round}
.hero-svg .wave.a{stroke:var(--sig)} .hero-svg .wave.b{stroke:var(--amber)}
.hero-svg .br{fill:none;stroke:var(--sig);stroke-width:2}
.hero-svg .br.b{stroke:var(--amber)}
.hero-svg .pulse{fill:var(--sig);stroke:#fff;stroke-width:2.5;opacity:0}
.hero-svg .pulse.go{opacity:1}
.hero-svg .ping{fill:none;stroke:var(--amber);stroke-width:3;opacity:0;transform-box:fill-box;transform-origin:center}
.hero-svg .ping.on{animation:ping 1.1s ease-out 1}
.hero-svg.send .rip{animation:rip 1.2s ease-out 1}
@keyframes ping{0%{opacity:.9;transform:scale(1)}100%{opacity:0;transform:scale(3.4)}}
@keyframes rip{0%{opacity:0}35%{opacity:1}100%{opacity:.7}}
@media (prefers-reduced-motion:reduce){.hero-svg .ping.on,.hero-svg.send .rip{animation:none}.hero-svg .ping.on{opacity:.9}}
.tool{display:flex;gap:6px 16px;align-items:center;flex-wrap:wrap;margin:8px 0 10px}
.btn{font:inherit;font-weight:700;font-size:15px;padding:9px 20px;min-height:44px;border-radius:999px;border:2px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer}
.btn.ghost{background:#fff;color:var(--ink)}
.btn:disabled{opacity:.55;cursor:default}
.btn:focus-visible,.freq:focus-visible{outline:3px solid #7FD3F5;outline-offset:3px}
.arrive p{margin:0;font-weight:700;font-size:16px}
.dialbox{margin:12px 0 6px;padding:14px 16px 12px;background:var(--mist);border-top:3px solid var(--ink)}
.dh{margin:0 0 4px;font-weight:800;font-size:17px}
.dw{margin:0 0 2px}
.dw text{font-size:15px;fill:var(--ink);font-weight:700}
.freq{-webkit-appearance:none;appearance:none;display:block;width:100%;height:44px;margin:0;background:transparent;cursor:pointer}
.freq::-webkit-slider-runnable-track{height:10px;border-radius:5px;background:linear-gradient(90deg,var(--sig),var(--amber))}
.freq::-moz-range-track{height:10px;border-radius:5px;background:linear-gradient(90deg,var(--sig),var(--amber))}
.freq::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:40px;margin-top:-15px;border-radius:7px;background:var(--ink);border:3px solid #fff;box-shadow:0 0 0 1.5px var(--ink)}
.freq::-moz-range-thumb{width:16px;height:34px;border-radius:7px;background:var(--ink);border:3px solid #fff;box-shadow:0 0 0 1.5px var(--ink)}
.ticks{position:relative;height:50px;margin:0 14px}
.tick{position:absolute;top:0;transform:translateX(-50%);font-size:12px;color:var(--muted);white-space:nowrap;text-align:center;line-height:1.3}
.tick::before{content:"";display:block;width:1px;height:6px;background:var(--ink);margin:0 auto 2px}
.tick.row2{top:24px}
.tick.hl{color:var(--ink);font-weight:700}
.out{display:flex;flex-wrap:wrap;gap:2px 28px;margin:2px 0 0;font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}
.dyn{margin:2px 0 0;min-height:1.7em;font-size:15px;font-weight:700;color:var(--amber)}
.dnote{margin:4px 0 0;font-size:13px;color:var(--muted)}
@media (max-width:640px){
  .hero-svg text,.hero-svg text.cap{font-size:23px}
  .hero-svg text.note{font-size:15px}
  .tick{font-size:11px}
  .out{font-size:18px}
}
@media print{.interact{display:none !important}}
```

`stage/handout_viz.js`:

```javascript
// 교육자료 시각화 부품의 자동 동작 — `stage/handout_live.js` 가 연 확장 지점(register·onReset·onLevel)에 붙는다.
// 부품은 `data-viz` 로 찾고 안쪽 요소는 `data-role` 로 찾는다(id 를 쓰지 않아 한 페이지에 같은 부품이 둘이어도 섞이지 않는다).
// 글자는 textContent 로만 쓰고, 소켓으로 아무것도 보내지 않는다.
(function () {
  'use strict';
  var H = window.handout;
  if (!H) return;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var MODE = { '초등': 'q', '중고등': 'n2', '일반': 'n3', '전문가': 'x' };   // 수준 이름 → 읽기값의 모양
  var parts = {};                                                            // 장 id → { atlantic, dial }

  // ── 02 신호 보내기 ───────────────────────────────────────────────
  function atlantic(root) {
    var svg = $('[data-role=svg]', root), pulse = $('[data-role=pulse]', root), ping = $('[data-role=ping]', root),
        send = $('[data-role=send]', root), box = $('[data-role=arrive]', root), run = 0;
    var P0 = [78, 132], C = [339, 8], P1 = [600, 104];
    function at(t) {
      var u = 1 - t;
      return [u * u * P0[0] + 2 * u * t * C[0] + t * t * P1[0], u * u * P0[1] + 2 * u * t * C[1] + t * t * P1[1]];
    }
    function reset() {
      run++;
      box.hidden = true; send.textContent = '신호 보내 보기'; send.disabled = false;
      ping.classList.remove('on'); pulse.classList.remove('go'); svg.classList.remove('send');
    }
    function arrived() {
      box.hidden = false;
      ping.classList.remove('on'); void ping.getBoundingClientRect(); ping.classList.add('on');
      send.textContent = '다시 보내기'; send.disabled = false;
    }
    function play() {
      var my = ++run;
      send.disabled = true; box.hidden = true; ping.classList.remove('on');
      svg.classList.remove('send'); void svg.getBoundingClientRect(); svg.classList.add('send');
      if (H.reduceMotion) { arrived(); return; }          // 모션 줄이기 — 움직임 없이 결과만
      pulse.classList.add('go');
      var t0 = performance.now(), D = 2200;
      (function step(now) {
        if (my !== run) return;
        var k = Math.min(1, (now - t0) / D), e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2, p = at(e);
        pulse.setAttribute('cx', p[0]); pulse.setAttribute('cy', p[1]);
        if (k < 1) requestAnimationFrame(step); else { pulse.classList.remove('go'); arrived(); }
      })(t0);
    }
    send.addEventListener('click', play);
    return { play: play, reset: reset };
  }

  // ── 03 주파수 다이얼 ─────────────────────────────────────────────
  function dial(root) {
    var fr = $('[data-role=freq]', root), W = $('[data-role=wave]', root), B = $('[data-role=bracket]', root),
        T = $('[data-role=label]', root), outF = $('[data-role=out-f]', root), outL = $('[data-role=out-l]', root),
        dyn = $('[data-role=dyn]', root), fm = $('[data-role=fm]', root);
    var X0 = 8, X1 = 668, CY = 58, AMP = 30, run = 0;
    var sig = function (x, n) { return parseFloat(x.toPrecision(n)); };
    function fmtF(f) {
      var U = ['Hz', 'kHz', 'MHz', 'GHz', 'THz'], k = Math.min(4, Math.floor(Math.log10(f) / 3 + 1e-9)), m = sig(f / Math.pow(10, 3 * k), 3);
      if (m >= 1000 && k < 4) { k++; m = sig(f / Math.pow(10, 3 * k), 3); }
      return m + ' ' + U[k];
    }
    function fmtL(l, n) {
      var U = [['km', 1e3], ['m', 1], ['cm', 1e-2], ['mm', 1e-3], ['µm', 1e-6]], u = U[U.length - 1];
      for (var i = 0; i < U.length; i++) { if (l >= U[i][1] * 0.9995) { u = U[i]; break; } }
      return sig(l / u[1], n) + ' ' + u[0];
    }
    var bucket = function (v) { return v < 5.5 ? 0 : v < 8 ? 1 : v < 10.5 ? 2 : 3; };
    function draw(v, mode) {
      // 물결 수는 느낌을 보여 주려고 줄여 그린다(실제 비율 아님 — 화면에도 그렇게 적었다).
      var N = 1.5 + 12.5 * (v - 3) / 10, per = (X1 - X0) / N, steps = Math.max(240, Math.round(N * 40)), pts = [];
      for (var i = 0; i <= steps; i++) {
        var x = X0 + (X1 - X0) * i / steps;
        pts.push(x.toFixed(1) + ',' + (CY - AMP * Math.sin(2 * Math.PI * (x - X0) / per)).toFixed(1));
      }
      var t = (v - 3) / 10, c0 = [11, 127, 181], c1 = [185, 111, 0],
          col = 'rgb(' + c0.map(function (a, j) { return Math.round(a + (c1[j] - a) * t); }).join(',') + ')';
      W.setAttribute('d', 'M' + pts.join(' L')); W.style.stroke = col;
      B.setAttribute('d', 'M' + X0 + ' 108 v8 M' + X0 + ' 112 H' + (X0 + per) + ' M' + (X0 + per) + ' 108 v8'); B.style.stroke = col;
      T.setAttribute('x', X0 + per + 12); T.setAttribute('y', 117);
      T.textContent = mode === 'q' ? '물결 하나' : '파장';
    }
    function render() {
      var mode = MODE[H.level()] || 'n3', v = parseFloat(fr.value), f = Math.pow(10, v),
          L = (mode === 'x' ? 299792458 : 3e8) / f, note = '';
      draw(v, mode);
      if (mode === 'q') {
        var b = bucket(v);
        outF.textContent = '물결이 ' + ['아주 천천히', '천천히', '빠르게', '아주 빠르게'][b] + ' 출렁여요';
        outL.textContent = '물결 하나가 ' + ['아주 길어요', '길어요', '짧아요', '아주 짧아요'][b];
        fr.setAttribute('aria-valuetext', outF.textContent);
      } else {
        fr.setAttribute('aria-valuetext', fmtF(f));
        if (mode === 'n2') { outF.textContent = '주파수 ' + fmtF(f); outL.textContent = '파장 약 ' + fmtL(L, 2); }
        if (mode === 'n3') { outF.textContent = '주파수 ' + fmtF(f); outL.textContent = '파장 = 약 ' + fmtL(L, 3); }
        if (mode === 'x') { outF.textContent = 'f = ' + fmtF(f); outL.textContent = 'λ = c ÷ f = ' + fmtL(L, 4); }
      }
      if (mode === 'n3' && Math.abs(v - 8) < 0.025) note = '100메가헤르츠 FM 라디오 전파는 파장이 약 3미터예요.';
      if (mode === 'x' && Math.abs(v - 8) < 0.025) note = 'FM 라디오 100MHz 근처다. 파장은 약 3m다.';
      if (mode === 'x' && f >= 3e12) note = '3,000GHz 이상이다 — ITU 전파규칙이 말하는 ‘전파’의 범위(3,000GHz 미만) 밖이다.';
      dyn.textContent = note;
    }
    function setV(v) { fr.value = v; render(); }
    function to(v1, ms) {
      var my = ++run, v0 = parseFloat(fr.value);
      if (H.reduceMotion || ms <= 0 || v0 === v1) { setV(v1); return; }
      var t0 = performance.now();
      (function step(now) {
        if (my !== run) return;
        var k = Math.min(1, (now - t0) / ms), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        setV(v0 + (v1 - v0) * e);
        if (k < 1) requestAnimationFrame(step);
      })(t0);
    }
    fr.addEventListener('input', function () { run++; render(); });          // 직접 돌리면 자동 동작을 멈춘다
    if (fm) fm.addEventListener('click', function () { run++; setV(8); });
    H.onLevel(render);
    render();
    return {
      sweep: function (ms) { to(13, ms * 0.9); },
      fm: function () { to(8, 2400); },
      reset: function () { run++; setV(3); }
    };
  }

  $$('[data-viz]').forEach(function (root) {
    var sh = root.closest('.sheet');
    if (!sh) return;
    var p = parts[sh.id] || (parts[sh.id] = {}), kind = root.getAttribute('data-viz');
    if (kind === 'history-atlantic') p.atlantic = atlantic(root);
    if (kind === 'frequency-dial') p.dial = dial(root);
  });
  H.register('pulse', function (sh) { var p = parts[sh.id]; if (p && p.atlantic) p.atlantic.play(); });
  H.register('dial-sweep', function (sh, ms) { var p = parts[sh.id]; if (p && p.dial) p.dial.sweep(ms); });
  H.register('dial-fm', function (sh) { var p = parts[sh.id]; if (p && p.dial) p.dial.fm(); });
  // 큐가 (다시) 시작되거나(장) 공연이 끝나면(null) 처음 모습으로 — 이전 관람객이 남긴 도착 문구·다이얼 값을 치운다.
  H.onReset(function (sh) {
    Object.keys(parts).forEach(function (id) {
      if (sh && sh.id !== id) return;
      var p = parts[id];
      if (p.atlantic) p.atlantic.reset();
      if (p.dial) p.dial.reset();
    });
  });
})();
```

- [ ] **Step 4: 통과를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_handout_viz.py tests/test_handout_data.py tests/test_handout_live.py tests/test_handout_browser.py tests/test_audience.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 눈으로 확인하고 커밋한다**

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
git add stage/handout_viz.py stage/handout_viz.js stage/handout.py stage/handout.css data/handout.yaml \
  tests/test_handout_viz.py tests/test_handout_data.py tests/test_handout_live.py tests/test_handout_browser.py
git commit -m "feat(stage): 교육자료 시각화 — 도슨트가 말하는 대목에서 신호 보내기·주파수 다이얼이 저절로 움직인다" \
  -m "부품은 코드(stage/handout_viz.py·.js), 어느 대목에서 무엇을 움직일지는 데이터(handout.yaml 의 viz·live)다. 모르는 부품·동작·턴은 기동에서 거절한다. 수준마다 글자가 다르다(초등은 숫자 없이, 전문가는 정확한 c 와 3,000GHz 경고). 직접 돌리면 자동 동작이 멈추고, 큐 다시·공연 종료에서 처음 모습으로 돌아간다. 모션 줄이기 설정이면 움직임 없이 결과만. 인쇄에서는 도구가 빠지고 그림만 남는다." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 관람객 전용 읽기 전용 리스너 (선택 — **사용자 승인 필요**, 기본 꺼짐)

> **왜 필요한가.** 관람객 폰이 `/handout` 에 닿으려면 지금은 대시보드를 `REACHY_DASHBOARD_HOST=0.0.0.0` 에 열어야 하고,
> 그러면 **인증 없는 조정실(`/`·`/ws`, 시연을 멈추고 건너뛸 수 있음)도 같은 주소로 열린다**(`docs/two-robot-offline-test.md`
> 의 기존 경고). 이 Task 는 관람객 경로(`/audience`·`/handout`·`/ws/audience`)만 다른 포트로 여는 **두 번째 리스너**를
> 더한다. 환경변수를 안 주면 아무것도 안 띄운다(위험한 쪽을 기본으로 두지 않는다). **승인하지 않으면 이 Task 만 건너뛴다**
> — Task 1~6·8 은 독립적이고, 그 경우 폰 접근은 "전용 공유기 + 조정실도 열림" 의 기존 위험을 감수하는 운영으로 남는다.

**Files:**
- Modify: `stage/dashboard.py`(`AUDIENCE_ONLY_PATHS`·`DashboardServer.__init__`·`process_request`·`start_dashboard`), `stage/__main__.py`(환경변수·두 번째 리스너·종료·머리 docstring)
- Modify: `tests/test_audience.py`, `tests/test_stage_main.py`

**Interfaces:**
- Consumes: Task 5 의 `DashboardServer(…, cards=…)`·`start_dashboard`.
- Produces: `DashboardServer(…, audience_only: bool = False)` — `True` 면 `/audience`·`/handout`·`/ws/audience` 외의 모든 경로(`/`·`/index.html`·`/ws`)가 **404** 다(조정실의 존재도 알리지 않는다). `start_dashboard(…, audience_only=False)` 키워드 인자(앞의 위치 인자·기존 호출부는 그대로). `python -m stage` 는 `REACHY_AUDIENCE_HOST`(비어 있으면 안 띄움)·`REACHY_AUDIENCE_PORT`(기본 8779)로 두 번째 리스너를 띄운다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_audience.py` 맨 아래에:

```python
# ── 관람객 전용 읽기 전용 리스너(조정실을 열지 않는다) ──────────────────


@pytest.fixture
def aud_only(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>조정실</title>", encoding="utf-8")
    hub, d, warned, dispatched = DashboardHub(), 가짜감독(), [], []
    ds = DashboardServer(hub, d, dispatch=lambda *a, **kw: dispatched.append(a), page=page, interval=0.05,
                         warn=warned.append, audience_only=True)
    with _served(ds) as port:
        yield {"hub": hub, "port": port, "warned": warned, "dispatched": dispatched}


def test_관람객_전용_리스너는_관람객_경로만_연다(aud_only):
    for path in ("/audience", "/handout"):
        status, ctype, _ = _get(aud_only["port"], path)
        assert status == 200 and ctype.startswith("text/html"), path


@pytest.mark.parametrize("path", ["/", "/index.html", "/ws", "/anything"])
def test_관람객_전용_리스너는_조정실을_열지_않는다(aud_only, path):
    """관람객 폰이 닿는 포트로 시연을 멈추고 건너뛸 수 있으면 이 리스너를 두는 이유가 없다."""
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(aud_only["port"], path)
    assert e.value.code == 404


def test_관람객_전용_리스너의_조정실_소켓은_핸드셰이크에서_거절된다(aud_only):
    with pytest.raises(InvalidStatus) as e:
        connect(f"ws://127.0.0.1:{aud_only['port']}/ws", open_timeout=3)
    assert e.value.response.status_code == 404
    assert aud_only["dispatched"] == []


def test_관람객_전용_리스너의_보조_소켓은_그대로_읽기_전용이다(aud_only):
    with connect(f"ws://127.0.0.1:{aud_only['port']}/ws/audience", open_timeout=3) as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "a"}))
        aud_only["hub"].publish("sent", role="mc", type="say", fields={"cue_id": "01-intro", "seq": 1, "text": "자막"})
        got = _recv_until(ws, lambda m: m["kind"] == "say")
    assert got["text"] == "자막" and aud_only["dispatched"] == []
```

`tests/test_stage_main.py` 의 "대시보드_포트가_숫자가_아니면…" 테스트 아래에(`_가짜서버`·`stage.console` 패턴을 그대로 쓴다):

```python
def _관람객_리스너_셋업(monkeypatch, 환경):
    for k in ("REACHY_AUDIENCE_HOST", "REACHY_AUDIENCE_PORT", "REACHY_AUDIENCE_LEVEL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in 환경.items():
        monkeypatch.setenv(k, v)
    seen: dict = {"dash": []}

    class 멈춤(Exception):
        pass

    class 가짜대시:
        def __init__(self):
            self.shutdowns = 0

        def shutdown(self):
            self.shutdowns += 1

    def 가짜서버(*a, **kw):
        return _가짜서버(seen, *a, **kw)

    def 가짜_start_dashboard(hub, director, host, port, camera=None, warn=print, audience_only=False):
        seen["dash"].append({"host": host, "port": port, "audience_only": audience_only, "camera": camera})
        d = 가짜대시()
        seen.setdefault("objs", []).append(d)
        return d

    def 가짜콘솔(director, camera=None):
        raise 멈춤()

    import stage.console

    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
    monkeypatch.setattr(stage_main, "StageServer", 가짜서버)
    monkeypatch.setattr(stage_main, "start_dashboard", 가짜_start_dashboard)
    monkeypatch.setattr(stage.console, "run_console", 가짜콘솔)
    return seen, 멈춤


def test_REACHY_AUDIENCE_HOST_가_없으면_관람객_전용_리스너를_띄우지_않는다(monkeypatch):
    seen, 멈춤 = _관람객_리스너_셋업(monkeypatch, {})
    with pytest.raises(멈춤):
        stage_main.main()
    assert [d["audience_only"] for d in seen["dash"]] == [False]


def test_REACHY_AUDIENCE_HOST_가_있으면_관람객_전용_리스너를_더_띄우고_끝에_내린다(monkeypatch):
    seen, 멈춤 = _관람객_리스너_셋업(monkeypatch, {"REACHY_AUDIENCE_HOST": "0.0.0.0", "REACHY_AUDIENCE_PORT": "9912"})
    with pytest.raises(멈춤):
        stage_main.main()
    조정실, 관람객 = seen["dash"]
    assert 조정실["audience_only"] is False
    assert (관람객["host"], 관람객["port"], 관람객["audience_only"]) == ("0.0.0.0", 9912, True)
    assert 관람객["camera"] is None                                       # 관람객 리스너는 카메라를 모른다
    assert [o.shutdowns for o in seen["objs"]] == [1, 1]


def test_REACHY_AUDIENCE_PORT_가_숫자가_아니면_경고하고_그_리스너만_뺀다(monkeypatch, capsys):
    seen, 멈춤 = _관람객_리스너_셋업(monkeypatch, {"REACHY_AUDIENCE_HOST": "0.0.0.0", "REACHY_AUDIENCE_PORT": "9x12"})
    with pytest.raises(멈춤):
        stage_main.main()
    assert [d["audience_only"] for d in seen["dash"]] == [False]
    assert "⚠ REACHY_AUDIENCE_PORT 가 포트 번호가 아니다('9x12')" in capsys.readouterr().out
```

Run: `.venv/bin/python -m pytest tests/test_audience.py tests/test_stage_main.py -v -k "관람객_전용 or AUDIENCE_HOST or AUDIENCE_PORT"`
Expected: `TypeError: DashboardServer.__init__() got an unexpected keyword argument 'audience_only'` 등으로 FAIL.

- [ ] **Step 2: 구현한다**

`stage/dashboard.py` — `AUDIENCE_SNAPSHOT_KEYS` 정의 바로 아래에 상수를 둔다.

```python
# 관람객 전용 리스너(`REACHY_AUDIENCE_HOST`)가 내보내는 경로 — 조정실(`/`·`/ws`, 명령 가능)은 이 리스너로 열리지 않는다.
AUDIENCE_ONLY_PATHS = frozenset({"/audience", "/handout", "/ws/audience"})
```
`DashboardServer.__init__` 시그니처의 `cards=None) -> None:` 를 `cards=None, audience_only: bool = False) -> None:` 로 바꾸고, 본문의 `self._cards = cards or {}` 줄 아래에 한 줄을 더한다.

```python
        self._audience_only = audience_only
```
`process_request` 의 `path = split.path` 바로 아래에 더한다.

```python
        if self._audience_only and path not in AUDIENCE_ONLY_PATHS:
            # 관람객 폰이 닿는 포트에서는 조정실의 존재도 알리지 않는다 — 인증 없는 화면이 시연을 멈추고 건너뛸 수 있다.
            return connection.respond(404, "not found")
```
`start_dashboard` 를 아래로 바꾼다(앞의 위치 인자는 그대로, 새 인자는 키워드).

```python
def start_dashboard(hub, director, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                    camera=None, warn: Callable[[str], None] = print, audience_only: bool = False):
    """대시보드를 띄운다. **실패해도 감독·콘솔은 그대로 돈다** — 경고하고 None.

    `audience_only` 면 관람객 경로(`/audience`·`/handout`·`/ws/audience`)만 여는 두 번째 리스너다 — 조정실을 열지
    않고 카메라도 모른다(`REACHY_AUDIENCE_HOST`).
    """
    # 교육자료 카드는 여기서 읽는다 — 카드가 깨져도 경고하고 말풍선만으로 간다(감독은 산다). 큐시트를 줄 수 없는
    # 감독(테스트의 가짜)은 카드 없이 간다.
    cards = None
    cues_of = getattr(director, "cues", None)
    if callable(cues_of):
        cards = load_cards_or_warn(cues_of(), warn)
    ds = DashboardServer(hub, director, camera=None if audience_only else camera, warn=warn,
                         cards=cards, audience_only=audience_only)
```
(나머지 본문은 그대로. 위 근거 주석을 지우지 않는다. 관람객 전용 리스너도 `start_dashboard` 라서 카드 파일이 깨졌을 때 `⚠ 교육자료 카드를 못 읽었다` 경고가 리스너마다 한 번씩 난다 — 동작에는 영향이 없다.) 마지막 안내 줄을 가른다.

```python
    warn(f"관람객 전용(읽기 전용) — http://{host}:{port}/handout" if audience_only
         else f"대시보드 — http://{host}:{port}/")
```

`stage/__main__.py` — `from stage.server import StageServer` 줄 바로 다음에 상수를 더한다.

```python
AUD_PORT = 8779   # 관람객 전용 리스너(`REACHY_AUDIENCE_HOST`)의 기본 포트
```
머리 docstring 의 `REACHY_DASHBOARD_PORT` 줄 아래에 더한다.

```
    REACHY_AUDIENCE_HOST   관람객 전용 읽기 전용 리스너의 주소(기본 없음 = 안 띄움). 관람객 폰이 교육자료(/handout)에
                           닿게 하려면 전용 공유기 쪽 주소(0.0.0.0)를 적는다 — 조정실(/, 명령 가능)은 이 포트로 열리지 않는다
    REACHY_AUDIENCE_PORT   기본 8779 (틀린 값이면 경고하고 그 리스너만 뺀다)
```
`main()` 에서 `dash = None` 선언 줄 옆에 `aud = None` 을 두고, 대시보드 `try/except/else` 블록이 끝난 뒤(`try: run_console(...)` 바로 위)에 더한다.

```python
    aud_host = os.environ.get("REACHY_AUDIENCE_HOST", "").strip()
    if aud_host:
        raw_aud_port = os.environ.get("REACHY_AUDIENCE_PORT", str(AUD_PORT))
        try:
            aud_port = int(raw_aud_port)
        except ValueError:
            terminal(
                f"⚠ REACHY_AUDIENCE_PORT 가 포트 번호가 아니다({raw_aud_port!r}) — 관람객 전용 리스너를 띄우지 않는다"
                "(기본 포트로 바꾸지 않는다). 감독과 콘솔은 그대로 돈다"
            )
        else:
            aud = start_dashboard(hub, server.director, aud_host, aud_port, warn=terminal, audience_only=True)
```
`finally:` 안 `dash.shutdown()` 아래에 더한다.

```python
        if aud is not None:
            aud.shutdown()
```

- [ ] **Step 3: 통과를 확인하고 커밋한다**

Run: `.venv/bin/python -m pytest tests/test_audience.py tests/test_stage_main.py tests/test_dashboard.py tests/test_dashboard_e2e.py -v`
Expected: 전부 PASS.

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
git add stage/dashboard.py stage/__main__.py tests/test_audience.py tests/test_stage_main.py
git commit -m "feat(stage): 관람객 전용 읽기 전용 리스너 — 폰이 닿아도 조정실은 열리지 않는다(기본 꺼짐)" \
  -m "REACHY_AUDIENCE_HOST 를 주면 /audience·/handout·/ws/audience 만 여는 두 번째 리스너를 띄운다. 그 밖의 경로(조정실 / 와 /ws)는 404 이고 카메라도 모른다. 환경변수가 없으면 아무것도 안 띄운다. 포트가 틀리면 경고하고 그 리스너만 뺀다." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 운영 문서·교훈 대장·실제 스택 확인

**Files:**
- Modify: `docs/two-robot-offline-test.md`(관람객 보조 화면과 교육자료 절), `docs/lessons.md`(끝에 항목 추가)

**Interfaces:**
- Consumes: Task 1~7 의 동작(문서가 그 동작을 설명한다). Task 7 을 건너뛰었으면 아래 "관람객 전용 포트" 문단과 `REACHY_AUDIENCE_*` 언급을 뺀다.
- Produces: 운영자가 읽는 사용법과 실측 기록란, 이번 작업에서 실제로 겪은 실수의 박제.

- [ ] **Step 1: 운영 문서를 고친다**

`docs/two-robot-offline-test.md` 의 `**교육자료** \`http://127.0.0.1:8778/handout?level=초등\`` 불릿(세 줄)을 아래로 **교체**하고, 그 아래에 불릿 둘을 더한다. 그리고 바로 위 기존 불릿(`**띄우는 곳은 운영 노트북에 HDMI 로 연결한 두 번째 모니터가 기본이다.** …`) 끝에 `(더 안전한 방법은 아래 ‘관람객 폰에서 열기’ 의 REACHY_AUDIENCE_HOST 다.)` 를 덧붙인다 — 위험 경고와 권장 방법이 따로 놀지 않게.

```markdown
- **교육자료** `http://127.0.0.1:8778/handout` — 오늘 들은 해설(사회자·도슨트 대화)을 옮긴 한 페이지 자료다(2026-10-01
  개편). **모든 수준이 한 페이지에 있고** 위의 [초등][중고등][일반][전문가] 탭으로 고른다 — 주소의 `?level=초등` 은 처음 수준이자
  "관람객이 고른 것" 이라 이후 감독이 수준을 바꿔도 따라가지 않는다. 코스는 `&course=하이라이트`. 검수한 고정 대본과
  `data/handout.yaml` 의 검수한 카드만 싣는다 — 관람 중 나눈 질문과 답은 담기지 않는다(생성 답은 검수 전이라 내보내지 않는다).
  [인쇄하기] 는 큐마다 한 쪽씩 나온다 — 카드가 있는 큐는 요약만(접힌 대화 전문·인터랙션은 빠진다), 카드가 없는 큐는 말풍선 대화가 그대로 나온다.
- **공연 따라가기** — 공연 중에 이 페이지를 열어 두면 **지금 이야기 중인 큐의 장이 저절로 열리고**(빨간 "지금 이야기 중"),
  말하는 말풍선과 카드가 켜지며, 아래 막대에 지금 말하는 문장이 뜬다. 카드가 있는 큐(지금 02·03)는 도슨트가 말하는 대목에서
  그림이 **저절로 움직인다** — 02 는 마르코니 설명에서 신호가 영국에서 대서양 건너로 가고, 03 은 주파수 설명 동안 다이얼이
  올라가고 파장 설명에서 FM 100MHz 에 선다. 카드가 없는 큐는 말풍선만 강조된다(카드는 `data/handout.yaml` 에 더한다).
  관람객이 직접 스크롤하면 따라가기가 멈추고 [지금 이야기로] 로 돌아온다. 수준은 감독을 따르다가 관람객이 탭을 누르면 그쪽이 이긴다.
  연결이 끊기면 "다시 연결하는 중…" 이 보이고 다시 붙으면 현재 상태로 맞춘다. 진행 신호는 감독이 로봇에게 보내는 `say` 의 발화
  라벨이다 — **로봇 재배포가 필요 없다.** 큐를 직접 옮기면(`g`·`p`·`r`) 그 큐의 처음으로 돌아가고, 공연을 끝내면(`e`) 모두 걷힌다.
  교육자료에 카드·그림이 안 보이면 터미널의 `⚠ 교육자료 카드를 못 읽었다` 를 본다(말풍선만으로 계속 돈다).
- **관람객 폰에서 열기** — 폰은 노트북의 LAN IP 로 연다. 대시보드를 `REACHY_DASHBOARD_HOST=0.0.0.0` 에 열면 조정실도 같이 열리므로,
  **`REACHY_AUDIENCE_HOST=0.0.0.0`**(`REACHY_AUDIENCE_PORT` 기본 8779)을 쓰는 편이 안전하다 — 관람객 경로(`/audience`·`/handout`)만 열리고
  `/`·`/ws`(조정실)는 404 다. 폰 주소는 `http://192.168.0.x:8779/handout`. 환경변수가 없으면 이 리스너는 안 뜬다.
```

- [ ] **Step 2: 교훈 대장에 이번 작업의 실수를 박제한다**

`docs/lessons.md` 맨 끝에 추가한다(시안 검증 중 실제로 겪은 것들이다).

```markdown
### 발화 라벨은 감독 안의 내부 규칙이다 — 읽는 쪽이 어긋나면 엉뚱한 카드가 켜진다
- **증상**(설계 중 발견): 교육자료가 "지금 어느 큐의 어느 대목인가"를 알려면 `say` 의 `cue_id` 를 읽어야 하는데, 그 문자열은
  `Director._point_label`·`_begin_cue` 가 만드는 **내부 규칙**이다(`02-history:pt1:docent`, 마지막 설명만 `02-history:docent`).
  규칙이 바뀌어도 읽는 쪽은 조용히 엉뚱한 대목으로 읽는다.
- **원인**: 라벨은 원래 감독 안에서 받아치기 분기를 가르는 용도(`on_speaking_ended`)라 계약 문서도 테스트도 없었다.
- **규칙**: 읽는 쪽(`stage/say_label.py`)을 한 곳에 두고, **실제 감독을 큐시트 끝까지 돌려** 나온 라벨을 읽어 보는 테스트로 박제한다.
  규칙에 안 맞는 라벨은 틀리게 읽지 말고 `None`(자막만)으로 둔다.
- **박제**: `tests/test_say_label.py::test_실제_큐시트의_모든_큐가_기대한_턴_순서로_읽힌다`,
  `::test_한_턴_큐는_여는_말과_마지막_도슨트만_있다`, `::test_큐시트에_없거나_규칙에_안_맞는_라벨은_None_이다`.

### 숫자로 시작하는 id 는 CSS 선택자로 못 쓴다 — `#02-history` 는 SyntaxError
- **증상**(시안 검증): 브라우저 자동화에서 `document.querySelector('#02-history .chain li')` 가 `is not a valid selector` 로 죽었다.
- **원인**: 큐 id(`02-history`)는 HTML id 로는 유효하지만 CSS 식별자는 숫자로 시작할 수 없다.
- **규칙**: 큐 id 를 선택자로 쓰지 않는다 — `getElementById('02-history')` 로 요소를 잡고 그 안에서 `querySelector` 한다
  (또는 `[id="02-history"]`). 앵커 링크(`#02-history`)는 된다.
- **박제**: 브라우저 테스트(`tests/test_handout_browser.py`)가 전부 `getElementById` 를 쓴다.

### 숨긴 부모 안의 자식은 `display` 가 그대로다 — 보이는지는 `getClientRects()` 로 가른다
- **증상**(시안 검증): "보이는 카드 수" 를 `getComputedStyle(li).display !== 'none'` 으로 셌더니 수준 4개 × 3 = 12 가 나왔다.
- **원인**: 숨긴 수준 묶음(`ol.lv`)이 `display:none` 이어도 그 안의 `li` 의 계산값은 `list-item` 그대로다.
- **규칙**: 화면에 그려지는지는 `el.getClientRects().length > 0`(`tests/_cdp.py::VISIBLE`)로 본다.
- **박제**: 브라우저 테스트의 `_rows`·`_items` 가 `VISIBLE` 로 거른다.
```

- [ ] **Step 3: 전체 테스트와 문서 경로를 확인한다**

Run: `.venv/bin/python -m pytest -q -p no:cacheprovider`
Expected: 전부 통과(이 작업 전 1270 + 새 테스트, 크롬 테스트는 이 맥에서 실제로 돈다).

- [ ] **Step 4: 실제 스택에서 사람이 눈으로 확인한다**

`./reachy.sh start --sim` 으로 시연 한 벌(시뮬 2대 + 감독 + 대시보드)을 띄운다. 크롬으로 `http://127.0.0.1:8778/handout` 을 열고(가능하면 폰도 — Task 7 을 했다면 `REACHY_AUDIENCE_HOST=0.0.0.0 ./reachy.sh start --sim` 후 `http://<노트북 LAN IP>:8779/handout`), 콘솔에서 `s` 로 공연을 시작해 아래를 **직접 보고 기록한다**.

- [ ] 01 큐부터 장이 저절로 열리고 "지금 이야기 중" 이 붙는다. 큐가 넘어가면 다음 장으로 스크롤한다.
- [ ] 말하는 말풍선이 강조되고 아래 막대의 문장이 로봇이 실제로 말하는 문장과 같다.
- [ ] 02 큐의 마르코니 설명에서 신호가 출발한다. 03 큐에서 다이얼이 올라가고 FM 100MHz 에 선다.
- [ ] 콘솔 `l 초등` → 페이지의 수준이 바뀐다(탭을 직접 누르지 않았을 때). 탭을 누른 뒤에는 안 바뀐다.
- [ ] 콘솔 `r`(이 큐 다시)·`e`(공연 종료)에서 강조가 처음으로 돌아가고 종료에서 막대가 사라진다.
- [ ] 노트북 와이파이를 껐다 켜면 "다시 연결하는 중…" 이 뜨고 복구된다.
- [ ] **타이밍 실측**: 화면 강조가 로봇의 실제 발성 시작보다 얼마나 빠른가(캐시 적중 대사 / 캐시에 없는 관람객 답 각각 대략 몇 초). `real-robot-deployment.md` §15.2-3 이 말하듯 `say` 는 발성보다 먼저 나간다 — 결과를 `docs/two-robot-offline-test.md` 의 "공연 따라가기" 불릿 끝에 `실측(날짜): …` 한 줄로 적는다. 체감상 어긋나면 02·03 의 `live` 동작에 지연 인자를 두는 후속 작업을 제안한다.
- [ ] `./reachy.sh logs` 의 경고(`대시보드 소켓을 거절했다`·`교육자료를 만들지 못했다`·`라벨을 읽으려…`)가 없다.

- [ ] **Step 5: 커밋한다**

```bash
git add docs/two-robot-offline-test.md docs/lessons.md
git commit -m "docs: 교육자료 공연 따라가기 운영법과 이번 작업의 교훈 3건" \
  -m "한 페이지 전 수준·공연 따라가기·카드·그림의 자동 동작·관람객 폰 접근 방법을 운영 문서에 적고, 발화 라벨 계약·숫자로 시작하는 id 의 CSS 선택자·숨긴 부모 속 자식의 가시성 판정을 교훈 대장에 박제한다." \
  -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review (작성자 점검 결과)

- **스펙 대응**: ① 퀴즈 제외 — 설계 결정 1(계획에 퀴즈 Task 없음). ② 도슨트 답변 시 교육자료 자동 선택 — Task 1·2(라벨 → `cue`·`turn`)·4(장 선택·강조). ③ 인터랙티브 요소 자동 동작 — Task 5(`live` 데이터)·6(신호·다이얼). ④ 시안의 핵심 카드·말풍선 — Task 3·5. ⑤ 시안의 인쇄 한 면·모바일 — Task 3·5·6 의 CSS(`@media print`, 640px). 빠진 요구 없음.
- **자리표시자 점검**: "TBD"·"나중에"·"비슷하게" 없음. 코드 단계에는 전체 코드를 실었다. 시안에서 옮기는 CSS·JS·SVG 도 이 문서에 전문이 있다(시안 파일을 보라고 하지 않는다).
- **타입·이름 일관성**: `SayRef(cue, turn)`·`parse_say_label(label, points_of)`(Task 1) = `audience_event(ev, points_of)`·`DashboardServer._points_of`(Task 2) = JS 의 `m.cue`·`m.turn`(Task 4). `render_handout(…, cards, live, level_locked)`(Task 3) 시그니처는 Task 4·5·6 이 같은 이름으로 쓴다. `CueCard.viz/.live`(Task 5) = `VIZ_ACTIONS`·`render_viz`(Task 6). 턴 이름 `open·ask<i>·docent<i>·after` 는 라벨 해석(Task 1)·말풍선 `data-t`(Task 3)·카드 `data-turns`(Task 5)·YAML(Task 5)·JS 가 모두 같다. `window.handout.register/onReset/onLevel/level/reduceMotion` 은 Task 4 에서 정의하고 Task 6 이 쓴다.
- **알려진 한계(계획 밖)**: 폰에 주소를 알리는 QR·안내 화면, 나머지 17큐의 카드·그림 저작, `say` 가 발성 시작보다 먼저 나가서 생기는 화면–소리 어긋남(Task 8 Step 4 가 실측하고, 어긋나면 후속 작업으로 지연 인자를 둔다), 관람객 질문 답의 교육자료 반영.

## 검증 이력 (사전 점검, 2026-10-02)

이 계획서는 **저장소 복사본에서 Task 1~8 을 문자 그대로 끝까지 실행**해 점검했다(원본은 건드리지 않았다).

- **결과**: 전체 테스트 **1381 passed, 2 skipped**(작업 전 기준선 1270 passed, 2 skipped — skip 2건은 기준선과 같은 `tests/test_camera_rtc.py`). 이번 작업의 새 테스트는 skip 이 없다. 브라우저 테스트 30건은 실제 헤드리스 Chrome 에서 돌았고 파일 단독 10회 반복이 모두 통과했다.
- **1차 점검(중단됨)에서 고친 것 2건**: DOM 요소를 그대로 돌려주는 `wait_for` 식은 `{}` 로 직렬화돼 영원히 거짓이다(Task 5, `!!` 추가) / 맞춤 큐시트에서 표준 카드 파일이 통째로 거절되어 경고가 늘던 것(Task 5, `strict=False` 로 그 큐시트에 없는 큐의 카드만 건너뜀).
- **2차 점검에서 고친 것**: ① Task 3 의 `data-level-locked` 부재 단언이 Task 4 에서 스크립트가 인라인되면 깨짐(따옴표까지 비교) ② Chrome 의 `/favicon.ico` 404 가 콘솔 오류로 잡힘 — 필터로 숨기지 않고 `<head>` 에 `<link rel="icon" href="data:,">` 로 요청 자체를 없앴다(3회 × 30건 통과) ③ 스무스 스크롤 도중에 읽는 테스트 타이밍(`=== 76` 정착 후 읽기, 30회 반복 0 실패) ④ `_points_of` 의 "경고 한 번" 이 연결이 여럿이면 깨짐 — 연결 6개에서 경고 6번을 재현한 뒤 잠금으로 고침(5회 통과) ⑤ Task 7 의 `start_dashboard` 교체가 근거 주석을 지우던 것, 운영 문서의 상충 불릿·인쇄 문장, 건수·Expected 문구 표기.
- **확인하지 못한 것**: Task 8 Step 4(실제 `./reachy.sh start --sim` 스택, 폰/LAN 접속, 와이파이 끊김, **발성 대비 화면 타이밍 실측**)와 640px 이하 모바일 레이아웃·인쇄 쪽 나눔의 눈 확인. 인쇄는 `.interact` 숨김만 테스트로 확인했다. 구현 후 사람이 확인할 몫이다.
