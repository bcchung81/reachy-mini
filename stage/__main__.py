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
    """LLM 호출 하나. **직렬화한다.**

    `client` 하나를 공유하면서 호출마다 `client.history` 를 통째로 갈아끼운다.
    감독은 이 함수를 두 갈래에서 부른다: 큐를 시작할 때 띄우는 생성 스레드
    (`_generate_docent`)와 관람객 질문 응답(`_answer`). 늦게 끝난 생성 스레드와
    질문이 겹치면 **한쪽이 다른 쪽의 이력으로 답한다** — 지난 섹션의 맥락으로
    질문에 답하거나 그 반대다. 락 하나로 막는다. LLM 왕복은 원래 한 번에 하나만
    도는 것이 맞다(PC 추론 서버도 하나다).
    """
    client = LLMClient(system_prompt=_system_prompt())
    lock = threading.Lock()

    def generate(brief: str, history: list[dict]) -> str:
        with lock:
            client.history = list(history)
            return "".join(client.chat_stream(brief, None))

    return generate


def _system_prompt() -> str:
    return (
        "너는 전파체험관의 도슨트다. 지시를 받으면 관람객에게 들려줄 해설을 "
        "말한다. 지시문을 따라 읽지 말고 해설로 바꿔 말한다. "
        "상대연도('몇 년 전')를 쓰지 않고 절대연도로만 말한다. "
        "모르는 것은 지어내지 않는다. "
        # 답은 TTS 가 읽는다 — 목록 기호·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5).
        "네 말은 음성으로 읽힌다. 목록·이모지·특수문자·마크다운을 쓰지 않고 "
        "문장은 마침표로 끝낸다. "
        # **분량은 상한만 주면 안 된다.** 큐시트 지시문이 "N문장 이내" 로만 적혀
        # 있어 모델이 한 문장으로 답해도 지시 위반이 아니었다 — 하한을 준다.
        "지시문이 문장 수를 정해 주면 그 수를 **채워서** 말한다. "
        "'N문장 이내' 는 N문장에 가깝게, 최소 두 문장 이상 채워서 쓰라는 뜻이지 "
        "한 문장으로 끝내라는 뜻이 아니다. "
        "한 문장짜리 답은 해설이 아니다. "
    )


def announce_level() -> None:
    """어느 수준으로 도는지 기동 때 밝힌다.

    `level_of_env` 가 오타를 예외로 던지므로 이 함수를 서버 생성 **전에**
    불러야 한다 — 수준이 잘못됐으면 서버를 띄우기 전에 죽는 편이,
    콘솔까지 뜬 뒤에 엉뚱한 수준으로 시연이 도는 것보다 낫다.
    """
    from stage.levels import level_of_env, load_levels

    lv = level_of_env(load_levels())
    src = "환경변수" if os.environ.get("REACHY_AUDIENCE_LEVEL") else "기본값"
    print(
        f"관람객 수준: {lv.name} ({src}) — "
        f"{lv.min_sentences}~{lv.max_sentences}문장 / {lv.min_chars}~{lv.max_chars}자",
        flush=True,
    )


def main() -> None:
    announce_level()  # 수준이 잘못됐으면 서버를 만들기 전에 여기서 죽는다.
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
