"""여는 대사 사전 생성. 시연 전에 돌리고 결과를 **사람이 읽어본다.**

    .venv/bin/python scripts/pregen_mc_lines.py            # 전 수준
    .venv/bin/python scripts/pregen_mc_lines.py 초등 일반   # 고른 수준만

**LLM 서버가 떠 있어야 실제로 돈다** — `build_generate` 가 `stage/__main__.py`
와 똑같은 클라이언트를 만들어 진짜로 추론 서버에 왕복한다. 그래서 이 스크립트
자체는 자동 테스트에서 돌리지 않는다(`tests/test_pregen.py` 는 캐시 키·폴백·
스킵·파일 보존 로직만 `build_generate` 를 가짜로 바꿔 단위로 본다).

**새 항목은 건별로 파일에 이어 붙인다 — 통째로 재작성하지 않는다.** 두 가지
이유다. ① 76회(19섹션 × 4수준) LLM 왕복 중 하나만 실패해도 그 전에 만든
것까지 통째로 사라지면 사전 생성의 의미가 없다. ② `yaml.safe_dump(전체, ...)`
로 매번 다시 쓰면 사람이 파일에 남긴 주석·순서가 실행마다 사라진다 —
"사람이 읽고 고친다"는 이 파일의 존재 이유와 정면으로 충돌한다. 기존 줄은
한 글자도 안 건드리고, 새로 만든 항목만 뒤에 이어 붙인다.
"""

import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from stage.cues import load_cues
from stage.levels import LEVEL_NAMES, load_levels
from stage.mc_cache import cache_key, cache_path, load_mc_lines
from stage.prompts import build_bridge_prompt
from stage.__main__ import build_generate


def _valid_keys(cues) -> set[str]:
    """지금 큐시트가 가질 수 있는 모든 (수준 무관) 키 — 고아 판정 기준이다.

    `wanted`(이번 실행이 고른 수준)가 아니라 **전체 수준**을 본다 — 안 그러면
    "이번엔 초등만 돌렸다" 는 이유만으로 다른 수준의 멀쩡한 키가 고아로
    잘못 잡힌다.

    다리 대사 키(`cache_key(cue.id, name, ask)`)도 포함한다 — 안 그러면
    이 스크립트가 방금 생성해 둔 다리 대사가 **다음 실행에서 고아로 오판**돼
    "지워도 되는지 확인한다" 는 경고가 뜬다. 사람이 그 경고를 믿고 지우면
    `Director` 가 그 키를 못 찾아 질문 원문을 그대로 읽는 폴백이 조용히
    되살아난다 — 이 스크립트를 시연 전에 돌리는 이유 자체가 그 폴백을 막는
    것이므로, 여기서 틀리면 존재 이유가 뒤집힌다.
    """
    keys = set()
    for cue in cues:
        for name in LEVEL_NAMES:
            mc_brief, _ = cue.brief_for(name)
            if mc_brief:
                keys.add(cache_key(cue.id, name, mc_brief))
            for point in cue.points_for(name):
                if point.ask:
                    keys.add(cache_key(cue.id, name, point.ask))
    return keys


def _append_entry(path: pathlib.Path, key: str, text: str) -> None:
    """항목 하나만 파일 끝에 이어 붙인다. 기존 줄(사람이 남긴 주석 포함)은
    절대 다시 쓰지 않는다 — `open(..., "a")` 라 파일이 없으면 새로 만든다.

    **붙이기 전에 끝 개행을 보장한다.** 이 파일은 사람이 손으로 고치는 것이
    존재 이유인데(`stage/mc_cache.py::load_mc_lines`), 편집기에 따라 마지막 줄
    뒤의 개행이 사라진 채로 저장된다. 그 뒤에 그냥 append 하면
    `…: 옛 대사c1|일반|abc: 새 대사` 라는 **한 줄**이 만들어져 YAML 이 깨지고,
    다음 기동이 `McCacheError` 로 죽거나(전부 잃는다) 두 항목이 한 값으로
    뭉친다 — "건별로 즉시 써서 하나도 잃지 않는다" 는 이 함수의 목적이
    통째로 뒤집히는 자리다(`tests/test_pregen.py::
    test_이어_붙이기가_끝_개행이_없어도_YAML_을_깨지_않는다`).

    빈 파일·없는 파일에는 붙이지 않는다 — 맨 앞 빈 줄은 사람이 읽기 나쁘다.
    """
    needs_nl = path.exists() and path.stat().st_size > 0 and not path.read_text(
        encoding="utf-8"
    ).endswith("\n")
    with path.open("a", encoding="utf-8") as f:
        if needs_nl:
            f.write("\n")
        f.write(yaml.safe_dump({key: text}, allow_unicode=True, sort_keys=True))


