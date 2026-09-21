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
    REACHY_MC_LINES_PATH   여는 대사 사전 생성 캐시 경로 (기본 data/mc_lines.yaml)
"""

import os
import pathlib
import sys
import threading

from stage.cues import CueSheet, load_cues
from stage.mc_cache import cache_path, load_mc_lines
from stage.server import StageServer

# 대화 로직은 앱 하나에만 둔다 — LLM 클라이언트를 다시 쓰지 않고 그것을 가져온다.
# tests/ 가 쓰는 것과 같은 경로 삽입 방식이다.
sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parent.parent / "apps/voice_chat/voice_chat")
)
from llm import LLMClient  # noqa: E402
from typing import Callable  # noqa: E402

from stage.director import SPEAKER_LABEL  # noqa: E402
from stage.prompts import _MC_MAX_CHARS, _MC_MAX_SENTENCES  # noqa: E402
from stage.speech_text import cap_length, strip_speaker_labels  # noqa: E402


def history_for(role: str, history: list[dict]) -> list[dict]:
    """감독의 공용 이력을 **생성하는 역할의 시점**으로 바꾼다.

    감독의 이력은 하나이고 내용 앞에 "사회자:"/"도슨트:"/"관람객:" 이 붙는다
    (`Director._remember`, 설계 §5.2). 그대로 실으면 사회자·도슨트 줄이 전부
    `assistant` 라 모델이 **상대의 말을 자기 말로** 보고, 그 말들이 전부
    "이름표: 텍스트" 모양이라 따라 한다 — 2026-09-21 실기에서 사회자가 "사회자:"
    를 소리 내 읽었다(mc:42).

    - 자기 줄 → `assistant`, 이름표를 뗀다(모델이 흉내 낼 원본을 없앤다)
    - 남의 줄 → `user`, 이름표를 둔다(누가 한 말인지는 알아야 한다)
    - 같은 역할이 연달아 오면 한 메시지로 합친다 — 역할 교대를 강제하는 채팅
      템플릿에 거절당하면 모든 생성이 큐시트 폴백으로 떨어진다
    """
    own = SPEAKER_LABEL[role] + ":"
    out: list[dict] = []
    for h in history:
        content = h["content"]
        if content.startswith(own):
            msg = {"role": "assistant", "content": content[len(own):].strip()}
        else:
            msg = {"role": "user", "content": content}
        if out and out[-1]["role"] == msg["role"]:
            out[-1] = {
                "role": msg["role"],
                "content": out[-1]["content"] + "\n" + msg["content"],
            }
        else:
            out.append(msg)
    return out


def build_generate(level, warn: Callable[[str], None] = print) -> "callable":
    """LLM 호출 하나. **직렬화한다.**

    두 화자가 **하나의 대화 이력**을 봐야 말이 이어진다 — B 의 대사는 A 가
    정해진 뒤에야 만들 수 있으므로 병렬이 아니라 파이프라인이다. 그래서
    클라이언트를 역할별로 둬도 락은 하나다.

    페르소나는 이제 역할·수준의 함수다(`stage/prompts.py`) — 도슨트만
    기술하던 문자열 하나(`_system_prompt`, 이 함수가 지웠다) 대신
    [공통 규약 + 역할 + 수준] 세 조각을 역할별로 조립한다.

    **모든 생성이 여기를 지나므로 생성문 정리도 여기서 한다**(도슨트 해설·질문
    응답·사회자 받아치기·예비·사전 생성 여는 대사). 텍스트가 TTS 와 감독 이력으로
    갈라지기 전이라 두 갈래가 함께 깨끗해진다. 순서는 이름표 정리 → 분량 상한 —
    상대 턴을 먼저 걷어야 문장 수를 바르게 센다. 바뀌면 반드시 경고한다.
    분량 한도는 프롬프트가 모델에게 준 바로 그 수다(두 곳에 따로 적으면 썩는다).
    """
    from stage.prompts import ROLES, build_system_prompt

    clients = {
        r: LLMClient(system_prompt=build_system_prompt(r, level),
                     max_tokens=level.max_tokens)
        for r in ROLES
    }
    limits = {
        "docent": (level.max_sentences, level.max_chars),
        "mc": (_MC_MAX_SENTENCES, _MC_MAX_CHARS),
    }
    lock = threading.Lock()

    def generate(role: str, brief: str, history: list[dict]) -> str:
        with lock:
            c = clients[role]
            hist = history_for(role, history)
            # 이력 끝의 남의 말은 이번 지시문 앞으로 옮긴다 — `chat_stream` 이
            # 지시문을 user 로 붙이므로 그대로 두면 user 가 연달아 간다.
            if hist and hist[-1]["role"] == "user":
                brief = hist.pop()["content"] + "\n\n" + brief
            c.history = hist
            raw = "".join(c.chat_stream(brief, None))
        text, stripped = strip_speaker_labels(raw)
        if stripped:
            warn(f"[{role}] 생성문에 화자 이름표/상대 턴이 섞여 걷어냈다: {raw[:60]!r}")
        max_sentences, max_chars = limits[role]
        text, capped = cap_length(text, max_sentences, max_chars)
        if capped:
            warn(
                f"[{role}] 생성문이 분량 상한({max_sentences}문장/{max_chars}자)을 "
                "넘어 문장 경계에서 잘랐다"
            )
        return text

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

    # `level.name` 은 이미 위에서 한 번 읽어 둔 `level` 객체의 속성일 뿐이다
    # — 환경변수를 다시 조회하지 않는다("수준을 두 번 읽지 않는다"). 캐시도
    # 여기서 한 번만 읽어 `Director` 로 흘려보낸다 — `StageServer.__init__`
    # 이 기본값(빈 dict·"일반")으로 넘기게 두면 캐시가 아무리 채워져 있어도
    # 늘 무시된다.
    mc_lines = load_mc_lines()
    # **기동 로그에 몇 개 읽었는지 남긴다.** "시연 전에 사람이 미리 확인한다"
    # 는 이 캐시의 존재 이유가, 정작 기동 때 몇 개가 실제로 실렸는지 아무
    # 데도 안 남으면 지켜지지 않는다 — 캐시를 통째로 못 읽어 왔거나(배선
    # 문제) 사전 생성을 깜빡한 채로 기동해도 콘솔에는 아무 신호가 없었다.
    print(f"여는 대사 캐시 {len(mc_lines)}개 로드됨 ({cache_path()})", flush=True)
    # `docent_min_chars=level.min_chars` — 도슨트 해설의 분량 미달 경고가 수준을
    # 따르게 하는 유일한 배선이다. 감독의 기본값은 `MIN_CHARS`(40)이라 여기서
    # 안 넘기면 일반(180자)·전문가(260자) 목표에 50자짜리 해설이 나와도 로그에
    # 아무것도 안 남는다(전체 리뷰 I1). `Level` 객체째 넘기지 않는 이유는
    # `Director.__init__` 의 `_docent_min_chars` 주석에 있다.
    server = StageServer(
        CueSheet(load_cues()), build_generate(level), expect_units=expect,
        mc_lines=mc_lines, level_name=level.name,
        docent_min_chars=level.min_chars,
    )
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
