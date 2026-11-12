"""구운 고정 대사 검수 — 로컬 STT 로 다시 받아써서 대본과 대조하고, 다른 것부터 듣는 페이지를 만든다.

계획 `docs/superpowers/plans/2026-11-12-elevenlabs-tts.md`(A3 검수). ElevenLabs 는 다시 구울 때마다 테이크가
달라지므로 굽기 뒤마다 다시 돌린다. 결과는 **저장소 밖**(`$TTS_ASSETS/review/<캐시 폴더 이름>/`)에 둔다.

STT 대조는 사람 귀를 대신하지 않는다 — **어디부터 들을지**를 정한다. 숫자·약어는 STT 표기 차이로 낮게 나올 수
있다(대조 전에 띄어쓰기·문장부호·쉼표를 지운다). 모델은 STT 서버와 같은 것(`stt_server.MODEL`)을 쓴다.

사용:
    .venv/bin/python scripts/tts_review.py [--cache-dir …/cache-elevenlabs] [--limit N]
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import pathlib
import re
import sys
import time
import wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = "mlx-community/whisper-large-v3-turbo"   # stt_server.MODEL 과 같다
RATE = 24000
_STRIP = re.compile(r"[\s.,!?…·'\"“”‘’~\-()\[\]:;]")


def norm(s: str) -> str:
    return _STRIP.sub("", s).lower()


def similarity(script: str, heard: str) -> float:
    return difflib.SequenceMatcher(None, norm(script), norm(heard)).ratio()


def main() -> int:
    assets = pathlib.Path(os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")).expanduser()
    ap = argparse.ArgumentParser(description="구운 고정 대사를 STT 로 대조하고 검수 페이지를 만든다")
    ap.add_argument("--cache-dir", default=str(assets / "cache-elevenlabs"))
    ap.add_argument("--limit", type=int, default=0, help="앞 N문장만(시험용)")
    args = ap.parse_args()

    import mlx_whisper
    import numpy as np
    from scipy.signal import resample_poly

    cdir = pathlib.Path(args.cache_dir).expanduser()
    idx = json.loads((cdir / "index.json").read_text(encoding="utf-8"))
    entries = [e for e in idx["entries"] if (cdir / f"{e['key']}.pcm").is_file()]
    if args.limit:
        entries = entries[: args.limit]
    out = assets / "review" / cdir.name
    (out / "wav").mkdir(parents=True, exist_ok=True)
    rows = []
    t0 = time.time()
    for i, e in enumerate(entries, 1):
        pcm = (cdir / f"{e['key']}.pcm").read_bytes()
        wav = out / "wav" / f"{e['key'][:16]}.wav"
        if not wav.is_file():
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm)
        audio = resample_poly(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0, 2, 3)
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language="ko",
                                   condition_on_previous_text=False, temperature=0.0)
        heard = (r.get("text") or "").strip()
        rows.append({"key": e["key"], "file": f"wav/{wav.name}", "text": e["text"], "heard": heard,
                     "sim": round(similarity(e["text"], heard), 3), "role": e.get("role"),
                     "levels": e.get("levels") or [], "where": e.get("where") or [], "sec": round(len(pcm) / 2 / RATE, 2)})
        if i % 50 == 0 or i == len(entries):
            print(f"   [{i}/{len(entries)}] {time.time() - t0:.0f}초", flush=True)
    rows.sort(key=lambda r: r["sim"])
    data = {"cache": str(cdir), "engine": idx.get("engine"), "made": time.strftime("%Y-%m-%d %H:%M"), "rows": rows}
    (out / "review.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    html = (ROOT / "scripts" / "tts_review.html").read_text(encoding="utf-8")
    (out / "index.html").write_text(
        html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")
    low = [r for r in rows if r["sim"] < 0.9]
    print(f"끝 — {len(rows)}문장, 대조 90% 미만 {len(low)}개. 듣기: {out / 'index.html'}")
    for r in low[:15]:
        print(f"   {r['sim']:.2f} {r['where'][0]} | 대본 {r['text'][:40]} | 들림 {r['heard'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
