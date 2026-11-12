"""웹툰 칸 연출 교육자료(`scripts/handout_webtoon`) — 빌더·콘티·틀의 불변식.

화면 확인은 `docs/design/webtoon-stage.html?lv=초등&cue=02&t=초`(한 순간 멈춤)와 `?check=1`(두 수준 × 모든 큐를 지어
'대사에 없는 낱말'·초등 숫자 경고를 body[data-warn], 배치 문제를 body[data-issues] 에 적는다)로 한다.
빌더 규칙은 가짜 캐시로(브라우저·ffmpeg 없이), 콘티는 실제 캐시가 있을 때만 대조한다.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

from scripts.handout_webtoon import build as B

ROOT = pathlib.Path(__file__).resolve().parents[1]
WT = ROOT / "scripts" / "handout_webtoon"
OUT = ROOT / "docs" / "design" / "webtoon-stage.html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ── 가짜 캐시 ────────────────────────────────────────────────────────────────
def _cue():
    return {"id": "99-test", "no": "99", "title": "시험", "n": 2,
            "open": "가나다. 라마바.", "after": "사아자.",
            "lv": {"l1": {"ask": [None, "차카타?"], "ans": ["파하. 거너.", "더러머."],
                          "headline": "h", "items": [], "remember": "r", "visual": {}}}}


def _cache(tmp_path, reverse_open=False):
    rows = [("가나다.", "99-test 오프닝", []), ("라마바.", "99-test 오프닝", []),
            ("파하.", "99-test 0턴 초등", ["초등"]), ("거너.", "99-test 0턴 초등", ["초등"]),
            ("차카타?", "99-test 1턴 질문", []), ("더러머.", "99-test 1턴 초등", ["초등"]),
            ("사아자.", "99-test 받아치기", [])]
    if reverse_open:
        rows[0], rows[1] = rows[1], rows[0]
    entries = []
    for i, (text, where, lv) in enumerate(rows):
        key = f"k{i}"
        (tmp_path / f"{key}.pcm").write_bytes(bytes(2 * 2400 * (i + 1)))      # 0.1초 × (i+1)
        entries.append({"key": key, "text": text, "levels": lv, "where": [where]})
    (tmp_path / "index.json").write_text(json.dumps({"engine": "elevenlabs", "entries": entries}, ensure_ascii=False))
    return entries


BOARD = [{"u": "open", "n": 2, "kind": "wide", "art": "hall"},
         {"u": "docent0", "n": 1, "kind": "normal", "art": "a"},
         {"u": "docent0", "n": 1, "kind": "normal", "art": "b"},
         {"u": "ask1", "n": 1, "kind": "band", "art": "ask"},
         {"u": "docent1", "n": 1, "kind": "slant", "art": "s", "brk": "ribbon"},
         {"kind": "silent", "art": "t"},
         {"u": "after", "n": 1, "kind": "free", "art": "f"}]


def _plan(tmp_path, board=BOARD, **kw):
    entries = _cache(tmp_path, **kw)
    seq = B.utterances(entries, tmp_path, _cue(), "l1", "초등")
    return seq, B.plan_panels(board, seq, "시험")


def test_색인_순서가_뒤집혀도_큐시트_순서로_잇는다(tmp_path):
    # 색인 순서는 말하는 순서가 아니다(docs/lessons.md) — 큐시트 글 안의 자리로 줄 세운다
    seq, _ = _plan(tmp_path, reverse_open=True)
    assert [e["text"] for e in seq[0][2]] == ["가나다.", "라마바."]
    assert [t for _, t, _ in seq] == ["open", "docent0", "ask1", "docent1", "after"]   # 감독 발화 라벨이 풀리는 이름


def test_캐시와_큐시트가_다르면_멈춘다(tmp_path):
    entries = _cache(tmp_path)
    cue = _cue(); cue["open"] = "가나다. 다른 문장."
    with pytest.raises(SystemExit, match="캐시와 큐시트가 다르다"):
        B.utterances(entries, tmp_path, cue, "l1", "초등")


@pytest.mark.parametrize("board, msg", [
    (BOARD[:-1], "덮지 않는다"),                                                          # after 를 안 덮으면
    ([dict(BOARD[0], n=3)] + BOARD[1:], "남은 문장"),                                      # 문장 수가 넘치면
    ([BOARD[1]] + BOARD[:1] + BOARD[2:], "차례가 아니다"),                                 # 순서가 틀리면
    (BOARD[:4] + [dict(BOARD[4], brk=None)] + BOARD[5:], "칸 깨기"),                       # 칸 깨기가 없으면
    (BOARD[:5] + BOARD[6:], "다음 칸은 침묵 칸"),                                          # 깨기 다음이 침묵 칸이 아니면
])
def test_콘티가_문장을_빠뜨리거나_남기면_멈춘다(tmp_path, board, msg):
    # 조용히 문장이 빠진 칸을 만들지 않는다 — 대본이 바뀌어 캐시 문장 수가 달라지면 여기서 걸린다
    board = [{k: v for k, v in b.items() if v is not None} for b in board]
    with pytest.raises(SystemExit, match=msg):
        _plan(tmp_path, board=board)


def test_쉼은_경계_종류마다_다르고_발화_안은_GAP_SENT_다(tmp_path):
    seq, panels = _plan(tmp_path)
    pcm, utts, pans = B.assemble(panels, lambda e: (tmp_path / f"{e['key']}.pcm").read_bytes())
    gaps = [round(b["t0"] - a["t1"], 3) for a, b in zip(pans, pans[1:])]
    P = B.PAUSE
    # 오프닝→답 · 같은 발화 칸 나눔 · 답→다음 질문 · 질문→답 · 침묵 칸 앞 · 침묵 칸 뒤
    assert gaps == [P["answer"], B.GAP_SENT, P["turn"], P["answer"], P["into_silent"], P["out_silent"]]
    assert B.GAP_SENT == P["split"] < P["answer"] < P["turn"] < P["into_silent"]           # 여백 리듬: 좁음 → 넓음
    # 공연 모드 계약: LiveFollow 는 발화마다 앵커를 잡고 그 안은 캐시 PCM 시각 그대로 흐른다고 본다 —
    # 그래서 발화 **안** 문장 간격은 종이 무대와 같은 GAP_SENT 여야 한다(칸이 나뉘어도)
    for u in utts:
        for a, b in zip(u["s"], u["s"][1:]):
            assert round(b["t0"] - a["t1"], 3) == B.GAP_SENT, u["turn"]
    assert [u["turn"] for u in utts] == ["open", "docent0", "ask1", "docent1", "after"]
    assert utts[0]["s"][0]["t0"] == B.LEAD
    sil = next(p for p in pans if p["kind"] == "silent")
    assert round(sil["t1"] - sil["t0"], 3) == P["silent"]
    assert len(pcm) / 2 / B.RATE == pytest.approx(pans[-1]["t1"] + B.TAIL, abs=1e-3)


def test_콘티는_실제_캐시의_문장을_모두_덮는다():
    # 실제 ElevenLabs 캐시로 두 수준 × 콘티의 모든 큐를 펼친다(ffmpeg 없이) — 캐시가 없는 기계에서는 건너뛴다
    cdir = B.cache_dir()
    if not (cdir / "index.json").exists():
        pytest.skip(f"캐시 없음: {cdir}")
    data, board = B.load_hud(), yaml.safe_load(B.BOARD.read_text())
    entries = json.loads((cdir / "index.json").read_text())["entries"]
    cues = {c["id"]: c for c in data["cues"]}
    for cid, by_level in board.items():
        for lkey, lname in B.LEVELS:
            seq = B.utterances(entries, cdir, cues[cid], lkey, lname)
            panels = B.plan_panels(by_level[lname], seq, f"{cid} {lname}")
            assert sum(len(p["clips"]) for p in panels) == sum(len(s[2]) for s in seq)


def test_콘티의_그림_이름은_장면에_모두_있다():
    arts = set(re.findall(r"ART\.(\w+)\s*=", (WT / "scenes.js").read_text()))
    brks = set(re.findall(r"BRK\.(\w+)\s*=", (WT / "scenes.js").read_text()))
    board = yaml.safe_load((WT / "storyboard.yaml").read_text())
    used = {p["art"] for lv in board.values() for ps in lv.values() for p in ps}
    used_brk = {p["brk"] for lv in board.values() for ps in lv.values() for p in ps if p.get("brk")}
    assert used - arts == set() and used_brk - brks == set()


def test_틀과_장면은_외부_리소스를_부르지_않는다():
    # 전시장은 오프라인이다. 주석의 출처 링크 말고는 http 주소를 불러오지 않는다(글꼴도 시스템 글꼴)
    names = [WT / "template.html", WT / "scenes.js"] + ([OUT] if OUT.exists() else [])
    for f in names:
        src = re.sub(r"<!--.*?-->", "", f.read_text(), flags=re.S)
        assert not re.search(r"""(src|href)\s*=\s*["']https?:|url\(\s*["']?https?:|@import|<link\b|<script[^>]+src=|\bimport\s*\(""", src), f.name


def test_글자는_캔버스에_그리지_않고_그림은_t_의_식이다():
    # 화면의 글은 DOM textContent 로만(검증된 카드·대사 그대로). 그림은 시각 t 의 순수 함수(되감아도 같은 그림)
    for name in ("template.html", "scenes.js"):
        src = (WT / name).read_text()
        assert "innerHTML" not in src and "fillText" not in src and "strokeText" not in src, name
        assert "Math.random" not in src and "Date.now" not in src and "new Date" not in src, name


def test_공연_모드는_시계_함수_하나로_따라가고_오디오를_만들지_않는다():
    src = (WT / "template.html").read_text()
    assert src.count("function clock()") == 1 and "const t = clock();" in src
    assert "LiveFollow.create(" in src and "/*__LIVE__*/" in src
    assert "const audio = (li, ci) => { if (LIVE) return null;" in src                 # ?live 면 Audio 를 만들지 않는다
    assert "lf.phase() === 'qa'" in src                                                 # 관람객 질문 흐름은 장면을 멈춘다
    if B.LIVE_JS.exists() and OUT.exists():
        page = OUT.read_text()                                                          # 빌더가 공용 모듈을 인라인했다
        assert "root.LiveFollow = api" in page and "공연 모드 모듈 없음" not in page


@pytest.mark.skipif(not (os.path.exists(CHROME) and OUT.exists()), reason="Chrome 또는 생성물 없음")
def test_생성물_check_경고와_배치_문제가_없다():
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--window-size=1600,948", "--virtual-time-budget=8000",
                          "--dump-dom", f"file://{OUT}?check=1"], capture_output=True, text=True, timeout=90).stdout
    body = re.search(r"<body([^>]*)>", out).group(1)
    import html
    get = lambda k: json.loads(html.unescape(re.search(k + r'="([^"]*)"', body).group(1)))   # noqa: E731
    assert get("data-warn") == []
    assert get("data-issues") == []


