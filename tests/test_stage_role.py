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


def test_데몬_포트는_기본이_8000_이다(monkeypatch, 빈_설정파일):
    """**기본값이 실기의 값이다.** 실기에는 데몬이 하나(:8000)뿐이고, 앱은
    `reachy_mini_apps` 진입점으로 데몬이 낳으므로 `__main__` 을 타지도 않는다.
    포트 지정은 시뮬에서 2대를 한 맥에 띄울 때만 쓰는 스위치다 — CLAUDE.md 의
    "시뮬 전용 우회는 스위치 뒤에 두고 기본을 꺼짐으로 한다".
    """
    monkeypatch.delenv("REACHY_DAEMON_PORT", raising=False)
    assert main_mod.daemon_port_of_env() == 8000


def test_데몬_포트를_바꿔_붙을_수_있다(monkeypatch, 빈_설정파일):
    # 시뮬 2대: 사회자 :8000, 도슨트 :8001.
    monkeypatch.setenv("REACHY_DAEMON_PORT", "8001")
    assert main_mod.daemon_port_of_env() == 8001


@pytest.mark.parametrize("나쁜값", ["팔천", "80 01", "", "0", "70000"])
def test_말이_안_되는_데몬_포트는_소리_내서_실패한다(monkeypatch, 빈_설정파일, 나쁜값):
    """조용히 8000 으로 흘려보내면 **두 앱이 같은 데몬에 붙는다** — 로봇 하나만
    움직이는데 양쪽 로그는 정상으로 보여서 시연장에서 추적하기 가장 비싸다.
    (빈 문자열은 사다리가 기본값으로 받으므로 8000 이 맞다.)
    """
    monkeypatch.setenv("REACHY_DAEMON_PORT", 나쁜값)
    if 나쁜값 == "":
        assert main_mod.daemon_port_of_env() == 8000
        return
    with pytest.raises(ValueError, match="REACHY_DAEMON_PORT"):
        main_mod.daemon_port_of_env()


def test_설정파일에_적힌_역할도_읽는다(monkeypatch, tmp_path):
    """**실기에서 값이 닿는 유일한 길이다.**

    Wireless 의 앱은 `POST /api/apps/start-app/` 로 데몬이 낳는 자식이라
    `source scripts/stage-env.sh mc` 의 export 가 건너오지 않는다. 환경변수만
    읽던 시절에는 두 로봇이 **조용히 1대 모드로** 떴고 로그는 정상으로
    보였다(리뷰 C2).
    """
    import json

    import config

    monkeypatch.delenv("REACHY_ROLE", raising=False)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"REACHY_ROLE": "docent"}))
    monkeypatch.setattr(config, "path", lambda: cfg)
    monkeypatch.setattr(config, "_cache", None)
    try:
        assert main_mod.role_of_env() == "docent"
    finally:
        config._cache = None


def test_설정파일의_역할_오타도_소리_내서_실패한다(monkeypatch, tmp_path):
    import json

    import config

    monkeypatch.delenv("REACHY_ROLE", raising=False)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"REACHY_ROLE": "MC로봇"}))
    monkeypatch.setattr(config, "path", lambda: cfg)
    monkeypatch.setattr(config, "_cache", None)
    try:
        with pytest.raises(ValueError, match="REACHY_ROLE"):
            main_mod.role_of_env()
    finally:
        config._cache = None


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


# ── 발화 워커 (리뷰 I1) ──────────────────────────────────────────────
#
# `abort`·`mic`·`say` 는 **같은 WS 수신 루프**로 들어온다. 발화를 그 루프 안에서
# 끝까지 기다리면 비상정지가 한 문장 내내 듣지 않는다.

def test_발화가_수신_루프를_막지_않는다():
    """`on_say` 는 즉시 돌아와야 한다 — 그래야 다음 메시지를 받는다."""
    import threading

    말하는중 = threading.Event()
    끝내라 = threading.Event()

    def speak_one(cue_id, text, seq):
        말하는중.set()
        끝내라.wait(5)

    r = main_mod.SayRunner(speak_one, warn=lambda m: None)
    r.on_say("c1", "긴 대사", None)          # 블록되면 여기서 멈춘다
    assert 말하는중.wait(2), "발화 워커가 시작되지 않았다"
    끝내라.set()
    r.join(2)


