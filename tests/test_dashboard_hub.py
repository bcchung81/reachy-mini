import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.dashboard_hub import DashboardHub, tee


class 시계:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_발행한_이벤트는_시각과_함께_이력에_남는다():
    h = DashboardHub(now=시계())
    h.publish("warn", text="경고 하나")
    assert h.history() == [{"kind": "warn", "t": 100.0, "text": "경고 하나"}]


def test_이력은_상한을_넘으면_앞에서_버린다():
    h = DashboardHub(now=시계(), history=3)
    for i in range(5):
        h.publish("n", i=i)
    assert [e["i"] for e in h.history()] == [2, 3, 4]


def test_구독자는_구독한_뒤의_이벤트만_받는다():
    h = DashboardHub(now=시계())
    h.publish("before")
    sub = h.subscribe()
    h.publish("after", x=1)
    assert sub.queue.get_nowait() == {"kind": "after", "t": 100.0, "x": 1}
    assert sub.queue.empty()


def test_구독을_끊으면_더_받지_않는다():
    h = DashboardHub(now=시계())
    sub = h.subscribe()
    h.unsubscribe(sub)
    h.publish("x")
    assert sub.queue.empty()


def test_구독자_큐가_넘치면_버리고_세되_예외는_없다():
    """publish 는 감독이 락을 쥔 채 부르는 자리에서 불린다 — 블로킹·예외 금지."""
    h = DashboardHub(now=시계())
    sub = h.subscribe(maxsize=2)
    for i in range(3):
        h.publish("n", i=i)
    assert sub.dropped == 1
    assert [sub.queue.get_nowait()["i"] for _ in range(2)] == [0, 1]


def test_tee_는_모든_곳에_보내고_터진_곳이_있어도_나머지는_받는다():
    got_a, got_c = [], []

    def 터짐(msg):
        raise ValueError("닫힌 stdout")

    w = tee(got_a.append, 터짐, got_c.append)
    with pytest.raises(ValueError):
        w("경고")
    assert got_a == ["경고"] and got_c == ["경고"]
