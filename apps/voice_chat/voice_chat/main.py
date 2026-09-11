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
    """역할별 음성을 환경변수로 넣는다. **이미 있으면 덮어쓰지 않는다** —
    현장에서 손으로 바꾼 값이 코드에 밀려나면 안 된다."""
    cfg = ROLE_VOICE[role]
    for env, key in (
        ("TTS_QWEN_VOICE", "voice"),
        ("TTS_QWEN_SPEED", "speed"),
        ("TTS_QWEN_INSTRUCT", "instruct"),
    ):
        os.environ.setdefault(env, cfg[key])


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
            threading.Thread(
                target=voice_loop,
                args=(llm, speaker, player, make_heard_sink(client, mic_open)),
                kwargs={"should_stop": stop_event.is_set},
                daemon=True,
            ).start()

        client.run(should_stop=stop_event.is_set)


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
