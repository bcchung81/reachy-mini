"""분해도 무대(전문가 교육자료, `scripts/handout_exploded`) — 틀·부품 표·빌더의 불변식. 브라우저 없이 도는 것만 둔다.

화면 확인은 `docs/design/exploded-stage.html?cue=NN&t=초`(한 순간 멈춤)와 `?check=1`(모든 장을 지어 '대사에 없는 낱말'
경고를 body[data-warn] 에 적는다)로 한다. 캐시 음성이 필요한 실제 빌드는 여기서 하지 않는다(캐시는 저장소 밖).
"""
import contextlib
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


def _highlight():
    courses = yaml.safe_load((ROOT / "data" / "courses.yaml").read_text())["courses"]
    return next(c["cues"] for c in courses if c["name"] == "하이라이트")


def _sheet():
    """큐시트 순서(= `data/courses.yaml` 의 '전체' 코스 — cues: all). 교육자료 데이터가 그 순서로 큐를 싣는다"""
    return [c["id"] for c in build.load_hud()["cues"]]


def test_빌드_범위는_큐시트_순서이고_하이라이트_밖은_06_부터_채운다():
    # 2026-11-14 하이라이트 9큐를 다 채웠고(갈래 D), 2026-11-16 하이라이트 밖 10큐를 채운다(계획 `2026-11-16-level-screens-rest.md` §4).
    # 생성물의 장 순서 = 미리보기에서 '다음 장' 으로 이어 듣는 순서라 큐시트 순서여야 한다(하이라이트 순서 뒤에 06 을 덧붙이면 19 다음에 06 이 온다).
    # 06(가장 물건다운 큐)을 먼저 끝내 사용자에게 보인다 — 그래서 06 은 반드시 있다
    assert list(build.CUE_IDS) == [c for c in _sheet() if c in build.CUE_IDS]
    assert "06-bands" in build.CUE_IDS


def test_하이라이트_코스의_모든_큐가_있다():
    # 2026-11-14 7큐(04·07·14·17·18·19)를 다 넣어 strict xfail 표시를 지웠다 — 하이라이트 코스가 분해도로 끝까지 간다
    assert set(_highlight()) <= set(build.CUE_IDS)


def test_전체_코스의_모든_큐가_있다():
    # 전체 코스(cues: all)를 전문가로 돌면 19큐 모두 분해도다. 2026-11-16 하이라이트 밖 10큐(05·06·08~13·15·16)를 다 넣어 strict xfail 표시를 지웠다
    assert list(build.CUE_IDS) == _sheet()


def test_06_대역_탑은_대역마다_같은_간격의_한_층이고_두_이름_칸은_양_끝_대역에_붙는다():
    # 06 은 ITU-R 권고 V.431-8 의 대역 표를 쌓은 탑이다. 대역번호 N 은 0.3×10^N ~ 3×10^N Hz — 대역마다 정확히 10배, 로그 눈금으로 같은 길이다.
    # 탑은 그 약속을 그림으로 말한다: 대역 4(VLF)~11(EHF) 여덟 층이 아래에서 위로, 조립·분해 둘 다 **같은 간격**. 간격이 어긋나면
    # '어떤 대역은 더 넓다' 는 거짓 그림이 된다. 이름 칸 둘은 사실 그대로 — 초장파는 가장 낮은 대역(4)의 **주파수 기준** 이름이라 맨 아래 층의
    # 왼쪽(주파수 기준 열) 칸, 밀리미터파는 가장 높은 대역(11)의 **파장 기준** 이름이라 맨 위 층의 오른쪽(파장 기준 열) 칸이다
    rows = {p["id"]: p for p in build.load_tables()["06-bands"]["parts"]}
    tiers = [rows[f"b{n}"] for n in range(4, 12)]
    assert all(p["dir"] == [0, 1, 0] and p.get("parent") is None for p in tiers)
    ys = [p["rest"][1] for p in tiers]
    ex = [p["rest"][1] + p["dist"] for p in tiers]
    for col in (ys, ex):
        steps = [b - a for a, b in zip(col, col[1:])]
        assert min(steps) > 0 and max(steps) - min(steps) < 1e-6, steps
    assert rows["f4"]["parent"] == "b4" and rows["f4"]["side"] == "L" and rows["f4"]["leave"].startswith("초장파")
    assert rows["w11"]["parent"] == "b11" and rows["w11"]["side"] == "R" and rows["w11"]["leave"].startswith("밀리미터파")


