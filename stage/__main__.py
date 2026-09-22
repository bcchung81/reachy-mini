"""무대감독 기동 — `python -m stage`.

주소는 전부 환경변수다:
    REACHY_DIRECTOR_HOST   기본 0.0.0.0
    REACHY_DIRECTOR_PORT   기본 8777
    REACHY_MC_UNIT         사회자 로봇의 hardware id (없으면 검증 생략)
    REACHY_DOCENT_UNIT     도슨트 로봇의 hardware id
    REACHY_LLM_URL         추론 서버 (llm.py 의 기본값을 따른다)
    REACHY_CUES_PATH       큐시트 경로 (기본 data/cues.yaml)
    REACHY_AUDIENCE_LEVEL  처음 관람객 수준 — 초등/중고등/일반/전문가 (기본 일반).
                           시연 중에는 콘솔·대시보드 `l <수준>` 으로 바꾼다(다음 큐부터)
    REACHY_LEVELS_PATH     수준 프로필 경로 (기본 data/levels.yaml)
    REACHY_MC_LINES_PATH   여는 대사 사전 생성 캐시 경로 (기본 data/mc_lines.yaml)
    REACHY_DASHBOARD_HOST  기본 127.0.0.1 (망에 열려면 0.0.0.0 — 전용 공유기에서만.
                           빈 값은 모든 망이 되므로 127.0.0.1 로 두고 경고한다)
    REACHY_DASHBOARD_PORT  기본 8778 (틀린 값이면 경고하고 대시보드만 빼고 돈다)
"""

import os
import pathlib
import sys
import threading

from stage.cues import CueSheet, load_cues
from stage.dashboard import DEFAULT_HOST as DASH_HOST
from stage.dashboard import DEFAULT_PORT as DASH_PORT
from stage.dashboard import start_dashboard
from stage.dashboard_hub import DashboardHub, tee
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

    **합쳐도 안 막히는 것이 남는다**: 사회자 이력은(그리고 `HISTORY_MAX` 로
    앞이 잘린 뒤라면 어느 역할이든) 여전히 `assistant` 로 **시작**할 수 있다
    — 위 병합은 연속된 같은 역할만 하나로 묶을 뿐, 이력의 첫 메시지가
    `user` 여야 한다는 규칙은 강제하지 않는다. "첫 메시지는 user" 를 강제하는
    채팅 템플릿이라면 이 모양도 거절할 수 있다. 예전 코드도 같은 모양(첫
    메시지가 assistant)을 보냈고 지금 붙는 서버는 받는다 — 서버가 바뀌면
    실서버 스모크(계획의 "최종 검증 2번")로 다시 확인한다.
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


# 경고에 싣는 잘린 조각의 최대 길이. 넘으면 **가운데를** 줄인다 — 앞만 남기면
# 사회자 받아치기의 질문처럼 **마지막 문장**에 있는 것이 로그에서 빠진다. 그
# 질문이 상한에 잘렸다는 것이, 감독의 "질문 유도가 없다" 경고의 원인을 가르는
# 유일한 단서다(`Director` 의 질문 유도 가드 주석 참고).
_WARN_CLIP = 60


def _clip(s: str, n: int = _WARN_CLIP) -> str:
    if len(s) <= n:
        return s
    half = n // 2
    return s[:half] + "…" + s[-half:]


def _stripped_parts(raw: str, clean: str) -> str:
    """이름표 정리가 **무엇을 걷었는지** — 앞머리에서 뗀 것과 뒤에서 자른 것.

    `strip_speaker_labels` 의 결과는 원문(앞뒤 공백 제거)의 **연속된 부분 문자열**
    이다(앞머리를 떼고 뒤를 자를 뿐 가운데를 고치지 않는다). 그래서 그 위치를
    찾으면 앞뒤로 걷힌 것이 나온다. `find` 는 첫 위치를 준다 — 정리된 텍스트가
    통째로 이름 글자로만 된 병적인 경우("사회자: 사회자")에만 앞뒤 구분이
    어긋나고, 그때도 걷힌 글자 자체는 빠짐없이 보인다. 뒤쪽(상대 턴)에 같은
    문장이 되풀이되는 흔한 경우를 틀리지 않으려고 `rfind` 가 아니라 `find` 다.
    남은 것이 없으면(원문이 이름표뿐) 앞뒤를 가를 수 없으니 통째로 보인다 — 빈
    결과는 감독이 따로 "빈 문자열 — 폴백" 으로 경고한다.
    """
    s = raw.strip()
    if not clean:
        return f"남은 것 없이 전부 걷었다 {_clip(s)!r}"
    i = s.find(clean)
    head, tail = s[:i].strip(), s[i + len(clean):].strip()
    parts = []
    if head:
        parts.append(f"앞에서 뗀 것 {_clip(head)!r}")
    if tail:
        parts.append(f"뒤에서 자른 것 {_clip(tail)!r}")
    return ", ".join(parts)


