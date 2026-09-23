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
from stage.cues import Cue, CueSheet, Turn
from stage.server import StageServer


@pytest.fixture
def server():
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner",
            points=(Turn("", {"일반": "도슨트 대사"}),))])
    warnings: list[str] = []
    s = StageServer(
        sheet,
        generate=lambda role, brief, history: "도슨트 대사",
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


def hello(ws, role, unit_id=None, expect_resync=True):
    """hello 를 보내고, 감독이 접속 직후 되돌려 주는 **마이크 재동기화 한 통**을
    걷어낸다(리뷰 A5a — 재접속한 로봇은 현재 마이크 상태를 모른다). 등록이
    거절되는 경우(`expect_resync=False`)에는 그 한 통이 오지 않는다."""
    ws.send(json.dumps({"type": "hello", "role": role, "unit_id": unit_id,
                        "version": "1.9.0"}))
    if expect_resync:
        m = recv(ws)
        assert m["type"] == "mic", f"접속 직후 mic 재동기화가 아니라 {m} 가 왔다"


# 연결마다 마지막으로 받은 `say` 의 seq — 로봇이 되돌려 줘야 하는 값이다.
_LAST_SAY_SEQ: dict = {}


def recv(ws, timeout=3.0):
    msg = json.loads(ws.recv(timeout=timeout))
    if msg.get("type") == "say":
        _LAST_SAY_SEQ[id(ws)] = msg["seq"]
    return msg


def drain(ws, n, timeout=3.0):
    """정확히 n 통을 읽는다. 남기면 다음 단언으로 샌다."""
    return [recv(ws, timeout) for _ in range(n)]


def ended(ws, cue_id="c1", seq=None):
    """발화 종료 보고. seq 를 안 주면 이 연결이 마지막으로 받은 say 의 것을 쓴다
    — 로봇이 실제로 하는 일과 같다."""
    if seq is None:
        seq = _LAST_SAY_SEQ[id(ws)]
    ws.send(json.dumps({"type": "speaking_ended", "cue_id": cue_id, "seq": seq}))


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
        # 질문 → 사회자가 먼저 확인 멘트(mic·gaze·say)를 받는다(B3) → 그 뒤 도슨트 답
        mc_msgs = drain(mc, 3)
        assert any(m["type"] == "say" and m["cue_id"] == "c1:ack" for m in mc_msgs)
        drain(docent, 1)                 # 도슨트 마이크 닫힘
        ended(mc, "c1:ack")
        doc_msgs = drain(docent, 3)
        assert any(m["type"] == "say" and m["cue_id"] == "c1:qa" for m in doc_msgs)


def test_hello_없이_보낸_메시지는_거절하고_끊는다(server):
    with connect(url_of(server)) as ws:
        ws.send(json.dumps({"type": "heard", "text": "안녕"}))
        time.sleep(0.3)
        assert any("hello" in w for w in server.warnings)


def test_모르는_역할은_거절한다(server):
    with connect(url_of(server)) as ws:
        hello(ws, "감독", expect_resync=False)
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
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner",
            points=(Turn("", {"일반": "도슨트 대사"}),))])
    warnings: list[str] = []
    s = StageServer(
        sheet,
        generate=lambda role, brief, history: "도슨트 대사",
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
        mc.send(json.dumps({"type": "speaking_started", "cue_id": "c1",
                            "seq": _LAST_SAY_SEQ[id(mc)]}))
        for _ in range(60):              # 서버 스레드가 처리할 때까지
            if server.director._deadline != before:
                break
            time.sleep(0.05)
        assert server.director._deadline != before, "데드라인이 다시 걸리지 않았다"


# ── 방어선 (리뷰 MINOR) ──────────────────────────────────────────────

def test_도슨트가_올린_heard_는_버리고_경고한다(server):
    """**관람객 창구는 하나다**(설계 §2).

    도슨트에 청취 루프가 생기거나 로봇 쪽 게이트(`make_heard_sink`)가 새면
    상대 로봇의 목소리가 관람객 발화로 올라온다 — 이 저장소가 이미 밟은
    자기목소리 루프다. 감독 쪽에서 한 줄 더 막는다.
    """
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        ended(mc)
        drain(docent, 3)
        drain(mc, 1)
        ended(docent, "c1:docent")
        drain(mc, 1)                       # 사회자 마이크가 열렸다

        before = server.director.state
        docent.send(json.dumps({"type": "heard", "text": "다음"}))
        for _ in range(60):
            if any("관람객 창구가 아니다" in w for w in server.warnings):
                break
            time.sleep(0.05)
        assert any("관람객 창구가 아니다" in w for w in server.warnings)
        assert server.director.state is before   # 진행하지 않았다


def test_사회자가_없으면_도슨트의_heard_를_받아준다(server):
    """1인 모드에서는 남은 한 대가 관람객 창구를 겸한다 — 막으면 안 된다."""
    with connect(url_of(server)) as docent:
        hello(docent, "docent")
        time.sleep(0.2)
        assert server.director.solo_role == "docent"
        server.director.start()
        drain(docent, 3)
        ended(docent, "c1")
        drain(docent, 3)                   # 도슨트 몫
        ended(docent, "c1:docent")
        drain(docent, 1)                   # 마이크가 열린다

        docent.send(json.dumps({"type": "heard", "text": "마르코니가 누구예요"}))
        msgs = drain(docent, 3)            # 1인 모드 — 확인 멘트도 도슨트가 읽는다
        assert any(m["type"] == "say" and m["cue_id"] == "c1:ack" for m in msgs)
        ended(docent, "c1:ack")
        msgs = drain(docent, 3)
        assert any(m["type"] == "say" and m["cue_id"] == "c1:qa" for m in msgs)


def test_같은_역할로_다시_붙으면_옛_연결을_닫고_경고한다(server):
    """옛 소켓을 열어둔 채 버리면 감독이 보내는 것을 아무도 안 받는 유령
    연결이 남는다. 두 로봇에 같은 역할을 준 사고일 수도 있다."""
    first = connect(url_of(server))
    hello(first, "mc")
    time.sleep(0.2)

    with connect(url_of(server)) as second:
        hello(second, "mc")
        for _ in range(60):
            if any("이미 다른 연결이 있었다" in w for w in server.warnings):
                break
            time.sleep(0.05)
        assert any("이미 다른 연결이 있었다" in w for w in server.warnings)

        # 옛 연결은 실제로 닫혔다 — 읽으려 하면 끊긴다.
        with pytest.raises(Exception):
            first.recv(timeout=2.0)

        # 새 연결은 멀쩡히 지시를 받는다.
        server.director.start()
        assert any(m["type"] == "say" for m in drain(second, 3))
    first.close()


# ── 방어선 (리뷰 A4·A8b) ─────────────────────────────────────────────

@pytest.fixture
def strict_server():
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner",
            points=(Turn("", {"일반": "도슨트 대사"}),))])
    warnings: list[str] = []
    s = StageServer(sheet, generate=lambda r, b, h: "도슨트 대사",
                    expect_units={"mc": "AAA"}, warn=warnings.append)
    s.warnings = warnings
    from websockets.sync.server import serve as ws_serve
    srv = ws_serve(s.handler, "127.0.0.1", 0)
    s.port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield s
    srv.shutdown()
    t.join(timeout=2)


