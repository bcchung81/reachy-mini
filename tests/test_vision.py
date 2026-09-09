"""카메라를 언제 켜는가 — 시각 질문 판별.

**보수적으로 켠다.** 못 봐서 다시 묻는 것보다, 매번 켜서 텍스트 첫 토큰
0.105s 를 0.4~0.6s 로 만드는 것이 시연에서 더 나쁘다(2026-09-09 실측).
LLM 에게 "카메라가 필요하니?" 를 되묻는 방식은 왕복이 하나 더 붙어 안 쓴다.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import config  # noqa: E402
import vision  # noqa: E402


def test_시각_질문이면_카메라를_켠다():
    for q in ["이게 뭐야", "앞에 뭐 보여?", "내가 뭘 들고 있게", "여기 몇 명 있어",
              "이거 무슨 색이야", "이것 좀 봐줘", "지금 뭐가 보여"]:
        assert vision.wants_camera(q), q


def test_일상_질문에는_안_켠다():
    for q in ["오늘 기분 어때", "타이타닉 이야기 해줘", "농담 하나 해줘",
              "노래 불러줘", "무선국 검사가 뭐야", "전파가 뭐예요"]:
        assert not vision.wants_camera(q), q


def test_자기소개_질문이_시각으로_새지_않는다():
    """`누구야` 는 자기소개다. respond() 의 첫 분기(selfintro)가 먼저 걸러 주지만,
    판별기 자체도 안 걸려야 순서에 기대지 않는다."""
    for q in ["너는 누구야", "너 누구니", "네 소개 해줘"]:
        assert not vision.wants_camera(q), q


def test_스위치로_끌_수_있다(monkeypatch):
    monkeypatch.setattr(config, "get", lambda n, d: "0" if n == "REACHY_VISION" else d)
    assert not vision.wants_camera("이게 뭐야")


def test_빈_입력은_거짓():
    assert not vision.wants_camera("")
