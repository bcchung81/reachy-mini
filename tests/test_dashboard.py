import json
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from websockets.sync.client import connect
from websockets.sync.server import serve as ws_serve

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.dashboard import DashboardServer, start_dashboard
from stage.dashboard_hub import DashboardHub
from stage.machine import TurnError


class 가짜감독:
    def __init__(self):
        self.calls = []
        self.fail_next = False

    def snapshot(self):
        return {"cue_id": "07-maritime", "cue_index": 6, "cue_count": 19, "state": "listening"}

    def cue_list(self):
        return [{"id": "07-maritime", "topic": "타이타닉"}]

    def abort(self):
        self.calls.append("abort")

    def next(self):
        if self.fail_next:
            raise TurnError("사회자 가 아직 말하는 중이다")
        self.calls.append("next")

    def goto(self, cue_id):
        self.calls.append(("goto", cue_id))


@pytest.fixture
def dash(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>t</title>", encoding="utf-8")
    hub, d, warned = DashboardHub(), 가짜감독(), []
    ds = DashboardServer(hub, d, page=page, interval=0.05, warn=warned.append)
    srv = ws_serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield {"hub": hub, "d": d, "warned": warned, "port": port, "page": page}
    srv.shutdown()
    t.join(timeout=2)


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


def test_접속하면_큐목록_이력_스냅샷을_한번에_준다(dash):
    dash["hub"].publish("warn", text="먼저 난 경고")
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        m = json.loads(ws.recv(timeout=3))
        assert m["kind"] == "hello"
        assert m["cues"] == [{"id": "07-maritime", "topic": "타이타닉"}]
        assert m["snapshot"]["cue_id"] == "07-maritime"
        assert [e["text"] for e in m["history"] if e["kind"] == "warn"] == ["먼저 난 경고"]


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


def test_거절된_명령은_ok_false_와_사유로_보인다(dash):
    dash["d"].fail_next = True
    with connect(f"ws://127.0.0.1:{dash['port']}/ws") as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "n"}))
        r = _recv_until(ws, "command")
        assert r["ok"] is False
        assert any("말하는 중" in line for line in r["lines"])


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
    assert any("페이지" in w for w in dash["warned"])


def test_포트가_막혀_있으면_경고하고_None(dash):
    warned = []
    assert start_dashboard(DashboardHub(), 가짜감독(), "127.0.0.1", dash["port"], warn=warned.append) is None
    assert any("띄우지 못했다" in w for w in warned), warned


def test_기본_페이지_파일이_있다():
    from stage.dashboard import PAGE
    assert PAGE.exists()
