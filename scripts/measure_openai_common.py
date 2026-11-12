"""OpenAI LLM·STT 실측 도구가 같이 쓰는 것 — 키 읽기, 산출물 폴더, 가격표, 통계.

계획 `docs/superpowers/plans/2026-11-12-openai-measure.md`. 측정 도구라 제품 경로에서 import 하지 않는다.

**키는 출력하지 않는다.** `tts_elevenlabs.load_api_key` 와 같은 방식으로 `.env` 의 그 한 줄만 파싱한다 — 파일을
셸에 `source` 하면 다른 키(ElevenLabs)까지 이 프로세스 환경으로 새고, 하위 프로세스(로컬 서버)로 흘러간다.
"""

from __future__ import annotations

import json
import os
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENAI_KEY_ENV = "OPENAI_API_KEY"
OPENAI_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com").rstrip("/")

# 측정 산출물(음성·원시 결과·나란히 표)은 **저장소 밖**에 둔다 — 공개용으로 정리 중인 저장소다.
OUT = pathlib.Path(os.environ.get("REACHY_MEASURE_OUT")
                   or pathlib.Path.home() / ".local/share/reachy-mini-measure/2026-11-12")

# 표준 요금(100만 토큰당 USD: 입력, 캐시 입력, 출력). 출처 developers.openai.com/api/docs/pricing (2026-11-12 읽음).
# 요금이 바뀌면 여기만 고친다 — 보고서의 비용은 이 표 × 응답의 usage 로 계산한다.
LLM_PRICE = {
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6-astra": (10.00, 1.00, 50.00),
}
# STT 분당 USD(같은 페이지). gpt-transcribe 는 토큰 요금이 없고 분당만 있다.
STT_PRICE_PER_MIN = {"gpt-transcribe": 0.0045}


def load_openai_key(env: dict | None = None, env_file: pathlib.Path | None = None) -> str | None:
    """환경변수 → `.env` 의 `OPENAI_API_KEY=` 한 줄. 없으면 None. 값은 어디에도 찍지 않는다."""
    env = os.environ if env is None else env
    v = (env.get(OPENAI_KEY_ENV) or "").strip()
    if v:
        return v
    path = env_file or ROOT / ".env"
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        s = line.strip()
        if s.startswith("export "):
            s = s[len("export "):].lstrip()
        if not s.startswith(OPENAI_KEY_ENV + "="):
            continue
        val = s[len(OPENAI_KEY_ENV) + 1:].strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        return val or None
    return None


def llm_cost(model: str, usage: dict | None) -> float:
    """응답 usage 로 계산한 요금. 캐시 적중 토큰은 캐시 요금으로 — 반복 시스템 프롬프트가 싸지는 몫이 여기서 보인다."""
    if not usage or model not in LLM_PRICE:
        return 0.0
    p_in, p_cache, p_out = LLM_PRICE[model]
    prompt = int(usage.get("prompt_tokens") or 0)
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    out = int(usage.get("completion_tokens") or 0)
    return ((prompt - cached) * p_in + cached * p_cache + out * p_out) / 1e6


def pct(xs: list[float], q: float) -> float | None:
    """백분위(선형 보간). 비면 None."""
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summary(xs: list[float]) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "median": statistics.median(xs), "p90": pct(xs, 0.9),
            "min": min(xs), "max": max(xs), "mean": statistics.fmean(xs)}


def fmt_s(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
