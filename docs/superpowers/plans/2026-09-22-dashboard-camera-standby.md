# 대시보드 카메라(WebRTC) + 로봇별 대기모드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드 CAM 1·CAM 2 칸에 두 로봇의 카메라 영상을 H.264 + WebRTC로 실시간으로 띄우고,
대시보드에서 로봇 한 대씩 대기모드(잠자기+모터 풀림)로 넣고 뺄 수 있게 한다.

**Architecture:** 감독 프로세스 안에 순수 로직 모듈 `stage/camera.py`(`CameraRelay`)를 새로 두고,
기존 로봇 소켓(8777)·대시보드 소켓(8778)을 시그널링 중계로만 쓴다(새 포트 없음). 영상 자체는
로봇에서 브라우저로 직접 간다(RTP/SRTP, UDP). 대기모드는 새 상태기계를 만들지 않고
`Director.solo_role` 판정을 `connected - standby` 로 일반화해 기존 1인 모드 경로를 재사용한다.

**Tech Stack:** Python 3.12, GStreamer 1.26+(webrtcbin·v4l2h264enc/x264enc·rtph264pay),
PyGObject(GstWebRTC·GstSdp), websockets(sync API), 순수 JS(빌드 없음).

**Spec:** `docs/superpowers/specs/2026-09-22-dashboard-camera-design.md`(본문: 카메라, 부록: 대기모드).
실행자는 이 계획과 스펙을 함께 읽는다 — 스펙이 "왜"를, 이 계획이 "어떻게·어디"를 답한다.

## Global Constraints

- **`.venv/bin/python` 하나만 쓴다** — 시스템 `python3` 는 SDK가 안 깔린다(CLAUDE.md).
- **각 태스크는 실패하는 테스트 → 최소 구현 → 통과 → 커밋** 순서다(test-driven-development).
- **카메라 기본값**: 640×480·15fps·2000kbps·I-프레임 간격 1초(스파이크 실측값, 스펙 §스파이크 결과).
- **인코더 사다리**: `v4l2h264enc`(실기 하드웨어) → `x264enc` → `openh264enc`. 하드웨어가 아니면 경고.
- **PyGObject 함정**(`docs/lessons.md`): `reply = promise.get_reply()` 로 **붙잡고**, SDP 텍스트는
  `set-local-description` **전에** 뽑는다. 이 규칙을 어기면 SDP 가 비거나 프로세스가 말없이 죽는다.
- **`camera`·`rtc` 메시지는 허브 `sent`/`recv` 에 싣지 않는다** — ICE·SDP 가 이력 200칸을 밀어낸다.
- **시뮬 전용 우회는 스위치 뒤, 기본 꺼짐**(CLAUDE.md) — `REACHY_CAMERA_SRC` 로 시뮬에서 켠다.
- **대기모드 전환은 항상 먼저 멈춘다**(`_abort_locked()`, `set_mode` 와 같은 패턴) — 부분 중단이라는
  새 개념을 만들지 않는다.
- 새 프로토콜 메시지가 늘 때마다 `stage/protocol.py` 와 `apps/voice_chat/voice_chat/stage_client.py` 의
  상수 집합을 **함께** 고친다(한쪽만 고치면 실기에서 "로봇이 보낼 수 없는 메시지다" 로 조용히 막힌다).

---

### Task 1: 프로토콜 메시지 3종 추가

**Files:**
- Modify: `stage/protocol.py`
- Modify: `apps/voice_chat/voice_chat/stage_client.py:15-16` (`_ROBOT_MSGS`/`_DIRECTOR_MSGS`)
- Test: `tests/test_stage_protocol.py`

**Interfaces:**
- Produces: `protocol.ROBOT_MSGS` 에 `"rtc"` 추가, `protocol.DIRECTOR_MSGS` 에 `"camera"`·`"rtc"`·
  `"standby"` 추가. `protocol.KNOWN_MSGS` 는 자동으로 합집합.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_protocol.py` 의 `test_메시지_종류는_9종뿐이다` 를 아래로 바꾼다:

```python
def test_메시지_종류는_12종이다():
    # 규약이 늘어나면 여기서 먼저 깨져야 한다 — 설계 문서 §4·카메라 설계 §프로토콜 표와 짝이다.
    assert protocol.ROBOT_MSGS == frozenset(
        {"hello", "heard", "speaking_started", "speaking_ended", "error", "rtc"}
    )
    assert protocol.DIRECTOR_MSGS == frozenset(
        {"say", "mic", "gaze", "abort", "camera", "rtc", "standby"}
    )
    assert len(protocol.ROBOT_MSGS | protocol.DIRECTOR_MSGS) == 12
    assert protocol.ROLES == {"mc", "docent"}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_protocol.py::test_메시지_종류는_12종이다 -v`
Expected: FAIL — `ROBOT_MSGS` 에 아직 `"rtc"` 가 없고, `DIRECTOR_MSGS` 에 세 메시지가 없다.

- [ ] **Step 3: 최소 구현**

`stage/protocol.py` 의 `ROBOT_MSGS`/`DIRECTOR_MSGS` 를 고친다:

```python
ROBOT_MSGS = frozenset(
    {"hello", "heard", "speaking_started", "speaking_ended", "error", "rtc"}
)
DIRECTOR_MSGS = frozenset({"say", "mic", "gaze", "abort", "camera", "rtc", "standby"})
```

`apps/voice_chat/voice_chat/stage_client.py` 도 같은 값으로:

```python
_ROBOT_MSGS = frozenset(
    {"hello", "heard", "speaking_started", "speaking_ended", "error", "rtc"}
)
_DIRECTOR_MSGS = frozenset({"say", "mic", "gaze", "abort", "camera", "rtc", "standby"})
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_protocol.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add stage/protocol.py apps/voice_chat/voice_chat/stage_client.py tests/test_stage_protocol.py
git commit -m "feat(protocol): rtc·camera·standby 메시지 3종 추가"
```

---

### Task 2: `stage_client.py` — 로봇 쪽 카메라·대기모드 콜백과 송신

**Files:**
- Modify: `apps/voice_chat/voice_chat/stage_client.py`
- Test: `tests/test_stage_client.py`

**Interfaces:**
- Consumes: Task 1 의 `_ROBOT_MSGS`/`_DIRECTOR_MSGS`.
- Produces: `Handlers(on_say, on_mic, on_gaze, on_abort, on_camera, on_rtc, on_standby)` — 뒤 셋은
  **기본값 없음**(기존 넷과 같은 수준으로 필수). `StageClient.__init__(..., caps: list[str] | None = None)`.
  `StageClient.rtc(viewer: str, payload: dict) -> None` — 로봇→감독 송신.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_client.py` 끝에 추가한다(기존 `collector()`/`FakeWS` 재사용):

```python
def test_hello에_caps를_싣는다():
    got, handlers = collector()
    client = StageClient("ws://x", "mc", handlers, caps=["camera"])
    ws = FakeWS()
    client.run(should_stop=lambda: True, connect_fn=lambda url: ws)
    assert ws.sent[0] == {"type": "hello", "role": "mc", "unit_id": None,
                           "version": "", "caps": ["camera"]}


def test_caps_없으면_hello에서_뺀다():
    got, handlers = collector()
    client = StageClient("ws://x", "mc", handlers)
    ws = FakeWS()
    client.run(should_stop=lambda: True, connect_fn=lambda url: ws)
    assert "caps" not in ws.sent[0]


def test_camera_지시가_on_camera로_간다():
    got, handlers = collector()
    ws = FakeWS(inbox=[{"type": "camera", "viewer": "v1", "on": True}])
    client = StageClient("ws://x", "mc", handlers)
    n = [0]

    def should_stop():
        n[0] += 1
        return n[0] > 1

    client.run(should_stop=should_stop, connect_fn=lambda url: ws)
    assert ("camera", "v1", True) in got


def test_rtc_지시가_on_rtc로_간다():
    got, handlers = collector()
    ws = FakeWS(inbox=[{"type": "rtc", "viewer": "v1", "sdp": {"type": "answer", "sdp": "v=0"}}])
    client = StageClient("ws://x", "mc", handlers)
    n = [0]

    def should_stop():
        n[0] += 1
        return n[0] > 1

    client.run(should_stop=should_stop, connect_fn=lambda url: ws)
    assert ("rtc", "v1", {"sdp": {"type": "answer", "sdp": "v=0"}}) in got


def test_standby_지시가_on_standby로_간다():
    got, handlers = collector()
    ws = FakeWS(inbox=[{"type": "standby", "on": True}])
    client = StageClient("ws://x", "mc", handlers)
    n = [0]

    def should_stop():
        n[0] += 1
        return n[0] > 1

    client.run(should_stop=should_stop, connect_fn=lambda url: ws)
    assert ("standby", True) in got


def test_rtc_송신은_viewer와_페이로드를_싣는다():
    got, handlers = collector()
    client = StageClient("ws://x", "mc", handlers)
    ws = FakeWS()
    client._ws = ws
    client.rtc("v1", {"sdp": {"type": "offer", "sdp": "v=0"}})
    assert ws.sent[-1] == {"type": "rtc", "viewer": "v1", "sdp": {"type": "offer", "sdp": "v=0"}}
```

`collector()` 가 넷만 채우고 있으므로 이 파일 상단의 `collector()` 도 고친다(같은 파일, 기존 함수):

```python
def collector():
    got = []
    return got, Handlers(
        on_say=lambda cue_id, text, seq: got.append(("say", cue_id, text, seq)),
        on_mic=lambda open_: got.append(("mic", open_)),
        on_gaze=lambda target: got.append(("gaze", target)),
        on_abort=lambda: got.append(("abort",)),
        on_camera=lambda viewer, on: got.append(("camera", viewer, on)),
        on_rtc=lambda viewer, payload: got.append(("rtc", viewer, payload)),
        on_standby=lambda on: got.append(("standby", on)),
    )
```
(기존 `on_gaze`/`on_abort` 줄이 이미 있으면 그대로 두고 뒤 세 줄만 더한다 — 정확한 기존 내용은
파일을 먼저 읽고 맞춘다.)

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_client.py -v -k "camera or rtc or standby or caps"`
Expected: FAIL — `Handlers` 에 `on_camera` 등이 없다는 `TypeError`.

- [ ] **Step 3: 최소 구현**

`apps/voice_chat/voice_chat/stage_client.py` 의 `Handlers` 에 필드 3개 추가:

```python
    on_camera: Callable[[str, bool], None]
    on_rtc: Callable[[str, dict], None]
    on_standby: Callable[[bool], None]
```

`StageClient.__init__` 에 `caps` 파라미터 추가(시그니처 끝, `warn` 앞):

```python
    def __init__(
        self,
        url: str,
        role: str,
        handlers: Handlers,
        unit_id: str | None = None,
        version: str = "",
        caps: list[str] | None = None,
        warn: Callable[[str], None] = print,
    ) -> None:
        self._url = url
        self._role = role
        self._h = handlers
        self._unit_id = unit_id
        self._version = version
        self._caps = caps
        self._warn = warn
        self._ws = None
```

`rtc()` 송신 메서드 추가(`error()` 옆):

```python
    def rtc(self, viewer: str, payload: dict) -> None:
        self._send("rtc", viewer=viewer, **payload)
```

hello 를 보내는 자리(`run()` 안, `self._send("hello", role=..., unit_id=..., version=...)`)를 고친다:

```python
                self._send(
                    "hello", role=self._role, unit_id=self._unit_id,
                    version=self._version,
                    **({"caps": self._caps} if self._caps is not None else {}),
                )