def build_generate(level, warn: Callable[[str], None] = print) -> "callable":
    """LLM 호출 하나. **직렬화한다.**

    두 화자가 **하나의 대화 이력**을 봐야 말이 이어진다 — B 의 대사는 A 가
    정해진 뒤에야 만들 수 있으므로 병렬이 아니라 파이프라인이다. 그래서
    클라이언트를 역할별로 둬도 락은 하나다.

    이 함수는 **한 수준**의 생성기를 만든다(프롬프트·상한이 수준의 함수라서).
    시연 중 수준을 바꾸면 수준마다 하나씩 생기는데(`LevelSwitch`), 그때 이 락은
    생성기마다 따로다 — 수준을 가로지르는 직렬화는 `LevelSwitch` 의 락이 맡는다.

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
        # 경고는 **걷어낸 부분**을 보여 준다. 예전에는 `raw[:60]`(원문 앞)을 찍어,
        # 상대 턴이 60자 뒤에 붙은 실측 모양(docent:106)에서는 정작 새어 든 부분이
        # 로그에 안 보였다(Task 2 리뷰 #5).
        if stripped:
            warn(
                f"[{role}] 생성문에 화자 이름표/상대 턴이 섞여 걷어냈다 — "
                f"{_stripped_parts(raw, text)}"
            )
        max_sentences, max_chars = limits[role]
        before = text
        text, capped = cap_length(text, max_sentences, max_chars)
        # 원래→잘린 길이와 **잘린 뒷부분**을 함께 찍는다. 상한은 감독의 두 가드보다
        # 앞에 걸린다 — 사회자의 마지막 질문 문장이 잘리면 질문 유도 가드가 "질문
        # 유도가 없다" 고, 첫 문장만 남은 도슨트 해설은 `_warn_if_short` 가 "너무
        # 짧다" 고 경고한다. 원인은 모델이 아니라 상한인데, 이 줄이 무엇을 잘랐는지
        # 말하지 않으면 로그만 보고는 그 둘을 잇지 못한다(Task 2 리뷰). 잘린
        # 뒷부분은 `cap_length` 결과가 원문의 앞부분(접두)이라 뺄셈으로 나온다.
        if capped:
            dropped = before[len(text):].strip()
            warn(
                f"[{role}] 생성문이 분량 상한({max_sentences}문장/{max_chars}자)을 "
                f"넘어 문장 경계에서 잘랐다({len(before)}자→{len(text)}자) — "
                f"잘린 뒷부분 {_clip(dropped)!r}"
            )
        return text

    return generate


class LevelSwitch:
    """관람객 수준별 생성기를 **필요할 때 한 번씩** 만들고, 지금 수준의 것으로 넘긴다.

    시연 중 수준을 바꿀 수 있게 되면서(콘솔·대시보드 `l <수준>`) 생성기 하나로는
    모자라게 됐다 — 페르소나 프롬프트(`build_system_prompt(role, level)`)와 분량
    상한이 수준의 함수라서다. `Director` 에는 이 객체가 `generate` 로, `select` 가
    `on_level_change` 로 간다. 감독이 큐를 시작할 때 대기 수준을 적용하며 `select`
    를 부르고, 그 뒤 띄우는 생성이 새 수준의 생성기를 탄다.

    **`select` 는 대입 하나다.** 감독이 `Director._lock` 을 쥔 채 부르는 훅이라
    (`StageServer._send`·경고 콜백과 같은 규칙) 감독 상태를 읽거나 블로킹하면 안
    된다. 그래서 새 수준 생성기를 거기서 만들지 않는다(페르소나 파일을 읽는다) —
    처음 쓰일 때 생성 스레드에서, 락 밖에서 만든다. 이 객체의 락은 생성 스레드만
    쥔다 — 감독 락과 얽히지 않는다.

    **처음 수준은 기동에서 바로 만든다.** 지금까지의 기동과 같다: 페르소나 파일이
    깨져 있으면 시연 전에 죽는다. 나머지 수준은 고르기 전에는 안 만든다 — 한 번도
    안 쓰는 수준의 클라이언트를 들고 있을 이유가 없다. 늦게 만든 수준에서 페르소나가
    깨져 있으면 그 예외가 감독의 "LLM 생성 실패 — 폴백" 경고로 드러난다(조용하지 않다).

    **호출 전체를 락 하나로 묶는다 — 수준을 가로질러.** `build_generate` 의 직렬화
    락은 생성기마다 따로라, 수준을 바꾼 직후 앞 큐(옛 수준)의 늦은 생성과 새 큐(새
    수준)의 도슨트 해설이 동시에 LLM 에 간다. 앞 것은 어차피 세대 검사로 버려지는데
    새 큐의 임계경로가 그것과 추론 서버를 나눠 쓴다. 한 락으로 두면 "LLM 호출은
    한 번에 하나" 가 수준을 바꿔도 그대로다.

    지금 수준 이름은 **호출 때** 읽는다. 앞 큐가 띄운 생성이 락을 기다리다 새 수준
    생성기로 돌 수는 있다 — 그 결과는 감독이 큐를 시작하며 세 슬롯의 세대를 모두
    올렸으므로 버려진다(`Director._apply_pending_level` 주석).
    """

    def __init__(self, levels: dict, first, build: Callable, warn: Callable[[str], None]) -> None:
        self._levels = levels
        self._build = build
        # 늦게 만드는 생성기도 **같은 경고 출구**(tee)를 받는다 — `build` 의 기본값
        # `print` 로 새면 수준을 바꾼 뒤에만 이름표·분량 상한 경고가 대시보드에서
        # 빠진다(최종 리뷰 Y1 과 같은 자리).
        self._warn = warn
        self._gens = {first.name: build(first, warn=warn)}
        self._name = first.name
        self._lock = threading.Lock()

    def select(self, name: str) -> None:
        """`Director` 의 수준 전환 훅. **대입만 한다** — 위 docstring 참고."""
        self._name = name

    def __call__(self, role: str, brief: str, history: list[dict]) -> str:
        with self._lock:
            name = self._name
            gen = self._gens.get(name)
            if gen is None:
                gen = self._gens[name] = self._build(self._levels[name], warn=self._warn)
            return gen(role, brief, history)


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
    # 수준 **목록**도 이 한 번의 읽기에서 나온다 — 시연 중 전환(`l <수준>`)이 고를 수
    # 있는 이름과 하한, 수준별 생성기의 재료가 다 여기서 간다. 처음 수준은 여전히
    # `REACHY_AUDIENCE_LEVEL` 이다.
    levels = load_levels()
    level = level_of_env(levels)
    announce_level(level, explicit)  # 수준이 잘못됐으면 이미 위에서 죽었다.
    host = os.environ.get("REACHY_DIRECTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("REACHY_DIRECTOR_PORT", "8777"))
    # 허브는 **쌓기만** 한다(`DashboardHub.publish`) — 감독이 락을 쥔 채 부르는
    # 자리(`StageServer._send`, 경고 콜백)에서도 안전하다. `warn` 은 터미널과
    # 허브 양쪽으로 가는 tee — 대시보드가 없거나 죽어 있어도 터미널 경고는
    # 그대로 살고, 대시보드가 붙어 있으면 같은 경고가 화면에도 뜬다.
    #
    # **첫 경고보다 먼저 만든다.** 예전에는 아래 역할 검증 경고가 허브를 만들기
    # 전에 `print` 로 나가 대시보드 이력에 없었다 — 지난 실기 리허설의 역할
    # 뒤바뀜을 막는 검증이 꺼져 있다는 경고인데 운영자 화면에서만 빠졌다(최종
    # 리뷰 Y3). 허브 이력은 대시보드가 나중에 붙어도 `hello` 로 받으므로, 대시보드가
    # 뜨기 전에 낸 경고도 여기 실으면 화면에 보인다. 정보성 출력(수준·캐시 개수)은
    # 경고가 아니라 `print` 그대로다.
    def terminal(m: str) -> None:
        print(m, flush=True)

    hub = DashboardHub()
    warn = tee(terminal, lambda m: hub.publish("warn", text=m))
    expect = {
        k: v
        for k, v in (
            ("mc", os.environ.get("REACHY_MC_UNIT")),
            ("docent", os.environ.get("REACHY_DOCENT_UNIT")),
        )
        if v
    }
    if not expect:
        warn("⚠ REACHY_MC_UNIT / REACHY_DOCENT_UNIT 이 없다 — 역할 검증을 건너뛴다")

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
    #
    # `build_generate` 에도 같은 tee `warn` 을 넘긴다. 기본값(`print`)에 기대면
    # 생성기 경고(화자 이름표를 걷었다·분량 상한에서 잘랐다)만 터미널에 남고
    # 대시보드 이력에서 빠진다(최종 리뷰 Y1) — 감독의 "질문 유도가 없다"·"너무
    # 짧다" 경고는 화면에 뜨는데 그 **원인**인 상한 경고는 안 보이는 꼴이다.
    #
    # **관람객 수준 실시간 전환**(콘솔·대시보드 `l <수준>`, 다음 큐부터). 생성기는
    # 한 수준짜리 `build_generate` 대신 `LevelSwitch` — 처음 수준 것은 여기서 바로
    # 만들고 나머지는 처음 쓸 때 한 번씩 만든다. 감독에는 셋이 같이 가야 한다:
    # 전환기(`generate`), 그것을 돌리는 훅(`on_level_change`), 고를 수 있는 이름과
    # 하한(`level_min_chars`). 하나라도 빠지면 반쪽 전환이다 — 훅이 빠지면 감독이
    # 기동에서 막고, 목록이 빠지면 "모르는 수준" 경고만 뜬다.
    generate = LevelSwitch(levels, level, build_generate, warn=warn)
    server = StageServer(
        CueSheet(load_cues()), generate, expect_units=expect,
        mc_lines=mc_lines, level_name=level.name,
        docent_min_chars=level.min_chars,
        level_min_chars={name: lv.min_chars for name, lv in levels.items()},
        on_level_change=generate.select,
        warn=warn, hub=hub,
    )
    stop = threading.Event()
    threading.Thread(
        target=server.tick_forever, args=(0.5, stop.is_set), daemon=True
    ).start()

    from stage.console import run_console

    srv = server.serve(host, port)
    print(f"무대감독 대기 중 — ws://{host}:{port}")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # `run_console` **앞에** 띄운다 — 콘솔은 표준입력을 막고 버티므로, 뒤에 두면
    # 대시보드가 절대 뜨지 않는다. 이 서버 자신의 `warn` 은 **터미널로만**
    # 낸다(`terminal`, tee 가 아니다) — tee 를 넘기면 대시보드 자신의
    # 실패 경고가 다시 허브를 거쳐 대시보드로 흘러 자기 자신을 부르는 꼴이 된다
    # (`stage/dashboard.py` 머리 docstring과 같은 이유).
    #
    # **포트 값이 틀려도 감독은 죽지 않는다.** 예전에는 `int(...)` 의 ValueError 가
    # 여기서 새어 기동이 통째로 죽었다(최종 리뷰 Y4) — 곁다리 화면의 오타 하나로
    # 시연이 못 뜬다. 값을 보여 주고 대시보드만 뺀다. 기본 포트로 **몰래 바꾸지
    # 않는다**: 주소는 환경변수가 권위다 — 운영자는 적은 포트로 열려 하는데 다른
    # 포트에 떠 있으면 "대시보드가 안 뜬다" 로만 보인다. 범위 밖 숫자(99999)는
    # `start_dashboard` 가 같은 모양으로 경고하고 None 을 준다. 경고는 터미널로만 —
    # 대시보드가 없으니 허브에 실어도 볼 화면이 없다.
    dash = None
    raw_port = os.environ.get("REACHY_DASHBOARD_PORT", str(DASH_PORT))
    try:
        dash_port = int(raw_port)
    except ValueError:
        terminal(
            f"⚠ REACHY_DASHBOARD_PORT 가 포트 번호가 아니다({raw_port!r}) — 대시보드를 "
            "띄우지 않는다(기본 포트로 바꾸지 않는다). 감독과 콘솔은 그대로 돈다"
        )
    else:
        # 빈 값(`REACHY_DASHBOARD_HOST=`)은 `get(…, 기본값)` 을 지나 `serve("", …)` 에 닿고,
        # 빈 호스트는 **모든 인터페이스**에 바인드된다 — 인증 없는 제어 화면이 빈 값 하나로
        # 망에 열린다. 위험한 쪽을 기본으로 두지 않는다(설계 결정 1): 루프백으로 두고 알린다.
        # 포트와 달리 여기서는 바꾼다 — 빈 값은 "아무 주소" 가 아니라 "안 정했다" 로 읽는 게 맞고,
        # 바꾸는 방향이 더 좁은 쪽이다.
        dash_host = os.environ.get("REACHY_DASHBOARD_HOST", DASH_HOST)
        if not dash_host.strip():
            terminal(
                f"⚠ REACHY_DASHBOARD_HOST 가 비어 있다 — 빈 값은 모든 망에 여는 것이라 "
                f"{DASH_HOST}(노트북에서만)로 띄운다. 망에 열려면 0.0.0.0 을 적는다"
            )
            dash_host = DASH_HOST
        dash = start_dashboard(
            hub, server.director,
            dash_host,
            dash_port,
            camera=server.camera,
            warn=terminal,
        )
    try:
        run_console(server.director, camera=server.camera)
    finally:
        stop.set()
        srv.shutdown()
        if dash is not None:
            dash.shutdown()


if __name__ == "__main__":
    main()