def _wait_warning(server_, needle, n=60):
    for _ in range(n):
        if any(needle in w for w in server_.warnings):
            return True
        time.sleep(0.05)
    return False


def test_뒤바뀐_로봇은_경고_한_줄로_거부되고_감독은_살아_있다(strict_server):
    """리뷰 A4 — 예전엔 UnitMismatch 가 핸들러 밖으로 새어 traceback 만 남고
    시연은 그냥 시작됐다."""
    with connect(url_of(strict_server)) as mc:
        hello(mc, "mc", unit_id="BBB", expect_resync=False)
        with pytest.raises(Exception):
            mc.recv(timeout=2)          # 감독이 연결을 닫는다
    assert _wait_warning(strict_server, "뒤바뀌었는지")
    assert "mc" in strict_server.director.rejected
    from stage.machine import TurnError
    with pytest.raises(TurnError):
        strict_server.director.start()
    assert not any("연결이 끊어졌다" in w for w in strict_server.warnings), (
        "거부된 연결을 '끊어졌다' 로 오해하게 적었다"
    )


def test_text_가_null_인_heard_는_경고하고_연결을_유지한다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        ended(mc)
        drain(docent, 3); drain(mc, 1)
        ended(docent, "c1:docent")
        drain(mc, 1)                                    # mic open
        mc.send(json.dumps({"type": "heard", "text": None}))
        assert _wait_warning(server, "규약")
        time.sleep(0.2)
        assert server.director.solo_role is None, "타입 오류로 연결이 끊겨 1인 모드가 됐다"


