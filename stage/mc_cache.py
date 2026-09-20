"""여는 대사 사전 생성 캐시.

**왜 미리 만드나.** 지연이 0 인 것도 이유지만 더 큰 이유는 **사람이 시연 전에
19섹션 × 4수준 = 76개를 읽어볼 수 있다**는 것이다. 런타임 생성은 그 기회가 없다.
"""

import hashlib
import pathlib

import yaml


def cache_key(cue_id: str, level: str, mc_brief: str) -> str:
    """지시문 해시를 키에 넣는다 — 큐시트를 고치면 낡은 항목이 드러난다."""
    h = hashlib.sha256(mc_brief.encode("utf-8")).hexdigest()[:12]
    return f"{cue_id}|{level}|{h}"


def cache_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "mc_lines.yaml"


def load_mc_lines(path: pathlib.Path | None = None) -> dict[str, str]:
    p = pathlib.Path(path) if path is not None else cache_path()
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}
