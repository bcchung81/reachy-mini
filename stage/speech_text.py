"""생성된 대사를 말할 수 있는 모양으로 다듬는다 — 순수 함수만.

LLM 이 낸 텍스트는 두 갈래로 간다: 로봇의 TTS(`say`)와 감독의 대화 이력
(`Director._remember`). `stage/__main__.py::build_generate` 가 생성 직후 여기를
한 번 지나게 해서 두 갈래가 **함께** 깨끗해진다. 한쪽만 고치면 다른 쪽이
다음 생성을 다시 오염시킨다 — 이력에 "사회자: 사회자:" 가 쌓이면 모델이 그
이중 이름표를 따라 말한 것이 실측이다(2026-09-21 실기 리허설, mc:74).
"""

import re

# 이력의 화자 접두(`stage/director.py::SPEAKER_LABEL` + 관람객). **콜론이 붙은
# 경우만** 이름표다 — "사회자님 말씀처럼" 같은 정상 문장은 건드리지 않는다.
# 마크다운 강조(`**사회자:**`)와 전각 콜론도 모델이 실제로 낸다.
_NAMES = r"(?:사회자|도슨트|관람객)"
_LEADING = re.compile(rf"^(?:[*\s]*{_NAMES}[*\s]*[:：])+[*\s]*")
_INNER = re.compile(rf"\**{_NAMES}[*\s]*[:：]")

# 문장 끝: 종결부호 묶음 뒤에 숫자가 오되, **마침표 앞이 ASCII 영숫자일 때만**
# 소수점으로 보고 안 나눈다. `build_generate` 가 절을 `"".join` 하므로 문장
# 사이에 공백이 없다("입니다.이 기관은") — 공백에 기대면 못 나눈다.
#
# ~~옛 규칙은 "종결부호 뒤가 숫자가 아니면" 만 봐서 "2.4GHz"·"12.5센티미터" 같은
# 소수점에서는 안 나눴다.~~ 그런데 이 저장소의 실제 문장은 "…실용화했습니다.
# 1901년에는…" 처럼 **한글 문장 끝 뒤에 연도가 오는 모양**이 훨씬 흔하다
# (`data/cues.yaml` 에 363곳, 대부분 연도) — 옛 규칙은 이 마침표도 소수점으로
# 오인해 두 문장을 하나로 합쳤고, 그 결과 `cap_length` 의 문장 수 상한이 조용히
# 무력화됐다(전체 리뷰 I1). "했습니다.1901년" 은 쪼개고 "2.4GHz"·"V.431"·
# "No.1.5" 는 그대로 두려면, 소수점은 **앞이 숫자/알파벳이고 뒤가 숫자인** 마침표
# 뿐이다 — 한글 뒤에 오는 마침표는 항상 문장 경계다.
_SENT_END = re.compile(r"[.?!…]+(?!(?<=[0-9A-Za-z]\.)[0-9])")


def strip_speaker_labels(text: str) -> tuple[str, bool]:
    """앞머리 이름표를 걷고, 본문 안에 이름표가 또 나오면 그 앞에서 자른다.

    본문 안의 이름표는 **상대 턴을 이어 쓴 것**이다(실측 docent:106 — 도슨트
    한 발화 안에 "…것입니다.사회자: 사회자: …" 로 사회자 반응이 붙었다). 그
    뒤는 이 로봇의 대사가 아니므로 버린다.

    돌려주는 bool 은 "이름표 때문에 바뀌었나" 다 — 앞뒤 공백 차이는 치지 않는다.
    """
    s = text.strip()
    body = _LEADING.sub("", s, count=1)
    m = _INNER.search(body)
    if m:
        body = body[: m.start()]
    body = body.strip()
    return body, body != s


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _SENT_END.finditer(text):
        if text[start : m.end()].strip():
            spans.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def split_sentences(text: str) -> list[str]:
    return [text[a:b].strip() for a, b in _sentence_spans(text)]


def cap_length(text: str, max_sentences: int, max_chars: int) -> tuple[str, bool]:
    """문장 경계에서 분량 상한을 건다. (결과, 잘랐는지).

    프롬프트의 분량 지시만으로는 안 지켜진다 — 실측 도슨트 235~517자(목표
    180~280자), 사회자 147~195자(목표 40~120자). `max_tokens` 는 문장 중간을
    자르므로 상한 역할을 못 한다.

    - 문장을 앞에서부터 담다가 문장 수가 `max_sentences` 에 닿거나 누적 길이가
      `max_chars` 를 넘으면 멈춘다. 길이는 원문 앞에서부터의 글자 수다.
    - **첫 문장은 길어도 통째로 남긴다.** 문장 중간 절단은 TTS 가 말을 뚝 끊어
      조금 긴 것보다 나쁘다.
    - 잘라도 원문의 간격을 그대로 둔다 — 새로 이어 붙이지 않는다.
    """
    s = text.strip()
    spans = _sentence_spans(s)
    if not spans:
        return s, False
    cut_end = spans[0][1]
    kept = 1
    for _, end in spans[1:]:
        if kept >= max_sentences or end > max_chars:
            break
        cut_end = end
        kept += 1
    if kept == len(spans):
        return s, False
    return s[:cut_end].strip(), True
