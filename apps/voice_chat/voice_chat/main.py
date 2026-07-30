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

# demo.py 와 같은 평면 import 를 쓴다 — `python main.py` 로 직접 돌려도 깨지지 않는다.
sys.path.insert(0, str(Path(__file__).parent))
from demo import announce_voice, build, respond  # noqa: E402
from voice_loop import voice_loop  # noqa: E402


class VoiceChat(ReachyMiniApp):
    # 설정 페이지를 쓰지 않는다. 쓰려면 여기에 URL 을 주고 settings_app 라우트를 단다.
    custom_app_url: str | None = None

    # 영상 스트리밍을 쓰지 않으므로 wireless 에서는 "gstreamer_no_video" 로 CPU 를
    # 아낄 수 있다. 다만 우리 MicCapture 가 **자체 GStreamer 파이프라인**을 열기
    # 때문에 SDK 미디어 백엔드와의 상호작용이 실기에서 미검증이다 — 기본값을 둔다.
    request_media_backend: str | None = None

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        with contextlib.ExitStack() as stack:
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