def test_말하는_도중에_abort_와_mic_이_처리된다():
    """**이 저장소가 잡으려는 실제 증상이다** — 콘솔의 비상정지가 듣지 않았다.

    `_on_raw` 는 WS 수신 루프 안에서 동기로 불린다. `on_say` 가 거기서
    `wait_idle()` 까지 기다리면 뒤따라온 `abort` 는 **한 문장이 끝난 뒤에야**
    처리된다. 그래서 실제 StageClient 에 say → abort → mic 을 순서대로
    흘려 넣고, 발화가 아직 안 끝난 상태에서 뒤엣것이 도착하는지 본다.
    """
    import json
    import threading

    from stage_client import Handlers, StageClient

    말하는중 = threading.Event()
    멈춰 = threading.Event()
    받은것: list[str] = []

    def speak_one(cue_id, text, seq):
        말하는중.set()
        멈춰.wait(5)   # speaker.wait_idle() 흉내 — 발화가 흐르는 동안
        받은것.append("발화끝")

    r = main_mod.SayRunner(speak_one, warn=lambda m: None)

    def on_abort():
        받은것.append("abort")
        멈춰.set()      # speaker.stop() 이 하는 일 — 발화를 끊는다

    client = StageClient(
        "ws://x", "mc",
        Handlers(
            on_say=r.on_say,
            on_mic=lambda o: 받은것.append(f"mic:{o}"),
            on_gaze=lambda t: None,
            on_abort=on_abort,
        ),
        warn=lambda m: None,
    )
    client._on_raw(json.dumps({"type": "say", "cue_id": "c1", "text": "긴 대사"}))
    assert 말하는중.wait(2), "발화 워커가 시작되지 않았다"

    # 발화가 아직 흐르는 중이다. 여기서 abort 가 처리돼야 한다.
    client._on_raw(json.dumps({"type": "abort"}))
    client._on_raw(json.dumps({"type": "mic", "open": True}))
    r.join(2)

    # **순서가 전부다.** 동기로 처리하던 시절에는 `발화끝` 이 맨 앞에 왔다 —
    # 비상정지가 문장이 끝난 뒤에야 들었다는 뜻이다.
    assert 받은것 == ["abort", "mic:True", "발화끝"]


def test_발화가_겹쳐_들어오면_기다리며_경고한다():
    """불변식 ② 가 깨진 상황. 조용히 겹쳐 말하면 원인을 못 찾는다."""
    import threading

    시작 = threading.Event()
    끝내라 = threading.Event()
    순서: list[str] = []

    def speak_one(cue_id, text, seq):
        순서.append(f"start:{cue_id}")
        시작.set()
        끝내라.wait(5)
        순서.append(f"end:{cue_id}")

    logs: list[str] = []
    r = main_mod.SayRunner(speak_one, warn=logs.append)
    r.on_say("c1", "첫 대사", None)
    assert 시작.wait(2)

    t = threading.Thread(target=r.on_say, args=("c2", "둘째 대사", None))
    t.start()
    끝내라.set()
    t.join(5)
    r.join(2)

    assert any("불변식 ②" in m for m in logs)
    assert 순서 == ["start:c1", "end:c1", "start:c2", "end:c2"]


def test_발화가_안_끝나면_종료_때_소리_내서_경고한다():
    import threading

    never = threading.Event()
    r = main_mod.SayRunner(lambda *a: never.wait(), warn=(logs := []).append)
    r.on_say("c1", "대사", None)
    r.join(0.05)
    assert any("멈추지 않았다" in m for m in logs)
    never.set()


def test_발화가_없으면_join_은_조용하다():
    logs: list[str] = []
    main_mod.SayRunner(lambda *a: None, warn=logs.append).join(0.05)
    assert logs == []


# ── 마이크 지시 (리뷰 I2) ────────────────────────────────────────────

def test_들을_루프가_있으면_마이크_지시는_조용히_먹는다():
    import threading

    logs: list[str] = []
    gate = threading.Event()
    on_mic = main_mod.make_mic_sink(gate, has_listener=lambda: True, log=logs.append)
    on_mic(True)
    assert gate.is_set()
    assert not any("경고" in m for m in logs)


def test_들을_루프가_없는데_마이크를_열라면_크게_경고한다():
    """도슨트 1인 모드에는 관람객 채널이 **실질적으로 없다.**

    감독은 남은 한 대가 도슨트여도 `mic(open=True)` 를 보내지만, 도슨트는
    `voice_loop` 를 띄우지 않는다. 조용히 반쪽으로 돌면 운영자는 콘솔로
    진행해야 한다는 것을 모른다(리뷰 I2).
    """
    import threading

    logs: list[str] = []
    on_mic = main_mod.make_mic_sink(
        threading.Event(), has_listener=lambda: False, log=logs.append
    )
    on_mic(True)
    경고 = [m for m in logs if "경고" in m]
    assert 경고 and "콘솔" in 경고[0]


