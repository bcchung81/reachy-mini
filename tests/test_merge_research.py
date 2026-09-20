import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from scripts.merge_research import merge_all, merged_cue


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


def _full_briefs(tag: str) -> dict:
    return {
        lv: {"mc_brief": f"{tag} 진행", "docent_brief": f"{tag} 해설"}
        for lv in ("초등", "중고등", "일반", "전문가")
    }


# ── merge_all: mc_after 인터랙션 불변식(다음 안내·90자 예산) 보호 ──────────
#
# 실제 조사 파일 19개를 접어 보니 mc/mc_after 어디에도 사실 오류가 없었고(오류는
# 전부 docent_brief 쪽), 오히려 조사가 다시 쓴 mc_after 가 18/19섹션에서 '다음'
# 안내를 빠뜨리고 1곳은 90자를 넘겨 `tests/test_stage_cues.py` 의 두 불변식을
# 깼다. merged_cue 는 한 큐만 보므로 "마지막 큐인가"를 모른다 — 그 판단과 안전
# 장치는 merge_all 의 몫이다.


def test_mc_after가_다음_안내를_빠뜨리면_옛_값으로_되돌린다():
    cues = [
        {"id": "a", "title": "A", "gaze": "partner", "mc": "옛 대사 A",
         "mc_after": "옛 받아치기 A, 이어가려면 '다음' 이요.", "docent_brief": "옛 지시문"},
        {"id": "b", "title": "B", "gaze": "partner", "mc": "옛 대사 B",
         "mc_after": "옛 받아치기 B, 이어가려면 '다음' 이요.", "docent_brief": "옛 지시문"},
    ]
    research = {
        # a: 마지막이 아닌데 '다음' 이 없다 — 되돌아가야 한다.
        "a": {"id": "a", "briefs": _full_briefs("A"), "mc_after": "궁금한 점 있으실까요?"},
        # b: 마지막 큐라 '다음' 이 없어도 된다 — 그대로 접힌다.
        "b": {"id": "b", "briefs": _full_briefs("B"), "mc_after": "감사합니다."},
    }
    merged, skipped, reverted = merge_all(cues, research)
    assert merged[0]["mc_after"] == "옛 받아치기 A, 이어가려면 '다음' 이요."
    assert merged[1]["mc_after"] == "감사합니다."
    assert reverted == ["a"]
    assert skipped == []


def test_mc_after가_90자를_넘으면_옛_값으로_되돌린다():
    too_long = "다음으로 가려면 다음이라고 말씀해 주세요. " + "가" * 90
    cues = [
        {"id": "a", "title": "A", "gaze": "partner", "mc": "옛 대사",
         "mc_after": "옛 받아치기", "docent_brief": "옛 지시문"},
        {"id": "b", "title": "B", "gaze": "partner", "mc": "옛 대사 B",
         "mc_after": "옛 받아치기 B", "docent_brief": "옛 지시문"},
    ]
    research = {"a": {"id": "a", "briefs": _full_briefs("A"), "mc_after": too_long}}
    merged, skipped, reverted = merge_all(cues, research)
    assert merged[0]["mc_after"] == "옛 받아치기"
    assert reverted == ["a"]


def test_불변식을_만족하면_조사_mc_after를_그대로_쓴다():
    cues = [
        {"id": "a", "title": "A", "gaze": "partner", "mc": "옛 대사",
         "mc_after": "옛 받아치기", "docent_brief": "옛 지시문"},
        {"id": "b", "title": "B", "gaze": "partner", "mc": "옛 대사 B",
         "mc_after": "옛 받아치기 B", "docent_brief": "옛 지시문"},
    ]
    research = {
        "a": {"id": "a", "briefs": _full_briefs("A"),
              "mc_after": "새 받아치기, 이어가려면 '다음' 이라고 해 주세요."},
    }
    merged, skipped, reverted = merge_all(cues, research)
    assert merged[0]["mc_after"] == "새 받아치기, 이어가려면 '다음' 이라고 해 주세요."
    assert reverted == []
