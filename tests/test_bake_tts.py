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
    assert all(l.level for l in lines if l.role == "docent")
    assert all(l.level is None for l in lines if l.role == "mc")


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
