import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from motion import CATEGORY_MOVES, MotionPlayer, classify


class FakeMoves:
    def list_moves(self):
        return sorted({m for ms in CATEGORY_MOVES.values() for m in ms})

    def get(self, name):
        return name


class FakeMini:
    """play_move 가 duration 동안 블록하고, cancel_move 로 즉시 끊긴다."""

    def __init__(self, duration=5.0):
        self.played = []
        self.cancelled = 0
        self.duration = duration
        self._cancel = threading.Event()

    def cancel_move(self):
        self.cancelled += 1
        self._cancel.set()

    def play_move(self, move, initial_goto_duration=0.0):
        self._cancel.clear()
        self.played.append(move)
        self._cancel.wait(self.duration)

# 2026-07-29 RecordedMoves('pollen-robotics/reachy-mini-emotions-library')
# .list_moves() 실측 85개 중 이 앱이 쓰는 부분집합
KNOWN_MOVES = {
    "welcoming1", "cheerful1", "laughing1", "enthusiastic1", "success1",
    "surprised1", "amazed1", "curious1", "inquiring1", "thoughtful1",
    "no1", "sad1", "yes1", "understanding1", "attentive1",
    "dance2", "dance3",
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


def test_노래_춤_요청은_공연으로():
    assert classify("노래 불러줘") == "perform"
    assert classify("춤 한번 춰봐") == "perform"


def test_공연은_사운드_있는_긴_모션():
    # dance2/dance3 는 자체 사운드를 갖는다 — say 로 노래를 흉내내는 것보다 낫다
    assert set(CATEGORY_MOVES["perform"]) == {"dance2", "dance3"}


def test_공연이_기쁨보다_우선():
    # "재밌는 노래 불러줘" 는 joy 키워드('재밌')도 맞지만 공연이어야 한다
    assert classify("재밌는 노래 불러줘") == "perform"


def test_재생중_일반요청은_버려진다():
    p = MotionPlayer(FakeMini(duration=5.0), FakeMoves())
    assert p.play_for("ack") is not None
    assert p.play_for("greet") is None  # 겹치는 감정 모션은 버린다


def test_공연은_진행중인_모션을_끊고_재생된다():
    # 노래 요청은 상호작용의 목적 자체다 — busy 라고 버리면 시연이 깨진다
    mini = FakeMini(duration=5.0)
    p = MotionPlayer(mini, FakeMoves())
    p.play_for("ack")
    name = p.play_for("perform", force=True)
    assert name in ("dance2", "dance3")
    assert mini.cancelled == 1
    assert len(mini.played) == 2
