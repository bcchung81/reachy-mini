import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from tts import pick_voice


def test_한글은_유나():
    assert pick_voice("안녕하세요. 오늘 기분이 좋아요.") == "Yuna"


def test_영문은_영어_음성():
    assert pick_voice("I feel quite cheerful today.") == "Samantha"


def test_일본어_가나는_일본어_음성():
    assert pick_voice("こんにちは。元気ですか。") == "Kyoko"


def test_한자만_있으면_중국어_음성():
    assert pick_voice("你好，今天天气很好。") == "Tingting"


def test_한글이_조금이라도_섞이면_한국어_우선():
    # 로봇의 기본 언어가 한국어다. 영어 단어가 섞인 한국어 문장을
    # 영어 음성으로 읽으면 문장 전체가 무너진다.
    assert pick_voice("오늘 mood가 아주 좋아요.") == "Yuna"


def test_숫자나_기호뿐이면_기본값():
    assert pick_voice("123 ... !") == "Yuna"
