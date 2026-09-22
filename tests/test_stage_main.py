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


class _기록LLM:
    """`build_generate` 가 LLM 에 실제로 무엇을 싣는지 기록한다."""
    본것: list[tuple[str, list[dict]]] = []
    답: list[str] = ["답"]

    def __init__(self, **kw):
        self.history: list[dict] = []

    def chat_stream(self, brief, image):
        type(self).본것.append((brief, list(self.history)))
        return iter(type(self).답)


@pytest.fixture
def 기록LLM(monkeypatch):
    _기록LLM.본것 = []
    _기록LLM.답 = ["답"]
    monkeypatch.setattr(stage_main, "LLMClient", _기록LLM)
    return _기록LLM


def test_이력은_생성하는_역할의_시점으로_바꿔_싣는다(기록LLM):
    """자기 말은 assistant(이름표 없이), 남의 말은 user(이름표 유지).

    예전에는 받은 이력을 그대로 실었고, 사회자·도슨트 줄이 **전부 assistant**
    였다 — 모델이 상대의 말을 자기 말로 보고 "이름표: 텍스트" 모양을 따라 해
    실기에서 "사회자:" 를 소리 내 읽었다(2026-09-21, mc:42). 이력 끝의 남의 말은
    이번 지시문 앞으로 옮긴다 — user 가 연달아 가지 않게.
    """
    generate = stage_main.build_generate(_레벨)
    이력 = [
        {"role": "assistant", "content": "사회자: 첫 질문"},
        {"role": "assistant", "content": "도슨트: 첫 해설"},
        {"role": "assistant", "content": "사회자: 다음 질문"},
    ]
    assert generate("docent", "지시", 이력) == "답"
    assert 기록LLM.본것 == [(
        "사회자: 다음 질문\n\n지시",
        [
            {"role": "user", "content": "사회자: 첫 질문"},
            {"role": "assistant", "content": "첫 해설"},
        ],
    )]


def test_같은_역할이_연달아_오면_한_메시지로_합친다(기록LLM):
    """역할 교대를 강제하는 채팅 템플릿이 있다 — 거절당하면 모든 생성이 폴백으로 떨어진다."""
    generate = stage_main.build_generate(_레벨)
    이력 = [
        {"role": "assistant", "content": "사회자: 여는 말"},
        {"role": "assistant", "content": "사회자: 덧붙임"},
        {"role": "user", "content": "관람객: 질문 하나"},
        {"role": "assistant", "content": "도슨트: 답"},
    ]
    generate("mc", "지시", 이력)
    assert 기록LLM.본것 == [(
        "관람객: 질문 하나\n도슨트: 답\n\n지시",
        [{"role": "assistant", "content": "여는 말\n덧붙임"}],
    )]


