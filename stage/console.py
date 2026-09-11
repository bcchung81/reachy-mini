"""비상 수동 오버라이드.

진행의 정본은 관람객 발화다. 이 콘솔은 **전시장 소음으로 오인식이 나거나
진행이 멈췄을 때 사람이 되돌리기 위한 폴백**이다 — 기본 경로가 아니다.
"""

from stage.director import Director

HELP = """
  n  다음 큐로   |  r  현재 큐 다시  |  s  시작
  a  즉시 중단   |  ?  도움말        |  q  종료
"""


def run_console(director: Director) -> None:
    print(HELP)
    while True:
        try:
            cmd = input("무대감독> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if cmd in ("q", "quit"):
            return
        if cmd == "s":
            director.start()
        elif cmd == "n":
            director.on_heard("다음")
        elif cmd == "r":
            director.abort()
            director.start()
        elif cmd == "a":
            director.abort()
        elif cmd == "?":
            print(HELP)
        elif cmd:
            print(f"모르는 명령: {cmd!r}  — ? 로 도움말")
