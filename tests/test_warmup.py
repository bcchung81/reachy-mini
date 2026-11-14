"""예열(`scripts/warmup.py`)의 외부 API 사전 점검 — 계획 `docs/superpowers/plans/2026-11-14-show-readiness.md` A-1.

외부 전용(`REACHY_LOCAL_MODELS=off`)에서 예열 실패는 "건너뜀" 이 아니라 **점검 실패**다 — 무엇 때문인지(키·잔액/한도·인터넷)와
그래서 공연에서 **무엇이 안 되는지**를 줄마다 말한다(U1 ①: 빨간 줄로 알리고 계속). 실패 종류는 게이트웨이·TTS 프록시가
502 머리 `X-Reachy-Upstream` 에 싣는다(`tests/test_openai_gateway.py`·`tests/test_tts_elevenlabs.py` 가 그쪽을 본다).

진짜 OpenAI·ElevenLabs·저장소 `.env` 는 건드리지 않는다 — 게이트웨이·프록시 자리에 가짜 서버를 세우고, 크레딧 조회는
가짜 함수로 바꾼다(저장소 `.env` 에 진짜 키가 있다 — 조회 함수가 새면 실제 ElevenLabs 를 부른다).
"""

import importlib.util
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_warmup():
    spec = importlib.util.spec_from_file_location("warmup_under_test", ROOT / "scripts" / "warmup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


warmup = _load_warmup()
import tts as robot_tts  # noqa: E402  (warmup 이 앱 폴더를 sys.path 에 넣는다)


class _Fake(BaseHTTPRequestHandler):
    """경로마다 (상태, 실패 종류) — 실패 종류가 있으면 게이트웨이·프록시처럼 502 본문·머리에 싣는다."""
    protocol_version = "HTTP/1.1"
    plan: dict = {}

    def log_message(self, *a):
        return

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        status, kind = _Fake.plan.get(self.path, (200, None))
        if status == 200:
            if "chat" in self.path:
                data, ctype = b'data: {"choices":[{"delta":{"content":"x"}}]}\n\ndata: [DONE]\n\n', "text/event-stream"
            elif "transcriptions" in self.path:
                data, ctype = json.dumps({"text": "안녕"}).encode(), "application/json"
            else:
                data, ctype = b"RIFF0000WAVE", "audio/wav"
        else:
            body = {"error": "no-local"}
            if kind:
                body["upstream"] = kind
            data, ctype = json.dumps(body).encode(), "application/json"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if kind:
            self.send_header("X-Reachy-Upstream", kind)
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def stack(tmp_path, monkeypatch):
    """가짜 게이트웨이(LLM·STT)·TTS 프록시 하나. 모션 카탈로그(허깅페이스)·크레딧 조회(ElevenLabs)는 가짜로."""
    _Fake.plan = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    prompt = tmp_path / "prompt.md"
    prompt.write_text("시스템", encoding="utf-8")
    monkeypatch.setattr(warmup, "LLM_URL", base + "/v1/chat/completions")
    monkeypatch.setattr(warmup, "STT_URL", base + "/v1/audio/transcriptions")
    monkeypatch.setattr(robot_tts, "QWEN_URL", base + "/v1/audio/speech")
    monkeypatch.setattr(warmup, "_prompt", lambda: prompt)
    monkeypatch.setattr(warmup, "warm_moves", lambda: "(가짜)")
    looked = []

    def credits(key):
        looked.append(key)
        return stack_state["credits"]

    stack_state = {"credits": (7_429, 131_000), "looked": looked, "base": base,
                   "out": tmp_path / "preflight.txt"}
    monkeypatch.setattr(warmup, "credits_left", credits)
    monkeypatch.setattr(warmup, "el_key", lambda: "sk_test_FAKE")
    yield stack_state
    srv.shutdown()
    srv.server_close()


_OFF = {"REACHY_LOCAL_MODELS": "off", "TTS_ENGINE": "elevenlabs", "TTS_BACKEND": "qwen"}


def _env(stack, **kw):
    return dict(_OFF, REACHY_PREFLIGHT_OUT=str(stack["out"]), **kw)


def _preflight(stack):
    p = stack["out"]
    return [l.split("\t", 1) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_외부_전용_예열_실패는_종류와_안_되는_것을_말한다(stack, capsys):
    _Fake.plan = {"/v1/chat/completions": (502, "401"),
                  "/v1/audio/transcriptions": (502, "429"),
                  "/v1/audio/speech": (502, "connect")}
    rc = warmup.main(_env(stack))
    out = capsys.readouterr().out
    assert rc == 1
    assert "건너뜀" not in out.replace("모션", "")             # 외부 전용에서 LLM·STT·TTS 실패는 '건너뜀' 이 아니다
    lines = out.splitlines()
    llm = next(l for l in lines if l.lstrip().startswith("LLM") and "점검 실패" in l)
    assert "키가 틀렸거나 만료" in llm and "OPENAI_API_KEY" in llm
    stt = next(l for l in lines if l.lstrip().startswith("STT") and "점검 실패" in l)
    assert "잔액" in stt and "한도" in stt                    # 429 는 두 원인을 가르지 못한다 — 둘 다 적는다
    tts = next(l for l in lines if l.lstrip().startswith("TTS") and "점검 실패" in l)
    assert "인터넷" in tts
    # 줄마다 무엇이 안 되는지 — 그리고 대본 공연은 계속된다는 것
    assert "관람객 질문 답" in out and "음성인식" in out and "관람객 답 목소리" in out
    assert "대본 공연" in out and "계속" in out
    # reachy.sh 가 감독 콘솔 위로 밀리기 전에 빨간 묶음으로 다시 보이는 목록
    pf = _preflight(stack)
    assert [lvl for lvl, _ in pf].count("bad") == 3, pf
    assert any("OPENAI_API_KEY" in t for _, t in pf) and any("음성인식" in t for _, t in pf)
    assert "\x1b[" not in out                                 # 터미널이 아니면 색 코드를 싣지 않는다


@pytest.mark.parametrize("kind,want", [
    ("5xx", "일시 오류"), ("timeout", "인터넷"), ("4xx", "openai-gateway.log"), (None, "openai-gateway.log"),
])
def test_외부_전용_LLM_실패_종류마다_할_일이_다르다(stack, capsys, kind, want):
    _Fake.plan = {"/v1/chat/completions": (502, kind)}
    warmup.main(_env(stack))
    llm = next(l for l in capsys.readouterr().out.splitlines() if l.lstrip().startswith("LLM"))
    assert "점검 실패" in llm and want in llm, llm


def test_외부_전용인데_게이트웨이가_안_떠_있으면_그렇게_말한다(stack, capsys, monkeypatch):
    monkeypatch.setattr(warmup, "LLM_URL", "http://127.0.0.1:9/v1/chat/completions")
    warmup.main(_env(stack))
    llm = next(l for l in capsys.readouterr().out.splitlines() if l.lstrip().startswith("LLM"))
    assert "점검 실패" in llm and "게이트웨이" in llm and "응답하지 않는다" in llm, llm


def test_외부_전용_TTS_401_은_크레딧도_보라고_한다(stack, capsys):
    """ElevenLabs 는 크레딧이 바닥나도 401 을 줄 수 있다(실측 안 함) — 키만 의심하게 두지 않는다."""
    _Fake.plan = {"/v1/audio/speech": (502, "401")}
    warmup.main(_env(stack))
    tts = next(l for l in capsys.readouterr().out.splitlines() if l.lstrip().startswith("TTS") and "점검 실패" in l)
    assert "ELEVENLABS_API_KEY" in tts and "크레딧" in tts


def test_외부_전용이_다_되면_점검_목록이_비고_0을_돌려준다(stack, capsys):
    stack["credits"] = (7_429, 131_000)                       # 123,571 남음 — 문턱 위
    assert warmup.main(_env(stack)) == 0
    out = capsys.readouterr().out
    assert "점검 실패" not in out and "크레딧 남음 123,571 / 131,000" in out
    assert _preflight(stack) == []


@pytest.mark.parametrize("used,limit,level,word", [
    (7_429, 131_000, "ok", None),
    (122_000, 131_000, "warn", "10,000"),                     # 9,000 남음 — U2 호박 문턱
    (129_500, 131_000, "bad", "2,000"),                       # 1,500 남음 — U2 빨강 문턱(답 약 15개분)
], ids=["넉넉", "호박", "빨강"])
def test_크레딧이_문턱_아래면_경고한다(stack, capsys, used, limit, level, word):
    stack["credits"] = (used, limit)
    warmup.main(_env(stack))
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if "크레딧" in l)
    assert f"{limit - used:,} / {limit:,}" in line
    pf = _preflight(stack)
    if level == "ok":
        assert pf == []
    else:
        assert word in line and [lvl for lvl, _ in pf] == [level], pf
    if level == "bad":
        assert "15개" in line                                 # 답 하나 약 100 크레딧 — 몇 개 남았는지로 말한다
    assert warmup.CREDITS_WARN == 10_000 and warmup.CREDITS_BAD == 2_000


def test_크레딧_조회가_실패해도_한_줄_경고하고_계속한다(stack, capsys, monkeypatch):
    import tts_elevenlabs as el

    def boom(key):
        raise el.ElevenLabsError(0, "URLError: timed out")
    monkeypatch.setattr(warmup, "credits_left", boom)
    assert warmup.main(_env(stack)) == 0                      # 조회 실패는 예열 실패가 아니다(합성은 됐다)
    line = next(l for l in capsys.readouterr().out.splitlines() if "크레딧" in l)
    assert "확인하지 못했다" in line and "timeout" in line
    assert [lvl for lvl, _ in _preflight(stack)] == ["warn"]


def test_로컬_구성의_예열_문구는_그대로다(stack, capsys):
    """스위치 없음(로컬 모델 on) — 로컬 예열 실패는 원래 "느려질 뿐" 이다. 문구·종료코드가 예전과 같고, 크레딧을 묻지 않는다."""
    _Fake.plan = {"/v1/chat/completions": (502, None)}
    rc = warmup.main({"REACHY_PREFLIGHT_OUT": str(stack["out"]), "TTS_BACKEND": "qwen"})
    out = capsys.readouterr().out
    assert rc == 1
    assert "   LLM  프리픽스 캐시 건너뜀 (HTTPError)" in out.splitlines()
    assert "점검 실패" not in out and "크레딧" not in out and "대본 공연" not in out
    assert stack["looked"] == [] and _preflight(stack) == []


def test_점검_목록_파일은_실행마다_새로_쓴다(stack, capsys):
    """reachy.sh 가 지난 실행의 빨간 줄을 이번 것처럼 다시 보이면 안 된다."""
    stack["out"].write_text("bad\t지난 실행의 줄\n", encoding="utf-8")
    warmup.main(_env(stack))
    assert _preflight(stack) == []
