import contextlib
import inspect
import json
import pathlib
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from websockets.exceptions import ConnectionClosedError, InvalidStatus
from websockets.sync.client import connect
from websockets.sync.server import serve as ws_serve

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.dashboard import DashboardServer, start_dashboard
from stage.dashboard_hub import DashboardHub
from stage.machine import TurnError


class 가짜감독:
    # 콘솔 `n`·`g` 는 단독이 아닐 때만 먼저 멈춘다(`stage/console.py::_stop_first`).
    mode = "podcast"

    def __init__(self):
        self.calls = []
        self.fail_next = False
        # (들어왔다, 놓아라) — 설정하면 snapshot() 이 그 안에서 멈춘다. 펌프를 한 자리에
        # 붙잡아 두고 구독 큐를 넘치게 만들 때 쓴다(sleep 없이 결정적으로).
        self.hold = None

    def snapshot(self):
        hold = self.hold
        if hold is not None:
            entered, release = hold
            entered.set()
            release.wait(timeout=3)
        return {"cue_id": "07-maritime", "cue_index": 6, "cue_count": 19, "state": "listening"}

    def cue_list(self):
        # 계약 모양 그대로 — `Director.cue_list()` 는 {id, title, topic} 을 준다.
        return [{"id": "07-maritime", "title": "해상무선통신", "topic": "타이타닉"}]

    def level_names(self):
        # levels.yaml 의 네 개가 아닌 **둘**을 준다 — hello 가 파일을 따로 읽지 않고
        # 감독이 준 목록을 그대로 싣는지 가른다.
        return ["초등", "전문가"]

    def mode_names(self):
        # 헤더의 운영 모드 토글(계약: 이 순서). 감독이 준 것을 그대로 싣는지는
        # `test_hello_의_모드_목록은_감독이_준_것을_그대로_싣는다` 가 다른 값으로 본다.
        return ["podcast", "solo"]

    def abort(self):
        self.calls.append("abort")

    def next(self):
        if self.fail_next:
            raise TurnError("사회자 가 아직 말하는 중이다")
        self.calls.append("next")

    def goto(self, cue_id):
        self.calls.append(("goto", cue_id))


@contextlib.contextmanager
def _served(ds):
    """`DashboardServer` 를 실소켓(port=0)에 띄운다. 핸들러가 예외로 끝났는지와 끝난
    횟수를 기록한다 — websockets 는 핸들러 예외를 트레이스백으로만 남기므로 그걸 봐야
    '조용히 끝났다' 를 단언할 수 있다."""
    errors, finished = [], threading.Semaphore(0)

    def handler(ws):
        try:
            ds.handler(ws)
        except BaseException as exc:
            errors.append(exc)
            raise
        finally:
            finished.release()

    srv = ws_serve(handler, "127.0.0.1", 0, process_request=ds.process_request)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.socket.getsockname()[1], errors, finished
    finally:
        srv.shutdown()
        t.join(timeout=2)


