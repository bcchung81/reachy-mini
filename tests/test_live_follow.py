"""교육자료 공연 모드의 시계(`scripts/handout_live/live_follow.js` 의 `core`) — node 로 돌린다(2026-11-12).

실제 시연에서는 로봇 2대가 말하고 화면은 소리 없이 감독 이벤트를 따라간다. 이 계산이 틀리면 화면이 로봇보다 앞서거나
(다음 대목 그림이 먼저 나온다) 뒤처진다. node 가 없으면 건너뛴다(브라우저 쪽은 헤드리스 통합 확인이 본다).
"""

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOD = ROOT / "scripts" / "handout_live" / "live_follow.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node 가 없다")

CUES = [
    {"id": "01-intro", "dur": 11.6, "utt": [
        {"role": "mc", "turn": "open", "t0": 0.9, "t1": 3.0},
        {"role": "docent", "turn": "docent0", "t0": 3.5, "t1": 8.0},
        {"role": "mc", "turn": "after", "t0": 8.5, "t1": 10.0}]},
    {"id": "02-history", "dur": 6.0, "utt": [{"role": "mc", "turn": "open", "t0": 0.9, "t1": 4.0}]},
]


def run(steps):
    """steps: [["feed", 이벤트, 벽시계, 경과] | ["time", 벽시계] | ["state"]] → 각 단계의 결과 목록."""
    js = f"""
const lf = require({json.dumps(str(MOD))});
const c = lf.core({json.dumps(CUES)}, {{lat: 0.3}});
const out = [];
for (const s of {json.dumps(steps)}) {{
  if (s[0] === 'feed') out.push(c.feed(s[1], s[2], s[3] || 0));
  else if (s[0] === 'time') out.push(Math.round(c.timeAt(s[1]) * 1000) / 1000);
  else out.push({{cue: c.cue(), phase: c.phase(), speaking: c.speaking()}});
}}
console.log(JSON.stringify(out));
"""
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def ev(kind, cue, turn, role="mc"):
    return {"kind": kind, "cue": cue, "turn": turn, "role": role}


def test_대사가_나가면_큐를_바꾸고_소리가_나기_전에는_첫_장면에서_기다린다():
    out = run([["feed", ev("say", "01-intro", "open"), 100], ["time", 100], ["time", 105], ["state"]])
    assert out[0] is True and out[1] == 0 and out[2] == 0
    assert out[3]["cue"] == 0 and out[3]["phase"] == "script"


def test_발화_시작에_턴의_t0_로_앵커하고_소리_지연만큼_앞에서_출발한다():
    out = run([["feed", ev("say", "01-intro", "open"), 100],
               ["feed", ev("speaking_started", "01-intro", "open"), 100], ["time", 100], ["time", 101.3], ["state"]])
    assert out[2] == pytest.approx(0.6) and out[3] == pytest.approx(1.9)       # 0.9 - 0.3, +1.3초
    assert out[4]["speaking"] == {"role": "mc", "turn": "open"}


def test_끝_보고가_늦으면_턴_끝에서_멈춰_다음_대목_그림을_먼저_꺼내지_않는다():
    out = run([["feed", ev("speaking_started", "01-intro", "open"), 100], ["time", 110]])
    assert out[1] == pytest.approx(3.0 + 0.25)                                  # t1 + OVERRUN 에서 멈춘다


def test_로봇이_먼저_끝내면_턴_끝으로_맞추고_다음_턴_앵커_앞까지만_흘린다():
    out = run([["feed", ev("speaking_started", "01-intro", "docent0", "docent"), 100],
               ["feed", ev("speaking_ended", "01-intro", "docent0", "docent"), 102],    # 2초 만에 끝 보고(장면은 5.2)
               ["time", 102], ["time", 120], ["state"]])
    assert out[2] == pytest.approx(8.0)                                         # t1 로 맞춤
    assert out[3] == pytest.approx(8.5 - 0.3 - 0.05)                            # 다음 턴 앵커 바로 앞에서 멈춤
    assert out[4]["speaking"] is None


