"""주소 설정 사다리(§10) — 환경변수 → 설정파일 → 기본값.

Wireless 에서 앱은 systemd 데몬의 자식이라 셸 export 가 닿지 않는다.
파일 단이 그 구멍을 메우고, 실기에서 loopback 이면 기동 로그가 크게 경고한다 —
주소가 틀려도 앱은 조용히 돌기 때문에(STT 빈 문자열·LLM 폴백) 원인이
로그에 보이지 않으면 시연장에서 못 잡는다.
"""

import importlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import config  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    """테스트마다 설정파일을 임시 경로로 돌리고 캐시를 비운다."""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(config, "path", lambda: cfg)
    monkeypatch.setattr(config, "_cache", None)
    for k in ("REACHY_LLM_URL", "REACHY_STT_URL", "TTS_QWEN_URL"):
        monkeypatch.delenv(k, raising=False)
    yield cfg


def test_환경변수가_없으면_기본값(_fresh):
    assert config.get("REACHY_LLM_URL", "http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert config.source("REACHY_LLM_URL") == "기본값"


def test_설정파일이_기본값을_이긴다(_fresh):
    _fresh.write_text(json.dumps({"REACHY_LLM_URL": "http://192.168.0.10:8080"}))
    assert config.get("REACHY_LLM_URL", "http://127.0.0.1:8080") == "http://192.168.0.10:8080"
    assert config.source("REACHY_LLM_URL") == "설정파일"


def test_환경변수가_설정파일을_이긴다(_fresh, monkeypatch):
    """시뮬·테스트가 환경변수 경로를 쓴다 — 파일이 있어도 export 가 우선이어야 한다."""
    _fresh.write_text(json.dumps({"REACHY_LLM_URL": "http://192.168.0.10:8080"}))
    monkeypatch.setenv("REACHY_LLM_URL", "http://10.0.0.5:8080")
    assert config.get("REACHY_LLM_URL", "x") == "http://10.0.0.5:8080"
    assert config.source("REACHY_LLM_URL") == "환경변수"


def test_깨진_설정파일은_경고하고_기본값으로_간다(_fresh, capsys):
    """조용히 무시하면 §10 이 막으려는 상황(적었다고 믿는데 loopback)이 된다."""
    _fresh.write_text("{ 이건 JSON 이 아니다")
    assert config.get("REACHY_LLM_URL", "기본") == "기본"
    assert "[설정 경고]" in capsys.readouterr().out


def test_파일의_비문자열_값은_무시한다(_fresh):
    _fresh.write_text(json.dumps({"REACHY_LLM_URL": 8080}))
    assert config.get("REACHY_LLM_URL", "기본") == "기본"


def test_실기에서_loopback_이면_경고한다(_fresh, monkeypatch, capsys):
    """배포 대상은 Wireless(Linux) — 거기서 loopback 은 거의 확실히 잘못이다."""
    monkeypatch.setattr(config.sys, "platform", "linux")
    config.announce()
    out = capsys.readouterr().out
    assert "주소:" in out
    assert "[주소 경고]" in out
    assert "LLM" in out and "STT" in out and "TTS" in out


def test_시뮬에서는_loopback_이_정상이라_경고하지_않는다(_fresh, monkeypatch, capsys):
    monkeypatch.setattr(config.sys, "platform", "darwin")
    config.announce()
    out = capsys.readouterr().out
    assert "주소:" in out          # 출처는 항상 밝힌다
    assert "[주소 경고]" not in out


def test_실기라도_주소가_밖을_가리키면_경고하지_않는다(_fresh, monkeypatch, capsys):
    _fresh.write_text(json.dumps({
        "REACHY_LLM_URL": "http://192.168.0.10:8080",
        "REACHY_STT_URL": "http://192.168.0.10:8090/v1/audio/transcriptions",
        "TTS_QWEN_URL": "http://192.168.0.10:8099/v1/audio/speech",
    }))
    # 모듈들이 import 시점에 주소를 굳히므로 **reload** 로 다시 읽게 한다.
    # sys.modules 에서 pop 하면 안 된다 — 다른 테스트 파일이 들고 있는 참조와
    # 정체성이 어긋나 그쪽의 importlib.reload() 가 ImportError 를 낸다
    # (실측: pop 방식으로 14건이 연쇄로 깨졌다. reload 는 같은 객체를 유지한다).
    def _refreeze():
        for m in ("llm", "stt", "tts"):
            if m in sys.modules:
                importlib.reload(sys.modules[m])
            else:
                importlib.import_module(m)

    _refreeze()
    try:
        monkeypatch.setattr(config.sys, "platform", "linux")
        config.announce()
        out = capsys.readouterr().out
        assert "[주소 경고]" not in out
        assert "설정파일" in out
    finally:
        # 설정파일을 비우고 같은 객체 그대로 기본 주소로 되돌린다
        _fresh.write_text("{}")
        config._cache = None
        _refreeze()
