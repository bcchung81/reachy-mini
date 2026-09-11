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

    감독은 발화 중 `mic(open=False)` 를 보내지만 `voice_loop` 는 그걸 모르고
    계속 듣는다. 여기서 막지 않으면 로봇이 **상대 로봇의 목소리를 받아적어**
    감독에 올리고, 그것이 이 저장소가 이미 밟은 자기목소리 루프다.
    설계 §4.2 불변식 ① 이 로봇 쪽에서 실제로 성립하는 지점이 여기다.
    """

    def on_heard(text: str, *args, **kwargs) -> None:
        if not mic_open.is_set():
            log(f"  [마이크 닫힘 — 버림: {text!r}]")
            return
        client.heard(text)

    return on_heard


def role_of_env() -> str | None:
    """`REACHY_ROLE` 을 읽는다. 없으면 1대 모드.

    오타를 조용히 1대 모드로 흘려보내지 않는다 — 시연장에서 "왜 한 대만
    말하지" 를 추적하는 데 드는 시간이 가장 비싸다.
    """
    raw = os.environ.get("REACHY_ROLE")
    if raw is None or not raw.strip():
        return None
    role = raw.strip().lower()
    if role not in ROLES:
        raise ValueError(
            f"REACHY_ROLE 이 {raw!r} 다 — 쓸 수 있는 값: {', '.join(ROLES)}"
        )
    return role


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


# STT 왕복 하나가 최대 15초까지 걸릴 수 있다(stt.py:43 의 requests timeout=15).
# voice_loop 는 프레임마다(30ms) should_stop 을 보지만, transcribe() 호출 도중에는
# 응답이 돌아올 때까지 다음 프레임을 보지 못한다 — 그 안에서는 stop_event 가 서도
# 스레드가 즉시 멈추지 않는다. STT 타임아웃보다 여유 있게 잡아야 "정상적으로
# 끝나기를 기다리는 것"과 "멈추지 않는 스레드"를 헷갈리지 않는다.
VOICE_THREAD_JOIN_TIMEOUT_S = 20.0


def _join_voice_thread(thread: threading.Thread, timeout: float, warn=print) -> None:
    """voice_loop 스레드가 실제로 멈출 때까지(최대 timeout 초) 기다린다.

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
            f"  [경고] voice_loop 스레드가 {timeout}초 안에 멈추지 않았다 — "
            "자원 정리와 경쟁할 수 있다"
        )


def stage_run(reachy_mini, stop_event: threading.Event, role: str) -> None:
    """2대 모드 — 무대감독의 지시로 말하고 움직인다.

    마이크는 감독이 연다. 사회자만 열리고 도슨트는 상시 닫혀 있다(설계 §2).
    """
    from session import announce_endpoints, announce_voice, build, speak

    apply_role_voice(role)
    announce_endpoints()
    announce_voice()

    url = os.environ.get("REACHY_DIRECTOR_URL", "ws://127.0.0.1:8777")
    print(f"무대감독: {url}  역할: {role}")

    with contextlib.ExitStack() as stack:
        llm, speaker, player = build(stack, mini=reachy_mini)
        mic_open = threading.Event()
        client: StageClient | None = None
        voice_thread: threading.Thread | None = None

        def on_say(cue_id: str, text: str, gaze: str | None) -> None:
            try:
                speak(text, speaker, player)
            except Exception as exc:
                if client:
                    client.error("speak", f"{type(exc).__name__}: {exc}")
                raise
            finally:
                # **발성 경계는 여기서만 보고한다.** 감독의 게이팅이 이 값을
                # 믿는다 — 빠뜨리면 감독이 타임아웃까지 멈춰 있는다.
                if client:
                    client.speaking_started(cue_id)
                    speaker.wait_idle()
                    client.speaking_ended(cue_id)

        def on_mic(open_: bool) -> None:
            mic_open.set() if open_ else mic_open.clear()
            print(f"  [마이크 {'열림' if open_ else '닫힘'}]")

        client = StageClient(
            url,
            role,
            Handlers(
                on_say=on_say,
                on_mic=on_mic,
                on_gaze=lambda target: print(f"  [시선 {target}]"),
                on_abort=lambda: speaker.stop(),
            ),
            unit_id=_unit_id(reachy_mini),
            version=_sdk_version(),
        )

        # 사회자만 듣는다. 도슨트는 감독의 지시만 받는다.
        if role == "mc":
            voice_thread = threading.Thread(
                target=voice_loop,
                args=(llm, speaker, player, make_heard_sink(client, mic_open)),
                kwargs={"should_stop": stop_event.is_set},
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


def _unit_id(mini) -> str | None:
    """로봇의 hardware id. 시뮬(macOS)에서는 언제나 None 이다."""
    try:
        return mini.client.get_status().hardware_id
    except Exception:
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
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
