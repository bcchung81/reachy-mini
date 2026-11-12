"""분해도 무대(전문가 교육자료, `scripts/handout_exploded`) — 틀·부품 표·빌더의 불변식. 브라우저 없이 도는 것만 둔다.

화면 확인은 `docs/design/exploded-stage.html?cue=NN&t=초`(한 순간 멈춤)와 `?check=1`(두 장을 모두 지어 '대사에 없는 낱말'
경고를 body[data-warn] 에 적는다)로 한다. 캐시 음성이 필요한 실제 빌드는 여기서 하지 않는다(캐시는 저장소 밖).
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

from scripts.handout_exploded import build

ROOT = pathlib.Path(__file__).resolve().parents[1]
EX = ROOT / "scripts" / "handout_exploded"
SOURCES = ("template.html", "scenes.js", "parts.js", "layout.js")
_EXTERNAL = re.compile(r"""(src|href)\s*=\s*["']?https?:|url\(\s*["']?https?:|from\s*["']https?:|import\(\s*["']https?:|fetch\(|XMLHttpRequest|<link\b""")


def _cues():
    return {c["id"]: c for c in build.load_hud()["cues"]}


def test_외부_리소스_검사는_심어_둔_외부_주소를_잡는다():
    # 아래 '없다' 단언들이 공허하지 않다는 대조군(docs/lessons.md — 짝이 없는 부정 단언 금지)
    for bad in ('<script src="https://cdn.x/three.js">', "import * as T from 'https://esm.sh/three'", "url(https://f/a.woff2)", "fetch('/x')"):
        assert _EXTERNAL.search(bad), bad


def test_틀과_장면은_외부_리소스를_부르지_않는다():
    # 전시장은 오프라인이다. three 도 import map 의 data: URL 로만 들어간다 — 틀이 부르는 모듈 이름은 맨 이름뿐
    for name in SOURCES:
        src = re.sub(r"<!--.*?-->", "", (EX / name).read_text(), flags=re.S)
        assert not _EXTERNAL.search(src), name
    tpl = (EX / "template.html").read_text()
    assert sorted(set(re.findall(r"""from\s+'([^']+)'""", tpl))) == sorted(build.IMPORTS.keys() - {"three/core"})


def test_생성물은_import_map_이_전부_data_URL_이고_외부_주소가_없다():
    out = build.OUT
    if not out.exists():
        pytest.skip("생성물이 없다 — TTS_CACHE_DIR=… python -m scripts.handout_exploded.build")
    html = out.read_text()
    m = re.search(r'<script type="importmap">(.*?)</script>', html, re.S)
    imports = json.loads(m.group(1))["imports"]
    assert set(imports) == set(build.IMPORTS) and all(v.startswith("data:text/javascript;base64,") for v in imports.values())
    body = re.sub(r'<script type="importmap">.*?</script>', "", html, flags=re.S)
    body = re.sub(r'<script type="application/json" id="data">.*?</script>', "", body, flags=re.S)
    assert not _EXTERNAL.search(re.sub(r"<!--.*?-->", "", body, flags=re.S))


def test_import_map_은_원본을_고치지_않고_상대_경로만_맨_이름으로_바꾼다():
    imports = json.loads(build.vendor_import_map().replace("<\\/", "</"))["imports"]
    import base64
    mod = base64.b64decode(imports["three"].split(",", 1)[1]).decode()
    assert "from './three.core.js'" not in mod and "from 'three/core'" in mod
    # 바꾼 곳 말고는 원본 그대로(바꾼 문자열만 되돌리면 vendor 파일과 바이트가 같다)
    assert mod.replace("from 'three/core'", "from './three.core.js'") == (EX / "vendor" / "three.module.js").read_text()


def test_vendor_는_받은_원본_그대로이고_라이선스가_있다():
    man = json.loads((EX / "vendor" / "MANIFEST.json").read_text())
    assert man["package"] == "three" and man["version"] == "0.186.1" and man["license"] == "MIT"
    for name, meta in man["files"].items():
        assert hashlib.sha256((EX / "vendor" / name).read_bytes()).hexdigest() == meta["sha256"], name
    assert "MIT License" in (EX / "vendor" / "three-LICENSE").read_text()
    assert "kstost" in (EX / "LICENSE-aimotion").read_text()          # 옮긴 코드(pava·필렛·분해 곡선)의 MIT 고지


def test_글자는_캔버스에_그리지_않는다():
    # 화면의 글은 DOM textContent 로만 넣는다(검증된 카드·대사 그대로 — innerHTML·fillText 금지). 캔버스에는 선·점·고리만
    for name in SOURCES:
        src = (EX / name).read_text()
        assert "innerHTML" not in src and "fillText" not in src and "strokeText" not in src, name


def test_부품_표는_대사와_검증_카드의_낱말만_쓰고_도슨트_턴마다_강조가_있다():
    tables, cues = build.load_tables(), _cues()
    for cid in build.CUE_IDS:
        assert build.check_table(cid, tables[cid], cues[cid]) == [], cid


def test_부품_표가_낱말을_지어내거나_대사에_없는_때를_가리키면_잡는다():
    tables, cues = build.load_tables(), _cues()
    t = json.loads(json.dumps(tables["02-history"]))
    t["parts"][0]["label"] = "안테나"                     # 전문가 대사·카드에 없는 낱말(§7.4 초안의 말)
    t["parts"][1]["say"] = ["송신기"]                     # 도슨트가 말하지 않는 낱말 — 강조 시각을 못 잡는다
    bad = build.check_table("02-history", t, cues["02-history"])
    assert any("'안테나'" in b for b in bad) and any("'송신기'" in b for b in bad)


def test_흐름_매핑의_쉼표가_값을_자르면_모르는_키로_잡는다():
    # 실제로 밟았다: sub: 약 3,500km … 가 "약 3" 으로 잘렸는데 낱말 대조는 통과했다(약·3 은 대사에 있다)
    row = yaml.safe_load("{id: r, shape: receiver, parent: null, rest: [0, 0, 0], dir: [1, 0, 0], dist: 1, order: 0, anchor: [0, 1], "
                         "side: R, label: 세인트존스 (뉴펀들랜드), sub: 약 3,500km (2,200마일), say: [세인트존스에서]}")
    assert row["sub"] == "약 3"
    tables, cues = build.load_tables(), _cues()
    t = json.loads(json.dumps(tables["02-history"]))
    t["parts"].append(row)
    assert any("모르는 키" in b for b in build.check_table("02-history", t, cues["02-history"]))


def test_도슨트_턴에_강조가_하나도_없으면_잡는다():
    tables, cues = build.load_tables(), _cues()
    t = json.loads(json.dumps(tables["01-intro"]))
    for p in t["parts"]:
        p["say"] = [w for w in p.get("say") or [] if w not in ("대국민 전시 공간", "2020년 11월", "진흥과 인력양성")]
        if p.get("label") and not p["say"]:
            p["say"] = ["전파법 제66조"]
    assert any("docent0 에서 강조되는 부품이 없다" in b for b in build.check_table("01-intro", t, cues["01-intro"]))


def test_표의_모양_이름이_모두_scenes_js_에_있다():
    # 없는 모양은 빈 묶음으로 조용히 지나간다(엔진은 경고만) — 표를 늘리면 여기서 걸린다
    src = (EX / "scenes.js").read_text()
    for cid in build.CUE_IDS:
        block = re.search(r"SHAPES\['" + re.escape(cid) + r"'\]\s*=\s*\{(.*?)\n  \};", src, re.S).group(1)
        have = set(re.findall(r"^\s{4}(\w+):\s*function", block, re.M))
        need = {p["shape"] for p in build.load_tables()[cid]["parts"]}
        assert need <= have, (cid, need - have)


def _fake_cache(tmp_path, texts):
    entries = []
    for i, (txt, where) in enumerate(texts):
        key = f"k{i}"
        (tmp_path / f"{key}.pcm").write_bytes(b"\0\0" * 10)
        entries.append({"key": key, "text": txt, "levels": ["전문가"], "where": [where]})
    return entries


def test_빌더는_캐시를_큐시트_자리로_줄_세우고_글이_다르면_멈춘다(tmp_path):
    # 색인 순서 ≠ 말하는 순서(docs/lessons.md) — 일부러 거꾸로 넣는다
    want = "첫 문장이에요. 둘째 문장이에요."
    entries = _fake_cache(tmp_path, [("둘째 문장이에요.", "01-intro 0턴 전문가"), ("첫 문장이에요.", "01-intro 0턴 전문가")])
    got = build.clips(entries, tmp_path, "01-intro", "0턴 전문가", "전문가", want)
    assert [e["text"] for e in got] == ["첫 문장이에요.", "둘째 문장이에요."]
    with pytest.raises(SystemExit):
        build.clips(entries, tmp_path, "01-intro", "0턴 전문가", "전문가", want + " 셋째 문장이에요.")


@pytest.mark.skipif(not shutil.which("node"), reason="node 가 없다")
def test_설명선_배치는_간격_순서_경계를_지키고_가까이_둔다():
    js = r"""
    const L = require(process.argv[1]);
    const res = {};
    // ① 떨어진 기준점은 그 자리 그대로
    let a = [{ay: 200, w: 1, above: 15, below: 40}, {ay: 400, w: 1, above: 15, below: 40}];
    L.column(a, 100, 800, 14); res.free = a.map(i => i.y);
    // ② 몰린 기준점은 간격을 지키며 순서대로 벌어진다(입력 순서를 섞어도)
    let b = [{ay: 305, w: 1, above: 15, below: 42}, {ay: 300, w: 1, above: 15, below: 20}, {ay: 302, w: 1, above: 15, below: 42}];
    const r = L.column(b, 100, 800, 14); res.packed = r.order.map(i => [b[i].ay, b[i].y, b[i].above, b[i].below]);
    // ③ 무거운 쪽(강조)이 자기 기준점에 더 가깝다
    let c = [{ay: 300, w: 4, above: 15, below: 40}, {ay: 301, w: 1, above: 15, below: 40}];
    L.column(c, 100, 800, 14); res.weight = [Math.abs(c[0].y - 300), Math.abs(c[1].y - 301)];
    // ④ 경계: 위로 몰려도 top 아래
    let d = [{ay: 0, w: 1, above: 15, below: 40}, {ay: 5, w: 1, above: 15, below: 40}];
    L.column(d, 100, 800, 14); res.top = d.map(i => i.y);
    // ⑤ 넘치면 over
    let e = Array.from({length: 20}, (_, i) => ({ay: 300 + i, w: 1, above: 15, below: 40}));
    res.over = L.column(e, 100, 500, 14).over;
    console.log(JSON.stringify(res));
    """
    out = json.loads(subprocess.run(["node", "-e", js, str(EX / "layout.js")], capture_output=True, text=True, check=True).stdout)
    assert out["free"] == [200, 400]
    rows = out["packed"]
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)                                   # 기준점 순서 = 라벨 순서
    for (a0, y0, _, b0), (a1, y1, ab1, _) in zip(rows, rows[1:]):
        assert y1 - y0 >= b0 + 14 + ab1 - 1e-6                                                   # 겹치지 않는다
    assert out["weight"][0] < out["weight"][1]
    assert min(out["top"]) >= 100 + 15 - 1e-6
    assert out["over"] is True