# ── 공연 모드 통합 — 진짜 대시보드 서버가 준 웹툰(`/stage/webtoon`)이 감독 이벤트를 따라가는가 ─────────────────────
# 본보기: tests/test_live_stage.py(종이 무대). 로봇 대신 허브에 감독과 같은 이벤트를 올리고, 헤드리스 Chrome 으로 연 **빌드된 진짜
# 페이지**의 큐·시계·수준·배지를 window.webtoonStage 로 읽는다. 웹툰은 한 HTML 에 초등·중고등을 담아 감독 수준을 따라 바꾸고,
# 운영자가 직접 고른 수준이 있으면 그쪽을 지킨다. Chrome 이 없으면 건너뛴다.
BADGE = "(document.querySelector('[data-live-badge]')||{}).textContent"
WS = "window.webtoonStage"
UTT = "JSON.parse(document.getElementById('data').textContent).levels[{li}].cues[{c}].utt[{k}]"


@pytest.fixture(scope="module")
def live():
    if not (os.path.exists(CHROME) and OUT.exists() and B.LIVE_JS.exists()):
        pytest.skip("Chrome·빌드된 웹툰·공연 모듈 중 하나가 없다")
    import socket
    import sys
    import tempfile
    import threading
    import time
    import urllib.request

    from websockets.sync.client import connect
    from websockets.sync.server import serve

    sys.path.insert(0, str(ROOT / "scripts" / "handout_live"))
    import fake_show
    from stage.cues import load_cues
    from stage.dashboard import DashboardServer
    from stage.dashboard_hub import DashboardHub

    hub, director, warned = DashboardHub(), fake_show.FakeDirector(load_cues(), "초등"), []
    director.running = True
    ds = DashboardServer(hub, director, interval=0.1, warn=warned.append, motion_pages={"webtoon": OUT})
    srv = serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.socket.getsockname()[1]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="webtoon-live-"))
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
        call("Page.navigate", url=f"http://127.0.0.1:{port}/stage/webtoon")
        wait("document.documentElement.getAttribute('data-ready') === '1'", 30)
        yield {"hub": hub, "js": js, "wait": wait, "errors": errors, "director": director, "sleep": time.sleep}
    finally:
        proc.terminate()
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


