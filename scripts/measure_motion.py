"""1분 대본을 실제로 돌리며 로봇이 굳어 있는 구간이 없는지 잰다.

`GET /api/state/full` 을 10Hz 로 샘플링해 발화 구간과 겹쳐 본다.
핵심 지표는 '발화 중인데 움직이지 않은 시간'이다 — 애니메이터를 넣은 이유가
답변이 길어질 때 로봇이 멍하니 있는 것을 없애는 것이기 때문.

실행: .venv/bin/python scripts/measure_motion.py     (LLM·STT·데몬 필요)
"""

from __future__ import annotations

import contextlib
import sys
import threading
import time
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))

from demo import build, respond  # noqa: E402

STATE_URL = "http://127.0.0.1:8000/api/state/full"
KEYS = ["x", "y", "z", "roll", "pitch", "yaw"]
SAMPLE_HZ = 10.0

# 1분 남짓 나오도록 짠 대본. 시연 시나리오와 같은 결이다.
SCRIPT = [
    "안녕!",
    "너는 무슨 일을 할 수 있어?",
    "네가 가지고 있는 지식이 어디까지야?",
    "재밌는 얘기 하나 해줘",
    "헐 대박!",
    "고마워, 잘 있어",
]

# 이 값보다 작게 움직인 1초 창은 '굳었다'로 본다.
# 호흡만 있을 때가 약 0.7deg 이므로 그보다 낮게 잡는다.
FROZEN_DEG_PER_SEC = 0.5


class Sampler(threading.Thread):
    def __init__(self, speaker, player):
        super().__init__(daemon=True)
        self._speaker, self._player = speaker, player
        self._stop = threading.Event()
        self.rows: list[tuple[float, np.ndarray, bool, bool]] = []

    def run(self) -> None:
        dt = 1.0 / SAMPLE_HZ
        while not self._stop.is_set():
            t0 = time.time()
            try:
                s = requests.get(STATE_URL, timeout=2).json()
                pose = np.array([s["head_pose"][k] for k in KEYS] + list(s["antennas_position"]))
                self.rows.append((time.time(), pose, self._speaker.speaking, self._player.busy))
            except Exception:
                pass
            rest = dt - (time.time() - t0)
            if rest > 0:
                time.sleep(rest)

    def stop(self) -> None:
        self._stop.set()


def analyse(rows) -> None:
    if len(rows) < 20:
        print("샘플이 부족하다")
        return
    t0 = rows[0][0]
    ts = np.array([r[0] - t0 for r in rows])
    poses = np.array([r[1] for r in rows])
    speaking = np.array([r[2] for r in rows])
    busy = np.array([r[3] for r in rows])

    # 프레임 간 변화량(도) — 회전 6성분 + 안테나 2성분을 합산
    deltas = np.abs(np.diff(poses, axis=0))
    deg = np.degrees(deltas[:, 3:]).sum(axis=1) + deltas[:, :3].sum(axis=1) * 1000
    mid_speak, mid_busy = speaking[1:], busy[1:]

    total = ts[-1]
    print(f"\n총 {total:.1f}초, 샘플 {len(rows)}개")
    print(f"  발화 중      {mid_speak.mean() * 100:5.1f}%")
    print(f"  녹화모션 중  {mid_busy.mean() * 100:5.1f}%")

    # 1초 창 단위로 굳음 판정
    frozen_windows, speak_windows, worst = 0, 0, 0.0
    for start in np.arange(0, total - 1.0, 1.0):
        m = (ts[1:] >= start) & (ts[1:] < start + 1.0)
        if m.sum() < 3:
            continue
        if not mid_speak[m].any():
            continue  # 발화 구간만 본다
        speak_windows += 1
        moved = deg[m].sum()
        worst = max(worst, 0.0)
        if moved < FROZEN_DEG_PER_SEC:
            frozen_windows += 1
            print(f"  ⚠ {start:5.1f}초 창: 발화 중인데 {moved:.2f}deg 만 움직임")

    print(f"\n  발화 중 1초 창 {speak_windows}개 중 굳은 창 {frozen_windows}개")
    spk = deg[mid_speak & ~mid_busy]
    idl = deg[~mid_speak & ~mid_busy]
    if spk.size:
        print(f"  발화 중 움직임   평균 {spk.mean() * SAMPLE_HZ:6.2f} deg/s")
    if idl.size:
        print(f"  조용할 때 움직임 평균 {idl.mean() * SAMPLE_HZ:6.2f} deg/s")
    print("\n판정:", "굳는 구간 없음 ✅" if frozen_windows == 0 else f"굳는 구간 {frozen_windows}개 ❌")


if __name__ == "__main__":
    with contextlib.ExitStack() as stack:
        llm, speaker, player = build(stack)
        sampler = Sampler(speaker, player)
        sampler.start()
        time.sleep(1.0)
        wall = time.time()
        for line in SCRIPT:
            print(f"\n나> {line}")
            respond(line, llm, speaker, player)
        print(f"\n대본 소요 {time.time() - wall:.1f}초")
        time.sleep(1.0)
        sampler.stop()
        analyse(sampler.rows)
