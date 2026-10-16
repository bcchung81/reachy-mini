"""발표형 교육자료 HTML 만들기 — `data/handout-cards/*.yaml`(카드) + `data/cues.yaml`(대사) + 이 틀 → 한 장짜리 HTML.

    .venv/bin/python -m scripts.handout_hud.build            # docs/design/handout-hud.html
    .venv/bin/python -m scripts.handout_hud.build --out 경로

카드가 검증기(`cards.py`)를 하나라도 못 넘으면 **만들지 않고 멈춘다** — 대본에 없는 말이 교육자료에 섞이는 것을
막는 마지막 관문이다. 결과물은 외부 리소스 없는 단일 HTML 이다(전시장은 오프라인).
"""
import argparse
import base64
import json
import pathlib
import sys

import yaml

from scripts.handout_hud import cards as C

HERE = pathlib.Path(__file__).resolve().parent
ROOT = C.ROOT
DEFAULT_OUT = ROOT / "docs" / "design" / "handout-hud.html"

# 02·03 장은 코드가 그리는 그림(경로·다이얼)과 그림에 맞춘 움직임이 있다
SPECIAL = {
    "02-history": dict(
        turns=dict(headline="open docent0", visual="docent2"),
        actions={"docent2": [dict(type="pulse")]},
    ),
    "03-theory": dict(
        turns=dict(headline="open", visual="docent1 docent2"),
        actions={"docent1": [dict(type="dial", **{"from": 3, "to": 12.3})], "docent2": [dict(type="dial", to=8, ms=2400)]},
    ),
}


def courses(cue_ids: list[str]) -> list[dict]:
    raw = yaml.safe_load((ROOT / "data" / "courses.yaml").read_text(encoding="utf-8"))["courses"]
    out = []
    for c in raw:
        ids = cue_ids if c["cues"] == "all" else list(c["cues"])
        unknown = [i for i in ids if i not in cue_ids]
        if unknown:
            raise SystemExit(f"코스 {c['name']!r} 에 큐시트에 없는 id: {unknown}")
        out.append(dict(name=c["name"], ids=ids))
    return out


def _visual(v: dict) -> dict:
    v = dict(v)
    if v["type"] == "route":
        return dict(type="route", label=v["label"], **{"from": v["from"], "to": v["to"]})
    return v


def build_data() -> dict:
    sources = C.load_sources()
    cue_ids = list(sources)
    cues, problems = [], []
    for cid, src in sources.items():
        path = C.CARDS_DIR / f"{cid}.yaml"
        if not path.exists():
            problems.append(f"{cid}: 카드 파일이 없다 ({path})")
            continue
        card = C.load_card_file(path)
        errs = C.validate(card, src)
        if errs:
            problems += [f"{cid}: {e}" for e in errs]
            continue
        c = src.cue
        lv = {}
        for name in C.LEVELS:
            d = card["levels"][name]
            lv[C.LV_KEY[name]] = dict(
                headline=d["headline"], items=d["items"], remember=d["remember"],
                source=C.source_line(src, d), visual=_visual(d["visual"]),
                ask=[p.get("ask") for p in c["points"]],
                ans=[p["answers"][name] for p in c["points"]],
            )
        cue = dict(id=cid, no=cid.split("-")[0], title=c["title"], n=len(c["points"]),
                   open=c["mc"], after=c["mc_after"], lv=lv)
        cue.update(SPECIAL.get(cid, {}))
        cues.append(cue)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(f"카드 {len(problems)}건이 검증을 못 넘었다 — 교육자료를 만들지 않는다")
    return dict(levels=[dict(key=C.LV_KEY[n], name=n) for n in C.LEVELS], cues=cues, courses=courses(cue_ids))


def render(data: dict) -> str:
    icon = "data:image/png;base64," + base64.b64encode((HERE / "reachy-mini-icon.png").read_bytes()).decode("ascii")
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("__ICON__", icon).replace("__DATA__", payload)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    html = render(build_data())
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} — {len(html):,} bytes")


if __name__ == "__main__":
    main()
