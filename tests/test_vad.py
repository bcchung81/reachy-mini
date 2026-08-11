import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from audio_in import EnergyVAD

RATE = 16000
FRAME = int(RATE * 0.03)  # 30ms


def frames_of(kind: str, seconds: float):
    n = int(seconds / 0.03)
    rng = np.random.default_rng(0)
    for _ in range(n):
        if kind == "silence":
            yield (rng.standard_normal(FRAME) * 0.001).astype(np.float32)  # 노이즈 바닥
        else:
            yield (rng.standard_normal(FRAME) * 0.05).astype(np.float32)  # 발화 수준


def run(vad, sequence):
    outs = []
    for kind, sec in sequence:
        for f in frames_of(kind, sec):
            r = vad.feed(f)
            if r is not None:
                outs.append(r)
    return outs


# 침묵 구간은 기본 hangover(0.70s)보다 길어야 발화가 종료된다
SILENCE = 1.0


def test_발화가_한_덩어리로_잘린다():
    outs = run(EnergyVAD(), [("silence", 0.5), ("speech", 1.0), ("silence", SILENCE)])
    assert len(outs) == 1
    assert len(outs[0]) >= RATE * 0.9  # 프리롤 포함 대략 1초 이상


def test_짧은_잡음은_무시된다():
    outs = run(EnergyVAD(), [("silence", 0.5), ("speech", 0.1), ("silence", SILENCE)])
    assert outs == []


def test_두_발화는_두_덩어리():
    outs = run(
        EnergyVAD(),
        [("speech", 0.8), ("silence", SILENCE), ("speech", 0.8), ("silence", SILENCE)],
    )
    assert len(outs) == 2


def test_문장_중간_짧은_뜸은_발화를_끊지_않는다():
    # "…어디까지 [0.5초 쉼] 있어?" 처럼 종결어미 앞에서 뜸을 들여도 한 덩어리여야 한다
    outs = run(
        EnergyVAD(),
        [("speech", 0.8), ("silence", 0.5), ("speech", 0.5), ("silence", SILENCE)],
    )
    assert len(outs) == 1


# ── 적응 임계 ───────────────────────────────────────────────────
def test_조용한_마이크에서도_발화를_잡는다():
    """고정 임계 0.010 은 마이크·거리·장비가 바뀌면 그대로 깨진다.

    실측: 마이크 이득을 1.0 으로 되돌렸더니 사용자 목소리가 0.009~0.012 로 잡혀
    임계를 못 넘었고, 로봇이 **아무 말도 못 알아들었다.**
    """
    import numpy as np

    from audio_in import EnergyVAD

    vad = EnergyVAD()
    # 조용한 방(소음 0.0008)에서 3초쯤 대기
    for _ in range(60):
        vad.feed(np.full(480, 0.0008, dtype=np.float32))
    assert vad.threshold < 0.010, f"조용한 방에서 임계가 안 내려갔다: {vad.threshold}"

    # 그 상태에서 0.009 짜리 작은 목소리 0.5초 + 침묵
    out = None
    for _ in range(17):
        vad.feed(np.full(480, 0.009, dtype=np.float32))
    for _ in range(30):
        got = vad.feed(np.full(480, 0.0008, dtype=np.float32))
        out = out if got is None else got
    assert out is not None, "작은 목소리를 발화로 못 잡았다"


def test_시끄러운_방에서는_임계가_올라간다():
    import numpy as np

    from audio_in import EnergyVAD

    vad = EnergyVAD()
    for _ in range(60):
        vad.feed(np.full(480, 0.004, dtype=np.float32))
    assert vad.threshold > 0.010, "소음을 따라 올라가지 않았다"


def test_적응을_끌_수_있다(monkeypatch):
    import importlib

    import numpy as np

    import audio_in

    monkeypatch.setenv("REACHY_VAD_ADAPTIVE", "0")
    importlib.reload(audio_in)
    try:
        vad = audio_in.EnergyVAD()
        for _ in range(60):
            vad.feed(np.full(480, 0.0008, dtype=np.float32))
        assert vad.threshold == 0.010, "고정 모드인데 임계가 움직였다"
    finally:
        monkeypatch.delenv("REACHY_VAD_ADAPTIVE")
        importlib.reload(audio_in)