def _say(hub, role, label, seq, kind):
    if kind == "say":
        hub.publish("sent", role=role, type="say", fields={"cue_id": label, "seq": seq, "text": "대사"})
    else:
        hub.publish("recv", role=role, type=kind, fields={"cue_id": label, "seq": seq})


def test_공연_대시보드가_준_웹툰은_공연_모드로_뜨고_소리를_만들지_않는다(live):
    js = live["js"]
    assert js("document.documentElement.getAttribute('data-live')") == "1"
    assert js(f"{WS}.live.enabled") is True
    assert js(f"{WS}.audios()") == 0 and js("document.querySelectorAll('audio').length") == 0
    assert js("document.querySelector('#play').hidden && document.querySelector('#scrub').hidden && document.querySelector('#cues').hidden") is True
    live["wait"](f"{WS}.level() === '초등'")                                        # 감독 수준(초등)을 따른다
    live["wait"](f"{BADGE} === '공연 대기' || {BADGE} === '공연 따라가는 중'")


def test_공연_대사가_나가면_그_큐로_넘어가고_발화_시작에_맞춰_장면이_흐른다(live):
    hub, js, wait = live["hub"], live["js"], live["wait"]
    _say(hub, "mc", "02-history", 101, "say")
    wait(f"{WS}.cue() === 1")
    t0 = js(UTT.format(li=0, c=1, k=0) + ".t0")
    _say(hub, "mc", "02-history", 101, "speaking_started")
    live["sleep"](1.5)
    t = js(f"{WS}.clock()")
    assert t == pytest.approx(t0 - 0.3 + 1.5, abs=0.35), (t, t0)                    # 소리 지연 0.3초 보정 + 1.5초 경과
    assert js(f"{BADGE}") == "공연 따라가는 중"
    # 칸이 그 시각의 칸이다 — 첫 풍선이 보이고, 사회자 로봇이 켜져 있다
    assert js("[...document.querySelectorAll('.sroot')].filter(r => r.style.display !== 'none').length") == 1
    assert js("[...document.querySelectorAll('.bl')].some(b => b.style.visibility === 'visible')") is True
    assert js("document.querySelector('#rb-mc').classList.contains('on')") is True


