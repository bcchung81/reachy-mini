"""무대감독 기동 — `python -m stage`.

주소는 전부 환경변수다:
    REACHY_DIRECTOR_HOST   기본 0.0.0.0
    REACHY_DIRECTOR_PORT   기본 8777
    REACHY_MC_UNIT         사회자 로봇의 hardware id (없으면 검증 생략)
    REACHY_DOCENT_UNIT     도슨트 로봇의 hardware id
    REACHY_LLM_URL         추론 서버 (llm.py 의 기본값을 따른다)
    REACHY_CUES_PATH       큐시트 경로 (기본 data/cues.yaml)
    REACHY_AUDIENCE_LEVEL  관람객 수준 — 초등/중고등/일반/전문가 (기본 일반)
    REACHY_LEVELS_PATH     수준 프로필 경로 (기본 data/levels.yaml)
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


def build_generate(level) -> "callable":
    """LLM 호출 하나. **직렬화한다.**

    두 화자가 **하나의 대화 이력**을 봐야 말이 이어진다 — B 의 대사는 A 가
    정해진 뒤에야 만들 수 있으므로 병렬이 아니라 파이프라인이다. 그래서
    클라이언트를 역할별로 둬도 락은 하나다.

    페르소나는 이제 역할·수준의 함수다(`stage/prompts.py`) — 도슨트만
    기술하던 문자열 하나(`_system_prompt`, 이 함수가 지웠다) 대신
    [공통 규약 + 역할 + 수준] 세 조각을 역할별로 조립한다.
    """
    from stage.prompts import ROLES, build_system_prompt

    clients = {
        r: LLMClient(system_prompt=build_system_prompt(r, level),
                     max_tokens=level.max_tokens)
        for r in ROLES
    }
    lock = threading.Lock()

    def generate(role: str, brief: str, history: list[dict]) -> str:
        with lock:
            c = clients[role]
            c.history = list(history)
            return "".join(c.chat_stream(brief, None))

    return generate


def announce_level(lv, explicit: bool) -> None:
    """어느 수준으로 도는지 기동 때 밝힌다.

    `lv` 와 `explicit` 은 **같은 호출자**(`main()`)에게서 받는다. 예전에는
    `lv` 는 인자로 받으면서 "환경변수인지 기본값인지" 라벨만 이 함수가 따로
    `os.environ` 을 봐서 판정했다 — 호출자가 env 와 다른 `Level` 을 넘기면
    (예: 테스트가 임의의 `Level` 을 만들어 넘기는 경우) 로그가 거짓 출처를
    찍는다(리뷰 Minor 4). `lv`/`explicit` 을 한 곳에서 같이 받으면 그 둘이
    갈릴 여지가 없다 — (b)가 "수준을 두 번 읽지 않는다" 로 없앤 여지를 여기서
    "출처 판정을 두 번 하지 않는다" 로 마저 없앤다.
    """
    src = "환경변수" if explicit else "기본값"
    print(
        f"관람객 수준: {lv.name} ({src}) — "
        f"{lv.min_sentences}~{lv.max_sentences}문장 / {lv.min_chars}~{lv.max_chars}자",
        flush=True,
    )


def main() -> None:
    from stage.levels import level_of_env, load_levels

    # **여기서 한 번만 읽는다.** `level_of_env` 가 오타를 예외로 던지므로 이
    # 줄을 서버 생성 **전에** 둬야 한다 — 수준이 잘못됐으면 서버를 띄우기
    # 전에 죽는 편이, 콘솔까지 뜬 뒤에 엉뚱한 수준으로 시연이 도는 것보다 낫다.
    #
    # `explicit` 도 이 한 번의 환경 조회에서 함께 뽑는다 — `level_of_env` 가
    # 보는 것과 같은 환경변수를 같은 자리에서 본다. `announce_level` 이 따로
    # `os.environ` 을 보게 하면 "무엇을 찍는지" 와 "무엇으로 도는지" 가
    # 서로 다른 조회에서 나와 갈릴 여지가 생긴다.
    explicit = bool(os.environ.get("REACHY_AUDIENCE_LEVEL", "").strip())
    level = level_of_env(load_levels())
    announce_level(level, explicit)  # 수준이 잘못됐으면 이미 위에서 죽었다.
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

    server = StageServer(CueSheet(load_cues()), build_generate(level), expect_units=expect)
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
