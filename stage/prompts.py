"""시스템 프롬프트 조립 — [공통 규약 + 역할 페르소나 + 수준 지침].

페르소나를 코드가 아니라 데이터에 둔 이유: 시연 전에 사람이 읽고 고쳐야
하는데 코드에 박혀 있으면 못 고친다. 이 저장소에는 이미 프롬프트를 파일로
두는 선례가 있다(`apps/voice_chat/voice_chat/prompt.md`).
"""

import pathlib

from stage.levels import Level

ROLES = ("mc", "docent")

# TTS 가 읽는다 — 목록 기호·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5).
# 이 규칙이 있는 프롬프트 **본문 자체**가 마크다운을 쓰면 자기모순이다 — 모델이
# 시스템 프롬프트 서식(강조 `**`)을 출력 스타일로 따라 하면 그 별표가 그대로
# 새어 TTS 가 읽는다(리뷰 Minor 5). 그래서 아래 어떤 조각도 `**`·목록 기호를
# 쓰지 않는다 — 강조가 필요하면 낱말 선택이나 어순으로 한다.
_COMMON = (
    "네 말은 음성으로 읽힌다. 목록·이모지·특수문자·마크다운을 쓰지 않고 "
    "문장은 마침표로 끝낸다."
)

# 사회자는 해설하지 않는다(`data/personas/mc.md`) — 반응은 짧다. 도슨트처럼
# 분량을 수준의 수치로 두면, 전문가 수준에서 사회자가 "5~7문장 260~400자를
# 채워서" 라는 자기 페르소나와 모순되는 지시를 받는다(리뷰 Important 2) —
# 받아치기 생성(다음 태스크)이 켜지는 순간 사회자가 도슨트 분량으로 떠든다.
# 그래서 사회자의 분량은 **수준과 무관하게 고정**한다 — 짧은 반응은 어느
# 수준에서나 짧다. 어휘·깊이·숫자 정밀도·출처 노출은 역할과 무관하게 수준을
# 그대로 따른다(초등에게 말하는 사회자도 쉬운 말을 쓴다) — `build_system_prompt`
# 가 `level.vocabulary` 등을 두 역할 모두에 그대로 얹는 이유다.
_MC_MIN_SENTENCES = 1
_MC_MAX_SENTENCES = 3
_MC_MIN_CHARS = 40
_MC_MAX_CHARS = 120


class PromptError(ValueError):
    """페르소나 파일이 없거나 비어 있다.

    `stage/levels.py::LevelError` 와 같은 이유로 소리 내서 실패한다 — 빈
    페르소나로 조용히 돌면 "역할 없는 프롬프트" 가 되는데, 그 증상은 시연장
    에서 대사가 밋밋해지는 것으로만 나타나 원인을 못 찾는다.
    """


def personas_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "personas"


def _read_persona(role: str) -> str:
    path = personas_dir() / f"{role}.md"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise PromptError(f"페르소나 파일이 없다: {path}") from exc
    if not text:
        raise PromptError(f"페르소나 파일이 비어 있다: {path}")
    return text


def _amount_for(role: str, level: Level) -> str:
    """분량 지시. **역할마다 다른 축이다**(리뷰 Important 2) — 슬롯·역할이
    다른 축인 것과 같은 이유로, 분량도 "무엇을 말하는가" 가 아니라
    "누가 말하는가" 의 함수다.

    도슨트는 수준의 함수다: 상한만 주면 모델이 하단에 붙으므로(design spec
    §5) 범위를 주고, 그마저 "N문장 이내" 로 오독될 수 있어 하한을 동사로
    다시 못박는다(그리고 한 문장 답을 명시적으로 거부하는 문장). 이 문구를
    지우면 리뷰로 잡았던 문제가 조용히 되돌아온다.

    사회자는 수준과 무관하게 고정이다 — "해설이 아니다" 같은 도슨트용
    문구는 사회자에게는 거짓말이라 넣지 않는다(사회자는 애초에 해설하지
    않는다, `data/personas/mc.md`).
    """
    if role == "mc":
        return (
            f"{_MC_MIN_SENTENCES}~{_MC_MAX_SENTENCES}문장으로, "
            f"{_MC_MIN_CHARS}~{_MC_MAX_CHARS}자 사이로 짧게 반응한다."
        )
    return (
        f"{level.min_sentences}~{level.max_sentences}문장으로, "
        f"{level.min_chars}~{level.max_chars}자 사이로 말한다. "
        f"최소 {level.min_sentences}문장 이상, {level.min_chars}자 이상을 "
        "채워서 말한다. 한 문장짜리 답은 해설이 아니다."
    )


def build_system_prompt(role: str, level: Level) -> str:
    if role not in ROLES:
        raise ValueError(f"모르는 역할: {role!r} — 쓸 수 있는 값: {', '.join(ROLES)}")
    persona = _read_persona(role)
    amount = _amount_for(role, level)
    return "\n\n".join([persona, _COMMON, amount,
                        level.vocabulary, level.depth, level.numbers, level.sources])
