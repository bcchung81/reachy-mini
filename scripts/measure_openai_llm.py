"""관람객 질문 답 LLM 실측 — 로컬 Gemma vs OpenAI(`gpt-6-luna` 등), 앱이 실제로 쓰는 경로 그대로.

계획 `docs/superpowers/plans/2026-11-12-openai-measure.md`, 결과 `docs/research/2026-11-12-openai-llm-stt-measure.md`.

**앱 경로를 그대로 태운다**(docs/lessons.md 「측정·예열 도구는 앱이 실제로 쓰는 경로를 태운다」):
- 지시문(brief)은 실제 큐시트로 띄운 `Director._answer()` 가 만든 것을 생성 콜백에서 가로챈다 — 여기서 다시 짜면
  근거·금지 규칙·참고 사실(초등·중고등)이 앱과 갈라진다.
- 생성은 `stage.__main__.build_generate(level)` 그 자체를 부른다 → 시스템 프롬프트(`build_system_prompt`)·이력 변환
  (`history_for`)·요청 본문(`LLMClient.chat_stream`: temperature 0.7, max_tokens = level.max_tokens, stream)·후처리
  (이름표 → 분량 상한 → 글 표기 → 글말 경고)가 전부 앱의 코드다.
- **바꾸는 것은 `llm._session` 하나** — 게이트웨이 자리를 이 도구 안에서 흉내 낸다(`Gateway`): 주소를 측정 대상으로
  돌리고, OpenAI 면 키·모델 이름·`reasoning_effort` 를 넣는다. 그래서 이 클래스가 하는 번역이 곧 B2 게이트웨이가
  해야 할 번역의 목록이다. 시간(첫 글자·끝)과 토큰 사용량도 여기서 잰다.

사용:
    .venv/bin/python scripts/measure_openai_llm.py --dry-run            # 호출 없이 질문 수·예상 비용
    .venv/bin/python scripts/measure_openai_llm.py --preflight          # OpenAI 가 로봇 본문을 받는지(1회씩)
    .venv/bin/python scripts/measure_openai_llm.py --run main           # 4수준 × 질문 × (로컬, luna)
    .venv/bin/python scripts/measure_openai_llm.py --run expert         # 전문가 질문 × 상위 후보
    .venv/bin/python scripts/measure_openai_llm.py --report             # 표·나란히 HTML
로컬 서버는 `--local-url`(기본 http://127.0.0.1:18080 — 시연 포트 8080 을 피한다).
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import random
import re
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import stage.__main__ as stage_main  # noqa: E402  (앱 경로 삽입 + llm import 까지 여기서 된다)
import llm as llm_mod  # noqa: E402  (stage_main 이 넣은 경로의 그 모듈 — 같은 객체다)
from scripts.handout_hud.cards import latin, numbers  # noqa: E402  교육자료 검증기와 같은 숫자·영문 판정
from scripts.measure_openai_common import (  # noqa: E402
    LLM_PRICE, OPENAI_BASE, OUT, fmt_s, llm_cost, load_openai_key, read_jsonl, summary, write_jsonl,
)
from stage.cues import CueSheet, load_cues  # noqa: E402
from stage.director import Director  # noqa: E402
from stage.levels import LEVEL_NAMES, load_levels  # noqa: E402
from stage.speech_text import split_sentences  # noqa: E402

LLM_OUT = OUT / "llm"

# ── 질문 ──────────────────────────────────────────────────────────────
# 로그(`.demo-logs/*.log`)의 사용자 발화 70여 줄은 모두 개발자 시험 발화였다("대본", "너는 누구야?" …) — 전시 질문 0개.
# 그래서 질문은 만들었다. 출처 표지: `테스트예시` = tests/test_stage_retrieval.py 에 개발자가 "관람객이 할 법한" 으로 적은 것,
# `합성` = 이 측정을 위해 큐시트 주제로 만든 것. **둘 다 실제 관람객 말이 아니다.** 각 질문은 (그 섹션이 진행 중일 때) 들어온
# 것으로 둔다 — 앞 섹션을 되묻는 질문은 일부러 다른 섹션에 둔다(검색 테스트와 같은 배치).
# 함정 표시(trap): 브리프가 "말하지 말라" 고 한 것을 건드리는 질문 — 지어내기·금지 위반을 보려고 넣었다.
QUESTIONS: list[dict] = [
    {"id": "q01", "cue": "01-intro", "q": "이 체험관은 언제 생겼어요?", "src": "테스트예시"},
    {"id": "q02", "cue": "01-intro", "q": "여기는 누가 만든 곳이에요?", "src": "합성"},
    {"id": "q03", "cue": "07-maritime", "q": "아까 마르코니가 누구라고 했죠?", "src": "테스트예시"},
    {"id": "q04", "cue": "02-history", "q": "전파는 누가 발명했어요?", "src": "합성", "trap": "발명이 아니라 발견"},
    {"id": "q05", "cue": "02-history", "q": "마르코니는 대서양 건너로 어떻게 신호를 보냈어요?", "src": "합성", "trap": "'캐나다' 금지"},
    {"id": "q06", "cue": "03-theory", "q": "주파수가 높으면 파장은 어떻게 돼요?", "src": "테스트예시"},
    {"id": "q07", "cue": "03-theory", "q": "전파는 우주에서도 가요?", "src": "합성"},
    {"id": "q08", "cue": "03-theory", "q": "헤르츠가 뭐예요?", "src": "테스트예시"},
    {"id": "q09", "cue": "08-aviation", "q": "모스 부호는 누가 만들었어요?", "src": "테스트예시"},
    {"id": "q10", "cue": "04-morse", "q": "SOS는 무슨 뜻이에요?", "src": "합성"},
    {"id": "q11", "cue": "05-donor", "q": "장황남 박사님은 왜 통신 장비를 모았어요?", "src": "합성"},
    {"id": "q12", "cue": "06-bands", "q": "주파수 대역은 몇 개로 나뉘어요?", "src": "합성", "trap": "'10개 대역' 금지"},
    {"id": "q13", "cue": "06-bands", "q": "파장이 길면 왜 멀리 가요?", "src": "합성"},
    {"id": "q14", "cue": "15-emf", "q": "타이타닉은 왜 가라앉았어요?", "src": "테스트예시"},
    {"id": "q15", "cue": "07-maritime", "q": "타이타닉에서 몇 명이 살았어요?", "src": "합성", "trap": "초등 수치 금지"},
    {"id": "q16", "cue": "07-maritime", "q": "SOS는 언제부터 썼어요?", "src": "테스트예시"},
    {"id": "q17", "cue": "08-aviation", "q": "비행기는 왜 무전기를 두 개씩 달아요?", "src": "합성"},
    {"id": "q18", "cue": "10-ham", "q": "아마추어 무선은 아무나 할 수 있어요?", "src": "합성"},
    {"id": "q19", "cue": "11-iot", "q": "5G가 되면 자율주행차가 되는 거예요?", "src": "합성", "trap": "5G→자율주행 인과 금지"},
    {"id": "q20", "cue": "11-iot", "q": "사물인터넷이 뭐예요?", "src": "합성"},
    {"id": "q21", "cue": "13-chromakey", "q": "크로마키는 왜 초록색이에요?", "src": "합성", "trap": "근거 밖"},
    {"id": "q22", "cue": "14-mobile", "q": "1세대 이동통신은 언제예요?", "src": "테스트예시"},
    {"id": "q23", "cue": "14-mobile", "q": "5G는 우리나라가 처음 만든 거예요?", "src": "합성", "trap": "'스마트폰 기반 세계 최초 상용화'"},
    {"id": "q24", "cue": "15-emf", "q": "전자파는 몸에 해로워요?", "src": "테스트예시"},
    {"id": "q25", "cue": "15-emf", "q": "휴대폰을 머리맡에 두고 자도 괜찮아요?", "src": "합성", "trap": "근거 밖 건강 조언"},
    {"id": "q26", "cue": "18-science", "q": "무선국 검사는 누가 해요?", "src": "테스트예시"},
    {"id": "q27", "cue": "17-rover", "q": "화성 로버는 왜 조이스틱으로 못 움직여요?", "src": "합성"},
    {"id": "q28", "cue": "03-theory", "q": "테레민은 어떻게 소리가 나요?", "src": "테스트예시"},
    {"id": "q29", "cue": "09-special-exhibit", "q": "이 전시는 언제까지 해요?", "src": "합성", "trap": "확인 안 된 정보 — 모른다가 정답"},
    {"id": "q30", "cue": "12-multimedia", "q": "여기서 영화도 만들어요?", "src": "합성", "trap": "작품명 금지"},
    {"id": "q31", "cue": "17-rover", "q": "달에 있는 차는 누가 운전했어요?", "src": "합성", "trap": "루노호트(원격) vs 아폴로(직접)"},
    {"id": "q32", "cue": "19-closing", "q": "로봇은 어떻게 제 말을 알아들어요?", "src": "합성", "trap": "전시 밖 — 자기 소개"},
]

# ── 측정 대상 ─────────────────────────────────────────────────────────
# reasoning_effort: 모델 페이지 기준(2026-11-12). none 이 되는 것은 luna·6-sol·6.1-terra 뿐. 6.1-sol 은 최저 low.
# `min_out`: 사고 토큰이 출력 상한(max_completion_tokens)을 함께 먹는다 — low 면 level.max_tokens(전문가 424)로는 사고만
# 하다 답이 잘린다. 게이트웨이가 상한을 이만큼 올려야 한다는 근거를 재려고 둔다(실측 사고 토큰을 기록한다).
TARGETS = {
    "local": {"kind": "local", "model": "local"},
    "gpt-6-luna": {"kind": "openai", "model": "gpt-6-luna", "effort": "none"},
    "gpt-6.1-terra": {"kind": "openai", "model": "gpt-6.1-terra", "effort": "none"},
    "gpt-6.1-sol": {"kind": "openai", "model": "gpt-6.1-sol", "effort": "low", "min_out": 4000},
    # 지연 흔들림 시험(같은 시간대에 나란히): 표준 재측정 · Fast 모드(요금 2배, `service_tier:"fast"` — 옛 이름 priority 도 받는다)
    # · 매번 새 연결(게이트웨이가 오래 쉬어 연결이 끊긴 뒤의 첫 질문 — TLS 핸드셰이크가 첫 글자에 얹힌다).
    "luna-std2": {"kind": "openai", "model": "gpt-6-luna", "effort": "none"},
    "luna-fast": {"kind": "openai", "model": "gpt-6-luna", "effort": "none", "extra": {"service_tier": "fast"}, "price_x": 2.0},
    "luna-cold": {"kind": "openai", "model": "gpt-6-luna", "effort": "none", "fresh_session": True},
}
RUNS = {
    "main": {"levels": LEVEL_NAMES, "targets": ("local", "gpt-6-luna")},
    "expert": {"levels": ("전문가",), "targets": ("gpt-6.1-terra", "gpt-6.1-sol")},
    "jitter": {"levels": ("일반",), "targets": ("luna-std2", "luna-fast", "luna-cold")},
}


class _Stream:
    """`requests.Response` 대신 `LLMClient` 에 돌려주는 것 — 줄을 그대로 흘리며 시간·사용량만 기록한다.

    OpenAI 는 `stream_options.include_usage` 를 켜면 마지막에 `choices: []` 인 사용량 청크를 보낸다. `LLMClient` 는
    `["choices"][0]` 을 바로 읽으므로 그 청크를 그대로 넘기면 IndexError 로 생성 전체가 실패한다 — **게이트웨이가 켠다면
    걸러서 넘겨야 한다**(여기서 거른다).
    """

    def __init__(self, resp: requests.Response, rec: dict) -> None:
        self._r = resp
        self._rec = rec

    def raise_for_status(self) -> None:
        self._r.raise_for_status()

    def iter_lines(self):
        rec = self._rec
        parts: list[str] = []
        for raw in self._r.iter_lines():
            if raw and raw.startswith(b"data: "):
                data = raw[len(b"data: "):]
                if data != b"[DONE]":
                    try:
                        d = json.loads(data.decode("utf-8"))
                    except ValueError:
                        d = {}
                    if d.get("usage"):
                        rec["usage"] = d["usage"]
                    choices = d.get("choices") or []
                    if not choices:
                        continue                       # 사용량 청크 — LLMClient 에 넘기지 않는다
                    delta = (choices[0].get("delta") or {}).get("content") or ""
                    if delta:
                        if "ttft" not in rec:
                            rec["ttft"] = time.perf_counter() - rec["t0"]
                        parts.append(delta)
                    fr = choices[0].get("finish_reason")
                    if fr:
                        rec["finish_reason"] = fr
                else:
                    rec["total"] = time.perf_counter() - rec["t0"]
            yield raw
        rec.setdefault("total", time.perf_counter() - rec["t0"])
        rec["raw"] = "".join(parts)


class Gateway:
    """`llm._session` 자리에 끼우는 가짜 게이트웨이. **이 클래스의 번역 목록 = B2 게이트웨이가 할 일.**

    - 주소: 로봇은 `REACHY_LLM_URL/v1/chat/completions` 를 부른다 → 측정 대상 주소로 돌린다.
    - OpenAI: `Authorization`, `model`(로봇은 "local" 을 보낸다), `reasoning_effort`(안 보내면 기본 medium — 사고한다).
    - `rename_max_tokens`: OpenAI 가 `max_tokens` 를 거절하면 `max_completion_tokens` 로 바꾼다(--preflight 가 정한다).
    - `drop_temperature`: 거절하면 뺀다(같은 방식).
    """

    def __init__(self, name: str, local_url: str, key: str | None, compat: dict | None = None) -> None:
        t = TARGETS[name]
        self.name = name
        self.t = t
        self.key = key
        self.local_url = local_url.rstrip("/")
        self.compat = compat or {}
        self.s = requests.Session()     # keep-alive — 게이트웨이도 연결을 재사용할 것이다
        self.last: dict = {}

    def body_for(self, body: dict) -> dict:
        b = dict(body)
        t = self.t
        if t["kind"] == "openai":
            b["model"] = t["model"]
            b["reasoning_effort"] = t["effort"]
            b["stream_options"] = {"include_usage": True}
            if t.get("min_out") and "max_tokens" in b:
                b["max_tokens"] = max(int(b["max_tokens"]), int(t["min_out"]))
            if self.compat.get("rename_max_tokens") and "max_tokens" in b:
                b["max_completion_tokens"] = b.pop("max_tokens")
            if self.compat.get("drop_temperature"):
                b.pop("temperature", None)
            b.update(t.get("extra") or {})
        return b

    def post(self, url, json=None, stream=False, timeout=None, **_kw):
        b = self.body_for(json or {})
        if self.t["kind"] == "openai":
            target = f"{OPENAI_BASE}/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.key}"}
        else:
            target = f"{self.local_url}/v1/chat/completions"
            headers = {}
        if self.t.get("fresh_session"):
            self.s.close()
            self.s = requests.Session()
        rec = {"t0": time.perf_counter(), "sent_keys": sorted(b), "max_out": b.get("max_tokens") or b.get("max_completion_tokens")}
        self.last = rec
        # timeout 은 로봇의 것(LLMClient 10초) 그대로 — 게이트웨이를 거쳐도 로봇이 기다리는 한도는 이것이다.
        r = self.s.post(target, json=b, headers=headers, stream=True, timeout=timeout)
        rec["status"] = r.status_code
        if r.status_code >= 400:
            rec["error"] = r.text[:600]
        return _Stream(r, rec)


# ── 감독이 만드는 지시문 ──────────────────────────────────────────────
def cue_history(cue, level_name: str) -> list[str]:
    """질문 창이 열릴 때까지 그 큐에서 오간 고정 대사 — 감독이 `_remember` 로 쌓는 모양("사회자: …"/"도슨트: …").

    실제 공연에서는 앞 큐들의 대사도 `HISTORY_MAX`(12줄)까지 남는다. 여기서는 그 큐 것만 쌓는다(근사) — 근거 밖 숫자
    검사가 "이력에 있던 숫자" 를 근거로 쳐 주므로, 이력이 실제보다 짧으면 그 검사는 조금 엄해진다.
    """
    lines = [f"사회자: {cue.mc}"]
    for pt in cue.points_for(level_name):
        if pt.ask:
            lines.append(f"사회자: {pt.ask}")
        lines.append(f"도슨트: {pt.answer}")
    if cue.mc_after:
        lines.append(f"사회자: {cue.mc_after}")
    return lines


def director_brief(cues, levels, level_name: str, cue_id: str, question: str) -> tuple[str, list[dict], list[str]]:
    """실제 `Director._answer()` 가 생성에 넘기는 (지시문, 이력, 감독 경고). 생성 콜백에서 가로챈다."""
    got: dict = {}
    ev = threading.Event()
    warns: list[str] = []

    def capture(role, brief, history):
        got.update(role=role, brief=brief, history=history)
        ev.set()
        return "측정용 자리표시"          # 감독이 이 답을 쓸 일은 없다(바로 버린다)

    sheet = CueSheet(cues)
    d = Director(
        sheet, generate=capture, send=lambda role, cmd: None, warn=warns.append,
        level_name=level_name, docent_min_chars=levels[level_name].min_chars,
        level_min_chars={n: lv.min_chars for n, lv in levels.items()},
        on_level_change=lambda n: None,
    )
    i = sheet.find(cue_id)
    if i is None:
        raise SystemExit(f"큐시트에 없는 섹션: {cue_id}")
    sheet.seek(i)
    for line in cue_history(sheet.current(), level_name):
        d._remember(line)
    with d._lock:
        d._answer(question)
    if not ev.wait(5):
        raise SystemExit(f"감독이 생성을 부르지 않았다: {cue_id} {question!r}")
    assert got["role"] == "docent", got["role"]
    return got["brief"], got["history"], warns


# ── 규칙 검사 ─────────────────────────────────────────────────────────
_YEAR = re.compile(r"(\d{4})\s*년")
_HANGUL_NUM = re.compile(r"(?<![가-힣])(?:[이삼사오육칠팔구]?[십백천만억])+\s?(?:년|명|개|킬로미터|미터|헤르츠|분|초|퍼센트)")
_DECLINE = re.compile(r"모르|확인되지 않|확인된 .{0,6}없|알 수 없|정확히 .{0,6}없|말씀드리기 어렵")


def checks(level, text: str, raw: str, brief: str, history: list[dict], question: str, warns: list[str]) -> dict:
    """앱이 내는 경고 + 수준 규칙. **판정은 저장소에 이미 있는 함수로** — 새 규칙을 여기서 지어내지 않는다.

    - 분량 상한·이름표·글 표기·글말: `build_generate` 가 낸 경고 그대로(같은 함수가 판정한다).
    - 하한: 감독 `_warn_if_short` 와 같은 기준(len < level.min_chars).
    - 초등 숫자: 교육자료 검증기(`scripts/handout_hud/cards.py`)의 초등 규칙과 같은 `\\d` 판정. 초등 영문: 같은 파일의 `latin`.
    - 중고등: levels.yaml "연도만 말한다" → 'NNNN년' 이 아닌 숫자.
    - 근거 밖 숫자: 답의 숫자 ⊄ (지시문 + 이력 + 질문)의 숫자 — 지어낸 수치 **의심**(사람이 확인한다).
    """
    w = " | ".join(warns)
    ctx = brief + " " + " ".join(h["content"] for h in history) + " " + question
    nums = numbers(text)
    out = {
        "capped": "분량 상한" in w,
        "labels": "이름표" in w,
        "symbols": "글 표기를 말로" in w,
        "written": "글말 어미" in w,
        "short": len(text) < level.min_chars,
        "empty": not text.strip(),
        "sentences": len(split_sentences(text)),
        "ungrounded_nums": ungrounded(text, ctx),
        "declined": bool(_DECLINE.search(text)),
    }
    out.update(level_flags(level.name, text, question))
    return out


_CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(20)}     # ①…⑳ — 브리프는 "제66조④" 로, 답은 "제4항" 으로 쓴다


def _num_set(s: str) -> set[str]:
    """숫자 집합 — 표기 차이를 맞춘다: 원문자(④→4), 앞자리 0("2012-06" 의 06 → 6). 첫 실행에서 근거 밖 숫자 2건이 둘 다
    이 표기 차이였다(사람이 브리프와 대조해 확인)."""
    for a, b in _CIRCLED.items():
        s = s.replace(a, f" {b} ")
    return {n.lstrip("0") or "0" for n in numbers(s)}


def ungrounded(text: str, ctx: str) -> list[str]:
    return sorted(_num_set(text) - _num_set(ctx))


def level_flags(level_name: str, text: str, question: str) -> dict:
    """수준 숫자 규칙. **관람객이 질문에서 말한 숫자는 빼고 센다** — "5G" "1세대" 를 물었는데 답이 그 이름을 되받는
    것은 모델이 수치를 꺼낸 것이 아니다(첫 실행에서 초등 위반 4건 중 3건이 이것이었다). 빼기 전 판정(`*_raw`)도 남긴다.
    보고(`report`)가 저장된 답으로 다시 계산하므로 판정을 고쳐도 다시 잴 필요가 없다.
    """
    out: dict = {}
    nums = numbers(text)
    echo = numbers(question)
    if level_name == "초등":
        out["kid_digits_raw"] = bool(re.search(r"\d", text))
        out["kid_digits"] = sorted(nums - echo)
        out["kid_hangul_num"] = _HANGUL_NUM.findall(text)
        out["kid_latin"] = sorted(latin(text) - latin(question))
    if level_name == "중고등":
        years = {m for m in _YEAR.findall(text)}
        out["teen_nonyear_nums"] = sorted(n for n in nums - echo if n not in years)
    out["level_violation"] = bool(
        out.get("kid_digits") or out.get("kid_hangul_num") or out.get("teen_nonyear_nums")
    )
    return out


# ── 실행 ──────────────────────────────────────────────────────────────
def est_tokens(s: str) -> int:
    """어림 — 한글 1자 ≈ 1토큰, 그 밖 4자 ≈ 1토큰. 비용 상한을 보수적으로 잡으려는 값이지 정확한 수가 아니다."""
    ko = sum(1 for c in s if "가" <= c <= "힣")
    return ko + (len(s) - ko) // 4 + 1


def plan_items(cues, levels, run: str, limit: int | None):
    qs = QUESTIONS[:limit] if limit else QUESTIONS
    for lv in RUNS[run]["levels"]:
        for q in qs:
            brief, hist, dwarn = director_brief(cues, levels, lv, q["cue"], q["q"])
            yield lv, q, brief, hist, dwarn


def dry_run(cues, levels, runs: list[str], limit: int | None) -> None:
    from stage.prompts import build_system_prompt
    total = 0.0
    for run in runs:
        n = 0
        cost: dict[str, float] = {}
        for lv, q, brief, hist, _ in plan_items(cues, levels, run, limit):
            sys_p = build_system_prompt("docent", levels[lv])
            p_tok = est_tokens(sys_p + brief + "".join(h["content"] for h in hist))
            for name in RUNS[run]["targets"]:
                t = TARGETS[name]
                if t["kind"] != "openai":
                    continue
                out_tok = max(levels[lv].max_tokens, t.get("min_out", 0))
                p_in, _, p_out = LLM_PRICE[t["model"]]
                cost[name] = cost.get(name, 0.0) + (p_tok * p_in + out_tok * p_out) / 1e6
            n += 1
        print(f"[{run}] 질문×수준 {n}건 · 대상 {', '.join(RUNS[run]['targets'])}")
        for name, c in cost.items():
            print(f"   {name}: 예상 상한 ${c:.3f} (캐시 할인·실제 출력 길이 미반영 — 실제는 이보다 적다)")
        total += sum(cost.values())
    print(f"OpenAI 예상 상한 합계 ${total:.3f}")


def preflight(key: str, local_url: str) -> dict:
    """OpenAI 가 **로봇 본문 그대로**(max_tokens·temperature) + reasoning_effort 를 받는지 모델마다 한 번씩. 결과는 파일로."""
    results = {}
    body = {"model": "local", "messages": [{"role": "system", "content": "짧게 답한다."},
                                            {"role": "user", "content": "전파가 뭐예요?"}],
            "stream": True, "temperature": 0.7, "max_tokens": 40}
    for name, t in TARGETS.items():
        if t["kind"] != "openai":
            continue
        tried = []
        for compat in ({}, {"rename_max_tokens": True}, {"rename_max_tokens": True, "drop_temperature": True}):
            g = Gateway(name, local_url, key, compat)
            st = g.post("x", json=body, timeout=60)
            text = ""
            if g.last.get("status") == 200:
                for _ in st.iter_lines():
                    pass
                text = g.last.get("raw", "")
            tried.append({"compat": compat, "status": g.last.get("status"), "error": g.last.get("error"),
                          "sample": text[:60], "usage": g.last.get("usage")})
            print(f"{name} {compat or '로봇 본문 그대로'} → {g.last.get('status')} "
                  f"{(g.last.get('error') or text)[:160]!r}")
            if g.last.get("status") == 200:
                break
        results[name] = {"tried": tried, "compat": tried[-1]["compat"] if tried[-1]["status"] == 200 else None}
    LLM_OUT.mkdir(parents=True, exist_ok=True)
    (LLM_OUT / "preflight.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def run(cues, levels, run_name: str, key: str | None, local_url: str, limit: int | None, warm: bool) -> None:
    pf_path = LLM_OUT / "preflight.json"
    pf = json.loads(pf_path.read_text(encoding="utf-8")) if pf_path.exists() else {}
    targets = RUNS[run_name]["targets"]
    gws = {}
    for name in targets:
        if TARGETS[name]["kind"] == "openai":
            if not key:
                raise SystemExit("OPENAI_API_KEY 가 없다(.env) — OpenAI 대상은 잴 수 없다")
            compat = (pf.get(name) or pf.get(TARGETS[name]["model"]) or {}).get("compat")
            if compat is None:
                raise SystemExit(f"{name}: --preflight 를 먼저 돌린다(본문 호환성을 모른다)")
            gws[name] = Gateway(name, local_url, key, compat)
        else:
            gws[name] = Gateway(name, local_url, None)
    out_path = LLM_OUT / f"results-{run_name}.jsonl"
    rows = read_jsonl(out_path)
    done = {(r["level"], r["qid"], r["model"]) for r in rows if r.get("ok")}
    rows = [r for r in rows if r.get("ok")]            # 실패한 줄은 다시 잰다
    rng = random.Random(20261112)

    for lv_name in RUNS[run_name]["levels"]:
        level = levels[lv_name]
        warns: list[str] = []
        gen = stage_main.build_generate(level, warn=warns.append)
        items = [it for it in plan_items(cues, levels, run_name, limit) if it[0] == lv_name]
        if warm:
            # 예열 — 통계에서 뺀다. 로컬은 슬롯 3개(llamactl 기본 parallel 3)를 다 채우게 세 번(scripts/warmup.py 와 같은 이유).
            _, q0, b0, h0, _ = items[0]
            for name in targets:
                llm_mod._session = gws[name]
                for _ in range(3 if TARGETS[name]["kind"] == "local" else 1):
                    try:
                        gen("docent", b0, list(h0))
                    except Exception as exc:  # 예열 실패는 본 측정에서 다시 드러난다
                        print(f"   예열 실패 {name}: {type(exc).__name__}: {exc}")
        for lv, q, brief, hist, dwarn in items:
            order = list(targets)
            rng.shuffle(order)                         # 순서 효과(서버 열기·캐시)를 섞는다
            for name in order:
                if (lv, q["id"], name) in done:
                    continue
                gw = gws[name]
                llm_mod._session = gw
                warns.clear()
                err = None
                text = ""
                t_wall = time.perf_counter()
                try:
                    text = gen("docent", brief, list(hist))
                except Exception as exc:              # 감독이라면 큐시트 폴백으로 간다 — 실패로 센다
                    err = f"{type(exc).__name__}: {exc}"[:400]
                wall = time.perf_counter() - t_wall
                rec = gw.last
                raw = rec.get("raw", "")
                row = {
                    "run": run_name, "level": lv, "qid": q["id"], "cue": q["cue"], "question": q["q"],
                    "src": q["src"], "trap": q.get("trap", ""), "model": name,
                    "ok": err is None and rec.get("status") == 200,
                    "error": err or rec.get("error"), "status": rec.get("status"),
                    "ttft": rec.get("ttft"), "total": rec.get("total"), "wall": wall,
                    "finish_reason": rec.get("finish_reason"), "max_out": rec.get("max_out"),
                    "usage": rec.get("usage"),
                    "cost": llm_cost(TARGETS[name].get("model", ""), rec.get("usage")) * TARGETS[name].get("price_x", 1.0),
                    "raw": raw, "text": text, "warns": list(warns), "director_warns": dwarn,
                    "brief": brief,
                }
                row["checks"] = checks(level, text, raw, brief, hist, q["q"], warns) if row["ok"] else {}
                rows.append(row)
                write_jsonl(out_path, rows)            # 줄마다 저장 — 중간에 끊겨도 이어 잰다
                c = row["checks"]
                print(f"{lv} {q['id']} {name:14s} ttft={fmt_s(row['ttft'])} total={fmt_s(row['total'])} "
                      f"{len(text):3d}자 {'위반' if c.get('level_violation') else ''}"
                      f"{' 상한' if c.get('capped') else ''}{' 짧음' if c.get('short') else ''}"
                      f"{' 오류 ' + str(row['error'])[:80] if not row['ok'] else ''}")


# ── 보고 ──────────────────────────────────────────────────────────────
def _rate(rows, key) -> str:
    n = len(rows)
    k = sum(1 for r in rows if r["checks"].get(key))
    return f"{k}/{n}" if n else "—"


def report() -> str:
    rows = [r for f in sorted(LLM_OUT.glob("results-*.jsonl")) for r in read_jsonl(f)]
    cues = {c.id: c for c in load_cues()}
    for r in rows:                                     # 수준 규칙·근거 밖 숫자는 저장된 답으로 다시 판정한다(판정을 고쳐도 같은 답)
        if r.get("ok"):
            r["checks"].update(level_flags(r["level"], r["text"], r["question"]))
            ctx = " ".join([r["brief"], *cue_history(cues[r["cue"]], r["level"]), r["question"]])
            r["checks"]["ungrounded_nums"] = ungrounded(r["text"], ctx)
    out: list[str] = []
    models = list(dict.fromkeys(r["model"] for r in rows))
    # q01 은 수준마다 예열에 쓴 바로 그 지시문이라 캐시가 통째로 맞는다(로컬 첫 글자 0.03초) — 지연 통계에서 뺀다
    out.append("### 지연(초) — 한국 PC, 스트리밍, 예열 뒤(예열에 쓴 q01 은 뺐다)\n")
    out.append("| 모델 | 수준 | n | 실패 | 첫 글자 중앙 | 첫 글자 p90 | 첫 글자 최대 | 끝 중앙 | 끝 p90 |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for m in models:
        for lv in LEVEL_NAMES + ("전체",):
            rs = [r for r in rows if r["model"] == m and (lv == "전체" or r["level"] == lv) and r["qid"] != "q01"]
            if not rs:
                continue
            ok = [r for r in rs if r["ok"]]
            a, b = summary([r["ttft"] for r in ok]), summary([r["total"] for r in ok])
            out.append(f"| {m} | {lv} | {len(rs)} | {len(rs) - len(ok)} | {fmt_s(a.get('median'))} | {fmt_s(a.get('p90'))} | "
                       f"{fmt_s(a.get('max'))} | {fmt_s(b.get('median'))} | {fmt_s(b.get('p90'))} |")
    out.append("\n### 규칙 — 앱 경고·수준 규칙(건수/표본)\n")
    out.append("| 모델 | 수준 | 상한 잘림 | 하한 미달 | 글말 | 기호 | 이름표 | 수준 규칙 위반 | 근거 밖 숫자 | 모른다 | 답 길이 중앙(자) |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for m in models:
        for lv in LEVEL_NAMES:
            rs = [r for r in rows if r["model"] == m and r["level"] == lv and r["ok"]]
            if not rs:
                continue
            ung = sum(1 for r in rs if r["checks"].get("ungrounded_nums"))
            med = summary([len(r["text"]) for r in rs]).get("median")
            out.append(f"| {m} | {lv} | {_rate(rs, 'capped')} | {_rate(rs, 'short')} | {_rate(rs, 'written')} | "
                       f"{_rate(rs, 'symbols')} | {_rate(rs, 'labels')} | {_rate(rs, 'level_violation')} | {ung}/{len(rs)} | "
                       f"{_rate(rs, 'declined')} | {med:.0f} |")
    out.append("\n### 비용(실제 usage × 표준 요금)\n")
    out.append("| 모델 | 호출 | 입력 토큰 중앙 | 캐시 적중 비율 | 출력 토큰 중앙 | 사고 토큰 중앙 | 합계 $ | 호출당 $ |")
    out.append("|---|---|---|---|---|---|---|---|")
    for m in models:
        rs = [r for r in rows if r["model"] == m and r["ok"] and r.get("usage")]
        if not rs:
            continue
        pt = [r["usage"].get("prompt_tokens", 0) for r in rs]
        ct = [r["usage"].get("completion_tokens", 0) for r in rs]
        cached = sum((r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0) for r in rs)
        rt = [(r["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0) for r in rs]
        tot = sum(r["cost"] for r in rs)
        out.append(f"| {m} | {len(rs)} | {summary(pt)['median']:.0f} | {cached / max(1, sum(pt)):.0%} | "
                   f"{summary(ct)['median']:.0f} | {summary(rt)['median']:.0f} | {tot:.4f} | {tot / len(rs):.5f} |")
    out.append("\n### 수준 규칙 위반·근거 밖 숫자 — 낱낱이\n")
    for r in rows:
        c = r.get("checks") or {}
        bad = []
        if c.get("kid_digits"):
            bad.append(f"초등 숫자 {c['kid_digits']}")
        if c.get("kid_latin"):
            bad.append(f"초등 영문 {c['kid_latin']}")
        if c.get("kid_hangul_num"):
            bad.append(f"초등 한글 수사 {c['kid_hangul_num']}")
        if c.get("teen_nonyear_nums"):
            bad.append(f"중고등 연도 아닌 수 {c['teen_nonyear_nums']}")
        if c.get("ungrounded_nums"):
            bad.append(f"근거 밖 숫자 {c['ungrounded_nums']}")
        if bad:
            out.append(f"- {r['model']} · {r['level']} · {r['qid']} {r['question']} — {'; '.join(bad)} — 「{r['text']}」")
    text = "\n".join(out)
    (LLM_OUT / "summary.md").write_text(text, encoding="utf-8")
    write_side_by_side(rows)
    return text


def write_side_by_side(rows) -> None:
    """사람이 볼 나란히 표 — **모델 이름을 가린다**(줄마다 A/B 순서를 섞고, 접힌 칸을 열어야 보인다)."""
    by = {}
    for r in rows:
        by.setdefault((r["level"], r["qid"]), []).append(r)
    rng = random.Random(7)
    parts = []
    for lv in LEVEL_NAMES:
        parts.append(f"<h2>{lv}</h2>")
        for (l2, qid), rs in sorted(by.items()):
            if l2 != lv:
                continue
            rs = [r for r in rs if r["ok"]]
            rng.shuffle(rs)
            q = rs[0] if rs else None
            if not q:
                continue
            cells = []
            for i, r in enumerate(rs):
                c = r["checks"]
                flags = [k for k in ("capped", "short", "written", "symbols", "labels", "level_violation") if c.get(k)]
                if c.get("ungrounded_nums"):
                    flags.append("근거밖숫자 " + ",".join(c["ungrounded_nums"]))
                cells.append(
                    # 첫 글자 시간은 접힌 칸에만 — 로컬은 0.5초대라 겉에 두면 블라인드가 깨진다
                    f"<div class=ans><b>{'ABCDE'[i]}</b> <span class=len>{len(r['text'])}자</span>"
                    f"<p>{html.escape(r['text'])}</p><details><summary>모델·표지</summary>{html.escape(r['model'])} · "
                    f"첫 글자 {fmt_s(r['ttft'])}s — {html.escape(', '.join(flags) or '표지 없음')}</details></div>")
            trap = f" <span class=trap>함정: {html.escape(q['trap'])}</span>" if q.get("trap") else ""
            parts.append(f"<section><h3>{qid} [{html.escape(q['cue'])}] {html.escape(q['question'])} "
                         f"<small>({html.escape(q['src'])})</small>{trap}</h3><div class=row>{''.join(cells)}</div>"
                         f"<details><summary>감독이 준 지시문</summary><pre>{html.escape(q['brief'])}</pre></details></section>")
    page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>LLM 답 나란히 보기</title>
<style>:root{{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6b66;--line:#e2dfd6;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151513;--fg:#ecebe6;--mut:#a3a29b;--line:#34332f;--card:#1f1f1c}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"Apple SD Gothic Neo",sans-serif;margin:0 auto;max-width:1200px;padding:16px}}
h3{{font-size:16px;margin:22px 0 8px}} small,.len{{color:var(--mut);font-weight:400}} .trap{{font-size:12px;color:#b4530b}}
.row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}}
.ans{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}} .ans p{{margin:6px 0}}
pre{{white-space:pre-wrap;font-size:12px;color:var(--mut)}} summary{{cursor:pointer;color:var(--mut);font-size:12px}}</style>
<h1>관람객 질문 답 — 나란히 보기(블라인드)</h1>
<p>질문은 실제 관람객 말이 아니다(합성·테스트예시). 답은 앱 후처리(이름표·분량 상한·글 표기)를 지난 뒤 로봇이 말할 문장이다.
A/B 순서는 줄마다 섞었다 — 먼저 읽고 고른 뒤 「모델·표지」를 연다.</p>
{''.join(parts)}"""
    (LLM_OUT / "side-by-side.html").write_text(page, encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="호출 없이 질문 수·예상 비용")
    ap.add_argument("--preflight", action="store_true", help="OpenAI 가 로봇 본문을 받는지 한 번씩")
    ap.add_argument("--run", choices=sorted(RUNS), action="append", help="측정 묶음(여러 번 줄 수 있다)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="질문 앞 N개만")
    ap.add_argument("--no-warm", action="store_true")
    ap.add_argument("--local-url", default="http://127.0.0.1:18080")
    a = ap.parse_args(argv)
    cues, levels = load_cues(), load_levels()
    key = load_openai_key()
    print(f"OPENAI_API_KEY: {'설정됨' if key else '없음'} · 산출물 {LLM_OUT}")
    if a.dry_run:
        dry_run(cues, levels, a.run or sorted(RUNS), a.limit)
        return
    if a.preflight:
        preflight(key, a.local_url)
    for r in a.run or []:
        run(cues, levels, r, key, a.local_url, a.limit, warm=not a.no_warm)
    if a.report:
        print(report())


if __name__ == "__main__":
    main()
