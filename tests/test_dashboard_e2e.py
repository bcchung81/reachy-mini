"""대시보드 생산자↔소비자 계약 — 진짜 `StageServer`(그 안의 진짜 `Director`) + 진짜 대시보드.

`tests/test_dashboard.py` 는 전부 **가짜 감독**이고, `tests/test_stage_server.py` 는 허브를
기록용 가짜로 본다. 양쪽이 각자의 흉내하고만 맞춰져 있어, 서버가 싣는 이벤트 모양
(`sent.fields.text`)이나 감독 스냅샷의 키(`speaking_role`)가 바뀌어도 둘 다 통과한다 —
페이지는 그 자리에서 빈 자막·꺼진 탤리로 굳는다(최종 리뷰 Y5). 페이지가 읽는 바로 그
필드를 한 경로로 묶는다: 로봇 hello → 대시보드 `s` → 사회자에게 간 say → 다음 스냅샷.

**LLM 을 부르지 않는 경로다.** `s` 의 첫 사회자 대사는 큐시트 원문이고(캐시 없음 — 감독이
경고하고 원문을 읽는다), 같은 자리에서 띄우는 도슨트 사전 생성은 가짜 `generate` 가 받는다.

**감시 루프(`tick_forever`)는 돌리지 않는다.** 발화 기한이 다음 스냅샷보다 먼저 터져
`speaking_role` 을 되돌리면 결과가 시계에 달린다. sleep 도 없다 — 등록 완료는 로봇이
받는 마이크 재동기화로, 나머지는 `recv(timeout)` 루프로 기다린다.
"""

import contextlib
import json
import pathlib
import sys
import threading
import time

from websockets.sync.client import connect

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage.cues import Cue, CueSheet
from stage.dashboard import start_dashboard
from stage.dashboard_hub import DashboardHub, tee
from stage.server import StageServer


def _recv_until(ws, pred, timeout=3.0) -> dict:
    """조건에 맞는 메시지가 올 때까지 읽는다(맞지 않는 것은 버린다). 남은 시간만큼만
    기다리므로 안 오면 `TimeoutError` 로 끝난다 — pytest 를 붙잡지 않는다."""
    end = time.monotonic() + timeout
    while True:
        left = end - time.monotonic()
        if left <= 0:
            raise AssertionError("기다리던 메시지가 제한 시간 안에 안 왔다")
        m = json.loads(ws.recv(timeout=left))
        if pred(m):
            return m


