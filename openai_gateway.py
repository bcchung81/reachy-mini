"""LLM·STT 게이트웨이 — 로봇·감독이 부르는 PC 주소(:8080 LLM · :8090 STT) 앞에 서서 OpenAI 로 넘긴다.

계획 `docs/superpowers/plans/2026-11-12-openai-gateway.md`. 근거 `docs/handoff/2026-11-10-frontier-ai-transition.md` §2.
**PC 쪽에서만 돈다.** 로봇·감독은 지금처럼 OpenAI 호환 요청을 PC 주소로 보내고, 키 주입·형식 번역은 여기서 끝난다
(로봇 재배포 없음, 키는 이 프로세스만 안다). 스위치(`REACHY_LLM_ENGINE`·`REACHY_STT_ENGINE`)를 안 켜면 `reachy.sh` 가
이 프로세스를 띄우지 않는다 — 지금 구성(llama-server·stt_server 직결) 그대로다.

    로봇·감독 ─:8080─▶ 게이트웨이 ─┬ OpenAI /v1/chat/completions(gpt-6-luna, reasoning_effort none, SSE 받는 대로)
                                  └ 실패·키 없음 → 로컬 llama-server(안쪽 127.0.0.1:8081, 원래 본문)
    로봇      ─:8090─▶ 게이트웨이 ─┬ OpenAI /v1/audio/transcriptions(gpt-transcribe, languages)
                                  └ 실패·키 없음 → 로컬 stt_server(안쪽 127.0.0.1:8091, 원래 본문)

키를 다루는 규칙(공개 저장소라 어기면 그대로 새어 나간다 — `tts_elevenlabs.py` 와 같다):
- 환경변수 `OPENAI_API_KEY` 가 먼저, 없으면 저장소 루트 `.env` 에서 **그 한 줄만** 읽는다(`source` 하지 않는다 — 그 셸이
  띄우는 앱까지 키를 물려받는다).
- 키 값은 로그·오류 응답·예외 어디에도 싣지 않는다. OpenAI 의 401 메시지는 키 일부(`sk-…abcd`)를 되돌려 주므로 오류
  요약에서 키와 `sk-…` 꼴을 지운다(`scrub`).

**외부 전용**(2026-11-13, `--no-local` — `reachy.sh` 의 `REACHY_LOCAL_MODELS=off`): 안쪽 로컬 서버를 아예 안 띄운 구성.
엔진이 openai 이고 키가 있을 때만 뜬다(`external_only_problems` — 아니면 기동에서 멈춘다). OpenAI 가 실패하면 넘길 곳이
없으니 **경고 한 줄 + 502** — 로봇 LLM 은 예외를 받아 "다시 말해 줄래요" 대사로, 감독은 폴백 대사로, 로봇 STT 는 못 들은
것으로 간다(`stt.transcribe` → ""). 헬스는 `"engines": "llm=openai,stt=openai,local=off"` 를 싣는다.

실행(보통은 `reachy.sh` 가 띄운다):
    .venv/bin/python openai_gateway.py --host 127.0.0.1 \
        --llm-port 8080 --llm-local http://127.0.0.1:8081 --llm-engine openai \
        --stt-port 8090 --stt-local http://127.0.0.1:8091 --stt-engine openai
    .venv/bin/python openai_gateway.py --host 127.0.0.1 --no-local \
        --llm-port 8080 --llm-engine openai --stt-port 8090 --stt-engine openai
"""

from __future__ import annotations

import argparse
import dataclasses
import http.client
import io
import json
import logging
import os
import pathlib
import re
import ssl
import threading
import time
import urllib.parse
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("openai-gateway")

ROOT = pathlib.Path(__file__).resolve().parent
KEY_ENV = "OPENAI_API_KEY"
ENGINES = ("local", "openai")
CHAT_PATH = "/v1/chat/completions"
STT_PATH = "/v1/audio/transcriptions"
DEFAULT_BASE = "https://api.openai.com"
# **[결정 2026-11-12]** LLM 기본 후보. `reasoning_effort` 기본이 medium 이라 그대로면 첫 토큰이 수 초다 — none 이 기본.
DEFAULT_LLM_MODEL = "gpt-6-luna"
DEFAULT_LLM_EFFORT = "none"
DEFAULT_STT_MODEL = "gpt-transcribe"

# 감독이 **전문가 수준** 요청에 싣는 표지(`model` 필드). `stage/__main__.py::EXPERT_MODEL_MARK` 와 같아야 한다(테스트가 본다).
# 로봇·감독이 원래 보내는 값은 `"local"`(`llm.LLMClient` 기본값) — 로컬로 넘길 때는 그 값으로 되돌린다.
EXPERT_MARK = "reachy-expert"
LOCAL_MODEL = "local"

# 사고를 켠 모델(effort 가 none 이 아님)의 상한은 **사고 토큰까지** 센다(`max_completion_tokens` 정의). 로봇이 주는 200 그대로면
# 사고에 다 쓰고 답이 비어 나온다 — 그만큼을 더한다. none 이면 더하지 않는다(지금 상한과 같은 분량).
REASONING_HEADROOM = 2000
# llama.cpp 서버만 아는 필드. OpenAI 는 모르는 필드를 400 으로 거절한다 — 우리 클라이언트는 지금 하나도 안 보내지만, 누가
# 실어 보내도 공연이 400 폴백으로 떨어지지 않게 버리고 **필드마다 한 번** 경고한다.
LLAMA_ONLY_FIELDS = (
    "cache_prompt", "id_slot", "slot_id", "n_predict", "n_keep", "n_probs", "top_k", "min_p", "typical_p",
    "tfs_z", "repeat_penalty", "repeat_last_n", "penalize_nl", "mirostat", "mirostat_tau", "mirostat_eta",
    "samplers", "grammar", "json_schema", "dynatemp_range", "dynatemp_exponent", "xtc_probability",
    "xtc_threshold", "dry_multiplier", "dry_base", "dry_allowed_length", "dry_penalty_last_n",
    "chat_template_kwargs", "reasoning_format", "t_max_predict_ms", "ignore_eos", "return_tokens",
)
# 사고를 켜면 OpenAI 가 거절하는 샘플링 필드(실측 2026-11-12: effort low + temperature 0.7 → 400 "Only the default (1)
# value is supported"). none 이면 그대로 둔다 — 지금 클라이언트의 temperature 0.7 이 그대로 먹는다.
SAMPLING_FIELDS = ("temperature", "top_p", "logprobs", "top_logprobs")

CHUNK = 4096
# 프록시에서 다시 쓰면 안 되는 홉 단위 헤더(`tts_cache_proxy._HOP` 와 같다).
_HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "proxy-connection"}
_SK_RE = re.compile(r"sk-[A-Za-z0-9_\-*]{3,}")


# ── 키 ─────────────────────────────────────────────────────────────
def load_api_key(env: dict | None = None, env_file: pathlib.Path | None = None) -> str | None:
    """키를 찾는다 — 환경변수가 먼저, 없으면 `.env` 의 `OPENAI_API_KEY=` 한 줄. 없으면 None.

    `tts_elevenlabs.load_api_key` 와 같은 방식이다(그 함수는 ElevenLabs 키 이름에 묶여 있어 고치지 않고 같은 패턴을 둔다).
    """
    env = os.environ if env is None else env
    v = (env.get(KEY_ENV) or "").strip()
    if v:
        return v
    path = env_file or pathlib.Path(env.get("OPENAI_ENV_FILE") or ROOT / ".env")
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        s = line.strip()
        if s.startswith("export "):
            s = s[len("export "):].lstrip()
        if not s.startswith(KEY_ENV + "="):
            continue
        val = s[len(KEY_ENV) + 1:].strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        return val or None
    return None


def key_status(key: str | None) -> str:
    """로그에 남기는 유일한 키 정보."""
    return "설정됨" if key else "없음"


def scrub(text: str, key: str | None) -> str:
    """오류 문구에서 키를 지운다 — 통째든 일부(`sk-proj-****abcd`)든."""
    if key:
        text = text.replace(key, "***")
    return _SK_RE.sub("sk-***", text)


def error_summary(raw: bytes, key: str | None) -> str:
    """OpenAI 오류 본문에서 사람이 읽을 요약만(본문 전체를 싣지 않는다)."""
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
        e = d.get("error", d) if isinstance(d, dict) else d
        msg = f"{e.get('code') or e.get('type') or ''} {e.get('message') or ''}".strip() if isinstance(e, dict) else str(e)
    except ValueError:
        msg = raw[:200].decode("utf-8", "replace")
    return scrub(msg[:300], key)


