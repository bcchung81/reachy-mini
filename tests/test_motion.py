import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import sound as sound_mod  # noqa: E402
from motion import CATEGORY_MOVES, MotionPlayer, classify  # noqa: E402


class FakeMove:
    def __init__(self, name, duration=3.0):
        self.name = name
        self.duration = duration
        self.sound_path = f"/fake/{name}.ogg"

    def __repr__(self):
        return f"<{self.name}>"


class FakeMoves:
    def list_moves(self):
        from emotions import IDLE_MOVES

        return sorted({m for ms in CATEGORY_MOVES.values() for m in ms} | set(IDLE_MOVES))

    def get(self, name):
        return FakeMove(name)


class FakeDriver:
    """`RobotDriver` 계약만 흉내낸다 — 로봇에 쓰는 것은 드라이버뿐이다."""

    def __init__(self):
        self.played: list[tuple[str, bool]] = []
        self.cancelled = 0
        self.quiet = False
        self._playing = False
        self._idle = False

    def set_quiet(self, quiet):
        self.quiet = quiet

    def play(self, move, idle=False, blend_s=0.3):
        self.played.append((move.name, idle))
        self._playing, self._idle = True, idle

    def cancel(self):
        self.cancelled += 1
        self._playing, self._idle = False, False

    @property
    def playing(self):
        return self._playing

    @property
    def playing_idle(self):
        return self._idle

    def finish(self):
        """모션이 자연스럽게 끝난 상황."""
        self._playing, self._idle = False, False


class FakeSpeaker:
    def __init__(self):
        self.sounds: list[tuple[int, int]] = []  # (바이트수, 레이트)

    def play_sound(self, pcm, rate):
        self.sounds.append((len(pcm), rate))


def _player(monkeypatch, *, sound_bytes=4800):
    """디코딩을 타지 않는 MotionPlayer. `full` 인자를 그대로 기록한다."""
    calls: list[bool] = []

    def fake_load(path, rate, full=False):
        calls.append(full)
        return b"\x00" * (sound_bytes * (10 if full else 1))

    monkeypatch.setattr(sound_mod, "load", fake_load)
    driver, speaker = FakeDriver(), FakeSpeaker()
    return MotionPlayer(driver, FakeMoves(), speaker), driver, speaker, calls


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


# ── 로봇에 직접 쓰지 않는다 ─────────────────────────────────────


def test_로봇에_직접_쓰지_않고_드라이버에만_건다(monkeypatch):
    """공식 규칙: set_target 을 부르는 곳은 하나여야 한다.

    MotionPlayer 가 예전처럼 자기 스레드에서 play_move 를 돌면 쓰는 주체가 둘이 된다.
    여기서는 드라이버에 거는 것 말고 아무것도 하지 않는지 본다.
    """
    p, driver, _, _ = _player(monkeypatch)
    p.play_for("ack")
    assert len(driver.played) == 1
    assert not hasattr(p, "_mini"), "MotionPlayer 가 로봇 핸들을 들고 있으면 안 된다"


# ── 우선순위 ───────────────────────────────────────────────────


def test_재생중_일반요청은_버려진다(monkeypatch):
    p, driver, _, _ = _player(monkeypatch)
    assert p.play_for("ack") is not None
    assert p.play_for("greet") is None  # 겹치는 감정 모션은 버린다
    assert len(driver.played) == 1


def test_응답_모션은_대기_모션을_밀어낸다(monkeypatch):
    # 사용자가 말을 걸었는데 혼자 놀던 동작이 막고 있으면 안 된다
    p, driver, _, _ = _player(monkeypatch)
    p.play("waiting", idle=True)
    assert p.play_for("greet") is not None
    assert len(driver.played) == 2
    assert driver.played[1][1] is False  # 두 번째는 응답 모션


def test_대기_모션은_응답_모션을_밀어내지_못한다(monkeypatch):
    p, driver, _, _ = _player(monkeypatch)
    p.play_for("greet")
    assert p.play("waiting", idle=True) is None
    assert len(driver.played) == 1


def test_공연은_진행중인_모션을_끊고_재생된다(monkeypatch):
    # 노래 요청은 상호작용의 목적 자체다 — busy 라고 버리면 시연이 깨진다
    p, driver, _, _ = _player(monkeypatch)
    p.play_for("ack")
    name = p.play_for("perform", force=True)
    assert name in ("dance2", "dance3")
    assert len(driver.played) == 2


def test_모션이_끝나면_다음_요청을_받는다(monkeypatch):
    p, driver, _, _ = _player(monkeypatch)
    p.play_for("ack")
    driver.finish()
    assert p.play_for("greet") is not None


# ── 사운드 ─────────────────────────────────────────────────────


def test_응답_모션은_발성을_발화_큐에_넣는다(monkeypatch):
    """SDK 의 play_move(sound=True) 는 no_media 에서 무음이다 — 우리가 낸다."""
    p, _, speaker, _ = _player(monkeypatch)
    p.play_for("ack")
    assert len(speaker.sounds) == 1


def test_대기_모션은_소리를_내지_않는다(monkeypatch):
    """소리를 내면 마이크 게이팅이 걸려 말을 못 걸게 된다."""
    p, _, speaker, _ = _player(monkeypatch)
    assert p.play("yes1", idle=True) == "yes1"
    assert speaker.sounds == []
    assert p.moving is True  # 다만 몸은 움직인다


