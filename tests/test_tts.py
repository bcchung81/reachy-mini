import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import tts as tts_mod
from tts import Speaker


class _FakeSD:
    """sounddevice 대역 — `OutputStream` 에 들어온 인자를 기록한다.

    `못_여는_장치` 로 지정한 device 값에는 실패해, "지정한 장치를 못 열었다" 경로를
    실제 오디오 하드웨어 없이 재현한다.
    """

    def __init__(self, 못_여는_장치=None):
        self.calls: list[dict] = []
        self._못_여는_장치 = 못_여는_장치

    def OutputStream(self, **kw):  # noqa: N802 — sounddevice 이름을 그대로 흉내낸다
        self.calls.append(kw)
        if self._못_여는_장치 is not None and kw.get("device") == self._못_여는_장치:
            raise OSError(f"Error opening OutputStream: {kw.get('device')!r}")
        return _FakeStream()

    def query_devices(self):
        return [{"name": "내장 출력", "max_output_channels": 2}]


class _FakeStream:
    def start(self):
        pass


@pytest.fixture
def 가짜_sounddevice(monkeypatch):
    """`_open_stream` 은 함수 안에서 import 하므로 sys.modules 로 갈아끼운다."""

    def _설치(fake):
        monkeypatch.setitem(sys.modules, "sounddevice", fake)
        return fake

    return _설치


def test_출력장치_지정이_없으면_device_를_주지_않는다(monkeypatch, 가짜_sounddevice):
    """기본은 지금 그대로 — 시스템 기본 출력. 실기는 스피커가 하나뿐이라
    여기를 건드릴 이유가 없다(CLAUDE.md: 시뮬 전용 우회는 기본 꺼짐)."""
    fake = 가짜_sounddevice(_FakeSD())
    monkeypatch.setattr(tts_mod, "OUT_DEVICE", "")
    assert tts_mod._open_stream(24000) is not None
    assert "device" not in fake.calls[0]


def test_출력장치를_지정하면_그_장치로_연다(monkeypatch, 가짜_sounddevice):
    # 시뮬 2대: 사회자와 도슨트가 서로 다른 출력으로 나가야 목소리가 안 섞인다.
    fake = 가짜_sounddevice(_FakeSD())
    monkeypatch.setattr(tts_mod, "OUT_DEVICE", "BlackHole 2ch")
    assert tts_mod._open_stream(24000) is not None
    assert fake.calls[0]["device"] == "BlackHole 2ch"


def test_지정한_출력장치를_못_열면_소리_내서_경고하고_기본으로_떨어진다(
    monkeypatch, 가짜_sounddevice, capsys
):
    """장치 이름 오타를 조용히 기본 출력으로 흘리면 **두 앱이 같은 스피커로**
    나간다 — 정확히 이 설정으로 막으려던 그 상태다. 소리를 아예 못 내는 것보다는
    기본 출력으로라도 내는 편이 낫지만, 경고 없이는 안 된다.
    """
    fake = 가짜_sounddevice(_FakeSD(못_여는_장치="없는장치"))
    monkeypatch.setattr(tts_mod, "OUT_DEVICE", "없는장치")
    monkeypatch.setattr(tts_mod, "_warned", set())
    assert tts_mod._open_stream(24000) is not None       # 기본으로라도 열린다
    assert [c.get("device") for c in fake.calls] == ["없는장치", None]
    경고 = capsys.readouterr().out
    assert "없는장치" in 경고 and "REACHY_AUDIO_OUT" in 경고


def test_speak은_즉시_반환하고_순차_실행된다(tmp_path):
    out = tmp_path / "log"
    # 한 줄씩 기록하는 가짜 TTS — 0.1초 걸린다
    fake = ["/bin/sh", "-c", f'sleep 0.1; echo "$0" >> {out}']
    s = Speaker(cmd=fake)
    t0 = time.time()
    s.speak("첫째")
    s.speak("둘째")
    assert time.time() - t0 < 0.05  # 비차단
    assert s.speaking  # 적재 직후부터 True (게이팅용)
    s.wait_idle(timeout=3)
    assert not s.speaking
    assert out.read_text().splitlines() == ["첫째", "둘째"]


def test_빈_문자열은_무시():
    s = Speaker(cmd=["/usr/bin/true"])
    s.speak("   ")
    assert not s.speaking


def test_기본_음성은_환경변수로_바뀐다(monkeypatch):
    import importlib

    import tts as tts_mod

    monkeypatch.setenv("REACHY_VOICE", "Rocko (한국어(한국))")
    importlib.reload(tts_mod)
    try:
        assert tts_mod.pick_voice("안녕하세요") == "Rocko (한국어(한국))"
        # 다른 문자체계는 영향받지 않는다
        assert tts_mod.pick_voice("Hello there") == "Samantha"
    finally:
        monkeypatch.delenv("REACHY_VOICE")
        importlib.reload(tts_mod)


