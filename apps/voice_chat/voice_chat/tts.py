"""TTS 큐 워커 — speak()는 즉시 반환, 백그라운드에서 순차 발화.

speaking 플래그는 큐 적재 순간 켜진다 — 마이크 게이팅이 소리보다
늦게 걸리면 에코가 새기 때문이다.

플래그를 큐가 비었는지로 판정하면 안 된다. 워커가 task_done() 직후
빈 큐를 확인하는 사이에 speak()가 끼어들면, 재생이 남았는데 플래그가
내려간다. 그래서 잠금으로 보호되는 대기 건수로 판정한다.
"""

import queue
import re
import subprocess
import threading
import time

DEFAULT_VOICE = "Yuna"  # ko_KR — 로봇의 기본 언어

# 문자체계 → macOS 음성. 사용자가 "영어로 답해줘" 같은 요청을 했을 때
# 유나가 영문을 읽으면 알아들을 수 없게 뭉개지므로 문장별로 음성을 고른다.
_SCRIPTS = [
    ("Yuna", re.compile(r"[가-힣ᄀ-ᇿ]")),  # 한글
    ("Kyoko", re.compile(r"[぀-ヿ]")),  # 히라가나·가타카나
    ("Tingting", re.compile(r"[一-鿿]")),  # 한자 (가나가 없을 때만)
    ("Samantha", re.compile(r"[A-Za-z]")),  # 라틴 문자
]


def pick_voice(text: str) -> str:
    """문장의 문자체계로 음성을 고른다. 한글이 섞였으면 무조건 한국어 음성이다."""
    for voice, pattern in _SCRIPTS:
        if pattern.search(text):
            return voice
    return DEFAULT_VOICE


class Speaker:
    def __init__(self, voice: str | None = None, cmd: list[str] | None = None):
        # voice 를 고정하면 그 음성만 쓴다. None 이면 문장마다 자동 선택.
        self._voice = voice
        self._cmd = cmd
        self._q: queue.Queue[str] = queue.Queue()
        self._speaking = threading.Event()
        self._lock = threading.Lock()
        self._pending = 0
        threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        with self._lock:  # 적재 즉시 — 워커 시작 전에 게이팅부터
            self._pending += 1
            self._speaking.set()
        self._q.put(text)

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
            text = self._q.get()
            try:
                cmd = self._cmd or ["say", "-v", self._voice or pick_voice(text)]
                subprocess.run([*cmd, text], check=False)
            except Exception:
                pass  # 시연 중 TTS 실패로 워커가 죽지 않게
            finally:
                with self._lock:
                    self._pending -= 1
                    if self._pending == 0:
                        self._speaking.clear()
                self._q.task_done()
