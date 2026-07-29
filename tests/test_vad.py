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
