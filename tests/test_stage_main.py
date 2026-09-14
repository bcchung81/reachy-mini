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