# ── 감정 어조 (설계 §12.5 — 스위치 뒤, 기본 꺼짐) ─────────────────────
#
# 역할 기본 어조(`main.ROLE_VOICE` 의 instruct)에 감정 한 줄을 덧붙여 보낸다.
# **기본은 꺼짐이다**: Qwen3-TTS 는 요청마다 `instructions` 를 받는데, 지시문이
# 발화마다 달라지면 음색·음높이가 흔들릴 수 있다(lessons.md 의 VoiceDesign 항목 —
# 요청마다 음색을 새로 만들어 문장마다 목소리가 달라진 전례가 있다). 같은 문장 ×
# 감정 8개 청취 비교 뒤에 기본값을 정한다.


@pytest.fixture
def 빈_설정파일(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "path", lambda: tmp_path / "없는파일.json")
    monkeypatch.setattr(config, "_cache", None)
    yield
    config._cache = None


@pytest.fixture(autouse=True)
def 감정_원복():
    yield
    tts_mod.set_emotion("")


def test_감정_어조는_기본으로_꺼져_있다(monkeypatch, 빈_설정파일):
    """꺼져 있으면 **지금 동작 그대로** — 역할 어조만 나간다."""
    monkeypatch.delenv("REACHY_EMOTION_TTS", raising=False)
    monkeypatch.setenv("TTS_QWEN_INSTRUCT", "차분하고 낮게, 설명하듯 또박또박")
    tts_mod.set_emotion("놀람")
    assert tts_mod.qwen_instruct() == "차분하고 낮게, 설명하듯 또박또박"
    assert "instructions" in tts_mod._qwen_body("안녕", None, stream=True)
    assert tts_mod._qwen_body("안녕", None, stream=True)["instructions"] == (
        "차분하고 낮게, 설명하듯 또박또박"
    )


def test_켜면_역할_어조_뒤에_감정이_붙는다(monkeypatch, 빈_설정파일):
    monkeypatch.setenv("REACHY_EMOTION_TTS", "1")
    monkeypatch.setenv("TTS_QWEN_INSTRUCT", "차분하고 낮게, 설명하듯 또박또박")
    tts_mod.set_emotion("놀람")
    instruct = tts_mod.qwen_instruct()
    assert instruct.startswith("차분하고 낮게, 설명하듯 또박또박")
    assert instruct != "차분하고 낮게, 설명하듯 또박또박"
    assert tts_mod.EMOTION_INSTRUCT["놀람"] in instruct


def test_켜져_있어도_설명은_역할_어조_그대로다(monkeypatch, 빈_설정파일):
    """'설명' 은 기본 태그다 — 해설 대부분이 여기라 지시문이 흔들리면 안 된다."""
    monkeypatch.setenv("REACHY_EMOTION_TTS", "1")
    monkeypatch.setenv("TTS_QWEN_INSTRUCT", "밝고 또렷하게, 진행자처럼 활기차게")
    tts_mod.set_emotion("설명")
    assert tts_mod.qwen_instruct() == "밝고 또렷하게, 진행자처럼 활기차게"


def test_켜져_있어도_모르는_감정은_역할_어조_그대로다(monkeypatch, 빈_설정파일):
    monkeypatch.setenv("REACHY_EMOTION_TTS", "1")
    monkeypatch.setenv("TTS_QWEN_INSTRUCT", "밝고 또렷하게")
    tts_mod.set_emotion("뾰로통")
    assert tts_mod.qwen_instruct() == "밝고 또렷하게"


def test_감정_어조_어휘가_대본_감정과_같다():
    """대본의 8종 전부에 어조가 있어야 한다 — 하나 빠지면 그 감정만 조용히
    역할 기본 어조로 돈다(켠 사람은 켰다고 믿는다)."""
    import pathlib as _p
    import sys as _s

    _s.path.insert(0, str(_p.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
    from motion import STAGE_EMOTIONS

    assert set(tts_mod.EMOTION_INSTRUCT) == set(STAGE_EMOTIONS)


def test_스위치는_설정_사다리를_탄다(monkeypatch, tmp_path):
    """실기의 앱은 데몬의 자식이라 셸 export 가 닿지 않는다 — 파일 단으로도
    켤 수 있어야 한다(docs/lessons.md 의 config 사다리 항목)."""
    import json

    import config

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"REACHY_EMOTION_TTS": "1"}))
    monkeypatch.setattr(config, "path", lambda: p)
    monkeypatch.setattr(config, "_cache", None)
    monkeypatch.delenv("REACHY_EMOTION_TTS", raising=False)
    try:
        assert tts_mod.emotion_tts_enabled() is True
    finally:
        config._cache = None
