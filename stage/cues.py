"""큐시트 로더와 진행 신호 판정.

정본은 `docs/exhibit-guide.md` 이고 이 모듈이 읽는 `data/cues.yaml` 은 그 위에
얹은 진행 단위다. 둘이 어긋나면 큐시트를 고친다 — 반대가 아니다.
"""

import os
import pathlib
import re
from dataclasses import dataclass, field

import yaml

from stage.levels import LEVEL_NAMES

GAZE_TARGETS = frozenset({"partner", "audience"})

_REQUIRED = ("id", "title", "mc", "docent_brief", "gaze")
# 선택 문자열 필드 — 있으면 문자열이어야 한다.
_OPTIONAL_STR = ("mc_after",)

# 진행 신호로 볼 낱말의 어근.
_ADVANCE_WORDS = ("다음", "계속", "넘어가", "진행")

# 긴 문장은 질문일 확률이 높다. 전환 지시는 짧다.
_ADVANCE_MAX_CHARS = 15

# 관람객 질문을 받았을 때 사회자가 **즉시** 하는 말. 이 멘트가 흐르는 3~4초 동안
# 도슨트 답을 생성한다 — 큐 전환의 "고정 대사로 지연 은닉" 과 같은 수법이다(리뷰 B3).
# 돌아가며 쓴다. 같은 말이 반복되면 녹음처럼 들린다.
QA_ACK_LINES = (
    "좋은 질문이네요. 도슨트, 답해 줄래요?",
    "오, 그건 저도 궁금했어요. 도슨트?",
    "네, 그건 도슨트가 잘 알 거예요. 도슨트, 부탁해요.",
)
# 위 확인 멘트와 **같은 자리끼리** 짝을 이루는 감정(계획 §12.3). 따로 둔 이유: 멘트를
# (문장, 감정) 짝으로 바꾸면 이 상수를 문자열로 읽는 자리가 전부 흔들린다. 길이가 어긋나면
# 테스트가 잡는다(`tests/test_stage_cues.py::test_관람객_경로_고정_대사의_감정이_어휘_안에_있다`).
#
# 감정을 안 실으면 로봇이 "감독이 옛 버전이면 재배포가 필요하다" 는 **거짓 경고**를 찍고
# 문장 키워드로 모션을 추측한다(2026-09-24 점검) — 관람객 답에 '타이타닉' 이 나오면
# 고개를 젓는다.
# 셋째("도슨트, 부탁해요")는 도슨트에게 넘기는 손짓이라 `권유`다(2026-09-24 어휘 확장).
QA_ACK_EMOTIONS = ("기쁨", "궁금", "권유")
# 재질문(`QUESTION_PROMPTS`)은 관람객에게 **말을 걸어 보라고 권하는** 말이다 — ~~`궁금`~~ 이면
# 질문 동작(고개 갸웃)이 나가는데, 권유(come1: 가까이 오라는 손짓)가 뜻에 맞는다.
QUESTION_PROMPT_EMOTION = "권유"
# 관람객 질문 답은 LLM 생성이라 내용마다 감정을 붙일 수 없다 — 형식 이탈 위험을 지지
# 않으려고 첫 판은 '설명'(모션 없이 흔들림만)으로 고정한다(계획 §12.3).
QA_ANSWER_EMOTION = "설명"

# **단독 모드**(사회자 혼자 답한다, 2026-09-25)의 확인 멘트. 팟캐스트의 `QA_ACK_LINES` 처럼 사회자가
# 답을 만드는 동안(LLM) 흐르는 짧은 말이다 — 정적 대신 반응이 먼저 간다. 도슨트에게 넘기는 말이 없고,
# 인사("안녕하세요")에도 어색하지 않은 중립 문장만 둔다. 고정 대사라 TTS 결과 캐시에 굽는다
# (`scripts/bake_tts.py::fixed_lines`). 감정은 같은 자리끼리 짝이다(길이는 데이터 테스트가 본다).
SOLO_ACK_LINES = (
    "네, 잘 들었어요.",
    "음, 잠깐 생각해 볼게요.",
    "네, 잠시만요.",
)
SOLO_ACK_EMOTIONS = ("끄덕", "골똘", "경청")
# 단독에서 도슨트는 **깨어 있되 조용히** 있다(결정 2026-09-25) — 사회자가 답하는 동안 사회자를 보고
# (시선) 듣는 반응 하나만 한다. 대본이 없는 생성 답이라 내용에 맞춘 반응을 고를 수 없어 끄덕임 하나로 둔다.
SOLO_LISTENER_REACT = "끄덕"

