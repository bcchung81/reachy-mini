"""비상 수동 오버라이드.

진행의 정본은 관람객 발화다. 이 콘솔은 **전시장 소음으로 오인식이 나거나
진행이 멈췄을 때 사람이 되돌리기 위한 폴백**이다 — 기본 경로가 아니다.
"""

import threading

from stage.director import Director

HELP = """
  n  다음 큐로   |  p  이전 큐로     |  r  현재 큐 다시  |  s  시작
  a  즉시 중단   |  ?  도움말        |  q  종료
  g <큐id>  그 큐로 이동
  l <수준>  관람객 수준 바꾸기(다음 큐부터)
  m <모드>  운영 모드 바꾸기(podcast/solo)
  z <mc|docent>  대기모드 켜고 끄기
  c <mc|docent>  카메라 스트림 켜고 끄기
"""


def block_forever() -> None:
    """돌아오지 않는다. Ctrl-C(또는 SIGTERM)로만 끝난다."""
    threading.Event().wait()


def run_console(director: Director, read=input, out=print, block=block_forever, camera=None) -> None:
    """콘솔 루프. `read`/`out`/`block` 은 테스트가 주입한다 — 실제 동작을
    시험하려면 `input()` 을 우회할 수 있어야 한다."""
    out(HELP)
    while True:
        try:
            cmd = read("무대감독> ").strip().lower()
        except KeyboardInterrupt:
            return
        except EOFError:
            # **표준입력이 없다고 무대감독을 내리면 안 된다.**
            # `nohup python -m stage &` 처럼 띄우면 첫 input() 이 곧장
            # EOFError 를 내고, 예전에는 그대로 돌아가 `main()` 의 finally 가
            # 서버를 닫았다 — 프로세스가 **아무 말 없이** 끝나고, 로봇들은
            # 영원히 재접속만 시도한다. 콘솔만 없을 뿐 감독은 멀쩡하다.
            out(
                "표준입력이 없다 — 콘솔 없이 계속 돈다(진행은 관람객 발화로). "
                "종료는 Ctrl-C 또는 kill."
            )
            block()
            return
        if cmd in ("q", "quit"):
            return
        if cmd and cmd != "?":
            # **운영자 조작을 로그에 남긴다**(2026-09-24). 치는 글자는 표준입력이라
            # `start` 의 tee 로그(`start-director.log`)에 안 남는다 — 그래서 "IDLE 에서
            # 들린 말 221건" 이 `a` 뒤에 생긴 것인지 로그만으로 가를 수 없었다.
            out(f"[운영] 콘솔 {cmd}")
        try:
            dispatch(director, cmd, out, camera=camera)
        except Exception as exc:  # noqa: BLE001
            # **여기서 예외가 새면 무대감독이 통째로 죽는다.**
            # `__main__.main()` 의 finally 가 서버를 내리기 때문이다. 가장
            # 흔한 경로는 `s` 를 두 번 누르는 것 — "시작됐나? 한 번 더" 는
            # 운영자가 하는 가장 평범한 행동인데, 두 번째 `start()` 가
            # 발화 중이라 `TurnError` 를 던지고 시연이 끝난다.
            # 거절은 알려주되 콘솔은 계속 돈다.
            out(f"  거절됨: {exc}")


def _stop_first(director: Director) -> None:
    """진행 명령(`n`·`p`·`r`·`g`) 앞의 "먼저 멈춘다". **단독 모드에서는 멈추지 않는다.**

    단독에서 이 넷은 감독이 거절한다(`Director._refused_in_solo`). 거절될 명령 때문에
    말하던 것을 끊으면 안 된다 — 4단계에서는 그것이 사회자의 단독 답변이다. `g` 가
    모르는 큐에서 멈추지 않는 것과 같은 이유다(이동은 안 됐는데 시연만 멈춘 꼴). `a` 는
    이 헬퍼를 거치지 않으므로 단독에서도 그대로 멈춘다.

    모드를 락 밖에서 읽고 멈춘다 — 그 사이에 다른 화면이 단독으로 바꾸면 전환 직후에
    중단이 한 번 더 나가는 틈이 남는다. 운영자 둘이 같은 순간에 눌러야 생기고, 전환이
    방금 멈춘 자리라 끊을 것이 거의 없어 받아들인다.
    """
    if director.mode != "solo":
        director.abort()