```

`_on_raw` 의 분기에 셋을 추가(기존 `elif t == "abort":` 다음):

```python
            elif t == "camera":
                self._h.on_camera(msg.get("viewer", ""), bool(msg.get("open") if False else msg.get("on")))
            elif t == "rtc":
                payload = {k: v for k, v in msg.items() if k not in ("type", "viewer")}
                self._h.on_rtc(msg.get("viewer", ""), payload)
            elif t == "standby":
                self._h.on_standby(bool(msg.get("on")))
```

(`on_camera` 줄의 `if False else` 는 실수 방지용 임시가 아니라 — **지운다**, 그냥
`bool(msg.get("on"))` 으로 쓴다. 위 스니펫을 그대로 베끼지 말고 아래처럼 단순화해서 넣는다:)

```python
            elif t == "camera":
                self._h.on_camera(msg.get("viewer", ""), bool(msg.get("on")))
            elif t == "rtc":
                payload = {k: v for k, v in msg.items() if k not in ("type", "viewer")}
                self._h.on_rtc(msg.get("viewer", ""), payload)
            elif t == "standby":
                self._h.on_standby(bool(msg.get("on")))
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_client.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add apps/voice_chat/voice_chat/stage_client.py tests/test_stage_client.py
git commit -m "feat(stage_client): camera·rtc·standby 수신, caps 송신, rtc() 송신"
```

---

### Task 3: `stage/camera.py` — `CameraRelay` (순수 로직, 새 모듈)

**Files:**
- Create: `stage/camera.py`
- Test: `tests/test_stage_camera.py`

**Interfaces:**
- Produces: `CameraRelay(send_robot: Callable[[str, str, dict], None], warn=print)`.
  공개 메서드: `add_viewer(deliver) -> str`, `remove_viewer(viewer)`, `on_robot_hello(role, caps)`,
  `on_robot_disconnect(role)`, `on_robot_error(role, detail)`, `on_robot_rtc(role, msg)`,
  `on_viewer_rtc(viewer, msg)`, `toggle(role)`, `snapshot() -> dict`.
- Consumes: 없음(네트워크·감독을 모른다).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_camera.py` 새로 작성:

```python
"""CameraRelay — 순수 로직. 네트워크·감독 없이 콜백만으로 시험한다."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.camera import CameraRelay


def _relay():
    sent = []  # (role, type, fields)
    return CameraRelay(send_robot=lambda role, t, f: sent.append((role, t, f)), warn=lambda m: None), sent


def test_시청자도_로봇도_없으면_꺼진_상태다():
    relay, sent = _relay()
    assert relay.snapshot()["mc"] == {"available": False, "enabled": True, "reason": "OFFLINE"}


def test_로봇이_hello로_카메라_능력을_알리면_available이_된다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    assert relay.snapshot()["mc"]["available"] is True
    assert relay.snapshot()["mc"]["reason"] == ""


def test_caps에_camera가_없으면_사유를_보인다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", [])
    assert "카메라 없음" in relay.snapshot()["mc"]["reason"]


def test_시청자가_붙으면_가능한_로봇에게만_camera_on을_보낸다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.on_robot_hello("docent", [])  # 능력 없음
    vid = relay.add_viewer(lambda ev: None)
    assert ("mc", "camera", {"viewer": vid, "on": True}) in sent
    assert not any(r == "docent" and t == "camera" for r, t, f in sent)


def test_같은_상태로는_다시_보내지_않는다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.add_viewer(lambda ev: None)
    n = len(sent)
    relay.on_robot_hello("mc", ["camera"])  # 다시 hello — 상태는 이미 on
    assert len(sent) == n


def test_운영자가_끄면_on을_끄고_시청자에게_bye를_보낸다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    events = []
    vid = relay.add_viewer(events.append)
    relay.toggle("mc")  # 끔
    assert ("mc", "camera", {"viewer": vid, "on": False}) in sent
    assert {"kind": "rtc", "role": "mc", "bye": True} in events
    assert relay.snapshot()["mc"]["reason"] == "카메라 꺼짐"


def test_로봇_offer가_그_시청자에게만_간다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    a_events, b_events = [], []
    va = relay.add_viewer(a_events.append)
    vb = relay.add_viewer(b_events.append)
    relay.on_robot_rtc("mc", {"viewer": va, "sdp": {"type": "offer", "sdp": "v=0"}})
    assert {"kind": "rtc", "role": "mc", "sdp": {"type": "offer", "sdp": "v=0"}} in a_events
    assert not any(e.get("sdp") for e in b_events)


def test_모르는_시청자에게_온_rtc는_버린다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.on_robot_rtc("mc", {"viewer": "없는id", "sdp": {"type": "offer", "sdp": "v=0"}})  # 죽지 않는다


def test_시청자의_answer는_그_로봇에게만_간다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.on_robot_hello("docent", ["camera"])
    vid = relay.add_viewer(lambda ev: None)
    sent.clear()
    relay.on_viewer_rtc(vid, {"role": "mc", "sdp": {"type": "answer", "sdp": "v=0"}})
    assert sent == [("mc", "rtc", {"viewer": vid, "sdp": {"type": "answer", "sdp": "v=0"}})]


def test_너무_큰_sdp는_버린다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    vid = relay.add_viewer(lambda ev: None)
    sent.clear()
    relay.on_viewer_rtc(vid, {"role": "mc", "sdp": {"type": "answer", "sdp": "x" * 70000}})
    assert sent == []


def test_시청자가_떠나면_로봇의_그_분기를_끈다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    vid = relay.add_viewer(lambda ev: None)
    sent.clear()
    relay.remove_viewer(vid)
    assert ("mc", "camera", {"viewer": vid, "on": False}) in sent


def test_로봇이_끊기면_시청자에게_bye를_보낸다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    events = []
    relay.add_viewer(events.append)
    relay.on_robot_disconnect("mc")
    assert {"kind": "rtc", "role": "mc", "bye": True} in events
    assert relay.snapshot()["mc"]["available"] is False


def test_오류는_다음에_켤_때까지_사유에_남는다():
    relay, sent = _relay()
    relay.on_robot_hello("mc", ["camera"])
    relay.add_viewer(lambda ev: None)
    relay.on_robot_error("mc", "파이프라인 실패")
    assert "파이프라인 실패" in relay.snapshot()["mc"]["reason"]
    relay.toggle("mc")   # 끔
    relay.toggle("mc")   # 다시 켬
    assert "파이프라인 실패" not in relay.snapshot()["mc"]["reason"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_camera.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stage.camera'`

- [ ] **Step 3: 구현**

`stage/camera.py` 새로 작성:

```python
"""대시보드 카메라 중계 — 순수 로직, 네트워크를 모른다.

로봇의 카메라 영상(H.264, WebRTC)을 대시보드로 잇는다. 영상 자체는 로봇에서 브라우저로
**직접** 간다(RTP/SRTP, UDP) — 여기를 지나는 것은 SDP·ICE 시그널링과 "켤지 말지" 판단뿐이다.
설계: docs/superpowers/specs/2026-09-22-dashboard-camera-design.md.

**콜백 둘로 네트워크를 가린다**: `send_robot(role, type, fields)`(로봇에게)와 시청자마다
`deliver(ev)`(그 대시보드 연결에게). 소켓 없이 단위 테스트된다 — `stage/server.py`·
`stage/dashboard.py` 가 배선만 한다.
"""

from dataclasses import dataclass
from typing import Callable

ROLES = frozenset({"mc", "docent"})
MAX_SDP_BYTES = 64 * 1024
MAX_CANDIDATE_BYTES = 2 * 1024


@dataclass
class _RobotState:
    connected: bool = False
    has_camera: bool = False   # hello.caps 에 "camera" 를 실었다
    enabled: bool = True       # 운영자 스위치(콘솔·대시보드 `c`) — 기본 켜짐
    reason: str = ""           # 로봇이 올린 오류(있으면). 다음에 켤 때 지운다


class CameraRelay:
    def __init__(self, send_robot: Callable[[str, str, dict], None],
                 warn: Callable[[str], None] = print) -> None:
        self._send_robot = send_robot
        self._warn = warn
        self._robots: dict[str, _RobotState] = {r: _RobotState() for r in ROLES}
        self._viewers: dict[str, Callable[[dict], None]] = {}
        # (role, viewer) -> 지금 그 로봇이 그 시청자에게 켜져 있다고 우리가 마지막으로
        # 보낸 값. **바뀔 때만** 다시 보낸다(설계: "바뀐 쌍에만 camera{on} 을 보낸다").
        self._active: dict[tuple[str, str], bool] = {}
        self._next_id = 1
        self._warned_once: set[str] = set()

    # ── 시청자 ────────────────────────────────────────────────────
    def add_viewer(self, deliver: Callable[[dict], None]) -> str:
        vid = f"v{self._next_id}"
        self._next_id += 1
        self._viewers[vid] = deliver
        self._recompute_all()
        return vid

    def remove_viewer(self, viewer: str) -> None:
        self._viewers.pop(viewer, None)
        for role in ROLES:
            self._set_pair(role, viewer, False)
            self._active.pop((role, viewer), None)

    # ── 로봇에게서 오는 것 ────────────────────────────────────────
    def on_robot_hello(self, role: str, caps: list[str] | None) -> None:
        if role not in ROLES:
            return
        st = self._robots[role]
        st.connected = True
        st.has_camera = bool(caps and "camera" in caps)
        self._recompute(role)

    def on_robot_disconnect(self, role: str) -> None:
        if role not in ROLES:
            return
        self._robots[role].connected = False
        self._robots[role].has_camera = False
        for viewer in list(self._viewers):
            self._set_pair(role, viewer, False)

    def on_robot_error(self, role: str, detail: str) -> None:
        if role not in ROLES:
            return
        self._robots[role].reason = f"카메라 오류: {detail}"
        self._warn(f"[{role}] 카메라 오류: {detail}")

    def on_robot_rtc(self, role: str, msg: dict) -> None:
        if role not in ROLES:
            return
        viewer = msg.get("viewer")
        if not isinstance(viewer, str) or viewer not in self._viewers:
            self._warn_once(f"unknown-viewer-{role}",
                             f"[{role}] 모르는 시청자에게 rtc — 버린다: {viewer!r}")
            return
        ok, payload = self._validate_rtc(msg)
        if not ok:
            self._warn_once(f"bad-rtc-{role}", f"[{role}] rtc 가 규약에 안 맞는다({payload}) — 버린다")
            return
        self._deliver(viewer, {"kind": "rtc", "role": role, **payload})

    # ── 시청자에게서 오는 것 ──────────────────────────────────────
    def on_viewer_rtc(self, viewer: str, msg: dict) -> None:
        role = msg.get("role")
        if role not in ROLES:
            self._warn_once("viewer-bad-role", f"대시보드가 모르는 역할로 rtc — 버린다: {role!r}")
            return
        if msg.get("restart"):
            self._set_pair(role, viewer, False)
            self._recompute(role)
            return
        ok, payload = self._validate_rtc(msg)
        if not ok:
            self._warn_once(f"viewer-bad-rtc-{role}", f"대시보드의 rtc 가 규약에 안 맞는다({payload}) — 버린다")
            return
        self._send_robot(role, "rtc", {"viewer": viewer, **payload})

    # ── 운영자 ────────────────────────────────────────────────────
    def toggle(self, role: str) -> None:
        if role not in ROLES:
            self._warn(f"모르는 역할이다: {role!r} — 카메라를 바꾸지 않는다")
            return
        st = self._robots[role]
        st.enabled = not st.enabled
        self._warn(f"[{role}] 카메라 {'켬' if st.enabled else '끔'}")
        self._recompute(role)

    def snapshot(self) -> dict:
        return {role: {"available": st.connected and st.has_camera,
                        "enabled": st.enabled, "reason": self._reason(role)}
                for role, st in self._robots.items()}

    # ── 내부 ──────────────────────────────────────────────────────
    def _reason(self, role: str) -> str:
        st = self._robots[role]
        if not st.connected:
            return "OFFLINE"
        if not st.has_camera:
            return "카메라 없음 — 시뮬이거나 로봇 앱이 카메라를 모른다(재배포 필요)"
        if not st.enabled:
            return "카메라 꺼짐"
        return st.reason

    def _recompute_all(self) -> None:
        for role in ROLES:
            self._recompute(role)

    def _recompute(self, role: str) -> None:
        st = self._robots[role]
        want_on = st.connected and st.has_camera and st.enabled and bool(self._viewers)
        for viewer in list(self._viewers):
            self._set_pair(role, viewer, want_on)

    def _set_pair(self, role: str, viewer: str, on: bool) -> None:
        if self._active.get((role, viewer), False) == on:
            return
        self._active[(role, viewer)] = on
        if on:
            self._robots[role].reason = ""   # 다음에 켤 때 옛 오류를 지운다
        self._send_robot(role, "camera", {"viewer": viewer, "on": on})
        if not on:
            self._deliver(viewer, {"kind": "rtc", "role": role, "bye": True})

    def _deliver(self, viewer: str, ev: dict) -> None:
        d = self._viewers.get(viewer)
        if d is not None:
            d(ev)

    def _validate_rtc(self, msg: dict) -> tuple[bool, object]:
        sdp = msg.get("sdp")
        if sdp is not None:
            ok = (isinstance(sdp, dict) and isinstance(sdp.get("type"), str)
                  and isinstance(sdp.get("sdp"), str) and len(sdp["sdp"]) <= MAX_SDP_BYTES)
            return (ok, {"sdp": sdp}) if ok else (False, "sdp")
        cand = msg.get("candidate")
        if cand is not None:
            ok = isinstance(cand, str) and len(cand) <= MAX_CANDIDATE_BYTES
            return (ok, {"candidate": cand, "sdpMLineIndex": msg.get("sdpMLineIndex")}) if ok else (False, "candidate")
        return False, "sdp/candidate 둘 다 없다"

    def _warn_once(self, key: str, text: str) -> None:
        if key in self._warned_once:
            return
        self._warned_once.add(key)
        self._warn(text)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_camera.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add stage/camera.py tests/test_stage_camera.py
git commit -m "feat(stage): CameraRelay — 시청자·로봇 카메라 시그널링 순수 로직"
```

