"""대기모드 → 실행모드 왕복 실기 진단 — 관리자 페이지(대시보드)와 **같은 경로**로 재현한다.

pytest 로 수집되지 않게 막는다(실기·네트워크가 있어야 의미가 있다 — `stage/dashboard.py`
의 계약대로 `ws://<대시보드>/ws` 에 `{"cmd": "z <role>"}` 를 보내는 것은 브라우저의
`sendCmd("z "+role)` 와 정확히 같은 코드 경로다, `console.dispatch` 한 곳으로 합류한다).
기존 `stage/dashboard.py`·`director.py` 는 참고만 하고 수정하지 않는다.

실행 전제: `./reachy.sh start --robot` 로 대시보드(:8778)와 대상 로봇이 이미 붙어 있어야 한다.

실행:
    .venv/bin/python tests/test_standby_roundtrip_live.py [mc|docent] [로봇호스트]
"""

import json
import sys
import time

import requests
from websockets.sync.client import connect

DASHBOARD_WS = "ws://127.0.0.1:8778/ws"


def _motor_status(robot_host: str) -> str | None:
    try:
        r = requests.get(f"http://{robot_host}:8000/api/motors/status", timeout=3)
        r.raise_for_status()
        return r.json().get("mode")
    except Exception as e:  # noqa: BLE001
        return f"조회 실패({type(e).__name__}: {e})"


def _drain(ws, seconds: float) -> dict | None:
    """그 시간 동안 온 메시지를 전부 찍고, 마지막 snapshot 을 돌려준다."""
    end = time.monotonic() + seconds
    last_snapshot = None
    while time.monotonic() < end:
        try:
            raw = ws.recv(timeout=max(0.1, end - time.monotonic()))
        except TimeoutError:
            break
        except Exception:  # noqa: BLE001
            break
        ev = json.loads(raw)
        kind = ev.get("kind")
        if kind == "snapshot":
            last_snapshot = ev
            print(f"    [snapshot] standby={ev.get('standby')}", flush=True)
        elif kind == "command":
            print(f"    [command 응답] cmd={ev.get('cmd')!r} ok={ev.get('ok')} lines={ev.get('lines')}", flush=True)
        elif kind == "warn":
            print(f"    [경고] {ev.get('text')}", flush=True)
        else:
            print(f"    [{kind}] {ev}", flush=True)
    return last_snapshot


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else "mc"
    robot_host = sys.argv[2] if len(sys.argv) > 2 else "192.168.0.4"

    print(f"대상: {role} ({robot_host}) — 대시보드 {DASHBOARD_WS}", flush=True)
    print(f"[진입 전] 모터 상태: {_motor_status(robot_host)}", flush=True)

    with connect(DASHBOARD_WS, open_timeout=5) as ws:
        hello = json.loads(ws.recv())
        snap = hello.get("snapshot") or {}
        print(f"[연결됨] 초기 standby={snap.get('standby')}", flush=True)
        if role not in snap.get("standby", []) and role not in ("mc", "docent"):
            print(f"모르는 역할이다: {role!r}", flush=True)
            return

        print(f"\n1) 대기모드 진입 — z {role} 전송", flush=True)
        ws.send(json.dumps({"cmd": f"z {role}"}))
        snap = _drain(ws, 6.0)
        entered = snap is not None and role in (snap.get("standby") or [])
        print(f"   진입 결과: standby 목록에 {'있음(성공)' if entered else '없음(실패)'}", flush=True)
        print(f"   [진입 후] 모터 상태: {_motor_status(robot_host)}", flush=True)

        print(f"\n2) 대기모드 해제 — z {role} 다시 전송", flush=True)
        ws.send(json.dumps({"cmd": f"z {role}"}))
        snap = _drain(ws, 8.0)
        exited = snap is not None and role not in (snap.get("standby") or [])
        print(f"   해제 결과: standby 목록에서 {'빠짐(성공)' if exited else '여전히 있음(실패)'}", flush=True)
        print(f"   [해제 후] 모터 상태: {_motor_status(robot_host)}", flush=True)

    print("\n=== 결론 ===", flush=True)
    print(f"진입: {'OK' if entered else 'FAIL'} / 해제: {'OK' if exited else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
