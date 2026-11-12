"""교육자료 공연 모드 통합 — 진짜 대시보드 서버가 준 종이 무대가 감독 이벤트를 따라가는가(2026-11-12).

실제 시연: 로봇 2대(사회자·도슨트)가 말하고 화면(`/stage/paper`)은 소리 없이 따라간다. 여기서는 로봇 대신 허브에 감독과 같은
이벤트를 올리고, 헤드리스 Chrome 으로 연 **빌드된 진짜 페이지**(`docs/design/paper-stage.html`)의 큐·시계·배지를 읽는다.
Chrome 이 없으면 건너뛴다. 시계 계산 자체는 `tests/test_live_follow.py`(node)가 본다.
"""

import json
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "handout_live"))

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGE = ROOT / "docs" / "design" / "paper-stage.html"
pytestmark = pytest.mark.skipif(not (pathlib.Path(CHROME).exists() and PAGE.exists()), reason="Chrome 또는 빌드된 종이 무대가 없다")


@pytest.fixture(scope="module")
def stage():
    from websockets.sync.client import connect
    from websockets.sync.server import serve

    import fake_show
    from stage.cues import load_cues
    from stage.dashboard import DashboardServer
    from stage.dashboard_hub import DashboardHub

    hub, director, warned = DashboardHub(), fake_show.FakeDirector(load_cues(), "일반"), []
    director.running = True                                       # 공연 중 — 스냅샷 show_running
    ds = DashboardServer(hub, director, interval=0.1, warn=warned.append)
    srv = serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.socket.getsockname()[1]

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="live-stage-"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); dport = s.getsockname()[1]
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={dport}", "--no-first-run", "--disable-gpu",
                             "--autoplay-policy=no-user-gesture-required", f"--user-data-dir={tmp / 'profile'}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{dport}/json"))
                ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"); break
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        assert ws_url, "Chrome 디버그 소켓이 안 열렸다"
        cdp = connect(ws_url, max_size=None)
        n, errors = [0], []

        def call(method, **params):
            n[0] += 1
            cdp.send(json.dumps({"id": n[0], "method": method, "params": params}))
            while True:
                m = json.loads(cdp.recv(timeout=60))
                if m.get("method") == "Runtime.exceptionThrown":
                    errors.append(json.dumps(m["params"]["exceptionDetails"], ensure_ascii=False)[:300])
                if m.get("id") == n[0]:
                    return m.get("result", {})

        def js(expr):
            r = call("Runtime.evaluate", expression=expr, returnByValue=True)
            if "exceptionDetails" in r:
                errors.append(json.dumps(r["exceptionDetails"], ensure_ascii=False)[:300])
            return r.get("result", {}).get("value")

        def wait(expr, timeout=8.0):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                v = js(expr)
                if v:
                    return v
                time.sleep(0.1)
            raise AssertionError(f"시간 안에 참이 되지 않았다: {expr} (마지막 {js(expr)!r})")

        call("Runtime.enable"); call("Page.enable")
        call("Emulation.setDeviceMetricsOverride", width=1280, height=720, deviceScaleFactor=1, mobile=False)
        call("Page.navigate", url=f"http://127.0.0.1:{port}/stage/paper")
        wait("document.documentElement.getAttribute('data-ready') === '1'", 30)
        yield {"hub": hub, "js": js, "wait": wait, "errors": errors, "warned": warned, "director": director}
    finally:
        proc.terminate()
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


BADGE = "(document.querySelector('[data-live-badge]')||{}).textContent"
UTT = "JSON.parse(document.getElementById('data').textContent).cues[{c}].utt[{k}]"


def say(hub, role, label, seq):
    hub.publish("sent", role=role, type="say", fields={"cue_id": label, "seq": seq, "text": "대사"})


def started(hub, role, label, seq):
    hub.publish("recv", role=role, type="speaking_started", fields={"cue_id": label, "seq": seq})


def ended(hub, role, label, seq):
    hub.publish("recv", role=role, type="speaking_ended", fields={"cue_id": label, "seq": seq})


def test_대시보드가_준_페이지는_공연_모드로_뜨고_소리를_만들지_않는다(stage):
    js = stage["js"]
    assert js("document.documentElement.getAttribute('data-live')") == "1"
    assert js("window.paperStage.live.enabled") is True
    assert js("document.querySelectorAll('audio').length") == 0
    assert js("document.querySelector('#play').hidden && document.querySelector('#scrub').hidden") is True
    stage["wait"](f"{BADGE} === '공연 대기' || {BADGE} === '공연 따라가는 중'")


def test_대사가_나가면_그_큐로_넘어가고_발화_시작에_맞춰_장면이_흐른다(stage):
    hub, js, wait = stage["hub"], stage["js"], stage["wait"]
    say(hub, "mc", "02-history", 101)
    wait("window.paperStage.cue() === 1")
    t0 = js(UTT.format(c=1, k=0) + ".t0")
    started(hub, "mc", "02-history", 101)
    time.sleep(1.5)
    t = js("window.paperStage.clock()")
    assert t == pytest.approx(t0 - 0.3 + 1.5, abs=0.35), (t, t0)           # 소리 지연 0.3초 보정 + 1.5초 경과
    assert js(BADGE) == "공연 따라가는 중"


def test_발화가_끝나면_턴_끝으로_맞추고_다음_턴_앞에서_기다린다(stage):
    hub, js = stage["hub"], stage["js"]
    ended(hub, "mc", "02-history", 101)
    time.sleep(0.5)
    t1, nxt = js(UTT.format(c=1, k=0) + ".t1"), js(UTT.format(c=1, k=1) + ".t0")
    t = js("window.paperStage.clock()")
    assert t1 - 0.01 <= t <= nxt, (t, t1, nxt)
    time.sleep(1.0)
    assert js("window.paperStage.clock()") <= nxt                            # 다음 턴 그림을 먼저 꺼내지 않는다


def test_관람객_질문_흐름에는_장면이_멈추고_배지가_알린다(stage):
    hub, js, wait = stage["hub"], stage["js"], stage["wait"]
    say(hub, "docent", "02-history:qa", 102)
    started(hub, "docent", "02-history:qa", 102)
    wait(f"{BADGE} === '관람객 질문에 답하는 중'")
    a = js("window.paperStage.clock()"); time.sleep(1.0); b = js("window.paperStage.clock()")
    assert a == pytest.approx(b, abs=1e-6)


def test_수준이_다르면_배지가_알린다(stage):
    stage["director"].level = "전문가"
    stage["wait"](f"({BADGE}||'').indexOf('수준이 다르다') === 0")
    stage["director"].level = "일반"
    stage["wait"](f"({BADGE}||'').indexOf('수준이 다르다') !== 0")


def test_자바스크립트_오류가_없다(stage):
    assert stage["errors"] == []