@pytest.fixture
def dash(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>t</title>", encoding="utf-8")
    hub, d, warned = DashboardHub(), 가짜감독(), []
    ds = DashboardServer(hub, d, page=page, interval=0.05, warn=warned.append)
    with _served(ds) as (port, errors, finished):
        yield {"hub": hub, "d": d, "warned": warned, "port": port, "page": page,
               "handler_errors": errors, "handler_finished": finished}


def _recv_until(ws, kind, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        m = json.loads(ws.recv(timeout=timeout))
        if m["kind"] == kind:
            return m
    raise AssertionError(f"{kind} 가 안 왔다")


def test_루트는_페이지를_html_로_준다(dash):
    with urllib.request.urlopen(f"http://127.0.0.1:{dash['port']}/") as r:
        assert r.status == 200
        assert r.headers["Content-Type"].startswith("text/html")
        assert "<title>t</title>" in r.read().decode("utf-8")


def test_모르는_경로는_404(dash):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://127.0.0.1:{dash['port']}/nope")
    assert e.value.code == 404


def test_쿼리가_붙은_주소도_같은_자리로_간다(dash):
    # 브라우저 캐시 무효화(`/?v=2`)나 소켓 URL 의 쿼리는 흔하다 — 경로만 봐야 한다.
    with urllib.request.urlopen(f"http://127.0.0.1:{dash['port']}/?v=2", timeout=3) as r:
        assert r.status == 200
        assert "<title>t</title>" in r.read().decode("utf-8")
    with connect(f"ws://127.0.0.1:{dash['port']}/ws?x=1") as ws:
        assert json.loads(ws.recv(timeout=3))["kind"] == "hello"


def test_접속하면_큐목록_이력_스냅샷을_한번에_준다(dash):
    dash["hub"].publish("warn", text="먼저 난 경고")
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        m = json.loads(ws.recv(timeout=3))
        assert m["kind"] == "hello"
        assert m["cues"] == [{"id": "07-maritime", "title": "해상무선통신", "topic": "타이타닉"}]
        assert m["levels"] == ["초등", "전문가"]      # 헤더의 수준 버튼(감독이 준 순서 그대로)
        assert m["modes"] == ["podcast", "solo"]     # 헤더의 운영 모드 토글
        assert m["snapshot"]["cue_id"] == "07-maritime"
        assert [e["text"] for e in m["history"] if e["kind"] == "warn"] == ["먼저 난 경고"]


def test_hello_의_모드_목록은_감독이_준_것을_그대로_싣는다(dash):
    """계약값(`["podcast", "solo"]`)과 **다른** 목록을 준다 — 대시보드가 목록을 제 손으로
    박아 두면 위 테스트는 통과해도 여기서 걸린다(감독이 받는 이름과 버튼이 갈라진다)."""
    dash["d"].mode_names = lambda: ["solo"]
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        m = json.loads(ws.recv(timeout=3))
        assert m["kind"] == "hello"
        assert m["modes"] == ["solo"]


def test_접속_뒤_이벤트와_주기_스냅샷이_온다(dash):
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))                 # hello
        dash["hub"].publish("sent", role="mc", type="say", fields={"text": "안녕"})
        assert _recv_until(ws, "sent")["fields"] == {"text": "안녕"}
        assert _recv_until(ws, "snapshot")["cue_index"] == 6


def test_버튼_명령은_콘솔과_같은_경로로_실행되고_결과가_모두에게_보인다(dash):
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "N"}))              # 대문자도 콘솔처럼 소문자로
        r = _recv_until(ws, "command")
        assert (r["cmd"], r["ok"]) == ("n", True)
        ws.send(json.dumps({"cmd": "g 07-maritime"}))
        _recv_until(ws, "command")
    assert dash["d"].calls == ["abort", "next", "abort", ("goto", "07-maritime")]


def test_수준_버튼_명령은_소문자로_바꿔도_한글_이름이_그대로_감독에_닿는다(dash):
    """서버는 명령을 `.lower()` 한다(콘솔과 같게). 수준 이름은 한글이라 영향이 없어야
    한다 — 이 계약이 깨지면 버튼을 눌러도 "모르는 수준" 경고만 뜬다."""
    dash["d"].set_level = lambda name: dash["d"].calls.append(("set_level", name))
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "L 전문가"}))
        r = _recv_until(ws, "command")
        assert (r["cmd"], r["ok"]) == ("l 전문가", True)
    assert dash["d"].calls == [("set_level", "전문가")]


def test_한_화면에서_누른_명령이_다른_화면에도_보인다(dash):
    # 운영자 둘(또는 노트북+태블릿)이 같은 시연을 볼 때, 누가 무엇을 눌렀는지 서로 보여야
    # 한다 — 결과를 누른 쪽 소켓에만 돌려주면 다른 화면은 이유 모를 진행 변화만 본다.
    url = f"ws://127.0.0.1:{dash['port']}/ws"
    with connect(url) as a, connect(url) as b:
        json.loads(a.recv(timeout=3))
        json.loads(b.recv(timeout=3))
        a.send(json.dumps({"cmd": "a"}))
        r = _recv_until(b, "command")
        assert (r["cmd"], r["ok"]) == ("a", True)
    assert dash["d"].calls == ["abort"]


