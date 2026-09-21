"""무대감독 기동 배선(`stage/__main__.py`).

콘솔과 함께 **테스트가 하나도 없던 곳**이다. 여기서 잘못 배선하면 시연 당일
기동에서만 드러난다.
"""

import pathlib
import sys
import threading
import time

import pytest

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
    m.announce_level(level_of_env(load_levels()), explicit=True)
    assert "초등" in capsys.readouterr().out


def test_수준_출처_라벨은_전달받은_explicit만_보고_환경변수를_다시_읽지_않는다(
    monkeypatch, capsys
):
    """리뷰 Minor 4 — `announce_level` 이 `lv` 는 인자로 받으면서 "환경변수인지
    기본값인지" 라벨만 몰래 `os.environ` 을 다시 봐서 판정하면, 호출자가 env 와
    다른 값을 넘겼을 때 로그가 거짓 출처를 찍는다. 환경변수를 **설정해 두고도**
    `explicit=False` 를 주면 라벨이 인자를 따라야 한다 — 그러지 않으면 함수가
    인자를 무시하고 `os.environ` 을 다시 읽은 것이다.
    """
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "전문가")  # 환경변수는 있지만
    stage_main.announce_level(_레벨, explicit=False)         # 기본값이라고 알려준다
    out = capsys.readouterr().out
    assert "기본값" in out
    assert "환경변수" not in out


def test_main_은_수준을_한_번만_읽어_announce_level과_build_generate에_같이_넘긴다(
    monkeypatch,
):
    """리뷰 Minor 4 — (b)(main 이 수준을 한 번만 읽어 양쪽에 넘긴다) 자체를
    박제한 테스트가 없었다. 지금까지의 테스트는 `announce_level`/`build_generate`
    를 직접 불러 넘기므로 `main()` 의 배선은 아무도 보지 않는다.

    `load_levels` 호출 횟수를 세고, `announce_level`/`build_generate` 가 받은
    `Level` 객체가 **동일 객체**인지 본다. `main()` 이 소켓·콘솔까지 가면
    (표준입력이 없을 때 끝내지 않고 버티는 `run_console` 때문에) 테스트가
    멈추므로, `build_generate` 를 가짜로 바꿔 그 안에서 즉시 멈춘다 — 실제
    서버·콘솔은 아직 만들어지기 전이다.
    """
    # 이 테스트는 어느 수준이 골라지는지가 아니라 "몇 번 읽고 같은 값이 두
    # 곳에 가는지"만 본다 — 그래도 환경에 REACHY_AUDIENCE_LEVEL 이 이미
    # (오타로) 남아 있으면 `level_of_env` 가 `LevelError` 를 던져 아래
    # `pytest.raises(_멈춤)` 이 엉뚱한 예외로 실패한다. 깨끗한 상태를 보장한다.
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)

    calls = {"load_levels": 0}
    seen: dict[str, object] = {}

    import stage.levels as levels_mod

    원래_load_levels = levels_mod.load_levels

    def counting_load_levels(*a, **kw):
        calls["load_levels"] += 1
        return 원래_load_levels(*a, **kw)

    monkeypatch.setattr(levels_mod, "load_levels", counting_load_levels)

    def fake_announce(lv, explicit):
        seen["announce"] = lv

    class _멈춤(Exception):
        """`build_generate` 호출 직후 `main()` 을 여기서 멈춘다 — 서버·콘솔이
        뜨기 전이라 소켓도 안 열리고 표준입력 대기 루프도 안 돈다."""

    def fake_build_generate(level):
        seen["build"] = level
        raise _멈춤

    monkeypatch.setattr(stage_main, "announce_level", fake_announce)
    monkeypatch.setattr(stage_main, "build_generate", fake_build_generate)

    with pytest.raises(_멈춤):
        stage_main.main()

    assert calls["load_levels"] == 1, (
        f"load_levels 가 {calls['load_levels']} 번 불렸다 — 한 번이어야 한다"
    )
    assert "announce" in seen and "build" in seen
    assert seen["announce"] is seen["build"], (
        "announce_level 과 build_generate 가 서로 다른 Level 객체를 받았다 — "
        "main() 이 수준을 두 번 읽었을 가능성이 있다"
    )


