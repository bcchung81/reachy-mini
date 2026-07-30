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


def test_기본값은_say_다(monkeypatch):
    # 시연 안전장치 — 환경변수를 안 주면 지금까지와 완전히 같아야 한다
    monkeypatch.delenv("TTS_BACKEND", raising=False)
    importlib.reload(tts_mod)
    assert tts_mod.BACKEND == "say"


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


def test_qwen_이_죽으면_say_로_떨어진다(monkeypatch):
    # 시연 중 TTS 서버가 죽어도 로봇은 계속 말해야 한다
    monkeypatch.setenv("TTS_BACKEND", "qwen")
    monkeypatch.setenv("TTS_QWEN_URL", "http://127.0.0.1:1/v1/audio/speech")  # 죽은 포트
    importlib.reload(tts_mod)
    try:
        spoken = []
        s = tts_mod.Speaker(cmd=["/usr/bin/true"], play=lambda b: spoken.append(b))
        s.speak("안녕하세요.")
        s.wait_idle(timeout=5)
        assert spoken == []  # 오디오를 못 받았고
        assert not s.speaking  # 큐는 정상적으로 비워졌다(멈추지 않는다)
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)
