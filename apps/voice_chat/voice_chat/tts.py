"""TTS 큐 워커 — speak()는 즉시 반환, 백그라운드에서 순차 발화.

speaking 플래그는 큐 적재 순간 켜진다 — 마이크 게이팅이 소리보다
늦게 걸리면 에코가 새기 때문이다.

플래그를 큐가 비었는지로 판정하면 안 된다. 워커가 task_done() 직후
빈 큐를 확인하는 사이에 speak()가 끼어들면, 재생이 남았는데 플래그가
내려간다. 그래서 잠금으로 보호되는 대기 건수로 판정한다.
"""

import collections
import difflib
import io
import json
import math
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from typing import NamedTuple

import numpy as np

import aec

# ── 백엔드 선택 ──────────────────────────────────────────────────
# 기본은 채택 음색(Qwen3-TTS CustomVoice 화자 'serena')이다.
# macOS 유나로 되돌리려면 TTS_BACKEND=say.
#
# qwen 은 별도 서버(:8099)를 요구하므로 그게 죽으면 소리가 안 난다. 그래서
# **합성 실패 시 say 로 떨어뜨린다.** 대화 도중 음색이 바뀌는 건 어색하지만,
# 로봇이 조용히 벙어리가 되는 것보다는 훨씬 낫다.
BACKEND = os.environ.get("TTS_BACKEND", "qwen")

# 사다리: 환경변수 → 설정파일 → 기본값 (근거는 config.py 머리말)
import config as _config

QWEN_URL = _config.get("TTS_QWEN_URL", "http://127.0.0.1:8099/v1/audio/speech")
QWEN_SPEED = float(os.environ.get("TTS_QWEN_SPEED", "1.2"))

# 스트리밍 합성 — 서버가 만드는 대로 PCM 을 흘려받아 첫 청크에 재생을 시작한다.
# 이게 없으면 첫 소리까지 걸리는 시간이 입력 길이에 선형으로 늘어난다
# (실측: 6자 0.34s / 26자 1.10s / 77자 3.67s). 스트리밍이면 길이와 무관하게
# 0.23~0.29s 로 고정된다. 서버가 stream 을 모르면 wav 를 한 방에 주므로
# Content-Type 을 보고 예전 경로로 자동 복귀한다 — 구버전 서버와도 호환된다.
QWEN_STREAM = os.environ.get("TTS_QWEN_STREAM", "1").lower() not in ("0", "false", "no")
# PCM 응답에는 헤더가 없다. Qwen3-TTS 출력은 24 kHz mono s16le 고정이고,
# 서버가 X-Sample-Rate 를 주면 그것을 우선한다.
QWEN_PCM_RATE = int(os.environ.get("TTS_QWEN_PCM_RATE", "24000"))

# ── 출력 샘플레이트 맞추기 ──────────────────────────────────────
# **로봇 오디오 장치는 16 kHz 다.** 탑재 펌웨어 `ua_io16_lin` 의 `io16` 이 USB
# 입출력 16 kHz 를 뜻하고(비트폭이 아니다), SDK 도 `media/audio_base.py` 에서
# `SAMPLE_RATE = 16000` 을 쓴다. 그런데 TTS 는 24 kHz 로 뱉는다.
#
# 지금까지는 24k 스트림이 안 열리면 발화마다 `_afplay` 로 떨어졌다 — 프로세스
# 기동이 **길이와 무관하게 0.8초 고정비**라(실측) 스트리밍으로 얻은 첫 청크
# 0.23초가 통째로 사라진다. 소리는 나지만 대화 리듬이 무너진다.
#
# 그래서 장치가 받는 레이트에 **우리가 맞춘다.** 원본 레이트를 먼저 시도하므로
# 맥(24k 를 그대로 받는다)에서는 리샘플이 끼지 않는다 — 시뮬 쪽 회귀가 없다.
OUT_RATE_CANDIDATES = (16000, 48000, 44100)
# 숫자를 주면 원본 레이트 시도를 건너뛰고 그 레이트로 연다(실기에서 탐색 생략용).
OUT_RATE_FORCED = os.environ.get("REACHY_TTS_OUT_RATE", "auto")
# 재생 음량(0~1). **끼어들기의 신호대잡음비를 직접 좌우한다.** 마이크 이득을 올려도
# 목소리와 에코가 같이 커져 비율은 그대로지만, 스피커를 줄이면 에코만 작아진다.
# 실측 로그에서 에코 바닥이 0.041 까지 올라가 임계가 사람 목소리 수준(0.058)이 됐다 —
# 그때 필요한 것이 이 손잡이다.
TTS_VOLUME = float(os.environ.get("REACHY_TTS_VOLUME", "1.0"))
_PCM_CHUNK = 4096
# **첫 청크만 쓰고 재생을 시작하면 첫 음절이 깨진다.** 출력 버퍼가 약 119ms 인데
# 청크 하나가 85ms 라, 두 번째 청크가 조금만 늦으면 그 사이에 버퍼가 빈다(실측).
# 옵션(음량 스케일링·에코 프로브)을 켜면 청크당 작업이 늘어 그 여유가 더 좁아진다.
# 그래서 재생을 시작하기 전에 이만큼을 모아 둔다 — 첫 소리가 그만큼 늦지만
# (0.23s → 0.35s 수준) 깨지는 것보다 낫다.
PREBUFFER_S = float(os.environ.get("REACHY_TTS_PREBUFFER", "0.25"))
# 넉넉히 잡는다. 타임아웃으로 연결을 끊으면 서버가 그 소켓에 쓰다 죽는다(실측).
# 절 단위로 보내므로 정상적으로는 1~3초면 끝난다 — 이 값은 안전장치일 뿐이다.
QWEN_TIMEOUT = float(os.environ.get("TTS_QWEN_TIMEOUT", "90"))

# 채택 음색 — 2026-07-30 청취 비교로 고른 CustomVoice 화자 'serena'.
#
# VoiceDesign(지시문으로 음색을 묘사하는 방식)은 쓰지 않는다. 요청마다 음색을
# 새로 만들어서 **문장마다 목소리가 달라진다**(실제로 겪었다). 시드 고정도
# 듣지 않고(같은 문장 2회가 서로 다름), CrispASR 은 참조 WAV 복제도 지원하지
# 않는다("CustomVoice expects a speaker NAME for --voice").
# 내장 화자는 학습된 임베딩이라 매번 완전히 동일하다.
QWEN_VOICE = os.environ.get("TTS_QWEN_VOICE", "serena")