# 섹션 끝에 사회자가 관람객 창구를 **말로** 여는 문장. 마이크가 열려도 관람객은
# 그것을 모른다(리뷰 B2) — 그래서 큐시트의 고정 `mc_after` 19곳이 전부 이 안내를
# 달고 있고, 데이터 테스트가 그것을 못박는다(`tests/test_stage_cues.py::
# test_모든_큐에_받아치기가_있고_다음을_안내한다`).
#
# **받아치기를 생성으로 바꾸면 그 보장이 폴백(큐시트)에만 남는다 — 비대칭이다.**
# 생성이 성공할수록 관람객이 참여 방법을 모르게 되는 꼴이라, 감독이 생성된
# 받아치기에 이 유도가 없으면 붙인다(`Director._ensure_visitor_cue`).
# 같은 말이 19번 반복되면 녹음처럼 들리므로 돌아가며 쓴다.
# "여기까지" 를 안 쓴다 — 위치 지시어 가드(리뷰 B4)가 `여기`/`이곳`/… 을 훑는다.
# 이 쓰임은 시간적("지금까지")이라 거짓말이 아니지만, 고정 문자열에 그 낱말을
# 안 두면 가드를 나중에 생성물·런타임 문자열까지 넓힐 때 헛경보가 안 난다.
QUESTION_PROMPTS = (
    "궁금한 점 있으실까요?",
    "지금까지 질문 있으실까요?",
    "더 듣고 싶은 게 있으실까요?",
)

# 사회자가 **제 말로** 질문을 권했음을 알아보는 어근.
#
# 왜 고정 문구 대조만으로는 안 되는가: 사회자 지시문이 "짧게 받고 관람객에게
# 질문을 권한다" 라, 모델은 `QUESTION_PROMPTS` 가 아니라 제 말로 묻는다("혹시 더
# 궁금하신 점 있으신가요?"). 완전 포함 검사만 하면 한 글자만 달라도 못 알아봐서
# ① 같은 뜻이 두 번 나가고(고정 문장을 생성으로 바꾼 이 작업의 목적이 무너진다),
# ② 경고가 매 섹션 떠서 "잦으면 페르소나를 고쳐라" 는 신호가 죽고, ③ 길어진다.
_INVITE_WORDS = ("질문", "궁금", "여쭤", "여쭈", "물어보", "물어봐")

# "있으실까요?" 류의 청유형 물음. 어근이 없어도 이 꼬리 + 물음표면 관람객에게
# 묻는 것이다("더 듣고 싶으신 부분 있으실까요?"). 물음표만으로는 부족하다 —
# 수사의문("정말 놀랍지 않나요?")은 창구를 여는 말이 아니다.
_INVITE_ENDINGS = ("있으실까요", "있으신가요", "있으세요", "있나요", "말씀해 주세요", "말씀해주세요")

# 진행 방법 안내. 관람객은 "다음" 이라는 낱말을 알아야 섹션을 넘길 수 있다
# (`is_advance`). 마지막 큐에는 붙이지 않는다 — 더 넘어갈 데가 없다.
# `scripts/merge_research.py::_ADVANCE_SUFFIX` 와 같은 문장이다(그쪽은 큐시트
# **데이터**를 접을 때 쓰고 이쪽은 **생성물**에 쓴다 — 지키는 불변식이 같다).
ADVANCE_HINT = "이어가려면 '다음'이라고 해 주세요."

# 진행 키워드를 **키워드로** 내보인 모양. 따옴표 종류는 모델이 고른다.
_ADVANCE_QUOTES = ("'다음'", '"다음"', "“다음”", "‘다음’")

# 따옴표가 없으면 "말한다" 는 뜻이 붙어 있어야 안내다.
_ADVANCE_VERBS = ("말씀", "말해", "말하", "라고")


def invites_question(text: str) -> bool:
    """이 대사가 관람객에게 **질문을 권하는가**.

    `Director._ensure_visitor_cue` 가 생성된 받아치기에 고정 문장을 덧붙일지
    정할 때 쓴다. 고정 문구를 그대로 썼든 제 말로 물었든 둘 다 "물었다" 로 본다
    — 덧붙이는 것은 **정말 빠졌을 때만**이어야 중복이 안 난다.
    """
    if any(q in text for q in QUESTION_PROMPTS):
        return True
    if any(w in text for w in _INVITE_WORDS):
        return True
    return "?" in text and any(e in text for e in _INVITE_ENDINGS)


