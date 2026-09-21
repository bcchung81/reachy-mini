"""음성 모드 — VAD 발화 검출 → STT → respond(). half-duplex 게이팅 포함.

하드웨어 AEC 가 없으므로 로봇이 소리를 내는 동안에는 마이크 입력을 통째로 버린다.
버리는 동안 VAD 를 reset() 한다 — 무음 프레임을 먹이면 발화 중이던 상태기계가
hangover 를 채우고 가짜 발화를 뱉는다.

REACHY_BARGE_IN=1 이면 그 게이팅을 풀고 **말하는 중에도 듣는다**(끼어들기).
에코가 없는 환경에서만 켠다 — 헤드셋·이어폰, 또는 AEC 를 붙인 뒤. 스피커로
그냥 켜면 로봇이 자기 목소리에 반응해 스스로 말을 끊는다.
"""

import collections
import os
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from audio_in import EnergyVAD, MicCapture
from stt import transcribe

POST_PLAYBACK_GUARD_S = 0.3  # 재생 종료 후 잔향이 VAD에 잡히지 않게

# ── 끼어들기 ────────────────────────────────────────────────────
BARGE_IN = os.environ.get("REACHY_BARGE_IN", "0").lower() not in ("0", "false", "no")
# **고정 임계는 못 쓴다.** 실측: 사용자 목소리가 마이크에 0.029~0.030 으로 잡히는데
# 고정 임계 0.020 이면 여유가 1.5배뿐이라, 거리·음량·방 상태가 조금만 달라져도
# 걸렸다 안 걸렸다 한다("여러 번 하면 잘 못 듣는다").
#
# 그래서 **잔여 에코 바닥을 계속 추정해 그 배수로 임계를 잡는다.** 로봇이 말하는
# 동안 마이크에 남는 소리(=AEC 가 못 지운 것)가 바닥이고, 사람이 끼어들면 그보다
# 뚜렷하게 커진다. 방·음량·AEC 성능이 달라져도 따라간다.
BARGE_IN_RMS = float(os.environ.get("REACHY_BARGE_IN_RMS", "0.014"))  # 임계 하한
BARGE_IN_FACTOR = float(os.environ.get("REACHY_BARGE_IN_FACTOR", "2.0"))  # 바닥의 몇 배
BARGE_IN_FLOOR_FRAMES = int(os.environ.get("REACHY_BARGE_IN_FLOOR_FRAMES", "100"))  # 3초
# 에코는 정상 신호가 아니다 — 실측에서 로봇 말의 조용한 구간은 0.003, 큰 음절은
# 0.025 였고 사용자 목소리(0.023~0.031)와 겹쳤다. **에너지만으로는 못 가른다.**
#
# 다행히 우리는 지금 무슨 소리를 내보내는지 안다. 마이크에 잡힌 세기를 "그 순간
# 스피커로 나간 세기 x 결합계수"와 비교하면, 예측된 에코보다 뚜렷하게 큰 것만
# 사람 목소리로 본다. 결합계수(방·음량·AEC 성능)는 관측으로 추정한다.
BARGE_IN_ECHO_MARGIN = float(os.environ.get("REACHY_BARGE_IN_ECHO_MARGIN", "1.8"))
# **실패했을 때 이유가 남아야 한다.** 계측을 성공 경로에만 붙였다가, "3~4번 말했는데
# 아무 반응 없음" 로그에 진단 줄이 한 개도 없어서 원인을 추측해야 했다.
# 말하는 동안 이 주기로 상태를 남긴다(0 이면 끔).
BARGE_IN_TRACE_S = float(os.environ.get("REACHY_BARGE_IN_TRACE", "2.0"))