def test_생성물의_큐는_빌드_범위와_같다():
    # 표만 늘리고 다시 빌드하지 않으면 /stage/manifest 가 옛 생성물의 큐로 화면을 고른다(빌드된 페이지에서 읽는다) — 여기서 잡는다
    if not build.OUT.exists():
        pytest.skip("생성물이 없다 — TTS_CACHE_DIR=… python -m scripts.handout_exploded.build")
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', build.OUT.read_text(), re.S)
                      .group(1).replace("<\\/", "</"))
    assert [c["id"] for c in data["cues"]] == list(build.CUE_IDS)


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


def test_카드_낱말이_도슨트_대사에_없거나_순서가_어긋나거나_수가_다르면_잡는다():
    # 03 은 카드 셋(정의·ITU·빛의 속도)이 도슨트 턴 셋(정의+ITU·주파수·파장+c)과 맞지 않는다 — 카드 i 를 docent i 에 묶으면 헤르츠를
    # 말하는 동안 'ITU 전파규칙' 카드가 떴다(docs/lessons.md "턴 번호와 포인트 번호는 같지 않다"). 그래서 표에 카드마다 뜨는 낱말을 적는다
    tables, cues = build.load_tables(), _cues()
    assert build.check_table("03-theory", tables["03-theory"], cues["03-theory"]) == []
    for cards, want in ((["전파법은", "전기장이", "진공에서"], "'전기장이'"),          # 대사에 없는 낱말
                        (["전파법은", "진공에서", "ITU 전파규칙이"], "순서"),          # 말하는 순서와 다르다
                        (["전파법은", "ITU 전파규칙이"], "개수")):                     # 카드 수와 다르다
        t = json.loads(json.dumps(tables["03-theory"]))
        t["cards"] = cards
        assert any(want in b for b in build.check_table("03-theory", t, cues["03-theory"])), cards


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
        # 모양 = 함수 직접(`name: function`) · 함수를 만드는 호출(`name: zoneRing(1.8)` — 07 해역 고리) · 함수 이름(`stage: hamStage,` — 05·10 이
        # 같은 무선국 모양을 같이 쓴다. 없는 이름이면 페이지가 불러올 때 ReferenceError 로 터져 ?check=1 시험이 잡는다). 한 줄에 하나씩 쓴다
        have = set(re.findall(r"^\s{4}(\w+):\s*(?:function\b|\w+\(|\w+\s*,?\s*(?://.*)?$)", block, re.M))
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


