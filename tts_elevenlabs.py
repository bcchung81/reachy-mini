"""ElevenLabs 어댑터 — 로봇의 TTS 요청 본문을 ElevenLabs 요청으로 바꾸고 PCM 을 받는다.

계획 `docs/superpowers/plans/2026-11-12-elevenlabs-tts.md`. **PC 쪽에서만 쓴다**(캐시 프록시·굽기·오디션).
로봇 앱은 이 파일을 모른다 — 로봇은 지금처럼 PC 주소에 Qwen 형식 본문을 보내고, 번역은 PC 가 한다.

키를 다루는 규칙(공개 저장소라 어기면 그대로 새어 나간다):
- 키는 환경변수 `ELEVENLABS_API_KEY` 가 먼저, 없으면 저장소 루트 `.env` 에서 **그 한 줄만** 읽는다.
  `.env` 를 셸에 `source` 하지 않는 이유: 그러면 그 셸이 띄우는 앱·로봇 쪽 프로세스까지 키를 물려받는다.
- 키 값은 로그·예외 메시지·반환값 어디에도 싣지 않는다. 남기는 것은 "설정됨/없음" 뿐이다.

ElevenLabs 쪽 사실(2026-11-12, 이 계정 API 로 확인 — 계획서 「실측한 사실」):
- 출력은 `pcm_24000` 을 **반드시 지정**한다. 기본은 MP3 라 로봇이 잡음으로 튼다.
- `eleven_v4` 글자당 1.0 크레딧, `eleven_v4_turbo` 0.5 크레딧. Creator 월 131,000 크레딧, 초과 사용 불가.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
KEY_ENV = "ELEVENLABS_API_KEY"
# 테스트가 가짜 서버를 세우는 자리이기도 하다 — 운영에서는 바꿀 일이 없다.
API_BASE = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io")
PCM_FORMAT = "pcm_24000"          # 로봇이 받는 형식(24 kHz · s16le · mono) — tts.QWEN_PCM_RATE 와 같다
PCM_RATE = 24000
# **[결정 2026-11-12 오디션]** 고정 대사도 Turbo — 관람객 답(Turbo)과 같은 소리로 이어지고 크레딧이 절반이다.
MODEL_BAKE = "eleven_v4_turbo"
MODEL_LIVE = "eleven_v4_turbo"    # 관람객 답 — 첫 소리가 빠르다
# **[결정 2026-11-12 오디션]** 사회자 Juan, 도슨트 Yooni(둘 다 라이브러리 목소리, 예고 기간 730일).
# 키는 로봇이 보내는 목소리 이름이다(`main.ROLE_VOICE` — 사회자 serena, 도슨트 sohee). 로봇 설정은 그대로 두고
# PC 가 이름을 ElevenLabs 목소리로 바꾼다. 다른 목소리로 바꿀 때는 `TTS_EL_VOICES` 로(그리고 다시 굽는다).
DEFAULT_VOICES = {"serena": "hjCvGtSCRPyjYwe2lDf1", "sohee": "n2fbxG88jqAoaVPUy3IG"}
LANGUAGE = "ko"
ENGINES = ("crispasr", "elevenlabs")
# 관람객 답을 합성하다 ElevenLabs 가 실패했을 때 같은 목소리로 한 번 내는 안내(결정 2026-11-12: 실패 정책 ①).
# 굽기가 역할마다 미리 굽는다. **한 문장**이어야 한다 — 프록시가 한 파일로 꺼내 쓴다.
NOTICE_TEXT = "잠시 연결이 불안정해서 다음으로 넘어갈게요."
CREDITS_PER_CHAR = {"eleven_v4": 1.0, "eleven_v4_turbo": 0.5}   # GET /v1/models 의 character_cost_multiplier
READINGS_PATH = ROOT / "data" / "tts_readings.yaml"
# 다시 시도할 상태 — 동시 요청 초과(429), 서버 쪽 일시 오류, 그리고 409.
# **409 `already_running`**: 라이브러리 목소리는 처음 쓰는 순간 계정의 "내 목소리"에 자동으로 추가되는데,
# 같은 목소리로 첫 요청이 동시에 들어가면 추가 작업끼리 부딪혀 409 가 난다(2026-11-12 오디션에서 140건 중
# 21건). 잠깐 뒤 다시 하면 된다. 그 밖의 4xx 는 다시 해도 같다.
_RETRY_STATUS = {409, 429, 500, 502, 503, 504}


class ElevenLabsError(RuntimeError):
    """ElevenLabs 호출 실패. **메시지에 키가 들어가지 않는다** — 상태 코드와 서버 오류 요약만."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"ElevenLabs {status or '연결 실패'}: {message}")
        self.status = status


