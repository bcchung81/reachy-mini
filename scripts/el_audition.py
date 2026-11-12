"""목소리 오디션 — ElevenLabs 후보 × 실제 대본 문장 × 모델 → WAV + 나란히 듣는 HTML 한 장.

계획 `docs/superpowers/plans/2026-11-12-elevenlabs-tts.md`(A2). 결과는 **저장소 밖**에 둔다
(`$TTS_ASSETS/audition/<날짜>/`) — 소리 파일은 커밋하지 않는다.

문장은 손으로 적지 않고 **굽기가 쓰는 고정 대사 목록에서 찾는다**(`bake_tts.plan`). 대본이 바뀌어
찾는 문장이 사라지면 조용히 다른 문장으로 넘어가지 않고 멈춘다.

라이브러리 목소리는 "내 목소리"에 추가하지 않아도 API 로 바로 합성된다(2026-11-12 실측).

사용:
    .venv/bin/python scripts/el_audition.py [--out DIR] [--voices stella,seulki] [--models eleven_v4,eleven_v4_turbo]
        [--dry-run] [--force]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys
import wave
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tts_elevenlabs as el  # noqa: E402

# 후보 — 보이스 라이브러리에서 예고 기간 730일·별도 요율 없음을 확인했다(2026-11-12, GET /v1/shared-voices).
# Jennie 는 예고 기간이 비어 있어(주인이 공유를 내리면 바로 사라질 수 있다) 비교용으로만 둔다.
CANDIDATES = [
    {"key": "stella", "name": "Stella", "desc": "Steady, Clear and Cheerful", "id": "1YzIw7PZ7iaD4alelyHY",
     "group": "사회자 후보", "notice": "730일"},
    {"key": "jy", "name": "JY", "desc": "Trendy · upbeat", "id": "bQlkYuipD5BHEhntA5iz",
     "group": "사회자 후보", "notice": "730일"},
    {"key": "yooni", "name": "Yooni", "desc": "Natural & Clear", "id": "n2fbxG88jqAoaVPUy3IG",
     "group": "사회자 후보", "notice": "730일"},
    {"key": "jennie", "name": "Jennie", "desc": "Narrational · 예고 기간 미설정(비교용)", "id": "z6Kj0hecH20CdetSElRT",
     "group": "사회자 후보", "notice": "미설정"},
    {"key": "seulki", "name": "Seulki", "desc": "Inviting, Calm and Measured", "id": "ksaI0TCD9BstzEzlxj4q",
     "group": "도슨트 후보", "notice": "730일"},
    {"key": "selly", "name": "Selly Han", "desc": "Warm, Calm and Steady", "id": "ETPP7D0aZVdEj12Aa7ho",
     "group": "도슨트 후보", "notice": "730일"},
    {"key": "hyein", "name": "Hyein", "desc": "Calm & Professional", "id": "6Vgh4FaCc0SCcWPwcyXa",
     "group": "도슨트 후보", "notice": "730일"},
    {"key": "anna", "name": "Anna Kim", "desc": "Tender, Calm and Clear", "id": "uyVNoMrnUku1dZyVEXwD",
     "group": "도슨트 후보", "notice": "730일"},
    {"key": "jeonggi", "name": "Jeonggi", "desc": "Confident Narrator · 교육", "id": "HCANy6ACvOWyndVWS0gV",
     "group": "남성 대안", "notice": "730일"},
    {"key": "juan", "name": "Juan", "desc": "Deep, Clear, Edu & Corporate", "id": "hjCvGtSCRPyjYwe2lDf1",
     "group": "남성 대안", "notice": "730일"},
]

# (표시 이름, 찾을 낱말들) — 낱말마다 고정 대사 한 문장을 찾아 이어 붙인다.
SENTENCES = [
    ("사회자 인사", ["안녕하세요, 여러분!", "이야기 시간에 오신 걸 환영해요"]),
    ("사회자 질문", ["어떤 곳인지부터 소개해 줄래요"]),
    ("연도·날짜 — 일반", ["1901년 12월 12일"]),
    ("영문 약어 — 일반", ["초장파는 VLF"]),
    ("수치·단위 — 일반", ["100메가헤르츠 FM"]),
    ("소수점 주파수 — 전문가", ["121.5메가헤르츠와 406"]),
    ("비유 — 초등", ["연못의 물결처럼"]),
]


def pick_sentences() -> list[dict]:
    """굽기의 고정 대사 목록에서 오디션 문장을 찾는다. 하나라도 없으면 멈춘다."""
    import bake_tts
    entries = bake_tts.plan(bake_tts.fixed_lines())
    out = []
    for label, needles in SENTENCES:
        texts, wheres = [], []
        for n in needles:
            hits = [e for e in entries if n in e["text"]]
            if not hits:
                sys.exit(f"✗ 오디션 문장을 대본에서 못 찾았다: {n!r} — 대본이 바뀌었다. SENTENCES 를 고친다")
            e = min(hits, key=lambda e: len(e["text"]))
            texts.append(e["text"])
            wheres.append(e["where"][0])
        out.append({"label": label, "text": " ".join(texts), "where": " · ".join(wheres)})
    return out


def write_wav(path: pathlib.Path, pcm: bytes) -> None:
    tmp = path.with_suffix(".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(el.PCM_RATE)
        w.writeframes(pcm)
    os.replace(tmp, path)


def wav_seconds(path: pathlib.Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def main() -> int:
    ap = argparse.ArgumentParser(description="ElevenLabs 목소리 오디션")
    assets = pathlib.Path(os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")).expanduser()
    ap.add_argument("--out", default=str(assets / "audition" / datetime.date.today().isoformat()))
    ap.add_argument("--voices", default="", help="쉼표로 후보 key 만 고른다(기본: 전부)")
    ap.add_argument("--models", default=f"{el.MODEL_BAKE},{el.MODEL_LIVE}")
    ap.add_argument("--dry-run", action="store_true", help="합성 없이 문장·비용만 본다")
    ap.add_argument("--force", action="store_true", help="있는 소리도 다시 받는다(크레딧이 든다)")
    args = ap.parse_args()

    voices = CANDIDATES
    if args.voices:
        want = {v.strip() for v in args.voices.split(",") if v.strip()}
        voices = [v for v in CANDIDATES if v["key"] in want]
        if missing := want - {v["key"] for v in voices}:
            sys.exit(f"✗ 모르는 후보: {sorted(missing)}")
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    sents = pick_sentences()
    out = pathlib.Path(args.out).expanduser()

    jobs = []
    for v in voices:
        for si, s in enumerate(sents):
            for m in models:
                path = out / f"{v['key']}_{si}_{m}.wav"
                if args.force or not path.is_file():
                    jobs.append((v, si, s, m, path))
    cost = sum(el.credits_for(s["text"], m) for _, _, s, m, _ in jobs)
    print(f"후보 {len(voices)} × 문장 {len(sents)} × 모델 {len(models)} — 새로 받을 소리 {len(jobs)}개, 약 {cost:,.0f} 크레딧")
    for s in sents:
        print(f"   [{s['label']}] {len(s['text'])}자 ({s['where']}) {s['text']}")
    if args.dry_run:
        return 0

    key = el.load_api_key()
    if not key:
        sys.exit("✗ ElevenLabs 키가 없다(ELEVENLABS_API_KEY 또는 저장소 루트 .env)")
    used, limit = el.credits_left(key)
    print(f"   크레딧 {used:,} / {limit:,} 사용 중 — 이번 약 {cost:,.0f}")
    if limit and used + cost > limit * 0.9:
        sys.exit("✗ 이번 오디션이 월 한도의 90%를 넘긴다 — 후보나 문장을 줄인다")
    out.mkdir(parents=True, exist_ok=True)

    def run(job):
        v, si, s, m, path = job
        _, payload = el.el_request({"voice": v["key"], "input": s["text"]}, voices={v["key"]: v["id"]},
                                   model=m, language_code="ko")
        pcm = el.synth(v["id"], payload, key)
        write_wav(path, pcm)
        return f"{v['name']} [{s['label']}] {m} {el.pcm_seconds(pcm):.1f}초"

    failed = 0
    # 동시 요청은 3개까지 — Creator 의 v4 계열 한도는 5개다(로봇이 같은 키로 돌고 있을 수 있다).
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(run, j) for j in jobs]
        for i, f in enumerate(futs, 1):
            try:
                print(f"   [{i}/{len(jobs)}] {f.result()}", flush=True)
            except el.ElevenLabsError as exc:
                failed += 1
                v, si, s, m, _ = jobs[i - 1]
                print(f"   ✗ [{i}/{len(jobs)}] {v['name']} [{s['label']}] {m} — {exc}", flush=True)

    # 목록과 길이 — HTML 이 읽는다. 받은 파일만 싣는다.
    clips = []
    for v in voices:
        for si, s in enumerate(sents):
            for m in models:
                path = out / f"{v['key']}_{si}_{m}.wav"
                if path.is_file():
                    clips.append({"voice": v["key"], "s": si, "model": m, "file": path.name,
                                  "sec": round(wav_seconds(path), 2)})
    manifest = {"made": datetime.datetime.now().isoformat(timespec="seconds"),
                "voices": voices, "sentences": sents, "models": models, "clips": clips}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    html = (ROOT / "scripts" / "el_audition.html").read_text(encoding="utf-8")
    data = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    (out / "index.html").write_text(html.replace("/*__DATA__*/null", data), encoding="utf-8")
    used2, _ = el.credits_left(key)
    print(f"끝 — 실패 {failed}. 크레딧 {used2:,} / {limit:,}(집계는 몇 초 늦게 반영된다)")
    print(f"듣기: {out / 'index.html'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
