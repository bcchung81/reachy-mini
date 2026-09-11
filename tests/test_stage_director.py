"""무대감독 — machine·cues·LLM 을 묶는다.

전송을 모르므로 소켓 없이 종단 흐름을 전부 돌린다.
"""

import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet
from stage.director import CHARS_PER_SEC, TIMEOUT_MARGIN_S, Director, UnitMismatch
from stage.machine import State


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Harness:
    """감독 하나와 그가 내보낸 지시를 모으는 그릇."""

    def __init__(self, generate=None, expect_units=None):
        self.sent: list[tuple[str, str, dict]] = []
        self.warnings: list[str] = []
        self.clock = Clock()
        self.gen_calls: list[tuple[str, int]] = []
        sheet = CueSheet([
            Cue("c1", "첫째", "사회자 첫 대사", "첫 지시", "partner"),
            Cue("c2", "둘째", "사회자 둘째 대사", "둘째 지시", "audience"),
        ])

        def _gen(brief, history):
            self.gen_calls.append((brief, len(history)))
            if generate is not None:
                return generate(brief, history)
            return f"[{brief} 로 만든 대사]"

        self.d = Director(
            sheet,
            generate=_gen,
            send=lambda role, cmd: self.sent.append((role, cmd.type, cmd.fields)),
            now=self.clock,
            expect_units=expect_units,
            warn=self.warnings.append,
        )

    def types(self, role=None):
        return [(r, t) for r, t, _ in self.sent if role is None or r == role]

    def says(self):
        return [(r, f["text"]) for r, t, f in self.sent if t == "say"]

    def mics(self):
        return [(r, f["open"]) for r, t, f in self.sent if t == "mic"]

    def clear(self):
        self.sent.clear()


def test_시작하면_사회자가_첫_큐를_말한다():
    h = Harness()
    h.d.start()
    assert h.says() == [("mc", "사회자 첫 대사")]
    assert h.d.state is State.MC_SPEAKING


def test_시작할_때_양쪽_마이크를_닫는다():
    h = Harness()
    h.d.start()
    assert sorted(h.mics()) == [("docent", False), ("mc", False)]


def test_사회자가_말하는_동안_도슨트_대사를_미리_만든다():
    """지연 은닉 — 이게 하이브리드의 진짜 이득이다.

    생성은 별도 스레드에서 돈다. `start()` 직후에 `gen_calls` 를 보면
    스레드가 아직 안 돌아 **간헐적으로 실패한다** — 생성 쪽에서 신호를
    받아 결정적으로 기다린다.
    """
    import threading as _t

    started = _t.Event()
    seen: list[str] = []

    def gen(brief, history):
        seen.append(brief)
        started.set()
        return "미리 만든 대사"

    h = Harness(generate=gen)
    h.d.start()
    assert started.wait(2.0), "사회자 발화 시작 시점에 생성이 걸려 있지 않다"
    assert seen == ["첫 지시"]


def test_사회자_발화가_끝나면_도슨트가_바로_받는다():
    h = Harness()
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert h.says() == [("docent", "[첫 지시 로 만든 대사]")]
    assert h.d.state is State.DOCENT_SPEAKING


def test_사회자에서_도슨트로_넘어갈_때_마이크가_열리지_않는다():
    # coalesce 가 하는 일 — 깜빡 열린 사이로 들어온 소리가 유령 발화가 된다.
    h = Harness()
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert all(open_ is False for _, open_ in h.mics())


def test_도슨트_발화가_끝나면_사회자_마이크가_열린다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.clear()
    h.d.on_speaking_ended("docent", "c1:docent")  # 도슨트 몫에 붙는 구분 id
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]


def test_진행_신호를_들으면_다음_큐로_간다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1:docent")
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == [("mc", "사회자 둘째 대사")]


def test_질문을_들으면_도슨트가_답한다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1:docent")
    h.clear()
    h.d.on_heard("마르코니가 누구예요")
    answered = h.says()
    assert len(answered) == 1
    assert answered[0][0] == "docent"
    assert h.d.state is State.DOCENT_SPEAKING


def test_질문과_답이_대화_이력에_쌓인다():
    # 사회자와 도슨트가 하나의 이력을 본다 — 그래서 말이 이어진다.
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")
    roles = [m["role"] for m in h.d.history]
    assert roles[-2:] == ["user", "assistant"]


def test_발화_중에_들린_말은_버리고_경고한다():
    h = Harness()
    h.d.start()          # MC_SPEAKING
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == []
    assert any("발화 중" in w for w in h.warnings)


