"""TTS 큐 워커 — speak()는 즉시 반환, 백그라운드에서 순차 발화.

speaking 플래그는 큐 적재 순간 켜진다 — 마이크 게이팅이 소리보다
늦게 걸리면 에코가 새기 때문이다.

플래그를 큐가 비었는지로 판정하면 안 된다. 워커가 task_done() 직후
빈 큐를 확인하는 사이에 speak()가 끼어들면, 재생이 남았는데 플래그가
내려간다. 그래서 잠금으로 보호되는 대기 건수로 판정한다.
"""

import io
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave

import numpy as np

# ── 백엔드 선택 ──────────────────────────────────────────────────
# 기본은 채택 음색(Qwen3-TTS '소년')이다. macOS 유나로 되돌리려면 TTS_BACKEND=say.
#
# qwen 은 별도 서버(:8099)를 요구하므로 그게 죽으면 소리가 안 난다. 그래서
# **합성 실패 시 say 로 떨어뜨린다.** 대화 도중 음색이 바뀌는 건 어색하지만,
# 로봇이 조용히 벙어리가 되는 것보다는 훨씬 낫다.
BACKEND = os.environ.get("TTS_BACKEND", "qwen")

QWEN_URL = os.environ.get("TTS_QWEN_URL", "http://127.0.0.1:8099/v1/audio/speech")
QWEN_SPEED = float(os.environ.get("TTS_QWEN_SPEED", "1.2"))
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


def _qwen_synth(text: str, seed: int | None = None) -> bytes | None:
    """Qwen3-TTS 서버에 합성을 요청한다. 실패하면 None — 앱은 계속 돌아야 한다.

    합성은 결정적이다 — 같은 문장은 항상 같은 소리가 난다(PCM 해시로 확인.
    응답 바이트가 매번 다른 것은 C2PA 워터마크 메타데이터 때문이지 오디오가
    아니다). seed 는 운율 재추첨 레버다: 특정 문장의 음높이가 튀면 시드를
    바꿔 뽑고, 마음에 드는 값을 문장별로 고정한다(selfintro.SEEDS 참조).
    """
    body = {"input": text, "model": "tts", "voice": QWEN_VOICE, "speed": QWEN_SPEED}
    if QWEN_INSTRUCT:
        body["instructions"] = QWEN_INSTRUCT
    if seed is not None:
        body["seed"] = seed
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        QWEN_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=QWEN_TIMEOUT) as r:
            return r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _afplay(data: bytes) -> None:
    """폴백 재생 — 오디오 장치를 못 열 때만 쓴다. 기동에 0.8초가 든다(실측)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        f.write(data)
        f.flush()
        subprocess.run(["afplay", f.name], check=False)


def _open_stream(rate: int):
    """PortAudio 출력 스트림을 연다. 실패하면 None — 호출부가 afplay 로 떨어진다."""
    try:
        import sounddevice as sd

        stream = sd.OutputStream(samplerate=rate, channels=1, dtype="int16")
        stream.start()
        return stream
    except Exception:
        return None


class StreamPlayer:
    """상주 오디오 스트림. 열어둔 채 재사용한다.

    `afplay` 는 발화마다 프로세스를 띄워 CoreAudio 를 새로 초기화하는데,
    실측하면 **파일 길이와 무관하게 0.8초 고정비**다(0.1초 파일도 0.83초).
    전체 응답 지연 2.60초 중 31% 가 여기였다. 스트림을 한 번만 열면 0.00초다.

    스레드 안전하지 않다 — Speaker 의 워커 스레드 하나만 쓴다는 전제다.
    """

    def __init__(self) -> None:
        self._stream = None
        self._rate: int | None = None
        self.opened = 0  # 스트림을 실제로 연 횟수(테스트가 재사용을 확인한다)

    def play(self, data: bytes) -> None:
        try:
            with wave.open(io.BytesIO(data)) as w:
                rate = w.getframerate()
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        except Exception:
            _afplay(data)  # wav 로 못 읽으면 외부 재생기에 맡긴다
            return

        if self._stream is None or self._rate != rate:
            self._close_stream()
            self._stream = _open_stream(rate)
            self._rate = rate
            if self._stream is not None:
                self.opened += 1

        if self._stream is None:
            _afplay(data)
            return
        try:
            self._stream.write(pcm)
        except Exception:
            # 장치가 중간에 사라진 경우 — 다음 발화는 다시 열어보고, 이번 건 폴백
            self._close_stream()
            _afplay(data)

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def close(self) -> None:
        self._close_stream()


class Speaker:
    def __init__(
        self,
        voice: str | None = None,
        cmd: list[str] | None = None,
        play=None,
        fallback_cmd: list[str] | None = None,
    ):
        # voice 를 고정하면 그 음성만 쓴다. None 이면 문장마다 자동 선택.
        self._voice = voice
        self._cmd = cmd  # 주면 say 경로를 강제한다(테스트용)
        self._fallback_cmd = fallback_cmd  # qwen 실패 시 쓸 명령(테스트용)
        # 상주 스트림 하나를 워커 스레드가 독점한다(afplay 0.8초 고정비 제거)
        self._player = StreamPlayer()
        self._play = play or self._player.play  # 테스트에서 재생을 가로채는 지점
        self._q: queue.Queue[tuple[str, str, int | None]] = queue.Queue()
        self._speaking = threading.Event()
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

        `qwen` 은 정반대다. 합성 시간이 입력 길이에 선형으로 늘어나(420자 = 32.9초,
        실측) 합치면 첫 소리까지 한참 걸리고, 클라이언트 타임아웃에 걸려 연결이
        끊기면 **서버가 죽는다**(그 뒤 모든 발화가 say 로 폴백된다 — 실제로 겪었다).
        절마다 따로 보내면 다음 절 합성이 앞 절 재생 시간 안에 끝나 끊기지 않는다.
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

    def _enqueue(self, voice: str, text: str, seed: int | None = None) -> None:
        with self._lock:  # 적재 즉시 — 워커 시작 전에 게이팅부터
            self._pending += 1
            self._speaking.set()
        self._q.put((voice, text, seed))

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
        while True:
            voice, text, seed = self._q.get()
            try:
                if BACKEND == "qwen" and self._cmd is None:
                    audio = _qwen_synth(text, seed)
                    if audio is not None:
                        self._play(audio)
                    else:
                        # 서버가 죽었다 — say 로라도 말한다. 음색이 바뀌는 건
                        # 어색하지만 조용히 벙어리가 되는 것보다 낫다.
                        fb = self._fallback_cmd or ["say", "-v", voice]
                        subprocess.run([*fb, text], check=False)
                else:
                    cmd = self._cmd or ["say", "-v", voice]
                    subprocess.run([*cmd, text], check=False)
            except Exception:
                pass  # 시연 중 TTS 실패로 워커가 죽지 않게
            finally:
                with self._lock:
                    self._pending -= 1
                    if self._pending == 0:
                        self._speaking.clear()
                self._q.task_done()
