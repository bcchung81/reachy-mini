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


def test_websockets_가_앱_의존성에_선언돼_있다():
    import pathlib
    import tomllib

    p = pathlib.Path(__file__).parent.parent / "apps/voice_chat/pyproject.toml"
    deps = tomllib.loads(p.read_text())["project"]["dependencies"]
    assert any(d.startswith("websockets") for d in deps)