def mentions_advance(text: str) -> bool:
    """이 대사가 **진행 방법**을 알려 주는가.

    낱말 등장만 보면 안 된다 — "다음 섹션도 기대되네요" 에는 '다음' 이 있지만
    관람객은 **'다음' 이라고 말하면 된다**는 것을 못 듣는다. 키워드를 따옴표로
    내보였거나, 말하라는 뜻이 함께 있어야 안내다.
    """
    if "다음" not in text:
        return False
    if any(q in text for q in _ADVANCE_QUOTES):
        return True
    return any(v in text for v in _ADVANCE_VERBS)


class CueError(ValueError):
    """큐시트가 규약에 맞지 않는다."""


# 한 큐의 최대 턴 수(사회자 질문 → 도슨트 설명 한 왕복이 한 턴). **수준과
# 무관하다** — 전문가도 3턴이다. 수준이 바꾸는 것은 설명의 난이도뿐이고, 턴이
# 늘면 한 섹션이 늘어져 관람객이 끼어들 창구(받아치기 뒤)가 그만큼 멀어진다.
MAX_TURNS = 3

# 대사 감정 태그(계획 §12.2). 감독이 `say` 에 실어 보내고 로봇 앱이 모션 범주·어조로
# 바꾼다. **로봇 앱(`apps/voice_chat/voice_chat/`)에 같은 목록이 한 벌 더 있다** —
# 로봇에는 `stage/` 가 안 올라가서 import 할 수 없다. 둘은 테스트가 묶는다.
# `설명` 은 "특별한 감정 없음" — 모션 없이 말할 때 흔들림만 한다.
#
# ~~8종~~ → **18종**(2026-09-24, 계획 `2026-09-24-emotion-vocabulary.md`). 8종이 대본의 결
# (감탄·체험 권유·깊이 묻기·멋쩍음·안심시키기·감사·작별 …)을 `궁금`·`기쁨`·`끄덕` 에 뭉갰다.
# 새 태그의 뜻(저작할 때 고르는 기준):
#   신남 — 들뜬 기대("바다 다음은 하늘이에요!")      감탄 — 남이 한 일·사실에 감탄("멋지네요")
#   골똘 — 곰곰이 묻는 질문("왜 나눠 놓은 거예요?")   경청 — 듣는 쪽 기본 반응(계속 말해 보라는 몸짓)
#   안도 — 위험이 풀림(구조·안전 장치)               안심 — 상대를 안심시키며 답함(건강 질문)
#   감사 — 고마움                                     작별 — 마무리 인사
#   권유 — 해 보라고·말해 보라고 권함(체험·질문)     멋쩍음 — "저도 헷갈렸어요" 같은 멋쩍은 인정
EMOTIONS = (
    "반가움", "기쁨", "신남", "놀람", "감탄", "궁금", "골똘", "뿌듯", "끄덕",
    "경청", "아쉬움", "안도", "안심", "감사", "작별", "권유", "멋쩍음", "설명",
)
DEFAULT_EMOTION = "설명"


@dataclass(frozen=True)
class Turn:
    """사회자 질문 → 도슨트 설명 한 왕복. 질문은 수준 공통, 설명만 수준별이다.

    `ask` 는 **소리 내 읽어도 되는 질문**이다 — 다리 대사는 수준별로 사전
    생성되지만 캐시가 없으면 이 원문이 그대로 나간다. 0턴은 비어 있다(오프닝이
    묻는다). `answers` 는 수준 → **구어체 설명**이다 — 도슨트 생성의 씨앗이자,
    생성이 전부 실패했을 때 그대로 읽는 폴백이라 지시문 문체로 쓰면 안 된다.
    """

    ask: str
    answers: dict
    # 감정은 **수준 공통**이다 — 수준은 설명의 난이도만 바꾼다. `listener_emotion` 은
    # 도슨트가 설명하는 동안 사회자가 짓는 반응이고, 빈 문자열이면 반응하지 않는다.
    ask_emotion: str = DEFAULT_EMOTION
    answer_emotion: str = DEFAULT_EMOTION
    listener_emotion: str = ""


@dataclass(frozen=True)
class Point:
    """턴 하나를 한 수준에서 본 것 — 감독과 사전 생성이 쓰는 모양."""

    ask: str
    answer: str
    ask_emotion: str = DEFAULT_EMOTION
    answer_emotion: str = DEFAULT_EMOTION
    listener_emotion: str = ""


