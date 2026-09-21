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


# ── 필드 타입 (리뷰 A8a) ─────────────────────────────────────────────


def test_숫자인_mc_는_거절한다(tmp_path):
    """`mc: 123` 이 통과해 `_estimate` 의 len() 에서 TypeError 가 났고,
    감독은 MC_SPEAKING 에 데드라인 없이 굳었다(리뷰 A8a)."""
    p = write(tmp_path, """
- {id: "a", title: "t", mc: 123, docent_brief: "b", gaze: partner}
""")
    with pytest.raises(CueError, match="문자열"):
        load_cues(p)


def test_값이_없는_mc_는_거절한다(tmp_path):
    p = write(tmp_path, """
- id: "a"
  title: "t"
  mc:
  docent_brief: "b"
  gaze: partner
""")
    with pytest.raises(CueError, match="mc"):
        load_cues(p)


def test_숫자인_id_는_거절한다(tmp_path):
    p = write(tmp_path, """
- {id: 07, title: "t", mc: "m", docent_brief: "b", gaze: partner}
""")
    with pytest.raises(CueError, match="문자열"):
        load_cues(p)


# ── 받아치기 mc_after (B2) ───────────────────────────────────────────


def test_mc_after_는_선택이고_없으면_빈_문자열이다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: partner}
- {id: "b", title: "t", mc: "m", docent_brief: "b", gaze: partner, mc_after: "네, 그렇군요."}
""")
    a, b = load_cues(p)
    assert a.mc_after == "" and b.mc_after == "네, 그렇군요."


def test_mc_after_가_문자열이_아니면_거절한다(tmp_path):
    p = write(tmp_path, """
- {id: "a", title: "t", mc: "m", docent_brief: "b", gaze: partner, mc_after: 3}
""")
    with pytest.raises(CueError, match="mc_after"):
        load_cues(p)


# ── 대담 프레임 (B4) ─────────────────────────────────────────────────

_DEIXIS = ("여기", "이곳", "저기", "이쪽", "저쪽")


def test_사회자_대사에_위치_지시어가_없다():
    """두 로봇은 책상 위에 고정돼 있고 관람객이 움직인다(원장 「걷어낸 것」).
    "여기는 ~존입니다" 는 로봇이 그 자리에 있다는 거짓말이다(리뷰 B4)."""
    for c in load_cues():
        for w in _DEIXIS:
            assert w not in c.mc, f"{c.id} mc: {w!r}"
            assert w not in c.mc_after, f"{c.id} mc_after: {w!r}"


def test_모든_큐에_받아치기가_있고_다음을_안내한다():
    cues = load_cues()
    for c in cues:
        assert c.mc_after, f"{c.id} 에 mc_after 가 없다"
    for c in cues[:-1]:                 # 마지막 큐는 '다음' 이 없다
        assert "다음" in c.mc_after, f"{c.id} 받아치기가 진행 신호를 안내하지 않는다"


def test_사회자_대사_길이가_예산_안이다():
    # CHARS_PER_SEC=4 → 130자면 32초 + 여유 15초. 이보다 길면 한 큐가 늘어진다.
    for c in load_cues():
        assert len(c.mc) <= 130, f"{c.id} mc {len(c.mc)}자"
        assert len(c.mc_after) <= 90, f"{c.id} mc_after {len(c.mc_after)}자"


def test_사회자_대사가_한_틀로_반복되지_않는다():
    firsts = [c.mc.split(" ")[0] for c in load_cues()]
    assert len(set(firsts)) >= 8, f"첫 낱말이 너무 겹친다: {firsts}"


# ── 수준별 브리프 (Task 5) ───────────────────────────────────────────


def test_수준별_브리프를_읽는다(tmp_path):
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  mc_after: "받아치기"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: {mc_brief: "초등 진행", docent_brief: "초등 해설"}
    중고등: {mc_brief: "중고등 진행", docent_brief: "중고등 해설"}
    일반: {mc_brief: "일반 진행", docent_brief: "일반 해설"}
    전문가: {mc_brief: "전문가 진행", docent_brief: "전문가 해설"}
""")
    c = load_cues(p)[0]
    assert c.brief_for("초등") == ("초등 진행", "초등 해설")
    assert c.brief_for("전문가") == ("전문가 진행", "전문가 해설")