def dispatch(director: Director, cmd: str, out, camera=None) -> None:
    """콘솔 명령 하나 — **대시보드도 이 함수를 부른다**, 명령 경로를 하나로 둔다."""
    if cmd == "s":
        director.start()
    elif cmd == "n":
        # 콘솔은 STT 판정기를 거치지 않는다. `on_heard("다음")` 을 흉내내면
        # LISTENING 이 아닐 때(`a` 뒤, 발화 중) 거부된다 — `p`·`r` 과 같은
        # 모양으로 먼저 멈추고 간다(리뷰 A7b). 단독이면 멈추지 않는다(`_stop_first`).
        _stop_first(director)
        director.next()
    elif cmd == "p":
        # 오인식으로 섹션이 넘어가 버렸을 때 되돌리는 유일한 길이다(설계 §7).
        # `r` 와 같은 모양으로 중단부터 한다 — 대개 잘못 넘어간 대사가
        # 흐르는 중에 누르기 때문이다.
        _stop_first(director)
        director.previous()
    elif cmd == "r":
        _stop_first(director)
        director.start()
    elif cmd == "a":
        director.abort()
    elif cmd.startswith("g "):
        # 대시보드 런다운의 이동. `n`·`p`·`r` 과 같은 모양으로 먼저 멈춘다.
        #
        # **단, 아는 큐일 때만 멈춘다.** 무조건 멈추면 말하는 도중의 오타(`g c9`)가
        # 발화를 끊고 IDLE 에 남긴다 — 이동은 안 됐는데 시연만 멈춘 꼴이다.
        # 모르는 id 도 `goto` 에 넘긴다: 경고 문구를 한 곳(`Director.goto`)에만
        # 두기 위해서고, `goto` 가 모르는 id 를 발화 검사보다 먼저 보므로 말하는
        # 중이어도 거절 대신 경고 한 줄로 끝난다. id 확인에 `cue_list()` 를 쓰는
        # 것은 대시보드가 이미 쓰는 공개 조회라 가짜 감독이 새 메서드를 흉내 낼
        # 필요가 없어서다. 아는 큐여도 단독이면 멈추지 않는다(`_stop_first`).
        cue_id = cmd[2:].strip()
        if any(c["id"] == cue_id for c in director.cue_list()):
            _stop_first(director)
        director.goto(cue_id)
    elif cmd.startswith("l "):
        # 관람객 수준(초등/중고등/일반/전문가) — **다음 큐부터** 적용된다. `n`·`g` 와
        # 달리 먼저 멈추지 않는다: 지금 큐는 원래 수준으로 끝까지 가는 것이 사용자
        # 결정이고, 바로 적용하려면 운영자가 이어서 `r` 을 누른다. 이름 검증·경고
        # 문구는 `Director.set_level` 한 곳에만 둔다(`g` 와 같은 이유). 대시보드가
        # 명령을 `.lower()` 해도 한글 수준 이름은 그대로다.
        director.set_level(cmd[2:].strip())
    elif cmd.startswith("m "):
        # 운영 모드(podcast/solo). **여기서 먼저 멈추지 않는다** — 말하던 것을 멈추는 일은
        # 전환이 받아들여졌을 때만 감독이 락 안에서 한다. 여기서 `abort()` 하면 거절될
        # 전환(모르는 이름·사회자 없음·앱이 단독을 모름)도 시연을 끊는다. 이름 검증·
        # 경고 문구는 `Director.set_mode` 한 곳에만 둔다(`g`·`l` 과 같은 이유 — 페이지
        # 로그에 뜨는 문구가 계약이다).
        director.set_mode(cmd[2:].strip())
    elif cmd.startswith("z "):
        # 대기모드(connected-standby) 토글 — 대시보드의 로봇별 스위치와 같은 경로다.
        director.toggle_standby(cmd[2:].strip())
    elif cmd.startswith("c "):
        # 카메라 스트림 토글. `camera` 는 선택 인자다 — 카메라 중계가 없는
        # 감독(아직 안 붙인 배포, 옛 호출부)에서는 조용히 삼키지 않고 안내한다.
        # **실패는 소리 내서 실패한다**(CLAUDE.md) — 안 되는 걸 조용히 무시하면
        # 운영자가 시연장에서 "왜 안 켜지지"를 추적할 방법이 없다.
        if camera is None:
            out("  카메라 기능을 쓸 수 없다(이 감독에 카메라 중계가 없다)")
        else:
            camera.toggle(cmd[2:].strip())
    elif cmd == "?":
        out(HELP)
    elif cmd:
        out(f"모르는 명령: {cmd!r}  — ? 로 도움말")
