"""LLM·STT OpenAI 게이트웨이(`openai_gateway.py`) — 계획 `docs/superpowers/plans/2026-11-12-openai-gateway.md`.

가짜 OpenAI 서버·가짜 로컬 서버(llama-server·stt_server 자리)를 세우고 게이트웨이를 실제로 띄워, **로봇이 쓰는 바로 그
클라이언트**(`llm.LLMClient`·`stt.transcribe`)로 부른다. 진짜 OpenAI·진짜 `.env` 는 건드리지 않는다.

`reachy.sh` 배선은 `tests/test_reachy_start.py` 와 같은 방법(source 후 바깥에 닿는 함수만 가짜로)으로 본다.
"""

import email.parser
import email.policy
import io
import json
import logging
import os
import pathlib
import socket
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))

import openai_gateway as og  # noqa: E402
import llm as robot_llm  # noqa: E402
import stt as robot_stt  # noqa: E402
import stage.__main__ as stage_main  # noqa: E402
from llm import LLMClient  # noqa: E402
from stage.levels import LEVEL_NAMES, load_levels  # noqa: E402

KEY = "sk-test-SECRETabcdef1234567890"
KEY_TAIL = "7890"


# ── 가짜 서버 ──────────────────────────────────────────────────────
def sse(content=None, role=False):
    delta = {"role": "assistant", "content": ""} if role else {"content": content}
    return f"data: {json.dumps({'choices': [{'index': 0, 'delta': delta}]}, ensure_ascii=False)}\n\n".encode()


DONE = b"data: [DONE]\n\n"


class _FakeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        with self.server.fake.lock:
            self.server.fake.connections += 1

    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass                     # 게이트웨이가 연결을 버렸다(시간 초과·끊김 시험) — 시험이 의도한 것이다

    def _chunk(self, data):
        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")

    def do_GET(self):
        self._dispatch(b"")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._dispatch(self.rfile.read(n) if n else b"")

    def _dispatch(self, body):
        fake = self.server.fake
        req = {"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body}
        with fake.lock:
            fake.requests.append(req)
        fake.action_for(self.command, self.path)(self, req)


class Fake:
    """스크립트대로 답하는 HTTP 서버. 경로마다 동작 큐(비면 기본 동작)."""

    def __init__(self, defaults=None):
        self.requests = []
        self.connections = 0
        self.lock = threading.Lock()
        self.queues = {}
        self.defaults = defaults or {}
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeHandler)
        self.srv.daemon_threads = True
        self.srv.block_on_close = False
        self.srv.fake = self
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def push(self, path, *actions):
        self.queues.setdefault(path, []).extend(actions)

    def action_for(self, method, path):
        q = self.queues.get(path)
        if q:
            return q.pop(0)
        return self.defaults.get(path) or json_ok({"status": "ok"})

    def posts(self, path):
        return [r for r in self.requests if r["method"] == "POST" and r["path"] == path]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def sse_ok(events, gate=None):
    def act(h, req):
        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream")
        h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()
        for i, ev in enumerate(events):
            h._chunk(ev)
            if gate is not None and i == 1:
                gate.wait(5)
        h.wfile.write(b"0\r\n\r\n")
    return act


def json_ok(obj, status=200):
    def act(h, req):
        data = json.dumps(obj, ensure_ascii=False).encode()
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)
    return act


def hang(seconds):
    def act(h, req):
        time.sleep(seconds)
        h.close_connection = True
    return act


def slow(header_delay, body_delay):
    """머리까지 `header_delay`, 첫 청크까지 다시 `body_delay` — 단계마다는 상한 안이어도 합치면 넘는 느린 서버."""
    def act(h, req):
        time.sleep(header_delay)
        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream")
        h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()
        h.wfile.flush()
        time.sleep(body_delay)
        for ev in OPENAI_ANSWER:
            h._chunk(ev)
        h.wfile.write(b"0\r\n\r\n")
    return act


def drop_after_first(events):
    """머리와 첫 청크만 보내고 끝맺지 않은 채 연결을 끊는다(흐르는 도중 끊김)."""
    def act(h, req):
        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream")
        h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()
        h._chunk(events[0])
        h.wfile.flush()
        time.sleep(0.05)
        h.connection.shutdown(socket.SHUT_RDWR)
        h.close_connection = True
    return act


OPENAI_ANSWER = [sse(role=True), sse("오픈에이아이 답이에요."), sse(" 둘째 문장이에요."), DONE]
LOCAL_ANSWER = [sse(role=True), sse("로컬 답이에요."), DONE]


@pytest.fixture
def openai_fake():
    f = Fake({og.CHAT_PATH: sse_ok(OPENAI_ANSWER),
              og.STT_PATH: json_ok({"text": "오픈에이아이 전사", "languages": [{"code": "ko"}]})})
    yield f
    f.close()


@pytest.fixture
def local_fake():
    f = Fake({og.CHAT_PATH: sse_ok(LOCAL_ANSWER),
              og.STT_PATH: json_ok({"text": "로컬 전사", "language": "ko"}),
              "/health": json_ok({"status": "ok"})})
    yield f
    f.close()


@pytest.fixture
def gateway():
    started = []

    def make(cfg, local_url, llm=True, stt=True):
        servers = og.make_servers(cfg, "127.0.0.1", llm=(0, local_url) if llm else None,
                                  stt=(0, local_url) if stt else None)
        for s in servers:
            threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
            started.append(s)
        return {s.service: f"http://127.0.0.1:{s.server_address[1]}" for s in servers}

    yield make
    for s in started:
        s.shutdown()
        s.server_close()
    # 로봇 모듈의 keep-alive 세션이 닫힌 포트의 연결을 들고 다음 테스트로 넘어가지 않게.
    robot_llm._session.close()
    robot_stt._session.close()


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.INFO, logger="openai-gateway")

    def warnings():
        return [r.getMessage() for r in caplog.records if r.name == "openai-gateway" and r.levelno >= logging.WARNING]

    caplog.warnings = warnings
    return caplog


