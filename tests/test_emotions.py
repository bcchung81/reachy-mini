import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
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
