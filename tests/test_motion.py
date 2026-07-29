import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from motion import CATEGORY_MOVES, classify

# 2026-07-29 RecordedMoves('pollen-robotics/reachy-mini-emotions-library')
# .list_moves() 실측 85개 중 이 앱이 쓰는 부분집합
KNOWN_MOVES = {
    "welcoming1", "cheerful1", "laughing1", "enthusiastic1", "success1",
    "surprised1", "amazed1", "curious1", "inquiring1", "thoughtful1",
    "no1", "sad1", "yes1", "understanding1", "attentive1",
}


def test_모든_매핑_모션이_실재한다():
    for moves in CATEGORY_MOVES.values():
        for m in moves:
            assert m in KNOWN_MOVES, f"{m}: 데이터셋에 없는 모션"


def test_범주_분류():
    assert classify("안녕! 오늘 처음 보네") == "greet"
    assert classify("와 진짜 최고다 너무 좋아") == "joy"
    assert classify("헐 대박 말도 안 돼") == "surprise"
    assert classify("그건 좀 싫어") == "no"
    assert classify("이건 왜 이렇게 되는 거야") == "curious"


def test_물음표는_궁금으로():
    assert classify("내일 비 올까?") == "curious"


def test_매칭_실패는_수긍으로():
    assert classify("음 그렇군") == "ack"