def cfg_on(openai_fake, **kw):
    base = dict(key=KEY, llm_engine="openai", stt_engine="openai", base=openai_fake.url,
                llm_timeout_s=1.0, stt_timeout_s=1.0)
    base.update(kw)
    return og.Config(**base)


def body_of(req):
    return json.loads(req["body"].decode())


def wav_audio(seconds):
    t = np.arange(int(16000 * seconds)) / 16000
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def form_of(req):
    """게이트웨이가 OpenAI 로 보낸 multipart — 게이트웨이 파서와 **다른 구현**(email)으로 푼다."""
    msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
        b"Content-Type: " + req["headers"]["Content-Type"].encode() + b"\r\n\r\n" + req["body"])
    fields, file = [], None
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if part.get_filename():
            file = part.get_payload(decode=True)
        else:
            fields.append((name, part.get_payload(decode=True).decode()))
    return fields, file


# ── 키 ─────────────────────────────────────────────────────────────
def test_키는_환경변수가_먼저고_없으면_env_파일의_그_한_줄만(tmp_path):
    f = tmp_path / ".env"
    f.write_text('ELEVENLABS_API_KEY=el-other\n# 주석\nexport OPENAI_API_KEY="sk-from-file"\nX=1\n')
    assert og.load_api_key({"OPENAI_API_KEY": "sk-env"}, env_file=f) == "sk-env"
    assert og.load_api_key({}, env_file=f) == "sk-from-file"
    assert og.load_api_key({}, env_file=tmp_path / "없음") is None
    g = tmp_path / "빈.env"
    g.write_text("OPENAI_API_KEY=\n")
    assert og.load_api_key({}, env_file=g) is None


def test_오류_요약은_키와_sk_꼴을_지운다():
    raw = json.dumps({"error": {"code": "invalid_api_key",
                                "message": f"Incorrect API key provided: {KEY}. also sk-test-****{KEY_TAIL}"}}).encode()
    s = og.error_summary(raw, KEY)
    assert KEY not in s and KEY_TAIL not in s and "invalid_api_key" in s


# ── 스위치·키 없음 ─────────────────────────────────────────────────
def test_키가_없으면_외부_호출_0_경고_한_줄씩_로컬로(openai_fake, local_fake, gateway, logs, tmp_path):
    env = {"REACHY_LLM_ENGINE": "openai", "REACHY_STT_ENGINE": "openai", "REACHY_OPENAI_BASE": openai_fake.url,
           "OPENAI_ENV_FILE": str(tmp_path / "없음.env")}
    cfg = og.config_from_env(env)
    assert cfg.key is None
    w = logs.warnings()
    assert len(w) == 2 and all("키가 없다" in m for m in w), w
    urls = gateway(cfg, local_fake.url)
    assert list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문")) == ["로컬 답이에요."]
    assert robot_stt.transcribe(wav_audio(2.0), url=urls["stt"] + og.STT_PATH) == "로컬 전사"
    assert openai_fake.requests == []
    assert len(logs.warnings()) == 2              # 요청마다 새 경고가 붙지 않는다(기동 때 한 번)


def test_엔진이_local_이면_게이트웨이는_통과만_한다(openai_fake, local_fake, gateway, logs):
    urls = gateway(cfg_on(openai_fake, llm_engine="local", stt_engine="local"), local_fake.url)
    assert list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문")) == ["로컬 답이에요."]
    assert robot_stt.transcribe(wav_audio(2.0), url=urls["stt"] + og.STT_PATH) == "로컬 전사"
    assert openai_fake.requests == []
    assert logs.warnings() == []


def test_모르는_엔진_값은_멈춘다():
    with pytest.raises(ValueError):
        og.config_from_env({"REACHY_LLM_ENGINE": "openia"})


# ── LLM 번역·스트리밍 ──────────────────────────────────────────────
def test_로봇_본문을_OpenAI_형식으로_번역하고_키를_붙인다(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    out = list(LLMClient(base_url=urls["llm"], system_prompt="시스템").chat_stream("질문"))
    assert out == ["오픈에이아이 답이에요.", "둘째 문장이에요."]
    (req,) = openai_fake.posts(og.CHAT_PATH)
    b = body_of(req)
    assert req["headers"]["Authorization"] == f"Bearer {KEY}"
    assert b["model"] == "gpt-6-luna" and b["reasoning_effort"] == "none"
    assert b["max_completion_tokens"] == 200 and "max_tokens" not in b      # gpt-6 는 max_tokens 를 400 으로 거절
    assert b["temperature"] == 0.7 and b["stream"] is True                  # none 이면 temperature 를 받는다
    assert "stream_options" not in b                                         # include_usage 의 빈 choices → 로봇 IndexError
    assert b["messages"] == [{"role": "system", "content": "시스템"}, {"role": "user", "content": "질문"}]
    assert local_fake.posts(og.CHAT_PATH) == []


def test_사고를_켜면_temperature_를_빼고_상한에_사고_몫을_더한다():
    cfg = og.Config(key=KEY, llm_engine="openai", llm_effort="low")
    out, dropped = og.to_openai_chat({"model": "local", "messages": [], "stream": True, "temperature": 0.7,
                                      "max_tokens": 200, "top_p": 0.9}, cfg)
    assert out["reasoning_effort"] == "low" and "temperature" not in out and "top_p" not in out
    assert out["max_completion_tokens"] == 200 + og.REASONING_HEADROOM
    assert dropped == []


def test_llama_전용_필드는_버리고_필드마다_한_번만_경고한다(openai_fake, local_fake, gateway, logs):
    answer = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "답"}}]}
    openai_fake.push(og.CHAT_PATH, json_ok(answer), json_ok(answer))
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    for _ in range(2):
        r = requests.post(urls["llm"] + og.CHAT_PATH, json={
            "model": "local", "stream": False, "max_tokens": 8, "cache_prompt": True, "top_k": 40,
            "messages": [{"role": "user", "content": "x"}]}, timeout=5)
        assert r.status_code == 200 and r.json() == answer          # 비스트림 응답은 받은 그대로
    for req in openai_fake.posts(og.CHAT_PATH):
        b = body_of(req)
        assert "cache_prompt" not in b and "top_k" not in b
    w = logs.warnings()
    assert len(w) == 2 and any("cache_prompt" in m for m in w) and any("top_k" in m for m in w), w