# ───────────────────────────────────────────── 공연 모드 계약(로봇 2대가 말하고 화면은 따라간다 — 조율자 LIVE-contract)

def test_발화_표의_턴_이름과_시각_계산은_종이_무대와_같다():
    # 감독의 발화 라벨(open·ask<i>·docent<i>·after)을 이 표로 풀어 장면 시각을 정한다 — 세 교육자료가 다르게 계산하면
    # 같은 발화에 다른 장면이 나온다
    from scripts.handout_paper import build as paper
    assert (build.GAP_SENT, build.GAP_UTT, build.LEAD, build.RATE) == (paper.GAP_SENT, paper.GAP_UTT, paper.LEAD, paper.RATE)
    cue = _cues()["02-history"]
    assert [t for _, t, _, _ in build.turns(cue)] == ["open", "docent0", "ask1", "docent1", "ask2", "docent2", "after"]


def test_장면은_시계_함수_하나만_보고_live_면_오디오를_만들지_않는다():
    tpl = (EX / "template.html").read_text()
    assert re.search(r"function loop\(\) \{\s*var c = sceneClock\(\)", tpl)
    assert "var audios = LIVE ? [] :" in tpl                       # 공연 모드: 로봇이 말한다 — 페이지는 소리를 내지 않는다
    assert "if (ph === 'qa') t = held[ci]" in tpl                    # 질문 흐름: 장면을 마지막 대본 시각에 멈춘다
    assert "if (!opt.qa) cue.utt.forEach" in tpl                     # 질문 흐름의 말풍선에는 대본 글도 생성 글도 싣지 않는다


