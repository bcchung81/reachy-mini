"""TTS 결과 캐시 프록시 — 로봇이 부르는 TTS 주소(:8099) 앞에 선다.

미리 구운 고정 대사(`scripts/bake_tts.py`)는 **합성 서버를 거치지 않고** 캐시의 PCM 을 그대로
흘리고, 나머지(관람객 답)는 CrispASR 로 **스트리밍 그대로** 넘긴다. 계획
`docs/superpowers/plans/2026-09-25-tts-result-cache.md`.

왜 필요한가: 해설은 사람이 검수한 고정 대본(526문장)인데 공연마다 1.7B 모델로 다시 합성했다
(실측 RTF 0.49~0.94 — 한 건은 6.8초 오디오를 6.37초에 만들어 끊길 여유가 거의 없었다). 두 로봇이
서버 하나를 줄 서서 쓰고, 서버가 붙잡히면 로봇은 로컬 합성기로 물러난다(남자 기계음 결함).
한국어 TTS 를 운영하는 커뮤니티 사례도 같은 대본은 결과 캐시에서 즉시 내보낸다
(`docs/research/2026-09-25-tts-sllm-cases.md`).

왜 결과가 같다고 믿는가: 같은 요청 두 번의 PCM SHA1 이 같다(2026-09-25 실측) — 캐시 재생은
실시간 합성과 바이트 단위로 같은 소리다.

로봇 앱은 아무것도 모른다 — 주소도 응답 형식(`audio/pcm` chunked, 24 kHz)도 그대로다.

**ElevenLabs 엔진**(2026-11-12, 계획 `docs/superpowers/plans/2026-11-12-elevenlabs-tts.md`): `--engine elevenlabs`
(`TTS_ENGINE`)이면 캐시에 없는 문장(관람객 답)을 CrispASR 대신 ElevenLabs 로 합성해 같은 형식으로 흘린다.
키는 이 프로세스만 읽는다(`tts_elevenlabs.load_api_key`). 실패하면 같은 목소리의 미리 구운 안내를 한 번 내고
그 답의 나머지 문장은 짧은 무음으로 넘긴다 — **빈 응답이나 5xx 를 주면 로봇이 로컬 기계음으로 대신 말한다**
(`tts._open_qwen` 의 "첫 청크가 비었다" → 폴백). 엔진을 안 정하면 지금과 똑같이 돈다.

**외부 전용**(2026-11-13, `--no-local` — `reachy.sh` 의 `REACHY_LOCAL_MODELS=off`): 로컬 CrispASR 를 아예 안 띄운 구성.
ElevenLabs 엔진에 키가 있을 때만 뜬다(아니면 기동에서 멈춘다 — 넘길 곳이 없는 프록시가 조용히 502 만 주면 안 된다).
로컬로 넘기던 wav 한 방 요청(로봇의 기동 확인 `session.announce_voice`·예열)은 ElevenLabs 로 만들어 WAV 로 싸 준다.

실행:
    .venv/bin/python tts_cache_proxy.py [--host 127.0.0.1] [--port 8099]
        [--upstream http://127.0.0.1:8098 | --no-local] [--cache-dir ~/.local/share/reachy-mini-tts/cache]
        [--engine crispasr|elevenlabs]
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import http.client
import io
import json
import logging
import os
import pathlib
import threading
import time
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tts_elevenlabs as el

log = logging.getLogger("tts-proxy")

SPEECH_PATH = "/v1/audio/speech"
INDEX_NAME = "index.json"
# 로봇의 읽기 단위(`tts._PCM_CHUNK`)와 같다 — 적중 재생도 실시간 스트림과 같은 모양으로 흐른다.
CHUNK = 4096
# 업스트림 합성 대기. 로봇의 `TTS_QWEN_TIMEOUT`(90초)보다 넉넉히 — 프록시가 먼저 끊으면 로봇은
# 원인을 "서버가 죽었다" 로 오해한다.
UPSTREAM_TIMEOUT_S = 120.0
# 프록시에서 다시 쓰면 안 되는 홉 단위 헤더. 본문 길이·전송 방식은 프록시가 새로 정한다.
_HOP = {"connection", "keep-alive", "transfer-encoding", "content-length", "proxy-connection"}


def default_cache_dir(engine: str = "crispasr") -> pathlib.Path:
    """캐시 위치 — TTS 자산 옆(저장소 밖, 재부팅에도 남는다). `TTS_CACHE_DIR` 로 바꾼다.

    **엔진마다 폴더가 다르다**(crispasr → `cache`, elevenlabs → `cache-elevenlabs`). 캐시 키는 로봇 요청
    본문뿐이라 엔진이 들어가지 않는다 — 같은 폴더를 쓰면 옛 목소리가 그대로 나간다.
    """
    env = os.environ.get("TTS_CACHE_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    assets = os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")
    return pathlib.Path(assets).expanduser() / ("cache" if engine == "crispasr" else f"cache-{engine}")


def cache_key(body: dict) -> str:
    """요청 본문 → 캐시 키. **굽기(`scripts/bake_tts.py`)와 프록시가 이 함수 하나를 같이 쓴다.**

    본문을 파싱해 키 순서를 고정하고 다시 직렬화하므로 필드 순서와 무관하다. 화자·배속·어조가
    하나라도 다르면 다른 키다 — 다른 소리이기 때문이다.
    """
    canon = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def is_cacheable(body: dict) -> bool:
    """캐시 대상 요청인가 — 로봇의 기본 경로(스트리밍 PCM)만. wav 한 방 요청은 늘 통과한다."""
    return body.get("stream") is True and body.get("response_format") == "pcm"


class Cache:
    """캐시 폴더 — `{키}.pcm` 파일과 굽기가 남긴 색인(`index.json`).

    색인은 **지금 대본의 고정 대사 전부**(구웠든 안 구웠든)를 문장 → 굽기 때의 화자·배속·어조로
    적는다. 프록시는 이것으로 드리프트를 잡는다: 고정 대사인데 키가 빗나가면 로봇 설정(화자·배속·
    어조)이 굽기와 달라진 것이고, 그대로 두면 **조용히 전부 빗나간다.** 색인은 파일 mtime 이
    바뀌면 다시 읽는다 — `bake` 뒤 프록시를 다시 띄울 필요가 없다.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        self._lock = threading.Lock()
        self._index_mtime: float | None = None
        self._by_text: dict[str, list[dict]] = {}
        self._engine: str | None = None

    def path(self, key: str) -> pathlib.Path:
        return self.root / f"{key}.pcm"

    def get(self, key: str) -> pathlib.Path | None:
        p = self.path(key)
        return p if p.is_file() and p.stat().st_size > 0 else None

    def count(self) -> int:
        if not self.root.is_dir():
            return 0
        return sum(1 for _ in self.root.glob("*.pcm"))

    def _reload_index(self) -> None:
        p = self.root / INDEX_NAME
        try:
            mtime = p.stat().st_mtime
        except OSError:
            self._by_text, self._index_mtime, self._engine = {}, None, None
            return
        if mtime == self._index_mtime:
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
        except (OSError, ValueError) as exc:
            log.warning("색인을 못 읽었다(%s: %s) — 드리프트 경고 없이 돈다", type(exc).__name__, exc)
            self._by_text, self._index_mtime = {}, mtime
            return
        by_text: dict[str, list[dict]] = {}
        for e in entries:
            by_text.setdefault(e.get("text", ""), []).append(e)
        # 엔진 표지가 없는 색인은 ElevenLabs 이전(2026-11-12 전)에 구운 것 — 곧 CrispASR 다.
        self._by_text, self._index_mtime = by_text, mtime
        self._engine = data.get("engine") or "crispasr"

    def engine(self) -> str | None:
        """이 폴더를 어느 엔진으로 구웠나(색인 표지). 색인이 없으면 None."""
        with self._lock:
            self._reload_index()
            return self._engine

    def baked_for(self, text: str) -> list[dict]:
        """이 문장을 굽기가 어떤 설정으로 구웠(거나 구울 예정이)었나. 고정 대사가 아니면 빈 목록."""
        with self._lock:
            self._reload_index()
            return list(self._by_text.get(text, ()))