def test_스트리밍은_받는_대로_로봇에_닿는다(openai_fake, local_fake, gateway):
    gate = threading.Event()
    openai_fake.push(og.CHAT_PATH, sse_ok([sse(role=True), sse("첫 절이에요."), sse(" 나머지예요."), DONE], gate=gate))
    urls = gateway(cfg_on(openai_fake, llm_timeout_s=5.0), local_fake.url)
    it = LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문")
    first = next(it)
    # 가짜 OpenAI 는 아직 둘째 청크를 안 보냈다(gate 에서 기다린다) — 그런데 첫 절이 벌써 로봇에 닿았다.
    assert first == "첫 절이에요." and not gate.is_set()
    gate.set()
    assert list(it) == ["나머지예요."]


def test_OpenAI_연결을_다시_쓴다(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    c = LLMClient(base_url=urls["llm"], system_prompt="s")
    for q in ("하나", "둘", "셋"):
        assert list(c.chat_stream(q))[0] == "오픈에이아이 답이에요."
    assert len(openai_fake.posts(og.CHAT_PATH)) == 3
    assert openai_fake.connections == 1          # 새 연결마다 TLS 왕복이 첫 토큰 앞에 얹힌다


def test_이미지_질문은_그대로_싣는다(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("이게 뭐야?", b"\xff\xd8jpeg"))
    content = body_of(openai_fake.posts(og.CHAT_PATH)[0])["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": "이게 뭐야?"}
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


# ── 전문가 라우팅 ──────────────────────────────────────────────────
def test_전문가_표지는_상위_모델과_그_effort_로(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake, llm_model_expert="gpt-x-expert", llm_effort_expert="low"), local_fake.url)
    list(LLMClient(base_url=urls["llm"], system_prompt="s", model=og.EXPERT_MARK).chat_stream("질문"))
    list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문"))
    expert, normal = (body_of(r) for r in openai_fake.posts(og.CHAT_PATH))
    assert expert["model"] == "gpt-x-expert" and expert["reasoning_effort"] == "low" and "temperature" not in expert
    assert normal["model"] == "gpt-6-luna" and normal["reasoning_effort"] == "none"


