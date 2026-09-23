import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))                              # 감독 쪽(stage/) — 저장소에서만 가능
sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))
from emotions import EMOTION_MOVES, IDLE_MOVES, find_request, pick_idle

# 2026-07-29 RecordedMoves('pollen-robotics/reachy-mini-emotions-library')
# .list_moves() 실측 85개
KNOWN = {
    "amazed1", "anxiety1", "attentive1", "attentive2", "boredom1", "boredom2",
    "calming1", "cheerful1", "come1", "confused1", "contempt1", "curious1",
    "dance1", "dance2", "dance3", "disgusted1", "displeased1", "displeased2",
    "downcast1", "dying1", "electric1", "enthusiastic1", "enthusiastic2",
    "exhausted1", "fear1", "frustrated1", "furious1", "go_away1", "grateful1",
    "helpful1", "helpful2", "impatient1", "impatient2", "incomprehensible2",
    "indifferent1", "inquiring1", "inquiring2", "inquiring3", "irritated1",
    "irritated2", "laughing1", "laughing2", "lonely1", "lost1", "loving1",
    "mini-deep-sleep", "no1", "no_excited1", "no_sad1", "oops1", "oops2",
    "proud1", "proud2", "proud3", "rage1", "relief1", "relief2", "reprimand1",
    "reprimand2", "reprimand3", "resigned1", "sad1", "sad2", "scared1",
    "serenity1", "shy1", "sleep1", "success1", "surprised1", "surprised2",
    "thoughtful1", "thoughtful2", "tired1", "toc-toc-toc", "uncertain1",
    "uncomfortable1", "understanding1", "understanding2", "waiting",
    "wake-mini-up", "welcoming1", "welcoming2", "yes1", "yes_sad1",
}


def test_매핑된_모션이_모두_실재한다():
    for moves in EMOTION_MOVES.values():
        for m in moves:
            assert m in KNOWN, f"{m}: 데이터셋에 없는 모션"


def test_대기_모션이_모두_실재한다():
    for m in IDLE_MOVES:
        assert m in KNOWN, f"{m}: 데이터셋에 없는 모션"


def test_감정_연기_요청을_잡는다():
    assert find_request("슬픈 표정 지어봐") in EMOTION_MOVES["슬픔"]
    assert find_request("화난 거 표현해봐") in EMOTION_MOVES["화남"]
    assert find_request("기쁜 표정 보여줘") in EMOTION_MOVES["기쁨"]
    assert find_request("놀란 표정 지어봐") in EMOTION_MOVES["놀람"]
    assert find_request("부끄러운 표정 해봐") in EMOTION_MOVES["부끄러움"]


def test_감정만_말한_것은_연기가_아니다():
    # '나 슬퍼' 는 공감할 상황이지 연기 요청이 아니다 — LLM 이 답해야 한다
    assert find_request("나 오늘 좀 슬퍼") is None
    assert find_request("화나는 일이 있었어") is None
    assert find_request("기뻐!") is None


def test_요청만_있고_감정이_없으면_연기가_아니다():
    assert find_request("노래 한번 해봐") is None
    assert find_request("춤 보여줘") is None


def test_대기_모션은_카탈로그에_있는_것만_고른다():
    assert pick_idle({"attentive1", "waiting"}) in {"attentive1", "waiting"}
    assert pick_idle(set()) is None
    assert pick_idle({"존재하지않는모션"}) is None


# ── 대본 감정 태그 (설계 §12.2·§12.5) ────────────────────────────────
#
# 감정 어휘는 **두 벌**이다 — 감독은 `stage/cues.py::EMOTIONS`, 로봇 앱은
# `motion.EMOTION_CATEGORY`. 로봇 앱은 `stage/` 를 import 할 수 없다(실기에는
# 앱만 올라간다, `tests/test_deployment_contract.py` 가 그걸 고정한다).
# 그 대가로 **두 곳이 조용히 어긋날 수 있다**: 감독이 새 태그를 보내면 로봇은
# "모르는 태그" 로 키워드 추측에 떨어지고, 로그를 보지 않으면 그냥 "모션이 좀
# 이상하다" 로만 보인다. 여기서 묶는다 — 저장소 테스트는 양쪽을 동시에 들여올
# 수 있는 유일한 자리다.


def test_감정_어휘가_감독과_로봇에서_같다():
    from motion import STAGE_EMOTIONS

    from stage.cues import EMOTIONS

    assert tuple(STAGE_EMOTIONS) == tuple(EMOTIONS), (
        f"감독 {tuple(EMOTIONS)} ≠ 로봇 {tuple(STAGE_EMOTIONS)}"
    )


def test_감독의_기본_감정도_로봇이_안다():
    from motion import EMOTION_CATEGORY

    from stage.cues import DEFAULT_EMOTION

    assert DEFAULT_EMOTION in EMOTION_CATEGORY


def test_감정_태그가_모두_모션_범주로_이어진다():
    """태그마다 갈 곳이 있어야 한다 — 없으면 그 대사만 조용히 안 움직인다."""
    from motion import CATEGORY_MOVES, EMOTION_CATEGORY, NO_MOTION, STAGE_EMOTIONS

    assert set(EMOTION_CATEGORY) == set(STAGE_EMOTIONS)
    for tag, category in EMOTION_CATEGORY.items():
        assert category == NO_MOTION or category in CATEGORY_MOVES, (
            f"{tag}: 모션 범주 {category!r} 가 CATEGORY_MOVES 에 없다"
        )


def test_계약된_감정_매핑_그대로다():
    """설계 §12.2 의 표. 바뀌면 큐시트 저작과 어긋나므로 여기서 먼저 깨진다."""
    from motion import EMOTION_CATEGORY, NO_MOTION

    assert EMOTION_CATEGORY == {
        "반가움": "greet",
        "기쁨": "joy",
        "놀람": "surprise",
        "궁금": "curious",
        "뿌듯": "proud",
        "끄덕": "ack",
        "아쉬움": "sad",
        "설명": NO_MOTION,
    }


def test_새_범주_proud_와_sad_의_모션이_실재한다():
    from motion import CATEGORY_MOVES

    assert CATEGORY_MOVES["proud"] == ["proud1", "proud2", "proud3"]
    assert CATEGORY_MOVES["sad"] == ["sad1", "downcast1"]
    for name in CATEGORY_MOVES["proud"] + CATEGORY_MOVES["sad"]:
        assert name in KNOWN, f"{name}: 데이터셋에 없는 모션"
