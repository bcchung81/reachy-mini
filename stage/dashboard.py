"""무대감독 대시보드 서버 — 시안 B(방송 조정실) 페이지 한 장과 실시간 소켓 하나.

설계: `docs/superpowers/specs/2026-09-21-stage-dashboard-design.md`.

- **로봇용 포트(8777)와 다른 포트**(기본 `127.0.0.1:8778`)다. 로봇 포트는 로봇 때문에
  `0.0.0.0` 이어야 하는데, 이 화면은 인증 없이 시연을 멈추고 건너뛸 수 있다 — 위험한
  쪽을 기본으로 두지 않는다. 망에 열려면 `REACHY_DASHBOARD_HOST`.
- **연결 하나에 보내는 스레드는 하나**(펌프)다. 명령 결과도 허브 이벤트로 흘려 같은
  펌프가 보낸다 — 두 스레드가 한 소켓에 동시에 쓰지 않게.
- 감독 상태(`Director.snapshot()`)는 펌프가 **락 밖에서** 읽는다. 허브 이벤트를 받는
  자리(감독이 락을 쥔 자리)에서 읽으면 교착이다.
- 경고는 **터미널로만** 낸다(`warn=print`). 허브로 되돌리면 이 서버가 자기 경고를 다시
  페이지로 흘리고, 그 경로가 망가졌을 때 끝없이 되돌아온다.
"""

import json
import pathlib
import queue
import threading
import time
from typing import Callable

from websockets.sync.server import serve as _ws_serve

from stage.console import dispatch as console_dispatch

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8778
SNAPSHOT_INTERVAL_S = 0.5
PAGE = pathlib.Path(__file__).with_name("dashboard_page.html")


class DashboardServer:
    def __init__(self, hub, director, dispatch: Callable = console_dispatch,
                 page: pathlib.Path = PAGE, interval: float = SNAPSHOT_INTERVAL_S,
                 warn: Callable[[str], None] = print) -> None:
        self._hub = hub
        self._director = director
        self._dispatch = dispatch
        self._page = page
        self._interval = interval
        self._warn = warn

    # ── HTTP ──────────────────────────────────────────────────────
    def process_request(self, connection, request):
        if request.path == "/ws":
            return None  # 웹소켓 핸드셰이크로 넘어간다
        if request.path in ("/", "/index.html"):
            try:
                # 요청마다 읽는다 — 시연 중 페이지 파일을 고쳐도 새로고침으로 반영되고,
                # 파일이 사라졌으면 기동 때가 아니라 그 요청에서 500 + 경고로 드러난다.
                body = self._page.read_text(encoding="utf-8")
            except OSError as exc:
                self._warn(f"대시보드 페이지를 못 읽었다({self._page}: {exc})")
                return connection.respond(500, "dashboard page missing")
            resp = connection.respond(200, body)
            # `respond` 는 text/plain 을 붙인다 — 브라우저가 HTML 로 그리게 바꾼다.
            # `Headers` 는 같은 이름을 여러 번 담을 수 있어 대입만 하면 text/plain 이
            # 남은 채 한 줄이 더 붙는다 — 지우고 넣는다.
            del resp.headers["Content-Type"]
            resp.headers["Content-Type"] = "text/html; charset=utf-8"
            return resp
        return connection.respond(404, "not found")

    # ── WebSocket ─────────────────────────────────────────────────
    def handler(self, ws) -> None:
        # **구독을 이력보다 먼저 한다.** 거꾸로면 이력을 읽은 뒤·구독하기 전에 난
        # 이벤트가 어디에도 안 실린다(조용히 빠진다). 이 순서면 그 틈의 이벤트가
        # 이력과 큐 양쪽에 실려 한 번 겹칠 수는 있어도 빠지지는 않는다.
        sub = self._hub.subscribe()
        stop = threading.Event()
        try:
            # hello 는 펌프를 띄우기 **전에** 이 스레드가 보낸다 — 펌프가 뜬 뒤에는
            # 펌프만 보낸다(한 소켓에 송신자는 언제나 하나).
            ws.send(self._dumps({
                "kind": "hello",
                "cues": self._director.cue_list(),
                "history": self._hub.history(),
                "snapshot": self._safe_snapshot(),
            }))
            threading.Thread(target=self._pump, args=(ws, sub, stop), daemon=True).start()
            for raw in ws:
                self._on_command(raw)
        finally:
            stop.set()
            self._hub.unsubscribe(sub)

    def _pump(self, ws, sub, stop: threading.Event) -> None:
        """이 연결의 유일한 송신자. 이벤트는 오는 대로, 스냅샷은 `interval` 마다."""
        last = 0.0
        while not stop.is_set():
            try:
                ev = sub.queue.get(timeout=self._interval)
            except queue.Empty:
                ev = None
            try:
                if ev is not None:
                    ws.send(self._dumps(ev))
                if time.monotonic() - last >= self._interval:
                    snap = self._safe_snapshot()
                    if snap is not None:
                        ws.send(self._dumps({"kind": "snapshot", **snap}))
                    last = time.monotonic()
            except Exception:  # noqa: BLE001 — 연결이 닫혔다. 핸들러가 정리한다.
                return

    def _safe_snapshot(self) -> dict | None:
        try:
            return self._director.snapshot()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"대시보드 스냅샷 실패({type(exc).__name__}: {exc}) — 다음 주기에 다시 읽는다")
            return None

    def _on_command(self, raw) -> None:
        try:
            # 콘솔(`run_console`)과 같게 `strip().lower()` — 같은 문자열이 두 길에서
            # 다르게 해석되면 명령 경로를 하나로 둔 의미가 없다. 큐 id 는 전부 소문자다.
            cmd = str(json.loads(raw)["cmd"]).strip().lower()
        except (ValueError, KeyError, TypeError):
            self._warn(f"대시보드 명령이 규약에 안 맞는다 — 버린다: {str(raw)[:80]!r}")
            return
        lines: list[str] = []
        ok = True
        try:
            self._dispatch(self._director, cmd, lines.append)
        except Exception as exc:  # noqa: BLE001 — 콘솔과 같다: 거절은 보여주고 계속
            ok = False
            lines.append(f"거절됨: {exc}")
        # 결과는 이 소켓에 직접 쓰지 않고 허브로 흘린다 — 여기서 `ws.send` 하면 펌프와
        # 두 스레드가 한 소켓에 쓰게 되고, 다른 대시보드는 누가 무엇을 눌렀는지 못 본다.
        self._hub.publish("command", cmd=cmd, ok=ok, lines=lines)

    @staticmethod
    def _dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)


def start_dashboard(hub, director, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                    warn: Callable[[str], None] = print):
    """대시보드를 띄운다. **실패해도 감독·콘솔은 그대로 돈다** — 경고하고 None."""
    ds = DashboardServer(hub, director, warn=warn)
    try:
        srv = _ws_serve(ds.handler, host, port, process_request=ds.process_request)
    except OSError as exc:
        warn(f"대시보드를 띄우지 못했다({host}:{port} — {exc}) — 감독과 콘솔은 그대로 돈다")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    warn(f"대시보드 — http://{host}:{port}/")
    return srv