def test_빌더는_공연_모듈을_인라인하고_없으면_자리만_두며_script_닫는_태그는_거부한다(tmp_path, monkeypatch):
    data = {"level": "전문가", "cues": []}
    mod = tmp_path / "live_follow.js"
    mod.write_text("var LiveFollow = { create: function () { return { enabled: true }; } }; /*MARK-LF*/")
    monkeypatch.setattr(build, "LIVE_JS", mod)
    html = build.assemble(data)
    assert "/*MARK-LF*/" in html and html.index("/*MARK-LF*/") < html.index('<script type="module">')   # 전역 LiveFollow 가 먼저
    monkeypatch.setattr(build, "LIVE_JS", tmp_path / "없음.js")
    assert "live_follow.js 없음" in build.assemble(data)
    mod.write_text("var x = '</script>';")
    monkeypatch.setattr(build, "LIVE_JS", mod)
    with pytest.raises(SystemExit):
        build.assemble(data)


# ───────────────────────────────────────────── 브라우저 통합 — 진짜 대시보드 서버가 준 /stage/exploded 가 감독 이벤트를 따라가는가
# 본보기: tests/test_live_stage.py(종이 무대). 로봇 대신 허브에 감독과 같은 이벤트를 올리고, 헤드리스 Chrome 으로 연 **빌드된 진짜
# 페이지**의 큐·시계·배지·말풍선을 읽는다. Chrome 이나 생성물이 없으면 건너뛴다(생성물 빌드에는 저장소 밖 캐시가 필요하다).
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_live = pytest.mark.skipif(not (pathlib.Path(CHROME).exists() and build.OUT.exists()), reason="Chrome 또는 빌드된 분해도 무대가 없다")
BADGE = "(document.querySelector('[data-live-badge]')||{}).textContent"
UTT = "JSON.parse(document.getElementById('data').textContent).cues[{c}].utt[{k}]"


