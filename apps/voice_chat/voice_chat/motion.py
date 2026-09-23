"""사용자 발화 → 감정 범주 → 모션 재생. STT 직후 LLM을 기다리지 않고 즉시 반응한다.

classify()는 교체 지점이다 — 시그니처(str -> str)만 지키면
임베딩·소형 분류기로 통째로 갈아끼울 수 있다.
"""

import random
import threading

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
    # 아래 둘은 **대본 감정 태그 전용**이다(설계 §12.2). `classify` 의 키워드
    # 규칙은 이 둘을 고르지 않는다 — 추측으로 "뿌듯" 을 맞히는 규칙을 만들면
    # 엉뚱한 문장에서 터진다. 감독이 태그를 실어 줄 때만 쓴다.
    "proud": ["proud1", "proud2", "proud3"],
    "sad": ["sad1", "downcast1"],
}

# ── 대본 감정 태그 (설계 §12.2·§12.5) ──────────────────────────────
#
# 큐시트가 감정을 명시하고 감독이 `say.emotion` 으로 실어 준다. 로봇은 추측
# (`classify`) 대신 그 태그를 쓴다 — 추측은 "타이타닉" 한 단어에 슬픈 모션을
# 거는 식으로 대본과 어긋난다.
#
# **어휘는 두 벌이다.** 감독은 `stage/cues.py::EMOTIONS`, 로봇은 여기. 로봇 앱은
# `stage/` 를 import 할 수 없다(실기에는 앱만 올라간다 —
# `tests/test_deployment_contract.py` 가 그걸 고정한다). 둘이 어긋나면
# `tests/test_emotions.py::test_감정_어휘가_감독과_로봇에서_같다` 가 깨진다.

# '설명' — 모션도 리액션 발성도 내지 않는다(말할 때 driver 의 흔들림만 남는다).
# 해설의 기본 태그라 여기서 모션을 내면 대사마다 몸이 튄다.
NO_MOTION = "none"

EMOTION_CATEGORY: dict[str, str] = {
    "반가움": "greet",
    "기쁨": "joy",
    "놀람": "surprise",
    "궁금": "curious",
    "뿌듯": "proud",
    "끄덕": "ack",
    "아쉬움": "sad",
    "설명": NO_MOTION,
}
STAGE_EMOTIONS: tuple[str, ...] = tuple(EMOTION_CATEGORY)

# "감정이 아예 안 온다" 는 상태(감독이 옛 버전이거나 대본에 태그가 없다)는
# 발화마다 나므로 한 번만 찍는다. 반대로 **모르는 태그**는 그 큐에서만 나므로
# 매번 찍는다 — 한 번만 찍으면 어느 큐의 오타인지 알 수 없다.
_emotion_warned: set[str] = set()


def category_for(emotion: str, warn=print) -> str | None:
    """대본 감정 태그 → 모션 범주. 모르면 `None`(호출부가 키워드 추측으로 내려간다).

    `NO_MOTION` 은 '설명' 이다 — 호출부가 **모션을 아예 걸지 않아야** 한다.
    `None`(모름)과 구별되는 값인 것이 핵심이다: 둘을 같은 값으로 두면 '설명'
    대사가 전부 키워드 추측으로 내려가 해설 내내 모션이 터진다.
    """
    tag = (emotion or "").strip()
    if not tag:
        if "빈태그" not in _emotion_warned:
            _emotion_warned.add("빈태그")
            warn(
                "  [감정 경고] say 에 감정이 실려 오지 않는다 — 키워드 추측"
                "(classify)으로 돈다. 감독이 옛 버전이면 재배포가 필요하다"
            )
        return None
    category = EMOTION_CATEGORY.get(tag)
    if category is None:
        warn(
            f"  [감정 경고] 모르는 감정 태그다: {tag!r} — 키워드 추측으로 돈다 "
            f"(쓸 수 있는 값: {', '.join(STAGE_EMOTIONS)})"
        )
        return None
    return category

