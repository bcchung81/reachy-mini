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
from stage.cues import Cue, CueSheet, Turn
from stage.director import Director
from stage.machine import State, TurnError


def _모든_수준(text):
    return {lv: text for lv in ("초등", "중고등", "일반", "전문가")}


class Harness:
    def __init__(self, sheet=None, **director_kw):
        """`director_kw` 는 수준 전환(`l`)을 보는 테스트만 넘긴다(수준·캐시·훅)."""
        self.sent: list[tuple[str, str, dict]] = []
        self.all_sent: list[tuple[str, str, dict]] = []
        self.warnings: list[str] = []
        self.out: list[str] = []
        if sheet is None:
            # 해설은 고정 대본이다(2026-09-23) — `points` 없는 큐는 도슨트가
            # 말할 것이 없어 오프닝 뒤 곧장 관람객 차례로 간다. 수준을 안 보는
            # 테스트들이라 네 수준에 같은 문장을 채운다.
            sheet = CueSheet([
                Cue("c1", "첫째", "사회자 첫 대사", "첫 지시", "partner",
                    points=(Turn("", _모든_수준("첫 해설")),)),
                Cue("c2", "둘째", "사회자 둘째 대사", "둘째 지시", "audience",
                    points=(Turn("", _모든_수준("둘째 해설")),)),
            ])
        self.d = Director(
            sheet,
            generate=lambda role, brief, history: "도슨트 대사",
            send=lambda role, cmd: (
                self.sent.append((role, cmd.type, cmd.fields)),
                self.all_sent.append((role, cmd.type, cmd.fields)),
            ),
            warn=self.warnings.append,
            **director_kw,
        )

    def seq_of(self, cue_id):
        return [f["seq"] for _, t, f in self.all_sent if t == "say" and f["cue_id"] == cue_id][-1]

    def ended(self, role, cue_id):
        self.d.on_speaking_ended(role, cue_id, self.seq_of(cue_id))

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


def test_s_를_두_번_눌러도_공연을_되감지_않고_콘솔이_살아_있다():
    """운영자가 가장 흔히 하는 행동이다 — "시작됐나? 한 번 더".

    ~~두 번째 `start()` 는 발화 중이라 TurnError 를 던진다~~ — 2026-09-25 `s` 가 [공연 시작]
    (`start_show`)이 되어, 진행 중이면 경고만 하고 아무것도 안 건드린다. 두 번째 `s` 가 공연을
    첫 큐로 되감으면 관람객 앞에서 여는 인사가 다시 나온다.
    """
    h = Harness()
    h.run(["s", "s", "q"])
    assert "공연이 이미 진행 중이다 — 처음부터 다시 하려면 먼저 공연 종료(e)" in h.warnings
    assert h.d.state is State.MC_SPEAKING  # 첫 발화는 살아 있다
    assert h.says() == [("mc", "사회자 첫 대사")]


def test_거절_사유를_사람이_읽을_수_있게_보여준다():
    """감독이 던진 거절(TurnError)은 콘솔이 삼키지 않고 사유를 보여 준다 — 무대감독이 죽지 않는다(리뷰 C3)."""
    h = Harness()
    h.d.reject("docent", "기대한 로봇이 아니다.")
    h.run(["s", "q"])
    거절 = [m for m in h.out if "거절됨" in m]
    assert 거절 and "거부된 역할" in 거절[0]


def test_거절_뒤에도_다음_명령이_먹는다():
    """콘솔이 살아 있다는 말은 다음 키가 실제로 처리된다는 뜻이다."""
    h = Harness()
    h.d.reject("docent", "기대한 로봇이 아니다.")
    h.run(["s", "e", "q"])
    assert any("거절됨" in m for m in h.out)
    assert "공연이 진행 중이 아니다 — 끝낼 것이 없다" in h.warnings   # e 가 먹었다


def test_예상_못한_예외도_삼키지_않고_보여준다():
    """TurnError 만 잡으면 다음에 다른 예외가 나올 때 또 죽는다."""
    h = Harness()

    def 터진다():
        raise RuntimeError("감독이 터졌다")

    h.d.start_show = 터진다
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
    h.ended("mc", cue_id)
    h.ended("docent", f"{cue_id}:docent")


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



