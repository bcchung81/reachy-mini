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
        self.waited = False

    def speak(self, text, seed=None):
        self.spoken.append(text)

    def speak_many(self, texts):
        self.many.append(list(texts))

    def wait_idle(self, timeout=None):
        self.waited = True


class FakePlayer:
    def __init__(self):
        self.played: list[tuple[str, bool]] = []

    def play_for(self, category, force=False, idle=False):
        self.played.append((category, force))
        return f"move_{category}"

    def play(self, name, force=False):
        self.played.append((name, force))
        return name


def test_텍스트를_말한다():
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("안녕하세요", sp, pl)
    assert sp.spoken == ["안녕하세요"]


def test_로봇이_없으면_말만_한다():
    # player=None 이면 모션 없이 말만 한다.
    sp = FakeSpeaker()
    session.speak("안녕하세요", sp, None)
    assert sp.spoken == ["안녕하세요"]
    # 암묵적: player가 없으면 pl.played 를 쓸 수 없으므로 검증은 위 한 줄만


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
    # speak() 가 speaker.wait_idle() 을 부르면 이 테스트가 붉어진다.
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("안녕하세요", sp, pl)
    assert sp.waited is False


def test_respond_는_여전히_동작한다():
    # 1대 구성 회귀 방지 — speak() 를 뽑아내도 기존 경로가 살아 있어야 한다.
    assert callable(session.respond)


def test_category_를_안_주면_문장으로_고른다():
    """리뷰 B1 — 2대 모드의 say 는 category 를 안 주는데 기본값 'neutral' 은 모션 표에
    없어 언제나 None 이었다. 로봇이 말하는 내내 몸이 가만히 있었다."""
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("도슨트, 햄이 뭔가요?", sp, pl)
    assert pl.played == [("curious", False)]
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("1912년 4월 타이타닉호가 침몰할 때 잭 필립스가 구조를 요청했습니다.", sp, pl)
    assert pl.played == [("no", False)]


# ── 무대 발화를 문장 단위 요청으로(voice-fix-brief V1) ─────────────────────
#
# 원인: 무대 모드는 감독 대사(최대 280자, 40~90초 분량) 전체를 speaker.speak()
# 하나(=TTS 요청 하나)로 보냈다. Qwen3-TTS 서버는 요청을 하나씩 순서대로 처리
# 하고 클라이언트가 연결을 끊어도 끊긴 요청을 끝까지 합성한다(실측 65.3초).
# 그래서 다음 요청이 QWEN_TIMEOUT(90초)을 넘겨 로컬 합성기(실기 Linux 는
# espeak-ng — 남성 기계음)로 폴백했다. 요청을 문장 단위로 쪼개면 끊었을 때
# 서버가 붙잡는 시간이 문장 하나로 준다.


def test_문장이_둘_이상이면_speak_many_로_나간다():
    # 감독 대사는 문장 사이에 공백이 없다("…입니다.주파수란…") — split_sentences
    # 가 나눈 문장 리스트가 그대로 speak_many 에 실려야 한다.
    sp, pl = FakeSpeaker(), FakePlayer()
    text = "빛은 초당 30만km를 이동합니다.주파수란 초당 진동수를 말합니다."
    session.speak(text, sp, pl)
    assert sp.spoken == []
    assert sp.many == [
        ["빛은 초당 30만km를 이동합니다.", "주파수란 초당 진동수를 말합니다."]
    ]


def test_한_문장이면_기존처럼_speak_로_나간다():
    # 기존 테스트(test_텍스트를_말한다 등)가 이미 이 경로를 지키지만,
    # 문장 분리가 끼어든 뒤에도 회귀하지 않는지 명시적으로 다시 잡는다.
    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("이 신호는 2.4GHz 대역을 씁니다.", sp, pl)  # 소수점 — 안 나뉜다
    assert sp.spoken == ["이 신호는 2.4GHz 대역을 씁니다."]
    assert sp.many == []


def test_연도로_시작하는_문장도_나뉜다():
    sp, pl = FakeSpeaker(), FakePlayer()
    text = "무선통신을 실용화했습니다.1901년에는 대서양을 건넜습니다."
    session.speak(text, sp, pl)
    assert sp.many == [
        ["무선통신을 실용화했습니다.", "1901년에는 대서양을 건넜습니다."]
    ]


def test_설명_범주는_모션을_내지_않는다():
    """대본의 기본 감정 '설명' 이다(설계 §12.2) — 해설 내내 모션이 터지면
    안 되고, 그렇다고 키워드 추측으로 내려가서도 안 된다."""
    from motion import NO_MOTION

    sp, pl = FakeSpeaker(), FakePlayer()
    session.speak("전파는 빛과 같은 전자기파입니다.", sp, pl, category=NO_MOTION)
    assert pl.played == [], "'설명' 인데 모션을 냈다"
    assert sp.spoken == ["전파는 빛과 같은 전자기파입니다."]


def test_문장_분리가_돼도_모션은_발화_전체에_한_번이다():
    # split_sentences 는 TTS 요청 단위만 바꾼다 — 모션은 지금처럼 전체 텍스트
    # 기준으로 한 번만 고르고 재생한다(문장마다 모션이 다시 튀면 안 된다).
    sp, pl = FakeSpeaker(), FakePlayer()
    text = "빛은 초당 30만km를 이동합니다.주파수란 초당 진동수를 말합니다."
    session.speak(text, sp, pl)
    assert len(pl.played) == 1
