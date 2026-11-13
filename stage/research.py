"""큐별 조사 자료(`data/cues-research/<큐>.yaml`)를 관람객 질문 답의 근거로 — 2026-11-13.

왜: 질문 답이 "단답형" 이었다(사용자). 분량을 2~3문장으로 묶어 둔 이유는 근거가 브리프 한두 문단뿐이라 분량을 채우라면
지어낼 압력이 생겨서였다(`data/levels.yaml` 머리말). 조사 자료에는 큐마다 **출처·등급이 붙은 사실**과 **바로잡은 것**(흔히
틀리는 말), **확인 안 된 것**(단정하면 안 되는 말)이 있다 — 브리프를 만든 원재료다. 이것을 같이 실으면 분량을 늘려도 근거
안에서 말할 거리가 생긴다.

싣는 것:
- 사실은 등급 A·B 만(C 는 근거가 약하다 — 답에 쓰면 단정이 된다). 주장 문장만 — **출처 문자열은 싣지 않는다**: 파일 경로
  (`docs/exhibit-guide.md:55`)·URL 이 섞여 있어 모델이 그대로 읽으면 TTS 로 샌다. 기관·조항 이름은 주장 안에 이미 있다.
- 바로잡은 것·확인 안 된 것은 그대로(금지 규칙 쪽이다 — 지키라고 싣는다).
글자 상한(`MAX_CHARS`)을 넘으면 사실을 앞에서부터 남기고 자른다(조사 파일은 중요한 사실을 앞에 둔다). 자료가 없거나 깨졌으면
None — 답은 지금처럼 브리프만으로 돈다(감독이 경고한다).
"""

from __future__ import annotations

import functools
import os
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESEARCH_DIR = ROOT / "data" / "cues-research"
GRADES = ("A", "B")
# 큐 하나 몫의 상한(글자). 가장 큰 큐(15-emf)가 사실 2.8천·바로잡기 1천·확인 불가 0.5천자다 — 두 큐(지금 + 질문이 더 가까운
# 큐)를 실어도 프롬프트가 수천 토큰 안이다(첫 글자 지연에 거의 안 보인다, 2026-11-13 실측으로 확인).
MAX_CHARS = 5000


def research_dir() -> pathlib.Path:
    override = os.environ.get("REACHY_RESEARCH_DIR")
    return pathlib.Path(override) if override else RESEARCH_DIR


def _clean(text: str) -> str:
    """서식 걷기 — `**`·백틱은 모델이 흉내 내 TTS 로 샌다(`stage/prompts.py` 머리말과 같은 이유). 줄바꿈은 한 칸으로."""
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


@functools.lru_cache(maxsize=64)
def _load(path: str, mtime: float) -> dict | None:
    try:
        data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


def research_brief(cue_id: str, max_chars: int = MAX_CHARS) -> str | None:
    """조사 자료를 근거 문단으로. 없거나 실을 것이 없으면 None."""
    path = research_dir() / f"{cue_id}.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    data = _load(str(path), mtime)
    if data is None:
        return None
    facts = [_clean(str(f.get("claim", ""))) for f in data.get("facts") or []
             if isinstance(f, dict) and f.get("grade") in GRADES and f.get("claim")]
    corrections = [_clean(str(c)) for c in data.get("corrections") or [] if c]
    unknown = [_clean(str(c)) for c in data.get("unverifiable") or [] if c]
    tail = []
    if corrections:
        tail.append("바로잡은 것(이렇게 말하면 틀린다):")
        tail += [f"- {c}" for c in corrections]
    if unknown:
        tail.append("확인되지 않은 것(단정하지 않는다):")
        tail += [f"- {c}" for c in unknown]
    if not facts and not tail:
        return None
    # 금지 쪽(바로잡기·확인 불가)은 다 싣고, 남은 자리만큼 사실을 앞에서부터 — 자를 때도 지키라는 말은 빠지지 않게.
    room = max_chars - sum(len(t) + 1 for t in tail)
    head: list[str] = []
    if facts:
        head.append("검증된 사실:")
        for f in facts:
            line = f"- {f}"
            if sum(len(t) + 1 for t in head) + len(line) + 1 > room:
                break
            head.append(line)
        if len(head) == 1:
            head = []
    return "\n".join(head + tail) or None
