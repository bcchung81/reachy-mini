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

실행:
    .venv/bin/python tts_cache_proxy.py [--host 127.0.0.1] [--port 8099]
        [--upstream http://127.0.0.1:8098] [--cache-dir ~/.local/share/reachy-mini-tts/cache]
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import logging
import os
import pathlib
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def default_cache_dir() -> pathlib.Path:
    """캐시 위치 — TTS 자산 옆(저장소 밖, 재부팅에도 남는다). `TTS_CACHE_DIR` 로 바꾼다."""
    env = os.environ.get("TTS_CACHE_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    assets = os.environ.get("TTS_ASSETS", "~/.local/share/reachy-mini-tts")
    return pathlib.Path(assets).expanduser() / "cache"


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
            self._by_text, self._index_mtime = {}, None
            return
        if mtime == self._index_mtime:
            return
        try:
            entries = json.loads(p.read_text(encoding="utf-8")).get("entries", [])
        except (OSError, ValueError) as exc:
            log.warning("색인을 못 읽었다(%s: %s) — 드리프트 경고 없이 돈다", type(exc).__name__, exc)
            self._by_text, self._index_mtime = {}, mtime
            return
        by_text: dict[str, list[dict]] = {}
        for e in entries:
            by_text.setdefault(e.get("text", ""), []).append(e)
        self._by_text, self._index_mtime = by_text, mtime

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

    def add(self, field: str) -> None:
        with self._lock:
            setattr(self, field, getattr(self, field) + 1)

    def snapshot(self) -> dict:
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "drifts": self.drifts}


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, upstream: str, cache: Cache) -> None:
        super().__init__(addr, Handler)
        u = urllib.parse.urlsplit(upstream)
        self.upstream_host = u.hostname or "127.0.0.1"
        self.upstream_port = u.port or 80
        self.cache = cache
        self.stats = Stats()
        # 드리프트 경고는 문장마다 한 번 — 공연 내내 같은 줄이 반복되면 진짜 신호가 묻힌다.
        self.drift_warned: set[str] = set()
        self.drift_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server: ProxyServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 요청마다 찍는 기본 접근 로그는 끈다 — 아래에서 필요한 것만
        return

    # ── 공용 ──────────────────────────────────────────────────────
    def _send_json(self, status: int, obj: dict) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
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
                **self.server.stats.snapshot()}
        try:
            conn = self._upstream()
            conn.timeout = 3.0
            conn.request("GET", "/health")
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
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
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("X-TTS-Cache", "hit")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            with open(path, "rb") as f:
                while True:
                    data = f.read(CHUNK)
                    if not data:
                        break
                    self._write_chunk(data)
            self._end_chunks()
        except (BrokenPipeError, ConnectionResetError):
            # 로봇이 끼어들기로 끊었다 — 정상이다. 더 쓸 곳이 없을 뿐이다.
            pass

    # ── 통과 ──────────────────────────────────────────────────────
    def _pass(self, method: str, raw: bytes | None, cache_tag: str | None = None) -> None:
        """업스트림으로 넘기고 응답을 **받는 대로** 돌려준다 — 모아서 보내면 관람객 답의 첫 소리가
        합성 전체 시간만큼 늦는다(로봇 실측: 비스트리밍이면 77자 3.67초)."""
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="TTS 결과 캐시 프록시")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--upstream", default="http://127.0.0.1:8098")
    ap.add_argument("--cache-dir", default=None)
    args = ap.parse_args()
    cache = Cache(pathlib.Path(args.cache_dir).expanduser() if args.cache_dir else default_cache_dir())
    srv = ProxyServer((args.host, args.port), args.upstream, cache)
    log.info("TTS 캐시 프록시 %s:%d → %s · 캐시 %s(%d개)",
             args.host, args.port, args.upstream, cache.root, cache.count())
    srv.serve_forever()


if __name__ == "__main__":
    main()
