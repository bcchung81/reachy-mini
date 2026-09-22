"""로봇 측 무대감독 클라이언트.

가짜 연결을 주입해 소켓 없이 시험한다 — `run(connect_fn=...)`.
"""

import json
import pathlib
import queue
import sys
import threading

from websockets.exceptions import ConnectionClosedOK

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from stage_client import Handlers, StageClient


class FakeWS:
    """서버가 보낼 메시지를 미리 넣어 두는 가짜 연결.

    `recv(timeout=...)` 로 실제 `websockets.sync.connection.Connection.recv`
    와 같은 모양을 흉내낸다 — 메시지가 없으면 `TimeoutError`, 닫혔으면
    `ConnectionClosedOK`. `close_when_empty=False` 로 만들면 큐가 비어도
    절대 닫히지 않는다 — 연결은 살아 있는데 그냥 조용한 상황(실제 무대감독이
    큐 사이에 이런다)을 흉내낸다.

    `__iter__` 는 실제 `websockets` 라이브러리의 이터레이터를 그대로
    흉내낸다 — `recv(timeout=None)` 을 반복 호출하다가 `ConnectionClosedOK`
    에서만 멈춘다(진짜 무한 블록). `recv()` 를 재사용하므로, `stage_client.run()`
    이 예전처럼 `for raw in ws:` 로 되돌아가는 회귀가 생겨도 아래 "조용한
    연결" 테스트가 여전히 잡아낸다.
    """

    def __init__(self, inbox=(), close_when_empty=True):
        self.sent: list[dict] = []
        self._inbox = queue.Queue()
        for m in inbox:
            self._inbox.put(json.dumps(m))
        self.closed = False
        self._close_when_empty = close_when_empty
        self.recv_started = threading.Event()  # 첫 recv 호출 시점 신호(테스트 동기화용)

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def recv(self, timeout=None):
        self.recv_started.set()
        try:
            return self._inbox.get_nowait()
        except queue.Empty:
            pass
        if self._close_when_empty:
            raise ConnectionClosedOK(None, None)
        try:
            return self._inbox.get(timeout=timeout)  # timeout=None 이면 진짜로 영원히 블록
        except queue.Empty:
            raise TimeoutError

    def __iter__(self):
        try:
            while True:
                yield self.recv(timeout=None)
        except ConnectionClosedOK:
            return

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def collector():
    got = []
    return got, Handlers(
        on_say=lambda cue_id, text, seq: got.append(("say", cue_id, text, seq)),
        on_mic=lambda open_: got.append(("mic", open_)),
        on_gaze=lambda target: got.append(("gaze", target)),
        on_abort=lambda: got.append(("abort",)),
        on_camera=lambda viewer, on: got.append(("camera", viewer, on)),
        on_rtc=lambda viewer, payload: got.append(("rtc", viewer, payload)),
        on_standby=lambda on: got.append(("standby", on)),
    )


def run_once(ws, role="mc", unit_id="abc", warn=None):
    got, handlers = collector()
    c = StageClient("ws://x", role, handlers, unit_id=unit_id,
                    version="1.9.0", warn=warn or (lambda m: None))
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    c.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    return c, got, calls


def test_붙으면_hello_를_먼저_보낸다():
    ws = FakeWS()
    run_once(ws)
    assert ws.sent[0] == {"type": "hello", "role": "mc",
                          "unit_id": "abc", "version": "1.9.0"}


def test_say_를_받으면_seq_와_함께_핸들러로_넘긴다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕", "seq": 7}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", 7) in got


def test_seq_가_없는_say_도_받는다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕"}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", None) in got


def test_발성_경계_보고에_seq_를_되돌려준다():
    ws = FakeWS(close_when_empty=False)
    c = StageClient("ws://x", "mc", collector()[1], warn=lambda m: None)
    c._ws = ws
    c.speaking_started("c1", 7)
    c.speaking_ended("c1", 7)
    assert ws.sent[-2:] == [
        {"type": "speaking_started", "cue_id": "c1", "seq": 7},
        {"type": "speaking_ended", "cue_id": "c1", "seq": 7},
    ]


def test_mic_과_gaze_와_abort_를_넘긴다():
    ws = FakeWS([
        {"type": "mic", "open": False},
        {"type": "gaze", "target": "audience"},
        {"type": "abort"},
    ])
    _, got, _ = run_once(ws)
    assert ("mic", False) in got
    assert ("gaze", "audience") in got
    assert ("abort",) in got


