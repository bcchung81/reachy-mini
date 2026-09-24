"""실기 배포 계약 — 시뮬에서는 절대 드러나지 않는 두 가지를 고정한다.

둘 다 "시뮬에서는 잘 돌지만 실기에 올리면 앱이 아예 안 뜨는" 부류라, 문서로만
남기면 다음 사람이 되돌린다. 근거는 SDK 소스이므로 여기서 SDK 를 직접 읽어
대조한다 — SDK 가 규칙을 바꾸면 이 테스트가 먼저 실패해야 한다.
"""

import pathlib
import sys
import tomllib

from packaging.requirements import Requirement

ROOT = pathlib.Path(__file__).parent.parent
APP = ROOT / "apps/voice_chat"
sys.path.insert(0, str(APP / "voice_chat"))


def test_미디어_백엔드를_no_media_로_요청한다():
    """SDK 가 오디오 장치를 쥔 채로 두면 우리 MicCapture 가 같은 장치를 못 연다.

    기본값(None → "default")이면 LOCAL/WEBRTC 백엔드가 떠서 데몬이 마이크를
    점유한다. "no_media" 만이 SDK 에 `release_media()` 를 시켜 장치를 놓게 한다.
    """
    from main import VoiceChat

    assert VoiceChat.request_media_backend == "no_media"


def test_no_media_가_SDK_에서_release_media_로_이어진다():
    """우리가 기대하는 SDK 동작이 실제로 그러한지 소스로 확인한다.

    SDK 가 이 분기의 문자열을 바꾸면(예: "none") 조용히 기본 백엔드로 떨어져
    다시 장치 충돌이 난다 — 그때 여기서 잡는다.
    """
    import inspect

    import reachy_mini.reachy_mini as rm

    src = inspect.getsource(rm.ReachyMini._configure_mediamanager)
    assert 'media_backend.lower() == "no_media"' in src
    assert "self.release_media()" in src


def _deps() -> dict[str, Requirement]:
    data = tomllib.loads((APP / "pyproject.toml").read_text())
    reqs = [Requirement(s) for s in data["project"]["dependencies"]]
    return {r.name.lower(): r for r in reqs}


def test_PyGObject_는_리눅스에서만_선언한다():
    """비-Linux 에서 `gi` 는 reachy-mini 가 끄는 gstreamer-bundle 이 공급한다.

    조건 없이 선언하면 macOS/Windows(Lite 구성)에서 pip 가 PyGObject 소스 빌드로
    들어가 설치가 깨진다.
    """
    r = _deps()["pygobject"]
    assert r.marker is not None, "PyGObject 에 플랫폼 마커가 없다"
    assert r.marker.evaluate({"sys_platform": "linux"}) is True
    assert r.marker.evaluate({"sys_platform": "darwin"}) is False
    assert r.marker.evaluate({"sys_platform": "win32"}) is False


def test_PyGObject_범위가_SDK_핀과_어긋나지_않는다():
    """reachy-mini 가 `<=3.46.0,>=3.42.2` 로 묶어 둔다. 상한이 없으면 충돌한다."""
    from importlib.metadata import requires

    sdk = [
        Requirement(s)
        for s in (requires("reachy-mini") or [])
        if Requirement(s).name.lower() == "pygobject"
    ]
    assert sdk, "reachy-mini 가 PyGObject 를 더 이상 선언하지 않는다 — 우리 선언을 재검토하라"
    ours = _deps()["pygobject"].specifier
    assert str(ours) == str(sdk[0].specifier), (
        f"SDK 핀 {sdk[0].specifier} 과 우리 선언 {ours} 이 어긋난다"
    )


def test_stage_client_는_stage_패키지를_import_하지_않는다():
    """`stage/` 는 노트북에만 있다. 로봇에는 앱만 올라간다.

    여기서 import 하면 실기에서 ModuleNotFoundError 로 죽는다 — 시뮬에서는
    저장소 루트가 경로에 있어 절대 드러나지 않는다.
    """
    import pathlib

    src = (
        pathlib.Path(__file__).parent.parent
        / "apps/voice_chat/voice_chat/stage_client.py"
    ).read_text()
    assert "import stage" not in src
    assert "from stage" not in src