def drift_message(body: dict, baked: list[dict]) -> str:
    """고정 대사인데 빗나간 요청 — 굽기와 무엇이 다른지 한 줄로."""
    want = {k: body.get(k) for k in ("voice", "speed", "instructions")}
    have = [{k: e.get(k) for k in ("voice", "speed", "instructions")} for e in baked]
    return (
        f"고정 대사인데 캐시 키가 다르다 — 로봇 설정이 굽기와 다르다(요청 {want} / 굽기 {have}). "
        "로봇 설정을 되돌리거나 ./reachy.sh bake 로 다시 굽는다"
    )


class Stats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.drifts = 0
        self.el_ok = 0        # ElevenLabs 로 합성해 흘린 관람객 답 문장
        self.el_fail = 0      # ElevenLabs 실패 — 실패 정책으로 넘긴 문장

    def add(self, field: str) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def snapshot(self) -> dict:
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "drifts": self.drifts,
                    "el_ok": self.el_ok, "el_fail": self.el_fail}


# 실패 정책 ① 에서 안내 뒤 나머지 문장에 보내는 무음. **0 바이트면 안 된다** — 로봇은 첫 청크가 비면
# "서버가 죽었다" 로 보고 로컬 합성기(say/espeak, 다른 목소리)로 대신 말한다(`tts._open_qwen`).
SILENCE_S = 0.15


