import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from scripts.merge_research import (
    _SHORTENED_MC_AFTER,
    _clean_briefs,
    _fix_mc,
    _fix_mc_after,
    _strip_sentence_count,
    load_research,
    merge_all,
    merged_cue,
)

# **피검 모듈에서 가져오지 않는다.** 예전에는
# `from scripts.merge_research import _DEIXIS` 였는데, 그러면 그 모듈의 출력을
# 그 모듈이 들고 있는 표로 검사하는 자기참조가 된다 — `merge_research.py` 의
# `_DEIXIS` 를 비우면 정화 가드와 이 테스트가 **동시에** 눈이 멀어, 위치 지시어가
# 브리프에 가득해도 `offenders == []` 로 통과한다(전체 리뷰).
# 같은 파일의 `sentence_count_re` 와 `tests/test_stage_cues.py` 의 위치 지시어
# 목록은 일부러 리터럴을 따로 들고 있다 — 여기만 안 그랬다.
_DEIXIS = ("여기", "이곳", "저기", "이쪽", "저쪽")


def test_조사_브리프가_큐시트로_접힌다():
    research = {
        "id": "t1", "topic": "주제",
        "briefs": {
            "초등": {"mc_brief": "초등 진행", "docent_brief": "초등 해설"},
            "중고등": {"mc_brief": "중 진행", "docent_brief": "중 해설"},
            "일반": {"mc_brief": "일반 진행", "docent_brief": "일반 해설"},
            "전문가": {"mc_brief": "전 진행", "docent_brief": "전 해설"},
        },
        "mc": "새 여는 대사", "mc_after": "새 받아치기",
    }
    cue = {"id": "t1", "title": "제목", "gaze": "partner",
           "mc": "옛 여는 대사", "mc_after": "옛 받아치기", "docent_brief": "옛 지시문"}
    out = merged_cue(cue, research)
    assert out["briefs"]["초등"]["docent_brief"] == "초등 해설"
    assert out["topic"] == "주제"
    # 조사가 고친 폴백 원문이 이긴다 — corrections 가 거기 반영돼 있다.
    assert out["mc"] == "새 여는 대사"
    assert out["mc_after"] == "새 받아치기"
    # 옛 docent_brief 는 지우지 않는다 — briefs 가 비는 섹션의 폴백이다.
    assert out["docent_brief"] == "옛 지시문"


def test_조사가_없는_섹션은_그대로_둔다():
    cue = {"id": "t9", "title": "제목", "gaze": "partner",
           "mc": "옛 대사", "docent_brief": "옛 지시문"}
    assert merged_cue(cue, None) == cue


def test_브리프가_비어_있으면_접지_않는다():
    """조사 파일은 있는데 briefs 가 비었으면(예: 조사 실패) 옛 값을 지키는 편이 안전하다."""
    cue = {"id": "t1", "title": "제목", "gaze": "partner",
           "mc": "옛 대사", "docent_brief": "옛 지시문"}
    assert merged_cue(cue, {"id": "t1", "briefs": {}})["mc"] == "옛 대사"


# ── mc_after: 되돌리지 않고 접미사를 붙이거나 본문을 줄인다 (리뷰, 2026-09-20) ──
#
# 첫 구현은 인터랙션 불변식(다음 안내·90자)을 어기면 옛 mc_after 로 되돌렸는데,
# 그러면 조사가 고친 사실 오류(14-mobile "아파트"→"자동차", 05-donor "의학박사"
# →"의사", 15-emf 의 근거 없는 건강 단정 삭제)가 함께 사라진다. 아래는 그
# 되돌림 대신 붙인 새 로직(_fix_mc_after)을 직접 검증한다.


def test_mc_after에_다음_안내가_없으면_접미사를_붙인다():
    fixed, note = _fix_mc_after("x", "궁금한 점 있으실까요?", is_last=False)
    assert "다음" in fixed
    assert fixed.startswith("궁금한 점 있으실까요?"), "원문을 지우지 않고 뒤에 덧붙여야 한다"
    assert len(fixed) <= 90
    assert note["action"] == "접미사_추가"


