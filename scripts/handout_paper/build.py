"""종이 무대(스톱모션) 교육자료 만들기 — 19큐 전체, 일반 수준.

    .venv/bin/python -m scripts.handout_paper.build      # → docs/design/paper-stage.html

- 글(제목·카드·대사)은 `docs/design/handout-hud.html` 에 이미 검증돼 들어간 데이터를 그대로 읽는다(새 사실 없음).
- 음성은 **새로 합성하지 않는다.** 고정 대사 TTS 캐시(`~/.local/share/reachy-mini-tts/cache`, `./reachy.sh bake` 가 굽는 것)의
  문장별 PCM(24 kHz s16 mono)을 큐마다 한 줄로 이어 붙여 mp3 로 넣는다. 문장 시작·끝 시각을 같이 적어 그림이 말에 맞춰 움직인다.
- 캐시에 문장이 없거나 큐시트와 글이 다르면 **멈춘다**(조용히 빠진 채 만들지 않는다).
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

ROOT = pathlib.Path(__file__).resolve().parents[2]
HUD = ROOT / "docs" / "design" / "handout-hud.html"
TPL = pathlib.Path(__file__).with_name("template.html")
ICON = ROOT / "scripts" / "handout_hud" / "reachy-mini-icon.png"
SCENES = pathlib.Path(__file__).with_name("scenes.js")
OUT = ROOT / "docs" / "design" / "paper-stage.html"
LEVEL_KEY, LEVEL_NAME = "l3", "일반"
RATE = 24000
GAP_SENT, GAP_UTT, LEAD, TAIL = 0.16, 0.5, 0.9, 1.6   # 초


def cache_dir() -> pathlib.Path:
    env = os.environ.get("TTS_CACHE_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path(os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")).expanduser() / "cache"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def main() -> None:
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', HUD.read_text(), re.S).group(1))
    cdir = cache_dir()
    entries = json.loads((cdir / "index.json").read_text())["entries"]

    def clips(cid: str, tag: str, level: str | None, want: str) -> list[dict]:
        got = [e for e in entries if any(w == f"{cid} {tag}" for w in e["where"]) and (level is None or level in e["levels"])]
        # 색인 순서는 말하는 순서가 아니다(여러 큐가 같이 쓰는 문장은 먼저 나온 자리에 한 번만 적힌다) — 큐시트의 자리로 줄 세운다
        got.sort(key=lambda e: norm(want).find(norm(e["text"])))
        if norm("".join(e["text"] for e in got)) != norm(want):
            sys.exit(f"✗ 캐시와 큐시트가 다르다 — {cid} {tag}: 캐시={[e['text'] for e in got]!r} 큐시트={want!r} (./reachy.sh bake 를 먼저)")
        for e in got:
            if not (cdir / f"{e['key']}.pcm").exists():
                sys.exit(f"✗ 캐시 파일 없음 — {e['text']!r}")
        return got

    out_cues = []
    for cue in data["cues"]:
        cid = cue["id"]
        L = cue["lv"][LEVEL_KEY]
        seq = [("mc", "open", clips(cid, "오프닝", None, cue["open"]))]
        for i in range(cue["n"]):
            if L["ask"][i]:
                seq.append(("mc", f"ask{i}", clips(cid, f"{i}턴 질문", None, L["ask"][i])))
            seq.append(("docent", f"docent{i}", clips(cid, f"{i}턴 {LEVEL_NAME}", LEVEL_NAME, L["ans"][i])))
        seq.append(("mc", "after", clips(cid, "받아치기", None, cue["after"])))

        pcm = bytearray(int(LEAD * RATE) * 2)
        utt = []
        for role, turn, cs in seq:
            sents = []
            for e in cs:
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
        out_cues.append({"id": cid, "no": cue["no"], "title": cue["title"], "headline": L["headline"], "items": L["items"],
                         "remember": L["remember"], "visual": L["visual"], "dur": round(dur, 3), "utt": utt, "audio": audio})
        print(f"  {cid}: {dur:.1f}s · 문장 {sum(len(u['s']) for u in utt)}개")

    icon = "data:image/png;base64," + base64.b64encode(ICON.read_bytes()).decode()
    payload = json.dumps({"level": LEVEL_NAME, "cues": out_cues}, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TPL.read_text().replace("/*__SCENES__*/", SCENES.read_text()).replace("__ICON__", icon).replace("__DATA__", payload))
    print(f"wrote {OUT.relative_to(ROOT)} — {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
