"""실기 진입점 — `reachy_mini_apps` 엔트리포인트가 이 클래스를 실행한다.

**대화 로직은 demo.py 와 같은 것을 쓴다.** 여기서 다른 점은 둘뿐이다:

1. `ReachyMini` 인스턴스를 프레임워크가 주입한다 — 우리가 만들지도, 닫지도 않는다.
   `build(mini=...)` 로 넘기면 컨텍스트로 잡지 않는다(이중 해제 방지).
2. 종료가 Ctrl-C 가 아니라 `stop_event` 다 — `voice_loop` 에 `should_stop` 으로 넘긴다.

경로 주의: LLM·STT·TTS 는 실기에서 **PC 를 가리켜야 한다.** 셋 다 환경변수로 바꾼다.

    REACHY_LLM_URL=http://<PC>:8080
    REACHY_STT_URL=http://<PC>:8090/v1/audio/transcriptions
    TTS_QWEN_URL=http://<PC>:8099/v1/audio/speech

미검증 항목(실기가 있어야 확인된다)은 `docs/real-robot-deployment.md` 참고.
"""

import contextlib
import sys
import threading
from pathlib import Path

from reachy_mini import ReachyMini, ReachyMiniApp

# 평면 import 를 쓴다 — `python main.py` 로 직접 돌려도 깨지지 않는다.
sys.path.insert(0, str(Path(__file__).parent))
from session import announce_endpoints, announce_voice, build, respond  # noqa: E402
from voice_loop import voice_loop  # noqa: E402

import os

import config as _config  # noqa: E402
from stage_client import Handlers, StageClient  # noqa: E402

ROLES = ("mc", "docent")

# 설계 §11. 배속은 **1.2 기준 환산값**이다 — TTS_QWEN_SPEED 기본이 1.2 라
# (tts.py:46) 1.06/0.94 를 그대로 넣으면 시연 전체가 지금보다 느려진다.
ROLE_VOICE = {
    "mc": {
        "voice": "serena",
        "speed": "1.27",
        "instruct": "밝고 또렷하게, 진행자처럼 활기차게",
    },
    "docent": {
        "voice": "sohee",
        "speed": "1.13",
        "instruct": "차분하고 낮게, 설명하듯 또박또박",
    },
}


def make_heard_sink(client, mic_open: threading.Event, log=print):
    """STT 결과를 감독에게 올리는 함수를 만든다. **마이크가 닫혀 있으면 버린다.**

    **이것은 이중 방어선이다.** 일차 게이트는 `voice_loop(mic_open=...)` 의 캡처
    단이다 — 닫힌 동안 프레임을 버리고 VAD 를 리셋한다. 여기(STT 결과 시점)만
    있었을 때는 상대 로봇의 마지막 문장을 VAD 가 담아 두었다가, 게이트가 열린
    뒤 전사가 도착해 관람객 발화로 올라갔다(리뷰 A1 — 자기목소리 루프).
    그래도 남겨 둔다: STT 왕복 중에 게이트가 닫혔다면 그 결과는 버려야 한다.
    """

    def on_heard(text: str, *args, **kwargs) -> None:
        if not mic_open.is_set():
            log(f"  [마이크 닫힘 — 버림: {text!r}]")
            return
        client.heard(text)

    return on_heard