def test_main_이_사전_생성_캐시와_수준_이름을_StageServer에_넘긴다(monkeypatch):
    """(A) 배선 확인 — 브리프에 없던 자리다. `Director.__init__` 가
    `mc_lines`/`level_name` 을 받게 됐어도, 그것을 만드는 `StageServer` 를
    만드는 `main()` 이 값을 채워 넘기지 않으면 두 인자는 늘 기본값(빈
    캐시·"일반")으로 굳는다 — 이 태스크 전체가 무효화된다.

    `level` 은 이미 `test_main_은_수준을_한_번만_읽어…` 가 "한 번만 읽는다"
    를 박제했으므로 여기서는 그 값(`level.name`)이 실제로 `StageServer` 까지
    닿는지, 그리고 `load_mc_lines()` 의 결과가 함께 닿는지만 본다.

    **기본값과 다른 수준을 세운다.** 예전에는 `REACHY_AUDIENCE_LEVEL` 을
    **지우고** `== "일반"` 을 단언했는데, "일반" 은 `stage/server.py` 와
    `stage/director.py` 의 `level_name` **기본값과 같은 값**이라 배선을 아무것도
    안 지켰다 — `stage/__main__.py` 의 `level_name=level.name` 을
    `level_name="일반"` 으로 바꿔도(= `REACHY_AUDIENCE_LEVEL` → `Director` 로
    가는 **유일한 통로**를 끊어도) 이 테스트를 포함해 전부 통과했다(전체 리뷰
    B1, 뮤테이션으로 실제로 뚫렸다). 기본값이 아닌 "초등" 으로 세워야 그 한 줄이
    지켜진다 — 이 저장소가 반복해 밟은 "기본값이 있는 인자를 기본값과 같은 값으로
    단언한다" 함정이다.
    """
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "초등")
    seen: dict[str, object] = {}

    class _멈춤(Exception):
        """`StageServer(...)` 호출 직후 여기서 멈춘다 — 소켓·콘솔은 아직 안 뜬다."""

    def fake_server(*a, **kw):
        seen["mc_lines"] = kw.get("mc_lines")
        seen["level_name"] = kw.get("level_name")
        raise _멈춤

    monkeypatch.setattr(stage_main, "StageServer", fake_server)
    monkeypatch.setattr(stage_main, "load_mc_lines", lambda: {"가짜": "캐시"})

    with pytest.raises(_멈춤):
        stage_main.main()

    assert seen["mc_lines"] == {"가짜": "캐시"}, (
        "main() 이 load_mc_lines() 의 결과를 StageServer 에 넘기지 않았다"
    )
    assert seen["level_name"] == "초등", (
        "main() 이 level.name 을 StageServer 에 넘기지 않았다 — 환경변수로 세운 "
        f"'초등' 이 아니라 {seen['level_name']!r} 이 닿았다"
    )


def test_기동_로그에_캐시_개수가_찍힌다(monkeypatch, capsys):
    """리뷰 Important 2 — "시연 전에 사람이 확인한다" 는 이 캐시의 존재
    이유가, 정작 기동 로그에 몇 개를 읽었는지 한 줄도 안 남으면 지켜지지
    않는다. 캐시를 통째로 못 읽어 왔거나 사전 생성을 깜빡한 채 기동해도
    그 사실이 콘솔에 안 남는다."""
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    monkeypatch.setattr(stage_main, "load_mc_lines", lambda: {"a": "1", "b": "2", "c": "3"})

    class _멈춤(Exception):
        pass

    def fake_server(*a, **kw):
        raise _멈춤

    monkeypatch.setattr(stage_main, "StageServer", fake_server)

    with pytest.raises(_멈춤):
        stage_main.main()

    assert "여는 대사 캐시 3개" in capsys.readouterr().out


def test_모듈_문서에_수준_환경변수가_적혀_있다():
    """`announce_level()` 이 실제로 쓰는 두 환경변수(REACHY_AUDIENCE_LEVEL/
    REACHY_LEVELS_PATH)가 기동 문서에서 빠지면, "주소는 전부 환경변수다" 규약대로
    이 파일 머리말만 보고 배포하는 사람이 그 존재를 알 길이 없다. `REACHY_MC_LINES_PATH`
    도 같은 이유로 형제 로더들과 나란히 적혀 있어야 한다(리뷰 Important 4)."""
    doc = stage_main.__doc__ or ""
    assert "REACHY_AUDIENCE_LEVEL" in doc
    assert "REACHY_LEVELS_PATH" in doc
    assert "REACHY_MC_LINES_PATH" in doc
