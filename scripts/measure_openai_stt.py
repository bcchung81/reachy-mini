"""관람객 말 STT 실측 — 로컬(`stt_server.py`, mlx-whisper large-v3-turbo) vs OpenAI `gpt-transcribe`.

계획 `docs/superpowers/plans/2026-11-12-openai-measure.md`, 결과 `docs/research/2026-11-12-openai-llm-stt-measure.md`.

**실제 관람객 녹음이 없다**(저장소의 wav 3개는 로봇 TTS 샘플). 그래서 시험 세트를 ElevenLabs 로 합성한다 — 한계:
사람 녹음보다 또박또박하고, 실제 전시장 잔향·말 겹침이 없다. 그래서 **절대 수치보다 두 STT 의 상대 비교**로 읽는다.

**아이 목소리**: ElevenLabs 보이스 라이브러리의 한국어 목소리에는 실제 아이 목소리가 없고(age=young 은 젊은 성인),
목소리 디자인으로 아이 목소리를 만들려 하면 403 `blocked_generation`(안전 정책)으로 막힌다(2026-11-12 실측). 그래서
젊은 목소리 둘을 **음높이·포먼트를 함께 올려**(위상 보코더로 늘인 뒤 재표본화) 아이 목소리를 근사한다 — 아이 음성 인식
연구에서 쓰는 증강 기법이지만 진짜 아이 발음(조음 미숙·억양)은 없다. 보고서에 "근사" 로 적는다.

로봇 입력과 맞추기: 24 kHz → **16 kHz 모노 16-bit**(앱 `stt.transcribe` 가 보내는 형식), 앞뒤 무음 0.3초(VAD 가 자른 조각
모양), 음량 정규화. 조건 두 가지 — 깨끗함 · 분홍 잡음 SNR 15 dB(전시장 대용). 잡음·거의 무음만 있는 조각도 넣어
환각(없는 말 만들기)을 본다 — 감독의 잡음 거르개(`stage.cues.noise_reason`)를 통과하는지까지 센다(앱 경로).

사용:
    .venv/bin/python scripts/measure_openai_stt.py --dry-run          # 문장·목소리·예상 크레딧/비용
    .venv/bin/python scripts/measure_openai_stt.py --make-set         # ElevenLabs 합성(크레딧 확인 후) + 16 kHz 변환
    .venv/bin/python scripts/measure_openai_stt.py --run              # 로컬(:18090)·OpenAI 받아쓰기
    .venv/bin/python scripts/measure_openai_stt.py --report
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import json
import pathlib
import sys
import time
import wave

import numpy as np
import requests
from scipy import signal

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tts_elevenlabs as E  # noqa: E402
from scripts.measure_openai_common import (  # noqa: E402
    OPENAI_BASE, OUT, STT_PRICE_PER_MIN, fmt_s, load_openai_key, read_jsonl, summary, write_jsonl,
)
from scripts.tts_review import norm, phonetic, spoken  # noqa: E402  검수 도구와 같은 정규화·발음 규칙
from stage.cues import noise_reason  # noqa: E402  감독이 잡음 전사를 거르는 판정 그대로

STT_OUT = OUT / "stt"
EL_MODEL = "eleven_v4_turbo"           # 구운 고정 대사·실시간 답과 같은 모델(글자당 0.5 크레딧)
CREDIT_BUDGET = 1400                   # 브리프 상한 1,500 에서 여유를 둔다
RATE_IN = 24000
RATE = 16000                           # 로봇이 STT 로 보내는 형식

# 목소리 — 라이브러리 한국어, 예고 기간 730일(Sung-ho 4015일). 나이·성별·억양을 섞는다.
VOICES = {
    "aria": ("O2KReOFLpoR65nz6C9Se", "여 · 젊음 · 밝고 어려 보이는 목소리(Aria)"),
    "deoksu": ("IAETYMYM3nJvjnlkVTKI", "남 · 젊음 · 귀여운 캐릭터 목소리(Deoksu)"),
    "taek": ("rCm09Tf1yMYbOyCRLDyB", "남 · 젊음 · 대화체(Taek)"),
    "shinrara": ("VFNaRkx6q2IQZn2mmwwg", "여 · 중년 · 약한 지역 억양(Shin rara)"),
    "sungho": ("AgA5UKT9OrVg7jxVBZd4", "남 · 노년 · 대화체(Sung-ho)"),
    "mjay": ("SrkN8J8D7m8bAtmS0uiq", "여 · 노년 · 차분(MJay)"),
}
# 아이 근사 — (원본 목소리, 반음). 아이는 기본 주파수와 포먼트가 함께 높다(성도가 짧다) — 둘을 같이 올린다.
CHILD_SIM = {"child-girl~": ("aria", 4.0), "child-boy~": ("deoksu", 5.0)}

# 문장 — 질문은 LLM 측정과 같은 것에서 고르고(같은 출처 표지), 짧은 말은 공연에서 실제로 쓰는 진행·인사말이다
# (감독의 `is_advance` 가 "다음" 을 본다). 짧은 말은 언어 자동 감지가 가장 위험한 자리다(stt_server.AUTO_MIN_SECONDS 주석).
STT_QIDS = ("q01", "q03", "q04", "q06", "q07", "q08", "q09", "q10", "q11", "q12", "q13", "q14",
            "q15", "q17", "q18", "q19", "q20", "q21", "q22", "q23", "q24", "q27", "q28", "q31")
SHORT = [("s01", "네"), ("s02", "다음"), ("s03", "아니요"), ("s04", "감사합니다"),
         ("s05", "안녕하세요"), ("s06", "한 번 더 말해 주세요")]
# OpenAI `keywords` 시험용 — 전시 고유명사(게이트웨이가 얹을 수 있는 선택지). 대본에서 고른 낱말이다.
KEYWORDS = ["마르코니", "헤르츠", "맥스웰", "모스 부호", "타이타닉", "테레민", "크로마키", "장황남",
            "아마추어 무선", "사물인터넷", "전자파", "무선국", "화성 로버", "루노호트", "주파수", "파장"]

SYSTEMS = {
    # 앱 기본(`REACHY_STT_LANG` 미설정 = auto) — 서버가 자동 감지, 1초 미만은 ko, 허용 밖 언어면 ko 로 재전사
    "local-auto": {"kind": "local", "language": "auto"},
    "local-ko": {"kind": "local", "language": "ko"},
    # 게이트웨이 번역: language=auto → languages 생략, ko → languages[]=ko (둘 다 보내면 거절 — STT 가이드)
    "openai-auto": {"kind": "openai", "languages": None},
    "openai-ko": {"kind": "openai", "languages": ["ko"]},
    # 게이트웨이(B2 `openai_gateway.languages_for`)가 로봇의 auto 를 1초 이상이면 허용 언어 전부(ko,en)로 보낸다 — 그 모양
    "openai-koen": {"kind": "openai", "languages": ["ko", "en"]},
    "openai-ko-kw": {"kind": "openai", "languages": ["ko"], "keywords": KEYWORDS},
}


def texts() -> list[dict]:
    from scripts.measure_openai_llm import QUESTIONS
    qs = {q["id"]: q for q in QUESTIONS}
    out = [{"tid": i, "text": qs[i]["q"], "kind": "질문", "src": qs[i]["src"]} for i in STT_QIDS]
    out += [{"tid": i, "text": t, "kind": "짧은 말", "src": "합성"} for i, t in SHORT]
    return out


# ── 소리 만들기 ──────────────────────────────────────────────────────
def _time_stretch(x: np.ndarray, rate: float, n_fft: int = 1024, hop: int = 256) -> np.ndarray:
    """위상 보코더 — rate < 1 이면 길어진다(음높이는 그대로)."""
    _, _, Z = signal.stft(x, nperseg=n_fft, noverlap=n_fft - hop)
    steps = np.arange(0, Z.shape[1] - 1, rate)
    omega = 2 * np.pi * hop * np.arange(Z.shape[0]) / n_fft
    phase = np.angle(Z[:, 0])
    out = np.zeros((Z.shape[0], len(steps)), dtype=complex)
    for i, s in enumerate(steps):
        k = int(s)
        frac = s - k
        mag = (1 - frac) * np.abs(Z[:, k]) + frac * np.abs(Z[:, k + 1])
        out[:, i] = mag * np.exp(1j * phase)
        d = np.angle(Z[:, k + 1]) - np.angle(Z[:, k]) - omega
        d -= 2 * np.pi * np.round(d / (2 * np.pi))
        phase = phase + omega + d
    _, y = signal.istft(out, nperseg=n_fft, noverlap=n_fft - hop)
    return y.astype(np.float32)


def pitch_formant_shift(x: np.ndarray, semitones: float) -> np.ndarray:
    """음높이와 포먼트를 함께 올리고 길이는 그대로 — 늘인 뒤(r 배) 빠르게 재표본화(1/r)."""
    r = 2 ** (semitones / 12)
    y = _time_stretch(x, 1 / r)
    return signal.resample(y, int(round(len(y) / r))).astype(np.float32)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f 잡음(전시장 웅성거림·공조 대용). 주파수 영역에서 1/sqrt(f) 로 깎는다."""
    white = rng.standard_normal(n)
    f = np.fft.rfft(white)
    k = np.arange(len(f))
    k[0] = 1
    y = np.fft.irfft(f / np.sqrt(k), n)
    return (y / (np.sqrt(np.mean(y ** 2)) + 1e-12)).astype(np.float32)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64))) + 1e-12))


