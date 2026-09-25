"""TTS 결과 캐시 프록시(`tts_cache_proxy.py`, 2026-09-25).

진짜 프록시 앞뒤에 **가짜 업스트림**(CrispASR 처럼 청크 `audio/pcm` 을 흘린다)을 두고, 로봇이
실제로 여는 경로(`tts._qwen_open`)로 요청한다. 실측(진짜 CrispASR): 적중 첫 청크 5.9ms, 통과는
직접 대비 +15ms, 바이트 동일 — 계획 docs/superpowers/plans/2026-09-25-tts-result-cache.md.
"""

import json
import logging
import pathlib
import socket
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))
import tts as robot_tts  # noqa: E402

from tts_cache_proxy import INDEX_NAME, Cache, ProxyServer, cache_key, is_cacheable  # noqa: E402

PCM = bytes(range(256)) * 40            # 10240 바이트 — 청크 여러 개
BODY = {"input": "안녕하세요, 여러분!", "model": "tts", "voice": "serena", "speed": 1.27,
        "instructions": "밝고 또렷하게", "stream": True, "response_format": "pcm"}


class _Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    calls: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        data = b'{"status": "ok", "backend": "fake"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n))
        type(self).calls.append(body)
        payload = ("업스트림:" + body["input"]).encode() * 50
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for i in range(0, len(payload), 1000):
            c = payload[i:i + 1000]
            self.wfile.write(f"{len(c):X}\r\n".encode() + c + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


def _serve(srv):
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


@pytest.fixture
def stack(tmp_path):
    _Upstream.calls = []
    up = _serve(ThreadingHTTPServer(("127.0.0.1", 0), _Upstream))
    cache = Cache(tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    proxy = _serve(ProxyServer(("127.0.0.1", 0), f"http://127.0.0.1:{up.server_port}", cache))
    yield {"proxy": proxy, "up": up, "cache": cache, "dir": tmp_path / "cache",
           "url": f"http://127.0.0.1:{proxy.server_port}"}
    proxy.shutdown()
    up.shutdown()


def _speak(url, body, monkeypatch):
    """로봇이 여는 경로 그대로 — `tts._qwen_open` 이 모듈의 `QWEN_URL` 로 연다."""
    monkeypatch.setattr(robot_tts, "QWEN_URL", url + "/v1/audio/speech")
    with robot_tts._qwen_open(body) as r:
        ctype = r.headers.get("Content-Type")
        tag = r.headers.get("X-TTS-Cache")
        read = getattr(r, "read1", None) or r.read
        chunks = []
        while True:
            c = read(4096)
            if not c:
                break
            chunks.append(c)
    return ctype, tag, b"".join(chunks)


def test_키는_필드_순서와_무관하고_화자_배속이_다르면_다르다():
    reordered = dict(reversed(list(BODY.items())))
    assert cache_key(BODY) == cache_key(reordered)
    assert cache_key(BODY) != cache_key({**BODY, "speed": 1.2})
    assert cache_key(BODY) != cache_key({**BODY, "voice": "sohee"})


def test_캐시_대상은_스트리밍_PCM_요청뿐이다():
    assert is_cacheable(BODY)
    assert not is_cacheable({k: v for k, v in BODY.items() if k not in ("stream", "response_format")})


def test_구운_대사는_합성_서버를_거치지_않고_같은_형식으로_나간다(stack, monkeypatch):
    (stack["dir"] / f"{cache_key(BODY)}.pcm").write_bytes(PCM)
    ctype, tag, data = _speak(stack["url"], BODY, monkeypatch)
    assert (ctype, tag) == ("audio/pcm", "hit")
    assert data == PCM
    assert _Upstream.calls == [], "적중인데 합성 서버를 불렀다"


def test_빗나간_요청은_스트리밍으로_통과하고_저장하지_않는다(stack, monkeypatch):
    body = {**BODY, "input": "관람객 질문 답이에요."}
    ctype, tag, data = _speak(stack["url"], body, monkeypatch)
    assert (ctype, tag) == ("audio/pcm", "miss")
    assert data == ("업스트림:" + body["input"]).encode() * 50
    assert [c["input"] for c in _Upstream.calls] == [body["input"]]
    assert list(stack["dir"].glob("*.pcm")) == [], "관람객 답을 저장했다 — 결정: 구운 고정 대사만"


def _index(dirpath, entries):
    (dirpath / INDEX_NAME).write_text(json.dumps({"entries": entries}, ensure_ascii=False))


def test_고정_대사인데_설정이_달라_빗나가면_한_번만_경고한다(stack, monkeypatch, caplog):
    _index(stack["dir"], [{"key": cache_key(BODY), "text": BODY["input"], "voice": "serena",
                           "speed": 1.27, "instructions": "밝고 또렷하게"}])
    drifted = {**BODY, "speed": 1.2}
    with caplog.at_level(logging.WARNING, logger="tts-proxy"):
        _speak(stack["url"], drifted, monkeypatch)
        _speak(stack["url"], drifted, monkeypatch)
    msgs = [r.getMessage() for r in caplog.records if "캐시 키가 다르다" in r.getMessage()]
    assert len(msgs) == 1, msgs
    assert "1.2" in msgs[0] and "1.27" in msgs[0]


def test_색인에_있는데_파일이_없으면_아직_안_구웠다고_알린다(stack, monkeypatch, caplog):
    _index(stack["dir"], [{"key": cache_key(BODY), "text": BODY["input"], "voice": "serena",
                           "speed": 1.27, "instructions": "밝고 또렷하게"}])
    with caplog.at_level(logging.WARNING, logger="tts-proxy"):
        _speak(stack["url"], BODY, monkeypatch)
    assert any("아직 안 구운" in r.getMessage() for r in caplog.records)
    assert not any("캐시 키가 다르다" in r.getMessage() for r in caplog.records)


def test_색인은_굽기_뒤_다시_띄우지_않아도_새로_읽힌다(stack):
    assert stack["cache"].baked_for("새 문장") == []
    _index(stack["dir"], [{"key": "k", "text": "새 문장"}])
    import os
    os.utime(stack["dir"] / INDEX_NAME, (1, 2_000_000_000))   # mtime 이 바뀐 것을 확실히
    assert stack["cache"].baked_for("새 문장") == [{"key": "k", "text": "새 문장"}]


def test_헬스는_프록시_표지와_캐시_수를_싣고_업스트림이_죽으면_503(stack):
    (stack["dir"] / "a.pcm").write_bytes(b"x")
    h = json.loads(urllib.request.urlopen(stack["url"] + "/health").read())
    assert h["status"] == "ok" and h["proxy"] == "tts-cache" and h["cache_entries"] == 1
    stack["up"].shutdown()
    stack["up"].server_close()
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(stack["url"] + "/health")
    assert e.value.code == 503


def test_업스트림이_죽으면_합성은_502(stack, monkeypatch):
    stack["up"].shutdown()
    stack["up"].server_close()
    with pytest.raises(urllib.error.HTTPError) as e:
        _speak(stack["url"], {**BODY, "input": "안 구운 문장"}, monkeypatch)
    assert e.value.code == 502


def test_로봇이_도중에_끊어도_프록시는_다음_요청을_받는다(stack, monkeypatch):
    """끼어들기 — 로봇이 재생 도중 연결을 끊는다. 프록시가 BrokenPipe 로 죽으면 그 뒤 모든 발화가 안 나간다."""
    (stack["dir"] / f"{cache_key(BODY)}.pcm").write_bytes(PCM * 200)
    raw = json.dumps(BODY, ensure_ascii=False).encode()
    s = socket.create_connection(("127.0.0.1", stack["proxy"].server_port))
    s.sendall(b"POST /v1/audio/speech HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
              + f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
    s.recv(100)
    s.close()
    ctype, tag, data = _speak(stack["url"], BODY, monkeypatch)
    assert tag == "hit" and data == PCM * 200
