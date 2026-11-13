"""큐별 조사 자료를 질문 답 근거로(2026-11-13 — "단답형이 아니라 좀 더 풍부하게").

분량을 늘리면 근거 밖으로 채울 압력이 생긴다(`data/levels.yaml` 머리말) — 그래서 근거도 같이 늘린다: 검증 등급 A·B 사실과
바로잡은 것·확인 안 된 것. 출처 문자열(파일 경로·URL)은 싣지 않는다(모델이 읽으면 TTS 로 샌다).
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stage import research  # noqa: E402
from stage.research import research_brief  # noqa: E402


def _write(tmp_path, monkeypatch, body):
    (tmp_path / "x.yaml").write_text(body, encoding="utf-8")
    monkeypatch.setenv("REACHY_RESEARCH_DIR", str(tmp_path))


def test_A_B_사실과_금지_쪽을_싣고_C_와_출처는_뺀다(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, """
facts:
  - {claim: "**강조** 된 사실 하나.", source: "docs/exhibit-guide.md:55", grade: A}
  - {claim: "둘째 사실.", source: "https://example.org", grade: B}
  - {claim: "약한 사실.", source: "블로그", grade: C}
corrections: ["'10개 대역' 이라고 하지 않는다."]
unverifiable: ["전시품 개수 — 현장 확인 필요."]
""")
    r = research_brief("x")
    assert "강조 된 사실 하나." in r and "둘째 사실." in r and "약한 사실" not in r
    assert "exhibit-guide" not in r and "https://" not in r and "**" not in r
    assert "바로잡은 것" in r and "'10개 대역'" in r and "확인되지 않은 것" in r and "전시품 개수" in r


def test_상한을_넘으면_사실을_앞에서부터_남기고_금지_쪽은_지킨다(tmp_path, monkeypatch):
    facts = "\n".join(f'  - {{claim: "사실{i:02d} ' + "가" * 80 + '.", grade: A}' for i in range(40))
    _write(tmp_path, monkeypatch, f"facts:\n{facts}\ncorrections: [\"틀린 말을 하지 않는다.\"]\n")
    r = research_brief("x", max_chars=600)
    assert len(r) <= 600 and "사실00" in r and "사실39" not in r and "틀린 말을 하지 않는다" in r


def test_자료가_없거나_깨졌으면_None(tmp_path, monkeypatch):
    monkeypatch.setenv("REACHY_RESEARCH_DIR", str(tmp_path))
    assert research_brief("없는큐") is None
    (tmp_path / "깨짐.yaml").write_text("facts: [", encoding="utf-8")
    assert research_brief("깨짐") is None


def test_실제_조사_자료가_있는_큐는_근거가_생긴다():
    research._load.cache_clear()
    r = research_brief("15-emf")
    assert r and "검증된 사실" in r and len(r) <= research.MAX_CHARS
    assert "`" not in r and "docs/" not in r


def test_감독의_질문_답_근거에_조사_자료가_실린다():
    sys.path.insert(0, str(ROOT / "tests"))
    from test_stage_director import Harness
    from stage.cues import CueSheet, load_cues
    from stage.machine import State
    h = Harness(sheet=CueSheet(load_cues()))
    for r in ("mc", "docent"):
        h.d.on_connect(r)
    h.d.goto("15-emf")
    for _ in range(40):
        if h.d.state is State.LISTENING:
            break
        role, cid = next((r, f["cue_id"]) for r, t, f in reversed(h.all_sent) if t == "say")
        h.ended(role, cid)
    h.gen_calls.clear()
    h.d.on_heard("휴대폰 전자파는 몸에 해롭지 않나요?")
    for _ in range(100):
        if h.gen_calls:
            break
        import time
        time.sleep(0.02)
    brief = h.gen_calls[0][0]
    assert "조사 자료" in brief and "검증된 사실" in brief and "문서·자료 이름은 말하지 않는다" in brief