def test_mc_after가_이미_안전하면_그대로_쓴다():
    fixed, note = _fix_mc_after("x", "새 받아치기, 이어가려면 '다음' 이라고 해 주세요.", is_last=False)
    assert fixed == "새 받아치기, 이어가려면 '다음' 이라고 해 주세요."
    assert note is None


def test_mc_after가_마지막_큐면_다음_없이도_그대로_쓴다():
    fixed, note = _fix_mc_after("19-closing", "감사합니다.", is_last=True)
    assert fixed == "감사합니다."
    assert note is None


def test_15emf는_되돌리지_않고_줄인_대체본을_쓴다():
    """실제 조사 원문(106자, '다음' 없음)은 접미사를 붙여도 90자를 넘는다.
    되돌리면 15-emf corrections 가 삭제하라고 한 건강 단정이 되살아난다 —
    되돌리지 않고 정정을 지킨 대체본을 쓴다."""
    original = (
        "세기가 발생원에서 멀어질수록 빠르게 줄어든다는 것, 그래서 기준도 일반인용과 "
        "직업인용으로 따로 있다는 게 핵심이군요. 이 주제는 특히 궁금한 점이 많으실 것 "
        "같아요. 무엇이든 물어봐 주세요."
    )
    fixed, note = _fix_mc_after("15-emf", original, is_last=False)
    assert fixed == _SHORTENED_MC_AFTER["15-emf"]
    assert len(fixed) <= 90
    assert "다음" in fixed
    assert "괜찮다" not in fixed and "유해하지 않다" not in fixed
    assert note["action"] == "줄여서_채택"


def test_대체본도_접미사도_안_통하면_소리_내서_실패한다():
    too_long_no_advance = "가" * 100  # '다음' 없음, 접미사를 붙여도 여전히 90자 초과
    with pytest.raises(ValueError, match="mc_after"):
        _fix_mc_after("등록되지-않은-id", too_long_no_advance, is_last=False)


# ── mc: 실측 결과 사실 정정을 나르지 않으므로 불변식 위반이면 되돌려도 안전 ──


def test_mc가_130자를_넘으면_되돌린다():
    long_new = "가" * 131
    fixed, note = _fix_mc("x", long_new, "짧은 옛 mc")
    assert fixed == "짧은 옛 mc"
    assert note["before"] == long_new


def test_mc에_위치_지시어가_있으면_되돌린다():
    fixed, note = _fix_mc("x", "여기는 전파체험관입니다.", "옛 mc")
    assert fixed == "옛 mc"


def test_mc가_안전하면_그대로_쓴다():
    fixed, note = _fix_mc("x", "새 mc", "옛 mc")
    assert fixed == "새 mc"
    assert note is None


# ── briefs 정화: 위치 지시어(리뷰 B4) ────────────────────────────────────


def test_briefs의_위치_지시어가_고쳐진다():
    # 09-special-exhibit/초등/mc_brief 는 고침표에 항목이 하나뿐이라(docent_brief
    # 는 등록돼 있지 않다) 이 필드만 신경 쓰면 된다.
    briefs = {"초등": {"mc_brief": "여기에는 가끔 바뀌는 특별한 전시가 있다고 알린다.",
                      "docent_brief": "그대로"}}
    cleaned, changes = _clean_briefs("09-special-exhibit", briefs)
    assert "여기" not in cleaned["초등"]["mc_brief"]
    assert cleaned["초등"]["mc_brief"] == "특별교류전시에는 가끔 바뀌는 전시가 있다고 알린다."
    assert cleaned["초등"]["docent_brief"] == "그대로"
    assert changes[0]["kind"] == "위치_지시어"