def test_r_로_다시_시작한_뒤_중단된_발화의_늦은_종료_보고는_도슨트를_깨우지_않는다():
    """리뷰 A2 — 예전에는 여기서 도슨트 say 가 나가 두 로봇이 동시에 말했다."""
    h = Harness()
    h.run(["s", "r", "q"])
    old_seq = [f["seq"] for _, t, f in h.all_sent if t == "say"][0]
    n_before = len(h.says())
    h.d.on_speaking_ended("mc", "c1", old_seq)     # 중단된 발화의 늦은 보고
    assert len(h.says()) == n_before, "유령 종료로 도슨트가 시작됐다"
    # 버리되 로그에는 남는다 — 방금 멈춘 발화의 보고라 "유령" 이 아닌 정상으로 적힌다(2026-09-25).
    assert any("멈춘 발화의 늦은 speaking_ended" in w for w in h.warnings), h.warnings
    h.ended("mc", "c1")                              # 진짜 보고
    assert h.says()[-1][0] == "docent"


def test_a_뒤에_n_을_누르면_다음_큐로_간다():
    """리뷰 A7b — 예전엔 `n` 이 on_heard("다음") 경유라 IDLE 에서 버려졌다."""
    h = Harness()
    h.run(["s", "a", "n", "q"])
    assert h.says()[-1] == ("mc", "사회자 둘째 대사")


def test_발화_중_n_은_중단하고_다음으로_간다():
    h = Harness()
    h.run(["s", "n", "q"])
    assert h.says()[-1] == ("mc", "사회자 둘째 대사")


def test_g_는_먼저_멈추고_그_큐로_간다():
    import stage.console as console
    calls = []

    class 가짜감독:
        mode = "podcast"          # 단독이 아니므로 먼저 멈춘다(`_stop_first`)

        def cue_list(self):
            return [{"id": "07-maritime", "title": "해상무선통신", "topic": "해상무선통신"}]

        def abort(self):
            calls.append("abort")

        def goto(self, cue_id):
            calls.append(("goto", cue_id))

    console.dispatch(가짜감독(), "g 07-maritime", out=lambda m: None)
    assert calls == ["abort", ("goto", "07-maritime")]


def test_g_의_모르는_큐는_진행_중인_시연을_멈추지_않는다():
    """오타 한 번이 시연을 멈추면 안 된다. 예전에는 `abort()` 를 먼저 불러
    사회자가 말하는 도중에 `g c9` 를 치면 발화가 끊기고 IDLE 에 남았다 —
    이동은 안 됐는데 시연만 멈춘 꼴이다."""
    import stage.console as console

    h = Harness()
    h.d.start()                              # 사회자가 c1 을 말하는 중
    h.sent.clear()
    h.warnings.clear()
    console.dispatch(h.d, "g c9", out=h.out.append)
    assert h.d.state is State.MC_SPEAKING
    assert [(r, t) for r, t, _ in h.sent] == []          # abort 도 say 도 안 나갔다
    assert len(h.warnings) == 1 and "c9" in h.warnings[0], h.warnings


def test_dispatch_는_콘솔과_같은_n_경로다():
    import stage.console as console
    calls = []

    class 가짜감독:
        mode = "podcast"          # 단독이 아니므로 먼저 멈춘다(`_stop_first`)

        def abort(self):
            calls.append("abort")

        def next(self):
            calls.append("next")

    console.dispatch(가짜감독(), "n", out=lambda m: None)
    assert calls == ["abort", "next"]


def test_l_은_수준을_감독에_넘기고_진행을_멈추지_않는다():
    """적용이 다음 큐라서 지금 발화를 끊을 이유가 없다 — `n`·`g` 와 달리 `abort()` 하지
    않는다. 수준 이름 검증은 감독이 한다(경고 문구를 한 곳에 둔다, `g` 와 같은 이유)."""
    import stage.console as console
    calls = []

    class 가짜감독:
        def abort(self):
            calls.append("abort")

        def set_level(self, name):
            calls.append(("set_level", name))

    console.dispatch(가짜감독(), "l  초등 ", out=lambda m: None)
    assert calls == [("set_level", "초등")]


