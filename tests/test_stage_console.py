"""비상 수동 오버라이드 콘솔.

**여기는 시연이 무너졌을 때 사람이 잡는 마지막 손잡이다.** 그런데 여기서
예외가 새면 `__main__.main()` 의 finally 가 서버를 내려 무대감독이 통째로
죽는다 — 되돌리려다 시연을 끝낸다. 그 경로를 테스트로 막는다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.console import run_console
from stage.cues import Cue, CueSheet
from stage.director import Director
from stage.machine import State, TurnError


class Harness:
    def __init__(self):
        self.sent: list[tuple[str, str, dict]] = []
        self.warnings: list[str] = []
        self.out: list[str] = []
        sheet = CueSheet([
            Cue("c1", "첫째", "사회자 첫 대사", "첫 지시", "partner"),
            Cue("c2", "둘째", "사회자 둘째 대사", "둘째 지시", "audience"),
        ])
        self.d = Director(
            sheet,
            generate=lambda brief, history: "도슨트 대사",
            send=lambda role, cmd: self.sent.append((role, cmd.type, cmd.fields)),
            warn=self.warnings.append,
        )

    def run(self, keys, block=lambda: None):
        """키를 순서대로 먹인다. 다 먹으면 EOFError — 실제 파이프 입력과 같다."""
        it = iter(keys)

        def read(_prompt):
            try:
                return next(it)
            except StopIteration:
                raise EOFError

        run_console(self.d, read=read, out=self.out.append, block=block)

    def says(self):
        return [(r, f["text"]) for r, t, f in self.sent if t == "say"]


def test_s_를_두_번_눌러도_콘솔이_살아_있다():
    """운영자가 가장 흔히 하는 행동이다 — "시작됐나? 한 번 더".

    두 번째 `start()` 는 발화 중이라 TurnError 를 던진다. 예전에는 그 예외가
    그대로 새서 무대감독 프로세스가 끝났다(리뷰 C3).
    """
    h = Harness()
    h.run(["s", "s", "q"])
    assert any("거절됨" in m for m in h.out)
    assert h.d.state is State.MC_SPEAKING  # 첫 발화는 살아 있다


def test_거절_사유를_사람이_읽을_수_있게_보여준다():
    h = Harness()
    h.run(["s", "s", "q"])
    거절 = [m for m in h.out if "거절됨" in m]
    assert 거절 and "말하는 중" in 거절[0]


def test_거절_뒤에도_다음_명령이_먹는다():
    """콘솔이 살아 있다는 말은 다음 키가 실제로 처리된다는 뜻이다."""
    h = Harness()
    h.run(["s", "s", "a", "q"])
    assert h.d.state is State.IDLE  # a 가 먹었다


def test_예상_못한_예외도_삼키지_않고_보여준다():
    """TurnError 만 잡으면 다음에 다른 예외가 나올 때 또 죽는다."""
    h = Harness()

    def 터진다():
        raise RuntimeError("감독이 터졌다")

    h.d.start = 터진다
    h.run(["s", "q"])
    assert any("감독이 터졌다" in m for m in h.out)


def test_q_는_돌아온다():
    h = Harness()
    h.run(["q"])
    assert h.d.state is State.IDLE


def test_모르는_키는_안내한다():
    h = Harness()
    h.run(["z", "q"])
    assert any("모르는 명령" in m for m in h.out)


def test_빈_줄은_아무_것도_하지_않는다():
    h = Harness()
    h.run(["", "q"])
    assert h.sent == []


def test_a_는_양쪽을_멈춘다():
    h = Harness()
    h.run(["s", "a", "q"])
    assert [(r, t) for r, t, _ in h.sent if t == "abort"] == [
        ("mc", "abort"), ("docent", "abort")
    ]


def test_r_는_현재_큐를_다시_말한다():
    h = Harness()
    h.run(["s", "r", "q"])
    assert h.says() == [("mc", "사회자 첫 대사"), ("mc", "사회자 첫 대사")]


def test_표준입력이_없으면_끝내지_않고_버틴다():
    """`nohup python -m stage &` 로 띄우면 첫 input() 이 EOFError 를 낸다.

    예전에는 그대로 돌아가 `main()` 의 finally 가 서버를 닫았다 —
    프로세스가 아무 말 없이 끝나고 로봇들은 영원히 재접속만 시도한다(리뷰 I5).
    """
    h = Harness()
    blocked = []
    h.run([], block=lambda: blocked.append(True))
    assert blocked == [True]
    assert any("표준입력이 없다" in m for m in h.out)


def test_Ctrl_C_는_조용히_돌아온다():
    h = Harness()

    def read(_p):
        raise KeyboardInterrupt

    run_console(h.d, read=read, out=h.out.append)
    assert not any("거절됨" in m for m in h.out)


def test_TurnError_가_여전히_불변식을_지킨다():
    """콘솔이 예외를 삼키는 것이지, 감독이 안 던지는 것이 아니다 —
    불변식 ②(동시 발화 금지)는 그대로여야 한다."""
    h = Harness()
    h.d.start()
    with pytest.raises(TurnError):
        h.d.start()


def _한_큐를_끝낸다(h, cue_id="c1"):
    """사회자 → 도슨트 → 듣기. `n` 은 LISTENING 에서만 먹는다."""
    h.d.on_speaking_ended("mc", cue_id)
    h.d.on_speaking_ended("docent", f"{cue_id}:docent")


def test_p_는_이전_큐로_되돌린다():
    """오인식으로 섹션이 넘어가 버렸을 때 되돌리는 유일한 길이다(설계 §7).
    앞으로만 갈 수 있으면 수동 오버라이드가 반쪽이다(리뷰 I4)."""
    h = Harness()
    h.d.start()
    _한_큐를_끝낸다(h, "c1")
    h.run(["n", "p", "q"])
    말한것 = [t for _, t in h.says()]
    assert 말한것[0] == "사회자 첫 대사"
    assert 말한것[-2:] == ["사회자 둘째 대사", "사회자 첫 대사"]


def test_첫_큐에서_p_는_경고만_남기고_되돌리지_않는다():
    h = Harness()
    h.run(["s", "p", "q"])
    assert any("더 되돌릴 곳이 없다" in m for m in h.warnings)
    assert [t for _, t in h.says()] == ["사회자 첫 대사"]


def test_도움말에_p_가_있다():
    """운영자가 존재를 모르는 손잡이는 없는 것과 같다."""
    h = Harness()
    h.run(["?", "q"])
    assert any("이전 큐로" in m for m in h.out)