def make_mic_sink(mic_open: threading.Event, has_listener, log=print):
    """감독의 `mic` 지시를 받는 함수를 만든다.

    **마이크를 열라는데 들을 루프가 없으면 크게 말한다.** 도슨트는 `voice_loop`
    를 띄우지 않는다(설계 §2 — 관람객 창구는 사회자 하나). 그런데 1인 모드로
    강등되면 감독은 남은 로봇이 도슨트여도 `mic(open=True)` 를 보낸다 —
    관람객 창구를 겸하라는 뜻이다. 지금 도슨트에는 그것을 받을 STT 루프가
    없으므로 **관람객 채널이 실질적으로 없다.** 조용히 반쪽으로 도는 것이
    가장 나쁘다: 운영자는 콘솔(`n`/`p`)로 진행해야 한다는 것을 알아야 한다.

    도슨트에 STT 를 상시로 띄우지 않는 이유는 비용이다 — PC 추론 부하가
    두 배가 된다(설계 §10 의 미검증 항목).
    """

    def on_mic(open_: bool) -> None:
        mic_open.set() if open_ else mic_open.clear()
        log(f"  [마이크 {'열림' if open_ else '닫힘'}]")
        if open_ and not has_listener():
            log(
                "  [경고] 마이크를 열라는 지시를 받았지만 이 로봇에는 청취 루프가 "
                "없다 — 관람객 발화로는 진행되지 않는다. 무대감독 콘솔에서 "
                "n(다음)/p(이전)으로 진행한다 (docs/two-robot-setup.md §7)"
            )

    return on_mic


def make_abort(speaker, player, log=print):
    """감독의 `abort`. **소리와 몸을 같이 끊는다** — 끼어들기와 같은 규칙이다
    (`voice_loop` 의 두 stop 자리가 `player.cancel()` 을 짝으로 부른다). 소리만
    끊고 몸이 계속 추면 끊긴 게 아니다(리뷰 A10, lessons.md 게이팅 항목)."""

    def on_abort() -> None:
        speaker.stop()
        if player is not None:
            player.cancel()
        log("  [감독 abort — 발화·모션 중단]")

    return on_abort


def role_of_env() -> str | None:
    """`REACHY_ROLE` 을 **설정 사다리**로 읽는다. 없으면 1대 모드.

    `os.environ` 만 보면 실기에서 절대 닿지 않는다. Wireless 의 앱은
    `POST /api/apps/start-app/` 로 **systemd 데몬이 낳는 자식 프로세스**라
    (`reachy.sh` 의 robot_up) 운영자 셸의 export 가 건너오지 않는다 —
    `config.py` 머리말이 주소 3종을 파일 단으로 내린 것과 똑같은 이유다.
    그래서 `source scripts/stage-env.sh mc` 를 아무리 해도 이 값이 없었고,
    **두 로봇이 조용히 1대 모드로 떴다**(리뷰 C2). 로그는 정상으로 보인다.

    오타를 조용히 1대 모드로 흘려보내지도 않는다 — 시연장에서 "왜 한 대만
    말하지" 를 추적하는 데 드는 시간이 가장 비싸다.
    """
    raw = _config.get("REACHY_ROLE", "")
    if not raw.strip():
        return None
    role = raw.strip().lower()
    if role not in ROLES:
        raise ValueError(
            f"REACHY_ROLE 이 {raw!r} 다 — 쓸 수 있는 값: {', '.join(ROLES)}"
        )
    return role


def daemon_port_of_env() -> int:
    """앱이 붙을 데몬 포트. **기본 8000 — 실기는 언제나 여기다.**

    실기에는 데몬이 하나뿐이고, 앱은 `reachy_mini_apps` 진입점으로 **데몬이 낳는
    자식**이라 아래 `__main__` 을 타지도 않는다(`pyproject.toml` 의
    `voice_chat = "voice_chat.main:VoiceChat"`). 그쪽 경로는 `wrapped_run()` 을
    인자 없이 부르므로 이 값이 관여하지 않는다.

    갈리는 곳은 하나뿐이다 — 시뮬에서 2대를 한 맥에 띄울 때. 데몬 두 개를
    `--fastapi-port 8000`(사회자) / `8001`(도슨트) 로 올리고 앱도 각각 그 포트에
    붙인다. CLAUDE.md 의 "시뮬 전용 우회는 스위치 뒤에 두고 기본을 꺼짐으로
    한다" 그대로다 — 기본값이 실기의 값이라 설정을 안 건드리면 실기가 그대로다.

    ⚠️ SDK 는 **8000 이 살아 있는지로** localhost/network 모드를 고른다
    (`ReachyMiniApp._check_daemon_on_localhost(port=8000)` 이 8000 고정). 8001 만
    띄우면 network 모드로 빠져 `reachy-mini.local` 을 찾다 실패한다 — 시뮬 2대에서
    사회자를 8000 에 두는 이유다.

    오타를 조용히 8000 으로 흘려보내지 않는다. 두 앱이 같은 데몬에 붙으면 로봇
    하나만 움직이는데 양쪽 로그는 정상으로 보인다 — 시연장에서 가장 비싼 종류다.
    """
    raw = _config.get("REACHY_DAEMON_PORT", "8000")
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"REACHY_DAEMON_PORT 가 {raw!r} 다 — 숫자여야 한다"
        ) from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"REACHY_DAEMON_PORT 가 {port} 다 — 1..65535 여야 한다")
    return port


