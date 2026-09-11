"""무대감독 WS 서버 — 실제 소켓으로 도는 종단 테스트.

pytest-asyncio 가 없으므로 websockets 의 **sync API** 만 쓴다.

**메시지 개수 주의.** 감독은 큐의 gaze 를 대사와 함께 보낸다. 그래서 말할 차례가
된 로봇은 `mic`·`gaze`·`say` **3통**을 받고 상대는 `mic` 1통만 받는다. 덜 읽으면
남은 것이 다음 단언으로 새어 들어가 **엉뚱한 이유로 통과하는 테스트**가 된다 —
그래서 매 단계 정확한 통수를 걷어낸다.
"""

import json
import pathlib
import sys
import threading
import time

import pytest
from websockets.sync.client import connect

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet
from stage.server import StageServer


@pytest.fixture
def server():
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner")])
    warnings: list[str] = []
    s = StageServer(
        sheet,
        generate=lambda brief, history: "도슨트 대사",
        warn=warnings.append,
    )
    s.warnings = warnings

    from websockets.sync.server import serve as ws_serve

    srv = ws_serve(s.handler, "127.0.0.1", 0)
    s.port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield s
    srv.shutdown()
    t.join(timeout=2)


def url_of(server_):
    return f"ws://127.0.0.1:{server_.port}"


def hello(ws, role, unit_id=None):
    ws.send(json.dumps({"type": "hello", "role": role, "unit_id": unit_id,
                        "version": "1.9.0"}))


def recv(ws, timeout=3.0):
    return json.loads(ws.recv(timeout=timeout))


def drain(ws, n, timeout=3.0):
    """정확히 n 통을 읽는다. 남기면 다음 단언으로 샌다."""
    return [recv(ws, timeout) for _ in range(n)]


def ended(ws, cue_id="c1"):
    ws.send(json.dumps({"type": "speaking_ended", "cue_id": cue_id}))


def start_and_drain(server_, mc, docent):
    """두 로봇을 붙이고 첫 큐를 시작한 뒤 그 메시지를 남김없이 걷어낸다."""
    hello(mc, "mc")
    hello(docent, "docent")
    time.sleep(0.2)                      # 등록이 끝나기를 기다린다
    server_.director.start()
    return drain(mc, 3), drain(docent, 1)   # mic·gaze·say / mic


def test_두_로봇이_붙고_시작하면_사회자가_대사를_받는다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        mc_msgs, doc_msgs = start_and_drain(server, mc, docent)
        assert {m["type"] for m in mc_msgs} == {"mic", "gaze", "say"}
        said = next(m for m in mc_msgs if m["type"] == "say")
        assert said["text"] == "사회자 대사"
        # 도슨트는 마이크만 닫힌다 — 불변식 ①
        assert [m["type"] for m in doc_msgs] == ["mic"]
        assert doc_msgs[0]["open"] is False


def test_사회자_발화가_끝나면_도슨트가_대사를_받는다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        ended(mc)
        doc_msgs = drain(docent, 3)      # mic·gaze·say
        assert any(m["type"] == "say" and m["text"] == "도슨트 대사"
                   for m in doc_msgs)
        # 전환 중 사회자 마이크는 열리지 않는다 — coalesce 가 하는 일
        mc_msgs = drain(mc, 1)
        assert mc_msgs[0]["type"] == "mic" and mc_msgs[0]["open"] is False


def test_들은_말이_감독에_닿는다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        ended(mc)
        drain(docent, 3)
        drain(mc, 1)
        ended(docent)
        opened = drain(mc, 1)            # 이제서야 사회자 마이크가 열린다
        assert opened[0]["type"] == "mic" and opened[0]["open"] is True

        mc.send(json.dumps({"type": "heard", "text": "마르코니가 누구예요"}))
        doc_msgs = drain(docent, 3)
        assert any(m["type"] == "say" for m in doc_msgs)


def test_hello_없이_보낸_메시지는_거절하고_끊는다(server):
    with connect(url_of(server)) as ws:
        ws.send(json.dumps({"type": "heard", "text": "안녕"}))
        time.sleep(0.3)
        assert any("hello" in w for w in server.warnings)


def test_모르는_역할은_거절한다(server):
    with connect(url_of(server)) as ws:
        hello(ws, "감독")
        time.sleep(0.3)
        assert any("역할" in w for w in server.warnings)


def test_망가진_메시지는_경고하고_연결을_유지한다(server):
    with connect(url_of(server)) as mc:
        hello(mc, "mc")
        time.sleep(0.2)
        mc.send("이건 JSON 이 아니다")
        time.sleep(0.3)
        assert any("JSON" in w for w in server.warnings)
        mc.send(json.dumps({"type": "heard", "text": "다음"}))   # 아직 살아 있다
        time.sleep(0.2)


def test_붙지_않은_로봇에게_보내면_경고한다(server):
    with connect(url_of(server)) as mc:
        hello(mc, "mc")
        time.sleep(0.2)
        server.director.start()           # 도슨트가 없다
        drain(mc, 3)
        assert any("docent" in w and "붙지" in w for w in server.warnings)


def test_연결이_끊기면_감독이_1인_모드로_내려간다(server):
    url = f"ws://127.0.0.1:{server.port}"
    with connect(url) as mc:
        hello(mc, "mc")
        time.sleep(0.2)
        with connect(url) as docent:
            hello(docent, "docent")
            time.sleep(0.2)
            assert server.director.solo_role is None
        time.sleep(0.4)                          # 도슨트가 나갔다
        assert server.director.solo_role == "mc"
