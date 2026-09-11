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
        ended(docent, "c1:docent")       # 도슨트 몫은 구분되는 cue_id 로 끝난다
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


def test_사회자가_없으면_도슨트가_직접_듣는다(server):
    """review finding — `_to_listening` 이 "사회자" 로 고정돼 있으면 도슨트
    1인 모드에서는 어느 마이크도 안 열린다(관람객 창구가 아예 사라진다).
    실제 소켓으로 도슨트 자신의 마이크 열기 지시가 진짜로 도착하는지까지
    확인한다 — 감독의 내부 상태만 보는 것과 달리 전송 경로 전체가 맞다."""
    with connect(url_of(server)) as docent:
        hello(docent, "docent")
        time.sleep(0.2)
        server.director.start()          # 사회자가 없다 — 도슨트가 사회자 몫도 읽는다
        drain(docent, 3)                 # mic·gaze·say (사회자 몫)
        ended(docent)                    # 사회자 몫 종료 → 도슨트 몫 시작
        drain(docent, 3)                 # mic·gaze·say (도슨트 몫)
        ended(docent, "c1:docent")       # 도슨트 몫 종료
        opened = drain(docent, 1)        # 도슨트 자신의 마이크가 열린다
        assert opened[0]["type"] == "mic" and opened[0]["open"] is True


class _StubWS:
    """`handler()` 가 요구하는 최소 인터페이스만 흉내낸다 — 진짜 소켓 없이
    stale 핸들러의 `finally` 가 언제 실행되는지를 손으로(결정적으로) 통제한다.
    """

    def __init__(self, hello_msg: str, release: threading.Event):
        self._hello = hello_msg
        self._release = release
        self._sent_hello = False

    def __iter__(self):
        return self

    def __next__(self):
        if not self._sent_hello:
            self._sent_hello = True
            return self._hello
        self._release.wait(2.0)   # 풀리기 전까지는 "아직 연결돼 있다"
        raise StopIteration       # 풀리면 그제서야 연결이 끊어진 것으로 본다

    def send(self, data):
        pass  # 이 테스트는 감독이 보내는 지시를 보지 않는다


def test_빠른_재연결에서_새_연결을_끊긴_것으로_보고하지_않는다():
    """review finding 2 — `_conns` 삭제는 `is ws` 로 지키면서 `on_disconnect`
    는 무조건 불렀다. 같은 role 로 빠르게 재연결하면(새 연결이 이미 그
    자리를 차지한 뒤에야 stale 한 옛 핸들러의 finally 가 실행) 실제로는
    계속 붙어 있는 role 을 감독이 "끊겼다"고 오판해 조용히 1인 모드로
    내려간다 — 실기 WiFi 순단에서 재현 가능한 시나리오다."""
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner")])
    warnings: list[str] = []
    s = StageServer(
        sheet,
        generate=lambda brief, history: "도슨트 대사",
        warn=warnings.append,
    )
    s.director.on_connect("docent")  # 도슨트는 시종일관 붙어 있다고 가정한다

    hello_msg = json.dumps(
        {"type": "hello", "role": "mc", "unit_id": None, "version": "1.9.0"}
    )

    release_old = threading.Event()
    old_ws = _StubWS(hello_msg, release_old)
    t_old = threading.Thread(target=s.handler, args=(old_ws,), daemon=True)
    t_old.start()
    time.sleep(0.2)  # old 가 hello 를 처리하고 등록될 시간을 준다

    release_new = threading.Event()  # 절대 풀지 않는다 — new 는 살아 있는 채로 둔다
    new_ws = _StubWS(hello_msg, release_new)
    t_new = threading.Thread(target=s.handler, args=(new_ws,), daemon=True)
    t_new.start()
    time.sleep(0.2)  # new 가 등록돼 old 의 자리를 이미 차지한다

    release_old.set()  # stale 한 old 핸들러가 이제야 finally 로 빠진다
    t_old.join(timeout=2.0)
    assert not t_old.is_alive(), "old 핸들러가 안 끝났다"

    assert s.director.solo_role is None, (
        "mc 는 새 연결로 계속 붙어 있다 — 1인 모드로 내려가면 안 된다"
    )
    assert not any("[mc]" in w and "끊겼다" in w for w in warnings), warnings


def test_발화_시작_보고가_감독까지_닿는다(server):
    """예전에는 `_dispatch` 가 `pass` 로 버렸다 — 타임아웃 기준점을 다시 거는
    유일한 신호인데 감독이 아예 못 봤다(리뷰 I3)."""
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        before = server.director._deadline
        mc.send(json.dumps({"type": "speaking_started", "cue_id": "c1"}))
        for _ in range(60):              # 서버 스레드가 처리할 때까지
            if server.director._deadline != before:
                break
            time.sleep(0.05)
        assert server.director._deadline != before, "데드라인이 다시 걸리지 않았다"
