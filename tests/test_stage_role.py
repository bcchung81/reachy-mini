"""역할 배선 — 1대 모드와 2대 모드는 같은 진입점에서 갈린다."""

import pathlib
import sys

import pytest

APP = pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"
sys.path.insert(0, str(APP))
import main as main_mod

_VOICE_ENV = ("TTS_QWEN_VOICE", "TTS_QWEN_SPEED", "TTS_QWEN_INSTRUCT")


class _FakeClient:
    """StageClient 대역 — heard() 로 올라온 것만 모은다."""

    def __init__(self, sink: list):
        self._sink = sink

    def heard(self, text: str) -> None:
        self._sink.append(text)


@pytest.fixture(autouse=True)
def 음성_환경변수_원복():
    """`apply_role_voice` 는 `os.environ.setdefault` 를 쓴다 — monkeypatch 가
    추적하지 못해 다음 테스트로 값이 샌다. 직접 스냅샷하고 되돌린다."""
    import os

    saved = {k: os.environ.get(k) for k in _VOICE_ENV}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def 빈_설정파일(monkeypatch, tmp_path):
    """설정 사다리의 파일 단을 비운다 — 개발 맥에 남은 설정이 테스트를
    좌우하면 같은 테스트가 사람마다 다른 결과를 낸다."""
    import config

    monkeypatch.setattr(config, "path", lambda: tmp_path / "없는파일.json")
    monkeypatch.setattr(config, "_cache", None)
    yield
    config._cache = None


def test_ROLE_이_없으면_1대_모드다(monkeypatch):
    monkeypatch.delenv("REACHY_ROLE", raising=False)
    assert main_mod.role_of_env() is None


@pytest.mark.parametrize("role", ["mc", "docent"])
def test_ROLE_을_알아본다(monkeypatch, role):
    monkeypatch.setenv("REACHY_ROLE", role)
    assert main_mod.role_of_env() == role


def test_모르는_ROLE_은_소리_내서_실패한다(monkeypatch):
    # 오타 하나로 조용히 1대 모드가 되면 시연장에서 못 찾는다.
    monkeypatch.setenv("REACHY_ROLE", "사회자")
    with pytest.raises(ValueError, match="REACHY_ROLE"):
        main_mod.role_of_env()


def test_대문자와_공백을_받아준다(monkeypatch):
    monkeypatch.setenv("REACHY_ROLE", "  MC ")
    assert main_mod.role_of_env() == "mc"


def test_stage_run_이_있다():
    assert callable(main_mod.stage_run)


def test_마이크가_닫혀_있으면_감독에_올리지_않는다():
    """불변식 ① 이 로봇 쪽에서 실제로 성립하는지 — 장부가 아니라 동작으로."""
    import threading

    sent: list[str] = []
    gate = threading.Event()          # 닫힌 상태
    sink = main_mod.make_heard_sink(
        _FakeClient(sent), gate, log=lambda m: None
    )
    sink("상대 로봇이 말한 내용")
    assert sent == []


def test_마이크가_열려_있으면_감독에_올린다():
    import threading

    sent: list[str] = []
    gate = threading.Event()
    gate.set()
    sink = main_mod.make_heard_sink(
        _FakeClient(sent), gate, log=lambda m: None
    )
    sink("다음")
    assert sent == ["다음"]


def test_버릴_때_소리_내서_남긴다():
    """조용히 버리면 시연장에서 '왜 안 듣지' 를 추적할 수 없다."""
    import threading

    logs: list[str] = []
    sink = main_mod.make_heard_sink(
        _FakeClient([]), threading.Event(), log=logs.append
    )
    sink("버려질 말")
    assert any("버림" in m for m in logs)


def test_음성_스레드가_금방_끝나면_조용히_join된다():
    """정상 종료 — timeout 안에 끝나면 경고가 없어야 한다."""
    import threading
    import time

    t = threading.Thread(target=lambda: time.sleep(0.01))
    t.start()
    logs: list[str] = []
    main_mod._join_voice_thread(t, timeout=1.0, warn=logs.append)
    assert not t.is_alive()
    assert logs == []