# ── 호출어로 확실하게 끊기 ──────────────────────────────────────
# 에너지만으로는 로봇의 큰 음절과 사람 목소리를 원리적으로 못 가른다(실측에서
# 두 분포가 겹쳤다). **내용으로 가르면** 그 한계가 사라진다.
#
# 그래서 두 갈래로 판정한다:
#   빠른 길 — 에너지가 충분히 크면 그 자리에서 끊는다(지금까지의 동작)
#   확실한 길 — 애매한 세기여도 STT 로 호출어가 확인되면 끊는다(약 0.5초 더 걸림)
#
# 호격 "미니야"를 기본으로 둔다. 로봇은 자기를 부르지 않으므로(대본에도 "리치 미니"
# 뿐이다) **에코가 이 말을 만들어낼 수 없다** — 자기 목소리 오인이 구조적으로 불가능하다.
# 반면 "미니"만 넣으면 대본의 "저는 리치 미니예요"가 그대로 걸린다.
BARGE_IN_WAKE = [
    w.strip()
    for w in os.environ.get("REACHY_BARGE_IN_WAKE", "미니야,그만,잠깐만,스톱").split(",")
    if w.strip()
]
# 호출어 확인은 STT 를 한 번 더 부르므로(약 0.4초) 남발하지 않는다. 다만 **별도
# 스레드**에서 돌린다 — 마이크 루프에서 직접 부르면 그 0.4초 동안 프레임을 못 읽어
# 정작 호출어 뒷부분을 놓친다.
BARGE_IN_WAKE_INTERVAL_S = float(os.environ.get("REACHY_BARGE_IN_WAKE_INTERVAL", "0.5"))
# (REACHY_BARGE_IN_WAKE_MARGIN 은 삭제됐다 — 정의만 있고 판정 어디에도 쓰이지 않는
#  죽은 손잡이였다. 후보 판정은 말소리 프레임 수와 hot 프레임 수로만 한다.)
# **무음을 STT 에 넣지 않는다.** 실측 로그에서 마이크 0.001 짜리 구간을 넘겼더니
# Whisper 가 '조금 조금 조금 …' 을 만들어냈다(환각). 창 안에 말소리가 이만큼은
# 있어야 검사한다 — 30ms 프레임 8개 ≈ 0.24초.
# "미니야" 는 0.5초짜리 짧은 말이다. 8프레임(0.24초)을 요구했더니 정작 호출어가
# 문턱을 못 넘어 검사가 아예 안 돌았다(실측 로그). 4프레임(0.12초)이면 충분하고,
# 무음 환각 방어라는 원래 목적은 그대로 지켜진다.
BARGE_IN_WAKE_MIN_SPEECH = int(os.environ.get("REACHY_BARGE_IN_WAKE_MIN_SPEECH", "4"))
# **창이 짧으면 STT 에 넘기지 않는다.** 'hot 프레임 2개면 확인' 조건이 버퍼가 차기도
# 전에 검사를 발동시켜, 0.1초짜리 조각을 Whisper 에 넘겼다(실측 로그). 그 결과가
# '감사합니다' · '핏뚜어신지' 같은 환각이다. 최소 0.6초는 있어야 말이 된다.
BARGE_IN_WAKE_MIN_WINDOW = int(os.environ.get("REACHY_BARGE_IN_WAKE_MIN_WINDOW", "20"))

# Whisper 가 무음·잡음에서 습관적으로 뱉는 말들. 반복 토막 검사로는 안 걸린다.
# 비교는 `_flatten()` 한 모양(공백·구두점 제거, 소문자)으로 한다 — 항목도 그
# 모양으로 적는다. ~~"감사합니다" 와 "감사합니다." 를 따로 적는다~~ — 구두점을
# 걷고 비교하면서 중복 항목과 "。"/"." 항목이 필요 없어졌다(빈 문자열이 된다).
_WHISPER_FILLER = {
    "감사합니다", "시청해주셔서감사합니다", "구독과좋아요부탁드립니다",
    "thankyou", "thanksforwatching", "you",
    # 실기 2대 리허설(2026-09-21): 마이크 최대 0.002(사실상 무음)에서 나와 관람객
    # 질문으로 처리됐다 — 도슨트가 "다음 영상에서 다시 만나 뵙기를…" 로 답했다.
    # "다음" 이 들어 있지만 진행 키워드 "다음" 자체는 이 목록과 **정확 일치**해야
    # 걸리므로 막히지 않는다(tests/test_stt_filler.py).
    "다음영상에서만나요",
    # 같은 리허설: 한국어 관람객 앞에서 영어 한 단어로 나와 질문이 됐다.
    "come",
}


def _flatten(text: str) -> str:
    """공백·구두점을 걷고 소문자로 — 상용구 비교용. 한글은 `\\w` 라 남는다."""
    return re.sub(r"[\W_]+", "", text.lower())


def _filler(text: str) -> bool:
    """내용 없는 상용구 — 무음에 가까운 입력에서 나오는 환각이다.

    구두점만 남는 전사(`!`, `.`)도 여기서 버린다 — 2026-09-09 실기에서 `!` 가
    그대로 통과해 로봇이 엉뚱한 답을 했다.
    """
    flat = _flatten(text)
    return not flat or flat in _WHISPER_FILLER


def _hallucinated(text: str) -> bool:
    """같은 토막이 계속 반복되면 STT 환각이다 — 무음에 가까운 입력에서 자주 나온다.

    **두 검사를 쓴다.** 종류 수만 세면 꼬리에 잡음 한두 토막이 섞였을 때 빠져나간다 —
    실기 로그가 정확히 그 형태였다: `편집 Sno Sno … Sno`(200회, 2026-09-09).
    한 토막이 전체의 60% 이상을 차지하면 종류가 셋이든 넷이든 환각으로 본다.
    """
    toks = text.split()
    if len(toks) < 6:
        return False
    if len(set(toks)) <= 2:
        return True
    return collections.Counter(toks).most_common(1)[0][1] / len(toks) >= 0.6