class VoiceNotMapped(ValueError):
    """로봇이 보낸 목소리 이름에 대응하는 ElevenLabs 목소리가 없다 — 조용히 아무 목소리로 내지 않는다."""


# ── 키 ─────────────────────────────────────────────────────────────
def load_api_key(env: dict | None = None, env_file: pathlib.Path | None = None) -> str | None:
    """키를 찾는다 — 환경변수가 먼저, 없으면 `.env` 의 `ELEVENLABS_API_KEY=` 한 줄. 없으면 None."""
    env = os.environ if env is None else env
    v = (env.get(KEY_ENV) or "").strip()
    if v:
        return v
    path = env_file or pathlib.Path(env.get("ELEVENLABS_ENV_FILE") or ROOT / ".env")
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


# ── 목소리·읽기 표기 ───────────────────────────────────────────────
def parse_voice_map(spec: str) -> dict[str, str]:
    """`"serena=<id>,sohee=<id>"` → {로봇 목소리 이름: ElevenLabs 목소리 ID}."""
    out: dict[str, str] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, vid = part.partition("=")
        if not sep or not name.strip() or not vid.strip():
            raise ValueError(f"TTS_EL_VOICES 형식이 틀렸다(이름=ID 를 쉼표로): {part!r}")
        out[name.strip()] = vid.strip()
    return out


def voice_map(env: dict | None = None) -> dict[str, str]:
    """`TTS_EL_VOICES` 가 있으면 그것, 없으면 오디션으로 정한 기본값."""
    env = os.environ if env is None else env
    spec = (env.get("TTS_EL_VOICES") or "").strip()
    return parse_voice_map(spec) if spec else dict(DEFAULT_VOICES)


def engine_from_env(env: dict | None = None) -> str:
    """`TTS_ENGINE` — 기본 `crispasr`(지금 구성). 모르는 값은 조용히 넘기지 않고 멈춘다."""
    env = os.environ if env is None else env
    v = (env.get("TTS_ENGINE") or "crispasr").strip().lower()
    if v not in ENGINES:
        raise ValueError(f"TTS_ENGINE 은 {'/'.join(ENGINES)} 중 하나다: {v!r}")
    return v


def seed_for(cache_key: str) -> int:
    """문장마다 고정한 시드 — 같은 문장을 다시 구워도 가능한 한 같은 테이크가 나오게(ElevenLabs 는 '최선'만 약속한다)."""
    return int(cache_key[:8], 16) & 0x7FFFFFFF


def load_readings(path: pathlib.Path = READINGS_PATH) -> list[tuple[str, str]]:
    """읽기 표기 사전 — 원문 낱말 → 소리 내 읽는 표기. **긴 낱말부터** 바꾼다(겹치는 짧은 낱말이 먼저
    바뀌면 긴 낱말이 깨진다). 파일이 없으면 빈 사전이다 — 표기 없이도 합성은 된다."""
    try:
        import yaml
        data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return []
    items = (data.get("readings") or {}) if isinstance(data, dict) else {}
    pairs = [(str(k), str(v)) for k, v in items.items() if str(k)]
    return sorted(pairs, key=lambda kv: -len(kv[0]))


def apply_readings(text: str, readings: list[tuple[str, str]]) -> str:
    for src, dst in readings:
        text = text.replace(src, dst)
    return text


