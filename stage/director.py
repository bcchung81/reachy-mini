"""무대감독 — 턴·대사·마이크를 중계한다.

**전송을 모른다.** `send(role, command)` 콜러블만 받는다. 그래서 종단 흐름
전체가 소켓 없이 테스트된다. WebSocket 배선은 `stage/__main__.py` 가 한다.

LLM 호출을 여기서 독점한다 — 사회자와 도슨트가 **하나의 대화 이력**을 봐야
말이 이어지기 때문이다. TTS 는 로봇에 남는다(목소리가 달라야 한다).
"""

import threading
import time
from typing import Callable

from stage.cues import Cue, CueSheet, is_advance
from stage.machine import SPEAKING, Command, State, TurnError, TurnMachine, coalesce

# 발화 길이 추정치. 실측(2026-09-11, Qwen3-TTS 1.7B CustomVoice, 배속 1.0):
#   34자 → 7.04초 (4.8자/초),  57자 → 10.64초 (5.4자/초),  25자 → 4.00초 (6.3자/초)
# 타임아웃은 **일찍 터지면 안 되므로** 가장 느린 쪽보다 더 보수적으로 잡는다.
CHARS_PER_SEC = 4.0

# **여유분은 합성 지연을 덮는 몫이다 — 재생 길이가 아니다.**
#
# 감독은 로봇이 언제 실제로 소리를 내기 시작했는지 모른다. 로봇은
# `speaker.speak()` 가 **큐에 넣고 돌아온 직후** `speaking_started` 를 보내는데
# (`tts.Speaker.speak` → `_enqueue`, `_speaking` 플래그가 적재 시점에 선다)
# TTS 합성은 그 **뒤**에 일어난다. 그래서 `on_speaking_started` 의 데드라인
# 재설정으로도 합성 지연은 빠지지 않는다 — 이 상수가 그 몫을 통째로 진다.
#
# 예전 값 5.0 은 그 몫을 감당하지 못했다. Qwen3-TTS 첫 합성은 Metal 커널
# JIT 로 **8.5초**가 걸리고(`scripts/warmup.py` 실측), 예열을 건너뛴 첫 큐에서
# 계산하면:
#
#   짧은 전환   12자   예산  8.0초   필요 10.7초   ❌ 터진다
#   사회자 대사  34자   예산 13.5초   필요 14.7초   ❌ 터진다
#   긴 해설     57자   예산 19.2초   필요 18.9초   ✓ (아슬아슬)
#
# 짧은·중간 길이가 대부분이므로 예열을 빠뜨리면 **거의 확실히** 헛타임아웃이
# 난다. 그러면 `force_listening` 이 리스너 마이크를 열고, 직후 로봇이 말을
# 시작해 사회자가 그것을 관람객 발화로 받아적는다 — 불변식 ① 이 막으려던
# 자기목소리 루프가 타임아웃 경로로 되살아난다. 운영자가 기억해야 하는 절차
# (예열)만으로 막기에는 너무 얇은 방어선이다.
#
# 10.0 이면 위 세 경우가 다 통과하지만 여유가 1초뿐이다. **15.0** 은 같은
# 상수 하나짜리 변경이면서 틀릴 여지를 남긴다. 타임아웃이 늦게 터지는 비용은
# "멈춘 것을 늦게 알아챈다" 뿐이고(운영자가 콘솔 `a`/`r` 로 즉시 복구한다),
# 일찍 터지는 비용은 자기목소리 루프다 — 비대칭이 크다.
#
# ⚠️ 이것은 **임시 방어선**이다. 구조적으로 옳은 고침은 로봇이 **첫 오디오
# 시점에** `speaking_started` 를 보내게 해서 이 여유분을 합성 지연이 아니라
# 재생 지터만 덮는 값으로 되돌리는 것이다. 그 선택지와 폐기한 대안(하트비트)
# 은 `docs/real-robot-deployment.md` §15.4 에 적어 두었다.
TIMEOUT_MARGIN_S = 15.0

# 도슨트 대사 생성이 사회자 발화보다 늦어질 때 더 기다려 줄 한도.
GENERATE_GRACE_S = 8.0

