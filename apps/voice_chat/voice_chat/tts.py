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

# ── 백엔드 선택 ──────────────────────────────────────────────────
# 기본은 `say` 다. 새 음색을 쓰려면 TTS_BACKEND=qwen.
# 기본값을 바꾸지 않는 이유: say 는 검증됐고 의존성이 없다. qwen 은 별도 서버가
# 떠 있어야 하므로, 서버가 없을 때 조용히 벙어리가 되는 일이 없어야 한다.
BACKEND = os.environ.get("TTS_BACKEND", "say")

QWEN_URL = os.environ.get("TTS_QWEN_URL", "http://127.0.0.1:8099/v1/audio/speech")
QWEN_SPEED = float(os.environ.get("TTS_QWEN_SPEED", "1.2"))
QWEN_TIMEOUT = float(os.environ.get("TTS_QWEN_TIMEOUT", "20"))

# 채택 음색 — 2026-07-30 청취 비교로 고른 '소년'.
# 지시문의 속도 제어가 불안정하다(같은 취지의 다른 표현이 오히려 느려진다).
# **상수로 고정하고, 손대면 반드시 발화 길이를 다시 잴 것.** docs/tts-voice-followup.md 참조.
QWEN_INSTRUCT = os.environ.get(
    "TTS_QWEN_INSTRUCT",
    "활발한 남자아이 목소리. 밝고 에너지가 넘치며 말끝이 통통 튄다.",
)

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


def _qwen_synth(text: str) -> bytes | None:
    """Qwen3-TTS 서버에 합성을 요청한다. 실패하면 None — 앱은 계속 돌아야 한다."""
    payload = json.dumps(
        {"input": text, "model": "tts", "instructions": QWEN_INSTRUCT, "speed": QWEN_SPEED}
    ).encode()
    req = urllib.request.Request(
        QWEN_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=QWEN_TIMEOUT) as r:
            return r.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _play_wav(data: bytes) -> None:
    """받은 wav 를 재생한다. afplay 는 파일만 받으므로 임시 파일을 거친다."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
        f.write(data)
        f.flush()
        subprocess.run(["afplay", f.name], check=False)


class Speaker:
    def __init__(
        self,
        voice: str | None = None,
        cmd: list[str] | None = None,
        play=None,
    ):
        # voice 를 고정하면 그 음성만 쓴다. None 이면 문장마다 자동 선택.
        self._voice = voice
        self._cmd = cmd
        self._play = play or _play_wav  # 테스트에서 재생을 가로채는 지점
        self._q: queue.Queue[tuple[str, str]] = queue.Queue()
        self._speaking = threading.Event()
        self._lock = threading.Lock()
        self._pending = 0
        threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._enqueue(self._voice or pick_voice(text), text)

    def speak_many(self, clauses: list[str]) -> None:
        """여러 절을 한 번에 넘긴다. 같은 음성끼리 묶여 호출 수가 줄어든다."""
        if self._voice is not None:  # 음성이 고정돼 있으면 묶을 이유가 없다
            joined = " ".join(c.strip() for c in clauses if c.strip())
            if joined:
                self._enqueue(self._voice, joined)
            return
        for voice, text in group_by_voice(clauses):
            self._enqueue(voice, text)

    def _enqueue(self, voice: str, text: str) -> None:
        with self._lock:  # 적재 즉시 — 워커 시작 전에 게이팅부터
            self._pending += 1
            self._speaking.set()
        self._q.put((voice, text))

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
            voice, text = self._q.get()
            try:
                if BACKEND == "qwen" and self._cmd is None:
                    audio = _qwen_synth(text)
                    if audio is not None:
                        self._play(audio)
                    # 서버가 죽었으면 이 발화는 건너뛴다. 여기서 say 로 되돌리면
                    # 음색이 갑자기 바뀌어 더 어색하다 — 모션과 대화는 계속 돈다.
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
