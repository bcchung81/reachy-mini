"""소프트웨어 음향 에코 제거(AEC) 설정 — 스피커로 말하면서 듣기 위한 것.

끼어들기를 이어폰 없이 쓰려면 마이크에 섞여 들어오는 **로봇 자기 목소리**를
지워야 한다. 실기는 XMOS 하드웨어 AEC 가 하고, 시뮬에서는 GStreamer 의
WebRTC Audio Processing(`webrtcdsp` + `webrtcechoprobe`)이 그 자리를 채운다.

동작 방식은 하나뿐이다 — **재생 경로에 프로브를 달아 far-end 를 기록하고,
캡처 경로의 `webrtcdsp` 가 그 신호를 빼는 것.** 그래서 둘은 한 프로세스 안에서
같은 이름으로 짝지어야 한다(`probe=` 속성). 재생이 PortAudio 로 나가면 프로브가
아무것도 못 보므로, AEC 를 켜면 재생도 GStreamer 로 나간다.

기본값은 **꺼짐**이다. 켜는 순간 재생 경로가 통째로 바뀌므로, 검증 전까지는
기존 PortAudio 경로(상주 스트림)를 정본으로 둔다.

주의: `noise-suppression` 과 `gain-control` 은 기본으로 끈다. 예전에 데몬의
webrtcdsp 가 "음성을 깎는다"고 기록된 적이 있는데(`audio_in.py` §9),
STT 품질을 깎는 것은 대개 이 둘이다. 에코 제거만 쓰고 나머지는 손대지 않는다.
"""

import os


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() not in ("0", "false", "no")


# AEC 를 켠다 — 재생(webrtcechoprobe) + 캡처(webrtcdsp) 가 함께 바뀐다.
ENABLED = _flag("REACHY_AEC")

# 프로브 이름 — 재생 쪽 요소 이름과 캡처 쪽 probe 속성이 이 값으로 만난다.
PROBE_NAME = os.environ.get("REACHY_AEC_PROBE", "reachy_echo_probe")

# webrtcdsp/echoprobe 가 받는 레이트는 8/16/32/48k 뿐이다. 마이크가 이미
# 16k 라 둘 다 16k 로 맞춘다 — 리샘플 한 번을 아낀다.
RATE = int(os.environ.get("REACHY_AEC_RATE", "16000"))

# 스피커→마이크 지연을 모를 때 켜 둔다. 우리 재생 경로는 지연이 고정이 아니라
# (앱 → GStreamer → CoreAudio) 이 모드가 사실상 필수다.
DELAY_AGNOSTIC = _flag("REACHY_AEC_DELAY_AGNOSTIC", "1")
# 잔향이 긴 방에서 필터 길이를 늘린다.
EXTENDED_FILTER = _flag("REACHY_AEC_EXTENDED_FILTER", "1")
# 아래 둘은 STT 품질을 깎는 쪽이라 기본 꺼짐 — 필요할 때만 켠다.
NOISE_SUPPRESSION = _flag("REACHY_AEC_NOISE_SUPPRESSION")
GAIN_CONTROL = _flag("REACHY_AEC_GAIN_CONTROL")
# 에코 억제 강도: low / moderate / high
SUPPRESSION_LEVEL = os.environ.get("REACHY_AEC_SUPPRESSION", "moderate")


def dsp_description() -> str:
    """캡처 파이프라인에 넣을 `webrtcdsp` 요소 문자열."""
    return (
        f"webrtcdsp probe={PROBE_NAME} echo-cancel=true"
        f" delay-agnostic={str(DELAY_AGNOSTIC).lower()}"
        f" extended-filter={str(EXTENDED_FILTER).lower()}"
        f" echo-suppression-level={SUPPRESSION_LEVEL}"
        f" noise-suppression={str(NOISE_SUPPRESSION).lower()}"
        f" gain-control={str(GAIN_CONTROL).lower()}"
        " high-pass-filter=true"
    )
