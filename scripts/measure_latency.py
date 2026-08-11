"""M0: TTFT / 첫 절 생성 / 첫 절 say 합성을 실측한다. LLM 서버(:8080) 필요.

`say`를 인자 없이 호출하면 재생이 끝날 때까지 블록되므로 합성 지연과 재생 길이가
섞인다. 그래서 `say -o`(파일 출력)로 순수 합성 시간만 따로 잰다 — 이 값이
'첫 오디오까지'의 보수적 상한이다(실제 재생은 합성과 겹쳐 더 빨리 시작한다).
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests

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

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "clause.aiff"
        t1 = time.time()
        subprocess.run(["say", "-v", "Yuna", "-o", str(out), first_clause], check=False)
        synth_s = time.time() - t1

    return {
        "q": q,
        "ttft": ttft,
        "first_clause_s": first_clause_t,
        "llm_total": total,
        "synth_s": synth_s,
        "clause": first_clause,
        "answer": answer,
    }


if __name__ == "__main__":
    print(f"{'TTFT':>6} {'첫절':>6} {'전체':>6} {'합성':>6}  질문 → 첫 절")
    worst = 0.0
    rows = []
    for q in QUESTIONS:
        m = one_round(q)
        first_audio = m["first_clause_s"] + m["synth_s"]
        worst = max(worst, first_audio)
        rows.append(m)
        print(
            f"{m['ttft']:6.2f} {m['first_clause_s']:6.2f} {m['llm_total']:6.2f} "
            f"{m['synth_s']:6.2f}  {m['q']} → {m['clause']!r}"
        )

    budget = VAD_HANGOVER + STT_WORST + worst
    print(f"\nVAD {VAD_HANGOVER:.2f} + STT {STT_WORST:.2f} + LLM첫절·합성 최악 {worst:.2f}")
    print(f"예상 '발화 종료→첫 오디오' 최악치: {budget:.2f}s  "
          f"(SLO 2.0s {'만족' if budget <= 2.0 else '초과!'})")
    print(f"\n전체 응답 예시: {rows[0]['answer']!r}")
