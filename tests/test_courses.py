"""코스(전체/하이라이트) — 2026-09-25 결정 문서 「코스」·「하이라이트 구성」, 전환은 **바로**(재결정).

로더는 틀린 데이터를 기동에서 막고, 커서는 코스 안의 큐만 밟고, 감독은 지금 큐를 끝까지 말한 뒤 새 코스로 간다.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.courses import CourseError, load_courses
from stage.cues import Cue, CueError, CueSheet, Turn, load_cues
from stage.director import Director
from stage.machine import State

_모든 = ("초등", "중고등", "일반", "전문가")


def _큐(cid):
    return Cue(cid, cid.upper(), f"{cid} 여는 말", "옛", "partner",
               points=(Turn("", {lv: f"{cid} 설명" for lv in _모든}),))


def _시트(n=5):
    return CueSheet([_큐(f"c{i}") for i in range(1, n + 1)])


def _코스파일(tmp_path, body):
    p = tmp_path / "courses.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# ── 로더 ─────────────────────────────────────────────────────────────


def test_실제_코스_파일은_전체와_하이라이트_9큐다():
    """결정 문서의 하이라이트 구성 그대로 — 큐시트가 바뀌어 id 가 사라지면 여기서 깨진다."""
    courses = load_courses(tuple(load_cues()))
    assert list(courses) == ["전체", "하이라이트"]
    assert courses["전체"] is None
    assert courses["하이라이트"] == (
        "01-intro", "02-history", "03-theory", "04-morse", "07-maritime",
        "14-mobile", "17-rover", "18-science", "19-closing",
    )


@pytest.mark.parametrize("body, 문구", [
    ("courses: []", "비어 있다"),
    ("courses:\n  - name: 가\n    cues: [c1, c9]", "큐시트에 없는 큐"),
    ("courses:\n  - name: 가\n    cues: [c1, c1]", "두 번"),
    ("courses:\n  - name: 가\n    cues: [c3, c1]", "큐시트 순서대로"),
    ("courses:\n  - name: 가\n    cues: all\n  - name: 가\n    cues: all", "겹친다"),
    ("courses:\n  - cues: all", "이름이 없다"),
    ("courses:\n  - name: 가\n    cues: 3", "'all' 이거나"),
])
def test_틀린_코스_파일은_기동에서_막는다(tmp_path, body, 문구):
    with pytest.raises(CourseError, match=문구):
        load_courses(tuple(_시트().cues()), _코스파일(tmp_path, body))


def test_코스_파일이_없으면_막는다(tmp_path):
    with pytest.raises(CourseError, match="없다"):
        load_courses(tuple(_시트().cues()), tmp_path / "없는.yaml")


# ── 커서 ─────────────────────────────────────────────────────────────


def test_코스가_있으면_다음과_이전은_코스_안의_큐만_밟는다():
    s = _시트()
    s.set_course(["c1", "c3", "c5"])
    assert [s.advance().id, s.advance().id, s.advance()] == ["c3", "c5", None]
    assert s.done
    assert [s.back().id, s.back().id, s.back()] == ["c3", "c1", None]


def test_되감기는_코스의_첫_큐로_간다():
    s = _시트()
    s.set_course(["c2", "c4"])
    s.reset()
    assert s.current().id == "c2"
    assert s.course_position() == (1, 2)


def test_직접_이동은_코스_밖도_가고_그_뒤_다음은_코스로_돌아온다():
    """운영자가 고른 큐는 코스 밖이어도 간다(`g`). 위치는 코스 밖이라 None."""
    s = _시트()
    s.set_course(["c1", "c4", "c5"])
    s.seek(1)                                     # c2 — 코스 밖
    assert s.course_position() == (None, 3)
    assert s.advance().id == "c4"


def test_코스를_바꿔도_커서는_그대로다_지금_큐는_끝까지():
    s = _시트()
    s.seek(1)                                     # c2
    s.set_course(["c1", "c5"])
    assert s.current().id == "c2"
    assert s.advance().id == "c5"


def test_모르는_큐나_빈_코스는_큐시트가_거절한다():
    s = _시트()
    with pytest.raises(CueError):
        s.set_course(["c9"])
    with pytest.raises(CueError):
        s.set_course([])


# ── 감독 ─────────────────────────────────────────────────────────────

_코스 = {"전체": None, "짧게": ("c1", "c3", "c5")}


class _감독:
    def __init__(self, courses=_코스):
        self.warnings: list[str] = []
        self.sent: list[tuple[str, str, dict]] = []
        self.d = Director(
            _시트(), generate=lambda r, b, h: "답이에요. 그래요.",
            send=lambda role, cmd: self.sent.append((role, cmd.type, cmd.fields)),
            warn=self.warnings.append, courses=courses,
        )

    def says(self):
        return [f["cue_id"] for _, t, f in self.sent if t == "say"]

    def ended(self, cue_id):
        seq = [f["seq"] for _, t, f in self.sent if t == "say" and f["cue_id"] == cue_id][-1]
        self.d.on_speaking_ended(self.d._machine.speaking_role, cue_id, seq)


def test_코스를_주지_않으면_전체_하나다():
    d = Director(_시트(), generate=lambda r, b, h: "x", send=lambda r, c: None, warn=lambda m: None)
    assert d.course_names() == ["전체"]
    assert d.snapshot()["course_cue_ids"] is None


def test_공연_전에_코스를_바꾸면_공연_시작은_그_코스의_첫_큐부터다():
    h = _감독({"전체": None, "뒤쪽": ("c3", "c4")})
    h.d.set_course("뒤쪽")
    assert h.warnings[-1] == "코스 전체 → 뒤쪽(2큐) — 공연 시작은 이 코스의 첫 큐부터"
    h.d.start_show()
    assert h.says() == ["c3"]


def test_공연_중에_바꾸면_지금_큐는_끝까지_다음부터_새_코스다():
    h = _감독()
    h.d.start_show()                                     # c1
    h.d.abort(); h.d.next()                              # c2 진행 중
    h.sent.clear()
    h.d.set_course("짧게")
    assert h.sent == []                                  # 멈추지 않는다
    assert h.warnings[-1] == (
        "코스 전체 → 짧게(3큐) — 바로 적용(지금 큐는 끝까지, 다음 큐부터 새 코스). "
        "지금 큐(c2)는 새 코스에 없다 — 끝나면 새 코스의 다음 큐로 간다."
    )
    assert h.d.state is State.MC_SPEAKING
    h.d.abort(); h.d.next()
    assert h.says()[-1] == "c3"


def test_코스의_마지막_큐가_침묵으로_끝나면_코스의_첫_큐로_되감는다():
    h = _감독({"전체": None, "뒤쪽": ("c4", "c5")})
    h.d.set_course("뒤쪽")
    h.d.start_show()                                     # c4
    h.d.abort(); h.d.next()                              # c5 (코스의 마지막)
    h.ended("c5"); h.ended("c5:docent")                  # 받아치기 없는 큐 → 질문 창
    assert h.d.state is State.LISTENING
    h.d._now = lambda: 10 ** 9
    h.d.tick()
    s = h.d.snapshot()
    assert (s["cue_id"], s["show_running"]) == ("c4", False)


def test_스냅샷에_코스_이름_위치_큐가_실린다():
    h = _감독()
    h.d.set_course("짧게")
    s = h.d.snapshot()
    assert (s["course"], s["course_position"], s["course_cue_ids"]) == ("짧게", [1, 3], ["c1", "c3", "c5"])


def test_모르는_코스와_같은_코스는_경고만():
    h = _감독()
    h.d.set_course("반나절")
    h.d.set_course("전체")
    assert "모르는 코스다: '반나절' — 바꾸지 않는다(고를 수 있는 것: 전체, 짧게)" in h.warnings
    assert "코스는 이미 전체 이다 — 바꿀 것이 없다" in h.warnings


def test_콘솔_k_는_코스를_감독에_넘기고_먼저_멈추지_않는다():
    import stage.console as console

    h = _감독()
    h.d.start_show()
    h.sent.clear()
    console.dispatch(h.d, "k 짧게", out=lambda m: None)
    assert h.d.snapshot()["course"] == "짧게"
    assert [t for _, t, _ in h.sent].count("abort") == 0


def test_도움말에_k_가_있다():
    from stage.console import HELP

    assert "k <코스>  코스 바꾸기(전체/하이라이트 — 바로, 다음 큐부터 새 코스)" in HELP


# ── 진입점 배선 ───────────────────────────────────────────────────────


def test_main_에서_감독까지_코스가_이어진다(monkeypatch, tmp_path):
    """대장 「`Director` 생성자 인자를 늘려도 배선 두 단계를 같이 안 고치면 늘 기본값으로 죽는다」 — main → 진짜
    StageServer → 진짜 Director. 어디서 빠뜨려도 코스가 "전체" 하나로 굳는다."""
    import stage.__main__ as stage_main
    from tests.test_stage_main import _수준_큐시트

    cues = tmp_path / "cues.yaml"
    cues.write_text(_수준_큐시트, encoding="utf-8")
    monkeypatch.setenv("REACHY_CUES_PATH", str(cues))
    monkeypatch.setenv("REACHY_COURSES_PATH", str(_코스파일(
        tmp_path, "courses:\n  - name: 전체\n    cues: all\n  - name: 한큐\n    cues: [c1]\n")))
    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
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
    assert seen["server"].director.course_names() == ["전체", "한큐"]


def test_코스_파일이_틀리면_경고하고_전체로_돈다(monkeypatch, tmp_path, capsys):
    import stage.__main__ as stage_main
    from tests.test_stage_main import _수준_큐시트

    cues = tmp_path / "cues.yaml"
    cues.write_text(_수준_큐시트, encoding="utf-8")
    monkeypatch.setenv("REACHY_CUES_PATH", str(cues))
    monkeypatch.setenv("REACHY_COURSES_PATH", str(_코스파일(tmp_path, "courses:\n  - name: 가\n    cues: [없는큐]\n")))
    monkeypatch.setattr(stage_main, "build_generate", lambda level, warn=print: (lambda r, b, h: "x"))
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
    assert seen["server"].director.course_names() == ["전체"]
    assert "코스 파일을 쓸 수 없다" in capsys.readouterr().out
