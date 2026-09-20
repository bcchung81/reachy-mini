"""조사 산출물(`data/cues-research/*.yaml`)을 큐시트에 접는다.

**조사 파일이 원본이고 큐시트가 사본이다.** 옛 `docent_brief` 는 지우지 않는다 —
`briefs` 가 비는 섹션의 폴백이다.

## 되돌리지 않는다 — 접미사를 붙이거나 본문을 줄인다 (리뷰, 2026-09-20)

첫 구현은 `mc_after` 가 인터랙션 불변식(진행 키워드 '다음' 안내, 90자 예산)을
어기면 **옛 값으로 되돌렸다.** 그런데 실측해 보니 이 판단의 전제("`mc`/`mc_after`
에는 사실 오류가 없다")가 **틀렸다** — 조사 쪽 `mc_after` 는 옛 값의 사실 오류를
고친 버전이었다:

- `14-mobile`: "카폰이 아파트 한 채 값" → "자동차 한 대보다 비쌌다"
  (corrections[0] 이 `mc_after` 도 함께 고치라고 명시했다)
- `15-emf`: "거리를 조금만 두면 괜찮다" 라는 **출처 없는 건강 단정**을 삭제
  (전파법 제47조의2 제2항은 기준 초과 구역에 출입을 막는다 — "그래도 괜찮다"는
  그 조문과 정면으로 어긋난다. `19-closing` 의 corrections 는 이 삭제를 마무리에서
  되살리지 말라고까지 명시한다)
- `05-donor`: "의학박사" → "의사" (박사학위 미확인)
- `03-theory`: '퐁당퐁당' 물결 비유를 사회자가 그대로 되받던 문장을 중립화

되돌리면 이 정정들이 **조용히 사라진다.** 그래서 지금은:

1. '다음' 이 빠졌을 뿐이면 `_ADVANCE_SUFFIX` 를 붙인다(조사 본문은 24~55자라
   붙여도 대부분 90자 예산 안에 든다).
2. 접미사를 붙여도 넘치면(`15-emf`, 106자) **옛 값으로 되돌리지 않고** 조사
   본문을 사람이 줄인 대체본(`_SHORTENED_MC_AFTER`)을 쓴다 — 정정 내용(건강
   단정 삭제)을 포기할 수 없기 때문이다. 원문·대체본은 `main()` 출력과
   `task-9-report.md` 에 나란히 남긴다.
3. 그래도 고칠 방법이 없으면(예: 위치 지시어까지 섞인 경우) **소리 내서
   실패한다** — 조용히 아무거나 골라 쓰지 않는다.

## `briefs` 도 리뷰 B4(위치 지시어)·수준 프로필(문장 수)의 적용 대상이다

기존 가드(`tests/test_stage_cues.py`)는 `mc`/`mc_after`(고정 대사)만 봤다.
그런데 접힌 `briefs.*.docent_brief`/`mc_brief` 는 **LLM 지시문**이라 "여기서는"
같은 표현이 있으면 도슨트가 그대로 되읊을 위험이 있고, "2~3문장" 같은 수치가
있으면 `data/levels.yaml`(수준 프로필)과 진실 원천이 둘이 된다. 조사 파일은
읽기 전용이라 원본을 고칠 수 없다 — 접는 시점에 `_DEIXIS_FIXES`/
`_strip_sentence_count` 로 고치고, `_assert_briefs_clean` 으로 빠짐없이
잡혔는지 다시 확인한다(다음 조사 갱신에서 새 위치 지시어가 들어오면 이 확인이
소리 내서 실패한다 — 표에 없는 문구를 조용히 통과시키지 않는다).
"""

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "data" / "cues-research"
CUES = ROOT / "data" / "cues.yaml"

# `tests/test_stage_cues.py` 의 `_DEIXIS`/불변식과 반드시 같은 값을 쓴다 — 여기서
# 벌어지면 이 스크립트가 "안전하다"고 판단한 것과 실제 가드가 "위반"으로 보는
# 것이 달라져, 접은 결과가 테스트를 통과 못 하는 이번 사고가 다시 난다.
_DEIXIS = ("여기", "이곳", "저기", "이쪽", "저쪽")
_MC_MAX_CHARS = 130
_MC_AFTER_MAX_CHARS = 90


def _has_deixis(text: str) -> bool:
    return any(w in text for w in _DEIXIS)


def _mc_is_safe(text: str) -> bool:
    """`test_사회자_대사_길이가_예산_안이다`/`test_사회자_대사에_위치_지시어가_없다`."""
    return len(text) <= _MC_MAX_CHARS and not _has_deixis(text)


