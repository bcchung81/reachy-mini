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
    # `--disable-gpu` 그대로 — 소프트웨어 WebGL(swiftshader)을 켜면 그리기가 느려져 시계 시험이 1초쯤 밀렸다(2026-11-13 실측).
    # 그래서 GPU 없는 헤드리스에서 분해도(three.js)는 WebGL 을 못 만든다 — 그 예외 하나만 아래 `_errors_but_webgl` 가 거른다.
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
                    d = m["params"]["exceptionDetails"]
                    errors.append(((d.get("exception") or {}).get("description") or "")[:160] + " · "
                                  + json.dumps(d, ensure_ascii=False)[:300])
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


def _errors_but_webgl(errors):
    """GPU 없는 헤드리스에서만 나는 분해도의 WebGL 생성 실패를 뺀 나머지(페이지는 이때 스스로 안내 띠를 띄운다)."""
    return [e for e in errors if "Error creating WebGL context" not in e]
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


def test_자동_선택_화면은_수준과_지금_큐로_화면을_고른다(stage):
    """운영자가 연 /stage/auto 하나가 (수준, 큐)로 화면을 고른다(2026-11-13).
    ① 교육자료 화면을 안 열어 '시연영상이 안 보인다' ② ~~웹툰·분해도엔 01·02큐뿐이라~~ 06큐에서 수준을 바꾸면 01큐에 멈췄다.
    (2026-11-14 웹툰·분해도가 하이라이트 9큐로 늘었다 — 06 은 하이라이트 밖이라 여전히 카드 화면이고, 이 시험의 단언은 그대로 맞다.)"""
    js, wait, director, hub = stage["js"], stage["wait"], stage["director"], stage["hub"]
    SA = "(window.stageAuto||{})"
    director.level, director.cue_id = "일반", "01-intro"
    js("location.href = '/stage/auto'")
    wait(f"{SA}.screen === 'paper'", 15)
    # 전문가 · 01 → 분해도(가졌다). 카드 화면을 뒤에 미리 띄워 둔다 — 03큐로 넘어갈 때 빈 화면이 없게.
    director.level = "전문가"
    wait(f"{SA}.screen === 'exploded'", 10)
    wait(f"JSON.stringify({SA}.loaded.slice().sort()) === JSON.stringify(['exploded','hud'])", 10)
    # 06큐 대사가 나가면 — 스냅샷을 기다리지 않고 — 카드 화면으로. 그 화면은 이미 공연을 따라가고 있다(전문가 카드 · 06장).
    director.cue_id = "06-bands"
    say(hub, "mc", "06-bands", 901); started(hub, "mc", "06-bands", 901)
    wait(f"{SA}.screen === 'hud'", 10)
    assert js(f"{SA}.why") == "분해도에 06-bands 가 아직 없다 — 카드 화면으로 이어 보기"
    shown = "document.querySelector('iframe.on')"
    win = f"{shown}.contentWindow"
    wait(f"{shown}.getAttribute('data-page') === 'hud'", 5)
    wait(f"{win}.hud && {win}.hud.state.lv === 'l4' && {win}.hud.state.slide === 5", 15)
    wait(f"({win}.document.querySelector('[data-live-badge]')||{{}}).textContent === '공연 따라가는 중'", 15)
    # 초등 · 06 → 카드 화면(초등 카드로 바뀐다). 다시 01 → 웹툰(가졌다). 틀은 다시 읽지 않는다(이미 띄운 화면을 쓴다).
    director.level = "초등"
    wait(f"{SA}.screen === 'hud' && {win}.hud.state.lv === 'l1'", 10)
    director.cue_id = "01-intro"
    say(hub, "mc", "01-intro", 902)
    wait(f"{SA}.screen === 'webtoon'", 10)
    # 일반은 종이 무대(19큐 전부 가졌다)
    director.level = "일반"
    wait(f"{SA}.screen === 'paper' && document.documentElement.getAttribute('data-screen') === 'paper'", 10)
    assert _errors_but_webgl(stage["errors"]) == []