def _has_wake(text: str) -> bool:
    """전사에 호출어가 들어 있나 — **토큰 단위**로 본다.

    평탄화한 전체 문자열에서 부분 문자열을 찾으면 안 된다: '그만' 이 '그만큼'
    안에서 걸려, "그만큼 좋아?" 같은 정상 질문이 중단 명령이 된다(리뷰 확인).
    토큰 정확 일치 + 인접 토큰 결합(STT 가 '미니 야' 로 띄우는 경우)으로 잡는다.
    """
    if not text:
        return False
    toks = [t for t in re.split(r"[^\w가-힣]+", text) if t]
    cands = set(toks) | {a + b for a, b in zip(toks, toks[1:])}
    return any(w and "".join(w.split()) in cands for w in BARGE_IN_WAKE)
# **연속이 아니라 비율로 센다.** 사람 말은 음절 사이에서 에너지가 순간적으로 떨어져,
# "N프레임 연속"으로 재면 한 프레임만 내려가도 카운터가 0이 된다 — 실측 로그에서
# 첫 끼어들기만 우연히 통과하고 그 뒤로는 한 번도 성립하지 않았다.
# 최근 WINDOW 프레임 중 FRAMES 개 이상이 임계를 넘으면 인정한다.
# 기침·문 닫는 소리 방어는 그대로다(짧은 충격음은 창을 못 채운다).
BARGE_IN_FRAMES = int(os.environ.get("REACHY_BARGE_IN_FRAMES", "5"))
BARGE_IN_WINDOW = int(os.environ.get("REACHY_BARGE_IN_WINDOW", "9"))  # 9 x 30ms = 270ms
# 끼어들었을 때 그 발화에 **대답까지 할지**. 기본은 안 한다 — 끊기만 하고 다음 질문을
# 기다린다. 끊는 순간의 전사는 잔여 에코가 섞여 엉뚱한 답을 부르기 쉽다(실측:
# "Bye, man." → "안녕히 가세요", "잠깐만." → "네, 잠시 기다리고 있을게요").
BARGE_IN_ANSWER = os.environ.get("REACHY_BARGE_IN_ANSWER", "0").lower() not in ("0", "false", "no")
# 끊은 직후 speaking 플래그가 내려가기까지 잠깐 걸린다(워커가 finally 로 정리).
# 그 틈만 메우면 되므로 **짧게, 그리고 절대 연장하지 않는다.**
# 발화 중이라고 유예를 계속 밀었더니 잔여 에코가 VAD 를 계속 살려 둬서
# 게이팅이 영영 돌아오지 않았고, 로봇이 자기 대본을 통째로 받아 적어
# 스스로에게 다시 대답했다(실측 로그).
BARGE_IN_GRACE_S = float(os.environ.get("REACHY_BARGE_IN_GRACE", "1.0"))
# 끊고 나서 "이 발화는 끼어들 때 낸 소리다"로 볼 수 있는 시간. 이걸 시간 제한 없이
# 두면 **그 뒤의 재질의를 삼킨다**(실측: 끊고 20초 뒤에 한 질문이 통째로 버려졌다).
BARGE_IN_DROP_WINDOW_S = float(os.environ.get("REACHY_BARGE_IN_DROP_WINDOW", "3.0"))


def _strip_wake(text: str) -> str:
    """호출어만 떼어낸 나머지 — 남는 게 있으면 그건 질문이다.

    `_has_wake` 와 **같은 토큰 규칙**을 쓴다. 예전에는 감지는 평탄화 문자열로,
    제거는 원문 `str.replace` 로 해서 규칙이 어긋났다 — STT 가 '미니 야' 로 띄우면
    감지는 되는데 제거가 안 돼 호출어가 질문에 딸려 갔고, '미니 야' 만 말했는데
    rest 가 남아 대기 대신 대답을 했다(리뷰 확인).
    """
    toks = [t for t in re.split(r"[^\w가-힣]+", text) if t]
    wakes = {"".join(w.split()) for w in BARGE_IN_WAKE if w}
    out: list[str] = []
    i = 0
    while i < len(toks):
        if toks[i] in wakes:
            i += 1
        elif i + 1 < len(toks) and toks[i] + toks[i + 1] in wakes:
            i += 2
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))


class EchoCoupling:
    """스피커로 나간 세기 → 마이크에 되돌아오는 세기의 비(결합계수)를 추정한다.

    로봇이 소리를 내는 동안 관측한 `mic / out` 의 **중앙값**이다. 이 값이 있으면
    "지금 나가는 소리라면 마이크에 이 정도 잡혀야 한다"를 예측할 수 있고,
    그보다 뚜렷하게 크면 사람이 말하는 것이다(double-talk).

    중앙값이라 사람이 잠깐 끼어들어도 추정이 흔들리지 않는다.
    """

    def __init__(self, maxlen: int = BARGE_IN_FLOOR_FRAMES):
        self._buf: collections.deque = collections.deque(maxlen=maxlen)

    def observe(self, mic: float, out: float) -> None:
        if out > 0.01:  # 로봇이 실제로 소리를 내는 구간만 본다
            self._buf.append(min(mic / out, 1.0))

    def ratio(self) -> float:
        return float(np.median(self._buf)) if len(self._buf) >= 20 else 0.0

    def predict(self, out: float) -> float:
        """지금 나가는 세기 out 이면 마이크에 이 정도 잡힐 것이다."""
        r = self.ratio()
        return out * r if r else 0.0