def _mc_after_is_safe(text: str, is_last: bool) -> bool:
    """진행 키워드 안내·길이 예산·위치 지시어, 세 인터랙션 불변식을 만족하는가.

    마지막 큐는 '다음' 이 없어도 된다(더 넘어갈 데가 없다) — `test_stage_cues.py`
    가 `cues[:-1]` 로 마지막을 빼고 검사하는 것과 같은 예외다.
    """
    if len(text) > _MC_AFTER_MAX_CHARS:
        return False
    if _has_deixis(text):
        return False
    return is_last or "다음" in text


# '다음' 안내가 빠졌을 때 붙이는 접미사. 조사 mc_after 는 24~55자(15-emf 제외)라
# 붙여도 대부분 90자 예산 안에 든다 — 옛 mc_after 가 이미 쓰던 표현 중 하나를
# 그대로 가져왔다(예: 04-morse 옛 값 "...없으면 '다음'이라고 말씀해 주세요.").
_ADVANCE_SUFFIX = " 이어가려면 '다음'이라고 해 주세요."

# 접미사를 붙여도 90자를 넘는 mc_after 는 되돌리지 않고 조사 본문을 줄여 채택한다.
# 원문(106자)은 "출처 없는 건강 단정 삭제"라는, 사실이 아니라 **법(전파법
# 제47조의2)과 어긋나는 문장을 지운** 정정이라 되돌릴 수 없다 — 줄인 본문도
# 그 정정(거리에 따라 세기가 줄어든다는 사실만 남기고 "괜찮다"는 단정은 없앤다)
# 을 그대로 지킨다. 원문·대체본은 `task-9-report.md` 에 나란히 적었다.
_SHORTENED_MC_AFTER: dict[str, str] = {
    "15-emf": (
        "세기가 발생원에서 멀어질수록 빠르게 줄어든다는 게 핵심이군요. "
        "궁금한 점 있으시면 말씀해 주시고, 아니면 '다음'이요."
    ),
}


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


def _fix_mc(cue_id: str, new_text: str, old_text: str) -> tuple[str, dict | None]:
    """`mc` 는 실측 결과 사실 정정을 나르지 않는다(18/19섹션이 옛 값과 완전히
    같았다) — 불변식을 어기면 되돌려도 잃을 정정이 없다. 그래도 조용히 넘어가지
    않고 로그를 남긴다."""
    if _mc_is_safe(new_text):
        return new_text, None
    return old_text, {"id": cue_id, "before": new_text, "after": old_text}


def _fix_mc_after(cue_id: str, text: str, is_last: bool) -> tuple[str, dict | None]:
    """되돌리지 않고 접미사를 붙이거나(1) 본문을 줄인 대체본을 쓴다(2).

    둘 다 안 되면(위치 지시어가 섞이는 등 표에 없는 사고) 소리 내서 실패한다 —
    사람이 `_SHORTENED_MC_AFTER` 에 대체본을 추가하거나 조사 파일을 다시 봐야 한다.
    """
    if _mc_after_is_safe(text, is_last):
        return text, None

    if not is_last and "다음" not in text and not _has_deixis(text):
        candidate = text + _ADVANCE_SUFFIX
        if _mc_after_is_safe(candidate, is_last):
            return candidate, {
                "id": cue_id, "action": "접미사_추가",
                "note": "조사 mc_after 에 '다음' 진행 키워드 안내가 없어 접미사를 붙였다"
                        "(정정 내용은 그대로 두었다)",
                "before": text, "after": candidate,
            }

    if cue_id in _SHORTENED_MC_AFTER:
        shortened = _SHORTENED_MC_AFTER[cue_id]
        assert _mc_after_is_safe(shortened, is_last), (
            f"{cue_id}: _SHORTENED_MC_AFTER 대체본 자체가 불변식을 못 만족한다 — "
            "대체본을 다시 써야 한다."
        )
        return shortened, {
            "id": cue_id, "action": "줄여서_채택",
            "note": "접미사를 붙여도 90자를 넘어 조사 본문을 줄였다(정정 내용은 유지)",
            "before": text, "after": shortened,
        }

    raise ValueError(
        f"{cue_id}: mc_after 가 인터랙션 불변식(다음 안내/90자/위치 지시어)을 "
        f"어기는데 고칠 방법이 없다 — _SHORTENED_MC_AFTER 에 수동 대체본을 "
        f"추가하거나 사람이 검토해야 한다. 조사 원문: {text!r}"
    )