def apply_role_voice(role: str) -> None:
    """역할별 음성을 환경변수로 넣는다. **운영자가 정한 값은 덮어쓰지 않는다** —
    현장에서 손으로 바꾼 값이 코드에 밀려나면 안 된다.

    "이미 있으면" 의 기준은 환경변수 하나가 아니라 **설정 사다리 전체**다
    (`config.source()`). 실기에서 운영자가 손으로 적을 수 있는 자리는
    설정파일이지 셸이 아니다 — 앱은 systemd 데몬의 자식이라 export 가 닿지
    않는다(`config.py` 머리말). `os.environ.setdefault` 만 보면 설정파일에 적힌
    화자를 코드 기본값이 조용히 밀어낸다.

    `tts.py` 는 이 값을 **요청마다** 사다리에서 다시 읽는다 — 상수로 얼어
    있던 시절에는 이 함수가 아무 효과도 없었다(리뷰 C1).
    """
    cfg = ROLE_VOICE[role]
    for env, key in (
        ("TTS_QWEN_VOICE", "voice"),
        ("TTS_QWEN_SPEED", "speed"),
        ("TTS_QWEN_INSTRUCT", "instruct"),
    ):
        if _config.source(env) != "기본값":
            continue  # 환경변수든 설정파일이든 사람이 정한 값이 이긴다
        os.environ[env] = cfg[key]


def listener_alive(thread) -> bool:
    """청취 루프가 **실제로 돌고 있는가.** `is not None` 은 기동 직후 죽은 스레드도
    True 다 — 그러면 사회자가 귀먹은 채 진행되고 경고가 없다(리뷰 A5b)."""
    return thread is not None and thread.is_alive()


def run_listener(loop_fn, args, kwargs, client, log=print) -> None:
    """청취 루프를 감싼다. 죽으면 **소리 내서** 죽는다 — 로그와 감독 양쪽에.

    `MicCapture` 가 못 뜨면 `voice_loop` 는 `RuntimeError` 로 곧장 끝난다. 스레드
    안이라 아무도 못 받고, 예전에는 `threading.excepthook` 의 traceback 한 줄이
    전부였다 — 운영자가 봐야 할 "관람객 발화로는 진행되지 않는다" 는 말이 없었다.
    """
    try:
        loop_fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        log(
            f"  [경고] 청취 루프가 죽었다({type(exc).__name__}: {exc}) — 관람객 발화로는 "
            "진행되지 않는다. 무대감독 콘솔에서 n(다음)/p(이전)으로 진행한다"
        )
        if client is not None:
            client.error("voice_loop", f"{type(exc).__name__}: {exc}")


# STT 왕복 하나가 최대 15초까지 걸릴 수 있다(stt.py:43 의 requests timeout=15).
# voice_loop 는 프레임마다(30ms) should_stop 을 보지만, transcribe() 호출 도중에는
# 응답이 돌아올 때까지 다음 프레임을 보지 못한다 — 그 안에서는 stop_event 가 서도
# 스레드가 즉시 멈추지 않는다. STT 타임아웃보다 여유 있게 잡아야 "정상적으로
# 끝나기를 기다리는 것"과 "멈추지 않는 스레드"를 헷갈리지 않는다.
VOICE_THREAD_JOIN_TIMEOUT_S = 20.0