def upstream_kind(exc: BaseException) -> str:
    """외부 전용 wav 502 에 싣는 실패 **종류** — `openai_gateway.upstream_kind` 와 같은 이름·같은 갈래다(예열이 두 서버의
    502 를 한 표로 읽는다, 계획 2026-11-14 A-1). 종류만 싣고 키는 어디에도 싣지 않는다.

    `ElevenLabsError.status == 0` 은 연결 실패와 시간 초과를 같이 담는다(`tts_elevenlabs.open_stream`) — 메시지의
    "timed out" 으로 가른다. 401 은 키 문제지만 ElevenLabs 는 크레딧이 바닥나도 401 을 줄 수 있어(실측 안 함) 예열은
    401 줄에 크레딧 줄을 같이 보라고 쓴다."""
    status = getattr(exc, "status", None) if isinstance(exc, el.ElevenLabsError) else None
    if status is not None and status != 0:
        if status in (401, 429):
            return str(status)
        if 500 <= status < 600:
            return "5xx"
        if 400 <= status < 500:
            return "4xx"
        return "other"
    if status == 0:
        return "timeout" if "timed out" in str(exc).lower() or "timeout" in str(exc).lower() else "connect"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, OSError):
        return "connect"
    return "other"                      # 목소리 매핑 없음(VoiceNotMapped) 등 — 설정 문제, 예열은 로그 경로를 가리킨다


@dataclasses.dataclass
class ElevenLabsLive:
    """캐시에 없는 문장(관람객 답)을 ElevenLabs 로 — 프록시의 실시간 경로 설정."""

    key: str
    voices: dict
    model: str = el.MODEL_LIVE
    readings: list = dataclasses.field(default_factory=list)
    language_code: str | None = el.LANGUAGE
    on_fail: str = "notice"            # notice(같은 목소리 안내 한 번 + 무음) | local(CrispASR 로, 목소리가 바뀐다)
    notice_window_s: float = 15.0      # 이 시간 안의 연속 실패는 한 번의 끊김으로 본다 — 안내는 한 번만
    open_timeout_s: float = 15.0
    base: str | None = None            # 테스트의 가짜 서버


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, upstream: str | None, cache: Cache, el_live: ElevenLabsLive | None = None) -> None:
        super().__init__(addr, Handler)
        # upstream=None — 외부 전용(로컬 CrispASR 없음). 넘기던 자리는 `_pass` 가 502 로, wav 요청은 `_el_wav` 가 받는다.
        u = urllib.parse.urlsplit(upstream) if upstream else None
        self.upstream_host = (u.hostname or "127.0.0.1") if u else None
        self.upstream_port = (u.port or 80) if u else 0
        self.cache = cache
        self.stats = Stats()
        # 드리프트 경고는 문장마다 한 번 — 공연 내내 같은 줄이 반복되면 진짜 신호가 묻힌다.
        self.drift_warned: set[str] = set()
        self.drift_lock = threading.Lock()
        self.el = el_live
        self.el_last_fail = float("-inf")   # 마지막 ElevenLabs 실패 시각(monotonic) — 안내를 한 번만 내려고