def test_다음_발화가_시작돼도_장면이_뒤로_튀지_않는다():
    out = run([["feed", ev("speaking_started", "01-intro", "docent0", "docent"), 100],
               ["feed", ev("speaking_ended", "01-intro", "docent0", "docent"), 104.8],
               ["time", 120], ["feed", ev("speaking_started", "01-intro", "after"), 120], ["time", 120]])
    assert out[3] is False and out[4] >= out[2] - 1e-9


def test_관람객_질문_흐름은_장면을_멈추고_말하는_로봇만_표시한다():
    out = run([["feed", ev("speaking_started", "01-intro", "docent0", "docent"), 100], ["time", 101],
               ["feed", ev("say", "01-intro", "qa", "docent"), 101], ["feed", ev("speaking_started", "01-intro", "qa", "docent"), 101],
               ["time", 130], ["state"]])
    assert out[4] == pytest.approx(out[1])                                      # 질문 동안 장면은 그 자리
    assert out[5]["phase"] == "qa" and out[5]["speaking"]["turn"] == "qa"


def test_모르는_라벨은_장면을_건드리지_않는다():
    out = run([["feed", ev("speaking_started", "01-intro", "open"), 100],
               ["feed", {"kind": "say", "cue": None, "turn": None, "role": "mc"}, 101],
               ["feed", ev("speaking_started", "99-none", "open"), 101], ["state"], ["time", 101]])
    assert out[1] is False and out[2] is False and out[3]["cue"] == 0 and out[4] == pytest.approx(1.6)


def test_공연_도중에_붙으면_경과만큼_앞에서_시작한다():
    out = run([["feed", ev("speaking_started", "01-intro", "docent0", "docent"), 100, 2.0], ["time", 100]])
    assert out[1] == pytest.approx(3.5 - 0.3 + 2.0)


def test_스냅샷은_아직_큐를_모를_때만_큐를_정한다():
    out = run([["feed", {"kind": "snapshot", "cue_id": "02-history", "show_running": True}, 100], ["state"],
               ["feed", {"kind": "snapshot", "cue_id": "01-intro", "show_running": True}, 101], ["state"]])
    assert out[0] is True and out[1]["cue"] == 1
    assert out[2] is False and out[3]["cue"] == 1                               # 이벤트가 정한 큐를 스냅샷이 뒤집지 않는다


def test_큐가_바뀌면_새_큐의_처음에서_기다린다():
    out = run([["feed", ev("speaking_started", "01-intro", "after"), 100], ["time", 101],
               ["feed", ev("say", "02-history", "open"), 102], ["time", 103], ["state"]])
    assert out[2] is True and out[3] == 0 and out[4]["cue"] == 1


def test_모듈은_외부_리소스를_부르지_않고_소켓으로_보내지_않는다():
    src = MOD.read_text(encoding="utf-8")
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", ".send(", "http://", "https://"):
        assert bad not in src, bad


def test_말하는_중에는_공연_아님_스냅샷이_상태를_대기로_덮지_않는다():
    """스냅샷은 0.5초마다 온다 — 방금 들어온 발화 상태를 덮으면 배지가 깜빡인다(통합 테스트에서 실제로 그랬다)."""
    out = run([["feed", ev("speaking_started", "01-intro", "open"), 100],
               ["feed", {"kind": "snapshot", "cue_id": "01-intro", "show_running": False}, 100.5], ["state"],
               ["feed", ev("speaking_ended", "01-intro", "open"), 102],
               ["feed", {"kind": "snapshot", "cue_id": "01-intro", "show_running": False}, 102.5], ["state"]])
    assert out[2]["phase"] == "script"
    assert out[5]["phase"] == "idle"                                            # 말이 끝났고 공연이 안 돈다 — 대기