def _join_voice_thread(
    thread: threading.Thread, timeout: float, warn=print, name: str = "voice_loop"
) -> None:
    """스레드가 실제로 멈출 때까지(최대 timeout 초) 기다린다.

    `daemon=True` 는 프로세스가 이 자리에서 곧장 죽을 때만 안전한데,
    `ReachyMiniApp.wrapped_run()` 은 `run()` 이 돌아온 뒤에도 같은 프로세스에서
    계속 돈다(다음 앱을 받을 수 있다) — 그래서 여기서 join 없이 지나가면
    `stage_run` 을 감싼 `ExitStack` 이 speaker/player 를 정리하는 동안 아직 살아
    있는 이 스레드가 방금 닫힌 자원을 건드리는 레이스가 생긴다.

    timeout 안에 안 멈추면 **조용히 넘어가지 않는다** — 계속 도는 스레드가
    있다는 신호를 운영자가 봐야 실기에서 "왜 다음 앱이 마이크를 못 잡지" 를
    추적할 수 있다.
    """
    thread.join(timeout)
    if thread.is_alive():
        warn(
            f"  [경고] {name} 스레드가 {timeout}초 안에 멈추지 않았다 — "
            "자원 정리와 경쟁할 수 있다"
        )


# 발화 워커가 이전 발화를 아직 끝내지 못했을 때 기다려 줄 한도.
SAY_OVERLAP_JOIN_S = 5.0
# 종료할 때 진행 중인 발화를 기다려 줄 한도. TTS 한 문장은 길어야 15초대다
# (긴 해설 57자 → 10.6초 실측, tts 타임아웃은 90초지만 그건 안전장치다).
SAY_THREAD_JOIN_TIMEOUT_S = 20.0


class SayRunner:
    """`say` 를 **워커 스레드에서** 실행한다 — 수신 루프를 막지 않기 위해서다.

    `abort` 와 `mic` 은 `say` 와 같은 WebSocket 수신 루프로 들어온다
    (`stage_client.py` 의 `_on_raw` 는 그 루프 안에서 동기로 불린다).
    발화를 그 루프 안에서 `speaker.wait_idle()` 로 끝까지 기다리면 그동안
    도착한 `abort` 가 **한 문장이 다 끝난 뒤에야** 처리된다 — 콘솔의
    비상정지가 듣지 않는다. 감독이 `abort` 를 보내는 상황은 대부분 "지금
    말하는 것을 멈춰라" 인데, 정확히 그때 멈출 수 없었다.

    워커는 하나면 된다. 불변식 ②(직전 `speaking_ended` 를 받기 전에는 다음
    `say` 를 보내지 않는다)가 겹치기를 이미 막는다. 그래도 겹쳐 들어오면
    **조용히 겹쳐 말하지 않고 기다리며 경고한다** — 두 목소리가 한 스피커로
    나오면 시연장에서 원인을 못 찾는다.
    """

    def __init__(self, speak_one, warn=print) -> None:
        self._speak_one = speak_one
        self._warn = warn
        self._thread: threading.Thread | None = None

    def on_say(self, cue_id: str, text: str, seq: int | None = None) -> None:
        prev = self._thread
        if prev is not None and prev.is_alive():
            self._warn(
                f"  [경고] 이전 발화가 안 끝났는데 say({cue_id}) 가 왔다 — "
                f"불변식 ② 위반. 최대 {SAY_OVERLAP_JOIN_S}초 기다린다"
            )
            prev.join(SAY_OVERLAP_JOIN_S)
            if prev.is_alive():
                self._warn("  [경고] 이전 발화가 멈추지 않았다 — 겹쳐 말할 수 있다")
        t = threading.Thread(
            target=self._speak_one,
            args=(cue_id, text, seq),
            daemon=True,
            name="stage-say",
        )
        self._thread = t
        t.start()

    def join(self, timeout: float) -> None:
        """진행 중인 발화가 끝날 때까지 기다린다(ExitStack 정리 전에)."""
        t = self._thread
        if t is not None and t.is_alive():
            _join_voice_thread(t, timeout, warn=self._warn, name="발화(say)")


