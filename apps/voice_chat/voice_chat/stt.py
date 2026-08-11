"""발화 오디오 → 텍스트. 로컬 STT 서버(:8090, OpenAI 호환)를 호출한다."""

import io
import os
import wave

import numpy as np
import requests

# 실기에서는 앱이 로봇에서 돌고 추론은 PC 가 맡으므로 **이 주소가 PC 를 가리켜야
# 한다.** 사다리는 환경변수 → 설정파일 → 기본값이다(config.py) — Wireless 에서
# 앱은 systemd 데몬의 자식이라 셸 export 가 닿지 않으므로 파일 단이 필요하다.
#   REACHY_STT_URL=http://<PC>:8090/v1/audio/transcriptions
import config

DEFAULT_URL = config.get(
    "REACHY_STT_URL", "http://127.0.0.1:8090/v1/audio/transcriptions"
)

# `auto` 면 whisper 가 언어를 감지한다 — 영어로 말하면 영어로 알아듣는다.
# 한국어만 쓸 거라면 REACHY_STT_LANG=ko 로 고정하는 편이 짧은 발화에 더 안전하다.
LANGUAGE = os.environ.get("REACHY_STT_LANG", "auto")

# keep-alive 연결 재사용 — 실기 분리 배치에서 발화마다 TCP 핸드셰이크를 아낀다.
# (본 루프와 호출어 확인 스레드가 동시에 부를 수 있다 — Session 의 커넥션 풀은
#  스레드 안전하다.)
_session = requests.Session()


def transcribe(audio: np.ndarray, rate: int = 16000, url: str = DEFAULT_URL) -> str:
    """float32 mono 배열을 16-bit WAV로 조립해 전사한다. 실패·침묵이면 빈 문자열."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    try:
        r = _session.post(
            url,
            files={"file": ("utt.wav", buf.getvalue(), "audio/wav")},
            data={"language": LANGUAGE},
            timeout=15,
        )
        r.raise_for_status()
        return (r.json().get("text") or "").strip()
    except requests.RequestException:
        return ""
