"""무대감독 대시보드 서버 — 시안 B(방송 조정실) 페이지 한 장과 실시간 소켓 하나.

설계: `docs/superpowers/specs/2026-09-21-stage-dashboard-design.md`.

- **로봇용 포트(8777)와 다른 포트**(기본 `127.0.0.1:8778`)다. 로봇 포트는 로봇 때문에
  `0.0.0.0` 이어야 하는데, 이 화면은 인증 없이 시연을 멈추고 건너뛸 수 있다 — 위험한
  쪽을 기본으로 두지 않는다. 망에 열려면 `REACHY_DASHBOARD_HOST`.
- 루프백 바인드는 **운영자 자신의 브라우저**에서 오는 사이트 간 소켓을 못 막는다 —
  `/ws` 는 `Origin` 이 이 서버 주소(`Host`)와 같을 때만 받는다(`_check_origin`).
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
import urllib.parse
from typing import Callable

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve as _ws_serve

from stage.console import dispatch as console_dispatch

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8778
SNAPSHOT_INTERVAL_S = 0.5
PAGE = pathlib.Path(__file__).with_name("dashboard_page.html")


class DashboardServer:
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

    # ── HTTP ──────────────────────────────────────────────────────
    def process_request(self, connection, request):
        # `request.path` 는 쿼리까지 담는다 — 그대로 비교하면 캐시 무효화용 `/?v=2` 나
        # `/ws?x=1` 이 404 가 된다. 경로만 본다.
        path = urllib.parse.urlsplit(request.path).path
        if path == "/ws":
            return self._check_origin(connection, request)  # None 이면 핸드셰이크로 넘어간다
        if path in ("/", "/index.html"):
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

    def _check_origin(self, connection, request):
        """다른 사이트가 연 소켓(CSWSH)을 막는다. 통과면 None, 아니면 403 응답.

        **`127.0.0.1` 바인드로는 못 막는다.** 운영자 브라우저에 열린 아무 탭(광고·검색
        결과 속 스크립트)이나 `new WebSocket("ws://127.0.0.1:8778/ws")` 을 열 수 있고,
        브라우저는 웹소켓에 동일 출처 정책을 걸지 않는다 — 그 탭이 `a`·`n`·`g` 를 보내면
        인증 없는 이 화면이 시연을 멈추고 건너뛴다. 브라우저가 스스로 붙이는(페이지가
        못 바꾸는) `Origin` 이 이 서버의 주소(`Host`)와 같을 때만 받는다.

        `Origin` 이 **없으면** 받는다 — 브라우저가 아닌 클라이언트(테스트, 스크립트)다.
        브라우저는 웹소켓에 늘 `Origin` 을 붙이므로 이 예외로 사이트 간 공격이 새지 않는다.
        같은 헤더가 둘 이상이면 어느 쪽을 믿을지 정할 수 없으니 거절한다.
        """
        origins = request.headers.get_all("Origin")
        if not origins:
            return None
        hosts = request.headers.get_all("Host")
        ok = (
            len(origins) == 1
            and len(hosts) == 1
            # 호스트 이름은 대소문자를 가리지 않는다. `Origin: null`(sandbox·file://)은
            # netloc 이 비어 여기서 걸린다.
            and urllib.parse.urlsplit(origins[0]).netloc.lower() == hosts[0].lower()
        )
        if ok:
            return None
        self._warn(
            f"대시보드 소켓을 거절했다 — 다른 사이트에서 온 연결이다(Origin={origins}, Host={hosts}). "
            "운영자 브라우저의 다른 탭이 시연을 조작하려 했을 수 있다"
        )
        return connection.respond(403, "cross-origin dashboard connection refused")

    # ── WebSocket ─────────────────────────────────────────────────
    def handler(self, ws) -> None:
        # **구독을 이력보다 먼저 한다.** 거꾸로면 이력을 읽은 뒤·구독하기 전에 난
        # 이벤트가 어디에도 안 실린다(조용히 빠진다). 이 순서면 그 틈의 이벤트가
        # 이력과 큐 양쪽에 실려 한 번 겹칠 수는 있어도 빠지지는 않는다.
        sub = self._hub.subscribe()
        viewer = self._camera.add_viewer(self._deliver_maker(sub)) if self._camera is not None else None
        stop = threading.Event()
        try:
            # hello 는 펌프를 띄우기 **전에** 이 스레드가 보낸다 — 펌프가 뜬 뒤에는
            # 펌프만 보낸다(한 소켓에 송신자는 언제나 하나).
            ws.send(self._dumps({
                "kind": "hello",
                "cues": self._director.cue_list(),
                # 헤더의 관람객 수준 버튼(levels.yaml 순서). 파일을 따로 읽지 않고 감독에게
                # 받는다 — 버튼 이름과 감독이 받아들이는 이름(`l <수준>`)이 한 곳에서 나온다.
                "levels": self._director.level_names(),
                # 헤더의 운영 모드 토글(podcast/solo 순서). 수준과 같은 이유로 감독에게
                # 받는다 — 버튼 이름과 `m <모드>` 가 받아들이는 이름이 한 곳에서 나온다.
                "modes": self._director.mode_names(),
                "history": self._hub.history(),
                "snapshot": self._safe_snapshot(),
            }))
            threading.Thread(target=self._pump, args=(ws, sub, stop), daemon=True).start()
            for raw in ws:
                # `rtc` 모양만 여기서 가로챈다 — 그 외(깨진 JSON 포함)는 전부 `_on_command`
                # 로 넘겨 그쪽의 "규약에 안 맞는다" 경고 하나로만 걸러지게 한다. 여기서 JSON
                # 파싱 실패를 따로 warn 하면 같은 상황(깨진 메시지)에 경고 문구가 둘로
                # 갈라져 기존 계약(`_on_command` 의 "규약" 경고)이 깨진다.
                try:
                    obj = json.loads(raw)
                except (ValueError, TypeError):
                    obj = None
                if isinstance(obj, dict) and "rtc" in obj and self._camera is not None and viewer is not None:
                    self._camera.on_viewer_rtc(viewer, obj["rtc"])
                    continue
                self._on_command(raw)
        except ConnectionClosed:
            # 페이지가 close 프레임 없이 사라졌다(노트북 절전·Wi-Fi 끊김·브라우저 강제
            # 종료) — `for raw in ws` 가 ConnectionClosedError 를 낸다. 여기서 새면
            # websockets 가 "connection handler failed" 트레이스백을 찍는데, 운영자가 할
            # 일이 없는 정상 경로라 터미널의 진짜 경고를 묻어 버린다. 페이지는 스스로
            # 다시 붙는다. 펌프가 송신 실패로 1011 을 보내고 닫은 경우도 여기로 온다
            # (그 경고는 펌프가 이미 냈다).
            pass
        finally:
            stop.set()
            self._hub.unsubscribe(sub)
            if self._camera is not None and viewer is not None:
                self._camera.remove_viewer(viewer)

    @staticmethod
    def _deliver_maker(sub):
        def deliver(ev: dict) -> None:
            try:
                sub.queue.put_nowait(ev)
            except queue.Full:
                # `mark_dropped()` — 이 `deliver` 는 카메라 릴레이를 거쳐 로봇 연결
                # 스레드에서도 불린다. 허브의 `publish` 도 같은 `sub.dropped` 를 다른
                # 스레드에서 올릴 수 있어, 락 없는 `+= 1` 은 카운트를 잃는다
                # (`stage/dashboard_hub.py::Subscription.mark_dropped` 가 락을 쥔다).
                sub.mark_dropped()
        return deliver

    def _pump(self, ws, sub, stop: threading.Event) -> None:
        """이 연결의 유일한 송신자. 이벤트는 오는 대로, 스냅샷은 `interval` 마다."""
        last = 0.0
        dropped_seen = 0
        while not stop.is_set():
            try:
                ev = sub.queue.get(timeout=self._interval)
            except queue.Empty:
                ev = None
            # 구독 큐가 넘쳐 허브가 버린 이벤트. 상태 칸은 다음 스냅샷으로 다시 맞춰지지만
            # 대사·경고 줄은 로그에서 **빠진 채** 남는다 — 페이지만 보면 모른다. 늘어난
            # 만큼만 한 번 알린다(같은 수를 주기마다 되풀이하지 않게). 보내기 **전에**
            # 알려, 버린 뒤 처음 도착한 이벤트보다 경고가 늦지 않게 한다.
            dropped = sub.dropped
            if dropped > dropped_seen:
                self._warn(
                    f"대시보드 구독 큐가 넘쳐 이벤트 {dropped - dropped_seen}개를 버렸다"
                    f"(이 연결 누적 {dropped}) — 페이지 로그에서 빠졌다. 상태는 다음 스냅샷으로 맞춰진다"
                )
                dropped_seen = dropped
            try:
                if ev is not None:
                    ws.send(self._dumps(ev))
                if time.monotonic() - last >= self._interval:
                    snap = self._safe_snapshot()
                    if snap is not None:
                        ws.send(self._dumps({"kind": "snapshot", **snap}))
                    last = time.monotonic()
            except ConnectionClosed:
                return  # 연결이 닫혔다. 핸들러가 정리한다.
            except Exception as exc:  # noqa: BLE001
                # **조용히 return 하면 안 된다.** 이 스레드가 이 연결의 유일한 송신자라,
                # 여기서 말없이 끝나면 소켓은 열린 채 페이지가 그 자리에서 굳는다(재접속도
                # 안 한다 — 끊긴 게 아니므로). 가장 흔한 원인은 직렬화 실패(문자열이 아닌
                # dict 키는 `default=str` 로도 못 넘긴다). 알리고 1011 로 닫아 핸들러가
                # 정리하고 페이지가 다시 붙게 한다.
                self._warn(
                    f"대시보드 송신 실패({type(exc).__name__}: {exc}) — 이 연결을 닫는다"
                    "(페이지는 다시 붙는다)"
                )
                ws.close(1011, "dashboard send failed")
                return

    def _safe_snapshot(self) -> dict | None:
        try:
            snap = self._director.snapshot()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"대시보드 스냅샷 실패({type(exc).__name__}: {exc}) — 다음 주기에 다시 읽는다")
            return None
        if self._camera is not None:
            snap = {**snap, "cameras": self._camera.snapshot()}
        return snap

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
            # 페이지에만 보이면 안 된다 — 콘솔은 거절을 터미널에 찍고, 문제 보고를 받으면
            # 터미널 로그부터 읽는다. 대시보드에서 누른 것도 같은 자리에 남긴다.
            self._warn(f"대시보드 명령 {cmd!r} 거절됨: {exc}")
        # 결과는 이 소켓에 직접 쓰지 않고 허브로 흘린다 — 여기서 `ws.send` 하면 펌프와
        # 두 스레드가 한 소켓에 쓰게 되고, 다른 대시보드는 누가 무엇을 눌렀는지 못 본다.
        self._hub.publish("command", cmd=cmd, ok=ok, lines=lines)

    @staticmethod
    def _dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)


def start_dashboard(hub, director, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                    camera=None, warn: Callable[[str], None] = print):
    """대시보드를 띄운다. **실패해도 감독·콘솔은 그대로 돈다** — 경고하고 None."""
    ds = DashboardServer(hub, director, camera=camera, warn=warn)
    try:
        srv = _ws_serve(ds.handler, host, port, process_request=ds.process_request)
    # `bind()` 는 0~65535 밖의 포트(`REACHY_DASHBOARD_PORT=99999`)에 OSError 가 아니라
    # OverflowError 를 낸다 — OSError 만 잡으면 그 하나로 감독이 기동에서 죽었다(최종
    # 리뷰 Y4). 막힌 포트와 같은 실패다: 경고하고 None.
    except (OSError, OverflowError) as exc:
        warn(f"대시보드를 띄우지 못했다({host}:{port} — {exc}) — 감독과 콘솔은 그대로 돈다")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    warn(f"대시보드 — http://{host}:{port}/")
    return srv
