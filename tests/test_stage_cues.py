"""큐시트 — 진행의 뼈대.

`mc` 는 고정 대사이고 `docent_brief` 는 LLM 에게 주는 **지시**다(대사가 아니다).
사회자를 고정하는 이유는 두 가지다: 진행이 결정적이어야 시연이 안 무너지고,
사회자가 고정 대사를 말하는 3~5초 동안 도슨트 대사를 생성해 **LLM 지연을 숨긴다**.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage import cues as cues_mod
from stage.cues import Cue, CueError, CueSheet, is_advance, load_cues


def write(tmp_path, text):
    p = tmp_path / "cues.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_저장소의_큐시트가_읽힌다():
    loaded = load_cues()
    assert len(loaded) >= 4
    assert loaded[0].id == "01-intro"
    assert all(isinstance(c, Cue) for c in loaded)


def test_모든_큐가_필수_필드를_채우고_있다():
    for c in load_cues():
        assert c.id and c.title and c.mc and c.docent_brief, c.id
        assert c.gaze in cues_mod.GAZE_TARGETS, c.id


def test_큐_id_가_중복되면_거절한다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: partner}
- {id: "a", title: "t2", mc: "m2", docent_brief: "b2", gaze: partner}
""")
    with pytest.raises(CueError, match="중복"):
        load_cues(p)


def test_필수_필드가_비면_거절한다(tmp_path):
    # 조용히 빈 대사를 말하는 로봇이 되는 것이 최악이다.
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "", docent_brief: "b", gaze: partner}
""")
    with pytest.raises(CueError, match="mc"):
        load_cues(p)


def test_모르는_gaze_는_거절한다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: 하늘}
""")
    with pytest.raises(CueError, match="gaze"):
        load_cues(p)


def test_빈_큐시트는_거절한다(tmp_path):
    with pytest.raises(CueError, match="비어"):
        load_cues(write(tmp_path, "[]"))


def test_환경변수로_큐시트_경로를_바꾼다(tmp_path, monkeypatch):
    p = write(tmp_path, """
- {id: "z", title: "t", mc: "m", docent_brief: "b", gaze: partner}
""")
    monkeypatch.setenv("REACHY_CUES_PATH", str(p))
    assert load_cues()[0].id == "z"


# ── 진행 신호 판정 ────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["다음", "계속", "계속하죠", "다음으로", "넘어가요", "진행해"])
def test_진행_신호를_알아본다(text):
    assert is_advance(text)


@pytest.mark.parametrize(
    "text",
    [
        "궁금한 거 없어요 다음",   # "궁금"이 있지만 부정문 — 진짜 전환이다
        "설명 됐어요 다음",       # "설명"이 있지만 끝맺는 낱말은 전환어다
        "다 알고 있어요 다음",    # "알고"가 있지만 끝맺는 낱말은 전환어다
    ],
)
def test_질문_낱말이_섞여도_마지막_낱말이_전환어면_진행_신호다(text):
    """질문 표지 확장(2026-09-11)이 연 반대 방향 사각지대.

    부분 문자열 포함만으로는 부정문을 못 가른다. 마지막 낱말의 **위치**가
    전환인지 질문인지를 가른다 — 한국어 전환 발화는 전환어로 끝나고
    ("...다음"), 질문은 의문 표지로 끝난다("...궁금해요").
    """
    assert is_advance(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "그 다음에 헤르츠는 뭘 했나요?",   # 질문이다 — LLM 으로 넘긴다
        "다음은 뭔가요?",                  # 질문 표지가 있으면 넘기지 않는다
        "마르코니가 누구예요",
        "전파가 뭐예요",
        "다음 얘기 궁금해요",       # 의문사도 물음표도 없지만 질문이다
        "다음 거 설명해줘",
        "계속 알려주세요",
        "언제 다음이에요",          # 서술어가 전환어 어근으로 시작할 뿐인 질문이다
        "얼마나 계속되나요",
        "다음은?",                  # 접미가 2자 이내여도 물음표가 있으면 질문이다
        "다음?",
        "계속?",
        "계속돼?",
        "여기가 다음이에요",        # 마지막 낱말이 전환어 접미 판정에 걸리지 않는 질문
        "다음인가요",
        "다음 전시실이 맞아요",
        "이게 다음 순서예요",
    ],
)
def test_진행_신호가_아닌_것을_넘기지_않는다(text):
    assert not is_advance(text)


# ── 커서 ──────────────────────────────────────────────────────────

def sheet():
    return CueSheet([
        Cue("a", "A", "m1", "b1", "partner"),
        Cue("b", "B", "m2", "b2", "audience"),
    ])


def test_처음에는_첫_큐를_가리킨다():
    s = sheet()
    assert s.index == 0
    assert s.current().id == "a"
    assert not s.done


def test_advance_는_다음_큐를_준다():
    s = sheet()
    assert s.advance().id == "b"
    assert s.index == 1


def test_마지막_다음은_None_이고_done_이_된다():
    s = sheet()
    s.advance()
    assert s.advance() is None
    assert s.done
    assert s.current().id == "b"   # 커서는 마지막에 머문다


def test_reset_은_처음으로_되돌린다():
    s = sheet()
    s.advance()
    s.reset()
    assert s.index == 0
    assert not s.done


def test_빈_큐시트로는_만들_수_없다():
    with pytest.raises(CueError, match="비어"):
        CueSheet([])


def test_큐시트가_해설_원장의_모든_섹션을_덮는다():
    """`docs/exhibit-guide.md` 의 `## N.` 섹션마다 큐가 하나씩 있어야 한다.

    원장에 섹션을 더하고 큐를 안 만들면 그 구간을 로봇이 통째로 건너뛴다.
    """
    import re

    guide = (
        pathlib.Path(__file__).parent.parent / "docs/exhibit-guide.md"
    ).read_text(encoding="utf-8")
    sections = re.findall(r"^## (\d+)\.", guide, flags=re.MULTILINE)
    assert sections, "원장에서 섹션을 못 찾았다 — 형식이 바뀌었는지 확인한다"

    numbers = {c.id.split("-")[0] for c in load_cues()}
    missing = [n for n in sections if f"{int(n):02d}" not in numbers]
    assert not missing, f"큐가 없는 섹션: {missing}"


def test_이전_큐로_되돌릴_수_있다():
    """수동 오버라이드(설계 §7)가 성립하려면 커서가 뒤로도 가야 한다.

    앞으로만 갈 수 있으면 오인식으로 넘어가 버린 섹션을 되찾을 길이
    아예 없다(리뷰 I4)."""
    s = sheet()
    s.advance()
    assert s.current().id == "b"
    assert s.back().id == "a"
    assert s.current().id == "a"


def test_첫_큐에서_되돌리면_None_이고_커서는_머문다():
    s = sheet()
    assert s.back() is None
    assert s.index == 0
