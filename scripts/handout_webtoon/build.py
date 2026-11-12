"""웹툰 칸 연출 교육자료 만들기 — 초등·중고등, 01·02 시안.

    TTS_CACHE_DIR=~/.local/share/reachy-mini-tts/cache-elevenlabs .venv/bin/python -m scripts.handout_webtoon.build
    # → docs/design/webtoon-stage.html (외부 리소스 0, 한 파일)

- 글(제목·카드·대사)은 `docs/design/handout-hud.html` 에 이미 검증돼 들어간 데이터를 그대로 읽는다(새 사실 없음).
- 음성은 **새로 합성하지 않는다.** 고정 대사 TTS 캐시의 문장별 PCM(24 kHz s16 mono)을 이어 붙여 mp3 로 넣는다.
- 칸 구성은 `storyboard.yaml`(콘티)이 정한다. 칸 사이에 넣는 **쉼의 길이가 곧 여백 높이**다(화면이 쉼에서 여백을 푼다) —
  그래서 쉼을 칸 경계 종류(같은 발화 안 / 질문→답 / 답→다음 질문 / 침묵 칸)마다 다르게 넣는다(`PAUSE`).
- 캐시에 문장이 없거나, 큐시트와 글이 다르거나, 콘티가 문장을 빠뜨리거나 남기면 **멈춘다**(조용히 빠진 채 만들지 않는다).
"""
from __future__ import annotations

import base64
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
HUD = ROOT / "docs" / "design" / "handout-hud.html"
HERE = pathlib.Path(__file__).resolve().parent
TPL, SCENES, BOARD = HERE / "template.html", HERE / "scenes.js", HERE / "storyboard.yaml"
ICON = ROOT / "scripts" / "handout_hud" / "reachy-mini-icon.png"
OUT = ROOT / "docs" / "design" / "webtoon-stage.html"
# 공연 모드(`?live`): 로봇 2대가 말하고 화면은 감독의 발화 라벨을 따라간다. 조율자가 만드는 공용 모듈을 그대로 인라인한다
# (세 교육자료가 같은 접속·배지 모양을 쓴다). 없으면 미리보기만 되는 파일을 만들고 경고한다.
LIVE_JS = ROOT / "scripts" / "handout_live" / "live_follow.js"
LEVELS = (("l1", "초등"), ("l2", "중고등"))
RATE = 24000
GAP_SENT, LEAD, TAIL = 0.16, 0.9, 1.6   # 초 — 칸 안 문장 사이 · 시작 전 · 끝난 뒤
# 칸 경계의 쉼(초). 화면은 이 쉼 안에 스크롤 이동이 정확히 끝나도록 여백 높이를 푼다 — 턴이 바뀌면 넓은 여백,
# '기억해 두기' 앞 침묵 칸 앞이 가장 넓다. 이동 하나는 최소 0.6초쯤 걸린다(손 출발·정지 0.3초 + 칸 반쪽 두 개를 지나는 시간).
# **같은 발화 안의 칸 나눔(split)은 문장 사이 쉼(GAP_SENT)과 같다** — 공연 모드(LiveFollow)는 발화마다 앵커를 잡고 그 안은
# 캐시 PCM 시각 그대로 흐른다고 본다. 여기에 0.7초를 넣었더니 로봇보다 칸 하나에 0.5초씩 늦었다. 그래서 여백은 최솟값에
# 붙고 이동은 앞 문장 끝을 0.4초쯤 앞당겨 출발한다(엔진의 early) — 같은 사람이 이어 말하는 칸 사이는 좁은 여백이 맞다.
# 발화 **사이**의 쉼은 종이 무대(GAP_UTT 0.5)와 다르게 경계 종류마다 다르다(여백 = 쉼). 공연에서는 실제 쉼을 감독 이벤트가 주므로
# 이 값은 미리보기와 여백 높이에만 쓰인다.
PAUSE = {"split": GAP_SENT, "answer": 0.95, "turn": 1.25, "into_silent": 1.5, "silent": 0.8, "out_silent": 0.9}
KINDS = {"wide", "band", "normal", "slant", "silent", "free"}


def fail(msg: str) -> None:
    raise SystemExit(f"✗ {msg}")