# ── briefs 정화: 위치 지시어(리뷰 B4) · 문장 수 중복(수준 프로필과 충돌) ──────
#
# (id, 수준, 필드) -> (원문 조각, 고친 조각). 원문 조각이 그 자리에 없으면
# 조사 파일이 바뀌었다는 뜻이므로 조용히 넘어가지 않고 실패한다.
_DEIXIS_FIXES: dict[tuple[str, str, str], tuple[str, str]] = {
    ("01-intro", "초등", "mc_brief"): ("여기가 어떤 곳인지", "이 체험관이 어떤 곳인지"),
    ("01-intro", "초등", "docent_brief"): (
        "여기는 그 보이지 않는 전파를 보고 만질 수 있게 만든 곳",
        "전파체험관은 그 보이지 않는 전파를 보고 만질 수 있게 만든 곳",
    ),
    ("01-intro", "중고등", "docent_brief"): ("이곳을 만든 기관이", "체험관을 만든 기관이"),
    ("04-morse", "초등", "docent_brief"): (
        "그리고 그걸 여기서 직접 손으로 쳐볼 수 있다는 것.",
        "그리고 그걸 체험존에서 직접 손으로 쳐볼 수 있다는 것.",
    ),
    ("06-bands", "초등", "mc_brief"): ("여기 무엇이 놓여 있는지", "이 코너에 무엇이 놓여 있는지"),
    ("06-bands", "초등", "docent_brief"): ("여기 놓인 기계들은", "이 코너에 놓인 기계들은"),
    ("08-aviation", "초등", "docent_brief"): (
        "여기서는 진짜 조종석에 앉아",
        "항공무선통신 코너에서는 진짜 조종석에 앉아",
    ),
    ("09-special-exhibit", "초등", "mc_brief"): (
        "여기에는 가끔 바뀌는 특별한 전시가 있다",
        "특별교류전시에는 가끔 바뀌는 전시가 있다",
    ),
    ("11-iot", "일반", "docent_brief"): ("여기서 '사물' 은", "이 정의에서 '사물' 은"),
    ("12-multimedia", "초등", "mc_brief"): (
        "여기서는 방송 프로그램을 볼 수 있다",
        "멀티미디어실에서는 방송 프로그램을 볼 수 있다",
    ),
    ("12-multimedia", "초등", "docent_brief"): (
        "여기는 방송 프로그램을 직접 볼 수 있는 곳",
        "멀티미디어실은 방송 프로그램을 직접 볼 수 있는 곳",
    ),
    ("15-emf", "초등", "docent_brief"): (
        "나라가 '여기까지' 라는 선을 정해 두고 어른들이 그 선을 넘지 않는지",
        "나라가 정해 둔 선이 있고 어른들이 그 선을 넘지 않는지",
    ),
    ("16-inspection", "초등", "docent_brief"): (
        "여기 있는 장비들이 그 확인에 쓰던 것들",
        "전시된 장비들이 그 확인에 쓰던 것들",
    ),
    ("16-inspection", "일반", "docent_brief"): (
        "그때 쓰던 검사 장비들이 여기 전시돼 있다",
        "그때 쓰던 검사 장비들이 전시돼 있다",
    ),
    ("16-inspection", "전문가", "docent_brief"): (
        "앞서 본 해상·항공 무선국이 여기서 다시 만난다.",
        "앞서 본 해상·항공 무선국이 이 코너에서 다시 만난다.",
    ),
    ("17-rover", "초등", "mc_brief"): (
        "여기서 우주 자동차를 몰아볼 수 있다",
        "이 코너에서 우주 자동차를 몰아볼 수 있다",
    ),
}

# "2~3문장"/"5~7문장" 형태(그리고 옛 자리인 "N문장 이내")를 걷어낸다. 문장 수는
# `data/levels.yaml` 하나만의 몫이다 — 두 군데서 정하면 진실 원천이 둘이 되고
# 어긋나도 아무도 못 알아챈다(직전 커밋이 옛 자리에서 걷어낸 것과 같은 결함이
# `briefs` 라는 새 필드로 되돌아온 것).
_SENTENCE_COUNT_RE = re.compile(r"\s*\d+\s*(?:[~\-]\s*\d+\s*)?문장(?:\s*이내)?\.?")


def _strip_sentence_count(text: str) -> str:
    cleaned = _SENTENCE_COUNT_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _clean_briefs(cue_id: str, briefs: dict) -> tuple[dict, list[dict]]:
    out: dict = {}
    changes: list[dict] = []
    for level, b in briefs.items():
        nb = dict(b)
        for field in ("mc_brief", "docent_brief"):
            text = nb.get(field, "")
            if not isinstance(text, str):
                continue
            key = (cue_id, level, field)
            if key in _DEIXIS_FIXES:
                old, new = _DEIXIS_FIXES[key]
                if old not in text:
                    raise ValueError(
                        f"{cue_id}/{level}/{field}: 위치 지시어 고침표의 원문 조각을 "
                        f"못 찾았다 — 조사 파일이 바뀌었다. 찾던 조각: {old!r}"
                    )
                text = text.replace(old, new, 1)
                changes.append(
                    {"id": cue_id, "level": level, "field": field,
                     "kind": "위치_지시어", "before": old, "after": new}
                )
            stripped = _strip_sentence_count(text)
            if stripped != text:
                changes.append(
                    {"id": cue_id, "level": level, "field": field,
                     "kind": "문장_수_중복", "before": text, "after": stripped}
                )
                text = stripped
            nb[field] = text
        out[level] = nb
    return out, changes


