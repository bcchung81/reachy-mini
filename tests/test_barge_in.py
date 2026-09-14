"""끼어들기 — 말을 끊는 쪽(Speaker.stop)과 듣는 쪽(voice_loop 게이팅)."""

import importlib
import json
import pathlib
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import tts as tts_mod  # noqa: E402


class SlowStream(BaseHTTPRequestHandler):
    """오래 이어지는 PCM 스트림 — 끊지 않으면 6초짜리다."""

    chunks = 60
    delay = 0.1

    def do_POST(self):
        json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for _ in range(SlowStream.chunks):
                payload = b"\x00\x01" * 512
                self.wfile.write(b"%x\r\n" % len(payload) + payload + b"\r\n")
                self.wfile.flush()
                time.sleep(SlowStream.delay)
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass  # 클라이언트가 끊었다 — 정상

    def log_message(self, *a):
        pass


@pytest.fixture
def stream_url(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), SlowStream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("TTS_BACKEND", "qwen")
    monkeypatch.setenv("TTS_QWEN_URL", f"http://127.0.0.1:{srv.server_port}/v1/audio/speech")
    importlib.reload(tts_mod)
    yield
    monkeypatch.delenv("TTS_BACKEND")
    importlib.reload(tts_mod)


def test_stop_은_재생_중인_발화를_끊는다(stream_url):
    # 끊지 않으면 60청크가 다 온다. 한 청크(0.1초) 안에 빠져나와야 한다.
    got = []
    s = tts_mod.Speaker(play_pcm=lambda chunks, rate: [got.append(c) for c in chunks])
    s.speak("아주 긴 문장입니다.")
    time.sleep(0.5)
    n_before = len(got)
    s.stop()
    time.sleep(0.5)
    assert n_before < SlowStream.chunks, "테스트 전제가 깨졌다 — 이미 다 받았다"
    assert len(got) - n_before <= 2, f"stop 후에도 청크가 계속 왔다 (+{len(got) - n_before})"


def test_stop_은_대기중인_절을_버린다(stream_url):
    s = tts_mod.Speaker(play_pcm=lambda chunks, rate: list(chunks))
    for i in range(5):
        s.speak(f"{i}번째 절입니다.")
    time.sleep(0.3)
    s.stop()
    s.wait_idle(timeout=5)
    assert not s.speaking, "끊었는데도 speaking 이 남아 있다"


def test_stop_다음_발화는_정상적으로_나온다(stream_url):
    # 취소 플래그가 남아 있으면 그 다음 답변이 통째로 묵음이 된다.
    got = []
    s = tts_mod.Speaker(play_pcm=lambda chunks, rate: [got.append(c) for c in chunks])
    s.speak("끊길 문장.")
    time.sleep(0.3)
    s.stop()
    time.sleep(0.3)
    got.clear()
    s.speak("다음 문장.")
    time.sleep(0.6)
    assert got, "끼어들기 뒤의 발화가 나오지 않았다"


def test_abort_는_스트림을_되살린다():
    # abort 후 다시 write 가 되어야 다음 발화가 난다.
    player = tts_mod.StreamPlayer()
    try:
        pcm = (np.zeros(2400, dtype=np.int16)).tobytes()
        player.play_pcm_stream(iter([pcm]), 24000)
        player.abort()
        player.play_pcm_stream(iter([pcm]), 24000)   # 예외 없이 이어져야 한다
        assert player.opened <= 2
    finally:
        player.close()


# ── 듣는 쪽 ────────────────────────────────────────────────────
def _frames(rms_values, n_each=1, rate=16000, chunk_s=0.03):
    """지정한 RMS 를 갖는 30ms 프레임들을 만든다."""
    out = []
    for v in rms_values:
        for _ in range(n_each):
            out.append(np.full(int(rate * chunk_s), v, dtype=np.float32))
    return out


