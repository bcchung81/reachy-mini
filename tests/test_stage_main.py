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
from stage.levels import load_levels

# 테스트용 수준 하나 — `build_generate(level)` 이 실제 페르소나 파일
# (`data/personas/*.md`)을 읽어 프롬프트를 조립하므로 진짜 `Level` 이 필요하다.
_레벨 = load_levels()["일반"]


def test_LLM_호출이_직렬화된다():
    """`build_generate` 는 역할별 `LLMClient` 를 두되 락은 **하나**를 공유한다.

    감독은 이 함수를 두 갈래에서 부른다: 큐 시작 때 띄우는 생성 스레드
    (`_generate_docent`)와 관람객 질문 응답(`_answer`). 겹치면 **한쪽이 다른
    쪽의 이력으로 답한다** — 지난 섹션 맥락으로 질문에 답하거나 그 반대다.
    역할이 둘로 늘어난 뒤에도(클라이언트 객체가 mc/docent 로 갈렸다) 이
    직렬화가 유지되는지 보려고 두 역할을 섞어 부른다.
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
        generate = stage_main.build_generate(_레벨)
        역할들 = ["mc", "docent"]
        ts = [
            threading.Thread(target=generate, args=(역할들[i % 2], f"지시{i}", []))
            for i in range(6)
        ]
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
        generate = stage_main.build_generate(_레벨)
        assert generate(
            "docent", "지시", [{"role": "assistant", "content": "사회자: 앞선 말"}]
        ) == "답"
    finally:
        stage_main.LLMClient = 원래

    assert 본것 == [[{"role": "assistant", "content": "사회자: 앞선 말"}]]


def test_도슨트_프롬프트에_음성_출력_규칙이_있다():
    """도슨트 답은 TTS 로 읽힌다 — 목록·이모지가 나오면 그 기호를 소리 내 읽는다(리뷰 B5).

    `_system_prompt()` 는 이 태스크에서 지워지고 `stage.prompts.build_system_prompt`
    가 그 자리를 대신한다 — 조립 함수가 바뀌어도 이 규칙 자체는 살아 있어야 한다.
    """
    from stage.prompts import build_system_prompt
    p = build_system_prompt("docent", _레벨)
    assert "음성" in p and "목록" in p and "이모지" in p


# `test_시스템_프롬프트에_분량_규정이_있다` 는 `tests/test_prompts.py` 로 옮겼다 —
# 검사 대상이던 `stage.__main__._system_prompt()` 가 이 태스크에서 지워지고
# `stage.prompts.build_system_prompt()` 가 그 자리를 대신하기 때문이다. 옮기며
# 수치 범위 단언(브리프 교체본)과 원래의 하한 문구 단언을 **모두** 남겼다 —
# 한쪽만 남기면 리뷰로 잡은 하한 강제 문구가 조립 과정에서 조용히 빠져도
# 테스트가 계속 통과한다.


def test_기동_로그에_수준이_찍힌다(capsys, monkeypatch):
    """엉뚱한 수준으로 도는 것은 조용히 품질만 떨어지는 전형적인 실패다."""
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "초등")
    import stage.__main__ as m
    from stage.levels import level_of_env
    m.announce_level(level_of_env(load_levels()))
    assert "초등" in capsys.readouterr().out


def test_모듈_문서에_수준_환경변수가_적혀_있다():
    """`announce_level()` 이 실제로 쓰는 두 환경변수(REACHY_AUDIENCE_LEVEL/
    REACHY_LEVELS_PATH)가 기동 문서에서 빠지면, "주소는 전부 환경변수다" 규약대로
    이 파일 머리말만 보고 배포하는 사람이 그 존재를 알 길이 없다."""
    doc = stage_main.__doc__ or ""
    assert "REACHY_AUDIENCE_LEVEL" in doc
    assert "REACHY_LEVELS_PATH" in doc