---

### Task 4: `Director` — 대기모드(`_standby`), `solo_role` 일반화, `toggle_standby`

**Files:**
- Modify: `stage/director.py`
- Test: `tests/test_stage_director.py`

**Interfaces:**
- Produces: `Director.toggle_standby(role: str) -> None`. `Director.snapshot()` 에 `"standby"` 키 추가.
  `Director.solo_role` 은 `connected - standby` 기준으로 바뀐다(기존 시그니처 그대로, 동작만 바뀐다).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_director.py` 는 `Harness` 클래스(감독 하나를 만들고 `h.sent`/`h.warnings` 에
모은다, `h.d` 가 `Director` 인스턴스)와 `State`(`stage/machine.py`, 값: `IDLE`·`MC_SPEAKING`·
`DOCENT_SPEAKING`·`LISTENING`)를 이미 쓰고 있다. 그 관례 그대로 끝에 추가한다. `Director` 는
`on_connect(role)` 를 이미 갖고 있다(§ 기존 코드) — `Harness` 는 로봇 연결을 직접 흉내내지 않으므로
아래 테스트가 `h.d.on_connect(...)` 를 직접 부른다:

```python
def test_대기_진입은_solo_role을_남은_로봇으로_만든다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    assert h.d.solo_role is None
    h.d.toggle_standby("mc")
    assert h.d.solo_role == "docent"
    assert h.d.snapshot()["standby"] == ["mc"]


def test_대기_해제는_solo_role을_되돌린다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.toggle_standby("mc")
    h.d.toggle_standby("mc")
    assert h.d.solo_role is None
    assert h.d.snapshot()["standby"] == []


def test_둘_다_대기로_두는_것은_거절한다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.toggle_standby("mc")
    h.d.toggle_standby("docent")
    assert h.d.snapshot()["standby"] == ["mc"]
    assert any("진행할 로봇이 없다" in w for w in h.warnings)


def test_대기_전환은_말하던_것을_먼저_멈춘다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.start()
    assert h.d.state is State.MC_SPEAKING
    h.d.toggle_standby("docent")
    assert h.d.state is State.IDLE


def test_로봇이_끊기면_대기_목록에서도_지운다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.toggle_standby("mc")
    h.d.on_disconnect("mc")
    assert h.d.snapshot()["standby"] == []


def test_모르는_역할은_경고하고_바꾸지_않는다():
    h = Harness()
    h.d.toggle_standby("아무거나")
    assert h.d.snapshot()["standby"] == []
    assert any("모르는 역할" in w for w in h.warnings)


def test_대기_중이어도_기존_1인_모드_테스트는_그대로_돈다():
    """`_standby` 가 비어 있으면 `connected - standby == connected` 라 기존 동작이
    안 바뀐다는 것을 한 번 더 확인한다 — 회귀 방지용 스모크."""
    h = Harness()
    h.d.on_connect("mc")
    assert h.d.solo_role == "mc"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -k standby -v`
Expected: FAIL — `AttributeError: 'Director' object has no attribute 'toggle_standby'`

- [ ] **Step 3: 구현**

`stage/director.py` 상단 임포트에 추가:

```python
from stage.protocol import ROLES
```

`__init__` 의 `self._caps: dict[str, set[str]] = {}` 다음 줄에 추가:

```python
        # 대기모드에 들어간 역할. 새 상태기계를 만들지 않는다 — `solo_role` 이 이 값을
        # 보므로, 대기 진입은 그 로봇이 "끊겼다" 와 같은 모양으로 진행에서 빠진다
        # (재배정·마이크 재동기화까지 `on_disconnect` 와 같은 길을 탄다). 끊기면 지운다
        # (`_caps` 와 같은 수명 — 다시 붙는 앱은 새로 판단한다).
        self._standby: set[str] = set()
```

`solo_role` 프로퍼티를 고친다:

```python
    @property
    def solo_role(self) -> str | None:
        """진행에 쓸 수 있는 로봇이 한 대뿐이면 그 역할. 둘이거나 없으면 None.

        **연결됐지만 대기모드인 로봇은 빼고 센다** — 대기 진입이 "끊겼다" 와 같은 모양으로
        진행에서 빠지게 하는 지점이 여기 하나다. 이것은 **1인 모드**(한 대가 없을 때 남은
        한 대가 양쪽 대사를 읽는 폴백)다 — 운영 모드 `solo`(단독, `mode`/`set_mode`)와
        이름만 닮았지 다른 것이다.
        """
        active = self._connected - self._standby
        if len(active) == 1:
            return next(iter(active))
        return None
```

`on_disconnect` 안, `self._caps.pop(role, None)` 다음 줄에 추가:

```python
            self._standby.discard(role)
```

`toggle_standby` 새 메서드 추가(`set_mode` 근처, `_solo_refusal_locked` 앞이 자연스럽다):

```python
    def toggle_standby(self, role: str) -> None:
        """대기모드 on/off — 콘솔·대시보드 `z <역할>`.

        새 상태기계를 만들지 않는다: `solo_role` 판정이 `connected - standby` 를 보므로,
        대기 진입은 그 로봇이 "끊겼다" 와 같은 모양으로 진행에서 빠진다(재배정·마이크
        재동기화까지 `on_disconnect` 와 같은 자리에서 일어난다).

        **전환은 항상 먼저 멈춘다**(`set_mode` 와 같은 패턴, `_abort_locked()`) — 그 역할이
        지금 말하는 중인지 따로 검사하지 않는다(부분 중단이라는 새 개념을 만들지 않는다).
        상대 로봇이 말하던 줄도 함께 끊긴다 — `set_mode` 가 이미 받아들인 트레이드오프와 같다.

        **말하는 중 마이크가 열려 있던 로봇이 대기로 들어가도 그 마이크를 따로 닫지
        않는다** — `on_disconnect` 도 안 닫는다(같은 이유: `speak()` 가 다음 큐에서 양쪽을
        닫고, 그 전에는 서버의 리스너 검사(`solo_role` 아니면 `heard` 를 버린다)가 이미
        막는다). 대칭을 깨지 않는다.
        """
        with self._lock:
            if role not in ROLES:
                self._warn(f"모르는 역할이다: {role!r} — 대기모드를 바꾸지 않는다")
                return
            entering = role not in self._standby
            if entering:
                active_after = (self._connected - self._standby) - {role}
                if not active_after:
                    self._warn(
                        f"[{role}] 를 대기모드로 두면 진행할 로봇이 없다 — 바꾸지 않는다"
                    )
                    return
            self._abort_locked()
            if entering:
                self._standby.add(role)
            else:
                self._standby.discard(role)
            self._warn(f"[{role}] 대기모드 {'진입' if entering else '해제'}")
            self._emit([Command(to=role, type="standby", fields={"on": entering})])
            if self.solo_role is not None and self._machine.state is State.LISTENING:
                self._emit(self._machine.force_listening(self._who("mc")))
```

`snapshot()` 이 돌려주는 dict 에 한 줄 추가(`"solo_available": ...` 다음):

```python
                "standby": sorted(self._standby),
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_director.py -v`
Expected: 전부 PASS(기존 `solo_role`/1인 모드 테스트도 그대로 — `_standby` 가 빈 집합일 때
`connected - standby == connected` 라 동작이 안 바뀐다).

- [ ] **Step 5: 커밋**

```bash
git add stage/director.py tests/test_stage_director.py
git commit -m "feat(director): 대기모드 — solo_role 을 connected-standby 로 일반화"
```

---

### Task 5: `stage/console.py` — `z`(대기모드)·`c`(카메라) 명령

**Files:**
- Modify: `stage/console.py`
- Test: `tests/test_stage_console.py`

**Interfaces:**
- Consumes: Task 3 의 `CameraRelay.toggle`, Task 4 의 `Director.toggle_standby`.
- Produces: `dispatch(director, cmd, out, camera=None)` — `camera` 는 선택 인자(기존 호출부는
  그대로 돈다). `run_console(director, read=input, out=print, block=block_forever, camera=None)`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_console.py` 에 추가(파일의 기존 `가짜감독` 클래스를 재사용한다 — 먼저 읽고
`toggle_standby` 호출을 기록하는 메서드를 그 클래스에 보태거나, 새 가짜를 만든다):