def _run_loop(monkeypatch, frames, barge_in, speaking_frames, gate=None):
    """voice_loop 을 가짜 마이크·가짜 Speaker 로 한 바퀴 돌린다.

    `gate` 는 감독의 마이크 게이트(`mic_open`) 흉내 — None 이면 1대 모드다.
    돌아온 Speaker 의 `stt_calls` 에 STT 로 넘어간 발화 길이가 쌓인다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1" if barge_in else "0")
    import voice_loop as vl

    importlib.reload(vl)

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        def __init__(self):
            self.stopped = 0
            self._left = speaking_frames

        @property
        def speaking(self):
            return self._left > 0

        def tick(self):
            self._left -= 1

        def stop(self):
            self.stopped += 1
            self._left = 0

        def output_level(self, window_s=0.35):
            # 로봇이 내는 소리 — 기본은 조용하다고 본다(에코 예측 0).
            return getattr(self, "out_level", 0.0)

    spk = FakeSpeaker()
    spk.stt_calls = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: (spk.stt_calls.append(len(utt)), "")[1])
    # 프레임마다 speaking 을 한 칸씩 소모한다
    orig_rms = vl._rms
    monkeypatch.setattr(vl, "_rms", lambda f: (spk.tick(), orig_rms(f))[1])
    vl.voice_loop(None, spk, None, lambda *a: None, mic_open=gate)
    return spk


def test_끼어들기가_꺼져_있으면_말하는_중에는_듣지_않는다(monkeypatch):
    loud = _frames([0.05], n_each=20)   # 충분히 크고 충분히 길다
    spk = _run_loop(monkeypatch, loud, barge_in=False, speaking_frames=20)
    assert spk.stopped == 0


def test_끼어들기가_켜지면_연속으로_큰_소리에만_끊는다(monkeypatch):
    loud = _frames([0.05], n_each=20)
    spk = _run_loop(monkeypatch, loud, barge_in=True, speaking_frames=20)
    assert spk.stopped == 1


def test_짧은_충격음으로는_끊지_않는다(monkeypatch):
    # 3프레임(90ms)만 크고 나머지는 조용 — 기침·문소리
    frames = _frames([0.05], n_each=3) + _frames([0.001], n_each=20)
    spk = _run_loop(monkeypatch, frames, barge_in=True, speaking_frames=25)
    assert spk.stopped == 0


# ── AEC 설정 ───────────────────────────────────────────────────
def test_aec_는_기본으로_꺼져_있다(monkeypatch):
    monkeypatch.delenv("REACHY_AEC", raising=False)
    import aec

    importlib.reload(aec)
    assert aec.ENABLED is False


def test_aec_를_켜면_dsp_가_프로브를_이름으로_찾는다(monkeypatch):
    monkeypatch.setenv("REACHY_AEC", "1")
    import aec

    importlib.reload(aec)
    d = aec.dsp_description()
    assert aec.ENABLED
    assert f"probe={aec.PROBE_NAME}" in d
    assert "echo-cancel=true" in d
    # STT 품질을 깎는 둘은 기본 꺼짐이어야 한다(§9 — 음성이 깎였던 전례)
    assert "noise-suppression=false" in d
    assert "gain-control=false" in d
    monkeypatch.delenv("REACHY_AEC")
    importlib.reload(aec)


def test_aec_를_켜면_재생기에_에코_프로브가_붙는다(monkeypatch):
    # 재생 자체는 검증된 PortAudio 경로 그대로 두고, 같은 PCM 을 프로브로 한 벌 더 보낸다.
    # (재생을 GStreamer 로 옮겼더니 TTS 청크 간격 때문에 소리가 끊겼다 — 실측)
    monkeypatch.setenv("REACHY_AEC", "1")
    import aec

    importlib.reload(aec)
    importlib.reload(tts_mod)
    try:
        s = tts_mod.Speaker(play=lambda b: None)
        assert type(s._player).__name__ == "StreamPlayer", "재생기는 그대로여야 한다"
        assert s._player.tap is not None, "에코 프로브가 붙지 않았다"
        assert type(s._player.tap).__name__ == "EchoProbeTap"
        s._player.close()
    finally:
        monkeypatch.delenv("REACHY_AEC")
        importlib.reload(aec)
        importlib.reload(tts_mod)


def test_aec_가_꺼져_있으면_프로브를_만들지_않는다(monkeypatch):
    monkeypatch.delenv("REACHY_AEC", raising=False)
    import aec

    importlib.reload(aec)
    importlib.reload(tts_mod)
    s = tts_mod.Speaker(play=lambda b: None)
    assert s._player.tap is None
    s._player.close()


def test_재생하면_프로브에도_같은_pcm_이_간다():
    # 프로브가 far-end 를 못 보면 AEC 가 지울 대상을 모른다.
    pushed = []

    class FakeTap:
        def push(self, pcm, rate):
            pushed.append((len(pcm), rate))

        def close(self):
            pass

    player = tts_mod.StreamPlayer()
    player.tap = FakeTap()
    try:
        pcm = np.zeros(2400, dtype=np.int16).tobytes()
        player.play_pcm_stream(iter([pcm]), 24000)
        assert pushed and pushed[0][1] == 24000
    finally:
        player.close()


def test_끊은_뒤_발화_앞부분을_잃지_않는다(monkeypatch):
    """끼어든 말에 대답하는 모드(REACHY_BARGE_IN_ANSWER=1)에서는 어두를 살려야 한다.

    판정에 쓴 프레임을 버리면 STT 가 앞이 잘린 오디오를 받아 못 알아듣는다.
    """
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_ANSWER", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_WAKE", "")  # 에너지 경로만 본다
    import voice_loop as vl

    importlib.reload(vl)

    speech = _frames([0.05], n_each=25)          # 750ms 발화 (판정 5 + 계속 20)
    tail = _frames([0.0005], n_each=30)          # 침묵 → hangover 로 발화 종료
    frames = speech + tail

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        def __init__(self):
            self._left = 25   # 발화 구간 내내 말하는 중
            self.stopped = 0

        @property
        def speaking(self):
            return self._left > 0

        def tick(self):
            self._left -= 1

        def stop(self):
            self.stopped += 1
            self._left = 0

        def output_level(self, window_s=0.35):
            # 로봇이 내는 소리 — 기본은 조용하다고 본다(에코 예측 0).
            return getattr(self, "out_level", 0.0)

    spk = FakeSpeaker()
    got = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: got.append(utt) or "")
    orig = vl._rms
    monkeypatch.setattr(vl, "_rms", lambda f: (spk.tick(), orig(f))[1])
    vl.voice_loop(None, spk, None, lambda *a: None)

    assert spk.stopped == 1
    assert got, "끼어든 발화가 STT 로 넘어가지 않았다"
    # 판정에 쓴 5프레임이 포함돼야 한다 — 20프레임(0.6초)보다 길어야 통과
    assert len(got[0]) > 20 * 480, f"발화 앞부분이 잘렸다 ({len(got[0])} 샘플)"


# ── 자기 목소리 방어선 ──────────────────────────────────────────
def test_방금_한_말이_전사되면_무시한다(monkeypatch):
    """AEC 가 다 못 지운 에코를 사용자 발화로 오인하면 스스로에게 대답한다.

    실측 로그: 자기소개 대본을 통째로 받아 적고 대본을 다시 시작했다.
    에코는 재생 꼬리에만 있으므로 **방금 소리를 냈다는 조건**이 함께 성립해야
    한다 — 여기서는 출력 시각을 찍어 그 상황을 만든다(say 폴백은 출력 기록이
    없어 이 방어선을 못 탄다 — half-duplex 게이팅이 덮는 경로다).
    """
    monkeypatch.setenv("TTS_BACKEND", "say")
    importlib.reload(tts_mod)
    try:
        s = tts_mod.Speaker(cmd=["/usr/bin/true"])
        s.speak("음성을 글자로 바꾸는 건 Whisper Large V3 Turbo 예요.")
        s.speak("저는 인터넷에 연결되어 있지 않아요.")
        s._player.last_output_ts = time.time()  # 방금 재생이 끝난 상황
        # 실제 로그에서 나온 오전사들
        assert s.said_recently("음성을 글자로바꾸는 건 위스퍼를 라지 V3 철보예요")
        assert s.said_recently("저는 인터넷에 연결되어 있지 않아요")
        # 진짜 사용자 발화는 통과해야 한다
        assert not s.said_recently("오늘 날씨 어때")
        assert not s.said_recently("대본")
        assert not s.said_recently("음성 인식은 어떻게 해?")
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_재생_꼬리가_지나면_로봇_말을_인용해도_받는다(monkeypatch):
    """검사를 시간 제한 없이 걸면 사용자가 로봇 말을 **인용**한 질문까지 버린다
    (리뷰 확인: "네가 방금 위스퍼라고 했잖아" 류가 90초 동안 난청이 됐다).
    에코가 물리적으로 존재할 수 없는 시점이면 통과시킨다.
    """
    monkeypatch.setenv("TTS_BACKEND", "say")
    importlib.reload(tts_mod)
    try:
        s = tts_mod.Speaker(cmd=["/usr/bin/true"])
        s.speak("음성을 글자로 바꾸는 건 Whisper Large V3 Turbo 예요.")
        s._player.last_output_ts = time.time() - 10.0  # 재생이 끝난 지 오래
        assert not s.said_recently("음성을 글자로 바꾸는 건 위스퍼라고 했잖아 그게 뭐야")
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_말한_적_없으면_통과시킨다(monkeypatch):
    monkeypatch.setenv("TTS_BACKEND", "say")
    importlib.reload(tts_mod)
    try:
        s = tts_mod.Speaker(cmd=["/usr/bin/true"])
        assert not s.said_recently("아무 말이나 해보세요")
    finally:
        monkeypatch.delenv("TTS_BACKEND")
        importlib.reload(tts_mod)


def test_유예는_연장되지_않는다(monkeypatch):
    """유예를 발화 중이라고 계속 밀면 게이팅이 영영 돌아오지 않는다.

    실측: 잔여 에코가 VAD 를 계속 살려 둬 로봇이 자기 대본을 통째로 받아 적었다.
    """
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    import voice_loop as vl

    importlib.reload(vl)
    src = pathlib.Path(vl.__file__).read_text()
    assert "barge_until = now + BARGE_IN_GRACE_S" in src
    assert src.count("barge_until = now + BARGE_IN_GRACE_S") == 1, "유예를 두 곳에서 밀고 있다"
    assert vl.BARGE_IN_GRACE_S <= 1.5, "유예가 길면 자기 목소리를 들을 창이 넓어진다"


def test_기본은_끊기만_하고_그_발화에는_대답하지_않는다(monkeypatch):
    """끊는 순간의 전사는 잔여 에코가 섞여 엉뚱한 답을 부른다.

    실측: "Bye, man." → "안녕히 가세요", "잠깐만." → "네, 잠시 기다리고 있을게요".
    기본값은 **끊고 조용히 다음 질문을 기다리는 것**이다.
    """
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.delenv("REACHY_BARGE_IN_ANSWER", raising=False)
    import voice_loop as vl

    importlib.reload(vl)

    frames = _frames([0.05], n_each=25) + _frames([0.0005], n_each=30)

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        def __init__(self):
            self._left = 25
            self.stopped = 0

        @property
        def speaking(self):
            return self._left > 0

        def tick(self):
            self._left -= 1

        def stop(self):
            self.stopped += 1
            self._left = 0

        def output_level(self, window_s=0.35):
            # 로봇이 내는 소리 — 기본은 조용하다고 본다(에코 예측 0).
            return getattr(self, "out_level", 0.0)

        def said_recently(self, text):
            return False

    spk = FakeSpeaker()
    answered = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: "무언가 말했다")
    orig = vl._rms
    monkeypatch.setattr(vl, "_rms", lambda f: (spk.tick(), orig(f))[1])
    vl.voice_loop(None, spk, None, lambda *a: answered.append(a))

    assert spk.stopped == 1, "끼어들기가 걸리지 않았다"
    assert answered == [], "끊은 발화에 대답했다 — 기본값은 대답하지 않는 것이다"


def test_음절_사이_끊김이_있어도_끼어들기가_걸린다(monkeypatch):
    """사람 말은 음절 사이에서 에너지가 떨어진다.

    '연속 N프레임' 으로 재면 한 프레임만 내려가도 카운터가 0이 돼서, 실측 로그에서
    첫 끼어들기만 우연히 통과하고 그 뒤로는 한 번도 성립하지 않았다.
    """
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    import voice_loop as vl

    importlib.reload(vl)

    # 크게-작게를 오가는 말소리 (연속 5프레임은 절대 못 만든다)
    pattern = []
    for _ in range(10):
        pattern += _frames([0.05], n_each=3) + _frames([0.008], n_each=1)
    frames = pattern + _frames([0.0005], n_each=30)

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        def __init__(self):
            self._left = len(pattern)
            self.stopped = 0

        @property
        def speaking(self):
            return self._left > 0

        def tick(self):
            self._left -= 1

        def stop(self):
            self.stopped += 1
            self._left = 0

        def output_level(self, window_s=0.35):
            # 로봇이 내는 소리 — 기본은 조용하다고 본다(에코 예측 0).
            return getattr(self, "out_level", 0.0)

        def said_recently(self, text):
            return False

    spk = FakeSpeaker()
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: "")
    orig = vl._rms
    monkeypatch.setattr(vl, "_rms", lambda f: (spk.tick(), orig(f))[1])
    vl.voice_loop(None, spk, None, lambda *a: None)

    assert spk.stopped == 1, "음절 사이 끊김 때문에 끼어들기가 안 걸렸다"


# ── 적응 임계 ───────────────────────────────────────────────────
def test_적응_임계는_에코_바닥의_배수로_잡힌다(monkeypatch):
    """고정 임계로는 못 버틴다 — 실측에서 사용자 목소리 0.029 vs 임계 0.020,
    여유가 1.5배뿐이라 거리·음량이 조금만 달라져도 걸렸다 안 걸렸다 했다."""
    monkeypatch.delenv("REACHY_BARGE_IN_RMS", raising=False)
    import voice_loop as vl

    importlib.reload(vl)

    echo = vl.EchoFloor()
    assert echo.threshold() == vl.BARGE_IN_RMS, "표본이 없으면 하한을 쓴다"

    for _ in range(60):  # 잔여 에코 바닥 0.010 인 방
        echo.observe(0.010)
    assert abs(echo.floor() - 0.010) < 1e-6
    assert abs(echo.threshold() - 0.020) < 1e-6, "바닥 x 2.0"

    # 실측된 사용자 목소리(0.029)는 넉넉히 넘는다
    assert 0.029 >= echo.threshold()

    # 조용한 방이면 임계가 하한까지 내려간다 — 작게 말해도 걸린다
    quiet = vl.EchoFloor()
    for _ in range(60):
        quiet.observe(0.003)
    assert abs(quiet.threshold() - vl.BARGE_IN_RMS) < 1e-6


def test_잠깐_끼어든_소리는_바닥_추정을_흔들지_않는다():
    """중앙값을 쓰는 이유 — 사람이 잠깐 말해도 임계가 따라 올라가면 안 된다."""
    import voice_loop as vl

    importlib.reload(vl)
    echo = vl.EchoFloor()
    for _ in range(80):
        echo.observe(0.010)
    before = echo.threshold()
    for _ in range(15):  # 0.45초쯤 크게 말한 구간
        echo.observe(0.045)
    assert abs(echo.threshold() - before) < 0.002, "짧은 발화가 바닥을 밀어 올렸다"


def test_에코_바닥이_하한보다_높아도_학습된다():
    """'임계 아래 프레임만 모으기'는 닭-달걀이다 — 바닥이 하한보다 높으면
    표본이 하나도 안 쌓여 임계가 영영 하한에 머문다(실제로 그렇게 짰다가 잡았다)."""
    import voice_loop as vl

    importlib.reload(vl)
    echo = vl.EchoFloor()
    for _ in range(60):
        echo.observe(0.016)  # 하한(0.014)보다 시끄러운 방
    assert echo.threshold() > vl.BARGE_IN_RMS, "바닥을 학습하지 못했다"
    assert abs(echo.threshold() - 0.032) < 1e-6


# ── double-talk: 로봇의 큰 음절 vs 사람 목소리 ──────────────────
def test_로봇의_큰_음절에는_안_걸리고_사람_목소리에는_걸린다(monkeypatch):
    """실측 로그의 숫자를 그대로 재현한다.

    로봇 말은 조용한 구간 0.003 / 큰 음절 0.025 로 요동치고, 사람 목소리는 0.028 이다.
    에너지만 보면 둘이 겹쳐서 — 큰 음절에 헛트리거되거나 사람을 놓친다.
    지금은 '그때 스피커로 나간 세기'로 예측한 에코와 비교해 가른다.
    """
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    import voice_loop as vl

    importlib.reload(vl)

    # 결합계수 0.05 인 방: 출력 0.5 → 마이크에 0.025 로 되돌아온다
    coupling = vl.EchoCoupling()
    for _ in range(40):
        coupling.observe(mic=0.025, out=0.50)   # 로봇 큰 음절 구간
        coupling.observe(mic=0.003, out=0.06)   # 조용한 구간
    assert 0.04 < coupling.ratio() < 0.06, f"결합계수 추정 실패: {coupling.ratio()}"

    floor = vl.EchoFloor()
    for _ in range(60):
        floor.observe(0.006)   # p50 실측치

    def hot(mic, out):
        th = max(floor.threshold(), coupling.predict(out) * vl.BARGE_IN_ECHO_MARGIN)
        return mic >= th

    # 로봇이 큰 음절을 내는 순간의 에코 — 걸리면 안 된다(예전엔 걸렸다)
    assert not hot(mic=0.025, out=0.50)
    # 같은 순간에 사람이 말하면 — 에코 예측(0.025x1.8=0.045)을 넘어야 한다
    assert hot(mic=0.050, out=0.50)
    # 로봇이 조용한 틈(출력 0.06)에 사람이 말하면 — 바로 걸린다
    assert hot(mic=0.028, out=0.06)
    assert hot(mic=0.020, out=0.02), "말 사이 틈에서는 작게 말해도 걸려야 한다"


def test_결합계수를_모르면_바닥_임계로만_판정한다(monkeypatch):
    """표본이 모이기 전(대화 시작 직후)에도 끼어들기는 돼야 한다."""
    import voice_loop as vl

    importlib.reload(vl)
    coupling = vl.EchoCoupling()
    assert coupling.ratio() == 0.0
    assert coupling.predict(0.5) == 0.0, "모르면 0 — 바닥 임계가 그대로 쓰인다"


def test_출력_레벨은_말_사이_틈에서_내려간다():
    """최대값으로 재면 큰 음절이 창에 남아 틈에서도 값이 높게 유지된다.

    그러면 사람이 끼어드는 바로 그 순간(틈)에 예측 에코가 커져 임계가 올라가고,
    아무것도 안 걸린다 — 실측으로 당한 증상이다.
    """
    import time

    import numpy as np

    player = tts_mod.StreamPlayer()
    loud = (np.sin(np.arange(4800) * 0.1) * 8000).astype(np.int16).tobytes()
    quiet = np.zeros(4800, dtype=np.int16).tobytes()

    player._note_output(loud)
    time.sleep(0.1)
    assert player.output_level() > 0.05, "큰 음절이 안 잡힌다"

    player._note_output(quiet)
    time.sleep(0.25)
    assert player.output_level() < 0.01, "틈에서 출력 레벨이 안 내려간다"
    player.close()


def test_실패해도_진단이_남는다(monkeypatch):
    """계측을 성공 경로에만 붙였다가, '3~4번 말했는데 무반응' 로그에 단서가
    한 줄도 없었다. 안 걸릴 때도 임계와 그 근거가 남아야 한다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_TRACE", "0.001")  # 즉시 찍히게
    import voice_loop as vl

    importlib.reload(vl)

    frames = _frames([0.004], n_each=40)  # 임계를 못 넘는 작은 소리만

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        speaking = True
        out_level = 0.1

        def stop(self):
            pass

        def output_level(self, window_s=0.35):
            return self.out_level

        def said_recently(self, text):
            return False

    printed = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: "")
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))
    vl.voice_loop(None, FakeSpeaker(), None, lambda *a: None)

    trace = [line for line in printed if "[듣는 중]" in line]
    assert trace, "안 걸리는 동안 진단이 하나도 안 남았다"
    assert "임계" in trace[0] and "결합" in trace[0]