def test_생성문의_화자_이름표를_걷고_경고한다(기록LLM):
    기록LLM.답 = ["사회자: 사회자: ", "좋은 설명이네요."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("mc", "지시", []) == "좋은 설명이네요."
    assert any("이름표" in w for w in 경고), 경고


def test_warn_기본값은_print다(기록LLM, capsys):
    """전체 리뷰 I2 — `build_generate(level, warn=print)` 의 **기본값**이
    실제로 콘솔에 찍히는지 본다. 이 테스트가 없으면 기본값을 `lambda m: None`
    으로 바꿔도 690개가 전부 통과했다 — 실제 호출부 둘(`main()`,
    `scripts/pregen_mc_lines.py`)이 기본값에만 기대므로, 그러면 실기 경로의
    이름표·상한 경고가 전부 무방비가 된다(조용한 실패 금지 규약 위반).
    `warn` 을 일부러 넘기지 않는다.

    (갱신: 대시보드가 들어온 뒤 `main()` 은 tee `warn` 을 넘긴다 — 최종 리뷰 Y1,
    `test_감독_경고는_허브에_싣고…` 가 지킨다. 기본값에만 기대는 호출부는 이제
    `scripts/pregen_mc_lines.py` 하나지만, 그 하나 때문에 이 테스트는 여전히 필요하다.)
    """
    기록LLM.답 = ["사회자: 좋은 설명이네요."]
    generate = stage_main.build_generate(_레벨)
    assert generate("mc", "지시", []) == "좋은 설명이네요."
    assert "이름표" in capsys.readouterr().out


def test_이력_끝이_assistant면_지시문_앞으로_접지_않는다(기록LLM):
    """전체 리뷰 M1 — `if hist and hist[-1]["role"] == "user":` 를 `if hist:`
    로 완화해도(역할을 안 보고 무조건 접어도) 통과하던 자리다. 질문 재촉 뒤
    `director.py` 가 "사회자: …" 를 기록하면, 다음 사회자 생성은 자기 마지막
    말을 지시문 앞에 이름표 없는 user 로 받는 실제 경로가 있다 — 그 반대(이력
    끝이 assistant, 즉 방금 자기가 말한 차례)일 때는 접으면 안 된다.
    """
    generate = stage_main.build_generate(_레벨)
    이력 = [
        {"role": "assistant", "content": "도슨트: 해설"},
        {"role": "assistant", "content": "사회자: 질문 받습니다"},
    ]
    generate("mc", "지시", 이력)
    assert 기록LLM.본것 == [(
        "지시",
        [
            {"role": "user", "content": "도슨트: 해설"},
            {"role": "assistant", "content": "질문 받습니다"},
        ],
    )]


def test_상대_턴까지_이어_쓴_생성문은_그_앞에서_자른다(기록LLM):
    """실측 docent:106 — 도슨트 한 발화 안에 사회자 반응이 이어 붙었다."""
    기록LLM.답 = ["설명을 마칩니다.", "사회자: 반응입니다."]
    generate = stage_main.build_generate(_레벨, warn=lambda m: None)
    assert generate("docent", "지시", []) == "설명을 마칩니다."


def test_도슨트_생성문은_수준_상한_5문장에서_자르고_경고한다(기록LLM):
    """일반 수준은 4~5문장 / 180~280자(`data/levels.yaml`). 수는 리터럴로 박는다."""
    기록LLM.답 = ["하나.", "둘.", "셋.", "넷.", "다섯.", "여섯.", "일곱."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("docent", "지시", []) == "하나.둘.셋.넷.다섯."
    assert any("5문장/280자" in w for w in 경고), 경고


def test_사회자_생성문은_고정_상한_3문장에서_자른다(기록LLM):
    """사회자는 수준과 무관하게 1~3문장 / 40~120자(`stage/prompts.py`)."""
    기록LLM.답 = ["하나.", "둘.", "셋.", "넷.", "다섯."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("mc", "지시", []) == "하나.둘.셋."
    assert any("3문장/120자" in w for w in 경고), 경고


def test_깨끗하고_상한_안인_생성문은_그대로이고_경고하지_않는다(기록LLM):
    """위 두 경고 테스트의 짝 — 이것이 없으면 "늘 경고한다" 도 통과한다."""
    기록LLM.답 = ["전파는 파동입니다.", "눈에 보이지 않습니다."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("docent", "지시", []) == "전파는 파동입니다.눈에 보이지 않습니다."
    assert 경고 == []


def test_분량_상한_경고는_원래와_잘린_길이와_잘린_뒷부분을_보여_준다(기록LLM):
    """상한 뒤에는 감독의 분량 미달 경고(`Director._warn_if_short`)가 **상한 때문에**
    날 수 있다 — 모델은 450자를 썼는데 첫 문장만 남아 "너무 짧다(150자)" 가 찍힌다.
    상한 경고에 원래→잘린 길이와 잘린 뒷부분이 없으면 로그만 보고는 두 경고를
    잇지 못한다(Task 2 리뷰). 길이·뒷부분은 리터럴로 본다."""
    기록LLM.답 = ["하나.", "둘.", "셋.", "넷.", "다섯.", "여섯.", "일곱."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    generate("docent", "지시", [])
    assert any("18자→12자" in w and "여섯.일곱." in w for w in 경고), 경고


def test_분량_상한_경고는_잘린_뒷부분의_끝까지_보여_준다(기록LLM):
    """사회자의 질문은 대개 **마지막 문장**이다. 상한은 앞에서부터 남기므로 그
    질문이 잘리고, 감독의 질문 유도 가드가 고정 문장을 붙이며 "질문 유도가 없다"
    고 경고한다 — 원인은 모델이 아니라 상한이다. 잘린 뒷부분을 **앞에서만** 줄여
    보여 주면 정작 그 질문이 로그에서 빠진다(리뷰가 든 예 그대로: 313자 → 100자)."""
    기록LLM.답 = ["나" * 99 + ".", "나" * 99 + ".", "나" * 99 + ".", "오늘은 질문 있으신가요?"]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("mc", "지시", []) == "나" * 99 + "."
    assert any("313자→100자" in w and "질문 있으신가요?" in w for w in 경고), 경고


def test_이름표_경고는_걷어낸_상대_턴을_보여_준다(기록LLM):
    """실측 docent:106 모양 — 도슨트 해설 뒤에 사회자 반응이 이어 붙었다. 예전
    경고는 `raw[:60]`(원문 **앞**)을 찍어, 새어 든 부분이 60자 뒤에 있으면 로그에
    안 보였다(Task 2 리뷰 #5). 걷어낸 부분을 보여야 한다."""
    설명 = ("전파는 눈에 보이지 않지만 휴대전화와 방송과 와이파이처럼 우리 생활 "
            "곳곳에서 하루 종일 쉬지 않고 쓰이고 있는 것입니다.")
    # 전제: 해설이 60자를 넘어야 "원문 앞 60자" 로는 새어 든 부분이 안 보인다 —
    # 이 리터럴을 줄이면 옛 경고로도 통과하는 공허한 테스트가 된다.
    assert len(설명) > 60
    기록LLM.답 = [설명, "사회자: 사회자: 반응입니다."]
    경고: list[str] = []
    generate = stage_main.build_generate(_레벨, warn=경고.append)
    assert generate("docent", "지시", []) == 설명
    assert any("반응입니다" in w for w in 경고), 경고


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

    # 진짜 `build_generate(level, warn=print)` 와 인자 모양을 맞춘다 — `main()` 은
    # 이제 tee `warn` 을 넘긴다(최종 리뷰 Y1).
    def fake_build_generate(level, warn=print):
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


def test_main이_수준의_분량_하한을_StageServer에_넘긴다(monkeypatch):
    """전체 리뷰 I1 — 분량 미달 경고만 수준이 닿지 않던 자리의 배선이다.

    `Director` 의 `docent_min_chars` 기본값은 `MIN_CHARS`(40)이고, `main()` 이
    `level.min_chars` 를 채워 넘기지 않으면 일반(180)·전문가(260)에서 50자짜리
    해설이 나와도 경고가 없다 — 설계 §5·§10 이 요구한 경고가 절반만 도는 상태로
    조용히 굳는다.

    **기본값(40)이 아닌 값으로 확인한다**: 초등의 `min_chars` 는 70이다. 40으로
    보면 배선이 끊겨도 통과한다(이 저장소가 반복해 밟은 함정 3).
    """
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "초등")
    seen: dict[str, object] = {}

    class _멈춤(Exception):
        pass

    def fake_server(*a, **kw):
        seen["docent_min_chars"] = kw.get("docent_min_chars")
        raise _멈춤

    monkeypatch.setattr(stage_main, "StageServer", fake_server)
    monkeypatch.setattr(stage_main, "load_mc_lines", lambda: {})

    with pytest.raises(_멈춤):
        stage_main.main()

    from stage.levels import load_levels

    초등_하한 = load_levels()["초등"].min_chars
    assert 초등_하한 == 70, "data/levels.yaml 의 초등 min_chars 가 바뀌었다 — 이 테스트를 갱신한다"
    assert seen["docent_min_chars"] == 초등_하한, (
        f"main() 이 level.min_chars 를 StageServer 에 넘기지 않았다 — {seen['docent_min_chars']!r} 이 닿았다"
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


def test_main_은_허브를_서버에_넘기고_환경변수_주소로_대시보드를_띄운다(monkeypatch):
    """REACHY_DASHBOARD_HOST/PORT 가 그대로 닿는지 — 기본값(127.0.0.1:8778)이
    아닌 값으로 본다(함정 3)."""
    monkeypatch.setenv("REACHY_DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setenv("REACHY_DASHBOARD_PORT", "9911")
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    seen = {}

    class 멈춤(Exception):
        pass

    class 가짜서버:
        def __init__(self, *a, **kw):
            seen["hub"] = kw.get("hub")
            self.director = object()
            # 진짜 `StageServer.__init__` 은 항상 `CameraRelay` 를 만들어 `.camera` 에
            # 둔다(Task 6) — `main()` 이 그 값을 `start_dashboard(..., camera=...)` 에
            # 그대로 넘기므로, 흉내에도 속성이 있어야 AttributeError 없이 그 자리에 닿는다.
            self.camera = object()

        def serve(self, host, port):
            class S:
                def serve_forever(self): pass
                def shutdown(self): pass
            return S()

        def tick_forever(self, *a): pass

    def 가짜대시보드(hub, director, host, port, camera=None, warn=print):
        seen.update(dash_hub=hub, host=host, port=port)
        raise 멈춤()

    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
    monkeypatch.setattr(stage_main, "StageServer", 가짜서버)
    monkeypatch.setattr(stage_main, "start_dashboard", 가짜대시보드)
    with pytest.raises(멈춤):
        stage_main.main()
    assert seen["hub"] is not None and seen["dash_hub"] is seen["hub"]
    assert (seen["host"], seen["port"]) == ("0.0.0.0", 9911)


def test_main은_dashboard에_server_camera를_넘긴다(monkeypatch):
    """Task 8 — `StageServer.__init__` 이 스스로 만드는 `server.camera`(Task 6, 항상
    실제 `CameraRelay` — `None` 이 아니다)가 `main()` 을 거쳐 `start_dashboard` 에
    그대로 닿는지. 위 `test_main_은_허브를_서버에_넘기고_환경변수_주소로_대시보드를_띄운다`
    의 셋업을 그대로 쓰고 camera 단언만 더한다."""
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    seen = {}

    class 멈춤(Exception):
        pass

    카메라_표식 = object()

    class 가짜서버:
        def __init__(self, *a, **kw):
            self.director = object()
            self.camera = 카메라_표식

        def serve(self, host, port):
            class S:
                def serve_forever(self): pass
                def shutdown(self): pass
            return S()

        def tick_forever(self, *a): pass

    def 가짜대시보드(hub, director, host, port, camera=None, warn=print):
        seen["camera"] = camera
        raise 멈춤()

    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
    monkeypatch.setattr(stage_main, "StageServer", 가짜서버)
    monkeypatch.setattr(stage_main, "start_dashboard", 가짜대시보드)
    with pytest.raises(멈춤):
        stage_main.main()

    assert seen["camera"] is not None
    assert seen["camera"] is 카메라_표식


class _가짜서버:
    """`StageServer` 대역 — 받은 `warn`·`hub` 를 적고 소켓은 열지 않는다.

    `warn` 이 안 넘어오면 **진짜의 기본값(`print`)** 을 쥔다. 배선이 빠졌을 때 표식이
    터미널로만 가 허브 단언이 **단언으로** 떨어지게 한다 — `None` 을 쥐면 부르다가
    TypeError 로 엉뚱하게 죽어, 무엇이 끊겼는지 테스트가 말해 주지 않는다.
    """

    def __init__(self, seen, *a, **kw):
        seen["server_warn"] = kw.get("warn", print)
        seen["hub"] = kw["hub"]
        self.director = object()
        # 진짜 `StageServer` 는 항상 `.camera` 에 `CameraRelay` 를 둔다(Task 6) — `main()` 이
        # `start_dashboard`/`run_console` 양쪽에 `server.camera` 를 그대로 넘기므로(Task 8),
        # 이 흉내도 속성이 있어야 그 두 호출부까지 닿는 테스트가 AttributeError 없이 돈다.
        self.camera = object()
        self._seen = seen

    def serve(self, host, port):
        seen = self._seen

        class S:
            def serve_forever(self):
                pass

            def shutdown(self):
                seen["shutdown"] = seen.get("shutdown", 0) + 1

        return S()

    def tick_forever(self, *a):
        pass


def _허브_경고(hub) -> list[str]:
    return [e["text"] for e in hub.history() if e["kind"] == "warn"]


def test_감독_경고는_허브에_싣고_대시보드_자신의_경고는_터미널로만_보낸다(monkeypatch, capsys):
    """경고 배선(최종 리뷰 Y1·Y2) — `StageServer` 와 `build_generate` 가 받은 `warn` 은
    터미널+허브(tee), `start_dashboard` 가 받은 `warn` 은 터미널로만.

    - 생성기 경고(화자 이름표를 걷었다·분량 상한에서 잘랐다)는 `main()` 이
      `build_generate(level)` 로 불러 기본값 `print` 로 갔다 — 터미널에만 남고 운영자가
      보는 대시보드 이력에는 없었다(Y1). 스펙은 경고 전부를 tee 로 보낸다.
    - 대시보드 자신의 경고(송신 실패·소켓 거절·큐 넘침)를 허브에 실으면, 넘침 경고가
      허브 → 넘친 그 구독 큐로 다시 들어가 또 버려지는 자기 고리가 된다(스펙 "오류 처리").

    셋에 **서로 다른 표식**을 넣어 부르고 **같은 허브**(StageServer 가 받은 것)의 이력을
    본다. 대시보드 표식이 "없다" 는 단언만 두면 대시보드 warn 이 아무 데도 안 가도
    통과하므로(함정 ④) 셋 다 터미널에 찍히는지와 짝으로 본다.
    """
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    monkeypatch.delenv("REACHY_DASHBOARD_HOST", raising=False)
    monkeypatch.delenv("REACHY_DASHBOARD_PORT", raising=False)
    seen: dict = {}

    class 멈춤(Exception):
        pass

    def 가짜생성기(level, warn=print):   # 진짜와 같은 기본값 — 위 `_가짜서버` 주석과 같은 이유
        seen["gen_warn"] = warn
        return lambda r, b, h: "x"

    def 가짜대시보드(hub, director, host, port, camera=None, warn=print):
        seen["dash_warn"] = warn
        raise 멈춤()

    monkeypatch.setattr(stage_main, "build_generate", 가짜생성기)
    monkeypatch.setattr(stage_main, "StageServer", lambda *a, **kw: _가짜서버(seen, *a, **kw))
    monkeypatch.setattr(stage_main, "start_dashboard", 가짜대시보드)
    with pytest.raises(멈춤):
        stage_main.main()

    seen["server_warn"]("표식-서버")
    seen["gen_warn"]("표식-생성기")
    seen["dash_warn"]("표식-대시보드")

    허브 = _허브_경고(seen["hub"])
    assert "표식-서버" in 허브, 허브
    assert "표식-생성기" in 허브, 허브
    assert "표식-대시보드" not in 허브, 허브
    터미널 = capsys.readouterr().out.splitlines()
    assert {"표식-서버", "표식-생성기", "표식-대시보드"} <= set(터미널), 터미널


def test_역할_검증을_건너뛴다는_기동_경고가_대시보드_이력에도_남는다(monkeypatch, capsys):
    """최종 리뷰 Y3 — 이 경고는 허브를 만들기 **전에** `print` 로 나가 대시보드 이력에
    없었다. 지난 실기 리허설의 역할 뒤바뀜(사회자·도슨트 로봇이 서로 바뀐 채 시작)을
    막는 검증이 꺼져 있다는 경고라, 운영자가 보는 화면에 있어야 한다. 터미널에도
    그대로 남는지 함께 본다(tee 의 한쪽만 살아도 통과하지 않게)."""
    monkeypatch.delenv("REACHY_MC_UNIT", raising=False)
    monkeypatch.delenv("REACHY_DOCENT_UNIT", raising=False)
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    seen: dict = {}

    class 멈춤(Exception):
        pass

    def 가짜서버(*a, **kw):
        seen["hub"] = kw["hub"]
        raise 멈춤()

    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
    monkeypatch.setattr(stage_main, "StageServer", 가짜서버)
    monkeypatch.setattr(stage_main, "load_mc_lines", lambda: {})
    with pytest.raises(멈춤):
        stage_main.main()

    경고문 = "⚠ REACHY_MC_UNIT / REACHY_DOCENT_UNIT 이 없다 — 역할 검증을 건너뛴다"
    assert 경고문 in _허브_경고(seen["hub"]), _허브_경고(seen["hub"])
    assert 경고문 in capsys.readouterr().out.splitlines()


def test_대시보드_포트가_숫자가_아니면_경고하고_대시보드만_빼고_감독과_콘솔은_돈다(monkeypatch, capsys):
    """최종 리뷰 Y4 — `int(REACHY_DASHBOARD_PORT)` 의 ValueError 가 기동을 통째로 죽였다.
    대시보드는 곁다리다: 값이 틀렸으면 **그 값을 보여 주고** 대시보드만 빼고 감독·콘솔은
    돈다. 기본 포트로 몰래 바꾸지 않는다 — 주소는 환경변수가 권위다(운영자는 적은 포트로
    열려 하는데 다른 포트에 떠 있으면 "대시보드가 안 뜬다" 로만 보인다).

    "대시보드를 안 불렀다" 는 부정 단언은 "콘솔까지 갔다"·"끝에 서버를 내렸다" 와 짝이다
    — 기동이 그 전에 죽어도 대시보드는 안 불리기 때문이다(함정 ④)."""
    monkeypatch.setenv("REACHY_DASHBOARD_PORT", "88x8")
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    seen: dict = {"dash": []}
    서버들: list = []

    class 멈춤(Exception):
        pass

    def 가짜서버(*a, **kw):
        서버들.append(_가짜서버(seen, *a, **kw))
        return 서버들[-1]

    def 가짜콘솔(director, camera=None):
        seen["console"] = director
        # 리뷰(Important 1) — `start_dashboard` 쪽 camera 배선은 새 테스트가 정체성까지
        # 확인하는데 `run_console` 쪽은 시그니처만 맞추고 값을 한 번도 안 봤다. 여기서
        # 받은 camera 를 적어 아래에서 `서버들[0].camera` 와 정체성으로 비교한다.
        seen["console_camera"] = camera
        raise 멈춤()

    import stage.console

    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
    monkeypatch.setattr(stage_main, "StageServer", 가짜서버)
    monkeypatch.setattr(stage_main, "start_dashboard", lambda *a, **kw: seen["dash"].append(a))
    monkeypatch.setattr(stage.console, "run_console", 가짜콘솔)
    with pytest.raises(멈춤):
        stage_main.main()

    assert "⚠ REACHY_DASHBOARD_PORT 가 포트 번호가 아니다('88x8')" in capsys.readouterr().out
    assert seen["console"] is 서버들[0].director
    # `director` 와 같은 방식(같은 서버 인스턴스의 속성과 정체성 비교)으로 camera 도 본다 —
    # `run_console(server.director, camera=server.camera)` 배선이 실제로 그 객체를 옮기는지,
    # 시그니처만 맞고 값은 안 보는 반쪽짜리 확인에 머무르지 않게 한다.
    assert seen["console_camera"] is 서버들[0].camera
    assert seen["shutdown"] == 1
    assert seen["dash"] == []


# ── 관람객 수준 실시간 전환: 수준별 생성기 전환기(`LevelSwitch`)와 그 배선 ──────────


def _가짜_생성기_공장(만든것: list, 받은_warn: list | None = None):
    """`build_generate(level, warn)` 대역. 만든 수준을 순서대로 적고, 생성 결과에
    수준 이름을 박아 **어느 수준의 생성기가 돌았는지** 문자열로 가른다."""
    def build(level, warn=print):
        만든것.append(level.name)
        if 받은_warn is not None:
            받은_warn.append(warn)
        return lambda role, brief, history: f"{level.name}:{role}:{brief}"
    return build


def test_수준_전환기는_처음_수준만_바로_만들고_나머지는_처음_쓸_때_한_번씩_만든다():
    """고르기(`select`)는 감독이 락을 쥔 채 부르는 훅이다 — 거기서 생성기를 만들면
    (페르소나 파일 읽기) 락 안에서 파일 I/O 를 한다. 만드는 일은 첫 생성 때 생성
    스레드에서, 수준마다 한 번만. 처음 수준은 기동에서 바로 만든다 — 페르소나가
    깨져 있으면 시연 전에 죽는 편이 낫다(지금까지의 기동과 같다)."""
    levels = load_levels()
    만든것: list[str] = []
    받은: list = []

    def 경고(m):
        pass

    sw = stage_main.LevelSwitch(levels, levels["중고등"], _가짜_생성기_공장(만든것, 받은), warn=경고)
    assert 만든것 == ["중고등"]
    assert sw("docent", "지시", []) == "중고등:docent:지시"
    sw.select("전문가")
    assert 만든것 == ["중고등"]
    assert sw("mc", "받아치기", []) == "전문가:mc:받아치기"
    assert sw("docent", "해설", []) == "전문가:docent:해설"
    sw.select("중고등")
    assert sw("docent", "다시", []) == "중고등:docent:다시"
    assert 만든것 == ["중고등", "전문가"]
    # 나중에 만든 생성기도 같은 경고 출구(tee)를 받는다 — 기본값 print 로 새면 이름표·
    # 분량 상한 경고가 수준을 바꾼 뒤에만 대시보드에서 빠진다(최종 리뷰 Y1 과 같은 자리).
    assert 받은 == [경고, 경고]


def test_수준_전환기는_수준이_달라도_LLM_호출을_하나씩만_보낸다():
    """`build_generate` 의 직렬화 락은 생성기마다 하나다. 수준별로 생성기를 따로 두면
    앞 큐(옛 수준)의 늦은 생성과 새 큐(새 수준)의 도슨트 해설이 **동시에** LLM 에
    간다 — 새 큐의 임계경로가 버려질 생성과 추론 서버를 나눠 쓴다. 전환기가 호출
    전체를 한 락으로 묶는다(`test_LLM_호출이_직렬화된다` 와 같은 불변식)."""
    levels = load_levels()
    순서: list[str] = []
    앞이_도는_중 = threading.Event()
    놓아라 = threading.Event()
    새것_시작 = threading.Event()

    def build(level, warn=print):
        def gen(role, brief, history):
            순서.append(f"{level.name} 시작")
            if level.name == "중고등":
                앞이_도는_중.set()
                놓아라.wait(3)
            else:
                새것_시작.set()
            순서.append(f"{level.name} 끝")
            return "x"
        return gen

    sw = stage_main.LevelSwitch(levels, levels["중고등"], build, warn=print)
    앞 = threading.Thread(target=sw, args=("docent", "앞 큐", []))
    앞.start()
    assert 앞이_도는_중.wait(3)
    sw.select("전문가")
    새 = threading.Thread(target=sw, args=("docent", "새 큐", []))
    새.start()
    새것_시작.wait(0.3)      # 직렬화가 깨졌으면 새 생성이 여기서 앞 생성 도중에 시작한다
    놓아라.set()
    앞.join(3)
    새.join(3)
    assert 순서 == ["중고등 시작", "중고등 끝", "전문가 시작", "전문가 끝"]


def test_select는_진행_중인_LLM_호출_뒤에서_기다리지_않는다():
    """수준 리뷰 Minor 1 — `LevelSwitch.select` 는 **대입 하나**여야 한다(docstring).
    `Director._begin_cue` 가 `Director._lock` 을 쥔 채 이 훅을 부르므로, `select`
    안에 `self._lock` 을 넣어(`__call__` 이 생성 내내 쥐고 있는 락) 생성과 얽히면
    진행 중인 LLM 호출이 끝날 때까지 감독 락이 통째로 묶인다 — 콘솔 `a`(즉시 중단)·
    tick·대시보드 스냅샷이 그동안 전부 멈춘다. 감독 락을 직접 흉내 낼 필요는 없다 —
    `select` 가 `LevelSwitch` 자신의 락 뒤에서 기다리는지만 보면 같은 불변식을 지킨다
    (감독 락이든 이 락이든, "대입 하나" 가 깨지면 여기서 걸린다).

    생성기 하나를 `release` 가 풀릴 때까지 멈춰 두고, 그 생성이 `__call__` 의 락을
    쥔 채로 도는 동안 다른 스레드에서 `select` 를 부른다 — 대입 하나면 즉시
    돌아오고, 락을 잡으면 `release.set()` 전까지 못 돌아온다.
    """
    levels = load_levels()
    inside, release = threading.Event(), threading.Event()

    def build(level, warn=print):
        def gen(role, brief, history):
            inside.set()
            release.wait(3)
            return "x"
        return gen

    sw = stage_main.LevelSwitch(levels, levels["중고등"], build, warn=print)
    t = threading.Thread(target=sw, args=("docent", "앞 큐", []))
    t.start()
    try:
        assert inside.wait(3), "생성기가 시작되지 않았다"
        done = threading.Event()
        threading.Thread(target=lambda: (sw.select("전문가"), done.set())).start()
        assert done.wait(0.5), (
            "select 가 진행 중인 생성 뒤에서 블로킹했다 — "
            "감독 락과 얽힐 수 있는 자리다(Director._begin_cue 가 그 락을 쥔 채 부른다)"
        )
    finally:
        release.set()
        t.join(3)


def test_main_은_수준별_하한과_전환_훅과_전환기를_StageServer에_넘긴다(monkeypatch):
    """배선 하나라도 빠지면 `l` 이 반쯤만 돈다: 하한 목록이 빠지면 네 수준 중 지금
    것만 알아 나머지는 "모르는 수준", 훅이 빠지면 감독이 기동에서 막고(ValueError),
    전환기 대신 한 수준 생성기를 넘기면 페르소나가 처음 수준에 굳는다.
    처음 수준은 기본값("일반")이 아닌 "초등"(함정 ③)."""
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "초등")
    만든것: list[str] = []
    monkeypatch.setattr(stage_main, "build_generate", _가짜_생성기_공장(만든것))
    monkeypatch.setattr(stage_main, "load_mc_lines", lambda: {})
    seen: dict = {}

    class _멈춤(Exception):
        pass

    def fake_server(sheet, generate, **kw):
        seen.update(kw, generate=generate)
        raise _멈춤

    monkeypatch.setattr(stage_main, "StageServer", fake_server)
    with pytest.raises(_멈춤):
        stage_main.main()

    assert list(seen["level_min_chars"].items()) == [
        ("초등", 70), ("중고등", 120), ("일반", 180), ("전문가", 260),
    ]
    assert seen["generate"]("docent", "지시", []) == "초등:docent:지시"
    seen["on_level_change"]("전문가")
    assert seen["generate"]("docent", "지시", []) == "전문가:docent:지시"
    assert 만든것 == ["초등", "전문가"]


_수준_큐시트 = """\
- id: c1
  title: 첫째
  mc: 원문 c1
  docent_brief: 옛 지시
  gaze: partner
  briefs:
    초등: {mc_brief: 초등 진행, docent_brief: 초등 해설}
    중고등: {mc_brief: 중고등 진행, docent_brief: 중고등 해설}
    일반: {mc_brief: 일반 진행, docent_brief: 일반 해설}
    전문가: {mc_brief: 전문가 진행, docent_brief: 전문가 해설}
"""


def test_main_에서_감독까지_수준_전환이_끝까지_이어진다(monkeypatch, tmp_path):
    """대장 「`Director` 생성자 인자를 늘려도 배선 두 단계를 같이 안 고치면 늘 기본값으로
    죽는다」 — `main()` → **진짜** `StageServer` → **진짜** `Director` 를 한 줄로 잇는다.
    두 단계 중 어디서 `level_min_chars`/`on_level_change` 를 빠뜨려도 여기서 깨진다
    (목록이 빠지면 "전문가" 가 모르는 수준, 훅이 빠지면 감독 생성에서 ValueError).
    소켓·콘솔은 안 띄운다 — 진짜 서버를 만든 직후 멈춘다."""
    cues = tmp_path / "cues.yaml"
    cues.write_text(_수준_큐시트, encoding="utf-8")
    monkeypatch.setenv("REACHY_CUES_PATH", str(cues))
    monkeypatch.setenv("REACHY_AUDIENCE_LEVEL", "초등")
    monkeypatch.setattr(stage_main, "load_mc_lines", lambda: {})
    만든것: list[str] = []
    불린것: list[tuple[str, str, str]] = []
    해설_받음 = threading.Event()

    def build(level, warn=print):
        만든것.append(level.name)

        def gen(role, brief, history):
            불린것.append((level.name, role, brief))
            해설_받음.set()
            return "해설"
        return gen

    monkeypatch.setattr(stage_main, "build_generate", build)
    진짜 = stage_main.StageServer
    seen: dict = {}

    class _멈춤(Exception):
        pass

    def 붙잡기(*a, **kw):
        seen["server"] = 진짜(*a, **kw)
        raise _멈춤

    monkeypatch.setattr(stage_main, "StageServer", 붙잡기)
    with pytest.raises(_멈춤):
        stage_main.main()

    d = seen["server"].director
    assert d.level_names() == ["초등", "중고등", "일반", "전문가"]
    d.set_level("전문가")
    d.start()            # 로봇이 없어 say 는 "아직 붙지 않았다" 로 버려진다 — 생성만 본다
    assert 해설_받음.wait(2.0), 불린것
    assert 불린것 == [("전문가", "docent", "전문가 해설")]
    assert 만든것 == ["초등", "전문가"]
    assert d.snapshot()["level"] == "전문가"


@pytest.mark.parametrize("빈값", ["", "   "])
def test_대시보드_주소가_비어_있으면_모든_망이_아니라_노트북에서만_열고_경고한다(monkeypatch, capsys, 빈값):
    """`REACHY_DASHBOARD_HOST=` (빈 값) 은 `os.environ.get(…, 기본값)` 을 지나 빈 문자열로
    `serve("", …)` 에 닿고, 빈 호스트는 **모든 인터페이스**에 바인드된다 — 인증 없이
    시연을 멈추는 화면이 빈 값 하나로 망에 열린다(최종 수정 웨이브 뒤 관찰). 위험한 쪽을
    기본으로 두지 않는다는 결정 1에 따라 빈 값은 루프백으로 두고, 소리 내서 알린다."""
    monkeypatch.setenv("REACHY_DASHBOARD_HOST", 빈값)
    monkeypatch.setenv("REACHY_DASHBOARD_PORT", "9911")
    monkeypatch.delenv("REACHY_AUDIENCE_LEVEL", raising=False)
    seen: dict = {}

    class 멈춤(Exception):
        pass

    def 가짜대시보드(hub, director, host, port, camera=None, warn=print):
        seen["host"] = host
        raise 멈춤()

    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
    monkeypatch.setattr(stage_main, "StageServer", lambda *a, **kw: _가짜서버(seen, *a, **kw))
    monkeypatch.setattr(stage_main, "start_dashboard", 가짜대시보드)
    with pytest.raises(멈춤):
        stage_main.main()

    assert seen["host"] == "127.0.0.1"
    assert "⚠ REACHY_DASHBOARD_HOST 가 비어 있다" in capsys.readouterr().out