def test_브리프가_없으면_옛_지시문으로_폴백한다(tmp_path):
    """큐시트 전체를 한 번에 옮길 수 없다 — 섹션마다 순차로 보강한다."""
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
""")
    c = load_cues(p)[0]
    assert c.brief_for("초등") == ("", "옛 지시문")


def test_수준이_하나라도_빠지면_소리_내서_실패한다(tmp_path):
    """한 수준만 빠지면 그 수준의 시연이 통째로 옛 지시문으로 도는데 로그에는
    아무것도 안 남는다 — 그래서 일부만 채운 briefs 는 기동에서 막는다.

    match 는 "빠진 수준이 있다" 로 잡는다. 예전에는 `match="수준"` 이었는데,
    모든 `CueError` 메시지에 파일 경로가 들어가고 그 경로에는 pytest 가
    `tmp_path` 로 넣어 주는 **테스트 함수 이름**(이 안에 "수준" 이 들어 있다)이
    그대로 박힌다 — 검증을 통째로 지워도 다른 에러의 경로 문자열과 우연히
    일치해 통과한다. 바로 아래 `test_briefs_가_매핑이_아니면_거절한다` 가
    같은 함정을 이미 알고 피한 전례다.
    """
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: {mc_brief: "a", docent_brief: "b"}
""")
    with pytest.raises(CueError, match="빠진 수준이 있다"):
        load_cues(p)


def test_briefs_가_매핑이_아니면_거절한다(tmp_path):
    # match 는 "매핑이어야" 로 잡는다 — "briefs" 로 잡으면 pytest tmp_path 가
    # 테스트 함수 이름(이 안에 "briefs" 가 들어 있다)을 경로에 그대로 넣어
    # 주는 바람에, 검증을 통째로 지워도 다른 에러 메시지의 **경로 문자열**과
    # 우연히 일치해 테스트가 계속 통과하는 걸 실제로 확인했다.
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs: "초등만 적었다"
""")
    with pytest.raises(CueError, match="매핑이어야"):
        load_cues(p)


def test_브리프_항목의_docent_brief가_비면_거절한다(tmp_path):
    """`levels.py` 의 선례(리뷰: 존재만 보고 타입을 안 봤다)와 같은 자리다 —
    briefs 안의 값도 비어 있으면 조용히 빈 지시문으로 LLM 이 돈다.

    match 는 "비어 있지 않은 문자열이어야" 로 잡는다. `match="docent_brief"` 는
    `tmp_path` 에 박히는 **테스트 함수 이름**에 "docent_brief" 가 들어 있어
    검증을 지워도 다른 에러의 경로와 우연히 일치한다(위
    `test_briefs_가_매핑이_아니면_거절한다` 의 전례와 같은 함정).
    """
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: {mc_brief: "a", docent_brief: ""}
    중고등: {mc_brief: "a", docent_brief: "b"}
    일반: {mc_brief: "a", docent_brief: "b"}
    전문가: {mc_brief: "a", docent_brief: "b"}
""")
    with pytest.raises(CueError, match="비어 있지 않은 문자열이어야"):
        load_cues(p)


def test_브리프_항목이_매핑이_아니면_거절한다(tmp_path):
    """`bool` 은 `int` 의 하위형이라 `isinstance` 만으로는 못 거르는 함정이
    이 저장소에 선례가 있다(`stage/server.py::_seq_field`) — 여기서는 항목
    자체가 매핑이 아닌 경우(예: 참/거짓, 문자열)를 가장 먼저 거른다."""
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: true
    중고등: {mc_brief: "a", docent_brief: "b"}
    일반: {mc_brief: "a", docent_brief: "b"}
    전문가: {mc_brief: "a", docent_brief: "b"}
