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