def test_마지막_큐에서_진행_신호를_받으면_끝내고_경고한다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1:docent")
    h.d.on_heard("다음")                      # c2 로
    h.d.on_speaking_ended("mc", "c2")
    h.d.on_speaking_ended("docent", "c2:docent")
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == []
    assert any("마지막" in w for w in h.warnings)


def test_발화_종료가_안_오면_타임아웃으로_복구하고_경고한다():
    h = Harness()
    h.d.start()
    h.clear()
    h.clock.t = len("사회자 첫 대사") / CHARS_PER_SEC + TIMEOUT_MARGIN_S + 0.1
    h.d.tick()
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]
    assert any("응답이 없다" in w for w in h.warnings)


def test_타임아웃_전에는_복구하지_않는다():
    h = Harness()
    h.d.start()
    h.clear()
    h.clock.t = 1.0
    h.d.tick()
    assert h.d.state is State.MC_SPEAKING
    assert h.sent == []


def test_LLM_이_실패하면_지시문을_읽고_경고한다():
    def boom(brief, history):
        raise RuntimeError("추론 서버가 죽었다")

    h = Harness(generate=boom)
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    said = h.says()
    assert len(said) == 1 and said[0][0] == "docent"
    assert said[0][1]                      # 빈 대사를 말하지 않는다
    assert any("LLM" in w for w in h.warnings)


def test_unit_id_가_다르면_기동에서_실패한다():
    # 사회자와 도슨트가 뒤바뀐 채 시연을 시작하는 것을 여기서 막는다.
    h = Harness(expect_units={"mc": "aaaa", "docent": "bbbb"})
    with pytest.raises(UnitMismatch, match="mc"):
        h.d.on_hello("mc", "bbbb", "1.9.0")


def test_unit_id_가_맞으면_통과한다():
    h = Harness(expect_units={"mc": "aaaa", "docent": "bbbb"})
    h.d.on_hello("mc", "aaaa", "1.9.0")
    assert h.warnings == []


def test_unit_id_가_없으면_경고하고_통과한다():
    # 시뮬(macOS)에서는 언제나 None 이다 — 여기서 막으면 개발이 멈춘다.
    h = Harness(expect_units={"mc": "aaaa", "docent": "bbbb"})
    h.d.on_hello("mc", None, "1.9.0")
    assert any("unit_id" in w for w in h.warnings)


def test_로봇이_보낸_오류는_경고로_남는다():
    h = Harness()
    h.d.on_error("docent", "tts", "합성 서버 연결 실패")
    assert any("docent" in w and "tts" in w for w in h.warnings)


def test_abort_는_양쪽을_멈춘다():
    h = Harness()
    h.d.start()
    h.clear()
    h.d.abort()
    assert sorted(h.types()) == [("docent", "abort"), ("mc", "abort")]
    assert h.d.state is State.IDLE


def test_늦게_끝난_생성_스레드는_다음_큐로_새지_않고_버려진다(monkeypatch):
    """review finding 1 — 생성이 유예시간을 넘겨 폴백으로 진행된 뒤, 스레드가
    뒤늦게 끝나면 이미 시작된 다음 큐로 새지 않고 버려져야 한다. 안 그러면
    엉뚱한 큐의 대사가 조용히(경고 없이) 나온다.

    `threading.Event` 로 정확히 통제한다 — sleep 경합이 아니다:
    c1 의 생성은 `release_c1` 이 풀릴 때까지 절대 끝나지 않으므로 유예시간
    안에 반드시 타임아웃하고, `release_c1.set()` 뒤에는 스레드 join 으로
    "결과가 나왔다"는 사실 자체를 결정적으로 기다린다.
    """
    import stage.director as director_mod

    monkeypatch.setattr(director_mod, "GENERATE_GRACE_S", 0.05)

    release_c1 = threading.Event()

    def gen(brief, history):
        if brief == "첫 지시":
            release_c1.wait(5.0)
            return "c1 늦은 대사"
        return f"[{brief} 로 만든 대사]"

    h = Harness(generate=gen)
    h.d.start()
    c1_thread = h.d._gen_thread  # c1 의 생성 스레드 — 곧 유예시간을 넘긴다

    h.d.on_speaking_ended("mc", "c1")  # 유예시간(0.05s) 안에 못 끝나 지시문 폴백
    assert h.says()[-1] == ("docent", "첫 지시")
    h.d.on_speaking_ended("docent", "c1:docent")
    h.d.on_heard("다음")  # c2 시작 — 새 생성 스레드가 돈다
    h.clear()
    h.warnings.clear()

    release_c1.set()  # 이제서야 c1 의 스레드가 풀려 결과를 내놓는다
    c1_thread.join(2.0)
    assert not c1_thread.is_alive()

    assert any("버려" in w for w in h.warnings)  # 폐기했다고 경고한다
    assert h.says() == []  # 아직 c2 도슨트 대사를 말하지 않았다

    h.d.on_speaking_ended("mc", "c2")
    assert h.says() == [("docent", "[둘째 지시 로 만든 대사]")]  # c1 의 늦은 대사가 아니다


