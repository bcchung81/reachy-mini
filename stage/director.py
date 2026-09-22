"""무대감독 — 턴·대사·마이크를 중계한다.

**전송을 모른다.** `send(role, command)` 콜러블만 받는다. 그래서 종단 흐름
전체가 소켓 없이 테스트된다. WebSocket 배선은 `stage/__main__.py` 가 한다.

LLM 호출을 여기서 독점한다 — 사회자와 도슨트가 **하나의 대화 이력**을 봐야
말이 이어지기 때문이다. TTS 는 로봇에 남는다(목소리가 달라야 한다).
"""

import threading
import time
from typing import Callable, NamedTuple

from stage.cues import (
    ADVANCE_HINT,
    QA_ACK_LINES,
    QUESTION_PROMPTS,
    Cue,
    CueSheet,
    invites_question,
    is_advance,
    mentions_advance,
)
from stage.machine import SPEAKING, Command, State, TurnError, TurnMachine, coalesce
from stage.mc_cache import cache_key
from stage.protocol import ROLES

# 발화 길이 추정치. 실측(2026-09-11, Qwen3-TTS 1.7B CustomVoice, 배속 1.0):
#   34자 → 7.04초 (4.8자/초),  57자 → 10.64초 (5.4자/초),  25자 → 4.00초 (6.3자/초)
# 타임아웃은 **일찍 터지면 안 되므로** 가장 느린 쪽보다 더 보수적으로 잡는다.
CHARS_PER_SEC = 4.0

# **여유분은 합성 지연을 덮는 몫이다 — 재생 길이가 아니다.**
#
# 감독은 로봇이 언제 실제로 소리를 내기 시작했는지 모른다. 로봇은
# `speaker.speak()` 가 **큐에 넣고 돌아온 직후** `speaking_started` 를 보내는데
# (`tts.Speaker.speak` → `_enqueue`, `_speaking` 플래그가 적재 시점에 선다)
# TTS 합성은 그 **뒤**에 일어난다. 그래서 `on_speaking_started` 의 데드라인
# 재설정으로도 합성 지연은 빠지지 않는다 — 이 상수가 그 몫을 통째로 진다.
#
# 예전 값 5.0 은 그 몫을 감당하지 못했다. Qwen3-TTS 첫 합성은 Metal 커널
# JIT 로 **8.5초**가 걸리고(`scripts/warmup.py` 실측), 예열을 건너뛴 첫 큐에서
# 계산하면:
#
#   짧은 전환   12자   예산  8.0초   필요 10.7초   ❌ 터진다
#   사회자 대사  34자   예산 13.5초   필요 14.7초   ❌ 터진다
#   긴 해설     57자   예산 19.2초   필요 18.9초   ✓ (아슬아슬)
#
# 짧은·중간 길이가 대부분이므로 예열을 빠뜨리면 **거의 확실히** 헛타임아웃이
# 난다. 그러면 `force_listening` 이 리스너 마이크를 열고, 직후 로봇이 말을
# 시작해 사회자가 그것을 관람객 발화로 받아적는다 — 불변식 ① 이 막으려던
# 자기목소리 루프가 타임아웃 경로로 되살아난다. 운영자가 기억해야 하는 절차
# (예열)만으로 막기에는 너무 얇은 방어선이다.
#
# 10.0 이면 위 세 경우가 다 통과하지만 여유가 1초뿐이다. **15.0** 은 같은
# 상수 하나짜리 변경이면서 틀릴 여지를 남긴다. 타임아웃이 늦게 터지는 비용은
# "멈춘 것을 늦게 알아챈다" 뿐이고(운영자가 콘솔 `a`/`r` 로 즉시 복구한다),
# 일찍 터지는 비용은 자기목소리 루프다 — 비대칭이 크다.
#
# ⚠️ 이것은 **임시 방어선**이다. 구조적으로 옳은 고침은 로봇이 **첫 오디오
# 시점에** `speaking_started` 를 보내게 해서 이 여유분을 합성 지연이 아니라
# 재생 지터만 덮는 값으로 되돌리는 것이다. 그 선택지와 폐기한 대안(하트비트)
# 은 `docs/real-robot-deployment.md` §15.4 에 적어 두었다.
TIMEOUT_MARGIN_S = 15.0

# 도슨트 대사 생성이 사회자 발화보다 늦어질 때 더 기다려 줄 한도.
GENERATE_GRACE_S = 8.0

# 섹션 끝에서 관람객 질문을 기다리는 시간. 넘으면 다음 섹션으로 간다.
#
# 예전에는 기한이 없었다 — 마이크만 열린 채 관람객이 **"다음" 이라는 낱말을
# 알아야** 시연이 진행됐고(`is_advance`), 관람객은 그 규칙을 모른다. 사회자가
# 말로 묻고(`QUESTION_PROMPTS`), 그래도 조용하면 여기서 스스로 넘어간다.
#
# **비대칭이라 넉넉한 쪽으로 잡는다.** 짧으면 말을 꺼내려던 관람객을 자르는데
# 그건 회복이 안 된다(사람이 무안해서 다시 입을 열지 않는다). 길면 정적이
# 흐를 뿐이고 운영자가 콘솔 `n` 으로 즉시 넘긴다.
QUESTION_WAIT_S = 8.0

# 대화 이력 상한(줄 수). 큐시트가 19섹션이고 그 위에 관람객 질문이 얹히므로
# 상한이 없으면 시연이 진행될수록 프롬프트가 계속 커진다 — TTFT 가 늘고,
# 컨텍스트 창을 넘기면 **앞이 조용히 잘려 나간다**(무엇이 잘렸는지 아무도
# 모른다). 최근 것만 남기는 편이 예측 가능하다. 6턴 남짓이면 "방금 무슨
# 얘기를 했는가" 에는 충분하다 — 그보다 먼 맥락은 `docent_brief` 가 준다.
HISTORY_MAX = 12

# 관람객 질문에 LLM 이 답을 못 만들었을 때 도슨트가 하는 말.
QA_FALLBACK = "죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?"

# 이보다 짧은 생성 결과는 해설이 아니다. 경고만 하고 그대로 쓴다 — 버리면
# 정적이 되는데 그게 더 나쁘다. ~~목표 분량은 Task 3 에서 수준 프로필로 올라간다.~~
#
# **이제 갈린다 — 도슨트만 수준을 따른다.**
#
# 받아치기(`role="mc"`)에는 계속 이 값이 걸린다 — 우연이 아니라 같은 수치다.
# `stage/prompts.py::_MC_MIN_CHARS` 가 사회자에게 "40~120자" 를 **수준과 무관하게**
# 주므로(해설하지 않는 역할이라 분량이 수준을 따르지 않는다), 40자 미만은 사회자
# 프롬프트를 모델이 안 지켰다는 뜻이다. 받아치기에 도슨트 분량을 따로 얹을 필요가
# 없는 이유이기도 하다 — 역할별 분량은 프롬프트 쪽에 이미 갈려 있다.
#
# 반면 도슨트(`role="docent"`: 해설·질문 응답)의 하한은 `Director.__init__` 의
# `docent_min_chars` 로 들어온다(`stage/__main__.py` 가 `level.min_chars` 를
# 넘긴다). 이 값이 40으로 고정이던 동안에는 일반(하한 180자)·전문가(260자)에서
# **50자짜리 해설이 나와도 경고가 한 줄도 없었다** — 설계 §5·§10 이 요구한
# "목표 범위에 한참 못 미치면 경고" 가 절반만 돌았다(전체 리뷰 I1). 여기 남은
# 40은 이제 "사회자 몫" 과 "배선이 안 닿았을 때의 안전한 기본값" 둘 다다.
MIN_CHARS = 40

# 이력에 남길 화자 접두. 이력은 **하나**이고 접두로 화자를 가른다(설계 §5.2).
# `_who()` 가 돌려주는 "실제로 말한 로봇" 이 아니라 **역할**로 적는다 — 1인 모드
# 에서 사회자 한 대가 양쪽을 읽어도 이력에는 "도슨트:" 가 남아야 대화가 이어진다.
SPEAKER_LABEL = {"mc": "사회자", "docent": "도슨트"}

# 폴백이 **무엇인지** 로그에 적는 이름. 사다리 2단(예비)과 3단(큐시트)이 같은
# 문구로 찍히면 `./reachy.sh logs` 로 "예비가 산 섹션" 과 "예비까지 죽은 섹션" 을
# 못 가른다 — 둘은 전혀 다른 문제다(앞은 LLM 이 한 번 늦은 것, 뒤는 사회자 쪽
# 생성이 통째로 안 도는 것).
FB_BRIEF = "도슨트 지시문"
FB_QA = "질문 응답 사과문"
FB_SPARE = "예비 받아치기"
FB_SHEET = "큐시트 받아치기"

# 폴백인데도 **진짜 생성 결과**인 것. 예비만 그렇다 — 큐시트 원문·지시문·사과문은
# 사람이 쓴 문장이라 길이를 재지 않지만(MIN_CHARS 경고가 헛돈다) 예비는 LLM 이
# 낸 대사라 짧으면 짧다고 말해야 한다.
_GENERATED_FALLBACKS = frozenset({FB_SPARE})

# 운영 모드(설계 `docs/superpowers/specs/2026-09-21-launch-and-modes-design.md` §1-2).
# **순서가 곧 페이지 버튼 순서다**(`mode_names` → 대시보드 hello `modes`). 처음 값은
# 언제나 첫째(팟캐스트)다 — 지금 운영 흐름(운영자가 시작을 누를 때까지 대기)을 그대로
# 둔다. 스펙의 `REACHY_MODE`(처음 모드를 환경변수로)는 1단계에서 뺐다: 단독을 켤 로봇이
# 아직 없어(`caps` 를 보내는 앱이 4단계) 켜 봐야 거절될 값이다.
#
#   podcast — 큐시트를 따라 사회자·도슨트가 주고받는다(지금까지의 전부).
#   solo    — 사회자 한 대가 관람객 질문에 답한다. 감독은 진행하지 않는다(`s`·`n`·`p`·
#             `r`·`g` 거절). 1단계에는 로봇에게 알리는 일도 없다 — 4단계에서 `mode`
#             지시가 붙는다(`set_mode` 의 주석 자리).
MODES = ("podcast", "solo")


class _Pending(NamedTuple):
    """`on_speaking_ended` 가 락을 놓고 기다릴 **한 건**.

    튜플 위치로 들고 다니다 `slot`/`role` 을 서로 바꿔 넣는 사고가 이 저장소에
    이미 있었다(대장 「값이 같은 두 인자를 서로 바꿔도 안 잡힌다」). 이름을 붙여
    두면 그 자리가 아예 없어진다 — 6칸이 되면서 더 그렇다.
    """

    slot: str            # 어느 슬롯의 세대를 기다리는가(밀어내기·세대 검사의 단위)
    role: str            # 어느 페르소나로 말할 것인가(`stage/prompts.py`)
    cue_id: str          # 내보낼 발화의 id(`:docent`/`:qa`/`:after`)
    fallback: str        # 생성이 늦거나 실패했을 때 읽을 것
    fallback_kind: str   # 그 폴백이 무엇인지(로그용, 위 FB_* 중 하나)
    label: str           # 경고에 찍을 이름


class UnitMismatch(RuntimeError):
    """로봇이 신고한 hardware id 가 기대값과 다르다 — 두 대가 뒤바뀌었다."""


