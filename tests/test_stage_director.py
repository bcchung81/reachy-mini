"""무대감독 — machine·cues·LLM 을 묶는다.

전송을 모르므로 소켓 없이 종단 흐름을 전부 돌린다.
"""

import pathlib
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet
from stage.director import CHARS_PER_SEC, TIMEOUT_MARGIN_S, Director, UnitMismatch
from stage.machine import State
from stage.mc_cache import cache_key


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Harness:
    """감독 하나와 그가 내보낸 지시를 모으는 그릇."""

    def __init__(
        self, generate=None, expect_units=None, after=("", ""),
        sheet=None, level_name="일반", mc_lines=None,
    ):
        self.sent: list[tuple[str, str, dict]] = []
        # `clear()` 뒤에도 남는 누적 목록 — 발화 seq 를 되찾는 데 쓴다
        self.all_sent: list[tuple[str, str, dict]] = []
        self.warnings: list[str] = []
        self.clock = Clock()
        self.gen_calls: list[tuple[str, int]] = []
        # 생성 콜백이 실제로 받은 role 을 호출 순서대로 남긴다(리뷰 Important 1).
        # `_spawn_generate`/`_generate_pending` 은 slot 과 role 을 **둘 다** 받는데,
        # `Director._begin_cue`/`_answer` 의 실제 호출은 늘 slot == role == "docent"
        # 라 `self._generate(role, …)` 를 실수로 `self._generate(slot, …)` 로
        # 바꿔도 그 두 호출부만으로는 절대 드러나지 않는다 — slot 과 role 을
        # 일부러 다르게 주는 테스트(`test_생성_콜백은_슬롯이_아니라_role_을_받는다`)
        # 가 이 목록을 본다.
        self.gen_roles: list[str] = []
        # `sheet` 를 넘기지 않으면 지금까지 쓰던 2큐짜리 기본 시트를 그대로
        # 쓴다(기본값은 지금 동작 유지) — 수준별 브리프를 손으로 채운
        # `Cue` 가 필요한 테스트만 자기 시트를 넘긴다.
        if sheet is None:
            sheet = CueSheet([
                Cue("c1", "첫째", "사회자 첫 대사", "첫 지시", "partner", mc_after=after[0]),
                Cue("c2", "둘째", "사회자 둘째 대사", "둘째 지시", "audience", mc_after=after[1]),
            ])

        # `Director` 가 부르는 `generate` 는 이제 `(role, brief, history)` 다 —
        # 역할별로 다른 프롬프트를 조립해 쓰기 때문이다(`stage/prompts.py`).
        # `gen_calls` 모양은 그대로 `(brief, len(history))` 로 둔다 — 이걸 보는
        # 유일한 단언(`len(h.gen_calls) == 1`)이 개수만 보므로 굳이 넓힐 이유가
        # 없고, 넓히면 이 파일의 커스텀 `generate=` 콜백을 쓰는 테스트들이 전부
        # role 인자까지 신경 써야 해서 변경 범위만 늘어난다. role 은 별도
        # 목록(`gen_roles`)에 쌓는다.
        def _gen(role, brief, history):
            self.gen_calls.append((brief, len(history)))
            self.gen_roles.append(role)
            if generate is not None:
                return generate(role, brief, history)
            return f"[{brief} 로 만든 대사]"

        self.d = Director(
            sheet,
            generate=_gen,
            send=lambda role, cmd: (
                self.sent.append((role, cmd.type, cmd.fields)),
                self.all_sent.append((role, cmd.type, cmd.fields)),
            ),
            now=self.clock,
            expect_units=expect_units,
            warn=self.warnings.append,
            mc_lines=mc_lines,
            level_name=level_name,
        )

    def types(self, role=None):
        return [(r, t) for r, t, _ in self.sent if role is None or r == role]

    def says(self):
        return [(r, f["text"]) for r, t, f in self.sent if t == "say"]

    def mics(self):
        return [(r, f["open"]) for r, t, f in self.sent if t == "mic"]

    def clear(self):
        self.sent.clear()

    def seq_of(self, cue_id):
        """마지막으로 보낸 그 큐의 say 가 받은 seq — 로봇이 되돌려 줄 값."""
        return [f["seq"] for _, t, f in self.all_sent if t == "say" and f["cue_id"] == cue_id][-1]

    def ended(self, role, cue_id):
        self.d.on_speaking_ended(role, cue_id, self.seq_of(cue_id))

    def started(self, role, cue_id):
        self.d.on_speaking_started(role, cue_id, self.seq_of(cue_id))


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

    def gen(role, brief, history):
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
    h.ended("mc", "c1")
    assert h.says() == [("docent", "[첫 지시 로 만든 대사]")]
    assert h.d.state is State.DOCENT_SPEAKING


def test_사회자에서_도슨트로_넘어갈_때_마이크가_열리지_않는다():
    # coalesce 가 하는 일 — 깜빡 열린 사이로 들어온 소리가 유령 발화가 된다.
    h = Harness()
    h.d.start()
    h.clear()
    h.ended("mc", "c1")
    assert all(open_ is False for _, open_ in h.mics())


def test_도슨트_발화가_끝나면_사회자_마이크가_열린다():
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")  # 도슨트 몫에 붙는 구분 id
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]


def test_진행_신호를_들으면_다음_큐로_간다():
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.clear()
    h.d.on_heard("다음")
    assert h.says() == [("mc", "사회자 둘째 대사")]


def test_질문을_들으면_사회자가_먼저_받고_도슨트가_답한다():
    """B3 — 질문 뒤 LLM 이 도는 동안 정적이 흐르지 않는다. 큐 전환과 같은 수법이다:
    사회자 고정 멘트가 흐르는 동안 생성한다. 그래서 `on_heard` 는 LLM 을 기다리지 않는다."""
    from stage.cues import QA_ACK_LINES
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.clear()
    h.d.on_heard("마르코니가 누구예요")
    assert len(h.says()) == 1 and h.says()[0][0] == "mc"
    assert h.says()[0][1] in QA_ACK_LINES
    assert h.d.state is State.MC_SPEAKING
    h.clear()
    h.ended("mc", "c1:ack")
    answered = h.says()
    assert len(answered) == 1 and answered[0][0] == "docent"
    assert "마르코니가 누구예요" in answered[0][1]
    assert h.d.state is State.DOCENT_SPEAKING


def test_질문_응답_생성은_on_heard_를_막지_않는다():
    """`_answer` 가 락을 쥔 채 LLM 을 기다리면 콘솔 `a` 가 그동안 먹지 않는다(리뷰 C1)."""
    import time
    gate = threading.Event()
    seen = threading.Event()

    def slow(role, brief, history):
        if brief.startswith("관람객이"):
            seen.set()
            gate.wait(5)
        return "답"

    h = Harness(generate=slow)
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    t0 = time.monotonic()
    h.d.on_heard("질문")
    assert time.monotonic() - t0 < 1.0, "on_heard 가 LLM 을 기다렸다"
    assert seen.wait(2.0), "생성 스레드가 돌지 않았다"
    h.d.abort()                      # 락이 자유로워야 즉시 돌아온다
    assert time.monotonic() - t0 < 1.0
    gate.set()