def test_고침표의_원문_조각이_없으면_소리_내서_실패한다():
    """조사 파일이 바뀌어 고침표가 겨냥하던 문구가 사라지면, 조용히 넘어가지
    않고 실패해야 한다 — 안 그러면 다음에 같은 문구가 다른 자리에 다시 들어와도
    아무도 못 잡는다."""
    briefs = {"초등": {"mc_brief": "완전히 다른 문장이다.", "docent_brief": "그대로"}}
    with pytest.raises(ValueError, match="못 찾았다"):
        _clean_briefs("09-special-exhibit", briefs)


# ── briefs 정화: 문장 수 중복(수준 프로필과 진실 원천이 둘이 된다) ──────────


def test_문장_수_중복_표현이_걷어진다():
    assert _strip_sentence_count("2~3문장. 전파는 파동이다.") == "전파는 파동이다."
    assert _strip_sentence_count("전파는 파동이다. 5~7문장.") == "전파는 파동이다."
    assert _strip_sentence_count("3문장 이내. 말한다.") == "말한다."
    assert _strip_sentence_count("문장 수 표현이 없는 문장이다.") == "문장 수 표현이 없는 문장이다."


# ── merge_all 통합: 실제 조사 파일로 접었을 때 사실 정정이 살아 있는가 ─────
#
# 리뷰(2026-09-20): 첫 구현은 아래 세 섹션의 mc_after 정정을 조용히 버렸다.
# 실제 data/cues-research/*.yaml 을 읽어 옛(사실 오류가 있던) mc_after 를
# 흉내 낸 큐와 함께 접어서, 정정이 살아남는지 직접 확인한다.


def _old_cue(cue_id, mc, mc_after, title="제목", gaze="partner"):
    return {"id": cue_id, "title": title, "gaze": gaze, "mc": mc,
            "mc_after": mc_after, "docent_brief": "옛 지시문"}


def test_실제_조사에서_사실_정정이_유지된다():
    research = load_research()
    old_cues = [
        _old_cue(
            "14-mobile",
            "이번 주제는 휴대폰의 발전, 이동통신입니다. 도슨트, 1세대부터 5세대까지 어떻게 달라졌나요?",
            "카폰이 아파트 한 채 값이었다니 놀랍네요. 질문 있으시면 말씀해 주시고, 이어가려면 '다음'이요.",
            gaze="audience",
        ),
        _old_cue(
            "15-emf",
            "지금부터는 KCA가 정부에서 위탁받은 전파품질 관리 업무 이야기입니다. 도슨트, 전자파는 안전한가요?",
            "거리를 조금만 두면 괜찮다는 게 핵심이군요. 이 주제는 질문이 많을 것 같아요. 말씀해 주시고, 아니면 '다음'입니다.",
            gaze="audience",
        ),
        _old_cue(
            "05-donor",
            "이 체험관 정식 이름에는 사람 이름이 하나 들어 있습니다. 도슨트, 장황남 박사가 누구인지 소개해 주세요.",
            "의학박사가 통신 장비를 모았다는 게 뜻밖이죠. 궁금한 점 있으시면 말씀해 주시고, 이어가려면 '다음'이요.",
        ),
        # 위 셋을 "마지막 큐"로 만들지 않으려는 더미 — 마지막 큐는 '다음' 검사가
        # 빠지므로, 이걸 넣지 않으면 이 테스트가 실제로 검증하려는 접미사/줄임
        # 경로를 안 타고도 통과해 버릴 수 있다.
        _old_cue("__dummy__", "dummy", "dummy"),
    ]
    merged, log = merge_all(old_cues, research)
    by_id = {c["id"]: c for c in merged}

    assert "아파트" not in by_id["14-mobile"]["mc_after"]
    assert "자동차" in by_id["14-mobile"]["mc_after"]

    # **부정 단언에는 반드시 긍정 짝을 붙인다.** 아래 셋이 `not in` 뿐이던 동안에는
    # `mc_after` 가 통째로 비거나 접미사("이어가려면 '다음'…")만 남아도 통과했다
    # — 조사가 고친 사실 정정이 사라진 그 상태가 정확히 이 테스트가 막으려던
    # 것이다(전체 리뷰). 14-mobile 은 처음부터 긍정 짝이 있었고, 나머지 둘만
    # 없었다.
    assert "괜찮다" not in by_id["15-emf"]["mc_after"]
    assert "유해하지 않다" not in by_id["15-emf"]["mc_after"]
    # 15-emf 는 접미사를 붙여도 90자를 넘어 사람이 줄인 대체본으로 간다 — 그
    # 대체본의 본문(거리에 따라 세기가 준다는 정정된 서술)이 실제로 살아 있어야
    # 한다. 건강 단정만 빠지고 본문이 날아가면 해설이 사라진다.
    assert "멀어질수록" in by_id["15-emf"]["mc_after"]
    assert "줄어든다" in by_id["15-emf"]["mc_after"]

    assert "의학박사" not in by_id["05-donor"]["mc_after"]
    # corrections 2번이 '의학박사' 를 '의사' 로 바꾼 것 — 낱말이 통째로 빠진 것이
    # 아니라 **바뀐 낱말로** 남아야 정정이 유지된 것이다.
    assert "의사" in by_id["05-donor"]["mc_after"]
    assert "통신 장비" in by_id["05-donor"]["mc_after"]