def test_정상_생성은_폐기_로직을_넣어도_그대로_말해진다():
    """review finding 1 회귀 방지 — 세대 검사를 넣어도 정상 경로(스레드가
    늦지 않게 끝나는 경우)는 그대로 도슨트 대사를 말한다."""
    ready = threading.Event()

    def gen(brief, history):
        text = f"[{brief} 로 만든 대사]"
        ready.set()
        return text

    h = Harness(generate=gen)
    h.d.start()
    assert ready.wait(2.0)
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert h.says() == [("docent", "[첫 지시 로 만든 대사]")]


def test_도슨트_생성이_빈_문자열이면_경고하고_지시문으로_폴백한다():
    """review finding 2 — 빈 문자열도 벙어리가 되는 것과 같다."""
    h = Harness(generate=lambda brief, history: "")
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert h.says() == [("docent", "첫 지시")]
    assert any("빈" in w for w in h.warnings)


def test_질문_응답이_빈_문자열이면_경고하고_폴백한다():
    """review finding 2 — `_answer` 쪽 폴백도 같은 이유로 조용히 넘기지 않는다."""
    calls = {"n": 0}

    def gen(brief, history):
        calls["n"] += 1
        if calls["n"] == 1:
            return "[첫 지시 로 만든 대사]"  # 사전 생성(도슨트 첫 대사)은 정상
        return ""  # 질문 응답만 빈 문자열

    h = Harness(generate=gen)
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1:docent")
    h.clear()
    h.warnings.clear()
    h.d.on_heard("마르코니가 누구예요")
    said = h.says()
    assert len(said) == 1 and said[0][0] == "docent"
    assert said[0][1]  # 빈 대사가 아니다
    assert any("빈" in w for w in h.warnings)


def test_도슨트_타임아웃도_올바른_로봇을_지목한다():
    """사회자 타임아웃 테스트(`test_발화_종료가_안_오면_타임아웃으로_복구하고_경고한다`)의
    짝. 로직 경로는 같지만 로봇 이름이 하드코딩되지 않았음을 값으로 못박는다 —
    나중에 `role` 대신 실수로 고정 문자열을 넣는 회귀를 여기서 잡는다."""
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")  # 이제 도슨트가 말하는 중
    h.clear()
    h.warnings.clear()
    h.clock.t = len("[첫 지시 로 만든 대사]") / CHARS_PER_SEC + TIMEOUT_MARGIN_S + 0.1
    h.d.tick()
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]
    assert any("[docent]" in w and "응답이 없다" in w for w in h.warnings)


