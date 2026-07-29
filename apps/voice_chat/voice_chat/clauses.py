"""LLM 스트림 델타를 절(節) 단위로 자른다 — 절이 완성되는 즉시 TTS로 보내기 위함."""

_BOUNDARY = ".!?…。"


class ClauseBuffer:
    def __init__(self, soft_limit: int = 30):
        self._buf = ""
        self._soft_limit = soft_limit

    def feed(self, delta: str) -> list[str]:
        """델타를 누적하고, 완성된 절이 있으면 순서대로 반환한다."""
        self._buf += delta
        out: list[str] = []
        while True:
            cut = -1
            for i, ch in enumerate(self._buf):
                if ch in _BOUNDARY:
                    cut = i
                    break
                if i >= self._soft_limit and ch == " ":
                    cut = i
                    break
            if cut < 0:
                break
            clause = self._buf[: cut + 1].strip()
            self._buf = self._buf[cut + 1 :]
            if clause:
                out.append(clause)
        return out

    def flush(self) -> str | None:
        """스트림 종료 시 잔여분을 내보낸다."""
        s = self._buf.strip()
        self._buf = ""
        return s or None
