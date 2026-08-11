"""출력 리샘플 — 로봇 오디오 장치가 16 kHz 라서 필요하다.

TTS 는 24 kHz 로 뱉는데 탑재 펌웨어(`ua_io16_lin`)와 SDK(`SAMPLE_RATE = 16000`)가
둘 다 16 kHz 를 가리킨다. 24k 스트림이 안 열리면 발화마다 `_afplay`(0.8초 고정비)로
떨어져 스트리밍으로 번 0.23초가 통째로 사라진다.

여기서 고정하는 것은 셋이다:
  ① 장치가 안 받는 레이트면 받는 레이트로 열고 리샘플한다(맥에서는 리샘플 안 낀다)
  ② 청크로 나눠 넣어도 한 방에 넣은 것과 같다 — 경계 클릭이 없다
  ③ 신호가 살아 있다 — 주파수가 유지되고 에일리어싱이 안 생긴다
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import tts as tts_mod


def _tone(freq: float, rate: int, seconds: float = 0.5) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    return (np.sin(2 * np.pi * freq * t) * 12000).astype(np.int16).tobytes()


def _peak_hz(pcm: bytes, rate: int) -> float:
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
    spec = np.abs(np.fft.rfft(a * np.hanning(a.size)))
    return float(np.fft.rfftfreq(a.size, 1 / rate)[int(np.argmax(spec))])


# ── ② 청크 경계 ────────────────────────────────────────────────


def test_청크로_나눠_넣어도_한_방에_넣은_것과_같다():
    """상태를 안 이으면 여기서 갈린다 — 그 차이가 귀에는 클릭으로 들린다."""
    src = _tone(1000, 24000)

    one = tts_mod._Resampler(24000, 16000).process(src)

    r = tts_mod._Resampler(24000, 16000)
    # 4096바이트는 실제 스트리밍 청크 크기(_PCM_CHUNK)다. 2048샘플이라
    # 3의 배수가 아니므로 데시메이션 위상이 매 청크 달라진다 — 그게 요점이다.
    step = tts_mod._PCM_CHUNK
    many = b"".join(r.process(src[i : i + step]) for i in range(0, len(src), step))

    assert len(one) == len(many)
    a = np.frombuffer(one, dtype=np.int16).astype(np.float64)
    b = np.frombuffer(many, dtype=np.int16).astype(np.float64)
    assert np.max(np.abs(a - b)) <= 1, "청크 경계에서 신호가 어긋난다(필터 상태 미연결)"


def test_홀수_길이_청크에서도_위상이_이어진다():
    """청크가 down(=3)의 배수가 아니어도 샘플이 빠지거나 겹치면 안 된다."""
    src = _tone(800, 24000, seconds=0.2)
    one = tts_mod._Resampler(24000, 16000).process(src)

    r = tts_mod._Resampler(24000, 16000)
    out, i = [], 0
    for step in (1000, 302, 78, 1234):  # 전부 3의 배수가 아닌 샘플 수를 만든다
        while i < len(src):
            out.append(r.process(src[i : i + step * 2]))
            i += step * 2
            break
    out.append(r.process(src[i:]))
    many = b"".join(out)

    assert len(one) == len(many)
    a = np.frombuffer(one, dtype=np.int16).astype(np.float64)
    b = np.frombuffer(many, dtype=np.int16).astype(np.float64)
    assert np.max(np.abs(a - b)) <= 1


def test_리셋하면_이전_발화의_꼬리가_안_샌다():
    r = tts_mod._Resampler(24000, 16000)
    r.process(_tone(3000, 24000, seconds=0.1))
    r.reset()
    after = r.process(_tone(1000, 24000))
    fresh = tts_mod._Resampler(24000, 16000).process(_tone(1000, 24000))
    assert after == fresh


# ── ③ 신호 보존 ────────────────────────────────────────────────


def test_주파수가_유지된다():
    for freq in (300.0, 1000.0, 3000.0):
        out = tts_mod._Resampler(24000, 16000).process(_tone(freq, 24000))
        assert abs(_peak_hz(out, 16000) - freq) < 15, f"{freq}Hz 가 어긋났다"


def test_길이가_비율대로_나온다():
    src = _tone(1000, 24000, seconds=1.0)  # 24000 샘플
    out = tts_mod._Resampler(24000, 16000).process(src)
    assert len(out) // 2 == 16000


def test_진폭이_보존된다():
    """DC 이득이 1 이어야 한다 — 필터 합을 up 으로 안 맞추면 소리가 커지거나 작아진다."""
    src = _tone(1000, 24000)
    out = tts_mod._Resampler(24000, 16000).process(src)
    a = np.frombuffer(src, dtype=np.int16).astype(np.float64)
    b = np.frombuffer(out, dtype=np.int16).astype(np.float64)
    # 앞뒤 필터 램프 구간은 뺀다
    assert abs(np.abs(b[500:-500]).max() / np.abs(a).max() - 1.0) < 0.02


def test_나이키스트_위_성분은_접히지_않고_지워진다():
    """16 kHz 로 내리면 8 kHz 위는 버려야 한다. 안 지우면 낮은 쪽으로 접혀 들어온다.

    양끝은 뺀다 — 톤이 뚝 시작하고 뚝 끝나는 데서 나오는 과도응답이라 에일리어싱과
    무관하다(실측: 정상구간 8 / 가장자리 1941, 둘을 안 가르면 오판한다).
    """
    out = tts_mod._Resampler(24000, 16000).process(_tone(10000, 24000))
    a = np.frombuffer(out, dtype=np.int16).astype(np.float64)
    assert np.abs(a[500:-500]).max() < 0.01 * 12000, "에일리어싱이 남았다"


# ── ① 장치 레이트 협상 ─────────────────────────────────────────


class _FakeStream:
    def __init__(self, rate):
        self.rate = rate
        self.active = True
        self.written = 0

    def write(self, arr):
        self.written += len(arr)

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        pass


def _only(supported: set[int], opened: list[int]):
    def _open(rate):
        opened.append(rate)
        return _FakeStream(rate) if rate in supported else None

    return _open


def test_장치가_원본_레이트를_받으면_리샘플하지_않는다(monkeypatch):
    """맥에서는 24k 가 그대로 열린다 — 시뮬 회귀가 없어야 한다."""
    opened: list[int] = []
    monkeypatch.setattr(tts_mod, "_open_stream", _only({24000, 16000}, opened))
    player = tts_mod.StreamPlayer()
    try:
        assert player._ensure_output(24000) is True
        assert opened == [24000], "원본 레이트를 먼저 시도해야 한다"
        assert player._resampler is None
        assert player._for_device(b"\x01\x02") == b"\x01\x02"
    finally:
        player.close()


def test_장치가_16k_만_받으면_16k_로_열고_리샘플한다(monkeypatch):
    """로봇(XVF3800, io16)이 이 경우다."""
    opened: list[int] = []
    monkeypatch.setattr(tts_mod, "_open_stream", _only({16000}, opened))
    player = tts_mod.StreamPlayer()
    try:
        assert player._ensure_output(24000) is True
        assert opened == [24000, 16000], "원본 실패 후 후보로 내려가야 한다"
        assert player._dev_rate == 16000
        assert player._resampler is not None
        # 0.5초 24k 를 넣으면 0.5초치 16k 가 나온다
        assert len(player._for_device(_tone(1000, 24000))) // 2 == 8000
    finally:
        player.close()


def test_리샘플로_물러나면_경고를_남긴다(monkeypatch, capsys):
    """조용히 성능이 떨어진 채 도는 것이 가장 나쁘다."""
    monkeypatch.setattr(tts_mod, "_open_stream", _only({16000}, []))
    monkeypatch.setattr(tts_mod, "_warned", set())
    player = tts_mod.StreamPlayer()
    try:
        player._ensure_output(24000)
    finally:
        player.close()
    out = capsys.readouterr().out
    assert "리샘플" in out and "16000" in out


def test_아무_레이트도_안_열리면_afplay_로_떨어진다(monkeypatch):
    """리샘플 경로가 생겨도 마지막 방어선은 그대로여야 한다."""
    monkeypatch.setattr(tts_mod, "_open_stream", _only(set(), []))
    calls: list[int] = []
    monkeypatch.setattr(tts_mod, "_afplay", lambda data: calls.append(len(data)))
    player = tts_mod.StreamPlayer()
    player.play_pcm_stream(iter([_tone(1000, 24000)]), rate=24000)
    assert len(calls) == 1


def test_출력_레이트를_강제할_수_있다(monkeypatch):
    """실기에서 탐색을 건너뛰고 싶을 때 — REACHY_TTS_OUT_RATE."""
    opened: list[int] = []
    monkeypatch.setattr(tts_mod, "OUT_RATE_FORCED", "16000")
    monkeypatch.setattr(tts_mod, "_open_stream", _only({16000, 24000}, opened))
    player = tts_mod.StreamPlayer()
    try:
        player._ensure_output(24000)
        assert opened == [16000], "강제하면 원본 레이트를 시도하지 않는다"
        assert player._resampler is not None
    finally:
        player.close()


def test_스트리밍_재생이_리샘플을_거쳐_장치로_간다(monkeypatch):
    """경로 전체 확인 — 청크가 16k 로 변환돼 스트림에 쓰인다."""
    streams: list[_FakeStream] = []

    def _open(rate):
        if rate != 16000:
            return None
        s = _FakeStream(rate)
        streams.append(s)
        return s

    monkeypatch.setattr(tts_mod, "_open_stream", _open)
    monkeypatch.setattr(tts_mod, "PREBUFFER_S", 0.0)
    player = tts_mod.StreamPlayer()
    try:
        src = _tone(1000, 24000, seconds=0.6)  # 14400 샘플 → 9600 샘플
        step = tts_mod._PCM_CHUNK
        player.play_pcm_stream(
            iter([src[i : i + step] for i in range(0, len(src), step)]), rate=24000
        )
        assert streams and streams[0].written == 9600
    finally:
        player.close()
