"""마이크 캡처(GStreamer) + 에너지 VAD.

임계 RMS 0.010은 실측 기반 — 노이즈 바닥 0.0014, 음성 0.068 (설계문서 §2).
데몬 마이크를 쓰지 않고 직접 캡처한다 — 시뮬의 webrtcdsp가 음성을 깎는다(§9).
실기 배포 시 이 파일 전체가 SDK 미디어 백엔드로 교체된다.
"""

import collections
import os

import numpy as np


class EnergyVAD:
    """프레임 흐름에서 발화 구간을 잘라낸다. feed()가 발화 종료 시 전체 발화를 반환."""

    def __init__(
        self,
        rate: int = 16000,
        threshold: float = 0.010,
        # 한국어는 종결어미 앞에서 뜸을 들이는 일이 흔하다("…어디까지 [쉼] 있어?").
        # 0.30 이면 그 틈에 발화가 끊겨 질문이 잘린 채 전사된다.
        hangover_s: float = 0.70,
        min_speech_s: float = 0.25,
        pre_roll_s: float = 0.2,
    ):
        self._rate = rate
        self._threshold = threshold
        self._hangover_s = hangover_s
        self._min_speech_s = min_speech_s
        self._pre_roll: collections.deque = collections.deque(
            maxlen=max(1, int(pre_roll_s / 0.03))
        )
        self._voiced: list[np.ndarray] = []
        self._silence_s = 0.0
        self._speech_s = 0.0

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        frame_s = len(frame) / self._rate
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))

        if not self._voiced:  # 대기 상태
            if rms >= self._threshold:
                self._voiced = [*self._pre_roll, frame]  # 프리롤로 어두 보존
                self._silence_s = 0.0
                self._speech_s = frame_s
            else:
                self._pre_roll.append(frame)
            return None

        self._voiced.append(frame)  # 발화 중
        if rms >= self._threshold:
            self._silence_s = 0.0
            # 실제 발화량만 누적한다 — 버퍼 길이로 재면 프리롤과 hangover 가
            # 섞여 들어가 짧은 잡음이 발화로 통과한다.
            self._speech_s += frame_s
            return None
        self._silence_s += frame_s
        if self._silence_s < self._hangover_s:
            return None

        utterance = np.concatenate(self._voiced)  # 발화 종료
        speech_s = self._speech_s
        self.reset()
        return utterance if speech_s >= self._min_speech_s else None

    def reset(self) -> None:
        """게이팅 구간을 빠져나올 때 상태를 비운다 — 잔여 프레임이 발화로 오인되지 않게."""
        self._voiced = []
        self._pre_roll.clear()
        self._silence_s = 0.0
        self._speech_s = 0.0


class MicCapture:
    """GStreamer 마이크 → 16kHz mono float32 프레임 이터레이터.

    소스는 `autoaudiosrc` 다 — 플랫폼에 맞는 것을 GStreamer 가 고른다.
    **`osxaudiosrc` 를 박아 두면 실기(Pi5/Linux)에서 엘리먼트가 없어
    `parse_launch` 부터 실패한다.** macOS 에서도 `autoaudiosrc` 로 캡처되는 것을
    확인했으므로 시뮬 쪽 손해는 없다.
    특정 장치를 강제하려면 `REACHY_MIC_SRC` 로 소스 엘리먼트를 통째로 지정한다
    (예: `alsasrc device=hw:1`).
    """

    def __init__(self, rate: int = 16000, chunk_s: float = 0.03):
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        self._Gst = Gst
        self._rate = rate
        self._chunk = int(rate * chunk_s)
        src = os.environ.get("REACHY_MIC_SRC", "autoaudiosrc")
        self._pipe = Gst.parse_launch(
            f"{src} ! audioconvert ! audioresample "
            f"! audio/x-raw,format=F32LE,channels=1,rate={rate} "
            "! appsink name=sink max-buffers=64 drop=true sync=false"
        )
        self._sink = self._pipe.get_by_name("sink")
        self._sink.set_property("emit-signals", False)
        self._pipe.set_state(Gst.State.PLAYING)

    def frames(self):
        """블로킹 이터레이터 — chunk_s 간격의 float32 배열을 낸다."""
        leftover = np.empty(0, dtype=np.float32)
        while True:
            sample = self._sink.emit("pull-sample")
            if sample is None:  # EOS/종료
                return
            buf = sample.get_buffer()
            ok, info = buf.map(self._Gst.MapFlags.READ)
            if not ok:
                continue
            try:
                data = np.frombuffer(info.data, dtype=np.float32).copy()
            finally:
                buf.unmap(info)
            data = np.concatenate([leftover, data])
            while len(data) >= self._chunk:
                yield data[: self._chunk]
                data = data[self._chunk :]
            leftover = data

    def close(self) -> None:
        self._pipe.set_state(self._Gst.State.NULL)
