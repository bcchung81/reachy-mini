"""시스템 프롬프트 조립 — [공통 규약 + 역할 페르소나 + 수준 지침].

페르소나를 **코드가 아니라 데이터**에 둔 이유: 시연 전에 사람이 읽고 고쳐야
하는데 코드에 박혀 있으면 못 고친다. 이 저장소에는 이미 프롬프트를 파일로
두는 선례가 있다(`apps/voice_chat/voice_chat/prompt.md`).
"""

import pathlib

from stage.levels import Level

ROLES = ("mc", "docent")

# TTS 가 읽는다 — 목록 기호·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5).
_COMMON = (
    "네 말은 음성으로 읽힌다. 목록·이모지·특수문자·마크다운을 쓰지 않고 "
    "문장은 마침표로 끝낸다."
)


def personas_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "personas"


def build_system_prompt(role: str, level: Level) -> str:
    if role not in ROLES:
        raise ValueError(f"모르는 역할: {role!r} — 쓸 수 있는 값: {', '.join(ROLES)}")
    persona = (personas_dir() / f"{role}.md").read_text(encoding="utf-8").strip()
    # **분량은 범위로 준다.** 상한만 주면 모델이 하단에 붙는다(design spec §5) —
    # 큐시트가 "N문장 이내" 로만 적혀 있던 시절에 실제로 겪은 문제다.
    #
    # 범위를 숫자로만 줘도 "N문장 이내" 로 다시 오독될 수 있어(상한만 본다),
    # 하한을 **동사로도** 못박는다("채워서"/"이상", 그리고 한 문장 답을
    # 명시적으로 거부하는 문장). 이 문구를 지우면 리뷰로 잡았던 그 문제가
    # 조용히 되돌아온다 — `tests/test_prompts.py::test_시스템_프롬프트에_분량_규정이_있다`
    # 가 수치 범위와 이 문구를 **모두** 본다.
    amount = (
        f"{level.min_sentences}~{level.max_sentences}문장으로, "
        f"{level.min_chars}~{level.max_chars}자 사이로 말한다. "
        f"최소 {level.min_sentences}문장 이상, {level.min_chars}자 이상을 "
        "**채워서** 말한다. 한 문장짜리 답은 해설이 아니다."
    )
    return "\n\n".join([persona, _COMMON, amount,
                        level.vocabulary, level.depth, level.numbers, level.sources])
