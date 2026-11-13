"""요청 없이 닫힌 빈 연결의 스택 추적만 거른다(`stage/ws_quiet.py`, 2026-11-13).

실기 구동 때 감독 콘솔에 `opening handshake failed … EOFError …` 스택이 통째로 찍혀 운영자가 오류로 읽었다 — 브라우저가 미리 열어 둔
연결이 요청 없이 닫힌 것(무해). 깨진 요청은 여전히 남아야 한다(실패는 소리 내서).
"""

import logging
import pathlib
import socket
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from websockets.sync.server import serve  # noqa: E402

from stage.ws_quiet import EmptyHandshakeFilter, quiet_empty_handshakes  # noqa: E402


def _rec(exc):
    try:
        raise exc
    except Exception:  # noqa: BLE001
        return logging.LogRecord("websockets.server", logging.ERROR, __file__, 1, "opening handshake failed", None, sys.exc_info())


def test_원인_체인에_EOFError_가_있으면_거르고_다른_실패는_남긴다():
    f = EmptyHandshakeFilter()
    try:
        try:
            raise EOFError("stream ends after 0 bytes")
        except EOFError as e:
            raise ValueError("did not receive a valid HTTP request") from e
    except ValueError as chained:
        assert f.filter(_rec(chained)) is False
    assert f.filter(_rec(ValueError("invalid HTTP request line"))) is True
    other = logging.LogRecord("websockets.server", logging.ERROR, __file__, 1, "connection handler failed", None, None)
    assert f.filter(other) is True


def test_필터는_한_번만_걸린다():
    quiet_empty_handshakes(); quiet_empty_handshakes()
    assert sum(isinstance(x, EmptyHandshakeFilter) for x in logging.getLogger("websockets.server").filters) == 1


def _server():
    quiet_empty_handshakes()
    srv = serve(lambda ws: ws.close(), "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.socket.getsockname()[1]


def test_요청_없이_닫힌_빈_연결은_스택을_남기지_않는다(caplog):
    srv, port = _server()
    try:
        with caplog.at_level(logging.ERROR, logger="websockets.server"):
            socket.create_connection(("127.0.0.1", port), timeout=2).close()     # 브라우저 미리 연결·포트 점검
            time.sleep(0.4)
        assert "opening handshake failed" not in caplog.text
    finally:
        srv.shutdown()


def test_깨진_요청은_여전히_로그에_남는다(caplog):
    srv, port = _server()
    try:
        with caplog.at_level(logging.ERROR, logger="websockets.server"):
            s = socket.create_connection(("127.0.0.1", port), timeout=2)
            s.sendall(b"HELLO NOT HTTP\r\n\r\n")
            s.close()
            time.sleep(0.5)                       # websockets 는 이 로그를 연결이 닫힌 **뒤에** 찍는다(실측)
        assert "opening handshake failed" in caplog.text
    finally:
        srv.shutdown()
