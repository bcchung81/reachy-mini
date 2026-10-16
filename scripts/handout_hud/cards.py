"""발표형 교육자료 카드(`data/handout-cards/<큐>.yaml`) — 읽기·검증.

카드는 **검수한 고정 대본에서 줄여 쓴 것**이다. 새 사실을 들이지 않는다(교육자료에 환각이 섞이는 것이 가장 나쁘다 —
`stage/handout.py` 머리말과 같은 원칙). 그래서 사람이 쓴 카드도 아래 규칙으로 기계가 대조한다:

- 숫자·연도·영문 약어는 **그 수준이 허용하는 글**에 있어야 한다.
    초등·중고등: 그 수준에서 실제로 **말하는 대사**(사회자 여는 말·질문·받아치기·그 수준의 도슨트 답)만.
    일반: 위 + 그 수준의 브리프(검수한 사실 목록).  전문가: 위 + 조사 자료의 `facts`.
- 글 겹침(한글 3글자 조각이 허용 글에 있는 비율)이 문턱 이상이어야 한다 — 줄여 쓰되 지어내지는 않는다.
- 길이 한도(화면 가득 읽히는 크기 — `LIMITS`)와 포인트 수와의 일치.

스키마(큐마다 한 파일):
    id: 04-morse
    levels:
      초등|중고등|일반|전문가:
        headline: 한 줄 결론
        items: [{t: 제목, b: 본문}, ...]      # 포인트 수와 같다. i 번째 = i 번째 도슨트 설명
        remember: 기억해 두기
        visual: {type: keyfact, at: 0, facts: [{big: 1984년, label: 국내 첫 차량전화}]}
                {type: steps,   at: 1, title: 선택, steps: [{k: 1G, v: 차량전화}, ...]}
                {type: route|dial, ...}          # 02·03 장 전용(코드가 그린다)
        facts_used: [1, 3]                       # 전문가만, 선택 — 조사 자료 facts 번호(0부터). 근거 줄을 만든다
        source: 직접 적은 근거 줄(선택, facts_used 보다 앞선다)
"""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
LEVELS = ("초등", "중고등", "일반", "전문가")
LV_KEY = {"초등": "l1", "중고등": "l2", "일반": "l3", "전문가": "l4"}
CARDS_DIR = ROOT / "data" / "handout-cards"

# 화면 가득 읽히는 크기에서 정한 한도(1280×720 기준 카드 3장이 한 줄에 놓인다)
# item_b 는 1280×720 에서 4줄까지 들어간다(실측). 쓰는 쪽 목표는 70자 안쪽이다.
LIMITS = dict(headline=32, item_t=18, item_b=90, remember=46, big=10, label=30, step_k=9, step_v=22, vtitle=24)
# 글 겹침 문턱 — 02·03 장의 손으로 만든 카드를 재서 정했다(2026-10-06): 본문은 모두 50% 이상이었고, 제목·기억해 두기는 대본을
# 줄여 맺는 결론 문장이라 33~48% 였다. 본문이 더 엄하다.
MIN_COVERAGE = {"b": 0.5, "headline": 0.3, "remember": 0.3}
# 단위 약어는 영문 검사에서 뺀다(대본은 "킬로미터" 로 말하고 카드는 "km" 로 줄여 쓴다)
UNITS = frozenset({"km", "m", "cm", "mm", "hz", "khz", "mhz", "ghz", "thz", "kg", "g", "w", "mw", "db", "dbm", "bps", "kbps", "mbps", "gbps", "s", "ms", "kw", "v"})
VISUALS = ("keyfact", "steps", "route", "dial")


def _norm_num(s: str) -> str:
    return s.replace(",", "").rstrip(".")


def numbers(text: str) -> set[str]:
    return {_norm_num(m) for m in re.findall(r"\d[\d,]*\.?\d*", text)}


def latin(text: str) -> set[str]:
    return {m.lower() for m in re.findall(r"[A-Za-z][A-Za-z0-9\-]+|[A-Za-z]{2,}", text)}


def trigrams(text: str) -> set[str]:
    s = "".join(re.findall(r"[0-9A-Za-z가-힣]+", text.lower()))
    return {s[i : i + 3] for i in range(len(s) - 2)}


class Source:
    """한 큐의 대본·브리프·조사 자료를 수준별 허용 글로 묶는다."""

    def __init__(self, cue: dict, research: dict | None):
        self.cue = cue
        self.facts = (research or {}).get("facts") or []
        self.n_points = len(cue["points"])

    def spoken(self, lv: str) -> str:
        c = self.cue
        parts = [c["mc"], c["mc_after"]]
        for p in c["points"]:
            if p.get("ask"):
                parts.append(p["ask"])
            parts.append(p["answers"][lv])
        return " ".join(parts)

    def brief(self, lv: str) -> str:
        b = self.cue["briefs"][lv]
        return " ".join(str(b.get(k, "")) for k in ("mc_brief", "docent_brief"))

    def allowed(self, lv: str) -> str:
        text = self.spoken(lv)
        if lv in ("일반", "전문가"):
            text += " " + self.brief(lv)
        if lv == "전문가":
            text += " " + " ".join(f["claim"] for f in self.facts)
        return text

    def guard(self, lv: str) -> str:
        return str(self.cue["briefs"][lv].get("guard", ""))