def test_도움말에_l_이_있다():
    """운영자가 존재를 모르는 손잡이는 없는 것과 같다 — 언제 적용되는지까지 보여야
    누르고 나서 "왜 안 바뀌지" 를 안 한다."""
    h = Harness()
    h.run(["?", "q"])
    assert any("l <수준>  관람객 수준 바꾸기(바로 — 다음 발화부터)" in m for m in h.out), h.out


def test_m_은_모드를_감독에_넘긴다():
    """이름 검증·경고 문구·말하던 것 멈추기는 전부 `Director.set_mode` 한 곳이 한다 —
    콘솔이 먼저 `abort()` 하면 거절될 전환(모르는 이름·사회자 없음)도 시연을 멈춘다."""
    import stage.console as console
    calls = []

    class 가짜감독:
        def abort(self):
            calls.append("abort")

        def set_mode(self, name):
            calls.append(("set_mode", name))

    console.dispatch(가짜감독(), "m  solo ", out=lambda m: None)
    assert calls == [("set_mode", "solo")]


def test_도움말에_m_이_있다():
    h = Harness()
    h.run(["?", "q"])
    assert any("m <모드>  운영 모드 바꾸기(podcast/solo)" in m for m in h.out), h.out


@pytest.mark.parametrize(
    "cmd, 무엇",
    [("n", "다음"), ("p", "이전"), ("r", "시작"), ("g c2", "이동"), ("s", "시작"), ("e", "종료")],
    ids=["n", "p", "r", "g", "s", "e"],
)
def test_단독에서_거절될_진행_명령은_먼저_멈추지도_않는다(cmd, 무엇):
    """진짜 감독으로 본다. 단독에서 `n`·`p`·`r`·`g`·`s`·`e` 는 감독이 거절하는데, 콘솔이 그 앞에서
    `abort()` 를 보내면 거절될 명령이 말하던 것을 끊는다 — 사회자의 단독 답변이 그것이다.
    `g` 는 **아는 큐**(c2)로 본다: 모르는 큐는 원래도 멈추지 않는다."""
    import stage.console as console

    h = Harness()
    h.d.on_connect("mc")
    h.d.set_mode("solo")
    assert h.d.mode == "solo"                  # 전제: 단독으로 바뀌었다
    h.sent.clear()
    h.warnings.clear()
    console.dispatch(h.d, cmd, out=h.out.append)
    assert h.sent == []
    assert h.warnings == [f"단독 모드에서는 팟캐스트 진행({무엇})을 하지 않는다 — 먼저 m podcast"]


def test_단독에서도_a_는_멈추고_사회자가_다시_듣는다():
    """거절될 명령만 멈추지 않는 것이지 중단 자체가 막힌 것이 아니다(설계 §1-2). 단독의 중단은
    "지금 답을 멈추고 다시 듣는다" 다(2026-09-25) — 단독에는 다시 시작할 큐가 없다."""
    import stage.console as console

    h = Harness()
    h.d.on_connect("mc")
    h.d.set_mode("solo")
    h.sent.clear()
    h.warnings.clear()
    console.dispatch(h.d, "a", out=h.out.append)
    # 중단은 양쪽 마이크를 닫고 멈춘다(2026-09-24, `TurnMachine.abort`) — 그 뒤 사회자 마이크를 다시 연다.
    assert [(r, t) for r, t, _ in h.sent] == [
        ("mc", "mic"), ("docent", "mic"), ("mc", "abort"), ("docent", "abort"), ("mc", "mic"),
    ]
    assert h.sent[-1][2] == {"open": True}
    assert h.warnings == ["단독 — 말을 멈추고 다시 듣는다(완전히 멈추려면 m podcast)"]


