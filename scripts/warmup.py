"""시연 직전 예열 — 첫 질문이 느려지지 않도록 모든 경로를 한 번씩 태운다.

핵심은 LLM 프리픽스 캐시다. llama.cpp 는 **실제 토큰 접두사**로 캐시를 잡으므로,
앱이 보내는 것과 같은 시스템 블록으로 예열해야 한다. 시스템 프롬프트 없이
"안녕"만 보내면 접두사가 달라 앱의 첫 요청이 프리필 비용을 그대로 문다.

실행: ./reachy.sh warmup   (demo 가 자동으로 태우지만 단독 실행도 된다)
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps/voice_chat/voice_chat"
sys.path.insert(0, str(APP))


def _prompt() -> Path:
    """앱이 실제로 쓸 프롬프트 파일. **session 과 같은 것을 골라야 한다.**

    여기서 prompt.md 로 고정해 두면 해설 모드(REACHY_PROMPT)일 때 예열이
    엉뚱한 접두사를 데워 **캐시가 헛돈다.** 실측(2026-09-09): 2.5k 토큰 프롬프트가
    예열되면 0.089s, 안 되면 2.512s 다. 조용히 느려지는 종류라 반드시 맞춘다.
    """
    import session

    return session.prompt_path()
# **앱과 같은 환경변수를 읽는다**(CLAUDE.md: "주소는 전부 환경변수다").
# 하드코딩하면 실기 분리 배치(앱은 로봇, 추론은 PC)에서 예열이 엉뚱한 호스트를
# 조용히 데우고 — _step 이 실패를 '건너뜀'으로 삼킨다 — 첫 발화가 콜드스타트를
# 그대로 문다(리뷰 확인). 예열의 존재 이유가 사라지는 실패다.
LLM_URL = os.environ.get("REACHY_LLM_URL", "http://127.0.0.1:8080").rstrip("/") + "/v1/chat/completions"
STT_URL = os.environ.get("REACHY_STT_URL", "http://127.0.0.1:8090/v1/audio/transcriptions")
# 언어도 앱과 같게 — 다르면 다른 디코드 경로를 데운다.
STT_LANG = os.environ.get("REACHY_STT_LANG", "auto")
# TTS_BACKEND=say 폴백 경로에서만 쓰는 macOS 음성 이름.
VOICE = os.environ.get("REACHY_VOICE", "Yuna")


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
    system = _prompt().read_text()
    times = [_llm_ttft(system, f"안녕{i}") for i in range(LLM_WARM_ROUNDS)]
    done = [t for t in times if t is not None]
    if not done:
        return ""
    return f"(TTFT {done[0]:.2f}s → {done[-1]:.2f}s, 슬롯 {LLM_WARM_ROUNDS}회)"


def _tts_mod():
    """앱의 tts 모듈. 요청 본문을 여기서 다시 짜면 tts.py 와 갈라진다."""
    sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))
    import tts as tts_mod

    return tts_mod


def warm_tts() -> str:
    """첫 호출은 리소스를 올리느라 느리다. 소리 없이 한 번 태운다.

    Qwen3-TTS 는 **첫 실행에 Metal 커널 JIT 로 8.5초**가 걸린다(실측).
    예열을 빠뜨리면 시연 첫 발화가 그만큼 늦는다. **Metal JIT 캐시는 모델·화자별**
    이라 조건이 어긋나면 예열이 헛돈다(0.6B 로 예열한 캐시가 1.7B 에는 안 먹혔다,
    실측 10.0초) — 그래서 앱이 쓰는 함수를 그대로 부른다.
    """
    if os.environ.get("TTS_BACKEND", "qwen") != "say":
        tts_mod = _tts_mod()
        if tts_mod._qwen_synth("준비되었습니다.") is None:
            raise RuntimeError(f"TTS 서버 응답 없음: {tts_mod.QWEN_URL}")
        return "(Qwen3-TTS)"

    # TTS_BACKEND=say 로 명시했을 때만 온다 — 그 경로는 macOS 전용이다.
    cmd = shutil.which("say")
    if cmd is None:
        raise RuntimeError("TTS_BACKEND=say 인데 `say` 가 없다(macOS 전용)")
    subprocess.run([cmd, "-v", VOICE, "-o", "/dev/null", "준비"], check=True)
    return "(say)"


def _probe_wav() -> bytes:
    """STT 예열용 16 kHz mono WAV.

    **플랫폼 전용 합성기에 의존하지 않는다.** 예전에는 macOS `say -o` 로 만들어
    리눅스 PC 에서는 예열이 통째로 건너뛰어졌다. 지금은 우리 TTS 서버(앱이 쓰는
    바로 그 경로)로 만들고, 그마저 없으면 톤으로 대신한다 — 무음은 쓰지 않는다
    (Whisper 가 무음에서 환각을 뱉는다, `voice_loop._WHISPER_FILLER` 참조).
    """
    try:
        tts_mod = _tts_mod()
        pcm = tts_mod._qwen_synth("안녕하세요")
        if pcm:
            return pcm  # 서버는 wav 를 준다
    except Exception:  # noqa: BLE001
        pass
    # 폴백: 440 Hz 톤 1초. 전사 내용은 의미 없고 **디코드 경로를 태우는 것**이 목적이다.
    import numpy as np

    t = np.arange(16000) / 16000
    pcm16 = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as o:
        o.setnchannels(1)
        o.setsampwidth(2)
        o.setframerate(16000)
        o.writeframes(pcm16.tobytes())
    return buf.getvalue()


def warm_stt() -> str:
    """무음이 아니라 실제 음성으로 전사 경로를 태운다."""
    r = requests.post(
        STT_URL,
        files={"file": ("w.wav", _probe_wav(), "audio/wav")},
        data={"language": STT_LANG},
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
