"""분해도 무대(전문가 교육자료) 만들기 — 01·02 시안.

    TTS_CACHE_DIR=~/.local/share/reachy-mini-tts/cache-elevenlabs .venv/bin/python -m scripts.handout_exploded.build
    # → docs/design/exploded-stage.html

종이 무대(`scripts/handout_paper/build.py`)와 같은 뼈대다.
- 글(제목·카드·대사)은 `docs/design/handout-hud.html` 에 이미 검증돼 들어간 데이터(전문가 = l4)를 그대로 읽는다(새 사실 없음).
- 음성은 새로 합성하지 않는다. 고정 대사 TTS 캐시의 문장별 PCM 을 큐마다 한 줄로 이어 mp3 로 넣는다. 캐시 색인 순서는 말하는
  순서가 아니므로 큐시트 글 안의 위치로 줄 세우고, 이어 붙인 글이 큐시트와 다르면 **멈춘다**(docs/lessons.md).
- 장면은 `tables.yaml` 의 부품 표가 정한다. 라벨 낱말이 그 큐의 대사·검증 카드에 없거나, 강조·분리 낱말(say·leave)이 도슨트
  대사에 없으면 **멈춘다**(조용히 지어낸 라벨이 화면에 오르지 않게).
- three.js 는 `vendor/`(npm 원본, 해시는 MANIFEST.json)를 import map 의 data: URL 로 내장한다 — 전시장은 오프라인이다.
  해시가 MANIFEST 와 다르면 멈춘다(누가 손으로 고친 라이브러리가 섞이지 않게).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import wave

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
HUD = ROOT / "docs" / "design" / "handout-hud.html"
ICON = ROOT / "scripts" / "handout_hud" / "reachy-mini-icon.png"
VENDOR = HERE / "vendor"
OUT = ROOT / "docs" / "design" / "exploded-stage.html"
# 공연 모드(?live) 모듈 — 조율자가 만든다. 세 교육자료가 같은 파일을 인라인한다(접속·배지 모양이 같게). 없으면 경고하고 자리만 둔다
LIVE_JS = ROOT / "scripts" / "handout_live" / "live_follow.js"
CUE_IDS = ("01-intro", "02-history")      # 시안 범위 — 19큐 확장은 사용자가 시안을 본 뒤에 정한다
LEVEL_KEY, LEVEL_NAME = "l4", "전문가"
RATE = 24000
# 발화 표(utt)의 시각 계산은 종이 무대 빌더와 **같아야** 한다(GAP_SENT·GAP_UTT·LEAD) — 공연 모드에서 감독의 발화 라벨(턴 이름)을
# 이 표로 풀어 장면 시각을 정하므로, 세 교육자료가 다르게 계산하면 같은 발화에 다른 장면이 나온다. TAIL 은 큐 끝 여유라 따로 둔다
GAP_SENT, GAP_UTT, LEAD, TAIL = 0.16, 0.5, 0.9, 3.2   # 초 — 꼬리를 길게: 재조립·점등이 끝까지 보이게
# import map 이름 → vendor 파일. three.module.js 는 './three.core.js' 를 상대 경로로 부르는데 data: URL 모듈에서는 상대 경로가
# 풀리지 않는다 → 그 한 곳만 맨 이름 'three/core' 로 바꾼다(원본 파일은 그대로 두고 빌드 때만).
IMPORTS = {"three": "three.module.js", "three/core": "three.core.js",
           "three/addons/RoomEnvironment.js": "RoomEnvironment.js",
           "three/addons/LightProbeGenerator.js": "LightProbeGenerator.js",
           "three/addons/RoundedBoxGeometry.js": "RoundedBoxGeometry.js"}
_SPLIT = re.compile(r"[\s·—()/]+")       # 라벨 낱말 나누기 — 숫자 안의 쉼표(3,500km)는 나누지 않는다
# 부품 표 한 행에 올 수 있는 키. 흐름 매핑 {…} 안의 쉼표는 값을 자르고 나머지를 **새 키**로 만든다("약 3,500km" → sub "약 3" +
# 키 "500km (2") — 잘린 값은 낱말 대조를 통과해 버리므로(약·3 은 대사에 있다) 모르는 키로 잡는다
PART_KEYS = {"id", "shape", "parent", "rest", "dir", "dist", "order", "delay", "spin", "tilt", "phi", "over", "anchor", "side",
             "label", "sub", "say", "leave", "ghost", "hull"}


def cache_dir() -> pathlib.Path:
    env = os.environ.get("TTS_CACHE_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path(os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")).expanduser() / "cache-elevenlabs"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def load_hud() -> dict:
    return json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', HUD.read_text(), re.S).group(1))


def load_tables() -> dict:
    return yaml.safe_load((HERE / "tables.yaml").read_text())


def turns(cue: dict) -> list[tuple[str, str, str, str | None]]:
    """발화 순서: (역할, 턴 이름, 큐시트 글, 캐시 색인의 where 꼬리표 수준) — 종이 무대와 같은 순서"""
    L = cue["lv"][LEVEL_KEY]
    seq = [("mc", "open", cue["open"], None)]
    for i in range(cue["n"]):
        if L["ask"][i]:
            seq.append(("mc", f"ask{i}", L["ask"][i], None))
        seq.append(("docent", f"docent{i}", L["ans"][i], LEVEL_NAME))
    seq.append(("mc", "after", cue["after"], None))
    return seq


def _tag(turn: str) -> str:
    if turn == "open":
        return "오프닝"
    if turn == "after":
        return "받아치기"
    if turn.startswith("ask"):
        return f"{turn[3:]}턴 질문"
    return f"{turn[6:]}턴 {LEVEL_NAME}"


def card_strings(card: dict) -> list[str]:
    """검증된 카드(이 수준)의 글 — 헤드라인·포인트·기억해 두기·그림(facts·steps·route 등)"""
    out = [card["headline"], card["remember"]] + [x for it in card["items"] for x in (it["t"], it["b"])]

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in ("type", "at", "mode"):
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(card["visual"])
    return out


def corpus(cue: dict) -> str:
    """라벨 낱말이 있어야 하는 곳: 그 큐 대사(전문가) + 검증 카드. 공백을 지우지 않는다(낱말 단위로 찾는다)"""
    return "\n".join([t for _, _, t, _ in turns(cue)] + card_strings(cue["lv"][LEVEL_KEY]))


def words(text: str) -> list[str]:
    return [w for w in _SPLIT.split(text or "") if w]


def check_table(cid: str, table: dict, cue: dict) -> list[str]:
    """부품 표 대조 — 문제를 모두 모아 돌려준다(빈 목록이면 통과)"""
    bad: list[str] = []
    text = corpus(cue)
    docent = "\n".join(t for r, _, t, _ in turns(cue) if r == "docent")
    parts = table.get("parts") or []
    ids = [p["id"] for p in parts]
    if len(set(ids)) != len(ids):
        bad.append(f"{cid}: 부품 id 가 겹친다 {ids}")
    by = {p["id"]: p for p in parts}
    for p in parts:
        where = f"{cid}/{p['id']}"
        extra = sorted(set(p) - PART_KEYS)
        if extra:
            bad.append(f"{where}: 모르는 키 {extra} — 값 안의 쉼표가 흐름 매핑을 잘랐나(쉼표가 든 글은 따옴표로)")
        for k in ("shape", "rest", "dir", "dist", "order", "anchor", "side"):
            if k not in p:
                bad.append(f"{where}: {k} 가 없다")
        if p.get("side") not in ("L", "R"):
            bad.append(f"{where}: side 는 L 또는 R — {p.get('side')!r}")
        if p.get("parent") is not None and p["parent"] not in by:
            bad.append(f"{where}: 부모 {p['parent']!r} 가 표에 없다")
        seen, q = set(), p
        while q and q.get("parent"):
            if q["id"] in seen:
                bad.append(f"{where}: 부모 관계가 돈다")
                break
            seen.add(q["id"])
            q = by.get(q["parent"])
        for fld in ("label", "sub"):
            for w in words(p.get(fld)):
                if w not in text:
                    bad.append(f"{where}: 대사·카드에 없는 낱말 {w!r} ({fld} {p[fld]!r})")
        if p.get("label") and not p.get("say"):
            bad.append(f"{where}: 라벨이 있으면 say(설명선이 나오는 낱말)가 있어야 한다")
        for w in list(p.get("say") or []) + ([p["leave"]] if p.get("leave") else []):
            if w not in docent:
                bad.append(f"{where}: 도슨트 대사에 없는 낱말 {w!r} (say/leave)")
    for ln in table.get("links") or []:
        for k in ("from", "to"):
            if ln.get(k) not in by:
                bad.append(f"{cid}: links 의 {k} {ln.get(k)!r} 가 표에 없다")
        if ln.get("say") and ln["say"] not in docent:
            bad.append(f"{cid}: links 의 낱말 {ln['say']!r} 가 도슨트 대사에 없다")
    # 포인트마다 강조: 도슨트 턴마다 그 턴에서 강조되는 부품이 하나 이상
    for r, turn, t, _ in turns(cue):
        if r == "docent" and not any(w in t for p in parts for w in (p.get("say") or [])):
            bad.append(f"{cid}: {turn} 에서 강조되는 부품이 없다(포인트를 말할 때 부품이 강조돼야 한다)")
    return bad


def clips(entries: list[dict], cdir: pathlib.Path, cid: str, tag: str, level: str | None, want: str) -> list[dict]:
    got = [e for e in entries if any(w == f"{cid} {tag}" for w in e["where"]) and (level is None or level in e["levels"])]
    # 색인 순서는 말하는 순서가 아니다(여러 큐가 같이 쓰는 문장은 먼저 나온 자리에 한 번만 적힌다) — 큐시트의 자리로 줄 세운다
    got.sort(key=lambda e: norm(want).find(norm(e["text"])))
    if norm("".join(e["text"] for e in got)) != norm(want):
        sys.exit(f"✗ 캐시와 큐시트가 다르다 — {cid} {tag}: 캐시={[e['text'] for e in got]!r} 큐시트={want!r} (./reachy.sh bake 를 먼저)")
    for e in got:
        if not (cdir / f"{e['key']}.pcm").exists():
            sys.exit(f"✗ 캐시 파일 없음 — {e['text']!r}")
    return got


def vendor_import_map() -> str:
    man = json.loads((VENDOR / "MANIFEST.json").read_text())
    for name, meta in man["files"].items():
        h = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
        if h != meta["sha256"]:
            sys.exit(f"✗ vendor/{name} 해시가 MANIFEST 와 다르다 — 받은 원본 그대로가 아니다({h[:12]}… ≠ {meta['sha256'][:12]}…)")
    imports = {}
    for spec, fn in IMPORTS.items():
        src = (VENDOR / fn).read_text()
        if fn == "three.module.js":
            if src.count("from './three.core.js'") < 1:
                sys.exit("✗ three.module.js 의 './three.core.js' import 를 못 찾았다 — 버전이 바뀌었나")
            src = src.replace("from './three.core.js'", "from 'three/core'")
        left = re.findall(r"""(?:from|import)\s*['"](\.{1,2}/[^'"]+)['"]""", src)
        if left:
            sys.exit(f"✗ {fn} 에 data: URL 에서 못 푸는 상대 import 가 남았다: {left[:3]}")
        imports[spec] = "data:text/javascript;base64," + base64.b64encode(src.encode()).decode()
    return json.dumps({"imports": imports}).replace("</", "<\\/")


def live_module() -> str:
    """공연 모드 모듈 원문. 없으면 **경고하고** 빈 자리 — 페이지는 ?live 로 열리면 '모듈 없음' 을 화면에 띄운다(조용히 멈춘 화면 금지)"""
    name = LIVE_JS.relative_to(ROOT) if LIVE_JS.is_relative_to(ROOT) else LIVE_JS
    if LIVE_JS.exists():
        src = LIVE_JS.read_text()
        if "</script" in src.lower():
            sys.exit(f"✗ {name} 에 </script 가 있다 — 인라인하면 페이지가 깨진다")
        return src
    print(f"⚠ {name} 가 없다 — 공연 모드(?live)는 '모듈 없음' 배지만 뜬다(모듈이 생기면 다시 빌드)", file=sys.stderr)
    return "/* live_follow.js 없음 — 빌드 때 scripts/handout_live/live_follow.js 가 없었다 */"


def assemble(data: dict) -> str:
    """틀 + 형상·장면·배치 코드 + 공연 모듈 + three(import map) + 아이콘 + 데이터 → HTML 한 장"""
    icon = "data:image/png;base64," + base64.b64encode(ICON.read_bytes()).decode()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (HERE / "template.html").read_text()
    for mark, path in (("/*__LAYOUT__*/", "layout.js"), ("/*__PARTS__*/", "parts.js"), ("/*__SCENES__*/", "scenes.js")):
        html = html.replace(mark, (HERE / path).read_text())
    html = html.replace("/*__LIVE__*/", live_module())
    return html.replace("__IMPORTMAP__", vendor_import_map()).replace("__ICON__", icon).replace("__DATA__", payload)


def main() -> None:
    hud = load_hud()
    tables = load_tables()
    cues = {c["id"]: c for c in hud["cues"]}
    problems = [p for cid in CUE_IDS for p in check_table(cid, tables[cid], cues[cid])]
    if problems:
        sys.exit("✗ 부품 표 대조 실패:\n  " + "\n  ".join(problems))
    cdir = cache_dir()
    entries = json.loads((cdir / "index.json").read_text())["entries"]
    out_cues = []
    for cid in CUE_IDS:
        cue = cues[cid]
        L = cue["lv"][LEVEL_KEY]
        pcm = bytearray(int(LEAD * RATE) * 2)
        utt = []
        for role, turn, want, level in turns(cue):
            sents = []
            for e in clips(entries, cdir, cid, _tag(turn), level, want):
                raw = (cdir / f"{e['key']}.pcm").read_bytes()
                t0 = len(pcm) / 2 / RATE
                pcm += raw
                sents.append({"x": e["text"], "t0": round(t0, 3), "t1": round(len(pcm) / 2 / RATE, 3)})
                pcm += bytes(int(GAP_SENT * RATE) * 2)
            utt.append({"role": role, "turn": turn, "t0": sents[0]["t0"], "t1": sents[-1]["t1"], "s": sents})
            pcm += bytes(int(GAP_UTT * RATE) * 2)
        pcm += bytes(int(TAIL * RATE) * 2)
        dur = len(pcm) / 2 / RATE
        with tempfile.TemporaryDirectory() as td:
            wav, mp3 = pathlib.Path(td) / "a.wav", pathlib.Path(td) / "a.mp3"
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(bytes(pcm))
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-ac", "1", "-b:a", "40k", str(mp3)], check=True)
            audio = "data:audio/mpeg;base64," + base64.b64encode(mp3.read_bytes()).decode()
        table = tables[cid]
        out_cues.append({"id": cid, "no": cue["no"], "title": cue["title"], "headline": L["headline"], "items": L["items"],
                         "remember": L["remember"], "card": card_strings(L), "dur": round(dur, 3), "utt": utt, "audio": audio,
                         "view": table["view"], "parts": table["parts"], "links": table.get("links") or []})
        print(f"  {cid}: {dur:.1f}s · 문장 {sum(len(u['s']) for u in utt)}개 · 부품 {len(table['parts'])}개")

    OUT.write_text(assemble({"level": LEVEL_NAME, "cues": out_cues}))
    print(f"wrote {OUT.relative_to(ROOT)} — {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