def test_전문가_모델이_비면_라우팅하지_않는다(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    list(LLMClient(base_url=urls["llm"], system_prompt="s", model=og.EXPERT_MARK).chat_stream("질문"))
    assert body_of(openai_fake.posts(og.CHAT_PATH)[0])["model"] == "gpt-6-luna"


def test_전문가_표지는_로컬로_갈_때_local_로_되돌린다(openai_fake, local_fake, gateway):
    openai_fake.push(og.CHAT_PATH, json_ok({"error": {"message": "boom"}}, status=500))
    urls = gateway(cfg_on(openai_fake, llm_model_expert="gpt-x-expert"), local_fake.url)
    assert list(LLMClient(base_url=urls["llm"], system_prompt="s", model=og.EXPERT_MARK)
                .chat_stream("질문")) == ["로컬 답이에요."]
    assert body_of(local_fake.posts(og.CHAT_PATH)[0])["model"] == "local"


def test_감독과_게이트웨이의_표지가_같다():
    assert stage_main.EXPERT_MODEL_MARK == og.EXPERT_MARK
    assert stage_main.EXPERT_LEVEL_NAME in LEVEL_NAMES


def test_감독은_스위치가_켜진_전문가_수준에만_표지를_싣는다():
    levels = load_levels()
    on = {"REACHY_LLM_ENGINE": "openai"}
    assert stage_main.client_model_kw(levels["전문가"], on) == {"model": og.EXPERT_MARK}
    assert stage_main.client_model_kw(levels["전문가"], {}) == {}
    assert stage_main.client_model_kw(levels["전문가"], {"REACHY_LLM_ENGINE": "local"}) == {}
    for name in ("초등", "중고등", "일반"):
        assert stage_main.client_model_kw(levels[name], on) == {}


def test_감독의_클라이언트_인자는_스위치를_끄면_지금과_같다(monkeypatch):
    seen = []

    class 기록:
        def __init__(self, **kw):
            seen.append(kw)
            self.history = []

    monkeypatch.setattr(stage_main, "LLMClient", 기록)
    levels = load_levels()
    monkeypatch.delenv("REACHY_LLM_ENGINE", raising=False)
    stage_main.build_generate(levels["전문가"], warn=lambda m: None)
    assert seen and all(set(kw) == {"system_prompt", "max_tokens"} for kw in seen)
    seen.clear()
    monkeypatch.setenv("REACHY_LLM_ENGINE", "openai")
    stage_main.build_generate(levels["전문가"], warn=lambda m: None)
    assert seen and all(kw.get("model") == og.EXPERT_MARK for kw in seen)
    seen.clear()
    stage_main.build_generate(levels["일반"], warn=lambda m: None)
    assert seen and all("model" not in kw for kw in seen)


# ── 실패 정책 ──────────────────────────────────────────────────────
@pytest.mark.parametrize("action", [
    json_ok({"error": {"message": "server down"}}, status=500),
    json_ok({"error": {"message": "slow down"}}, status=429),
    hang(3.0),
    slow(0.35, 0.35),      # 단계마다 0.35초(상한 0.5초 안)지만 첫 바이트까지 0.7초 — 합친 마감으로 잘라야 한다
], ids=["500", "429", "시간초과", "합쳐서_느림"])
def test_OpenAI_LLM_실패는_로컬로_넘기고_경고_한_줄(openai_fake, local_fake, gateway, logs, action):
    openai_fake.push(og.CHAT_PATH, action)
    urls = gateway(cfg_on(openai_fake, llm_timeout_s=0.5), local_fake.url)
    t0 = time.monotonic()
    assert list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문")) == ["로컬 답이에요."]
    assert time.monotonic() - t0 < 3.0
    w = logs.warnings()
    assert len(w) == 1 and "로컬 LLM 으로 넘긴다" in w[0], w
    # **LLM 은 다시 보내지 않는다**(관람객이 기다린다 — B2 후속 브리프). 시간 초과여도 OpenAI 요청은 한 번이다.
    assert len(openai_fake.posts(og.CHAT_PATH)) == 1
    # 로컬로 간 본문은 원래 본문 그대로다(max_tokens·model "local").
    b = body_of(local_fake.posts(og.CHAT_PATH)[0])
    assert b["max_tokens"] == 200 and b["model"] == "local" and "reasoning_effort" not in b


def test_OpenAI_에_못_닿으면_로컬로(local_fake, gateway, logs):
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()                                   # 아무도 안 듣는 포트 → 연결 거부
    cfg = og.Config(key=KEY, llm_engine="openai", stt_engine="openai", base=f"http://127.0.0.1:{port}",
                    llm_timeout_s=0.5, stt_timeout_s=0.5)
    urls = gateway(cfg, local_fake.url)
    assert list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문")) == ["로컬 답이에요."]
    assert robot_stt.transcribe(wav_audio(2.0), url=urls["stt"] + og.STT_PATH) == "로컬 전사"
    assert len(logs.warnings()) == 2


def test_흐르는_도중_끊기면_로봇이_예외를_받는다(openai_fake, local_fake, gateway, logs):
    openai_fake.push(og.CHAT_PATH, drop_after_first([sse("첫 절이에요."), sse("못 간 절."), DONE]))
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    with pytest.raises(requests.RequestException):
        list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문"))
    w = logs.warnings()
    assert len(w) == 1 and "도중에 끊겼다" in w[0], w
    assert local_fake.posts(og.CHAT_PATH) == []    # 이미 말한 답을 로컬로 다시 말하지 않는다


def test_로컬도_없으면_지금과_같은_오류(openai_fake, gateway):
    openai_fake.push(og.CHAT_PATH, json_ok({"error": {"message": "x"}}, status=503))
    urls = gateway(cfg_on(openai_fake), "http://127.0.0.1:9")
    with pytest.raises(requests.HTTPError):
        list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문"))


def test_로그_오류_로컬요청_헬스_어디에도_키가_없다(openai_fake, local_fake, gateway, logs):
    leak = json_ok({"error": {"code": "invalid_api_key",
                              "message": f"Incorrect API key provided: {KEY} (sk-test-****{KEY_TAIL})"}}, status=401)
    openai_fake.push(og.CHAT_PATH, leak)
    openai_fake.push(og.STT_PATH, leak)
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    assert list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문")) == ["로컬 답이에요."]
    assert robot_stt.transcribe(wav_audio(2.0), url=urls["stt"] + og.STT_PATH) == "로컬 전사"
    health = requests.get(urls["llm"] + "/health", timeout=5).text + requests.get(urls["stt"] + "/health", timeout=5).text
    everything = logs.text + health + "".join(og.describe(cfg_on(openai_fake), []))
    assert KEY not in everything and KEY_TAIL not in everything
    assert "invalid_api_key" in logs.text           # 원인은 남는다
    for req in local_fake.requests:                 # 로컬 서버에는 키를 넘기지 않는다
        assert "Authorization" not in req["headers"]


# ── 헬스 ───────────────────────────────────────────────────────────
def test_헬스는_게이트웨이_표지와_엔진을_싣고_키가_있으면_로컬이_죽어도_200(openai_fake, gateway, tmp_path):
    urls = gateway(cfg_on(openai_fake, stt_engine="local"), "http://127.0.0.1:9")
    r = requests.get(urls["llm"] + "/health", timeout=5)
    assert r.status_code == 200
    d = r.json()
    assert d["gateway"] == "openai" and d["engines"] == "llm=openai,stt=local" and d["key"] == "설정됨"
    assert d["local"].startswith("down")
    assert openai_fake.requests == []              # 헬스는 외부를 부르지 않는다
    # STT 는 local 통과라 로컬이 곧 이 서비스다 — 죽었으면 503.
    assert requests.get(urls["stt"] + "/health", timeout=5).status_code == 503


# ── STT ────────────────────────────────────────────────────────────
def _stt_call(openai_fake, local_fake, gateway, monkeypatch, language, seconds, **cfg_kw):
    monkeypatch.setattr(robot_stt, "LANGUAGE", language)
    urls = gateway(cfg_on(openai_fake, **cfg_kw), local_fake.url)
    audio = wav_audio(seconds)
    text = robot_stt.transcribe(audio, url=urls["stt"] + og.STT_PATH)
    return text, audio


def test_STT_auto_는_기본_ko_하나로(openai_fake, local_fake, gateway, monkeypatch):
    """B1 실측: `languages` 를 비우거나 넓히면 짧은 한국어가 외국어가 된다("다음" → `Palum.`). 앱 기본 `auto` 도 ko 하나로."""
    text, audio = _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 2.0)
    assert text == "오픈에이아이 전사"
    (req,) = openai_fake.posts(og.STT_PATH)
    fields, file = form_of(req)
    assert ("model", "gpt-transcribe") in fields
    assert [v for k, v in fields if k == "languages[]"] == ["ko"]
    assert not any(k == "language" for k, _ in fields)          # 둘 다 보내지 말 것(공식 문서)
    with wave.open(io.BytesIO(file)) as w:                       # 파일은 손대지 않고 넘긴다
        assert w.getframerate() == 16000 and w.getnframes() == len(audio)
    assert req["headers"]["Authorization"] == f"Bearer {KEY}"


def test_STT_언어_목록을_넓혀도_1초_미만이면_ko_하나(openai_fake, local_fake, gateway, monkeypatch):
    _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 2.0, stt_languages=("ko", "en"))
    _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 0.4, stt_languages=("ko", "en"))
    long_, short = (form_of(r)[0] for r in openai_fake.posts(og.STT_PATH))
    assert [v for k, v in long_ if k == "languages[]"] == ["ko", "en"]
    assert [v for k, v in short if k == "languages[]"] == ["ko"]


