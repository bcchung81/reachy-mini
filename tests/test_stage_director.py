"""무대감독 — machine·cues·LLM 을 묶는다.

전송을 모르므로 소켓 없이 종단 흐름을 전부 돌린다.
"""

import pathlib
import sys

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
    h.d.on_speaking_ended("docent", "c1")
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]


def test_진행_신호를_들으면_다음_큐로_간다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1")
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == [("mc", "사회자 둘째 대사")]


def test_질문을_들으면_도슨트가_답한다():
    h = Harness()
    h.d.start()
    h.d.on_speaking_ended("mc", "c1")
    h.d.on_speaking_ended("docent", "c1")
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
    h.d.on_speaking_ended("docent", "c1")
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
    h.d.on_speaking_ended("docent", "c1")
    h.d.on_heard("다음")                      # c2 로
    h.d.on_speaking_ended("mc", "c2")
    h.d.on_speaking_ended("docent", "c2")
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