def test_대시보드의_s_가_진짜_감독을_돌려_사회자_say_와_발화_스냅샷이_페이지에_닿는다():
    hub = DashboardHub()
    터미널: list[str] = []
    # `main()` 과 같은 배선 — 감독·서버 경고는 터미널+허브, 대시보드 자신의 경고는 따로.
    warn = tee(터미널.append, lambda m: hub.publish("warn", text=m))
    server = StageServer(
        CueSheet([Cue("c1", "첫째", "사회자 여는 대사", "도슨트 지시", "partner")]),
        generate=lambda role, brief, history: "도슨트 해설",
        warn=warn, hub=hub,
    )
    대시보드_경고: list[str] = []

    with contextlib.ExitStack() as 정리:   # 뒤에 등록한 것부터 닫는다 — 클라이언트 → 서버
        robot_srv = server.serve("127.0.0.1", 0)
        t = threading.Thread(target=robot_srv.serve_forever, daemon=True)
        t.start()
        정리.callback(t.join, 2)
        정리.callback(robot_srv.shutdown)
        dash = start_dashboard(hub, server.director, "127.0.0.1", 0, warn=대시보드_경고.append)
        assert dash is not None, 대시보드_경고
        정리.callback(dash.shutdown)
        rport = robot_srv.socket.getsockname()[1]
        dport = dash.socket.getsockname()[1]

        robot = 정리.enter_context(connect(f"ws://127.0.0.1:{rport}", open_timeout=3))
        robot.send(json.dumps({"type": "hello", "role": "mc", "unit_id": None, "version": "1.9.0"}))
        # 동기화 점: 감독은 등록(`Director.on_connect`)의 락 안에서 마이크 재동기화를 보낸다.
        # 이것이 왔으면 `connected` 에 mc 가 있다 — sleep 없이 `s` 를 눌러도 된다.
        assert json.loads(robot.recv(timeout=3)) == {"type": "mic", "open": False}

        # 브라우저처럼 Origin 을 붙인다 — 실제 페이지가 타는 `_check_origin` 경로 그대로.
        page = 정리.enter_context(connect(
            f"ws://127.0.0.1:{dport}/ws", origin=f"http://127.0.0.1:{dport}", open_timeout=3,
        ))
        hello = json.loads(page.recv(timeout=3))
        assert hello["kind"] == "hello"
        assert hello["cues"] == [{"id": "c1", "title": "첫째", "topic": "첫째"}]
        # 전제: 누르기 **전에는** 아무도 말하지 않는다. 이것이 없으면 아래 "mc" 단언이
        # 처음부터 참인 공허한 테스트일 수 있다.
        pre = hello["snapshot"]
        assert (pre["state"], pre["speaking_role"], pre["connected"]) == ("idle", None, ["mc"])

        page.send(json.dumps({"cmd": "s"}))
        said = _recv_until(
            page, lambda m: m["kind"] == "sent" and m["role"] == "mc" and m["type"] == "say"
        )
        assert said["fields"]["text"] == "사회자 여는 대사"
        # `sent` 뒤의 **첫** 스냅샷. 펌프는 이벤트를 보낸 뒤에야 스냅샷을 읽고, `sent` 는
        # 감독이 상태를 옮긴 뒤 락 안에서 실린다 — 그래서 이 스냅샷은 반드시 발화 중이다.
        snap = _recv_until(page, lambda m: m["kind"] == "snapshot")
        assert (snap["state"], snap["speaking_role"], snap["cue_id"]) == ("mc_speaking", "mc", "c1")

        # 페이지의 자막은 로봇이 실제로 받은 say 와 같은 문장이다.
        got = _recv_until(robot, lambda m: m["type"] == "say")
        assert got["text"] == said["fields"]["text"]

    # 대시보드는 기동 안내 한 줄과 운영자 조작 기록(`[운영] 대시보드 s`, 2026-09-24) 말고는
    # 아무 경고도 안 냈다(송신 실패·거절·큐 넘침 없음). 위의 단언들이 "페이지에 닿았다" 의 짝이다.
    assert len(대시보드_경고) == 2, 대시보드_경고
    assert 대시보드_경고[0].startswith("대시보드 — http://127.0.0.1:"), 대시보드_경고
    assert 대시보드_경고[1] == "[운영] 대시보드 s", 대시보드_경고


def test_대시보드의_수준_버튼이_진짜_감독에서_대기로_보였다가_s_에서_적용된다():
    """관람객 수준 전환의 페이지 계약 — `hello.levels`, `snapshot.level`/`level_pending`,
    명령 `l <수준>`, 그리고 페이지 로그에 남는 경고 두 줄. 페이지가 읽는 바로 그 필드를
    진짜 감독에서 뽑는다(가짜 감독과만 맞춘 필드 이름은 바뀌어도 아무도 모른다).

    처음 수준은 기본값("일반")이 아닌 "중고등"(함정 ③). 로봇은 붙이지 않는다 — `s` 의
    say 는 "아직 붙지 않았다" 로 버려지지만 큐 시작(= 수준 적용)은 그대로 일어난다."""
    hub = DashboardHub()
    warn = tee(lambda m: None, lambda m: hub.publish("warn", text=m))
    훅: list[str] = []
    server = StageServer(
        CueSheet([Cue("c1", "첫째", "사회자 여는 대사", "도슨트 지시", "partner")]),
        generate=lambda role, brief, history: "도슨트 해설",
        warn=warn, hub=hub, level_name="중고등", docent_min_chars=120,
        level_min_chars={"초등": 70, "중고등": 120, "일반": 180, "전문가": 260},
        on_level_change=훅.append,
    )
    대시보드_경고: list[str] = []

    with contextlib.ExitStack() as 정리:
        dash = start_dashboard(hub, server.director, "127.0.0.1", 0, warn=대시보드_경고.append)
        assert dash is not None, 대시보드_경고
        정리.callback(dash.shutdown)
        dport = dash.socket.getsockname()[1]
        page = 정리.enter_context(connect(
            f"ws://127.0.0.1:{dport}/ws", origin=f"http://127.0.0.1:{dport}", open_timeout=3,
        ))
        hello = json.loads(page.recv(timeout=3))
        assert hello["levels"] == ["초등", "중고등", "일반", "전문가"]
        assert (hello["snapshot"]["level"], hello["snapshot"]["level_pending"]) == ("중고등", None)

        page.send(json.dumps({"cmd": "l 전문가"}))
        w = _recv_until(page, lambda m: m["kind"] == "warn" and "다음 큐부터" in m["text"])
        assert w["text"] == "관람객 수준 중고등 → 전문가 — 다음 큐부터 적용(바로 하려면 r)"
        # 경고는 감독이 대기를 세운 **뒤** 락 안에서 실린다 — 그 뒤 첫 스냅샷은 대기를 보인다.
        snap = _recv_until(page, lambda m: m["kind"] == "snapshot")
        assert (snap["level"], snap["level_pending"]) == ("중고등", "전문가")

        page.send(json.dumps({"cmd": "s"}))
        w = _recv_until(page, lambda m: m["kind"] == "warn" and "바꿨다" in m["text"])
        assert w["text"] == "관람객 수준을 전문가(으)로 바꿨다 — c1 부터"
        snap = _recv_until(page, lambda m: m["kind"] == "snapshot")
        assert (snap["level"], snap["level_pending"]) == ("전문가", None)

    assert 훅 == ["전문가"]


