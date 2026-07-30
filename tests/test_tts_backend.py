import importlib
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import tts as tts_mod


class SpeechStub(BaseHTTPRequestHandler):
    """POST /v1/audio/speech 를 흉내낸다. 받은 본문을 클래스에 남긴다."""

    requests: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SpeechStub.requests.append((self.path, body))
        wav = b"RIFF" + b"\x00" * 40  # 내용은 검사하지 않는다
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.end_headers()
        self.wfile.write(wav)

    def log_message(self, *a):
        pass


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), SpeechStub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def test_기본값은_qwen_이다(monkeypatch):
    # 채택한 소년 음색이 기본이어야 한다 — 환경변수를 따로 주지 않아도.
    monkeypatch.delenv("TTS_BACKEND", raising=False)
    importlib.reload(tts_mod)
    assert tts_mod.BACKEND == "qwen"


def test_say_로_되돌릴_수_있다(monkeypatch):
    monkeypatch.setenv("TTS_BACKEND", "say")
    importlib.reload(tts_mod)
    try:
        assert tts_mod.BACKEND == "say"
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_qwen_백엔드는_지시문과_배속을_실어_보낸다(monkeypatch):
    base = _serve()
    SpeechStub.requests.clear()
    monkeypatch.setenv("TTS_BACKEND", "qwen")
    monkeypatch.setenv("TTS_QWEN_URL", f"{base}/v1/audio/speech")
    monkeypatch.setenv("TTS_QWEN_SPEED", "1.2")
    importlib.reload(tts_mod)
    try:
        played = []
        s = tts_mod.Speaker(play=played.append)
        s.speak("안녕하세요.")
        s.wait_idle(timeout=5)
        assert len(SpeechStub.requests) == 1
        path, body = SpeechStub.requests[0]
        assert path == "/v1/audio/speech"
        assert body["input"] == "안녕하세요."
        assert body["speed"] == 1.2
        assert "남자아이" in body["instructions"]  # 채택한 소년 음색
        assert len(played) == 1  # 받은 오디오를 재생했다
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_qwen_이_죽으면_say_로_떨어진다(monkeypatch, tmp_path):
    # 시연 중 TTS 서버가 죽어도 로봇은 **반드시 말해야 한다.**
    # 음색이 바뀌는 것보다 소리가 안 나는 쪽이 훨씬 나쁘다.
    monkeypatch.setenv("TTS_BACKEND", "qwen")
    monkeypatch.setenv("TTS_QWEN_URL", "http://127.0.0.1:1/v1/audio/speech")  # 죽은 포트
    importlib.reload(tts_mod)
    try:
        out = tmp_path / "log"
        fallback = ["/bin/sh", "-c", f'echo "$0" >> {out}']
        played = []
        s = tts_mod.Speaker(fallback_cmd=fallback, play=played.append)
        s.speak("안녕하세요.")
        s.wait_idle(timeout=5)
        assert played == []  # qwen 오디오는 못 받았지만
        assert out.read_text().strip() == "안녕하세요."  # say 로 발화했다
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)
