"""큐시트 로더와 진행 신호 판정.

정본은 `docs/exhibit-guide.md` 이고 이 모듈이 읽는 `data/cues.yaml` 은 그 위에
얹은 진행 단위다. 둘이 어긋나면 큐시트를 고친다 — 반대가 아니다.
"""

import os
import pathlib
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
    # 수준 → {mc_brief, docent_brief}. 비어 있으면 옛 `docent_brief` 로 폴백한다
    # — 큐시트 19섹션을 한 번에 옮길 수 없으므로 섞여 있는 기간이 있다.
    briefs: dict = field(default_factory=dict)

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
        extra["briefs"] = briefs
        out.append(Cue(**{k: item[k] for k in _REQUIRED}, **extra))
    return out


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