# 어조를 더 얹고 싶을 때만 채운다(예: "밝고 씩씩하게"). 비우면 보내지 않는다.
QWEN_INSTRUCT = os.environ.get("TTS_QWEN_INSTRUCT", "")

# 한국어 음성은 REACHY_VOICE 로 바꾼다. macOS 에는 ko_KR 음성이 9종 있다:
#   Yuna / Eddy / Flo / Grandma / Grandpa / Reed / Rocko / Sandy / Shelley
# Yuna 외에는 "이름 (한국어(한국))" 전체 이름으로 불러야 로케일이 맞는다.
# 캐릭터 음성들은 유나(0.82s)보다 합성이 빠르다(0.46~0.56s, 실측).
DEFAULT_VOICE = os.environ.get("REACHY_VOICE", "Yuna")

# 문자체계 → macOS 음성. 사용자가 "영어로 답해줘" 같은 요청을 했을 때
# 한국어 음성이 영문을 읽으면 알아들을 수 없게 뭉개지므로 문장별로 음성을 고른다.
_SCRIPTS = [
    (None, re.compile(r"[가-힣ᄀ-ᇿ]")),  # 한글 → DEFAULT_VOICE
    ("Kyoko", re.compile(r"[぀-ヿ]")),  # 히라가나·가타카나
    ("Tingting", re.compile(r"[一-鿿]")),  # 한자 (가나가 없을 때만)
    ("Samantha", re.compile(r"[A-Za-z]")),  # 라틴 문자
]


def pick_voice(text: str) -> str:
    """문장의 문자체계로 음성을 고른다. 한글이 섞였으면 무조건 한국어 음성이다."""
    for voice, pattern in _SCRIPTS:
        if pattern.search(text):
            return voice or DEFAULT_VOICE
    return DEFAULT_VOICE


def group_by_voice(clauses: list[str]) -> list[tuple[str, str]]:
    """연속한 절 중 **같은 음성끼리만** 묶는다.

    절을 전부 한 문자열로 합치면 안 된다. 한글이 하나라도 섞이면 한글 우선
    규칙이 걸려 유나가 중국어·일본어까지 읽어 발음이 깨진다(실제 발생).
    언어가 바뀌는 지점에서만 끊고 나머지는 묶어, 문장 사이 공백은 그대로 없앤다.
    """
    out: list[list[str]] = []
    for c in clauses:
        c = c.strip()
        if not c:
            continue
        v = pick_voice(c)
        if out and out[-1][0] == v:
            out[-1][1] += " " + c
        else:
            out.append([v, c])
    return [(v, t) for v, t in out]


def _norm(text: str) -> str:
    """비교용 정규화 — 공백·문장부호를 걷어낸다(STT 는 이것들을 다르게 찍는다)."""
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text).lower()


def _qwen_synth(text: str, seed: int | None = None) -> bytes | None:
    """Qwen3-TTS 서버에 합성을 요청한다. 실패하면 None — 앱은 계속 돌아야 한다.

    합성은 결정적이다 — 같은 문장은 항상 같은 소리가 난다(PCM 해시로 확인.
    응답 바이트가 매번 다른 것은 C2PA 워터마크 메타데이터 때문이지 오디오가
    아니다). seed 는 운율 재추첨 레버다: 특정 문장의 음높이가 튀면 시드를
    바꿔 뽑고, 마음에 드는 값을 문장별로 고정한다(selfintro.SEEDS 참조).
    """
    try:
        with _qwen_open(_qwen_body(text, seed, stream=False)) as r:
            return r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _qwen_open(body: dict):
    """합성 요청을 보내고 **열린 응답**을 돌려준다(스트리밍 읽기용)."""
    req = urllib.request.Request(
        QWEN_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=QWEN_TIMEOUT)


def _qwen_body(text: str, seed: int | None, stream: bool) -> dict:
    body = {"input": text, "model": "tts", "voice": QWEN_VOICE, "speed": QWEN_SPEED}
    if QWEN_INSTRUCT:
        body["instructions"] = QWEN_INSTRUCT
    if seed is not None:
        body["seed"] = seed
    if stream:
        # CrispASR 서버는 이 둘이 같이 있어야 chunked PCM 을 흘린다.
        body["stream"] = True
        body["response_format"] = "pcm"
    return body


# 폴백 사다리는 **플랫폼마다 다르다.** macOS 전용 이름을 박아 두면 실기(Linux)에서
# FileNotFoundError 가 나고, 그걸 _worker 의 except 가 삼켜 **소리도 로그도 없이
# 벙어리가 된다**(실측으로 재현했다: 재생 0건, 로그 0줄, 0.02초 만에 통과).
# 여기서 있는 것을 고르고, 아무것도 없으면 반드시 경고를 남긴다.
_warned: set[str] = set()


def _warn_once(key: str, msg: str) -> None:
    """같은 경고를 발화마다 반복하지 않는다 — 한 번은 반드시 남긴다."""
    if key in _warned:
        return
    _warned.add(key)
    print(f"  [TTS 경고] {msg}", flush=True)