class Director:
    def __init__(
        self,
        sheet: CueSheet,
        generate: Callable[[str, str, list[dict]], str],
        send: Callable[[str, Command], None],
        now: Callable[[], float] = time.monotonic,
        expect_units: dict[str, str] | None = None,
        warn: Callable[[str], None] = print,
        mc_lines: dict[str, str] | None = None,
        level_name: str = "일반",
        docent_min_chars: int = MIN_CHARS,
        level_min_chars: dict[str, int] | None = None,
        on_level_change: Callable[[str], None] | None = None,
    ) -> None:
        self._sheet = sheet
        self._generate = generate
        self._send = send
        self._now = now
        self._expect_units = expect_units or {}
        self._warn = warn
        # 여는 대사 사전 생성 캐시(`scripts/pregen_mc_lines.py` 가 채운다)와
        # 그것을 찾을 수준. 둘 다 `stage/__main__.py::main()` 에서 한 번만
        # 읽어 `StageServer` → `Director` 로 흘러온다 — 여기서 기본값(빈
        # dict·"일반")으로 두는 것은 오직 테스트 편의를 위해서다. 실기
        # 기동에서 이 값이 안 흘러오면(배선을 빠뜨리면) 캐시는 늘 비고
        # 수준은 늘 "일반" 으로 굳어 이 태스크 전체가 무효가 된다.
        self._mc_lines = mc_lines or {}
        self._level_name = level_name
        # 도슨트 발화의 분량 하한(`level.min_chars`). **수준 프로필 전체(`Level`)
        # 를 받지 않는 이유**: 이 생성자가 테스트 수십 곳에 퍼져 있어 객체로
        # 바꾸면 그 전부가 같이 흔들린다. 감독이 수준에서 실제로 쓰는 것은 이
        # 수 하나뿐이라 수 하나만 받는다(이름은 `_level_name` 과 같은 결이다).
        # 사회자 몫은 이 값을 쓰지 않는다 — 위 `MIN_CHARS` 주석 참고.
        #
        # ~~기동 때 한 번 정해지고 바뀌지 않는다.~~ 2026-09-21부터 `_level_name` 과
        # 함께 **큐를 시작할 때** 바뀔 수 있다(`set_level` → `_apply_pending_level`).
        self._docent_min_chars = docent_min_chars

        # **관람객 수준 실시간 전환**(콘솔·대시보드 `l <수준>`). 셋이 한 묶음이다:
        #   `_level_min_chars` — 고를 수 있는 수준 이름 → 도슨트 하한(levels.yaml 순서).
        #                        dict 순서가 곧 페이지 버튼 순서다(`level_names`).
        #   `_on_level_change` — 생성기(역할·수준별 페르소나)를 그 수준으로 바꾸는 훅.
        #                        `stage/__main__.py::LevelSwitch.select` 가 온다.
        #   `_level_pending`   — 다음 큐부터 적용할 이름. 없으면 None.
        #
        # 목록을 안 받으면 **지금 수준 하나만** 아는 감독이다(기존 호출부·테스트 그대로).
        # 수준 프로필 전체가 아니라 이름 → 하한만 받는 이유는 위 `_docent_min_chars`
        # 와 같다 — 감독이 수준에서 쓰는 것이 이 수 하나뿐이다.
        self._level_min_chars = (
            dict(level_min_chars) if level_min_chars else {level_name: docent_min_chars}
        )
        # **반쯤 끊긴 배선을 기동에서 막는다.** 대장 「`Director` 생성자 인자를 늘려도
        # 배선 두 단계를 같이 안 고치면 늘 기본값으로 죽는다」 그대로의 자리다. 목록만
        # 흘러오고 훅이 빠지면 `l` 이 받아들여져 브리프·캐시 키·하한은 새 수준으로
        # 가는데 생성기는 옛 수준 페르소나로 남는다 — 초등 지시문을 전문가 말투로
        # 해설하는데 경고는 "바꿨다" 뿐이라 아무도 모른다.
        if len(self._level_min_chars) > 1 and on_level_change is None:
            raise ValueError(
                "관람객 수준 목록을 받았는데 생성기 전환 훅(on_level_change)이 없다 — "
                "수준을 바꿔도 생성기가 옛 수준으로 남는다"
            )
        if level_name not in self._level_min_chars:
            raise ValueError(
                f"지금 관람객 수준 {level_name!r} 이 수준 목록에 없다: "
                f"{list(self._level_min_chars)}"
            )
        # 목록이 하나뿐이면 `set_level` 이 대기를 만들 수 없으므로(모르는 이름이거나
        # "이미 그 수준") 아무것도 안 하는 훅이 불릴 일도 없다.
        self._on_level_change = on_level_change or (lambda name: None)
        self._level_pending: str | None = None

        self._machine = TurnMachine()
        self.history: list[dict] = []

        self._deadline: float | None = None
        # 관람객 질문을 기다리는 기한. **`_deadline` 과 절대 섞지 않는다.**
        #
        # 둘은 뜻도 복구 동작도 다르다. `_deadline` 은 "말하라고 보냈는데
        # 끝났다는 보고가 안 온다"(고장)라 `force_listening` 으로 **복구**하고
        # "응답이 없다" 고 경고한다. 이쪽은 "관람객이 조용하다"(정상)라 다음
        # 섹션으로 **진행**하고 경고하지 않는다. 한 필드로 합치면 침묵할
        # 때마다 로그에 "발화 종료 응답이 없다" 가 찍혀, 시연 중 로그를 보는
        # 사람이 로봇이 먹통이 된 줄 안다 — 게다가 진짜 타임아웃 복구가
        # 관람객 침묵에 밀려 안 돈다.
        self._question_deadline: float | None = None
        # 방금 보낸 `say` 에 준 시간 예산. `speaking_started` 가 오면 그 시점을
        # 기준으로 데드라인을 다시 건다 — `__init__` 아래 on_speaking_started
        # 참고.
        self._speak_budget: float = 0.0
        # 생성 슬롯 — **이름으로 나뉜다.** 예전에는 하나뿐이라 "한 턴에 생성은
        # 하나" 였는데, 사회자 받아치기가 도슨트 해설과 동시에 살아 있어야 해서
        # 나눴다. 슬롯이 하나면 나중에 띄운 생성이 앞선 생성을 밀어내고, 밀려난
        # 쪽은 세대 검사에 걸려 통째로 버려진다 — 받아치기를 만들었더니 해설이
        # 사라지는 식이다.
        #
        # 한 칸은 네 항목이다:
        #   text        — 생성 결과(또는 폴백)
        #   is_fallback — 그 `text` 가 **진짜 생성 결과**인지, `_generate_pending`
        #                 이 빈 문자열·예외를 만나 이미 폴백으로 갈아치운 것인지.
        #                 이 표시가 없으면 `_await_pending` 의 MIN_CHARS 검사가
        #                 폴백 문자열에도 걸려 "생성 실패" 경고 뒤에 "생성 결과가
        #                 짧다" 는 **틀린** 경고가 덧붙는다(QA_FALLBACK 은 37자,
        #                 MIN_CHARS 는 40) — 로그만 보면 LLM 이 37자짜리 답을 낸
        #                 것으로 오판한다.
        #   ready       — 이 세대의 결과가 들어왔음을 알리는 이벤트
        #   token       — 세대 번호. 슬롯마다 따로 센다. 하나로 뭉쳐 두면 한
        #                 슬롯을 가는 것만으로 다른 슬롯의 진행 중인 생성까지
        #                 세대가 어긋나 버려진다.
        #
        # 지금 쓰는 슬롯은 셋이다:
        #   "docent"      — 도슨트 해설과 질문 응답(둘 다 도슨트가 이어서 말할 자리)
        #   "after_spare" — 받아치기 **예비**. 섹션 시작에 도슨트 *지시문*만 보고 만든다.
        #   "after"       — 받아치기 **실제**. 도슨트가 *실제로 한 말*을 보고 만든다.
        # 예비와 실제를 **다른 슬롯**에 둔 이유: 같은 슬롯 안에서는 "마지막 하나만
        # 산다"(`_spawn_generate` 가 `text` 를 비우고 세대를 올린다). 한 칸에 담으면
        # 실제를 띄우는 순간 예비가 지워져, 실제가 늦을 때 쓰려던 여유분이 사라진다
        # — 예비 생성이 통째로 죽은 LLM 호출이 된다.
        self._slots: dict[str, dict] = {}
        self._ack_i = 0   # 질문 확인 멘트를 돌아가며 쓰는 커서
        self._q_i = 0     # 생성된 받아치기에 붙일 질문 유도를 돌아가며 쓰는 커서
        # 슬롯을 읽고 쓰는 락. "세대 확인 + 결과 반영"을 한 번에 묶어 그 사이에
        # `_spawn_generate` 가 끼어드는 경합을 막는다. 슬롯이 여럿이어도 락은
        # **하나로 둔다** — 쥐는 구간이 딕셔너리 한 칸을 읽고 쓰는 정도라 쪼갤
        # 이득이 없고, 쪼개면 `self._lock` → `_gen_lock` 한 방향뿐이던 락 순서가
        # 슬롯 수만큼 갈래를 늘려 교착을 따지기 어려워진다.
        self._gen_lock = threading.Lock()

        # 진입점 직렬화. `stage/server.py` 가 붙은 뒤로는 `tick()` 이 타이머
        # 스레드에서, 나머지는 커넥션마다 다른 스레드에서 불린다. 이 락이
        # 없으면: tick() 이 데드라인 만료를 판정한 직후(`_deadline`/
        # `speaking_role` 을 아직 안 건드린 시점), 커넥션 스레드가
        # 사회자→도슨트 핸드오프를 통째로 끝내 상태를 옮긴 뒤, tick() 이
        # 이어서 `force_listening()` 을 불러 **도슨트가 말하는 도중** 사회자
        # 마이크를 강제로 연다 — 불변식 ① 위반이다. `force_listening()` 이
        # 부르는 `TurnMachine._to_listening()` 은 현재 상태를 재확인하지
        # 않는 무조건 전이라 이 경합을 스스로 막지 못한다. 게다가 그 강제
        # 전이가 `speaking_role`/`cue_id` 를 리셋해 버려서, 도슨트의 진짜
        # `speaking_ended` 가 나중에 도착하면 유령 메시지로 조용히 버려진다
        # — 도슨트 발화가 타임아웃 보호를 통째로 잃는다.
        #
        # 공개 진입점(`start`/`on_hello`/`on_heard`/`on_speaking_ended`/
        # `on_error`/`tick`/`abort`) 을 전부 이 락으로 직렬화하면 "만료 판정
        # → 강제 전이"가 원자적이 된다 — 세 문제(마이크 오픈, 엉뚱한 로봇을
        # 지목하는 경고, 유령 처리된 진짜 종료)가 한 번에 없어진다. 어느
        # 공개 메서드도 다른 공개 메서드를 부르지 않으므로(전부 `_begin_cue`
        # 등 내부 헬퍼만 거친다) 재진입이 필요 없어 일반 Lock 으로 충분하다.
        # 모드 전환(`set_mode`)이 말하던 것을 멈출 때도 공개 `abort()` 가 아니라
        # 락 안의 몸체 `_abort_locked()` 를 부른다 — 이 규칙을 깨면 그 자리에서 교착이다.
        #
        # ~~`_speak_docent()` 의 유예시간(`GENERATE_GRACE_S`, 최대 8초) 대기는
        # 이 락을 쥔 채로 일어난다 — 그동안 tick() 은 막힌다. 의도한 동작이다:
        # 사회자→도슨트 핸드오프가 진행 중일 때는 애초에 아무것도 타임아웃돼서는
        # 안 된다.~~ **2026-09-20 되돌림.** 그 보호는 이미 바로 위의
        # `self._deadline = None` 이 하고 있었다 — 락이 거기에 더한 일은
        # **운영자의 비상정지를 막는 것**뿐이었다. 큐 19개마다, 그리고 관람객
        # 질문마다 한 번씩 콘솔 `a`/`n` 이 최대 8초 먹지 않았다. 지금은
        # `on_speaking_ended()` 가 대기 전에 이 락을 놓고, 깨어난 뒤 상태와
        # 세대 토큰을 다시 보고 얹는다.
        #
        # 생성 스레드(`_generate_pending`)는 이 락을 절대 요구하지 않는다 —
        # `_gen_lock` 만 짧게 쥐었다 놓는다. 두 락을 겹쳐 잡는 자리는
        # `self._lock` → `_gen_lock` **한 방향뿐**이라(교착 없음) 대기 구간에서
        # 세대를 확인할 때도 그 순서를 지킨다.
        self._lock = threading.Lock()

        self._connected: set[str] = set()
        # 역할 검증(`on_hello`)에 실패한 로봇. 비어 있지 않으면 `start()` 를 거절한다.
        self._rejected: set[str] = set()

        # 운영 모드(`MODES`). `set_mode` 만 바꾼다.
        self._mode = "podcast"
        # 역할 → 그 로봇 앱이 hello 로 알린 능력(`caps`, 예: {"solo"}). **끊기면 지운다**
        # (`on_disconnect`) — 안 지우면 단독을 아는 앱이 나가고 모르는 앱이 다시 붙어도
        # 옛 능력이 남아 단독이 켜진다. 지금 로봇 앱은 `caps` 를 안 보내 늘 빈 집합이다.
        self._caps: dict[str, set[str]] = {}
        # 대기모드에 들어간 역할. 새 상태기계를 만들지 않는다 — `solo_role` 이 이 값을
        # 보므로, 대기 진입은 그 로봇이 "끊겼다" 와 같은 모양으로 진행에서 빠진다
        # (재배정·마이크 재동기화까지 `on_disconnect` 와 같은 길을 탄다). 끊기면 지운다
        # (`_caps` 와 같은 수명 — 다시 붙는 앱은 새로 판단한다).
        self._standby: set[str] = set()

    # ── 상태 ──────────────────────────────────────────────────────
    @property
    def state(self) -> State:
        return self._machine.state

    @property
    def solo_role(self) -> str | None:
        """진행에 쓸 수 있는 로봇이 한 대뿐이면 그 역할. 둘이거나 없으면 None.

        **연결됐지만 대기모드인 로봇은 빼고 센다** — 대기 진입이 "끊겼다" 와 같은 모양으로
        진행에서 빠지게 하는 지점이 여기 하나다. 이것은 **1인 모드**(한 대가 없을 때 남은
        한 대가 양쪽 대사를 읽는 폴백)다 — 운영 모드 `solo`(단독, `mode`/`set_mode`)와
        이름만 닮았지 다른 것이다.
        """
        active = self._connected - self._standby
        if len(active) == 1:
            return next(iter(active))
        return None

    @property
    def rejected(self) -> frozenset[str]:
        return frozenset(self._rejected)

    @property
    def mode(self) -> str:
        """지금 운영 모드(`MODES` 중 하나). 읽기 전용 — 바꾸는 길은 `set_mode` 하나다.

        락을 잡지 않는다: 문자열 한 칸의 대입·읽기는 원자적이고, 다른 값과 **한 시점으로**
        묶어 봐야 하는 쪽(대시보드)은 `snapshot()` 이 락 안에서 읽는다.
        """
        return self._mode

    def mode_names(self) -> list[str]:
        """고를 수 있는 운영 모드 — 페이지 버튼 순서. 바뀌지 않으므로 락이 필요 없다
        (`level_names` 와 같다). 감독이 받아들이는 이름과 버튼 이름이 한 곳에서 나온다."""
        return list(MODES)

    def reject(self, role: str, reason: str) -> None:
        """역할 검증에 실패한 로봇. 맞는 로봇이 붙기 전에는 시연을 시작하지 않는다.

        서버가 `on_hello` 의 `UnitMismatch` 를 받아 여기로 넘긴다. 예전에는 그
        예외가 핸들러 밖으로 새어 websockets 로거의 traceback 만 2초마다
        반복됐고, 감독의 경고 채널에는 아무것도 없어 `s` 로 뒤바뀐 로봇과
        시연을 시작할 수 있었다(리뷰 A4).
        """
        with self._lock:
            self._rejected.add(role)
            self._warn(f"[{role}] 거부됨 — {reason} 맞는 로봇이 붙기 전에는 시작하지 않는다")

    def on_connect(self, role: str) -> None:
        # `server.py::handler` 가 커넥션 스레드에서 부르는 새 공개 진입점이다.
        # 다른 공개 메서드 안에서(`_who()` 를 통해서든) 이걸 부르지 않으므로
        # `self._lock` 을 또 쥐어도 재진입 걱정이 없다 — `_connected` 를
        # 커넥션 스레드 여럿이 동시에 건드리는 경합만 막으면 된다.
        with self._lock:
            self._connected.add(role)
            # **마이크 상태를 다시 준다.** 갓 붙은 앱의 게이트는 닫혀 있다. 감독이
            # LISTENING 인데 리스너가 다시 붙었으면 마이크를 열어 줘야 관람객
            # 창구가 산다 — 안 그러면 앱 재기동/WiFi 순단 뒤 아무도 안 듣는데
            # 경고도 없다(리뷰 A5a). `mic` 지시는 멱등이라 다시 보내도 안전하다.
            self._emit(self._resync_mic(role))

    def on_disconnect(self, role: str) -> None:
        with self._lock:
            self._connected.discard(role)
            # 능력은 **그 연결의** 것이다 — 다시 붙는 앱은 새 hello 로 다시 알린다.
            self._caps.pop(role, None)
            self._standby.discard(role)
            # 4단계: 단독 모드(`self._mode == "solo"`)에서 사회자가 끊기면 어떻게 할지 정한다.
            # 지금은 모드가 solo 로 남고(`solo_available` 만 꺼진다) 아래 경고가 "1인 모드로
            # 내려간다 — 도슨트가 양쪽 대사를 읽는다" 라고 찍히는데, 단독에는 읽을 대사가
            # 없어 오해를 부른다. 1단계에서는 단독에 들어갈 로봇이 없어 닿지 않는 자리다.
            if self.solo_role is not None:
                self._warn(
                    f"[{role}] 이 끊겼다 — 1인 모드로 내려간다. "
                    f"{self.solo_role} 가 양쪽 대사를 읽는다"
                )
                if self._machine.state is State.LISTENING:
                    # 끊긴 쪽이 리스너였을 수 있다 — 남은 로봇에게 창구를 넘긴다.
                    # 안 그러면 LISTENING 인데 아무 마이크도 안 열린 채 데드라인도
                    # 없어 감독이 영영 기다린다(리뷰 A5a).
                    self._emit(self._machine.force_listening(self._who("mc")))

    def _resync_mic(self, role: str) -> list[Command]:
        """이 로봇이 지금 가져야 할 마이크 상태 — 리스너이고 듣는 중일 때만 연다."""
        open_ = self._machine.state is State.LISTENING and role == self._who("mc")
        return [Command(to=role, type="mic", fields={"open": open_})]

    def _who(self, preferred: str) -> str:
        """대사를 읽을 로봇. 1인 모드면 남은 한 대가 전부 읽는다."""
        solo = self.solo_role
        return solo if solo is not None else preferred

    # ── 로봇에게서 오는 것 ────────────────────────────────────────
    def on_hello(
        self, role: str, unit_id: str | None, version: str,
        caps: list[str] | None = None,
    ) -> None:
        """역할 자기신고. 두 대가 뒤바뀐 채 시연을 시작하는 것을 여기서 막는다.

        `caps` 는 그 로봇 앱이 할 줄 아는 것(선택 필드, 예: `["solo"]`). 없으면 빈 목록 —
        지금 로봇 앱은 보내지 않는다(4단계 앱이 보낸다). 형식 검사는 서버가 한다.
        """
        with self._lock:
            expected = self._expect_units.get(role)
            # **거절을 먼저 가른다 — 그래야 caps 를 한 자리에서 기억할 수 있다.**
            # 예전 순서(기대값 없음 → 반환, unit_id 없음 → 반환, 다르면 예외)에 caps 를
            # 끼우면 조기 반환 두 갈래마다 따로 적어야 하고, 하나를 빠뜨리면 그 갈래
            # (시뮬은 늘 `unit_id is None` 이다)의 사회자는 단독을 영영 못 켠다. 거꾸로
            # 맨 앞에 두면 `UnitMismatch` 로 거절된 로봇(붙은 적이 없다 — 서버가 그
            # 연결만 닫는다)이 자리에 남은 맞는 로봇의 능력을 덮는다.
            if expected is not None and unit_id is not None and unit_id != expected:
                raise UnitMismatch(
                    f"{role} 자리에 다른 로봇이 있다: 기대 {expected!r}, 신고 {unit_id!r}. "
                    "사회자와 도슨트가 뒤바뀌었는지 확인한다."
                )
            # hello 마다 **갈아끼운다**(합치지 않는다) — 같은 자리에 옛 앱이 다시 인사하면
            # 그 앱이 모르는 능력이 남으면 안 된다.
            self._caps[role] = set(caps or ())
            if expected is None:
                return
            if unit_id is None:
                # 시뮬(macOS)에서는 언제나 None 이다 — get_hardware_id() 가 리눅스
                # sysfs 를 읽는다. 여기서 막으면 실기 없이 개발할 수 없다.
                self._warn(f"[{role}] unit_id 가 없다 — 실기라면 확인할 것 (시뮬은 정상)")
                return
            self._rejected.discard(role)   # 맞는 로봇이 붙었다 — 거부를 푼다

    def on_heard(self, text: str) -> None:
        with self._lock:
            if self._machine.state is not State.LISTENING:
                self._warn(f"발화 중({self._machine.state.value})에 들린 말을 버린다: {text!r}")
                return
            # 관람객이 입을 열었다 — 침묵이 아니다. 아래 두 갈래는 대개 곧바로
            # 발화로 넘어가고 `tick()` 의 침묵 갈래는 LISTENING 일 때만 보지만,
            # **LISTENING 에 그대로 머무는 갈래가 실제로 있다**: 마지막 큐에서
            # 진행 신호를 받으면 `_next_locked()` 가 "마지막 큐다" 만 경고하고
            # 상태를 안 바꾼다. 그때 기한이 살아 있으면 8초 뒤 같은 경고가
            # 한 번 더 찍힌다 — 상태 검사에만 기대면 이런 자리가 조용히 는다.
            self._question_deadline = None
            if is_advance(text):
                # 관람객이 넘겨 달라고 **말했다** — 마지막 큐라 못 넘기면 알려준다.
                self._next_locked(quiet_if_last=False)
                return
            self._answer(text)

    def on_speaking_started(self, role: str, cue_id: str, seq: int | None) -> None:
        """발화 시작 보고. **데드라인을 여기서 다시 건다.**

        예전에는 `say` 를 보낸 순간부터 시간을 셌다. 그 사이에 든 시간
        (전송, 로봇의 수신 루프가 밀린 시간, 앱이 바쁜 시간)이 전부 발화
        예산을 깎아먹어, 로봇이 **말을 시작하기도 전에** 데드라인이 터질 수
        있었다. 그러면 `force_listening` 이 리스너 마이크를 열고, 그 직후
        로봇이 말을 시작해 사회자가 그것을 관람객 발화로 받아적는다 —
        불변식 ① 이 막으려던 자기목소리 루프가 타임아웃 경로로 되살아난다.

        ⚠️ **남은 구멍**: 로봇은 `speaker.speak()` 가 큐에 넣고 돌아온
        직후에 이것을 보낸다(`main.py` 의 speak_one). TTS 합성 자체는 그
        뒤에 일어나므로, 모델이 차가워 첫 합성이 오래 걸리는 경우는 이
        재설정으로 덮이지 않는다 — `TIMEOUT_MARGIN_S` 가 그 몫이다.
        (`docs/real-robot-deployment.md` 의 2대 구성 잔여 위험)
        """
        with self._lock:
            if not self._machine.is_current(role, cue_id, seq):
                self._warn_ghost("speaking_started", role, cue_id, seq)
                return
            self._deadline = self._now() + self._speak_budget

    def _warn_ghost(self, kind: str, role: str, cue_id: str, seq: int | None) -> None:
        """유령 보고를 **소리 내서** 버린다 — 두 종류의 경고문이 따로 놀지 않게 한 곳에."""
        self._warn(
            f"[{role}] 유령 {kind}({cue_id!r}, seq={seq}) — 지금 말하는 것은 "
            f"{self._machine.speaking_role}/{self._machine.cue_id!r}/seq={self._machine.seq} 다. 버린다"
        )

    def on_speaking_ended(self, role: str, cue_id: str, seq: int | None) -> None:
        """발화 종료 보고. 도슨트 몫으로 넘어갈 때는 **락을 놓고** 생성을 기다린다.

        기다리는 동안에도 콘솔 `a`/`n`, tick, 재접속이 살아 있어야 한다 — 그 대기가
        최대 `GENERATE_GRACE_S` 라 락을 쥔 채로는 비상정지가 그만큼 먹통이 된다.
        대신 깨어난 뒤 **세상이 그대로인지 다시 확인**하고 얹는다(상태 + 세대 토큰).
        """
        with self._lock:
            # 관람객 창구를 열어줄 로봇도 `_who()` 로 정한다 — 1인 모드에서
            # 리스닝으로 넘어갈 때 마이크를 열어야 할 대상은 "사회자" 가
            # 아니라 "남은 한 대" 다. 여기서 고정값을 쓰면(review finding
            # 1인 모드 두 번째 라운드) 사회자가 끊긴 도슨트 1인 모드에서
            # 어느 로봇의 마이크도 열리지 않아 관람객 창구가 아예 없어진다.
            cmds = self._machine.on_speaking_ended(role, cue_id, self._who("mc"), seq=seq)
            if not cmds:
                # 유령 메시지 — 상태를 건드리지 않는다. 하지만 **조용히
                # 버리지도 않는다**: 여기에 걸리는 진짜 종료 보고가 있다면
                # (타임아웃이 먼저 터져 `speaking_role` 을 리셋해 버린 경우가
                # 대표적이다) 그 로봇의 발화가 통째로 타임아웃 보호를 잃은
                # 것이고, 그 사실이 로그에 없으면 추적할 수 없다.
                # seq 불일치도 여기로 온다 — 콘솔 `r` 뒤 중단된 발화의 늦은
                # 보고가 그것이다(리뷰 A2). 그것은 버려지는 것이 맞다.
                self._warn_ghost("speaking_ended", role, cue_id, seq)
                return
            self._deadline = None
            # **침묵 기한도 여기서 끊는다 — 유령 검사 아래에서.**
            #
            # 왜 끊는가: 아래 갈래 중 셋은 곧바로 다음 대사를 내보내지만, 그
            # 사이 `_await_pending` 이 락을 놓고 최대 `GENERATE_GRACE_S` 동안
            # 기다리는데 그동안 상태는 **LISTENING 이다**. 이전 섹션 끝에
            # 걸어 둔 기한이 그때 만료되면 `tick()` 이 "침묵이다" 로 읽고
            # 다음 섹션을 시작해 버린다 — 관람객은 조용한 적이 없는데 해설이
            # 통째로 건너뛰어진다. 쉬러 들어가는 갈래(아래 `else`)가 그 자리에서
            # 새로 건다.
            #
            # 왜 유령 검사 **아래**인가: 늦게 도착한 유령 `speaking_ended`
            # (콘솔 `r` 뒤의 중단된 발화 등)가 관람객을 기다리는 기한을 꺼
            # 버리면, 그 뒤로는 침묵이 아무리 길어도 자동 진행이 안 된다.
            self._question_deadline = None

            # 큐 id 만으로 "사회자 몫이 방금 끝났다" 를 판정한다 — role 은
            # 안 본다. 도슨트 몫에는 아래에서 `f"{cue.id}:docent"` 처럼 구분되는
            # id 를 붙이므로(§ 리뷰 finding 1), 맨 cue.id 는 두 모드 어디서든
            # 사회자 몫에만 붙는다. 1인 모드에서는 같은 로봇이 두 몫을 연달아
            # 말하므로 role 로는 구분이 안 된다 — role 로 갈랐다가 도슨트 몫이
            # 끝난 뒤에도 다시 도슨트 몫을 트리거해 자기 대사를 무한 반복하는
            # 버그가 났었다.
            cue = self._sheet.current()
            # 도슨트 해설을 내보낼 때 **실제 반응**(받아치기) 생성을 띄울 큐.
            # 해설 갈래에서만 세운다 — `:qa`(질문 응답) 뒤에는 받아치지 않으므로
            # 그 자리에서 생성을 띄우면 아무도 안 읽는 LLM 호출만 남는다.
            after_of: Cue | None = None
            if cue_id == cue.id:
                # 수준별 브리프를 쓴다(계획 보완 Step 5b) — 옛 `cue.docent_brief`
                # 를 그대로 두면 여기 폴백만 수준을 안 따라, 사전 생성이 늦어
                # 유예시간을 넘길 때마다 초등이든 전문가든 같은 문장이 나간다.
                pending = _Pending(
                    "docent", "docent", f"{cue.id}:docent",
                    cue.brief_for(self._level_name)[1], FB_BRIEF, cue.id,
                )
                if cue.mc_after:
                    after_of = cue
            elif cue_id == f"{cue.id}:ack":
                # 확인 멘트가 끝났다 — 그동안 만든 답을 도슨트가 말한다.
                # 그 답이 끝나면 아래 `:qa` 갈래가 사회자에게 한 번 더 묻게 한다.
                pending = _Pending(
                    "docent", "docent", f"{cue.id}:qa",
                    QA_FALLBACK, FB_QA, f"{cue.id}:qa",
                )
            elif cue_id == f"{cue.id}:qa":
                # **도슨트 답이 끝났다 — 사회자가 짧게 다시 묻는다.**
                #
                # 예전에는 여기서 곧장 LISTENING 으로 갔다. 마이크는 열리지만
                # 사회자가 아무 말도 안 하므로, 관람객은 자기 차례인지 다음
                # 질문을 해도 되는지 알 수 없다 — 받아치기(`:after`)가 창구를
                # 말로 열어 주는 것과 같은 이유로 여기도 말이 필요하다(리뷰 B2).
                # 이 발화가 끝나야 LISTENING 으로 가고 침묵 기한이 걸린다.
                #
                # **여기서는 생성하지 않는다.** 고정 문장이라 지연이 0 이다.
                # 질문마다 LLM 을 한 번 더 띄우면 답을 들은 관람객이 다음
                # 물음을 꺼내기까지 몇 초를 더 기다려야 하는데, 이 자리에서
                # 얻는 것(말투의 다양성)보다 잃는 것(반응 지연)이 크다.
                # 같은 말이 반복되면 녹음처럼 들리므로 돌아가며 쓴다.
                prompt = QUESTION_PROMPTS[self._q_i % len(QUESTION_PROMPTS)]
                self._q_i += 1
                # 이력에도 남긴다 — 다음 생성이 "사회자가 방금 질문을 권했다"
                # 를 못 보면 받아치기·해설이 같은 권유를 또 한다.
                self._remember(f"사회자: {prompt}")
                self._emit(
                    cmds
                    + self._machine.speak(
                        self._who("mc"), f"{cue.id}:reask", prompt, gaze="audience"
                    )
                )
                return
            elif cue_id == f"{cue.id}:docent" and cue.mc_after:
                # **받아치기.** 도슨트 뒤 사회자가 짧게 받고 관람객 창구를 말로
                # 연다 — 마이크가 열려도 관람객은 그것을 모른다(리뷰 B2, 설계
                # §4.1 의 "DOCENT_SPEAKING → MC_SPEAKING(받아치기)"). coalesce 가
                # 방금 열린 마이크를 도로 닫는다(사회자→도슨트 전환과 같은 모양).
                #
                # 이 갈래도 **해설과 같은 길**(락을 놓고 기다렸다가 다시 본다)을
                # 탄다. 고정 대사를 그 자리에서 읽던 예전과 달리, 도슨트가 실제로
                # 한 말을 보고 만든 반응을 기다려야 하기 때문이다.
                #
                # 폴백 사다리는 셋이다: 실제 → 예비 → 큐시트. 예비(`after_spare`)는
                # 도슨트 대사를 보낼 때 실제와 나란히 띄웠으므로, 도슨트가 말한
                # 7~8초 동안 둘 다 돌았다 — 준비된 것만 가져온다(`_slot_text` 는
                # 기다리지 않는다). 없으면 큐시트 원문이다.
                spare = self._slot_text("after_spare")
                pending = _Pending(
                    "after", "mc", f"{cue.id}:after",
                    spare or cue.mc_after,
                    FB_SPARE if spare else FB_SHEET,
                    f"{cue.id}:after",
                )
            else:
                # 기다릴 것이 없는 갈래는 여기서 끝난다 — 락을 놓지 않는다.
                # **여기가 관람객 차례다**(받아치기·다시 묻기가 끝났거나 받아치기
                # 없는 큐의 해설이 끝났다). 마이크가 열리는 바로 그 자리에서
                # 침묵 기한을 건다 — 말로 물어 놓고 아무도 답하지 않으면
                # `tick()` 이 다음 섹션으로 넘긴다.
                self._question_deadline = self._now() + QUESTION_WAIT_S
                self._emit(cmds)
                return

            # 기다릴 이벤트와 세대를 **락 안에서** 찍어 둔다. 대기 중
            # `_spawn_generate` 가 슬롯을 갈아끼워도 우리는 우리 세대의 결과를
            # 기다린 뒤 아래 검사에서 물러난다. 겹쳐 잡는 순서는 언제나
            # `self._lock` → `_gen_lock` 이다.
            ready, token = self._snapshot_slot(pending.slot)
            # 마지막 큐인지도 **여기서** 찍는다 — 아래 관람객 창구 안내가 '다음'
            # 을 붙일지 정할 때 쓴다. 대기 중에 커서가 움직일 수 있으므로 판단
            # 근거는 이 순간의 것이어야 한다.
            is_last = self._sheet.done
            # **여기서는 아무것도 내보내지 않는다.** `cmds` 의 마이크 열기 지시는
            # 2구간에서 도슨트의 닫기와 한 번에 나가 coalesce 가 덮는다 — 그래야
            # 핸드오프 사이에 마이크가 깜빡이지 않는다. 취소되면 통째로 버린다
            # (끼어든 쪽이 이미 제 지시를 내보냈다).

        text = self._await_pending(pending, ready, token)

        with self._lock:
            if self._machine.state is not State.LISTENING:
                # abort 가 대표적이다 — 운영자가 멈췄는데 늦게 끝난 생성이
                # 뒤늦게 입을 열면, 멈춘 줄 아는 사람 앞에서 로봇이 말한다.
                self._warn(
                    f"[{pending.label}] 기다리는 사이에 {self._machine.state.value} 로 "
                    "바뀌었다 — 이 대사는 얹지 않는다"
                )
                return
            # 세대 재확인도 **찍었던 그 슬롯**을 본다. 다른 슬롯의 세대가 올라간
            # 것은 이 대사와 무관하다 — 뭉뚱그려 보면 멀쩡한 해설이 버려진다.
            # 슬롯 이름을 `pending` 에 실어 온 이유가 이것이다: 여기에 "docent" 를
            # 박아 두면 받아치기 갈래가 **남의 슬롯 세대**와 자기 토큰을 비교해,
            # 멀쩡한 받아치기가 매번 "다음 턴으로 넘어갔다" 며 버려진다.
            _, current_token = self._snapshot_slot(pending.slot)
            if token != current_token:
                # 상태만으로는 못 잡는 틈이다: 대기 중 다음 큐가 시작되고 그
                # 사회자 발화까지 끝나면 상태가 **다시 LISTENING** 이 된다.
                # 그대로 얹으면 이전 섹션 해설이 나가고, 뒤이어 새 큐의
                # 핸드오프가 불변식 ② 로 TurnError 를 맞는다.
                self._warn(
                    f"[{pending.label}] 기다리는 사이에 다음 턴으로 넘어갔다 — 이 대사는 버린다"
                )
                return
            if pending.slot == "after" and text != cue.mc_after:
                # 큐시트 원문으로 물러난 경우는 건드리지 않는다 — 그것은 데이터
                # 테스트가 이미 안내를 못박은 **안전한** 문장이고(마지막 큐의
                # 마무리 인사처럼 일부러 '다음' 을 뺀 것도 있다), 거기에 또 붙이면
                # 사람이 다듬어 둔 대사를 감독이 망친다. 예비를 읽은 경우는
                # **생성물이라** 검사를 받는다 — 예비도 LLM 출력이다.
                text = self._ensure_visitor_cue(text, pending.label, is_last)
            self._remember(f"{SPEAKER_LABEL[pending.role]}: {text}")
            if after_of is not None:
                self._spawn_after(after_of, text)
            # 역할은 **여기서 다시 정한다.** 기다리는 사이에 상대가 끊겼으면 남은
            # 한 대가 읽어야 한다(설계 §7). 1구간의 판단을 들고 가면 이미 끊긴
            # 로봇에게 보내고, 전송 계층은 "아직 붙지 않았다" 경고만 남기고 버린다
            # — 상태기계는 그 로봇이 말하는 중이라 믿으므로 `speaking_ended` 가
            # 영영 오지 않고 tick 타임아웃까지 정적이 된다.
            self._emit(
                cmds
                + self._machine.speak(
                    self._who(pending.role), pending.cue_id, text, gaze="audience"
                )
            )

    def _spawn_after(self, cue: Cue, docent_text: str) -> None:
        """받아치기 두 벌을 **여기서 나란히** 띄운다 — 도슨트 대사를 보내는 순간에.

        **왜 섹션 시작(`_begin_cue`)이 아닌가.** `stage/__main__.py::build_generate`
        는 LLM 호출 **전체를 락 하나로 직렬화**한다(역할별 클라이언트를 둬도 락은
        하나다 — 두 화자가 하나의 이력을 보는 파이프라인이라 그렇다). 그래서
        `_begin_cue` 에서 도슨트 해설과 예비를 연달아 띄우면 둘이 같은 락을
        노리는데, 파이썬 `Lock` 은 FIFO 가 아니라 **예비가 먼저 잡으면 도슨트
        해설 생성이 사회자 대사 한 벌만큼 통째로 밀린다.** 도슨트의 예산은 여는
        대사 재생 + `GENERATE_GRACE_S` 8초뿐이고, 넘기면 폴백이 `docent_brief`
        라 **도슨트가 지시문을 소리 내어 읽는다** — 이 작업이 숨기려던 지연을
        이 작업이 임계경로에 새로 만드는 꼴이었다(리뷰 Important 1).
        여기서는 도슨트 해설 생성이 이미 끝나 있으므로 임계경로와 다투지 않고,
        도슨트가 말하는 7~8초가 두 생성의 시간을 산다.

        **예비를 먼저 띄운다.** 프롬프트가 짧아(지시문 vs 도슨트 발언 전문) 더
        빨리 끝나므로, 실제가 늦거나 터졌을 때 여유분으로 준비돼 있을 확률이 는다.

        호출부가 `_remember` **뒤에** 부른다 — 생성 스레드는 `list(self.history)`
        를 찍어가므로, 먼저 띄우면 사회자가 방금 나간 해설을 못 본 채 반응을 만든다.
        """
        _, docent_brief = cue.brief_for(self._level_name)
        # 받아치기 **예비** — 도슨트 지시문만 보고 만든다. 실제가 늦거나 터질 때의
        # 여유분이다(폴백 사다리 2단).
        #
        # slot="after_spare" / role="mc" — **다른 축이다.** 슬롯은 "어느 자리의
        # 생성인가", role 은 "어느 페르소나로 말할 것인가" 다. role 이 "mc" 라서
        # `stage/prompts.py` 가 사회자 분량(1~3문장·40~120자, 수준과 무관하게
        # 고정)을 준다 — 받아치기가 저절로 짧게 나오는 것이 그 덕이다.
        self._spawn_generate(
            "after_spare", "mc",
            f"도슨트가 이런 해설을 할 것이다: {docent_brief}. "
            "짧게 받고 관람객에게 질문을 권한다.",
            cue.mc_after, f"{cue.id}:after-예비",
        )
        # 받아치기 **실제** — 도슨트가 방금 한 말을 보고 만든다. 이게 제시간에
        # 오면 이것을 쓴다(사다리 1단).
        self._spawn_generate(
            "after", "mc",
            f"도슨트가 방금 이렇게 말했다: {docent_text}. "
            "짧게 받고 관람객에게 질문을 권한다.",
            cue.mc_after, f"{cue.id}:after",
        )

    def on_error(self, role: str, where: str, detail: str) -> None:
        with self._lock:
            self._warn(f"[{role}] {where} 에서 오류: {detail}")

    # ── 바깥에서 부르는 것 ────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            if self._refused_in_solo("시작"):
                return
            if self._rejected:
                raise TurnError(
                    f"거부된 역할이 있다: {sorted(self._rejected)} — "
                    "로봇을 바꿔 걸고 다시 붙인 뒤 시작한다"
                )
            self._begin_cue(self._sheet.current())

    def next(self) -> None:
        """다음 큐로 간다 — 콘솔 `n` 과 관람객의 진행 신호가 **같은 길**을 탄다.

        예전 콘솔 `n` 은 `on_heard("다음")` 을 흉내냈다. 그러면 `is_advance` 의
        조정이 콘솔을 끊고, LISTENING 이 아니면(`a` 로 멈춘 뒤, 발화 중) "발화
        중(idle)에 들린 말을 버린다" 는 엉뚱한 경고와 함께 아무 일도 안 일어난다
        — 운영자가 망가진 섹션을 건너뛸 길이 없었다(리뷰 A7b).
        """
        with self._lock:
            if self._refused_in_solo("다음"):
                return
            self._next_locked(quiet_if_last=False)

    def _next_locked(self, *, quiet_if_last: bool) -> None:
        """다음 큐로 간다. **마지막 큐에서 무엇을 할지는 부른 쪽이 정한다.**

        `quiet_if_last` 에 기본값을 두지 않는다 — 세 호출부가 각자 뜻을 밝히게
        강제한다. 기본값을 두면 나중에 생긴 호출부가 배선을 빠뜨린 채 조용히
        돌아(대장 「기본값 있는 인자는 배선이 끊겨도 조용히 돈다」) 경고 정책이
        한쪽으로 새어 나간다.

        - `False`(콘솔 `n`, 관람객의 "다음"): **누가 넘겨 달라고 했는데 못 넘겼다.**
          요청한 사람에게 알려줘야 한다.
        - `True`(침묵 자동 진행): 마지막 큐에서의 침묵은 **시연이 끝났다**는 뜻이다.
          완전 정상 종료라 경고할 것이 없다 — 여기에 경고를 달면 19-closing 이
          끝나고 8초 뒤 **매 시연마다** 찍혀서, 이 파일이 아끼는 진짜 신호
          (`_ensure_visitor_cue` 의 "질문 유도가 빠졌다" 같은 것)가 그 안에 묻힌다.
        """
        if self._machine.state in SPEAKING:
            raise TurnError(
                f"{self._machine.speaking_role} 가 아직 말하는 중이다 — 먼저 a 로 멈춘다"
            )
        nxt = self._sheet.advance()
        if nxt is None:
            if not quiet_if_last:
                self._warn("마지막 큐다 — 더 진행할 곳이 없다")
            return
        self._begin_cue(nxt)

    def previous(self) -> None:
        """이전 큐로 되돌려 다시 진행한다 — 수동 오버라이드(설계 §7).

        오인식으로 섹션이 넘어가 버렸을 때 되돌리는 유일한 길이다. 콘솔이
        `abort()` 로 먼저 멈춘 뒤 부르므로(대개 잘못 시작된 대사가 흐르는
        중이다) 여기서 상태를 따로 건드리지 않는다 — 발화 중이면 `speak()`
        가 불변식 ② 로 거절하고, 콘솔이 그 거절을 사람에게 보여준다.
        """
        with self._lock:
            if self._refused_in_solo("이전"):
                return
            prev = self._sheet.back()
            if prev is None:
                self._warn("첫 큐다 — 더 되돌릴 곳이 없다")
                return
            self._begin_cue(prev)

    def goto(self, cue_id: str) -> None:
        """지정한 큐로 가서 처음부터 진행한다 — 대시보드 런다운의 이동(수동 오버라이드).

        콘솔 `g` 가 `n`·`p`·`r` 처럼 먼저 `abort()` 한다. **커서를 옮기기 전에
        거절한다**: `previous()` 는 커서를 먼저 옮긴 뒤 `_begin_cue` 에서 거절당해
        커서만 움직인 채 남을 수 있는데, 이 메서드에는 그 틈을 만들지 않는다.

        **모르는 id 를 발화 여부보다 먼저 본다.** 콘솔 `g` 는 id 를 모르면 시연을
        멈추지 않고(오타 한 번이 발화를 끊으면 안 된다) 여기로 넘겨 경고만 받는다
        — 순서가 반대면 말하는 도중의 오타가 "먼저 a 로 멈춘다" 는 엉뚱한 거절로
        나가고 무엇을 잘못 쳤는지는 아무 데도 안 남는다. 둘 다 상태를 건드리기
        전에 끝나므로 순서를 바꿔도 "커서를 옮기기 전에 거절" 은 그대로다.
        """
        with self._lock:
            # 모르는 id 검사보다도 **먼저** 본다 — 단독에서는 어느 id 든 이동하지 않으므로
            # "모르는 큐다" 보다 "지금은 진행하지 않는다" 가 운영자에게 맞는 답이다.
            if self._refused_in_solo("이동"):
                return
            i = self._sheet.find(cue_id)
            if i is None:
                self._warn(f"모르는 큐다: {cue_id!r} — 이동하지 않는다")
                return
            if self._machine.state in SPEAKING:
                raise TurnError(
                    f"{self._machine.speaking_role} 가 아직 말하는 중이다 — 먼저 a 로 멈춘다"
                )
            self._begin_cue(self._sheet.seek(i))

    def set_level(self, name: str) -> None:
        """관람객 수준을 바꾼다 — **다음 큐부터**(콘솔·대시보드 `l <수준>`).

        사용자 결정(2026-09-21): 지금 큐는 원래 수준으로 끝까지 간다. 여기서 바로
        바꾸면 사회자는 옛 수준 브리프로 연 큐를 도슨트가 새 수준 브리프·페르소나로
        해설해 한 큐 안에서 수준이 섞인다(해설 폴백·받아치기 예비가 이 큐 도중에도
        `_level_name` 을 본다). 적용은 `_begin_cue` 한 곳에서만 한다 — 바로 적용하려면
        운영자가 `r` 을 누른다(= abort + start, 역시 `_begin_cue`).

        **발화 중에도 거절하지 않는다.** 적용이 다음 큐라 지금 발화를 건드리지 않는다
        — 콘솔 `n`·`g` 처럼 `abort()` 를 먼저 부를 이유도 없다.

        결과는 전부 경고 한 줄로 남긴다(바꿈·취소·이미·모름). 운영자 화면(대시보드
        로그)과 터미널에 같은 줄이 가야 "누가 언제 수준을 바꿨나" 를 로그로 따라간다.
        """
        with self._lock:
            if name not in self._level_min_chars:
                # 오타 한 번이 시연을 흔들면 안 된다 — 경고만. 고를 수 있는 것을 같이
                # 보여 줘야 운영자가 그 자리에서 다시 친다.
                self._warn(
                    f"모르는 관람객 수준이다: {name!r} — 바꾸지 않는다"
                    f"(고를 수 있는 것: {', '.join(self._level_min_chars)})"
                )
                return
            if name == self._level_name:
                if self._level_pending is not None:
                    # 대시보드에서 적용된 버튼을 다시 누른 것 — "되돌리기" 로 읽는다.
                    self._warn(
                        f"관람객 수준 {self._level_name} → {self._level_pending} 대기를 "
                        f"취소했다 — {self._level_name} 그대로 간다"
                    )
                    self._level_pending = None
                else:
                    self._warn(f"관람객 수준은 이미 {name} 이다 — 바꿀 것이 없다")
                return
            self._level_pending = name
            self._warn(
                f"관람객 수준 {self._level_name} → {name} — 다음 큐부터 적용(바로 하려면 r)"
            )

    def level_names(self) -> list[str]:
        """고를 수 있는 관람객 수준 이름 — levels.yaml 순서(페이지 버튼 순서).

        기동 뒤 바뀌지 않으므로 락이 필요 없다(`cue_list` 와 같다). 대시보드가 파일을
        따로 읽지 않고 여기서 받는 이유: 감독이 받아들이는 이름과 버튼 이름이 한 곳에서
        나와야 한다 — 따로 읽으면 `REACHY_LEVELS_PATH` 하나로 둘이 갈린다.
        """
        return list(self._level_min_chars)

    def set_mode(self, name: str) -> None:
        """운영 모드를 바꾼다 — 콘솔·대시보드 `m <모드>`(설계 §1-2).

        결과는 전부 경고 한 줄로 남긴다(바꿈·거절·이미·모름) — `set_level` 과 같은 이유로
        운영자 화면(대시보드 로그)과 터미널에 같은 줄이 가야 "누가 언제 모드를 바꿨나" 를
        로그로 따라간다. 문구는 페이지와의 계약이라 여기 한 곳에만 둔다(콘솔은 넘기기만).

        **단독은 사회자가 붙어 있고 그 앱이 `caps` 에 "solo" 를 알렸을 때만** 받는다.
        단독은 사회자 한 대가 관람객에게 답하는 모드라, 그 앱이 모르는 채로 감독만
        단독이 되면 진행은 멈췄는데 아무도 답하지 않는 정적이 된다 — 1단계의 지금
        로봇 앱은 `caps` 를 보내지 않으므로 단독은 늘 여기서 거절된다.
        """
        with self._lock:
            if name not in MODES:
                # 오타 한 번이 시연을 흔들면 안 된다 — 경고만, 고를 수 있는 것을 같이.
                self._warn(
                    f"모르는 모드다: {name!r} — 바꾸지 않는다"
                    f"(고를 수 있는 것: {', '.join(MODES)})"
                )
                return
            if name == self._mode:
                self._warn(f"이미 {name} 모드다 — 바꿀 것이 없다")
                return
            if name == "solo":
                refusal = self._solo_refusal_locked()
                if refusal is not None:
                    self._warn(refusal)
                    return
            # **말하던 것을 먼저 멈춘다 — 락 안에서, 내부 구현으로.** 공개 `abort()` 를
            # 여기서 부르면 `threading.Lock` 이 재진입을 안 받아 그 자리에서 영영 멈춘다
            # (`__init__` 의 `self._lock` 주석). 락을 놓고 부르면 그 틈에 다른 스레드가
            # 새 큐를 시작해, 모드는 단독인데 팟캐스트 발화가 흐르는 채로 남을 수 있다.
            #
            # 멈추면 IDLE 이다. 그래서 단독에서는 관람객의 "다음"(`on_heard`)도 침묵 자동
            # 진행(`tick`)도 따로 막지 않는다 — 둘 다 LISTENING 에서만 진행하는데, 진행
            # 명령(`start`·`next`·`previous`·`goto`)이 가드에 막혀 단독에서는 LISTENING 이
            # 될 길이 없다. 늦게 온 `speaking_ended` 는 멈춘 발화의 것이라 유령으로
            # 버려지고, 생성을 기다리던 핸드오프는 깨어나 IDLE 을 보고 물러난다.
            # (`test_듣는_중에_단독으로_바꾸면_침묵_자동_진행도_관람객의_다음도_진행하지_않는다`)
            self._abort_locked()
            old, self._mode = self._mode, name
            # 4단계: 여기서 로봇에게 mode 를 보낸다(앱이 단독 루프로 전환)
            self._warn(f"모드를 {old} → {name} 로 바꿨다")

    def toggle_standby(self, role: str) -> None:
        """대기모드 on/off — 콘솔·대시보드 `z <역할>`.

        새 상태기계를 만들지 않는다: `solo_role` 판정이 `connected - standby` 를 보므로,
        대기 진입은 그 역할이 "끊겼다" 와 같은 모양으로 진행에서 빠진다(재배정·마이크
        재동기화까지 `on_disconnect` 와 같은 자리에서 일어난다).

        **전환은 항상 먼저 멈춘다**(`set_mode` 와 같은 패턴, `_abort_locked()`) — 그 역할이
        지금 말하는 중인지 따로 검사하지 않는다(부분 중단이라는 새 개념을 만들지 않는다).
        상대 로봇이 말하던 줄도 함께 끊긴다 — `set_mode` 가 이미 받아들인 트레이드오프와 같다.

        **말하는 중 마이크가 열려 있던 로봇이 대기로 들어가도 그 마이크를 따로 닫지
        않는다** — `on_disconnect` 도 안 닫는다(같은 이유: `speak()` 가 다음 큐에서 양쪽을
        닫고, 그 전에는 서버의 리스너 검사(`solo_role` 아니면 `heard` 를 버린다)가 이미
        막는다). 대칭을 깨지 않는다.
        """
        with self._lock:
            if role not in ROLES:
                self._warn(f"모르는 역할이다: {role!r} — 대기모드를 바꾸지 않는다")
                return
            entering = role not in self._standby
            if entering:
                active_after = (self._connected - self._standby) - {role}
                if not active_after:
                    self._warn(
                        f"[{role}] 를 대기모드로 두면 진행할 로봇이 없다 — 바꾸지 않는다"
                    )
                    return
            self._abort_locked()
            if entering:
                self._standby.add(role)
            else:
                self._standby.discard(role)
            self._warn(f"[{role}] 대기모드 {'진입' if entering else '해제'}")
            self._emit([Command(to=role, type="standby", fields={"on": entering})])
            if self.solo_role is not None and self._machine.state is State.LISTENING:
                self._emit(self._machine.force_listening(self._who("mc")))

    def _solo_refusal_locked(self) -> str | None:
        """지금 단독을 켤 수 **없는** 이유(경고 문구 그대로). 켤 수 있으면 None.
        **`self._lock` 을 쥔 채** 부른다.

        `set_mode("solo")` 의 거절과 스냅샷의 `solo_available` 이 **이 한 곳**을 본다.
        두 자리에 같은 식을 따로 적으면 한쪽만 고쳐졌을 때 페이지의 단독 버튼은 켜졌는데
        누르면 거절되거나(또는 그 반대) — 화면과 감독이 어긋나도 둘 다 제 테스트는 통과한다.
        """
        if "mc" not in self._connected:
            return "단독 모드를 켤 수 없다 — 사회자 로봇이 붙어 있지 않다"
        if "solo" not in self._caps.get("mc", ()):
            return (
                "단독 모드를 켤 수 없다 — 사회자 로봇 앱이 단독 모드를 아직 모른다"
                "(로봇 앱 업데이트 뒤에 켜진다)"
            )
        return None

    def _refused_in_solo(self, what: str) -> bool:
        """단독이면 팟캐스트 진행 명령을 거절하고 True. **`self._lock` 을 쥔 채** 부른다.

        진행 명령 네 곳(`start`·`next`·`previous`·`goto`)의 **맨 앞**에서 부른다 — 다른
        검사(거부된 역할·발화 중·모르는 큐)보다 먼저여야 단독에서 누른 `s`·`n`·`p`·`g`·
        `r` 이 엉뚱한 사유("말하는 중이다" 등)로 거절되지 않는다. `a`(중단)·`l`(수준)·
        `m`(모드)은 단독에서도 된다(설계 §1-2).
        """
        if self._mode != "solo":
            return False
        self._warn(f"단독 모드에서는 팟캐스트 진행({what})을 하지 않는다 — 먼저 m podcast")
        return True

    def cue_list(self) -> list[dict]:
        """런다운용 큐 목록. 큐시트는 기동 뒤 바뀌지 않으므로 락이 필요 없다.

        **키가 둘인 이유**: `title` 은 `load_cues` 가 비어 있지 않은 문자열로
        강제하는 짧은 이름(“해상무선통신”)이라 런다운 한 줄에 맞는다. `topic` 은
        스펙의 `hello.cues: [{id, title, topic}]` 계약 키이고, 큐시트에서는 조사 주제
        문장(최대 50자 남짓)이다 — 둘은 다른 값이라 하나로 합치지 않는다.

        **`topic` 이 비면 `title` 로 채운다.** `topic` 은 큐시트의 **선택** 필드라
        (`load_cues` 가 빠지면 `""` 로 둔다) 그대로 주면 런다운·헤더에 빈 칸이
        생긴다 — 운영자가 어느 큐인지 못 읽는다. 품질이 떨어지는 폴백이 아니라
        스키마가 허용한 상태를 표시하는 방법이므로 경고하지 않는다(대시보드가
        붙을 때마다 부르므로 경고를 달면 접속마다 같은 줄이 찍힌다).
        """
        return [
            {"id": c.id, "title": c.title, "topic": c.topic or c.title}
            for c in self._sheet.cues()
        ]

    def snapshot(self) -> dict:
        """대시보드가 그릴 현재 상태 — **락을 잠깐 쥐고** 한 시점의 값을 모은다.

        ⚠️ 감독이 락을 쥔 채 부르는 자리(`StageServer._send`, 경고 콜백)에서
        부르면 교착이다(`threading.Lock` 은 재진입이 안 된다). 대시보드 서버의
        펌프 스레드가 락 밖에서 주기적으로 부른다.

        침묵 남은 시간은 **LISTENING 일 때만** 준다 — `abort()` 는 발화 기한만
        끄므로 멈춘 뒤에도 `_question_deadline` 이 남을 수 있는데, 그 값은
        `tick()` 이 LISTENING 에서만 보므로 실제로는 안 걸린 기한이다.
        """
        with self._lock:
            wait = None
            if (
                self._question_deadline is not None
                and self._machine.state is State.LISTENING
            ):
                wait = max(0.0, self._question_deadline - self._now())
            return {
                "cue_index": self._sheet.index,
                "cue_id": self._sheet.current().id,
                "cue_count": len(self._sheet.cues()),
                "state": self._machine.state.value,
                "speaking_role": self._machine.speaking_role,
                "question_wait_s": wait,
                "question_wait_total_s": QUESTION_WAIT_S,
                "connected": sorted(self._connected),
                "solo_role": self.solo_role,
                "standby": sorted(self._standby),
                "rejected": sorted(self._rejected),
                # `level` 은 지금 **적용된** 수준(이 큐가 도는 수준), `level_pending` 은
                # 다음 큐부터 적용될 수준(없으면 None). 페이지는 둘을 다르게 칠한다.
                "level": self._level_name,
                "level_pending": self._level_pending,
                # 운영 모드와 **단독을 지금 켤 수 있는가**. 뒤의 것은 `set_mode("solo")` 의
                # 거절과 같은 판정(`_solo_refusal_locked`)을 쓴다 — 페이지가 단독 버튼을 켜
                # 놓았는데 누르면 거절되는 어긋남이 없게. 사회자가 끊기면 꺼진다.
                "mode": self._mode,
                "solo_available": self._solo_refusal_locked() is None,
            }

    def tick(self) -> None:
        """기한 감시. 서버 루프가 주기적으로 부른다. **기한은 두 종류다.**

        진입 락 아래에서 판정과 전이를 한 번에 묶는다 — 그렇지 않으면
        판정 직후 다른 스레드가 핸드오프를 끝내고, 그 뒤에야 이 메서드가
        옛 데드라인을 근거로 방금 말을 시작한 로봇의 마이크를 강제로 연다
        (불변식 ① 위반. `__init__` 의 `self._lock` 주석 참고).

        둘을 `elif` 로 가르는 이유: 발화 기한이 살아 있다는 것은 누군가 말하는
        중이라는 뜻이라 관람객 침묵을 따질 자리가 아니다. 지금은 아래 갈래가
        상태까지 보므로 `if` 두 개로 써도 같게 돌지만, 그러면 "복구하자마자
        같은 tick 이 섹션을 넘길 수도 있다" 를 **상태 검사 하나에만** 맡기게
        된다 — 우선순위를 제어흐름에 박아 두면 그 검사를 나중에 누가 느슨하게
        고쳐도 고장 복구가 섹션 건너뛰기로 둔갑하지 않는다.
        """
        with self._lock:
            if self._deadline is not None and self._now() >= self._deadline:
                role = self._machine.speaking_role
                self._warn(f"[{role}] 발화 종료 응답이 없다 — 강제로 듣기 상태로 되돌린다")
                self._deadline = None
                # 복구로 열린 마이크도 관람객 창구다 — 기한을 안 걸면 복구된
                # 뒤로는 침묵이 아무리 길어도 운영자가 `n` 을 칠 때까지 정적이다.
                self._question_deadline = self._now() + QUESTION_WAIT_S
                self._emit(self._machine.force_listening(self._who("mc")))
            elif (
                self._question_deadline is not None
                and self._now() >= self._question_deadline
                # **LISTENING 일 때만 본다.** 기한은 쉬러 들어갈 때 걸리지만
                # 그 뒤 관람객 질문이 들어오면 상태가 발화로 옮겨간다 — 그때
                # 넘어가면 도슨트가 답하는 도중에 섹션이 바뀐다.
                and self._machine.state is State.LISTENING
            ):
                # 침묵이 한도를 넘었다 — 다음 섹션으로 간다. **경고하지 않는다**:
                # 정상 동작이고, 여기에 경고를 달면 섹션마다 찍혀서 바로 위의
                # 진짜 신호("응답이 없다")가 그 안에 묻힌다. 마지막 큐에서의
                # 침묵도 마찬가지라 `quiet_if_last=True` 다 — 시연이 끝난 것이지
                # 아무도 뭘 요청한 적이 없다.
                #
                # 기한은 **부르기 전에 끈다.** 마지막 큐면 `_next_locked()` 가
                # 상태를 안 바꾸고 돌아오므로, 안 끄면 이 갈래가 tick 마다
                # (0.5초에 한 번) 시연이 끝날 때까지 계속 돈다.
                self._question_deadline = None
                self._next_locked(quiet_if_last=True)

    def abort(self) -> None:
        with self._lock:
            self._abort_locked()

    def _abort_locked(self) -> None:
        """중단의 본체. **`self._lock` 을 쥔 채** 부른다.

        공개 `abort()` 와 모드 전환(`set_mode`)이 같은 몸을 쓴다 — 락을 이미 쥔
        `set_mode` 가 공개 `abort()` 를 부르면 재진입이 안 되는 락에서 교착이다.
        """
        self._deadline = None
        self._emit(self._machine.abort())

    # ── 내부 ──────────────────────────────────────────────────────
    def _begin_cue(self, cue: Cue) -> None:
        # **먼저 거절한다.** 발화 중이면 아래 `speak()` 가 TurnError 를 던지는데,
        # 그 전에 이력에 사회자 대사를 넣고 생성 스레드를 갈아끼우면 거절된
        # start() 가 부작용을 남긴다 — 운영자의 `s` 두 번이 이력을 오염시키고
        # 진행 중인 도슨트 생성을 "다음 큐로 넘어갔다" 는 엉뚱한 경고와 함께
        # 버린 뒤 LLM 을 다시 불렀다(리뷰 A7a). 검증 → 부작용 순서다.
        if self._machine.state in SPEAKING:
            raise TurnError(
                f"{self._machine.speaking_role} 가 아직 말하는 중이다"
                f"(큐 {self._machine.cue_id}) — 동시 발화를 막는다"
            )
        # **대기 중인 관람객 수준은 여기서 적용한다 — 큐를 시작하는 유일한 자리라서.**
        # start·next·previous·goto·관람객의 "다음"·침묵 자동 진행, 그리고 콘솔 `r`
        # (abort + start)이 모두 여기를 지난다(`test_큐를_시작하는_모든_길이_대기_수준을_
        # 적용한다`). 위 거절 **뒤**에 둔다: 발화 중이라 거절된 시작이 대기를 먹으면
        # 화면의 수준은 바뀌었는데 흐르는 큐는 옛 수준이다. 아래 브리프·캐시 키·도슨트
        # 사전 생성 **앞**에 둔다: 이 큐 전체가 새 수준으로 돌아야 한다.
        if self._level_pending is not None:
            self._apply_pending_level(cue)
        # **수준별 브리프를 여기서 한 번 가른다.** `brief_for` 는 이 섹션에
        # `briefs` 가 없으면 옛 `docent_brief` 로 폴백하므로, 아래 두 자리
        # (여는 대사 캐시 키·도슨트 사전 생성) 모두 이 한 쌍만 보면 된다.
        mc_brief, docent_brief = cue.brief_for(self._level_name)

        # **여는 대사는 런타임에 만들지 않는다 — 사전 생성 캐시에서 읽는다.**
        # `scripts/pregen_mc_lines.py` 가 시연 전에 19섹션 × 4수준을 만들어
        # `data/mc_lines.yaml` 에 적어 두면, 사람이 그것을 읽고 고친 뒤에야
        # 시연이 돈다 — 그게 이 캐시를 두는 진짜 이유다(지연 0 은 덤).
        key = cache_key(cue.id, self._level_name, mc_brief)
        mc_text = self._mc_lines.get(key, "")
        if not mc_text:
            # 조용히 물러나지 않는다 — 사전 생성을 빠뜨린 채 시연이 돌면
            # 애드리브가 통째로 없는데 아무도 모른다.
            #
            # **원인을 가릴 수 있게 적는다.** "사전 생성을 아예 안 돌렸다"
            # 와 "브리프를 고쳐 해시가 바뀌었다"(= 해시를 키에 넣은 바로 그
            # 목적)는 서로 다른 문제인데 문구가 같으면 구분이 안 된다. `key`
            # 를 그대로 찍어 두면 `data/mc_lines.yaml` 을 그 문자열로 grep
            # 해서 "정말 없는지"(사전 생성을 안 돌림) "다른 해시로 있는지"
            # (브리프가 바뀜)를 즉시 가를 수 있다. 캐시 항목 수도 같이
            # 찍는다 — 0개면 캐시 자체를 안 읽어 온 배선 문제([Task 6 리뷰]
            # (A))일 수도 있다는 신호가 된다.
            self._warn(
                f"[{cue.id}] 여는 대사 캐시가 없다({self._level_name}, key={key!r}, "
                f"로드된 캐시 {len(self._mc_lines)}개) — 큐시트 원문을 읽는다. "
                "scripts/pregen_mc_lines.py 를 다시 돌린다"
            )
            mc_text = cue.mc

        # **사회자 대사도 이력에 넣는다 — 생성 스레드를 띄우기 전에.**
        # 설계 §5.2 는 이력이 하나이고 `사회자:`/`도슨트:`/`관람객:` 접두로
        # 구분한다고 못박는다. 사회자 몫을 빠뜨리면 도슨트의 LLM 은 방금
        # 사회자가 뭐라고 넘겼는지 못 본다 — "도슨트, 맥스웰부터 부탁해요"
        # 라는 넘김을 못 보고 해설을 시작하니 말이 이어지지 않는다.
        # 순서가 중요하다: `_generate_docent` 가 `list(self.history)` 를
        # 찍어가므로 스레드를 띄운 **뒤에** 넣으면 이번 큐에는 안 들어간다.
        self._remember(f"사회자: {mc_text}")

        # **도슨트 대사를 미리 만든다.** 사회자가 고정 대사를 말하는 3~5초 동안
        # 생성이 끝나므로 LLM 지연이 섹션 전환에 실리지 않는다.
        # role="docent" — 이 슬롯은 도슨트 해설 전용이다.
        # **수준별 브리프를 쓴다** — 옛 `cue.docent_brief` 를 그대로 두면
        # 사회자 대사만 수준을 따르고 해설은 수준과 무관해진다(계획 보완
        # Step 5b). 폴백도 같은 값을 줘야 한다 — `brief_for` 가 브리프 없는
        # 섹션에서는 옛 `docent_brief` 를 돌려주므로 폴백 의미가 그대로다.
        self._spawn_generate("docent", "docent", docent_brief, docent_brief, cue.id)

        # **받아치기 슬롯 둘은 큐가 바뀔 때마다 반드시 갈아끼운다.**
        #
        # 예전에는 이 메서드가 `"docent"` 슬롯만 건드렸다. 받아치기가 고정
        # 대사이던 동안에는 그래도 됐지만 생성이 들어오면 얘기가 다르다 —
        # 이전 큐의 세대가 그대로 남으면 `on_speaking_ended` 2구간의 세대
        # 검사가 **큐 전환을 못 본다.** 그 검사는 "내가 기다리는 동안 이
        # 슬롯이 갈렸는가" 로 다음 턴을 판정하는데, 큐 전환이 슬롯을 안
        # 갈면 판정 근거 자체가 없다. 상태 검사(LISTENING 인가)로도 못
        # 잡는다 — 다음 큐의 사회자 발화까지 끝나면 상태가 **다시
        # LISTENING** 이라(`test_대기_중_다음_큐가_돌아…` 와 같은 틈) 이전
        # 섹션 반응이 그대로 새 섹션에 얹힌다.
        #
        # 둘 다 **이전 큐의 도슨트 발화·지시문**을 보고 만든 것이라 새 큐에서는
        # 언제나 남의 대사다. 여기서 새로 띄우지는 않는다 — 받아치기 생성은
        # 임계경로(도슨트 해설)와 LLM 락을 다투면 안 되므로 도슨트 대사를 보낼
        # 때 한꺼번에 띄운다(`_spawn_after` 주석).
        self._invalidate_slot("after")
        self._invalidate_slot("after_spare")

        self._emit(
            self._machine.speak(self._who("mc"), cue.id, mc_text, gaze=cue.gaze)
        )

    def _apply_pending_level(self, cue: Cue) -> None:
        """대기 수준을 적용한다. **`self._lock` 을 쥔 채** `_begin_cue` 에서만 부른다.

        **훅을 먼저 부른다.** 거꾸로면 훅이 터졌을 때 수준 표시·하한은 새 것인데
        생성기만 옛 것인 반쪽 상태가 남는다.

        **훅이 터져도 큐는 시작한다 — 옛 수준으로.** 예외를 올리면 대기가 남아 큐를
        시작할 때마다 같은 예외가 나고, 침묵 자동 진행은 커서를 옮긴 **뒤** 여기서
        터지므로 시연이 그 자리에서 굳는다. 곁다리 기능의 실패가 진행을 막으면 안
        된다 — 소리 내고, 대기를 버리고(운영자가 다시 고르면 다시 해 본다), 브리프·
        생성기·하한이 모두 옛 수준으로 맞는 상태로 간다. 대기를 **먼저** 비우는 이유도
        이것이다(`test_생성기_전환이_터지면_경고하고_옛_수준으로_큐를_시작한다`).

        훅은 락 안에서 불린다 — `StageServer._send`·경고 콜백과 같은 규칙을 진다:
        **감독 상태를 읽지 않고 블로킹하지 않는다.** 그래서 이름만 넘긴다. 실제 훅
        (`stage/__main__.py::LevelSwitch.select`)은 대입 하나이고, 새 수준 생성기를
        만드는 일(페르소나 파일 읽기)은 첫 생성 때 생성 스레드에서 한다 — 락 밖이다.

        이 뒤에 띄우는 생성(`_spawn_generate`)은 새 생성기를 탄다. 앞 큐가 띄운 늦은
        생성은 새 생성기로 돌든 옛 생성기로 돌든 **버려진다** — `_begin_cue` 가 세
        슬롯의 세대를 모두 올리므로(도슨트는 새 생성으로, 받아치기 둘은 무효화로)
        그 결과는 세대 검사에 걸린다.

        ⚠️ 락 밖에서 읽히는 값이 하나 있다: `_docent_min_chars` 는 `_await_pending`
        (→ `_warn_if_short`)이 락을 놓고 기다린 뒤 읽는다. 전에는 기동 뒤 안 바뀌어
        상관없었다. 이제는 그 대기의 세대 확인 **직후**에 다음 큐가 시작되면(콘솔 `n`)
        옛 큐의 대사를 새 수준 하한으로 잴 수 있다 — 그 대사는 곧바로 2구간의 세대
        재확인에 걸려 "다음 턴으로 넘어갔다 — 버린다" 가 뒤따르므로 나가지 않는다.
        틀릴 수 있는 것은 버려질 대사에 붙는 "너무 짧다" 경고 한 줄의 하한뿐이다.
        """
        name = self._level_pending
        self._level_pending = None
        try:
            self._on_level_change(name)
        except Exception as exc:  # noqa: BLE001 — 위 docstring: 진행을 막지 않는다
            self._warn(
                f"관람객 수준 {name} 전환 실패({type(exc).__name__}: {exc}) — "
                f"{self._level_name} 그대로 간다"
            )
            return
        self._level_name = name
        self._docent_min_chars = self._level_min_chars[name]
        self._warn(f"관람객 수준을 {name}(으)로 바꿨다 — {cue.id} 부터")

    def _spawn_generate(
        self, slot: str, role: str, brief: str, fallback: str, label: str
    ) -> None:
        """슬롯 **하나**를 비우고 스레드를 띄운다. 이력은 **이 시점의 사본**이다.

        다른 이름의 슬롯은 건드리지 않는다 — 받아치기 생성이 도슨트 해설 슬롯을
        밀어내면 해설이 통째로 사라진다(`tests/test_stage_director.py::
        test_슬롯이_다르면_서로를_지우지_않는다`).

        같은 슬롯 안에서는 여전히 "마지막 하나만 산다". 도슨트 해설(큐 시작 때)과
        질문 응답(확인 멘트 때)은 둘 다 도슨트가 이어서 말할 자리라 같은 슬롯을
        쓰고, 늦게 끝난 쪽은 세대 검사에 걸려 버려진다.

        `role` 은 **슬롯과 다른 축이다** — 슬롯은 "어느 자리의 생성인가"(밀어내기
        방지), `role` 은 "어느 페르소나로 말할 것인가"(`stage/prompts.py`).
        도슨트 해설·질문 응답은 `role="docent"`, 사회자 받아치기(예비·실제)는
        `role="mc"` 다 — 그래야 사회자가 도슨트 분량으로 떠들지 않는다.
        """
        token = self._bump_slot(slot)
        threading.Thread(
            target=self._generate_pending,
            args=(slot, role, brief, token, fallback, label),
            daemon=True,
        ).start()

    def _bump_slot(self, slot: str) -> int:
        """슬롯 한 칸의 세대를 올리고 내용을 비운다. 새 세대 번호를 준다.

        `_spawn_generate`(새 생성을 띄운다)와 `_invalidate_slot`(그냥 끊는다)이
        **같은 코드**를 쓰게 묶어 뒀다 — 둘이 갈라지면 한쪽만 `is_fallback` 을
        내리거나 한쪽만 대기자를 깨우는 식으로 어긋난다.
        """
        with self._gen_lock:
            s = self._slots.setdefault(
                slot,
                {"text": None, "is_fallback": False, "ready": threading.Event(), "token": 0},
            )
            # **이전 세대를 기다리던 스레드를 깨운다.** 그 세대의 결과는 이제
            # 버려지므로(`_generate_pending` 의 토큰 검사) 아무도 그 이벤트를
            # 세팅해 주지 않는다 — 깨우지 않으면 `_await_pending` 이 유예시간
            # 내내 좀비로 남고, 그 스레드는 커넥션 수신 루프라 그동안 그 로봇의
            # 메시지가 밀린다.
            s["ready"].set()
            s["text"] = None
            # 새 세대는 아직 폴백이 아니다. 여기서 안 내리면 이전 세대가 남긴
            # True 가 그대로 붙어 있어, 이번 세대가 진짜로 짧은 대사를 내놓아도
            # MIN_CHARS 경고가 걸리지 않는다 — 조용히 짧아지는 것을 못 잡는다.
            s["is_fallback"] = False
            s["ready"] = threading.Event()
            s["token"] += 1
            return s["token"]

    def _invalidate_slot(self, slot: str) -> None:
        """이 슬롯의 세대를 끊는다 — 진행 중인 생성 결과를 버리고 남은 텍스트도 지운다.

        새 생성을 띄우지 않는 "갈아끼움" 이다. 큐가 바뀔 때 받아치기 슬롯에 쓴다
        (`_begin_cue` 의 주석 참고). 슬롯이 아직 없으면 **빈 칸으로 만들어 둔다**
        — 그래야 `_snapshot_slot` 이 KeyError 없이 돌고, "한 번도 안 띄운 슬롯"
        과 "끊긴 슬롯" 이 같은 모양이 된다.
        """
        self._bump_slot(slot)

    def _slot_text(self, slot: str) -> str:
        """그 슬롯에 **이미 들어온 진짜 생성 결과**. 없으면 빈 문자열.

        기다리지 않는다 — 이 값은 "지금 준비돼 있으면 쓴다" 는 여유분이다.
        폴백으로 갈린 텍스트(`is_fallback`)는 주지 않는다: 그것은 생성 결과가
        아니라 호출부가 이미 아는 큐시트 문장이라, 폴백의 폴백으로 넘기면 같은
        값이 두 번 도는 셈이고 로그에는 "예비가 살아 있다" 는 착시만 남는다.

        **`self._lock` 을 쥔 채 부른다** — 락 순서는 언제나 `_lock` → `_gen_lock`
        한 방향뿐이다(`__init__` 의 `self._lock` 주석).
        """
        with self._gen_lock:
            s = self._slots.get(slot)
            if s is None or s["is_fallback"] or not s["ready"].is_set():
                return ""
            return s["text"] or ""

    def _ensure_visitor_cue(self, text: str, label: str, is_last: bool) -> str:
        """생성된 받아치기에 **관람객 창구 안내**가 있는지 보고, 없으면 붙인다.

        왜 필요한가: 마이크가 열려도 관람객은 그것을 모른다(리뷰 B2). 큐시트의
        고정 `mc_after` 19곳은 전부 "질문 받습니다 + '다음' 이라고 하면 넘어갑니다"
        를 달고 있고 데이터 테스트가 그것을 못박는다(`tests/test_stage_cues.py::
        test_모든_큐에_받아치기가_있고_다음을_안내한다`). 받아치기를 생성으로
        바꾸면 그 보장이 **폴백에만** 남는다 — 생성이 성공할수록 관람객이 참여
        방법을 모르게 되는 비대칭이라, 그 자리를 여기서 메운다.

        `is_last` 면 '다음' 안내는 붙이지 않는다 — 더 넘어갈 데가 없다. 데이터
        쪽 가드가 `cues[:-1]` 로 마지막을 빼는 것과 같은 예외다.

        **판정은 고정 문구 대조가 아니다**(`stage/cues.py::invites_question`).
        사회자 지시문이 "관람객에게 질문을 권한다" 라 모델은 제 말로 묻는다 —
        완전 포함 검사만 하면 거의 매번 같은 뜻을 두 번 내보내, 고정 문장을
        생성으로 바꾼 이 작업의 목적이 도로 무너진다(리뷰 Important 2).
        """
        added: list[str] = []
        if not invites_question(text):
            prompt = QUESTION_PROMPTS[self._q_i % len(QUESTION_PROMPTS)]
            self._q_i += 1
            added.append(prompt)
            # **여기만 경고한다.** 사회자 지시문이 "관람객에게 질문을 권한다" 라,
            # 질문 유도가 빠진 것은 대개 모델이 지시를 안 지킨 것이다 — 잦으면 고칠
            # 곳은 감독이 아니라 `data/personas/mc.md` 다. 그리고 원인을 가른다:
            # "정말 안 물었다"(페르소나를 고쳐라)와 "물어보긴 했는데 판정이 못
            # 알아봤다"(`invites_question` 의 어휘를 넓혀라)는 고칠 곳이 다르다.
            # 셋째 원인(2026-09-21~): 모델은 물었는데 `stage/__main__.py::
            # build_generate` 의 생성 뒤 분량 상한이 그 질문을 잘랐다. 상한은
            # 앞에서부터 남기고 사회자의 질문은 대개 마지막 문장이라, 받아치기가
            # 길게 나오면(실측 147~195자, 상한 120자) 이쪽이 흔하다. 이 경고보다
            # **앞서** `[mc]` 로 찍힌 `분량 상한` 경고를 찾는다 — 생성은 앞 화자가
            # 말하는 동안 미리 돌므로 그 사이에 다른 줄이 끼어 있을 수 있다(예비
            # 받아치기면 더 앞이다). 잘린 뒷부분에 질문이 보이면 원인은 페르소나의
            # 질문 지시가 아니라 분량 초과다.
            why = "물어보긴 했는데 질문 유도로 알아볼 수 없다" if "?" in text else "질문 유도가 없다"
            self._warn(
                f"[{label}] 생성된 받아치기에 {why} — 고정 문장을 붙인다: {prompt}"
            )
        if not is_last and not mentions_advance(text):
            # **여기는 경고하지 않는다.** 진행 방법("'다음'이라고 하세요")은 애초에
            # 모델에게 시키지 않는 것이라 빠지는 게 정상이고(19섹션 중 18섹션에서
            # 빠진다), 섹션마다 경고가 뜨면 바로 위의 **진짜 신호**가 그 안에 묻힌다.
            # 물러나는 것이 아니라 설계된 조립이다 — [생성된 반응 + 고정 길잡이].
            added.append(ADVANCE_HINT)
        if not added:
            return text
        return " ".join([text, *added])

    def _snapshot_slot(self, slot: str) -> tuple[threading.Event, int]:
        """기다릴 이벤트와 세대를 찍는다. **`self._lock` 을 쥔 채 부른다.**

        두 락을 겹쳐 잡는 순서는 언제나 `self._lock` → `_gen_lock` 한 방향뿐이다
        (`__init__` 의 `self._lock` 주석). 이 헬퍼를 락 밖에서 부르면 그 순서가
        깨지는 것은 아니지만, 찍은 세대와 그때의 상태가 서로 다른 순간의 것이
        되어 `on_speaking_ended` 의 "깨어나서 다시 본다" 가 무의미해진다.
        """
        with self._gen_lock:
            s = self._slots[slot]
            return s["ready"], s["token"]

    def _generate_pending(
        self, slot: str, role: str, brief: str, token: int, fallback: str, label: str
    ) -> None:
        is_fallback = False
        try:
            text = self._generate(role, brief, list(self.history))
            if not text:
                # 빈 문자열도 "아무 말도 안 하는 것"과 같다 — 조용히 넘기지 않는다.
                self._warn(f"[{label}] 대사 생성이 빈 문자열을 내놓았다 — 폴백")
                text = fallback
                is_fallback = True
        except Exception as exc:
            # 조용히 벙어리가 되지 않는다. 폴백(지시문 또는 사과 한 줄)을
            # 그대로 읽는 것이 아무 말도 안 하는 것보다 낫다.
            self._warn(f"[{label}] LLM 생성 실패({type(exc).__name__}: {exc}) — 폴백")
            text = fallback
            is_fallback = True

        with self._gen_lock:
            s = self._slots[slot]
            if token != s["token"]:
                # 이 결과가 나올 즈음 이미 다음 큐(또는 다음 질문)가 시작됐다.
                # 세대는 **슬롯마다** 세므로, 다른 슬롯이 갈린 것은 여기에 걸리지
                # 않는다 — 받아치기를 새로 띄웠다고 진행 중인 해설을 버리지 않는다.
                # 그대로 반영하면 엉뚱한 대사가 조용히 새어 들어간다 — 버리고 소리 낸다.
                self._warn(f"[{label}] 대사 생성이 늦게 끝나 버려졌다(다음 턴으로 이미 넘어갔다)")
                return
            s["text"] = text
            # 폴백 여부를 텍스트와 **한 락 안에서 같이** 남긴다 — 따로 쓰면
            # `_await_pending` 이 텍스트는 새 세대, 표시는 이전 세대 것을 섞어
            # 읽을 수 있다.
            s["is_fallback"] = is_fallback
            ready = s["ready"]
        ready.set()

    def _await_pending(
        self, pending: "_Pending", ready: threading.Event, token: int
    ) -> str:
        """`pending.slot` 에 생성된 대사를 기다린다 — **진입 락 밖에서.**

        유예를 넘기거나 생성이 실패했으면 `pending.fallback` 을 읽는다. 물러날
        때는 **무엇으로** 물러났는지를 같이 적는다(`pending.fallback_kind`) —
        받아치기의 사다리 2단(예비)과 3단(큐시트)이 같은 문구로 찍히면 로그로
        원인을 못 가른다.

        폴백을 슬롯의 `text` 에 **쓰지 않는다.** 예전에는 여기서 `_gen_lock`
        없이 써서, 유예가 끝나는 바로 그 순간에 생성 스레드가 막 넣은 진짜 대사를
        폴백으로 덮어쓸 수 있었다. 돌려주기만 하면 그 경합 자체가 없다.

        호출부(`on_speaking_ended`)가 사회자 여는 대사와 구분되는 id(`:docent`/
        `:qa`/`:after`)를 붙인다. 맨 `cue.id` 는 "사회자 몫이 끝났다" 판정에 그대로
        쓰이므로, 뒤따르는 몫까지 같은 id 를 쓰면(리뷰 finding 1) 1인 모드에서 같은
        로봇이 도슨트 몫을 끝낸 speaking_ended 가 다시 "사회자 몫이 끝났다" 로
        오판돼 무한 반복한다.
        """
        label = pending.label
        if not ready.wait(timeout=GENERATE_GRACE_S):
            self._warn(f"[{label}] 대사 생성이 늦다 — {pending.fallback_kind}(으)로 물러난다")
            return self._take_fallback(pending)
        with self._gen_lock:
            s = self._slots[pending.slot]
            if token != s["token"]:
                # 다음 턴이 **이 슬롯을** 갈면서 깨워 준 것이다 — 이 값은 의미가 없다.
                # 경고는 호출부가 한 번만 낸다(거기서 버리는 것이 확정된다).
                return pending.fallback
            text = s["text"]
            is_fallback = s["is_fallback"]
        if is_fallback:
            # **슬롯에 든 폴백이 아니라 호출부가 준 폴백을 읽는다.**
            # `_generate_pending` 은 빈 문자열·예외를 만나면 **띄울 때** 받은
            # 폴백을 슬롯에 넣고 `ready` 를 세운다. 그 값은 호출부가 지금 아는
            # 것보다 낡았다 — 받아치기라면 "큐시트 원문"이고, 그 사이 호출부는
            # 준비된 **예비**를 폴백으로 들고 있다(사다리 2단). 이 줄이 없으면
            # 실제 생성이 **터지거나 빈 문자열일 때** 준비된 예비를 건너뛰고
            # 큐시트로 직행한다 — 사다리가 "늦음" 에만 걸리는 꼴이다(리뷰 Critical).
            # 도슨트 해설·`:qa` 는 두 값이 같아 영향이 없다.
            self._warn(f"[{label}] 생성이 폴백으로 갈렸다 — {pending.fallback_kind}(으)로 물러난다")
            return self._take_fallback(pending)
        if not text:
            self._warn(f"[{label}] 대사가 비어 있다 — {pending.fallback_kind}(으)로 물러난다")
            return self._take_fallback(pending)
        # 여기까지 온 `text` 는 **진짜 생성 결과**다(폴백은 위에서 이미 돌아갔다).
        # 그래서 길이를 잰다. 폴백에 이 검사를 걸면 "생성 실패" 경고 뒤에 "생성
        # 결과가 짧다" 는 **틀린** 경고가 덧붙어, 로그만 보면 LLM 이 실제로 37자를
        # 냈다고 오판한다(QA_FALLBACK 이 37자, MIN_CHARS 가 40이다).
        self._warn_if_short(text, label, pending.role)
        return text

    def _take_fallback(self, pending: "_Pending") -> str:
        """폴백으로 물러난다. **예비는 진짜 생성 결과**라 길이 검사를 받는다.

        큐시트 원문·지시문·사과문은 사람이 쓴 문장이라 길이를 재면 헛경보가
        난다(QA_FALLBACK 은 37자다). 반면 예비 받아치기는 LLM 이 낸 대사이므로,
        이 자리에서 안 재면 **예비를 읽은 섹션만 길이 감시의 사각지대**가 된다
        — 조용히 짧아지는 것을 잡으려고 만든 경고가 하필 그때 꺼진다.

        재는 하한은 `pending.role` 이 정한다. 예비 받아치기는 `role="mc"` 라
        `MIN_CHARS`(40) 고정이다 — 수준이 전문가(260자)여도 그렇다. 사회자
        프롬프트가 수준과 무관하게 "40~120자" 라서, 여기에 도슨트 하한을 얹으면
        정상적인 받아치기가 전부 미달로 찍힌다(`_warn_if_short` 주석 참고).
        """
        if pending.fallback_kind in _GENERATED_FALLBACKS:
            self._warn_if_short(pending.fallback, pending.label, pending.role)
        return pending.fallback

    def _warn_if_short(self, text: str, label: str, role: str) -> None:
        """**진짜 생성 결과**가 해설·반응이라기엔 짧으면 소리 낸다. 그대로 쓴다 —
        버리면 정적이 되는데 그게 더 나쁘다.

        "진짜 생성 결과" 는 큐시트 폴백이 아니라는 뜻이지 **모델 원문**이라는 뜻이
        아니다(2026-09-21~). `stage/__main__.py::build_generate` 가 생성 직후 이름표
        정리와 분량 상한을 건 뒤의 텍스트가 여기 닿는다. 그래서 짧은 원인이 모델
        말고도 있다: 분량 상한이 첫 문장만 남겼거나(첫 문장이 길면 둘째부터
        버려진다 — 모델은 450자를 썼는데 여기서는 150자로 보인다), 이름표 정리가
        이어 쓴 상대 턴을 잘라냈다. 이 경고보다 **앞서** 같은 역할(`[docent]`/
        `[mc]`)로 찍힌 `분량 상한`(또는 `이름표`) 경고를 찾는다 — 생성은 미리 돌아
        그 사이에 다른 줄이 끼어 있을 수 있다. 그 경고가 원래 길이와 잘린 부분을
        보여 준다.

        **하한은 역할의 함수다**(`role`, 분량이 슬롯이 아니라 역할을 따르는 것은
        `stage/prompts.py::_amount_for` 와 같은 축이다):

        - `role="docent"`(해설·질문 응답) → `self._docent_min_chars`
          (= 그 수준의 `level.min_chars`). 40 고정이던 동안에는 일반 180자·
          전문가 260자 목표에 50자짜리 해설이 나와도 경고가 없었다(리뷰 I1).
        - `role="mc"`(받아치기) → `MIN_CHARS`(40) 고정. 사회자 프롬프트가 수준과
          무관하게 "40~120자" 이기 때문이다 — 여기에 도슨트 하한을 얹으면 사회자가
          지시를 **제대로 지켰는데도** 매 섹션 경고가 떠, 바로 옆의 진짜 신호
          (도슨트가 조용히 짧아지는 것)가 그 안에 묻힌다.

        `role` 을 라벨 문자열(`:qa`/`:after`)로 추측하지 않는다 — 역할은 이미
        `_spawn_generate(slot, role, …)` 로 들어와 `_Pending.role` 에 실려 여기까지
        온다. 슬롯 이름을 `_Pending` 에 실어 `"docent"` 하드코딩 버그를 고친 것과
        **같은 방식**이다(`on_speaking_ended` 의 세대 재확인 주석 참고).
        """
        limit = self._docent_min_chars if role == "docent" else MIN_CHARS
        if len(text) < limit:
            # **무엇에 못 미쳤는지 같이 적는다.** 하한이 역할·수준마다 다르므로
            # 글자 수만 찍으면 로그를 보는 사람이 그게 미달인지 판단할 수 없다.
            self._warn(
                f"[{label}] 생성 결과가 너무 짧다({len(text)}자, 하한 {limit}자) — 그대로 쓴다"
            )

    def _answer(self, question: str) -> None:
        cue = self._sheet.current()
        self._remember(f"관람객: {question}")
        # **분량 지시를 여기 박지 않는다.** 분량은 섹션이 아니라 수준의
        # 함수다(설계 §5, Task 3) — 시스템 프롬프트가 `level.min_sentences`
        # 등으로 이미 정해 준다. 예전에는 여기에 "3문장 이내로 답한다" 를
        # 박아 뒀는데, 그러면 (i) 사회자 대사·도슨트 해설은 수준을 따르는데
        # 질문 응답만 고정 분량으로 도는 비대칭이 생기고, (ii) 큐시트에서
        # 걷어낸 바로 그 "N문장 이내" 표현(Task 5)이 다른 자리에서 되살아난
        # 것이었다. 브리프 본문은 질문과 섹션 맥락만 준다.
        brief = f"관람객이 '{question}' 라고 물었다. 지금 섹션은 '{cue.title}' 이다. 도슨트로서 답한다."
        # **여기서 LLM 을 기다리지 않는다.** 예전에는 락을 쥔 채 왕복 전체를 기다려
        # 콘솔 `a` 와 tick() 이 그동안 멈췄다(리뷰 C1). 사회자의 확인 멘트가 흐르는
        # 동안 스레드에서 만든다 — 관람객에게도 정적 대신 반응이 먼저 간다(B3).
        # 큐 전환의 "고정 대사로 지연 은닉" 과 같은 수법이다.
        self._spawn_generate("docent", "docent", brief, QA_FALLBACK, f"{cue.id}:qa")
        ack = QA_ACK_LINES[self._ack_i % len(QA_ACK_LINES)]
        self._ack_i += 1
        self._remember(f"사회자: {ack}")
        self._emit(
            self._machine.speak(self._who("mc"), f"{cue.id}:ack", ack, gaze="audience")
        )

    def _remember(self, line: str) -> None:
        """이력에 한 줄 남긴다. **이력은 하나**이고 접두로 화자를 가른다(설계 §5.2).

        상한을 넘으면 앞에서 잘라낸다 — 자르는 쪽을 우리가 정해야 모델의
        컨텍스트 창이 말없이 자르는 것을 막는다.
        """
        # 이 role 은 LLM 으로 갈 때는 쓰이지 않는다 — `stage/__main__.py::history_for`
        # 가 **내용 앞의 이름표**(누가 한 줄인지)로 생성하는 역할의 시점(자기 줄
        # 은 assistant, 남의 줄은 user)을 다시 정한다. 여기서는 그냥 "관람객이
        # 말했나 로봇이 말했나" 만 가른다. 그러니 여기 role 을 "고쳐" 저 역할
        # 매핑을 대신하려 하지 않는다 — 두 층의 뜻이 다른데 하나로 합치면 어느
        # 한쪽을 바꿀 때 다른 쪽이 조용히 어긋난다(전체 리뷰 M3).
        role = "user" if line.startswith("관람객:") else "assistant"
        self.history.append({"role": role, "content": line})
        if len(self.history) > HISTORY_MAX:
            del self.history[: len(self.history) - HISTORY_MAX]

    def _emit(self, cmds: list[Command]) -> None:
        for cmd in coalesce(cmds):
            if cmd.type == "say":
                # 예산을 기억해 둔다 — `speaking_started` 가 오면 그 시점부터
                # 다시 센다(on_speaking_started 참고).
                self._speak_budget = self._estimate(cmd.fields["text"])
                self._deadline = self._now() + self._speak_budget
            self._send(cmd.to, cmd)

    @staticmethod
    def _estimate(text: str) -> float:
        return len(text) / CHARS_PER_SEC + TIMEOUT_MARGIN_S