def test_거절된_명령은_ok_false_와_사유로_보인다(dash):
    dash["d"].fail_next = True
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "n"}))
        r = _recv_until(ws, "command")
        assert r["ok"] is False
        assert any("말하는 중" in line for line in r["lines"])
    # 콘솔처럼 터미널에도 남는다 — 문제 보고를 받으면 로그부터 읽는다.
    assert "대시보드 명령 'n' 거절됨: 사회자 가 아직 말하는 중이다" in dash["warned"], dash["warned"]


def test_규약에_안_맞는_명령은_경고하고_연결은_산다(dash):
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send("이건 JSON 이 아니다")
        ws.send(json.dumps({"cmd": "n"}))
        assert _recv_until(ws, "command")["ok"] is True
    assert any("규약" in w for w in dash["warned"]), dash["warned"]


def test_페이지_파일이_없으면_500_과_경고(dash):
    dash["page"].unlink()
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://127.0.0.1:{dash['port']}/")
    assert e.value.code == 500
    # 문구의 **앞머리**로 단언한다. 경고에는 tmp_path(테스트 이름 = "…페이지…")가 들어가
    # `"페이지" in w` 는 문구를 무엇으로 바꿔도 통과했다(테스트 함정 ①).
    assert any(w.startswith("대시보드 페이지를 못 읽었다(") for w in dash["warned"]), dash["warned"]


def test_다른_사이트에서_온_소켓은_거절한다(dash):
    with pytest.raises(InvalidStatus) as e:
        connect(f"ws://127.0.0.1:{dash['port']}/ws", origin="http://evil.example",
                open_timeout=3)
    assert e.value.response.status_code == 403
    assert any(w.startswith("대시보드 소켓을 거절했다 — 다른 사이트") for w in dash["warned"]), dash["warned"]
    assert dash["d"].calls == []


def test_같은_주소에서_온_소켓은_받는다(dash):
    port = dash["port"]
    with connect(f"ws://127.0.0.1:{port}/ws", origin=f"http://127.0.0.1:{port}") as ws:
        assert json.loads(ws.recv(timeout=3))["kind"] == "hello"
    assert dash["warned"] == []


def test_보내다_터진_연결은_경고하고_닫아_페이지가_다시_붙게_한다(dash):
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        # 튜플 키는 `default=str` 로도 직렬화되지 않는다 — 연결 종료가 아닌 송신 실패.
        dash["hub"].publish("sent", role="mc", type="say", fields={(1, 2): "튜플 키"})
        with pytest.raises(ConnectionClosedError) as e:
            while True:
                ws.recv(timeout=3)
        assert e.value.rcvd.code == 1011
    assert len(dash["warned"]) == 1, dash["warned"]
    assert dash["warned"][0].startswith("대시보드 송신 실패(TypeError:"), dash["warned"]


def test_close_프레임_없이_사라진_페이지는_조용히_정리된다(dash):
    ws = connect(f"ws://127.0.0.1:{dash['port']}/ws")
    try:
        json.loads(ws.recv(timeout=3))
        # 노트북 절전·Wi-Fi 끊김 흉내 — close 프레임 없이 TCP 만 닫힌다.
        ws.socket.shutdown(socket.SHUT_RDWR)
    finally:
        ws.close()
    assert dash["handler_finished"].acquire(timeout=3)
    assert dash["handler_errors"] == []
    assert dash["warned"] == []