@dataclass(frozen=True)
class Cue:
    """진행 단위 하나."""

    id: str
    title: str
    mc: str
    docent_brief: str
    gaze: str
    # 도슨트 뒤 사회자의 받아치기. 관람객 창구가 열린다는 것을 **말로** 알린다 —
    # 마이크가 열려도 관람객은 모른다(리뷰 B2). 비면 곧장 듣기로 간다.
    mc_after: str = ""
    # 조사 주제와 출처 달린 사실. 발화에는 직접 쓰지 않고 사람이 검토한다.
    topic: str = ""
    # 수준 → {mc_brief, docent_brief, guard?}. 비어 있으면 옛 `docent_brief` 로
    # 폴백한다 — 큐시트 19섹션을 한 번에 옮길 수 없으므로 섞여 있는 기간이 있다.
    briefs: dict = field(default_factory=dict)
    # 턴 목록(`Turn`). 비어 있으면 옛 단일 라운드(`docent_brief` 한 번)로 돈다.
    # **큐 최상위에 둔다** — 수준별로 두면 턴 수와 질문이 수준마다 달라진다.
    points: tuple = ()
    # 사회자 오프닝·받아치기의 감정(계획 §12).
    mc_emotion: str = DEFAULT_EMOTION
    mc_after_emotion: str = DEFAULT_EMOTION

    def brief_for(self, level_name: str) -> tuple[str, str]:
        """수준에 맞는 (mc_brief, docent_brief) 를 준다.

        이 섹션에 `briefs` 가 없으면(아직 안 옮긴 섹션) 옛 `docent_brief` 로
        폴백한다 — `load_cues` 가 이미 "채웠으면 수준 전부" 를 강제하므로
        여기서는 "비었으면 폴백" 만 보면 된다.
        """
        b = self.briefs.get(level_name)
        if not b:
            return "", self.docent_brief
        return b.get("mc_brief", ""), b.get("docent_brief", self.docent_brief)

    def points_for(self, level_name: str) -> list[Point]:
        """이 수준에서 본 턴 목록. 없으면(단일 라운드 큐) 빈 목록.

        질문은 모든 수준이 같고 설명만 그 수준의 것이다. `load_cues` 가 네 수준
        설명을 전부 강제하므로 여기서 수준이 빠질 일은 없다.
        """
        return [
            Point(t.ask, t.answers[level_name], t.ask_emotion, t.answer_emotion, t.listener_emotion)
            for t in self.points
        ]

    def guard_for(self, level_name: str) -> str:
        """이 수준에서 말하면 안 되는 것. 도슨트 턴 지시문에만 붙고 읽히지 않는다.

        턴 설명(`answers`)만 주면 옛 수준 브리프의 금지 규칙("'캐나다'라고 하지
        않는다" 등)이 생성에서 통째로 빠진다 — 포인트로 옮긴 첫 판이 그랬다.
        """
        return (self.briefs.get(level_name) or {}).get("guard", "")


def cues_path() -> pathlib.Path:
    """큐시트 경로. `REACHY_CUES_PATH` 가 있으면 그것을 쓴다."""
    override = os.environ.get("REACHY_CUES_PATH")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "cues.yaml"