@pytest.fixture(scope="module")
def stage():
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

    hub, director, warned = DashboardHub(), fake_show.FakeDirector(load_cues(), "전문가"), []
    director.running = True
    ds = DashboardServer(hub, director, interval=0.1, warn=warned.append, motion_pages={"exploded": build.OUT})
    srv = serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.socket.getsockname()[1]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="exploded-live-"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); dport = s.getsockname()[1]
    # WebGL 이 있어야 한다 — GPU 없는 헤드리스에서는 SwiftShader 를 명시적으로 허용한다
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={dport}", "--no-first-run", "--use-angle=swiftshader",
                             "--enable-unsafe-swiftshader", "--autoplay-policy=no-user-gesture-required", f"--user-data-dir={tmp / 'profile'}",
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        call("Page.navigate", url=f"http://127.0.0.1:{port}/stage/exploded")
        wait("document.documentElement.getAttribute('data-ready') === '1'", 40)
        yield {"hub": hub, "js": js, "wait": wait, "errors": errors, "director": director, "sleep": time.sleep}
    finally:
        proc.terminate()
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


def _ev(hub, kind, role, label, seq):
    if kind == "say":
        hub.publish("sent", role=role, type="say", fields={"cue_id": label, "seq": seq, "text": "대사"})
    else:
        hub.publish("recv", role=role, type=kind, fields={"cue_id": label, "seq": seq})