def _wait_state(h, state, timeout=2.0):
    """감독이 그 상태에 닿을 때까지 기다린다 — 다른 스레드가 대기 구간에 들어갔는지 보는 눈.

    `Director.state` 는 진입 락을 잡지 않고 읽으므로, 그 락을 쥔 스레드가 있어도
    관찰된다. 그래서 고침 전후 양쪽에서 같은 지점을 잡을 수 있다.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if h.d.state is state:
            return True
        time.sleep(0.01)
    return False


def test_도슨트_생성_대기가_abort_를_막지_않는다():
    """사회자 발화가 끝나고 도슨트 대사를 기다리는 구간에서도 콘솔 `a` 는 즉시 먹어야
    한다. 예전에는 그 대기(`GENERATE_GRACE_S`, 최대 8초)가 **진입 락을 쥔 채**
    일어나 비상정지가 그만큼 먹통이었다. 대장의 "락을 쥔 채 네트워크를 기다리지
    않는다" 가 LLM *요청* 쪽(`_answer`)에만 적용돼 있던 나머지 구멍이다 —
    큐 19개마다, 그리고 관람객 질문마다 한 번씩 더 돌아온다.
    """
    gate = threading.Event()

    def slow(role, brief, history):
        gate.wait(3.0)
        return "도슨트 대사"

    h = Harness(generate=slow)
    h.d.start()
    handoff = threading.Thread(target=h.ended, args=("mc", "c1"), daemon=True)
    handoff.start()
    assert _wait_state(h, State.LISTENING), "핸드오프가 대기 구간에 들어가지 않았다"

    t0 = time.monotonic()
    h.d.abort()
    elapsed = time.monotonic() - t0

    gate.set()
    handoff.join(timeout=5.0)
    assert not handoff.is_alive(), "핸드오프 스레드가 안 끝났다(교착 의심)"
    assert elapsed < 1.0, f"abort 가 도슨트 생성 대기에 묶였다({elapsed:.1f}초)"


def test_대기_중_abort_가_나면_도슨트가_뒤늦게_말하지_않는다():
    """비상정지가 빨라진 대신 **늦게 끝난 생성이 그 뒤에 말을 얹으면** 더 나쁘다 —
    운영자는 멈췄다고 믿는데 도슨트가 입을 연다. 락을 놓고 기다리는 구조가 새로
    들일 수 있는 경합이라 값으로 못박는다: 대기에서 깨어나면 상태를 다시 보고
    물러난다.
    """
    gate = threading.Event()

    def slow(role, brief, history):
        gate.wait(3.0)
        return "도슨트 대사"

    h = Harness(generate=slow)
    h.d.start()
    handoff = threading.Thread(target=h.ended, args=("mc", "c1"), daemon=True)
    handoff.start()
    assert _wait_state(h, State.LISTENING), "핸드오프가 대기 구간에 들어가지 않았다"

    h.clear()
    h.d.abort()
    gate.set()                       # 늦게 끝난 생성이 돌아온다
    handoff.join(timeout=5.0)
    assert not handoff.is_alive(), "핸드오프 스레드가 안 끝났다(교착 의심)"
    assert h.says() == [], f"비상정지 뒤에 대사가 나갔다: {h.says()}"
    assert h.d.state is State.IDLE


def test_대기_중_다음_큐가_돌아_LISTENING_이_돼도_옛_대사는_안_나간다():
    """상태만 보는 판정으로는 못 잡는 틈. 대기 중 `n` 으로 다음 큐가 시작되고 그
    사회자 발화까지 끝나면 상태가 **다시 LISTENING** 이 된다 — 그때 깨어난 옛
    대기가 상태만 보면 "아직 내 차례" 로 오해해 **이전 섹션 해설**을 읽고, 뒤이어
    새 큐의 핸드오프가 `TurnError` 를 맞는다. 슬롯의 세대 토큰(`_slots[…]["token"]`)
    이 이것을 가른다 — `_generate_pending` 이 늦게 끝난 생성을 버릴 때 쓰는 것과 같은 장치다.
    """
    gates = {"첫 지시": threading.Event(), "둘째 지시": threading.Event()}

    def slow(role, brief, history):
        gates[brief].wait(3.0)
        return f"[{brief} 해설]"

    h = Harness(generate=slow)
    errors: list[Exception] = []

    def ended_in_thread(role, cue_id):
        try:
            h.ended(role, cue_id)
        except Exception as exc:  # noqa: BLE001 — 스레드 밖으로 못 나가는 예외를 걷는다
            errors.append(exc)

    h.d.start()                                   # c1 사회자 발화 + 생성 ①
    first = threading.Thread(target=ended_in_thread, args=("mc", "c1"), daemon=True)
    first.start()
    assert _wait_state(h, State.LISTENING), "첫 핸드오프가 대기에 들어가지 않았다"

    h.d.next()                                    # c2 로 넘어간다 — 생성 ②, 세대가 오른다
    assert h.d.state is State.MC_SPEAKING
    second = threading.Thread(target=ended_in_thread, args=("mc", "c2"), daemon=True)
    second.start()
    assert _wait_state(h, State.LISTENING), "둘째 핸드오프가 대기에 들어가지 않았다"

    gates["첫 지시"].set()                         # 옛 생성만 풀어 준다
    first.join(timeout=5.0)
    assert not first.is_alive(), "옛 핸드오프가 안 끝났다"

    stale = [f for _, t, f in h.all_sent if t == "say" and f["cue_id"] == "c1:docent"]
    assert not stale, f"이전 섹션 해설이 나갔다: {stale}"

    gates["둘째 지시"].set()
    second.join(timeout=5.0)
    assert not errors, f"핸드오프에서 예외가 났다: {errors}"


def test_대기_중_도슨트가_끊기면_남은_사회자가_그_대사를_읽는다():
    """대기에서 깨어난 뒤 **역할을 다시 계산한다.** 1구간의 판단을 들고 가면 이미
    끊긴 도슨트에게 대사를 보내고, 전송 계층은 "아직 붙지 않았다" 경고만 남기고
    버린다 — 상태기계는 도슨트가 말하는 중이라 믿으므로 `speaking_ended` 가 영영
    오지 않고 tick 타임아웃까지 정적이 된다. 남은 한 대가 양쪽을 읽어야 한다
    (설계 §7 1인 모드).
    """
    gate = threading.Event()

    def slow(role, brief, history):
        gate.wait(3.0)
        return "도슨트 대사"

    h = Harness(generate=slow)
    h.d.on_connect("mc")
    h.d.on_connect("docent")
    h.d.start()
    handoff = threading.Thread(target=h.ended, args=("mc", "c1"), daemon=True)
    handoff.start()
    assert _wait_state(h, State.LISTENING), "핸드오프가 대기 구간에 들어가지 않았다"

    h.d.on_disconnect("docent")       # 대기 중에 도슨트가 사라진다
    assert h.d.solo_role == "mc"
    gate.set()
    handoff.join(timeout=5.0)
    assert not handoff.is_alive(), "핸드오프 스레드가 안 끝났다(교착 의심)"

    said = [(r, f["cue_id"]) for r, t, f in h.all_sent if t == "say"]
    assert ("mc", "c1:docent") in said, f"남은 사회자가 도슨트 몫을 읽지 않았다: {said}"


def test_확인_멘트는_돌아가며_쓴다():
    from stage.cues import QA_ACK_LINES
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    seen = []
    for _ in range(len(QA_ACK_LINES)):
        h.clear()
        h.d.on_heard("질문")
        seen.append(h.says()[0][1])
        h.ended("mc", "c1:ack")
        h.ended("docent", "c1:qa")
        h.ended("mc", "c1:reask")   # 답 뒤에 사회자가 다시 묻는다 — 그것까지 끝나야 LISTENING
    assert len(set(seen)) == len(QA_ACK_LINES)


def test_질문과_답이_대화_이력에_쌓인다():
    # 사회자와 도슨트가 하나의 이력을 본다 — 그래서 말이 이어진다.
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    # 관람객 → 사회자 확인 멘트 → 도슨트 답, 셋 다 하나의 이력에 남는다
    tail = [m["content"].split(":")[0] for m in h.d.history[-3:]]
    assert tail == ["관람객", "사회자", "도슨트"]
    roles = [m["role"] for m in h.d.history]
    assert roles[-3:] == ["user", "assistant", "assistant"]


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
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.d.on_heard("다음")                      # c2 로
    h.ended("mc", "c2")
    h.ended("docent", "c2:docent")
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
    def boom(role, brief, history):
        raise RuntimeError("추론 서버가 죽었다")

    h = Harness(generate=boom)
    h.d.start()
    h.clear()
    h.ended("mc", "c1")
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
    c1_entered = threading.Event()
    c1_box: dict[str, threading.Thread] = {}

    def gen(role, brief, history):
        if brief == "첫 지시":
            # **생성 스레드 자신을 여기서 집는다.** 예전에는 `h.d._gen_thread` 를
            # 봤는데, 슬롯이 이름별로 갈리면서 "마지막에 띄운 스레드" 하나를
            # 들고 있는 그 필드가 없어졌다(슬롯이 둘이면 뒤에 띄운 것이 앞의
            # 핸들을 덮어써 엉뚱한 스레드를 join 하게 된다). 콜백 안에서 부르는
            # `current_thread()` 가 곧 그 생성 스레드라 감독 내부를 안 들춰도 된다.
            c1_box["t"] = threading.current_thread()
            c1_entered.set()
            release_c1.wait(5.0)
            return "c1 늦은 대사"
        return f"[{brief} 로 만든 대사]"

    h = Harness(generate=gen)
    h.d.start()
    assert c1_entered.wait(2.0), "c1 생성 스레드가 시작되지 않았다"
    c1_thread = c1_box["t"]  # c1 의 생성 스레드 — 곧 유예시간을 넘긴다

    h.ended("mc", "c1")  # 유예시간(0.05s) 안에 못 끝나 지시문 폴백
    assert h.says()[-1] == ("docent", "첫 지시")
    h.ended("docent", "c1:docent")
    h.d.on_heard("다음")  # c2 시작 — 새 생성 스레드가 돈다
    h.clear()
    h.warnings.clear()

    release_c1.set()  # 이제서야 c1 의 스레드가 풀려 결과를 내놓는다
    c1_thread.join(2.0)
    assert not c1_thread.is_alive()

    assert any("버려" in w for w in h.warnings)  # 폐기했다고 경고한다
    assert h.says() == []  # 아직 c2 도슨트 대사를 말하지 않았다

    h.ended("mc", "c2")
    assert h.says() == [("docent", "[둘째 지시 로 만든 대사]")]  # c1 의 늦은 대사가 아니다


def test_정상_생성은_폐기_로직을_넣어도_그대로_말해진다():
    """review finding 1 회귀 방지 — 세대 검사를 넣어도 정상 경로(스레드가
    늦지 않게 끝나는 경우)는 그대로 도슨트 대사를 말한다."""
    ready = threading.Event()

    def gen(role, brief, history):
        text = f"[{brief} 로 만든 대사]"
        ready.set()
        return text

    h = Harness(generate=gen)
    h.d.start()
    assert ready.wait(2.0)
    h.clear()
    h.ended("mc", "c1")
    assert h.says() == [("docent", "[첫 지시 로 만든 대사]")]


def test_도슨트_생성이_빈_문자열이면_경고하고_지시문으로_폴백한다():
    """review finding 2 — 빈 문자열도 벙어리가 되는 것과 같다."""
    h = Harness(generate=lambda role, brief, history: "")
    h.d.start()
    h.clear()
    h.ended("mc", "c1")
    assert h.says() == [("docent", "첫 지시")]
    assert any("빈" in w for w in h.warnings)


def test_질문_응답이_빈_문자열이면_경고하고_폴백한다():
    """review finding 2 — `_answer` 쪽 폴백도 같은 이유로 조용히 넘기지 않는다."""
    calls = {"n": 0}

    def gen(role, brief, history):
        calls["n"] += 1
        if calls["n"] == 1:
            return "[첫 지시 로 만든 대사]"  # 사전 생성(도슨트 첫 대사)은 정상
        return ""  # 질문 응답만 빈 문자열

    h = Harness(generate=gen)
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.clear()
    h.warnings.clear()
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    said = [x for x in h.says() if x[0] == "docent"]
    assert len(said) == 1
    assert said[0][1]  # 빈 대사가 아니다
    assert any("빈" in w for w in h.warnings)


def test_도슨트_타임아웃도_올바른_로봇을_지목한다():
    """사회자 타임아웃 테스트(`test_발화_종료가_안_오면_타임아웃으로_복구하고_경고한다`)의
    짝. 로직 경로는 같지만 로봇 이름이 하드코딩되지 않았음을 값으로 못박는다 —
    나중에 `role` 대신 실수로 고정 문자열을 넣는 회귀를 여기서 잡는다."""
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")  # 이제 도슨트가 말하는 중
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

    def gen(role, brief, history):
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
    assert d._snapshot_slot("docent")[0].wait(2.0), "도슨트 대사 생성이 끝나지 않았다"

    clock.t = 10_000.0  # 사회자 데드라인을 확실히 지난 시각으로 만든다

    timer = threading.Thread(target=d.tick, daemon=True)
    timer.start()
    assert reached.wait(2.0), "tick() 이 강제 복구 판정에 도달하지 못했다"

    handoff_done = threading.Event()

    def do_handoff():
        d.on_speaking_ended("mc", "c1", d._machine.seq)
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
    d.on_speaking_ended("docent", "c1", d._machine.seq)
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
    h.ended("mc", "c1")
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
    h.ended("mc", "c1")
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
    h.ended("mc", "c1")           # 사회자 몫 종료 → 도슨트 몫 시작
    h.clear()
    h.ended("mc", "c1:docent")    # 도슨트 몫 종료(로봇이 받은 cue_id 그대로 에코)
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
    h.ended("docent", "c1")         # 사회자 몫 종료 → 도슨트 몫 시작
    h.clear()
    h.ended("docent", "c1:docent")  # 도슨트 몫 종료
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
    h.started("mc", "c1")
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
    h.d.on_speaking_started("docent", "없는-큐", 999)
    assert h.d._deadline == before
    assert any("유령 speaking_started" in w for w in h.warnings)


def test_유령_발화_종료는_버리되_소리_내서_버린다():
    """조용히 버리면, 타임아웃이 먼저 터져 상태를 리셋한 뒤 도착한 **진짜**
    종료 보고도 흔적 없이 사라진다 — 그 로봇의 발화가 타임아웃 보호를
    통째로 잃었다는 사실을 아무도 모른다(리뷰 I3)."""
    h = Harness()
    h.d.start()
    h.clear()
    h.d.on_speaking_ended("docent", "없는-큐", 999)
    assert h.sent == []
    assert any("유령 speaking_ended" in w for w in h.warnings)
    assert h.d.state is State.MC_SPEAKING


# ── 공유 이력 (리뷰 I6 / 상한) ───────────────────────────────────────

def test_사회자_대사도_하나의_이력에_쌓인다():
    """설계 §5.2 — 이력은 하나이고 `사회자:`/`도슨트:`/`관람객:` 로 가른다.

    사회자 몫이 빠지면 도슨트의 LLM 은 방금 뭐라고 넘겨받았는지 못 본다.
    "도슨트, 맥스웰부터 부탁해요" 를 못 보고 해설을 시작하니 말이 안 이어진다.
    """
    h = Harness()
    h.d.start()
    assert h.d.history[0]["content"] == "사회자: 사회자 첫 대사"


def test_사회자_대사가_도슨트_생성에_실제로_넘어간다():
    """순서가 중요하다 — 생성 스레드는 `list(self.history)` 를 찍어간다.
    스레드를 띄운 **뒤에** 넣으면 이번 큐에는 안 들어간다."""
    본것: list[list[dict]] = []

    def gen(role, brief, history):
        본것.append(list(history))
        return "도슨트 대사"

    h = Harness(generate=gen)
    h.d.start()
    assert h.d._snapshot_slot("docent")[0].wait(2.0)
    assert 본것 and 본것[0][-1]["content"] == "사회자: 사회자 첫 대사"


def test_이력이_무한히_자라지_않는다():
    """19섹션 + Q&A 를 다 쌓으면 컨텍스트 창이 **말없이** 앞을 자른다 —
    자르는 쪽을 우리가 정해야 무엇이 남는지 알 수 있다."""
    from stage.director import HISTORY_MAX

    h = Harness()
    for i in range(HISTORY_MAX * 2):
        h.d._remember(f"도슨트: 줄 {i}")
    assert len(h.d.history) == HISTORY_MAX
    assert h.d.history[-1]["content"] == f"도슨트: 줄 {HISTORY_MAX * 2 - 1}"
    # 최근 것이 남는다 — 오래된 것부터 나간다
    assert h.d.history[0]["content"] == f"도슨트: 줄 {HISTORY_MAX}"


def test_관람객_줄만_user_로_들어간다():
    h = Harness()
    h.d._remember("관람객: 마르코니가 누구예요")
    h.d._remember("도슨트: 무선 전신을 실용화한 사람입니다")
    h.d._remember("사회자: 다음으로 가 볼까요")
    assert [m["role"] for m in h.d.history] == ["user", "assistant", "assistant"]


# ── 타임아웃 여유분 (리뷰 I3 판정) ───────────────────────────────────

# Qwen3-TTS 첫 합성의 Metal 커널 JIT (`scripts/warmup.py` 실측).
COLD_SYNTH_S = 8.5

# **실측** 발화 속도(2026-09-11, 57자 → 10.64초). `CHARS_PER_SEC` 는 이보다
# 보수적으로(4.0) 잡은 **예산용** 값이다 — 둘을 섞어 쓰면 안 된다:
# 예산은 4.0 으로, 실제로 걸리는 시간은 5.4 로 계산해야 비교가 성립한다.
MEASURED_CHARS_PER_SEC = 5.4


@pytest.mark.parametrize(
    "글자수",
    [
        12,   # 짧은 전환 — 예전 값 5.0 에서 터졌다 (예산 8.0 < 필요 10.7)
        34,   # 사회자 대사 — 예전 값 5.0 에서 터졌다 (예산 13.5 < 필요 14.8)
        57,   # 긴 해설 — 예전 값에서도 아슬아슬하게 통과했다 (19.2 > 19.1)
    ],
)
def test_예열을_빠뜨려도_첫_큐가_헛타임아웃되지_않는다(글자수):
    """**여유분은 합성 지연을 덮는 몫이다.**

    감독은 로봇이 언제 실제로 소리를 내기 시작했는지 모른다 — 로봇은
    `speaker.speak()` 가 큐에 넣고 돌아온 직후 `speaking_started` 를 보내고
    합성은 그 뒤에 일어난다. 예열을 건너뛰면 첫 합성에 8.5초가 더 붙는데,
    예전 여유분 5.0 초로는 짧은·중간 길이가 **거의 확실히** 헛타임아웃됐다.
    그러면 리스너 마이크가 열리고 직후 로봇이 말을 시작해 사회자가 그것을
    관람객 발화로 받아적는다 — 자기목소리 루프다.

    실제로 걸리는 시간 = 차가운 합성 + 재생 길이.
    """
    필요 = COLD_SYNTH_S + 글자수 / MEASURED_CHARS_PER_SEC
    예산 = 글자수 / CHARS_PER_SEC + TIMEOUT_MARGIN_S
    assert 예산 > 필요, (
        f"{글자수}자: 예산 {예산:.1f}초 < 필요 {필요:.1f}초 — "
        "예열을 빠뜨린 첫 큐가 헛타임아웃된다"
    )


def test_여유분이_차가운_합성을_덮는다():
    """상수 하나로 요약 — 여유분은 합성 JIT 보다 커야 한다."""
    assert TIMEOUT_MARGIN_S > COLD_SYNTH_S, (
        f"여유분 {TIMEOUT_MARGIN_S} 초가 차가운 합성 {COLD_SYNTH_S} 초를 못 덮는다"
    )


def test_늘어난_여유분이_타임아웃_자체를_없애지는_않는다():
    """느슨하게 잡았다고 감시가 꺼지면 안 된다 — 멈춘 로봇은 여전히 잡힌다."""
    h = Harness()
    h.d.start()
    h.clear()
    h.clock.t = len("사회자 첫 대사") / CHARS_PER_SEC + TIMEOUT_MARGIN_S + 0.1
    h.d.tick()
    assert h.d.state is State.LISTENING
    assert any("응답이 없다" in w for w in h.warnings)


# ── 거절은 부작용 전에 (리뷰 A7a) / next (리뷰 A7b) ──────────────────


def test_발화_중에_start_를_다시_불러도_이력과_생성이_오염되지_않는다():
    """운영자의 `s` 두 번. 거절은 하되 **부작용이 없어야** 한다(리뷰 A7a)."""
    from stage.machine import TurnError
    h = Harness()
    h.d.start()
    with pytest.raises(TurnError):
        h.d.start()
    assert [l["content"] for l in h.d.history] == ["사회자: 사회자 첫 대사"]
    assert len(h.gen_calls) == 1
    assert not any("버려졌다" in w for w in h.warnings)


def test_next_는_IDLE_에서도_다음_큐로_간다():
    h = Harness()
    h.d.start()
    h.d.abort()
    h.clear()
    h.d.next()
    assert h.says() == [("mc", "사회자 둘째 대사")]


def test_next_는_발화_중이면_거절한다():
    from stage.machine import TurnError
    h = Harness()
    h.d.start()
    with pytest.raises(TurnError):
        h.d.next()


# ── 거부 목록·재접속 재동기화 (리뷰 A4·A5a) ─────────────────────────


def test_거부된_역할이_있으면_start_가_거절한다():
    from stage.machine import TurnError
    h = Harness(expect_units={"mc": "AAA"})
    with pytest.raises(UnitMismatch):
        h.d.on_hello("mc", "BBB", "1.9.0")
    h.d.reject("mc", "뒤바뀜")
    assert "mc" in h.d.rejected
    with pytest.raises(TurnError, match="mc"):
        h.d.start()
    h.d.on_hello("mc", "AAA", "1.9.0")   # 맞는 로봇이 붙으면 풀린다
    h.d.start()
    assert h.says() == [("mc", "사회자 첫 대사")]


def test_듣는_중에_다시_붙은_리스너에게_마이크를_다시_연다():
    """리뷰 A5a — 앱 재기동/WiFi 순단 뒤 mic_open 이 비어 있는 채로 남아 청취가 죽었다."""
    h = Harness()
    h.d.on_connect("mc"); h.d.on_connect("docent")
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    assert h.d.state is State.LISTENING
    h.d.on_disconnect("mc")
    h.clear()
    h.d.on_connect("mc")
    assert h.mics() == [("mc", True)]


def test_말하는_중에_다시_붙은_로봇에게는_마이크를_닫는다():
    h = Harness()
    h.d.on_connect("mc"); h.d.on_connect("docent")
    h.d.start()
    h.clear()
    h.d.on_disconnect("docent"); h.d.on_connect("docent")
    assert ("docent", False) in h.mics()
    assert ("docent", True) not in h.mics()


def test_듣는_중에_리스너가_끊기면_남은_로봇의_마이크를_연다():
    h = Harness()
    h.d.on_connect("mc"); h.d.on_connect("docent")
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    h.clear()
    h.d.on_disconnect("mc")
    assert h.mics() == [("docent", True)]


# ── 사회자 받아치기 (B2) ─────────────────────────────────────────────


def test_도슨트가_끝나면_사회자가_받아치고_그_뒤에야_마이크가_열린다():
    """관람객은 마이크가 언제 열렸는지 모른다. 사회자가 말로 창구를 연다.

    **순서가 전부다.** 받아치기가 생성으로 바뀐 뒤에도 이 순서는 그대로여야 한다
    — 대사 내용은 LLM 이 정하지만 "도슨트 뒤 사회자 한 번, 그 다음에야 마이크"
    는 상태기계의 불변식이다(설계 §4.1).
    """
    h = Harness(after=("네, 그렇군요. 궁금한 점 있으면 말씀해 주세요.", ""))
    h.d.start(); h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")
    assert [r for r, _ in h.says()] == ["mc"], h.says()
    assert h.d.state is State.MC_SPEAKING
    assert all(open_ is False for _, open_ in h.mics())
    h.clear()
    h.ended("mc", "c1:after")
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]


def test_받아치기가_없는_큐는_도슨트_뒤_곧장_듣는다():
    h = Harness()
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    assert h.d.state is State.LISTENING


def test_받아치기도_이력에_남는다():
    """이력은 하나이고 접두로 화자를 가른다(설계 §5.2) — 받아치기는 `사회자:` 다.

    **실제로 나간 대사와 같아야 한다.** 받아치기가 생성으로 바뀌면서 이력에
    적는 자리와 말하는 자리가 갈라질 수 있게 됐다(관람객 창구 안내를 덧붙이는
    자리가 그 사이에 있다) — 둘이 어긋나면 다음 LLM 호출이 로봇이 실제로 한
    말과 다른 이력을 보게 된다.
    """
    h = Harness(after=("받아치기", ""))
    h.d.start(); h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][-1]
    assert h.d.history[-1]["content"] == f"사회자: {said}"


def test_생성_결과가_너무_짧으면_경고한다():
    """조용히 짧게 나오는 것이 지금 문제의 본질이다 — 최소한 로그에는 드러나야 한다."""
    h = Harness(generate=lambda role, brief, hist: "네.")
    h.d.start()
    h.ended("mc", "c1")
    assert any("짧다" in w for w in h.warnings), h.warnings


def test_빈_생성_결과의_폴백에는_짧다는_경고가_덧붙지_않는다():
    """리뷰 지적: `_generate_pending` 이 빈 문자열을 이미 폴백(QA_FALLBACK, 37자)
    으로 갈아친 뒤인데 `_await_pending` 이 그 폴백에도 MIN_CHARS(40) 검사를
    걸면 "생성 실패" 경고 뒤에 "생성 결과가 짧다" 는 **틀린** 경고가 덧붙는다.
    로그만 보면 LLM 이 37자짜리 답을 낸 것으로 오판한다 — 폴백에는 걸리지 않는다.
    """
    calls = {"n": 0}

    def gen(role, brief, history):
        calls["n"] += 1
        if calls["n"] == 1:
            return "[첫 지시 로 만든 대사]"  # 사전 생성(도슨트 첫 대사)은 정상
        return ""  # 질문 응답만 빈 문자열 → QA_FALLBACK(37자) 로 대체된다

    h = Harness(generate=gen)
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.clear()
    h.warnings.clear()
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    assert any("빈 문자열" in w for w in h.warnings), h.warnings
    assert not any("짧다" in w for w in h.warnings), h.warnings


def test_새_세대는_이전_세대의_폴백_표시를_물려받지_않는다():
    """같은 슬롯을 연달아 쓸 때 이전 세대의 폴백 표시가 남아 있으면, 다음 세대가
    **진짜로** 짧은 대사를 내놓아도 MIN_CHARS 경고가 침묵한다 — 조용히 짧아지는
    것을 잡으려고 만든 경고가 하필 그 상황에서 꺼진다.

    슬롯이 하나뿐일 때는 닿기 어려웠지만, 받아치기(`"after"`)처럼 한 섹션 안에서
    같은 슬롯이 여러 세대를 도는 자리가 생기면 "폴백 세대 → 진짜 생성" 배치가
    정상 경로가 된다. 슬롯을 나누는 지금이 막기 가장 싼 자리다.

    **어디를 봐야 하는가**: `_generate_pending` 은 `text` 와 `is_fallback` 을 한
    락 안에서 쌍으로 쓴 **뒤에야** `ready` 를 세우고, `_await_pending` 은 그
    이벤트를 기다린 뒤 토큰까지 맞아야 읽는다. 그래서 표시가 썩어 있는 구간은
    **띄운 직후부터 결과가 들어오기 전까지**뿐이다. 그 구간을 게이트로 붙잡아
    슬롯을 직접 본다 — 여기서 True 가 보이면 `_spawn_generate` 가 초기화를
    빠뜨린 것이고, 결과를 기다리지 않고 슬롯을 엿보는 경로가 하나라도 생기는
    순간 위의 침묵이 실제로 난다.
    """
    gate = threading.Event()
    calls = {"n": 0}

    def gen(role, brief, history):
        calls["n"] += 1
        if calls["n"] == 1:
            return ""        # 1세대: 빈 문자열 → 폴백으로 갈린다(표시가 True 가 된다)
        gate.wait(5.0)       # 2세대: 결과를 붙잡아 둔다 — 썩은 표시가 보이는 구간을 연다
        return "네."          # 진짜 생성 결과인데 MIN_CHARS(40) 미만

    h = Harness(generate=gen)
    h.d.start()                                        # 1세대
    ready1, _ = h.d._snapshot_slot("docent")
    assert ready1.wait(2.0), "1세대 생성이 끝나지 않았다"
    with h.d._gen_lock:
        assert h.d._slots["docent"]["is_fallback"] is True, "1세대가 폴백으로 갈리지 않았다"

    h.ended("mc", "c1")                                # 1세대 폴백을 도슨트가 읽는다
    h.ended("docent", "c1:docent")
    h.warnings.clear()
    h.d.on_heard("마르코니가 누구예요")                  # 2세대 — 같은 "docent" 슬롯

    # 2세대는 게이트에 걸려 아직 아무것도 못 썼다. `_spawn_generate` 가 띄우면서
    # 표시를 내려놨어야 하는 바로 그 구간이다.
    with h.d._gen_lock:
        assert h.d._slots["docent"]["is_fallback"] is False, \
            "새 세대가 이전 세대의 폴백 표시를 물려받았다"

    gate.set()
    h.ended("mc", "c1:ack")
    assert any("짧다" in w for w in h.warnings), h.warnings


def test_슬롯이_다르면_서로를_지우지_않는다():
    """도슨트 해설 생성이 받아치기 슬롯을 밀어내면 받아치기가 통째로 사라진다.

    `_spawn_generate(slot, role, brief, fallback, label)` — 슬롯은 "밀어내지
    않을 자리", `role` 은 "어느 페르소나로 말할지" 다. 이 태스크가 role 을
    시그니처에 더했다(이후 태스크가 전부 이 5-인자 형태를 쓴다).
    """
    from stage.director import FB_BRIEF, FB_SHEET, _Pending

    h = Harness()
    h.d._spawn_generate("docent", "docent", "해설 지시", "해설 폴백", "c1")
    h.d._spawn_generate("after", "mc", "받아치기 지시", "받아치기 폴백", "c1:after")
    ready_d, tok_d = h.d._snapshot_slot("docent")
    ready_a, tok_a = h.d._snapshot_slot("after")
    assert ready_d is not ready_a, "두 슬롯이 같은 Event 를 쓴다"
    assert ready_d.wait(3.0) and ready_a.wait(3.0)
    pend_d = _Pending("docent", "docent", "c1:docent", "x", FB_BRIEF, "c1")
    pend_a = _Pending("after", "mc", "c1:after", "y", FB_SHEET, "c1:after")
    assert h.d._await_pending(pend_d, ready_d, tok_d) != \
           h.d._await_pending(pend_a, ready_a, tok_a)


def test_생성_콜백은_슬롯이_아니라_role_을_받는다():
    """리뷰 Important 1 — `_generate_pending` 이 `self._generate(role, …)`
    대신 실수로 `self._generate(slot, …)` 를 부르면 이 테스트가 잡는다.

    `Director` 의 실제 호출부 둘(`_begin_cue`/`_answer`)은 늘
    `slot == role == "docent"` 라 그 두 자리만으로는 이 혼동이 드러나지
    않는다 — 533개가 전부 통과한 채로 `_generate(role, …)` 를
    `_generate(slot, …)` 로 바꿀 수 있었던 이유다. 그래서 slot 과 role 을
    일부러 다르게 준다("after"/"mc") — 생성 콜백에 "after" 가 닿으면
    슬롯이 새어 들어간 것이고, "mc" 가 닿아야 role 이 제대로 전달된 것이다.
    """
    h = Harness()
    h.d._spawn_generate("after", "mc", "받아치기 지시", "폴백", "c1:after")
    ready, _ = h.d._snapshot_slot("after")
    assert ready.wait(2.0), "생성이 끝나지 않았다"
    assert h.gen_roles[-1] == "mc", h.gen_roles


# ── Task 6 — 여는 대사 사전 생성 캐시 ────────────────────────────────

def test_여는_대사_캐시가_없으면_큐시트_원문을_읽고_경고한다():
    """캐시 미스는 조용히 넘어가면 안 된다 — 사전 생성을 빠뜨린 채 시연이
    돌면 애드리브가 통째로 없는데 아무도 모른다. `mc_lines` 를 안 주면
    (기본값) 늘 미스이므로 큐시트 원문(`cue.mc`)으로 물러나면서 경고해야
    한다."""
    h = Harness()
    h.d.start()
    assert h.says()[0][1] == "사회자 첫 대사"      # 큐시트 원문 그대로
    assert any("캐시" in w for w in h.warnings), h.warnings


def test_캐시_미스_경고에_키와_캐시_개수와_재생성_명령이_있다():
    """리뷰 Important 2 — "사전 생성을 아예 안 돌렸다" 와 "브리프를 고쳐
    해시가 바뀌었다"(해시를 키에 넣은 바로 그 목적)를 경고 문구가 구분 못
    하면, `data/mc_lines.yaml` 을 grep 해서 원인을 좁힐 수조차 없다. 조회한
    `key`, 로드된 캐시 개수, 재생성 명령을 경고에 담아야 그 즉시 원인을
    좁힐 수 있다."""
    from stage.mc_cache import cache_key

    h = Harness(mc_lines={"엉뚱한|키|000000000000": "관련없는 값"})
    h.d.start()

    key = cache_key("c1", "일반", "")   # 기본 시트는 briefs 가 없어 mc_brief 가 ""
    warning = next(w for w in h.warnings if "캐시가 없다" in w)
    assert str(key) in warning, warning
    assert "1개" in warning, warning   # 로드된 캐시 개수(엉뚱한 키 1개)
    assert "pregen_mc_lines.py" in warning, warning


def test_여는_대사_캐시가_있으면_캐시_문장을_읽는다():
    """(A) 배선 확인 — `mc_lines`/`level_name` 이 `Director` 까지 실제로
    흘러왔을 때만 캐시 히트가 쓰인다. 미스만 보는 앞 테스트는 `Director`
    가 `mc_lines` 인자를 통째로 무시해도(늘 빈 dict 로 취급해도) 통과하므로
    히트 쪽을 따로 확인한다 — `Director.__init__` 이 `mc_lines` 를
    저장하지 않게 되돌리면 이 테스트가 실패한다.

    **리뷰 Important 1** — 예전 버전은 `cache_key("c1", "초등", "")` 처럼
    `mc_brief` 가 빈 퇴화 케이스만 봤다(기본 시트에 `briefs` 가 없어서).
    그러면 `stage/director.py` 의 `cache_key(cue.id, self._level_name,
    mc_brief)` 를 `cache_key(cue.id, self._level_name, "")` 로 바꿔도(=
    지시문을 아예 안 본다) 이 테스트가 여전히 통과한다 — 캐시 키의 존재
    이유("큐시트를 고치면 낡은 항목이 드러난다")를 검증하는 경로가 통째로
    비어 있었다. 그래서 여기서는 `briefs` 를 채운 시트를 쓰고, **mc_brief
    만 다른 둘째 큐로 넘어가면 미스가 되는지**까지 본다 — 히트한 이유가
    "지시문을 봤기 때문"이지 "캐시에 뭐가 있든 무조건 맞기 때문"이 아님을
    가른다.
    """
    sheet = CueSheet([
        Cue("c1", "첫째", "여는 대사 c1", "지시1", "partner",
            briefs={"초등": {"mc_brief": "초등 브리프 A", "docent_brief": "해설1"}}),
        Cue("c2", "둘째", "여는 대사 c2", "지시2", "partner",
            briefs={"초등": {"mc_brief": "초등 브리프 B", "docent_brief": "해설2"}}),
    ])
    key1 = cache_key("c1", "초등", "초등 브리프 A")   # c2 의 키(다른 브리프)는 일부러 안 넣는다
    h = Harness(sheet=sheet, level_name="초등", mc_lines={key1: "캐시에서 읽은 여는 대사"})

    h.d.start()
    assert h.says() == [("mc", "캐시에서 읽은 여는 대사")]
    assert not any("캐시가 없다" in w for w in h.warnings), h.warnings

    # 같은 시트, 같은 수준인데 mc_brief 만 다른 c2 로 넘어간다 — 해시가
    # 달라 다른 키가 되므로 미스여야 한다. `cache_key` 가 `mc_brief` 를
    # 무시하게 망가지면 이 부분에서 (엉뚱하게) 다시 히트해 버린다.
    h.clear()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.warnings.clear()
    h.d.on_heard("다음")
    assert h.says()[-1] == ("mc", "여는 대사 c2"), h.says()   # 캐시 미스 → 큐시트 원문
    assert any("캐시가 없다" in w for w in h.warnings), h.warnings


def test_도슨트_해설_브리프가_수준을_따른다():
    """사회자 대사만 수준을 따르고 해설이 안 따르면 기능이 반만 도는 것이다.

    계획 보완(2026-09-20) Step 5b, 첫째 자리 — `_begin_cue` 의 도슨트
    사전 생성이 `cue.docent_brief` 대신 `cue.brief_for(level_name)[1]` 을
    써야 한다. 생성은 별도 스레드에서 돌므로(`_spawn_generate`) `started`
    이벤트로 결정적으로 기다린다 — 안 그러면 스레드가 아직 안 돈 시점에
    `seen` 을 봐서 간헐적으로 실패한다(위 `사회자가_말하는_동안…` 테스트와
    같은 함정).
    """
    sheet = CueSheet([Cue(
        "c1", "첫째", "여는 대사", "옛 지시문", "partner",
        briefs={
            "초등": {"mc_brief": "초등 진행", "docent_brief": "초등 해설 지시"},
            "중고등": {"mc_brief": "중 진행", "docent_brief": "중 해설 지시"},
            "일반": {"mc_brief": "일반 진행", "docent_brief": "일반 해설 지시"},
            "전문가": {"mc_brief": "전 진행", "docent_brief": "전문가 해설 지시"},
        },
    )])
    seen: list[str] = []
    started = threading.Event()

    def gen(role, brief, hist):
        seen.append(brief)
        started.set()
        return "대사"

    h = Harness(sheet=sheet, level_name="초등", generate=gen)
    h.d.start()
    assert started.wait(2.0), "도슨트 사전 생성이 돌지 않았다"
    assert any("초등 해설 지시" in b for b in seen), seen
    assert not any("옛 지시문" in b for b in seen), seen


def test_도슨트_해설_폴백도_수준을_따른다(monkeypatch):
    """계획 보완 Step 5b, 둘째 자리 — `on_speaking_ended` 의 `pending` 폴백.

    사전 생성이 유예시간(`GENERATE_GRACE_S`)을 넘기면 이 폴백이 그대로
    도슨트 입에 오른다. 여기를 옛 `cue.docent_brief` 로 남겨 두면 첫째
    자리(`_begin_cue`)만 고친 채로도 571개가 통과한다 — 사전 생성이
    "느릴 때만" 드러나는 잔여 버그라 놓치기 쉽다.
    """
    import stage.director as director_mod

    monkeypatch.setattr(director_mod, "GENERATE_GRACE_S", 0.05)

    sheet = CueSheet([Cue(
        "c1", "첫째", "여는 대사", "옛 지시문", "partner",
        briefs={
            "초등": {"mc_brief": "초등 진행", "docent_brief": "초등 해설 지시"},
            "중고등": {"mc_brief": "중 진행", "docent_brief": "중 해설 지시"},
            "일반": {"mc_brief": "일반 진행", "docent_brief": "일반 해설 지시"},
            "전문가": {"mc_brief": "전 진행", "docent_brief": "전문가 해설 지시"},
        },
    )])
    gate = threading.Event()

    def gen(role, brief, history):
        gate.wait(5.0)          # 유예시간을 반드시 넘기게 붙잡아 둔다
        return "늦은 대사"

    h = Harness(sheet=sheet, level_name="초등", generate=gen)
    h.d.start()
    h.ended("mc", "c1")          # 유예시간(0.05s) 안에 못 끝나 폴백으로 진행
    assert h.says()[-1] == ("docent", "초등 해설 지시"), h.says()
    gate.set()                   # 뒤늦게 끝난 생성 스레드를 풀어 정리한다


def test_질문_응답_브리프에_문장_수_지정이_없다():
    """리뷰 Important(범위 밖에서 찾아 범위로 접은 항목) — 분량은 섹션이
    아니라 수준의 함수다(설계 §5, Task 3). `_answer` 가 브리프 본문에
    "N문장 이내" 를 박으면 (i) 사회자 대사·도슨트 해설은 수준을 따르는데
    질문 응답만 고정 분량으로 도는 비대칭이 생기고, (ii) 큐시트에서 걷어낸
    (Task 5) 바로 그 표현이 다른 자리에서 되살아난 것이다."""
    import re

    got = threading.Event()
    seen: list[str] = []

    def gen(role, brief, hist):
        seen.append(brief)
        got.set()
        return "답"

    h = Harness(generate=gen)
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    got.clear()
    seen.clear()
    h.d.on_heard("마르코니가 누구예요")
    assert got.wait(2.0), "질문 응답 생성이 돌지 않았다"
    assert seen, "질문 응답 브리프를 못 봤다"
    qa_brief = seen[-1]
    assert "마르코니가 누구예요" in qa_brief, qa_brief   # 질문·섹션 맥락은 그대로 준다
    assert not re.search(r"\d+\s*문장\s*이내", qa_brief), qa_brief


# ── Task 7 — 받아치기 이중 생성(예비·실제) ───────────────────────────
#
# 받아치기는 두 벌로 만든다. **예비**는 섹션 시작에 도슨트 *지시문*만 보고,
# **실제**는 도슨트 대사를 보낼 때 도슨트가 *실제로 한 말*을 보고 만든다.
# 폴백 사다리는 셋이다: 실제 → 예비 → 큐시트 원문. 아래 테스트들은 그 세 단을
# 하나씩 밟는다 — 한 단이 끊기면 그 단의 테스트만 실패해야 원인이 바로 보인다.

_SPARE_MARK = "도슨트가 이런 해설을 할 것이다"   # 예비 생성 지시문의 머리
_REAL_MARK = "도슨트가 방금 이렇게 말했다"        # 실제 생성 지시문의 머리


def _wait_slot(h, slot, timeout=3.0):
    ready, _ = h.d._snapshot_slot(slot)
    assert ready.wait(timeout), f"{slot!r} 슬롯 생성이 끝나지 않았다"


def test_받아치기는_도슨트_실제_발언을_받는다():
    """미리 만든 것보다 실제 반응이 낫다 — 제시간에 오면 그걸 쓴다.

    **세대 재확인이 슬롯을 따라가는지도 여기서 드러난다.** 2구간의
    `_snapshot_slot(...)` 에 `"docent"` 를 박아 두면 받아치기 갈래가 남의 슬롯
    세대와 제 토큰을 비교하게 돼(둘은 따로 센다) 멀쩡한 받아치기가 매번
    "다음 턴으로 넘어갔다" 며 버려진다 — 그러면 사회자가 아무 말도 안 한다.
    """
    def gen(role, brief, hist):
        if role == "mc" and _REAL_MARK in brief:
            return "실제 반응 대사입니다. 관람객 여러분 궁금한 점 있으실까요?"
        return "[생성] " + brief

    h = Harness(generate=gen, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"]
    assert said and "실제 반응" in said[0], said


def test_받아치기_실제_생성이_늦으면_예비를_읽는다(monkeypatch):
    """예비는 **여유분**이다 — 실제가 늦으면 그것을 읽어야 존재 이유가 산다.

    예비와 실제를 **한 슬롯**에 담으면 이 테스트가 실패한다: 같은 슬롯은
    "마지막 하나만 산다" 라, 실제를 띄우는 순간 예비가 지워져 큐시트 원문까지
    미끄러진다(예비 생성은 통째로 죽은 LLM 호출이 된다).
    """
    from stage import director as _director
    monkeypatch.setattr(_director, "GENERATE_GRACE_S", 0.3)
    gate = threading.Event()

    def gen(role, brief, hist):
        if _REAL_MARK in brief:
            gate.wait(30)          # 유예를 넘긴다
            return "너무 늦은 반응"
        if _SPARE_MARK in brief:
            return "미리 만들어 둔 반응입니다. 궁금한 점 있으실까요?"
        return "해설입니다."

    h = Harness(generate=gen, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")                   # 여기서 예비·실제가 나란히 뜬다
    _wait_slot(h, "after_spare")          # 예비가 준비된 상태를 만든다
    h.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"]
    assert said, "받아치기가 안 나갔다"
    assert "미리 만들어 둔 반응" in said[0], said
    assert "너무 늦은" not in said[0], said
    assert "고정 받아치기" not in said[0], said   # 큐시트까지 미끄러지지 않았다
    gate.set()


def test_예비도_실제도_늦으면_큐시트_고정_문장을_읽는다(monkeypatch):
    """사다리의 마지막 단. 여기까지 내려와도 **조용히** 내려오지 않는다."""
    from stage import director as _director
    monkeypatch.setattr(_director, "GENERATE_GRACE_S", 0.3)
    gate = threading.Event()
    fixed = "저도 인상 깊었습니다. 궁금한 점 있으실까요? 이어가려면 '다음'이라고 해 주세요."

    def gen(role, brief, hist):
        if role == "mc":
            gate.wait(30)          # 예비도 실제도 안 돌아온다
            return "너무 늦은 반응"
        return "해설입니다."

    h = Harness(generate=gen, after=(fixed, ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"]
    assert said == [fixed], said
    assert any("늦다" in w for w in h.warnings), h.warnings
    gate.set()


def test_예비_받아치기는_도슨트_지시문을_사회자_역할로_받는다():
    """슬롯과 role 은 **다른 축이다**(`_spawn_generate(slot, role, …)`).

    대장 「값이 같은 두 인자를 서로 바꿔도 안 잡힌다」 — 도슨트 쪽은 slot 과 role
    이 둘 다 "docent" 라 바꿔 넣어도 드러나지 않았다. 여기는 값이 다르니
    ("after_spare"/"mc") 그 점을 쓴다: 생성 콜백에 "after_spare" 가 닿으면 슬롯이
    새어 들어간 것이고, "docent" 가 닿으면 사회자가 **도슨트 분량**(수준에 따라
    최대 5~7문장)으로 떠든다 — 받아치기는 짧아야 한다.
    """
    seen: list[tuple[str, str]] = []

    def gen(role, brief, hist):
        seen.append((role, brief))
        return "네, 그렇군요. 궁금한 점 있으실까요?"

    h = Harness(after=("고정 받아치기", ""), generate=gen)
    h.d.start()
    h.ended("mc", "c1")
    _wait_slot(h, "after_spare")
    spare = [(r, b) for r, b in seen if _SPARE_MARK in b]
    assert len(spare) == 1, seen
    role, brief = spare[0]
    assert role == "mc", f"예비 받아치기가 {role!r} 페르소나로 생성됐다"
    assert "첫 지시" in brief, brief        # 도슨트 **지시문**을 보고 만든다


def test_섹션_시작에는_도슨트_해설_생성만_띄운다():
    """(리뷰 Important 1) **임계경로에 받아치기 생성을 얹지 않는다.**

    `stage/__main__.py::build_generate` 는 LLM 호출 전체를 락 하나로 직렬화한다.
    그런데 파이썬 `Lock` 은 FIFO 가 아니라, `_begin_cue` 가 도슨트 해설과 예비를
    연달아 띄우면 **예비가 먼저 잡아 도슨트 해설 생성을 사회자 대사 한 벌만큼
    통째로 미룰 수 있다.** 도슨트의 예산은 여는 대사 재생 + `GENERATE_GRACE_S`
    8초뿐이고, 넘기면 폴백이 `docent_brief` 라 **도슨트가 지시문을 소리 내어
    읽는다** — 이 작업이 숨기려던 지연을 이 작업이 새로 만드는 꼴이다.

    그래서 섹션이 시작될 때 뜨는 생성은 **하나**여야 한다. 받아치기 두 벌은
    도슨트 해설 생성이 끝난 뒤(도슨트 대사를 보낼 때) 나란히 뜬다.
    """
    seen: list[tuple[str, str]] = []

    def gen(role, brief, hist):
        seen.append((role, brief))
        return "해설입니다. 충분히 긴 대사라고 가정한다. 정말 그렇다."

    h = Harness(after=("고정 받아치기", ""), generate=gen)
    h.d.start()
    _wait_slot(h, "docent")
    assert len(seen) == 1, f"섹션 시작에 생성이 {len(seen)}건 떴다: {seen}"
    assert seen[0][0] == "docent", seen

    h.ended("mc", "c1")                    # 도슨트 해설이 확정된 뒤에야
    _wait_slot(h, "after_spare"); _wait_slot(h, "after")
    assert len(seen) == 3, seen            # 해설 + 예비 + 실제
    assert any(_SPARE_MARK in b for _, b in seen), seen
    assert any(_REAL_MARK in b for _, b in seen), seen


def test_실제_받아치기_지시문은_도슨트가_실제로_한_말을_담는다():
    """지시문이 아니라 **발언**을 받아야 진짜 반응이다 — 그래서 도슨트 대사를
    확정한 뒤에야 띄운다. 도슨트 발화(~7-8초)가 이 생성 시간을 산다."""
    seen: list[tuple[str, str]] = []

    def gen(role, brief, hist):
        seen.append((role, brief))
        if role == "docent":
            return "도슨트가 실제로 한 말입니다."
        return "네, 그렇군요. 궁금한 점 있으실까요?"

    h = Harness(after=("고정 받아치기", ""), generate=gen)
    h.d.start()
    h.ended("mc", "c1")
    _wait_slot(h, "after")
    real = [(r, b) for r, b in seen if _REAL_MARK in b]
    assert len(real) == 1, seen
    role, brief = real[0]
    assert role == "mc", f"실제 받아치기가 {role!r} 페르소나로 생성됐다"
    assert "도슨트가 실제로 한 말입니다." in brief, brief
    assert "첫 지시" not in brief, brief    # 지시문을 보고 만들면 '예비' 와 똑같아진다


def test_질문_응답_뒤에는_받아치기를_생성하지_않는다():
    """`:qa` 뒤에는 **생성된** 받아치기를 띄우지 않는다.

    그 자리에서 생성을 띄우면 아무도 안 읽는 LLM 호출이 질문마다 하나씩 는다.
    `_spawn_generate` 가 세대를 **동기적으로** 올리므로 토큰으로 본다.

    답 뒤에 사회자가 다시 묻기는 한다(`:reask`) — 그건 고정 문장이라 LLM 을
    부르지 않는다. 이 테스트가 지키는 것이 바로 그 구분이다.
    """
    h = Harness(after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1"); h.ended("docent", "c1:docent"); h.ended("mc", "c1:after")
    assert h.d.state is State.LISTENING
    _, before = h.d._snapshot_slot("after")

    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    h.ended("docent", "c1:qa")
    h.ended("mc", "c1:reask")                # 고정 문장으로 다시 묻고 끝난다
    assert h.d.state is State.LISTENING
    _, after_tok = h.d._snapshot_slot("after")
    assert after_tok == before, "질문 응답 뒤에 받아치기 생성이 떴다"


# ── (A) 생성된 받아치기도 관람객 창구를 말로 연다 ──────────────────────


def test_생성된_받아치기에_관람객_창구_안내가_없으면_고정_문장을_붙인다():
    """마이크가 열려도 관람객은 그것을 모른다(리뷰 B2).

    큐시트의 고정 `mc_after` 19곳은 전부 이 안내를 달고 있고 데이터 테스트가
    그것을 못박는다(`tests/test_stage_cues.py::test_모든_큐에_받아치기가_있고_
    다음을_안내한다`). 받아치기를 생성으로 바꾸면 그 보장이 **폴백에만** 남는다
    — 생성이 성공할수록 관람객이 참여 방법을 모르게 되는 비대칭이다.
    """
    from stage.cues import ADVANCE_HINT, QUESTION_PROMPTS

    h = Harness(generate=lambda role, brief, hist: "그렇군요. 저도 놀랐습니다.",
                after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert said.startswith("그렇군요. 저도 놀랐습니다."), said   # 생성물을 버리지는 않는다
    assert any(q in said for q in QUESTION_PROMPTS), said       # 질문을 받는다고 말한다
    assert ADVANCE_HINT in said, said                           # 넘기는 법도 말한다
    assert any("질문 유도가 없다" in w for w in h.warnings), h.warnings


def test_받아치기에_이미_창구_안내가_있으면_덧붙이지_않는다():
    """덧붙이는 것은 **빠졌을 때만**이다 — 늘 붙이면 같은 말이 두 번 나간다."""
    from stage.cues import QUESTION_PROMPTS

    line = f"저도 그 대목이 좋았습니다. {QUESTION_PROMPTS[0]} 이어가려면 '다음'이라고 해 주세요."
    h = Harness(generate=lambda role, brief, hist: line, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert said == line, said
    assert not any("고정 문장을 붙인다" in w for w in h.warnings), h.warnings


def test_큐시트로_물러난_받아치기에는_안내를_덧붙이지_않는다():
    """폴백은 이미 안전하다 — 사람이 다듬었고 데이터 테스트가 지킨다.

    큐시트에는 `QUESTION_PROMPTS` 와 **글자가 다른** 안내가 있다(예: 15-emf 의
    "궁금한 점 있으시면 말씀해 주시고, 아니면 '다음'이요."). 문자열 대조만으로
    판정하면서 폴백까지 검사하면, 감독이 사람이 줄여 둔 대사 뒤에 같은 뜻의
    문장을 또 붙인다 — 90자 예산도 같이 넘긴다.
    """
    fixed = "저도 인상 깊었습니다. 궁금한 점 있으시면 말씀해 주시고, 아니면 '다음'이요."
    h = Harness(generate=lambda role, brief, hist: "" if role == "mc" else "해설입니다.",
                after=(fixed, ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert said == fixed, said
    assert not any("고정 문장을 붙인다" in w for w in h.warnings), h.warnings


def test_창구_안내_고정_문장은_돌아가며_쓴다():
    """같은 말이 19번 반복되면 녹음처럼 들린다 — `QA_ACK_LINES` 와 같은 이유다."""
    from stage.cues import QUESTION_PROMPTS

    h = Harness(generate=lambda role, brief, hist: "그렇군요.", after=("고정1", "고정2"))
    h.d.start()
    seen = []
    for cue in ("c1", "c2"):
        h.ended("mc", cue)
        h.clear()
        h.ended("docent", f"{cue}:docent")
        seen.append([t for r, t in h.says() if r == "mc"][0])
        h.ended("mc", f"{cue}:after")
        if cue == "c1":
            h.d.on_heard("다음")
    used = [next(q for q in QUESTION_PROMPTS if q in s) for s in seen]
    assert used[0] != used[1], seen


def test_마지막_큐의_받아치기에는_진행_안내를_붙이지_않는다():
    """더 넘어갈 데가 없다. 데이터 가드가 `cues[:-1]` 로 마지막을 빼는 것과 같은 예외다
    — 마무리 인사 끝에 "이어가려면 '다음'" 이 붙으면 시연이 안 끝난 것처럼 들린다."""
    from stage.cues import ADVANCE_HINT, QUESTION_PROMPTS

    h = Harness(generate=lambda role, brief, hist: "오늘 이야기 고맙습니다.",
                after=("고정1", "고정2"))
    h.d.start()
    h.ended("mc", "c1"); h.ended("docent", "c1:docent"); h.ended("mc", "c1:after")
    h.d.on_heard("다음")                      # c2 — 기본 시트의 마지막 큐
    h.ended("mc", "c2")
    h.clear()
    h.ended("docent", "c2:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert any(q in said for q in QUESTION_PROMPTS), said   # 질문은 마지막에도 받는다
    assert ADVANCE_HINT not in said, said


# ── (B) 큐가 바뀌면 받아치기 세대도 갈린다 ────────────────────────────


def test_대기_중_다음_큐가_돌면_이전_큐의_받아치기는_안_나간다():
    """(B) `_begin_cue` 가 `"docent"` 슬롯만 갈아끼우면 생기는 구멍.

    받아치기가 고정 대사이던 동안에는 그래도 됐다. 생성이 들어오면 2구간의
    **세대 검사가 큐 전환을 못 보게 된다** — 그 검사는 "기다리는 동안 이 슬롯이
    갈렸는가" 로 판정하는데, 큐 전환이 `"after"` 를 안 갈면 판정 근거 자체가 없다.
    상태 검사로도 못 잡는다: 다음 큐의 사회자 발화가 끝나면 상태는 **다시
    LISTENING** 이라(`test_대기_중_다음_큐가_돌아…` 와 같은 틈) 이전 섹션 반응이
    새 섹션에 그대로 얹힌다.
    """
    gate = threading.Event()

    def gen(role, brief, hist):
        if _REAL_MARK in brief:
            gate.wait(5.0)
            return "이전 섹션 반응입니다. 궁금한 점 있으실까요?"
        return "짧은 대사입니다. 궁금한 점 있으실까요?"

    h = Harness(generate=gen, after=("고정1", "고정2"))
    errors: list[Exception] = []

    def ended_in_thread(role, cue_id):
        try:
            h.ended(role, cue_id)
        except Exception as exc:  # noqa: BLE001 — 스레드 밖으로 못 나가는 예외를 걷는다
            errors.append(exc)

    h.d.start()
    h.ended("mc", "c1")          # 도슨트 해설이 나가면서 실제 받아치기 생성이 게이트에 걸린다
    waiter = threading.Thread(target=ended_in_thread, args=("docent", "c1:docent"), daemon=True)
    waiter.start()
    assert _wait_state(h, State.LISTENING), "받아치기 대기 구간에 들어가지 않았다"

    h.d.next()                   # c2 로 넘어간다 — 받아치기 세대가 갈려야 한다
    assert h.d.state is State.MC_SPEAKING
    h.clock.t += 1000
    h.d.tick()                   # 강제로 LISTENING — 상태 검사로는 못 잡는 틈을 연다
    assert h.d.state is State.LISTENING

    gate.set()
    waiter.join(timeout=5.0)
    assert not waiter.is_alive(), "받아치기 대기 스레드가 안 끝났다(교착 의심)"
    stale = [f for _, t, f in h.all_sent if t == "say" and f["cue_id"] == "c1:after"]
    assert not stale, f"이전 섹션 받아치기가 나갔다: {stale}"
    assert not errors, f"대기 스레드에서 예외가 났다: {errors}"


def test_받아치기가_없는_큐로_넘어가면_예비_슬롯도_끊는다():
    """(B) 구조적 보장. 받아치기가 없는 섹션은 이 슬롯을 **읽지 않으므로** 지금
    당장 새어 나올 길은 없다 — 그래서 더더욱 여기서 끊어 둔다. 이 슬롯을 읽는
    경로가 하나만 더 생기면(다음 태스크들이 그렇다) 이전 섹션 반응이 새 섹션의
    폴백으로 조용히 들어간다. 규칙은 하나다: **큐가 바뀌면 받아치기 세대는
    재생성되거나 무효화된다, 그대로 남지 않는다.**
    """
    h = Harness(after=("c1 고정 받아치기", ""))   # c2 에는 받아치기가 없다
    h.d.start()
    h.ended("mc", "c1")                           # c1 의 예비·실제가 뜬다
    _wait_slot(h, "after_spare")
    _, tok = h.d._snapshot_slot("after_spare")
    with h.d._gen_lock:
        assert h.d._slots["after_spare"]["text"], "예비가 생성되지 않았다"

    h.ended("docent", "c1:docent"); h.ended("mc", "c1:after")
    h.d.on_heard("다음")                          # c2 시작
    _, tok2 = h.d._snapshot_slot("after_spare")
    assert tok2 != tok, "큐가 바뀌었는데 예비 받아치기 세대가 그대로다"
    with h.d._gen_lock:
        assert h.d._slots["after_spare"]["text"] is None, "이전 큐의 예비가 남아 있다"


# ── 리뷰 수정 — 사다리가 "늦음" 에만 걸리던 구멍 (Critical) ─────────────


def _spare_ready_harness(real_result, after=("고정 받아치기", "")):
    """c1 의 예비는 준비시키고, 실제 생성만 `real_result` 로 망가뜨린 하네스.

    `real_result` 가 예외 클래스면 던지고, 문자열이면 그대로 돌려준다.
    """
    def gen(role, brief, hist):
        if _REAL_MARK in brief:
            if isinstance(real_result, type) and issubclass(real_result, Exception):
                raise real_result("실제 생성이 터졌다")
            return real_result
        if _SPARE_MARK in brief:
            return "미리 만들어 둔 반응입니다. 궁금한 점 있으실까요?"
        return "해설입니다. 충분히 긴 대사라고 가정한다. 정말 그렇다."

    h = Harness(generate=gen, after=after)
    h.d.start()
    h.ended("mc", "c1")
    _wait_slot(h, "after_spare")      # 예비는 **준비 완료** 상태다
    _wait_slot(h, "after")
    h.clear()
    h.warnings.clear()
    return h


def test_실제_생성이_터져도_준비된_예비를_읽는다():
    """**사다리가 "늦음" 에만 걸리면 안 된다**(리뷰 Critical).

    `_generate_pending` 은 예외를 만나면 **띄울 때 받은 폴백**(= 큐시트 원문)을
    슬롯에 넣고 `ready` 를 세운다. `_await_pending` 이 이벤트가 떴다는 이유로
    그 값을 그대로 돌려주면, 1구간이 계산해 둔 "준비된 예비" 가 **안 쓰이고**
    큐시트로 직행한다 — 늦을 때만 살아나는 반쪽짜리 사다리다.
    """
    h = _spare_ready_harness(RuntimeError)
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"]
    assert said, "받아치기가 안 나갔다"
    assert "미리 만들어 둔 반응" in said[0], said
    assert "고정 받아치기" not in said[0], said


def test_실제_생성이_빈_문자열이어도_준비된_예비를_읽는다():
    """예외와 빈 문자열은 `_generate_pending` 안에서 **같은 길**을 탄다 —
    한쪽만 고치면 다른 쪽이 조용히 남는다."""
    h = _spare_ready_harness("")
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"]
    assert said, "받아치기가 안 나갔다"
    assert "미리 만들어 둔 반응" in said[0], said
    assert "고정 받아치기" not in said[0], said


def test_사다리_2단과_3단의_경고가_구별된다():
    """`./reachy.sh logs` 로 원인을 가르는 저장소다 — "예비가 산 섹션" 과
    "예비까지 죽은 섹션" 은 전혀 다른 문제인데 문구가 같으면 구분이 안 된다."""
    from stage.director import FB_SHEET, FB_SPARE

    h = _spare_ready_harness(RuntimeError)          # 예비는 살아 있다
    h.ended("docent", "c1:docent")
    assert any(FB_SPARE in w for w in h.warnings), h.warnings
    assert not any(FB_SHEET in w for w in h.warnings), h.warnings

    # 예비까지 죽은 경우 — 두 생성 다 터진다
    def dead(role, brief, hist):
        if role == "mc":
            raise RuntimeError("사회자 생성이 통째로 죽었다")
        return "해설입니다. 충분히 긴 대사라고 가정한다. 정말 그렇다."

    h2 = Harness(generate=dead, after=("고정 받아치기", ""))
    h2.d.start()
    h2.ended("mc", "c1")
    _wait_slot(h2, "after")
    h2.warnings.clear()
    h2.ended("docent", "c1:docent")
    assert any(FB_SHEET in w for w in h2.warnings), h2.warnings
    assert not any(FB_SPARE in w for w in h2.warnings), h2.warnings


def test_예비를_읽어도_짧으면_경고한다():
    """예비는 큐시트 원문과 달리 **진짜 생성 결과**다. 폴백이라는 이유로 길이
    검사를 건너뛰면, 예비를 읽은 섹션만 "조용히 짧아지는 것" 의 사각지대가 된다."""
    def gen(role, brief, hist):
        if _REAL_MARK in brief:
            raise RuntimeError("실제는 터진다")
        if _SPARE_MARK in brief:
            return "네, 그렇군요."            # 진짜 생성 결과인데 MIN_CHARS(40) 미만
        return "해설입니다. 충분히 긴 대사라고 가정한다. 정말 그렇다."

    h = Harness(generate=gen, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    _wait_slot(h, "after_spare"); _wait_slot(h, "after")
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    assert any("너무 짧다" in w for w in h.warnings), h.warnings


def test_큐시트로_물러날_때는_짧다는_경고가_안_붙는다():
    """반대쪽 — 사람이 쓴 폴백에 길이를 재면 "LLM 이 짧은 답을 냈다" 는 **틀린**
    경고가 로그에 남는다(QA_FALLBACK 이 37자, MIN_CHARS 가 40이다)."""
    def dead(role, brief, hist):
        if role == "mc":
            raise RuntimeError("사회자 생성이 통째로 죽었다")
        return "해설입니다. 충분히 긴 대사라고 가정한다. 정말 그렇다."

    h = Harness(generate=dead, after=("짧은 큐시트", ""))   # 6자짜리 폴백
    h.d.start()
    h.ended("mc", "c1")
    _wait_slot(h, "after")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    assert [t for r, t in h.says() if r == "mc"] == ["짧은 큐시트"], h.says()
    assert not any("너무 짧다" in w for w in h.warnings), h.warnings


# ── 리뷰 수정 — 창구 안내 판정이 제 말도 알아본다 (Important 2) ──────────


def test_받아치기가_제_말로_물었으면_고정_문장을_안_붙인다():
    """사회자 지시문이 "관람객에게 질문을 권한다" 라, 모델은 `QUESTION_PROMPTS`
    가 아니라 제 말로 묻는다. 완전 포함 검사만 하면 거의 매번 같은 뜻이 두 번
    나가 **고정 문장을 생성으로 바꾼 이 작업의 목적이 도로 무너진다**(리뷰 I2).
    """
    line = "정말 흥미롭네요. 혹시 더 궁금하신 점 있으신가요? 아니면 '다음'이라고 말씀해 주세요."
    h = Harness(generate=lambda role, brief, hist: line, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert said == line, said
    assert not any("고정 문장을 붙인다" in w for w in h.warnings), h.warnings


def test_수사의문만_있으면_창구_안내를_붙인다():
    """물음표만으로 "물었다" 고 보면 안 된다 — "놀랍지 않나요?" 는 창구를 여는
    말이 아니다. 그때는 붙이되, 로그에서 **"정말 빠졌다" 와 구별**되게 적는다."""
    from stage.cues import QUESTION_PROMPTS

    h = Harness(generate=lambda role, brief, hist: "이거 정말 놀랍지 않나요?",
                after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert any(q in said for q in QUESTION_PROMPTS), said
    assert any("물어보긴 했는데" in w for w in h.warnings), h.warnings


def test_물음이_아예_없으면_다른_문구로_경고한다():
    """"정말 빠졌다"(페르소나를 고쳐라)와 "못 알아봤다"(판정 문구를 넓혀라)는
    고칠 곳이 다르다 — 로그가 같은 문장을 찍으면 어느 쪽인지 모른다."""
    h = Harness(generate=lambda role, brief, hist: "그렇군요. 저도 놀랐습니다.",
                after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    assert any("질문 유도가 없다" in w for w in h.warnings), h.warnings
    assert not any("물어보긴 했는데" in w for w in h.warnings), h.warnings


def test_진행_안내는_다음이라는_낱말_등장만으로_넘어가지_않는다():
    """"다음 섹션도 기대되네요" 에는 '다음' 이 있지만 관람객은 **'다음' 이라고
    말하면 된다**는 것을 못 듣는다 — 낱말이 아니라 안내인지를 본다."""
    from stage.cues import ADVANCE_HINT

    h = Harness(generate=lambda role, brief, hist: "다음 섹션도 기대되네요. 궁금한 점 있으실까요?",
                after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert ADVANCE_HINT in said, said


def test_진행_안내만_붙을_때는_경고하지_않는다():
    """모델에게 "'다음'이라고 안내해라" 를 시키지 않으므로 빠지는 게 정상이다
    (19섹션 중 18섹션에서 빠진다) — 그때마다 경고가 뜨면 "질문 유도가 **정말**
    빠졌다" 는 진짜 신호가 그 안에 묻힌다. 물러나는 것이 아니라 설계된 조립이다.

    반대로 이 경고를 없앴다고 **질문 유도** 쪽 경고까지 지우면
    `test_물음이_아예_없으면_다른_문구로_경고한다` 가 실패한다 — 둘은 다른 신호다.
    """
    from stage.cues import ADVANCE_HINT

    line = "정말 흥미롭네요. 혹시 더 궁금하신 점 있으신가요?"
    h = Harness(generate=lambda role, brief, hist: line, after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.warnings.clear()
    h.ended("docent", "c1:docent")
    said = [t for r, t in h.says() if r == "mc"][0]
    assert said == f"{line} {ADVANCE_HINT}", said
    assert not any("고정 문장을 붙인다" in w for w in h.warnings), h.warnings


# ── (D) 섹션 끝에 묻고, 침묵이면 스스로 넘어간다 ──────────────────────
#
# 예전에는 섹션이 끝나면 마이크만 열렸다. 관람객은 **"다음" 이라는 낱말을 알아야**
# 시연을 진행시킬 수 있었는데(`is_advance`) 그 규칙을 아무도 알려주지 않았다.
# 이제 사회자가 말로 묻고(`QUESTION_PROMPTS`), 그래도 조용하면 감독이 넘긴다.


def test_침묵이_한도를_넘으면_다음_큐로_간다():
    """관람객이 아무 말도 안 해도 시연은 계속돼야 한다.

    8.1 은 `QUESTION_WAIT_S`(8.0) 를 막 넘긴 시각이다 — 상수를 줄이면
    `test_침묵_한도_전에는_다음_큐로_가지_않는다` 가, 늘리면 이 테스트가 깨진다.
    """
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")       # 받아치기 없는 큐 → 곧장 듣기
    assert h.d.state is State.LISTENING
    h.clear()
    h.warnings.clear()
    h.clock.t = 8.1
    h.d.tick()
    assert h.says() == [("mc", "사회자 둘째 대사")], h.says()
    # **침묵 기한은 `_deadline` 과 다른 것이다.** 하나로 합치면 관람객이 조용할
    # 때마다 "발화 종료 응답이 없다" 가 찍혀, 로그를 보는 사람이 로봇이 먹통이
    # 된 줄 안다 — 그리고 진짜 타임아웃 복구가 침묵에 밀려 안 돈다.
    assert not any("응답이 없다" in w for w in h.warnings), h.warnings


def test_침묵_한도_전에는_다음_큐로_가지_않는다():
    """7.9 초는 아직 관람객이 입을 열 시간이다 — 말을 꺼내려던 사람을 자르면
    회복이 안 된다(무안해서 다시 입을 안 연다). 그래서 기한 검사 자체를 못박는다."""
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.clear()
    h.clock.t = 7.9
    h.d.tick()
    assert h.says() == [], h.says()
    assert h.d.state is State.LISTENING


def test_질문이_들어오면_침묵_기한이_꺼진다():
    """관람객이 입을 열었으면 침묵이 아니다.

    기한을 끄는 것은 `tick()` 의 상태 검사와 **다른** 방어선이다. 상태에만
    기대면, 답을 만드는 동안 LISTENING 에 머무는 갈래가 나중에 하나라도
    생기는 순간 관람객이 말하는 도중에 섹션이 넘어간다 — 그 회귀는 시연장
    에서만 드러난다. 그래서 기한 자체가 꺼졌는지를 값으로 본다.
    """
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")   # 질문 → 확인 멘트(MC_SPEAKING)
    assert h.d._question_deadline is None, "질문을 받고도 침묵 기한이 살아 있다"
    h.clear()
    h.clock.t = 8.1
    h.d.tick()
    assert h.says() == [], "질문 처리 중인데 다음 큐로 넘어갔다"
    assert h.d.state is State.MC_SPEAKING


def test_기한이_걸린_채_다음_큐가_시작되면_침묵_판정을_하지_않는다():
    """운영자 `n` 은 기한이 걸린 LISTENING 에서 곧장 발화로 옮겨간다 — 그 기한은
    아직 살아 있다. `tick()` 이 상태를 안 보면 사회자가 말하는 중에
    `_next_locked()` 가 불려 TurnError 로 터지거나 섹션이 건너뛰어진다.

    `on_heard` 의 기한 끄기로는 이 자리를 못 막는다 — 관람객이 아니라 운영자가
    넘긴 길이라 `on_heard` 를 지나지 않는다.
    """
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")        # 침묵 기한이 8.0 에 걸린다
    h.clock.t = 1.0
    h.d.next()                            # 운영자가 기한 만료 전에 넘긴다
    assert h.d.state is State.MC_SPEAKING
    h.clear()
    h.clock.t = 8.1                       # 침묵 기한은 지났고 발화 기한은 아직 멀다
    h.d.tick()
    assert h.says() == [], h.says()
    assert h.d.state is State.MC_SPEAKING


def test_유령_발화_종료는_침묵_기한을_끄지_않는다():
    """콘솔 `r` 뒤 중단된 발화의 늦은 보고 같은 유령이 관람객 대기를 꺼 버리면,
    그 뒤로는 침묵이 아무리 길어도 자동 진행이 안 된다 — 운영자가 `n` 을 칠
    때까지 정적이다. 기한을 끄는 줄은 반드시 유령 검사 **아래**에 있어야 한다."""
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.clear()
    h.d.on_speaking_ended("docent", "c1:docent", 999)   # seq 가 안 맞는 유령
    assert any("유령" in w for w in h.warnings), h.warnings
    h.clock.t = 8.1
    h.d.tick()
    assert h.says() == [("mc", "사회자 둘째 대사")], h.says()


def _마지막_큐_듣기까지(h):
    """기본 2큐 시트에서 마지막 큐(c2)의 LISTENING 까지 몰고 간다."""
    h.d.start()
    h.ended("mc", "c1"); h.ended("docent", "c1:docent")
    h.d.on_heard("다음")
    h.ended("mc", "c2"); h.ended("docent", "c2:docent")
    assert h.d.state is State.LISTENING


def test_마지막_큐에서_침묵으로_끝나면_경고하지_않는다():
    """19-closing 이 끝나고 8초 뒤는 **완전 정상 종료**다 — 아무도 뭘 요청한
    적이 없다. 여기에 경고를 달면 **매 시연마다** 찍혀서, 이 파일이 아끼는
    진짜 신호("질문 유도가 빠졌다" 같은 것)가 그 안에 묻힌다.

    **부정 단언이지만 공허하지 않다** — 바로 아래 짝 테스트
    (`test_마지막_큐에서_콘솔_n_은_여전히_경고한다`)가 그 경고 경로가 살아 있고
    도달 가능함을 값으로 증명한다. 둘이 같이 있어야 "갈랐다" 가 박힌다.
    """
    h = Harness()
    _마지막_큐_듣기까지(h)
    h.clear()
    h.warnings.clear()
    h.clock.t = 8.1
    h.d.tick()
    assert h.says() == [], h.says()
    assert not any("마지막" in w for w in h.warnings), h.warnings
    # 기한을 소비했는지 값으로 본다. 안 끄면 이 갈래가 tick 마다(0.5초에 한 번)
    # 시연이 끝날 때까지 계속 도는데, 마지막 큐에서는 경고가 사라져 **밖으로는
    # 아무 흔적도 안 남는다** — 그래서 필드를 직접 본다.
    assert h.d._question_deadline is None, "침묵 갈래가 기한을 소비하지 않았다"
    h.clock.t = 30.0
    h.d.tick()
    assert not any("마지막" in w for w in h.warnings), h.warnings


def test_마지막_큐에서_콘솔_n_은_여전히_경고한다():
    """운영자가 눌렀는데 아무 일도 안 일어났다 — 그건 알려줘야 한다.
    침묵 자연 종료와 **다른 사건**이라 같은 `_next_locked()` 를 다르게 부른다."""
    h = Harness()
    _마지막_큐_듣기까지(h)
    h.warnings.clear()
    h.d.next()
    assert any("마지막" in w for w in h.warnings), h.warnings


def test_마지막_큐에서_진행_신호를_받으면_침묵_기한도_꺼진다():
    """`on_heard` 의 `is_advance` 갈래는 마지막 큐에서 **LISTENING 에 그대로
    머문 채** 돌아온다 — `on_heard` 를 지나고도 상태가 안 바뀌는 유일한 자리다.
    기한을 끄는 줄이 `is_advance` 검사 **위**에 있어야 이 갈래까지 덮는다."""
    h = Harness()
    _마지막_큐_듣기까지(h)
    h.warnings.clear()
    h.d.on_heard("다음")                    # 마지막 큐 — 경고 한 번
    assert len([w for w in h.warnings if "마지막" in w]) == 1, h.warnings
    assert h.d.state is State.LISTENING     # 상태가 안 바뀌었다
    assert h.d._question_deadline is None, "진행 신호를 받고도 침묵 기한이 살아 있다"


def test_타임아웃_복구_뒤에도_침묵이_이어지면_다음_큐로_간다():
    """강제 복구로 열린 마이크도 관람객 창구다. 거기서 기한을 안 걸면 고장
    복구가 **영구 정지**가 된다 — 운영자가 `n` 을 칠 때까지 아무 일도 안 난다."""
    h = Harness()
    h.d.start()
    h.clock.t = len("사회자 첫 대사") / CHARS_PER_SEC + TIMEOUT_MARGIN_S + 0.1
    h.d.tick()                              # 발화 종료 보고가 없다 → 강제 복구
    assert h.d.state is State.LISTENING
    h.clear()
    h.clock.t += 8.1
    h.d.tick()
    assert h.says() == [("mc", "사회자 둘째 대사")], h.says()


def test_생성을_기다리는_동안에는_침묵_기한이_섹션을_건너뛰지_않는다():
    """**이 작업에서 가장 위험한 자리다.**

    `on_speaking_ended` 는 도슨트 대사를 기다리는 동안 락을 놓는데, 그때 상태는
    이미 LISTENING 이다(1구간이 상태기계를 옮겨 둔다). 이전 섹션 끝에 걸어 둔
    기한이 하필 그 대기 중에 만료되면 `tick()` 이 "침묵이다" 로 읽고 다음 섹션을
    시작한다 — 관람객은 조용한 적이 없는데 섹션 하나가 통째로 사라진다.
    1구간이 기한을 끄고, 쉬러 들어가는 갈래가 새로 거는 이유다.

    운영자 `n` 으로 재현한다: 기한이 걸린 채 다음 큐로 넘어가고, 그 큐의 도슨트
    생성이 느리다.
    """
    gate = threading.Event()
    started = threading.Event()

    def gen(role, brief, hist):
        if brief == "둘째 지시":
            started.set()
            gate.wait(5.0)
        return f"[{brief} 로 만든 대사]"

    sheet = CueSheet([
        Cue("c1", "첫째", "사회자 첫 대사", "첫 지시", "partner"),
        Cue("c2", "둘째", "사회자 둘째 대사", "둘째 지시", "partner"),
        Cue("c3", "셋째", "사회자 셋째 대사", "셋째 지시", "partner"),
    ])
    h = Harness(sheet=sheet, generate=gen)
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")          # 침묵 기한이 8.0 에 걸린다
    assert h.d.state is State.LISTENING

    h.clock.t = 1.0
    h.d.next()                              # 운영자가 기한 만료 전에 넘긴다
    assert started.wait(2.0), "둘째 큐 도슨트 생성이 시작되지 않았다"

    done = threading.Event()

    def end_mc():
        h.ended("mc", "c2")                 # 여기서 생성 대기에 들어간다
        done.set()

    waiter = threading.Thread(target=end_mc, daemon=True)
    waiter.start()
    # 대기 구간에 들어갔는지 상태로 본다 — `tick()` 은 진입 락을 잡으므로
    # 1구간이 끝난 뒤에야 돈다(경합이 아니라 순서가 보장된다).
    assert _wait_state(h, State.LISTENING), "생성 대기 구간에 들어가지 않았다"

    h.clear()
    h.clock.t = 8.1                         # c1 끝에 걸렸던 기한을 지난 시각
    h.d.tick()
    assert h.says() == [], f"해설을 기다리는 사이에 섹션이 건너뛰어졌다: {h.says()}"
    assert h.d._sheet.current().id == "c2"

    gate.set()
    assert done.wait(3.0), "생성 대기 스레드가 안 끝났다"


# ── (E) 질문에 답한 뒤에도 사회자가 다시 묻는다 ───────────────────────


def test_질문_응답이_끝나면_사회자가_다시_묻는다():
    """예전에는 `:qa` 뒤에 곧장 LISTENING 이었다 — 마이크만 열리고 사회자는
    아무 말도 안 하니, 답을 들은 관람객은 더 물어도 되는지 알 수 없었다.
    받아치기가 창구를 말로 여는 것과 같은 이유로 여기도 말이 필요하다(리뷰 B2).
    """
    from stage.cues import QUESTION_PROMPTS

    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    h.clear()
    h.ended("docent", "c1:qa")
    assert h.says() == [("mc", QUESTION_PROMPTS[0])], h.says()
    assert h.d.state is State.MC_SPEAKING
    # 불변식 ① — 다시 묻는 동안에는 어느 마이크도 열리지 않는다.
    #
    # **`all(...)` 로 쓰지 않는다.** 마이크 지시가 하나도 안 나가면 그 단언은
    # 공허하게 참이 된다(대장 「부정·공허 단언은 죽은 코드를 못 잡는다」) —
    # `cmds` 의 마이크 열기를 `coalesce` 가 덮는지가 정확히 이 테스트의 관심사인데,
    # 지시가 통째로 사라져도 통과해 버린다. 나간 것을 값으로 못박는다.
    assert h.mics() == [("mc", False), ("docent", False)], h.mics()


def test_다시_묻는_말이_끝나야_듣기로_가고_침묵_기한이_걸린다():
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    h.ended("docent", "c1:qa")
    h.clear()
    h.ended("mc", "c1:reask")
    assert h.d.state is State.LISTENING
    assert h.mics() == [("mc", True)]
    h.clear()
    h.clock.t = 8.1
    h.d.tick()
    assert h.says() == [("mc", "사회자 둘째 대사")], h.says()


def test_다시_묻는_말은_생성을_띄우지_않는다():
    """고정 문장이라 지연이 0 이다. 여기서 LLM 을 부르면 답을 들은 관람객이
    다음 물음을 꺼내기까지 몇 초를 더 기다린다 — 얻는 것(말투)보다 잃는 것
    (반응 지연)이 크다.

    **세대 토큰으로 본다.** `_spawn_generate` 는 토큰을 **동기적으로** 올리지만
    `gen_calls` 는 스레드가 돌아야 쌓인다 — 개수만 보면 "아직 안 돌았을 뿐"
    인 것을 "안 띄웠다" 로 오판한다(간헐적으로 통과하는 테스트가 된다).
    """
    slots = ("docent", "after", "after_spare")
    h = Harness(after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.ended("mc", "c1:after")
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    before = {s: h.d._snapshot_slot(s)[1] for s in slots}
    h.ended("docent", "c1:qa")
    assert {s: h.d._snapshot_slot(s)[1] for s in slots} == before


def test_다시_묻는_말은_돌아가며_쓴다():
    """같은 말이 반복되면 녹음처럼 들린다 — `QA_ACK_LINES` 와 같은 이유다."""
    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    seen = []
    for _ in range(2):
        h.d.on_heard("질문")
        h.ended("mc", "c1:ack")
        h.clear()
        h.ended("docent", "c1:qa")
        seen.append(h.says()[0][1])
        h.ended("mc", "c1:reask")
    assert seen[0] != seen[1], seen


def test_받아치기_안내와_다시_묻는_말이_커서를_함께_쓴다():
    """**한 섹션 안에서 같은 문장이 두 번 나가면 안 된다.**

    두 자리가 모두 `QUESTION_PROMPTS` 에서 꺼낸다: 받아치기에 질문 유도가 빠졌을
    때 붙이는 것(`_ensure_visitor_cue`)과 도슨트 답 뒤에 다시 묻는 것(`:reask`).
    커서(`_q_i`)를 따로 두면 둘 다 0번을 집어, 관람객은 받아치기 끝에
    "궁금한 점 있으실까요?" 를 듣고 질문에 답을 들은 직후 **똑같은 문장**을 또
    듣는다 — 돌아가며 쓰는 이유(녹음처럼 들린다)가 바로 이 자리에서 무너진다.
    """
    from stage.cues import QUESTION_PROMPTS

    h = Harness(generate=lambda role, brief, hist: "그렇군요. 저도 놀랐습니다.",
                after=("고정 받아치기", ""))
    h.d.start()
    h.ended("mc", "c1")
    h.clear()
    h.ended("docent", "c1:docent")            # 받아치기 — 창구 안내가 붙는다
    after_line = [t for r, t in h.says() if r == "mc"][0]
    used = [q for q in QUESTION_PROMPTS if q in after_line]
    assert len(used) == 1, (after_line, used)  # 안내가 실제로 붙었다
    h.ended("mc", "c1:after")
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    h.clear()
    h.ended("docent", "c1:qa")                # 다시 묻기
    reask = h.says()[0][1]
    assert reask in QUESTION_PROMPTS, reask
    assert reask != used[0], (after_line, reask)


def test_다시_묻는_말도_이력에_남는다():
    """이력은 하나다(설계 §5.2). 사회자가 방금 질문을 권한 것을 다음 생성이
    못 보면, 이어지는 받아치기·해설이 같은 권유를 또 한다."""
    from stage.cues import QUESTION_PROMPTS

    h = Harness()
    h.d.start()
    h.ended("mc", "c1")
    h.ended("docent", "c1:docent")
    h.d.on_heard("마르코니가 누구예요")
    h.ended("mc", "c1:ack")
    h.clear()
    h.ended("docent", "c1:qa")
    said = h.says()[0][1]
    assert h.d.history[-1] == {"role": "assistant", "content": f"사회자: {said}"}
    assert said in QUESTION_PROMPTS, said