def test_seq_가_숫자가_아닌_종료_보고는_경고하고_버린다(server):
    with connect(url_of(server)) as mc, connect(url_of(server)) as docent:
        start_and_drain(server, mc, docent)
        mc.send(json.dumps({"type": "speaking_ended", "cue_id": "c1", "seq": "one"}))
        assert _wait_warning(server, "규약")
        from stage.machine import State
        assert server.director.state is State.MC_SPEAKING


def test_role_이_문자열이_아닌_hello_는_경고하고_끊는다(server):
    with connect(url_of(server)) as ws:
        ws.send(json.dumps({"type": "hello", "role": ["mc"], "unit_id": None, "version": ""}))
        with pytest.raises(Exception):
            ws.recv(timeout=2)
    assert _wait_warning(server, "모르는 역할")


# ~~여는 대사 사전 생성 캐시가 서버 배선까지 닿는지~~ — 고정 대본 전환(2026-09-23)
# 으로 `mc_lines` 배선 자체가 사라져 테스트도 지웠다. 오프닝은 이제 큐시트 원문
# (`Cue.mc`)이라 배선이 끊길 자리가 없다. `level_name` 배선은 아래 하한 테스트와
# `tests/test_stage_main.py` 의 수준 전환 테스트가 계속 지킨다.


def test_StageServer가_도슨트_분량_하한을_감독까지_전달한다():
    """전체 리뷰 I1 — `stage/__main__.py` → `StageServer` → `Director` 배선의
    가운데 토막이다. 여기서 기본값(`MIN_CHARS`=40)으로 삼키면 `main()` 이
    `level.min_chars` 를 아무리 제대로 읽어도 수준별 하한이 감독까지 못 간다
    — `level_name` 이 정확히 그렇게 끊길 뻔했던 자리다.

    **40이 아닌 값으로 본다**(전문가 260). 기본값과 같은 값으로 단언하면 배선이
    끊겨도 통과한다.
    """
    s = StageServer(
        CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner",
            points=(Turn("", {"일반": "도슨트 대사"}),))]),
        generate=lambda role, brief, history: "도슨트 대사",
        docent_min_chars=260,
    )
    assert s.director._docent_min_chars == 260


def test_tick_이_터져도_감시_루프는_계속_돌고_소리를_낸다():
    """**감시 루프는 한 번 터졌다고 죽지 않는다.**

    예전에는 `tick_forever` 가 무방비였다. `director.tick()` 이 `force_listening`
    + `_emit` 뿐이던 동안에는 잃는 것이 타임아웃 복구 하나였지만, 침묵 자동
    진행이 들어오면서 이 루프가 **진행의 임계경로**가 됐다 — 침묵 갈래는
    `_next_locked()` → `_begin_cue()` 까지 돌며 `_warn`(기본값이 `print` 라
    stdout 이 닫히면 `ValueError`), `_spawn_generate` → `Thread().start()`
    (`RuntimeError: can't start new thread`), `_emit` 을 거친다.

    스레드가 죽으면 **타임아웃 복구와 침묵 자동 진행이 동시에 영구 정지**하고,
    관람객은 "다음" 이라는 낱말을 모르므로 시연이 그 자리에서 굳는다 — 자동
    진행이 없애려던 바로 그 상태다. 그래서 삼키되 **반드시 소리 낸다**.

    루프가 안 죽는 것(횟수)과 소리를 내는 것(경고)을 **둘 다** 본다. 경고 없이
    삼키기만 하면 조용히 감시가 헛도는 것을 아무도 모른다.
    """
    calls: list[int] = []
    warnings: list[str] = []
    s = StageServer(
        CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner",
            points=(Turn("", {"일반": "도슨트 대사"}),))]),
        generate=lambda role, brief, history: "도슨트 대사",
        warn=warnings.append,
    )

    def boom():
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("can't start new thread")

    s.director.tick = boom
    # `interval_s=0` — 잠들지 않는다. 멈춤 조건이 호출 횟수라 무한 루프가 아니다.
    s.tick_forever(0.0, lambda: len(calls) >= 3)

    assert len(calls) >= 3, f"첫 예외에서 감시 루프가 죽었다(호출 {len(calls)}회)"
    assert any("tick 에서 오류" in w and "RuntimeError" in w for w in warnings), warnings


