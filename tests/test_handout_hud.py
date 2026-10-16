"""발표형 교육자료(`scripts/handout_hud/`, 2026-10-06) — 카드 검증기·빌더·브라우저 렌더.

카드는 검수한 고정 대본을 줄여 쓴 것이다. 교육자료에 지어낸 말이 섞이는 것이 가장 나쁘므로, 사람이(또는 모델이) 쓴 카드를
기계가 대본·조사 자료와 대조한다 — 이 테스트가 그 대조 자체와, 지금 있는 19큐 카드 전부를 지킨다.
"""

import copy
import json
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from scripts.handout_hud import build as B
from scripts.handout_hud import cards as C

SOURCES = C.load_sources()
CUE_IDS = list(SOURCES)


def _card(cid):
    return C.load_card_file(C.CARDS_DIR / f"{cid}.yaml")


# ── 지금 있는 카드 ───────────────────────────────────────────────────

def test_큐시트의_모든_큐에_카드_파일이_있다():
    have = {p.stem for p in C.CARDS_DIR.glob("*.yaml")}
    assert have == set(CUE_IDS), (sorted(set(CUE_IDS) - have), sorted(have - set(CUE_IDS)))


@pytest.mark.parametrize("cid", CUE_IDS)
def test_카드가_검증기를_통과한다(cid):
    assert C.validate(_card(cid), SOURCES[cid]) == []


@pytest.mark.parametrize("cid", CUE_IDS)
def test_카드는_포인트마다_하나씩이고_네_수준이_다_있다(cid):
    card, n = _card(cid), SOURCES[cid].n_points
    assert set(card["levels"]) == set(C.LEVELS)
    for lv in C.LEVELS:
        assert len(card["levels"][lv]["items"]) == n


# ── 검증기가 지어낸 말을 잡는다 ───────────────────────────────────────

def _fresh(cid="04-morse"):
    return copy.deepcopy(_card(cid)), SOURCES[cid]


def test_대본에_없는_연도는_잡는다():
    card, src = _fresh()
    card["levels"]["일반"]["items"][0]["b"] += " 1999년에 시작했어요."
    assert any("숫자" in e and "1999" in e for e in C.validate(card, src))


def test_초등은_말하지_않은_숫자를_쓰지_못한다():
    card, src = _fresh()
    card["levels"]["초등"]["headline"] = "1844년에 시작된 이야기예요"
    assert any("초등" in e or "숫자" in e for e in C.validate(card, src))


def test_대본에_없는_영문_약어는_잡는다():
    card, src = _fresh()
    card["levels"]["일반"]["remember"] = "NASA 가 처음 만들었어요."
    assert any("영문" in e and "nasa" in e for e in C.validate(card, src))


def test_단위_약어는_영문_검사에서_뺀다():
    card, src = _fresh("02-history")
    assert C.validate(card, src) == []          # 02 는 km 를 쓴다(대본은 "킬로미터")


def test_대본과_겹치지_않는_본문은_잡는다():
    card, src = _fresh()
    card["levels"]["일반"]["items"][1]["b"] = "고래는 바다에 사는 포유류로 새끼를 낳아 젖을 먹여 기르는 동물이에요."
    assert any("겹침" in e for e in C.validate(card, src))


def test_포인트_수와_다른_카드는_잡는다():
    card, src = _fresh()
    card["levels"]["일반"]["items"].pop()
    assert any("items" in e for e in C.validate(card, src))


def test_수준이_빠진_카드는_잡는다():
    card, src = _fresh()
    del card["levels"]["전문가"]
    assert any("전문가" in e and "빠졌다" in e for e in C.validate(card, src))


def test_길이_한도를_넘는_글은_잡는다():
    card, src = _fresh()
    card["levels"]["일반"]["headline"] = "모스 부호" * 12
    assert any("한도" in e for e in C.validate(card, src))


def test_그림의_어느_포인트인지가_범위_밖이면_잡는다():
    card, src = _fresh()
    v = card["levels"]["일반"]["visual"]
    if v["type"] in ("keyfact", "steps"):
        v["at"] = 9
        assert any("visual.at" in e for e in C.validate(card, src))


def test_근거_줄은_쓴_사실의_가장_약한_등급을_적는다():
    src = SOURCES["04-morse"]
    grades = [f["grade"] for f in src.facts]
    a, b = grades.index("A"), grades.index("B")
    line = C.source_line(src, {"facts_used": [a, b]})
    assert line.startswith("근거 · ") and line.endswith("(신뢰 등급 B)")
    assert "http" not in line, "출처 이름만 적는다 — 주소는 싣지 않는다"


# ── 빌더 ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def built():
    data = B.build_data()
    return data, B.render(data)