def test_실제_조사를_접으면_briefs에_위치_지시어나_문장_수_중복이_안_남는다():
    research = load_research()
    old_cues = [
        _old_cue(rid, "m", "m") for rid in sorted(research)
    ]
    merged, log = merge_all(old_cues, research)

    sentence_count_re = re.compile(r"\d+\s*[~\-]\s*\d+\s*문장")
    offenders = []
    for c in merged:
        for level, b in (c.get("briefs") or {}).items():
            for field in ("mc_brief", "docent_brief"):
                text = b.get(field, "")
                if not isinstance(text, str):
                    continue
                if any(w in text for w in _DEIXIS):
                    offenders.append((c["id"], level, field, "위치 지시어", text))
                if sentence_count_re.search(text):
                    offenders.append((c["id"], level, field, "문장 수", text))
    assert offenders == []

    # 이번에 실제로 고쳤다고 보고한 위치 지시어 ~~16곳~~ 15곳 + 문장 수 중복 20곳
    # (5섹션×4수준)이 이 실행에서도 그대로 잡혔는지 — 표가 비거나 함수가 no-op 이
    # 되면 이 수가 0으로 떨어진다. 16 → 15: 2026-09-22 06-bands 초등 mc_brief 의
    # 질문을 바꿔("왜 여러 종류로 나눠 놓았는지") 위치 지시어 자체가 없어졌다.
    deixis_fixed = [c for c in log["briefs_changes"] if c["kind"] == "위치_지시어"]
    sc_fixed = [c for c in log["briefs_changes"] if c["kind"] == "문장_수_중복"]
    assert len(deixis_fixed) == 15
    assert len(sc_fixed) == 20


def test_저장소_큐시트는_다시_접어도_바뀌지_않는다():
    """**조사 파일이 원본이고 큐시트가 사본이다.** 큐시트만 고치고 조사 파일을 안
    고치면 다음 접기(`merge_research.py`)가 그 수정을 조용히 되돌린다 — `briefs`·
    `mc`·`mc_after` 를 조사 값으로 통째로 덮어쓰기 때문이다. 포인트 첫 판이
    `briefs` 안에 둔 points 와, 02·06 의 오프닝·`guard` 가 그런 자리였다.
    지금 큐시트가 곧 "지금 조사 파일을 접은 결과" 여야 한다."""
    import copy

    import yaml

    from scripts.merge_research import CUES

    cues = yaml.safe_load(CUES.read_text(encoding="utf-8"))
    merged, _ = merge_all(copy.deepcopy(cues), load_research())
    for before, after in zip(cues, merged):
        assert after == before, f"{before['id']}: 다시 접으면 바뀐다"