def load_cues(path: pathlib.Path | None = None) -> list[Cue]:
    """큐시트를 읽는다. 어긋나면 **소리 내서 실패한다.**"""
    p = pathlib.Path(path) if path is not None else cues_path()
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CueError(f"큐시트가 없다: {p}") from exc
    except yaml.YAMLError as exc:
        raise CueError(f"큐시트가 YAML 이 아니다: {p} — {exc}") from exc

    if not raw:
        raise CueError(f"큐시트가 비어 있다: {p}")
    if not isinstance(raw, list):
        raise CueError(f"큐시트는 목록이어야 한다: {p} (지금은 {type(raw).__name__})")

    out: list[Cue] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CueError(f"{p} {i}번째 항목이 매핑이 아니다")
        for key in _REQUIRED:
            v = item.get(key)
            # `str()` 로 감싸면 `mc: 123`·`mc:`(None) 이 통과한다 — 그 값이
            # `_estimate` 의 len() 에서 터져 감독이 데드라인 없이 굳는다(리뷰 A8a).
            # 타입을 요구하는 자리는 강제 변환이 아니라 거절이다.
            if not isinstance(v, str) or not v.strip():
                raise CueError(
                    f"{p} {i}번째 항목의 {key} 가 비어 있거나 문자열이 아니다"
                    f"({type(v).__name__})"
                )
        if item["gaze"] not in GAZE_TARGETS:
            raise CueError(
                f"{p} {item['id']}: 모르는 gaze {item['gaze']!r} "
                f"(쓸 수 있는 값: {sorted(GAZE_TARGETS)})"
            )
        if item["id"] in seen:
            raise CueError(f"{p}: 큐 id 가 중복이다 — {item['id']!r}")
        seen.add(item["id"])
        extra = {}
        for key in _OPTIONAL_STR:
            v = item.get(key, "")
            if v is None:
                v = ""
            if not isinstance(v, str):
                raise CueError(f"{p} {item['id']}: {key} 는 문자열이어야 한다({type(v).__name__})")
            extra[key] = v.strip()
        extra["topic"] = item.get("topic", "") or ""
        briefs = item.get("briefs")
        if briefs is None:
            # 못 채운 섹션의 기본 상태다 — "키가 없음"과 "명시적 null" 을 같게
            # 본다. 19섹션을 순차로 옮기는 동안 나머지는 이 상태로 남는다.
            briefs = {}
        elif not isinstance(briefs, dict):
            # `item.get("briefs") or {}` 로 감싸면 `briefs: false`·`briefs: 0`
            # 처럼 falsy 이면서 매핑도 아닌 값이 조용히 빈 매핑으로 둔갑해
            # 아래 매핑 검사 자체를 건너뛴다(리뷰 Minor). `None`·빠짐만 빈
            # 매핑으로 받고 그 외에는 여기서 먼저 거절한다.
            raise CueError(
                f"{p} {item['id']}: briefs 는 매핑이어야 한다 — "
                f"지금은 {type(briefs).__name__}({briefs!r})"
            )
        if briefs:
            missing = set(LEVEL_NAMES) - set(briefs)
            if missing:
                # 한 수준만 빠지면 그 수준의 시연이 통째로 옛 지시문으로
                # 돈다 — 조용히 품질이 떨어지므로 기동에서 막는다.
                raise CueError(f"{p} {item['id']}: 빠진 수준이 있다 — {sorted(missing)}")
            for name, b in briefs.items():
                if not isinstance(b, dict):
                    raise CueError(
                        f"{p} {item['id']} {name}: briefs 항목이 매핑이어야 한다 — "
                        f"지금은 {type(b).__name__}({b!r})"
                    )
                for field_name in ("mc_brief", "docent_brief"):
                    v = b.get(field_name)
                    # `docent_brief: true` 처럼 YAML 이 boolean 으로 파싱한 값은
                    # `not b.get(...)` 같은 truthiness 검사만으로는 못 거른다 —
                    # `bool` 은 `int` 의 하위형이라는 함정과 같은 자리다
                    # (`stage/levels.py` 96행, `stage/server.py::_seq_field`).
                    # 걸러지지 않으면 `brief_for` 가 파이썬 `True` 를 그대로
                    # 돌려줘 프롬프트에 리터럴 "True" 가 꽂힌다(리뷰 Important 1).
                    if not isinstance(v, str) or not v.strip():
                        raise CueError(
                            f"{p} {item['id']} {name}.{field_name} 는 비어 있지 "
                            f"않은 문자열이어야 한다 — 지금은 {type(v).__name__}({v!r})"
                        )
                if "points" in b:
                    # 수준별 포인트는 턴 수와 질문을 수준마다 다르게 만든다 —
                    # 조용히 무시하면 저작자가 고친 줄이 시연에 안 나온다.
                    raise CueError(
                        f"{p} {item['id']} {name}: points 는 큐 최상위로 옮겼다 — "
                        "턴마다 ask 하나와 수준별 answers 를 둔다"
                    )
                if "guard" in b:
                    g = b["guard"]
                    if not isinstance(g, str) or not g.strip():
                        raise CueError(
                            f"{p} {item['id']} {name}.guard 는 비어 있지 않은 "
                            f"문자열이어야 한다 — 지금은 {type(g).__name__}({g!r})"
                        )
        extra["briefs"] = briefs
        extra["points"] = _load_turns(p, item["id"], item.get("points"))
        for key in ("mc_emotion", "mc_after_emotion"):
            extra[key] = _emotion(f"{p} {item['id']}", key, item.get(key, DEFAULT_EMOTION))
        if extra["points"] and not extra["mc_after"]:
            raise CueError(
                f"{p} {item['id']}: points 가 있는데 mc_after 가 없다 — "
                "마지막 라운드 뒤 받아치기로 합류할 자리가 없다"
            )
        out.append(Cue(**{k: item[k] for k in _REQUIRED}, **extra))
    return out