# ── 설정 ───────────────────────────────────────────────────────────
@dataclasses.dataclass
class Config:
    key: str | None
    llm_engine: str = "local"
    stt_engine: str = "local"
    llm_model: str = DEFAULT_LLM_MODEL
    llm_effort: str = DEFAULT_LLM_EFFORT
    llm_model_expert: str = ""          # 비면 전문가 라우팅 없음 — 표지가 와도 기본 모델(B1 이 정한다)
    llm_effort_expert: str = DEFAULT_LLM_EFFORT
    stt_model: str = DEFAULT_STT_MODEL
    # 로봇·감독의 LLM 타임아웃(10초) 안에 로컬 폴백(1~2초)까지 들어가게 — 첫 바이트까지 합친 마감. **다시 보내지 않는다**
    # (관람객이 기다린다 — 실패는 경고 + 로컬).
    llm_timeout_s: float = 5.0
    # Fast 모드 등(`service_tier`). **[B1 실측]** fast 는 첫 글자 p90 1.04 대 1.26초, 요금 2배 — 기본 비움(보내지 않음).
    llm_service_tier: str = ""
    # STT 는 **시도당** 상한이고 응답이 늦으면 한 번 더 보낸다. **[B1 실측]** 1,940회 중 중앙 0.73초·최대 3.12초, 그리고 27.4초
    # 1건 — 다시 보내면 정상이었다. 5초 × 2회 + 로컬 폴백(약 1초)이 로봇의 STT 타임아웃 15초 안에 든다.
    stt_timeout_s: float = 5.0
    stt_retries: int = 1
    base: str = DEFAULT_BASE
    # **[B1 실측]** `languages` 를 비우면 짧은 한국어가 외국어가 된다("다음" → `Palum.`·`さん。`). 기본은 한국어 하나 — 로봇의
    # `auto` 도 이것으로 보낸다. 영어 관람객을 받으려면 `REACHY_OPENAI_STT_LANGUAGES=ko,en`(그때만 허용 밖 감지 → ko 재전사가 돈다).
    stt_languages: tuple = ("ko",)
    stt_keywords: tuple = ()            # 큐시트에서 만든 전시 고유명사(`cue_keywords`) — 기동 때 한 번
    default_lang: str = "ko"
    auto_min_s: float = 1.0             # 이보다 짧은 `auto` 는 기본 언어 하나로(`stt_server.AUTO_MIN_SECONDS` 와 같은 규칙)

    def llm_openai(self) -> bool:
        return self.llm_engine == "openai" and bool(self.key)

    def stt_openai(self) -> bool:
        return self.stt_engine == "openai" and bool(self.key)


def engine_of(env: dict, name: str) -> str:
    """`local`/`openai`. 모르는 값은 조용히 넘기지 않고 멈춘다."""
    v = (env.get(name) or "local").strip().lower()
    if v not in ENGINES:
        raise ValueError(f"{name} 은 {'/'.join(ENGINES)} 중 하나다: {v!r}")
    return v


def config_from_env(env: dict | None = None, *, llm_engine: str | None = None,
                    stt_engine: str | None = None) -> Config:
    """기동 설정. 스위치를 켰는데 키가 없으면 **경고 한 줄**(서비스마다) — 그 서비스는 로컬로만 간다(외부 호출 0)."""
    env = os.environ if env is None else env
    llm = llm_engine or engine_of(env, "REACHY_LLM_ENGINE")
    stt = stt_engine or engine_of(env, "REACHY_STT_ENGINE")
    for name, v in (("--llm-engine", llm), ("--stt-engine", stt)):
        if v not in ENGINES:
            raise ValueError(f"{name} 은 {'/'.join(ENGINES)} 중 하나다: {v!r}")
    key = load_api_key(env) if "openai" in (llm, stt) else None
    effort = (env.get("REACHY_OPENAI_LLM_EFFORT") or DEFAULT_LLM_EFFORT).strip()
    cfg = Config(
        key=key, llm_engine=llm, stt_engine=stt,
        llm_model=(env.get("REACHY_OPENAI_LLM_MODEL") or DEFAULT_LLM_MODEL).strip(),
        llm_effort=effort,
        llm_model_expert=(env.get("REACHY_OPENAI_LLM_MODEL_EXPERT") or "").strip(),
        llm_effort_expert=(env.get("REACHY_OPENAI_LLM_EFFORT_EXPERT") or effort).strip(),
        stt_model=(env.get("REACHY_OPENAI_STT_MODEL") or DEFAULT_STT_MODEL).strip(),
        llm_timeout_s=float(env.get("REACHY_OPENAI_LLM_TIMEOUT_S") or 5.0),
        llm_service_tier=(env.get("REACHY_OPENAI_LLM_SERVICE_TIER") or "").strip(),
        stt_timeout_s=float(env.get("REACHY_OPENAI_STT_TIMEOUT_S") or 5.0),
        stt_retries=int(env.get("REACHY_OPENAI_STT_RETRIES") or 1),
        base=(env.get("REACHY_OPENAI_BASE") or DEFAULT_BASE).strip(),
        stt_languages=tuple(s.strip().lower() for s in (env.get("REACHY_OPENAI_STT_LANGUAGES") or "ko").split(",")
                            if s.strip()) or ("ko",),
        auto_min_s=float(env.get("STT_AUTO_MIN_S") or 1.0),
    )
    if not key:
        for service, v, var in (("LLM", llm, "REACHY_LLM_ENGINE"), ("STT", stt, "REACHY_STT_ENGINE")):
            if v == "openai":
                log.warning("%s=openai 인데 OpenAI 키가 없다(OPENAI_API_KEY 또는 저장소 루트 .env) — 로컬 %s 로 돈다",
                            var, service)
    if cfg.stt_openai():
        cfg.stt_keywords = tuple(stt_keywords_from_env(env))
    return cfg


def external_only_problems(cfg: Config, services: list[str]) -> list[str]:
    """외부 전용(`--no-local`)으로 띄울 수 없는 이유들 — 비면 띄운다.

    로컬이 없는 게이트웨이가 local 엔진이거나 키가 없으면 **모든 요청에 502** 만 준다. 띄워 두면 로봇은 "생각이 안 나요"
    만 되풀이하고 원인은 로그 속에 묻힌다 — 기동에서 멈춘다.
    """
    out = []
    for s in services:
        eng = cfg.llm_engine if s == "llm" else cfg.stt_engine
        if eng != "openai":
            out.append(f"{s.upper()} 엔진이 {eng} 다 — 외부 전용이면 REACHY_{s.upper()}_ENGINE=openai 여야 한다")
    if not cfg.key:
        out.append("OpenAI 키가 없다(OPENAI_API_KEY 또는 저장소 루트 .env) — 외부 전용이면 넘길 곳이 없다")
    return out


def stt_keywords_from_env(env: dict) -> list[str]:
    """STT 키워드 — 기본은 큐시트에서 만든다. `REACHY_OPENAI_STT_KEYWORDS=off` 면 보내지 않는다.

    만들다 실패해도(큐시트가 깨졌다 등) STT 는 돈다 — 경고 한 줄 + 키워드 없이. 상한·금지 문자에 걸리면 자르고 **경고 한 줄**.
    """
    if (env.get("REACHY_OPENAI_STT_KEYWORDS") or "cues").strip().lower() in ("0", "off", "false", "no"):
        log.info("STT 키워드 꺼짐(REACHY_OPENAI_STT_KEYWORDS)")
        return []
    try:
        words = control_keywords(env) + cue_keywords()
    except Exception as exc:  # noqa: BLE001 — 키워드는 정확도를 올릴 뿐이다, 기동을 막지 않는다
        log.warning("STT 키워드를 큐시트에서 만들지 못했다(%s: %s) — 키워드 없이 전사한다", type(exc).__name__, exc)
        return []
    seen: dict[str, None] = {}
    for w in words:
        if w.lower() not in {k.lower() for k in seen}:
            seen[w] = None
    words, problems = limit_keywords(list(seen), int(env.get("REACHY_OPENAI_STT_KEYWORDS_MAX") or KEYWORDS_MAX))
    if problems:
        log.warning("STT 키워드를 손봤다 — %s", " · ".join(problems))
    return words


