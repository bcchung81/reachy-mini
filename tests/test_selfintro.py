import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from selfintro import SCRIPT, matches


def test_만들어진_방식을_묻는_질문을_잡는다():
    assert matches("넌 어떻게 만들어졌어?")
    assert matches("너 어떻게 만들었어")
    assert matches("어떻게 개발했어?")
    assert matches("어떤 모델 쓰니?")
    assert matches("무슨 기술로 동작해?")
    assert matches("구조가 어떻게 돼?")


def test_띄어쓰기가_달라도_잡는다():
    # STT 결과는 띄어쓰기가 들쭉날쭉하다
    assert matches("넌어떻게만들어졌어")
    assert matches("어떻게  만들어 졌어")


def test_평범한_대화는_잡지_않는다():
    assert not matches("안녕!")
    assert not matches("오늘 날씨 어때?")
    assert not matches("재밌는 얘기 해줘")
    assert not matches("노래 한번 불러줘")
    assert not matches("영어로 대답해줘")


def test_대본_문장은_모두_한글을_포함한다():
    # 순수 영문 문장이 되면 tts.pick_voice 가 영어 음성으로 넘겨 흐름이 끊긴다
    for s in SCRIPT:
        assert any("가" <= ch <= "힣" for ch in s), s


def test_대본이_비어있지_않다():
    assert len(SCRIPT) >= 5