class EchoFloor:
    """로봇이 말하는 동안 마이크에 남는 소리(잔여 에코)의 바닥을 추정한다.

    **모든 프레임을 넣되 중앙값을 쓴다.** "임계 아래만 넣는" 방식은 못 쓴다 —
    에코 바닥이 임계 하한보다 높은 방에서는 표본이 하나도 안 쌓여 임계가 영영
    학습되지 않는다(닭-달걀). 중앙값은 소수의 큰 값에 흔들리지 않으므로,
    사람이 잠깐 끼어들어도 바닥 추정은 유지된다.
    """

    def __init__(self, maxlen: int = BARGE_IN_FLOOR_FRAMES):
        self._buf: collections.deque = collections.deque(maxlen=maxlen)

    def threshold(self) -> float:
        if len(self._buf) < 20:  # 표본이 적으면 하한을 그대로 쓴다
            return BARGE_IN_RMS
        floor = float(np.median(self._buf))
        return max(BARGE_IN_RMS, floor * BARGE_IN_FACTOR)

    def observe(self, rms: float) -> None:
        self._buf.append(rms)

    def floor(self) -> float:
        return float(np.median(self._buf)) if self._buf else 0.0

    def reset(self) -> None:
        self._buf.clear()


def _check_wake(audio, hit: threading.Event, busy: threading.Event, speaker=None) -> None:
    """백그라운드에서 호출어를 확인한다. 마이크 루프는 그동안 계속 듣는다."""
    try:
        said = transcribe(audio)
        if _filler(said):
            print(f"  [호출어 확인 — 상용구 무시] '{said.strip()}'", flush=True)
            return
        if _hallucinated(said):
            print(f"  [호출어 확인 — 환각 무시] '{said.strip()[:30]}…'", flush=True)
            return
        # **자기 목소리 방어선은 여기에도 필요하다.** 기본 호출어 넷 중 셋('그만'·
        # '잠깐만'·'스톱')은 로봇 스스로 말할 수 있는 평범한 말이다 — LLM 이
        # "네, 잠깐만요" 라고 답하면 그 잔여 에코가 여기 전사돼 로봇이 자기 말을
        # 끊는다(리뷰 확인). 본 경로(voice_loop 의 said_recently)와 같은 검사를 탄다.
        # (getattr — 테스트 더블이 said_recently 없이도 루프를 돌릴 수 있게)
        check = getattr(speaker, "said_recently", None)
        if check is not None and check(said):
            print(f"  [호출어 확인 — 자기 목소리 무시] '{said.strip()[:30]}'", flush=True)
            return
        if _has_wake(said):
            hit.set()
        elif said.strip():
            print(f"  [호출어 아님] '{said.strip()[:40]}'", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  [호출어 확인 실패: {type(exc).__name__}]", flush=True)
    finally:
        busy.clear()


def voice_loop(llm, speaker, player, respond, should_stop=None, mic_open=None) -> None:
    """`should_stop` 은 매 프레임 확인하는 종료 조건이다(실기의 stop_event.is_set).

    프레임이 30ms 마다 오므로 그 간격으로 반응한다. `respond()` 는 큐에 넣고 곧바로
    반환하므로(재생 완료를 기다리지 않는다) 로봇이 말하는 동안에도 이 루프는 돈다 —
    그래야 끼어들기 판정이 실행된다.

    `mic_open` 은 2대 구성에서 무대감독이 여닫는 마이크 게이트다(None 이면 1대
    모드 — 게이트 없음). **캡처 단에서 막는다** — 닫힌 동안은 프레임을 버리고
    VAD 를 리셋하며 STT 를 부르지 않는다. 결과 단(`main.make_heard_sink`)에서만
    버리면 상대 로봇의 마지막 문장을 VAD 가 담아 두었다가 게이트가 열린 뒤 전사가
    도착해 관람객 발화로 올라간다 — 도슨트가 자기 말에 답하는 무한 루프(리뷰 A1).
    """
    mic, vad = MicCapture(), EnergyVAD()
    print("음성 모드 — 말을 걸어보세요 (Ctrl-C 종료)", flush=True)
    if BARGE_IN:
        print(
            f"끼어들기 켜짐 — 말하는 중에도 듣는다 (임계는 잔여 에코의 {BARGE_IN_FACTOR}배,"
            f" 하한 {BARGE_IN_RMS} / 호출어 {'·'.join(BARGE_IN_WAKE) or '없음'})",
            flush=True,
        )
    guard_until = 0.0
    recent = collections.deque(maxlen=BARGE_IN_WINDOW)  # 최근 프레임이 임계를 넘었나
    loud = collections.deque(maxlen=BARGE_IN_WINDOW)    # 그 프레임 자체(어두 보존용)
    heard: collections.deque = collections.deque(maxlen=50)  # 최근 1.5초(호출어 확인용)
    # 같은 창의 "말소리였나" 플래그. 매 프레임 버퍼 전체를 다시 재면 초당 1,650회의
    # 헛계산이 된다(50프레임 x 33fps) — 프레임당 한 번 판정해 같이 밀어 넣는다.
    heard_speech: collections.deque = collections.deque(maxlen=50)
    wake_checked = 0.0      # 마지막 호출어 확인 시각
    wake_hit = threading.Event()   # 백그라운드 검사가 호출어를 찾으면 켠다
    wake_busy = threading.Event()  # 검사가 도는 중 — 겹쳐 돌리지 않는다
    barge_until = 0.0   # 끊은 직후 게이팅을 풀어 두는 유예 구간
    drop_until = 0.0    # 이 시각까지 끝난 발화는 "끼어들 때 낸 소리"로 본다
    echo = EchoFloor()      # 잔여 에코 바닥 추정 → 적응 임계(하한)
    coupling = EchoCoupling()  # 출력 세기 → 예측 에코 (double-talk 판정)
    traced = 0.0            # 마지막 진단 출력 시각(말하는 중)
    idle_traced = 0.0       # 마지막 진단 출력 시각(듣기만 하는 중)
    idle_peak = 0.0         # 그동안 마이크에 잡힌 최대치
    silent_ticks = 0        # 임계를 못 넘은 대기 구간이 연속 몇 번인가
    near = 0                # 아깝게 못 넘은 횟수(창은 찼는데 개수가 모자람)
    seen: list = []         # 재생 중 관찰한 RMS — 끝날 때 분포를 로그로 남긴다
    frames = mic.frames()
    errors = 0
    try:
        while True:
            try:
                for frame in frames:
                    if should_stop is not None and should_stop():
                        break
                    # 게이팅은 **소리가 나는 동안**이다. 모션 발성도 speaker 큐를
                    # 타므로(`motion.MotionPlayer._queue_sound`) 이 플래그 하나로
                    # 덮인다 — 예전에는 `player.busy` 를 따로 봤는데 그게 두 가지를
                    # 망가뜨렸다: ① 게이팅이 사운드가 아니라 **모션 길이**를 따라가서
                    # 사운드가 더 긴 9개 모션에서 자기 발성 꼬리를 주웠고(최대 +1.43초)
                    # ② 끼어들기를 켜 놔도 모션 구간은 통째로 버려서 춤 18초 동안
                    # 로봇이 완전히 귀머거리였다.
                    busy = speaker.speaking
                    now = time.time()
                    if mic_open is not None and not mic_open():
                        # **감독의 마이크 게이트 — 캡처 단.** 상대 로봇이 말하는
                        # 동안이다. 여기서 리셋해야 그 목소리가 VAD 버퍼에 남지
                        # 않고, 게이트가 열린 뒤 관람객 발화로 튀어나오지 않는다
                        # (리뷰 A1). STT 도 안 부르므로 PC 추론 낭비도 사라진다 —
                        # 예전에는 도슨트 발화 전부를 전사한 뒤 결과만 버렸다.
                        recent.clear()
                        loud.clear()
                        heard.clear()
                        heard_speech.clear()
                        vad.reset()
                        guard_until = now + POST_PLAYBACK_GUARD_S
                        continue
                    # 모터 정숙(§12): 발화를 모으는 동안 sway·호흡·대기 모션을
                    # 접는다 — 서보 소음이 STT 와 소음 바닥 추정을 오염시킨다.
                    # 30ms 마다 bool 하나 넘기는 것이라 비용은 없다.
                    if player is not None:
                        # **`active` 가 아니라 `speaking` 이다.** 잡음 한 프레임에
                        # 몸이 굳고 대기 모션이 취소되면 몸통이 초기 자세에서
                        # 못 벗어난다(실기 2026-09-08). audio_in.speaking 주석 참고.
                        player.set_user_speaking(vad.speaking)
                    if busy and now < barge_until:
                        busy = False  # 방금 끊었다 — 사용자 발화를 받는 중이다
                    if busy:
                        if not BARGE_IN:
                            # 끼어들기를 꺼뒀으면 예전처럼 버린다
                            recent.clear()
                            loud.clear()
                            heard.clear()
                            heard_speech.clear()
                            vad.reset()
                            guard_until = now + POST_PLAYBACK_GUARD_S
                            continue
                        # 말하는 중이지만 듣는다 — 최근 창에서 충분히 자주 크면 끊는다
                        rms = _rms(frame)
                        seen.append(rms)
                        echo.observe(rms)
                        out = speaker.output_level()
                        coupling.observe(rms, out)
                        # 두 관문을 **모두** 넘어야 사람 목소리로 본다.
                        #  ① 배경(잔여 에코 바닥)의 배수 — 조용한 구간에서 새는 소리 방어
                        #  ② 지금 나가는 소리로 예측되는 에코의 배수 — 큰 음절 방어
                        threshold = max(
                            echo.threshold(), coupling.predict(out) * BARGE_IN_ECHO_MARGIN
                        )
                        hot = rms >= threshold
                        recent.append(hot)
                        heard.append(frame)
                        heard_speech.append(rms >= vad.threshold)
                        if hot:
                            loud.append(frame)

                        # ── 확실한 길: 호출어 확인(백그라운드) ────────
                        # 마이크 루프에서 STT 를 직접 부르면 0.4초간 프레임을 못 읽어
                        # 정작 호출어 뒷부분을 놓친다. 그래서 스레드로 던지고 계속 듣는다.
                        speechy = sum(heard_speech)
                        # 에너지 판정이 조금이라도 반응했으면(창에 hot 프레임이 있으면)
                        # 말소리 길이가 짧아도 확인해 본다 — 짧은 호출어를 놓치지 않으려는 것.
                        candidate = speechy >= BARGE_IN_WAKE_MIN_SPEECH or sum(recent) >= 2
                        if (
                            BARGE_IN_WAKE
                            and not wake_busy.is_set()
                            and candidate
                            and len(heard) >= BARGE_IN_WAKE_MIN_WINDOW  # 조각을 넘기지 않는다
                            and now - wake_checked >= BARGE_IN_WAKE_INTERVAL_S
                        ):
                            wake_checked = now
                            wake_busy.set()
                            if BARGE_IN_TRACE_S:
                                print(
                                    f"  [호출어 확인 중] 말소리 {speechy}프레임"
                                    f" ({len(heard) * 0.03:.1f}초 창)",
                                    flush=True,
                                )
                            threading.Thread(
                                target=_check_wake,
                                args=(np.concatenate(list(heard)), wake_hit, wake_busy, speaker),
                                daemon=True,
                            ).start()

                        if wake_hit.is_set():
                            wake_hit.clear()
                            print("  [호출어 감지 — 발화 중단]", flush=True)
                            speaker.stop()
                            if player is not None:
                                player.cancel()  # 춤은 18초짜리다 — 소리만 끊으면 계속 춘다
                            drop_until = time.time() + BARGE_IN_DROP_WINDOW_S
                            guard_until = 0.0
                            barge_until = time.time() + BARGE_IN_GRACE_S
                            recent.clear()
                            loud.clear()
                            heard.clear()
                            heard_speech.clear()
                            vad.reset()
                            continue

                        # 왜 안 걸리는지 말해 준다 — 임계·바닥·예측에코·결합을 그대로 남긴다
                        if BARGE_IN_TRACE_S and now - traced >= BARGE_IN_TRACE_S:
                            traced = now
                            print(
                                f"  [듣는 중] 마이크 {rms:.3f} / 임계 {threshold:.3f}"
                                f" (바닥 {echo.floor():.3f}x{BARGE_IN_FACTOR}"
                                f" | 출력 {out:.3f}x결합 {coupling.ratio():.2f}x{BARGE_IN_ECHO_MARGIN})"
                                f" 창 {sum(recent)}/{BARGE_IN_FRAMES} 말소리 {speechy}",
                                flush=True,
                            )
                        if sum(recent) < BARGE_IN_FRAMES:
                            if sum(recent) >= max(2, BARGE_IN_FRAMES - 2):
                                near += 1
                                if near % 20 == 1:  # 너무 자주 찍지 않는다
                                    # 호출어 검사가 왜 안 돌았는지도 함께 남긴다 — 지난 로그에서
                                    # 이 정보가 없어 "짧은 호출어가 문턱을 못 넘었다"를 놓쳤다.
                                    why = (
                                        "확인 중"
                                        if wake_busy.is_set()
                                        else (
                                            "간격 대기"
                                            if now - wake_checked < BARGE_IN_WAKE_INTERVAL_S
                                            else (
                                                f"창 짧음 {len(heard)}/{BARGE_IN_WAKE_MIN_WINDOW}"
                                                if len(heard) < BARGE_IN_WAKE_MIN_WINDOW
                                                else "말소리 부족"
                                            )
                                        )
                                    )
                                    print(
                                        f"  [아깝게 못 넘음] {sum(recent)}/{BARGE_IN_FRAMES}"
                                        f" — 마이크 {rms:.3f} 임계 {threshold:.3f}"
                                        f" | 호출어 검사: 말소리 {speechy}/{BARGE_IN_WAKE_MIN_SPEECH}"
                                        f" ({why})",
                                        flush=True,
                                    )
                            vad.reset()  # 아직 확신 못 한다 — 발화로 세지 않는다
                            continue
                        # 확정: 말을 끊고, **모아 둔 프레임부터** VAD 에 넣는다.
                        # 이걸 버리면 발화 앞부분이 잘려 STT 가 못 알아듣는다.
                        print(
                            f"  [끼어들기 — 발화 중단] (RMS {rms:.3f} / 임계 {threshold:.3f}"
                            f" — 에코바닥 {echo.floor():.3f}, 출력 {out:.3f}"
                            f" x 결합 {coupling.ratio():.2f})",
                            flush=True,
                        )
                        speaker.stop()
                        if player is not None:
                            player.cancel()  # 소리만 끊고 몸은 계속 추면 안 끊긴 것이다
                        drop_until = 0.0 if BARGE_IN_ANSWER else now + BARGE_IN_DROP_WINDOW_S
                        guard_until = 0.0
                        barge_until = now + BARGE_IN_GRACE_S
                        buffered = list(loud)[:-1] if loud else []
                        recent.clear()
                        loud.clear()
                        heard.clear()
                        heard_speech.clear()
                        if not drop_until:
                            for f in buffered:
                                vad.feed(f)
                        else:
                            vad.reset()
                            continue  # 끊을 때 낸 소리는 안 받는다 — 다음 질문을 기다린다
                    else:
                        # **낡은 호출어 판정을 버린다.** 백그라운드 검사는 재생이
                        # 끝난 뒤에 완료될 수 있다 — 그때 set 된 wake_hit 을 안 지우면
                        # (검사·해제가 busy 분기 안에만 있다) 몇 분 뒤 **다음** 답변이
                        # 시작하자마자 아무도 안 말했는데 끊긴다(리뷰 확인).
                        wake_hit.clear()
                        if seen and BARGE_IN:
                            # 재생이 끝났다 — 그동안 마이크에 뭐가 잡혔는지 분포로 남긴다.
                            # 끼어들기가 안 걸릴 때 임계를 어디로 옮길지 판단할 근거다.
                            a = np.asarray(seen)
                            th = echo.threshold()
                            print(
                                f"  [재생 중 마이크 RMS p50 {np.median(a):.3f}"
                                f" p90 {np.percentile(a, 90):.3f} 최대 {a.max():.3f}"
                                f" / 임계 {th:.3f} 결합 {coupling.ratio():.2f}]",
                                flush=True,
                            )
                            if th > 0.030:
                                # 사람 목소리가 마이크에 잡히는 세기가 실측 0.029~0.035 다.
                                # 임계가 그 근처면 끼어들기가 걸릴 여지가 거의 없다.
                                print(
                                    "  [경고] 잔여 에코가 커서 끼어들기 임계가 사람 목소리 수준까지"
                                    " 올라갔다 — REACHY_TTS_VOLUME=0.6 으로 재생을 낮추거나"
                                    " REACHY_AEC_SUPPRESSION=high 를 써라",
                                    flush=True,
                                )
                            seen = []
                        recent.clear()
                        loud.clear()
                        heard.clear()
                        heard_speech.clear()
                    if now < guard_until:  # 재생 직후 잔향 구간
                        vad.reset()
                        continue

                    # **유휴 구간 심장박동.** 여기가 안 찍히면 마이크 루프가 죽은 것이고,
                    # 찍히는데 최대치가 VAD 임계(0.010) 근처면 목소리가 작아 못 잡는 것이다.
                    # 끼어들기 직후 사용자 질의를 놓쳤을 때 이 둘을 가르는 유일한 단서다.
                    if BARGE_IN_TRACE_S:
                        idle_peak = max(idle_peak, _rms(frame))
                        if now - idle_traced >= BARGE_IN_TRACE_S * 3:
                            if idle_traced:  # 첫 호출은 건너뛴다(기동 직후 소음)
                                quiet = idle_peak < vad.threshold
                                print(
                                    f"  [대기 중] 마이크 최대 {idle_peak:.3f}"
                                    f" / VAD 임계 {vad.threshold:.3f}"
                                    f" {'· 발화 모으는 중' if vad.active else ''}"
                                    # 과길이 강제종료가 늘어난다면 바닥이 임계를 계속
                                    # 넘고 있다는 뜻이다 — 실기에서 이 고리에 걸려
                                    # STT 가 한 번도 안 불린 적이 있다(2026-09-08).
                                    + (
                                        f" · 과길이 강제종료 {vad.overlong_resets}회"
                                        if vad.overlong_resets
                                        else ""
                                    ),
                                    flush=True,
                                )
                                # 계속 임계를 못 넘으면 말을 걸어도 못 알아듣는다.
                                # 그 상태를 조용히 두지 않는다(실측: 원인을 못 찾고 헤맸다).
                                silent_ticks = silent_ticks + 1 if quiet else 0
                                if silent_ticks == 4:
                                    print(
                                        "  [경고] 마이크에 잡히는 소리가 계속 임계 아래다 —"
                                        " REACHY_MIC_GAIN=2.5 로 올리거나 마이크에 더 가까이 말하라",
                                        flush=True,
                                    )
                            idle_traced = now
                            idle_peak = 0.0

                    utterance = vad.feed(frame)
                    if utterance is None:
                        continue

                    t0 = time.time()
                    text = transcribe(utterance)
                    # 사람 발화는 이만큼 길지 않다. 환각 전사가 수백 토막이라
                    # 로그를 통째로 덮어 정작 볼 줄이 밀려난다.
                    shown = text if len(text) <= 200 else text[:200] + "…"
                    print(f"나(STT +{time.time() - t0:.2f}s)> {shown}", flush=True)
                    if not text:
                        continue  # 침묵·잡음 — 다시 듣기

                    # **환각 방어는 여기에도 필요하다.** 예전에는 `_check_wake`
                    # (끼어들기 호출어 확인)에만 걸려 있어서, 실제 대화를 모는 이
                    # 경로는 비어 있지 않기만 하면 무엇이든 받았다. 실기에서
                    # `편집 Sno Sno …`(200회)와 `!` 가 그대로 통과해 로봇이 엉뚱한
                    # 답을 했다(2026-09-09). 잡음에 답하는 것은 침묵보다 나쁘다.
                    if _filler(text):
                        print(f"  [상용구 무시 — 환각] '{text.strip()}'", flush=True)
                        continue
                    if _hallucinated(text):
                        print(f"  [반복 전사 무시 — 환각] '{text.strip()[:30]}…'", flush=True)
                        continue

                    # 끊은 직후의 발화만 "끼어들 때 낸 소리"로 본다. **내용까지 보고 판단한다** —
                    # 호출어를 떼고도 말이 남으면 그건 질문이므로 그대로 받는다
                    # ("미니야 오늘 날씨 어때" → 날씨를 묻는 질문).
                    if drop_until:
                        expired = time.time() > drop_until
                        drop_until = 0.0
                        if not expired:
                            # 호출어 뒤에 말이 이어졌으면 그건 질문이다("미니야 오늘 날씨 어때").
                            # 그 외(호출어만 / 호출어 없이 소리로만 끊은 경우)는 흘려듣는다 —
                            # 끊는 순간의 전사는 잔여 에코가 섞여 엉뚱한 답을 부른다.
                            rest_text = _strip_wake(text) if _has_wake(text) else ""
                            if len(rest_text) >= 2:
                                print(f"  [호출어를 떼고 질문으로 받는다] '{rest_text}'", flush=True)
                                text = rest_text
                            else:
                                print("  [끼어든 말은 흘려듣고 다음 질문을 기다린다]", flush=True)
                                vad.reset()
                                guard_until = time.time() + POST_PLAYBACK_GUARD_S
                                continue
                    # **자기 목소리 방어선.** AEC 가 다 못 지운 에코가 발화로 잡히면
                    # 로봇이 자기 말을 받아 적어 스스로에게 대답한다(실측: 대본을 통째로
                    # 다시 시작했다). 방금 한 말과 닮았으면 버린다 — 에코는 반드시
                    # 우리가 방금 낸 문장이므로, 임계를 넘기 전에 여기서 걸린다.
                    if speaker.said_recently(text):
                        print("  [자기 목소리로 판단 — 무시]", flush=True)
                        vad.reset()
                        guard_until = time.time() + POST_PLAYBACK_GUARD_S
                        continue
                    respond(text, llm, speaker, player)
                    guard_until = time.time() + POST_PLAYBACK_GUARD_S
                break  # 이터레이터가 끝났다(EOS) — 정상 종료
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                # **한 프레임의 사고로 귀를 잃지 않는다.** 예전에는 예외가 새면
                # 루프가 통째로 죽어 앱이 조용히 귀머거리가 됐다(실제로 `_out`
                # deque 경합이 이 자리에서 터질 수 있었다). 알리고 계속 듣는다.
                errors += 1
                if errors <= 3 or errors % 50 == 0:
                    print(
                        f"  [음성 루프 오류 #{errors}: {type(exc).__name__}: {exc}]"
                        " — 상태를 비우고 계속 듣는다",
                        flush=True,
                    )
                vad.reset()
                recent.clear()
                loud.clear()
                heard.clear()
                heard_speech.clear()
                # **제너레이터는 안에서 예외가 나면 끝난다.** 같은 객체로 재진입
                # 하면 곧장 StopIteration 이라 위 for 가 "EOS" 로 조용히 끝났다 —
                # 한 프레임의 사고로 귀를 잃지 않으려던 이 복구가 실제로는
                # 루프를 끝내고 있었다(리뷰 A5b). 새 이터레이터를 만든다.
                frames = mic.frames()
    except KeyboardInterrupt:
        pass
    finally:
        mic.close()