def test_STT_언어_기본값은_환경변수로_바꾼다(tmp_path):
    env = {"REACHY_STT_ENGINE": "openai", "OPENAI_API_KEY": KEY, "REACHY_OPENAI_STT_KEYWORDS": "off"}
    assert og.config_from_env(env).stt_languages == ("ko",)
    assert og.config_from_env({**env, "REACHY_OPENAI_STT_LANGUAGES": "ko, EN"}).stt_languages == ("ko", "en")


@pytest.mark.parametrize("language,want", [("ko", ["ko"]), ("en", ["en"]), ("", ["ko"])])
def test_STT_언어를_정하면_그_언어_하나(openai_fake, local_fake, gateway, monkeypatch, language, want):
    _stt_call(openai_fake, local_fake, gateway, monkeypatch, language, 2.0)
    fields, _ = form_of(openai_fake.posts(og.STT_PATH)[0])
    assert [v for k, v in fields if k == "languages[]"] == want


def test_STT_목록이_둘_이상일_때_감지가_허용_밖이면_ko_로_한_번_더(openai_fake, local_fake, gateway, monkeypatch):
    openai_fake.push(og.STT_PATH, json_ok({"text": "こまわお。", "languages": [{"code": "ja"}]}),
                     json_ok({"text": "고마워", "languages": [{"code": "ko"}]}))
    text, _ = _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 2.0, stt_languages=("ko", "en"))
    assert text == "고마워"
    second = form_of(openai_fake.posts(og.STT_PATH)[1])[0]
    assert [v for k, v in second if k == "languages[]"] == ["ko"]


def test_STT_응답은_로컬_서버_모양(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x00" * 32000)
    r = requests.post(urls["stt"] + og.STT_PATH, files={"file": ("utt.wav", buf.getvalue(), "audio/wav")},
                      data={"language": "auto"}, timeout=5)
    assert r.json() == {"text": "오픈에이아이 전사", "language": "ko"}


def test_STT_실패는_로컬로_넘기고_경고_한_줄(openai_fake, local_fake, gateway, logs, monkeypatch):
    openai_fake.push(og.STT_PATH, json_ok({"error": {"message": "boom"}}, status=500))
    text, _ = _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 2.0)
    assert text == "로컬 전사"
    w = logs.warnings()
    assert len(w) == 1 and "로컬 STT 로 넘긴다" in w[0], w
    assert len(openai_fake.posts(og.STT_PATH)) == 1                  # HTTP 오류는 다시 보내지 않는다(느린 응답만)
    (req,) = local_fake.posts(og.STT_PATH)                          # 로컬은 원래 본문(language=auto)을 받는다
    assert b'name="language"' in req["body"] and b"auto" in req["body"]


def test_multipart_파서는_requests_가_만든_본문을_푼다():
    wav = bytes(range(256)) * 40 + b"\r\n--\r\n"                  # 경계 비슷한 바이트·CRLF 가 섞인 이진
    p = requests.Request("POST", "http://x/", files={"file": ("utt.wav", wav, "audio/wav")},
                         data={"language": "auto"}).prepare()
    fields, f = og.parse_multipart(p.headers["Content-Type"], p.body)
    assert fields == {"language": "auto"} and f.data == wav and f.filename == "utt.wav"
    assert f.content_type == "audio/wav"


# ── reachy.sh 배선 ─────────────────────────────────────────────────
_SH_ENV = ("REACHY_LLM_ENGINE", "REACHY_STT_ENGINE", "REACHY_LLM_INNER_PORT", "REACHY_STT_INNER_PORT",
           "REACHY_BIND_HOST", "REACHY_DIRECTOR_PORT", "REACHY_DASHBOARD_PORT", "REACHY_DASHBOARD_HOST",
           "REACHY_MC_HOST", "REACHY_DOCENT_HOST", "TTS_QWEN_PORT", "REACHY_PY", "TTS_QWEN_VOICE", "TTS_BACKEND",
           "STT_PYTHON", "LLM_PORT", "STT_PORT", "LLM_HOST", "STT_HOST")


def _sh(script, tmp_path, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in _SH_ENV}
    env.update({"CALLS": str(tmp_path / "calls.txt"), "REACHY_PY": sys.executable})
    env.update(env_extra or {})
    body = (f'source ./reachy.sh\nLOG_DIR="{tmp_path}"\nGATEWAY_PID_FILE="$LOG_DIR/openai-gateway.pid"\n'
            f'TTS_PROXY_PID_FILE="$LOG_DIR/tts-proxy.pid"\n{script}')
    return subprocess.run(["bash", "-c", body], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)


def _calls(tmp_path):
    p = tmp_path / "calls.txt"
    return p.read_text().splitlines() if p.exists() else []


def _fake_ctl(tmp_path):
    f = tmp_path / "llamactl"
    f.write_text('#!/bin/sh\necho "ctl $* LLM_PORT=${LLM_PORT:-unset} STT_PORT=${STT_PORT:-unset} '
                 'LLM_HOST=$LLM_HOST STT_HOST=$STT_HOST" >> "$CALLS"\n')
    f.chmod(0o755)
    return str(f)


_GW_FAKES = r'''
wait_for() { echo "wait $1" >> "$CALLS"; return 0; }
nohup()    { echo "nohup $*" >> "$CALLS"; }
LLAMACTL="$FAKE_CTL"
'''


def test_bash_문법():
    assert subprocess.run(["bash", "-n", str(ROOT / "reachy.sh")]).returncode == 0