def test_로봇과_감독의_메시지_규약이_같다():
    """`stage_client.py` 는 `stage/protocol.py` 를 import 하지 않는다 —
    로봇에는 `stage/` 가 올라가지 않기 때문이다(위 테스트가 그걸 고정한다).

    대가로 **두 곳이 조용히 어긋날 수 있다.** 한쪽에 메시지를 더하고 다른
    쪽을 잊으면 시연장에서 "감독은 보냈는데 로봇이 무시한다" 가 된다.
    여기서 묶어 둔다.
    """
    import pathlib
    import sys

    root = pathlib.Path(__file__).parent.parent
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "apps/voice_chat/voice_chat"))
    import stage_client
    from stage import protocol

    assert stage_client._ROBOT_MSGS == protocol.ROBOT_MSGS
    assert stage_client._DIRECTOR_MSGS == protocol.DIRECTOR_MSGS


def test_websockets_하한이_recv_타임아웃을_보장한다():
    """`stage_client.run()` 은 `ws.recv(timeout=...)` 에 기대고 있다.

    sync API 의 recv 타임아웃은 **13.0** 에서 들어왔다. 하한이 12 면 로봇에
    12.x 가 깔려도 설치가 통과하고, 그 로봇은 조용한 구간에서 영원히 블록돼
    `should_stop()` 을 다시 보지 못한다 — 앱이 안 끝나고 데몬의 앱 슬롯이
    반환되지 않는다. 시뮬에는 15.x 가 깔려 있어 절대 드러나지 않는다.
    """
    from packaging.specifiers import SpecifierSet

    spec = _deps()["websockets"].specifier
    assert not spec.contains("12.0"), f"12.x 를 허용한다: {spec}"
    assert spec.contains("13.0"), f"13.0 을 배제한다: {spec}"
    # reachy-mini 가 `websockets<16,>=12` 로 끌어온다 — 상한을 넘기면 충돌한다.
    assert not SpecifierSet(str(spec)).contains("16.0"), f"상한이 없다: {spec}"


def test_recv_타임아웃이_설치된_websockets_에_실제로_있다():
    """하한을 적어 두는 것과 그 API 가 실재하는 것은 다른 문제다."""
    import inspect

    from websockets.sync.connection import Connection

    assert "timeout" in inspect.signature(Connection.recv).parameters


def _cross_modules():
    """감독 쪽과 로봇 쪽을 **동시에** 들여온다 — 이 저장소에서만 가능한 일이다.
    실기에는 `stage/` 가 올라가지 않으므로 어긋남을 잡을 곳이 여기뿐이다."""
    import pathlib
    import sys

    root = pathlib.Path(__file__).parent.parent
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "apps/voice_chat/voice_chat"))
    import stage_client

    from stage import protocol
    from stage.machine import TurnMachine

    return stage_client, protocol, TurnMachine


def test_감독이_만든_지시가_로봇_핸들러에_그대로_닿는다():
    """**이름 집합만 맞춰서는 부족하다.**

    `mic` 의 `open` 필드를 한쪽에서 이름만 바꿔도 이름 집합 테스트는 통과하고,
    로봇의 `bool(msg.get("open"))` 은 조용히 False 가 된다 — 마이크가 영영
    안 열리는데 로그는 정상이다(리뷰 I7). 그래서 `TurnMachine` 이 실제로
    만드는 Command 를 `protocol.encode()` 로 직렬화해 진짜 `StageClient` 의
    수신 경로에 밀어 넣고, **핸들러가 무엇을 받는지** 본다.
    """
    stage_client, protocol, TurnMachine = _cross_modules()

    m = TurnMachine()
    cmds = m.speak("mc", "c1", "사회자 대사", gaze="partner")
    cmds += m.on_speaking_ended("mc", "c1", seq=m.seq)
    cmds += m.abort()

    got: list[tuple] = []
    client = stage_client.StageClient(
        "ws://x",
        "mc",
        stage_client.Handlers(
            # `emotion` 은 이 테스트의 관심사가 아니다(감독이 싣기 시작하면 값이
            # 생긴다) — 여기서 보는 것은 cue_id·text·seq 의 **필드 이름**이다.
            on_say=lambda cue_id, text, seq, emotion="": got.append(
                ("say", cue_id, text, seq)
            ),
            on_mic=lambda open_: got.append(("mic", open_)),
            on_gaze=lambda target: got.append(("gaze", target)),
            on_abort=lambda: got.append(("abort",)),
            on_camera=lambda viewer, on: None,
            on_rtc=lambda viewer, payload: None,
            on_standby=lambda on: None,
        ),
        warn=lambda msg: got.append(("경고", msg)),
    )
    for cmd in cmds:
        client._on_raw(protocol.encode(cmd.type, **cmd.fields))

    assert got == [
        ("mic", False),                        # 마이크부터 닫는다 (양쪽)
        ("mic", False),
        ("gaze", "partner"),                   # 시선은 **독립 메시지**로 간다
        # `say` 는 발화 번호 `seq` 를 싣는다 — 로봇이 `speaking_started/ended`
        # 에 그대로 되돌려 줘야 감독이 유령 보고를 가른다(리뷰 A2). 한쪽만
        # 이름을 바꾸면 모든 종료 보고가 유령이 되어 시연이 첫 큐에서 멈춘다.
        ("say", "c1", "사회자 대사", 1),
        ("mic", True),                         # 듣기로 넘어가며 리스너만 연다
        # 중단은 **양쪽 마이크를 닫고** 멈춘다(2026-09-24) — 듣는 중에 멈추면 열린
        # 리스너 마이크가 IDLE 내내 남아 STT 가 소음을 계속 올렸다.
        ("mic", False),
        ("mic", False),
        ("abort",),
        ("abort",),
    ], got