@_live
def test_공연_대시보드가_준_분해도는_공연_모드로_뜨고_소리를_만들지_않는다(stage):
    js = stage["js"]
    assert js("document.documentElement.getAttribute('data-live')") == "1"
    assert js("window.explodedStage.live.enabled") is True
    assert js("document.querySelectorAll('audio').length") == 0
    assert js("['#play','#scrub','#cues','#prev','#nextc'].every(s => document.querySelector(s).hidden)") is True
    stage["wait"](f"{BADGE} === '공연 대기' || {BADGE} === '공연 따라가는 중'")


@_live
def test_공연_대사가_나가면_그_큐로_넘어가고_발화_시작에_맞춰_장면이_흐른다(stage):
    hub, js, wait = stage["hub"], stage["js"], stage["wait"]
    _ev(hub, "say", "mc", "02-history", 201)
    wait("window.explodedStage.cue() === 1")
    wait("document.querySelector('#chip').textContent.indexOf('02') === 0")      # 3D 장면도 02 로 바뀌었다
    t0 = js(UTT.format(c=1, k=0) + ".t0")
    _ev(hub, "speaking_started", "mc", "02-history", 201)
    stage["sleep"](1.5)
    assert js("window.explodedStage.clock()") == pytest.approx(t0 - 0.3 + 1.5, abs=0.35)
    assert js(BADGE) == "공연 따라가는 중"


@_live
def test_공연_발화가_끝나면_턴_끝으로_맞추고_다음_턴_앞에서_기다린다(stage):
    hub, js = stage["hub"], stage["js"]
    _ev(hub, "speaking_ended", "mc", "02-history", 201)
    stage["sleep"](0.5)
    t1, nxt = js(UTT.format(c=1, k=0) + ".t1"), js(UTT.format(c=1, k=1) + ".t0")
    assert t1 - 0.01 <= js("window.explodedStage.clock()") <= nxt
    stage["sleep"](1.0)
    assert js("window.explodedStage.clock()") <= nxt


@_live
def test_공연_도슨트_턴은_그_턴의_장면과_포인트_카드를_보인다(stage):
    # 감독 라벨 "02-history:pt1:docent" → 턴 docent1 — 분해된 기둥, 포인트 카드 02/03, 도슨트 말풍선에 대본 문장
    hub, js, wait = stage["hub"], stage["js"], stage["wait"]
    _ev(hub, "say", "docent", "02-history:pt1:docent", 202)
    _ev(hub, "speaking_started", "docent", "02-history:pt1:docent", 202)
    t0 = js(UTT.format(c=1, k=3) + ".t0")
    assert js(UTT.format(c=1, k=3) + ".turn") == "docent1"
    stage["sleep"](1.2)
    assert js("window.explodedStage.clock()") == pytest.approx(t0 - 0.3 + 1.2, abs=0.35)
    wait("document.querySelector('#p-no').textContent.indexOf('02 / 03') === 0")
    wait("document.querySelector('#b-docent').className.indexOf('bubble on') === 0")
    assert js("document.querySelector('#b-docent').textContent").startswith("맥스웰")


@_live
def test_공연_관람객_질문_흐름에는_장면이_멈추고_생성_답_글은_싣지_않는다(stage):
    hub, js, wait = stage["hub"], stage["js"], stage["wait"]
    _ev(hub, "say", "docent", "02-history:qa", 203)
    _ev(hub, "speaking_started", "docent", "02-history:qa", 203)
    wait(f"{BADGE} === '관람객 질문에 답하는 중'")
    a = js("window.explodedStage.clock()"); stage["sleep"](1.0); b = js("window.explodedStage.clock()")
    assert a == pytest.approx(b, abs=1e-6)
    wait("document.querySelector('#b-docent').className === 'bubble'")          # 말풍선이 비었다(대본도 생성 답도 없음)


@_live
def test_공연_수준이_다르면_배지가_알린다(stage):
    stage["director"].level = "일반"
    stage["wait"](f"({BADGE}||'').indexOf('수준이 다르다') === 0")
    stage["director"].level = "전문가"
    stage["wait"](f"({BADGE}||'').indexOf('수준이 다르다') !== 0")


@_live
def test_공연_자바스크립트_오류가_없다(stage):
    assert stage["errors"] == []