@contextlib.contextmanager
def _chrome(url, ready_timeout=40.0):
    """헤드리스 Chrome 으로 url 을 열고 data-ready 를 기다린 뒤 {js, wait, errors, sleep} 를 준다. 끝나면 Chrome 을 내린다.
    공연 통합 시험(대시보드가 준 /stage/exploded)과 `?check=1` 시험(file://)이 같이 쓴다."""
    import socket
    import tempfile
    import time
    import urllib.request

    from websockets.sync.client import connect

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="exploded-chrome-"))
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

        def brief(d, where):
            # 예외 JSON 을 앞 300자로 자르면 정작 메시지(description)가 잘린다 — 무엇이·어디서만 남긴다
            return f"{where}: {(d.get('exception') or {}).get('description') or d.get('text')} @ {d.get('url', '')}:{d.get('lineNumber')}"[:400]

        def call(method, **params):
            n[0] += 1
            cdp.send(json.dumps({"id": n[0], "method": method, "params": params}))
            while True:
                m = json.loads(cdp.recv(timeout=60))
                if m.get("method") == "Runtime.exceptionThrown":
                    errors.append(brief(m["params"]["exceptionDetails"], "페이지"))
                if m.get("id") == n[0]:
                    return m.get("result", {})

        def js(expr):
            r = call("Runtime.evaluate", expression=expr, returnByValue=True)
            if "exceptionDetails" in r:
                errors.append(brief(r["exceptionDetails"], f"평가 {expr[:60]!r}"))
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
        call("Page.navigate", url=url)
        # 탐색 중에는 document.documentElement 가 잠깐 null 이다 — 그때 기다리기 식 자체가 TypeError 를 내 errors 에 쌓이고, 뒤의
        # "오류 0" 단언이 가끔(새로 빌드한 직후 첫 회차에 잘) 빨개졌다. 식을 null 에 안전하게 쓴다
        wait("!!document.documentElement && (document.documentElement.getAttribute('data-ready') === '1' || "
             "document.documentElement.hasAttribute('data-error'))", ready_timeout)
        yield {"js": js, "wait": wait, "errors": errors, "sleep": time.sleep}
    finally:
        proc.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def stage():
    import sys
    import threading

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
    try:
        with _chrome(f"http://127.0.0.1:{port}/stage/exploded") as page:
            yield {**page, "hub": hub, "director": director}
    finally:
        srv.shutdown()


# 모든 장을 짓고(?check=1), 장마다 분해 직후·설명 중간·재조립 직전·점등 뒤를 실제로 그린다 — 낱말 대조 경고뿐 아니라 그리는 동안에만
# 나오는 경고(설명선 열이 넘친다·모양이 없다)와 예외까지 잡는다. 시각은 페이지가 지은 장면의 사건 시각(T_EXP·T_RE·T_ON)에서 고른다
_DRAW_ALL = """(function(){var S=window.explodedStage,n=JSON.parse(document.getElementById('data').textContent).cues.length;
  for(var i=0;i<n;i++){var sc=S.getScene(i);[sc.T_EXP+2,(sc.T_EXP+sc.T_RE)/2,sc.T_RE-.3,sc.T_ON+1].forEach(function(t){S.draw(i,t);});}
  return n;})()"""


@pytest.fixture(scope="module")
def checked():
    with _chrome(build.OUT.as_uri() + "?check=1") as page:
        yield page


# 03 의 포인트 카드 — 카드는 표의 `cards` 낱말을 도슨트가 말할 때 뜨고, 그 도슨트 턴이 끝나면 내려간다(카드가 없는 턴에는 비어 있다)
_CARD_AT = """(function(ci,t){var S=window.explodedStage;S.draw(ci,t);var p=document.querySelector('#point');
  return p.style.visibility==='hidden'?null:document.querySelector('#p-no').textContent+' '+document.querySelector('#p-t').textContent;})"""


@_live
def test_포인트_카드는_그_포인트를_말하는_도슨트_낱말에_뜨고_카드_없는_턴에는_비운다(checked):
    js, ci = checked["js"], build.CUE_IDS.index("03-theory")
    sc = f"window.explodedStage.getScene({ci})"
    at = js(f"{sc}.cardAt.map(function(c){{return [c.t0, c.t1];}})")
    utt = {u["turn"]: u for u in js(f"{sc}.cue.utt")}
    assert len(at) == 3 and at[0][0] < at[1][0] < at[2][0]
    assert utt["docent0"]["t0"] - 0.3 <= at[1][0] <= utt["docent0"]["t1"]          # ITU 는 0턴 안에서(ITU 전파규칙이)
    assert utt["docent2"]["t0"] <= at[2][0] <= utt["docent2"]["t1"]                # 빛의 속도 c 는 2턴(진공에서)
    show = lambda t: js(f"{_CARD_AT}({ci},{t})")
    assert show(at[0][0] + 0.8) == "01 / 03 전파법상 정의"
    assert show(at[1][0] + 0.8) == "02 / 03 ITU 전파규칙"
    assert show((utt["docent1"]["t0"] + utt["docent1"]["t1"]) / 2) is None         # 주파수·헤르츠를 말하는 동안 — 맞는 카드가 없다
    assert show(at[2][0] + 0.8) == "03 / 03 빛의 속도 c"
    assert checked["errors"] == []