def el_request(body: dict, *, voices: dict[str, str], model: str,
               readings: list[tuple[str, str]] = (), seed: int | None = None,
               language_code: str | None = None) -> tuple[str, dict]:
    """로봇 본문(`tts._qwen_body` 모양) → (목소리 ID, ElevenLabs 본문).

    **캐시 키는 이 결과가 아니라 로봇 본문으로 계산한다**(`tts_cache_proxy.cache_key`) — 읽기 표기나
    모델을 바꿔도 로봇이 보내는 요청은 같기 때문이다. `speed`·`instructions` 는 여기서 쓰지 않는다
    (v4 는 속도 숫자가 없고, 어조 스위치는 기본 꺼짐 — 계획서 「번역」).
    """
    name = str(body.get("voice") or "")
    vid = voices.get(name)
    if not vid:
        raise VoiceNotMapped(
            f"로봇 목소리 {name!r} 에 대응하는 ElevenLabs 목소리가 없다 — "
            f"TTS_EL_VOICES 에 '{name}=<목소리 ID>' 를 넣는다(지금: {sorted(voices) or '비었음'})"
        )
    payload: dict = {"text": apply_readings(str(body.get("input", "")), list(readings)), "model_id": model}
    if language_code:
        payload["language_code"] = language_code
    if seed is not None:
        payload["seed"] = int(seed)
    return vid, payload


# ── 호출 ───────────────────────────────────────────────────────────
def _error_summary(raw: bytes) -> str:
    """서버 오류 본문에서 사람이 읽을 요약만 꺼낸다(본문 전체를 싣지 않는다)."""
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return raw[:200].decode("utf-8", "replace")
    det = d.get("detail", d) if isinstance(d, dict) else d
    if isinstance(det, dict):
        return f"{det.get('status') or det.get('code') or ''} {det.get('message') or ''}".strip()[:300]
    return str(det)[:300]


def open_stream(voice_id: str, payload: dict, key: str, *, timeout: float = 60.0,
                base: str | None = None):
    """스트리밍 합성 요청을 열어 응답 객체를 돌려준다 — 본문(PCM)은 호출자가 받는 대로 읽는다.
    2xx 가 아니면 ElevenLabsError(키는 메시지에 없다)."""
    base = (base or API_BASE).rstrip("/")
    url = (f"{base}/v1/text-to-speech/{urllib.parse.quote(voice_id, safe='')}/stream"
           f"?output_format={PCM_FORMAT}")
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/pcm"},
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise ElevenLabsError(exc.code, _error_summary(exc.read())) from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ElevenLabsError(0, f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}") from None


def synth(voice_id: str, payload: dict, key: str, *, timeout: float = 120.0, base: str | None = None,
          retries: int = 3, sleep=time.sleep) -> bytes:
    """PCM 을 끝까지 받는다(굽기·오디션). 429·5xx·연결 실패는 1·2·4초 쉬고 다시 — 그 밖의 4xx 는 바로 실패."""
    for attempt in range(retries + 1):
        try:
            with open_stream(voice_id, payload, key, timeout=timeout, base=base) as r:
                data = r.read()
            if not data:
                raise ElevenLabsError(200, "빈 응답")
            return data
        except ElevenLabsError as exc:
            if attempt >= retries or (exc.status and exc.status not in _RETRY_STATUS):
                raise
            sleep(2 ** attempt)
    raise AssertionError("도달하지 않는다")


def _get_json(path: str, key: str, *, base: str | None = None, timeout: float = 20.0) -> dict:
    base = (base or API_BASE).rstrip("/")
    req = urllib.request.Request(base + path, headers={"xi-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ElevenLabsError(exc.code, _error_summary(exc.read())) from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ElevenLabsError(0, f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}") from None


def credits_left(key: str, *, base: str | None = None) -> tuple[int, int]:
    """(이번 달 쓴 크레딧, 한도). 굽기 전에 모자라면 멈추는 데 쓴다."""
    d = _get_json("/v1/user/subscription", key, base=base)
    return int(d.get("character_count") or 0), int(d.get("character_limit") or 0)


def credits_for(text: str, model: str) -> float:
    """이 글을 이 모델로 합성할 때 드는 크레딧(어림 — 서버는 글자 수 × 모델 배수로 센다)."""
    return len(text) * CREDITS_PER_CHAR.get(model, 1.0)


def pcm_seconds(pcm: bytes) -> float:
    return len(pcm) / 2 / PCM_RATE