# ── LLM 번역 ───────────────────────────────────────────────────────
def route_llm(body: dict, cfg: Config) -> tuple[str, str]:
    """(OpenAI 모델, effort). 전문가 표지 + 전문가 모델 설정이 있을 때만 상위 모델로."""
    if body.get("model") == EXPERT_MARK and cfg.llm_model_expert:
        return cfg.llm_model_expert, cfg.llm_effort_expert
    return cfg.llm_model, cfg.llm_effort


def to_openai_chat(body: dict, cfg: Config) -> tuple[dict, list[str]]:
    """로봇·감독 본문(llama-server 용 OpenAI 호환) → OpenAI 본문. (본문, 버린 llama.cpp 필드).

    바꾸는 것과 근거(실측 2026-11-12, 계획서 「실측한 사실」):
    - `model` → 설정한 OpenAI 모델(전문가 표지면 상위 모델).
    - `reasoning_effort` 를 붙인다(요청에 있으면 그대로) — 기본 medium 이면 첫 토큰이 수 초다.
    - `max_tokens` → `max_completion_tokens` — gpt-6 계열은 `max_tokens` 를 400 으로 거절한다.
    - 사고를 켰으면(effort ≠ none) `temperature` 등 샘플링 필드를 뺀다(400) + 상한에 사고 몫을 더한다.
    - `stream_options` 는 **넣지 않는다** — `include_usage` 의 마지막 줄은 `choices` 가 비어 로봇 파서가 `IndexError` 를 낸다.
    """
    out = dict(body)
    model, effort = route_llm(body, cfg)
    out["model"] = model
    effort = out.setdefault("reasoning_effort", effort)
    dropped = [k for k in LLAMA_ONLY_FIELDS if k in out]
    for k in dropped:
        out.pop(k)
    if "max_tokens" in out:
        mt = out.pop("max_tokens")
        if mt is not None and "max_completion_tokens" not in out:
            out["max_completion_tokens"] = int(mt) + (0 if effort == "none" else REASONING_HEADROOM)
    elif effort != "none" and out.get("max_completion_tokens") is not None:
        out["max_completion_tokens"] = int(out["max_completion_tokens"]) + REASONING_HEADROOM
    if effort != "none":
        for k in SAMPLING_FIELDS:
            out.pop(k, None)
    if cfg.llm_service_tier:
        out.setdefault("service_tier", cfg.llm_service_tier)
    return out, dropped


def to_local_chat(raw: bytes, body: dict | None) -> bytes:
    """로컬로 넘길 본문. **원래 바이트 그대로** — 전문가 표지만 원래 값(`"local"`)으로 되돌린다.

    표지는 스위치를 켰을 때만 실린다(감독). 로컬 llama-server 는 지금까지 `"local"` 만 받아 왔다 — 다른 이름을 보내 본 적이
    없으니 폴백 경로에서도 바꾸지 않는다.
    """
    if isinstance(body, dict) and body.get("model") == EXPERT_MARK:
        return json.dumps({**body, "model": LOCAL_MODEL}, ensure_ascii=False).encode("utf-8")
    return raw


# ── STT 번역 ───────────────────────────────────────────────────────
@dataclasses.dataclass
class FormFile:
    filename: str
    content_type: str
    data: bytes


def parse_multipart(content_type: str | None, raw: bytes) -> tuple[dict[str, str], FormFile]:
    """multipart/form-data → (글 필드, 파일). `cgi` 는 3.13 에서 사라져(`stt_server.py` 가 아직 쓴다) 직접 가른다.

    로봇은 `requests` 의 `files=`/`data=` 로 보낸다(경계 문자열은 무작위 16진) — 파일 바이트 안에 경계가 나올 일은 없다.
    """
    ct = content_type or ""
    m = re.search(r'boundary="?([^";]+)"?', ct, re.I)
    if "multipart/form-data" not in ct.lower() or not m:
        raise ValueError(f"multipart/form-data 가 아니다: {ct[:60]!r}")
    delim = b"--" + m.group(1).encode("latin-1")
    fields: dict[str, str] = {}
    file: FormFile | None = None
    for part in raw.split(delim)[1:]:
        if part.startswith(b"--"):
            break
        if part.startswith(b"\r\n"):
            part = part[2:]
        head, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers = {}
        for line in head.decode("utf-8", "replace").split("\r\n"):
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
        cd = headers.get("content-disposition", "")
        name = re.search(r'\bname="([^"]*)"', cd)
        if not name:
            continue
        filename = re.search(r'\bfilename="([^"]*)"', cd)
        if filename is not None:
            file = FormFile(filename.group(1) or "audio.wav",
                            headers.get("content-type", "application/octet-stream"), data)
        else:
            fields[name.group(1)] = data.decode("utf-8", "replace")
    if file is None:
        raise ValueError("file 필드가 없다")
    return fields, file


def build_multipart(fields: list[tuple[str, str]], file: FormFile) -> tuple[str, bytes]:
    bnd = uuid.uuid4().hex
    out = []
    for k, v in fields:
        out.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    out.append(f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="{file.filename}"\r\n'
               f"Content-Type: {file.content_type}\r\n\r\n".encode("utf-8") + file.data + b"\r\n")
    out.append(f"--{bnd}--\r\n".encode("ascii"))
    return f"multipart/form-data; boundary={bnd}", b"".join(out)


def wav_seconds(data: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, ZeroDivisionError):
        return None


def languages_for(raw: str | None, seconds: float | None, cfg: Config) -> tuple[list[str], bool]:
    """로봇의 `language` 값 → (`languages`, 허용 밖 감지면 다시 전사할 수 있나). 로컬 STT 서버 규칙을 옮긴다.

    - 값 없음·빈 값 → 기본 언어(`stt_server.resolve_language` — None 이면 ko).
    - `auto`/`detect`(앱 기본) → 설정한 언어 목록(`REACHY_OPENAI_STT_LANGUAGES`, 기본 **ko 하나**). 단 **1초 미만은 기본 언어
      하나** — 0.3초 "예" 가 영어로 판정돼 "Yay!" 가 나왔다(`stt_server.AUTO_MIN_SECONDS`).
    - 그 밖 → 그 언어 하나(로봇이 정했다). `gpt-transcribe` 는 `language` 대신 `languages` 배열을 받는다("둘 다 보내지 말 것").
    다시 전사는 목록이 둘 이상일 때만 뜻이 있다 — 이미 ko 하나로 보냈으면 같은 요청을 되풀이할 뿐이다.
    """
    if raw is None or not raw.strip():
        return [cfg.default_lang], False
    v = raw.strip().lower()
    if v in ("auto", "detect"):
        if seconds is not None and seconds < cfg.auto_min_s:
            return [cfg.default_lang], False
        langs = list(cfg.stt_languages) or [cfg.default_lang]
        return langs, len(langs) > 1
    return [v], False


