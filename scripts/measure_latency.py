"""TTFT / 첫 절 생성 / 첫 절 합성을 실측한다. LLM(:8080)·TTS(:8099) 서버 필요.

**합성은 앱이 쓰는 경로 그대로 잰다.** 예전에는 macOS `say -o` 로 쟀는데, 앱이
Qwen3-TTS 스트리밍으로 옮긴 뒤로 그 수치는 프로덕션과 무관해졌다 — 게다가
`say` 는 macOS 전용이라 PC 가 리눅스면 측정 자체가 안 된다. 지금은
`tts.Speaker` 가 쓰는 함수를 직접 부른다:

  · 스트리밍 켬(기본) — **첫 청크까지**를 잰다. 이게 사용자가 첫 소리를 듣는
    시점이고, 입력 길이와 무관하게 고정이라는 것이 이 구성의 요점이다.
  · 스트리밍 끔(`TTS_QWEN_STREAM=0`) — 전체 합성 완료까지. 입력 길이에 선형으로
    늘어나는 예전 특성을 보고 싶을 때만.

TTS 서버가 없으면 합성 열은 건너뛰고 LLM 수치만 낸다 — 조용히 0 을 적지 않는다.

    ./reachy.sh measure latency
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

# 앱과 **같은 합성 경로**를 쓴다 — 여기서 요청을 다시 짜면 tts.py 와 갈라진다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps/voice_chat/voice_chat"))
import tts as tts_mod  # noqa: E402


def _synth_first_audio(text: str) -> float | None:
    """첫 소리까지 걸린 시간(초). TTS 서버가 없으면 None.

    스트리밍이면 **첫 청크까지**만 잰다 — 사용자가 첫 소리를 듣는 시점이고,
    입력 길이와 무관하게 고정이라는 것이 이 구성의 요점이다.
    """
    t0 = time.time()
    try:
        opened = tts_mod._qwen_open(
            tts_mod._qwen_body(text, seed=None, stream=tts_mod.QWEN_STREAM)
        )
    except Exception:  # noqa: BLE001
        return None
    with opened:
        ctype = (opened.headers.get("Content-Type") or "").lower()
        if tts_mod.QWEN_STREAM and "pcm" in ctype:
            read = getattr(opened, "read1", None) or opened.read
            if not read(tts_mod._PCM_CHUNK):
                return None
        else:
            if not opened.read():  # 구버전 서버 — wav 한 방
                return None
    return time.time() - t0

# 앱과 같은 환경변수를 읽는다 — 하드코딩하면 분리 배치에서 엉뚱한 호스트를 잰다.
BASE = os.environ.get("REACHY_LLM_URL", "http://127.0.0.1:8080").rstrip("/")
SYSTEM = "너는 데스크톱 로봇 '미니'야. 한국어로 짧고 다정하게 1~2문장으로 답해. 사용자 말을 그대로 반복하지 마."
QUESTIONS = ["안녕, 오늘 기분 어때?", "점심에 뭐 먹을지 고민이야.", "재밌는 얘기 하나 해줘."]
BOUNDARY = ".!?…。"
VAD_HANGOVER = 0.30
STT_WORST = 0.25


def one_round(q: str) -> dict:
    t0 = time.time()
    r = requests.post(
        f"{BASE}/v1/chat/completions",
        stream=True,
        timeout=30,
        json={
            "model": "local",
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 200,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": q},
            ],
        },
    )
    r.raise_for_status()

    ttft = first_clause_t = None
    first_clause = ""
    buf, full = "", []
    # 바이트로 줄을 나눈 뒤 줄 단위로 디코드한다. decode_unicode=True 는 청크
    # 경계에서 한글 멀티바이트를 쪼개 JSON 을 깨뜨린다(실측 확인).
    for raw in r.iter_lines():
        if not raw or not raw.startswith(b"data: "):
            continue
        data = raw[6:].decode("utf-8")
        if data == "[DONE]":
            break
        delta = json.loads(data)["choices"][0].get("delta", {}).get("content") or ""
        if not delta:
            continue
        if ttft is None:
            ttft = time.time() - t0
        full.append(delta)
        if first_clause_t is None:
            buf += delta
            if any(c in buf for c in BOUNDARY) or len(buf) > 30:
                first_clause = buf.strip()
                first_clause_t = time.time() - t0
    total = time.time() - t0

    answer = "".join(full)
    if first_clause_t is None:  # 구두점 없이 짧게 끝난 경우
        first_clause = answer.strip()
        first_clause_t = total

    return {
        "q": q,
        "ttft": ttft,
        "first_clause_s": first_clause_t,
        "llm_total": total,
        "synth_s": _synth_first_audio(first_clause),
        "clause": first_clause,
        "answer": answer,
    }


if __name__ == "__main__":
    mode = "첫 청크" if tts_mod.QWEN_STREAM else "전체 합성"
    print(f"LLM {BASE}  ·  TTS {tts_mod.QWEN_URL}  ·  합성 측정: {mode}")
    print(f"{'TTFT':>6} {'첫절':>6} {'전체':>6} {'합성':>6}  질문 → 첫 절")
    worst = 0.0
    rows, missing = [], 0
    for q in QUESTIONS:
        m = one_round(q)
        rows.append(m)
        if m["synth_s"] is None:
            missing += 1
            synth_txt = "   n/a"
        else:
            worst = max(worst, m["first_clause_s"] + m["synth_s"])
            synth_txt = f"{m['synth_s']:6.2f}"
        print(
            f"{m['ttft']:6.2f} {m['first_clause_s']:6.2f} {m['llm_total']:6.2f} "
            f"{synth_txt}  {m['q']} → {m['clause']!r}"
        )

    if missing:
        # 조용히 0 으로 적으면 예산이 실제보다 좋아 보인다 — 소리 내서 알린다.
        print(f"\n⚠ TTS 서버 응답 없음 {missing}/{len(QUESTIONS)}건 — "
              f"합성 항목을 뺀 수치다. `./reachy.sh check` 로 :8099 를 확인하라")
    if worst == 0.0:
        print("\n합성을 한 번도 못 재서 예산을 산출하지 않는다.")
    else:
        budget = VAD_HANGOVER + STT_WORST + worst
        print(f"\nVAD {VAD_HANGOVER:.2f} + STT {STT_WORST:.2f} + LLM첫절·합성 최악 {worst:.2f}")
        print(f"예상 '발화 종료→첫 오디오' 최악치: {budget:.2f}s  "
              f"(SLO 2.0s {'만족' if budget <= 2.0 else '초과!'})")
    print(f"\n전체 응답 예시: {rows[0]['answer']!r}")
