"""로봇 측 무대감독 클라이언트.

가짜 연결을 주입해 소켓 없이 시험한다 — `run(connect_fn=...)`.
"""

import json
import pathlib
import queue
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from stage_client import Handlers, StageClient


class FakeWS:
    """서버가 보낼 메시지를 미리 넣어 두는 가짜 연결."""

    def __init__(self, inbox=()):
        self.sent: list[dict] = []
        self._inbox = queue.Queue()
        for m in inbox:
            self._inbox.put(json.dumps(m))
        self.closed = False

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def __iter__(self):
        while True:
            try:
                yield self._inbox.get(timeout=0.3)
            except queue.Empty:
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
        on_say=lambda cue_id, text, gaze: got.append(("say", cue_id, text, gaze)),
        on_mic=lambda open_: got.append(("mic", open_)),
        on_gaze=lambda target: got.append(("gaze", target)),
        on_abort=lambda: got.append(("abort",)),
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


def test_say_를_받으면_핸들러로_넘긴다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕", "gaze": "partner"}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", "partner") in got


def test_gaze_가_없는_say_도_받는다():
    ws = FakeWS([{"type": "say", "cue_id": "c1", "text": "안녕"}])
    _, got, _ = run_once(ws)
    assert ("say", "c1", "안녕", None) in got


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
    c.speaking_started("c1")
    c.speaking_ended("c1")
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
