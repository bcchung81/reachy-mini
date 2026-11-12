"""ElevenLabs 어댑터(`tts_elevenlabs.py`)와 오디션(`scripts/el_audition.py`) — 외부 호출 없이 가짜 서버로.

계획 `docs/superpowers/plans/2026-11-12-elevenlabs-tts.md`. 키는 공개 저장소에서 가장 새기 쉬운 것이라
"메시지·로그에 키 값이 없다" 를 여기서 박제한다.
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tts_cache_proxy  # noqa: E402
import tts_elevenlabs as el  # noqa: E402

SECRET = "sk_test_DO_NOT_LEAK_0123456789"


# ── 키 ─────────────────────────────────────────────────────────────
def test_키는_환경변수가_먼저다(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"ELEVENLABS_API_KEY=from_file\n", encoding="utf-8")
    assert el.load_api_key({"ELEVENLABS_API_KEY": "from_env"}, f) == "from_env"


def test_키는_env_파일의_그_한_줄만_읽는다(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# 주석\nOPENAI_API_KEY=other\nexport ELEVENLABS_API_KEY=\"quoted\"\n", encoding="utf-8")
    assert el.load_api_key({}, f) == "quoted"


def test_키가_없거나_비었으면_None(tmp_path):
    assert el.load_api_key({}, tmp_path / "없는파일") is None
    f = tmp_path / ".env"
    f.write_text("ELEVENLABS_API_KEY=\n", encoding="utf-8")
    assert el.load_api_key({}, f) is None


def test_로그에_남기는_것은_설정됨_없음뿐이다():
    assert el.key_status(SECRET) == "설정됨"
    assert el.key_status(None) == "없음"


# ── 목소리·번역 ─────────────────────────────────────────────────────
def test_목소리_매핑을_읽고_형식이_틀리면_멈춘다():
    assert el.parse_voice_map("serena=A1, sohee=B2") == {"serena": "A1", "sohee": "B2"}
    assert el.parse_voice_map("") == {}
    with pytest.raises(ValueError):
        el.parse_voice_map("serena")


def test_번역은_목소리_ID와_모델과_읽기_표기를_쓰고_속도_어조는_싣지_않는다():
    body = {"input": "GMDSS 장비예요.", "model": "tts", "voice": "sohee", "speed": 1.13,
            "instructions": "차분하게", "stream": True, "response_format": "pcm"}
    before = json.dumps(body, sort_keys=True)
    vid, payload = el.el_request(body, voices={"sohee": "VID"}, model="eleven_v4",
                                 readings=[("GMDSS", "지엠디에스에스")], language_code="ko", seed=7)
    assert vid == "VID"
    assert payload == {"text": "지엠디에스에스 장비예요.", "model_id": "eleven_v4", "language_code": "ko", "seed": 7}
    # 캐시 키는 번역 전 로봇 본문으로 계산한다 — 번역이 본문을 바꾸면 키가 흔들린다.
    assert json.dumps(body, sort_keys=True) == before
    assert tts_cache_proxy.cache_key(body) == tts_cache_proxy.cache_key(json.loads(before))


def test_매핑이_없는_목소리는_아무_목소리로_내지_않고_멈춘다():
    with pytest.raises(el.VoiceNotMapped, match="serena"):
        el.el_request({"input": "안녕", "voice": "serena"}, voices={"sohee": "VID"}, model="eleven_v4")


def test_읽기_표기는_긴_낱말부터_바꾼다(tmp_path):
    f = tmp_path / "r.yaml"
    f.write_text("readings:\n  EHF: 이에이치에프\n  VLF: 브이엘에프\n  VLF·EHF: 브이엘에프와 이에이치에프\n", encoding="utf-8")
    r = el.load_readings(f)
    assert r[0][0] == "VLF·EHF"
    assert el.apply_readings("VLF·EHF 대역", r) == "브이엘에프와 이에이치에프 대역"
    assert el.load_readings(tmp_path / "없음.yaml") == []


# ── 호출(가짜 ElevenLabs) ──────────────────────────────────────────
class _Fake(BaseHTTPRequestHandler):
    script: list = []          # 차례로 돌려줄 (상태, 본문)
    seen: list = []

    def log_message(self, *a):
        return

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        _Fake.seen.append({"path": self.path, "key": self.headers.get("xi-api-key"),
                           "body": json.loads(self.rfile.read(n) or b"{}")})
        status, data = _Fake.script.pop(0)
        self.send_response(status)
        self.send_header("Content-Type", "audio/pcm" if status == 200 else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def fake():
    _Fake.script, _Fake.seen = [], []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _err(msg):
    return json.dumps({"detail": {"status": "x", "message": msg}}).encode()


def test_합성은_pcm_24000을_지정하고_키를_헤더로만_보낸다(fake):
    _Fake.script = [(200, b"\x01\x00" * 100)]
    pcm = el.synth("VID", {"text": "안녕", "model_id": "eleven_v4"}, SECRET, base=fake, sleep=lambda s: None)
    assert pcm == b"\x01\x00" * 100
    req = _Fake.seen[0]
    assert req["path"] == "/v1/text-to-speech/VID/stream?output_format=pcm_24000"
    assert req["key"] == SECRET and SECRET not in json.dumps(req["body"])


def test_오류_메시지에_키_값이_없다(fake):
    _Fake.script = [(401, _err("invalid api key"))]
    with pytest.raises(el.ElevenLabsError) as ei:
        el.synth("VID", {"text": "안녕", "model_id": "eleven_v4"}, SECRET, base=fake, sleep=lambda s: None)
    assert ei.value.status == 401
    assert SECRET not in str(ei.value) and SECRET not in repr(ei.value.args)


def test_동시_요청_초과_429는_쉬었다_다시_하고_400은_바로_실패한다(fake):
    _Fake.script = [(429, _err("too many")), (200, b"\x00\x00")]
    waits = []
    assert el.synth("VID", {"text": "a"}, SECRET, base=fake, sleep=waits.append) == b"\x00\x00"
    assert waits == [1]
    _Fake.script = [(400, _err("bad")), (200, b"\x00\x00")]
    with pytest.raises(el.ElevenLabsError):
        el.synth("VID", {"text": "a"}, SECRET, base=fake, sleep=lambda s: None)
    assert len(_Fake.script) == 1          # 400 뒤에는 다시 부르지 않았다


def test_라이브러리_목소리_첫_사용이_겹친_409는_다시_한다(fake):
    """처음 쓰는 라이브러리 목소리로 동시에 요청하면 자동 추가끼리 부딪혀 409 already_running 이 난다."""
    _Fake.script = [(409, _err("Multiple voice additions/deletions for the same voice")), (200, b"\x00\x00")]
    assert el.synth("VID", {"text": "a"}, SECRET, base=fake, sleep=lambda s: None) == b"\x00\x00"


def test_서버에_못_닿으면_상태_0으로_실패한다():
    with pytest.raises(el.ElevenLabsError) as ei:
        el.synth("VID", {"text": "a"}, SECRET, base="http://127.0.0.1:9", retries=0)
    assert ei.value.status == 0 and SECRET not in str(ei.value)


def test_크레딧_어림은_모델_배수를_따른다():
    assert el.credits_for("가" * 100, "eleven_v4") == 100
    assert el.credits_for("가" * 100, "eleven_v4_turbo") == 50


# ── 오디션 ─────────────────────────────────────────────────────────
def test_오디션_문장은_지금_대본에_모두_있다(monkeypatch):
    """대본이 바뀌어 문장이 사라지면 오디션이 멈춘다 — 여기서 먼저 알게 한다.

    `pick_sentences` 는 굽기 목록(`bake_tts.plan`)을 만들며 역할 목소리를 `os.environ` 에 **직접** 넣는다.
    그대로 두면 다음 테스트(`test_tts_backend`)가 사회자·도슨트 목소리를 물려받아 깨진다(2026-11-12 실제로 깨짐 —
    `tests/test_bake_tts.py` 머리의 픽스처와 같은 이유). monkeypatch 에 원래 상태를 기억시킨다.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import bake_tts
    import el_audition
    for k in bake_tts._ROLE_ENV:
        monkeypatch.setenv(k, "__원래값_기록용__")
        monkeypatch.delenv(k)
    try:
        sents = el_audition.pick_sentences()
    finally:
        robot_tts_mod = sys.modules.get("tts")
        if robot_tts_mod is not None:
            robot_tts_mod.set_emotion("")
    assert [s["label"] for s in sents] == [label for label, _ in el_audition.SENTENCES]
    assert all(s["text"] for s in sents)