def test_변수_바로_뒤에_한글_기호를_붙이지_않는다():
    """macOS 기본 bash 3.2 는 `$LLM_INNER_PORT·` 의 `·`(멀티바이트)까지 변수 이름으로 읽어 `set -u` 아래에서
    "unbound variable" 로 죽는다(2026-11-12 게이트웨이 기동 줄에서 실제로 밟았다). `bash -n` 은 못 잡는다 — 실행해야
    드러난다. 변수 뒤에 ASCII 가 아닌 글자가 오면 `${…}` 로 감싼다."""
    import re
    bad = [f"{i}: {line.strip()}" for i, line in enumerate((ROOT / "reachy.sh").read_text().splitlines(), 1)
           if not line.lstrip().startswith("#") and re.search(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]", line)]
    assert bad == [], bad


def _dry(*args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in _SH_ENV}
    env.update(env_extra or {})
    r = subprocess.run(["bash", str(ROOT / "reachy.sh"), "start", *args, "--dry-run"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=30)
    return r, [l for l in r.stdout.splitlines() if l.startswith("PLAN ")]


def test_dry_run_스위치_꺼짐은_지금과_같은_4줄():
    for target in ("--sim", "--robot"):
        r, plan = _dry(target)
        assert r.returncode == 0 and len(plan) == 4 and not any("gateway" in l for l in plan), plan


def test_dry_run_스위치_켜짐은_게이트웨이_한_줄을_더():
    r, plan = _dry("--sim", env_extra={"REACHY_STT_ENGINE": "openai"})
    assert r.returncode == 0 and len(plan) == 5
    assert "PLAN gateway llm=local stt=openai ports=8080,8090 inner=127.0.0.1:8081,8091" in plan
    r, plan = _dry("--sim", env_extra={"REACHY_LLM_ENGINE": "OpenAI"})       # 대소문자도 오타로 본다
    assert r.returncode == 2 and plan == []


def test_스위치_꺼짐이면_llamactl_을_지금처럼_바깥_포트로(tmp_path):
    r = _sh(_GW_FAKES + r'''
up() { return 1; }
BIND_HOST=0.0.0.0
start_llm_stt; echo "rc=$?"
''', tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path)})
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    calls = _calls(tmp_path)
    assert calls[0] == "ctl reach-llm LLM_PORT=unset STT_PORT=unset LLM_HOST=0.0.0.0 STT_HOST=0.0.0.0", calls
    assert not any("openai_gateway" in c for c in calls)
    assert "wait http://localhost:8080/health" in calls and "wait http://localhost:8090/health" in calls


def test_스위치_켜짐이면_로컬은_안쪽_loopback_게이트웨이는_바깥(tmp_path):
    r = _sh(_GW_FAKES + r'''
up()   { return 1; }
curl() { return 7; }          # 아무도 안 듣는다(진짜 curl 이면 이 맥에 떠 있는 것에 따라 결과가 바뀐다)
BIND_HOST=0.0.0.0
start_llm_stt; echo "rc=$?"
wait
''', tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path), "REACHY_LLM_ENGINE": "openai"})
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    calls = _calls(tmp_path)
    assert calls[0] == "ctl reach-llm LLM_PORT=8081 STT_PORT=8091 LLM_HOST=127.0.0.1 STT_HOST=127.0.0.1", calls
    gw = [c for c in calls if c.startswith("nohup ")]
    assert len(gw) == 1, calls
    assert ("openai_gateway.py --host 0.0.0.0 --llm-port 8080 --llm-local http://127.0.0.1:8081 --llm-engine openai "
            "--stt-port 8090 --stt-local http://127.0.0.1:8091 --stt-engine local") in gw[0]
    assert calls.index("wait http://127.0.0.1:8081/health") < calls.index("wait http://localhost:8080/health")


def test_스위치_켜짐인데_바깥_포트에_로컬_직결이_떠_있으면_멈춘다(tmp_path):
    r = _sh(_GW_FAKES + r'''
up()   { case "$1" in http://localhost:8080/*) return 0 ;; esac; return 1; }
curl() { echo '{"status":"ok"}'; }
start_llm_stt; echo "rc=$?"
''', tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path), "REACHY_STT_ENGINE": "openai"})
    assert "rc=1" in r.stdout and "게이트웨이가 아닌 서버" in r.stdout, r.stdout + r.stderr
    assert _calls(tmp_path) == []                   # 아무것도 띄우지 않았다


def test_503_을_주는_옛_게이트웨이도_떠_있는_것으로_본다(tmp_path):
    """안쪽 로컬이 죽은 통과 모드 게이트웨이는 헬스가 503 이다 — `up` 으로 보면 "안 떠 있다" 가 되어 새 게이트웨이가
    포트를 못 잡고, 옛 설정의 게이트웨이가 그대로 돈다."""
    r = _sh(_GW_FAKES + r'''
up()   { return 1; }
curl() { echo '{"status": "local-down", "gateway": "openai", "engines": "llm=local,stt=openai"}'; }
start_llm_stt; echo "rc=$?"
''', tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path), "REACHY_LLM_ENGINE": "openai"})
    assert "rc=1" in r.stdout and "설정이 다른 게이트웨이" in r.stdout, r.stdout + r.stderr
    assert _calls(tmp_path) == []


def test_같은_설정의_게이트웨이가_떠_있으면_재사용한다(tmp_path):
    r = _sh(_GW_FAKES + r'''
up()   { return 0; }
curl() { echo '{"gateway": "openai", "engines": "llm=openai,stt=openai"}'; }
start_llm_stt; echo "rc=$?"
''', tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path), "REACHY_LLM_ENGINE": "openai", "REACHY_STT_ENGINE": "openai"})
    assert "rc=0" in r.stdout and "이미 떠 있다" in r.stdout, r.stdout + r.stderr
    assert _calls(tmp_path) == []


def test_설정이_다른_게이트웨이가_떠_있으면_멈춘다(tmp_path):
    r = _sh(_GW_FAKES + r'''
up()   { return 0; }
curl() { echo '{"gateway": "openai", "engines": "llm=openai,stt=local"}'; }
start_llm_stt; echo "rc=$?"
''', tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path), "REACHY_LLM_ENGINE": "openai", "REACHY_STT_ENGINE": "openai"})
    assert "rc=1" in r.stdout and "설정이 다른 게이트웨이" in r.stdout, r.stdout + r.stderr