def test_마이크_이득이_파이프라인에_들어간다(monkeypatch):
    """사용자 목소리가 마이크에 0.020 으로만 잡히면 VAD 임계(0.010)와 여유가 없다.
    이득으로 절대 임계와의 거리를 벌 수 있어야 한다."""
    monkeypatch.setenv("REACHY_MIC_GAIN", "2.5")
    monkeypatch.delenv("REACHY_AEC", raising=False)
    import audio_in

    importlib.reload(audio_in)
    built = {}

    class FakeGst:
        class State:
            PLAYING = "playing"
            NULL = "null"

        SECOND = 10**9

        @staticmethod
        def init(x):
            pass

        @staticmethod
        def parse_launch(desc):
            built["desc"] = desc
            raise RuntimeError("여기서는 실제로 세우지 않는다")

    monkeypatch.setattr(audio_in, "np", audio_in.np)
    mic = audio_in.MicCapture.__new__(audio_in.MicCapture)
    mic._Gst = FakeGst
    mic._start(  # 문자열만 확인한다
        "autoaudiosrc ! audioconvert ! audioresample ! volume volume=2.5 ! "
        "audio/x-raw,format=F32LE,channels=1,rate=16000"
    )
    assert "volume volume=2.5" in built["desc"]


# ── respond() 는 마이크 루프를 막으면 안 된다 ────────────────────
def test_respond_는_재생_완료를_기다리지_않는다(monkeypatch):
    """기다리면 그동안 마이크 루프가 멈춰 끼어들기 판정이 한 번도 안 돈다.

    실측: 대본은 끊기는데 일반 답변은 안 끊겼다 — 대본 분기에서만 wait_idle 을
    걷어내고 일반 경로 끝의 한 줄을 놓쳤기 때문이었다. **두 경로 모두** 즉시 반환해야 한다.
    """
    import session

    waited = []

    class FakeSpeaker:
        def speak(self, text, seed=None):
            pass

        def speak_many(self, clauses):
            pass

        def wait_idle(self, timeout=None):
            waited.append(timeout)

    class FakeLLM:
        history: list = []

        def chat_stream(self, user):
            yield "첫 절입니다."
            yield "둘째 절입니다."

    # ① 일반 답변 경로
    session.respond("오늘 날씨 어때", FakeLLM(), FakeSpeaker(), None)
    assert waited == [], "일반 답변이 재생 완료를 기다렸다 — 그동안 못 듣는다"

    # ② 자기소개 대본 경로
    session.respond("어떻게 만들어졌어?", FakeLLM(), FakeSpeaker(), None)
    assert waited == [], "대본이 재생 완료를 기다렸다"