def test_로봇이_보낼_수_있는_메시지를_보낸다():
    ws = FakeWS()
    c, _, _ = run_once(ws)
    c._ws = ws                     # run 이 끝난 뒤에도 직접 확인한다
    c.heard("다음")
    c.speaking_started("c1", 1)
    c.speaking_ended("c1", 1)
    c.error("tts", "합성 실패")
    types = [m["type"] for m in ws.sent[1:]]
    assert types == ["heard", "speaking_started", "speaking_ended", "error"]
    assert ws.sent[1]["text"] == "다음"
    assert ws.sent[-1] == {"type": "error", "where": "tts", "detail": "합성 실패"}


def test_감독이_보낼_수_없는_메시지는_경고하고_무시한다():
    warns = []
    ws = FakeWS([{"type": "heard", "text": "감독이 이걸 보내면 안 된다"}])
    _, got, _ = run_once(ws, warn=warns.append)
    assert got == []
    assert any("heard" in w for w in warns)


def test_망가진_메시지는_경고하고_연결을_유지한다():
    warns = []
    ws = FakeWS()
    ws._inbox.put("이건 JSON 이 아니다")
    ws._inbox.put(json.dumps({"type": "mic", "open": True}))
    _, got, _ = run_once(ws, warn=warns.append)
    assert ("mic", True) in got
    assert any("JSON" in w for w in warns)


def test_연결이_끊기면_다시_붙는다():
    got, handlers = collector()
    warns = []
    c = StageClient("ws://x", "mc", handlers, unit_id=None, version="1.9.0",
                    warn=warns.append)
    boxes = [FakeWS(), FakeWS([{"type": "mic", "open": True}])]
    calls = {"n": 0}

    def connect_fn(url):
        i = calls["n"]
        calls["n"] += 1
        if i >= len(boxes):
            raise RuntimeError("그만")
        return boxes[i]

    c.run(should_stop=lambda: calls["n"] >= 2 and boxes[1].closed,
          connect_fn=connect_fn, retry_s=0.0)
    assert calls["n"] >= 2
    assert ("mic", True) in got
    assert any("다시" in w or "재접속" in w for w in warns)


def test_연결_전에_보내면_경고하고_버린다():
    warns = []
    got, handlers = collector()
    c = StageClient("ws://x", "mc", handlers, warn=warns.append)
    c.heard("다음")
    assert any("연결" in w for w in warns)


def test_조용한_연결에서도_should_stop_이_바뀌면_run_이_돌아온다():
    """실제 소켓의 `recv(timeout=None)` 은 메시지가 올 때까지 무한정 블록된다.

    옛 `for raw in ws:` 구현은 메시지를 하나 받은 뒤에만 `should_stop()` 을
    다시 봤다 — 감독이 조용한 구간(정상적인 상황)에는 셧다운 신호가 서도
    영원히 블록됐다. `FakeWS(close_when_empty=False)` 는 큐가 비어도 절대
    닫히지 않는, 즉 메시지도 종료 신호도 주지 않는 조용한 실연결을 흉내낸다.
    `run()` 은 그래도 곧 돌아와야 한다.

    `t.join(timeout=...)` 이 바운드 가드다 — 회귀가 나도 스위트가 걸리지
    않고 이 테스트가 실패로 끝난다.
    """
    ws = FakeWS(close_when_empty=False)
    _, handlers = collector()
    c = StageClient("ws://x", "mc", handlers, warn=lambda m: None)
    stop_event = threading.Event()

    def connect_fn(url):
        return ws

    t = threading.Thread(
        target=c.run,
        kwargs=dict(should_stop=stop_event.is_set, connect_fn=connect_fn),
        daemon=True,
    )
    t.start()
    assert ws.recv_started.wait(timeout=2.0), "recv 루프에 들어가지 못했다"
    stop_event.set()
    t.join(timeout=2.0)
    assert not t.is_alive(), (
        "run() 이 조용한 연결(recv 가 절대 안 끝나는 실제 소켓과 같다)에서 "
        "should_stop 을 못 보고 블록됐다"
    )


# ── 핸들러 예외는 연결 문제가 아니다 (리뷰 A9) ───────────────────────


