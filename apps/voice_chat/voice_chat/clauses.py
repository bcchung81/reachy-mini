"""LLM 스트림 델타를 절(節) 단위로 자른다 — 절이 완성되는 즉시 TTS로 보내기 위함.

절마다 `say` 프로세스가 따로 뜨므로 경계에는 반드시 공백과 억양 초기화가 생긴다.
그래서 **자연스러운 경계에서만** 끊는다. 글자 수를 세어 공백에서 자르면
"…바탕으로 대화하고 / 있습니다." 처럼 문장 한가운데가 쪼개져 뚝뚝 끊겨 들린다.

예외는 응답의 첫 절 하나뿐이다. 첫 소리를 빨리 내려고 쉼표에서도 끊는데,
쉼표는 원래 쉬는 자리라 끊어도 어색하지 않다.
"""

import re

_SENTENCE_END = ".!?…。"
_FIRST_CLAUSE_EXTRA = ",，"


class ClauseBuffer:
    def __init__(self, runaway_limit: int = 120, first_break_on_comma: bool = True):
        self._buf = ""
        self._runaway_limit = runaway_limit
        self._first_break_on_comma = first_break_on_comma
        self._emitted = 0

    def _find_cut(self) -> int:
        """자를 위치를 찾는다. 없으면 -1."""
        breakers = _SENTENCE_END
        if self._emitted == 0 and self._first_break_on_comma:
            breakers += _FIRST_CLAUSE_EXTRA
        for i, ch in enumerate(self._buf):
            if ch in breakers:
                return i
        # 안전장치 — 구두점 없이 한없이 길어지면 공백에서라도 끊는다
        if len(self._buf) >= self._runaway_limit:
            for i in range(self._runaway_limit, len(self._buf)):
                if self._buf[i] == " ":
                    return i
        return -1

    def feed(self, delta: str) -> list[str]:
        """델타를 누적하고, 완성된 절이 있으면 순서대로 반환한다."""
        self._buf += delta
        out: list[str] = []
        while True:
            cut = self._find_cut()
            if cut < 0:
                break
            clause = self._buf[: cut + 1].strip()
            self._buf = self._buf[cut + 1 :]
            if clause:
                out.append(clause)
                self._emitted += 1
        return out

    def flush(self) -> str | None:
        """스트림 종료 시 잔여분을 내보낸다."""
        s = self._buf.strip()
        self._buf = ""
        if s:
            self._emitted += 1
        return s or None


# ── split_sentences — 완성된 문자열을 문장 단위로 쪼갠다 ────────────────────
#
# ClauseBuffer 와는 다른 문제다: ClauseBuffer 는 LLM 스트림 델타를 누적하며
# "지금까지 온 만큼"에서 자르지만, 이건 무대감독이 이미 다 만들어 놓은 대사
# 문자열 하나(최대 280자, 40~90초 분량)를 한 번에 문장 리스트로 쪼갠다.
#
# 왜 필요한가(TTS 폴백 결함 원인): 무대 모드는 이 문장을 통째로 `speaker.speak()`
# 하나로 보냈다. TTS 서버(Qwen3-TTS)는 요청을 하나씩 순서대로 처리하고,
# **클라이언트가 연결을 끊어도 끊긴 요청을 끝까지 합성한다**(실측: 40.8초 요청을
# 3초 뒤 보낸 5.2초 요청이 65.3초 걸렸다). 운영자가 `n`/`a`/`g` 로 끊을 때마다
# 버려진 감독 대사 전체(최대 90초)가 서버를 붙잡았고, 그 뒤에 밀린 짧은 요청이
# `QWEN_TIMEOUT`(90초)을 넘겨 로컬 합성기(실기 Linux 는 espeak-ng, 남성 기계음)로
# 폴백했다 — 이것이 "목소리가 가끔 남자로 바뀐다"는 결함의 원인이다. 요청을
# 문장 단위로 쪼개면 끊었을 때 서버가 붙잡는 시간이 문장 하나(+선요청 하나)로
# 줄어든다(`session.speak` 가 이 함수로 나눈 뒤 `speaker.speak_many()` 로 보낸다).
#
# 로봇에는 `stage/` 가 없으므로 이 로직은 앱 안에 둔다 — `stage/speech_text.py`
# 에 같은 규칙의 구현이 있지만 **import 하지 않는다**(경계를 넘으면 무대 대시보드가
# 없는 실기 배포에서 그대로 깨진다).
#
# 종결부호(위 `_SENTENCE_END` 재사용) 뒤에 숫자가 오되, **마침표 앞이 ASCII
# 영숫자일 때만** 소수점으로 보고 안 자른다("2.4GHz", "1.5배"). 한글 문장 끝
# 뒤의 연도("…했습니다.1901년에는…")는 마침표 앞이 한글이라 이 예외에 안 걸려
# 문장 경계로 남는다 — 감독 대본에 이 모양이 훨씬 흔하다(연도 인용이 소수점보다
# 많다).
_SENT_END_RE = re.compile(
    r"[" + re.escape(_SENTENCE_END) + r"]+(?!(?<=[0-9A-Za-z]\.)[0-9])"
)


def split_sentences(text: str) -> list[str]:
    """텍스트를 문장 단위로 나눈다. 종결부호가 없으면 통째로 한 문장, 빈 조각은 버린다."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENT_END_RE.finditer(text):
        if text[start : m.end()].strip():
            spans.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return [text[a:b].strip() for a, b in spans]
