import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stt_server import DEFAULT_LANGUAGE, resolve_language


def test_auto는_None으로_바뀐다():
    # None 이라야 whisper 가 언어를 감지한다
    assert resolve_language("auto") is None
    assert resolve_language("AUTO") is None
    assert resolve_language("detect") is None


def test_구체적_언어는_그대로():
    assert resolve_language("ko") == "ko"
    assert resolve_language("en") == "en"
    assert resolve_language(" JA ") == "ja"


def test_허용밖_언어면_재전사한다():
    from stt_server import should_retry

    allowed = {"ko", "en"}
    # 실측 사례: '네' → vi, '고마워' → ja 로 오판되어 쓰레기가 나왔다
    assert should_retry(None, "vi", allowed) is True
    assert should_retry(None, "ja", allowed) is True


def test_허용된_언어는_그대로_쓴다():
    from stt_server import should_retry

    allowed = {"ko", "en"}
    assert should_retry(None, "ko", allowed) is False
    assert should_retry(None, "en", allowed) is False
    assert should_retry(None, "EN", allowed) is False


def test_언어를_명시한_요청은_재전사하지_않는다():
    from stt_server import should_retry

    # 호출자가 ja 를 달라고 했으면 ja 가 나오는 게 맞다
    assert should_retry("ja", "ja", {"ko", "en"}) is False


def test_값이_없으면_기본값():
    # 예전 코드는 `or DEFAULT_LANGUAGE` 라서 auto 도 여기로 떨어졌다 — 그게 결함이었다
    assert resolve_language(None) == DEFAULT_LANGUAGE
    assert resolve_language("") == DEFAULT_LANGUAGE
    assert resolve_language("   ") == DEFAULT_LANGUAGE
