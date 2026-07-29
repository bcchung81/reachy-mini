import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from motion import CATEGORY_MOVES, MotionPlayer, classify


class FakeMoves:
    def list_moves(self):
        from emotions import IDLE_MOVES

        return sorted({m for ms in CATEGORY_MOVES.values() for m in ms} | set(IDLE_MOVES))

    def get(self, name):
        return name


class FakeMini:
    """play_move 가 duration 동안 블록하고, cancel_move 로 즉시 끊긴다."""

    def __init__(self, duration=5.0):
        self.played = []
        self.sounds = []
        self.cancelled = 0
        self.duration = duration
        self._cancel = threading.Event()

    def cancel_move(self):
        self.cancelled += 1
        self._cancel.set()

    def play_move(self, move, initial_goto_duration=0.0, sound=True):
        self._cancel.clear()
        self.played.append(move)
        self.sounds.append(sound)
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


def test_대기_모션은_소리를_내지_않고_마이크를_막지_않는다():
    mini = FakeMini(duration=5.0)
    p = MotionPlayer(mini, FakeMoves())
    assert p.play("yes1", idle=True) == "yes1"
    assert mini.sounds == [False]  # 소리를 내면 마이크를 막아야 한다
    assert p.moving is True  # 애니메이터는 물러나야 하고
    assert p.busy is False  # 마이크는 열려 있어야 한다


def test_응답_모션은_소리를_내고_마이크를_막는다():
    mini = FakeMini(duration=5.0)
    p = MotionPlayer(mini, FakeMoves())
    p.play_for("ack")
    assert mini.sounds == [True]
    assert p.busy is True


def test_응답_모션은_대기_모션을_밀어낸다():
    # 사용자가 말을 걸었는데 혼자 놀던 동작이 막고 있으면 안 된다
    mini = FakeMini(duration=5.0)
    p = MotionPlayer(mini, FakeMoves())
    p.play("waiting", idle=True)
    assert p.play_for("greet") is not None
    assert mini.cancelled == 1


def test_대기_모션은_응답_모션을_밀어내지_못한다():
    mini = FakeMini(duration=5.0)
    p = MotionPlayer(mini, FakeMoves())
    p.play_for("greet")
    assert p.play("waiting", idle=True) is None
    assert mini.cancelled == 0


def test_공연은_진행중인_모션을_끊고_재생된다():
    # 노래 요청은 상호작용의 목적 자체다 — busy 라고 버리면 시연이 깨진다
    mini = FakeMini(duration=5.0)
    p = MotionPlayer(mini, FakeMoves())
    p.play_for("ack")
    name = p.play_for("perform", force=True)
    assert name in ("dance2", "dance3")
    assert mini.cancelled == 1
    assert len(mini.played) == 2