def test_마이크를_닫으라는_지시는_경고하지_않는다():
    import threading

    logs: list[str] = []
    gate = threading.Event()
    gate.set()
    on_mic = main_mod.make_mic_sink(gate, has_listener=lambda: False, log=logs.append)
    on_mic(False)
    assert not gate.is_set()
    assert not any("경고" in m for m in logs)


def test_unit_id_를_못_읽으면_소리_내서_경고한다():
    """감독은 이 값으로 두 로봇이 뒤바뀌었는지 본다(설계 §6.3). None 이면
    검증을 건너뛰므로 **왜 None 인지**가 중요하다 — 시뮬이라 그런 것과 SDK
    호출이 실패한 것은 전혀 다른 상황인데 예전엔 둘 다 조용한 None 이었다."""

    class 터지는미니:
        class client:
            @staticmethod
            def get_status():
                raise RuntimeError("데몬이 응답하지 않는다")

    logs: list[str] = []
    assert main_mod._unit_id(터지는미니, warn=logs.append) is None
    assert any("unit_id 를 못 읽었다" in m for m in logs)
    assert any("역할 검증이 꺼진다" in m for m in logs)


def test_배속_기본값이_1_2_다(monkeypatch, 빈_설정파일):
    """**1.0 이 아니다.** 설계 §11.4 의 연출 배속(1.06/0.94)은 CLI 기본 1.0
    기준으로 만든 값이라, 환산 없이 넣으면 시연 전체가 지금보다 느려진다.
    `ROLE_VOICE` 의 1.27/1.13 이 그 환산값이다 — 근거가 이 기본값이므로
    기본값이 바뀌면 그 둘도 다시 계산해야 한다."""
    monkeypatch.delenv("TTS_QWEN_SPEED", raising=False)
    import tts

    assert tts.qwen_speed() == 1.2
    assert float(main_mod.ROLE_VOICE["mc"]["speed"]) == pytest.approx(1.2 * 1.06, abs=0.01)
    assert float(main_mod.ROLE_VOICE["docent"]["speed"]) == pytest.approx(1.2 * 0.94, abs=0.01)


def test_배속이_숫자가_아니면_소리_내서_기본값으로_간다(monkeypatch, 빈_설정파일):
    monkeypatch.setenv("TTS_QWEN_SPEED", "빠르게")
    import tts

    tts._warned.discard("speed")
    assert tts.qwen_speed() == 1.2


# ── abort 는 소리와 몸을 같이 끊는다 (리뷰 A10) ──────────────────────


def test_abort_는_소리와_모션을_함께_끊는다():
    """소리만 끊고 몸은 계속 추면 끊긴 게 아니다(lessons.md 게이팅 항목)."""
    calls: list[str] = []

    class Sp:
        def stop(self):
            calls.append("stop")

    class Pl:
        def cancel(self):
            calls.append("cancel")

    main_mod.make_abort(Sp(), Pl(), log=lambda m: None)()
    assert calls == ["stop", "cancel"]
    calls.clear()
    main_mod.make_abort(Sp(), None, log=lambda m: None)()
    assert calls == ["stop"]


# ── 청취 스레드 생존 (리뷰 A5b) ─────────────────────────────────────


def test_죽은_청취_스레드는_리스너로_치지_않는다():
    """MicCapture 가 못 뜨면 스레드가 곧장 죽는데 `voice_thread is not None`
    은 True 라 사회자가 귀먹은 채 진행됐고 경고가 없었다."""
    import threading

    t = threading.Thread(target=lambda: None)
    assert main_mod.listener_alive(None) is False
    assert main_mod.listener_alive(t) is False        # 아직 안 시작
    t.start()
    t.join()
    assert main_mod.listener_alive(t) is False        # 끝났다


def test_청취_루프가_죽으면_감독과_로그에_알린다():
    logs: list[str] = []
    errors: list[tuple[str, str]] = []

    class C:
        def error(self, where, detail):
            errors.append((where, detail))

    def boom(*a, **k):
        raise RuntimeError("마이크 파이프라인을 기동하지 못했다")

    main_mod.run_listener(boom, (), {}, C(), log=logs.append)
    assert errors and errors[0][0] == "voice_loop"
    assert any("청취 루프가 죽었다" in m for m in logs)