def _emotion(where: str, key: str, value, allow_empty: bool = False) -> str:
    """감정 태그 하나를 검사한다. 모르는 태그는 **거절한다** — 오타("놀라움")가
    조용히 기본값으로 떨어지면 그 줄만 몸짓이 사라지는데 아무도 모른다."""
    if allow_empty and value == "":
        return ""
    if value not in EMOTIONS:
        raise CueError(
            f"{where}: {key} 가 모르는 감정이다 — {value!r} (쓸 수 있는 값: {', '.join(EMOTIONS)})"
        )
    return value


def _load_turns(p: pathlib.Path, cue_id: str, raw) -> tuple[Turn, ...]:
    """큐 최상위 `points` 를 턴 목록으로 읽는다. **없으면 거절한다.**

    해설은 전부 검수한 고정 대본이다(2026-09-23 전환) — 대본이 없는 큐는 시연에서
    오프닝만 말하고 해설 없이 지나간다. 조용히 넘어가면 저작을 빠뜨린 큐가 있어도
    아무도 모르므로 기동에서 막는다. ~~없으면 옛 단일 라운드(`docent_brief` 생성)로
    돌았다~~ — 그 경로는 같은 전환에서 지웠다.
    """
    if raw is None:
        raise CueError(f"{p} {cue_id}: points(턴 대본)가 없다 — 해설은 고정 대본이다")
    if not isinstance(raw, list) or not raw:
        raise CueError(
            f"{p} {cue_id}: points 는 비어 있지 않은 목록이어야 한다 — "
            f"지금은 {type(raw).__name__}({raw!r})"
        )
    if len(raw) > MAX_TURNS:
        raise CueError(
            f"{p} {cue_id}: 턴이 {len(raw)}개다 — 최대 {MAX_TURNS}턴(모든 수준 공통)"
        )
    turns = []
    for ti, t in enumerate(raw):
        where = f"{p} {cue_id} points[{ti}]"
        if not isinstance(t, dict):
            # 옛 형식(사실 문장 한 줄)이 여기로 온다. 그 형식이 사회자가 사실을
            # 되묻고 도슨트가 확인만 하는 대화를 만들었다.
            raise CueError(
                f"{where} 는 {{ask, answers}} 매핑이어야 한다 — "
                f"지금은 {type(t).__name__}({t!r})"
            )
        ask = t.get("ask")
        if ti == 0:
            if ask is not None:
                raise CueError(
                    f"{where}: 첫 턴에는 ask 를 두지 않는다 — 오프닝(mc/mc_brief)이 묻는다"
                )
            if "ask_emotion" in t:
                raise CueError(
                    f"{where}: 첫 턴에는 ask_emotion 을 두지 않는다 — 오프닝의 감정은 mc_emotion 이다"
                )
            ask = ""
        elif not isinstance(ask, str) or not ask.strip():
            raise CueError(
                f"{where}: ask(사회자 질문)가 비어 있거나 문자열이 아니다 — "
                f"지금은 {type(ask).__name__}({ask!r})"
            )
        answers = t.get("answers")
        if not isinstance(answers, dict):
            raise CueError(
                f"{where}.answers 는 수준별 매핑이어야 한다 — 지금은 {type(answers).__name__}"
            )
        for name in LEVEL_NAMES:
            a = answers.get(name)
            if not isinstance(a, str) or not a.strip():
                raise CueError(
                    f"{where}.answers.{name} 는 비어 있지 않은 문자열이어야 한다 — "
                    f"지금은 {type(a).__name__}({a!r})"
                )
        turns.append(Turn(
            ask.strip(),
            {n: answers[n].strip() for n in LEVEL_NAMES},
            ask_emotion=_emotion(where, "ask_emotion", t.get("ask_emotion", DEFAULT_EMOTION)),
            answer_emotion=_emotion(where, "answer_emotion", t.get("answer_emotion", DEFAULT_EMOTION)),
            listener_emotion=_emotion(
                where, "listener_emotion", t.get("listener_emotion", ""), allow_empty=True
            ),
        ))
    return tuple(turns)


