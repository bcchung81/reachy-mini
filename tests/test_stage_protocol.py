"""무대감독 ↔ 로봇 메시지 규약.

알 수 없는 메시지를 조용히 흘려보내지 않는 것이 이 모듈의 존재 이유다 —
프로토콜이 어긋난 채 도는 것이 시연장에서 가장 찾기 어려운 고장이다.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from stage import protocol


def test_인코딩과_디코딩이_왕복한다():
    raw = protocol.encode("say", cue_id="02-history", text="맥스웰부터 봅니다")
    msg = protocol.decode(raw)
    assert msg == {"type": "say", "cue_id": "02-history", "text": "맥스웰부터 봅니다"}


def test_한글을_이스케이프하지_않는다():
    # 로그를 사람이 읽어야 한다. \uXXXX 로 새어 나가면 시연장에서 못 읽는다.
    raw = protocol.encode("heard", text="다음으로 넘어가요")
    assert "다음으로 넘어가요" in raw
    assert "\\u" not in raw


def test_알_수_없는_메시지_종류는_인코딩에서_막는다():
    with pytest.raises(protocol.ProtocolError, match="알 수 없는"):
        protocol.encode("셀프토크", text="…")


def test_알_수_없는_메시지_종류는_디코딩에서도_막는다():
    with pytest.raises(protocol.ProtocolError, match="알 수 없는"):
        protocol.decode(json.dumps({"type": "셀프토크"}))


def test_JSON_이_아니면_거절한다():
    with pytest.raises(protocol.ProtocolError, match="JSON"):
        protocol.decode("이건 JSON 이 아니다")


def test_객체가_아니면_거절한다():
    with pytest.raises(protocol.ProtocolError, match="객체"):
        protocol.decode("[1, 2, 3]")


def test_type_이_없으면_거절한다():
    with pytest.raises(protocol.ProtocolError, match="알 수 없는"):
        protocol.decode(json.dumps({"text": "type 이 빠졌다"}))


def test_메시지_종류는_12종이다():
    # 규약이 늘어나면 여기서 먼저 깨져야 한다 — 설계 문서 §4·카메라 설계 §프로토콜 표와 짝이다.
    assert protocol.ROBOT_MSGS == frozenset(
        {"hello", "heard", "speaking_started", "speaking_ended", "error", "rtc"}
    )
    assert protocol.DIRECTOR_MSGS == frozenset(
        {"say", "mic", "gaze", "abort", "camera", "rtc", "standby"}
    )
    assert len(protocol.ROBOT_MSGS | protocol.DIRECTOR_MSGS) == 12
    assert protocol.ROLES == {"mc", "docent"}
