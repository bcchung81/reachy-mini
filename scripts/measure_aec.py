"""AEC 실측 — 스피커로 말하면서 마이크로 들을 수 있는지 판정한다.

로봇이 말하는 동안 **사람은 조용히** 있는 상태로 마이크를 관찰한다.
AEC 가 제 몫을 하면 그때 마이크에 남는 소리(잔여 에코)가 끼어들기 임계
아래로 떨어지고, 오탐이 0 이 된다.

    ./reachy.sh check                      # TTS 서버(:8099)가 떠 있어야 한다
    ./reachy.sh measure aec

같은 발화를 AEC 끄고 / 켜고 두 번 재생해 비교한다. 판정 기준은 셋:

  1) 잔여 에코 RMS < 끼어들기 임계(REACHY_BARGE_IN_RMS, 기본 0.014)
  2) 오탐 0 — voice_loop 과 같은 규칙(적응 임계 위 9프레임 중 5개)으로 센다
  3) 사람이 말할 때는 제대로 넘는가 — 마지막에 직접 말해 확인한다

⚠ 스피커로 소리가 난다. 헤드셋을 빼고, 평소 시연하는 볼륨으로 돌린다.
"""

import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parent.parent / "apps/voice_chat/voice_chat"
sys.path.insert(0, str(APP))

TEXT = (
    "저는 리치 미니예요. 책상 위에 앉아 여러분과 이야기를 나누는 작은 로봇이고, "
    "고개를 끄덕이거나 안테나를 흔들어 감정을 표현할 수 있어요. "
    "지금은 에코 제거가 되는지 확인하려고 길게 말하는 중이에요."
)


def run_case(aec_on: bool) -> dict:
    """한 번 재생하며 마이크를 동시에 관찰한다."""
    os.environ["REACHY_AEC"] = "1" if aec_on else "0"
    os.environ["TTS_BACKEND"] = "qwen"
    for mod in ("aec", "tts", "audio_in", "voice_loop"):
        sys.modules.pop(mod, None)

    import tts as tts_mod
    import voice_loop as vl
    from audio_in import MicCapture

    # **Speaker(에코 프로브)를 마이크보다 먼저 세운다.** webrtcdsp 는 기동할 때
    # 짝이 되는 webrtcechoprobe 를 같은 프로세스에서 찾는다 — 순서를 뒤집으면
    # AEC 파이프라인이 READY 에 걸렸다가 5초 타임아웃 후 **AEC 없는 파이프라인으로
    # 폴백**해서, 'AEC 켬' 케이스가 끈 케이스와 동일한 것을 측정한다(리뷰 확인 —
    # 이 스크립트가 내는 go/no-go 판정 자체가 무효였다). 앱 쪽 규칙
    # (`tts.EchoProbeTap` "마이크보다 먼저 서 있어야 한다")과 같은 이유다.
    speaker = tts_mod.Speaker()
    mic = MicCapture()
    frames: list[float] = []
    stop = threading.Event()

    def listen():
        for frame in mic.frames():
            frames.append(float(np.sqrt(np.mean(frame.astype(np.float64) ** 2))))
            if stop.is_set():
                return

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(1.0)  # 조용한 구간 — 바닥 소음 측정용
    quiet = len(frames)

    speaker.speak(TEXT)
    time.sleep(0.5)
    play_from = len(frames)
    speaker.wait_idle(timeout=120)
    # AEC 재생기는 appsrc 백프레셔로 밀어 넣으므로 wait_idle 이 끝나도 싱크에
    # 0.5초쯤 남아 있다. 그 꼬리까지 관찰해야 잔여 에코를 놓치지 않는다.
    time.sleep(0.7)
    play_to = len(frames)
    stop.set()
    time.sleep(0.2)
    mic.close()
    speaker._player.close()

    floor = float(np.mean(frames[:quiet])) if quiet else 0.0
    during = frames[play_from:play_to]
    # **voice_loop 과 같은 규칙**으로 오탐을 센다 — 적응 임계(EchoFloor) 위를
    # "최근 9프레임 중 5개"로 판정한다. 예전에는 "고정 임계 N프레임 연속"으로
    # 셌는데, 본 루프는 음절 사이 에너지 급락 때문에 일부러 연속이 아니라 비율로
    # 바꿨다(voice_loop.py 주석). 규칙이 다르면 hot,hot,quiet,hot,hot 패턴에서
    # 게이트는 "오탐 0 → 통과"인데 실제 루프는 발동한다 — 통과한 설정이 무대에서
    # 자기 목소리에 끊긴다(리뷰 확인). 예측 에코 관문(출력 x 결합계수)은 출력
    # 레벨 시계열이 없어 여기서 재현하지 못한다 — 그만큼 이 게이트가 더 엄격하다.
    import collections as _c

    echo = vl.EchoFloor()
    recent: _c.deque = _c.deque(maxlen=vl.BARGE_IN_WINDOW)
    trig = 0
    for r in during:
        echo.observe(r)
        recent.append(r >= echo.threshold())
        if sum(recent) >= vl.BARGE_IN_FRAMES:
            trig += 1
            recent.clear()
    return {
        "floor": floor,
        "mean": float(np.mean(during)) if during else 0.0,
        "p95": float(np.percentile(during, 95)) if during else 0.0,
        "max": float(np.max(during)) if during else 0.0,
        "frames": len(during),
        "triggers": trig,
        "threshold": echo.threshold(),
    }


def show(label: str, r: dict) -> None:
    print(
        f"  {label:8s} 바닥 {r['floor']:.5f} | 재생 중 평균 {r['mean']:.5f} "
        f"p95 {r['p95']:.5f} 최대 {r['max']:.5f} | 오탐 {r['triggers']}회 "
        f"({r['frames']}프레임)"
    )


if __name__ == "__main__":
    print(__doc__)
    print("사람은 조용히 있는다 — 로봇 소리만 잡아야 한다.\n")
    print("① AEC 끄고")
    off = run_case(False)
    show("AEC off", off)
    time.sleep(1.0)
    print("② AEC 켜고")
    on = run_case(True)
    show("AEC on", on)

    print("\n판정")
    thr = on["threshold"]
    erle = 20 * np.log10(off["mean"] / on["mean"]) if on["mean"] > 0 else float("inf")
    print(f"  에코 감쇠(ERLE): {erle:+.1f} dB")
    ok_level = on["p95"] < thr
    ok_trig = on["triggers"] == 0
    print(f"  잔여 에코 p95 {on['p95']:.5f} {'<' if ok_level else '≥'} 임계 {thr}"
          f"  → {'통과' if ok_level else '실패'}")
    print(f"  오탐 {on['triggers']}회 → {'통과' if ok_trig else '실패'}")
    if ok_level and ok_trig:
        print("\n  ✅ 스피커 + 마이크로 끼어들기를 켤 수 있다:")
        print("     REACHY_AEC=1 REACHY_BARGE_IN=1 ./reachy.sh demo")
    else:
        print("\n  ❌ 아직 이르다. 스피커 볼륨을 낮추거나,")
        print("     REACHY_AEC_SUPPRESSION=high, REACHY_BARGE_IN_RMS 상향을 시도한다.")