# ── 호출어로 끊기 ───────────────────────────────────────────────
def test_호출어_판정은_로봇_자기_말과_겹치지_않는다(monkeypatch):
    """'미니' 만 호출어로 두면 대본의 '저는 리치 미니예요' 가 그대로 걸린다.

    호격 '미니야' 는 로봇이 절대 하지 않는 말이라 에코가 만들어낼 수 없다 —
    자기 목소리 오인이 구조적으로 불가능하다.
    """
    import selfintro
    import voice_loop as vl

    importlib.reload(vl)

    assert vl._has_wake("미니야")
    assert vl._has_wake("미니야 잠깐만")
    assert vl._has_wake("미니야, 그만해")
    assert vl._has_wake("그만")
    assert not vl._has_wake("")
    assert not vl._has_wake("오늘 날씨 어때")

    # 대본 13문장 중 어느 것도 호출어로 오인되면 안 된다
    for line in selfintro.SCRIPT:
        assert not vl._has_wake(line), f"대본이 호출어로 걸린다: {line}"


def test_호출어는_토큰_단위다_부분일치_오탐_금지(monkeypatch):
    """평탄화 문자열의 부분일치는 '그만' 을 '그만큼' 안에서 잡는다(리뷰 확인) —
    "그만큼 좋아?" 같은 정상 질문이 중단 명령이 되면 안 된다."""
    import voice_loop as vl

    importlib.reload(vl)
    assert not vl._has_wake("그만큼 좋아했다는 거야?")
    assert not vl._has_wake("스톱워치 기능 있어?")
    assert vl._has_wake("그만")          # 정확 토큰
    assert vl._has_wake("미니 야")       # STT 가 띄어 쓴 호출어 — 인접 결합으로 잡는다