def main() -> None:
    wanted = sys.argv[1:] or list(LEVEL_NAMES)
    levels = load_levels()
    cues = load_cues()
    out = load_mc_lines()
    before = len(out)
    orphans = [k for k in out if k not in _valid_keys(cues)]
    p = cache_path()

    try:
        for name in wanted:
            gen = build_generate(levels[name])
            for cue in cues:
                mc_brief, _ = cue.brief_for(name)
                if not mc_brief:
                    print(f"  건너뜀 {cue.id}/{name} — mc_brief 가 없다", flush=True)
                else:
                    key = cache_key(cue.id, name, mc_brief)
                    if key not in out:
                        text = gen("mc", mc_brief, [])
                        out[key] = text
                        # **여기서 바로 쓴다.** 다음 반복에서 다른 왕복이 실패해도
                        # 이 항목은 이미 파일에 남아 있다.
                        _append_entry(p, key, text)
                        print(f"  {cue.id}/{name}: {text}", flush=True)
                    # key in out 이어도 여기서 아래 포인트 루프로 그냥
                    # 흘러간다 — `continue` 로 건너뛰지 않는다. (리뷰
                    # Critical 대응: 예전엔 `if key in out: continue` 가
                    # 오프닝 대사 캐시 히트일 때 이 아래 포인트 루프까지
                    # 통째로 건너뛰었다. `mc_brief` 는 이미 캐시됐는데
                    # `points` 만 나중에 추가/수정되는 게 실제 반복 패턴이라
                    # — 그 경우 다리 대사 키가 영영 안 생기고, 스크립트는
                    # "캐시가 최신 상태다" 라고 거짓 보고하며, `Director` 는
                    # 원문 포인트 텍스트를 그대로 낭독하는 폴백으로 조용히
                    # 빠진다. 시연 담당자에게 경고 한 줄 없이.)

                # 턴 왕복의 다리 대사(사회자 질문)도 같은 캐시·같은 키 형식으로
                # 미리 만든다. 오프닝 대사(`key`)의 캐시 히트/미스와 **무관하게**
                # 독립적으로 돈다 — 각 턴은 자기 자신의 `pkey in out` 으로만
                # 스킵을 판단한다(위 주석 참고).
                #
                # 0턴은 건너뛴다 — 오프닝이 묻는다. 사전 생성은 이력이 없으므로
                # 사회자가 반응할 **앞 턴의 그 수준 설명**을 지시문에 넣는다.
                points = cue.points_for(name)
                for point_i, point in enumerate(points):
                    if not point.ask:
                        continue
                    pkey = cache_key(cue.id, name, point.ask)
                    if pkey in out:
                        continue
                    prev_answer = points[point_i - 1].answer
                    ptext = gen("mc", build_bridge_prompt(point.ask, prev_answer), [])
                    out[pkey] = ptext
                    _append_entry(p, pkey, ptext)
                    print(f"  {cue.id}/{name}/pt{point_i} 다리대사: {ptext}", flush=True)
    finally:
        # 도중에 예외가 나도 여기까지는 반드시 실행된다 — 시연 담당자가
        # "몇 개까지 만들고 어디서 죽었는지" 를 알아야 다음 실행에서 재개할
        # 수 있다(스킵 로직이 이미 만든 것은 다시 안 부른다).
        새로 = len(out) - before
        if 새로:
            print(f"\n{새로}개를 새로 만들어 {p} 에 이어 붙였다(총 {len(out)}개). "
                  "**읽어보고 고친다.**")
        else:
            print(f"\n새로 만들 것이 없다(총 {len(out)}개, {p}) — 캐시가 최신 상태다.")
        if orphans:
            # 지우지는 않는다 — 사람이 지금 큐시트와 대조해서 지울지 정한다.
            print(f"고아 {len(orphans)}개 — 지금 큐시트에 없는 키다({p}). "
                  "지워도 되는지 확인한다.")


if __name__ == "__main__":
    main()