def test_스위치를_껐는데_게이트웨이가_남아_있으면_경고한다(tmp_path):
    r = _sh(_GW_FAKES + r'''
up()   { return 0; }
curl() { echo '{"gateway": "openai", "engines": "llm=openai,stt=local"}'; }
start_llm_stt; echo "rc=$?"
''', tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path)})
    assert "rc=0" in r.stdout and "지난 실행의 OpenAI 게이트웨이" in r.stdout, r.stdout + r.stderr


def test_stop_은_게이트웨이와_안쪽_포트도_내린다(tmp_path):
    script = r'''
kill_pidfile() { echo "kill $2" >> "$CALLS"; }
sweep()        { echo "sweep $1" >> "$CALLS"; }
pgrep()        { %s; }
LLAMACTL="$FAKE_CTL"
stop_all >/dev/null
'''
    r = _sh(script % "return 1", tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path)})
    assert r.returncode == 0, r.stderr
    calls = _calls(tmp_path)
    assert "kill OpenAI 게이트웨이" in calls and "sweep openai_gateway.py" in calls
    assert [c for c in calls if c.startswith("ctl ")] == [
        "ctl stop LLM_PORT=unset STT_PORT=unset LLM_HOST= STT_HOST="]
    (tmp_path / "calls.txt").unlink()
    _sh(script % "return 0", tmp_path, {"FAKE_CTL": _fake_ctl(tmp_path)})
    assert [c for c in _calls(tmp_path) if c.startswith("ctl ")][-1].startswith("ctl stop LLM_PORT=8081 STT_PORT=8091")


def test_STT_응답이_늦으면_한_번_더_보내_받고_경고_한_줄(openai_fake, local_fake, gateway, logs, monkeypatch):
    """B1 실측: 27.4초 응답 1/1,940 — 다시 보내면 정상. 시도당 상한에 걸리면 한 번 더."""
    openai_fake.push(og.STT_PATH, hang(1.5), json_ok({"text": "두 번째에 받았다", "languages": [{"code": "ko"}]}))
    t0 = time.monotonic()
    text, _ = _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 2.0, stt_timeout_s=0.3)
    assert text == "두 번째에 받았다" and time.monotonic() - t0 < 1.5
    assert len(openai_fake.posts(og.STT_PATH)) == 2 and local_fake.posts(og.STT_PATH) == []
    w = logs.warnings()
    assert len(w) == 1 and "한 번 더 보내 받았다" in w[0], w


def test_STT_두_번_다_늦으면_로컬로_경고_한_줄(openai_fake, local_fake, gateway, logs, monkeypatch):
    openai_fake.push(og.STT_PATH, hang(1.5), hang(1.5))
    text, _ = _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 2.0, stt_timeout_s=0.3)
    assert text == "로컬 전사"
    assert len(openai_fake.posts(og.STT_PATH)) == 2
    w = logs.warnings()
    assert len(w) == 1 and "로컬 STT 로 넘긴다" in w[0] and "2번 모두" in w[0], w


def test_STT_연결이_안_되면_다시_보내지_않는다(local_fake, gateway, logs, monkeypatch):
    """연결 거부·오프라인은 다시 해도 같다 — 시간만 버린다. 느린 **응답**만 다시 보낸다."""
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()
    monkeypatch.setattr(robot_stt, "LANGUAGE", "auto")
    urls = gateway(og.Config(key=KEY, stt_engine="openai", base=f"http://127.0.0.1:{port}", stt_timeout_s=0.3),
                   local_fake.url)
    assert robot_stt.transcribe(wav_audio(2.0), url=urls["stt"] + og.STT_PATH) == "로컬 전사"
    w = logs.warnings()
    assert len(w) == 1 and "한 번 더" not in w[0], w


# ── STT 키워드 ─────────────────────────────────────────────────────
def test_키워드를_싣는다_순서대로_한_줄씩(openai_fake, local_fake, gateway, monkeypatch):
    _stt_call(openai_fake, local_fake, gateway, monkeypatch, "auto", 2.0, stt_keywords=("도슨트", "마르코니", "GMDSS"))
    fields, _ = form_of(openai_fake.posts(og.STT_PATH)[0])
    assert [v for k, v in fields if k == "keywords[]"] == ["도슨트", "마르코니", "GMDSS"]


def test_큐시트에서_전시_고유명사를_만든다():
    """손으로 적은 목록이 아니라 대본(큐시트 대사·제목·주제)과 교육자료 카드 라벨에서 나온다 — 대본이 바뀌면 따라 바뀐다."""
    kw = og.cue_keywords()
    for name in ("마르코니", "맥스웰", "헤르츠", "폴듀", "뉴펀들랜드", "세인트존스", "타이타닉", "테레민", "크로마키",
                 "루노호트", "장황남 박사", "라이덴", "모스부호", "사물인터넷", "GMDSS", "SOLAS", "ICAO", "VLF", "EHF", "5G"):
        assert name in kw, name
    # 잡음이 아니어야 하는 것들 — 단위·규격 번호·조사 붙은 꼴·동사 꼴·이음말·의문 꼴
    for junk in ("Hz", "MHz", "100W", "V.431-8", "LTE로", "빛이", "여기서 보내면", "그리고 테레민", "멀어질수록",
                 "무엇이 언제", "어디서 처음이었나", "200마일"):
        assert junk not in kw, junk
    assert len(kw) == len({k.lower() for k in kw})                   # 중복 없음
    assert all(not og._KW_FORBIDDEN.search(k) and len(k) <= og.KEYWORD_MAX_CHARS for k in kw)
    assert len(kw) <= og.KEYWORDS_MAX                                 # 지금 대본은 상한 안 — 기동마다 자름 경고가 뜨지 않는다


def test_부르는_말과_멈추는_말을_먼저_싣는다(tmp_path):
    words = og.control_keywords({})
    assert words[:2] == ["사회자", "도슨트"]                         # stage.director.SPEAKER_LABEL
    assert {"미니야", "그만", "잠깐만", "스톱"} <= set(words)          # 로봇 앱 기본 BARGE_IN_WAKE(소스에서 읽는다)
    assert og.control_keywords({"REACHY_BARGE_IN_WAKE": "리치야, 멈춰"})[2:] == ["리치야", "멈춰"]