def test_호출어_제거는_감지와_같은_규칙이다(monkeypatch):
    """감지는 평탄화·제거는 원문 replace 로 규칙이 달랐다(리뷰 확인) —
    '미니 야' 는 감지되는데 제거가 안 돼 호출어가 질문에 딸려 갔고,
    호출어만 말했는데 rest 가 남아 대기 대신 대답을 했다."""
    import voice_loop as vl

    importlib.reload(vl)
    assert vl._strip_wake("미니 야 오늘 날씨 어때") == "오늘 날씨 어때"
    assert vl._strip_wake("미니 야") == ""          # 호출어만 → 조용히 대기해야 한다
    assert vl._strip_wake("그만큼 좋아") == "그만큼 좋아"  # 남의 단어를 자르지 않는다


def test_호출어_확인도_자기_목소리를_거른다(monkeypatch):
    """기본 호출어 셋('그만'·'잠깐만'·'스톱')은 로봇이 스스로 말할 수 있다 —
    "네, 잠깐만요" 의 잔여 에코가 호출어 검사에 걸려 자기 말을 끊으면 안 된다
    (리뷰 확인). 검사 경로도 said_recently 를 타야 한다."""
    import voice_loop as vl

    importlib.reload(vl)
    monkeypatch.setattr(vl, "transcribe", lambda utt: "네 잠깐만 생각해 볼게요")

    class Spk:
        def said_recently(self, text):
            return True  # 방금 로봇이 한 말이다

    hit, busy = threading.Event(), threading.Event()
    vl._check_wake(np.zeros(1600, dtype=np.float32), hit, busy, Spk())
    assert not hit.is_set(), "자기 목소리 에코가 호출어로 걸렸다"

    class Quiet:
        def said_recently(self, text):
            return False  # 로봇이 한 말이 아니다 — 진짜 사용자

    hit.clear()
    vl._check_wake(np.zeros(1600, dtype=np.float32), hit, busy, Quiet())
    assert hit.is_set(), "진짜 호출어가 걸리지 않았다"


