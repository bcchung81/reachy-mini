"""관람객 보조 화면(`/audience`, `/ws/audience`)과 수준별 교육자료(`/handout`) — 2026-09-25.

보조 화면은 관람객 쪽 모니터에 뜬다. 가장 중요한 계약은 둘이다:
① **명령을 받지 않는다** — 보조 소켓으로 무엇을 보내도 감독은 움직이지 않는다.
② **운영 정보를 흘리지 않는다** — 경고·거부 사유·관람객 STT 원문(이벤트 이력)과 연결·카메라 상태는 나가지 않는다.
교육자료는 검수한 고정 대본만 옮기고(내부 지시문·저작 메모·진행 안내는 빼고) 모든 글자를 이스케이프한다.
"""

import contextlib
import json
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect
from websockets.sync.server import serve as ws_serve

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, Turn
from stage.dashboard import AUDIENCE_SNAPSHOT_KEYS, DashboardServer
from stage.dashboard_hub import DashboardHub
from stage.handout import render_handout

AUDIENCE_PAGE = pathlib.Path(__file__).parent.parent / "stage" / "audience_page.html"
_수준들 = ["초등", "일반"]


def _큐(cid, title, mc, answers_by_level, asks=None, **kw):
    asks = asks or [""] * len(answers_by_level)
    return Cue(
        cid, title, mc, "옛 지시", "partner",
        briefs={lv: {"mc_brief": "m", "docent_brief": f"{cid} 내부 지시문", "guard": f"{cid} 금지 규칙"}
                for lv in _수준들},
        points=tuple(Turn(ask, answers) for ask, answers in zip(asks, answers_by_level)),
        **kw,
    )


def _시트():
    return (
        _큐("01-intro", "체험관 개요", "안녕하세요! 도슨트, 소개해 줄래요?",
            [{"초등": "초등 첫 설명이에요.", "일반": "일반 첫 설명이에요."},
             {"초등": "초등 둘째 설명이에요.", "일반": "일반 둘째 설명이에요."}],
            asks=["", "그럼 누가 만들었어요?"],
            mc_after="질문 있으세요? '다음'이라고 말해 주세요.", topic="저작 메모 — 새 정보 없이 닫는다"),
        _큐("02-x", "<script>alert(1)</script>", "사회자 <b>대사</b>",
            [{"초등": "a < b & c", "일반": "일반"}]),
    )


# ── 교육자료(순수 함수) ─────────────────────────────────────────────


def test_교육자료는_그_수준의_대화를_그대로_옮긴다():
    page = render_handout(_시트(), "초등", _수준들)
    for want in ("안녕하세요! 도슨트, 소개해 줄래요?", "초등 첫 설명이에요.", "그럼 누가 만들었어요?",
                 "초등 둘째 설명이에요.", "체험관 개요"):
        assert want in page, want
    assert "일반 첫 설명이에요." not in page                      # 다른 수준 설명은 없다


def test_교육자료에는_내부_지시문과_저작_메모와_진행_안내가_없다():
    """브리프·금지 규칙은 모델에게 주는 지시문, topic 은 일부가 저작 메모, 받아치기는 진행 안내다."""
    page = render_handout(_시트(), "초등", _수준들)
    for leak in ("내부 지시문", "금지 규칙", "저작 메모", "'다음'이라고 말해 주세요"):
        assert leak not in page, leak


def test_교육자료는_모든_글자를_이스케이프한다():
    page = render_handout(_시트(), "초등", _수준들)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "사회자 &lt;b&gt;대사&lt;/b&gt;" in page and "a &lt; b &amp; c" in page


def test_교육자료는_수준을_바꾸는_링크와_지금_수준_표시가_있다():
    page = render_handout(_시트(), "일반", _수준들)
    assert 'href="/handout?level=%EC%B4%88%EB%93%B1"' in page            # 초등(퍼센트 인코딩)
    assert 'class="on" aria-current="page">일반</a>' in page


def test_모르는_수준의_교육자료는_만들지_않는다():
    with pytest.raises(ValueError, match="모르는 관람객 수준"):
        render_handout(_시트(), "유치원", _수준들)


def test_실제_큐시트로_네_수준_교육자료가_만들어진다():
    """데이터 쪽 회귀 — 수준이 빠진 턴이 있으면 KeyError 로 여기서 터진다."""
    from stage.cues import load_cues
    from stage.levels import load_levels

    cues = tuple(load_cues())
    levels = list(load_levels())
    for lv in levels:
        page = render_handout(cues, lv, levels)
        assert page.count("<section ") == len(cues)


