"""가짜 공연 — 로봇 없이 교육자료 공연 모드를 확인한다(2026-11-12).

실제 시연에서는 로봇 2대(사회자·도슨트)가 말하고 교육자료 화면은 소리 없이 따라간다. 이 스크립트는 **진짜 대시보드 서버**
(`stage.dashboard.DashboardServer` — 관람객 소켓의 모양·필터·라벨 해석, `/stage/<이름>` 페이지 제공)를 띄우고, 감독이 공연할 때와
같은 순서·같은 라벨로 이벤트를 허브에 올린다:
    say(대사를 보냄) → speaking_started(로봇이 말하기 시작) → [로봇이 실제로 틀 길이만큼] → speaking_ended
길이는 **로봇이 실제로 틀 캐시 소리**에서 잰다 — 로봇 앱이 하는 문장 분할·요청 본문(`scripts/bake_tts.py::bodies_for`)으로 캐시 키를
만들어 그 PCM 길이를 더한다. 그래서 화면이 맞으면 실제 공연에서도 맞는다(남는 차이는 로봇의 문장 사이 간격·지연 — `--gap`·화면 `?lat=`).

사용:
    .venv/bin/python scripts/handout_live/fake_show.py [--port 18778] [--cues 01-intro,02-history] [--level 일반]
        [--engine elevenlabs] [--gap 0.05] [--lead 2] [--qa] [--loop]
    → 브라우저로 http://127.0.0.1:18778/stage/paper (공연 모드가 기본)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

PCM_BYTES_PER_S = 24000 * 2


def say(msg: str) -> None:
    """진행 줄은 바로 내보낸다 — 출력을 파일로 돌리면 버퍼에 남은 채 프로세스가 꺼져 로그가 사라졌다(작업자 D 가 봄)."""
    print(msg, flush=True)


def show_lines(cue, level: str) -> list[tuple[str, str, str]]:
    """큐 하나를 감독이 말하게 하는 순서 — (역할, 발화 라벨, 대사). 라벨 규칙은 `stage/say_label.py` 와 같다
    (마지막 도슨트 설명은 `<큐>:docent`, 그 앞은 `<큐>:pt<i>:docent`, 첫 포인트에는 질문이 없다)."""
    out = [("mc", cue.id, cue.mc)]
    n = len(cue.points)
    for i, t in enumerate(cue.points):
        if t.ask:
            out.append(("mc", f"{cue.id}:pt{i}", t.ask))
        out.append(("docent", f"{cue.id}:docent" if i == n - 1 else f"{cue.id}:pt{i}:docent", t.answers[level]))
    if cue.mc_after:
        out.append(("mc", f"{cue.id}:after", cue.mc_after))
    return out


def spoken_seconds(role: str, text: str, cache_dir: pathlib.Path, gap: float, warn=say) -> float:
    """로봇이 이 대사를 말하는 길이 — 로봇 경로 그대로 문장을 나눠 캐시 PCM 길이를 더한다. 캐시에 없으면 어림(6.6자/초)."""
    import bake_tts
    from tts_cache_proxy import cache_key
    total, parts = 0.0, bake_tts.bodies_for(bake_tts.Line(role, text, "fake", None, ""))
    for sentence, body in parts:
        p = cache_dir / f"{cache_key(body)}.pcm"
        if p.is_file():
            total += p.stat().st_size / PCM_BYTES_PER_S
        else:
            warn(f"  ⚠ 캐시에 없다 — 어림한다: {sentence[:30]!r}")
            total += len(sentence) / 6.6
    return total + gap * max(0, len(parts) - 1)


class FakeDirector:
    """대시보드가 묻는 것만 답한다 — 스냅샷·큐 목록·큐시트."""

    def __init__(self, cues, level: str) -> None:
        self._cues, self.level = tuple(cues), level
        self.cue_id, self.state, self.speaking_role, self.running = None, "idle", None, False

    def cues(self):
        return self._cues

    def cue_list(self):
        return [{"id": c.id, "title": c.title, "topic": c.topic or c.title} for c in self._cues]

    def level_names(self):
        return [self.level]

    def snapshot(self):
        ids = [c.id for c in self._cues]
        return {"cue_id": self.cue_id, "cue_index": ids.index(self.cue_id) if self.cue_id in ids else None,
                "cue_count": len(ids), "state": self.state, "speaking_role": self.speaking_role,
                "question_wait_s": None, "question_wait_total_s": None, "mode": "podcast",
                "show_running": self.running, "level": self.level, "course": "전체", "course_position": None}


def run_show(hub, director, plan, gap_turn: float, lead: float, qa: bool, log=say) -> None:
    """감독처럼 이벤트를 올린다. plan: [(cue_id, [(역할, 라벨, 대사, 초)])]."""
    seq = 0
    time.sleep(lead)
    director.running = True
    for cue_id, lines in plan:
        director.cue_id = cue_id
        log(f"▶ {cue_id}")
        for role, label, text, secs in lines:
            seq += 1
            director.state, director.speaking_role = "speaking", role
            hub.publish("sent", role=role, type="say", fields={"cue_id": label, "seq": seq, "text": text})
            time.sleep(0.12)                                     # 감독 → 로봇 → 큐에 넣고 시작 보고까지
            hub.publish("recv", role=role, type="speaking_started", fields={"cue_id": label, "seq": seq})
            log(f"  {role:6} {label:24} {secs:5.1f}초  {text[:28]}")
            time.sleep(secs)
            hub.publish("recv", role=role, type="speaking_ended", fields={"cue_id": label, "seq": seq})
            director.state, director.speaking_role = "listening", None
            time.sleep(gap_turn)
        if qa:
            # 관람객 질문 한 번 — 생성 답이라 화면은 글을 싣지 않고 멈춰 있어야 한다.
            for role, label, secs in (("mc", f"{cue_id}:ack", 2.0), ("docent", f"{cue_id}:qa", 4.0)):
                seq += 1
                hub.publish("sent", role=role, type="say", fields={"cue_id": label, "seq": seq, "text": "(생성 답)"})
                hub.publish("recv", role=role, type="speaking_started", fields={"cue_id": label, "seq": seq})
                log(f"  {role:6} {label:24} {secs:5.1f}초  (관람객 질문 흐름)")
                time.sleep(secs)
                hub.publish("recv", role=role, type="speaking_ended", fields={"cue_id": label, "seq": seq})
        time.sleep(1.5)
    director.running, director.state = False, "idle"
    log("■ 끝")


def main() -> int:
    from websockets.sync.server import serve

    from stage.cues import load_cues
    from stage.dashboard import DashboardServer
    from stage.dashboard_hub import DashboardHub
    from tts_cache_proxy import default_cache_dir

    ap = argparse.ArgumentParser(description="가짜 공연 — 교육자료 공연 모드 확인용")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18778, help="감독 대시보드(8778)와 겹치지 않게 기본 18778")
    ap.add_argument("--cues", default="01-intro,02-history", help="쉼표로(빈 값이면 전부)")
    ap.add_argument("--level", default="일반")
    ap.add_argument("--engine", default=os.environ.get("TTS_ENGINE") or "elevenlabs")
    ap.add_argument("--gap", type=float, default=0.05, help="로봇의 문장 사이 간격(초, 추정 — 리허설에서 잰다)")
    ap.add_argument("--turn-gap", type=float, default=0.6, help="발화 사이 간격(초)")
    ap.add_argument("--lead", type=float, default=3.0, help="공연 시작 전 대기(초) — 페이지를 열 시간")
    ap.add_argument("--qa", action="store_true", help="큐마다 관람객 질문 흐름을 한 번 끼운다")
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()

    all_cues = load_cues()
    want = [c.strip() for c in args.cues.split(",") if c.strip()]
    cues = [c for c in all_cues if not want or c.id in want]
    if want and len(cues) != len(want):
        sys.exit(f"✗ 모르는 큐: {sorted(set(want) - {c.id for c in cues})}")
    cache_dir = default_cache_dir(args.engine)
    plan = [(c.id, [(r, lab, txt, spoken_seconds(r, txt, cache_dir, args.gap)) for r, lab, txt in show_lines(c, args.level)])
            for c in cues]

    hub, director = DashboardHub(), FakeDirector(all_cues, args.level)
    ds = DashboardServer(hub, director, warn=lambda m: say(f"  [대시보드] {m}"))
    srv = serve(ds.handler, args.host, args.port, process_request=ds.process_request)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://{args.host}:{args.port}/stage"
    say(f"가짜 공연 — {base}/paper(일반) · {base}/webtoon(초등·중고등) · {base}/exploded(전문가) — 수준 {args.level}, 캐시 {cache_dir}")
    try:
        while True:
            run_show(hub, director, plan, args.turn_gap, args.lead, args.qa)
            if not args.loop:
                break
        time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