def test_호출어가_들리면_에너지가_모자라도_끊는다(monkeypatch):
    """에너지 임계에 못 미치는 작은 소리여도 '미니야' 가 확인되면 끊어야 한다.
    실측에서 사용자 목소리가 0.020 으로만 잡혀 에너지 판정이 아슬아슬했다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_WAKE_INTERVAL", "0.001")
    import voice_loop as vl

    importlib.reload(vl)

    # 임계(0.014)에 못 미치지만 VAD 임계(0.010)는 넘는 작은 소리
    frames = _frames([0.012], n_each=40) + _frames([0.0005], n_each=30)

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        def __init__(self):
            self._left = 40
            self.stopped = 0

        @property
        def speaking(self):
            return self._left > 0

        def tick(self):
            self._left -= 1

        def stop(self):
            self.stopped += 1
            self._left = 0

        def output_level(self, window_s=0.35):
            return 0.0  # 로봇이 조용한 틈

        def said_recently(self, text):
            return False

    spk = FakeSpeaker()
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: "미니야")
    orig = vl._rms
    monkeypatch.setattr(vl, "_rms", lambda f: (spk.tick(), orig(f))[1])
    vl.voice_loop(None, spk, None, lambda *a: None)

    assert spk.stopped == 1, "호출어가 들렸는데 안 끊었다"


def test_무음_구간은_STT_에_넘기지_않는다(monkeypatch):
    """실측: 마이크 0.001 짜리 구간을 넘겼더니 Whisper 가
    '조금 조금 조금 …' 을 만들어냈다(환각). 말소리가 없으면 부르지 않는다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_WAKE_INTERVAL", "0.001")
    import voice_loop as vl

    importlib.reload(vl)

    frames = _frames([0.0008], n_each=60)  # VAD 임계(0.010) 한참 아래

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        speaking = True

        def stop(self):
            pass

        def output_level(self, window_s=0.35):
            return 0.05

        def said_recently(self, text):
            return False

    called = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: called.append(1) or "")
    vl.voice_loop(None, FakeSpeaker(), None, lambda *a: None)
    assert called == [], "무음을 STT 에 넘겼다 — 환각의 원인이다"


def test_반복_토막은_환각으로_보고_버린다():
    import voice_loop as vl

    importlib.reload(vl)
    assert vl._hallucinated("조금 조금 조금 조금 조금 조금 조금")
    assert vl._hallucinated("네 네 네 네 네 네 네 네")
    assert not vl._hallucinated("미니야 잠깐만")
    assert not vl._hallucinated("오늘 날씨는 어떤지 알려줘")


def test_호출어가_아니면_계속_말한다(monkeypatch):
    """후보 구간을 STT 로 확인했는데 호출어가 없으면 발화를 이어가야 한다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_WAKE_INTERVAL", "0.001")
    import voice_loop as vl

    importlib.reload(vl)

    frames = _frames([0.012], n_each=40) + _frames([0.0005], n_each=10)

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        def __init__(self):
            self._left = 40
            self.stopped = 0

        @property
        def speaking(self):
            return self._left > 0

        def tick(self):
            self._left -= 1

        def stop(self):
            self.stopped += 1
            self._left = 0

        def output_level(self, window_s=0.35):
            return 0.0

        def said_recently(self, text):
            return False

    spk = FakeSpeaker()
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: "저는 인터넷에 연결되어 있지 않아요")
    orig = vl._rms
    monkeypatch.setattr(vl, "_rms", lambda f: (spk.tick(), orig(f))[1])
    vl.voice_loop(None, spk, None, lambda *a: None)

    assert spk.stopped == 0, "호출어가 아닌데 끊었다"


def test_짧은_호출어도_확인_대상이_된다(monkeypatch):
    """'미니야' 는 0.5초짜리다. 말소리 8프레임(0.24초)을 요구했더니 정작 호출어가
    문턱을 못 넘어 검사가 한 번도 안 돌았다(실측 로그)."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_WAKE_INTERVAL", "0.001")
    import voice_loop as vl

    importlib.reload(vl)
    assert vl.BARGE_IN_WAKE_MIN_SPEECH <= 5, "짧은 호출어를 놓치는 문턱이다"

    # 0.15초(5프레임)짜리 짧은 발화 — 에너지 임계(0.014)에는 못 미치지만
    # VAD 임계(0.010)는 넘는 세기다. 그 뒤 창이 찰 때까지 조용한 구간이 이어진다.
    frames = _frames([0.012], n_each=5) + _frames([0.0008], n_each=40)

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        speaking = True

        def stop(self):
            self.stopped = True

        def output_level(self, window_s=0.35):
            return 0.0

        def said_recently(self, text):
            return False

    spk = FakeSpeaker()
    spk.stopped = False
    checked = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: checked.append(len(utt)) or "미니야")
    vl.voice_loop(None, spk, None, lambda *a: None)

    assert checked, "짧은 호출어 구간에서 STT 를 부르지 않았다"
    assert spk.stopped, "호출어를 확인하고도 안 끊었다"