def _assert_briefs_clean(cue_id: str, briefs: dict) -> None:
    """고침표를 다 적용한 뒤에도 위치 지시어가 남아 있으면 소리 내서 실패한다 —
    다음 조사 갱신에서 새 위치 지시어가 들어와도 이 확인이 잡는다."""
    for level, b in briefs.items():
        for field in ("mc_brief", "docent_brief"):
            text = b.get(field, "")
            if isinstance(text, str) and _has_deixis(text):
                raise ValueError(
                    f"{cue_id}/{level}/{field}: 위치 지시어가 남아 있다 — "
                    f"_DEIXIS_FIXES 에 항목을 추가해야 한다: {text!r}"
                )


def merge_all(cues: list[dict], research: dict[str, dict]) -> tuple[list[dict], dict]:
    """큐시트 전체에 조사 결과를 접는다.

    `merged_cue` 는 한 큐만 보고 판단하므로 "이게 마지막 큐인가"를 모른다 — 그
    판단(과 그에 딸린 안전장치)은 전체 목록을 든 이 함수의 몫이다. 반환값은
    (병합 결과, 무엇을 어떻게 고쳤는지 적은 로그).
    """
    merged: list[dict] = []
    log: dict = {
        "skipped": [],
        "mc_reverted": [],
        "mc_after_fixed": [],
        "briefs_changes": [],
    }
    last_i = len(cues) - 1
    for i, c in enumerate(cues):
        r = research.get(c["id"])
        if r is None or not r.get("briefs"):
            log["skipped"].append(c["id"])
        out = merged_cue(c, r)

        fixed_mc, mc_note = _fix_mc(c["id"], out.get("mc", ""), c.get("mc", ""))
        out["mc"] = fixed_mc
        if mc_note:
            log["mc_reverted"].append(mc_note)

        fixed_ma, ma_note = _fix_mc_after(c["id"], out.get("mc_after", ""), i == last_i)
        out["mc_after"] = fixed_ma
        if ma_note:
            log["mc_after_fixed"].append(ma_note)

        if out.get("briefs"):
            cleaned, changes = _clean_briefs(c["id"], out["briefs"])
            _assert_briefs_clean(c["id"], cleaned)
            out["briefs"] = cleaned
            log["briefs_changes"].extend(changes)

        merged.append(out)
    return merged, log


def main() -> None:
    research = load_research()
    cues = yaml.safe_load(CUES.read_text(encoding="utf-8"))
    merged, log = merge_all(cues, research)
    CUES.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )

    skipped = log["skipped"]
    print(f"{len(merged) - len(skipped)}개 섹션에 브리프를 접었다.")
    if skipped:
        print(f"건너뜀({len(skipped)}): {', '.join(skipped)}")

    if log["mc_reverted"]:
        print(f"\nmc 를 옛 값으로 되돌림({len(log['mc_reverted'])}) — 불변식 위반, 잃을 정정 없음:")
        for e in log["mc_reverted"]:
            print(f"  {e['id']}: 버린 조사 mc = {e['before']!r}")

    suffixed = [e for e in log["mc_after_fixed"] if e["action"] == "접미사_추가"]
    shortened = [e for e in log["mc_after_fixed"] if e["action"] == "줄여서_채택"]
    if suffixed:
        ids = ", ".join(e["id"] for e in suffixed)
        print(f"\nmc_after 에 '다음' 안내 접미사를 붙임({len(suffixed)}): {ids}")
    if shortened:
        print(f"\nmc_after 를 줄여서 채택({len(shortened)}) — 정정 내용은 유지:")
        for e in shortened:
            print(f"  {e['id']}: {e['note']}")
            print(f"    조사 원문({len(e['before'])}자): {e['before']!r}")
            print(f"    채택본({len(e['after'])}자): {e['after']!r}")

    changes = log["briefs_changes"]
    deixis_fixed = [c for c in changes if c["kind"] == "위치_지시어"]
    sc_stripped = [c for c in changes if c["kind"] == "문장_수_중복"]
    if deixis_fixed:
        print(f"\nbriefs 에서 위치 지시어를 고침({len(deixis_fixed)}건):")
        for c in deixis_fixed:
            print(f"  {c['id']}/{c['level']}/{c['field']}: {c['before']!r} -> {c['after']!r}")
    if sc_stripped:
        print(f"\nbriefs 에서 수준 프로필과 겹치는 문장 수 지정을 걷어냄({len(sc_stripped)}건):")
        for c in sc_stripped:
            print(f"  {c['id']}/{c['level']}/{c['field']}")


if __name__ == "__main__":
    main()