# 대화 이력 상한(줄 수). 큐시트가 19섹션이고 그 위에 관람객 질문이 얹히므로
# 상한이 없으면 시연이 진행될수록 프롬프트가 계속 커진다 — TTFT 가 늘고,
# 컨텍스트 창을 넘기면 **앞이 조용히 잘려 나간다**(무엇이 잘렸는지 아무도
# 모른다). 최근 것만 남기는 편이 예측 가능하다. 6턴 남짓이면 "방금 무슨
# 얘기를 했는가" 에는 충분하다 — 그보다 먼 맥락은 `docent_brief` 가 준다.
HISTORY_MAX = 12


class UnitMismatch(RuntimeError):
    """로봇이 신고한 hardware id 가 기대값과 다르다 — 두 대가 뒤바뀌었다."""


class Director:
    def __init__(
        self,
        sheet: CueSheet,
        generate: Callable[[str, list[dict]], str],
        send: Callable[[str, Command], None],
        now: Callable[[], float] = time.monotonic,
        expect_units: dict[str, str] | None = None,
        warn: Callable[[str], None] = print,
    ) -> None:
        self._sheet = sheet
        self._generate = generate
        self._send = send
        self._now = now
        self._expect_units = expect_units or {}
        self._warn = warn

        self._machine = TurnMachine()
        self.history: list[dict] = []

        self._deadline: float | None = None
        # 방금 보낸 `say` 에 준 시간 예산. `speaking_started` 가 오면 그 시점을
        # 기준으로 데드라인을 다시 건다 — `__init__` 아래 on_speaking_started
        # 참고.
        self._speak_budget: float = 0.0
        self._docent_text: str | None = None
        self._docent_ready = threading.Event()
        self._gen_thread: threading.Thread | None = None
        # 세대 번호 — `_begin_cue` 가 부를 때마다 하나씩 올라간다. 늦게 끝난
        # 생성 스레드가 이미 다음 큐로 넘어간 뒤에 결과를 들고 오면, 세대가
        # 안 맞으므로 버린다. 락은 "세대 확인 + 결과 반영"을 한 번에 묶어
        # 그 사이에 `_begin_cue` 가 끼어드는 경합을 막는다.
        self._gen_lock = threading.Lock()
        self._gen_token = 0

        # 진입점 직렬화. `stage/server.py` 가 붙은 뒤로는 `tick()` 이 타이머
        # 스레드에서, 나머지는 커넥션마다 다른 스레드에서 불린다. 이 락이
        # 없으면: tick() 이 데드라인 만료를 판정한 직후(`_deadline`/
        # `speaking_role` 을 아직 안 건드린 시점), 커넥션 스레드가
        # 사회자→도슨트 핸드오프를 통째로 끝내 상태를 옮긴 뒤, tick() 이
        # 이어서 `force_listening()` 을 불러 **도슨트가 말하는 도중** 사회자
        # 마이크를 강제로 연다 — 불변식 ① 위반이다. `force_listening()` 이
        # 부르는 `TurnMachine._to_listening()` 은 현재 상태를 재확인하지
        # 않는 무조건 전이라 이 경합을 스스로 막지 못한다. 게다가 그 강제
        # 전이가 `speaking_role`/`cue_id` 를 리셋해 버려서, 도슨트의 진짜
        # `speaking_ended` 가 나중에 도착하면 유령 메시지로 조용히 버려진다
        # — 도슨트 발화가 타임아웃 보호를 통째로 잃는다.
        #
        # 공개 진입점(`start`/`on_hello`/`on_heard`/`on_speaking_ended`/
        # `on_error`/`tick`/`abort`) 을 전부 이 락으로 직렬화하면 "만료 판정
        # → 강제 전이"가 원자적이 된다 — 세 문제(마이크 오픈, 엉뚱한 로봇을
        # 지목하는 경고, 유령 처리된 진짜 종료)가 한 번에 없어진다. 어느
        # 공개 메서드도 다른 공개 메서드를 부르지 않으므로(전부 `_begin_cue`
        # 등 내부 헬퍼만 거친다) 재진입이 필요 없어 일반 Lock 으로 충분하다.
        #
        # `_speak_docent()` 의 유예시간(`GENERATE_GRACE_S`, 최대 8초) 대기는
        # 이 락을 쥔 채로 일어난다 — 그동안 tick() 은 막힌다. 의도한
        # 동작이다: 사회자→도슨트 핸드오프가 진행 중일 때는 애초에 아무것도
        # 타임아웃돼서는 안 된다. 생성 스레드(`_generate_docent`)는 이 락을
        # 절대 요구하지 않는다 — `_gen_lock` 만 짧게 쥐었다 놓으므로, 진입
        # 락을 쥔 스레드가 생성 완료를 기다리는 동안에도 생성 스레드는
        # 막히지 않는다(교착 없음).
        self._lock = threading.Lock()

        self._connected: set[str] = set()

    # ── 상태 ──────────────────────────────────────────────────────
    @property
    def state(self) -> State:
        return self._machine.state

    @property
    def solo_role(self) -> str | None:
        """한 대만 붙어 있으면 그 역할. 둘 다거나 둘 다 없으면 None."""
        if len(self._connected) == 1:
            return next(iter(self._connected))
        return None

    def on_connect(self, role: str) -> None:
        # `server.py::handler` 가 커넥션 스레드에서 부르는 새 공개 진입점이다.
        # 다른 공개 메서드 안에서(`_who()` 를 통해서든) 이걸 부르지 않으므로
        # `self._lock` 을 또 쥐어도 재진입 걱정이 없다 — `_connected` 를
        # 커넥션 스레드 여럿이 동시에 건드리는 경합만 막으면 된다.
        with self._lock:
            self._connected.add(role)

    def on_disconnect(self, role: str) -> None:
        with self._lock:
            self._connected.discard(role)
            if self.solo_role is not None:
                self._warn(
                    f"[{role}] 이 끊겼다 — 1인 모드로 내려간다. "
                    f"{self.solo_role} 가 양쪽 대사를 읽는다"
                )

    def _who(self, preferred: str) -> str:
        """대사를 읽을 로봇. 1인 모드면 남은 한 대가 전부 읽는다."""
        solo = self.solo_role
        return solo if solo is not None else preferred

    # ── 로봇에게서 오는 것 ────────────────────────────────────────
    def on_hello(self, role: str, unit_id: str | None, version: str) -> None:
        """역할 자기신고. 두 대가 뒤바뀐 채 시연을 시작하는 것을 여기서 막는다."""
        with self._lock:
            expected = self._expect_units.get(role)
            if expected is None:
                return
            if unit_id is None:
                # 시뮬(macOS)에서는 언제나 None 이다 — get_hardware_id() 가 리눅스
                # sysfs 를 읽는다. 여기서 막으면 실기 없이 개발할 수 없다.
                self._warn(f"[{role}] unit_id 가 없다 — 실기라면 확인할 것 (시뮬은 정상)")
                return
            if unit_id != expected:
                raise UnitMismatch(
                    f"{role} 자리에 다른 로봇이 있다: 기대 {expected!r}, 신고 {unit_id!r}. "
                    "사회자와 도슨트가 뒤바뀌었는지 확인한다."
                )

    def on_heard(self, text: str) -> None:
        with self._lock:
            if self._machine.state is not State.LISTENING:
                self._warn(f"발화 중({self._machine.state.value})에 들린 말을 버린다: {text!r}")
                return
            if is_advance(text):
                self._next_locked()
                return
            self._answer(text)

    def on_speaking_started(self, role: str, cue_id: str, seq: int | None) -> None:
        """발화 시작 보고. **데드라인을 여기서 다시 건다.**

        예전에는 `say` 를 보낸 순간부터 시간을 셌다. 그 사이에 든 시간
        (전송, 로봇의 수신 루프가 밀린 시간, 앱이 바쁜 시간)이 전부 발화
        예산을 깎아먹어, 로봇이 **말을 시작하기도 전에** 데드라인이 터질 수
        있었다. 그러면 `force_listening` 이 리스너 마이크를 열고, 그 직후
        로봇이 말을 시작해 사회자가 그것을 관람객 발화로 받아적는다 —
        불변식 ① 이 막으려던 자기목소리 루프가 타임아웃 경로로 되살아난다.

        ⚠️ **남은 구멍**: 로봇은 `speaker.speak()` 가 큐에 넣고 돌아온
        직후에 이것을 보낸다(`main.py` 의 speak_one). TTS 합성 자체는 그
        뒤에 일어나므로, 모델이 차가워 첫 합성이 오래 걸리는 경우는 이
        재설정으로 덮이지 않는다 — `TIMEOUT_MARGIN_S` 가 그 몫이다.
        (`docs/real-robot-deployment.md` 의 2대 구성 잔여 위험)
        """
        with self._lock:
            if not self._machine.is_current(role, cue_id, seq):
                self._warn_ghost("speaking_started", role, cue_id, seq)
                return
            self._deadline = self._now() + self._speak_budget

    def _warn_ghost(self, kind: str, role: str, cue_id: str, seq: int | None) -> None:
        """유령 보고를 **소리 내서** 버린다 — 두 종류의 경고문이 따로 놀지 않게 한 곳에."""
        self._warn(
            f"[{role}] 유령 {kind}({cue_id!r}, seq={seq}) — 지금 말하는 것은 "
            f"{self._machine.speaking_role}/{self._machine.cue_id!r}/seq={self._machine.seq} 다. 버린다"
        )

    def on_speaking_ended(self, role: str, cue_id: str, seq: int | None) -> None:
        with self._lock:
            # 관람객 창구를 열어줄 로봇도 `_who()` 로 정한다 — 1인 모드에서
            # 리스닝으로 넘어갈 때 마이크를 열어야 할 대상은 "사회자" 가
            # 아니라 "남은 한 대" 다. 여기서 고정값을 쓰면(review finding
            # 1인 모드 두 번째 라운드) 사회자가 끊긴 도슨트 1인 모드에서
            # 어느 로봇의 마이크도 열리지 않아 관람객 창구가 아예 없어진다.
            cmds = self._machine.on_speaking_ended(role, cue_id, self._who("mc"), seq=seq)
            if not cmds:
                # 유령 메시지 — 상태를 건드리지 않는다. 하지만 **조용히
                # 버리지도 않는다**: 여기에 걸리는 진짜 종료 보고가 있다면
                # (타임아웃이 먼저 터져 `speaking_role` 을 리셋해 버린 경우가
                # 대표적이다) 그 로봇의 발화가 통째로 타임아웃 보호를 잃은
                # 것이고, 그 사실이 로그에 없으면 추적할 수 없다.
                # seq 불일치도 여기로 온다 — 콘솔 `r` 뒤 중단된 발화의 늦은
                # 보고가 그것이다(리뷰 A2). 그것은 버려지는 것이 맞다.
                self._warn_ghost("speaking_ended", role, cue_id, seq)
                return
            self._deadline = None

            # 큐 id 만으로 "사회자 몫이 방금 끝났다" 를 판정한다 — role 은
            # 안 본다. `_speak_docent` 가 도슨트 몫에는 `f"{cue.id}:docent"`
            # 처럼 구분되는 id 를 쓰므로(§ 리뷰 finding 1), 맨 cue.id 는
            # 두 모드 어디서든 사회자 몫에만 붙는다. 1인 모드에서는 같은
            # 로봇이 두 몫을 연달아 말하므로 role 로는 구분이 안 된다 —
            # role 로 갈랐다가 도슨트 몫이 끝난 뒤에도 다시 도슨트 몫을
            # 트리거해 자기 대사를 무한 반복하는 버그가 났었다.
            cue = self._sheet.current()
            if cue_id == cue.id:
                cmds = cmds + self._speak_docent(cue)
            self._emit(cmds)

    def on_error(self, role: str, where: str, detail: str) -> None:
        with self._lock:
            self._warn(f"[{role}] {where} 에서 오류: {detail}")

    # ── 바깥에서 부르는 것 ────────────────────────────────────────
    def start(self) -> None:
        with self._lock:
            self._begin_cue(self._sheet.current())

    def next(self) -> None:
        """다음 큐로 간다 — 콘솔 `n` 과 관람객의 진행 신호가 **같은 길**을 탄다.

        예전 콘솔 `n` 은 `on_heard("다음")` 을 흉내냈다. 그러면 `is_advance` 의
        조정이 콘솔을 끊고, LISTENING 이 아니면(`a` 로 멈춘 뒤, 발화 중) "발화
        중(idle)에 들린 말을 버린다" 는 엉뚱한 경고와 함께 아무 일도 안 일어난다
        — 운영자가 망가진 섹션을 건너뛸 길이 없었다(리뷰 A7b).
        """
        with self._lock:
            self._next_locked()

    def _next_locked(self) -> None:
        if self._machine.state in SPEAKING:
            raise TurnError(
                f"{self._machine.speaking_role} 가 아직 말하는 중이다 — 먼저 a 로 멈춘다"
            )
        nxt = self._sheet.advance()
        if nxt is None:
            self._warn("마지막 큐다 — 더 진행할 곳이 없다")
            return
        self._begin_cue(nxt)

    def previous(self) -> None:
        """이전 큐로 되돌려 다시 진행한다 — 수동 오버라이드(설계 §7).

        오인식으로 섹션이 넘어가 버렸을 때 되돌리는 유일한 길이다. 콘솔이
        `abort()` 로 먼저 멈춘 뒤 부르므로(대개 잘못 시작된 대사가 흐르는
        중이다) 여기서 상태를 따로 건드리지 않는다 — 발화 중이면 `speak()`
        가 불변식 ② 로 거절하고, 콘솔이 그 거절을 사람에게 보여준다.
        """
        with self._lock:
            prev = self._sheet.back()
            if prev is None:
                self._warn("첫 큐다 — 더 되돌릴 곳이 없다")
                return
            self._begin_cue(prev)

    def tick(self) -> None:
        """타임아웃 감시. 서버 루프가 주기적으로 부른다.

        진입 락 아래에서 판정과 강제 전이를 한 번에 묶는다 — 그렇지 않으면
        판정 직후 다른 스레드가 핸드오프를 끝내고, 그 뒤에야 이 메서드가
        옛 데드라인을 근거로 방금 말을 시작한 로봇의 마이크를 강제로 연다
        (불변식 ① 위반. `__init__` 의 `self._lock` 주석 참고).
        """
        with self._lock:
            if self._deadline is None or self._now() < self._deadline:
                return
            role = self._machine.speaking_role
            self._warn(f"[{role}] 발화 종료 응답이 없다 — 강제로 듣기 상태로 되돌린다")
            self._deadline = None
            self._emit(self._machine.force_listening(self._who("mc")))

    def abort(self) -> None:
        with self._lock:
            self._deadline = None
            self._emit(self._machine.abort())

    # ── 내부 ──────────────────────────────────────────────────────
    def _begin_cue(self, cue: Cue) -> None:
        # **먼저 거절한다.** 발화 중이면 아래 `speak()` 가 TurnError 를 던지는데,
        # 그 전에 이력에 사회자 대사를 넣고 생성 스레드를 갈아끼우면 거절된
        # start() 가 부작용을 남긴다 — 운영자의 `s` 두 번이 이력을 오염시키고
        # 진행 중인 도슨트 생성을 "다음 큐로 넘어갔다" 는 엉뚱한 경고와 함께
        # 버린 뒤 LLM 을 다시 불렀다(리뷰 A7a). 검증 → 부작용 순서다.
        if self._machine.state in SPEAKING:
            raise TurnError(
                f"{self._machine.speaking_role} 가 아직 말하는 중이다"
                f"(큐 {self._machine.cue_id}) — 동시 발화를 막는다"
            )
        # **사회자 대사도 이력에 넣는다 — 생성 스레드를 띄우기 전에.**
        # 설계 §5.2 는 이력이 하나이고 `사회자:`/`도슨트:`/`관람객:` 접두로
        # 구분한다고 못박는다. 사회자 몫을 빠뜨리면 도슨트의 LLM 은 방금
        # 사회자가 뭐라고 넘겼는지 못 본다 — "도슨트, 맥스웰부터 부탁해요"
        # 라는 넘김을 못 보고 해설을 시작하니 말이 이어지지 않는다.
        # 순서가 중요하다: `_generate_docent` 가 `list(self.history)` 를
        # 찍어가므로 스레드를 띄운 **뒤에** 넣으면 이번 큐에는 안 들어간다.
        self._remember(f"사회자: {cue.mc}")

        # **도슨트 대사를 미리 만든다.** 사회자가 고정 대사를 말하는 3~5초 동안
        # 생성이 끝나므로 LLM 지연이 섹션 전환에 실리지 않는다.
        with self._gen_lock:
            self._docent_text = None
            self._docent_ready = threading.Event()
            self._gen_token += 1
            token = self._gen_token
        self._gen_thread = threading.Thread(
            target=self._generate_docent, args=(cue, token), daemon=True
        )
        self._gen_thread.start()
        self._emit(
            self._machine.speak(self._who("mc"), cue.id, cue.mc, gaze=cue.gaze)
        )

    def _generate_docent(self, cue: Cue, token: int) -> None:
        try:
            text = self._generate(cue.docent_brief, list(self.history))
            if not text:
                # 빈 문자열도 "아무 말도 안 하는 것"과 같다 — 조용히 넘기지 않는다.
                self._warn(f"[{cue.id}] 도슨트 대사 생성이 빈 문자열을 내놓았다 — 지시문으로 폴백")
                text = cue.docent_brief
        except Exception as exc:
            # 조용히 벙어리가 되지 않는다. 지시문을 그대로 읽는 것이
            # 아무 말도 안 하는 것보다 낫다.
            self._warn(f"LLM 생성 실패({type(exc).__name__}: {exc}) — 지시문으로 폴백")
            text = cue.docent_brief

        with self._gen_lock:
            if token != self._gen_token:
                # 이 결과가 나올 즈음 이미 다음 큐가 시작됐다. 그대로 반영하면
                # 엉뚱한 큐의 대사가 조용히 새어 들어간다 — 버리고 소리 낸다.
                self._warn(f"[{cue.id}] 도슨트 대사 생성이 늦게 끝나 버려졌다(다음 큐로 이미 넘어갔다)")
                return
            self._docent_text = text
            ready = self._docent_ready
        ready.set()

    def _speak_docent(self, cue: Cue) -> list[Command]:
        if not self._docent_ready.wait(timeout=GENERATE_GRACE_S):
            self._warn("도슨트 대사 생성이 늦다 — 지시문으로 폴백")
            self._docent_text = cue.docent_brief
        text = self._docent_text
        if not text:
            self._warn(f"[{cue.id}] 도슨트 대사가 비어 있다 — 지시문으로 폴백")
            text = cue.docent_brief
        self._remember(f"도슨트: {text}")
        # 사회자 몫과 구분되는 id 를 쓴다 — `_answer` 의 `:qa` 와 같은 이유다.
        # 맨 `cue.id` 는 "사회자 몫이 끝났다" 판정에 `on_speaking_ended` 가
        # 그대로 쓰므로, 도슨트 몫까지 같은 id 를 쓰면(리뷰 finding 1) 1인
        # 모드에서 같은 로봇이 도슨트 몫을 끝낸 speaking_ended 가 다시
        # "사회자 몫이 끝났다" 로 오판돼 도슨트 몫을 무한히 반복한다.
        return self._machine.speak(
            self._who("docent"), f"{cue.id}:docent", text, gaze="audience"
        )

    def _answer(self, question: str) -> None:
        cue = self._sheet.current()
        self._remember(f"관람객: {question}")
        brief = (
            f"관람객이 '{question}' 라고 물었다. 지금 섹션은 '{cue.title}' 이다. "
            "도슨트로서 3문장 이내로 답한다."
        )
        try:
            text = self._generate(brief, list(self.history))
            if not text:
                self._warn("도슨트 응답 생성이 빈 문자열을 내놓았다 — 폴백")
                text = "죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?"
        except Exception as exc:
            self._warn(f"LLM 응답 실패({type(exc).__name__}: {exc}) — 폴백")
            text = "죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?"
        self._remember(f"도슨트: {text}")
        self._emit(
            self._machine.speak(
                self._who("docent"), f"{cue.id}:qa", text, gaze="audience"
            )
        )

    def _remember(self, line: str) -> None:
        """이력에 한 줄 남긴다. **이력은 하나**이고 접두로 화자를 가른다(설계 §5.2).

        상한을 넘으면 앞에서 잘라낸다 — 자르는 쪽을 우리가 정해야 모델의
        컨텍스트 창이 말없이 자르는 것을 막는다.
        """
        role = "user" if line.startswith("관람객:") else "assistant"
        self.history.append({"role": role, "content": line})
        if len(self.history) > HISTORY_MAX:
            del self.history[: len(self.history) - HISTORY_MAX]

    def _emit(self, cmds: list[Command]) -> None:
        for cmd in coalesce(cmds):
            if cmd.type == "say":
                # 예산을 기억해 둔다 — `speaking_started` 가 오면 그 시점부터
                # 다시 센다(on_speaking_started 참고).
                self._speak_budget = self._estimate(cmd.fields["text"])
                self._deadline = self._now() + self._speak_budget
            self._send(cmd.to, cmd)

    @staticmethod
    def _estimate(text: str) -> float:
        return len(text) / CHARS_PER_SEC + TIMEOUT_MARGIN_S