def test_빌드는_19큐_네_수준_두_코스를_담는다(built):
    data, _ = built
    assert [c["id"] for c in data["cues"]] == CUE_IDS
    assert [l["key"] for l in data["levels"]] == ["l1", "l2", "l3", "l4"]
    assert [c["name"] for c in data["courses"]] == ["전체", "하이라이트"]
    assert len(data["courses"][0]["ids"]) == 19 and len(data["courses"][1]["ids"]) == 9
    for c in data["cues"]:
        assert set(c["lv"]) == {"l1", "l2", "l3", "l4"}


def test_화면의_대사는_큐시트_그대로다(built):
    """말풍선에 흐르는 글은 로봇이 실제로 하는 말과 같아야 한다 — 요약하지 않는다."""
    data, _ = built
    for c in data["cues"]:
        cue = SOURCES[c["id"]].cue
        assert c["open"] == cue["mc"] and c["after"] == cue["mc_after"]
        for name, key in C.LV_KEY.items():
            assert c["lv"][key]["ans"] == [p["answers"][name] for p in cue["points"]]
            assert c["lv"][key]["ask"] == [p.get("ask") for p in cue["points"]]


def test_결과물은_외부_리소스를_부르지_않는다(built):
    """전시장은 오프라인이다 — CDN·웹폰트·이미지 주소가 한 곳이라도 있으면 그 자리가 빈다."""
    _, html = built
    urls = set(re.findall(r"https?://[^\s'\"<>)]+", html))
    assert urls <= {"http://www.w3.org/2000/svg"}, urls     # SVG 이름공간 식별자일 뿐 요청이 아니다
    assert "src=" not in re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S).split("<body>")[0]
    assert "<link" not in html and "@import" not in html


def test_결과물은_글자를_textContent_로만_넣는다(built):
    _, html = built
    script = html.split('id="data">')[1].split("</script>", 1)[1]
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert banned not in script, banned


def test_데이터_속_script_닫는_태그는_이스케이프된다():
    data = B.build_data()
    data["cues"][0]["open"] = "끝</script><b>x</b>"
    html = B.render(data)
    assert html.count("</script>") == 2, "데이터 블록이 `</script>` 로 일찍 닫히면 페이지가 깨진다"


def test_카드가_검증을_못_넘으면_빌더가_멈춘다(tmp_path, monkeypatch):
    bad = tmp_path / "cards"
    shutil.copytree(C.CARDS_DIR, bad)
    f = bad / "04-morse.yaml"
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    d["levels"]["일반"]["items"][0]["b"] = "대본에 없는 이야기를 길게 지어낸 문장이에요 1999년"
    f.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(C, "CARDS_DIR", bad)
    with pytest.raises(SystemExit, match="검증을 못 넘었다"):
        B.build_data()


def test_카드_파일이_없으면_빌더가_멈춘다(tmp_path, monkeypatch):
    bad = tmp_path / "cards"
    shutil.copytree(C.CARDS_DIR, bad)
    (bad / "19-closing.yaml").unlink()
    monkeypatch.setattr(C, "CARDS_DIR", bad)
    with pytest.raises(SystemExit):
        B.build_data()


# ── 브라우저: 모든 장·수준이 1280×720 에서 넘치지 않는다 ──────────────

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HAVE_BROWSER = pathlib.Path(CHROME).exists() and pytest.importorskip("websockets", reason="websockets 없음") is not None


@pytest.fixture(scope="module")
def page(built):
    if not HAVE_BROWSER:
        pytest.skip("헤드리스 Chrome 이 없다")
    from websockets.sync.client import connect
    _, html = built
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="hud-test-"))
    f = tmp / "handout.html"
    f.write_text(html, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}", "--no-first-run", "--disable-gpu",
                             f"--user-data-dir={tmp / 'profile'}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"); break
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        assert ws_url, "Chrome 디버그 소켓이 안 열렸다"
        ws = connect(ws_url, max_size=None)
        n, errors = [0], []

        def call(method, **params):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            while True:
                m = json.loads(ws.recv(timeout=30))
                if m.get("method") == "Runtime.exceptionThrown":
                    errors.append(json.dumps(m["params"]["exceptionDetails"], ensure_ascii=False)[:300])
                if m.get("id") == n[0]:
                    return m.get("result", {})

        def js(expr):
            r = call("Runtime.evaluate", expression=expr, returnByValue=True)
            if "exceptionDetails" in r:
                errors.append(json.dumps(r["exceptionDetails"], ensure_ascii=False)[:300])
            return r.get("result", {}).get("value")

        call("Runtime.enable"); call("Page.enable")
        call("Emulation.setDeviceMetricsOverride", width=1280, height=720, deviceScaleFactor=1, mobile=False)
        call("Page.navigate", url=f.as_uri()); time.sleep(0.8)
        yield js, errors
    finally:
        proc.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