def test_단독을_아는_사회자가_붙으면_대시보드의_m_solo_가_진짜_감독의_모드를_바꾼다():
    """운영 모드의 페이지 계약 — `hello.modes`, `snapshot.mode`/`solo_available`, 명령
    `m solo`, 그리고 페이지 로그의 전환 경고. 로봇 hello 의 `caps` 가 서버 → 감독 →
    스냅샷까지 한 줄로 닿는지를 진짜 서버·감독으로 본다(지금 로봇 앱은 `caps` 를 안
    보낸다 — 4단계 앱을 흉내 낸 가짜 사회자다)."""
    hub = DashboardHub()
    warn = tee(lambda m: None, lambda m: hub.publish("warn", text=m))
    server = StageServer(
        CueSheet([Cue("c1", "첫째", "사회자 여는 대사", "도슨트 지시", "partner")]),
        generate=lambda role, brief, history: "도슨트 해설",
        warn=warn, hub=hub,
    )
    대시보드_경고: list[str] = []

    with contextlib.ExitStack() as 정리:
        robot_srv = server.serve("127.0.0.1", 0)
        t = threading.Thread(target=robot_srv.serve_forever, daemon=True)
        t.start()
        정리.callback(t.join, 2)
        정리.callback(robot_srv.shutdown)
        dash = start_dashboard(hub, server.director, "127.0.0.1", 0, warn=대시보드_경고.append)
        assert dash is not None, 대시보드_경고
        정리.callback(dash.shutdown)
        rport = robot_srv.socket.getsockname()[1]
        dport = dash.socket.getsockname()[1]

        robot = 정리.enter_context(connect(f"ws://127.0.0.1:{rport}", open_timeout=3))
        robot.send(json.dumps({"type": "hello", "role": "mc", "unit_id": None,
                               "version": "2.0.0", "caps": ["solo"]}))
        # 동기화 점 — 등록(`on_connect`)의 락 안에서 오는 마이크 재동기화.
        assert json.loads(robot.recv(timeout=3)) == {"type": "mic", "open": False}

        page = 정리.enter_context(connect(
            f"ws://127.0.0.1:{dport}/ws", origin=f"http://127.0.0.1:{dport}", open_timeout=3,
        ))
        hello = json.loads(page.recv(timeout=3))
        assert hello["modes"] == ["podcast", "solo"]
        pre = hello["snapshot"]
        assert (pre["mode"], pre["solo_available"]) == ("podcast", True)

        page.send(json.dumps({"cmd": "m solo"}))
        w = _recv_until(page, lambda m: m["kind"] == "warn" and "모드를" in m["text"])
        assert w["text"] == "모드를 podcast → solo 로 바꿨다"
        # 경고는 감독이 모드를 바꾼 **뒤** 락 안에서 실린다 — 그 뒤 첫 스냅샷은 단독이다.
        snap = _recv_until(page, lambda m: m["kind"] == "snapshot")
        assert (snap["mode"], snap["state"]) == ("solo", "idle")
        # 전환은 말하던 것을 멈춘다 — 사회자 로봇이 중단 지시를 실제로 받는다.
        assert _recv_until(robot, lambda m: m["type"] == "abort") == {"type": "abort"}


