"""감독이 로봇에게 보내는 `say` 의 발화 라벨(`cue_id` 필드)을 읽는다.

교육자료·보조 화면이 "지금 어느 큐의 어느 대목을 말하는가"를 알려면 이것이 필요하다. 라벨을 **만드는 쪽**은
`stage/director.py`(`_begin_cue`·`_say_answer`·`_point_label`·`on_speaking_ended`)이고 이 모듈은 **읽는 쪽**이다 —
둘이 어긋나지 않게 `tests/test_say_label.py` 가 실제 감독을 큐시트 끝까지 돌려 박제한다.

  <큐>                 사회자 여는 말                 → open
  <큐>:pt<i>           사회자 질문(i ≥ 1)             → ask<i>
  <큐>:pt<i>:docent    도슨트 설명(마지막이 아닌 것)   → docent<i>
  <큐>:docent          **마지막** 도슨트 설명          → docent<포인트 수 - 1>
  <큐>:after           사회자 받아치기                → after
  <큐>:ack|qa|reask    관람객 질문 흐름               → 같은 이름
  solo:ack|solo:qa     단독 모드(큐시트에 없는 이름)   → 읽지 않는다(None)

마지막 설명이 `:pt<n-1>:docent` 로 오면 규칙이 바뀐 것이라 **모르는 라벨(None)** 로 둔다 — 조용히 엉뚱한 대목으로
읽는 것보다 낫다. None 은 호출부가 "자막만 흘린다" 로 받는다.
"""

import re
from typing import Callable, NamedTuple

# 관람객 질문 흐름의 대목 — 큐의 해설 흐름(open → … → after)이 아니라 곁가지다.
QA_TURNS = frozenset({"ack", "qa", "reask"})

_ASK = re.compile(r"^pt(\d+)$")
_DOCENT = re.compile(r"^pt(\d+):docent$")


class SayRef(NamedTuple):
    cue: str    # 큐 id
    turn: str   # open | ask<i> | docent<i> | after | ack | qa | reask


def parse_say_label(label, points_of: Callable[[str], int | None]) -> SayRef | None:
    """발화 라벨을 `SayRef` 로 푼다. 큐시트에 없거나 규칙에 안 맞으면 None.

    `points_of(큐 id)` 는 그 큐의 포인트 수(없으면 None) — 마지막 도슨트가 `docent<n-1>` 로 풀리려면 n 이 필요하다.
    """
    if not isinstance(label, str) or not label:
        return None
    cue, sep, rest = label.partition(":")
    n = points_of(cue)
    if not n:
        return None
    if not sep:
        return SayRef(cue, "open")
    if rest == "after" or rest in QA_TURNS:
        return SayRef(cue, rest)
    if rest == "docent":
        return SayRef(cue, f"docent{n - 1}")
    m = _ASK.match(rest)
    if m and 0 < int(m.group(1)) < n:
        return SayRef(cue, f"ask{m.group(1)}")
    m = _DOCENT.match(rest)
    if m and int(m.group(1)) < n - 1:
        return SayRef(cue, f"docent{m.group(1)}")
    return None