```python
class _가짜카메라:
    def __init__(self):
        self.toggled = []

    def toggle(self, role):
        self.toggled.append(role)


def test_z_는_대기모드를_토글한다():
    d = 가짜감독()   # 기존 클래스 — toggle_standby 호출을 기록하도록 이 테스트에서 monkeypatch 하거나
                      # 가짜감독에 toggled_standby 리스트 + toggle_standby 메서드를 이미 보탰다고 가정.
    console.dispatch(d, "z mc", out=lambda m: None)
    assert d.toggled_standby == ["mc"]


def test_c_는_카메라를_토글한다():
    cam = _가짜카메라()
    console.dispatch(가짜감독(), "c docent", out=lambda m: None, camera=cam)
    assert cam.toggled == ["docent"]


def test_카메라_객체가_없으면_c_는_조용히_무시하지_않고_안내한다():
    out = []
    console.dispatch(가짜감독(), "c mc", out=out.append, camera=None)
    assert any("카메라" in m for m in out)
```

`가짜감독` 클래스에 `toggle_standby` 가 없으면 이 태스크에서 보탠다(파일 상단, 기존 `abort`/`next`
메서드 옆):

```python
    def toggle_standby(self, role):
        self.toggled_standby = getattr(self, "toggled_standby", [])
        self.toggled_standby.append(role)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_console.py -k "z_ or c_" -v`
Expected: FAIL — `z`/`c` 를 모르는 명령으로 처리해 `out` 에 "모르는 명령" 이 찍힌다.

- [ ] **Step 3: 구현**

`stage/console.py` 의 `HELP` 문자열에 두 줄 추가:

```python
  z <mc|docent>  대기모드 켜고 끄기
  c <mc|docent>  카메라 스트림 켜고 끄기
```

`dispatch` 시그니처와 본문을 고친다:

```python
def dispatch(director: Director, cmd: str, out, camera=None) -> None:
    """콘솔 명령 하나 — **대시보드도 이 함수를 부른다**, 명령 경로를 하나로 둔다."""
    if cmd == "s":
        director.start()
    elif cmd == "n":
        _stop_first(director)
        director.next()
    elif cmd == "p":
        _stop_first(director)
        director.previous()
    elif cmd == "r":
        _stop_first(director)
        director.start()
    elif cmd == "a":
        director.abort()
    elif cmd.startswith("g "):
        cue_id = cmd[2:].strip()
        if any(c["id"] == cue_id for c in director.cue_list()):
            _stop_first(director)
        director.goto(cue_id)
    elif cmd.startswith("l "):
        director.set_level(cmd[2:].strip())
    elif cmd.startswith("m "):
        director.set_mode(cmd[2:].strip())
    elif cmd.startswith("z "):
        director.toggle_standby(cmd[2:].strip())
    elif cmd.startswith("c "):
        if camera is None:
            out("  카메라 기능을 쓸 수 없다(이 감독에 카메라 중계가 없다)")
        else:
            camera.toggle(cmd[2:].strip())
    elif cmd == "?":
        out(HELP)
    elif cmd:
        out(f"모르는 명령: {cmd!r}  — ? 로 도움말")
```

`run_console` 도 `camera` 를 받아 넘긴다:

```python
def run_console(director: Director, read=input, out=print, block=block_forever, camera=None) -> None:
    out(HELP)
    while True:
        try:
            cmd = read("무대감독> ").strip().lower()
        except KeyboardInterrupt:
            return
        except EOFError:
            out(
                "표준입력이 없다 — 콘솔 없이 계속 돈다(진행은 관람객 발화로). "
                "종료는 Ctrl-C 또는 kill."
            )
            block()
            return
        if cmd in ("q", "quit"):
            return
        try:
            dispatch(director, cmd, out, camera=camera)
        except Exception as exc:  # noqa: BLE001
            out(f"  거절됨: {exc}")
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_console.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add stage/console.py tests/test_stage_console.py
git commit -m "feat(console): z(대기모드)·c(카메라) 명령 — 대시보드와 같은 경로"
```

---

### Task 6: `stage/server.py` — 허브를 안 타는 송신, 로봇 캡스·연결·rtc·오류를 relay 로

**Files:**
- Modify: `stage/server.py`
- Test: `tests/test_stage_server.py`

**Interfaces:**
- Consumes: Task 3 의 `CameraRelay`.
- Produces: `StageServer(..., camera: CameraRelay | None = None)`, 공개 속성 `server.camera`
  (넘기지 않으면 `StageServer` 가 스스로 하나 만든다 — 항상 존재한다).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_server.py` 끝에 추가(파일 상단의 `hello`/`recv`/`url_of` 도우미를 그대로 쓴다):

```python
from stage.camera import CameraRelay


def test_server는_camera_속성을_스스로_만든다(server):
    assert isinstance(server.camera, CameraRelay)


def test_hello의_caps가_camera로_전달된다(server):
    with connect(url_of(server)) as ws:
        _hello_caps(ws, "mc", ["camera"])
    assert server.camera.snapshot()["mc"]["available"] is True


def test_연결이_끊기면_camera에도_알린다(server):
    with connect(url_of(server)) as ws:
        _hello_caps(ws, "mc", ["camera"])
    for _ in range(50):
        if server.camera.snapshot()["mc"]["available"] is False:
            break
        time.sleep(0.02)
    assert server.camera.snapshot()["mc"]["available"] is False


def test_rtc는_camera로_라우팅되고_허브_이력에_안_쌓인다(server_hub):
    with connect(url_of(server_hub)) as mc:
        _hello_caps(mc, "mc", ["camera"])
        events = []
        vid = server_hub.camera.add_viewer(events.append)
        mc.send(json.dumps({"type": "rtc", "viewer": vid, "sdp": {"type": "offer", "sdp": "v=0"}}))
        for _ in range(50):
            if events:
                break
            time.sleep(0.02)
        assert events and events[0]["kind"] == "rtc"
        assert not any(k == "recv" and f.get("type") == "rtc" for k, f in server_hub.hub.events)
        assert not any(k == "sent" and f.get("type") == "rtc" for k, f in server_hub.hub.events)


def test_camera_오류는_camera로도_간다(server):
    with connect(url_of(server)) as ws:
        _hello_caps(ws, "mc", ["camera"])
        ws.send(json.dumps({"type": "error", "where": "camera", "detail": "파이프라인 실패"}))
        for _ in range(50):
            if "파이프라인 실패" in server.camera.snapshot()["mc"]["reason"]:
                break
            time.sleep(0.02)
        assert "파이프라인 실패" in server.camera.snapshot()["mc"]["reason"]
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_server.py -k "camera or rtc" -v`
Expected: FAIL — `AttributeError: 'StageServer' object has no attribute 'camera'`

- [ ] **Step 3: 구현**

`stage/server.py` 상단 임포트에 추가:

```python
from stage.camera import CameraRelay
```

`__init__` 시그니처에 `camera` 추가(끝, `on_level_change` 다음):

```python
        on_level_change: Callable[[str], None] | None = None,
        camera: CameraRelay | None = None,
    ) -> None:
```

본문의 `self.director = Director(...)` 다음에 추가:

```python
        self.camera = camera if camera is not None else CameraRelay(
            send_robot=self._send_raw, warn=warn,
        )
```

**단, `camera` 를 밖에서 넘긴 경우에도 `send_robot` 은 이 서버의 `_send_raw` 여야 한다** — 넘겨받은
`CameraRelay` 가 이미 다른 `send_robot` 으로 만들어졌다면 배선이 어긋난다. 이 태스크의 실기 배선
(Task 8)은 항상 `camera=None` 으로 두고 `StageServer` 가 스스로 만들게 한다 — 밖에서 만들어 넘기는
경로는 테스트 전용이다.

`_send` 메서드 옆에 허브를 안 타는 송신을 추가:

```python
    def _send_raw(self, role: str, type_: str, fields: dict) -> None:
        """`CameraRelay` 가 로봇에게 camera/rtc 를 보낼 때 쓴다. `_send` 와 달리 허브에
        싣지 않는다 — ICE·SDP 는 초당 수십 개·수 KB 라 이력 200칸을 밀어낸다."""
        with self._lock:
            ws = self._conns.get(role)
        if ws is None:
            self._warn(f"[{role}] 아직 붙지 않았다 — {type_} 를 버린다")
            return
        try:
            ws.send(encode(type_, **fields))
        except Exception as exc:
            self._warn(f"[{role}] 전송 실패({type(exc).__name__}: {exc})")
```

`handler()` 안, hello 처리에서 `caps = self._caps_field(role, msg)` 다음(기존 `self.director.on_hello(...)`
호출 옆)에 추가:

```python
                    self.camera.on_robot_hello(role, caps)
```

같은 함수의 `finally` 블록, `if is_current:` 안(`self.director.on_disconnect(role)` 다음)에 추가:

```python
                    self.camera.on_robot_disconnect(role)
```

`_dispatch` 에 `rtc` 분기를 추가하고(허브에 싣지 않는다 — `_publish` 를 부르지 않는다),
`error` 분기에서 `where == "camera"` 면 `camera.on_robot_error` 도 부른다:

```python
    def _dispatch(self, role: str, msg: dict) -> None:
        t = msg["type"]
        if t == "heard":
            ...(기존 그대로)
        elif t in ("speaking_ended", "speaking_started"):
            ...(기존 그대로)
        elif t == "error":
            where, detail = str(msg.get("where", "")), str(msg.get("detail", ""))
            self._publish("recv", role=role, type="error", fields={"where": where, "detail": detail})
            self.director.on_error(role, where, detail)
            if where == "camera":
                self.camera.on_robot_error(role, detail)
        elif t == "rtc":
            self.camera.on_robot_rtc(role, msg)
        else:
            self._warn(f"[{role}] 로봇이 보낼 수 없는 메시지다: {t}")
```

(`heard`/`speaking_*` 분기는 기존 코드를 그대로 두고 `error`/새 `rtc` 분기만 고친다 — 파일을 읽고
정확한 기존 본문 위에 최소로 덧붙인다.)

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_server.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add stage/server.py tests/test_stage_server.py
git commit -m "feat(server): camera 배선 — hello caps·연결·rtc·오류, 허브를 안 타는 raw 송신"
```

---

### Task 7: `stage/dashboard.py` — 시청자 등록, `rtc` 라우팅, 스냅샷에 `cameras`

**Files:**
- Modify: `stage/dashboard.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: Task 3 의 `CameraRelay`(덕 타이핑 — `add_viewer`/`remove_viewer`/`on_viewer_rtc`/`snapshot`).
- Produces: `DashboardServer(hub, director, camera=None, dispatch=console_dispatch, ...)`.
  `camera` 가 없으면(기존 호출부) 지금처럼 돈다 — 스냅샷에 `cameras` 가 안 실린다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_dashboard.py` 끝에 추가(기존 `dash` 픽스처·`_가짜감독`·`_served` 를 재사용한다):