def test_핸들러_예외는_연결을_끊지_않는다():
    """리뷰 A9 — 핸들러 안의 버그 하나가 재접속을 일으키고, 감독은 그것을
    끊김으로 봐 1인 모드로 내려갔다가 2초 뒤 돌아왔다."""
    warns: list[str] = []
    ws = FakeWS([{"type": "abort"}, {"type": "mic", "open": True}])
    got: list = []

    def boom():
        raise RuntimeError("speaker.stop() 가 터졌다")

    handlers = Handlers(
        on_say=lambda c, t, s: None,
        on_mic=lambda o: got.append(("mic", o)),
        on_gaze=lambda t: None,
        on_abort=boom,
        on_camera=lambda viewer, on: None,
        on_rtc=lambda viewer, payload: None,
        on_standby=lambda on: None,
    )
    c = StageClient("ws://x", "mc", handlers, warn=warns.append)
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    c.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert calls["n"] == 1, "핸들러 예외로 재접속했다"
    assert ("mic", True) in got, "예외 뒤의 지시가 처리되지 않았다"
    assert any("지시 처리" in w for w in warns)
    assert not any("끊어졌다" in w and "RuntimeError" in w for w in warns)


def test_객체가_아닌_JSON_은_경고하고_넘어간다():
    warns: list[str] = []
    c = StageClient("ws://x", "mc", collector()[1], warn=warns.append)
    c._on_raw("[1, 2]")
    assert any("객체" in w for w in warns)


# ── 카메라·RTC·대기모드 (Task 2) ─────────────────────────────────────


def test_hello에_caps를_싣는다():
    got, handlers = collector()
    client = StageClient("ws://x", "mc", handlers, caps=["camera"])
    ws = FakeWS()
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    # `run()` 은 바깥(재접속)·안쪽(수신) 이중 루프라 `should_stop` 이 두 곳에서
    # 각각 불린다. `lambda: True` 는 바깥 루프 진입 자체를 막아 hello 가
    # 나가지 않는다 — `run_once()` 와 같은 관용구(접속 후 ws 가 닫히면 멈춘다)
    # 를 그대로 쓴다.
    client.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert ws.sent[0] == {"type": "hello", "role": "mc", "unit_id": None,
                           "version": "", "caps": ["camera"]}


def test_caps_없으면_hello에서_뺀다():
    got, handlers = collector()
    client = StageClient("ws://x", "mc", handlers)
    ws = FakeWS()
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    client.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert "caps" not in ws.sent[0]


def test_camera_지시가_on_camera로_간다():
    got, handlers = collector()
    ws = FakeWS(inbox=[{"type": "camera", "viewer": "v1", "on": True}])
    client = StageClient("ws://x", "mc", handlers)
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    client.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert ("camera", "v1", True) in got


def test_rtc_지시가_on_rtc로_간다():
    got, handlers = collector()
    ws = FakeWS(inbox=[{"type": "rtc", "viewer": "v1", "sdp": {"type": "answer", "sdp": "v=0"}}])
    client = StageClient("ws://x", "mc", handlers)
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    client.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert ("rtc", "v1", {"sdp": {"type": "answer", "sdp": "v=0"}}) in got


def test_standby_지시가_on_standby로_간다():
    got, handlers = collector()
    ws = FakeWS(inbox=[{"type": "standby", "on": True}])
    client = StageClient("ws://x", "mc", handlers)
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    client.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert ("standby", True) in got


def test_핸들러는_나중에_채울_수_있다():
    """`main.py::stage_run` 이 `client = StageClient(url, role, None, ...)` 로 먼저
    만들고 카메라 팩토리가 `client.rtc` 를 참조한 뒤 `set_handlers()` 로 채우는
    순서를 그대로 흉내낸다 — 순환 의존(Handlers 는 client.rtc 를, client 생성은
    Handlers 를 필요로 함)을 끊는 자리다.

    `run_once()` 와 같은 관용구(접속 후 ws 가 닫히면 멈춘다)를 쓴다 — 바깥(재접속)·
    안쪽(수신) 이중 루프라 단순 호출 횟수 카운터로는 `recv()` 가 한 번도 안 불리고
    끝나 버린다(브리프 초안의 `n[0] > 1` 이 그 함정이었다, 직접 실행해서 확인함).
    """
    got, handlers = collector()
    client = StageClient("ws://x", "mc", None)
    client.set_handlers(handlers)
    ws = FakeWS(inbox=[{"type": "abort"}])
    calls = {"n": 0}

    def connect_fn(url):
        calls["n"] += 1
        return ws

    client.run(should_stop=lambda: calls["n"] >= 1 and ws.closed, connect_fn=connect_fn)
    assert ("abort",) in got


def test_rtc_송신은_viewer와_페이로드를_싣는다():
    got, handlers = collector()
    client = StageClient("ws://x", "mc", handlers)
    ws = FakeWS()
    client._ws = ws
    client.rtc("v1", {"sdp": {"type": "offer", "sdp": "v=0"}})
    assert ws.sent[-1] == {"type": "rtc", "viewer": "v1", "sdp": {"type": "offer", "sdp": "v=0"}}