# ── 서버: 보조 화면·교육자료 경로 ─────────────────────────────────────


class 가짜감독:
    mode = "podcast"

    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {"cue_id": "01-intro", "cue_index": 0, "cue_count": 2, "state": "listening",
                "speaking_role": None, "question_wait_s": 5.2, "question_wait_total_s": 8.0,
                "mode": "podcast", "show_running": True, "level": "초등", "course": "전체",
                "course_position": [1, 2], "course_cue_ids": None,
                "connected": ["mc", "docent"], "rejected": ["docent"], "standby": [], "solo_role": None}

    def cue_list(self):
        return [{"id": c.id, "title": c.title, "topic": c.topic or c.title} for c in _시트()]

    def cues(self):
        return _시트()

    def level_names(self):
        return list(_수준들)

    def mode_names(self):
        return ["podcast", "solo"]

    def course_names(self):
        return ["전체", "첫큐만"]

    def course_ids(self, name):
        return {"전체": None, "첫큐만": ("01-intro",)}[name]

    def abort(self):
        self.calls.append("abort")

    def next(self):
        self.calls.append("next")


@contextlib.contextmanager
def _served(ds):
    srv = ws_serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.socket.getsockname()[1]
    finally:
        srv.shutdown()
        t.join(timeout=2)


