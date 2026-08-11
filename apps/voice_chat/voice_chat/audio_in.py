"""마이크 캡처(GStreamer) + 에너지 VAD.

임계 RMS 0.010은 실측 기반 — 노이즈 바닥 0.0014, 음성 0.068 (설계문서 §2).
데몬 마이크를 쓰지 않고 직접 캡처한다 — 시뮬의 webrtcdsp가 음성을 깎는다(§9).
실기 배포 시 이 파일 전체가 SDK 미디어 백엔드로 교체된다.
"""

import collections
import os

import numpy as np


class EnergyVAD:
    """프레임 흐름에서 발화 구간을 잘라낸다. feed()가 발화 종료 시 전체 발화를 반환.

    **임계는 고정이 아니라 주변 소음의 배수다.** 고정 0.010 은 마이크·거리·장비가
    바뀌면 그대로 깨진다 — 실측으로 겪었다: 이득을 1.0 으로 되돌렸더니 사용자 목소리가
    0.003~0.012 로 잡혀 임계(0.010)를 못 넘었고, 로봇이 **아무 말도 못 알아들었다.**
    조용한 방에서는 임계가 하한까지 내려가 작은 목소리도 잡고, 시끄러운 방에서는
    소음을 따라 올라간다. `REACHY_VAD_ADAPTIVE=0` 으로 예전 동작(고정)으로 돌린다.
    """

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
        self._adaptive = os.environ.get("REACHY_VAD_ADAPTIVE", "1").lower() not in (
            "0", "false", "no",
        )
        # 소음 바닥의 몇 배를 임계로 볼지, 그리고 아무리 조용해도 이 아래로는 안 내린다.
        self._factor = float(os.environ.get("REACHY_VAD_FACTOR", "3.0"))
        self._floor_min = float(os.environ.get("REACHY_VAD_MIN", "0.005"))
        self._noise: collections.deque = collections.deque(maxlen=100)  # 3초
        self._hangover_s = hangover_s
        self._min_speech_s = min_speech_s
        self._pre_roll: collections.deque = collections.deque(
            maxlen=max(1, int(pre_roll_s / 0.03))
        )
        self._voiced: list[np.ndarray] = []
        self._silence_s = 0.0
        self._speech_s = 0.0

    @property
    def threshold(self) -> float:
        """지금 쓰는 임계 — 소음 바닥이 쌓이면 그 배수로, 아니면 초기값 그대로."""
        if not self._adaptive or len(self._noise) < 30:
            return self._threshold
        return max(self._floor_min, float(np.median(self._noise)) * self._factor)

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        frame_s = len(frame) / self._rate
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
        threshold = self.threshold

        if not self._voiced:  # 대기 상태
            # 발화가 아닌 구간만 소음 바닥으로 삼는다
            self._noise.append(rms)
            if rms >= threshold:
                self._voiced = [*self._pre_roll, frame]  # 프리롤로 어두 보존
                self._silence_s = 0.0
                self._speech_s = frame_s
            else:
                self._pre_roll.append(frame)
            return None

        self._voiced.append(frame)  # 발화 중
        if rms >= threshold:
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

    @property
    def active(self) -> bool:
        """지금 발화를 모으는 중인가 — 끼어들기 유예를 연장할지 판단하는 데 쓴다."""
        return bool(self._voiced)

    def reset(self) -> None:
        """게이팅 구간을 빠져나올 때 상태를 비운다 — 잔여 프레임이 발화로 오인되지 않게."""
        self._voiced = []
        self._pre_roll.clear()
        self._silence_s = 0.0
        self._speech_s = 0.0


