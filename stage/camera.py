"""대시보드 카메라 중계 — 순수 로직, 네트워크를 모른다.

로봇의 카메라 영상(H.264, WebRTC)을 대시보드로 잇는다. 영상 자체는 로봇에서 브라우저로
**직접** 간다(RTP/SRTP, UDP) — 여기를 지나는 것은 SDP·ICE 시그널링과 "켤지 말지" 판단뿐이다.
설계: docs/superpowers/specs/2026-09-22-dashboard-camera-design.md.

**콜백 둘로 네트워크를 가린다**: `send_robot(role, type, fields)`(로봇에게)와 시청자마다
`deliver(ev)`(그 대시보드 연결에게). 소켓 없이 단위 테스트된다 — `stage/server.py`·
`stage/dashboard.py` 가 배선만 한다.

**자기 락을 쓴다**(설계 §감독). 로봇 연결 스레드(`on_robot_hello`/`on_robot_disconnect`/
`on_robot_rtc`/`on_robot_error`), 대시보드 연결마다 다른 스레드(`add_viewer`/`remove_viewer`/
`on_viewer_rtc`), 콘솔 스레드(`toggle`), 대시보드 펌프 스레드(`snapshot`)가 전부 같은 상태를
건드린다 — 가장 구체적인 예: `add_viewer` 의 `_next_id += 1` 이 잠금 없이 읽고 쓰면 두 대시보드
연결이 동시에 붙을 때 **같은 시청자 id** 를 받아, `self._viewers[vid]` 가 한쪽의 배달 콜백을
말없이 덮어쓸 수 있었다(리뷰 I3).

**로봇 송신·시청자 배달은 락을 놓은 뒤에 한다** — 상태를 판정·반영하는 `_xxx_locked` 메서드가
"보낼 것" 목록만 만들어 돌려주고, 공개 메서드가 락을 놓은 뒤 `_run()` 으로 실제 송신·배달을
한다. 느린 소켓 하나가 다른 시청자·로봇 처리를 막지 않게 하려는 것과 같은 이유다.
"""

import threading
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
        self._lock = threading.Lock()

    # ── 시청자 ────────────────────────────────────────────────────
    def add_viewer(self, deliver: Callable[[dict], None]) -> str:
        with self._lock:
            vid = f"v{self._next_id}"
            self._next_id += 1
            self._viewers[vid] = deliver
            actions = self._recompute_all_locked()
        self._run(actions)
        return vid

    def remove_viewer(self, viewer: str) -> None:
        with self._lock:
            self._viewers.pop(viewer, None)
            actions: list[tuple] = []
            for role in ROLES:
                actions += self._set_pair_locked(role, viewer, False)
                self._active.pop((role, viewer), None)
        self._run(actions)

    # ── 로봇에게서 오는 것 ────────────────────────────────────────
    def on_robot_hello(self, role: str, caps: list[str] | None) -> None:
        if role not in ROLES:
            return
        with self._lock:
            st = self._robots[role]
            st.connected = True
            st.has_camera = bool(caps and "camera" in caps)
            actions = self._recompute_locked(role)
        self._run(actions)

    def on_robot_disconnect(self, role: str) -> None:
        if role not in ROLES:
            return
        with self._lock:
            self._robots[role].connected = False
            self._robots[role].has_camera = False
            actions: list[tuple] = []
            for viewer in list(self._viewers):
                # **로봇에게는 보내지 않는다**(리뷰 M6). 연결이 끊어지는 바로 그
                # 자리라 `send_robot`(→ `StageServer._send_raw`)이 성공할 수 없다
                # — 예전에는 여기서도 `_set_pair` 가 `camera{on:false}` 송신을
                # 시도해, `_conns` 에서 이미(또는 아직) 이 role 을 못 찾고
                # "아직 붙지 않았다" 는 **오해를 부르는** 경고를 남겼다(이 로봇은
                # 방금까지 붙어 있었다). 로봇 앱은 감독 링크가 끊기면 스스로
                # 스트림을 닫는다(설계 §감독) — 여기서는 우리 쪽 상태만 정리하고
                # 시청자에게 bye 만 준다.
                if self._active.pop((role, viewer), False):
                    actions.append(("deliver", viewer,
                                     {"kind": "rtc", "role": role, "bye": True}))
        self._run(actions)

    def on_robot_error(self, role: str, detail: str) -> None:
        if role not in ROLES:
            return
        with self._lock:
            self._robots[role].reason = f"카메라 오류: {detail}"
        self._warn(f"[{role}] 카메라 오류: {detail}")

    def on_robot_rtc(self, role: str, msg: dict) -> None:
        if role not in ROLES:
            return
        viewer = msg.get("viewer")
        with self._lock:
            known = isinstance(viewer, str) and viewer in self._viewers
        if not known:
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
            with self._lock:
                actions = self._set_pair_locked(role, viewer, False)
                actions += self._recompute_locked(role)
            self._run(actions)
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
        with self._lock:
            st = self._robots[role]
            st.enabled = not st.enabled
            enabled_now = st.enabled
            actions = self._recompute_locked(role)
        self._warn(f"[{role}] 카메라 {'켬' if enabled_now else '끔'}")
        self._run(actions)

    def snapshot(self) -> dict:
        """**락을 잠깐 쥐고** 한 시점의 값을 모은다 — `Director.snapshot()` 과 같은
        모양(대시보드 펌프 스레드가 락 밖에서 주기적으로 부른다)."""
        with self._lock:
            return {role: {"available": st.connected and st.has_camera,
                            "enabled": st.enabled, "reason": self._reason_locked(role)}
                    for role, st in self._robots.items()}

    # ── 내부 — 아래는 전부 **`self._lock` 을 쥔 채** 불린다 ──────────
    def _reason_locked(self, role: str) -> str:
        st = self._robots[role]
        if not st.connected:
            return "OFFLINE"
        if not st.has_camera:
            return "카메라 없음 — 시뮬이거나 로봇 앱이 카메라를 모른다(재배포 필요)"
        if not st.enabled:
            return "카메라 꺼짐"
        return st.reason

    def _recompute_all_locked(self) -> list[tuple]:
        actions: list[tuple] = []
        for role in ROLES:
            actions += self._recompute_locked(role)
        return actions

    def _recompute_locked(self, role: str) -> list[tuple]:
        st = self._robots[role]
        want_on = st.connected and st.has_camera and st.enabled and bool(self._viewers)
        actions: list[tuple] = []
        for viewer in list(self._viewers):
            actions += self._set_pair_locked(role, viewer, want_on)
        return actions

    def _set_pair_locked(self, role: str, viewer: str, on: bool) -> list[tuple]:
        if self._active.get((role, viewer), False) == on:
            return []
        self._active[(role, viewer)] = on
        if on:
            self._robots[role].reason = ""   # 다음에 켤 때 옛 오류를 지운다
        actions: list[tuple] = [("send_robot", role, "camera", {"viewer": viewer, "on": on})]
        if not on:
            actions.append(("deliver", viewer, {"kind": "rtc", "role": role, "bye": True}))
        return actions

    # ── 락 밖에서만 불린다 ──────────────────────────────────────────
    def _run(self, actions: list[tuple]) -> None:
        """`_xxx_locked` 가 모은 송신·배달을 **락을 놓은 뒤에** 실제로 한다."""
        for action in actions:
            kind = action[0]
            if kind == "send_robot":
                _, role, type_, fields = action
                self._send_robot(role, type_, fields)
            else:  # "deliver"
                _, viewer, ev = action
                self._deliver(viewer, ev)

    def _deliver(self, viewer: str, ev: dict) -> None:
        with self._lock:
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
