"""무대감독 기동 배선(`stage/__main__.py`).

콘솔과 함께 **테스트가 하나도 없던 곳**이다. 여기서 잘못 배선하면 시연 당일
기동에서만 드러난다.
"""

import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import stage.__main__ as stage_main


def test_LLM_호출이_직렬화된다():
    """`build_generate` 는 `LLMClient` 하나를 공유하며 호출마다
    `client.history` 를 통째로 갈아끼운다.

    감독은 이 함수를 두 갈래에서 부른다: 큐 시작 때 띄우는 생성 스레드
    (`_generate_docent`)와 관람객 질문 응답(`_answer`). 겹치면 **한쪽이 다른
    쪽의 이력으로 답한다** — 지난 섹션 맥락으로 질문에 답하거나 그 반대다.
    """
    동시_최대 = 0
    지금 = 0
    자물쇠 = threading.Lock()

    class 가짜LLM:
        def __init__(self, **kw):
            self.history: list[dict] = []

        def chat_stream(self, brief, image):
            nonlocal 동시_최대, 지금
            with 자물쇠:
                지금 += 1
                동시_최대 = max(동시_최대, 지금)
            time.sleep(0.02)      # 왕복이 겹칠 틈을 준다
            with 자물쇠:
                지금 -= 1
            return iter(["답"])

    원래 = stage_main.LLMClient
    stage_main.LLMClient = 가짜LLM
    try:
        generate = stage_main.build_generate()
        ts = [threading.Thread(target=generate, args=(f"지시{i}", [])) for i in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(5)
            assert not t.is_alive(), "생성 스레드가 안 끝났다(교착 의심)"
    finally:
        stage_main.LLMClient = 원래

    assert 동시_최대 == 1, f"LLM 호출이 겹쳤다(최대 동시 {동시_최대})"


def test_이력을_호출마다_갈아끼운다():
    """감독이 준 이력이 그대로 실려야 한다 — 락을 넣으면서 이게 깨지면
    도슨트가 맥락 없이 말한다."""
    본것: list[list[dict]] = []

    class 가짜LLM:
        def __init__(self, **kw):
            self.history: list[dict] = []

        def chat_stream(self, brief, image):
            본것.append(list(self.history))
            return iter(["답"])

    원래 = stage_main.LLMClient
    stage_main.LLMClient = 가짜LLM
    try:
        generate = stage_main.build_generate()
        assert generate("지시", [{"role": "assistant", "content": "사회자: 앞선 말"}]) == "답"
    finally:
        stage_main.LLMClient = 원래

    assert 본것 == [[{"role": "assistant", "content": "사회자: 앞선 말"}]]


def test_도슨트_프롬프트에_음성_출력_규칙이_있다():
    """도슨트 답은 TTS 로 읽힌다 — 목록·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5)."""
    p = stage_main._system_prompt()
    assert "음성" in p and "목록" in p and "이모지" in p


def test_시스템_프롬프트에_분량_규정이_있다():
    """리뷰 지적: "이내" 부재/"문장" 존재만 보면 이 태스크 이전 프롬프트로
    되돌려도 트리비얼하게 통과한다 — "이내" 는 원래 프롬프트 어디에도 없고,
    무관한 기존 TTS 규칙("문장은 마침표로 끝낸다.")에 이미 "문장" 이 있기
    때문이다. 이 태스크가 실제로 새로 넣은 하한 지시 문구("채워서"/"이상"과
    한 문장 답을 명시적으로 거부하는 문장)가 있는지를 직접 본다.
    """
    import stage.__main__ as m
    p = m._system_prompt()
    # 상한만 주면 모델이 하단에 붙는다 — 하한을 "채워서" 라는 동사로 명시한다.
    assert "채워" in p, p
    # 하한 수치 표현("이상")이 실제로 있어야 한다 — 없으면 상한만 있는 옛 프롬프트다.
    assert "이상" in p, p
    # 한 문장 답이 지시 위반임을 명시적으로 못박는 문장이 있어야 한다.
    assert "한 문장" in p and "아니다" in p, p


def test_기동_로그에_수준이_찍힌다(capsys, monkeypatch):
    """엉뚱한 수준으로 도는 것은 조용히 품질만 떨어지는 전형적인 실패다."""
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "초등")
    import stage.__main__ as m
    m.announce_level()
    assert "초등" in capsys.readouterr().out
