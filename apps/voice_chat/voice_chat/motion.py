"""사용자 발화 → 감정 범주 → 모션 재생. STT 직후 LLM을 기다리지 않고 즉시 반응한다.

classify()는 교체 지점이다 — 시그니처(str -> str)만 지키면
임베딩·소형 분류기로 통째로 갈아끼울 수 있다.
"""

import random
import threading
import time

# 이름은 전부 pollen-robotics/reachy-mini-emotions-library 실측(85개)에서 확인함
CATEGORY_MOVES: dict[str, list[str]] = {
    # dance2(17.3s)·dance3(18.4s)는 자체 사운드를 갖는다. `say`로 노래를 흉내내면
    # 가사를 밋밋하게 읽을 뿐이라, 요청을 받으면 이 사운드 있는 모션으로 보여준다.
    "perform": ["dance2", "dance3"],
    "greet": ["welcoming1", "cheerful1"],
    "joy": ["laughing1", "enthusiastic1", "success1"],
    "surprise": ["surprised1", "amazed1"],
    "curious": ["curious1", "inquiring1", "thoughtful1"],
    "no": ["no1", "sad1"],
    "ack": ["yes1", "understanding1", "attentive1"],
}

# 위에서부터 먼저 맞는 규칙이 이긴다 — 인사·감정이 의문사보다 우선
_RULES: list[tuple[str, list[str]]] = [
    # 공연이 최우선 — "재밌는 노래 불러줘"는 joy('재밌')와도 겹치지만 공연이어야 한다
    ("perform", ["노래", "춤", "춰봐", "춰 봐", "불러줘", "불러 줘", "댄스"]),
    ("greet", ["안녕", "반가", "하이", "헬로", "좋은 아침", "잘 잤"]),
    ("joy", ["좋아", "신나", "재밌", "기뻐", "최고", "축하", "고마", "ㅋㅋ", "하하", "웃"]),
    ("surprise", ["헐", "대박", "진짜", "정말", "놀랐", "말도 안", "세상에"]),
    ("no", ["싫어", "아니", "안 돼", "안돼", "못 해", "슬퍼", "우울", "힘들", "짜증"]),
    ("curious", ["뭐", "왜", "어떻게", "궁금", "알려", "설명", "누구", "언제", "어디", "얼마"]),
]


def classify(text: str) -> str:
    for category, keywords in _RULES:
        if any(k in text for k in keywords):
            return category
    if text.rstrip().endswith("?"):
        return "curious"
    return "ack"  # 아무 반응 없는 것이 제일 어색하다 — 가벼운 끄덕임


class MotionPlayer:
    """감정 모션을 백그라운드 스레드에서 재생한다. 재생 중 요청은 버린다.

    모션은 두 종류다.
    · **응답 모션** — 사용자 발화에 대한 반응. 자체 사운드를 내므로 마이크를 막는다.
    · **대기 모션** — 아무도 말을 안 걸 때 혼자 움직이는 것. `sound=False` 로 재생해
      마이크를 막지 않는다. 사용자가 말을 걸면 언제든 밀려난다.
    """

    def __init__(self, mini, moves):
        self._mini = mini
        self._moves = moves  # RecordedMoves
        self._available = set(moves.list_moves())  # 기동 시 1회
        self._busy = threading.Event()
        self._idle = False  # 지금 도는 것이 대기 모션인가

    @property
    def available(self) -> set[str]:
        return self._available

    @property
    def busy(self) -> bool:
        """마이크를 막아야 하는가 — 소리를 내는 응답 모션일 때만 참."""
        return self._busy.is_set() and not self._idle

    @property
    def moving(self) -> bool:
        """어떤 모션이든 돌고 있는가 — 애니메이터가 물러나야 할 때 쓴다."""
        return self._busy.is_set()

    def _wait_free(self, timeout: float) -> bool:
        """취소 요청 후 재생 스레드가 정리될 때까지 기다린다."""
        deadline = time.time() + timeout
        while self._busy.is_set():
            if time.time() >= deadline:
                return False
            time.sleep(0.01)
        return True

    def play_for(self, category: str, force: bool = False) -> str | None:
        """범주에 맞는 모션을 골라 비차단 재생. 시작했으면 모션 이름을 돌려준다.

        force=True 면 진행 중인 모션을 끊고 재생한다. 공연(노래·춤) 요청처럼
        상호작용의 목적 자체인 동작은 겹친다고 버리면 안 된다.
        """
        candidates = [n for n in CATEGORY_MOVES.get(category, []) if n in self._available]
        if not candidates:
            return None
        return self.play(random.choice(candidates), force=force)

    def play(self, name: str, force: bool = False, idle: bool = False) -> str | None:
        """모션 이름을 직접 지정해 재생한다.

        대기 모션(idle=True)은 소리 없이 재생하고 마이크를 막지 않으며,
        응답 모션에 **항상 밀려난다** — 사용자 발화가 혼자 노는 것보다 우선이다.
        """
        if name not in self._available:
            return None
        if self._busy.is_set():
            # 대기 모션은 응답 모션에 자리를 내준다
            if not (force or (self._idle and not idle)):
                return None
            self._mini.cancel_move()
            if not self._wait_free(timeout=1.0):
                return None

        move = self._moves.get(name)
        self._idle = idle
        self._busy.set()

        def _run() -> None:
            try:
                self._mini.play_move(move, initial_goto_duration=0.3, sound=not idle)
            except Exception:
                pass  # 시연 중 모션 실패로 앱이 죽지 않게
            finally:
                self._idle = False
                self._busy.clear()

        threading.Thread(target=_run, daemon=True).start()
        return name