def test_l_은_말을_멈추지_않고_이_큐의_남은_설명부터_새_수준이다():
    """2026-09-25 결정 — 수준은 **바로, 다음 발화부터**. ~~바로 적용하려면 "이 큐 다시(R)"~~.
    콘솔 `l` 은 `n`·`g` 와 달리 먼저 멈추지 않는다: 지금 문장은 끝까지 가야 한다. 처음 수준은
    기본값("일반")이 아닌 "중고등"(함정 ③)."""
    def 브리프(수준):
        return {"mc_brief": f"{수준} 진행", "docent_brief": f"{수준} 해설"}

    sheet = CueSheet([
        Cue("c1", "첫째", "원문 c1", "옛 지시", "partner",
            briefs={n: 브리프(n) for n in ("초등", "중고등", "일반", "전문가")},
            points=(Turn("", {n: f"{n} 설명" for n in ("초등", "중고등", "일반", "전문가")}),)),
    ])
    훅: list[str] = []
    h = Harness(
        sheet=sheet, level_name="중고등", docent_min_chars=120,
        level_min_chars={"초등": 70, "중고등": 120, "일반": 180, "전문가": 260},
        on_level_change=훅.append,
    )
    h.run(["s", "l 초등", "q"])
    assert [t for _, t, _ in h.sent].count("abort") == 0        # 멈추지 않는다
    assert h.says() == [("mc", "원문 c1")]                       # 다시 열지도 않는다
    h.ended("mc", "c1")
    assert h.says()[-1] == ("docent", "초등 설명"), h.says()
    assert 훅 == ["초등"]
    assert "관람객 수준 중고등 → 초등 — 바로 적용(지금 문장은 끝까지, 다음 발화부터)" in h.warnings, h.warnings
    assert h.d.snapshot()["level"] == "초등"


class _가짜카메라:
    def __init__(self):
        self.toggled = []

    def toggle(self, role):
        self.toggled.append(role)


def test_z_는_대기모드를_토글한다():
    """`z` 는 대시보드와 같은 경로로 `Director.toggle_standby` 를 부른다(Task 4)."""
    import stage.console as console

    class 가짜감독:
        def __init__(self):
            self.toggled_standby = []

        def toggle_standby(self, role):
            self.toggled_standby.append(role)

    d = 가짜감독()
    console.dispatch(d, "z mc", out=lambda m: None)
    assert d.toggled_standby == ["mc"]


def test_c_는_카메라를_토글한다():
    """`c` 는 대시보드와 같은 경로로 `CameraRelay.toggle` 을 부른다(Task 3)."""
    import stage.console as console

    class 가짜감독:
        pass

    cam = _가짜카메라()
    console.dispatch(가짜감독(), "c docent", out=lambda m: None, camera=cam)
    assert cam.toggled == ["docent"]


def test_카메라_객체가_없으면_c_는_조용히_무시하지_않고_안내한다():
    """`camera` 기본값 `None` — 카메라 중계가 없는 감독(예: 아직 안 붙인 배포)에서
    `c` 를 눌러도 조용히 삼키지 않고 안내한다."""
    import stage.console as console

    class 가짜감독:
        pass

    out = []
    console.dispatch(가짜감독(), "c mc", out=out.append, camera=None)
    assert any("카메라" in m for m in out)


def test_도움말에_z_와_c_가_있다():
    h = Harness()
    h.run(["?", "q"])
    assert any("z <mc|docent>  대기모드 켜고 끄기" in m for m in h.out), h.out
    assert any("c <mc|docent>  카메라 스트림 켜고 끄기" in m for m in h.out), h.out


def test_콘솔_조작은_로그에_한_줄씩_남는다():
    """운영자가 친 글자는 표준입력이라 `start` 의 tee 로그에 안 남았다 — IDLE 에서 들린 말
    221건이 `a` 뒤에 생긴 것인지 로그만으로 가를 수 없었다(2026-09-24). 도움말은 조작이 아니다."""
    h = Harness()
    h.run(["s", "a", "?", "", "n"])
    ops = [m for m in h.out if m.startswith("[운영]")]
    assert ops == ["[운영] 콘솔 s", "[운영] 콘솔 a", "[운영] 콘솔 n"], ops


def test_w_는_침묵_대기_시간을_바꾸고_진행을_멈추지_않는다():
    import stage.console as console

    h = Harness()
    h.d.start()
    h.sent.clear()
    console.dispatch(h.d, "w 15", out=h.out.append)
    assert h.d.snapshot()["question_wait_total_s"] == 15
    assert not any(t == "abort" for _, t, _ in h.sent)   # 말하던 것을 끊지 않는다