def test_타이머와_발화종료가_겹쳐도_불변식이_깨지지_않는다():
    """concurrency review finding — `tick()` 은 타이머 스레드에서, 나머지 공개
    메서드는 커넥션마다 다른 스레드에서 불린다(`stage/server.py`). 락이 없으면:
    tick() 이 옛 데드라인으로 "응답이 없다" 고 판정해 강제 복구를 준비하는
    바로 그 순간, 다른 스레드가 사회자→도슨트 핸드오프를 통째로 끝내
    상태를 옮길 수 있다. 그 뒤 tick() 이 이어서 `force_listening()` 을 부르면
    `TurnMachine._to_listening()` 은 현재 상태를 재확인하지 않는 무조건
    전이라 **도슨트가 말하는 도중** 사회자 마이크를 강제로 연다 — 불변식
    ① 위반이다. 그 강제 전이가 `speaking_role`/`cue_id` 도 리셋해 버려서,
    도슨트의 진짜 `speaking_ended` 가 뒤이어 와도 유령 메시지로 조용히
    버려진다 — 도슨트 발화가 타임아웃 보호를 통째로 잃는다.

    `warn` 콜러블을 후킹해 경합을 결정적으로 재현한다 — sleep 경합이
    아니다: tick() 이 "응답이 없다" 경고를 내보내는 바로 그 지점(`role`
    을 이미 읽은 뒤, `force_listening()` 을 부르기 전)에서 멈춰 세우고,
    그 사이 다른 스레드가 핸드오프를 시도하게 한다. 락이 있으면 그
    핸드오프는 tick() 이 끝날 때까지 통째로 막힌다 — `handoff_done` 을
    짧은 타임아웃으로만 기다리는 이유다(락이 없을 때는 핸드오프가 거의
    즉시 끝나고, 락이 있을 때는 tick() 이 풀어줄 때까지 절대 안 끝난다 —
    둘 다 결정적이라 타임아웃 값 자체는 결과를 좌우하지 않는다).
    """
    reached = threading.Event()
    release = threading.Event()
    warnings: list[str] = []
    sent: list[tuple[str, str, dict]] = []

    def warn(msg):
        warnings.append(msg)
        if "응답이 없다" in msg:  # tick() 이 강제 복구를 결정한 시점
            reached.set()
            release.wait(timeout=5.0)

    gen_started = threading.Event()
    gen_release = threading.Event()

    def gen(brief, history):
        gen_started.set()
        gen_release.wait(timeout=5.0)
        return "도슨트 대사"

    class SimpleClock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

    clock = SimpleClock()
    d = Director(
        CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner")]),
        generate=gen,
        send=lambda role, cmd: sent.append((role, cmd.type, cmd.fields)),
        now=clock,
        warn=warn,
    )

    d.start()  # 사회자 데드라인 설정
    assert gen_started.wait(2.0), "생성 스레드가 시작되지 않았다"
    gen_release.set()
    assert d._docent_ready.wait(2.0), "도슨트 대사 생성이 끝나지 않았다"

    clock.t = 10_000.0  # 사회자 데드라인을 확실히 지난 시각으로 만든다

    timer = threading.Thread(target=d.tick, daemon=True)
    timer.start()
    assert reached.wait(2.0), "tick() 이 강제 복구 판정에 도달하지 못했다"

    handoff_done = threading.Event()

    def do_handoff():
        d.on_speaking_ended("mc", "c1")
        handoff_done.set()

    handoff = threading.Thread(target=do_handoff, daemon=True)
    handoff.start()
    handoff_done.wait(timeout=0.3)  # 락이 없으면 여기서 이미 핸드오프가 끝나 있다
    release.set()  # tick() 을 마저 진행시킨다(강제 복구 실행)

    timer.join(timeout=2.0)
    handoff.join(timeout=2.0)
    assert not timer.is_alive() and not handoff.is_alive(), "스레드가 안 끝났다(교착 의심)"

    # 불변식 ① — 도슨트가 말하기 시작한 뒤에 사회자 마이크가 강제로 열리면 안 된다.
    docent_say_idx = next(
        (i for i, (r, t, _) in enumerate(sent) if r == "docent" and t == "say"), None
    )
    if docent_say_idx is not None:
        violating = [
            (r, t, f)
            for r, t, f in sent[docent_say_idx + 1 :]
            if r == "mc" and t == "mic" and f.get("open") is True
        ]
        assert not violating, (
            f"도슨트가 말하는 도중 사회자 마이크가 열렸다(불변식 ① 위반): {sent}"
        )

    # 강제 복구 경고는 실제로 데드라인이 걸렸던 로봇(mc)을 지목해야 한다.
    timeout_warnings = [w for w in warnings if "응답이 없다" in w]
    assert timeout_warnings, "타임아웃 경고가 없다"
    assert all("[mc]" in w for w in timeout_warnings), timeout_warnings

    # 강제 복구 이후 도슨트의 진짜 speaking_ended 가 뒤늦게 와도 시스템이
    # 죽거나 예외를 내지 않는다 — 유령으로 처리되든 정상 처리되든, 조용히
    # 삼켜서 다음 큐 진행이 막히지는 않았는지 상태로 확인한다.
    d.on_speaking_ended("docent", "c1")
    assert d.state in (State.LISTENING, State.DOCENT_SPEAKING)


def test_둘_다_붙어_있으면_1인_모드가_아니다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    assert h.d.solo_role is None


def test_도슨트가_끊기면_사회자가_양쪽을_읽는다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.start()
    h.d.on_disconnect("docent")
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    said = h.says()
    assert len(said) == 1
    assert said[0][0] == "mc"                      # 도슨트 대사를 사회자가 읽는다
    assert said[0][1] == "[첫 지시 로 만든 대사]"
    assert any("1인 모드" in w for w in h.warnings)


def test_사회자가_끊기면_도슨트가_양쪽을_읽는다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.on_disconnect("mc")
    h.clear()
    h.d.start()
    assert [r for r, _ in h.says()] == ["docent"]
    assert any("1인 모드" in w for w in h.warnings)


def test_다시_붙으면_2인_모드로_돌아온다():
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.on_disconnect("docent")
    assert h.d.solo_role == "mc"
    h.d.on_connect("docent")
    assert h.d.solo_role is None