# ── STT 키워드 — 큐시트·교육자료 카드에서 기동 때 한 번 만든다 ─────────
# **[B1 실측 2026-11-12]** 전시 고유명사를 `keywords` 로 주면 키워드가 든 문장 CER 3.6% → 0.2%, 없는 키워드를 끌어온 받아쓰기
# 0/480(`docs/research/2026-11-12-openai-llm-stt-measure.md`). B1 은 시험 문장에서 16개를 손으로 골랐다 — 실제 관람객 질문에
# 걸리려면 **관람객이 듣고 보는 글**(큐시트 대사·교육자료 카드)에서 만들어야 한다. 손으로 적은 목록은 대본이 바뀌면 썩는다.
#
# 형태소 분석기 없이 **사람이 이미 골라 둔 자리**만 본다(정확도가 재현율보다 중요하다 — 공식 문서: "관련 있는 낱말만"):
#   K1 약어·부호 — 대사·카드의 라틴 낱말(GMDSS·VLF·ICAO·5G …). 단위(MHz·km·100W)와 규격 번호(V.431-8)는 뺀다.
#   K2 가운뎃점 나열 — "맥스웰·헤르츠·마르코니", "VLF·EHF" 의 각 항목. 대본이 용어를 나열할 때 쓰는 꼴이다.
#   K3 라벨 — 큐 제목·주제, 카드의 항목 제목·그림 라벨(지도 출발·도착, 단계 이름)을 구분 기호로 가른 1~2어절 명사구.
#      "폴듀 (영국)"·"뉴펀들랜드"·"루노호트와 월면차" 같은 이름이 여기 있다. 앞의 연도·번호("1912년 타이타닉")는 뗀다.
# 대사 문장 속에만 나오는 이름(예: 카르파티아호·쿨롱)은 못 줍는다 — 문장에서 이름을 가르려면 형태소 분석이 필요하다.
CARDS_DIR = ROOT / "data" / "handout-cards"
# 공식 문서(API 레퍼런스·STT 가이드·마이그레이션 쿡북, 2026-11-12 확인)는 금지 문자만 밝힌다 — `<`·`>`·CR·LF 가 하나라도 있으면
# **요청 전체를 거절**한다. 개수·길이 수치는 문서에 없다 → 실측(2026-11-12, 계획서 「실측한 사실」): 500개·한 낱말 1,000자는
# 받고 **1,000개는 400 "Could not parse multipart form"**(요청 전체 실패). 지금 큐시트에서 약 250개가 나온다 — 상한 300개로
# 여유를 두고, 넘치면 뒤(대본 뒤쪽 큐)를 자르고 경고 한 줄. 한 낱말 40자는 라벨에서 나올 수 없는 길이다(넘으면 추출이 샜다).
KEYWORDS_MAX = 300
KEYWORD_MAX_CHARS = 40
_KW_FORBIDDEN = re.compile(r"[<>\r\n]")
_LATIN = re.compile(r"(?<![A-Za-z0-9.])[0-9]*[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*(?![A-Za-z0-9]*\.[0-9])")
_UNIT = re.compile(r"^[0-9]*(?:[kMGT]?Hz|[kcm]?m|[mkM]?W|dB|V|A|B|bps|[kMG]bps)$")
_ENUM = re.compile(r"[가-힣A-Za-z0-9]+(?:·[가-힣A-Za-z0-9]+)+")
_LABEL_SPLIT = re.compile(r"\s*(?:[—–:,·/()\[\]]|\s그리고\s|\s및\s)\s*")
_COUNTED = re.compile(r"^(?:제?[0-9][0-9.,]*(?:년|월|일|세대|등급|급|호|명|분|초|항|km|%)?|[0-9]+(?:년대|세기))$")
# 받침이 있는 말 뒤에 붙는 것 / 없는 말 뒤에 붙는 것 — **받침 규칙을 지켜야 이름을 안 깎는다**("패러데이" 의 '이' 는 조사가
# 아니다 — '데' 에 받침이 없으니까. "테레민이" 의 '이' 는 조사다).
_AFTER_BATCHIM = ("이라는", "으로", "과", "은", "을", "이")
_AFTER_VOWEL = ("라는", "와", "는", "를", "가")      # '로' 는 넣지 않는다 — "회로"·"경로" 를 깎는다(조사 '으로' 는 위에)
_ANY = ("에서", "까지", "부터", "처럼", "보다", "의")
_VERB_END = ("다", "요", "까", "죠", "네", "며", "수록", "었나", "였나", "인가", "는가")
# 라벨이지만 이름이 아닌 것 — 의문 꼴("무엇이 언제")·이음말. 키워드 목록이 아니라 거르는 말이다.
_QUESTION = ("무엇", "언제", "어디", "누가", "누구", "어떻게", "어떤", "얼마")
_CONNECT = ("그리고", "또는", "및")


def _has_batchim(ch: str) -> bool:
    return "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0


def _strip_particle(w: str) -> tuple[str, bool]:
    """끝의 조사 하나를 뗀다 → (줄기, 뗐나). '의' 등 받침과 무관한 조사는 줄기가 두 글자 미만이면 떼지 않는다
    ("회의"·"주의" 를 지킨다). 받침 조사는 떼고 한 글자가 남아도 돌려준다 — "빛이" 같은 한 음절 말은 호출자가 버린다."""
    m = re.fullmatch(r"([A-Za-z0-9\-]*[A-Za-z][A-Za-z0-9\-]*)([가-힣]{1,3})", w)
    if m and m.group(2) in (*_AFTER_BATCHIM, *_AFTER_VOWEL, *_ANY, "로", "에", "도", "만"):
        # 라틴 낱말 + 조사("LTE로", "GMDSS는") — 받침 규칙을 볼 수 없다(영문자 읽기에 따라 다르다). 조사 목록에 있는 꼬리만
        # 뗀다 — "ICT기금" 의 '기금' 은 조사가 아니다.
        return m.group(1), True
    for p in sorted(_AFTER_BATCHIM + _AFTER_VOWEL + _ANY, key=len, reverse=True):
        if not w.endswith(p) or len(w) == len(p):
            continue
        prev = w[-len(p) - 1]
        if p in _AFTER_BATCHIM and not _has_batchim(prev):
            continue
        if p in _AFTER_VOWEL and _has_batchim(prev):
            continue
        stem = w[: -len(p)]
        if p in _ANY and len(stem) < 2:
            continue
        return stem, True
    return w, False


def _word_ok(w: str) -> bool:
    """키워드 한 어절로 쓸 만한가 — 두 글자 이상의 명사꼴. 동사 끝("보내면"·"멀어질수록")·의문 꼴·숫자로 시작하는 말은 아니다."""
    if len(w) < 2 or not re.fullmatch(r"[가-힣A-Za-z0-9\-]+", w) or w[0].isdigit() or _UNIT.match(w):
        return False
    if w.endswith(_VERB_END) or w.startswith(_QUESTION) or w in _CONNECT:
        return False
    # 받침 없는 줄기 + '면' = 조건 꼴("보내면"). "조종면"·"화면" 같은 명사는 지킨다(앞 글자 받침 / 두 글자).
    return not (len(w) >= 3 and w.endswith("면") and not _has_batchim(w[-2]))


def _latin_terms(text: str) -> list[str]:
    out = []
    for m in _LATIN.findall(text):
        letters = sum(c.isalpha() for c in m)
        if letters >= 2 and any(c.isupper() for c in m) and not _UNIT.match(m) or re.fullmatch(r"[0-9]G", m):
            out.append(m)
    return out


def _enum_terms(text: str) -> list[str]:
    out = []
    for m in _ENUM.findall(text):
        for part in m.split("·"):
            stem, _ = _strip_particle(part)
            if _word_ok(stem):
                out.append(stem)
    return out


def _label_terms(label: str) -> list[str]:
    out = []
    for seg in _LABEL_SPLIT.split(label or ""):
        words = [w for w in seg.split() if not w[0].isdigit() and not _COUNTED.match(w) and w not in _CONNECT]
        if not words or len(words) > 2:
            continue
        stripped = [_strip_particle(w) for w in words]
        if len(words) == 2 and stripped[0][1]:
            # 첫 어절에 조사가 붙었다 — 한 이름이 아니라 두 말이다("루노호트와 월면차", "타이타닉에서 GMDSS")
            cands = [[stripped[0][0]], [stripped[1][0]]]
        else:
            cands = [[*words[:-1], stripped[-1][0]]]
        for ws in cands:
            if all(_word_ok(w) for w in ws):
                out.append(" ".join(ws))
    return out


def _card_texts(card: dict) -> tuple[list[str], list[str]]:
    """카드 한 장 → (보이는 글 전부, 라벨). 그림 설정값(type·at·ticks 등)은 글이 아니다."""
    texts: list[str] = []
    labels: list[str] = []
    for lv in (card.get("levels") or {}).values():
        if not isinstance(lv, dict):
            continue
        texts += [str(lv.get(k)) for k in ("headline", "remember") if lv.get(k)]
        for it in lv.get("items") or []:
            if isinstance(it, dict):
                texts += [str(it.get(k)) for k in ("t", "b") if it.get(k)]
                labels += [str(it["t"])] if it.get("t") else []
        v = lv.get("visual") or {}
        if not isinstance(v, dict):
            continue
        for k in ("title", "label", "from", "to", "caption"):
            if v.get(k):
                texts.append(str(v[k]))
                labels.append(str(v[k]))
        for s in (v.get("steps") or []) + (v.get("facts") or []):
            if isinstance(s, dict):
                for k in ("k", "v", "label", "big"):
                    if s.get(k) is not None:
                        texts.append(str(s[k]))
                labels += [str(s[k]) for k in ("k", "label") if s.get(k) is not None]
    return texts, labels