def test_카드_화면은_공연을_따라_장_수준_차례_말풍선을_바꾼다(stage):
    """웹툰·분해도에 없는 큐를 맡는 카드 화면(2026-11-13) — 소리 없이 감독 이벤트만으로 따라간다."""
    js, wait, director, hub = stage["js"], stage["wait"], stage["director"], stage["hub"]
    director.level, director.cue_id = "중고등", "07-maritime"
    js("location.href = '/stage/hud'")
    wait("document.documentElement.getAttribute('data-live') === '1' && window.hud.state.lv === 'l2'", 15)
    assert js("getComputedStyle(document.querySelector('header.bar')).display") == "none"      # 도구줄은 숨긴다
    assert js("document.querySelectorAll('audio').length") == 0                                  # 소리를 만들지 않는다
    say(hub, "mc", "07-maritime", 950); started(hub, "mc", "07-maritime", 950)
    wait("window.hud.state.slide === 6 && window.hud.state.turn === 'open'", 10)
    cue = "JSON.parse(document.getElementById('data').textContent).cues[6]"
    first = js(f"window.hud.chunksOf({cue}.open)[0]")
    wait(f"document.querySelector('.hud.mc .t').textContent === {json.dumps(first)}", 5)
    assert js("document.querySelector('.hud.mc').classList.contains('speaking')") is True
    ended(hub, "mc", "07-maritime", 950)
    say(hub, "docent", "07-maritime:pt0:docent", 951); started(hub, "docent", "07-maritime:pt0:docent", 951)
    wait("window.hud.state.turn === 'docent0' && document.querySelector('.hud.docent').classList.contains('speaking')", 10)
    ans = js(f"window.hud.chunksOf({cue}.lv.l2.ans[0])[0]")
    wait(f"document.querySelector('.hud.docent .t').textContent === {json.dumps(ans)}", 5)   # 중고등 대본
    assert js("document.querySelector('.headline').classList.contains('now')") is True        # 제목은 open·docent0 차례
    # 관람객 질문 흐름 — 생성 답의 글은 싣지 않는다
    say(hub, "docent", "07-maritime:qa", 952); started(hub, "docent", "07-maritime:qa", 952)
    wait("document.querySelector('.hud.docent .t').textContent === '…'", 5)
    # 감독 수준이 바뀌면 그 수준 카드로
    director.level = "전문가"
    wait("window.hud.state.lv === 'l4' && window.hud.state.slide === 6", 10)
    assert _errors_but_webgl(stage["errors"]) == []


def test_조정실_안의_시연_화면이_고른_화면을_머리에_알린다(stage):
    js, wait, director = stage["js"], stage["wait"], stage["director"]
    director.level, director.cue_id = "중고등", "06-bands"
    js("location.href = '/'")
    wait("document.getElementById('stage-screen') && document.getElementById('stage-screen').textContent.indexOf('카드 화면') >= 0", 20)
    assert js("document.getElementById('stage-screen').classList.contains('fallback')") is True
    # 1280×720 을 패널에 맞춰 줄였다 — 틀이 패널 밖으로 안 나간다
    r = js("(function(){var v=document.getElementById('stage-view').getBoundingClientRect(),"
           "f=document.getElementById('stage-frame').getBoundingClientRect();"
           "return [f.width<=v.width+1, f.height<=v.height+1, f.left>=v.left-1, f.top>=v.top-1]})()")
    assert r == [True, True, True, True], r
    assert _errors_but_webgl(stage["errors"]) == []



def test_하이라이트_큐는_수준별_전용_화면으로_간다(stage):
    """2026-11-14 갈래 C·D — 초등·중고등 웹툰, 전문가 분해도가 하이라이트 9큐(01·02·03·04·07·14·17·18·19)로 늘었다.
    하이라이트 코스는 처음부터 끝까지 수준별 전용 화면이고, 하이라이트 밖(06)은 카드 화면이 잇는다. 빌드된 페이지를 그대로 읽는다(매니페스트)."""
    js, wait, director, hub = stage["js"], stage["wait"], stage["director"], stage["hub"]
    SA = "(window.stageAuto||{})"
    director.level, director.cue_id = "초등", "03-theory"
    js("location.href = '/stage/auto'")
    seq = 970
    for lv, cue, want in (("초등", "03-theory", "webtoon"), ("중고등", "19-closing", "webtoon"),
                          ("전문가", "03-theory", "exploded"), ("전문가", "14-mobile", "exploded"),
                          ("전문가", "06-bands", "hud"), ("일반", "17-rover", "paper")):
        director.level, director.cue_id = lv, cue
        seq += 1
        say(hub, "mc", cue, seq)
        wait(f"{SA}.screen === '{want}' && {SA}.cue === '{cue}'", 15)
    assert _errors_but_webgl(stage["errors"]) == []