def test_1인_모드에서도_불변식은_지켜진다():
    # 한 대가 연달아 두 대사를 읽으므로 발화 종료를 기다려야 한다.
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_disconnect("docent")
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("mc", "c1")
    assert h.d.state is State.MC_SPEAKING       # 두 번째 대사를 말하는 중
    assert all(open_ is False for _, open_ in h.mics())


def test_1인_모드에서_두_번째_발화_종료로_듣기_상태에_도달한다_사회자만_남았을_때():
    """review finding 1 — 도슨트 몫에 사회자 몫과 같은 맨 cue_id 를 쓰면, 1인
    모드에서는 같은 로봇의 speaking_ended 가 두 번 다 "사회자 몫이 끝났다"로
    오판된다. 두 번째 호출도 다시 도슨트 몫을 트리거해 같은 대사를 무한히
    반복하고, 마이크가 다시 열리지 않아 시연이 완전히 멈춘다."""
    h = Harness()
    h.d.on_connect("mc")
    h.d.on_disconnect("docent")
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")           # 사회자 몫 종료 → 도슨트 몫 시작
    h.clear()
    h.d.on_speaking_ended("mc", "c1:docent")    # 도슨트 몫 종료(로봇이 받은 cue_id 그대로 에코)
    assert h.d.state is State.LISTENING
    assert h.says() == []
    assert h.mics() == [("mc", True)]


def test_1인_모드에서_두_번째_발화_종료로_듣기_상태에_도달한다_도슨트만_남았을_때():
    """위 테스트의 반대 방향 — 아무 테스트도 덮지 않던 자리(사회자가 끊겨
    도슨트가 양쪽을 읽는 경우)라 finding 1 이 여기서 새어 나갔었다.

    마이크도 도슨트 것이 열려야 한다 — 사회자가 없으니 도슨트가 관람객
    창구를 겸한다(§ 리뷰 finding, 세 번째 라운드: `_to_listening` 이
    "사회자" 로 고정돼 있어 도슨트 1인 모드에서는 아무 마이크도 안 열렸었다).
    """
    h = Harness()
    h.d.on_connect("docent")
    h.d.on_disconnect("mc")
    h.d.start()                                  # 도슨트가 사회자 몫을 대신 읽는다
    h.d.on_speaking_ended("docent", "c1")         # 사회자 몫 종료 → 도슨트 몫 시작
    h.clear()
    h.d.on_speaking_ended("docent", "c1:docent")  # 도슨트 몫 종료
    assert h.d.state is State.LISTENING
    assert h.says() == []
    assert h.mics() == [("docent", True)]


# ── 타임아웃 기준점 (리뷰 I3) ────────────────────────────────────────

def test_발화_시작_보고가_데드라인을_다시_건다():
    """`say` 를 보낸 시점이 아니라 **로봇이 말을 시작한 시점**부터 센다.

    전송·수신 지연이 발화 예산을 깎아먹으면, 로봇이 말하기도 전에 데드라인이
    터져 `force_listening` 이 리스너 마이크를 연다 — 그 직후 로봇이 말을
    시작하면 사회자가 그것을 관람객 발화로 받아적는다(자기목소리 루프).
    """
    h = Harness()
    h.d.start()
    budget = h.d._deadline - h.clock.t

    h.clock.t += budget - 0.5          # 거의 다 썼다 (아직 말을 시작 못 했다)
    h.d.on_speaking_started("mc", "c1")
    assert h.d._deadline == pytest.approx(h.clock.t + budget)

    # 예전에는 여기서 이미 타임아웃이었다.
    h.clock.t += budget - 0.5
    h.clear()
    h.d.tick()
    assert h.mics() == []
    assert h.d.state is State.MC_SPEAKING


def test_유령_발화_시작_보고는_데드라인을_건드리지_않고_경고한다():
    h = Harness()
    h.d.start()
    before = h.d._deadline
    h.clock.t += 1.0
    h.d.on_speaking_started("docent", "없는-큐")
    assert h.d._deadline == before
    assert any("유령 speaking_started" in w for w in h.warnings)


def test_유령_발화_종료는_버리되_소리_내서_버린다():
    """조용히 버리면, 타임아웃이 먼저 터져 상태를 리셋한 뒤 도착한 **진짜**
    종료 보고도 흔적 없이 사라진다 — 그 로봇의 발화가 타임아웃 보호를
    통째로 잃었다는 사실을 아무도 모른다(리뷰 I3)."""
    h = Harness()
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("docent", "없는-큐")
    assert h.sent == []
    assert any("유령 speaking_ended" in w for w in h.warnings)
    assert h.d.state is State.MC_SPEAKING