# 위에서부터 먼저 맞는 규칙이 이긴다 — 인사·감정이 의문사보다 우선
_RULES: list[tuple[str, list[str]]] = [
    # 공연이 최우선 — "재밌는 노래 불러줘"는 joy('재밌')와도 겹치지만 공연이어야 한다
    ("perform", ["노래", "춤", "춰봐", "춰 봐", "불러줘", "불러 줘", "댄스"]),
    ("greet", ["안녕", "반가", "하이", "헬로", "좋은 아침", "잘 잤"]),
    ("joy", ["좋아", "신나", "재밌", "기뻐", "최고", "축하", "고마", "ㅋㅋ", "하하", "웃"]),
    ("surprise", ["헐", "대박", "진짜", "정말", "놀랐", "말도 안", "세상에"]),
    ("no", ["싫어", "아니", "안 돼", "안돼", "못 해", "슬퍼", "우울", "힘들", "짜증"]),
    # ── 해설 주제(전파체험관) ────────────────────────────────────────────
    # 위치가 중요하다. 기존 규칙보다 **앞**에 두면 "전파에 대한 노래 불러줘"가
    # perform 을 밀어내고, 아래 일반 curious 보다 **뒤**로 밀면 "설명"·"뭐" 같은
    # 흔한 말에 먼저 잡혀 주제 감정이 죽는다. 그래서 정확히 이 자리다.
    ("no", ["타이타닉", "침몰", "조난", "난파"]),
    ("joy", ["마르코니", "세계 최초", "세계최초", "성공", "개관"]),
    ("surprise", ["카폰", "벽돌폰", "삐삐", "아파트 한 채", "아파트 1채", "월면차"]),
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
    """어떤 모션을 걸지 정하고 사운드를 붙인다. **로봇에 직접 쓰지 않는다.**

    쓰는 것은 `driver.RobotDriver` 하나다 — 공식 규칙이 set_target 을 한 곳에서만
    부르라고 하고, 예전 구조(여기서 `play_move` 를 도는 스레드 + 애니메이터 스레드)가
    그걸 어기고 있었다. 여기 남은 것은 **정책**뿐이다: 무엇을 고를지, 무엇이 무엇을
    밀어내는지, 소리를 낼지.

    모션은 두 종류다.
    · **응답 모션** — 사용자 발화에 대한 반응. 자체 발성을 낸다.
    · **대기 모션** — 아무도 말을 안 걸 때 혼자 움직이는 것. 소리를 내지 않고,
      사용자가 말을 걸면 언제든 밀려난다.

    사운드는 `speaker` 를 통해 나간다(`sound.py` 참조). SDK 의 `play_move(sound=True)`
    경로는 `no_media` 에서 무음이 되고, 우리 경로를 타야 에코 프로브와 마이크 게이팅이
    발성을 인지한다.
    """

    def __init__(self, driver, moves, speaker=None):
        self._driver = driver
        self._moves = moves  # RecordedMoves
        self._available = set(moves.list_moves())  # 기동 시 1회
        self._speaker = speaker
        self.user_speaking = False  # Idler 가 본다 — 사용자 발화 중 대기 모션 금지
        # **우선순위 검사와 걸기를 한 덩어리로 묶는다.** 호출자가 둘이다 —
        # 응답 모션(voice_loop 스레드)과 대기 모션(Idler 스레드). 잠금 없이
        # `playing` 검사 후 `driver.play()` 를 부르면, 검사와 걸기 사이에 응답
        # 모션이 시작됐을 때 대기 모션이 그걸 덮는다 — 드라이버를 단일화하며
        # 없앤 바로 그 TOCTOU 를 정책 계층에서 재현하는 꼴이다.
        self._gate = threading.Lock()

    @property
    def available(self) -> set[str]:
        return self._available

    @property
    def moving(self) -> bool:
        """어떤 모션이든 돌고 있는가 — 대기 모션이 끼어들지 판단할 때 쓴다."""
        return self._driver.playing

    def set_user_speaking(self, active: bool) -> None:
        """사용자가 말하는 중인지 전달한다(voice_loop 이 vad.speaking 으로 매 프레임).

        **`vad.active` 를 넘기면 안 된다** — 임계를 한 프레임만 넘어도 참이라
        잡음마다 몸이 굳고 대기 모션이 취소된다(실기 2026-09-08).

        모터 정숙(§12)의 입력이다: sway·호흡이 접히고(driver), 대기 모션은
        돌던 것도 끊는다 — 대기 모션은 어차피 "심심할 때 혼자 노는 것"이라
        사용자 발화보다 우선일 수 없고, 그 서보 소음이 STT 를 오염시킨다.
        응답 모션은 끊지 않는다(로봇 발화 턴과 겹치는 정당한 동작이다).
        """
        was = self.user_speaking
        self.user_speaking = active
        self._driver.set_quiet(active)
        if active and not was and self._driver.playing_idle:
            self._driver.cancel()

    def cancel(self) -> None:
        """모션을 즉시 끊는다. 끼어들기에서 부른다 — 춤은 18초짜리라 안 끊으면
        '그만'이라고 해도 계속 춘다."""
        self._driver.cancel()

    @property
    def driver(self):
        """드라이버 자체. **모션 정책이 아닌 층**을 건드릴 때만 쓴다 — 지금은
        시선(`set_gaze`)뿐이다. 로봇에 쓰는 것은 여전히 드라이버 하나다."""
        return self._driver

    def play_for(
        self, category: str, force: bool = False, idle: bool = False
    ) -> str | None:
        """범주에 맞는 모션을 골라 비차단 재생. 시작했으면 모션 이름을 돌려준다.

        force=True 면 진행 중인 모션을 끊고 재생한다. 공연(노래·춤) 요청처럼
        상호작용의 목적 자체인 동작은 겹친다고 버리면 안 된다.

        idle=True 는 **소리 없는 경로**다(`play` 참조). 듣는 쪽 반응(`react`)이
        여기로 온다 — 상대가 말하는 중이라 발성이 겹치면 그 대사를 덮는다.
        내 차례가 오면 응답 모션이 이것을 밀어내는 것도 같은 이유로 옳다.
        """
        if category == NO_MOTION:
            # '설명' — 모션도 발성도 없다. 경고할 일이 아니라 **정상 경로**다.
            return None
        if category not in CATEGORY_MOVES:
            # 조용히 None 을 주면 "왜 안 움직이지" 를 못 찾는다(리뷰 B1 — 'neutral').
            print(
                f"  [모션 경고] 모션 범주가 아니다: {category!r}"
                f" (쓸 수 있는 것: {', '.join(CATEGORY_MOVES)})",
                flush=True,
            )
            return None
        candidates = [n for n in CATEGORY_MOVES[category] if n in self._available]
        if not candidates:
            return None
        return self.play(
            random.choice(candidates),
            force=force,
            idle=idle,
            full_sound=(category == "perform"),
        )

    def play(
        self,
        name: str,
        force: bool = False,
        idle: bool = False,
        full_sound: bool = False,
    ) -> str | None:
        """모션 이름을 직접 지정해 재생한다.

        대기 모션(idle=True)은 소리 없이 재생하고, 응답 모션에 **항상 밀려난다** —
        사용자 발화가 혼자 노는 것보다 우선이다.

        `full_sound=True` 면 발성을 통째로 재생한다(공연). 그 외에는 앞부분만 쓴다 —
        리액션 발성이 2~12초라 통째로 붙이면 답변이 그만큼 늦는다(`sound.REACTION_S`).
        """
        if name not in self._available:
            return None
        with self._gate:  # 검사와 걸기 사이에 다른 스레드가 끼어들지 못하게
            if self._driver.playing:
                # 대기 모션은 응답 모션에 자리를 내준다
                if not (force or (self._driver.playing_idle and not idle)):
                    return None
            move = self._moves.get(name)
            self._driver.play(move, idle=idle)
        if not idle:
            self._queue_sound(move, full=full_sound)
        return name

    def _queue_sound(self, move, full: bool) -> None:
        """모션 발성을 발화 큐에 넣는다. 실패해도 모션은 돌아야 한다."""
        if self._speaker is None:
            return
        try:
            import sound as sound_mod
            import tts as tts_mod

            pcm = sound_mod.load(
                getattr(move, "sound_path", None), tts_mod.QWEN_PCM_RATE, full=full
            )
            if pcm:
                self._speaker.play_sound(pcm, tts_mod.QWEN_PCM_RATE)
        except Exception as exc:  # noqa: BLE001
            print(f"  [모션 사운드 실패: {type(exc).__name__}: {exc}]", flush=True)
