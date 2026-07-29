"""사용자 발화 → 감정 범주 → 모션 재생. STT 직후 LLM을 기다리지 않고 즉시 반응한다.

classify()는 교체 지점이다 — 시그니처(str -> str)만 지키면
임베딩·소형 분류기로 통째로 갈아끼울 수 있다.
"""

import random
import threading

# 이름은 전부 pollen-robotics/reachy-mini-emotions-library 실측(85개)에서 확인함
CATEGORY_MOVES: dict[str, list[str]] = {
    "greet": ["welcoming1", "cheerful1"],
    "joy": ["laughing1", "enthusiastic1", "success1"],
    "surprise": ["surprised1", "amazed1"],
    "curious": ["curious1", "inquiring1", "thoughtful1"],
    "no": ["no1", "sad1"],
    "ack": ["yes1", "understanding1", "attentive1"],
}

# 위에서부터 먼저 맞는 규칙이 이긴다 — 인사·감정이 의문사보다 우선
_RULES: list[tuple[str, list[str]]] = [
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
    """감정 모션을 백그라운드 스레드에서 재생한다. 재생 중 요청은 버린다."""

    def __init__(self, mini, moves):
        self._mini = mini
        self._moves = moves  # RecordedMoves
        self._available = set(moves.list_moves())  # 기동 시 1회
        self._busy = threading.Event()

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def play_for(self, category: str) -> str | None:
        """범주에 맞는 모션을 골라 비차단 재생. 시작했으면 모션 이름을 돌려준다."""
        if self._busy.is_set():
            return None
        candidates = [n for n in CATEGORY_MOVES.get(category, []) if n in self._available]
        if not candidates:
            return None
        name = random.choice(candidates)
        move = self._moves.get(name)
        self._busy.set()

        def _run() -> None:
            try:
                self._mini.play_move(move, initial_goto_duration=0.3)
            except Exception:
                pass  # 시연 중 모션 실패로 앱이 죽지 않게
            finally:
                self._busy.clear()

        threading.Thread(target=_run, daemon=True).start()
        return name
