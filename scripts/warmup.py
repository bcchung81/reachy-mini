"""시연 직전 예열 — 첫 질문이 느려지지 않도록 모든 경로를 한 번씩 태운다.

핵심은 LLM 프리픽스 캐시다. llama.cpp 는 **실제 토큰 접두사**로 캐시를 잡으므로,
앱이 보내는 것과 같은 시스템 블록으로 예열해야 한다. 시스템 프롬프트 없이
"안녕"만 보내면 접두사가 달라 앱의 첫 요청이 프리필 비용을 그대로 문다.

실행: .venv/bin/python scripts/warmup.py
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PROMPT = ROOT / "apps/voice_chat/voice_chat/prompt.md"
LLM_URL = "http://127.0.0.1:8080/v1/chat/completions"
STT_URL = "http://127.0.0.1:8090/v1/audio/transcriptions"
VOICE = "Yuna"


def _step(label: str, fn) -> bool:
    t0 = time.time()
    try:
        detail = fn()
    except Exception as exc:
        print(f"   {label} 건너뜀 ({type(exc).__name__})")
        return False
    print(f"   {label} {time.time() - t0:5.2f}s{'  ' + detail if detail else ''}")
    return True


# llama-server 는 슬롯 여러 개로 뜬다(현재 구성 parallel=2). 한 번만 예열하면
# 슬롯 하나만 캐시가 차서, 다른 슬롯으로 간 요청이 0.09s → 0.40s 로 튄다(실측).
# 슬롯 수보다 넉넉히 태워 전부 채운다. 한 번에 0.1s 남짓이라 비용이 싸다.
LLM_WARM_ROUNDS = 3


def _llm_ttft(system: str, user: str) -> float | None:
    t0 = time.time()
    r = requests.post(
        LLM_URL,
        json={
            "model": "local",
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 8,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        stream=True,
        timeout=120,
    )
    r.raise_for_status()
    ttft = None
    for raw in r.iter_lines():
        if raw and raw.startswith(b"data: ") and raw[6:] != b"[DONE]":
            if ttft is None:
                ttft = time.time() - t0
    r.close()
    return ttft


def warm_llm() -> str:
    """앱과 동일한 시스템 블록으로 모든 슬롯의 프리픽스 캐시를 채운다."""
    system = PROMPT.read_text()
    times = [_llm_ttft(system, f"안녕{i}") for i in range(LLM_WARM_ROUNDS)]
    done = [t for t in times if t is not None]
    if not done:
        return ""
    return f"(TTFT {done[0]:.2f}s → {done[-1]:.2f}s, 슬롯 {LLM_WARM_ROUNDS}회)"


def _say_to_wav(text: str, path: Path) -> None:
    subprocess.run(
        ["say", "-v", VOICE, "-o", str(path), "--data-format=LEI16@16000", text],
        check=True,
    )


def warm_tts() -> str:
    """첫 호출은 리소스를 올리느라 느리다. 소리 없이 한 번 태운다.

    Qwen3-TTS 는 **첫 실행에 Metal 커널 JIT 로 8.5초**가 걸린다(실측).
    예열을 빠뜨리면 시연 첫 발화가 그만큼 늦는다.
    """
    if os.environ.get("TTS_BACKEND") == "qwen":
        import json
        import urllib.request

        url = os.environ.get("TTS_QWEN_URL", "http://127.0.0.1:8099/v1/audio/speech")
        payload = json.dumps({"input": "준비되었습니다.", "model": "tts"}).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
        return "(Qwen3-TTS)"

    with tempfile.TemporaryDirectory() as d:
        _say_to_wav("준비되었습니다.", Path(d) / "w.wav")
    return "(say)"


def warm_stt() -> str:
    """무음이 아니라 실제 한국어 음성으로 전사 경로를 태운다."""
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "w.wav"
        _say_to_wav("안녕하세요", wav)
        with wave.open(str(wav), "rb") as w:
            frames, rate = w.readframes(w.getnframes()), w.getframerate()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as o:
            o.setnchannels(1)
            o.setsampwidth(2)
            o.setframerate(rate)
            o.writeframes(frames)
        r = requests.post(
            STT_URL,
            files={"file": ("w.wav", buf.getvalue(), "audio/wav")},
            data={"language": "ko"},
            timeout=120,
        )
        r.raise_for_status()
        return f"({r.json().get('text', '')!r})"


def warm_moves() -> str:
    from reachy_mini.motion.recorded_move import RecordedMoves

    moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
    return f"({len(moves.list_moves())}개)"


if __name__ == "__main__":
    results = [
        _step("LLM  프리픽스 캐시", warm_llm),
        _step("TTS  음성 리소스  ", warm_tts),
        _step("STT  전사 경로    ", warm_stt),
        _step("모션 카탈로그     ", warm_moves),
    ]
    sys.exit(0 if all(results) else 1)