""")
    # match 는 "항목이 매핑이어야"(공백 포함)로 잡는다 — 함수 이름의
    # "항목이_매핑이_아니면"(밑줄)과 문자 그대로 겹치지 않는 문구를 고른다
    # (아래 "pytest tmp_path 와 match 가 우연히 겹친다" 항목 참고).
    with pytest.raises(CueError, match="항목이 매핑이어야"):
        load_cues(p)


# ── 리뷰 반영: briefs 필드 타입 검증 (리뷰 Important 1 / Minor) ──────────


def test_브리프_필드가_불리언이면_소리_내서_실패한다(tmp_path):
    """`docent_brief: true` 처럼 YAML 이 boolean 으로 파싱하는 값이 오면
    옛 검사(`not b.get("docent_brief")`)는 truthiness 만 보므로 조용히
    통과하고, `brief_for` 가 파이썬 `True` 를 그대로 돌려줘 프롬프트에
    리터럴 "True" 가 꽂힌다(리뷰 Important 1). `levels.py` 의 문자열 필드
    검증(`isinstance(v, str) and v.strip()`)과 같은 기준을 요구해야 한다."""
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: {mc_brief: "a", docent_brief: true}
    중고등: {mc_brief: "a", docent_brief: "b"}
    일반: {mc_brief: "a", docent_brief: "b"}
    전문가: {mc_brief: "a", docent_brief: "b"}
""")
    with pytest.raises(CueError, match="문자열이어야"):
        load_cues(p)


def test_브리프에_사회자_문구가_없으면_거절한다(tmp_path):
    """`mc_brief` 는 지금까지 아예 검사하지 않았다 — `docent_brief` 와 같은
    자리에 있는 값인데 타입·존재 검증이 비대칭이면 언젠가 같은 구멍이 난다."""
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
    초등: {docent_brief: "a"}
    중고등: {mc_brief: "a", docent_brief: "b"}
    일반: {mc_brief: "a", docent_brief: "b"}
    전문가: {mc_brief: "a", docent_brief: "b"}
""")
    with pytest.raises(CueError, match="mc_brief"):
        load_cues(p)


@pytest.mark.parametrize("raw", ["false", "0"])
def test_briefs가_거짓값이면서_매핑이_아니면_거절한다(tmp_path, raw):
    """`briefs = item.get("briefs") or {}` 로 감싸면 `briefs: false`·
    `briefs: 0` 처럼 falsy 이면서 매핑이 아닌 값이 조용히 빈 매핑으로
    둔갑해 "매핑이 아니면 거절한다" 검사 자체를 건너뛴다(리뷰 Minor).
    `None`·키가 빠진 경우만 빈 매핑으로 받고 나머지는 거절해야 한다."""
    p = write(tmp_path, f"""
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs: {raw}
""")
    with pytest.raises(CueError, match="매핑이어야"):
        load_cues(p)


def test_briefs가_없거나_null이면_빈_매핑으로_받는다(tmp_path):
    """`None` 과 "키 자체가 없음" 은 폴백 대상으로 계속 허용해야 한다 —
    19섹션을 순차로 채우는 동안 나머지는 이 상태로 남는다."""
    p = write(tmp_path, """
- id: "t1"
  title: "테스트"
  mc: "여는 대사"
  docent_brief: "옛 지시문"
  gaze: partner
  briefs:
""")
    c = load_cues(p)[0]
    assert c.briefs == {}
    assert c.brief_for("초등") == ("", "옛 지시문")


def test_데이터_큐시트에_섹션별_문장_수_지정이_없다():
    """분량은 이제 수준 프로필이 정한다(`stage/prompts.py::_amount_for`).
    docent_brief 에 "N문장 이내"(또는 "N~M문장") 가 남아 있으면 섹션 지정이
    수준 지정을 덮어써 수준을 바꿔도 분량이 안 변한다 — 회귀를 막는다.

    이 검사는 원래 옛 최상위 `docent_brief` 만 봤다. Task 9 가 접은 `briefs`
    (섹션×수준별 지시문)에 조사 파일의 "2~3문장"/"5~7문장" 표현이 그대로
    딸려 들어왔는데, 옛 정규식(`\\d+문장 이내`)은 "이내" 가 없는 이 범위 표현을
    못 잡았다(리뷰, 2026-09-20) — 그래서 정규식도 넓히고 `briefs` 까지 본다."""
    import re

    pattern = re.compile(r"\d+\s*(?:[~\-]\s*\d+\s*)?문장(?:\s*이내)?")
    for c in load_cues():
        assert not pattern.search(c.docent_brief), (
            f"{c.id}: docent_brief 에 문장 수 지정이 남아 있다"
        )
        for level, b in c.briefs.items():
            for field in ("mc_brief", "docent_brief"):
                text = b.get(field, "")
                assert not pattern.search(text), (
                    f"{c.id}/{level}/{field}: briefs 에 문장 수 지정이 남아 있다 — {text!r}"
                )


def test_모든_큐에_수준별_브리프가_채워져_있다():
    """`briefs` 가 비면 `Cue.brief_for` 가 옛 최상위 `docent_brief` 로 폴백하는데,
    거기엔 아직 못 걷어낸 사실 오류가 남아 있을 수 있다(예: 07-maritime 의
    '695명'/'1992년' — Task 9 보고서 참고). 19섹션 전부 채웠다는 것을 회귀
    가드로 박아 둔다 — `data/cues.yaml` 에서 `briefs` 를 통째로 지워도 이
    테스트 전에는 그걸 잡는 게 없었다(리뷰, 2026-09-20)."""
    from stage.levels import LEVEL_NAMES

    for c in load_cues():
        assert c.briefs, f"{c.id}: briefs 가 비어 있다 — 옛 docent_brief 로 폴백한다"
        assert set(c.briefs) == set(LEVEL_NAMES), f"{c.id}: 수준이 빠졌다 — {sorted(c.briefs)}"


def test_briefs에_위치_지시어가_없다():
    """`test_사회자_대사에_위치_지시어가_없다`(B4)는 고정 대사(`mc`/`mc_after`)만
    본다. 그런데 `briefs.*.docent_brief`/`mc_brief` 는 도슨트 LLM 에게 주는
    지시문이라 "여기서는"/"이곳" 같은 표현이 있으면 LLM 이 그대로 되읊을 위험이
    있다 — 로봇은 책상에 고정돼 있고 관람객이 움직인다(원장 「걷어낸 것」).
    Task 9 가 조사 briefs 를 접으면서 16곳을 놓쳤던 자리라 별도로 가드한다."""
    for c in load_cues():
        for level, b in c.briefs.items():
            for field in ("mc_brief", "docent_brief"):
                text = b.get(field, "")
                for w in _DEIXIS:
                    assert w not in text, f"{c.id}/{level}/{field}: {w!r} — {text!r}"


# ── 창구 안내 판정 (Task 7 리뷰 Important 2) ──────────────────────────


def test_붙이는_진행_안내는_스스로_안내로_인정된다():
    """`_ensure_visitor_cue` 가 붙이는 문장이 제 판정을 통과 못 하면, 그 검사를
    두 번 도는 경로가 하나라도 생기는 순간 같은 말을 두 번 붙인다."""
    from stage.cues import ADVANCE_HINT, mentions_advance

    assert mentions_advance(ADVANCE_HINT), ADVANCE_HINT


def test_고정_질문_유도는_목록_대조_없이도_알아본다():
    """`invites_question(q) for q in QUESTION_PROMPTS` 는 **지울 수 없는 단언**이다
    — 그 함수의 첫 규칙이 목록을 통째로 대조하므로 목록에 무엇을 넣든 참이 된다
    (대장 「검증을 지워도 통과하는 단언」과 같은 모양). 그래서 목록 대조를 빼고
    어근·꼬리 규칙만으로 알아보는지 본다.

    **이게 왜 중요한가**: 모델은 고정 문구를 그대로 쓰지 않고 제 말로 묻는다.
    우리 고정 문구가 그 어휘 안에 있어야, 모델이 조금 다르게 말해도 같은 규칙이
    알아본다 — 고정 문구만 알아보는 판정은 실전에서 매번 중복을 붙인다(리뷰 I2).
    """
    from stage.cues import _INVITE_ENDINGS, _INVITE_WORDS, QUESTION_PROMPTS

    for q in QUESTION_PROMPTS:
        by_word = any(w in q for w in _INVITE_WORDS)
        by_ending = "?" in q and any(e in q for e in _INVITE_ENDINGS)
        assert by_word or by_ending, f"어근·꼬리 규칙이 못 알아보는 고정 문구: {q!r}"


def test_큐시트_받아치기는_전부_창구_안내로_인정된다():
    """폴백(큐시트)에는 안내를 덧붙이지 않는다 — 그 전제가 "이미 안내가 있다" 다.
    판정 문구를 좁히다가 이 전제가 깨지면, 폴백이 안내 없이 나가는데 감독은
    "있다" 고 믿어 아무 경고도 안 낸다."""
    from stage.cues import invites_question, mentions_advance

    cues = load_cues()
    for c in cues:
        assert invites_question(c.mc_after), f"{c.id}: {c.mc_after}"
    for c in cues[:-1]:                 # 마지막 큐는 '다음' 이 없다
        assert mentions_advance(c.mc_after), f"{c.id}: {c.mc_after}"


def test_위치_지시어는_고정_안내_문구에도_없다():
    """두 로봇은 고정돼 있고 관람객이 움직인다(리뷰 B4). 데이터만 훑던 가드를
    **런타임에 붙이는 문자열**까지 넓힌다 — 생성된 받아치기 끝에 매번 따라붙는
    문장이라 큐시트 대사와 똑같은 무게를 진다."""
    from stage.cues import ADVANCE_HINT, QA_ACK_LINES, QUESTION_PROMPTS

    for line in (*QUESTION_PROMPTS, ADVANCE_HINT, *QA_ACK_LINES):
        for w in _DEIXIS:
            assert w not in line, f"{line!r} 에 위치 지시어 {w!r}"


# ── 대시보드 런다운이 쓰는 조회·이동 ────────────────────────────────


def _시트3():
    return CueSheet([
        Cue("a", "가", "m", "d", "partner"),
        Cue("b", "나", "m", "d", "partner"),
        Cue("c", "다", "m", "d", "partner"),
    ])


def test_큐_id_로_위치를_찾는다():
    s = _시트3()
    assert s.find("c") == 2
    assert s.find("없음") is None


def test_seek_는_커서를_옮기고_그_큐를_준다():
    s = _시트3()
    assert s.seek(2).id == "c"
    assert s.index == 2 and s.current().id == "c"


def test_seek_범위_밖이면_소리_내서_실패하고_커서는_그대로다():
    s = _시트3()
    s.seek(1)
    with pytest.raises(IndexError):
        s.seek(3)
    assert s.index == 1


def test_seek_음수도_범위_밖이다():
    """파이썬 음수 색인을 그대로 받으면 `seek(-1)` 이 **마지막 큐**를 조용히
    시작한다 — 호출자의 계산 실수가 마무리 인사로 둔갑한다. 위로만 막으면 이
    쪽이 열린다."""
    s = _시트3()
    s.seek(1)
    with pytest.raises(IndexError):
        s.seek(-1)
    assert s.index == 1


def test_cues_는_전체를_순서대로_준다():
    assert [c.id for c in _시트3().cues()] == ["a", "b", "c"]