def cue_keywords(cues_path: pathlib.Path | None = None, cards_dir: pathlib.Path | None = None) -> list[str]:
    """큐시트(감독과 같은 로더·같은 `REACHY_CUES_PATH`)와 교육자료 카드에서 STT 키워드를 만든다. 순서는 대본 순서(먼저 나온 것 먼저 —
    상한에 걸려 잘려도 앞 큐의 낱말이 남는다), 중복 없음. 상한·금지 문자는 `limit_keywords` 가 따로 본다."""
    from stage.cues import load_cues
    from stage.levels import LEVEL_NAMES

    seen: dict[str, None] = {}

    def add(terms):
        for t in terms:
            t = t.strip()
            if t and t.lower() not in {s.lower() for s in seen}:
                seen[t] = None

    cards_dir = CARDS_DIR if cards_dir is None else pathlib.Path(cards_dir)
    for cue in load_cues(cues_path):
        texts = [cue.title, cue.topic, cue.mc, cue.mc_after]
        for lv in LEVEL_NAMES:
            for p in cue.points_for(lv):
                texts += [p.ask, p.answer]
        labels = [cue.title, cue.topic]
        card = cards_dir / f"{cue.id}.yaml"
        if card.is_file():
            import yaml
            ct, cl = _card_texts(yaml.safe_load(card.read_text(encoding="utf-8")) or {})
            texts += ct
            labels += cl
        texts = [t for t in texts if t]
        for t in texts:
            add(_latin_terms(t))
        for t in texts:
            add(_enum_terms(t))
        for lab in labels:
            add(_label_terms(lab))
    return list(seen)


VOICE_LOOP = ROOT / "apps" / "voice_chat" / "voice_chat" / "voice_loop.py"


def control_keywords(env: dict | None = None) -> list[str]:
    """관람객이 로봇을 부르고 멈추는 말 — 대본 낱말보다 먼저 싣는다(상한에 걸려도 남게).

    - 역할 이름(감독의 `SPEAKER_LABEL` — "사회자"·"도슨트"): 관람객이 "도슨트, …" 로 부른다. 키워드 없이 "노슨트" 로 받아쓴
      것을 보았다(2026-11-12 스모크).
    - 끼어들기 호출어(로봇 앱 `voice_loop.BARGE_IN_WAKE` — 기본 "미니야,그만,잠깐만,스톱"): 앱이 **STT 결과에서** 이 말을 찾아
      말을 끊는다. 앱 모듈은 마이크 장치까지 불러오므로 import 하지 않고, PC 의 `REACHY_BARGE_IN_WAKE` 가 있으면 그것을,
      없으면 앱 소스의 기본값을 읽는다. 로봇 config 에서 바꿨다면 PC 에도 같은 값을 준다.
    - 진행어(2026-11-13, 감독 `stage.cues._ADVANCE_WORDS` — "다음"·"이어서"·"진행" …): 관람객이 큐 사이 질문 창에서 "다음"·
      "이어서 진행" 으로 넘긴다. 한두 음절짜리 짧은 말이라 가장 잘 틀린다 — 틀리면 질문으로 가서 도슨트가 그 말에 답을 만든다.
    """
    env = os.environ if env is None else env
    from stage.cues import _ADVANCE_WORDS
    from stage.director import SPEAKER_LABEL

    out = list(dict.fromkeys(SPEAKER_LABEL.values()))
    wake = env.get("REACHY_BARGE_IN_WAKE")
    if wake is None:
        try:
            m = re.search(r'"REACHY_BARGE_IN_WAKE",\s*"([^"]*)"', VOICE_LOOP.read_text(encoding="utf-8"))
            wake = m.group(1) if m else ""
        except OSError:
            wake = ""
    out += [w.strip() for w in wake.split(",") if w.strip()]
    out += list(_ADVANCE_WORDS)
    return list(dict.fromkeys(out))


def limit_keywords(words: list[str], max_count: int = KEYWORDS_MAX) -> tuple[list[str], list[str]]:
    """(보낼 키워드, 문제 설명들). 금지 문자가 든 것·너무 긴 것은 빼고, 개수가 넘치면 뒤를 자른다 — 하나라도 어기면 OpenAI 가
    요청 전체를 거절하므로(공식 문서) 보내기 전에 거른다. 문제 설명은 호출자가 **경고 한 줄**로 낸다."""
    problems = []
    bad = [w for w in words if _KW_FORBIDDEN.search(w) or len(w) > KEYWORD_MAX_CHARS]
    if bad:
        problems.append(f"금지 문자(<, >, 줄바꿈)나 {KEYWORD_MAX_CHARS}자 초과 {len(bad)}개를 뺐다(예: {bad[0][:20]!r})")
    ok = [w for w in words if w not in bad]
    if len(ok) > max_count:
        problems.append(f"{len(ok)}개가 상한 {max_count}개를 넘어 뒤 {len(ok) - max_count}개를 잘랐다(예: {ok[max_count]!r})")
        ok = ok[:max_count]
    return ok, problems


# ── OpenAI 연결 ────────────────────────────────────────────────────
class ResponseTimeout(TimeoutError):
    """요청은 보냈는데 응답 머리가 시간 안에 안 왔다(연결 시간 초과와 가르려고 따로 둔다)."""


# 외부 전용 502 에 싣는 실패 종류(`upstream`). 예열(`scripts/warmup.py`)이 이것으로 "키가 틀렸다 / 잔액·한도 / 인터넷" 을
# 가른다(계획 2026-11-14 A-1). **종류만** 싣는다 — OpenAI 메시지 글은 401 때 키 조각을 되돌려 주므로(lessons 2026-11-12)
# 응답에 실으면 예열 화면·로그로 샌다. 원인 글은 게이트웨이 로그에만 남는다(키는 `scrub` 으로 지워서).
UPSTREAM_KINDS = ("401", "429", "5xx", "4xx", "connect", "timeout", "other")


def upstream_kind(status: int | None = None, exc: BaseException | None = None) -> str:
    """상태 코드나 예외를 `UPSTREAM_KINDS` 하나로. 401·429 만 따로 둔다 — 운영자가 할 일이 다르다(키 확인 / 결제 확인).
    403 은 "키에 그 모델 권한이 없다" 같은 경우라 4xx 로 묶고 로그를 보게 한다."""
    if status is not None:
        if status in (401, 429):
            return str(status)
        if 500 <= status < 600:
            return "5xx"
        if 400 <= status < 500:
            return "4xx"
        return "other"
    if isinstance(exc, TimeoutError):          # ResponseTimeout·socket.timeout 모두 TimeoutError 다
        return "timeout"
    if isinstance(exc, OSError):               # 연결 거부·이름 풀기 실패·TLS·끊김(RemoteDisconnected 도 OSError)
        return "connect"
    return "other"


class GatewayError(RuntimeError):
    """OpenAI 쪽 실패. **메시지에 키가 들어가지 않는다** — 상태 코드와 오류 요약만. `slow` 는 요청을 보낸 뒤 응답이
    시간 안에 안 온 경우다 — STT 는 이것만 한 번 더 보낸다(연결이 안 되는 것은 다시 해도 같다 — 오프라인이면 시간만 버린다).
    `kind` 는 외부 전용 502 에 실을 실패 종류(`upstream_kind`)."""

    def __init__(self, message: str, slow: bool = False, kind: str = "other") -> None:
        super().__init__(message)
        self.slow = slow
        self.kind = "timeout" if slow else kind


def set_timeout(conn: http.client.HTTPConnection, seconds: float) -> None:
    """이미 열린 연결의 소켓 시간 상한을 바꾼다(응답 본문 읽기도 이 소켓을 탄다)."""
    conn.timeout = seconds
    if conn.sock is not None:
        conn.sock.settimeout(seconds)


