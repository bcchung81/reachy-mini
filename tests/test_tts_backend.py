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
        # 화자 이름으로 음색을 고정한다. VoiceDesign 의 instruct 방식은 요청마다
        # 음색이 달라져서 못 쓴다(문장마다 목소리가 바뀌는 문제를 실제로 겪었다).
        assert body["voice"] == "serena"
        assert "instructions" not in body
        assert len(played) == 1  # 받은 오디오를 재생했다
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def _wav_bytes(seconds: float = 0.05, rate: int = 24000) -> bytes:
    import io
    import wave

    import numpy as np

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.zeros(int(rate * seconds), dtype=np.int16).tobytes())
    return buf.getvalue()


def test_상주_스트림으로_재생한다():
    # afplay 는 발화마다 CoreAudio 를 새로 올려 0.8초를 고정으로 먹는다(실측).
    # 스트림을 한 번만 열고 재사용해야 그 비용이 사라진다.
    player = tts_mod.StreamPlayer()
    try:
        player.play(_wav_bytes())
        player.play(_wav_bytes())
        assert player.opened == 1, "스트림을 매번 새로 열면 안 된다"
    finally:
        player.close()


def test_스트림이_안_열리면_afplay_로_떨어진다(monkeypatch):
    # 오디오 장치가 없거나 sounddevice 가 없을 때도 소리는 나야 한다
    monkeypatch.setattr(tts_mod, "_open_stream", lambda rate: None)
    calls = []
    monkeypatch.setattr(tts_mod, "_afplay", lambda data: calls.append(len(data)))
    player = tts_mod.StreamPlayer()
    player.play(_wav_bytes())
    assert len(calls) == 1


def test_샘플레이트가_바뀌면_스트림을_다시_연다():
    player = tts_mod.StreamPlayer()
    try:
        player.play(_wav_bytes(rate=24000))
        player.play(_wav_bytes(rate=16000))
        assert player.opened == 2
    finally:
        player.close()


def test_seed_를_주면_요청에_실린다(monkeypatch):
    # 음높이가 튀는 문장은 시드를 골라 고정한다. 같은 시드 + 같은 문장은
    # 비트 단위로 동일한 오디오를 낸다(PCM 해시로 실측 확인).
    base = _serve()
    SpeechStub.requests.clear()
    monkeypatch.setenv("TTS_BACKEND", "qwen")
    monkeypatch.setenv("TTS_QWEN_URL", f"{base}/v1/audio/speech")
    importlib.reload(tts_mod)
    try:
        s = tts_mod.Speaker(play=lambda b: None)
        s.speak("시드 있는 문장.", seed=42)
        s.speak("시드 없는 문장.")
        s.wait_idle(timeout=5)
        bodies = [b for _, b in SpeechStub.requests]
        assert bodies[0]["seed"] == 42
        assert "seed" not in bodies[1]  # 안 주면 보내지 않는다(서버 기본 = 결정적)
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_대본의_시드_보정이_적용된다(monkeypatch):
    import selfintro

    base = _serve()
    SpeechStub.requests.clear()
    monkeypatch.setenv("TTS_BACKEND", "qwen")
    monkeypatch.setenv("TTS_QWEN_URL", f"{base}/v1/audio/speech")
    importlib.reload(tts_mod)
    try:
        s = tts_mod.Speaker(play=lambda b: None)
        for i, line in enumerate(selfintro.SCRIPT, 1):
            s.speak(line, seed=selfintro.SEEDS.get(i))
        s.wait_idle(timeout=10)
        assert len(SpeechStub.requests) == len(selfintro.SCRIPT)
        for i, (_, body) in enumerate(SpeechStub.requests, 1):
            if i in selfintro.SEEDS:
                assert body["seed"] == selfintro.SEEDS[i], f"{i}번 문장 시드 누락"
            else:
                assert "seed" not in body
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_qwen_은_절을_합치지_않는다(monkeypatch):
    # 합쳐 보내면 합성이 선형으로 길어진다(420자 = 32.9초, 실측). 타임아웃에 걸려
    # 연결이 끊기면 서버가 죽고, 그 뒤 모든 발화가 say 로 떨어진다 — 실제로 겪었다.
    # 절마다 따로 보내면 다음 절 합성이 앞 절 재생 시간 안에 끝나 끊기지 않는다.
    base = _serve()
    SpeechStub.requests.clear()
    monkeypatch.setenv("TTS_BACKEND", "qwen")
    monkeypatch.setenv("TTS_QWEN_URL", f"{base}/v1/audio/speech")
    importlib.reload(tts_mod)
    try:
        s = tts_mod.Speaker(play=lambda b: None)
        s.speak_many(["첫째 문장입니다.", "둘째 문장입니다.", "셋째 문장입니다."])
        s.wait_idle(timeout=5)
        assert len(SpeechStub.requests) == 3  # 하나로 뭉치지 않았다
        assert [b["input"] for _, b in SpeechStub.requests] == [
            "첫째 문장입니다.", "둘째 문장입니다.", "셋째 문장입니다."
        ]
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_say_는_같은_음성끼리_합친다(monkeypatch, tmp_path):
    # say 는 프로세스 기동이 고정비라 합치는 편이 낫다(문장 사이 공백 제거)
    monkeypatch.setenv("TTS_BACKEND", "say")
    importlib.reload(tts_mod)
    try:
        out = tmp_path / "log"
        fake = ["/bin/sh", "-c", f'echo "$0" >> {out}']
        s = tts_mod.Speaker(cmd=fake)
        s.speak_many(["첫째.", "둘째.", "셋째."])
        s.wait_idle(timeout=5)
        assert out.read_text().splitlines() == ["첫째. 둘째. 셋째."]
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