```python
class _가짜카메라:
    def __init__(self):
        self._deliver = {}
        self._n = 0

    def add_viewer(self, deliver):
        self._n += 1
        vid = f"v{self._n}"
        self._deliver[vid] = deliver
        return vid

    def remove_viewer(self, viewer):
        self._deliver.pop(viewer, None)

    def on_viewer_rtc(self, viewer, msg):
        self.last_viewer_rtc = (viewer, msg)

    def snapshot(self):
        return {"mc": {"available": True, "enabled": True, "reason": ""},
                "docent": {"available": False, "enabled": True, "reason": "OFFLINE"}}


@pytest.fixture
def dash_cam(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>t</title>", encoding="utf-8")
    hub, d, cam, warned = DashboardHub(), 가짜감독(), _가짜카메라(), []
    ds = DashboardServer(hub, d, camera=cam, page=page, interval=0.05, warn=warned.append)
    with _served(ds) as (port, errors, finished):
        yield {"hub": hub, "d": d, "cam": cam, "port": port,
               "handler_errors": errors, "handler_finished": finished}


def test_스냅샷에_cameras가_실린다(dash_cam):
    with connect(f"ws://127.0.0.1:{dash_cam['port']}/ws") as ws:
        m = _recv_until(ws, "snapshot")
        assert m["cameras"] == dash_cam["cam"].snapshot()


def test_연결되면_시청자를_등록하고_닫히면_해제한다(dash_cam):
    with connect(f"ws://127.0.0.1:{dash_cam['port']}/ws") as ws:
        _recv_until(ws, "hello")
    dash_cam["handler_finished"].acquire(timeout=3)
    assert dash_cam["cam"]._deliver == {}


def test_rtc_메시지는_camera로_간다(dash_cam):
    with connect(f"ws://127.0.0.1:{dash_cam['port']}/ws") as ws:
        _recv_until(ws, "hello")
        ws.send(json.dumps({"rtc": {"role": "mc", "sdp": {"type": "answer", "sdp": "v=0"}}}))
        for _ in range(50):
            if getattr(dash_cam["cam"], "last_viewer_rtc", None):
                break
            time.sleep(0.02)
        viewer, msg = dash_cam["cam"].last_viewer_rtc
        assert msg == {"role": "mc", "sdp": {"type": "answer", "sdp": "v=0"}}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k "cameras or 시청자_등록 or rtc_메시지" -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'camera'`

- [ ] **Step 3: 구현**

`stage/dashboard.py` 의 `DashboardServer.__init__` 시그니처와 본문에 `camera` 추가:

```python
    def __init__(self, hub, director, camera=None, dispatch: Callable = console_dispatch,
                 page: pathlib.Path = PAGE, interval: float = SNAPSHOT_INTERVAL_S,
                 warn: Callable[[str], None] = print) -> None:
        self._hub = hub
        self._director = director
        self._camera = camera
        self._dispatch = dispatch
        self._page = page
        self._interval = interval
        self._warn = warn
```

`handler()` 안, `sub = self._hub.subscribe()` 다음에 시청자 등록을 추가:

```python
        sub = self._hub.subscribe()
        viewer = self._camera.add_viewer(self._deliver_maker(sub)) if self._camera is not None else None
```

`try`/`finally` 의 `finally: stop.set(); self._hub.unsubscribe(sub)` 를 고쳐 시청자도 해제한다:

```python
        finally:
            stop.set()
            self._hub.unsubscribe(sub)
            if self._camera is not None and viewer is not None:
                self._camera.remove_viewer(viewer)
```

클래스에 작은 도우미를 추가(허브 `Subscription` 의 `queue`/`dropped` 를 그대로 재사용한다 —
새 델리버리 경로를 안 만든다):

```python
    @staticmethod
    def _deliver_maker(sub):
        def deliver(ev: dict) -> None:
            try:
                sub.queue.put_nowait(ev)
            except queue.Full:
                sub.dropped += 1
        return deliver
```

`for raw in ws:` 루프를 고쳐 `{"rtc": ...}` 모양을 `{"cmd": ...}` 와 가른다. **`viewer` 가
`handler()` 의 지역변수라 새 메서드로 빼지 않고 이 자리에서 직접 처리한다**(기존 `_on_command`
호출은 명령 모양일 때만 그대로 쓴다):

```python
            threading.Thread(target=self._pump, args=(ws, sub, stop), daemon=True).start()
            for raw in ws:
                try:
                    obj = json.loads(raw)
                except (ValueError, TypeError):
                    self._warn(f"대시보드 메시지가 JSON 이 아니다 — 버린다: {str(raw)[:80]!r}")
                    continue
                if isinstance(obj, dict) and "rtc" in obj and self._camera is not None and viewer is not None:
                    self._camera.on_viewer_rtc(viewer, obj["rtc"])
                    continue
                self._on_command(raw)
```

`_pump`/`_safe_snapshot` 가 보내는 스냅샷에 `cameras` 를 덧붙인다. `_safe_snapshot` 을 고친다:

```python
    def _safe_snapshot(self) -> dict | None:
        try:
            snap = self._director.snapshot()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"대시보드 스냅샷 실패({type(exc).__name__}: {exc}) — 다음 주기에 다시 읽는다")
            return None
        if self._camera is not None:
            snap = {**snap, "cameras": self._camera.snapshot()}
        return snap
```

`handler()` 의 hello 전송에서도 `"snapshot": self._safe_snapshot()` 을 그대로 쓰므로(이미 있다)
따로 고칠 곳이 없다 — `_safe_snapshot` 한 곳만 고치면 hello·주기 스냅샷 둘 다 `cameras` 를 싣는다.

파일 상단에 `queue` 가 이미 import 돼 있는지 확인한다(있다 — `import queue`).

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -v`
Expected: 전부 PASS(기존 테스트도 `camera=None` 기본값으로 그대로 돈다)

- [ ] **Step 5: 커밋**

```bash
git add stage/dashboard.py tests/test_dashboard.py
git commit -m "feat(dashboard): 시청자 등록·rtc 라우팅·스냅샷에 cameras"
```

---

### Task 8: `stage/__main__.py` — 전부 잇는다

**Files:**
- Modify: `stage/__main__.py`
- Modify: `stage/dashboard.py`(`start_dashboard()` 자유 함수 — Task 7 은 `DashboardServer` 클래스만
  고쳤다, 이 태스크가 그 바깥 함수를 마저 고친다)
- Test: `tests/test_stage_main.py`

**Interfaces:**
- Consumes: Task 5(`console.dispatch(..., camera=...)`), Task 6(`server.camera`), Task 7
  (`DashboardServer(..., camera=...)`).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_main.py` 를 먼저 읽어 `가짜대시보드`/`monkeypatch.setattr(stage_main, "start_dashboard", ...)`
관례를 확인한 뒤, 다음을 추가한다:

```python
def test_main은_dashboard에_server_camera를_넘긴다(monkeypatch, ...):  # 기존 테스트의 인자·셋업을 그대로 재사용
    seen = {}

    def 가짜대시보드(hub, director, host, port, camera=None, warn=print):
        seen["camera"] = camera
        return None

    monkeypatch.setattr(stage_main, "start_dashboard", 가짜대시보드)
    # ... 기존 테스트처럼 run_console 을 가짜로 막고 main() 을 부른다 ...
    assert seen["camera"] is not None
```

(이 태스크는 기존 `test_stage_main.py` 의 셋업이 복잡하므로 — 예: stdin 가짜, `run_console` 가짜,
`start_llm_stt` 유무 — 정확한 몸체는 그 파일의 **가장 비슷한 기존 테스트**(대시보드가 뜨는지 보는
것)를 복사해 `camera` 확인 단언만 더한다. 새로 지어내지 않는다.)

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_main.py -k camera -v`
Expected: FAIL — `start_dashboard` 가 `camera` 인자를 안 받아 `TypeError`.

- [ ] **Step 3: 구현**

`stage/__main__.py` 에서 `server = StageServer(...)` 를 만든 뒤(`server.camera` 가 이미 존재한다 —
Task 6 에서 `StageServer.__init__` 이 스스로 만든다), `dash = start_dashboard(...)` 호출에 `camera` 를
더한다. 콘솔 실행부 `run_console(server.director)` 도 `camera` 를 넘긴다.

`stage/dashboard.py::start_dashboard` 함수 시그니처도 `camera` 를 받아 `DashboardServer` 에 넘기도록
고친다(Task 7 에서 `DashboardServer` 만 고쳤다면 여기서 마저 고친다):

```python
def start_dashboard(hub, director, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                    camera=None, warn: Callable[[str], None] = print):
    """대시보드를 띄운다. **실패해도 감독·콘솔은 그대로 돈다** — 경고하고 None."""
    ds = DashboardServer(hub, director, camera=camera, warn=warn)
    ...
```

`stage/__main__.py` 의 두 호출부를 고친다:

```python
    dash = start_dashboard(
        hub, server.director,
        dash_host,
        dash_port,
        camera=server.camera,
        warn=terminal,
    )
    ...
    try:
        run_console(server.director, camera=server.camera)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_main.py tests/test_dashboard.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add stage/__main__.py stage/dashboard.py tests/test_stage_main.py
git commit -m "feat(stage): __main__ 배선 — server.camera 를 대시보드·콘솔에 넘긴다"
```

---

### Task 9: `camera_in.py` — RTC 스트림과의 배타 처리

**Files:**
- Modify: `apps/voice_chat/voice_chat/camera_in.py`
- Test: `tests/test_camera_in.py`

**Interfaces:**
- Produces: `camera_in.note_rtc_active(active: bool) -> None` — 모듈 전역 플래그.
  `camera_in.grab_jpeg()` 는 그 플래그가 True 면 경고하고 None.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_camera_in.py` 끝에 추가:

```python
def test_rtc_스트림_중에는_비전_캡처가_물러난다(monkeypatch, capsys):
    _linux(monkeypatch)
    camera_in.note_rtc_active(True)
    try:
        assert camera_in.grab_jpeg() is None
        assert "카메라" in capsys.readouterr().out
    finally:
        camera_in.note_rtc_active(False)


def test_rtc_스트림이_꺼지면_평소대로_캡처한다(monkeypatch):
    _linux(monkeypatch)
    camera_in.note_rtc_active(False)
    monkeypatch.setattr(camera_in, "_open", lambda: "PIPE")
    monkeypatch.setattr(camera_in, "_pull", lambda: JPEG)
    assert camera_in.grab_jpeg() == JPEG
```

이 파일 상단의 `_reset` autouse 픽스처도 `_rtc_active` 를 같이 되돌리게 고친다(다른 테스트가
`note_rtc_active(True)` 를 남긴 채 끝나도 다음 테스트로 새지 않게):

```python
@pytest.fixture(autouse=True)
def _reset():
    camera_in._pipe = None
    camera_in._rtc_active = False
    yield
    camera_in._pipe = None
    camera_in._rtc_active = False
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_camera_in.py -k rtc -v`
Expected: FAIL — `AttributeError: module 'camera_in' has no attribute 'note_rtc_active'`

- [ ] **Step 3: 구현**

`apps/voice_chat/voice_chat/camera_in.py` 상단 전역 변수 옆(`_pipe = None` 근처)에 추가:

```python
_rtc_active = False


def note_rtc_active(active: bool) -> None:
    """`camera_rtc.RtcStreamer` 가 스트림을 켜고 끌 때 부른다. 카메라는 한 프로세스만
    열 수 있어 스트림 중에는 비전 캡처가 물러난다 — 그 파이프라인이 이미 최신 프레임을
    돌려주므로(4단계에서 공유), 지금은 단순히 비전 캡처를 쉰다."""
    global _rtc_active
    _rtc_active = active
```

`grab_jpeg()` 맨 앞에 검사를 추가(`if not _enabled():` 앞):

```python
def grab_jpeg() -> bytes | None:
    """프레임 한 장을 JPEG 로. 실패하면 **None** — 대화는 계속된다."""
    global _pipe, _last
    if _rtc_active:
        print("  [카메라] RTC 스트림 중이라 비전 캡처를 쉰다", flush=True)
        return None
    if not _enabled():
        return None
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_camera_in.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add apps/voice_chat/voice_chat/camera_in.py tests/test_camera_in.py
git commit -m "feat(camera_in): RTC 스트림 중에는 비전 캡처가 물러난다"
```