class OpenAIPool:
    """OpenAI 로 가는 연결을 남겨 다시 쓴다. 새 연결마다 TCP·TLS 왕복이 **첫 토큰 앞에** 얹힌다.

    남겨 둔 연결은 서버가 그사이 닫았을 수 있다 — 보내다 끊기면(`RemoteDisconnected` 등) 새 연결로 한 번만 다시 보낸다.
    시간 초과는 다시 보내지 않는다(관람객이 기다린다 — 호출자가 로컬로 넘긴다).
    """

    _STALE = (http.client.RemoteDisconnected, http.client.CannotSendRequest, BrokenPipeError,
              ConnectionResetError, ConnectionAbortedError)

    def __init__(self, base: str, max_idle: int = 8) -> None:
        u = urllib.parse.urlsplit(base)
        self.https = u.scheme == "https"
        self.host = u.hostname or "api.openai.com"
        self.port = u.port or (443 if self.https else 80)
        self.prefix = u.path.rstrip("/")
        self.max_idle = max_idle
        self._idle: list[http.client.HTTPConnection] = []
        self._lock = threading.Lock()
        self._ctx = ssl.create_default_context() if self.https else None

    def _new(self, timeout: float) -> http.client.HTTPConnection:
        if self.https:
            return http.client.HTTPSConnection(self.host, self.port, timeout=timeout, context=self._ctx)
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)

    def _take(self) -> http.client.HTTPConnection | None:
        with self._lock:
            return self._idle.pop() if self._idle else None

    def request(self, method: str, path: str, body: bytes, headers: dict, deadline: float):
        """(연결, 응답). 응답 머리까지 받은 상태로 돌려준다 — 본문은 호출자가 읽고 `release` 한다.

        `deadline`(monotonic)은 **연결·보내기·응답 머리를 합친** 마감이다. 소켓 시간 상한은 단계마다 새로 걸리므로 하나만
        주면 느린(죽지는 않은) 서버에서 그 몇 배를 기다린다 — 로봇의 시간 상한 안에 로컬 폴백이 못 들어간다.
        """
        conn = self._take()
        for attempt in (0, 1):
            fresh = conn is None
            left = max(0.05, deadline - time.monotonic())
            if conn is None:
                conn = self._new(left)
            else:
                set_timeout(conn, left)
            try:
                conn.request(method, self.prefix + path, body=body, headers=headers)
                set_timeout(conn, max(0.05, deadline - time.monotonic()))
                try:
                    return conn, conn.getresponse()
                except TimeoutError as exc:
                    raise ResponseTimeout(f"응답 시간 초과({exc})") from None
            except self._STALE:
                conn.close()
                if fresh or attempt:
                    raise
                conn = None          # 남겨 둔 연결이 죽어 있었다 — 새 연결로 한 번 더
            except BaseException:
                conn.close()
                raise
        raise AssertionError("도달하지 않는다")

    def release(self, conn: http.client.HTTPConnection, resp: http.client.HTTPResponse) -> None:
        """본문을 끝까지 읽은 연결만 남긴다(덜 읽은 연결에 다음 요청을 실으면 응답이 엇갈린다)."""
        if resp.isclosed() and not resp.will_close and conn.sock is not None:
            with self._lock:
                if len(self._idle) < self.max_idle:
                    self._idle.append(conn)
                    return
        conn.close()


# ── 서버 ───────────────────────────────────────────────────────────
class GatewayServer(ThreadingHTTPServer):
    """한 서비스(llm 또는 stt)의 리스너. 한 프로세스가 둘을 띄운다 — 설정·OpenAI 연결 풀·경고 기록을 같이 쓴다."""

    daemon_threads = True

    def __init__(self, addr, service: str, local: str | None, cfg: Config, shared: "Shared") -> None:
        super().__init__(addr, Handler)
        self.service = service
        # local=None — 외부 전용(안쪽 로컬 서버 없음). 실패는 502 로 돌려준다(`_no_local`).
        u = urllib.parse.urlsplit(local) if local else None
        self.local_host = (u.hostname or "127.0.0.1") if u else None
        self.local_port = (u.port or 80) if u else 0
        self.cfg = cfg
        self.shared = shared


class Shared:
    def __init__(self, cfg: Config) -> None:
        self.pool = OpenAIPool(cfg.base)
        self._lock = threading.Lock()
        self._warned: set[str] = set()

    def warn_once(self, tag: str, message: str) -> None:
        with self._lock:
            if tag in self._warned:
                return
            self._warned.add(tag)
        log.warning(message)