def is_advance(text: str) -> bool:
    """관람객 발화가 '다음으로' 라는 뜻인가.

    규칙은 하나다: 비어 있지 않고, 길이 가드 이내이고, 물음표가 없고,
    마지막 낱말이 전환어 어근으로 시작하되 그 뒤에 붙은 글자가 2자
    이하일 때만 진행 신호로 본다. 그 외에는 전부 아니다.

    **왜 "마지막 낱말 + 접미 길이"인가.** 한국어 전환 발화는 전환어로
    끝나고("...다음", "...계속"), 전환어 어근으로 시작하는 질문의 서술어도
    있다("다음이에요?", "계속되나요"). 마지막 낱말이 전환어로 "시작한다"는
    것만으로는 이 둘을 못 가른다 — 조사·짧은 어미(-으로, -하죠, -해)는
    어근 뒤에 2자 이내로 붙지만, 서술어는 그보다 길게 붙는다. 그 길이
    차이가 경계선이다.

    **왜 "?" 는 따로, 가장 먼저 보는가.** 이 함수 안에서 유일하게
    모호하지 않은 신호이기 때문이다. 관람객이 직접 물음표로 표시한
    질문이면, 마지막 낱말의 접미가 2자 이내라도(예: "다음?", "계속?")
    전환으로 읽으면 안 된다 — 접미 길이 경계는 접미의 *길이*만 보고
    *내용*은 안 보므로, "?" 검사를 위치+접미 판정 뒤에 두거나 그 판정과
    같은 자격으로 묶으면 다시 밀려난다.

    **판정 오류의 방향은 의도적으로 비대칭이다.** 전환을 놓치면(예:
    "다음 걸로 진행해주세요"처럼 전환어가 문장 중간에 낀 요청) LLM 이
    답을 만들고, 관람객이 다시 "다음"이라 말하거나 운영자 콘솔로 복구
    할 수 있다 — 싼 손실이다. 질문을 전환으로 잘못 먹으면 관람객의
    물음이 통째로 사라진다 — 비싼 손실이다. 이 함수를 다음에 고칠 때도
    이 방향을 지켜야 한다: 애매하면 전환이 아니라고 판정한다.
    """
    t = text.strip()
    if not t or len(t) > _ADVANCE_MAX_CHARS or "?" in t:
        return False

    last_word = t.split()[-1]
    return any(
        last_word.startswith(w) and len(last_word) - len(w) <= 2
        for w in _ADVANCE_WORDS
    )


# 관람객 질문으로 받을 최소 조건(2026-09-24). 수치는 감독 로그의 **실제 잡음 전사**에서
# 뽑았다 — `'아'`(71회)·`'ome'`·`'omeomeome…'`·`'Up until theλιλιλι…'`·`'Watch out.'`·
# `'ㅋㅋㅋㅋ'`·`'세로 세로 세로'`. 로봇 쪽 환각 필터(`voice_loop._hallucinated`)는 **공백으로
# 나뉜 토막**의 반복만 봐서 이것들이 전부 통과했다.
#
# 문턱은 **통과시킬 가장 짧은 질문**에 맞췄다(docs/lessons.md 「문턱은 막으려는 것이
# 아니라 통과시킬 것에 맞춘다」): "왜요?"·"누가요?" 가 한글 두 음절이다. 영어·약어가 섞인
# 질문("GMDSS가 뭐예요?", "5G는요?")도 통과해야 하므로 라틴 문자·숫자는 막지 않고,
# 한글 음절 수만 센다.
_MIN_HANGUL_SYLLABLES = 2
_HANGUL_SYLLABLE = re.compile(r"[가-힣]")
# 한글(음절·자모)·라틴·숫자 밖의 글자. Whisper 가 잡음에서 그리스·키릴 문자를 낸다.
_FOREIGN_SCRIPT = re.compile(r"[^0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]")
# 1~4글자 토막이 3번 이상 **붙어서** 반복되고 전체의 60% 이상을 차지하면 반복 환각이다.
# `'하하하 재밌어요'`(43%)는 통과하고 `'세로세로세로'`(100%)는 걸린다.
_REPEAT_UNIT_MAX = 4
_REPEAT_MIN_TIMES = 3
_REPEAT_MIN_SHARE = 0.6


# 질문으로 볼 낱말(물음말·요청). `looks_like_question` 이 쓴다.
_QUESTION_WORDS = (
    "뭐", "무엇", "무슨", "왜", "어떻게", "어떤", "어느", "누구", "누가", "언제", "어디", "몇", "얼마",
    "알려", "설명", "궁금",
)


