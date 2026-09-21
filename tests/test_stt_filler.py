"""STT 무음 상용구 판정(`apps/voice_chat/voice_chat/voice_loop.py::_filler`).

실기 2대 리허설(2026-09-21)에서 두 문구가 관람객 질문으로 처리됐다:
"다음 영상에서 만나요."(마이크 최대 0.002, 사실상 무음) → 도슨트가 "다음 영상에서
다시 만나 뵙기를 희망하시는군요" 라고 답했다. "Come." 도 질문이 됐다.

`voice_loop` 는 다른 테스트처럼 **함수 안에서** import 한다 — 모듈 수준의
환경변수 읽기가 테스트 간에 섞이지 않게.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))


@pytest.mark.parametrize("text", [
    "다음 영상에서 만나요.",   # 실측
    "다음 영상에서 만나요",
    "Come.",                  # 실측
    "come",
    "감사합니다.",             # 기존 항목 — 구두점 차이를 두 번 적던 것을 한 번으로
    "감사합니다",
    "Thank you.",
    "!",                      # 구두점만 남는 전사(2026-09-09 실기 `!` 전례)
    " 。 ",
])
def test_무음_상용구는_버린다(text):
    import voice_loop as vl
    assert vl._filler(text) is True


@pytest.mark.parametrize("text", [
    "다음",                   # 진행 키워드 — 막으면 관람객이 진행을 못 시킨다
    "다음으로 넘어가 주세요",
    "전파는 어떻게 이동하나요?",
    "감사합니다 그런데 질문이 있어요",
    "Come here please",
])
def test_말이_되는_전사는_살린다(text):
    import voice_loop as vl
    assert vl._filler(text) is False
