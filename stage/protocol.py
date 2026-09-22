"""무대감독 ↔ 로봇 메시지. 한 줄 JSON.

메시지는 아래 `KNOWN_MSGS`(= `ROBOT_MSGS` ∪ `DIRECTOR_MSGS`)뿐이고, **모르는 것은
즉시 거절한다.** 조용히 무시하면 프로토콜이 어긋난 채로 계속 돌고, 시연장에서
원인을 찾을 수 없다. 설계 문서 §4 의 표와 짝이다 — 한쪽만 고치지 않는다.

(종류 수를 여기 하드코딩하지 않는다 — 메시지가 늘 때마다 이 주석의 숫자만 바꾸는
것을 잊어 stale 해지는 일이 실제로 있었다, 최종 전체 브랜치 리뷰 M1: "9종" 이 이미
12종이 된 뒤에도 안 고쳐진 채 남아 있었다.)
"""

import json

ROBOT_MSGS = frozenset(
    {"hello", "heard", "speaking_started", "speaking_ended", "error", "rtc"}
)
DIRECTOR_MSGS = frozenset({"say", "mic", "gaze", "abort", "camera", "rtc", "standby"})
KNOWN_MSGS = ROBOT_MSGS | DIRECTOR_MSGS
ROLES = frozenset({"mc", "docent"})


class ProtocolError(ValueError):
    """메시지가 규약에 맞지 않는다."""


def encode(type_: str, **fields) -> str:
    """메시지 한 줄을 만든다.

    `ensure_ascii=False` 는 취향이 아니라 요구사항이다 — 로그를 사람이 읽는다.
    """
    if type_ not in KNOWN_MSGS:
        raise ProtocolError(f"알 수 없는 메시지 종류: {type_!r}")
    return json.dumps({"type": type_, **fields}, ensure_ascii=False)


def decode(raw: str) -> dict:
    """메시지 한 줄을 읽는다. 규약에 안 맞으면 ProtocolError."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"JSON 이 아니다: {raw[:80]!r}") from exc
    if not isinstance(msg, dict):
        raise ProtocolError(f"객체가 아니다: {type(msg).__name__}")
    if msg.get("type") not in KNOWN_MSGS:
        raise ProtocolError(f"알 수 없는 메시지 종류: {msg.get('type')!r}")
    return msg