def test_로봇이_보낸_보고가_감독의_상태를_실제로_옮긴다():
    """반대 방향. 지금까지 양쪽 모두 **상대의 흉내**하고만 시험됐다 —
    진짜 `StageClient` 가 만든 바이트를 진짜 `StageServer` 가 읽게 한다."""
    import json

    stage_client, protocol, _ = _cross_modules()

    from stage.cues import Cue, CueSheet, Turn
    from stage.machine import State
    from stage.server import StageServer

    # 해설은 고정 대본이다(2026-09-23) — `points` 가 없으면 도슨트가 말할 것이
    # 없어 오프닝 뒤 곧장 관람객 차례로 간다. 이 테스트가 보려는 것은 그 다음
    # 발화가 실제로 나가는지라, 네 수준 모두에 한 줄을 채운다.
    설명 = {lv: "도슨트 대사" for lv in ("초등", "중고등", "일반", "전문가")}
    server = StageServer(
        CueSheet([Cue("c1", "첫째", "사회자 대사", "지시", "partner",
                      points=(Turn("", 설명),))]),
        generate=lambda role, brief, history: "쓰이지 않는다",
        warn=lambda m: None,
    )
    server.director.on_connect("mc")
    server.director.on_connect("docent")
    server.director.start()
    assert server.director.state is State.MC_SPEAKING

    class _CaptureWS:
        def __init__(self):
            self.sent: list[str] = []

        def send(self, raw):
            self.sent.append(raw)

    ws = _CaptureWS()
    client = stage_client.StageClient("ws://x", "mc", None, warn=lambda m: None)
    client._ws = ws
    seq = server.director._machine.seq        # 로봇이 say 에서 받은 그 번호
    client.speaking_started("c1", seq)
    client.speaking_ended("c1", seq)

    for raw in ws.sent:
        server._dispatch("mc", protocol.decode(raw))   # 감독이 읽는 그 경로

    # 사회자 몫이 끝났으므로 도슨트가 받아친다 — 필드 이름이 어긋났다면
    # 유령 메시지로 버려져 여기까지 못 온다.
    assert server.director.state is State.DOCENT_SPEAKING
    assert json.loads(ws.sent[0])["type"] == "speaking_started"


def test_설계_문서의_메시지_필드가_코드와_맞는다():
    """문서와 코드가 어긋나면 다음 사람이 문서를 믿고 한쪽만 고친다 — seq 처럼
    양쪽이 짝인 필드는 문서에도 박아 둔다."""
    doc = (pathlib.Path(__file__).parent.parent
           / "docs/superpowers/specs/2026-09-11-two-robot-mc-docent-design.md").read_text()
    assert "`speaking_started` / `speaking_ended` | `{cue_id, seq}`" in doc
    assert "mc_after" in doc
    assert ":ack" in doc