# ── Task 3 — 로봇 서버의 송수신·접속을 대시보드 허브로 흘린다 ──────────────


class 기록허브:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish(self, kind, **fields):
        self.events.append((kind, fields))

    def kinds(self):
        return [k for k, _ in self.events]


@pytest.fixture
def server_hub():
    sheet = CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner",
            points=(Turn("", {"일반": "도슨트 대사"}),))])
    hub = 기록허브()
    s = StageServer(sheet, generate=lambda role, brief, history: "도슨트 대사",
                     warn=lambda m: None, hub=hub)
    s.hub = hub

    from websockets.sync.server import serve as ws_serve
    srv = ws_serve(s.handler, "127.0.0.1", 0)
    s.port = srv.socket.getsockname()[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield s
    srv.shutdown()
    t.join(timeout=2)


def test_허브에_접속과_보낸_지시가_남는다(server_hub):
    with connect(url_of(server_hub)) as ws:
        hello(ws, "mc")                       # 접속 직후 mic 재동기화 한 통
        assert ("connect", {"role": "mc", "version": "1.9.0"}) in server_hub.hub.events
        sent = [f for k, f in server_hub.hub.events if k == "sent"]
        assert sent and sent[-1]["role"] == "mc" and sent[-1]["type"] == "mic"
        assert sent[-1]["fields"] == {"open": False}


def test_허브에_받은_관람객_발화와_발화_종료가_남는다(server_hub):
    """발화 흐름은 이 파일의 기존 종단 테스트(시작 → 사회자 say → ended)를 따라 만든다.
    heard 는 사회자가 LISTENING 일 때만 감독에게 가지만, **허브에는 검증을 통과한
    순간 남는다**(감독이 버려도 운영자는 무엇이 들렸는지 봐야 한다)."""
    with connect(url_of(server_hub)) as mc, connect(url_of(server_hub)) as docent:
        start_and_drain(server_hub, mc, docent)
        seq = _LAST_SAY_SEQ[id(mc)]
        ended(mc)

        for _ in range(60):
            if any(k == "recv" and f.get("type") == "speaking_ended"
                   for k, f in server_hub.hub.events):
                break
            time.sleep(0.05)
        recv_ = [f for k, f in server_hub.hub.events if k == "recv"]
        assert {"role": "mc", "type": "speaking_ended",
                "fields": {"cue_id": "c1", "seq": seq}} in recv_

        # 사회자 마이크가 열릴 때까지 흐름을 이어간다(도슨트 몫 완료) —
        # heard 는 LISTENING 에서만 감독에게 가지만 허브 기록은 검증만 통과하면
        # 남으므로, 실제로 그 자리까지 가서 관람객 발화 한 건을 넣어 본다.
        drain(docent, 3)
        drain(mc, 1)
        ended(docent, "c1:docent")
        drain(mc, 1)                          # 사회자 마이크가 열렸다

        mc.send(json.dumps({"type": "heard", "text": "마르코니가 누구예요"}))
        for _ in range(60):
            if any(k == "recv" and f.get("type") == "heard"
                   for k, f in server_hub.hub.events):
                break
            time.sleep(0.05)
        recv_ = [f for k, f in server_hub.hub.events if k == "recv"]
        assert {"role": "mc", "type": "heard",
                "fields": {"text": "마르코니가 누구예요"}} in recv_
        drain(mc, 3)                          # 확인 멘트(mic·gaze·say) 소비
        drain(docent, 1)


def test_허브에_끊김이_남는다(server_hub):
    with connect(url_of(server_hub)) as ws:
        hello(ws, "mc")
    for _ in range(50):
        if "disconnect" in server_hub.hub.kinds():
            break
        time.sleep(0.02)
    assert ("disconnect", {"role": "mc"}) in server_hub.hub.events


def test_허브가_없어도_지금처럼_돈다(server):
    """`hub=None`(기본값) — 기존 fixture 그대로. 한 번 붙었다 떨어져도 예외가 없다."""
    with connect(url_of(server)) as ws:
        hello(ws, "mc")


# ── 운영 모드 1단계 — hello 의 선택 필드 `caps`(로봇 앱이 할 줄 아는 것) ──────────


def _hello_caps(ws, role, caps):
    """`caps` 를 실은 hello. 접속 직후의 마이크 재동기화 한 통을 걷어낸다 — 그 한 통은
    감독이 등록(`on_connect`)의 락 안에서 보내므로, 받았으면 hello 처리가 끝났다."""
    ws.send(json.dumps({"type": "hello", "role": role, "unit_id": None,
                        "version": "2.0.0", "caps": caps}))
    m = recv(ws)
    assert m["type"] == "mic", f"접속 직후 mic 재동기화가 아니라 {m} 가 왔다"


def test_사회자가_hello_에_단독을_알리면_감독이_단독_가능으로_본다(server):
    with connect(url_of(server)) as mc:
        _hello_caps(mc, "mc", ["solo"])
        assert server.director.snapshot()["solo_available"] is True


@pytest.mark.parametrize(
    "caps, 보인_값",
    [("solo", "'solo'"), (["solo", 1], "['solo', 1]")],
    ids=["문자열", "문자열_아닌_원소"],
)
def test_caps_가_문자열_목록이_아니면_경고하고_없는_것으로_본다(server, caps, 보인_값):
    """규약 위반은 그 필드만 버린다 — 연결은 산다(`_str_field` 와 같은 원칙). 문자열을
    그대로 넘기면 `set("solo")` 가 {'s','o','l'} 이 되어 **조용히** 단독이 안 켜진다."""
    with connect(url_of(server)) as mc:
        _hello_caps(mc, "mc", caps)
        assert f"[mc] hello 의 caps 가 문자열 목록이 아니다 — 무시한다: {보인_값}" in server.warnings
        assert server.director.snapshot()["solo_available"] is False
        assert server.director.snapshot()["connected"] == ["mc"]   # 연결은 살아 붙어 있다


# ── Task 6 — CameraRelay 배선: hello caps·연결·rtc·오류, 허브를 안 타는 raw 송신 ──

from stage.camera import CameraRelay


def test_server는_camera_속성을_스스로_만든다(server):
    assert isinstance(server.camera, CameraRelay)


def test_hello의_caps가_camera로_전달된다(server):
    with connect(url_of(server)) as ws:
        _hello_caps(ws, "mc", ["camera"])
        assert server.camera.snapshot()["mc"]["available"] is True


def test_연결이_끊기면_camera에도_알린다(server):
    with connect(url_of(server)) as ws:
        _hello_caps(ws, "mc", ["camera"])
    for _ in range(50):
        if server.camera.snapshot()["mc"]["available"] is False:
            break
        time.sleep(0.02)
    assert server.camera.snapshot()["mc"]["available"] is False


def test_rtc는_camera로_라우팅되고_허브_이력에_안_쌓인다(server_hub):
    with connect(url_of(server_hub)) as mc:
        _hello_caps(mc, "mc", ["camera"])
        events = []
        vid = server_hub.camera.add_viewer(events.append)
        mc.send(json.dumps({"type": "rtc", "viewer": vid, "sdp": {"type": "offer", "sdp": "v=0"}}))
        for _ in range(50):
            if events:
                break
            time.sleep(0.02)
        assert events and events[0]["kind"] == "rtc"
        assert not any(k == "recv" and f.get("type") == "rtc" for k, f in server_hub.hub.events)
        assert not any(k == "sent" and f.get("type") == "rtc" for k, f in server_hub.hub.events)


def test_camera_오류는_camera로도_간다(server):
    with connect(url_of(server)) as ws:
        _hello_caps(ws, "mc", ["camera"])
        ws.send(json.dumps({"type": "error", "where": "camera", "detail": "파이프라인 실패"}))
        for _ in range(50):
            if "파이프라인 실패" in server.camera.snapshot()["mc"]["reason"]:
                break
            time.sleep(0.02)
        assert "파이프라인 실패" in server.camera.snapshot()["mc"]["reason"]


def test_거절된_사칭_연결이_기존_로봇의_카메라를_안_끈다(strict_server):
    """리뷰 Important 1 — `self.camera.on_robot_hello` 를 `director.on_hello` 의
    `UnitMismatch` 검사보다 **먼저** 부르면, 거절된 사칭 연결(이 역할로 붙은 적이
    없다)의 caps 가 이미 `CameraRelay._recompute` 를 돌려 자리에 계속 붙어 있는
    정상 로봇의 카메라를 경고 한 줄 없이 꺼 버린다. `director.on_hello` 자신이
    거절 검사를 caps 기록보다 먼저 두는 것(그 주석 참고)과 같은 순서를
    `handler()` 도 지켜야 한다."""
    with connect(url_of(strict_server)) as mc:
        # 정상 mc(unit_id 가 기대값과 일치)가 먼저 붙어 카메라 능력을 알린다.
        mc.send(json.dumps({"type": "hello", "role": "mc", "unit_id": "AAA",
                            "version": "1.9.0", "caps": ["camera"]}))
        m = recv(mc)
        assert m["type"] == "mic", f"접속 직후 mic 재동기화가 아니라 {m} 가 왔다"
        assert strict_server.camera.snapshot()["mc"]["available"] is True

        # 다른 unit_id 로 같은 mc 자리에 사칭 연결이 붙으려 한다 — caps 에는
        # camera 가 없다(뒤바뀐/오배선된 앱을 흉내낸다). UnitMismatch 로 거절돼야
        # 하고, 이 연결은 `_conns` 에 한 번도 등록되지 않는다.
        with connect(url_of(strict_server)) as impostor:
            impostor.send(json.dumps({"type": "hello", "role": "mc", "unit_id": "BBB",
                                      "version": "1.9.0", "caps": []}))
            with pytest.raises(Exception):
                impostor.recv(timeout=2)          # 감독이 연결을 닫는다
        assert _wait_warning(strict_server, "뒤바뀌었는지")

        # 거절 경로는 finally 를 안 타므로(등록된 적이 없다) 되돌릴 기회도 없다
        # — 애초에 꺼지지 않았어야 한다. 정상 mc 의 카메라는 그대로 켜져 있다.
        assert strict_server.camera.snapshot()["mc"]["available"] is True


# ── 최종 전체 브랜치 리뷰 C1 — 시청자가 로봇의 hello 보다 먼저 붙어도 camera{on:true} 가 실제로 로봇에 닿는다 ──


def test_시청자가_먼저_붙어_있어도_로봇_hello에_camera_on이_실제로_닿는다(server):
    """C1 — 예전에는 `self.camera.on_robot_hello(role, caps)` 가 `self._conns[role]
    = ws` **보다 먼저** 왔다. 대시보드 시청자가 이미 붙어 있는 상태에서 로봇이
    (재)연결되면 `on_robot_hello` → `_recompute` → `_set_pair(True)` → `_send_raw`
    가 `self._conns.get(role)` 를 아직 못 찾아 `camera{on:true}` 를 조용히 버렸다.
    `CameraRelay._active` 는 이미 True 로 찍혀서 재계산해도 다시 안 보낸다 —
    `server.camera.snapshot()["mc"]["available"]` 만 보면(기존
    `test_hello의_caps가_camera로_전달된다`) 이 버그를 못 잡는다(그 플래그는 송신
    성공 여부와 무관하게 True 가 된다). **로봇 자신의 소켓이 실제로 무엇을 받았는지**
    까지 봐야 한다 — 이 세션에서 실기로 그대로 재현된 시나리오(시청자가 로봇의
    hello 보다 먼저 붙어 있었다)를 그대로 옮긴다."""
    events = []
    # 시청자를 **로봇이 붙기 전에** 먼저 등록한다 — C1 이 겨냥하는 정확한 순서.
    vid = server.camera.add_viewer(events.append)

    with connect(url_of(server)) as ws:
        # `_hello_caps`/`hello` 헬퍼는 "첫 통은 mic" 를 전제한다 — 시청자가 없을 때는
        # 맞지만, 여기서는 시청자가 있어 `camera.on_robot_hello` 가 `director.on_connect`
        # (mic 재동기화)보다 **먼저** 불려 camera 가 먼저 올 수도 있다. 순서에 기대지
        # 않고 두 통을 걷어 **둘 다** 왔는지 본다.
        ws.send(json.dumps({"type": "hello", "role": "mc", "unit_id": None,
                            "version": "2.0.0", "caps": ["camera"]}))
        msgs = [recv(ws), recv(ws)]
        assert {m["type"] for m in msgs} == {"mic", "camera"}, msgs
        cam_on = next(m for m in msgs if m["type"] == "camera")
        assert cam_on == {"type": "camera", "viewer": vid, "on": True}, (
            "camera{on:true} 가 로봇 소켓에 실제로 안 닿았다 — C1 이 다시 났다"
        )
        # 연결이 살아 있는 **동안** 확인한다 — `with` 를 벗어나면 소켓이 닫혀
        # `camera.on_robot_disconnect` 가 돌아 `available` 이 다시 False 로 내려간다.
        assert server.camera.snapshot()["mc"]["available"] is True
