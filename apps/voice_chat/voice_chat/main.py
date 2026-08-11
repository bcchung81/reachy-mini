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