def to_robot(x24: np.ndarray, *, snr_db: float | None, seed: int) -> np.ndarray:
    """24 kHz float → 16 kHz, 앞뒤 무음 0.3초, 음성 RMS -23 dBFS, (선택) 분홍 잡음."""
    x = signal.resample_poly(x24, 2, 3).astype(np.float32)
    pad = np.zeros(int(0.3 * RATE), dtype=np.float32)
    speech_rms = rms(x)
    x = np.concatenate([pad, x, pad]) * (10 ** (-23 / 20) / speech_rms)
    if snr_db is not None:
        n = pink_noise(len(x), np.random.default_rng(seed))
        x = x + n * (10 ** (-23 / 20)) * (10 ** (-snr_db / 20))
    peak = float(np.max(np.abs(x))) or 1.0
    if peak > 0.98:
        x = x * (0.98 / peak)
    return x.astype(np.float32)


def wav_bytes(x: np.ndarray, rate: int = RATE) -> bytes:
    """앱 `stt.transcribe` 와 같은 조립 — 16-bit 모노."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def read_wav(path: pathlib.Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def make_set(dry: bool) -> None:
    items = texts()
    chars = sum(len(t["text"]) for t in items) * len(VOICES)
    credits = chars * E.CREDITS_PER_CHAR[EL_MODEL]
    print(f"문장 {len(items)}개 × 목소리 {len(VOICES)}개 = {len(items) * len(VOICES)}건 · {chars}자 · 예상 {credits:.0f} 크레딧"
          f"(상한 {CREDIT_BUDGET}) · 아이 근사 {len(CHILD_SIM)}개는 크레딧 없음")
    if dry:
        return
    key = E.load_api_key()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY 가 없다(.env)")
    used0, limit = E.credits_left(key)
    print(f"ElevenLabs 이번 달 사용 {used0}/{limit}")
    raw_dir = STT_OUT / "raw24k"
    raw_dir.mkdir(parents=True, exist_ok=True)
    need = [(v, t) for v in VOICES for t in items if not (raw_dir / f"{v}-{t['tid']}.pcm").exists()]
    est = sum(len(t["text"]) for _, t in need) * E.CREDITS_PER_CHAR[EL_MODEL]
    if est > CREDIT_BUDGET:
        raise SystemExit(f"예상 {est:.0f} 크레딧이 상한 {CREDIT_BUDGET} 을 넘는다 — 문장을 줄인다")
    for i, (v, t) in enumerate(need, 1):
        vid = VOICES[v][0]
        payload = {"text": t["text"], "model_id": EL_MODEL, "language_code": "ko"}
        pcm = E.synth(vid, payload, key)          # 409(첫 사용 겹침)·429·5xx 는 어댑터가 다시 한다
        (raw_dir / f"{v}-{t['tid']}.pcm").write_bytes(pcm)
        print(f"  {i}/{len(need)} {v} {t['tid']} {E.pcm_seconds(pcm):.1f}s")
    used1, _ = E.credits_left(key)
    (STT_OUT / "credits.json").write_text(json.dumps({"before": used0, "after": used1, "spent": used1 - used0,
                                                      "limit": limit}, indent=1))
    print(f"ElevenLabs 사용 {used1 - used0} 크레딧(이번 달 {used1}/{limit})")
    build_wavs(items)


def build_wavs(items: list[dict]) -> None:
    raw_dir = STT_OUT / "raw24k"
    wav_dir = STT_OUT / "wav16k"
    wav_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    voices = list(VOICES) + list(CHILD_SIM)
    for vi, v in enumerate(voices):
        src_v, semis = CHILD_SIM.get(v, (v, 0.0))
        for ti, t in enumerate(items):
            pcm = (raw_dir / f"{src_v}-{t['tid']}.pcm").read_bytes()
            x24 = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
            if semis:
                x24 = pitch_formant_shift(x24, semis)
            for cond, snr in (("clean", None), ("noise15", 15.0)):
                x = to_robot(x24, snr_db=snr, seed=1000 * vi + ti)
                name = f"{cond}/{v}-{t['tid']}.wav"
                (wav_dir / cond).mkdir(exist_ok=True)
                (wav_dir / name).write_bytes(wav_bytes(x))
                manifest.append({"file": name, "voice": v, "child_sim": bool(semis), "tid": t["tid"], "text": t["text"],
                                 "kind": t["kind"], "cond": cond, "secs": len(x) / RATE})
    # 말이 없는 조각 — 환각을 본다. 잡음은 잡음 조건과 같은 세기, 거의 무음은 -60 dBFS.
    rng = np.random.default_rng(99)
    for i, (secs, level_db, label) in enumerate([(1.5, -23 - 15, "잡음"), (3.0, -23 - 15, "잡음"), (5.0, -23 - 15, "잡음"),
                                                 (2.0, -60, "거의 무음"), (4.0, -60, "거의 무음")]):
        x = pink_noise(int(secs * RATE), rng) * (10 ** (level_db / 20))
        name = f"none/none-{i}.wav"
        (wav_dir / "none").mkdir(exist_ok=True)
        (wav_dir / name).write_bytes(wav_bytes(x))
        manifest.append({"file": name, "voice": "-", "child_sim": False, "tid": f"n{i}", "text": "", "kind": label,
                         "cond": "none", "secs": secs})
    write_jsonl(STT_OUT / "manifest.jsonl", manifest)
    print(f"16 kHz WAV {len(manifest)}개 → {wav_dir}")


# ── 받아쓰기 ─────────────────────────────────────────────────────────
_local = requests.Session()
_openai = requests.Session()


def call(system: str, wav: bytes, *, local_url: str, key: str | None) -> dict:
    cfg = SYSTEMS[system]
    t0 = time.perf_counter()
    if cfg["kind"] == "local":
        # 앱 `stt.transcribe` 와 같은 요청 — files·data 모양, 15초 타임아웃
        r = _local.post(f"{local_url}/v1/audio/transcriptions",
                        files={"file": ("utt.wav", wav, "audio/wav")},
                        data={"language": cfg["language"]}, timeout=15)
    else:
        data: list[tuple[str, str]] = [("model", "gpt-transcribe")]
        for lang in cfg.get("languages") or []:
            data.append(("languages[]", lang))
        for kw in cfg.get("keywords") or []:
            data.append(("keywords[]", kw))
        r = _openai.post(f"{OPENAI_BASE}/v1/audio/transcriptions",
                         headers={"Authorization": f"Bearer {key}"},
                         files={"file": ("utt.wav", wav, "audio/wav")}, data=data, timeout=60)
    dt = time.perf_counter() - t0
    out = {"latency": dt, "status": r.status_code}
    try:
        j = r.json()
    except ValueError:
        j = {"error": r.text[:300]}
    if r.status_code != 200:
        out["error"] = json.dumps(j, ensure_ascii=False)[:400]
        out["hyp"] = ""
    else:
        out["hyp"] = (j.get("text") or "").strip()
        out["lang"] = j.get("language") or j.get("languages")
        if j.get("usage"):
            out["usage"] = j["usage"]
    return out


def lev(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> tuple[float, float]:
    """(글자 CER, 발음 CER). 띄어쓰기·문장부호 무시, 숫자·단위는 읽는 소리로(`tts_review.spoken`)."""
    r, h = norm(spoken(ref)), norm(spoken(hyp))
    c = lev(r, h) / max(1, len(r))
    pr, ph = phonetic(ref), phonetic(hyp)
    return c, lev(pr, ph) / max(1, len(pr))


def run(local_url: str, systems: list[str], workers: int) -> None:
    key = load_openai_key()
    man = read_jsonl(STT_OUT / "manifest.jsonl")
    if not man:
        raise SystemExit("시험 세트가 없다 — --make-set 먼저")
    out_path = STT_OUT / "results.jsonl"
    rows = [r for r in read_jsonl(out_path) if r.get("status") == 200]
    done = {(r["file"], r["system"]) for r in rows}
    wav_dir = STT_OUT / "wav16k"
    # 로컬 예열(서버가 기동 때 하지만 우리 첫 요청의 연결·캐시도 데운다) — 통계에서 뺀다
    for s in systems:
        call(s, (wav_dir / man[0]["file"]).read_bytes(), local_url=local_url, key=key)

    def one(item, s):
        res = call(s, (wav_dir / item["file"]).read_bytes(), local_url=local_url, key=key)
        # 정답은 `text`(시험 세트), 받아쓴 것은 `hyp` — 한 이름으로 두면 정답이 덮인다
        row = {**item, "system": s, **res}
        if item["text"]:
            row["cer"], row["pcer"] = cer(item["text"], res["hyp"])
        row["noise_reason"] = noise_reason(res["hyp"]) if res["hyp"] else "빈 전사"
        return row

    for s in systems:
        todo = [m for m in man if (m["file"], s) not in done]
        # 로컬은 한 번에 하나(앱도 직렬 — 동시 요청이면 지연이 합쳐진다). OpenAI 는 몇 개씩(지연은 요청마다 잰다).
        n = 1 if SYSTEMS[s]["kind"] == "local" else workers
        with cf.ThreadPoolExecutor(max_workers=n) as ex:
            for i, row in enumerate(ex.map(lambda m: one(m, s), todo), 1):
                rows.append(row)
                if i % 25 == 0 or i == len(todo):
                    write_jsonl(out_path, rows)
                    print(f"  {s} {i}/{len(todo)}")
        write_jsonl(out_path, rows)


# ── 보고 ─────────────────────────────────────────────────────────────
def report() -> str:
    rows = read_jsonl(STT_OUT / "results.jsonl")
    systems = [s for s in SYSTEMS if any(r["system"] == s for r in rows)]
    out = []

    def agg(rs):
        cs = [r["cer"] for r in rs if "cer" in r]
        ps = [r["pcer"] for r in rs if "pcer" in r]
        exact = sum(1 for r in rs if r.get("cer") == 0)
        return (sum(cs) / len(cs) if cs else None, sum(ps) / len(ps) if ps else None, exact, len(cs))

    out.append("### 글자 오류율(CER, 평균) — 띄어쓰기·문장부호 무시, 숫자는 읽는 소리로\n")
    groups = [("성인 6목소리", lambda r: not r["child_sim"] and r["voice"] != "-"),
              ("아이 근사 2", lambda r: r["child_sim"]),
              ("질문만", lambda r: r["kind"] == "질문"),
              ("짧은 말만", lambda r: r["kind"] == "짧은 말")]
    out.append("| 시스템 | 조건 | " + " | ".join(f"{g} CER / 발음CER / 완전일치" for g, _ in groups) + " |")
    out.append("|---|---|" + "---|" * len(groups))
    for s in systems:
        for cond in ("clean", "noise15"):
            cells = []
            for _, f in groups:
                rs = [r for r in rows if r["system"] == s and r["cond"] == cond and f(r)]
                c, p, e, n = agg(rs)
                cells.append("—" if c is None else f"{c:.1%} / {p:.1%} / {e}/{n}")
            out.append(f"| {s} | {cond} | " + " | ".join(cells) + " |")
    out.append("\n### 목소리별 CER(깨끗함 / 잡음)\n")
    voices = list(VOICES) + list(CHILD_SIM)
    out.append("| 시스템 | " + " | ".join(voices) + " |")
    out.append("|---|" + "---|" * len(voices))
    for s in systems:
        cells = []
        for v in voices:
            a = agg([r for r in rows if r["system"] == s and r["voice"] == v and r["cond"] == "clean"])[0]
            b = agg([r for r in rows if r["system"] == s and r["voice"] == v and r["cond"] == "noise15"])[0]
            cells.append(f"{fmt_pct(a)} / {fmt_pct(b)}")
        out.append(f"| {s} | " + " | ".join(cells) + " |")
    out.append("\n### 지연(초, 요청~응답) · 실패 · 비용\n")
    out.append("| 시스템 | n | 실패 | 중앙 | p90 | 최대 | 오디오 분 | 비용 $(청구 초 기준) |")
    out.append("|---|---|---|---|---|---|---|---|")
    for s in systems:
        rs = [r for r in rows if r["system"] == s]
        ok = [r for r in rs if r["status"] == 200]
        lat = summary([r["latency"] for r in ok])
        mins = sum(r["secs"] for r in rs) / 60
        # 청구는 응답 usage 의 **초 단위 올림**(2.6초 조각 → 3초)이다 — 짧은 조각이 많으면 오디오 길이보다 비싸다
        billed = sum((r.get("usage") or {}).get("seconds", 0) for r in ok) / 60
        cost = (billed or mins) * STT_PRICE_PER_MIN["gpt-transcribe"] if SYSTEMS[s]["kind"] == "openai" else 0
        out.append(f"| {s} | {len(rs)} | {len(rs) - len(ok)} | {fmt_s(lat.get('median'))} | {fmt_s(lat.get('p90'))} | "
                   f"{fmt_s(lat.get('max'))} | {mins:.1f} | {cost:.3f} |")
    out.append("\n### 말이 없는 조각(잡음 3·거의 무음 2) — 무엇을 받아썼나, 감독이 거르나\n")
    out.append("| 시스템 | 조각 | 전사 | 감독 거르개 |")
    out.append("|---|---|---|---|")
    for s in systems:
        for r in [r for r in rows if r["system"] == s and r["cond"] == "none"]:
            out.append(f"| {s} | {r['kind']} {r['secs']:.1f}s | {r['hyp']!r} | {r['noise_reason'] or '통과(질문으로 처리됨)'} |")
    out.append("\n### 짧은 말 — 그대로 받아썼나(깨끗함, 목소리 8개 중 완전일치)\n")
    out.append("| 시스템 | " + " | ".join(t for _, t in SHORT) + " |")
    out.append("|---|" + "---|" * len(SHORT))
    for s in systems:
        cells = []
        for tid, _ in SHORT:
            rs = [r for r in rows if r["system"] == s and r["tid"] == tid and r["cond"] == "clean"]
            cells.append(f"{sum(1 for r in rs if r.get('cer') == 0)}/{len(rs)}")
        out.append(f"| {s} | " + " | ".join(cells) + " |")
    out.append("\n### 틀린 받아쓰기 표본(깨끗함, CER 높은 순)\n")
    bad = sorted([r for r in rows if r["cond"] == "clean" and r.get("cer", 0) > 0], key=lambda r: -r["cer"])
    for r in bad[:40]:
        out.append(f"- {r['system']} · {r['voice']} · CER {r['cer']:.0%} · 「{r['text']}」 → 「{r['hyp']}」")
    text = "\n".join(out)
    (STT_OUT / "summary.md").write_text(text, encoding="utf-8")
    return text


def fmt_pct(v):
    return "—" if v is None else f"{v:.1%}"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--make-set", action="store_true")
    ap.add_argument("--rebuild-wavs", action="store_true", help="합성 없이 16 kHz 변환만 다시")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--systems", default=",".join(SYSTEMS))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--local-url", default="http://127.0.0.1:18090")
    a = ap.parse_args(argv)
    print(f"OPENAI_API_KEY: {'설정됨' if load_openai_key() else '없음'} · ELEVENLABS: "
          f"{E.key_status(E.load_api_key())} · 산출물 {STT_OUT}")
    if a.dry_run:
        make_set(dry=True)
        items = texts()
        n_clips = len(items) * (len(VOICES) + len(CHILD_SIM)) * 2 + 5
        avg_s = 2.4
        n_open = sum(1 for s in a.systems.split(",") if SYSTEMS[s]["kind"] == "openai")
        print(f"받아쓰기 조각 {n_clips}개 × OpenAI 설정 {n_open}개 ≈ {n_clips * avg_s * n_open / 60:.0f}분 → "
              f"약 ${n_clips * avg_s * n_open / 60 * STT_PRICE_PER_MIN['gpt-transcribe']:.2f}")
        return
    if a.make_set:
        make_set(dry=False)
    if a.rebuild_wavs:
        build_wavs(texts())
    if a.run:
        run(a.local_url, a.systems.split(","), a.workers)
    if a.report:
        print(report())


if __name__ == "__main__":
    main()
