"""여는 대사 사전 생성 캐시.

**왜 미리 만드나.** 지연이 0 인 것도 이유지만 더 큰 이유는 **사람이 시연 전에
19섹션 × 4수준 = 76개를 읽어볼 수 있다**는 것이다. 런타임 생성은 그 기회가 없다.
"""

import hashlib
import os
import pathlib

import yaml


class McCacheError(ValueError):
    """여는 대사 캐시 파일이 규약에 맞지 않는다."""


def cache_key(cue_id: str, level: str, mc_brief: str) -> str:
    """지시문 해시를 키에 넣는다 — 큐시트를 고치면 낡은 항목이 드러난다."""
    h = hashlib.sha256(mc_brief.encode("utf-8")).hexdigest()[:12]
    return f"{cue_id}|{level}|{h}"


def cache_path() -> pathlib.Path:
    """캐시 경로. `REACHY_MC_LINES_PATH` 가 있으면 그것을 쓴다.

    형제 로더(`stage/cues.py::cues_path`, `stage/levels.py::levels_path`)는
    둘 다 환경변수 오버라이드가 있는데 이 파일만 하드코딩이면, 실기에서
    캐시 파일 위치를 옮기려 할 때 코드를 고쳐야 한다 — "주소는 전부
    환경변수다" 규약 위반이다.
    """
    override = os.environ.get("REACHY_MC_LINES_PATH")
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parent.parent / "data" / "mc_lines.yaml"


def load_mc_lines(path: pathlib.Path | None = None) -> dict[str, str]:
    """캐시를 읽는다. **이 파일은 사람이 손으로 고치는 것이 존재 이유다** —
    그래서 값이 문자열인지 반드시 검사한다.

    `키: 3` 이나 `키: true` 로 손이 미끄러지면 `bool`/`int` 값이 그대로
    `Director._begin_cue` 의 `mc_text` 가 되어 `machine.speak()` 까지 흘러가고,
    `Director._estimate` 의 `len(text)` 에서야 `TypeError` 로 터진다 —
    `stage/cues.py` 가 이미 겪은 것과 같은 함정이다(리뷰 A8a: "그 값이
    `_estimate` 의 len() 에서 터져 감독이 데드라인 없이 굳는다"). `bool` 은
    `int` 의 하위형이라 `isinstance(v, str)` 없이 truthy 만 보면 못 거른다.

    최상위가 매핑이 아닌 경우(리스트 등)도 조용히 `{}` 로 넘기지 않는다 —
    "실패는 소리 내서 실패한다" 위반이다. 다만 **파일이 없거나 비어 있는
    것**은 "아직 아무것도 생성 안 했다"는 정상 상태이므로 에러가 아니라
    빈 딕셔너리로 본다.
    """
    p = pathlib.Path(path) if path is not None else cache_path()
    if not p.exists():
        return {}
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise McCacheError(f"여는 대사 캐시가 YAML 이 아니다: {p} — {exc}") from exc
    if raw is None:
        return {}   # 빈 파일 — 파일이 없는 것과 같게 본다.
    if not isinstance(raw, dict):
        raise McCacheError(
            f"여는 대사 캐시는 매핑이어야 한다: {p} (지금은 {type(raw).__name__})"
        )
    for key, value in raw.items():
        if not isinstance(value, str):
            raise McCacheError(
                f"{p} {key!r} 의 값이 문자열이 아니다 — 지금은 "
                f"{type(value).__name__}({value!r})"
            )
    return raw
