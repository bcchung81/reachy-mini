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


# ── 부트스트랩 — 실기에서 터진 것 (2026-09-08) ───────────────────
# 증상: 마이크는 잡히는데 STT 가 한 번도 안 불렸다. 로그는 2분 내내
#   `[대기 중] 마이크 최대 0.503 / VAD 임계 0.010 · 발화 모으는 중`.
# 원인: 소음 표본은 **대기 상태에서만** 쌓이는데 실기 바닥(0.09~0.50)이 초기
#   임계(0.010)보다 높아 첫 프레임에서 발화 상태로 들어간 뒤 못 빠져나온다 →
#   표본이 안 쌓임 → 임계가 0.010 에 묶임 → 발화가 영영 안 끝난다.
LOUD_FLOOR = 0.20   # 실기 XMOS(AGC) 무음 바닥의 대표값


def _floor(v=LOUD_FLOOR):
    return np.full(FRAME, v, dtype=np.float32)


def test_소음_바닥이_초기_임계보다_높아도_스스로_빠져나온다():
    vad = EnergyVAD()
    for _ in range(int(12 / 0.03)):     # 과길이 한도(기본 10초)를 넘겨 먹인다
        vad.feed(_floor())
    assert not vad.active, "바닥 소음에 발화 상태로 갇혔다"
    assert vad.threshold > LOUD_FLOOR, f"바닥 위로 임계가 안 올라갔다: {vad.threshold}"


def test_과길이_발화는_STT로_넘기지_않는다():
    """10초를 0.7초 쉼 없이 이어 말하는 일은 드물다. 잡음 덩어리를 STT 에 넘기면
    환각 응답으로 로봇이 혼자 떠든다 — 침묵보다 나쁘다."""
    vad = EnergyVAD()
    outs = [vad.feed(_floor()) for _ in range(int(12 / 0.03))]
    assert all(o is None for o in outs), "잡음 덩어리가 STT 로 넘어갔다"


def test_발화_버퍼가_무한정_자라지_않는다():
    """상한이 없으면 약 63KB/s(≈226MB/시간) 로 자란다 — RAM 4GB CM4 는 못 버틴다."""
    vad = EnergyVAD()
    peak, amp = 0.0, LOUD_FLOOR
    for _ in range(int(60 / 0.03)):
        amp *= 1.002                    # 임계를 계속 따라 넘는 최악의 입력
        vad.feed(_floor(amp))
        peak = max(peak, vad.buffered_s)
    assert peak <= 11.0, f"버퍼가 상한을 넘었다: {peak:.1f}s"


def test_바닥이_높아진_뒤_그_위의_발화를_잡는다():
    vad = EnergyVAD()
    for _ in range(int(12 / 0.03)):     # 부트스트랩
        vad.feed(_floor())
    out = None
    for _ in range(20):                 # 0.6초 발화
        got = vad.feed(_floor(0.90))
        out = got if got is not None else out
    for _ in range(40):                 # 1.2초 바닥 → hangover 초과
        got = vad.feed(_floor())
        out = got if got is not None else out
    assert out is not None, "높은 바닥 위의 발화를 못 잘랐다"


def test_손잡이를_설정_사다리로_읽는다(monkeypatch):
    """실기에서 앱은 systemd 데몬의 자식이라 **환경변수가 안 닿는다**(§10).
    VAD 손잡이도 stt/llm/tts 와 같이 config.json 으로 바꿀 수 있어야 한다."""
    import audio_in
    import config

    monkeypatch.setattr(
        config, "get", lambda name, default: "9.0" if name == "REACHY_VAD_FACTOR" else default
    )
    assert audio_in.EnergyVAD()._factor == 9.0


# ── 정숙·대기모션 취소 게이트 (실기 2026-09-08) ──────────────────
# 증상: 질의응답은 되는데 몸통이 초기 자세에 굳어 있었다. 몸통은 녹화 모션에서만
#   움직이는데(`driver._secondary` 는 yaw 를 늘 0.0 으로 낸다), 대기 모션이
#   시작되자마자 `set_user_speaking(True)` 로 취소되고 sway 도 접혔다.
# 원인: 게이트 입력이 `vad.active` — **임계를 한 프레임만 넘어도 참**이다.
#   소음 바닥이 임계에 붙은 방에서는 잡음마다 몸이 굳는다.
def test_잡음_한_프레임은_발화로_보고하지_않는다():
    vad = EnergyVAD()
    for _ in range(40):
        vad.feed(_floor(0.001))      # 조용한 바닥으로 적응
    vad.feed(_floor(0.5))            # 잡음 한 프레임(30ms)
    assert vad.active, "발화 수집 자체는 시작돼야 한다(프리롤 보존)"
    assert not vad.speaking, "한 프레임 잡음을 '사용자 발화'로 보고했다"


def test_발화가_쌓이면_발화로_보고한다():
    vad = EnergyVAD()
    for _ in range(40):
        vad.feed(_floor(0.001))
    for _ in range(12):              # 0.36초 > min_speech_s(0.25)
        vad.feed(_floor(0.5))
    assert vad.speaking, "실제 발화가 쌓였는데 보고하지 않았다"


def test_발화가_끝나면_보고가_내려간다():
    vad = EnergyVAD()
    for _ in range(40):
        vad.feed(_floor(0.001))
    for _ in range(12):
        vad.feed(_floor(0.5))
    for _ in range(40):              # 1.2초 침묵 → hangover 초과
        vad.feed(_floor(0.001))
    assert not vad.speaking and not vad.active


# ── 과길이 발화: 바닥이 잡혀 있으면 말이다 (리뷰 A6) ─────────────────


def test_바닥이_잡힌_뒤의_긴_질문은_버리지_않는다(capsys):
    """관람객이 10초 넘게 물으면 버퍼로 바닥을 재파종해 임계가 음성×3 으로
    튀었고, 1.5초 침묵 전까지 다음 질문을 못 들었다. 바닥이 이미 잡혀 있으면
    그 위의 긴 소리는 잡음이 아니라 말이다."""
    vad = EnergyVAD()
    for f in frames_of("silence", 3.0):        # 바닥 부트스트랩(표본 ≥30)
        vad.feed(f)
    th_before = vad.threshold
    outs = [vad.feed(f) for f in frames_of("speech", 11.0)]
    got = [o for o in outs if o is not None]
    assert len(got) == 1, "긴 발화가 통째로 버려졌다"
    assert len(got[0]) >= RATE * 9
    assert vad.threshold == th_before, "발화 버퍼로 바닥이 재파종됐다"
    assert vad.overlong_passed == 1 and vad.overlong_resets == 0
    assert "과길이" in capsys.readouterr().out
    # 곧바로 이어지는 보통 길이 질문도 들린다
    outs = run(vad, [("silence", 0.3), ("speech", 1.0), ("silence", SILENCE)])
    assert len(outs) == 1


def test_바닥이_안_잡혔을_때의_과길이는_여전히_버린다(capsys):
    vad = EnergyVAD()
    outs = [vad.feed(_floor()) for _ in range(int(12 / 0.03))]
    assert all(o is None for o in outs)
    assert vad.overlong_resets == 1
    assert "과길이" in capsys.readouterr().out
