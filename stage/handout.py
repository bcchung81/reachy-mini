"""수준별 교육자료 — 오늘 들은 해설을 인쇄용 읽기 자료로 옮긴다(2026-09-25).

**큐시트의 고정 대본만 쓴다.** 해설은 조사 파일로 사실을 검증한 대본이고(교훈 대장 「정해진 해설을 공연 때마다
생성하면…」), 여기서 LLM 으로 요약하면 검증된 문장이 매번 새로 쓰인다 — 교육자료에 환각이 섞이는 것이 가장
나쁘다. 그래서 대화를 **그대로** 옮긴다: 사회자의 여는 말·턴 질문, 그 수준의 도슨트 설명.

싣지 않는 것과 이유:
- 브리프·금지 규칙(`briefs`·`guard`) — 모델에게 주는 내부 지시문이다("인명·연도는 말하지 않는다" 등).
- 한 줄 주제(`topic`) — 일부가 저작 메모다("해설 종료 인사와 되짚기 — 새 정보 없이 닫는다").
- 받아치기(`mc_after`) — "질문 있으세요? '다음'이라고 말해 주세요" 같은 진행 안내라 읽기 자료에 맞지 않는다.

순수 함수다(파일·네트워크 없음) — 대시보드 서버(`stage/dashboard.py`)가 요청마다 부른다. 모든 텍스트는
`html.escape` 를 거친다 — 대본은 사람이 쓰지만 이 페이지는 관람객 기기에서 열릴 수 있다.
"""

import html
import urllib.parse

from stage.cues import Cue

_STYLE = """
  :root { color-scheme: light; }
  body { margin: 0; background: #F5F6F8; color: #1B1F24; word-break: keep-all; overflow-wrap: anywhere;
         font-family: -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; line-height: 1.7; }
  main { max-width: 760px; margin: 0 auto; padding: 24px 16px 64px; }
  header { border-bottom: 2px solid #1B1F24; margin-bottom: 20px; padding-bottom: 12px; }
  h1 { font-size: 26px; margin: 0 0 6px; }
  .sub { color: #56606B; font-size: 14px; margin: 0; }
  nav { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 14px; }
  nav a { color: #0B63B6; text-decoration: none; padding: 4px 10px; border: 1px solid #C9D1DA;
          border-radius: 999px; background: #fff; }
  nav a.on { background: #1B1F24; border-color: #1B1F24; color: #fff; }
  nav button { margin-left: auto; font: inherit; padding: 6px 14px; border-radius: 6px;
               border: 1px solid #1B1F24; background: #fff; cursor: pointer; }
  section { background: #fff; border: 1px solid #DDE2E8; border-radius: 10px;
            padding: 16px 18px; margin: 0 0 14px; break-inside: avoid; }
  h2 { font-size: 19px; margin: 0 0 10px; }
  h2 .num { color: #0B63B6; margin-right: 8px; font-variant-numeric: tabular-nums; }
  /* 이름표 옆에 글을 붙이고 둘째 줄부터도 그 자리에서 시작한다(걸친 들여쓰기) — 긴 설명이 이름표 밑으로 파고들면
     누가 한 말인지 한눈에 안 들어온다. 한국어는 낱말 중간에서 줄을 바꾸지 않는다(keep-all). */
  p.line { margin: 6px 0; display: flex; gap: 8px; align-items: baseline; }
  .who { flex: 0 0 auto; min-width: 3.4em; font-weight: 700; font-size: 13px;
         padding: 1px 8px; border-radius: 999px; text-align: center; }
  .say { flex: 1; min-width: 0; }
  .mc .who { background: #E3F4F8; color: #0A6F84; }
  .docent .who { background: #FFF1DE; color: #9A5B00; }
  footer { color: #56606B; font-size: 13px; margin-top: 24px; }
  @media print {
    body { background: #fff; }
    nav { display: none; }
    section { border: none; border-bottom: 1px solid #DDE2E8; border-radius: 0; padding: 10px 0; }
  }
"""


def _line(who_class: str, who: str, text: str) -> str:
    return (
        f'<p class="line {who_class}"><span class="who">{html.escape(who)}</span>'
        f'<span class="say">{html.escape(text)}</span></p>'
    )


def render_handout(cues: tuple[Cue, ...] | list[Cue], level: str, levels: list[str],
                   title: str = "전파체험관 해설", course: str | None = None) -> str:
    """교육자료 한 장(HTML). `level` 은 `levels` 안에 있어야 한다 — 없으면 ValueError(부른 쪽이 가른다).

    `cues` 는 부른 쪽이 코스로 거른 것이다(오늘 들은 이야기). `course` 를 주면 머리에 코스를 적고 수준 링크가 그
    코스를 유지한다 — 하이라이트 자료를 보다 수준을 바꿨는데 전체 자료가 나오면 안 된다.
    """
    if level not in levels:
        raise ValueError(f"모르는 관람객 수준이다: {level!r} (고를 수 있는 것: {', '.join(levels)})")
    keep = f"&course={urllib.parse.quote(course)}" if course else ""
    links = []
    for lv in levels:
        on = ' class="on" aria-current="page"' if lv == level else ""
        links.append(f'<a href="/handout?level={urllib.parse.quote(lv)}{keep}"{on}>{html.escape(lv)}</a>')
    nav = "".join(links)
    sections = []
    for i, cue in enumerate(cues, start=1):
        lines = [_line("mc", "사회자", cue.mc)]
        for p in cue.points_for(level):
            if p.ask:
                lines.append(_line("mc", "사회자", p.ask))
            lines.append(_line("docent", "도슨트", p.answer))
        sections.append(
            f'<section id="{html.escape(cue.id)}"><h2><span class="num">{i:02d}</span>'
            f"{html.escape(cue.title)}</h2>{''.join(lines)}</section>"
        )
    return (
        "<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)} — {html.escape(level)} 교육자료</title>"
        f"<style>{_STYLE}</style></head><body><main>"
        f"<header><h1>{html.escape(title)} — 오늘 들은 이야기</h1>"
        f'<p class="sub">관람객 수준: <strong>{html.escape(level)}</strong>'
        + (f" · 코스: <strong>{html.escape(course)}</strong>" if course else "")
        + " · 사회자와 도슨트 로봇이 나눈 해설을 그대로 옮겼습니다.</p>"
        f'<nav aria-label="관람객 수준">{nav}<button type="button" onclick="window.print()">인쇄하기</button></nav>'
        "</header>"
        f"{''.join(sections)}"
        "<footer>이 자료는 체험관 해설 대본(사실 확인을 거친 고정 대본)에서 옮겼습니다. "
        "관람 중 나눈 질문과 답은 담기지 않습니다.</footer>"
        "</main></body></html>\n"
    )