def stage_run(reachy_mini, stop_event: threading.Event, role: str) -> None:
    """2대 모드 — 무대감독의 지시로 말하고 움직인다.

    마이크는 감독이 연다. 사회자만 열리고 도슨트는 상시 닫혀 있다(설계 §2).
    """
    from session import announce_endpoints, announce_voice, build, speak

    apply_role_voice(role)
    announce_endpoints()
    announce_voice()

    # 역할과 같은 이유로 사다리를 탄다 — 셸 export 는 실기의 앱에 닿지 않는다.
    url = _config.get("REACHY_DIRECTOR_URL", "ws://127.0.0.1:8777")
    print(f"무대감독: {url} ({_config.source('REACHY_DIRECTOR_URL')})  "
          f"역할: {role} ({_config.source('REACHY_ROLE')})")

    with contextlib.ExitStack() as stack:
        llm, speaker, player = build(stack, mini=reachy_mini)
        mic_open = threading.Event()
        client: StageClient | None = None
        voice_thread: threading.Thread | None = None

        def speak_one(cue_id: str, text: str, seq: int | None) -> None:
            """발화 하나. **워커 스레드에서 돈다**(SayRunner 참고).

            `seq` 는 감독이 `say` 에 실어 준 발화 번호 — 발성 경계 보고에
            그대로 되돌려 준다. 이것이 없으면 콘솔 `r` 뒤 중단된 발화의 늦은
            종료 보고를 감독이 새 발화의 것으로 오인한다(리뷰 A2)."""
            try:
                speak(text, speaker, player)
            except Exception as exc:
                # 워커 스레드라 raise 해도 아무도 못 받는다 — 대신 감독에게
                # 올리고 로그를 남긴다. 그리고 아래 finally 가 발성 경계를
                # 반드시 보고한다: 여기서 빠뜨리면 감독이 타임아웃까지 멈춘다.
                print(f"  [발화 실패] {type(exc).__name__}: {exc}", flush=True)
                if client:
                    client.error("speak", f"{type(exc).__name__}: {exc}")
            finally:
                # **발성 경계는 여기서만 보고한다.** 감독의 게이팅이 이 값을
                # 믿는다 — 빠뜨리면 감독이 타임아웃까지 멈춰 있는다.
                if client:
                    client.speaking_started(cue_id, seq)
                    speaker.wait_idle()
                    client.speaking_ended(cue_id, seq)

        say_runner = SayRunner(speak_one)

        on_mic = make_mic_sink(mic_open, has_listener=lambda: listener_alive(voice_thread))

        client = StageClient(
            url,
            role,
            Handlers(
                on_say=say_runner.on_say,
                on_mic=on_mic,
                on_gaze=lambda target: print(f"  [시선 {target}]"),
                on_abort=make_abort(speaker, player),
            ),
            unit_id=_unit_id(reachy_mini),
            version=_sdk_version(),
        )

        # 사회자만 듣는다. 도슨트는 감독의 지시만 받는다.
        if role == "mc":
            voice_thread = threading.Thread(
                target=run_listener,
                args=(
                    voice_loop,
                    (llm, speaker, player, make_heard_sink(client, mic_open)),
                    # 게이트는 **캡처 단**에 건다(리뷰 A1) — make_heard_sink 는 이중 방어선.
                    {"should_stop": stop_event.is_set, "mic_open": mic_open.is_set},
                    client,
                ),
                daemon=True,
            )
            voice_thread.start()

        client.run(should_stop=stop_event.is_set)

        # client.run() 이 돌아왔다 — stop_event 가 섰거나 감독 연결이 끊어졌다.
        # 이 `with` 블록이 끝나면 ExitStack 이 speaker/player/driver 를 정리한다.
        # voice_loop 스레드가 그 자원을 여전히 쓰는 채로 정리가 진행되면 레이스가
        # 된다 — 정리 전에 스레드가 실제로 멈췄는지 확인한다.
        if voice_thread is not None:
            _join_voice_thread(voice_thread, VOICE_THREAD_JOIN_TIMEOUT_S)
        # 발화 워커도 같은 이유로 기다린다 — 이쪽은 speaker 를 직접 쓴다.
        say_runner.join(SAY_THREAD_JOIN_TIMEOUT_S)


