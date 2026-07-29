"""로컬 STT 서버 — OpenAI 호환 /v1/audio/transcriptions.

LLM(llama.cpp)과 같은 인터페이스 규약을 쓴다. 나중에 클라우드 Whisper API로 옮길 때
클라이언트가 바꿀 것은 base_url 하나뿐이다.

백엔드는 mlx-whisper(Apple Silicon Metal). Windows·Linux로 배포할 때는
faster-whisper로 교체한다 — transcribe() 한 함수만 바꾸면 된다.

실행:
    .venv/bin/python stt_server.py [--port 8090] [--model mlx-community/whisper-large-v3-turbo]

확인:
    curl -F file=@sample.wav -F language=ko http://127.0.0.1:8090/v1/audio/transcriptions
"""

from __future__ import annotations

import argparse
import cgi
import io
import json
import logging
import os
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

log = logging.getLogger("stt")

MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_LANGUAGE = "ko"


def _decode_wav(raw: bytes) -> np.ndarray:
    """16-bit PCM WAV 바이트 → float32 모노 16kHz numpy 배열."""
    with wave.open(io.BytesIO(raw), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"16-bit PCM만 지원한다 (받은 값: {w.getsampwidth() * 8}-bit)")
        frames = w.readframes(w.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            audio = audio.reshape(-1, w.getnchannels()).mean(axis=1)
        if w.getframerate() != 16000:
            # 선형 보간 리샘플 — 발화 단위(수 초)라 품질 손실이 문제되지 않는다.
            n = int(len(audio) * 16000 / w.getframerate())
            audio = np.interp(np.linspace(0, len(audio), n, endpoint=False),
                              np.arange(len(audio)), audio).astype(np.float32)
    return audio


# 이보다 짧은 오디오는 자동 감지를 쓰지 않고 기본 언어로 간다.
# 실측: 0.3초 '예' 가 영어로 판정돼 'Yay!' 가 나왔다. 짧은 발화에는
# 언어를 판정할 단서가 부족하다. 대화체 문장은 1초를 넘으므로 영향이 없다.
AUTO_MIN_SECONDS = float(os.environ.get("STT_AUTO_MIN_S", "1.0"))


def allowed_languages() -> set[str]:
    """자동 감지 결과로 인정할 언어. 벗어나면 기본 언어로 재전사한다."""
    return {s.strip().lower() for s in os.environ.get("STT_ALLOWED_LANGS", "ko,en").split(",") if s.strip()}


def should_retry(requested: str | None, detected: str, allowed: set[str]) -> bool:
    """자동 감지가 허용 밖 언어를 골랐으면 재전사해야 한다.

    짧은 한국어가 특히 위험하다 — 실측에서 '네'가 베트남어로, '고마워'가
    일본어로 판정되어 각각 'Đề.', 'こまわお。' 라는 쓰레기가 나왔다.
    언어를 명시한 요청(requested is not None)은 재시도하지 않는다.
    """
    return requested is None and detected.lower() not in allowed


def resolve_language(raw: str | None) -> str | None:
    """요청의 language 값을 whisper 인자로 바꾼다.

    None 을 넘기면 whisper 가 자동 감지한다. 예전에는 `or DEFAULT_LANGUAGE` 로
    떨어뜨려서 자동 감지를 **요청할 방법 자체가 없었다** — 그 탓에 영어를 말하면
    한국어로 강제 전사되어 반복 환각이 났다.
    """
    if raw is None:
        return DEFAULT_LANGUAGE
    raw = raw.strip().lower()
    if raw in ("auto", "detect"):
        return None
    return raw or DEFAULT_LANGUAGE


def transcribe(audio: np.ndarray, language: str | None) -> tuple[str, str]:
    """백엔드 경계 — 다른 플랫폼으로 옮길 때 이 함수만 교체한다.

    (전사 텍스트, 실제 사용된 언어) 를 돌려준다. 자동 감지일 때 무엇으로
    판정됐는지 로그에 남겨야 오인식을 추적할 수 있다.
    """
    import mlx_whisper

    def run(lang: str | None) -> tuple[str, str]:
        r = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language=lang)
        return (r.get("text") or "").strip(), (r.get("language") or lang or "?")

    text, detected = run(language)
    if should_retry(language, detected, allowed_languages()):
        log.info("자동 감지가 %r 를 골랐다 — %s 로 재전사", detected, DEFAULT_LANGUAGE)
        text, detected = run(DEFAULT_LANGUAGE)
    return text, detected


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict) -> None:
        # 구분자에 공백을 넣지 않는다 — llama-server 와 같은 형식이라야
        # 헬스체크를 하는 쪽(llamactl 등)이 한 가지 패턴만 알면 된다.
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok", "model": MODEL})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/v1/audio/transcriptions":
            self._send(404, {"error": "not found"})
            return
        try:
            form = cgi.FieldStorage(
                fp=self.rfile, headers=self.headers,
                environ={"REQUEST_METHOD": "POST",
                         "CONTENT_TYPE": self.headers["Content-Type"]},
            )
            if "file" not in form:
                self._send(400, {"error": "file 필드가 없다"})
                return
            language = resolve_language(form.getvalue("language"))
            audio = _decode_wav(form["file"].file.read())

            # 짧은 발화는 자동 감지를 신뢰할 수 없다 — 기본 언어로 간다
            if language is None and len(audio) / 16000 < AUTO_MIN_SECONDS:
                language = DEFAULT_LANGUAGE

            t0 = time.time()
            text, detected = transcribe(audio, language)
            elapsed = time.time() - t0

            secs = len(audio) / 16000
            log.info("전사 %.1fs 오디오 → %.2fs (RTF %.2f) [%s%s]: %s",
                     secs, elapsed, elapsed / secs if secs else 0,
                     detected, "" if language else " 자동", text[:40])
            self._send(200, {"text": text, "language": detected})
        except Exception as exc:  # 서버가 죽지 않도록 요청 단위로 막는다
            log.exception("전사 실패")
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *_args) -> None:
        pass  # 기본 액세스 로그 억제 — 위 log.info로 대체


def main() -> None:
    global MODEL
    ap = argparse.ArgumentParser(description="로컬 STT 서버 (OpenAI 호환)")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    MODEL = args.model

    logging.basicConfig(level=logging.INFO, format="%(asctime)s stt %(levelname)s %(message)s")

    # 첫 요청에서 수 초를 잃지 않도록 모델을 미리 메모리에 올린다.
    log.info("모델 예열: %s", MODEL)
    t0 = time.time()
    transcribe(np.zeros(16000, dtype=np.float32), None)  # 자동 감지 경로까지 예열
    log.info("예열 완료 (%.1fs) — READY http://%s:%d/health", time.time() - t0, args.host, args.port)

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