def test_조사_떼기는_받침_규칙을_지킨다():
    assert og._strip_particle("테레민이") == ("테레민", True)
    assert og._strip_particle("패러데이") == ("패러데이", False)       # '데' 에 받침이 없다 — '이' 는 조사가 아니다
    assert og._strip_particle("마르코니가") == ("마르코니", True)
    assert og._strip_particle("회의") == ("회의", False)               # 떼면 한 글자 — 이름을 지킨다
    assert og._strip_particle("GMDSS는") == ("GMDSS", True)
    assert og._strip_particle("ICT기금") == ("ICT기금", False)          # '기금' 은 조사가 아니다
    assert og._label_terms("루노호트와 월면차") == ["루노호트", "월면차"]
    assert og._label_terms("1912년 타이타닉") == ["타이타닉"]
    assert og._latin_terms("406MHz 비상위치표지·V.431-8·GMDSS·5G·100W") == ["GMDSS", "5G"]


def test_키워드는_기동_때_큐시트에서_만들고_스위치로_끈다(tmp_path):
    env = {"REACHY_STT_ENGINE": "openai", "OPENAI_API_KEY": KEY}
    cfg = og.config_from_env(env)
    assert cfg.stt_keywords[:2] == ("사회자", "도슨트") and "마르코니" in cfg.stt_keywords
    assert og.config_from_env({**env, "REACHY_OPENAI_STT_KEYWORDS": "off"}).stt_keywords == ()
    # STT 를 OpenAI 로 안 보내면 만들지도 않는다(큐시트를 읽을 이유가 없다)
    assert og.config_from_env({"OPENAI_API_KEY": KEY}).stt_keywords == ()


def test_키워드_상한을_넘으면_자르고_경고_한_줄(logs):
    env = {"REACHY_STT_ENGINE": "openai", "OPENAI_API_KEY": KEY, "REACHY_OPENAI_STT_KEYWORDS_MAX": "10"}
    cfg = og.config_from_env(env)
    assert len(cfg.stt_keywords) == 10 and cfg.stt_keywords[:2] == ("사회자", "도슨트")   # 앞(부르는 말·앞 큐)이 남는다
    w = logs.warnings()
    assert len(w) == 1 and "잘랐다" in w[0], w


def test_금지_문자나_너무_긴_키워드는_보내기_전에_뺀다():
    ok, problems = og.limit_keywords(["마르코니", "a<b", "줄\n바꿈", "가" * 41, "GMDSS"], 10)
    assert ok == ["마르코니", "GMDSS"] and len(problems) == 1           # 하나라도 보내면 요청 전체가 거절된다(공식 문서)


def test_큐시트를_못_읽으면_키워드_없이_경고_한_줄(logs, monkeypatch, tmp_path):
    monkeypatch.setenv("REACHY_CUES_PATH", str(tmp_path / "없는-큐시트.yaml"))
    cfg = og.config_from_env({"REACHY_STT_ENGINE": "openai", "OPENAI_API_KEY": KEY})
    assert cfg.stt_keywords == ()
    w = logs.warnings()
    assert len(w) == 1 and "키워드 없이" in w[0], w


# ── service_tier ───────────────────────────────────────────────────
def test_service_tier_스위치는_기본_꺼짐(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake), local_fake.url)
    list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문"))
    assert "service_tier" not in body_of(openai_fake.posts(og.CHAT_PATH)[0])
    assert og.config_from_env({"REACHY_OPENAI_LLM_SERVICE_TIER": "fast"}).llm_service_tier == "fast"


def test_service_tier_를_켜면_LLM_요청에_싣는다(openai_fake, local_fake, gateway):
    urls = gateway(cfg_on(openai_fake, llm_service_tier="fast"), local_fake.url)
    list(LLMClient(base_url=urls["llm"], system_prompt="s").chat_stream("질문"))
    assert body_of(openai_fake.posts(og.CHAT_PATH)[0])["service_tier"] == "fast"


# ── 로봇 두 대 ─────────────────────────────────────────────────────
def _together(barrier, then):
    """두 요청이 **동시에** 들어와야 둘 다 답한다. 게이트웨이가 한 줄로 세우면 3초 뒤 BrokenBarrierError — 그 요청은
    게이트웨이 쪽에서 끊겨 로컬 답으로 떨어지고 아래 단언이 깨진다."""
    def act(h, req):
        barrier.wait(3)
        then(h, req)
    return act


def test_로봇_두_대의_동시_요청이_서로를_막지_않는다(openai_fake, local_fake, gateway, monkeypatch):
    llm_gate, stt_gate = threading.Barrier(2), threading.Barrier(2)
    openai_fake.push(og.CHAT_PATH, *[_together(llm_gate, sse_ok(OPENAI_ANSWER))] * 2)
    openai_fake.push(og.STT_PATH, *[_together(stt_gate, json_ok({"text": "같이 받았다", "languages": [{"code": "ko"}]}))] * 2)
    monkeypatch.setattr(robot_stt, "LANGUAGE", "auto")
    urls = gateway(cfg_on(openai_fake, llm_timeout_s=5.0, stt_timeout_s=5.0), local_fake.url)
    out = {}

    def robot(name):                    # 사회자·도슨트 — 각자 자기 클라이언트로 LLM 과 STT 를 부른다
        out[name, "llm"] = list(LLMClient(base_url=urls["llm"], system_prompt=name).chat_stream("질문"))
        out[name, "stt"] = robot_stt.transcribe(wav_audio(1.5), url=urls["stt"] + og.STT_PATH)

    ts = [threading.Thread(target=robot, args=(n,)) for n in ("mc", "docent")]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
        assert not t.is_alive()
    for n in ("mc", "docent"):
        assert out[n, "llm"] == ["오픈에이아이 답이에요.", "둘째 문장이에요."], out
        assert out[n, "stt"] == "같이 받았다", out
    assert local_fake.posts(og.CHAT_PATH) == [] and local_fake.posts(og.STT_PATH) == []