class MicCapture:
    """GStreamer 마이크 → 16kHz mono float32 프레임 이터레이터.

    소스는 `autoaudiosrc` 다 — 플랫폼에 맞는 것을 GStreamer 가 고른다.
    **`osxaudiosrc` 를 박아 두면 실기(CM4/Linux)에서 엘리먼트가 없어
    `parse_launch` 부터 실패한다.** macOS 에서도 `autoaudiosrc` 로 캡처되는 것을
    확인했으므로 시뮬 쪽 손해는 없다.
    특정 장치를 강제하려면 `REACHY_MIC_SRC` 로 소스 엘리먼트를 통째로 지정한다
    (예: `alsasrc device=hw:1`).
    """

    def _start(self, chain: str):
        """파이프라인을 세우고 **PLAYING 까지 갔는지 확인한다.**

        확인이 핵심이다. webrtcdsp 는 짝이 되는 에코 프로브를 못 찾으면 READY 에서
        멈추는데, 그러면 appsink 의 pull-sample 이 영영 반환하지 않아 앱이 통째로
        굳는다(실측: 대기 모션만 돌고 말은 못 알아듣는 상태). 여기서 걸러 내고
        호출부가 AEC 없는 파이프라인으로 물러난다.
        """
        Gst = self._Gst
        try:
            pipe = Gst.parse_launch(
                f"{chain} ! appsink name=sink max-buffers=64 drop=true sync=false"
            )
        except Exception as e:  # noqa: BLE001
            print(f"  [마이크 경고] 파이프라인을 만들지 못했다: {e}", flush=True)
            return None
        pipe.set_state(Gst.State.PLAYING)
        if pipe.get_state(5 * Gst.SECOND)[1] != Gst.State.PLAYING:
            pipe.set_state(Gst.State.NULL)
            return None
        return pipe

    def __init__(self, rate: int = 16000, chunk_s: float = 0.03):
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        self._Gst = Gst
        self._rate = rate
        self._chunk = int(rate * chunk_s)
        src = os.environ.get("REACHY_MIC_SRC", "autoaudiosrc")
        # 마이크 입력 이득. 실측에서 사용자 목소리가 마이크에 0.020~0.022 로만 잡혀
        # VAD 임계(0.010)·끼어들기 임계(0.014)와의 여유가 거의 없었다. 이득을 올리면
        # 절대 임계와의 여유가 생긴다(에코도 같이 커지지만, 끼어들기의 double-talk
        # 판정은 비율 기반이라 영향받지 않는다).
        gain = float(os.environ.get("REACHY_MIC_GAIN", "1.0"))
        amp = f"volume volume={gain} ! " if abs(gain - 1.0) > 1e-6 else ""
        # AEC 를 켜면 F32 로 바꾸기 **전에** webrtcdsp 를 통과시킨다 —
        # 이 요소는 S16LE 8/16/32/48k 만 받는다. 재생 쪽 프로브(tts.GstEchoPlayer)와
        # 같은 이름으로 짝지어져 로봇 자기 목소리를 빼 준다(tts.EchoProbeTap).
        import aec

        if aec.ENABLED:
            stage = (
                f"audioconvert ! audioresample "
                f"! audio/x-raw,format=S16LE,channels=1,rate={aec.RATE} "
                f"! {aec.dsp_description()} "
                f"! audioconvert ! audioresample ! {amp}"
                f"audio/x-raw,format=F32LE,channels=1,rate={rate}"
            )
        else:
            stage = (
                f"audioconvert ! audioresample ! {amp}"
                f"audio/x-raw,format=F32LE,channels=1,rate={rate}"
            )
        self._pipe = self._start(f"{src} ! {stage}")
        if self._pipe is None and aec.ENABLED:
            # AEC 단이 기동을 막았다 — 에코 제거를 포기하더라도 **듣기는 해야 한다.**
            # 여기서 막히면 pull-sample 이 영영 반환하지 않아 앱이 통째로 굳는다.
            # **이득({amp})은 유지한다.** 예전 폴백은 이득 요소를 빠뜨려서,
            # REACHY_MIC_GAIN=2.5 를 걸어 둔 환경에서 AEC 만 실패했는데 캡처가
            # 조용히 1.0 배로 돌았다 — 목소리가 VAD 임계를 못 넘어 로봇이
            # 귀머거리가 되는데 로그에는 이유가 없었다(리뷰 확인).
            print(
                "  [마이크 경고] AEC 파이프라인이 기동하지 않는다 — "
                "webrtcdsp 없이 계속한다(끼어들기를 켰다면 자기 목소리에 반응할 수 있다)",
                flush=True,
            )
            self._pipe = self._start(
                f"{src} ! audioconvert ! audioresample ! {amp}"
                f"audio/x-raw,format=F32LE,channels=1,rate={rate}"
            )
        if self._pipe is None:
            raise RuntimeError("마이크 파이프라인을 기동하지 못했다")
        self._sink = self._pipe.get_by_name("sink")
        self._sink.set_property("emit-signals", False)

    def frames(self):
        """블로킹 이터레이터 — chunk_s 간격의 float32 배열을 낸다.

        `pull-sample` 이 안 돌아오면 앱은 조용히 굳는다(실측: AEC 파이프라인이
        READY 에 머물렀을 때). 그 침묵을 구분할 수 있게 지연을 감시한다.
        """
        import time as _time

        leftover = np.empty(0, dtype=np.float32)
        warned = False
        while True:
            t0 = _time.time()
            sample = self._sink.emit("pull-sample")
            waited = _time.time() - t0
            if waited > 2.0 and not warned:
                warned = True
                print(
                    f"  [마이크 경고] 프레임이 {waited:.1f}초 만에 왔다 —"
                    " 캡처가 막히고 있다(AEC 파이프라인 확인)",
                    flush=True,
                )
            if sample is None:  # EOS/종료
                print("  [마이크 경고] 캡처가 끝났다(EOS) — 더 이상 듣지 않는다", flush=True)
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