def looks_like_question(text: str) -> bool:
    """관람객 말이 **질문(또는 설명 요청)** 처럼 보이는가 — 단독 모드가 확인 멘트를 붙일지 가른다.

    틀려도 싼 쪽으로 기운다: 질문을 가벼운 말로 잘못 보면 멘트 없이 1~2초 쉬고 답한다(조금 느릴 뿐).
    가벼운 말을 질문으로 잘못 보면 "감사합니다" 에 "잠깐 생각해 볼게요" 가 붙는다(어색함 — 실측으로 이
    판정이 생겼다). 그래서 물음표(STT 가 붙인다)나 물음말·요청어가 **있을 때만** 질문이다.
    """
    t = text.strip()
    return "?" in t or "？" in t or any(w in t for w in _QUESTION_WORDS)


def noise_reason(text: str) -> str | None:
    """이 전사를 관람객 질문으로 **보지 않을** 이유. 질문으로 받아도 되면 None.

    감독(`Director.on_heard`)이 LISTENING 에서 부른다 — 진행어(`is_advance`)는 먼저
    통과시킨 뒤다. 잡음에 LLM 이 답하는 것은 침묵보다 나쁘다: 관람객은 아무 말도
    안 했는데 로봇이 "좋은 질문이네요" 하고 엉뚱한 답을 한다.

    판정 오류의 방향: 여기서 질문을 잘못 버리면 관람객이 다시 묻거나 운영자가
    본다(경고가 남는다). 잡음을 질문으로 받으면 회복할 길이 없다 — 이미 말했다.
    """
    flat = re.sub(r"[\W_]+", "", text or "")
    if not flat:
        return "빈 전사"
    if _FOREIGN_SCRIPT.search(flat):
        return "한글·영문 밖 문자"
    n = len(_HANGUL_SYLLABLE.findall(flat))
    if n < _MIN_HANGUL_SYLLABLES:
        return f"한글 음절 {n}개"
    for size in range(1, _REPEAT_UNIT_MAX + 1):
        pattern = rf"(.{{{size}}})\1{{{_REPEAT_MIN_TIMES - 1},}}"
        for m in re.finditer(pattern, flat):
            if len(m.group(0)) >= len(flat) * _REPEAT_MIN_SHARE:
                return "같은 토막 반복"
    return None


class CueSheet:
    """큐 커서. 어디까지 진행했는지만 안다."""

    def __init__(self, cues: list[Cue]) -> None:
        if not cues:
            raise CueError("큐시트가 비어 있다")
        self._cues = list(cues)
        self._i = 0

    @property
    def index(self) -> int:
        return self._i

    @property
    def done(self) -> bool:
        return self._i >= len(self._cues) - 1

    def current(self) -> Cue:
        return self._cues[self._i]

    def advance(self) -> Cue | None:
        """다음 큐로 간다. 마지막이면 None 을 주고 커서는 머문다."""
        if self._i >= len(self._cues) - 1:
            return None
        self._i += 1
        return self._cues[self._i]

    def back(self) -> Cue | None:
        """이전 큐로 되돌린다. 첫 큐면 None 을 주고 커서는 머문다.

        `is_advance` 의 오판(설계 §7 "STT 오인식으로 진행 폭주")을 사람이
        되돌리는 유일한 길이다. 커서를 앞으로만 옮길 수 있으면 수동
        오버라이드가 반쪽이다 — 넘어가 버린 섹션을 되찾을 방법이 없었다.
        """
        if self._i <= 0:
            return None
        self._i -= 1
        return self._cues[self._i]

    def reset(self) -> None:
        self._i = 0

    def cues(self) -> tuple[Cue, ...]:
        """전체 큐 — 대시보드 런다운이 목록을 그린다. 바깥에서 못 바꾸게 튜플로 준다."""
        return tuple(self._cues)

    def find(self, cue_id: str) -> int | None:
        """큐 id 의 위치. 없으면 None — 호출자가 경고한다."""
        for i, c in enumerate(self._cues):
            if c.id == cue_id:
                return i
        return None

    def seek(self, index: int) -> Cue:
        """커서를 옮긴다. 범위 밖이면 IndexError 이고 **커서는 그대로다** — 조용히
        끝에 붙이면 엉뚱한 섹션이 시작돼도 아무도 모른다."""
        if not 0 <= index < len(self._cues):
            raise IndexError(f"큐 위치 {index} 는 0..{len(self._cues) - 1} 밖이다")
        self._i = index
        return self._cues[index]