def test_오디션_후보는_키가_겹치지_않고_ID가_있다():
    sys.path.insert(0, str(ROOT / "scripts"))
    import el_audition
    keys = [v["key"] for v in el_audition.CANDIDATES]
    assert len(keys) == len(set(keys))
    assert all(len(v["id"]) == 20 for v in el_audition.CANDIDATES)


# ── 프록시 ElevenLabs 엔진(관람객 답) ───────────────────────────────
sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))
import logging  # noqa: E402
import urllib.request  # noqa: E402

import tts as robot_tts  # noqa: E402
from tts_cache_proxy import INDEX_NAME, Cache, ElevenLabsLive, ProxyServer, cache_key  # noqa: E402

ROBOT_BODY = {"input": "좋은 질문이에요, 전파는 빛과 같은 속도로 가요.", "model": "tts", "voice": "serena",
              "speed": 1.27, "stream": True, "response_format": "pcm"}
EL_PCM = bytes(range(256)) * 30          # 7680 바이트 — 홀수 청크로 쪼개 보낸다


class _FakeEL(BaseHTTPRequestHandler):
    """ElevenLabs 스트리밍 흉내 — 청크 audio/pcm. fail 이면 500."""
    protocol_version = "HTTP/1.1"
    fail = False
    calls: list = []

    def log_message(self, *a):
        return

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        _FakeEL.calls.append({"path": self.path, "key": self.headers.get("xi-api-key"),
                              "body": json.loads(self.rfile.read(n))})
        if _FakeEL.fail:
            data = _err("upstream boom")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for i in range(0, len(EL_PCM), 1001):          # 샘플 경계와 안 맞는 홀수 청크
            c = EL_PCM[i:i + 1001]
            self.wfile.write(f"{len(c):X}\r\n".encode() + c + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


class _Local(BaseHTTPRequestHandler):
    """로컬 CrispASR 흉내 — `local` 정책 확인용."""
    protocol_version = "HTTP/1.1"
    calls: list = []

    def log_message(self, *a):
        return

    def do_GET(self):  # noqa: N802
        data = b'{"status": "ok"}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        _Local.calls.append(json.loads(self.rfile.read(n)))
        data = b"LOCAL!" * 100
        self.send_response(200)
        self.send_header("Content-Type", "audio/pcm")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _up(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def el_stack(tmp_path):
    _FakeEL.fail, _FakeEL.calls, _Local.calls = False, [], []
    fake_el, local = _up(_FakeEL), _up(_Local)
    cdir = tmp_path / "cache-elevenlabs"
    cdir.mkdir()
    made = []

    def make(on_fail="notice", local_up=True):
        live = ElevenLabsLive(key=SECRET, voices={"serena": "MCVOICE", "sohee": "DOCVOICE"},
                              on_fail=on_fail, base=f"http://127.0.0.1:{fake_el.server_port}")
        upstream = f"http://127.0.0.1:{local.server_port}" if local_up else "http://127.0.0.1:9"
        proxy = ProxyServer(("127.0.0.1", 0), upstream, Cache(cdir), live)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        made.append(proxy)
        return f"http://127.0.0.1:{proxy.server_port}"

    yield {"make": make, "dir": cdir}
    for p in made:
        p.shutdown()
    fake_el.shutdown()
    local.shutdown()


def _robot_speak(url, body, monkeypatch):
    """로봇이 여는 경로 그대로(`tts._qwen_open`). 첫 청크를 따로 돌려준다 — 로봇은 그게 비면 폴백한다."""
    monkeypatch.setattr(robot_tts, "QWEN_URL", url + "/v1/audio/speech")
    with robot_tts._qwen_open(body) as r:
        h = {k: r.headers.get(k) for k in ("Content-Type", "X-TTS-Cache", "X-TTS-Engine")}
        read = getattr(r, "read1", None) or r.read
        first = read(robot_tts._PCM_CHUNK)
        rest = []
        while True:
            c = read(robot_tts._PCM_CHUNK)
            if not c:
                break
            rest.append(c)
    return h, first, first + b"".join(rest)


def _bake_notice(cdir, voice, pcm):
    """굽기가 남기는 모양 그대로 — 안내 문장 색인 + 파일."""
    body = dict(ROBOT_BODY, input=el.NOTICE_TEXT, voice=voice)
    key = cache_key(body)
    (cdir / f"{key}.pcm").write_bytes(pcm)
    idx = {"engine": "elevenlabs", "entries": [{"key": key, "text": el.NOTICE_TEXT, "voice": voice}]}
    (cdir / INDEX_NAME).write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")


def test_EL_엔진_빗나감은_ElevenLabs_소리를_로봇_형식_그대로_흘린다(el_stack, monkeypatch):
    url = el_stack["make"]()
    h, first, pcm = _robot_speak(url, ROBOT_BODY, monkeypatch)
    assert pcm == el.apply_gain(EL_PCM)                    # 홀수 청크를 맞춰 흘려도 굽기와 같은 이득으로 같은 바이트
    assert h["Content-Type"] == "audio/pcm" and h["X-TTS-Cache"] == "miss" and h["X-TTS-Engine"] == "elevenlabs"
    call = _FakeEL.calls[0]
    assert call["path"] == "/v1/text-to-speech/MCVOICE/stream?output_format=pcm_24000"   # serena → 사회자 목소리
    assert call["body"]["model_id"] == "eleven_v4_turbo" and call["body"]["text"] == ROBOT_BODY["input"]
    assert call["key"] == SECRET


def test_EL_엔진도_구운_대사는_외부를_부르지_않는다(el_stack, monkeypatch):
    (el_stack["dir"] / f"{cache_key(ROBOT_BODY)}.pcm").write_bytes(b"\x07\x00" * 500)
    url = el_stack["make"]()
    h, _, pcm = _robot_speak(url, ROBOT_BODY, monkeypatch)
    assert h["X-TTS-Cache"] == "hit" and pcm == b"\x07\x00" * 500
    assert _FakeEL.calls == []                              # 네트워크가 끊겨도 대본 공연은 계속된다


def test_EL_실패하면_같은_목소리_안내를_한_번만_내고_나머지는_무음(el_stack, monkeypatch, caplog):
    _FakeEL.fail = True
    _bake_notice(el_stack["dir"], "serena", b"\x05\x00" * 800)
    url = el_stack["make"]()
    with caplog.at_level(logging.WARNING, logger="tts-proxy"):
        h1, _, p1 = _robot_speak(url, ROBOT_BODY, monkeypatch)
        h2, first2, p2 = _robot_speak(url, dict(ROBOT_BODY, input="다음 문장이에요."), monkeypatch)
    assert h1["X-TTS-Cache"] == "notice" and p1 == b"\x05\x00" * 800
    assert h2["X-TTS-Cache"] == "skip" and set(p2) == {0}
    # **빈 응답이면 로봇이 로컬 기계음으로 대신 말한다**(tts._open_qwen "첫 청크가 비었다") — 무음이라도 보낸다.
    assert first2, "첫 청크가 비었다 — 로봇이 say/espeak 로 폴백한다"
    warns = [r for r in caplog.records if "ElevenLabs 실패" in r.getMessage()]
    assert len(warns) == 1, "끊김 한 번에 경고는 한 줄"
    assert SECRET not in caplog.text


def test_EL_실패했는데_안내가_안_구워졌으면_무음과_경고(el_stack, monkeypatch, caplog):
    _FakeEL.fail = True
    url = el_stack["make"]()
    with caplog.at_level(logging.WARNING, logger="tts-proxy"):
        h, first, pcm = _robot_speak(url, ROBOT_BODY, monkeypatch)
    assert h["X-TTS-Cache"] == "skip" and first and set(pcm) == {0}
    assert "안내가 캐시에 없다" in caplog.text


def test_EL_실패_정책_local_은_로컬_TTS로_넘긴다(el_stack, monkeypatch):
    _FakeEL.fail = True
    url = el_stack["make"](on_fail="local")
    h, _, pcm = _robot_speak(url, ROBOT_BODY, monkeypatch)
    assert h["X-TTS-Cache"] == "fallback-local" and pcm == b"LOCAL!" * 100
    assert _Local.calls and _Local.calls[0]["input"] == ROBOT_BODY["input"]


def test_EL_매핑_없는_목소리도_로봇_폴백_대신_실패_정책을_탄다(el_stack, monkeypatch):
    url = el_stack["make"]()
    h, first, _ = _robot_speak(url, dict(ROBOT_BODY, voice="vivian"), monkeypatch)
    assert h["X-TTS-Cache"] == "skip" and first and _FakeEL.calls == []


def test_EL_헬스는_로컬이_죽어도_200이고_키는_설정됨만_싣는다(el_stack):
    url = el_stack["make"](local_up=False)
    with urllib.request.urlopen(url + "/health", timeout=5) as r:
        raw = r.read().decode()
    d = json.loads(raw)
    assert d["engine"] == "elevenlabs" and d["key"] == "설정됨" and d["local"].startswith("down")
    assert SECRET not in raw


def test_색인의_엔진_표지를_읽고_표지가_없는_옛_색인은_crispasr(tmp_path):
    c = Cache(tmp_path)
    assert c.engine() is None
    (tmp_path / INDEX_NAME).write_text('{"entries": []}', encoding="utf-8")
    assert Cache(tmp_path).engine() == "crispasr"
    (tmp_path / INDEX_NAME).write_text('{"engine": "elevenlabs", "entries": []}', encoding="utf-8")
    assert Cache(tmp_path).engine() == "elevenlabs"


def test_엔진마다_기본_캐시_폴더가_다르다(monkeypatch):
    import tts_cache_proxy as p
    monkeypatch.delenv("TTS_CACHE_DIR", raising=False)
    monkeypatch.setenv("TTS_ASSETS", "/x")
    assert str(p.default_cache_dir()) == "/x/cache"
    assert str(p.default_cache_dir("elevenlabs")) == "/x/cache-elevenlabs"


def test_정한_목소리가_기본이고_TTS_ENGINE_은_모르는_값에_멈춘다():
    assert el.voice_map({}) == {"serena": "hjCvGtSCRPyjYwe2lDf1", "sohee": "n2fbxG88jqAoaVPUy3IG"}
    assert el.voice_map({"TTS_EL_VOICES": "serena=X"}) == {"serena": "X"}
    assert el.engine_from_env({}) == "crispasr"
    with pytest.raises(ValueError):
        el.engine_from_env({"TTS_ENGINE": "elevenlab"})


# ── 검수(scripts/tts_review.py) ────────────────────────────────────
def test_검수_대조는_띄어쓰기_문장부호_천단위_쉼표를_무시한다():
    sys.path.insert(0, str(ROOT / "scripts"))
    import tts_review
    assert tts_review.similarity("약 3,500킬로미터 떨어진 곳이에요.", "약 3500 킬로미터 떨어진 곳이에요") == 1.0
    assert tts_review.similarity("초장파는 VLF예요.", "초장파는 브이엘에프예요") < 0.8   # 약어를 다르게 읽으면 낮다


# ── 여유 음량(2026-11-12) ───────────────────────────────────────────
def test_여유_음량은_dB_만큼_줄이고_0dB_는_그대로다():
    import array
    pcm = array.array("h", [32767, -32768, 1000, 0]).tobytes()
    assert el.apply_gain(pcm, 0.0) == pcm
    half = array.array("h", el.apply_gain(pcm, -6.0206))
    assert list(half) == [16384, -16384, 500, 0]
    assert el.GAIN_DB <= -1.0, "실기 16 kHz 변환에서 잘리지 않으려면 최소 -1 dB(실측)"


def test_검수_발음_대조는_맞춤법만_다른_같은_소리를_같다고_본다():
    """글자 대조의 헛경보(2026-11-12): 판은/파는(연음), 닉호/니코(거센소리), 맡/맞(받침 대표음), MHz·1000·DOCENT(STT 표기)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import tts_review as t
    for a, b in [("초장파는 VLF예요", "초장판은 VLF예요"), ("타이타닉호 이야기", "타이타니코 이야기"),
                 ("페달이 요를 맡습니다", "페달이 요를 맞습니다"), ("121.5메가헤르츠와", "121.5MHz와"),
                 ("천 번이면 1킬로헤르츠", "1000번이면 1kHz"), ("1제곱킬로미터당 백만 대", "1km²당 100만대"),
                 ("도슨트, 크로마키가", "DOCENT 크로마키가"), ("주파수에 반비례", "주파수의 반비례")]:
        assert t.same_sound(a, b), (a, b)
    # 소리가 다르면 다르다 — 그리고 어디가 다른지 낱말로 짚는다
    assert not t.same_sound("도슨트, 타이타닉호", "노슨트, 타이타니코")
    assert t.diffs("도슨트, 타이타닉호", "노슨트, 타이타니코") == [["도", "노"]]
    assert t.read_number("3,500") == "삼천오백" and t.read_number("121.5") == "백이십일점오"


def test_검수_판정은_한_글자라도_다르면_힌트_받아쓰기로_가른다():
    """~~문장 일치도 0.95~~ 는 긴 문장의 한 낱말 오류(도슨트→노슨트, 0.98)를 통과시켰다."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import tts_review as t
    text = "도슨트, 타이타닉호 이야기를 들려주실래요?"
    assert t.verdict({"text": text, "heard": "도슨트 타이타니코 이야기를 들려주실래요", "psim": 1.0}) == "ok"
    assert t.verdict({"text": text, "heard": "노슨트, 타이타니코 이야기를 들려주실래요?", "psim": 0.98,
                      "biased": text}) == "stt"
    assert t.verdict({"text": text, "heard": "노슨트, 타이타니코 이야기를 들려주실래요?", "psim": 0.98,
                      "biased": "노슨트, 타이타닉호 이야기를 들려주실래요?"}) == "suspect"
