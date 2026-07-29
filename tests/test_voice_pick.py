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


def test_같은_언어_절은_하나로_묶인다():
    from tts import group_by_voice

    out = group_by_voice(["안녕하세요.", "반가워요.", "오늘 어때요?"])
    assert out == [("Yuna", "안녕하세요. 반가워요. 오늘 어때요?")]


def test_언어가_바뀌면_묶음이_갈린다():
    # 실제 발생한 결함: 한국어와 중국어를 한 문자열로 합치면 한글 우선 규칙 때문에
    # 유나가 중국어까지 읽어 발음이 깨졌다.
    from tts import group_by_voice

    out = group_by_voice(
        [
            "하지만 조금 더 이어서 이야기해 드릴게요.",
            "小兔子很喜欢吃草。",
            "它总是蹦蹦跳跳的。",
        ]
    )
    assert out == [
        ("Yuna", "하지만 조금 더 이어서 이야기해 드릴게요."),
        ("Tingting", "小兔子很喜欢吃草。 它总是蹦蹦跳跳的。"),
    ]


def test_언어가_여러번_바뀌어도_순서가_유지된다():
    from tts import group_by_voice

    out = group_by_voice(["안녕.", "Hello.", "また会いましょう。", "잘 가."])
    assert [v for v, _ in out] == ["Yuna", "Samantha", "Kyoko", "Yuna"]


def test_빈_절은_묶음에서_빠진다():
    from tts import group_by_voice

    assert group_by_voice(["안녕.", "   ", ""]) == [("Yuna", "안녕.")]
