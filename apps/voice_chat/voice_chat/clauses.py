"""LLM 스트림 델타를 절(節) 단위로 자른다 — 절이 완성되는 즉시 TTS로 보내기 위함.

절마다 `say` 프로세스가 따로 뜨므로 경계에는 반드시 공백과 억양 초기화가 생긴다.
그래서 **자연스러운 경계에서만** 끊는다. 글자 수를 세어 공백에서 자르면
"…바탕으로 대화하고 / 있습니다." 처럼 문장 한가운데가 쪼개져 뚝뚝 끊겨 들린다.

예외는 응답의 첫 절 하나뿐이다. 첫 소리를 빨리 내려고 쉼표에서도 끊는데,
쉼표는 원래 쉬는 자리라 끊어도 어색하지 않다.
"""

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
