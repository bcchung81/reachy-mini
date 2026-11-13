"""웹소켓 서버 로그에서 **요청 없이 닫힌 빈 연결**의 스택 추적만 걸러 낸다(2026-11-13).

증상: 실기 구동 때 감독 콘솔에 `opening handshake failed … EOFError: stream ends after 0 bytes … InvalidMessage: did not receive a
valid HTTP request` 스택이 통째로 찍혔다. 원인: 누군가 TCP 로 붙었다가 HTTP 요청 한 줄도 없이 닫았다 — 브라우저가 대시보드·교육자료
화면(`/stage/…`)을 열 때 미리 열어 두는 연결(preconnect)이나 포트 점검이 그렇다(헤드리스 Chrome 으로 `/stage/` 를 열 때마다 재현 —
작업자 D 가 봄). 공연에는 무해한데, 운영자는 오류로 읽고 진짜 경고(로봇 끊김 등)가 그 스택에 묻힌다.

**걸러 내는 것은 원인 체인에 `EOFError` 가 있는 "opening handshake failed" 하나뿐이다** — 요청이 오긴 왔는데 틀린 것(다른 사이트의
접속 시도, 깨진 요청)은 그대로 남는다(실패는 소리 내서).
"""

from __future__ import annotations

import logging

LOGGER = "websockets.server"


class EmptyHandshakeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage() != "opening handshake failed" or not record.exc_info:
            return True
        # **직접 원인(`__cause__`) 체인만** 본다. 빈 연결은 `InvalidMessage` ← `EOFError("connection closed while reading HTTP
        # request line")` 로 직접 이어진다(실측). 깨진 요청(`HELLO NOT HTTP`)의 `ValueError` 도 `__context__` 에는 EOFError 가
        # 딸려 있어, 문맥까지 따라가면 진짜 오류까지 지워졌다(테스트에서 잡음).
        exc, seen = record.exc_info[1], set()
        while exc is not None and id(exc) not in seen:
            if isinstance(exc, EOFError):
                return False
            seen.add(id(exc))
            exc = exc.__cause__
        return True


def quiet_empty_handshakes(logger_name: str = LOGGER) -> None:
    """한 번만 건다(여러 서버가 불러도 필터가 겹치지 않게)."""
    log = logging.getLogger(logger_name)
    if not any(isinstance(f, EmptyHandshakeFilter) for f in log.filters):
        log.addFilter(EmptyHandshakeFilter())