def test_음성_스레드가_안_멈추면_소리_내서_경고한다():
    """ExitStack 이 speaker/player 를 정리하기 전에 이 신호가 있어야 레이스를
    운영자가 알아챌 수 있다 — 조용히 넘어가면 실기에서 원인 불명 오류가 된다."""
    import threading

    never = threading.Event()  # 절대 set 되지 않는다 — 멈추지 않는 스레드 흉내
    t = threading.Thread(target=never.wait, daemon=True)
    t.start()
    logs: list[str] = []
    main_mod._join_voice_thread(t, timeout=0.05, warn=logs.append)
    assert any("멈추지 않았다" in m for m in logs)
    never.set()
    t.join()


def test_역할별_음성이_문서와_일치한다():
    # 설계 §11. 배속은 1.0 이 아니라 **1.2 기준 환산값**이다(tts.py:46).
    assert main_mod.ROLE_VOICE == {
        "mc": {"voice": "serena", "speed": "1.27",
               "instruct": "밝고 또렷하게, 진행자처럼 활기차게"},
        "docent": {"voice": "sohee", "speed": "1.13",
                   "instruct": "차분하고 낮게, 설명하듯 또박또박"},
    }


def test_역할_음성이_실제_합성_요청에_실린다(monkeypatch, 빈_설정파일):
    """**환경변수 장부가 아니라 요청 본문을 본다.**

    예전 판은 `os.environ` 만 확인했다. 그래서 `tts.py` 가 화자·배속을
    import 시점 상수로 얼려 두고 있어 `apply_role_voice` 가 **아무 효과도
    없던 것**을 잡지 못했다 — 두 로봇이 같은 목소리로 말했고 설계 §11 이
    통째로 죽어 있었다(리뷰 C1). 절대 실패할 수 없는 테스트였다.
    """
    monkeypatch.delenv("TTS_QWEN_VOICE", raising=False)
    monkeypatch.delenv("TTS_QWEN_SPEED", raising=False)
    monkeypatch.delenv("TTS_QWEN_INSTRUCT", raising=False)
    import tts

    main_mod.apply_role_voice("docent")
    body = tts._qwen_body("안녕하세요.", None, stream=False)
    assert body["voice"] == "sohee"
    assert body["speed"] == 1.13
    assert "차분하고" in body["instructions"]


def test_사회자와_도슨트의_요청이_서로_다르다(monkeypatch, 빈_설정파일):
    """두 역할이 정말 갈리는지 — 한쪽만 보면 둘 다 기본값이어도 통과한다."""
    import tts

    for k in _VOICE_ENV:
        monkeypatch.delenv(k, raising=False)
    main_mod.apply_role_voice("mc")
    mc = tts._qwen_body("안녕", None, stream=False)
    for k in _VOICE_ENV:
        monkeypatch.delenv(k, raising=False)
    main_mod.apply_role_voice("docent")
    docent = tts._qwen_body("안녕", None, stream=False)

    assert (mc["voice"], mc["speed"]) == ("serena", 1.27)
    assert (docent["voice"], docent["speed"]) == ("sohee", 1.13)
    assert mc["instructions"] != docent["instructions"]


def test_운영자가_지정한_음성을_덮어쓰지_않는다(monkeypatch, 빈_설정파일):
    # 현장에서 손으로 바꾼 값이 코드에 밀려나면 안 된다.
    monkeypatch.setenv("TTS_QWEN_VOICE", "ono_anna")
    main_mod.apply_role_voice("mc")
    import tts

    assert tts._qwen_body("안녕", None, stream=False)["voice"] == "ono_anna"


def test_설정파일에_적힌_음성도_덮어쓰지_않는다(monkeypatch, tmp_path):
    """실기에서 운영자가 손으로 적을 수 있는 자리는 **설정파일**이다 —
    앱은 systemd 데몬의 자식이라 셸 export 가 닿지 않는다(config.py 머리말).
    `os.environ.setdefault` 만 보면 그 값이 코드 기본값에 조용히 밀려난다."""
    import json

    import config
    import tts

    for k in _VOICE_ENV:
        monkeypatch.delenv(k, raising=False)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"TTS_QWEN_VOICE": "vivian"}))
    monkeypatch.setattr(config, "path", lambda: cfg)
    monkeypatch.setattr(config, "_cache", None)

    main_mod.apply_role_voice("mc")
    assert tts._qwen_body("안녕", None, stream=False)["voice"] == "vivian"
