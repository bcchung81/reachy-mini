"""감정 표현 요청 해석 + 대기 중 재생할 모션 목록.

모션 이름은 전부 pollen-robotics/reachy-mini-emotions-library 실측(85개)에서 확인했다.

`나 슬퍼` 와 `슬픈 표정 지어봐` 는 다르다. 앞은 공감할 상황이고 뒤는 연기 요청이다.
그래서 **감정 단어와 요청 표시가 둘 다 있어야** 감정 연기로 판정한다.
"""

import random

# 한국어 감정 표현 → 모션 후보
EMOTION_MOVES: dict[str, list[str]] = {
    "기쁨": ["cheerful1", "enthusiastic1", "laughing1"],
    "슬픔": ["sad1", "sad2", "downcast1"],
    "화남": ["furious1", "rage1", "irritated1"],
    "놀람": ["surprised1", "amazed1"],
    "무서움": ["fear1", "scared1"],
    "지루함": ["boredom1", "boredom2"],
    "피곤": ["tired1", "exhausted1"],
    "부끄러움": ["shy1"],
    "뿌듯함": ["proud1", "proud2", "proud3"],
    "사랑": ["loving1"],
    "궁금함": ["curious1", "inquiring1"],
    "혼란": ["confused1", "lost1", "uncertain1"],
    "고마움": ["grateful1"],
    "안도": ["relief1", "relief2"],
    "역겨움": ["disgusted1"],
    "외로움": ["lonely1"],
    "짜증": ["frustrated1", "impatient1"],
    "평온": ["serenity1", "calming1"],
}

# 감정 단어 → 위 표의 열쇠. 어간만 적어 활용형을 함께 잡는다.
_WORDS: list[tuple[str, str]] = [
    ("기뻐", "기쁨"), ("기쁜", "기쁨"), ("기쁨", "기쁨"), ("신나", "기쁨"), ("행복", "기쁨"),
    ("슬퍼", "슬픔"), ("슬픈", "슬픔"), ("슬픔", "슬픔"), ("우울", "슬픔"),
    ("화나", "화남"), ("화난", "화남"), ("분노", "화남"), ("성난", "화남"),
    ("놀라", "놀람"), ("놀란", "놀람"), ("놀람", "놀람"),
    ("무서", "무서움"), ("겁나", "무서움"), ("공포", "무서움"),
    ("지루", "지루함"), ("심심", "지루함"),
    ("피곤", "피곤"), ("졸려", "피곤"), ("지쳐", "피곤"), ("지친", "피곤"),
    ("부끄", "부끄러움"), ("수줍", "부끄러움"),
    ("뿌듯", "뿌듯함"), ("자랑", "뿌듯함"), ("자신만만", "뿌듯함"),
    ("사랑", "사랑"), ("좋아하는", "사랑"),
    ("궁금", "궁금함"),
    ("혼란", "혼란"), ("헷갈", "혼란"), ("당황", "혼란"),
    ("고마", "고마움"), ("감사", "고마움"),
    ("안도", "안도"), ("다행", "안도"),
    ("역겨", "역겨움"), ("싫은", "역겨움"),
    ("외로", "외로움"), ("쓸쓸", "외로움"),
    ("짜증", "짜증"), ("답답", "짜증"),
    ("평온", "평온"), ("차분", "평온"),
]

# 연기 요청임을 알리는 표시. 이게 없으면 그냥 감정을 말한 것이다.
_REQUEST = ["표현", "표정", "지어", "해봐", "해 봐", "보여줘", "보여 줘", "흉내", "연기", "지어봐"]


def find_request(text: str) -> str | None:
    """감정 연기 요청이면 재생할 모션 이름을, 아니면 None 을 돌려준다."""
    t = text.replace(" ", "")
    if not any(m.replace(" ", "") in t for m in _REQUEST):
        return None
    for word, key in _WORDS:
        if word in t:
            return random.choice(EMOTION_MOVES[key])
    return None


# 대기 중 재생할 모션. 조건이 셋이다 —
#   · 짧을 것(긴 춤이 걸리면 사용자가 말을 걸 때 방해된다)
#   · 조용히 있어 보일 것(sleep·dying 처럼 죽은 척하는 것은 뺀다)
#   · 갑작스럽지 않을 것(rage·furious 처럼 격한 것은 뺀다)
IDLE_MOVES: list[str] = [
    "attentive1", "attentive2", "waiting", "curious1", "inquiring1", "inquiring2",
    "thoughtful1", "thoughtful2", "boredom1", "shy1", "serenity1", "calming1",
    "relief1", "uncertain1", "indifferent1", "understanding1",
]


# 무대(2대) 모드의 대기 모션(2026-09-24). 무대에서 "대기" 는 대개 **상대가 말하는 동안**이다
# — 위 목록의 `boredom1`(지루해 졸기)·`indifferent1`("뭐 어때")·`shy1`·`uncertain1` 이 도슨트
# 설명 도중에 무작위로 나와 사회자가 딴청을 피우는 것처럼 보였다(앱 로그: 도슨트 차례에
# `[대기 모션 indifferent1]`). 무대에서는 **듣는 자세**만 남긴다. `simple_nod`·`uh_huh_tilt` 는
# 춤 라이브러리(소리 없음) — 못 읽은 로봇에서는 `available` 거름에서 빠진다.
STAGE_IDLE_MOVES: list[str] = [
    "attentive1", "attentive2", "understanding1", "thoughtful1", "thoughtful2",
    "serenity1", "inquiring2", "simple_nod", "uh_huh_tilt",
]


def pick_idle(available: set[str], moves: list[str] | None = None) -> str | None:
    """대기 모션 하나를 고른다. 카탈로그에 없는 이름은 제외한다.

    `moves` 를 안 주면 1대 모드 목록(`IDLE_MOVES`)이다. 무대 모드는 `STAGE_IDLE_MOVES`.
    """
    candidates = [n for n in (moves or IDLE_MOVES) if n in available]
    return random.choice(candidates) if candidates else None
