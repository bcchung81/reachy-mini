"""여는 대사 사전 생성. 시연 전에 돌리고 결과를 **사람이 읽어본다.**

    .venv/bin/python scripts/pregen_mc_lines.py            # 전 수준
    .venv/bin/python scripts/pregen_mc_lines.py 초등 일반   # 고른 수준만

**LLM 서버가 떠 있어야 실제로 돈다** — `build_generate` 가 `stage/__main__.py`
와 똑같은 클라이언트를 만들어 진짜로 추론 서버에 왕복한다. 그래서 이 스크립트
자체는 자동 테스트에서 돌리지 않는다(`tests/test_pregen.py` 는 캐시 키·폴백·
스킵 로직만 `build_generate` 를 가짜로 바꿔 단위로 본다).
"""

import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from stage.cues import load_cues
from stage.levels import LEVEL_NAMES, load_levels
from stage.mc_cache import cache_key, cache_path, load_mc_lines
from stage.__main__ import build_generate


def main() -> None:
    wanted = sys.argv[1:] or list(LEVEL_NAMES)
    levels = load_levels()
    cues = load_cues()
    out = load_mc_lines()
    for name in wanted:
        gen = build_generate(levels[name])
        for cue in cues:
            mc_brief, _ = cue.brief_for(name)
            if not mc_brief:
                print(f"  건너뜀 {cue.id}/{name} — mc_brief 가 없다", flush=True)
                continue
            key = cache_key(cue.id, name, mc_brief)
            if key in out:
                continue
            text = gen("mc", mc_brief, [])
            out[key] = text
            print(f"  {cue.id}/{name}: {text}", flush=True)
    cache_path().write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )
    print(f"\n{len(out)}개를 {cache_path()} 에 썼다. **읽어보고 고친다.**")


if __name__ == "__main__":
    main()