def test_재생_음량을_낮추면_에코가_작아진다(monkeypatch):
    """마이크 이득은 목소리와 에코를 같이 키워 비율이 안 변한다.
    스피커를 줄여야 에코만 작아진다 — 끼어들기 SNR 을 직접 좌우한다."""
    import numpy as np

    monkeypatch.setenv("REACHY_TTS_VOLUME", "0.5")
    importlib.reload(tts_mod)
    try:
        pcm = (np.ones(2400, dtype=np.int16) * 10000).tobytes()
        out = tts_mod.StreamPlayer._scaled(pcm)
        a = np.frombuffer(out, dtype=np.int16)
        assert 4900 < a.mean() < 5100, f"음량이 안 줄었다: {a.mean()}"
    finally:
        monkeypatch.delenv("REACHY_TTS_VOLUME")
        importlib.reload(tts_mod)


def test_프로브는_줄인_뒤의_소리를_본다(monkeypatch):
    """프로브가 원본을 보면 AEC 가 실제보다 큰 에코를 지우려 해 어긋난다."""
    import numpy as np

    monkeypatch.setenv("REACHY_TTS_VOLUME", "0.5")
    importlib.reload(tts_mod)
    try:
        pushed = []

        class FakeTap:
            def push(self, pcm, rate):
                pushed.append(np.frombuffer(pcm, dtype=np.int16).mean())

            def close(self):
                pass

        player = tts_mod.StreamPlayer()
        player.tap = FakeTap()
        player.play_pcm_stream(iter([(np.ones(2400, dtype=np.int16) * 10000).tobytes()]), 24000)
        assert pushed and 4900 < pushed[0] < 5100, f"프로브가 원본을 봤다: {pushed}"
        player.close()
    finally:
        monkeypatch.delenv("REACHY_TTS_VOLUME")
        importlib.reload(tts_mod)


# ── 끊은 뒤의 재질의를 삼키지 않는다 ────────────────────────────
def test_끊은_뒤_한참_지난_질문은_받는다(monkeypatch):
    """실측: 끊고 20초 뒤에 한 질문이 '끼어든 말'로 분류돼 통째로 버려졌다.
    플래그에 시간 제한이 없었던 탓이다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    monkeypatch.setenv("REACHY_BARGE_IN_WAKE", "")
    import voice_loop as vl

    importlib.reload(vl)
    # 벽시계에 기대면 플래키하다 — 테스트 루프 전체가 1ms 안에 끝나기도 한다.
    # 창을 음수로 두어 "이미 지났다"를 결정적으로 만든다.
    monkeypatch.setattr(vl, "BARGE_IN_DROP_WINDOW_S", -1.0)

    # 큰 소리로 끊고 → 침묵 → 다시 질문
    frames = (
        _frames([0.05], n_each=12)      # 끼어들기
        + _frames([0.0005], n_each=30)  # 침묵(발화 종료)
        + _frames([0.05], n_each=15)    # 재질의
        + _frames([0.0005], n_each=30)
    )

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class FakeSpeaker:
        def __init__(self):
            self._left = 12
            self.stopped = 0

        @property
        def speaking(self):
            return self._left > 0

        def tick(self):
            self._left -= 1

        def stop(self):
            self.stopped += 1
            self._left = 0

        def output_level(self, window_s=0.35):
            return 0.0

        def said_recently(self, text):
            return False

    spk = FakeSpeaker()
    answered = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: "오늘 날씨 어때")
    orig = vl._rms
    monkeypatch.setattr(vl, "_rms", lambda f: (spk.tick(), orig(f))[1])
    vl.voice_loop(None, spk, None, lambda *a: answered.append(a[0]))

    assert spk.stopped == 1
    assert answered, "끊은 뒤의 재질의를 삼켰다"


def test_호출어_뒤에_이어진_말은_질문으로_받는다(monkeypatch):
    """'미니야 오늘 날씨 어때' → 호출어만 떼고 날씨를 답해야 한다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    import voice_loop as vl

    importlib.reload(vl)
    assert vl._strip_wake("미니야 오늘 날씨 어때") == "오늘 날씨 어때"
    assert vl._strip_wake("미니야") == ""
    assert vl._strip_wake("그만!") == ""


