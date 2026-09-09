"""기동 시 볼륨 최대화 — 실기 스피커가 62%(-23dB)로 출고된다(2026-09-09 실측).

ALSA 전용이라 시뮬(macOS)에서는 **조용히** 건너뛰어야 한다. 반대로 Linux(실기)에서
실패하면 소리 내서 알려야 한다 — 시연장에서 "왜 작지"를 못 찾는 게 최악이다.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import audio_setup  # noqa: E402
import config  # noqa: E402


class _Run:
    """subprocess.run 대역 — 호출을 기록한다."""

    def __init__(self, fail=()):
        self.calls = []
        self._fail = fail

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        rc = 1 if any(f in " ".join(argv) for f in self._fail) else 0

        class R:
            returncode = rc
            stdout = "card 0: Audio [Reachy Mini Audio], device 0: USB Audio [USB Audio]\n"

        return R()


def _linux(monkeypatch, run, amixer="/usr/bin/amixer"):
    monkeypatch.setattr(audio_setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(audio_setup.shutil, "which", lambda n: amixer)
    monkeypatch.setattr(audio_setup.subprocess, "run", run)


def test_비리눅스에서는_조용히_건너뛴다(monkeypatch, capsys):
    run = _Run()
    monkeypatch.setattr(audio_setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(audio_setup.subprocess, "run", run)
    audio_setup.maximize_volume()
    assert run.calls == []
    assert capsys.readouterr().out == "", "시뮬에서 경고를 쏟으면 안 된다"


def test_스위치를_끄면_아무것도_안_한다(monkeypatch):
    run = _Run()
    _linux(monkeypatch, run)
    monkeypatch.setattr(config, "get",
                        lambda n, d: "0" if n == "REACHY_AUDIO_MAX_VOLUME" else d)
    audio_setup.maximize_volume()
    assert run.calls == []


def test_스피커와_마이크를_모두_100퍼센트로(monkeypatch):
    run = _Run()
    _linux(monkeypatch, run)
    audio_setup.maximize_volume()
    sets = [" ".join(c) for c in run.calls if "sset" in c]
    assert any("PCM 100%" in s for s in sets), "스피커(PCM)를 안 올렸다"
    assert any("PCM,1 100%" in s for s in sets)
    assert any("Headset,0 100%" in s for s in sets), "마이크(Headset)를 안 올렸다"
    assert any("Headset,1 100%" in s for s in sets)


def test_카드를_이름으로_찾는다(monkeypatch):
    """인덱스를 0 으로 박으면 HDMI 가 끼어들 때 엉뚱한 카드를 만진다."""
    run = _Run()
    _linux(monkeypatch, run)
    audio_setup.maximize_volume()
    assert any(c[:3] == ["amixer", "-c", "0"] for c in run.calls if "sset" in c)


def test_amixer가_없으면_리눅스에서는_경고한다(monkeypatch, capsys):
    run = _Run()
    _linux(monkeypatch, run, amixer=None)
    audio_setup.maximize_volume()
    assert run.calls == []
    assert "amixer" in capsys.readouterr().out


def test_설정_실패는_소리내서_알린다(monkeypatch, capsys):
    run = _Run(fail=("sset PCM 100%",))
    _linux(monkeypatch, run)
    audio_setup.maximize_volume()
    assert "볼륨" in capsys.readouterr().out