def test_시청자가_붙으면_camera_on이_로봇에_닿고_떠나면_camera_off가_닿는다():
    """설계서 테스트 표의 E2E 줄(`시청자 붙음 → camera on → … → 시청자 닫힘 → camera off`)
    — Task 13 계획에서 빠졌던 자리(I5)를 메운다. `tests/test_stage_server.py`(허브를
    기록용 가짜로 본다)·`tests/test_stage_camera.py`(소켓 없는 순수 로직)는 각자의
    흉내에만 맞춰져 있어, `StageServer`↔`DashboardServer` 조합 순서 버그(C1이 바로 그
    부류다)를 못 잡는다 — 진짜 `StageServer` + 진짜 `DashboardServer` 를 실소켓으로
    엮어 로봇 소켓이 실제로 무엇을 받는지까지 본다.

    **시청자를 로봇보다 먼저 붙인다** — C1 이 실기에서 재현된 바로 그 순서다."""
    hub = DashboardHub()
    warn = tee(lambda m: None, lambda m: hub.publish("warn", text=m))
    server = StageServer(
        CueSheet([Cue("c1", "첫째", "사회자 여는 대사", "도슨트 지시", "partner")]),
        generate=lambda role, brief, history: "도슨트 해설",
        warn=warn, hub=hub,
    )
    대시보드_경고: list[str] = []

    with contextlib.ExitStack() as 정리:
        robot_srv = server.serve("127.0.0.1", 0)
        t = threading.Thread(target=robot_srv.serve_forever, daemon=True)
        t.start()
        정리.callback(t.join, 2)
        정리.callback(robot_srv.shutdown)
        # `camera=server.camera` 를 명시적으로 잇는다 — `stage/__main__.py::main()` 이
        # 실제로 배선하는 것과 같은 인자다(빠뜨리면 대시보드가 시청자를 등록하지 않는다).
        dash = start_dashboard(hub, server.director, "127.0.0.1", 0,
                                camera=server.camera, warn=대시보드_경고.append)
        assert dash is not None, 대시보드_경고
        정리.callback(dash.shutdown)
        rport = robot_srv.socket.getsockname()[1]
        dport = dash.socket.getsockname()[1]

        # 대시보드 시청자(브라우저처럼 Origin 을 붙인다)가 **먼저** 붙는다.
        page = 정리.enter_context(connect(
            f"ws://127.0.0.1:{dport}/ws", origin=f"http://127.0.0.1:{dport}", open_timeout=3,
        ))
        hello = json.loads(page.recv(timeout=3))
        assert hello["kind"] == "hello"
        assert hello["snapshot"]["cameras"]["mc"] == {
            "available": False, "enabled": True, "reason": "OFFLINE",
        }

        # 로봇은 시청자보다 **나중에** hello 한다 — camera 능력을 싣는다.
        robot = 정리.enter_context(connect(f"ws://127.0.0.1:{rport}", open_timeout=3))
        robot.send(json.dumps({"type": "hello", "role": "mc", "unit_id": None,
                               "version": "2.0.0", "caps": ["camera"]}))
        # 등록 직후 마이크 재동기화와 camera{on:true} 두 통이 온다 — 순서는 보장하지
        # 않는다(camera 는 hello 처리 중, mic 는 `on_connect` 에서 나가 서로 다른
        # 자리다). 둘 다 왔는지만 본다.
        msgs = [json.loads(robot.recv(timeout=3)), json.loads(robot.recv(timeout=3))]
        assert {m["type"] for m in msgs} == {"mic", "camera"}
        cam_on = next(m for m in msgs if m["type"] == "camera")
        assert cam_on["on"] is True
        viewer = cam_on["viewer"]

        # 스냅샷도 반영됐다 — 대시보드 펌프가 다음 주기에 다시 읽는다.
        snap = _recv_until(page, lambda m: m["kind"] == "snapshot"
                            and m.get("cameras", {}).get("mc", {}).get("available") is True)
        assert snap["cameras"]["mc"] == {"available": True, "enabled": True, "reason": ""}

        # 시청자가 떠난다 — 로봇은 그 시청자의 camera{on:false} 를 받는다.
        page.close()
        cam_off = json.loads(robot.recv(timeout=3))
        assert cam_off == {"type": "camera", "viewer": viewer, "on": False}