@_live
def test_투명_재질에는_껍질_외곽선을_붙이지_않는다(checked):
    # 뒷면 껍질이 유리를 통해 비쳐 강조될 때 꽉 찬 파란 상자로 보였다(19 선 상자 — 2026-11-14 헤드리스 캡처로 찾음). 대조: 유리 메시가 실제로 있다
    r = checked["js"]("""(function(){var S=window.explodedStage,n=JSON.parse(document.getElementById('data').textContent).cues.length,glass=0,bad=0;
      for(var i=0;i<n;i++)S.getScene(i).parts.forEach(function(p){p.shape.traverse(function(o){if(o.isMesh&&o.material&&o.material.transparent&&o.material.type!=='ShaderMaterial')glass++;});
        p.hulls.forEach(function(h){if(h.parent.material.transparent)bad++;});});return [glass,bad];})()""")
    assert r[0] > 0 and r[1] == 0, r


@_live
def test_모든_큐의_도슨트_턴마다_페이지가_지은_강조_사건이_있다(checked):
    # 표 대조(check_table)는 say 낱말이 도슨트 대사 **글**에 있는지만 본다. 페이지는 낱말 시각을 문장 안 글자 위치로 다시 풀므로(wordTime),
    # 실제로 그 턴 안에 강조 사건이 생겼는지는 지은 장면에서 확인한다 — 19큐 모두, 도슨트 턴마다(계획 2026-11-16 §4.5 "모든 큐의 도슨트 0턴에 강조 부품")
    r = checked["js"]("""(function(){var S=window.explodedStage,n=JSON.parse(document.getElementById('data').textContent).cues.length,bad=[];
      for(var i=0;i<n;i++){var sc=S.getScene(i);sc.cue.utt.forEach(function(u){if(u.role!=='docent')return;
        if(!sc.events.some(function(e){return e.t>=u.t0-.3&&e.t<=u.t1;}))bad.push(sc.cue.id+' '+u.turn);});}
      return {n:n,bad:bad};})()""")
    assert r["n"] == len(build.CUE_IDS) and r["bad"] == [], r


@_live
def test_모든_큐가_check_에서_경고와_오류가_없다(checked):
    js = checked["js"]
    assert js("document.documentElement.getAttribute('data-error')") is None          # WebGL 이 열렸다(SwiftShader)
    assert json.loads(js("document.body.getAttribute('data-warn')")) == []             # 장면을 다 지을 때의 낱말 대조
    assert js(_DRAW_ALL) == len(build.CUE_IDS)
    assert js("window.explodedStage.warn") == []                                       # 그리는 동안의 경고(열 넘침 등)
    assert checked["errors"] == []


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
    # 감독 라벨 "02-history:pt1:docent" → 턴 docent1 — 분해된 기둥, 도슨트 말풍선에 대본 문장, 포인트 카드 01/03 '맥스웰'.
    # 1턴은 "맥스웰 방정식이 …" 로 시작한다 — 예전에는 카드 i = 도슨트 i턴이라 여기서 '02/03 헤르츠' 가 떴다(2026-11-14 `cards` 로 고침:
    # 도입 턴은 카드 없음, 맥스웰 카드는 1턴 시작, 헤르츠 카드는 "헤르츠가" 부터)
    hub, js, wait = stage["hub"], stage["js"], stage["wait"]
    _ev(hub, "say", "docent", "02-history:pt1:docent", 202)
    _ev(hub, "speaking_started", "docent", "02-history:pt1:docent", 202)
    t0 = js(UTT.format(c=1, k=3) + ".t0")
    assert js(UTT.format(c=1, k=3) + ".turn") == "docent1"
    stage["sleep"](1.2)
    assert js("window.explodedStage.clock()") == pytest.approx(t0 - 0.3 + 1.2, abs=0.35)
    wait("document.querySelector('#p-no').textContent.indexOf('01 / 03') === 0 && "
         "document.querySelector('#p-t').textContent.indexOf('맥스웰') === 0")
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
