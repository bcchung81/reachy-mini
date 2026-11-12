"""구운 고정 대사 검수 — 로컬 STT 로 다시 받아써서 대본과 **발음 기준으로** 대조하고, 소리 품질을 재고,
의심스러운 것부터 듣는 페이지를 만든다.

계획 `docs/superpowers/plans/2026-11-12-elevenlabs-tts.md`(A3 검수). ElevenLabs 는 다시 구울 때마다 테이크가
달라지므로 굽기 뒤마다 다시 돌린다. 결과는 **저장소 밖**(`$TTS_ASSETS/review/<캐시 폴더 이름>/`)에 둔다.

세 겹으로 거른다(2026-11-12 — 글자 대조만으로는 헛경보가 많았다: "초장파는/초장판은"은 같은 소리다):
1. **발음 대조**(`phonetic`): 숫자·단위를 읽는 소리로 펴고(121.5MHz → 백이십일점오메가헤르츠), 연음·ㅎ 거센소리·받침
   대표음·비음화·된소리를 적용한 자모열끼리 비교한다. STT 표기 차이와 맞춤법만 다른 같은 소리를 지운다.
2. **대본을 힌트로 다시 받아쓰기**: 발음 대조가 낮은 문장만, 대본을 `initial_prompt` 로 주고 다시 받아쓴다. 힌트를
   줬는데도 다르게 들리면 소리 쪽 문제일 가능성이 높다(힌트로 맞춰지면 STT 가 헷갈린 쪽).
3. **소리 품질**: 클리핑, 역할 안에서 튀는 음량, 문장 안의 긴 멈춤.

**사람 귀를 대신하지 않는다** — 억양·자연스러움·로봇 스피커에서의 소리는 못 잰다. 어디부터 들을지와 확실한 오류를 가린다.
모델은 STT 서버와 같은 것(`stt_server.MODEL`)을 쓴다.

사용:
    .venv/bin/python scripts/tts_review.py [--cache-dir …/cache-elevenlabs] [--limit N]
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
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
LOUD_DEV_DB = 4.0       # 역할 중앙값에서 이만큼 벗어나면 음량이 튄다
PAUSE_S = 1.0           # 문장 안의 멈춤이 이보다 길면 표시


def norm(s: str) -> str:
    return _STRIP.sub("", s).lower()


def similarity(script: str, heard: str) -> float:
    """글자 대조(예전 방식) — 페이지에 참고로 남긴다."""
    return difflib.SequenceMatcher(None, norm(script), norm(heard)).ratio()


def take_id(pcm: bytes) -> str:
    """테이크 표지 — 소리가 바뀌면 바뀐다. **캐시 키는 다시 구워도 그대로라** 키만으로 이름을 지으면
    다시 구운 뒤에도 옛 wav 를 틀고, 페이지의 '확인함' 표시도 새 테이크에 그대로 붙는다."""
    return hashlib.sha1(pcm).hexdigest()[:8]


# ── 숫자·단위를 읽는 소리로 ────────────────────────────────────────
# STT 가 붙이는 단위 표기 → 대본이 쓰는 말. 긴 것부터(Hz 가 MHz 를 먼저 먹지 않게).
_UNITS = [("km²", "제곱킬로미터"), ("GHz", "기가헤르츠"), ("MHz", "메가헤르츠"), ("kHz", "킬로헤르츠"),
          ("KHz", "킬로헤르츠"), ("Hz", "헤르츠"), ("Gbps", "기가비트"), ("Mbps", "메가비트"),
          ("km", "킬로미터"), ("mm", "밀리미터"), ("cm", "센티미터"), ("ms", "밀리초"), ("mS", "밀리초"),
          ("%", "퍼센트"), ("DOCENT", "도슨트"), ("Docent", "도슨트"), ("docent", "도슨트")]
_DIG = "영일이삼사오육칠팔구"


def _read_small(n: int) -> str:
    """0~9999 를 한자어 수사로. 십·백·천 앞의 '일'은 읽지 않는다(일천 → 천)."""
    out = ""
    for unit, base in (("천", 1000), ("백", 100), ("십", 10)):
        d = n // base
        n %= base
        if d:
            out += ("" if d == 1 else _DIG[d]) + unit
    return out + (_DIG[n] if n else "")


def read_number(digits: str) -> str:
    """'3,500' → 삼천오백, '121.5' → 백이십일점오, '100' → 백. 만·억·조 단위로 끊는다."""
    whole, _, frac = digits.replace(",", "").partition(".")
    n = int(whole or "0")
    if n == 0:
        out = "영"
    else:
        out, groups = "", []
        while n:
            groups.append(n % 10000)
            n //= 10000
        for i in range(len(groups) - 1, -1, -1):
            g = groups[i]
            if g:
                big = ["", "만", "억", "조"][i]
                out += ("" if (g == 1 and big == "만" and not out) else _read_small(g)) + big
    if frac:
        out += "점" + "".join(_DIG[int(c)] for c in frac)
    return out


def spoken(s: str) -> str:
    """대본이든 STT 든 **읽는 소리의 글**로 — 단위를 말로, 숫자를 수사로."""
    for a, b in _UNITS:
        s = s.replace(a, b)
    s = re.sub(r"(?<=\d)m\b", "미터", s)
    return re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: read_number(m.group(0)), s)


# ── 한국어 발음 규칙(대조용 간이판) ────────────────────────────────
_L = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_V = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_T = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ",
      "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
_SPLIT = {"ㄳ": ("ㄱ", "ㅅ"), "ㄵ": ("ㄴ", "ㅈ"), "ㄺ": ("ㄹ", "ㄱ"), "ㄻ": ("ㄹ", "ㅁ"), "ㄼ": ("ㄹ", "ㅂ"),
          "ㄽ": ("ㄹ", "ㅅ"), "ㄾ": ("ㄹ", "ㅌ"), "ㄿ": ("ㄹ", "ㅍ"), "ㅄ": ("ㅂ", "ㅅ")}
_REP = {"ㄲ": "ㄱ", "ㅋ": "ㄱ", "ㄳ": "ㄱ", "ㄺ": "ㄱ", "ㅅ": "ㄷ", "ㅆ": "ㄷ", "ㅈ": "ㄷ", "ㅊ": "ㄷ",
        "ㅌ": "ㄷ", "ㅎ": "ㄷ", "ㅍ": "ㅂ", "ㅄ": "ㅂ", "ㄿ": "ㅂ", "ㄵ": "ㄴ", "ㄶ": "ㄴ", "ㄼ": "ㄹ",
        "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㅀ": "ㄹ", "ㄻ": "ㅁ"}
_ASP = {"ㄱ": "ㅋ", "ㄷ": "ㅌ", "ㅂ": "ㅍ", "ㅈ": "ㅊ"}
_NASAL = {"ㄱ": "ㅇ", "ㄷ": "ㄴ", "ㅂ": "ㅁ"}
_PLAIN = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
_VMERGE = {"ㅐ": "ㅔ", "ㅒ": "ㅖ", "ㅙ": "ㅞ", "ㅚ": "ㅞ", "ㅢ": "ㅔ", "ㅖ": "ㅔ"}


def phonetic(s: str) -> str:
    """글 → 소리 자모열. 맞춤법은 달라도 소리가 같으면 같은 열이 되게(판은/파는, 닉호/니코, 맡/맞)."""
    syl: list[list[str]] = []
    for ch in norm(spoken(s)):
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            syl.append([_L[c // 588], _V[(c % 588) // 28], _T[c % 28]])
        else:
            syl.append([ch, "", ""])       # 영문·기타는 그대로(VLF 등)
    for i in range(len(syl) - 1):
        a, b = syl[i], syl[i + 1]
        if not a[1] or not b[1]:
            continue
        t, o = a[2], b[0]
        if t in ("ㅎ", "ㄶ", "ㅀ") and o in ("ㅇ", "ㄱ", "ㄷ", "ㅈ"):      # ㅎ 탈락·거센소리(놓고→노코)
            if o != "ㅇ":
                b[0] = _ASP[o]
            a[2] = {"ㅎ": "", "ㄶ": "ㄴ", "ㅀ": "ㄹ"}[t]
        elif t and o == "ㅎ" and _REP.get(t, t) in _ASP:                 # 거센소리(닉호→니코)
            b[0] = _ASP[_REP.get(t, t)]
            a[2] = ""
        elif t and t != "ㅇ" and o == "ㅇ":                               # 연음(판은→파는)
            if t in _SPLIT:
                a[2], b[0] = _SPLIT[t]
            else:
                a[2], b[0] = "", t
        t = a[2]
        if t:
            a[2] = _REP.get(t, t)
        if a[2] in _NASAL and b[0] in ("ㄴ", "ㅁ"):                       # 비음화(습니다→슴니다)
            a[2] = _NASAL[a[2]]
    if syl and syl[-1][2]:
        syl[-1][2] = _REP.get(syl[-1][2], syl[-1][2])
    out = []
    for o, v, t in syl:
        out.append(_PLAIN.get(o, o) + _VMERGE.get(v, v) + t)
    return "".join(out)


def psim(script: str, heard: str) -> float:
    """발음 대조 — 소리 자모열끼리의 일치도."""
    return difflib.SequenceMatcher(None, phonetic(script), phonetic(heard)).ratio()


# ── 소리 품질 ───────────────────────────────────────────────────────
def audio_qc(pcm: bytes) -> dict:
    """클리핑 수, 말하는 구간의 음량(dBFS), 문장 안의 가장 긴 멈춤(초)."""
    import numpy as np
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    clip = int((np.abs(a) >= 32700).sum())
    hop = int(RATE * 0.02)
    n = len(a) // hop
    if n == 0:
        return {"clip": clip, "db": -99.0, "pause": 0.0}
    fr = a[: n * hop].reshape(n, hop)
    rms = np.sqrt((fr ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms / 32768.0)
    voiced = db > -45
    idx = np.flatnonzero(voiced)
    if len(idx) == 0:
        return {"clip": clip, "db": -99.0, "pause": 0.0}
    act = float(20 * math.log10(float(np.sqrt((fr[voiced] ** 2).mean())) / 32768.0 + 1e-12))
    longest = run = 0
    for v in voiced[idx[0]: idx[-1] + 1]:
        run = 0 if v else run + 1
        longest = max(longest, run)
    return {"clip": clip, "db": round(act, 1), "pause": round(longest * 0.02, 2)}


def same_sound(a: str, b: str) -> bool:
    return phonetic(a) == phonetic(b)


def verdict(row: dict) -> str:
    """ok(소리가 대본과 같다) · stt(대본을 힌트로 주면 같아진다 — STT 가 헷갈렸을 가능성) · suspect(힌트로도 다르다).

    ~~문장 일치도 0.95 이상이면 통과~~ — 긴 문장에서 한 낱말이 틀린 것(도슨트→노슨트)이 0.98 로 통과했다.
    **소리 자모열이 한 글자라도 다르면** 힌트 받아쓰기로 넘긴다(2026-11-12).
    """
    if same_sound(row["text"], row["heard"]):
        return "ok"
    if row.get("biased") is not None and same_sound(row["text"], row["biased"]):
        return "stt"
    return "suspect"


def diffs(script: str, heard: str) -> list[list[str]]:
    """대본과 들린 글이 **소리로** 다른 곳 — [대본 쪽, 들린 쪽]. 맞춤법만 다른 같은 소리(판은/파는)는 뺀다."""
    a, b = norm(spoken(script)), norm(spoken(heard))
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        ca, cb = a[max(0, i1 - 1): i2 + 1], b[max(0, j1 - 1): j2 + 1]     # 앞뒤 한 글자 — 연음은 경계를 넘는다
        if phonetic(ca) != phonetic(cb):
            out.append([a[i1:i2], b[j1:j2]])
    return out


def main() -> int:
    assets = pathlib.Path(os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")).expanduser()
    ap = argparse.ArgumentParser(description="구운 고정 대사를 STT 로 대조하고 검수 페이지를 만든다")
    ap.add_argument("--cache-dir", default=str(assets / "cache-elevenlabs"))
    ap.add_argument("--limit", type=int, default=0, help="앞 N문장만(시험용)")
    args = ap.parse_args()

    import mlx_whisper
    import numpy as np
    from scipy.signal import resample_poly

    def transcribe(pcm: bytes, prompt: str | None = None) -> str:
        audio = resample_poly(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0, 2, 3)
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language="ko", initial_prompt=prompt,
                                   condition_on_previous_text=False, temperature=0.0)
        return (r.get("text") or "").strip()

    cdir = pathlib.Path(args.cache_dir).expanduser()
    idx = json.loads((cdir / "index.json").read_text(encoding="utf-8"))
    entries = [e for e in idx["entries"] if (cdir / f"{e['key']}.pcm").is_file()]
    if args.limit:
        entries = entries[: args.limit]
    out = assets / "review" / cdir.name
    (out / "wav").mkdir(parents=True, exist_ok=True)
    # 바뀌지 않은 테이크는 지난 받아쓰기를 그대로 쓴다 — 몇 문장만 다시 구운 뒤의 검수가 몇 초면 끝난다.
    before: dict = {}
    try:
        for r in json.loads((out / "review.json").read_text(encoding="utf-8")).get("rows", []):
            before[(r["key"], r.get("take"))] = r
    except (OSError, ValueError):
        pass
    rows = []
    fresh = 0
    t0 = time.time()
    for i, e in enumerate(entries, 1):
        pcm = (cdir / f"{e['key']}.pcm").read_bytes()
        take = take_id(pcm)
        wav = out / "wav" / f"{e['key'][:12]}-{take}.wav"
        if not wav.is_file():
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm)
        old = before.get((e["key"], take)) or {}
        heard = old.get("heard")
        if heard is None:
            heard = transcribe(pcm)
            fresh += 1
        row = {"key": e["key"], "take": take, "file": f"wav/{wav.name}", "text": e["text"], "heard": heard,
               "sim": round(similarity(e["text"], heard), 3), "psim": round(psim(e["text"], heard), 3),
               "biased": old.get("biased"), "role": e.get("role"), "levels": e.get("levels") or [],
               "where": e.get("where") or [], "sec": round(len(pcm) / 2 / RATE, 2), **audio_qc(pcm)}
        if not same_sound(e["text"], heard) and row["biased"] is None:
            row["biased"] = transcribe(pcm, prompt=e["text"])     # 대본을 힌트로 — 그래도 다르면 소리 쪽
        row["diffs"] = diffs(e["text"], heard)
        rows.append(row)
        if i % 50 == 0 or i == len(entries):
            print(f"   [{i}/{len(entries)}] {time.time() - t0:.0f}초", flush=True)

    # 음량은 역할 안에서 견준다(사회자·도슨트 목소리가 원래 다르다).
    for role in {r["role"] for r in rows}:
        dbs = sorted(r["db"] for r in rows if r["role"] == role and r["db"] > -90)
        med = dbs[len(dbs) // 2] if dbs else 0.0
        for r in rows:
            if r["role"] == role:
                r["loud_dev"] = round(r["db"] - med, 1)
    for r in rows:
        r["verdict"] = verdict(r)
        r["flags"] = ([f"클리핑 {r['clip']}"] if r["clip"] else []) + \
                     ([f"음량 {r['loud_dev']:+.1f}dB"] if abs(r["loud_dev"]) > LOUD_DEV_DB else []) + \
                     ([f"멈춤 {r['pause']:.1f}초"] if r["pause"] > PAUSE_S else [])
    order = {"suspect": 0, "stt": 1, "ok": 2}
    rows.sort(key=lambda r: (order[r["verdict"]] if not r["flags"] or r["verdict"] != "ok" else 0.5, r["psim"]))
    keep = {r["file"].split("/", 1)[1] for r in rows}
    for p in (out / "wav").glob("*.wav"):     # 지난 테이크의 wav 는 치운다(페이지가 안 가리킨다)
        if p.name not in keep:
            p.unlink()
    print(f"   새로 받아쓴 테이크 {fresh}개 · 그대로 둔 것 {len(rows) - fresh}개")
    data = {"cache": str(cdir), "engine": idx.get("engine"), "made": time.strftime("%Y-%m-%d %H:%M"), "rows": rows}
    (out / "review.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    html = (ROOT / "scripts" / "tts_review.html").read_text(encoding="utf-8")
    (out / "index.html").write_text(
        html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")
    sus = [r for r in rows if r["verdict"] == "suspect"]
    stt = [r for r in rows if r["verdict"] == "stt"]
    flagged = [r for r in rows if r["flags"]]
    print(f"끝 — {len(rows)}문장: 발음 의심 {len(sus)} · STT 쪽 차이 {len(stt)} · 통과 {len(rows) - len(sus) - len(stt)}"
          f" · 소리 품질 표시 {len(flagged)}. 듣기: {out / 'index.html'}")
    for r in sus:
        print(f"   의심 {r['psim']:.2f} {r['where'][0]} | 다른 곳 {r['diffs']} | 대본 {r['text']} | 들림 {r['heard']} | 힌트 {r['biased']}")
    for r in stt:
        print(f"   STT  {r['psim']:.2f} {r['where'][0]} | 다른 곳 {r['diffs']}")
    for r in flagged:
        print(f"   품질 {', '.join(r['flags'])} {r['where'][0]} | {r['text'][:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