def _external_player() -> list[str] | None:
    """오디오 장치를 직접 못 열 때 쓸 외부 재생기. macOS/Linux 를 모두 본다."""
    for cmd in (["afplay"], ["paplay"], ["aplay", "-q"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def fallback_tts_cmd(voice: str) -> list[str] | None:
    """TTS 서버가 죽었을 때 쓸 로컬 합성기. 없으면 None(= 그 발화는 무음)."""
    if shutil.which("say"):
        return ["say", "-v", voice]
    for cmd in (["espeak-ng", "-v", "ko"], ["espeak", "-v", "ko"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def _afplay(data: bytes) -> None:
    """폴백 재생 — 오디오 장치를 못 열 때만 쓴다. 기동에 0.8초가 든다(실측)."""
    cmd = _external_player()
    if cmd is None:
        _warn_once(
            "noplayer",
            "외부 재생기가 없다(afplay/paplay/aplay) — 오디오 장치를 못 열면 무음이다",
        )
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        f.write(data)
        f.flush()
        subprocess.run([*cmd, f.name], check=False)


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    """헤더 없는 PCM 을 WAV 로 감싼다 — 외부 재생기 폴백용."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _open_stream(rate: int):
    """PortAudio 출력 스트림을 연다. 실패하면 None — 호출부가 afplay 로 떨어진다."""
    try:
        import sounddevice as sd

        stream = sd.OutputStream(samplerate=rate, channels=1, dtype="int16")
        stream.start()
        return stream
    except Exception:
        return None


def _open_output(src_rate: int):
    """장치가 실제로 받는 레이트로 스트림을 연다. `(스트림, 레이트)` 또는 None.

    원본 레이트를 **먼저** 시도한다 — 맥에서는 그대로 열리므로 리샘플이 끼지 않고
    시뮬 동작이 그대로다. 안 되면 후보로 내려가고, 그때만 호출부가 리샘플한다.
    """
    if OUT_RATE_FORCED != "auto":
        rate = int(OUT_RATE_FORCED)
        stream = _open_stream(rate)
        return (stream, rate) if stream is not None else None

    tried: list[int] = []
    for rate in (src_rate, *OUT_RATE_CANDIDATES):
        if rate in tried:
            continue
        tried.append(rate)
        stream = _open_stream(rate)
        if stream is not None:
            if rate != src_rate:
                # 조용히 성능이 떨어진 채 도는 것이 가장 나쁘다 — 반드시 알린다.
                _warn_once(
                    "resample",
                    f"오디오 장치가 {src_rate} Hz 를 안 받는다 —"
                    f" {rate} Hz 로 리샘플해 재생한다"
                    " (강제하려면 REACHY_TTS_OUT_RATE)",
                )
            return (stream, rate)
    return None


def _design_fir(up: int, down: int, half: int = 16, beta: float = 5.0) -> np.ndarray:
    """폴리페이즈용 안티에일리어싱 저역통과 FIR(윈도우드 싱크).

    차단 주파수는 중간 레이트(원본 x up) 나이키스트의 `1/max(up, down)` 이다 —
    업샘플의 이미지와 다운샘플의 에일리어싱을 같은 필터로 막는다.
    DC 이득이 1 이 되도록 합을 `up` 으로 맞춘다(제로스터핑이 1/up 을 먹으므로).

    numpy 만 쓴다. scipy 로도 되지만(`resample_poly`) 그건 **청크마다 상태가 0 에서
    다시 시작**해 85ms 마다 경계 클릭이 난다 — 아래 `_Resampler` 가 상태를 잇는다.
    """
    max_rate = max(up, down)
    ntaps = 2 * half * max_rate + 1
    n = np.arange(ntaps) - (ntaps - 1) / 2
    h = np.sinc(n / max_rate) * np.kaiser(ntaps, beta)
    return h * (up / h.sum())


class _Resampler:
    """스트리밍 리샘플러 — 청크 경계에서 딱딱거리지 않게 상태를 이어 간다.

    한 방에 다 받아서 변환하면 간단하지만, 우리는 도착하는 청크를 그대로 흘려
    재생한다(그게 첫 소리 0.23초의 근거다). 그래서 청크마다 변환해야 하는데,
    필터 상태를 안 이으면 **매 청크 경계마다 클릭이 들린다.**

    들고 다니는 상태는 둘이다:
      · `_tail` — 제로스터핑된 신호의 마지막 (탭수-1) 샘플. 다음 블록 앞에 붙인다.
      · `_phase` — 데시메이션 위상. 블록 길이가 `down` 의 배수가 아니면 다음
        블록에서 몇 번째 샘플부터 집어야 하는지가 달라진다.
    """

    def __init__(self, src_rate: int, dst_rate: int):
        g = math.gcd(src_rate, dst_rate)
        self.up, self.down = dst_rate // g, src_rate // g
        self._fir = _design_fir(self.up, self.down)
        self._tail = np.zeros(self._fir.size - 1, dtype=np.float64)
        self._phase = 0

    def reset(self) -> None:
        """발화가 바뀔 때 부른다 — 이전 발화의 꼬리가 다음 발화 머리에 새지 않게."""
        self._tail[:] = 0.0
        self._phase = 0

    def process(self, pcm: bytes) -> bytes:
        """s16le mono 청크 → 같은 형식, 목표 레이트. 짝수 바이트를 전제한다."""
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        if x.size == 0:
            return b""
        stuffed = np.zeros(x.size * self.up, dtype=np.float64)
        stuffed[:: self.up] = x
        buf = np.concatenate([self._tail, stuffed])
        # 'valid' 라 출력 길이가 정확히 stuffed 길이다 — 상태를 이어 붙인 효과.
        y = np.convolve(buf, self._fir, mode="valid")
        self._tail = buf[-self._tail.size :]
        out = y[self._phase :: self.down]
        self._phase = (self._phase - y.size) % self.down
        return np.clip(np.rint(out), -32768, 32767).astype(np.int16).tobytes()


class StreamPlayer:
    """상주 오디오 스트림. 열어둔 채 재사용한다.

    `afplay` 는 발화마다 프로세스를 띄워 CoreAudio 를 새로 초기화하는데,
    실측하면 **파일 길이와 무관하게 0.8초 고정비**다(0.1초 파일도 0.83초).
    전체 응답 지연 2.60초 중 31% 가 여기였다. 스트림을 한 번만 열면 0.00초다.

    재생은 워커 스레드가, abort() 는 마이크 루프 스레드가 부른다 — 스트림
    접근은 전부 self._io 잠금 안에서 한다.
    """

    def __init__(self) -> None:
        self._stream = None
        self._rate: int | None = None      # 들어오는 PCM 의 레이트(재개방 판단 기준)
        self._dev_rate: int | None = None  # 장치가 실제로 받는 레이트
        # 둘이 다를 때만 선다. 로봇(16k)에서 24k TTS 를 받을 때가 그 경우다.
        self._resampler: _Resampler | None = None
        self.opened = 0  # 스트림을 실제로 연 횟수(테스트가 재사용을 확인한다)
        # AEC 를 켜면 Speaker 가 여기에 EchoProbeTap 을 꽂는다. 재생하는 PCM 을
        # 한 벌 더 흘려 보내 에코 프로브가 far-end 를 보게 한다.
        self.tap = None
        # **끼어들기가 이 클래스를 다중 스레드로 만들었다.** 재생은 워커 스레드가,
        # abort() 는 마이크 루프 스레드가 부른다. 잠금 없이 겹치면 CoreAudio 가
        # 깨진다(실측: `PaMacCore (AUHAL) Error on line 2796: err='-50'`).
        # 잠금을 잡으면 abort 는 진행 중인 청크 쓰기(약 85ms)만 기다렸다 들어간다.
        self._io = threading.RLock()
        # 방금 스피커로 내보낸 소리의 세기 — 마이크에 잡힌 것이 '내 소리'인지
        # '사람 목소리'인지 가르는 기준이 된다(끼어들기 판정에서 쓴다).
        self._out: collections.deque = collections.deque(maxlen=200)  # 약 6초
        # 마지막으로 소리를 내보낸 시각. 에코는 물리적으로 재생 중 + 1초 미만의
        # 꼬리에만 존재하므로, 자기 목소리 방어선(said_recently)의 적용 여부를
        # 이 값으로 가른다. 0 이면 아직 아무것도 안 냈다.
        self.last_output_ts = 0.0
        # `_out` 은 **워커 스레드가 쓰고 마이크 루프가 읽는다.** 잠금 없이 순회하면
        # `RuntimeError: deque mutated during iteration` 이 난다(재현 확인). 그게
        # 마이크 루프에서 터지면 앱이 귀머거리가 된다 — 아주 짧게만 잡는 전용 잠금이다.
        # (재생용 self._io 를 쓰면 write 가 끝날 때까지 마이크가 막힌다 — 쓰면 안 된다.)
        self._out_lock = threading.Lock()

    @staticmethod
    def _scaled(pcm: bytes) -> bytes:
        """재생 음량을 적용한다. 프로브·레벨 기록도 **줄인 뒤의 소리**를 봐야 한다."""
        if abs(TTS_VOLUME - 1.0) < 1e-6:
            return pcm
        a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * TTS_VOLUME
        return np.clip(a, -32768, 32767).astype(np.int16).tobytes()

    def _feed_tap(self, pcm: bytes, rate: int) -> None:
        self._note_output(pcm)
        if self.tap is not None:
            self.tap.push(pcm, rate)

    def _note_output(self, pcm: bytes) -> None:
        """내보낸 청크의 RMS 를 시각과 함께 남긴다(0..1 정규화)."""
        if not pcm:
            return
        a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if a.size:
            with self._out_lock:
                self._out.append((time.time(), float(np.sqrt(np.mean(a * a)))))
                self.last_output_ts = time.time()  # 에코 방어선의 적용 범위 기준

    def output_level(self, window_s: float = 0.25, lag_s: float = 0.05) -> float:
        """지금 마이크에 들어오고 있을 소리의 세기 — 창의 **평균**이다. 조용하면 0.

        최대값을 쓰면 안 된다(실측으로 당했다): 큰 음절 하나가 창 안에 남아 있는
        동안 값이 계속 높게 유지돼, 정작 말 사이 틈에서도 예측 에코가 크게 잡힌다.
        그 틈이 사람이 끼어드는 바로 그 순간인데 임계가 높아져 아무것도 안 걸렸다.

        평균은 틈에서 실제로 내려간다. lag_s 는 스피커→마이크 지연 보정이다.
        """
        now = time.time()
        lo, hi = now - window_s - lag_s, now - lag_s
        with self._out_lock:
            snapshot = tuple(self._out)
        vals = [v for ts, v in snapshot if lo <= ts <= hi]
        return float(sum(vals) / len(vals)) if vals else 0.0

    def _ensure_output(self, src_rate: int) -> bool:
        """들어오는 PCM 의 레이트에 맞춰 스트림을 준비한다. 못 열면 False.

        장치가 그 레이트를 안 받으면 받는 레이트로 열고 리샘플러를 세운다.
        발화마다 리샘플러를 비워 이전 발화의 필터 꼬리가 새지 않게 한다.
        """
        if self._stream is not None and self._rate == src_rate:
            if self._resampler is not None:
                self._resampler.reset()
            return True

        self._close_stream()
        self._rate = src_rate
        opened = _open_output(src_rate)
        if opened is None:
            self._dev_rate, self._resampler = None, None
            return False
        self._stream, self._dev_rate = opened
        self._resampler = (
            _Resampler(src_rate, self._dev_rate) if self._dev_rate != src_rate else None
        )
        self.opened += 1
        return True

    def _for_device(self, pcm: bytes) -> bytes:
        """장치에 쓰기 직전 변환. 레이트가 같으면 손대지 않는다."""
        return pcm if self._resampler is None else self._resampler.process(pcm)

    def play(self, data: bytes) -> None:
        try:
            with wave.open(io.BytesIO(data)) as w:
                rate = w.getframerate()
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        except Exception:
            _afplay(data)  # wav 로 못 읽으면 외부 재생기에 맡긴다
            return

        if not self._ensure_output(rate):
            _afplay(data)
            return
        try:
            with self._io:
                out = self._scaled(pcm.tobytes())
                # 프로브·레벨 기록은 **원본 레이트로** 본다 — 에코 프로브는 far-end 를
                # 실시간 속도로 소비해야 시간축이 맞고, RMS 는 레이트와 무관하다.
                self._feed_tap(out, rate)
                self._ensure_started()
                self._stream.write(np.frombuffer(self._for_device(out), dtype=np.int16))
        except Exception:
            # 장치가 중간에 사라진 경우 — 다음 발화는 다시 열어보고, 이번 건 폴백
            self._close_stream()
            _afplay(data)

    def play_pcm_stream(self, chunks, rate: int = QWEN_PCM_RATE) -> None:
        """도착하는 PCM 청크를 그대로 스트림에 밀어 넣는다 — 첫 청크에 소리가 난다.

        장치를 못 열면 전부 모아 WAV 로 만들어 외부 재생기에 넘긴다. 이 경우
        스트리밍 이점은 사라지지만 소리는 난다 — 벙어리가 되는 것이 최악이다.
        """
        if not self._ensure_output(rate):
            _afplay(_pcm_to_wav(b"".join(chunks), rate))
            return

        carry = b""  # 청크 경계가 샘플(2바이트) 중간에서 끊길 수 있다
        buffered: list[bytes] = []
        prebuffer: list[bytes] = []
        prebuffer_bytes = int(PREBUFFER_S * rate * 2)
        primed = prebuffer_bytes <= 0
        try:
            for chunk in chunks:
                buffered.append(chunk)
                if not primed:
                    # 재생을 시작하기 전에 쿠션을 만든다(첫 음절 깨짐 방지)
                    prebuffer.append(chunk)
                    if sum(len(c) for c in prebuffer) < prebuffer_bytes:
                        continue
                    chunk = b"".join(prebuffer)
                    prebuffer.clear()
                    primed = True
                data = carry + chunk
                cut = len(data) - (len(data) % 2)
                carry = data[cut:]
                if cut:
                    with self._io:
                        if self._stream is None:  # abort 뒤 정리됐다
                            return
                        out = self._scaled(data[:cut])
                        self._feed_tap(out, rate)
                        self._ensure_started()
                        self._stream.write(
                            np.frombuffer(self._for_device(out), dtype=np.int16)
                        )
            if prebuffer:
                # 발화가 쿠션보다 짧았다 — 모은 것을 그대로 내보낸다
                data = carry + b"".join(prebuffer)
                cut = len(data) - (len(data) % 2)
                if cut:
                    with self._io:
                        if self._stream is not None:
                            out = self._scaled(data[:cut])
                            self._feed_tap(out, rate)
                            self._ensure_started()
                            self._stream.write(
                                np.frombuffer(self._for_device(out), dtype=np.int16)
                            )
        except Exception:
            # 재생 도중 장치가 사라졌다 — 남은 것은 외부 재생기로
            self._close_stream()
            _afplay(_pcm_to_wav(b"".join(buffered), rate))

    def _ensure_started(self) -> None:
        """abort 로 멈춘 스트림을 쓰기 직전에 되살린다."""
        if self._stream is not None and not self._stream.active:
            self._stream.start()

    def abort(self) -> None:
        """재생을 즉시 끊는다 — 버퍼에 남은 오디오까지 버린다(끼어들기).

        `stop()` 은 버퍼를 다 흘려보내고 멈춘다. 끼어들기에서는 그 남은 소리가
        그대로 나므로 반드시 `abort()` 여야 한다.

        **다른 스레드에서 불린다**(마이크 루프). 잠금 없이 워커의 write 와 겹치면
        CoreAudio 가 err=-50 을 뱉는다. 그리고 abort 직후 start() 를 바로 부르는
        것도 같은 오류를 내므로, 재시작은 다음 write 직전으로 미룬다.
        """
        with self._io:
            if self._stream is None:
                return
            try:
                self._stream.abort()
            except Exception:
                self._close_stream()  # 되살리지 못하면 다음 재생에서 새로 연다

    def _close_stream(self) -> None:
        # 호출부가 이미 self._io 를 잡고 있다(RLock 이라 재진입 가능)
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        # 리샘플러는 장치 레이트에 묶여 있다 — 스트림과 함께 버린다.
        # (`_ensure_output` 이 다음 재생에서 다시 세운다)
        self._dev_rate, self._resampler = None, None

    def close(self) -> None:
        self._close_stream()
        if self.tap is not None:
            self.tap.close()
            self.tap = None


class EchoProbeTap:
    """AEC 참조 신호 — 재생하는 PCM 을 **복사해서** 에코 프로브에 흘린다.

        appsrc → audioconvert/resample → webrtcechoprobe → fakesink(sync=true)

    처음에는 재생 자체를 GStreamer 로 옮겼는데(appsrc → probe → autoaudiosink)
    **소리가 끊겨서 못 쓴다.** TTS 서버가 청크를 최대 0.5초 간격으로 주는데
    오디오 싱크에는 그 공백을 메울 버퍼가 없어 매번 언더런이 났다.

    프로브는 far-end 를 *듣기만* 하면 되지 출력 경로일 필요가 없다. 그래서
    재생은 검증된 PortAudio 상주 스트림에 그대로 두고, 같은 PCM 을 여기로 한 벌
    더 보낸다. fakesink 는 sync=true 라 실시간 속도로 소비하므로 프로브가 보는
    시간축이 실제 재생과 맞고, 남는 오차는 webrtcdsp 의 delay-agnostic 이 흡수한다.
    """

    def __init__(self) -> None:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        self._Gst = Gst
        self._rate: int | None = None
        self._pipe = None
        self._src = None
        self._ensure(QWEN_PCM_RATE)  # 마이크보다 먼저 서 있어야 한다

    def _ensure(self, rate: int) -> bool:
        if self._pipe is not None and self._rate == rate:
            return True
        self.close()
        Gst = self._Gst
        try:
            self._pipe = Gst.parse_launch(
                f"appsrc name=src is-live=true format=time do-timestamp=true "
                f"caps=audio/x-raw,format=S16LE,channels=1,rate={rate},layout=interleaved "
                f"! audioconvert ! audioresample "
                f"! audio/x-raw,format=S16LE,channels=1,rate={aec.RATE} "
                f"! webrtcechoprobe name={aec.PROBE_NAME} "
                f"! fakesink sync=true"
            )
            self._src = self._pipe.get_by_name("src")
            if self._pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("프로브 파이프라인 상태 전이 실패")
            # 라이브 소스(is-live=true)는 **버퍼가 하나도 없으면 PLAYING 으로
            # 올라가지 않는다**(preroll 대기). 무음 10ms 를 먼저 밀어 넣어 깨운다 —
            # 이게 없으면 프로브가 안 선 채로 AEC 전체가 폴백된다(실측).
            silence = b"\x00\x00" * (rate // 100)
            self._src.emit("push-buffer", Gst.Buffer.new_wrapped(silence))
            state = self._pipe.get_state(3 * Gst.SECOND)[1]
            if state not in (Gst.State.PLAYING, Gst.State.PAUSED):
                raise RuntimeError(f"프로브 파이프라인이 {state.value_name} 에 머물렀다")
            self._rate = rate
            return True
        except Exception as e:  # noqa: BLE001
            _warn_once("echoprobe", f"에코 프로브를 세우지 못했다 — AEC 없이 간다: {e}")
            self.close()
            return False

    def push(self, pcm: bytes, rate: int) -> None:
        """재생과 같은 PCM 을 프로브에 흘린다. 실패해도 재생은 계속돼야 한다.

        단 **조용히 죽으면 안 된다** — far-end 공급이 끊기면 AEC 가 아무것도
        못 지우는데 재생은 멀쩡해서, 로봇이 자기 목소리에 반응하기 시작해도
        원인을 알 수 없다. 한 번은 반드시 로그를 남긴다.
        """
        if not self._ensure(rate):
            return
        try:
            self._src.emit("push-buffer", self._Gst.Buffer.new_wrapped(pcm))
        except Exception as e:  # noqa: BLE001
            _warn_once(
                "probe-push",
                f"에코 프로브 공급이 죽었다({type(e).__name__}) — "
                "AEC 가 무력화된 채 돈다(끼어들기가 자기 목소리에 반응할 수 있다)",
            )

    def close(self) -> None:
        if self._pipe is not None:
            try:
                self._pipe.set_state(self._Gst.State.NULL)
            except Exception:
                pass
        self._pipe = None
        self._src = None


def make_probe():
    """AEC 를 켰을 때만 프로브를 만든다. 못 만들면 None — 앱은 계속 돈다."""
    if not aec.ENABLED:
        return None
    try:
        return EchoProbeTap()
    except Exception as e:  # noqa: BLE001
        _warn_once("probe", f"에코 프로브 생성 실패: {e}")
        return None


class _Ahead:
    """다음 발화를 **재생 중에 미리 요청해 둔다.**

    지금까지는 합성과 재생이 직렬이라 문장마다 요청 왕복(실측 중앙 292ms)만큼
    소리가 비었다 — 대본 13문장에서 3.5초가 침묵이었다. 재생하는 동안 다음 문장의
    응답을 열어 첫 청크까지 받아 두면 그 공백이 사라진다.

    실패해도 조용히 버린다 — 본 경로가 다시 요청하면 그만이다(늦어질 뿐이다).
    """

    def __init__(self, text: str, seed: int | None):
        self.text = text
        self.seed = seed
        self.resp = None
        self.first = b""
        self.ctype = ""
        self.rate = QWEN_PCM_RATE
        self.ready = threading.Event()
        self.dead = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            r = _qwen_open(_qwen_body(self.text, self.seed, stream=QWEN_STREAM))
            self.ctype = (r.headers.get("Content-Type") or "").lower()
            self.rate = int(r.headers.get("X-Sample-Rate") or QWEN_PCM_RATE)
            read = getattr(r, "read1", None) or r.read
            self.first = read(_PCM_CHUNK)
            self.resp = r
        except Exception:  # noqa: BLE001
            self.dead = True
        finally:
            self.ready.set()

    def close(self) -> None:
        self.dead = True
        try:
            if self.resp is not None:
                self.resp.close()
        except Exception:  # noqa: BLE001
            pass


class _Item(NamedTuple):
    """발화 큐의 한 항목.

    `sound` 가 있으면 **합성 없이 그 PCM 을 그대로 재생한다**(감정 모션의 자체 발성).
    같은 큐에 태우는 이유는 셋이다 — 스피커가 하나뿐이라 순서를 지켜야 하고,
    `speaking` 플래그가 발성 구간에도 켜져야 마이크 게이팅이 맞으며,
    에코 프로브·출력 레벨 기록을 그대로 타야 끼어들기가 자기 소리를 구별한다.
    """

    voice: str
    text: str
    seed: int | None = None
    sound: tuple[bytes, int] | None = None   # (pcm, rate)
    gen: int = 0   # 적재 시점의 세대 — stop() 이후의 항목과 이전 항목을 가른다


class Speaker:
    def __init__(
        self,
        voice: str | None = None,
        cmd: list[str] | None = None,
        play=None,
        fallback_cmd: list[str] | None = None,
        play_pcm=None,
    ):
        # voice 를 고정하면 그 음성만 쓴다. None 이면 문장마다 자동 선택.
        self._voice = voice
        self._cmd = cmd  # 주면 say 경로를 강제한다(테스트용)
        self._fallback_cmd = fallback_cmd  # qwen 실패 시 쓸 명령(테스트용)
        # 상주 스트림 하나를 워커 스레드가 독점한다(afplay 0.8초 고정비 제거).
        # AEC 를 켜면 출력이 에코 프로브를 지나야 해서 GStreamer 재생기로 바뀐다.
        self._player = StreamPlayer()
        # AEC 를 켜면 재생 PCM 한 벌을 에코 프로브로도 보낸다.
        self._player.tap = make_probe()
        self._play = play or self._player.play  # 테스트에서 재생을 가로채는 지점
        # 스트리밍 경로의 재생 지점(측정·테스트에서 가로챈다)
        self._play_pcm = play_pcm or self._player.play_pcm_stream
        self._q: queue.Queue[_Item] = queue.Queue()
        self._held = None   # 워커가 선요청하려고 미리 꺼내 둔 항목(워커만 만진다)
        # 최근에 낸 말 — 마이크가 자기 목소리를 주웠는지 판정하는 데 쓴다.
        self._said: collections.deque = collections.deque(maxlen=40)
        self._speaking = threading.Event()
        # 끼어들기는 **세대 번호**로 판정한다. 이전에는 공유 Event 하나를 썼는데
        # 워커가 항목을 집을 때마다 clear() 해서, stop() 이 "워커의 finally 검사 뒤
        # ~ 다음 항목 pickup 사이"에 떨어지면 취소가 지워졌다 — 선요청해 둔 절이
        # 통째로 재생됐다(리뷰에서 확인). 세대는 지워지지 않는다: stop() 이 번호를
        # 올리면 그 이전에 적재된 항목은 어디서 발견되든 낡은 것이다.
        self._gen = 0
        self._lock = threading.Lock()
        self._pending = 0
        threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, text: str, seed: int | None = None) -> None:
        text = text.strip()
        if not text:
            return
        self._enqueue(self._voice or pick_voice(text), text, seed)

    def speak_many(self, clauses: list[str]) -> None:
        """여러 절을 한 번에 넘긴다.

        `say` 는 프로세스 기동이 고정비라 **합치는** 편이 낫다 — 절마다 띄우면
        문장 사이에 공백과 억양 초기화가 생긴다.

        `qwen` 은 정반대로 절마다 따로 보낸다. 스트리밍 전에는 합성 시간이 입력
        길이에 선형으로 늘어나 합치면 첫 소리가 한참 뒤였고, 타임아웃으로 연결이
        끊기면 서버까지 죽었다. 스트리밍이 그 둘을 없앴지만(첫 청크 0.23초 고정,
        202자도 서버 정상) 절 단위는 그대로 둔다 — 끼어들기(barge-in)로 발화를
        끊는 단위가 절이고, 절마다 시드를 따로 고정하기 때문이다.
        """
        if BACKEND == "qwen" and self._cmd is None:
            for c in clauses:
                self.speak(c)
            return
        if self._voice is not None:  # 음성이 고정돼 있으면 묶을 이유가 없다
            joined = " ".join(c.strip() for c in clauses if c.strip())
            if joined:
                self._enqueue(self._voice, joined)
            return
        for voice, text in group_by_voice(clauses):
            self._enqueue(voice, text)

    def stop(self) -> None:
        """말하는 것을 즉시 멈추고 대기 중인 절을 버린다 — 끼어들기(barge-in).

        셋을 함께 해야 진짜로 멈춘다:
          1) 세대 올림 — 이전 세대 항목은 청크 루프·pickup·선요청 어디서든 낡은
             것으로 판정돼 버려진다(약 85ms 안에). Event 방식과 달리 워커가
             지울 수 없으므로, 선요청해 둔 `_held` 절도 확실히 죽는다.
          2) 큐 비우기 — 아직 시작 안 한 절이 이어서 나오면 안 된다
          3) 재생 abort — PortAudio 버퍼에 남은 소리까지 버린다

        현재 발화와 `_held` 의 pending 은 워커가 finally 에서 내린다. 여기서는
        **버린 것만** 빼야 speaking 플래그가 실제 재생보다 먼저 꺼지지 않는다.
        """
        with self._lock:
            self._gen += 1
        dropped = 0
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
            dropped += 1
            self._q.task_done()
        if dropped:
            with self._lock:
                self._pending -= dropped
                if self._pending <= 0:
                    self._pending = 0
                    self._speaking.clear()
        self._player.abort()

    def _open_qwen(self, text: str, seed: int | None, ahead=None):
        """요청을 열고 첫 청크까지 받아 둔다. 실패하면 None.

        **여는 것과 재생을 나눈 이유**: 다음 문장을 미리 요청하려면 "현재 요청이
        서버에 도달한 뒤"여야 한다. 순서가 뒤집히면 서버(요청을 직렬 처리한다)가
        다음 문장을 먼저 만들어 현재 발화가 오히려 늦어진다 — 테스트로 잡았다.
        """
        pre_first = b""
        if ahead is not None:
            ahead.ready.wait(timeout=QWEN_TIMEOUT)
            if not ahead.dead and ahead.resp is not None:
                r, pre_first = ahead.resp, ahead.first  # 미리 열어 둔 것을 그대로 쓴다
            else:
                ahead = None
        if ahead is None:
            try:
                r = _qwen_open(_qwen_body(text, seed, stream=QWEN_STREAM))
            except (urllib.error.URLError, OSError, TimeoutError):
                return None

        ctype = (r.headers.get("Content-Type") or "").lower()
        rate = int(r.headers.get("X-Sample-Rate") or QWEN_PCM_RATE)
        if not (QWEN_STREAM and "pcm" in ctype):
            return (r, pre_first, ctype, rate)   # wav 경로는 재생 단계에서 마저 읽는다
        read = getattr(r, "read1", None) or r.read
        first = pre_first or read(_PCM_CHUNK)
        if not first:
            r.close()
            return None
        return (r, first, ctype, rate)

    def _stale(self, gen: int) -> bool:
        """이 세대의 항목이 stop() 으로 무효화됐는가 — 취소 판정의 유일한 기준."""
        return gen != self._gen

    def _play_qwen(self, opened, gen: int) -> bool:
        """열어 둔 응답을 재생한다. 취소(세대 교체)되면 도중에 멈춘다."""
        r, first, ctype, rate = opened
        with r:
            if not (QWEN_STREAM and "pcm" in ctype):
                data = first + r.read()  # wav 한 방 — 구버전 서버 호환 경로
                if not data:
                    return False
                if self._stale(gen):
                    return True  # 받아는 놨지만 끼어들기가 걸렸다 — 재생하지 않는다
                self._play(data)
                return True

            if self._stale(gen):
                return True
            read = getattr(r, "read1", None) or r.read

            def chunks():
                yield first
                while not self._stale(gen):
                    c = read(_PCM_CHUNK)
                    if not c:
                        return
                    yield c

            self._play_pcm(chunks(), rate)
            return True

    def play_sound(self, pcm: bytes, rate: int) -> None:
        """합성을 거치지 않고 이 PCM 을 발화 큐에 넣는다(감정 모션의 자체 발성).

        `_said` 에는 넣지 않는다 — 자기 목소리 판정은 **전사와 문장을 대조**하는
        것이라 가사 없는 발성에는 쓸 것이 없다. 대신 에코 프로브와 출력 레벨
        기록을 그대로 타므로 끼어들기의 에너지 판정은 정상 동작한다.
        """
        if not pcm:
            return
        with self._lock:
            self._pending += 1
            self._speaking.set()
            gen = self._gen
        self._q.put(_Item(voice="", text="", sound=(pcm, rate), gen=gen))

    def _sound_chunks(self, pcm: bytes, gen: int):
        """모션 발성을 TTS 와 **같은 크기의 청크**로 흘린다.

        한 덩어리로 넘기면 안 된다. 춤 발성은 16.5초짜리인데 그걸 한 번의
        `stream.write()` 로 쓰면 그동안 재생 잠금(`StreamPlayer._io`)을 쥐고 있어
        **끼어들기의 `abort()` 가 그 16초를 기다린다.** 청크로 쪼개면 취소가
        다음 청크(약 85ms)에서 걸린다 — TTS 스트리밍과 같은 규칙이다.
        """
        for i in range(0, len(pcm), _PCM_CHUNK):
            if self._stale(gen):
                return
            yield pcm[i : i + _PCM_CHUNK]

    def _enqueue(self, voice: str, text: str, seed: int | None = None) -> None:
        with self._lock:  # 적재 즉시 — 워커 시작 전에 게이팅부터
            self._pending += 1
            self._speaking.set()
            self._said.append((time.time(), _norm(text)))
            gen = self._gen
        self._q.put(_Item(voice, text, seed, gen=gen))

    def output_level(self, window_s: float = 0.35) -> float:
        """방금 스피커로 나간 소리의 세기 — 끼어들기 판정이 참조한다."""
        return self._player.output_level(window_s)

    def said_recently(self, text: str, window_s: float = 90.0, ratio: float = 0.55) -> bool:
        """이 전사가 **방금 로봇이 한 말**인가 — 에코를 사용자 발화로 오인하지 않으려는 방어선.

        AEC 가 완벽하지 않으면 잔여 에코가 발화로 잡히고, 그걸 받아 적어
        스스로에게 대답한다(실측: 자기소개 대본을 통째로 다시 시작했다).
        우리는 로봇이 무슨 말을 했는지 정확히 알고 있으므로 대조하면 된다.

        길이가 다를 수 있어(전사가 앞부분만 잡히는 일이 흔하다) 포함 관계도 본다.

        **적용 범위는 재생 꼬리까지다.** 에코는 물리적으로 재생 중 + 1초 미만의
        잔향에만 존재한다. 그런데 이 검사를 시간 제한 없이 걸었더니, 재생이 끝나고
        한참 뒤에 사용자가 로봇 말을 **인용**한 질문("네가 방금 위스퍼라고 했잖아,
        그게 뭐야?")까지 자기 목소리로 오인해 버렸다(리뷰 확인) — 시연에서는
        무작위 난청으로 보인다. 마지막 출력 이후 유예(hangover 0.7 + STT ~0.5 +
        여유)를 넘긴 발화는 에코일 수 없으므로 검사하지 않는다.
        (say/afplay 폴백은 출력 기록이 없어 이 방어선을 못 탄다 — 그 경로는
        half-duplex 게이팅이 덮는다.)
        """
        tail_s = float(os.environ.get("REACHY_ECHO_TAIL", "3.0"))
        if time.time() - self._player.last_output_ts > tail_s:
            return False
        probe = _norm(text)
        if len(probe) < 4:
            return False
        cutoff = time.time() - window_s
        with self._lock:
            recent = [t for ts, t in self._said if ts >= cutoff]
        for said in recent:
            if not said:
                continue
            if probe in said or said in probe:
                return True
            m = difflib.SequenceMatcher(None, probe, said)
            if m.ratio() >= ratio:
                return True
            # 전사가 부분만 잡히거나 모델명을 엉뚱하게 적는 일이 흔하다
            # ("Whisper Large V3 Turbo" → "위스퍼를 라지 V3 철보"). 전체 비율은
            # 떨어져도 **긴 공통 덩어리**가 남으므로 그것으로 잡는다.
            block = m.find_longest_match(0, len(probe), 0, len(said)).size
            if block >= max(6, int(0.35 * min(len(probe), len(said)))):
                return True
        return False

    @property
    def speaking(self) -> bool:
        return self._speaking.is_set()

    def wait_idle(self, timeout: float | None = None) -> None:
        """큐가 빌 때까지 대기(시연 루프의 half-duplex 동기화점)."""
        deadline = None if timeout is None else time.time() + timeout
        while self._speaking.is_set():
            if deadline is not None and time.time() >= deadline:
                return
            time.sleep(0.02)

    def _worker(self) -> None:
        held = None   # 미리 꺼내 둔 다음 항목 (세대 검사가 있어 stop() 이 못 봐도 안전)
        ahead = None  # 그 항목의 선요청 핸들
        while True:
            if held is not None:
                item = held
                held, self._held = None, None
            else:
                item = self._q.get()
                ahead = None
            voice, text, seed, gen = item.voice, item.text, item.seed, item.gen
            mine, ahead = ahead, None
            # 여기서 지우는 플래그는 없다 — 취소는 세대 비교다. stop() 이후에
            # 적재된 항목은 새 세대라 그냥 재생되고, 이전 세대는 어디서 발견되든
            # (pickup·청크 루프·선요청 핸들) 낡은 것으로 버려진다.

            try:
                if self._stale(gen):
                    pass  # stop() 에 걸린 항목 — 재생하지 않는다(pending 은 finally 가 내린다)
                elif item.sound is not None:
                    # 모션 발성 — 합성 없이 그대로 재생한다. 재생 경로가 같으므로
                    # 리샘플·에코 프로브·출력 레벨 기록을 전부 탄다.
                    pcm, rate = item.sound
                    self._play_pcm(self._sound_chunks(pcm, gen), rate)
                elif BACKEND == "qwen" and self._cmd is None:
                    opened = self._open_qwen(text, seed, ahead=mine)
                    # **현재 요청을 연 뒤에** 다음 항목을 미리 요청한다. 그래야 서버가
                    # 순서대로 만든다. 이게 없으면 문장마다 요청 왕복(실측 292ms)만큼
                    # 소리가 빈다 — 대본 13문장에서 3.5초가 침묵이었다.
                    try:
                        held = self._q.get_nowait()
                        self._held = held
                        self._q.task_done()
                        # 다음이 모션 발성이면 선요청할 것이 없다(합성을 안 한다).
                        ahead = None if held.sound is not None else _Ahead(held.text, held.seed)
                    except queue.Empty:
                        held, ahead = None, None
                    if opened is None or not self._play_qwen(opened, gen):
                        # 서버가 죽었다 — 로컬 합성기로라도 말한다. 음색이 바뀌는 건
                        # 어색하지만 조용히 벙어리가 되는 것보다 낫다.
                        fb = self._fallback_cmd or fallback_tts_cmd(voice)
                        if fb is None:
                            _warn_once(
                                "nofallback",
                                f"TTS 서버 응답 없음({QWEN_URL}) + 로컬 합성기 없음"
                                " (say/espeak-ng) — 이 발화는 무음이다",
                            )
                        else:
                            subprocess.run([*fb, text], check=False)
                else:
                    cmd = self._cmd or fallback_tts_cmd(voice)
                    if cmd is None:
                        _warn_once(
                            "nosay", "로컬 합성기가 없다(say/espeak-ng) — 무음이다"
                        )
                    else:
                        subprocess.run([*cmd, text], check=False)
            except Exception as exc:
                # 워커는 죽이지 않되 **조용히 넘어가지도 않는다.** 예전에는 여기서
                # 통째로 삼켜, 실기에서 무슨 일이 났는지 알 방법이 없었다.
                print(f"  [TTS 실패: {type(exc).__name__}: {exc}]", flush=True)
            finally:
                with self._lock:
                    self._pending -= 1
                    if self._pending == 0 and self._held is None:
                        self._speaking.clear()
                if mine is None:
                    # 미리 꺼낸 항목은 꺼낼 때 이미 task_done 했다
                    self._q.task_done()
                # 끼어들기가 걸렸으면 미리 받아 둔 다음 항목도 버린다.
                # **세대로 판정한다** — 예전 Event 방식은 다음 pickup 의 clear() 가
                # 이 검사와 경합해, 좁은 틈에 걸린 stop() 이 지워지고 held 절이
                # 통째로 재생됐다(리뷰 확인). 세대는 그 틈이 없다.
                if held is not None and self._stale(held.gen):
                    if ahead is not None:
                        ahead.close()
                    held, ahead, self._held = None, None, None
                    with self._lock:
                        self._pending -= 1
                        if self._pending <= 0:
                            self._pending = 0
                            self._speaking.clear()