def load_sources() -> dict[str, Source]:
    cues = yaml.safe_load((ROOT / "data" / "cues.yaml").read_text(encoding="utf-8"))
    out = {}
    for c in cues:
        rp = ROOT / "data" / "cues-research" / f"{c['id']}.yaml"
        research = yaml.safe_load(rp.read_text(encoding="utf-8")) if rp.exists() else None
        out[c["id"]] = Source(c, research)
    return out


def load_card_file(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def source_line(src: Source, lv_card: dict) -> str:
    """근거 줄. 직접 적은 `source` 가 있으면 그것, 아니면 `facts_used` 로 조사 자료의 출처 이름을 모은다."""
    if lv_card.get("source"):
        return lv_card["source"]
    used = lv_card.get("facts_used") or []
    if not used:
        return ""
    names, grades = [], []
    for i in used:
        f = src.facts[i]
        name = re.split(r"\s+https?://", f["source"])[0]
        name = re.sub(r"\s*\((원문[^)]*)\)\s*$", "", name).strip()
        if name not in names:
            names.append(name)
        grades.append(f.get("grade", "C"))
    worst = max(grades)           # A < B < C — 가장 약한 등급을 적는다
    return "근거 · " + " · ".join(names) + f" (신뢰 등급 {worst})"


def _check_text(errs, where, text, lim, allowed_nums, allowed_latin, allowed_tri, cover=None):
    if not isinstance(text, str) or not text.strip():
        errs.append(f"{where}: 비어 있다")
        return
    if len(text) > lim:
        errs.append(f"{where}: {len(text)}자 > 한도 {lim}자 — {text!r}")
    bad_n = sorted(n for n in numbers(text) if n not in allowed_nums)
    if bad_n:
        errs.append(f"{where}: 허용 글에 없는 숫자 {bad_n} — {text!r}")
    bad_l = sorted(w for w in latin(text) if w not in allowed_latin and w not in UNITS)
    if bad_l:
        errs.append(f"{where}: 허용 글에 없는 영문 {bad_l} — {text!r}")
    if cover:
        tg = trigrams(text)
        if len(tg) >= 6:
            ratio = len(tg & allowed_tri) / len(tg)
            if ratio < MIN_COVERAGE[cover]:
                errs.append(f"{where}: 대본과 겹침 {ratio:.0%} < {MIN_COVERAGE[cover]:.0%} — 대본에 없는 말을 지어냈을 수 있다: {text!r}")


def _check_source(where: str, line: str, src: Source) -> list[str]:
    """직접 적은 근거 줄도 조사 자료에 있는 출처여야 한다 — 없는 출처를 지어내면 근거 줄이 오히려 거짓말이 된다."""
    m = re.fullmatch(r"근거 · (.+) \(신뢰 등급 ([ABC])\)", line.strip())
    if not m:
        return [f"{where}.source: '근거 · 이름 · 이름 (신뢰 등급 A|B|C)' 모양이어야 한다 — {line!r}"]
    pool = _norm_src(" ".join(f["source"] for f in src.facts))
    errs = []
    for name in m.group(1).split(" · "):
        if _norm_src(name) not in pool:
            errs.append(f"{where}.source: 조사 자료 출처에 없는 이름 {name!r}")
    if src.facts and m.group(2) < min(f.get("grade", "C") for f in src.facts):
        errs.append(f"{where}.source: 등급 {m.group(2)} 가 조사 자료의 가장 높은 등급보다 좋다")
    return errs


def _norm_src(text: str) -> str:
    return re.sub(r"[\s·—\-–]+", "", text.lower().replace("’", "'"))


def validate(card: dict, src: Source, require_visual: bool = True) -> list[str]:
    errs: list[str] = []
    cid = src.cue["id"]
    if card.get("id") != cid:
        errs.append(f"id 가 {card.get('id')!r} — 파일은 {cid!r} 이어야 한다")
    levels = card.get("levels") or {}
    for lv in LEVELS:
        if lv not in levels:
            errs.append(f"{lv}: 수준이 빠졌다")
    extra = set(levels) - set(LEVELS)
    if extra:
        errs.append(f"모르는 수준: {sorted(extra)}")
    for lv in LEVELS:
        d = levels.get(lv)
        if not isinstance(d, dict):
            continue
        w = f"{cid}/{lv}"
        allowed = src.allowed(lv)
        nums, lat, tri = numbers(allowed), latin(allowed), trigrams(allowed)
        _check_text(errs, f"{w}.headline", d.get("headline"), LIMITS["headline"], nums, lat, tri, cover="headline")
        _check_text(errs, f"{w}.remember", d.get("remember"), LIMITS["remember"], nums, lat, tri, cover="remember")
        items = d.get("items")
        if not isinstance(items, list) or len(items) != src.n_points:
            errs.append(f"{w}.items: {src.n_points}개여야 한다(포인트 수) — 지금 {len(items) if isinstance(items, list) else items!r}")
        else:
            for i, it in enumerate(items):
                _check_text(errs, f"{w}.items[{i}].t", (it or {}).get("t"), LIMITS["item_t"], nums, lat, tri, cover=False)
                _check_text(errs, f"{w}.items[{i}].b", (it or {}).get("b"), LIMITS["item_b"], nums, lat, tri, cover="b")
        v = d.get("visual")
        if v is None:
            if require_visual:
                errs.append(f"{w}.visual: 없다")
        elif v.get("type") not in VISUALS:
            errs.append(f"{w}.visual.type: {v.get('type')!r} — {VISUALS} 중 하나")
        elif v["type"] == "keyfact":
            fs = v.get("facts")
            if not isinstance(fs, list) or not 1 <= len(fs) <= 3:
                errs.append(f"{w}.visual.facts: 1~3개여야 한다")
            else:
                for j, f in enumerate(fs):
                    _check_text(errs, f"{w}.visual.facts[{j}].big", f.get("big"), LIMITS["big"], nums, lat, tri, cover=False)
                    _check_text(errs, f"{w}.visual.facts[{j}].label", f.get("label"), LIMITS["label"], nums, lat, tri, cover=False)
        elif v["type"] == "steps":
            ss = v.get("steps")
            if not isinstance(ss, list) or not 3 <= len(ss) <= 5:
                errs.append(f"{w}.visual.steps: 3~5개여야 한다")
            else:
                for j, s in enumerate(ss):
                    _check_text(errs, f"{w}.visual.steps[{j}].k", s.get("k"), LIMITS["step_k"], nums, lat, tri, cover=False)
                    _check_text(errs, f"{w}.visual.steps[{j}].v", s.get("v"), LIMITS["step_v"], nums, lat, tri, cover=False)
            if v.get("title"):
                _check_text(errs, f"{w}.visual.title", v["title"], LIMITS["vtitle"], nums, lat, tri, cover=False)
        if v is not None and v.get("type") in ("keyfact", "steps"):
            at = v.get("at")
            if not isinstance(at, int) or not 0 <= at < src.n_points:
                errs.append(f"{w}.visual.at: 0~{src.n_points - 1} 의 정수 — 이 그림이 어느 포인트를 설명하는가")
        if d.get("source"):
            if lv != "전문가":
                errs.append(f"{w}.source: 전문가에만 쓴다")
            else:
                errs += _check_source(w, d["source"], src)
        fu = d.get("facts_used")
        if fu is not None:
            if lv != "전문가":
                errs.append(f"{w}.facts_used: 전문가에만 쓴다")
            elif not (isinstance(fu, list) and all(isinstance(i, int) and 0 <= i < len(src.facts) for i in fu)):
                errs.append(f"{w}.facts_used: 조사 자료 facts 번호(0~{len(src.facts) - 1}) 목록이어야 한다")
        if lv == "초등":
            for place, text in [("headline", d.get("headline")), ("remember", d.get("remember"))] + \
                    [(f"items[{i}]", (it or {}).get("t", "") + " " + (it or {}).get("b", "")) for i, it in enumerate(items or [])]:
                if isinstance(text, str) and re.search(r"\d", text) and not (numbers(text) <= numbers(src.spoken(lv))):
                    errs.append(f"{w}.{place}: 초등은 말하지 않은 숫자를 쓰지 않는다 — {text!r}")
    return errs


def check_files(paths) -> int:
    sources = load_sources()
    bad = 0
    for p in paths:
        p = pathlib.Path(p)
        card = load_card_file(p)
        cid = (card or {}).get("id", p.stem)
        if cid not in sources:
            print(f"{p}: 모르는 큐 id {cid!r}")
            bad += 1
            continue
        errs = validate(card, sources[cid])
        if errs:
            bad += 1
            print(f"✗ {p.name}: {len(errs)}건")
            for e in errs:
                print("   -", e)
        else:
            print(f"✓ {p.name}")
    return bad


if __name__ == "__main__":
    targets = sys.argv[1:] or sorted(CARDS_DIR.glob("*.yaml"))
    sys.exit(1 if check_files(targets) else 0)