def test_구독_큐가_넘쳐_버린_이벤트_수를_터미널에_남긴다(tmp_path):
    class 작은허브(DashboardHub):
        def subscribe(self, maxsize=1000):
            return super().subscribe(maxsize=1)

    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>t</title>", encoding="utf-8")
    hub, d, warned = 작은허브(), 가짜감독(), []
    ds = DashboardServer(hub, d, page=page, interval=0.05, warn=warned.append)
    with _served(ds) as (port, _, _), connect(f"ws://127.0.0.1:{port}/ws") as ws:
        json.loads(ws.recv(timeout=3))                          # hello
        entered, release = threading.Event(), threading.Event()
        d.hold = (entered, release)
        assert entered.wait(timeout=3)                           # 펌프가 스냅샷 안에 붙잡혔다
        for i in range(3):                                       # 큐(1칸)에 하나, 둘은 버려진다
            hub.publish("sent", role="mc", type="say", fields={"i": i})
        d.hold = None
        release.set()
        assert _recv_until(ws, "sent")["fields"] == {"i": 0}
        drops = [w for w in warned if w.startswith("대시보드 구독 큐가 넘쳐 이벤트 2개를 버렸다")]
        assert len(drops) == 1, warned


def test_포트가_막혀_있으면_경고하고_None(dash):
    warned = []
    assert start_dashboard(DashboardHub(), 가짜감독(), "127.0.0.1", dash["port"], warn=warned.append) is None
    assert any("띄우지 못했다" in w for w in warned), warned


def test_포트가_범위_밖이면_경고하고_None():
    """`bind()` 는 0~65535 밖의 포트에 OSError 가 아니라 **OverflowError** 를 낸다 —
    `except OSError` 만으로는 새어 나가 `REACHY_DASHBOARD_PORT=99999` 하나로 감독이 기동에서
    죽었다(최종 리뷰 Y4). 막힌 포트와 같은 경고·같은 None 이어야 한다."""
    warned = []
    assert start_dashboard(DashboardHub(), 가짜감독(), "127.0.0.1", 99999, warn=warned.append) is None
    assert any(w.startswith("대시보드를 띄우지 못했다(127.0.0.1:99999 — ") for w in warned), warned


def test_start_dashboard_는_실제_페이지와_소켓을_띄운다():
    warned = []
    srv = start_dashboard(DashboardHub(), 가짜감독(), "127.0.0.1", 0, warn=warned.append)
    assert srv is not None, warned
    try:
        port = srv.socket.getsockname()[1]
        # port=0 을 넘겼으니 OS 가 고른 임시 포트여야 한다 — 인자를 무시하고 기본 포트로
        # 떴다면 여기서 드러난다(기본값과 같은 값으로 단언하지 않는다, 함정 ③).
        assert port != 8778
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
            assert r.status == 200
            assert r.headers["Content-Type"] == "text/html; charset=utf-8"
            assert r.read().decode("utf-8") == (ROOT / "stage" / "dashboard_page.html").read_text(encoding="utf-8")
        with connect(f"ws://127.0.0.1:{port}/ws", open_timeout=3) as ws:
            assert json.loads(ws.recv(timeout=3))["kind"] == "hello"
    finally:
        srv.shutdown()


def test_기본값은_노트북에서만_8778_에서_반초마다():
    # 기대값은 리터럴이다 — 피검 모듈의 상수를 가져다 비교하면 상수를 바꿔도 통과한다(함정 ⑤).
    # 이 화면은 인증 없이 시연을 멈춘다 — 기본 바인드가 망에 열리면 안 된다.
    from stage import dashboard

    params = inspect.signature(start_dashboard).parameters
    assert params["host"].default == "127.0.0.1"
    assert params["port"].default == 8778
    assert dashboard.DEFAULT_HOST == "127.0.0.1"
    assert dashboard.DEFAULT_PORT == 8778
    assert dashboard.SNAPSHOT_INTERVAL_S == 0.5


def test_기본_페이지_파일이_있다():
    from stage.dashboard import PAGE
    assert PAGE.resolve() == ROOT / "stage" / "dashboard_page.html"
    assert PAGE.exists()


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