def _unit_id(mini, warn=print) -> str | None:
    """로봇의 hardware id. 시뮬(macOS)에서는 언제나 None 이다.

    감독은 이 값으로 두 로봇이 뒤바뀌었는지 본다(설계 §6.3). None 이면
    검증을 건너뛰므로 **왜 None 인지가 중요하다** — 시뮬이라 그런 것과
    SDK 호출이 실패한 것은 전혀 다른 상황인데, 예전에는 둘 다 조용한 None
    이었다. 실기에서 이 자리가 조용하면 역할 검증이 통째로 꺼진 채 시연에
    들어간다.
    """
    try:
        return mini.client.get_status().hardware_id
    except Exception as exc:  # noqa: BLE001
        warn(
            f"  [경고] unit_id 를 못 읽었다({type(exc).__name__}: {exc}) — "
            "감독의 역할 검증이 꺼진다. 시뮬(macOS)에서는 정상이다"
        )
        return None


def _sdk_version() -> str:
    try:
        from importlib.metadata import version

        return version("reachy_mini")
    except Exception:
        return "unknown"


class VoiceChat(ReachyMiniApp):
    # 설정 페이지를 쓰지 않는다. 쓰려면 여기에 URL 을 주고 settings_app 라우트를 단다.
    custom_app_url: str | None = None

    # **오디오 장치를 우리가 직접 연다고 SDK 에 알린다.**
    #
    # 기본값(None)은 SDK 에서 "default" 로 해석돼 LOCAL/WEBRTC 미디어 백엔드가
    # 뜨고, 그러면 **데몬이 마이크·카메라를 쥔 채로** 우리 MicCapture 가 같은
    # 장치를 또 연다(`audio_in.py` 의 autoaudiosrc). USB 오디오는 보통 캡처
    # 클라이언트를 하나만 받으므로 실기에서 캡처가 통째로 실패한다.
    #
    # "no_media" 는 SDK 가 `release_media()` 를 부르게 하는 값이다
    # (`reachy_mini.py:342-350`). 그 docstring 이 우리 설계를 그대로 적고 있다 —
    # *"the camera and microphone are available for direct access via
    # OpenCV / sounddevice / etc."* 앱이 끝나면 `__exit__` 이 acquire_media() 로
    # 되돌리므로 데몬 상태를 망가뜨리지 않는다(idempotent).
    #
    # 영상 스트리밍을 안 쓰는 만큼 CPU 도 같이 아낀다 — Wireless 는 CM4(RAM 4GB)라
    # 여유가 없다.
    request_media_backend: str | None = "no_media"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        role = role_of_env()
        if role is not None:
            stage_run(reachy_mini, stop_event, role)
            print("종료했습니다.")
            return

        # 1대 모드 — 기존 경로를 그대로 둔다.
        with contextlib.ExitStack() as stack:
            announce_endpoints()  # 주소·출처 + 실기 loopback 경고 (§10)
            announce_voice()
            llm, speaker, player = build(stack, mini=reachy_mini)
            voice_loop(llm, speaker, player, respond, should_stop=stop_event.is_set)
        print("종료했습니다.")


if __name__ == "__main__":
    app = VoiceChat()
    try:
        # 포트는 `wrapped_run` 이 `ReachyMini(...)` 로 그대로 넘긴다. 실기 경로
        # (데몬이 진입점으로 낳는 앱)는 여기를 타지 않으므로 기본 8000 그대로다 —
        # `daemon_port_of_env()` 주석 참고.
        app.wrapped_run(port=daemon_port_of_env())
    except KeyboardInterrupt:
        app.stop()
