"""speak() — 받은 텍스트를 말하고 움직인다. LLM 을 부르지 않는다.

1대 구성에서는 respond() 가 LLM 을 부른 뒤 이것을 쓰고,
2대 구성에서는 무대감독이 만든 텍스트로 이것만 쓴다.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import session


class FakeSpeaker:
    def __init__(self):
        self.spoken: list[str] = []
        self.many: list[list[str]] = []
        self.speaking = False

    def speak(self, text, seed=None):
        self.spoken.append(text)

    def speak_many(self, texts):
        self.many.append(list(texts))


class FakePlayer:
    def __init__(self):
        self.played: list[tuple[str, bool]] = []

    def play_for(self, category, force=False):
        self.played.append((category, force))
        return f"move_{category}"

    def play(self, name, force=False):
        self.played.append((name, force))
        return name


def test_텍스트를_말한다():
    sp = FakeSpeaker()
    session.speak("안녕하세요", sp, None)
    assert sp.spoken == ["안녕하세요"]


def test_로봇이_없으면_말만_한다():
    sp = FakeSpeaker()
    session.speak("안녕하세요", sp, None)      # player=None
    assert sp.spoken == ["안녕하세요"]


def test_모션을_함께_낸다():
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("안녕하세요", sp, pl, category="greet")
    assert pl.played == [("greet", False)]


def test_빈_텍스트는_말하지도_움직이지도_않는다():
    # 감독이 빈 대사를 보내는 사고가 나도 로봇이 헛돌지 않는다.
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("   ", sp, pl)
    assert sp.spoken == [] and pl.played == []


def test_재생_완료를_기다리지_않는다():
    # 기다리면 마이크 루프가 멈춰 끼어들기 판정이 한 번도 돌지 않는다.
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("안녕하세요", sp, pl)
    assert not hasattr(sp, "waited")


def test_respond_는_여전히_동작한다():
    # 1대 구성 회귀 방지 — speak() 를 뽄아내도 기존 경로가 살아 있어야 한다.
    assert callable(session.respond)