CHECK = """(function(){
  var vis=document.querySelector('.visual'), cards=document.querySelector('.cards'), slide=document.querySelector('.slide');
  var v=vis.getBoundingClientRect(), c=cards.getBoundingClientRect();
  var o={pageScroll:document.documentElement.scrollHeight-innerHeight, slideOverflow:slide.scrollHeight-slide.clientHeight,
         hscroll:document.documentElement.scrollWidth>innerWidth, visualToCards:Math.round(c.top-v.bottom),
         visualClipped:vis.scrollHeight>vis.clientHeight+1, cardsBottom:Math.round(c.bottom), headline:document.querySelector('.headline').textContent.length};
  ['mc','docent'].forEach(function(k){
    var h=document.querySelector('.hud.'+k), b=h.querySelector('.bubble'), lane=h.parentElement;
    var br=b.getBoundingClientRect(), lr=lane.getBoundingClientRect();
    o[k]={inLane:br.left>=lr.left-1&&br.right<=lr.right+1, overlapsVisual:!(br.right<=v.left||br.left>=v.right||br.bottom<=v.top||br.top>=v.bottom)};
  });
  return JSON.stringify(o);
})()"""


@pytest.mark.parametrize("lv", ["l1", "l2", "l3", "l4"])
def test_모든_장이_이_수준에서_넘치거나_겹치지_않는다(page, lv):
    """1280×720 에서 19장 모두 — 세로로 넘치지 않고, 그림이 카드를 먹지 않고, 말풍선이 구역 안에 있고 그림과 겹치지 않는다.
    말풍선은 가장 긴 조각을 띄운 순간으로 잰다(가리는 면적이 최대일 때)."""
    js, errors = page
    js(f"window.hud.setLevel('{lv}')")
    bad = []
    for i, cid in enumerate(CUE_IDS):
        js(f"window.hud.setCourse('전체'); window.hud.setSlide({i})")
        # 이 장의 모든 발화 중 가장 긴 조각으로 두 말풍선을 채워 가리는 면적이 최대일 때를 잰다
        js("(function(){var w=window.hud.worstChunks(); window.hud.showBoth(w.mc, w.docent);})()")
        o = json.loads(js(CHECK))
        where = f"{cid}/{lv}"
        if o["pageScroll"] > 0 or o["slideOverflow"] > 0 or o["hscroll"]:
            bad.append(f"{where}: 넘친다 {o}")
        if o["visualToCards"] < 0 or o["visualClipped"]:
            bad.append(f"{where}: 그림이 카드를 먹거나 잘렸다 {o['visualToCards']}")
        for k in ("mc", "docent"):
            if not o[k]["inLane"] or o[k]["overlapsVisual"]:
                bad.append(f"{where}: {k} 말풍선이 구역을 벗어나거나 그림과 겹친다 {o[k]}")
    assert not bad, "\n".join(bad)
    assert not errors, errors


def test_코스를_바꾸면_장_목록이_그_코스로_줄고_코스_밖_장이면_첫_장으로_간다(page):
    js, errors = page
    js("window.hud.setCourse('전체'); window.hud.setLevel('l3'); window.hud.setSlide(%d)" % CUE_IDS.index("06-bands"))
    assert js("document.querySelectorAll('#slidesel option').length") == 19
    js("window.hud.setCourse('하이라이트')")          # 06-bands 는 하이라이트에 없다
    assert js("document.querySelectorAll('#slidesel option').length") == 9
    assert js("document.querySelector('#slidesel').selectedOptions[0].textContent").startswith("01 ")
    assert js("document.querySelector('#pos').textContent") == "1 / 9"
    js("document.getElementById('nextslide').click()")
    assert js("document.querySelector('#slidesel').selectedOptions[0].textContent").startswith("02 ")
    js("window.hud.setCourse('전체')")
    assert not errors, errors


def test_포인트가_하나인_큐도_말_순서가_맞고_말하는_구역은_하나뿐이다(page):
    """포인트 수가 큐마다 달라(1~3) 말 순서가 open, docent0, [ask·docent]…, after 로 변한다 — 1개짜리로 잰다."""
    js, errors = page
    cid = "09-special-exhibit"
    js("window.hud.setCourse('전체'); window.hud.setLevel('l3'); window.hud.setSlide(%d)" % CUE_IDS.index(cid))
    js("document.getElementById('speed').value='6'")
    js("window.hud.play()")
    seen, most, t0 = [], 0, time.time()
    while time.time() - t0 < 60:
        s = json.loads(js("JSON.stringify({t:window.hud.state.turn, r:window.hud.state.running,"
                          " n:document.querySelectorAll('.hud.speaking').length})"))
        most = max(most, s["n"])
        if s["t"] and (not seen or seen[-1] != s["t"]):
            seen.append(s["t"])
        if not s["r"] and "after" in seen:
            break
        time.sleep(0.1)
    js("document.getElementById('speed').value='3'; window.hud.reset()")
    assert seen == ["open", "docent0", "after"], seen
    assert most <= 1, "두 구역이 동시에 말하면 가리는 면적이 두 배가 된다"
    assert not errors, errors