class Handler(BaseHTTPRequestHandler):
    server: ProxyServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 요청마다 찍는 기본 접근 로그는 끈다 — 아래에서 필요한 것만
        return

    # ── 공용 ──────────────────────────────────────────────────────
    def _send_json(self, status: int, obj: dict, extra: dict | None = None) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def _write_chunk(self, data: bytes) -> None:
        self.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")

    def _end_chunks(self) -> None:
        self.wfile.write(b"0\r\n\r\n")

    def _upstream(self) -> http.client.HTTPConnection:
        return http.client.HTTPConnection(
            self.server.upstream_host, self.server.upstream_port, timeout=UPSTREAM_TIMEOUT_S
        )

    # ── GET ───────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._health()
            return
        if self.path == "/cache/stats":
            self._send_json(200, {"proxy": "tts-cache", "cache_entries": self.server.cache.count(),
                                  **self.server.stats.snapshot()})
            return
        self._pass("GET", None)

    def _health(self) -> None:
        """업스트림이 살아 있을 때만 200. `reachy.sh` 의 기동 대기·로봇 도달 확인이 이것을 본다.

        `proxy` 표지를 싣는다 — `:8099` 가 떠 있는데 표지가 없으면 옛 구성(CrispASR 직결)이다.
        """
        base = {"proxy": "tts-cache", "cache_entries": self.server.cache.count(),
                "engine": "elevenlabs" if self.server.el else "crispasr",
                **self.server.stats.snapshot()}
        if self.server.upstream_host is None:
            # 외부 전용 — 물어볼 로컬이 없다. 기동이 "ElevenLabs + 키" 를 확인했으니 200(외부는 부르지 않는다).
            # `"local": "off"` 는 `reachy.sh` 가 "외부 전용 프록시가 떠 있나" 를 가르는 표지다 — 모양을 바꾸면 거기도 바꾼다.
            if self.server.el:
                self._send_json(200, {"status": "ok", "key": el.key_status(self.server.el.key), "local": "off", **base})
            else:
                self._send_json(503, {"status": "no-engine", "local": "off", **base})
            return
        try:
            conn = self._upstream()
            conn.timeout = 3.0
            conn.request("GET", "/health")
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            if self.server.el:
                # 합성은 ElevenLabs 가 한다 — 로컬 CrispASR 는 wav 요청·`local` 폴백용이라 없어도 선다.
                # 외부는 부르지 않는다(헬스는 자주 불린다). 키가 있다는 것만 확인됐다.
                self._send_json(200, {"status": "ok", "key": el.key_status(self.server.el.key),
                                      "local": f"down({type(exc).__name__})", **base})
                return
            self._send_json(503, {"status": "upstream-down", "detail": f"{type(exc).__name__}: {exc}", **base})
            return
        try:
            upstream = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            upstream = {"status": "?"}
        self._send_json(resp.status, {**upstream, **base})

    # ── POST ──────────────────────────────────────────────────────
    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if self.path != SPEECH_PATH:
            self._pass("POST", raw)
            return
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            self._pass("POST", raw)            # 우리가 판단할 일이 아니다 — 서버가 거절하게 둔다
            return
        if not isinstance(body, dict) or not is_cacheable(body):
            if self.server.upstream_host is None and self.server.el is not None and isinstance(body, dict):
                self._el_wav(body)             # 외부 전용 — 넘길 로컬이 없다
                return
            self._pass("POST", raw, cache_tag="skip")
            return
        key = cache_key(body)
        hit = self.server.cache.get(key)
        if hit is not None:
            self._serve_hit(hit, body)
            return
        text = str(body.get("input", ""))
        baked = self.server.cache.baked_for(text)
        if baked:
            # 고정 대사인데 빗나갔다 — 설정 드리프트거나 아직 안 구웠다. 둘을 가른다.
            if any(e.get("key") == key for e in baked):
                self._note_once(text, f"아직 안 구운 고정 대사다 — ./reachy.sh bake: {text[:40]!r}")
            else:
                self.server.stats.add("drifts")
                self._note_once(text, drift_message(body, baked))
        self.server.stats.add("misses")
        log.info("miss %s %r", body.get("voice"), text[:40])
        if self.server.el is not None:
            self._el_speak(body, raw)
            return
        self._pass("POST", raw, cache_tag="miss")

    def _note_once(self, text: str, message: str) -> None:
        with self.server.drift_lock:
            if text in self.server.drift_warned:
                return
            self.server.drift_warned.add(text)
        log.warning(message)

    def _serve_hit(self, path: pathlib.Path, body: dict) -> None:
        self.server.stats.add("hits")
        log.info("hit %s %r", body.get("voice"), str(body.get("input", ""))[:40])
        with open(path, "rb") as f:
            self._serve_pcm(lambda: f.read(CHUNK), tag="hit")

    def _pcm_headers(self, tag: str, engine: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("X-TTS-Cache", tag)
        if engine:
            self.send_header("X-TTS-Engine", engine)
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def _serve_pcm(self, read, tag: str, engine: str | None = None, transform=None) -> None:
        """PCM 을 청크로 흘린다. **샘플(2바이트) 경계를 맞춰** 보낸다 — 로봇도 맞추지만, 홀수 청크를 받는
        다른 재생기가 잡음을 내지 않게."""
        self._pcm_headers(tag, engine)
        carry = b""
        try:
            while True:
                data = read()
                if not data:
                    break
                data = carry + data
                cut = len(data) - (len(data) % 2)
                carry = data[cut:]
                if cut:
                    self._write_chunk(transform(data[:cut]) if transform else data[:cut])
            self._end_chunks()
        except (BrokenPipeError, ConnectionResetError):
            # 로봇이 끼어들기로 끊었다 — 정상이다. 더 쓸 곳이 없을 뿐이다.
            pass

    # ── ElevenLabs(관람객 답) ──────────────────────────────────────
    def _el_speak(self, body: dict, raw: bytes) -> None:
        """캐시에 없는 문장을 ElevenLabs 로 합성해 **받는 대로** 흘린다(모아서 보내면 첫 소리가 늦는다)."""
        cfg = self.server.el
        if body.get("instructions"):
            self._note_once("\0instructions", "로봇 요청의 어조 지시(instructions)는 ElevenLabs 로 보내지 않는다 — 오디션으로 고른 "
                            f"목소리가 어조를 맡는다(예: {str(body.get('instructions'))[:30]!r}). 이 경고는 한 번만 낸다")
        try:
            vid, payload = el.el_request(body, voices=cfg.voices, model=cfg.model, readings=cfg.readings,
                                         language_code=cfg.language_code)
        except el.VoiceNotMapped as exc:
            self._el_failed(body, raw, str(exc))
            return
        resp = None
        for attempt in range(2):
            try:
                resp = el.open_stream(vid, payload, cfg.key, timeout=cfg.open_timeout_s, base=cfg.base)
                break
            except el.ElevenLabsError as exc:
                # 409(목소리 첫 사용이 겹침)·429(동시 요청 초과)·5xx 는 한 번만 짧게 다시 — 관람객이 기다린다.
                if attempt == 0 and exc.status in el._RETRY_STATUS:
                    time.sleep(0.3)
                    continue
                self._el_failed(body, raw, str(exc))
                return
        self.server.stats.add("el_ok")
        read = getattr(resp, "read1", None) or resp.read
        with resp:
            try:
                # 굽기와 같은 여유 음량 — 고정 대사와 관람객 답의 음량이 같아야 하고, 실기 16 kHz 변환에서 안 잘린다.
                self._serve_pcm(lambda: read(CHUNK), tag="miss", engine="elevenlabs", transform=el.apply_gain)
            except (OSError, http.client.HTTPException) as exc:
                # 머리를 보낸 뒤 끊겼다 — 받은 데까지는 이미 로봇이 말했다. 되돌릴 수 없으니 남기기만 한다.
                log.warning("ElevenLabs 스트림이 도중에 끊겼다(%s) — 그 문장은 받은 데까지만 나갔다", type(exc).__name__)

    def _el_failed(self, body: dict, raw: bytes, reason: str) -> None:
        """실패 정책. notice: 같은 목소리 안내를 끊김 한 번에 한 번 + 나머지는 짧은 무음. local: CrispASR 로."""
        cfg = self.server.el
        self.server.stats.add("el_fail")
        if cfg.on_fail == "local":
            log.warning("ElevenLabs 실패 — 로컬 TTS(CrispASR)로 넘긴다, 목소리가 바뀐다: %s", reason)
            self._pass("POST", raw, cache_tag="fallback-local")
            return
        now = time.monotonic()
        with self.server.drift_lock:
            first = now - self.server.el_last_fail >= cfg.notice_window_s
            self.server.el_last_fail = now
        if first:
            log.warning("ElevenLabs 실패 — 같은 목소리 안내를 한 번 내고 이 답은 넘긴다: %s", reason)
            clip = self._notice_clip(body)
            if clip is not None:
                with open(clip, "rb") as f:
                    self._serve_pcm(lambda: f.read(CHUNK), tag="notice", engine="elevenlabs")
                return
            log.warning("연결 불안정 안내가 캐시에 없다 — 무음으로 넘긴다. TTS_ENGINE=elevenlabs ./reachy.sh bake")
        silence = [b"\x00\x00" * int(el.PCM_RATE * SILENCE_S)]
        self._serve_pcm(lambda: silence.pop() if silence else b"", tag="skip", engine="elevenlabs")

    def _el_wav(self, body: dict) -> None:
        """wav 한 방 요청 — 외부 전용이라 넘길 로컬 TTS 가 없다. ElevenLabs 로 끝까지 받아 WAV 로 싸서 준다.

        누가 부르나: 로봇 앱의 기동 확인(`session.announce_voice` 의 `_qwen_synth("준비")`)과 예열(`scripts/warmup.py`).
        관람객이 듣는 경로가 아니다(로봇의 말은 스트리밍 PCM — 위의 캐시·`_el_speak`). 그래서 실패는 안내·무음이 아니라
        **502** 다 — 로봇 기동 로그의 "응답 없음" 과 예열의 "건너뜀" 으로 드러난다. 여기서 502 를 숨기면 시연 직전에
        "ElevenLabs 가 안 된다" 를 알 길이 없다.
        """
        cfg = self.server.el
        t0 = time.monotonic()
        try:
            vid, payload = el.el_request(body, voices=cfg.voices, model=cfg.model, readings=cfg.readings,
                                         language_code=cfg.language_code)
            pcm = el.synth(vid, payload, cfg.key, timeout=cfg.open_timeout_s, base=cfg.base, retries=1)
        except (el.VoiceNotMapped, el.ElevenLabsError, OSError, http.client.HTTPException) as exc:
            # OSError·HTTPException: `synth` 는 머리를 받은 뒤 본문을 읽다 끊긴 것(시간 초과 포함)을 감싸지 않는다 —
            # 안 잡으면 처리기가 죽어 502 도 없이 연결이 끊기고, 예열은 원인 없는 "건너뜀" 만 찍는다.
            kind = upstream_kind(exc)
            self.server.stats.add("el_fail")
            log.warning("wav 요청(로봇 기동 확인·예열)을 ElevenLabs 로 못 만들었다(%s) — 502: %s", kind, exc)
            self._send_json(502, {"error": "elevenlabs-failed", "upstream": kind, "detail": str(exc)},
                            {"X-Reachy-Upstream": kind})
            return
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(el.PCM_RATE)
            w.writeframes(el.apply_gain(pcm[: len(pcm) - len(pcm) % 2]))
        data = buf.getvalue()
        log.info("wav(로봇 기동 확인·예열) elevenlabs %s %r %.2fs", body.get("voice"), str(body.get("input", ""))[:20],
                 time.monotonic() - t0)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-TTS-Cache", "skip")
        self.send_header("X-TTS-Engine", "elevenlabs")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(data)

    def _notice_clip(self, body: dict) -> pathlib.Path | None:
        """실패한 요청과 **같은 목소리**로 구운 안내. 어조가 달라도 목소리만 맞으면 쓴다."""
        voice = body.get("voice")
        for e in self.server.cache.baked_for(el.NOTICE_TEXT):
            if e.get("voice") == voice:
                p = self.server.cache.get(e.get("key", ""))
                if p is not None:
                    return p
        return None

    # ── 통과 ──────────────────────────────────────────────────────
    def _pass(self, method: str, raw: bytes | None, cache_tag: str | None = None) -> None:
        """업스트림으로 넘기고 응답을 **받는 대로** 돌려준다 — 모아서 보내면 관람객 답의 첫 소리가
        합성 전체 시간만큼 늦는다(로봇 실측: 비스트리밍이면 77자 3.67초)."""
        if self.server.upstream_host is None:
            log.warning("로컬 TTS 로 넘길 요청인데 외부 전용이라 로컬이 없다 — 502: %s %s", method, self.path)
            self._send_json(502, {"error": "no-local", "detail": "외부 전용(--no-local) — 로컬 TTS 를 띄우지 않았다"})
            return
        try:
            conn = self._upstream()
            headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
            conn.request(method, self.path, body=raw, headers=headers)
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            log.warning("업스트림에 못 닿았다(%s: %s) — 502", type(exc).__name__, exc)
            self._send_json(502, {"error": "upstream-unreachable", "detail": f"{type(exc).__name__}: {exc}"})
            return
        try:
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in _HOP:
                    self.send_header(k, v)
            if cache_tag:
                self.send_header("X-TTS-Cache", cache_tag)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            read = getattr(resp, "read1", None) or resp.read
            while True:
                data = read(CHUNK)
                if not data:
                    break
                self._write_chunk(data)
            self._end_chunks()
        except (BrokenPipeError, ConnectionResetError):
            pass  # 로봇이 끊었다(끼어들기). 서버는 끝까지 합성한다 — 지금과 같다
        finally:
            conn.close()


def make_live(engine: str, env: dict | None = None, *, local: bool = True) -> tuple[str, ElevenLabsLive | None]:
    """기동 때 실제로 쓸 (엔진, 실시간 경로). elevenlabs 인데 키가 없으면 **경고하고 crispasr 로**.

    `local=False`(외부 전용 — 로컬 CrispASR 없음)이면 물러날 곳이 없다: elevenlabs 가 아니거나 키가 없거나 실패 정책이
    `local` 이면 **멈춘다**(SystemExit). 띄워 놓고 요청마다 502 를 주면 로봇이 기계음으로 말하고 원인은 로그 속에 묻힌다.

    따로 뺀 이유: 이 분기가 `main()` 안에만 있으면 테스트할 수 없다(서버가 뜬다) — "키 없이 켜면 조용히 Qwen 으로 돈다" 가
    시연장에서 "목소리가 왜 바뀌었나" 로만 드러나는 사고를 테스트로 막는다.
    """
    env = os.environ if env is None else env
    if engine != "elevenlabs":
        if not local:
            raise SystemExit(f"외부 전용(--no-local)인데 TTS 엔진이 {engine} 다 — TTS_ENGINE=elevenlabs 여야 한다")
        return engine, None
    key = el.load_api_key(env)
    if not key:
        if not local:
            raise SystemExit("외부 전용(--no-local)인데 ElevenLabs 키가 없다(ELEVENLABS_API_KEY 또는 저장소 루트 .env) "
                             "— 넘길 로컬 TTS 가 없어 띄우지 않는다")
        log.warning("TTS_ENGINE=elevenlabs 인데 ElevenLabs 키가 없다(ELEVENLABS_API_KEY 또는 저장소 루트 .env) "
                    "— 로컬 CrispASR 로 돈다")
        return "crispasr", None
    on_fail = (env.get("TTS_EL_ON_FAIL") or "notice").strip().lower()
    if on_fail not in ("notice", "local"):
        raise SystemExit(f"TTS_EL_ON_FAIL 은 notice/local 중 하나다: {on_fail!r}")
    if on_fail == "local" and not local:
        raise SystemExit("TTS_EL_ON_FAIL=local 은 로컬 TTS 가 있어야 한다 — 외부 전용(--no-local)에서는 notice 만 된다")
    return engine, ElevenLabsLive(key=key, voices=el.voice_map(env),
                                  model=env.get("TTS_EL_MODEL_LIVE") or el.MODEL_LIVE,
                                  readings=el.load_readings(), on_fail=on_fail)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="TTS 결과 캐시 프록시")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--upstream", default="http://127.0.0.1:8098")
    ap.add_argument("--no-local", action="store_true",
                    help="외부 전용 — 로컬 CrispASR 없이(ElevenLabs 엔진과 키가 있어야 뜬다)")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--engine", default=None, choices=el.ENGINES,
                    help="캐시에 없는 문장을 누가 합성하나(기본 TTS_ENGINE, 없으면 crispasr)")
    args = ap.parse_args()
    engine, live = make_live(args.engine or el.engine_from_env(), local=not args.no_local)
    upstream = None if args.no_local else args.upstream
    cache = Cache(pathlib.Path(args.cache_dir).expanduser() if args.cache_dir else default_cache_dir(engine))
    baked_by = cache.engine()
    if live:
        try:
            g = json.loads((cache.root / INDEX_NAME).read_text(encoding="utf-8")).get("gain_db")
        except (OSError, ValueError):
            g = None
        if cache.count() and (g is None or abs(float(g) - el.GAIN_DB) > 1e-6):
            log.warning("구운 대사의 이득(%s dB)과 관람객 답의 이득(%+.1f dB)이 다르다 — 음량이 섞인다. "
                        "TTS_ENGINE=elevenlabs ./reachy.sh bake --regain", g, el.GAIN_DB)
    if baked_by and baked_by != engine:
        log.warning("캐시 폴더는 %s 로 구웠는데 엔진은 %s 다 — 구운 대사와 관람객 답의 목소리가 다르다. "
                    "TTS_CACHE_DIR 를 엔진에 맞춘다(%s)", baked_by, engine, default_cache_dir(engine))
    srv = ProxyServer((args.host, args.port), upstream, cache, live)
    log.info("TTS 캐시 프록시 %s:%d → %s · 엔진 %s · 캐시 %s(%d개, 구운 엔진 %s)",
             args.host, args.port, upstream or "로컬 없음(외부 전용)", engine, cache.root, cache.count(),
             baked_by or "없음")
    if live:
        log.info("ElevenLabs 키 %s · 목소리 %s · 모델 %s · 읽기 표기 %d개 · 실패 정책 %s",
                 el.key_status(live.key), live.voices, live.model, len(live.readings), live.on_fail)
    srv.serve_forever()


if __name__ == "__main__":
    main()
