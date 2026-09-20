"""조사 산출물(`data/cues-research/*.yaml`)을 큐시트에 접는다.

**조사 파일이 원본이고 큐시트가 사본이다.** 조사 쪽 `mc`/`mc_after` 가 이기는
이유는 거기에 corrections(사실 오류 정정)가 이미 반영돼 있기 때문이다.
옛 `docent_brief` 는 지우지 않는다 — `briefs` 가 비는 섹션의 폴백이다.
"""

import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "data" / "cues-research"
CUES = ROOT / "data" / "cues.yaml"

# `mc_after` 는 사실을 나르지 않는다 — 실제로 19섹션 조사 결과를 대조해 보면 `mc`/
# `mc_after` 는 어느 섹션도 사실 오류를 담고 있지 않았고(오류는 전부 `docent_brief`
# 쪽), 조사가 다시 쓴 `mc_after` 는 오히려 **진행 키워드 안내('다음')를 18/19섹션에서
# 빠뜨렸고** 1곳(15-emf)은 90자 예산을 넘겼다. 이 둘은
# `tests/test_stage_cues.py::test_모든_큐에_받아치기가_있고_다음을_안내한다` /
# `::test_사회자_대사_길이가_예산_안이다` 가 지키는 인터랙션 설계 불변식이다 — '다음'
# 안내가 없으면 마이크가 열려도 관람객은 진행 키워드를 모르고, 90자를 넘으면 그
# 받아치기 하나가 예산보다 오래 걸린다. 조사 파일은 사실 검증용으로 만들어졌고 이
# 불변식을 몰랐다. 그대로 접으면 "사실은 고쳤지만 진행 안내가 깨진" 큐시트가 되므로,
# 이 불변식을 어기는 `mc_after` 는 접지 않고 옛 값을 지킨다 — briefs 가 비었을 때
# 옛 docent_brief 로 폴백하는 것과 같은 안전 원칙이다.
_MC_AFTER_MAX_CHARS = 90


def _mc_after_is_safe(text: str, is_last: bool) -> bool:
    """진행 키워드 안내와 길이 예산, 두 인터랙션 불변식을 만족하는가.

    마지막 큐는 '다음' 이 없어도 된다(더 넘어갈 데가 없다) — `test_stage_cues.py`
    가 `cues[:-1]` 로 마지막을 빼고 검사하는 것과 같은 예외다.
    """
    if len(text) > _MC_AFTER_MAX_CHARS:
        return False
    return is_last or "다음" in text


def merged_cue(cue: dict, research: dict | None) -> dict:
    if not research or not research.get("briefs"):
        return cue
    out = dict(cue)
    out["topic"] = research.get("topic", "")
    out["briefs"] = research["briefs"]
    for k in ("mc", "mc_after"):
        v = research.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def load_research() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(RESEARCH.glob("*.yaml")):
        if p.name.startswith("_"):      # 공유 파일(_law-basis 등)은 섹션이 아니다
            continue
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        out[d["id"]] = d
    return out


def merge_all(
    cues: list[dict], research: dict[str, dict]
) -> tuple[list[dict], list[str], list[str]]:
    """큐시트 전체에 조사 결과를 접는다.

    `merged_cue` 는 한 큐만 보고 판단하므로 "이게 마지막 큐인가"를 모른다 — 그
    판단은 전체 목록을 든 이 함수의 몫이다. 반환값은 (병합 결과, 건너뛴 id 목록,
    mc_after 를 옛 값으로 되돌린 id 목록).
    """
    merged: list[dict] = []
    skipped: list[str] = []
    reverted: list[str] = []
    last_i = len(cues) - 1
    for i, c in enumerate(cues):
        r = research.get(c["id"])
        if r is None or not r.get("briefs"):
            skipped.append(c["id"])
        out = merged_cue(c, r)
        if not _mc_after_is_safe(out.get("mc_after", ""), i == last_i):
            out["mc_after"] = c.get("mc_after", "")
            reverted.append(c["id"])
        merged.append(out)
    return merged, skipped, reverted


def main() -> None:
    research = load_research()
    cues = yaml.safe_load(CUES.read_text(encoding="utf-8"))
    merged, skipped, reverted = merge_all(cues, research)
    CUES.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"{len(merged) - len(skipped)}개 섹션에 브리프를 접었다.")
    if skipped:
        print(f"건너뜀({len(skipped)}): {', '.join(skipped)}")
    if reverted:
        print(
            f"mc_after 되돌림({len(reverted)}): {', '.join(reverted)} "
            "— 다음 안내 누락 또는 90자 초과"
        )


if __name__ == "__main__":
    main()
