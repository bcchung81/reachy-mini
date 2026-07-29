"""발화 오디오 → 텍스트. 로컬 STT 서버(:8090, OpenAI 호환)를 호출한다."""

import io
import wave

import numpy as np
import requests

DEFAULT_URL = "http://127.0.0.1:8090/v1/audio/transcriptions"


def transcribe(audio: np.ndarray, rate: int = 16000, url: str = DEFAULT_URL) -> str:
    """float32 mono 배열을 16-bit WAV로 조립해 전사한다. 실패·침묵이면 빈 문자열."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    try:
        r = requests.post(
            url,
            files={"file": ("utt.wav", buf.getvalue(), "audio/wav")},
            data={"language": "ko"},
            timeout=15,
        )
        r.raise_for_status()
        return (r.json().get("text") or "").strip()
    except requests.RequestException:
        return ""