# ── 스레드 안전성 ───────────────────────────────────────────────
def test_출력_레벨_조회는_재생과_동시에_안전하다():
    """`_out` 은 워커가 쓰고 마이크 루프가 읽는다. 잠금 없이 순회하면
    `RuntimeError: deque mutated during iteration` 이 나고, 그게 마이크 루프에서
    터지면 앱이 귀머거리가 된다(재현 확인 후 잠금 추가)."""
    import threading
    import time

    import numpy as np

    player = tts_mod.StreamPlayer()
    stop = threading.Event()
    errs = []
    pcm = (np.ones(4096, dtype=np.int16) * 3000).tobytes()

    def writer():
        while not stop.is_set():
            for _ in range(200):
                player._note_output(pcm)

    def reader():
        while not stop.is_set():
            try:
                player.output_level()
            except Exception as e:  # noqa: BLE001
                errs.append(repr(e))
                return

    threads = [threading.Thread(target=writer, daemon=True) for _ in range(2)]
    threads += [threading.Thread(target=reader, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(1.5)
    stop.set()
    time.sleep(0.2)
    player.close()
    assert not errs, f"동시 접근에서 터졌다: {errs[:2]}"


def test_한_프레임의_예외로_귀를_잃지_않는다(monkeypatch):
    """예전 루프는 KeyboardInterrupt 만 잡았다 — 다른 예외가 새면 통째로 죽어
    앱이 조용히 귀머거리가 된다(실제로 deque 경합이 이 자리에서 터질 수 있었다)."""
    monkeypatch.setenv("REACHY_BARGE_IN", "1")
    import voice_loop as vl

    importlib.reload(vl)

    frames = _frames([0.05], n_each=10) + _frames([0.0005], n_each=20)

    class FakeMic:
        def frames(self):
            return iter(frames)

        def close(self):
            pass

    class BoomSpeaker:
        """세 번째 프레임에서 한 번 터지고, 그 뒤에는 정상 동작한다."""

        def __init__(self):
            self.calls = 0
            self.stopped = 0

        @property
        def speaking(self):
            self.calls += 1
            if self.calls == 3:
                raise RuntimeError("deque mutated during iteration")
            return self.calls < 12

        def stop(self):
            self.stopped += 1

        def output_level(self, window_s=0.35):
            return 0.0

        def said_recently(self, text):
            return False

    spk = BoomSpeaker()
    printed = []
    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: FakeMic())
    monkeypatch.setattr(vl, "transcribe", lambda utt: "")
    monkeypatch.setattr(
        "builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a)))
    )
    vl.voice_loop(None, spk, None, lambda *a: None)  # 예외가 새면 여기서 터진다

    assert any("음성 루프 오류" in line for line in printed), "오류를 알리지 않았다"
    assert spk.calls > 5, f"오류 뒤에 계속 듣지 않았다 (프레임 {spk.calls}개에서 멈춤)"


# ── 환각 방어가 본 경로에도 있어야 한다 (실기 2026-09-09) ─────────
# _filler·_hallucinated 는 _check_wake(끼어들기 호출어) 에서만 불렸고, 실제 대화를
# 모는 본 경로에는 `if not text: continue` 뿐이었다. 그래서 실기에서
# `편집 Sno Sno Sno …`(200회)가 그대로 통과해 로봇이 엉뚱한 답을 했다.
def test_꼬리에_잡음이_섞인_반복도_환각으로_잡는다():
    """set 검사만으로는 못 잡는다 — 실기 로그가 정확히 그 형태였다."""
    import voice_loop as vl
    said = "편집 " + "Sno " * 200
    assert vl._hallucinated(said)
    # 토막이 3종 이상이어도 하나가 압도적이면 환각이다
    assert vl._hallucinated("아 편집 Sno " + "Sno " * 50)


def test_정상_발화는_환각으로_잡지_않는다():
    import voice_loop as vl
    assert not vl._hallucinated("전파체험관에서 제일 재미있는 부스가 어디예요")
    assert not vl._hallucinated("타이타닉 이야기 좀 해줘")
    assert not vl._hallucinated("삐삐가 뭔지 알려줘")


# ── 감독의 마이크 게이트는 캡처 단에서 (리뷰 A1) ─────────────────────


def _speech_then_silence():
    # 1.2초 말 + 1.2초 침묵 — hangover(0.7s) 를 넘겨 발화가 닫힌다
    return _frames([0.05], n_each=40) + _frames([0.001], n_each=40)


def test_마이크_게이트가_닫혀_있으면_상대_로봇의_말을_STT_에_넘기지_않는다(monkeypatch):
    """리뷰 A1 — 게이트를 STT **결과** 시점에만 걸면, 도슨트 마지막 문장을 캡처한
    뒤 게이트가 열리고 나서 전사가 도착해 관람객 발화로 올라간다(자기목소리 루프).
    캡처 단에서 막아야 한다."""
    spk = _run_loop(monkeypatch, _speech_then_silence(), barge_in=False,
                    speaking_frames=0, gate=lambda: False)
    assert spk.stt_calls == []


def test_마이크_게이트가_열리면_듣는다(monkeypatch):
    spk = _run_loop(monkeypatch, _speech_then_silence(), barge_in=False,
                    speaking_frames=0, gate=lambda: True)
    assert len(spk.stt_calls) == 1


def test_게이트가_닫힌_동안_모은_발화는_열린_뒤에도_넘어가지_않는다(monkeypatch):
    """닫혀 있는 동안 VAD 가 담아 둔 것이 열리는 순간 발화로 튀어나오면 안 된다 —
    그것이 정확히 도슨트의 마지막 문장이다."""
    state = {"open": False, "n": 0}

    def gate():
        state["n"] += 1
        if state["n"] == 40:          # 말이 끝나는 프레임에서 열린다
            state["open"] = True
        return state["open"]

    spk = _run_loop(monkeypatch, _speech_then_silence(), barge_in=False,
                    speaking_frames=0, gate=gate)
    assert spk.stt_calls == []


def test_마이크_이터레이터_안의_예외_뒤에도_계속_듣는다(monkeypatch):
    """리뷰 A5b(L1) — 제너레이터는 예외 한 번에 죽는다. 같은 객체로 재진입하면
    StopIteration 이라 루프가 조용히 끝났다. 새 이터레이터를 다시 만들어야 한다."""
    monkeypatch.setenv("REACHY_BARGE_IN", "0")
    import voice_loop as vl

    importlib.reload(vl)
    made = {"n": 0}
    quiet = _frames([0.001], n_each=5)

    class Mic:
        def frames(self):
            made["n"] += 1
            if made["n"] == 1:
                yield quiet[0]
                raise ValueError("프레임 도중 터짐")
            for f in quiet:
                yield f

        def close(self):
            pass

    class Spk:
        speaking = False

        def output_level(self, w=0.35):
            return 0.0

    monkeypatch.setattr(vl, "MicCapture", lambda *a, **k: Mic())
    monkeypatch.setattr(vl, "transcribe", lambda u: "")
    vl.voice_loop(None, Spk(), None, lambda *a: None)
    assert made["n"] == 2, "예외 뒤 이터레이터를 다시 만들지 않았다"