---

### Task 10: `camera_rtc.py` — 로봇의 WebRTC 스트리머 (새 모듈)

**Files:**
- Create: `apps/voice_chat/voice_chat/camera_rtc.py`
- Test: `tests/test_camera_rtc.py`

**Interfaces:**
- Produces: `RtcStreamer(send_rtc: Callable[[str, dict], None], warn=print)`. 공개 메서드:
  `available() -> bool`, `start_viewer(viewer: str) -> None`, `stop_viewer(viewer: str) -> None`,
  `on_remote(viewer: str, payload: dict) -> None`, `stop_all() -> None`.
- Consumes: Task 9 의 `camera_in.note_rtc_active`.

**스파이크 근거**: `docs/lessons.md` 의 PyGObject 함정(`reply` 를 붙잡고, SDP 텍스트는
`set-local-description` 전에 뽑는다)을 그대로 따른다 — 스파이크 코드(`spike_robot.py`, 버렸다)의
offer 생성 부분이 검증된 순서다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_camera_rtc.py` 새로 작성 — **네트워크·실제 카메라 없이** `available()`과 파이프라인
문자열 조립만 가짜 GStreamer 요소 조회기로 시험한다(실제 송수신 통합 시험은 Step 3b, 맥 GStreamer
가 있을 때만 돈다):

```python
"""RtcStreamer — 요소 존재 여부·파이프라인 조립은 가짜로, 실제 송수신은 맥 GStreamer 로.

`available()`/파이프라인 문자열은 GStreamer 가 전혀 없어도 시험한다(가짜 조회기).
송수신 통합 시험(Step 3b)은 `Gst.ElementFactory.find` 로 실제 요소가 있는지 보고,
없으면 skip — 로봇에서만 도는 `v4l2h264enc` 등은 여기서 못 돈다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import camera_rtc  # noqa: E402


def _finder(present: set[str]):
    return lambda name: name in present


def test_인코더도_소스도_없으면_불가():
    assert camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(set())).available() is False


def test_webrtcbin이_없으면_불가():
    present = {"libcamerasrc", "v4l2h264enc", "rtph264pay", "h264parse"}
    assert camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present)).available() is False


def test_하드웨어_인코더_없이도_x264enc면_가능():
    present = {"libcamerasrc", "x264enc", "rtph264pay", "h264parse", "webrtcbin"}
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    assert st.available() is True
    assert st._encoder_name() == "x264enc"


def test_하드웨어_인코더가_있으면_그걸_먼저_쓴다():
    present = {"libcamerasrc", "v4l2h264enc", "x264enc", "rtph264pay", "h264parse", "webrtcbin"}
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    assert st._encoder_name() == "v4l2h264enc"


def test_파이프라인_문자열에_기본값이_들어간다(monkeypatch):
    present = {"libcamerasrc", "v4l2h264enc", "rtph264pay", "h264parse", "webrtcbin"}
    monkeypatch.delenv("REACHY_CAMERA_STREAM_WIDTH", raising=False)
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    chain = st._pipeline_str()
    assert "width=640" in chain and "height=480" in chain and "framerate=15" in chain
    assert "video_bitrate=2000000" in chain


def test_환경변수로_해상도를_바꾼다(monkeypatch):
    present = {"libcamerasrc", "v4l2h264enc", "rtph264pay", "h264parse", "webrtcbin"}
    monkeypatch.setenv("REACHY_CAMERA_STREAM_WIDTH", "320")
    monkeypatch.setenv("REACHY_CAMERA_STREAM_HEIGHT", "240")
    st = camera_rtc.RtcStreamer(send_rtc=lambda *a: None, find=_finder(present))
    assert "width=320" in st._pipeline_str() and "height=240" in st._pipeline_str()
```

`config` 모듈(같은 폴더)이 `os.environ` 을 먼저 본다는 것을 이미 알고 있으므로
(`apps/voice_chat/voice_chat/config.py`), `_pipeline_str` 은 `config.get(...)` 을 쓴다 — 위 테스트의
`monkeypatch.setenv` 가 바로 먹는다.

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_camera_rtc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'camera_rtc'`

- [ ] **Step 3: 구현**

`apps/voice_chat/voice_chat/camera_rtc.py` 새로 작성:

```python
"""로봇 카메라 → 브라우저 WebRTC(H.264). `camera_in.py`(JPEG 스냅샷)와 파이프라인을
나눠 쓰지 않는다 — 배타는 `camera_in.note_rtc_active` 가 맡는다.

**파이프라인 하나를 시청자가 나눠 쓴다.** 첫 시청자에서 소스·인코더·페이로더·`tee` 를
세우고, 시청자마다 `tee → queue → webrtcbin` 분기를 붙인다. 마지막 시청자가 나가면
파이프라인을 NULL 로 내린다.

**PyGObject 함정**(`docs/lessons.md`, 스파이크 실측): offer 를 만들 때 `reply =
promise.get_reply()` 로 **붙잡고**, SDP 텍스트는 `set-local-description` 을 부르기
**전에** 뽑는다. 한 줄로 꺼내면 SDP 가 비거나(`t=0 0`) 프로세스가 로그 없이 죽는다.