@pytest.fixture
def aud(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><title>조정실</title>", encoding="utf-8")
    hub, d, warned, dispatched = DashboardHub(), 가짜감독(), [], []

    def dispatch(director, cmd, out, camera=None):
        dispatched.append(cmd)

    ds = DashboardServer(hub, d, dispatch=dispatch, page=page, interval=0.05, warn=warned.append)
    with _served(ds) as port:
        yield {"hub": hub, "d": d, "warned": warned, "port": port, "dispatched": dispatched}


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
        return r.status, r.headers["Content-Type"], r.read().decode("utf-8")


def _recv_until(ws, pred, timeout=3.0):
    end = time.monotonic() + timeout
    while True:
        left = end - time.monotonic()
        if left <= 0:
            raise AssertionError("기다리던 메시지가 제한 시간 안에 안 왔다")
        m = json.loads(ws.recv(timeout=left))
        if pred(m):
            return m


def test_보조_화면_페이지를_html_로_준다(aud):
    status, ctype, body = _get(aud["port"], "/audience")
    assert status == 200 and ctype.startswith("text/html")
    assert "/ws/audience" in body


def test_교육자료는_수준을_주면_그_수준으로_안_주면_감독의_지금_수준으로(aud):
    _, ctype, body = _get(aud["port"], "/handout?level=%EC%9D%BC%EB%B0%98")      # 일반
    assert ctype.startswith("text/html") and "일반 첫 설명이에요." in body
    _, _, body = _get(aud["port"], "/handout")
    assert "초등 첫 설명이에요." in body                                          # 스냅샷의 level


def test_모르는_수준의_교육자료는_400으로_거절한다(aud):
    """조용히 기본 수준으로 바꿔 주면 초등 자료를 달라고 한 교사가 일반 자료를 받는다."""
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(aud["port"], "/handout?level=%EC%9C%A0%EC%B9%98%EC%9B%90")           # 유치원
    assert e.value.code == 400


def test_보조_소켓_hello_에는_이력_경고가_없고_허용_칸만_있다(aud):
    aud["hub"].publish("warn", text="[docent] 거부됨 — 운영 비밀")
    aud["hub"].publish("recv", role="mc", type="heard", fields={"text": "관람객 STT 원문"})
    aud["hub"].publish("sent", role="mc", type="say", fields={"cue_id": "01-intro", "seq": 1, "text": "마지막 대사"})
    aud["hub"].publish("sent", role="mc", type="mic", fields={"open": True})
    with connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", open_timeout=3) as ws:
        hello = json.loads(ws.recv(timeout=3))
    assert set(hello) == {"kind", "cues", "say", "snapshot"}
    assert hello["say"] == {"kind": "say", "role": "mc", "text": "마지막 대사", "cue_id": "01-intro"}
    assert hello["cues"][0] == {"id": "01-intro", "title": "체험관 개요"}             # topic(저작 메모) 없음
    assert set(hello["snapshot"]) == set(AUDIENCE_SNAPSHOT_KEYS)                        # connected·rejected 없음
    raw = json.dumps(hello, ensure_ascii=False)
    for leak in ("운영 비밀", "관람객 STT 원문", "rejected", "connected", "저작 메모"):
        assert leak not in raw, leak


def test_보조_소켓은_대사만_흘리고_경고와_마이크는_흘리지_않는다(aud):
    with connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", open_timeout=3) as ws:
        json.loads(ws.recv(timeout=3))                                               # hello
        aud["hub"].publish("warn", text="운영 경고")
        aud["hub"].publish("sent", role="docent", type="mic", fields={"open": False})
        aud["hub"].publish("sent", role="docent", type="say",
                           fields={"cue_id": "01-intro:docent", "seq": 2, "text": "도슨트 대사"})
        got = _recv_until(ws, lambda m: m["kind"] != "snapshot")
        assert got == {"kind": "say", "role": "docent", "text": "도슨트 대사", "cue_id": "01-intro:docent"}
        snap = _recv_until(ws, lambda m: m["kind"] == "snapshot")
        assert set(snap) == {"kind", *AUDIENCE_SNAPSHOT_KEYS}


def test_보조_소켓으로_보낸_명령은_실행되지_않는다(aud):
    """관람객 기기에서 조작하려 해도 감독은 움직이지 않는다 — 한 번 경고만 남긴다."""
    with connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", open_timeout=3) as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "a"}))
        ws.send(json.dumps({"cmd": "n"}))
        time.sleep(0.2)
    assert aud["dispatched"] == [] and aud["d"].calls == []
    assert sum("읽기 전용" in w for w in aud["warned"]) == 1, aud["warned"]


def test_조정실_소켓은_여전히_명령을_받는다(aud):
    """보조 경로를 가르는 분기가 조정실 경로까지 삼키지 않는지 — 같은 서버의 `/ws` 는 그대로다."""
    with connect(f"ws://127.0.0.1:{aud['port']}/ws", open_timeout=3) as ws:
        json.loads(ws.recv(timeout=3))
        ws.send(json.dumps({"cmd": "n"}))
        _recv_until(ws, lambda m: m["kind"] == "command")
    assert aud["dispatched"] == ["n"]


def test_보조_소켓도_다른_사이트의_연결은_거절한다(aud):
    with pytest.raises(InvalidStatus) as e:
        connect(f"ws://127.0.0.1:{aud['port']}/ws/audience", origin="http://evil.example", open_timeout=3)
    assert e.value.response.status_code == 403


# ── 보조 화면 페이지(정적) ────────────────────────────────────────────


def _page():
    return AUDIENCE_PAGE.read_text(encoding="utf-8")


def test_보조_화면은_아무것도_보내지_않는다():
    """읽기 전용 — 명령 문자열도, 소켓 송신도 없다."""
    src = _page()
    assert ".send(" not in src
    assert "cmd" not in src
    assert '"/ws/audience"' in src


def test_보조_화면은_textContent_로만_쓰고_외부_리소스를_안_부른다():
    import re

    src = _page()
    for token in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert token not in src, token
    assert re.findall(r'(?:src|href)\s*=\s*["\']https?://', src) == []
    assert re.search(r"@import", src) is None


def test_보조_화면은_공연이_끝나면_이전_관람객의_자막을_치운다():
    src = _page()
    assert 'if (!solo && s.show_running === false && s.state === "idle" && lines.length) {' in src



def test_교육자료는_코스의_큐만_싣고_수준_링크가_코스를_유지한다(aud):
    """"오늘 들은 이야기" 다 — 하이라이트면 하이라이트 큐만. 수준을 바꿔도 코스가 풀리지 않는다."""
    _, _, body = _get(aud["port"], "/handout?level=%EC%B4%88%EB%93%B1&course=%EC%B2%AB%ED%81%90%EB%A7%8C")
    assert body.count("<section ") == 1 and "체험관 개요" in body
    assert "코스: <strong>첫큐만</strong>" in body
    assert "&course=%EC%B2%AB%ED%81%90%EB%A7%8C" in body                            # 수준 링크가 코스를 유지
    _, _, body = _get(aud["port"], "/handout?level=%EC%B4%88%EB%93%B1")
    assert body.count("<section ") == 2                                               # 스냅샷의 코스(전체)


def test_모르는_코스의_교육자료는_400으로_거절한다(aud):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(aud["port"], "/handout?course=%EB%B0%98%EB%82%98%EC%A0%88")                # 반나절
    assert e.value.code == 400


def test_보조_화면은_코스_안_위치로_번호를_그린다():
    src = _page()
    assert 'pos.textContent = cp[0] ? cp[0] + " / " + cp[1] : "";' in src