def test_공연_발화가_끝나면_턴_끝으로_맞추고_다음_턴_앞에서_기다린다(live):
    hub, js = live["hub"], live["js"]
    _say(hub, "mc", "02-history", 101, "speaking_ended")
    live["sleep"](0.5)
    t1, nxt = js(UTT.format(li=0, c=1, k=0) + ".t1"), js(UTT.format(li=0, c=1, k=1) + ".t0")
    t = js(f"{WS}.clock()")
    assert t1 - 0.01 <= t <= nxt, (t, t1, nxt)
    live["sleep"](1.2)
    assert js(f"{WS}.clock()") <= nxt                                               # 다음 턴 그림(칸)을 먼저 꺼내지 않는다


def test_공연_관람객_질문_흐름에는_장면이_멈춘다(live):
    hub, js, wait = live["hub"], live["js"], live["wait"]
    _say(hub, "docent", "02-history:qa", 102, "say")
    _say(hub, "docent", "02-history:qa", 102, "speaking_started")
    wait(f"{BADGE} === '관람객 질문에 답하는 중'")
    a = js(f"{WS}.clock()"); live["sleep"](1.0); b = js(f"{WS}.clock()")
    assert a == pytest.approx(b, abs=1e-6)
    _say(hub, "docent", "02-history:qa", 102, "speaking_ended")


def test_공연_감독_수준을_따라_바꾸고_이_화면에_없는_수준이면_배지로_알린다(live):
    js, wait, d = live["js"], live["wait"], live["director"]
    d.level = "중고등"
    wait(f"{WS}.level() === '중고등'")                                              # 한 HTML 이 두 수준을 담는다 — 스스로 바꾼다
    assert js("document.querySelector('#lvseg [aria-pressed=\"true\"]').textContent") == "중고등"
    d.level = "전문가"                                                              # 이 화면에 없는 수준 — 그대로 두고 알린다
    wait(f"({BADGE}||'').indexOf('수준이 다르다') === 0")
    assert js(f"{WS}.level()") == "중고등"
    d.level = "중고등"
    wait(f"({BADGE}||'').indexOf('수준이 다르다') !== 0")


def test_공연_직접_고른_수준이_감독_수준보다_이긴다(live):
    js, wait, d = live["js"], live["wait"], live["director"]
    js("[...document.querySelectorAll('#lvseg button')].find(b => b.textContent === '초등').click()")
    wait(f"{WS}.level() === '초등'")
    d.level = "중고등"                                                              # 감독이 바꿔도 운영자가 고른 초등을 지킨다
    wait(f"({BADGE}||'').indexOf('수준이 다르다') === 0")
    assert js(f"{WS}.level()") == "초등"


def test_공연_자바스크립트_오류가_없다(live):
    assert live["errors"] == []