기본값(스파이크 실측, 사회자 로봇 640x480@15fps 에서 전체 CPU +4.2%p):
`REACHY_CAMERA_STREAM_WIDTH/HEIGHT/FPS/KBPS` = 640/480/15/2000.
"""

import threading
from typing import Callable

import config

_ENCODER_LADDER = ("v4l2h264enc", "x264enc", "openh264enc")
_REQUIRED = ("rtph264pay", "h264parse", "webrtcbin")


def _default_find(name: str) -> bool:
    """실제 GStreamer 요소 조회 — 기본 구현. 테스트는 가짜 `find` 를 주입한다."""
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    if not Gst.is_initialized():
        Gst.init(None)
    return Gst.ElementFactory.find(name) is not None


class RtcStreamer:
    def __init__(self, send_rtc: Callable[[str, dict], None],
                 find: Callable[[str], bool] = _default_find,
                 warn: Callable[[str], None] = print) -> None:
        self._send_rtc = send_rtc
        self._find = find
        self._warn = warn
        self._pipe = None
        self._webrtcbins: dict[str, object] = {}
        self._lock = threading.Lock()

    # ── 가능 여부 ─────────────────────────────────────────────────
    def available(self) -> bool:
        if config.get("REACHY_VISION", "1").lower() in ("0", "false", "no"):
            return False
        if not self._find(config.get("REACHY_CAMERA_SRC", "libcamerasrc").split()[0]):
            return False
        if self._encoder_name() is None:
            return False
        return all(self._find(n) for n in _REQUIRED)

    def _encoder_name(self) -> str | None:
        for name in _ENCODER_LADDER:
            if self._find(name):
                if name != "v4l2h264enc":
                    self._warn(
                        f"  [카메라] 하드웨어 H264 인코더가 없다 — {name} 로 물러난다(CPU 를 문다)"
                    )
                return name
        return None

    # ── 파이프라인 조립 ───────────────────────────────────────────
    def _pipeline_str(self) -> str:
        src = config.get("REACHY_CAMERA_SRC", "libcamerasrc")
        w = config.get("REACHY_CAMERA_STREAM_WIDTH", "640")
        h = config.get("REACHY_CAMERA_STREAM_HEIGHT", "480")
        fps = config.get("REACHY_CAMERA_STREAM_FPS", "15")
        kbps = config.get("REACHY_CAMERA_STREAM_KBPS", "2000")
        encoder = self._encoder_name()
        source = (
            f"{src} ! video/x-raw,width={w},height={h},framerate={fps}/1,format=YUY2,"
            f"colorimetry=bt709,interlace-mode=progressive"
            if src.split()[0] == "libcamerasrc"
            else f"{src} ! video/x-raw,width={w},height={h},framerate={fps}/1"
        )
        return (
            f"{source} "
            f'! {encoder} extra-controls="controls,repeat_sequence_header=1,'
            f'video_bitrate={int(kbps) * 1000},h264_i_frame_period={fps}" '
            f"! video/x-h264,stream-format=byte-stream,alignment=au,"
            f"level=(string)3.1,profile=(string)constrained-baseline "
            f"! h264parse ! rtph264pay config-interval=-1 pt=96 aggregate-mode=zero-latency "
            f"! application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000 "
            f"! tee name=camtee"
        )

    # ── 시청자 ────────────────────────────────────────────────────
    def start_viewer(self, viewer: str) -> None:
        import camera_in
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstWebRTC", "1.0")
        from gi.repository import Gst, GstWebRTC  # noqa: F401

        with self._lock:
            if viewer in self._webrtcbins:
                return
            if self._pipe is None:
                if not self.available():
                    self._warn("  [카메라] 스트림을 열 수 없다(available()=False)")
                    return
                camera_in.close()
                camera_in.note_rtc_active(True)
                if not Gst.is_initialized():
                    Gst.init(None)
                self._pipe = Gst.parse_launch(self._pipeline_str())
                self._pipe.set_state(Gst.State.PLAYING)
            tee = self._pipe.get_by_name("camtee")
            queue = Gst.ElementFactory.make("queue")
            queue.set_property("leaky", 2)  # downstream — 느린 시청자가 다른 시청자를 안 막는다
            wb = Gst.ElementFactory.make("webrtcbin")
            wb.set_property("bundle-policy", "max-bundle")
            self._pipe.add(queue)
            self._pipe.add(wb)
            queue.link(wb)
            tee.link(queue)
            queue.sync_state_with_parent()
            wb.sync_state_with_parent()
            wb.connect("on-negotiation-needed", lambda e, v=viewer: self._make_offer(v, e))
            wb.connect("on-ice-candidate", lambda e, m, c, v=viewer: self._send_rtc(
                v, {"candidate": c, "sdpMLineIndex": m}))
            self._webrtcbins[viewer] = wb

    def stop_viewer(self, viewer: str) -> None:
        import camera_in
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        with self._lock:
            wb = self._webrtcbins.pop(viewer, None)
            if wb is None:
                return
            wb.set_state(Gst.State.NULL)
            self._pipe.remove(wb)
            if not self._webrtcbins:
                self._pipe.set_state(Gst.State.NULL)
                self._pipe = None
                camera_in.note_rtc_active(False)

    def stop_all(self) -> None:
        for viewer in list(self._webrtcbins):
            self.stop_viewer(viewer)

    def on_remote(self, viewer: str, payload: dict) -> None:
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstSdp", "1.0")
        gi.require_version("GstWebRTC", "1.0")
        from gi.repository import Gst, GstSdp, GstWebRTC

        wb = self._webrtcbins.get(viewer)
        if wb is None:
            return
        if "sdp" in payload:
            ok, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(payload["sdp"]["sdp"].encode(), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            wb.emit("set-remote-description", answer, Gst.Promise.new())
        elif "candidate" in payload and payload["candidate"]:
            wb.emit("add-ice-candidate", payload.get("sdpMLineIndex") or 0, payload["candidate"])

    # ── 내부 ──────────────────────────────────────────────────────
    def _make_offer(self, viewer: str, webrtcbin) -> None:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        def on_offer(promise, _):
            # **reply 를 붙잡는다.** 한 줄로 꺼내면 SDP 메모리가 풀린다(PyGObject 함정).
            reply = promise.get_reply()
            offer = reply.get_value("offer")
            text = offer.sdp.as_text()   # set-local-description **전에** 뽑는다.
            webrtcbin.emit("set-local-description", offer, Gst.Promise.new())
            self._send_rtc(viewer, {"sdp": {"type": "offer", "sdp": text}})

        webrtcbin.emit("create-offer", None, Gst.Promise.new_with_change_func(on_offer, None))
```

- [ ] **Step 3b(선택, 맥에서만): 실제 송수신 통합 시험**

`tests/test_camera_rtc.py` 에 추가(요소가 없으면 skip):

```python
def _has(name):
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    if not Gst.is_initialized():
        Gst.init(None)
    return Gst.ElementFactory.find(name) is not None


@pytest.mark.skipif(not _has("x264enc") or not _has("webrtcbin"),
                     reason="이 맥에 x264enc/webrtcbin 이 없다")
def test_videotestsrc로_실제_프레임이_간다(monkeypatch):
    """videotestsrc(카메라 없이) + x264enc 로 실제 GStreamer 파이프라인을 돌려, 테스트
    수신측 webrtcbin 이 프레임을 디코딩하는지 본다. 로봇 전용 요소(libcamerasrc·
    v4l2h264enc)는 안 쓴다 — 이 맥에 없다."""
    monkeypatch.setenv("REACHY_CAMERA_SRC", "videotestsrc is-live=true")
    # 이 시험은 실제 Gst 메인루프·오퍼/앤서 교환이 필요해 상당히 길다 — 최소 골격만
    # 여기 둔다. 기존 스파이크(offer_probe.py, 버렸다)의 방식을 참고해 로봇 쪽 흉내
    # webrtcbin(테스트 수신측)을 만들고 SDP 를 주고받는다. 자세한 구현은 이 태스크를
    # 맡는 실행자가 스파이크의 검증된 흐름(오퍼 → 앤서 → ICE → connected)을 그대로
    # 옮긴다 — 새로 설계하지 않는다.
    pytest.skip("이 스텝은 수동 검증으로 대신한다 — 최종 검증(Task 13)이 실기로 확인한다")
```

(이 서브스텝은 **선택**이다 — 실제 GStreamer 메인루프 동기화는 pytest 안에서 불안정하기 쉽다.
스킵해도 Task 13 의 실기 최종 검증이 같은 것을 실물로 확인한다. 실행자가 시간이 되면 스파이크의
`spike_robot.py`/`spike_page.html` 흐름을 재현해 채워도 좋다 — 그때도 새로 설계하지 않는다.)

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_camera_rtc.py -v`
Expected: 전부 PASS(또는 skip 표시된 것 제외 PASS)

- [ ] **Step 5: 커밋**

```bash
git add apps/voice_chat/voice_chat/camera_rtc.py tests/test_camera_rtc.py
git commit -m "feat(camera_rtc): 로봇 WebRTC 스트리머 — 인코더 사다리, PyGObject 함정 반영"
```

---

### Task 11: `main.py` — 카메라·대기모드 콜백 배선

**Files:**
- Modify: `apps/voice_chat/voice_chat/main.py`
- Modify: `apps/voice_chat/voice_chat/stage_client.py`(`StageClient.__init__` 의 `handlers` 를
  선택 인자로, `set_handlers()` 추가 — 아래 "깨끗한 길" 참고)
- Test: `tests/test_stage_role.py`(기존 파일 — `stage_run`/`Handlers` 배선을 이미 다룬다)
- Test: `tests/test_stage_client.py`(`set_handlers` 최소 확인 하나 추가)

**Interfaces:**
- Consumes: Task 2 의 `Handlers`, Task 10 의 `RtcStreamer`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_stage_role.py` 를 먼저 읽어 `Handlers(...)` 를 직접 구성해 보는 기존 테스트 스타일을
확인한 뒤(예: `test_stage_role.py:345` 부근의 `Handlers(...)` 사용), 아래를 그 스타일로 추가한다:

```python
def test_stage_run은_카메라와_대기모드_핸들러를_배선한다(monkeypatch):
    """실제 로봇·소켓 없이 `stage_run` 안에서 만들어지는 Handlers 를 가로챈다."""
    captured = {}

    class 가짜StageClient:
        def __init__(self, url, role, handlers, **kw):
            captured["handlers"] = handlers
            captured["caps"] = kw.get("caps")

        def run(self, should_stop):
            pass

    monkeypatch.setattr(main_mod, "StageClient", 가짜StageClient)
    # ... 기존 test_stage_role.py 가 stage_run 을 부르는 셋업(가짜 reachy_mini, stop_event 등)을
    # 그대로 재사용한다 — 파일을 읽고 그 패턴을 복사한다.
    ...
    assert callable(captured["handlers"].on_camera)
    assert callable(captured["handlers"].on_rtc)
    assert callable(captured["handlers"].on_standby)
    assert captured["caps"] == ["camera"] or captured["caps"] == []
```

(정확한 셋업은 `tests/test_stage_role.py` 의 기존 `stage_run` 호출 테스트를 그대로 베낀다 — 그
파일이 이미 가짜 `reachy_mini`·`stop_event`·환경변수를 어떻게 만드는지 안다. 새로 설계하지 않는다.)

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_stage_role.py -k 카메라와_대기 -v`
Expected: FAIL — `Handlers(...)` 호출에 `on_camera` 등이 없어 `TypeError`.

- [ ] **Step 3a: `stage_client.py` — 핸들러를 나중에 채울 수 있게 한다**

**왜 필요한가**: `RtcStreamer(send_rtc=client.rtc, ...)` 는 이미 만들어진 `client` 가 있어야
하는데, 지금 `StageClient(...)` 생성자는 `Handlers` 를 **그 자리에서** 요구한다. `Handlers` 안의
`on_camera`/`on_rtc` 는 `RtcStreamer` 를 참조해야 하므로 "`client` 가 있어야 `RtcStreamer` 를
만들고, `RtcStreamer` 가 있어야 `Handlers` 를 만들고, `Handlers` 가 있어야 `client` 를 만든다"
는 순환이 생긴다. `StageClient` 가 핸들러 없이 만들어지고 나중에 채워지게 해서 끊는다.

`apps/voice_chat/voice_chat/stage_client.py::StageClient.__init__` 의 `handlers: Handlers` 를
`handlers: Handlers | None = None` 으로 바꾸고, 메서드를 하나 추가한다(`error()` 옆):

```python
    def set_handlers(self, handlers: Handlers) -> None:
        """`Handlers` 가 이 클라이언트 자신(`self.rtc` 등)을 참조해야 할 때, 생성 뒤에
        채운다 — `main.py::stage_run` 이 `RtcStreamer(send_rtc=client.rtc, ...)` 를 먼저
        만들고 그 뒤에 `Handlers` 를 조립하는 이유가 이것이다(순환을 끊는다).
        `run()` 을 부르기 **전에** 반드시 이 메서드로 채워야 한다 — 여기서는 `None` 검사를
        하지 않는다(배선 순서로 보장한다, 잘못되면 `_on_raw` 에서 `AttributeError` 로
        바로 드러난다)."""
        self._h = handlers
```

`tests/test_stage_client.py` 에 최소 확인 하나를 더한다:

```python
def test_핸들러는_나중에_채울_수_있다():
    got, handlers = collector()
    client = StageClient("ws://x", "mc", None)
    client.set_handlers(handlers)
    ws = FakeWS(inbox=[{"type": "abort"}])
    n = [0]

    def should_stop():
        n[0] += 1
        return n[0] > 1

    client.run(should_stop=should_stop, connect_fn=lambda url: ws)
    assert ("abort",) in got
```

- [ ] **Step 3b: `main.py` — 순서대로 조립한다**

`apps/voice_chat/voice_chat/main.py` 상단 임포트에 추가:

```python
from camera_rtc import RtcStreamer
```

`make_abort` 근처(같은 "감독 지시를 로봇 동작으로 잇는 팩토리" 자리)에 새 팩토리 두 개를 추가한다:

```python
def make_camera_handlers(client, log=print):
    """카메라 시청 시작/끊기·원격 SDP·ICE 를 `RtcStreamer` 로 잇는다.

    `client.rtc` 로 로봇→감독 송신을 한다 — `RtcStreamer` 는 소켓을 모른다.
    """
    streamer = RtcStreamer(send_rtc=client.rtc, warn=log)

    def on_camera(viewer: str, on: bool) -> None:
        (streamer.start_viewer if on else streamer.stop_viewer)(viewer)

    def on_rtc(viewer: str, payload: dict) -> None:
        streamer.on_remote(viewer, payload)

    return streamer, on_camera, on_rtc


def make_standby_worker(reachy_mini, speaker, player, log=print):
    """대기모드 진입/해제. **블로킹 SDK 호출을 감독 메시지 수신 스레드에서 안 돌린다**
    — `SayRunner` 와 같은 이유로 작은 워커 스레드에 맡긴다. 순서는 `reachy.sh` 의
    `robot_wake()` 와 같다(기상: 모터 켜기 → 3초 → wake_up)."""
    lock = threading.Lock()

    def enter():
        speaker.stop()
        if player is not None:
            player.cancel()
        with lock:
            reachy_mini.goto_sleep()
            reachy_mini.disable_motors()
        log("  [대기모드 진입]")

    def exit_():
        with lock:
            reachy_mini.enable_motors()
            time.sleep(3)
            reachy_mini.wake_up()
        log("  [대기모드 해제]")

    def on_standby(on: bool) -> None:
        threading.Thread(target=(enter if on else exit_), daemon=True).start()

    return on_standby
```

(`time` 이 파일 상단에서 이미 import 돼 있는지 확인한다 — 없으면 `import time` 을 더한다.)

`stage_run` 함수 본문의 `client = StageClient(...)` 조립 부분을 아래 순서로 바꾼다 — **`client` 를
핸들러 없이 먼저 만들고, 카메라·대기모드 팩토리를 그 뒤에, `Handlers` 조립을 가장 마지막에** 한다:

```python
        say_runner = SayRunner(speak_one)
        on_mic = make_mic_sink(mic_open, has_listener=lambda: listener_alive(voice_thread))

        # caps: 이 로봇이 카메라 스트림을 실제로 열 수 있을 때만 싣는다(재배포 안 된
        # 옛 앱은 아예 안 실어 감독이 그 로봇에 camera 지시를 보내지 않는다).
        caps = ["camera"] if RtcStreamer(send_rtc=lambda *a: None).available() else []

        client = StageClient(
            url, role, None,   # 핸들러는 카메라 팩토리가 client.rtc 를 참조한 뒤 채운다
            unit_id=_unit_id(reachy_mini),
            version=_sdk_version(),
            caps=caps,
        )
        camera_streamer, on_camera, on_rtc = make_camera_handlers(client)
        on_standby = make_standby_worker(reachy_mini, speaker, player)
        client.set_handlers(Handlers(
            on_say=say_runner.on_say,
            on_mic=on_mic,
            on_gaze=lambda target: print(f"  [시선 {target}]"),
            on_abort=make_abort(speaker, player),
            on_camera=on_camera,
            on_rtc=on_rtc,
            on_standby=on_standby,
        ))
```

아래로 이어지는 `voice_thread = threading.Thread(...)` 와 `client.run(should_stop=stop_event.is_set)`
은 그대로 둔다. **`client.run()` 이 끝난 뒤**(감독 연결이 끊기거나 stop_event) `camera_streamer.stop_all()`
을 불러 파이프라인을 정리한다 — `client.run(...)` 다음 줄에 추가:

```python
        client.run(should_stop=stop_event.is_set)
        camera_streamer.stop_all()
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_stage_role.py tests/test_stage_client.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add apps/voice_chat/voice_chat/main.py apps/voice_chat/voice_chat/stage_client.py tests/test_stage_role.py
git commit -m "feat(main): 카메라·대기모드 핸들러 배선, hello.caps 로 카메라 지원 알림"
```

---

### Task 12: `dashboard_page.html` — 영상·카메라 버튼·대기모드 버튼

**Files:**
- Modify: `stage/dashboard_page.html`
- Test: `tests/test_dashboard_page.py`

**Interfaces:**
- Consumes: Task 7 의 스냅샷 `cameras` 필드, Task 4 의 스냅샷 `standby` 필드.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_dashboard_page.py` 끝에 추가(`IDS` 목록에도 새 id 를 더한다 — 파일 상단):

```python
def test_카메라_video_요소가_있다():
    src = _src()
    assert 'id="vid-mc"' in src and "<video" in src
    assert 'id="vid-docent"' in src


def test_카메라_켜기_끄기_버튼이_c_명령을_보낸다():
    src = _src()
    assert re.search(r'sendCmd\(\s*"c\s*"\s*\+\s*"mc"', src) or "sendCmd(\"c \" + role" in src


def test_대기모드_버튼이_z_명령을_보낸다():
    src = _src()
    assert "sendCmd(\"z \" + role" in src or re.search(r'sendCmd\(\s*"z\s*"', src)


def test_rtc_메시지_kind를_처리한다():
    src = _src()
    handle = _css_rule  # 재사용 안 함, 그냥 문자열 검사
    assert '"rtc"' in src and "RTCPeerConnection" in src


def test_스냅샷의_cameras_사유를_칸에_표시한다():
    src = _src()
    assert "s.cameras" in src or "snap.cameras" in src
```

(위 assert 들은 **정확한 변수명까지 강제하지 않는다** — JS 구현이 자유롭게 짤 수 있도록 느슨한
패턴을 쓴다. 실행자가 실제로 짠 변수명에 맞춰 테스트 표현을 조정해도 된다 — 핵심은 "video 요소
존재"·"c/z 명령을 실제로 보낸다"·"rtc 종류를 안다"·"cameras 사유를 읽는다" 네 가지가 참인지다.)

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python -m pytest tests/test_dashboard_page.py -k "카메라 or 대기모드 or rtc_메시지 or cameras_사유" -v`
Expected: FAIL

- [ ] **Step 3: 구현**

`stage/dashboard_page.html` 의 CAM 칸 안, 기존 `<span class="cam-placeholder">...` 줄들을 **지우지
않고 그 옆에** `<video>` 를 추가한다(자리표시자는 연결 전 기본으로 보이고, 영상이 뜨면 JS 가 감춘다).
CAM 1(사회자) 칸 예시 — CAM 2(도슨트)도 같은 모양으로 `vid-docent`/`mon-docent` 로 고친다:

```html
    <div class="cam offline" id="mon-mc">
      <span class="cam-label">CAM 1 · 사회자</span>
      <span class="tally offline" id="tag-mc">OFFLINE</span>
      <video id="vid-mc" class="cam-video" autoplay muted playsinline hidden></video>
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#3A4350" stroke-width="1.6"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="3" y="6" width="18" height="13" rx="2"></rect>
        <circle cx="12" cy="12.5" r="3.5"></circle>
        <path d="M8 6l1.5-2h5L16 6"></path>
      </svg>
      <span class="cam-placeholder" id="cam-reason-mc">[사회자 카메라 영상 — 실기 연결 후]</span>
      <span class="mic" id="mic-mc">MIC —</span>
      <div class="cam-controls">
        <button type="button" class="cam-toggle" id="cam-toggle-mc">카메라 끄기</button>
        <button type="button" class="standby-toggle" id="standby-toggle-mc">대기모드</button>
      </div>
    </div>
```

CSS 추가(`.mic` 규칙 다음):

```css
  .cam-video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
               border-radius: 6px 6px 0 0; }
  .cam-video[hidden] { display: none; }
  .cam-controls { position: absolute; bottom: 8px; right: 8px; display: flex; gap: 6px; z-index: 1; }
  .cam-controls button { font-size: 11px; padding: 3px 8px; border-radius: 4px; border: 1px solid #3A4350;
                          background: #1C222B; color: #C9CFD6; }
```

`<script>` 안, 상태 변수 선언부 근처에 추가:

```javascript
var camPeers = {};  // role -> RTCPeerConnection
var camNoFrameTimer = {};  // role -> setTimeout id (끊김 판정)

function ensurePeer(role) {
  if (camPeers[role]) return camPeers[role];
  var pc = new RTCPeerConnection({ iceServers: [] });
  var video = document.getElementById("vid-" + role);
  pc.ontrack = function (ev) {
    video.srcObject = ev.streams[0] || new MediaStream([ev.track]);
    video.hidden = false;
    document.getElementById("cam-reason-" + role).hidden = true;
  };
  pc.onicecandidate = function (ev) {
    if (!ev.candidate) return;
    ws.send(JSON.stringify({ rtc: { role: role, candidate: ev.candidate.candidate,
                                     sdpMLineIndex: ev.candidate.sdpMLineIndex } }));
  };
  pc.onconnectionstatechange = function () {
    if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
      requestCamRestart(role);
    }
  };
  camPeers[role] = pc;
  return pc;
}

function requestCamRestart(role) {
  video_hide(role);
  ws.send(JSON.stringify({ rtc: { role: role, restart: true } }));
}

function video_hide(role) {
  var v = document.getElementById("vid-" + role);
  v.hidden = true;
  v.srcObject = null;
}

function handleRtc(msg) {
  var role = msg.role;
  if (!role) return;
  if (msg.bye) {
    var pc = camPeers[role];
    if (pc) { pc.close(); delete camPeers[role]; }
    video_hide(role);
    return;
  }
  var pc = ensurePeer(role);
  if (msg.sdp) {
    pc.setRemoteDescription(msg.sdp).then(function () {
      return pc.createAnswer();
    }).then(function (answer) {
      return pc.setLocalDescription(answer).then(function () { return answer; });
    }).then(function (answer) {
      ws.send(JSON.stringify({ rtc: { role: role, sdp: { type: "answer", sdp: answer.sdp } } }));
    }).catch(function (err) { console.warn("대시보드: rtc 협상 실패", role, err); });
  } else if (msg.candidate) {
    pc.addIceCandidate({ candidate: msg.candidate, sdpMLineIndex: msg.sdpMLineIndex }).catch(function () {});
  }
}
```

`handleMessage` 의 `switch` 에 가지를 추가:

```javascript
    case "rtc":
      handleRtc(msg);
      break;
```

`renderSnapshot(s)` 안에 카메라·대기모드 표시를 추가(함수 끝 `applyAutoProgress(...)` 다음):

```javascript
  if (s.cameras) {
    ["mc", "docent"].forEach(function (role) {
      var c = s.cameras[role];
      if (!c) return;
      var reasonEl = document.getElementById("cam-reason-" + role);
      var btn = document.getElementById("cam-toggle-" + role);
      if (reasonEl) { reasonEl.textContent = c.reason || ""; reasonEl.hidden = !c.reason; }
      if (btn) btn.textContent = c.enabled ? "카메라 끄기" : "카메라 켜기";
    });
  }
  if (Array.isArray(s.standby)) {
    ["mc", "docent"].forEach(function (role) {
      var btn = document.getElementById("standby-toggle-" + role);
      if (btn) btn.textContent = s.standby.indexOf(role) !== -1 ? "대기 해제" : "대기모드";
    });
  }
```

버튼 리스너를 초기화 블록(다른 `addEventListener("click", ...)` 들이 모여 있는 자리, 보통 파일 끝
근처 `document.getElementById("btn-abort").addEventListener(...)` 옆)에 추가:

```javascript
["mc", "docent"].forEach(function (role) {
  var camBtn = document.getElementById("cam-toggle-" + role);
  if (camBtn) camBtn.addEventListener("click", function () { sendCmd("c " + role); });
  var standbyBtn = document.getElementById("standby-toggle-" + role);
  if (standbyBtn) standbyBtn.addEventListener("click", function () { sendCmd("z " + role); });
});
```

`IDS` 리스트(`tests/test_dashboard_page.py` 상단)에 추가:

```python
IDS = [..., "vid-mc", "vid-docent", "cam-reason-mc", "cam-reason-docent",
       "cam-toggle-mc", "cam-toggle-docent", "standby-toggle-mc", "standby-toggle-docent"]
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_dashboard_page.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add stage/dashboard_page.html tests/test_dashboard_page.py
git commit -m "feat(dashboard_page): 카메라 영상·켜기끄기·대기모드 버튼"
```

---

### Task 13: 최종 검증 — 전체 테스트, 시뮬, 실기

**Files:** 없음(검증만)

- [ ] **Step 1: 전체 테스트**

Run: `.venv/bin/python -m pytest -q`
Expected: 전부 PASS(878 + 이번에 늘어난 수)

- [ ] **Step 2: 시뮬에서 카메라 없음 사유 확인**

```bash
REACHY_CAMERA_SRC="videotestsrc is-live=true" ./reachy.sh start --sim
```

대시보드 두 칸 모두 "카메라 없음 — 시뮬이거나…" 대신(시뮬 앱이 `videotestsrc` 로 caps 를 실었다면)
실제 테스트 패턴이 뜨는지 확인한다. 안 뜨면 `caps=["camera"]` 판정(`RtcStreamer.available()`)이
`videotestsrc` 를 소스로 받아들이는지 코드를 다시 본다(Task 10 의 `_pipeline_str`/`available` 의
소스 이름 파싱 — `src.split()[0]` 이 `"videotestsrc"` 를 돌려주는지).

- [ ] **Step 3: 두 로봇에 재배포**

```bash
REACHY_ROBOT_HOST=192.168.0.4 bash -c 'source ./reachy.sh; robot_deploy'
REACHY_ROBOT_HOST=192.168.0.5 bash -c 'source ./reachy.sh; robot_deploy'
```

- [ ] **Step 4: 실기 기동 + 영상 확인**

```bash
./reachy.sh start --robot
```

대시보드 두 칸에 실제 카메라 영상이 뜨는지, 스트림 중 `REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh
robot logs` 로 부하 경고가 없는지, 칸 끄기 버튼과 대기모드 버튼이 로봇 로그에 반영되는지 확인한다.

- [ ] **Step 5: 정리하며 로봇 CPU 실측**

`ssh pollen@192.168.0.4 uptime` 을 스트림 켜기 전/후로 비교해 `docs/superpowers/specs/
2026-09-22-dashboard-camera-design.md` 의 스파이크 실측(+4.2%p)과 크게 벗어나지 않는지 확인하고,
벗어나면 `docs/real-robot-deployment.md` 에 실측값을 남긴다.

- [ ] **Step 6: 커밋**

```bash
git add docs/real-robot-deployment.md   # 실측을 추가했다면
git commit -m "docs(camera): 실기 최종 검증 — 부하 실측·카메라 영상 확인"
```