def test_리액션은_앞부분만_공연은_전체(monkeypatch):
    """리액션 발성은 2~12초라 통째로 붙이면 답변이 그만큼 늦는다."""
    p, driver, speaker, calls = _player(monkeypatch)
    p.play_for("ack")
    assert calls == [False], "리액션은 잘라 써야 한다"
    driver.finish()
    p.play_for("perform")
    assert calls == [False, True], "공연은 통째로 재생해야 한다"
    assert speaker.sounds[1][0] > speaker.sounds[0][0]


def test_발성_디코딩이_실패해도_모션은_돈다(monkeypatch):
    def boom(path, rate, full=False):
        raise RuntimeError("디코딩 실패")

    monkeypatch.setattr(sound_mod, "load", boom)
    driver, speaker = FakeDriver(), FakeSpeaker()
    p = MotionPlayer(driver, FakeMoves(), speaker)
    assert p.play_for("ack") is not None
    assert len(driver.played) == 1
    assert speaker.sounds == []


def test_스피커가_없어도_동작한다(monkeypatch):
    """--no-robot 이나 테스트 경로에서 speaker 없이 쓸 수 있어야 한다."""
    monkeypatch.setattr(sound_mod, "load", lambda *a, **k: b"\x00" * 100)
    p = MotionPlayer(FakeDriver(), FakeMoves())
    assert p.play_for("ack") is not None


def test_우선순위_검사와_걸기가_원자적이다(monkeypatch):
    """호출자가 둘이다(voice_loop·Idler). 검사 후 걸기 전에 다른 스레드가
    끼어들면 대기 모션이 방금 시작된 응답 모션을 덮는다 — TOCTOU.

    Idler 의 `playing` 검사 순간에 응답 모션 요청이 도착한 상황을 재현한다:
    검사 지점에서 응답 스레드를 출발시키고 잠깐 기다린다. 잠금이 있으면 응답은
    잠금 밖에서 대기하다가 **대기 모션이 걸린 뒤에** 들어와 그걸 밀어낸다(정상
    우선순위). 잠금이 없으면 응답이 먼저 걸리고 대기 모션이 그걸 덮는다.
    """
    import threading as th

    monkeypatch.setattr(sound_mod, "load", lambda *a, **k: b"\x00" * 100)
    driver = FakeDriver()
    p = MotionPlayer(driver, FakeMoves(), FakeSpeaker())

    cls = type(driver)
    real = cls.playing
    rival = {"thread": None}

    def hijack(self):
        cls.playing = real  # 한 번만 — 응답 스레드의 재검사는 진짜를 본다
        t = th.Thread(target=lambda: p.play_for("greet"), daemon=True)
        rival["thread"] = t
        t.start()
        t.join(timeout=0.05)  # 잠금이 제대로면 여기서 타임아웃된다(밖에서 대기 중)
        return real.fget(self)

    cls.playing = property(hijack)
    try:
        p.play("waiting", idle=True)
    finally:
        cls.playing = real
    assert rival["thread"] is not None
    rival["thread"].join(timeout=1.0)  # 응답 스레드가 끝난 뒤에 판정한다
    assert not rival["thread"].is_alive(), "응답 스레드가 교착됐다"
    # 응답 모션(greet)이 최종 승자여야 한다 — 마지막에 걸린 것이 idle 이면 덮인 것
    assert driver.played, "아무것도 안 걸렸다"
    assert driver.played[-1][1] is False, "대기 모션이 응답 모션을 덮었다(TOCTOU)"


# ── 모터 정숙 (§12) ────────────────────────────────────────────


def test_사용자_발화는_대기_모션을_끊지만_응답_모션은_두다(monkeypatch):
    """대기 모션은 '심심할 때 혼자 노는 것' — 사용자 발화보다 우선일 수 없다.
    응답 모션은 로봇 발화 턴과 겹치는 정당한 동작이라 두다."""
    p, driver, _, _ = _player(monkeypatch)
    # 대기 모션 중 사용자가 말을 시작하면 → 끊는다
    p.play("waiting", idle=True)
    p.set_user_speaking(True)
    assert driver.cancelled == 1
    assert p.user_speaking is True
    p.set_user_speaking(False)
    # 응답 모션 중이면 → 두다
    p.play_for("ack")
    p.set_user_speaking(True)
    assert driver.cancelled == 1, "응답 모션까지 끊었다"


def test_사용자_발화가_드라이버_정숙으로_전달된다(monkeypatch):
    p, driver, _, _ = _player(monkeypatch)
    p.set_user_speaking(True)
    assert driver.quiet is True
    p.set_user_speaking(False)
    assert driver.quiet is False


def test_사용자_발화_중에는_대기_모션을_돌리지_않는다(monkeypatch):
    """Idler 억제 — 서보 소음이 STT 를 오염시킨다."""
    import time as _t

    from idler import Idler

    monkeypatch.setattr(sound_mod, "load", lambda *a, **k: b"\x00" * 100)
    driver = FakeDriver()
    p = MotionPlayer(driver, FakeMoves(), FakeSpeaker())
    p.user_speaking = True
    idler = Idler(p, lambda: False, min_gap=0.01, max_gap=0.02)
    idler.start()
    _t.sleep(0.15)
    assert driver.played == [], "사용자 발화 중인데 대기 모션이 돌았다"
    p.user_speaking = False
    _t.sleep(0.15)
    idler.stop()
    assert driver.played, "발화가 끝났는데 대기 모션이 돌아오지 않았다"


# ── 끼어들기 ───────────────────────────────────────────────────


def test_취소하면_드라이버가_모션을_끊는다(monkeypatch):
    """춤은 18초짜리다 — 소리만 끊고 몸이 계속 추면 안 끊긴 것이다."""
    p, driver, _, _ = _player(monkeypatch)
    p.play_for("perform")
    p.cancel()
    assert driver.cancelled == 1
    assert p.moving is False
