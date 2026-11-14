"""고정 대사 굽기(`scripts/bake_tts.py`, 2026-09-25).

핵심 계약: **굽기가 만든 요청 = 로봇이 보내는 요청.** 굽기는 로봇 앱의 함수(`clauses.split_sentences`·
`tts._qwen_body`·`main.apply_role_voice`)를 그대로 부르므로, 여기서는 그 결과가 로봇 경로와 같은지와
역할을 바꿀 때 목소리가 새지 않는지를 본다.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))
import bake_tts as bake  # noqa: E402
import clauses as robot_clauses  # noqa: E402
import main as robot_main  # noqa: E402
import tts as robot_tts  # noqa: E402

from tts_cache_proxy import INDEX_NAME, Cache, cache_key  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _역할_환경변수를_되돌린다(monkeypatch):
    """굽기는 역할마다 `os.environ` 에 목소리를 **직접** 넣는다(로봇 앱과 같은 방식). 실제로는 독립
    프로세스라 문제가 없지만, 테스트는 한 프로세스라 다음 테스트(`test_tts_backend` 등)가 그 목소리를
    물려받는다 — 실제로 깨졌다. monkeypatch 가 원래 상태(없음 포함)를 기억하도록 먼저 한 번 건드린다."""
    for k in bake._ROLE_ENV:
        monkeypatch.setenv(k, "__원래값_기록용__")
        monkeypatch.delenv(k)
    yield
    robot_tts.set_emotion("")


def test_여러_문장_대사는_로봇처럼_문장마다_요청한다():
    line = bake.Line("docent", " 전파는 발견이에요. 발명이 아니거든요. ", "t", "일반", "설명")
    got = bake.bodies_for(line)
    want = robot_clauses.split_sentences(line.text.strip())
    assert [s for s, _ in got] == want and len(want) == 2
    assert all(b["input"] == s for s, b in got)


def test_한_문장_대사는_통째로_요청한다():
    got = bake.bodies_for(bake.Line("mc", "  궁금한 점 있으실까요?  ", "t", None, "궁금"))
    assert [s for s, _ in got] == ["궁금한 점 있으실까요?"]


def test_역할을_바꿔도_앞_역할의_목소리가_새지_않는다(monkeypatch):
    """`apply_role_voice` 는 "이미 값이 있으면 안 덮는다" — 환경변수를 안 지우면 사회자 다음 도슨트가
    사회자 목소리로 구워진다. 운영자 셸에 남은 값도 같은 이유로 무시돼야 한다."""
    monkeypatch.setenv("TTS_QWEN_VOICE", "남은값")
    mc1 = bake.bodies_for(bake.Line("mc", "안녕하세요.", "t", None, "반가움"))[0][1]
    doc = bake.bodies_for(bake.Line("docent", "안녕하세요.", "t", "일반", "설명"))[0][1]
    mc2 = bake.bodies_for(bake.Line("mc", "안녕하세요.", "t", None, "반가움"))[0][1]
    rv = robot_main.ROLE_VOICE
    assert (mc1["voice"], mc1["speed"]) == (rv["mc"]["voice"], float(rv["mc"]["speed"]))
    assert (doc["voice"], doc["speed"]) == (rv["docent"]["voice"], float(rv["docent"]["speed"]))
    assert mc2 == mc1


def test_굽기_본문은_로봇의_본문_함수_결과와_같다():
    bake.use_role("docent")
    want = robot_tts._qwen_body("전파는 발견이에요.", None, stream=robot_tts.QWEN_STREAM)
    got = bake.bodies_for(bake.Line("docent", "전파는 발견이에요.", "t", "일반", "설명"))[0][1]
    assert got == want
    assert got["stream"] is True and got["response_format"] == "pcm"


def test_고정_대사는_큐시트와_감독_고정_멘트를_모두_덮는다():
    from stage.cues import QA_ACK_LINES, QUESTION_PROMPTS, SOLO_ACK_LINES, load_cues

    lines = bake.fixed_lines()
    texts = {l.text for l in lines}
    for c in load_cues():
        assert c.mc in texts and c.mc_after in texts
        for t in c.points:
            assert all(a in texts for a in t.answers.values())
    assert set(QA_ACK_LINES) <= texts and set(QUESTION_PROMPTS) <= texts
    assert set(SOLO_ACK_LINES) <= texts            # 단독 확인 멘트(2026-09-25)도 캐시 적중이어야 지연이 없다
    # 사과문(2026-11-14 A-2) — 인터넷이 끊기면 LLM 실패 → 사과문 → 캐시 빗나감 → ElevenLabs 실패 → 안내 한 번 뒤 무음.
    # 구워 두어야 두 번째 질문부터도 사과문이 들린다.
    from stage.director import QA_FALLBACK, SOLO_FALLBACK
    assert {QA_FALLBACK, SOLO_FALLBACK} <= texts
    from stage.cues import QA_REPROMPT_LINES
    assert set(QA_REPROMPT_LINES) <= texts         # 되묻기(2026-11-14 A-5)도 캐시 적중이어야 인터넷이 끊겨도 들린다
    # 큐시트의 도슨트 설명은 수준별이다. 사과문은 도슨트가 말해도 수준 공통이라 수준이 없다(None — 수준을 골라 구워도 들어간다).
    cue_docent = [l for l in lines if l.role == "docent" and l.text != QA_FALLBACK]
    assert cue_docent and all(l.level for l in cue_docent)
    assert all(l.level is None for l in lines if l.role == "mc" or l.text == QA_FALLBACK)


# ── 감독이 LLM 없이 말하는 고정 문장 전수(2026-11-14 A-2) ─────────────────────────
# 상수 목록을 손으로 맞추면 다음에 생기는 고정 대사를 또 빠뜨린다(사과문 둘이 그렇게 빠졌다). 그래서 **감독을 실제
# 큐시트로 돌리고 생성은 일부러 실패시켜** 감독이 내보내는 say 를 전부 모은다 — 생성물이 하나도 없으니 모인 것은 전부
# 고정 문장이다. 그 say 의 (역할, 문장, 감정)으로 만든 TTS 요청의 캐시 키가 굽기 계획에 있어야 한다 — 감정·역할이
# 감독과 다르면 같은 문장이라도 키가 빗나간다(계획 A-2 의 걱정).
def _director_fixed_says():
    import threading
    import time as _time

    from stage.cues import CueSheet, load_cues
    from stage.director import Director

    def boom(role, brief, history):
        raise RuntimeError("인터넷이 끊겼다(가짜)")

    sent, done, lock = [], set(), threading.Lock()

    def send(role, cmd):
        with lock:
            sent.append((role, cmd.type, dict(cmd.fields)))

    t = [0.0]
    d = Director(CueSheet(load_cues()), generate=boom, send=send, now=lambda: t[0], warn=lambda m: None,
                 level_name="일반")
    for role in ("mc", "docent"):                  # 두 대가 다 붙은 공연(1인 모드는 남은 로봇 목소리라 굽지 않는다)
        d.on_connect(role)
        d.on_hello(role, None, "1.9.0", caps=["emotion", "react", "gaze"])

    def says():
        with lock:
            return [(r, f) for r, ty, f in sent if ty == "say"]

    def pump():
        """보낸 say 를 차례로 '말이 끝났다' 고 되돌려 준다 — 새 say 가 안 나올 때까지(관람객 차례에서 멈춘다)."""
        for _ in range(400):
            todo = [(r, f) for r, f in says() if f["seq"] not in done]
            if not todo:
                return
            r, f = todo[0]
            done.add(f["seq"])
            d.on_speaking_ended(r, f["cue_id"], f["seq"])
        raise AssertionError("감독이 끝없이 말한다")

    def settle(n_before):
        """단독의 가벼운 말은 답을 스레드에서 낸다 — 새 say 가 올 때까지 잠깐 기다린다."""
        for _ in range(200):
            if len(says()) > n_before:
                return
            _time.sleep(0.01)

    d.start()
    pump()                                          # 첫 큐 오프닝 → 해설 → 받아치기 → 관람객 차례
    d.on_heard("마르코니가 누구예요?")               # 질문 → 확인 멘트 → (생성 실패) 사과문 → 재질문
    pump()
    for _ in range(3):                              # 확인 멘트·재질문은 돌아가며 쓴다 — 한 바퀴 다 본다
        d.on_heard("전파는 어떻게 가요?")
        pump()
    # 되묻기(2026-11-14 A-5) — 짧은 추임새 → 되묻기, 연달아 두 번째는 답(사과문), 다시 짧은 말 → 둘째 되묻기 문장
    for said in ("와 신기하다", "우와", "멋지다"):
        d.on_heard(said)
        pump()
    d.set_mode("solo")
    for q in ("마르코니가 누구예요?", "전파가 뭐예요?", "왜 그래요?"):   # 단독 — 확인 멘트 → 사과문
        d.on_heard(q)
        pump()
    n = len(says())
    d.on_heard("감사합니다")                        # 단독의 가벼운 말 — 확인 멘트 없이 사과문
    settle(n)
    pump()
    return [(r, f["text"], f.get("emotion", "")) for r, f in says()]


def test_감독이_LLM_없이_말하는_고정_문장은_전부_굽기_목록에_있다():
    from stage.director import QA_FALLBACK, SOLO_FALLBACK

    from stage.cues import QA_REPROMPT_LINES

    said = _director_fixed_says()
    texts = {t for _, t, _ in said}
    # 시나리오가 사과문 두 갈래·되묻기 두 문장을 실제로 지났는지 먼저 본다 — 안 지났으면 아래 대조는 헛통과다.
    assert QA_FALLBACK in texts and SOLO_FALLBACK in texts, texts
    assert set(QA_REPROMPT_LINES) <= texts, texts
    planned = {e["key"] for e in bake.plan(bake.fixed_lines())}
    missing = []
    for role, text, emotion in sorted(set(said)):
        for sentence, body in bake.bodies_for(bake.Line(role, text, "감독", None, emotion)):
            if cache_key(body) not in planned:
                missing.append((role, emotion, sentence))
    assert missing == [], f"굽기 목록에 없는(또는 역할·감정이 다른) 감독 대사: {missing}"


def test_사과문은_감독이_보내는_역할과_감정으로_굽는다():
    from stage.cues import QA_ANSWER_EMOTION
    from stage.director import QA_FALLBACK, SOLO_FALLBACK

    by_text = {l.text: l for l in bake.fixed_lines()}
    assert (by_text[QA_FALLBACK].role, by_text[QA_FALLBACK].emotion) == ("docent", QA_ANSWER_EMOTION)
    assert (by_text[SOLO_FALLBACK].role, by_text[SOLO_FALLBACK].emotion) == ("mc", QA_ANSWER_EMOTION)


def test_같은_문장은_한_번만_굽고_쓰이는_곳을_모은다():
    lines = [bake.Line("docent", "같은 문장이에요.", "a", "초등", "설명"),
             bake.Line("docent", "같은 문장이에요.", "b", "일반", "설명")]
    entries = bake.plan(lines)
    assert len(entries) == 1
    assert entries[0]["levels"] == ["초등", "일반"] and entries[0]["where"] == ["a", "b"]


def test_색인은_프록시가_그대로_읽는다(tmp_path):
    entries = bake.plan([bake.Line("mc", "안녕하세요.", "a", None, "반가움")])
    bake.write_index(tmp_path, entries)
    data = json.loads((tmp_path / INDEX_NAME).read_text())
    assert "body" not in data["entries"][0]                  # 본문 전체는 색인에 안 싣는다
    baked = Cache(tmp_path).baked_for("안녕하세요.")
    assert baked and baked[0]["key"] == cache_key(entries[0]["body"])


def test_점검_모드는_합성하지_않고_센다(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--check", "--cache-dir", str(tmp_path)])
    monkeypatch.setattr(bake, "synth", lambda *a: (_ for _ in ()).throw(AssertionError("합성했다")))
    assert bake.main() == 0
    out = capsys.readouterr().out
    assert "0개 구움" in out and "./reachy.sh bake" in out
    assert not (tmp_path / INDEX_NAME).exists()               # 점검은 아무것도 쓰지 않는다


def test_굽기는_빠진_것만_합성하고_원자적으로_쓴다(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(bake, "fixed_lines", lambda cues=None: [
        bake.Line("mc", "하나예요. 둘이에요.", "a", None, "설명")])
    monkeypatch.setattr(bake, "synth", lambda up, body: calls.append(body["input"]) or b"\x00\x01" * 100)
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--cache-dir", str(tmp_path)])
    assert bake.main() == 0
    assert calls == ["하나예요.", "둘이에요."]
    assert len(list(tmp_path.glob("*.pcm"))) == 2 and not list(tmp_path.glob("*.part"))
    calls.clear()
    assert bake.main() == 0
    assert calls == [], "있는 것을 다시 구웠다 — 바뀐 문장만 굽는다"


# ── ElevenLabs 엔진(2026-11-12) ────────────────────────────────────
import tts_elevenlabs as el  # noqa: E402


@pytest.fixture
def el_bake(monkeypatch):
    """외부 호출 없이 ElevenLabs 굽기 — 키·크레딧·합성을 바꿔 끼운다."""
    calls = []
    monkeypatch.delenv("TTS_ENGINE", raising=False)
    monkeypatch.delenv("TTS_EL_VOICES", raising=False)
    monkeypatch.setattr(bake, "fixed_lines", lambda cues=None: [bake.Line("mc", "안녕하세요.", "a", None, "설명")])
    monkeypatch.setattr(el, "load_api_key", lambda *a, **k: "sk_test")
    monkeypatch.setattr(el, "credits_left", lambda *a, **k: (0, 131000))
    monkeypatch.setattr(bake, "synth_el", lambda body, key, **kw: calls.append((body["input"], body["voice"], kw["model"])) or b"\x00\x01" * 50)
    monkeypatch.setattr(bake, "synth", lambda *a: (_ for _ in ()).throw(AssertionError("CrispASR 를 불렀다")))
    return calls


def test_EL_굽기는_안내를_역할마다_굽고_엔진_표지를_남긴다(tmp_path, monkeypatch, el_bake):
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--engine", "elevenlabs", "--cache-dir", str(tmp_path)])
    assert bake.main() == 0
    assert ("안녕하세요.", "serena", "eleven_v4_turbo") in el_bake
    assert (el.NOTICE_TEXT, "serena", "eleven_v4_turbo") in el_bake and (el.NOTICE_TEXT, "sohee", "eleven_v4_turbo") in el_bake
    data = json.loads((tmp_path / INDEX_NAME).read_text())
    assert data["engine"] == "elevenlabs"
    assert {e["voice"] for e in Cache(tmp_path).baked_for(el.NOTICE_TEXT)} == {"serena", "sohee"}


def test_다른_엔진으로_구운_폴더에는_굽지_않는다(tmp_path, monkeypatch, el_bake):
    (tmp_path / INDEX_NAME).write_text('{"entries": []}', encoding="utf-8")   # 표지 없음 = 옛 Qwen 폴더
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--engine", "elevenlabs", "--cache-dir", str(tmp_path)])
    assert bake.main() == 2 and el_bake == []


def test_EL_force_는_확인_없이는_검수한_테이크를_덮지_않는다(tmp_path, monkeypatch, el_bake):
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--engine", "elevenlabs", "--force", "--cache-dir", str(tmp_path)])
    assert bake.main() == 2 and el_bake == []
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--engine", "elevenlabs", "--force", "--confirm-retake",
                                      "--cache-dir", str(tmp_path)])
    assert bake.main() == 0 and el_bake


def test_EL_굽기는_크레딧이_모자라면_멈춘다(tmp_path, monkeypatch, el_bake):
    monkeypatch.setattr(el, "credits_left", lambda *a, **k: (130990, 131000))
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--engine", "elevenlabs", "--cache-dir", str(tmp_path)])
    assert bake.main() == 2 and el_bake == []


def test_EL_굽기는_키_없으면_멈춘다(tmp_path, monkeypatch, el_bake):
    monkeypatch.setattr(el, "load_api_key", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--engine", "elevenlabs", "--cache-dir", str(tmp_path)])
    assert bake.main() == 2 and el_bake == []


def test_EL_시드는_캐시_키에서_나오고_번역에_실린다(monkeypatch):
    seen = {}
    monkeypatch.setattr(el, "synth", lambda vid, payload, key, base=None: seen.update(vid=vid, **payload) or b"\x00\x00")
    body = {"input": "안녕하세요.", "voice": "sohee", "speed": 1.13, "stream": True, "response_format": "pcm"}
    bake.synth_el(body, "sk_test", voices=el.DEFAULT_VOICES, model="eleven_v4_turbo", readings=[])
    assert seen["vid"] == el.DEFAULT_VOICES["sohee"] and seen["seed"] == el.seed_for(cache_key(body))
    assert seen["language_code"] == "ko"


# ── 골라 다시 굽기(--retake, 2026-11-12) ───────────────────────────
@pytest.fixture
def two_lines(monkeypatch, el_bake):
    monkeypatch.setattr(bake, "fixed_lines", lambda cues=None: [
        bake.Line("mc", "초장파는 길어요.", "a", None, "설명"), bake.Line("mc", "밀리미터파는 짧아요.", "b", None, "설명")])
    return el_bake


def _bake(tmp_path, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["bake_tts.py", "--engine", "elevenlabs", "--cache-dir", str(tmp_path), *extra])
    return bake.main()


def test_다시_굽기는_낱말이_든_문장만_굽고_앞_테이크를_남긴다(tmp_path, monkeypatch, two_lines):
    assert _bake(tmp_path, monkeypatch) == 0
    first = {p.name: p.read_bytes() for p in tmp_path.glob("*.pcm")}
    two_lines.clear()
    monkeypatch.setattr(bake, "synth_el", lambda body, key, **kw: two_lines.append(body["input"]) or b"\x09\x00" * 50)
    assert _bake(tmp_path, monkeypatch, "--retake", "초장파") == 0
    assert two_lines == ["초장파는 길어요."], "고른 문장만 다시 구워야 한다"
    prev = list((tmp_path / bake.PREV_DIR).glob("*.pcm"))
    assert len(prev) == 1 and prev[0].read_bytes() == first[prev[0].name]       # 앞 테이크는 그대로 남는다
    assert (tmp_path / prev[0].name).read_bytes() == b"\x09\x00" * 50
    assert len(list(tmp_path.glob("*.pcm"))) == len(first)                      # 최상위에는 문장 수 그대로


def test_다시_굽기는_읽기_표기_사전의_낱말로_고를_수_있다(tmp_path, monkeypatch, two_lines):
    assert _bake(tmp_path, monkeypatch) == 0
    two_lines.clear()
    monkeypatch.setattr(el, "load_readings", lambda *a, **k: [("밀리미터파", "밀리미터 파")])
    assert _bake(tmp_path, monkeypatch, "--retake-readings") == 0
    assert [t for t, _, _ in two_lines] == ["밀리미터파는 짧아요."]


def test_다시_구울_문장이_없으면_크게_실패한다(tmp_path, monkeypatch, two_lines):
    assert _bake(tmp_path, monkeypatch, "--retake", "없는낱말") == 1
    assert two_lines == []


def test_검수의_테이크_표지는_소리가_바뀌면_바뀐다():
    sys.path.insert(0, str(ROOT / "scripts"))
    import tts_review
    assert tts_review.take_id(b"\x01\x00") != tts_review.take_id(b"\x02\x00")
    assert tts_review.take_id(b"\x01\x00") == tts_review.take_id(b"\x01\x00")


# ── 이득(여유 음량) — 섞어 굽지 않고, 합성 없이 맞춘다(2026-11-12) ──
def test_이득이_다른_폴더에는_이어_굽지_않고_regain_으로_음량만_맞춘다(tmp_path, monkeypatch, el_bake):
    import array
    loud = array.array("h", [20000, -20000] * 50).tobytes()
    assert _bake(tmp_path, monkeypatch) == 0
    idx = json.loads((tmp_path / INDEX_NAME).read_text())
    idx.pop("gain_db")                                     # 이득을 걸기 전에 구운 폴더(2026-11-12 첫 굽기)
    (tmp_path / INDEX_NAME).write_text(json.dumps(idx, ensure_ascii=False))
    for p in tmp_path.glob("*.pcm"):
        p.write_bytes(loud)
    el_bake.clear()
    assert _bake(tmp_path, monkeypatch) == 2, "이득이 다른 소리를 섞으면 안 된다"
    assert _bake(tmp_path, monkeypatch, "--regain") == 0
    assert el_bake == [], "음량만 맞춘다 — 합성하지 않는다"
    assert json.loads((tmp_path / INDEX_NAME).read_text())["gain_db"] == el.GAIN_DB
    want = el.apply_gain(loud, el.GAIN_DB)
    assert all(p.read_bytes() == want for p in tmp_path.glob("*.pcm"))
    assert _bake(tmp_path, monkeypatch) == 0                # 맞춘 뒤에는 그대로 이어 굽는다


def test_ElevenLabs_굽기는_여유_음량을_건다(monkeypatch):
    import array
    monkeypatch.setattr(el, "synth", lambda vid, payload, key, base=None: array.array("h", [32767] * 4).tobytes())
    body = {"input": "안녕하세요.", "voice": "sohee", "speed": 1.13, "stream": True, "response_format": "pcm"}
    out = array.array("h", bake.synth_el(body, "sk_test", voices=el.DEFAULT_VOICES, model="eleven_v4_turbo", readings=[]))
    assert max(out) < 32767 * 10 ** (-1 / 20) + 1