def cache_dir() -> pathlib.Path:
    env = os.environ.get("TTS_CACHE_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    # 결정된 공연 목소리는 ElevenLabs 다(2026-11-12). 옛 Qwen 캐시(`cache`)는 되돌릴 자리로 남겨 두고 기본으로 읽지 않는다.
    return pathlib.Path(os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")).expanduser() / "cache-elevenlabs"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def load_hud(path: pathlib.Path = HUD) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', path.read_text(), re.S).group(1))


def load_index(cdir: pathlib.Path) -> list[dict]:
    idx = json.loads((cdir / "index.json").read_text())
    if idx.get("engine") != "elevenlabs":
        # 시안을 다른 엔진 캐시로 만드는 것은 허용한다 — 다만 공연 목소리와 다르다는 걸 조용히 넘기지 않는다
        print(f"⚠ 캐시 엔진이 elevenlabs 가 아니다({idx.get('engine')!r}) — {cdir}", file=sys.stderr)
    return idx["entries"]


def clips(entries: list[dict], cdir: pathlib.Path, cid: str, tag: str, level: str | None, want: str) -> list[dict]:
    got = [e for e in entries if any(w == f"{cid} {tag}" for w in e["where"]) and (level is None or level in e["levels"])]
    # 색인 순서는 말하는 순서가 아니다(여러 큐가 같이 쓰는 문장은 먼저 나온 자리에 한 번만 적힌다, docs/lessons.md) —
    # 큐시트 글 안의 자리로 줄 세우고, 이어 붙인 글이 큐시트와 같은지 대조한다
    got.sort(key=lambda e: norm(want).find(norm(e["text"])))
    if norm("".join(e["text"] for e in got)) != norm(want):
        fail(f"캐시와 큐시트가 다르다 — {cid} {tag}: 캐시={[e['text'] for e in got]!r} 큐시트={want!r} (./reachy.sh bake 를 먼저)")
    for e in got:
        if not (cdir / f"{e['key']}.pcm").exists():
            fail(f"캐시 파일 없음 — {e['text']!r}")
    return got


def utterances(entries: list[dict], cdir: pathlib.Path, cue: dict, lkey: str, lname: str) -> list[tuple[str, str, list[dict]]]:
    """큐 하나의 발화 순서(종이 무대 빌더와 같은 차례): 오프닝 → (질문 → 도슨트)×n → 받아치기"""
    cid, L = cue["id"], cue["lv"][lkey]
    seq = [("mc", "open", clips(entries, cdir, cid, "오프닝", None, cue["open"]))]
    for i in range(cue["n"]):
        if L["ask"][i]:
            seq.append(("mc", f"ask{i}", clips(entries, cdir, cid, f"{i}턴 질문", None, L["ask"][i])))
        seq.append(("docent", f"docent{i}", clips(entries, cdir, cid, f"{i}턴 {lname}", lname, L["ans"][i])))
    seq.append(("mc", "after", clips(entries, cdir, cid, "받아치기", None, cue["after"])))
    return seq


def plan_panels(board: list[dict], seq: list[tuple[str, str, list[dict]]], where: str) -> list[dict]:
    """콘티를 발화 순서에 맞춰 펼친다 — 모든 문장이 순서대로 정확히 한 번 어느 칸에 들어가야 한다"""
    out, ui, si = [], 0, 0
    for k, b in enumerate(board):
        kind = b.get("kind")
        if kind not in KINDS:
            fail(f"{where} 칸 {k}: 모르는 kind {kind!r}")
        if kind == "silent":
            if "u" in b:
                fail(f"{where} 칸 {k}: 침묵 칸에는 말(u)이 없다")
            out.append({**b, "role": None, "clips": []})
            continue
        if ui >= len(seq):
            fail(f"{where} 칸 {k}: 발화가 이미 다 쓰였다(u={b.get('u')!r})")
        role, turn, cs = seq[ui]
        if b.get("u") != turn:
            fail(f"{where} 칸 {k}: 차례가 아니다 — 콘티 u={b.get('u')!r}, 지금 발화={turn!r}(문장 {si}부터: {cs[si]['text']!r})")
        n = int(b.get("n", 0))
        if n < 1 or si + n > len(cs):
            fail(f"{where} 칸 {k}: {turn} 에 남은 문장은 {len(cs) - si}개인데 n={n} — 캐시 문장: {[e['text'] for e in cs]!r}")
        out.append({**b, "role": role, "a": si, "clips": cs[si:si + n]})
        si += n
        if si == len(cs):
            ui, si = ui + 1, 0
    if ui < len(seq):
        left = seq[ui]
        fail(f"{where}: 콘티가 {left[1]} 의 문장 {si}부터를 덮지 않는다 — {[e['text'] for e in left[2][si:]]!r}")
    # 칸 깨기는 '기울어진 칸 → 침묵 칸' 으로만 건넌다(엔진의 합집합 clip 이 그 두 칸과 사이 여백으로 짜여 있다)
    brks = [i for i, p in enumerate(out) if p.get("brk")]
    if len(brks) != 1:
        fail(f"{where}: 칸 깨기는 큐마다 정확히 한 번이다(지금 {len(brks)}번)")
    i = brks[0]
    if i + 1 >= len(out) or out[i + 1]["kind"] != "silent":
        fail(f"{where}: 칸 깨기 다음 칸은 침묵 칸이어야 한다")
    if out[-1]["kind"] != "free":
        fail(f"{where}: 마지막 칸은 테두리 없는 칸(free)이다")
    return out


def pause(prev: dict, nxt: dict) -> float:
    """칸 경계의 쉼 — 여기서 정한 길이가 화면에서 여백 높이가 된다"""
    if nxt["kind"] == "silent":
        return PAUSE["into_silent"]
    if prev["kind"] == "silent":
        return PAUSE["out_silent"]
    if prev.get("u") == nxt.get("u"):
        return PAUSE["split"]
    if prev["role"] == "mc" and nxt["role"] == "docent":
        return PAUSE["answer"]
    return PAUSE["turn"]


def assemble(panels: list[dict], read_pcm) -> tuple[bytes, list[dict], list[dict]]:
    """문장 PCM 과 쉼을 이어 붙이고, 문장·발화·칸의 시작·끝 시각을 적는다(초, 소수 셋째 자리)"""
    pcm = bytearray(int(LEAD * RATE) * 2)
    now = lambda: len(pcm) / 2 / RATE  # noqa: E731
    sil = lambda s: bytes(int(round(s * RATE)) * 2)  # noqa: E731
    utt: dict[str, dict] = {}
    order: list[str] = []
    out = []
    prev = None
    for p in panels:
        if prev is not None:
            pcm += sil(pause(prev, p))
        if p["kind"] == "silent":
            t0 = now()
            pcm += sil(PAUSE["silent"])
            out.append({"kind": "silent", "art": p["art"], "t0": round(t0, 3), "t1": round(now(), 3)})
            prev = p
            continue
        turn = p["u"]
        if turn not in utt:
            utt[turn] = {"role": p["role"], "turn": turn, "s": []}
            order.append(turn)
        for j, e in enumerate(p["clips"]):
            if j:
                pcm += sil(GAP_SENT)
            t0 = now()
            pcm += read_pcm(e)
            utt[turn]["s"].append({"x": e["text"], "t0": round(t0, 3), "t1": round(now(), 3)})
        ss = utt[turn]["s"]
        q = {k: p[k] for k in ("kind", "art", "brk", "v", "item", "card") if k in p}
        q.update({"u": turn, "role": p["role"], "a": p["a"], "b": len(ss), "t0": ss[p["a"]]["t0"], "t1": ss[-1]["t1"]})
        out.append(q)
        prev = p
    pcm += sil(TAIL)
    utts = []
    for turn in order:
        u = utt[turn]
        utts.append({**u, "t0": u["s"][0]["t0"], "t1": u["s"][-1]["t1"]})
    return bytes(pcm), utts, out


def to_mp3(pcm: bytes) -> str:
    with tempfile.TemporaryDirectory() as td:
        wav, mp3 = pathlib.Path(td) / "a.wav", pathlib.Path(td) / "a.mp3"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-ac", "1", "-b:a", "40k", str(mp3)], check=True)
        return "data:audio/mpeg;base64," + base64.b64encode(mp3.read_bytes()).decode()


def build_cue(entries, cdir, cue, lkey, lname, board, encode=to_mp3) -> dict:
    cid, L = cue["id"], cue["lv"][lkey]
    seq = utterances(entries, cdir, cue, lkey, lname)
    panels = plan_panels(board, seq, f"{cid} {lname}")
    pcm, utts, pans = assemble(panels, lambda e: (cdir / f"{e['key']}.pcm").read_bytes())
    return {"id": cid, "no": cue["no"], "title": cue["title"], "headline": L["headline"], "items": L["items"],
            "remember": L["remember"], "visual": L["visual"], "dur": round(len(pcm) / 2 / RATE, 3),
            "utt": utts, "panels": pans, "audio": encode(pcm)}


def main() -> None:
    data = load_hud()
    board = yaml.safe_load(BOARD.read_text())
    cdir = cache_dir()
    entries = load_index(cdir)
    cues = [c for c in data["cues"] if c["id"] in board]          # 시안 범위 = 콘티가 있는 큐(지금 01·02)
    if [c["id"] for c in cues] != list(board):
        fail(f"콘티의 큐가 큐시트에 없다: {sorted(set(board) - {c['id'] for c in cues})}")
    levels = []
    for lkey, lname in LEVELS:
        out = []
        for cue in cues:
            if lname not in board[cue["id"]]:
                fail(f"{cue['id']}: {lname} 콘티가 없다")
            c = build_cue(entries, cdir, cue, lkey, lname, board[cue["id"]][lname])
            print(f"  {lname} {c['id']}: {c['dur']:.1f}s · 칸 {len(c['panels'])}개 · 문장 {sum(len(u['s']) for u in c['utt'])}개")
            out.append(c)
        levels.append({"key": lkey, "name": lname, "cues": out})
    if LIVE_JS.exists():
        live = LIVE_JS.read_text().replace("</script", "<\\/script")
    else:
        live = "/* 공연 모드 모듈 없음 — scripts/handout_live/live_follow.js 가 생기면 다시 빌드한다 */"
        print(f"⚠ 공연 모드 모듈이 없다({LIVE_JS.relative_to(ROOT)}) — ?live 는 '모듈 없음' 으로만 뜬다", file=sys.stderr)
    icon = "data:image/png;base64," + base64.b64encode(ICON.read_bytes()).decode()
    payload = json.dumps({"levels": levels, "pause": PAUSE, "gapSent": GAP_SENT, "cache": cdir.name},
                         ensure_ascii=False).replace("</", "<\\/")
    page = TPL.read_text().replace("/*__LIVE__*/", live).replace("/*__SCENES__*/", SCENES.read_text())
    OUT.write_text(page.replace("__ICON__", icon).replace("__DATA__", payload))
    print(f"wrote {OUT.relative_to(ROOT)} — {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
