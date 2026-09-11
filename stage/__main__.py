"""무대감독 기동 — `python -m stage`.

주소는 전부 환경변수다:
    REACHY_DIRECTOR_HOST   기본 0.0.0.0
    REACHY_DIRECTOR_PORT   기본 8777
    REACHY_MC_UNIT         사회자 로봇의 hardware id (없으면 검증 생략)
    REACHY_DOCENT_UNIT     도슨트 로봇의 hardware id
    REACHY_LLM_URL         추론 서버 (llm.py 의 기본값을 따른다)
    REACHY_CUES_PATH       큐시트 경로 (기본 data/cues.yaml)
"""

import os
import pathlib
import sys
import threading

from stage.cues import CueSheet, load_cues
from stage.server import StageServer

# 대화 로직은 앱 하나에만 둔다 — LLM 클라이언트를 다시 쓰지 않고 그것을 가져온다.
# tests/ 가 쓰는 것과 같은 경로 삽입 방식이다.
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parent.parent / "apps/voice_chat/voice_chat")
)
from llm import LLMClient  # noqa: E402


def build_generate() -> "callable":
    client = LLMClient(system_prompt=_system_prompt())

    def generate(brief: str, history: list[dict]) -> str:
        client.history = list(history)
        return "".join(client.chat_stream(brief, None))

    return generate


def _system_prompt() -> str:
    return (
        "너는 전파체험관의 도슨트다. 지시를 받으면 관람객에게 들려줄 해설을 "
        "말한다. 지시문을 따라 읽지 말고 해설로 바꿔 말한다. "
        "상대연도('몇 년 전')를 쓰지 않고 절대연도로만 말한다. "
        "모르는 것은 지어내지 않는다."
    )


def main() -> None:
    host = os.environ.get("REACHY_DIRECTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("REACHY_DIRECTOR_PORT", "8777"))
    expect = {
        k: v
        for k, v in (
            ("mc", os.environ.get("REACHY_MC_UNIT")),
            ("docent", os.environ.get("REACHY_DOCENT_UNIT")),
        )
        if v
    }
    if not expect:
        print("⚠ REACHY_MC_UNIT / REACHY_DOCENT_UNIT 이 없다 — 역할 검증을 건너뛴다")

    server = StageServer(CueSheet(load_cues()), build_generate(), expect_units=expect)
    stop = threading.Event()
    threading.Thread(
        target=server.tick_forever, args=(0.5, stop.is_set), daemon=True
    ).start()

    from stage.console import run_console

    srv = server.serve(host, port)
    print(f"무대감독 대기 중 — ws://{host}:{port}")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        run_console(server.director)
    finally:
        stop.set()
        srv.shutdown()


if __name__ == "__main__":
    main()