class Handler(BaseHTTPRequestHandler):
    server: GatewayServer
    protocol_version = "HTTP/1.1"
    # 로봇은 keep-alive 로 연결을 들고 있는다(`llm._session`). 쉬는 연결을 영원히 붙잡지 않게.
    timeout = 300

    def log_message(self, fmt, *args):  # 요청마다 찍는 기본 접근 로그는 끈다 — 필요한 것만 아래에서
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            # 로봇이 쉬던 keep-alive 연결을 끊었다 — 정상이다. 기본 처리는 요청마다 트레이스백을 로그에 쏟아
            # 진짜 경고를 묻는다.
            pass

    # ── 공용 ──────────────────────────────────────────────────────
    def _send_json(self, status: int, obj: dict, extra: dict | None = None) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _write_chunk(self, data: bytes) -> None:
        self.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")

    def _end_chunks(self) -> None:
        self.wfile.write(b"0\r\n\r\n")

    def _local_conn(self, timeout: float = 120.0) -> http.client.HTTPConnection:
        return http.client.HTTPConnection(self.server.local_host, self.server.local_port, timeout=timeout)

    def _base_info(self) -> dict:
        cfg = self.server.cfg
        info = {"gateway": "openai", "service": self.server.service,
                # `reachy.sh` 가 "같은 설정의 게이트웨이가 떠 있나" 를 이 한 줄로 가른다 — 모양을 바꾸면 거기도 바꾼다.
                # 외부 전용이면 `,local=off` 가 붙는다 — 로컬 폴백이 있는 게이트웨이를 외부 전용으로 착각해 재사용하지 않게.
                "engines": f"llm={cfg.llm_engine},stt={cfg.stt_engine}"
                           + (",local=off" if self.server.local_host is None else ""),
                "key": key_status(cfg.key)}
        if self.server.service == "llm":
            info.update(engine=cfg.llm_engine, model=cfg.llm_model, expert_model=cfg.llm_model_expert or None)
        else:
            info.update(engine=cfg.stt_engine, model=cfg.stt_model)
        return info

    def _openai_on(self) -> bool:
        cfg = self.server.cfg
        return cfg.llm_openai() if self.server.service == "llm" else cfg.stt_openai()

    # ── GET ───────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._health()
            return
        self._local("GET", None, tag="local")

    def _health(self) -> None:
        """OpenAI 로 가고 키가 있으면 로컬이 죽어 있어도 200(외부는 부르지 않는다 — 헬스는 자주 불린다).
        아니면 로컬 헬스를 그대로 — 로컬이 곧 이 서비스다."""
        base = self._base_info()
        if self.server.local_host is None:
            # 외부 전용 — 물어볼 로컬이 없다. 기동이 "openai + 키" 를 확인했다(`external_only_problems`).
            ok = self._openai_on()
            self._send_json(200 if ok else 503, {"status": "ok" if ok else "no-engine", **base, "local": "off"})
            return
        try:
            conn = self._local_conn(timeout=3.0)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            if self._openai_on():
                self._send_json(200, {"status": "ok", **base, "local": f"down({type(exc).__name__})"})
            else:
                self._send_json(503, {"status": "local-down", **base, "detail": f"{type(exc).__name__}: {exc}"})
            return
        try:
            local = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(local, dict):
                local = {}
        except ValueError:
            local = {}
        status = 200 if self._openai_on() else resp.status
        self._send_json(status, {**local, **base, "local": "ok" if resp.status == 200 else f"http {resp.status}"})

    # ── POST ──────────────────────────────────────────────────────
    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if self.server.service == "llm" and self.path == CHAT_PATH:
            self._chat(raw)
        elif self.server.service == "stt" and self.path == STT_PATH:
            self._stt(raw)
        else:
            self._local("POST", raw, tag="local")

    # ── LLM ───────────────────────────────────────────────────────
    def _chat(self, raw: bytes) -> None:
        cfg, shared = self.server.cfg, self.server.shared
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = None
        if not cfg.llm_openai() or not isinstance(body, dict):
            # 스위치가 꺼졌거나 키가 없다 — 외부를 부르지 않는다. 판단할 수 없는 본문은 로컬 서버가 거절하게 둔다.
            self._local("POST", to_local_chat(raw, body), tag="local")
            return
        payload, dropped = to_openai_chat(body, cfg)
        for k in dropped:
            shared.warn_once(f"field:{k}", f"OpenAI 가 모르는 llama.cpp 필드 {k!r} 를 버리고 보낸다 — 이 경고는 한 번만 낸다")
        model = payload["model"]
        stream = bool(body.get("stream"))
        headers = {"Authorization": f"Bearer {cfg.key}", "Content-Type": "application/json",
                   "Accept": "text/event-stream" if stream else "application/json",
                   "User-Agent": "reachy-gateway"}
        t0 = time.monotonic()
        # 첫 바이트까지 **합쳐서** 이 시간 안 — 넘으면 로컬로(로봇·감독의 10초 안에 로컬 답까지 들어가게).
        deadline = t0 + cfg.llm_timeout_s
        try:
            conn, resp = shared.pool.request("POST", CHAT_PATH, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                             headers, deadline)
        except (OSError, http.client.HTTPException) as exc:
            self._llm_fallback(raw, body, model, f"{type(exc).__name__}: {exc}", upstream_kind(exc=exc))
            return
        if resp.status != 200:
            summary = error_summary(resp.read(), cfg.key)
            conn.close()
            self._llm_fallback(raw, body, model, f"HTTP {resp.status} {summary}", upstream_kind(status=resp.status))
            return
        if not stream:
            try:
                data = resp.read()
            except (OSError, http.client.HTTPException) as exc:
                conn.close()
                self._llm_fallback(raw, body, model, f"{type(exc).__name__}: {exc}", upstream_kind(exc=exc))
                return
            shared.pool.release(conn, resp)
            # 받은 바이트 그대로 — 다시 직렬화하지 않는다(모양을 우리가 바꿀 이유가 없다).
            self.send_response(200)
            self.send_header("Content-Type", resp.getheader("Content-Type") or "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Reachy-Gateway", "openai")
            self.send_header("X-Reachy-Model", model)
            self.end_headers()
            self.wfile.write(data)
            log.info("llm openai %s 비스트림 %.2fs", model, time.monotonic() - t0)
            return
        # **첫 청크를 받은 뒤에야 머리를 보낸다** — 그 전에 끊기면 아직 로컬로 넘길 수 있다.
        read = getattr(resp, "read1", None) or resp.read
        try:
            set_timeout(conn, max(0.05, deadline - time.monotonic()))
            first = read(CHUNK)
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            self._llm_fallback(raw, body, model, f"첫 바이트 전에 끊김 {type(exc).__name__}: {exc}", upstream_kind(exc=exc))
            return
        if not first:
            conn.close()
            self._llm_fallback(raw, body, model, "빈 응답", "other")
            return
        ttfb = time.monotonic() - t0
        set_timeout(conn, cfg.llm_timeout_s)       # 여기부터는 바이트 사이 간격의 상한이다
        self.send_response(200)
        self.send_header("Content-Type", resp.getheader("Content-Type") or "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("X-Reachy-Gateway", "openai")
        self.send_header("X-Reachy-Model", model)
        self.end_headers()
        data = first
        while data:
            try:
                self._write_chunk(data)
            except (BrokenPipeError, ConnectionResetError):
                # 로봇이 끊었다(끼어들기) — 정상이다. OpenAI 쪽 연결은 덜 읽었으니 버린다.
                conn.close()
                self.close_connection = True
                return
            try:
                data = read(CHUNK)
            except (OSError, http.client.HTTPException) as exc:
                # 머리를 보낸 뒤 끊겼다 — 받은 데까지는 이미 로봇이 말했다. **끝맺지 않고 닫는다**: 정상 종료로 보이면
                # 로봇·감독이 잘린 답을 완성된 답으로 읽는다(감독은 예외를 받아야 폴백 대사로 간다).
                log.warning("OpenAI 스트림이 도중에 끊겼다(%s) — 받은 데까지만 나갔다, 연결을 끝맺지 않고 닫는다",
                            scrub(f"{type(exc).__name__}: {exc}", cfg.key))
                conn.close()
                self.close_connection = True
                return
        self._end_chunks()
        shared.pool.release(conn, resp)
        log.info("llm openai %s 첫 바이트 %.2fs 전체 %.2fs", model, ttfb, time.monotonic() - t0)

    def _llm_fallback(self, raw: bytes, body: dict, model: str, reason: str, kind: str = "other") -> None:
        """실패 정책: 로컬 서버로 **원래 본문**을 넘기고 경고 한 줄(요청마다). 로컬도 없으면 502 — 지금과 같은 오류.
        `kind` 는 외부 전용 502 에만 싣는다(로컬로 넘기면 로봇은 정상 답을 받는다 — 실을 자리가 없다)."""
        if self.server.local_host is None:
            self._no_local(f"OpenAI LLM({model}) 실패 — 외부 전용이라 넘길 로컬 LLM 이 없다, 502"
                           f"(로봇은 '다시 말해 줄래요' 대사, 감독은 폴백 대사로 간다): {reason}", upstream=kind)
            return
        log.warning("OpenAI LLM(%s) 실패 — 로컬 LLM 으로 넘긴다: %s", model, scrub(reason, self.server.cfg.key))
        self._local("POST", to_local_chat(raw, body), tag="fallback")

    # ── STT ───────────────────────────────────────────────────────
    def _stt(self, raw: bytes) -> None:
        cfg = self.server.cfg
        if not cfg.stt_openai():
            self._local("POST", raw, tag="local")
            return
        try:
            fields, file = parse_multipart(self.headers.get("Content-Type"), raw)
        except ValueError as exc:
            # 우리가 판단할 일이 아니다 — 로컬 서버가 지금처럼 거절하게 둔다.
            self.server.shared.warn_once(f"form:{exc}", f"전사 요청을 풀지 못했다({exc}) — 로컬 STT 로 넘긴다")
            self._local("POST", raw, tag="local")
            return
        secs = wav_seconds(file.data)
        langs, may_redo = languages_for(fields.get("language"), secs, cfg)
        t0 = time.monotonic()
        try:
            text, detected = self._transcribe_retry(file, langs)
            if may_redo and detected and not any(c in cfg.stt_languages for c in detected):
                # 로컬 서버와 같은 규칙: 감지가 허용 밖 언어를 골랐으면 기본 언어로 다시("네" → 베트남어 'Đề.').
                log.info("stt 감지 언어 %s 가 허용(%s) 밖 — %s 로 다시 전사", detected, ",".join(cfg.stt_languages),
                         cfg.default_lang)
                langs = [cfg.default_lang]
                text, detected = self._transcribe_retry(file, langs)
        except GatewayError as exc:
            if self.server.local_host is None:
                self._no_local(f"OpenAI STT({cfg.stt_model}) 실패 — 외부 전용이라 넘길 로컬 STT 가 없다, 502"
                               f"(로봇은 못 들은 것으로 친다): {exc}", upstream=exc.kind)
                return
            log.warning("OpenAI STT(%s) 실패 — 로컬 STT 로 넘긴다: %s", cfg.stt_model, scrub(str(exc), cfg.key))
            self._local("POST", raw, tag="fallback")
            return
        lang = detected[0] if detected else langs[0]
        log.info("stt openai %s %s오디오 → %.2fs [%s]", cfg.stt_model,
                 f"{secs:.1f}s " if secs is not None else "", time.monotonic() - t0, lang)
        # 로컬 STT 서버와 같은 응답 모양 — 로봇은 `text` 만 읽는다.
        self._send_json(200, {"text": text, "language": lang},
                        {"X-Reachy-Gateway": "openai", "X-Reachy-Model": cfg.stt_model})

    def _transcribe_retry(self, file: FormFile, langs: list[str]) -> tuple[str, list[str]]:
        """응답이 늦으면(`slow`) 한 번 더 보낸다 — **[B1 실측]** 27.4초 응답 1/1,940, 다시 보내면 정상. 다시 보내 받으면 경고 한 줄
        (자주 나오면 회선·OpenAI 쪽 문제다), 또 늦으면 호출자가 로컬로 넘기며 경고 한 줄. 연결 실패·HTTP 오류는 다시 보내지 않는다."""
        cfg = self.server.cfg
        for attempt in range(cfg.stt_retries + 1):
            try:
                out = self._transcribe(file, langs, time.monotonic() + cfg.stt_timeout_s)
            except GatewayError as exc:
                if not exc.slow or attempt >= cfg.stt_retries:
                    if exc.slow and attempt:
                        raise GatewayError(f"{attempt + 1}번 모두 {cfg.stt_timeout_s:g}초 안에 응답이 없다", slow=True) from None
                    raise
                continue
            if attempt:
                log.warning("OpenAI STT 응답이 %g초 안에 안 와 한 번 더 보내 받았다(%d번째) — 잦으면 회선·OpenAI 상태를 본다",
                            cfg.stt_timeout_s, attempt + 1)
            return out
        raise AssertionError("도달하지 않는다")

    def _transcribe(self, file: FormFile, langs: list[str], deadline: float) -> tuple[str, list[str]]:
        cfg, pool = self.server.cfg, self.server.shared.pool
        ctype, body = build_multipart([("model", cfg.stt_model), *(("languages[]", c) for c in langs),
                                       *(("keywords[]", k) for k in cfg.stt_keywords),
                                       ("response_format", "json")], file)
        headers = {"Authorization": f"Bearer {cfg.key}", "Content-Type": ctype, "User-Agent": "reachy-gateway"}
        try:
            conn, resp = pool.request("POST", STT_PATH, body, headers, deadline)
        except ResponseTimeout as exc:
            raise GatewayError(str(exc), slow=True) from None
        except (OSError, http.client.HTTPException) as exc:
            raise GatewayError(f"{type(exc).__name__}: {exc}", kind=upstream_kind(exc=exc)) from None
        try:
            set_timeout(conn, max(0.05, deadline - time.monotonic()))
            data = resp.read()
        except TimeoutError as exc:
            conn.close()
            raise GatewayError(f"응답 본문 시간 초과({exc})", slow=True) from None
        except (OSError, http.client.HTTPException) as exc:
            conn.close()
            raise GatewayError(f"{type(exc).__name__}: {exc}", kind=upstream_kind(exc=exc)) from None
        if resp.status != 200:
            conn.close()
            raise GatewayError(f"HTTP {resp.status} {error_summary(data, cfg.key)}", kind=upstream_kind(status=resp.status))
        pool.release(conn, resp)
        try:
            d = json.loads(data.decode("utf-8"))
        except ValueError:
            raise GatewayError("JSON 이 아닌 응답") from None
        codes = [str(x.get("code")).lower() for x in (d.get("languages") or []) if isinstance(x, dict) and x.get("code")]
        return (d.get("text") or "").strip(), codes

    # ── 로컬 통과 ──────────────────────────────────────────────────
    def _no_local(self, message: str, upstream: str | None = None) -> None:
        """외부 전용에서 로컬로 넘길 자리 — 경고 한 줄(키는 지운다) + 502. 로봇·감독은 지금의 실패 경로를 탄다.

        `upstream`(OpenAI 를 불렀다가 실패한 경우만): 실패 **종류**를 본문 `upstream`·머리 `X-Reachy-Upstream` 에 싣는다 —
        예열이 줄마다 "키 / 잔액·한도 / 인터넷" 을 말하게(계획 A-1). OpenAI 를 부르지 않은 502(모르는 경로)에는 싣지 않는다.
        로봇은 502 본문을 읽지 않으므로(예외로만 받는다) 로봇 재배포가 필요 없다."""
        log.warning("%s", scrub(message, self.server.cfg.key))
        body = {"error": "no-local", "detail": "외부 전용(--no-local) — 로컬 서버를 띄우지 않았다"}
        headers = {"X-Reachy-Gateway": "no-local"}
        if upstream:
            body["upstream"] = upstream
            headers["X-Reachy-Upstream"] = upstream
        self._send_json(502, body, headers)

    def _local(self, method: str, raw: bytes | None, tag: str) -> None:
        """안쪽 로컬 서버로 넘기고 응답을 **받는 대로** 돌려준다(스트리밍 LLM 이 모아서 나가면 첫 절이 늦는다)."""
        if self.server.local_host is None:
            self._no_local(f"{self.server.service.upper()} 요청을 넘길 로컬 서버가 없다(외부 전용) — 502: {method} {self.path}")
            return
        t0 = time.monotonic()
        try:
            conn = self._local_conn()
            headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
            conn.request(method, self.path, body=raw, headers=headers)
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            log.warning("로컬 %s 에 못 닿았다(%s: %s) — 502", self.server.service.upper(), type(exc).__name__, exc)
            self._send_json(502, {"error": "local-unreachable", "detail": f"{type(exc).__name__}: {exc}"},
                            {"X-Reachy-Gateway": tag})
            return
        try:
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in _HOP:
                    self.send_header(k, v)
            self.send_header("X-Reachy-Gateway", tag)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            read = getattr(resp, "read1", None) or resp.read
            while True:
                data = read(CHUNK)
                if not data:
                    break
                self._write_chunk(data)
            self._end_chunks()
            if method == "POST":
                log.info("%s %s %.2fs", self.server.service, tag, time.monotonic() - t0)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True          # 로봇이 끊었다(끼어들기)
        except (OSError, http.client.HTTPException) as exc:
            log.warning("로컬 %s 응답이 도중에 끊겼다(%s) — 연결을 끝맺지 않고 닫는다", self.server.service.upper(),
                        type(exc).__name__)
            self.close_connection = True
        finally:
            conn.close()


def make_servers(cfg: Config, host: str, *, llm: tuple[int, str | None] | None = None,
                 stt: tuple[int, str | None] | None = None) -> list[GatewayServer]:
    """리스너를 만든다(띄우지는 않는다). `llm`/`stt` = (포트, 로컬 주소 — None 이면 외부 전용). 테스트가 포트 0 으로 부른다."""
    shared = Shared(cfg)
    out = []
    if llm is not None:
        out.append(GatewayServer((host, llm[0]), "llm", llm[1], cfg, shared))
    if stt is not None:
        out.append(GatewayServer((host, stt[0]), "stt", stt[1], cfg, shared))
    return out


def describe(cfg: Config, servers: list[GatewayServer]) -> list[str]:
    """기동 줄 — 무엇이 어디로 가는지. 키는 설정됨/없음만."""
    lines = []
    for s in servers:
        where = f"{s.server_address[0]}:{s.server_address[1]}"
        local = f"{s.local_host}:{s.local_port}"
        on_fail = f"실패하면 로컬 {local}" if s.local_host else "실패하면 502(외부 전용 — 로컬 폴백 없음)"
        if s.service == "llm":
            if cfg.llm_openai():
                expert = (f"전문가 → {cfg.llm_model_expert}(effort {cfg.llm_effort_expert})" if cfg.llm_model_expert
                          else "전문가 라우팅 없음")
                tier = f", service_tier {cfg.llm_service_tier}" if cfg.llm_service_tier else ""
                lines.append(f"LLM {where} → OpenAI {cfg.llm_model}(effort {cfg.llm_effort}{tier}) · {expert} · "
                             f"{on_fail} · 시간 상한 {cfg.llm_timeout_s:g}초")
            else:
                lines.append(f"LLM {where} → 로컬 {local}(통과)")
        else:
            if cfg.stt_openai():
                kw = (f"키워드 {len(cfg.stt_keywords)}개(예: {', '.join(cfg.stt_keywords[:4])} …)" if cfg.stt_keywords
                      else "키워드 없음")
                lines.append(f"STT {where} → OpenAI {cfg.stt_model}(언어 {','.join(cfg.stt_languages)}, {kw}) · "
                             f"{on_fail} · 시도당 {cfg.stt_timeout_s:g}초 × {cfg.stt_retries + 1}번")
            else:
                lines.append(f"STT {where} → 로컬 {local}(통과)")
    lines.append(f"OpenAI 키 {key_status(cfg.key)}")
    return lines


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="LLM·STT OpenAI 게이트웨이")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--llm-port", type=int, default=None)
    ap.add_argument("--llm-local", default="http://127.0.0.1:8081")
    ap.add_argument("--llm-engine", default=None, choices=ENGINES, help="기본 REACHY_LLM_ENGINE, 없으면 local")
    ap.add_argument("--stt-port", type=int, default=None)
    ap.add_argument("--stt-local", default="http://127.0.0.1:8091")
    ap.add_argument("--stt-engine", default=None, choices=ENGINES, help="기본 REACHY_STT_ENGINE, 없으면 local")
    ap.add_argument("--no-local", action="store_true",
                    help="외부 전용 — 안쪽 로컬 서버 없이(엔진 openai 와 키가 있어야 뜬다, 실패는 502)")
    args = ap.parse_args()
    if args.llm_port is None and args.stt_port is None:
        ap.error("--llm-port 와 --stt-port 중 하나는 있어야 한다")
    try:
        cfg = config_from_env(llm_engine=args.llm_engine, stt_engine=args.stt_engine)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if args.no_local:
        problems = external_only_problems(cfg, [s for s, port in (("llm", args.llm_port), ("stt", args.stt_port))
                                                if port is not None])
        if problems:
            raise SystemExit("외부 전용(--no-local)으로 띄울 수 없다 — " + " / ".join(problems))
    servers = make_servers(cfg, args.host,
                           llm=(args.llm_port, None if args.no_local else args.llm_local)
                           if args.llm_port is not None else None,
                           stt=(args.stt_port, None if args.no_local else args.stt_local)
                           if args.stt_port is not None else None)
    log.info("OpenAI 게이트웨이 — %s", " | ".join(describe(cfg, servers)))
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
