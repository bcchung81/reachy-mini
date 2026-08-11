"""모션 발성이 우리 재생 경로를 타는지 — E1/E4 의 박제.

SDK 의 `play_move(sound=True)` 는 `media_manager.play_sound()` 를 쓰는데, 우리는
마이크를 직접 열려고 `request_media_backend="no_media"` 를 요청한다. 그러면
`MediaManager.audio` 가 None 이라 **경고 한 줄만 남기고 사운드가 사라진다** —
감정 라이브러리 85개 중 84개, 우리가 쓰는 17개 전부가 사운드를 갖는다.

옮기면 두 가지가 따라온다:
  · 게이팅이 **사운드 길이**를 따라간다. 예전에는 모션 길이를 따라가서, 사운드가
    더 긴 9개 모션에서 마이크가 자기 발성 꼬리를 주웠다(최대 +1.43초).
  · 발성이 에코 프로브·출력 레벨을 타므로 끼어들기가 그 구간에도 판정할 수 있다.
"""

import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import sound as sound_mod  # noqa: E402
import tts as tts_mod  # noqa: E402

RATE = 24000


def _pcm(seconds: float, amp: int = 8000) -> bytes:
    t = np.arange(int(RATE * seconds)) / RATE
    return (np.sin(2 * np.pi * 440 * t) * amp).astype(np.int16).tobytes()


class Captured:
    """`_play_pcm` 을 가로채 실제로 흘러간 청크를 모은다."""

    def __init__(self):
        self.calls: list[tuple[int, list[bytes]]] = []

    def __call__(self, chunks, rate=RATE):
        self.calls.append((rate, list(chunks)))

    @property
    def total(self) -> int:
        return sum(sum(len(c) for c in cs) for _, cs in self.calls)


def _speaker(cap):
    # fallback_cmd 를 줘서 qwen 서버를 찾아가지 않게 한다(사운드 항목은 어차피 안 탄다)
    return tts_mod.Speaker(play_pcm=cap, fallback_cmd=["true"])


def _wait_quiet(sp, timeout=3.0):
    end = time.time() + timeout
    while sp.speaking and time.time() < end:
        time.sleep(0.01)
    return not sp.speaking


# ── 큐 통합 ────────────────────────────────────────────────────


def test_발성이_재생_경로로_흘러간다():
    cap = Captured()
    sp = _speaker(cap)
    pcm = _pcm(0.5)
    sp.play_sound(pcm, RATE)
    assert _wait_quiet(sp), "발성이 끝나지 않았다"
    assert len(cap.calls) == 1
    assert cap.calls[0][0] == RATE
    assert cap.total == len(pcm), "PCM 이 손실 없이 전달돼야 한다"


def test_발성_동안_speaking_이_켜진다():
    """마이크 게이팅이 이 플래그를 본다 — 발성 구간을 정확히 덮어야 한다."""
    cap = Captured()
    sp = _speaker(cap)
    assert sp.speaking is False
    sp.play_sound(_pcm(0.3), RATE)
    assert sp.speaking is True, "적재 즉시 켜져야 한다(소리보다 게이팅이 먼저)"
    assert _wait_quiet(sp)


def test_발성은_청크로_흘러간다():
    """한 덩어리로 쓰면 춤 16.5초 동안 재생 잠금을 쥐어 끼어들기가 못 끊는다."""
    cap = Captured()
    sp = _speaker(cap)
    sp.play_sound(_pcm(2.0), RATE)
    assert _wait_quiet(sp)
    chunks = cap.calls[0][1]
    assert len(chunks) > 5, f"청크가 {len(chunks)}개뿐 — 통째로 넘겼다"
    assert max(len(c) for c in chunks) <= tts_mod._PCM_CHUNK


def test_stop_이후_낡은_세대_항목은_어디서_발견되든_버려진다():
    """끼어들기 취소는 **세대 비교**다. 예전 공유 Event 방식은 워커가 항목을
    집을 때마다 clear() 해서, stop() 이 워커의 finally 검사와 다음 pickup 사이
    좁은 틈에 떨어지면 취소가 지워지고 선요청해 둔 절이 통째로 재생됐다(리뷰
    확인). 세대는 지울 수 없다 — stop() 전에 적재된 항목은 큐·held 어디에
    있었든 재생되지 않아야 한다.
    """
    cap = Captured()
    sp = _speaker(cap)
    # stop() 이전 세대의 항목이 아직 큐에 남아 있던 상황을 그대로 만든다
    old = tts_mod._Item(voice="", text="", sound=(_pcm(0.3), RATE), gen=sp._gen)
    sp.stop()  # 세대 교체 — old 는 이제 낡았다
    with sp._lock:
        sp._pending += 1
        sp._speaking.set()
    sp._q.put(old)
    assert _wait_quiet(sp), "낡은 항목이 pending 정리를 막았다"
    assert cap.calls == [], "stop() 이전 세대의 발성이 재생됐다"
    # 새 세대 항목은 정상 재생된다 — stop 이 미래 발화까지 막으면 안 된다
    sp.play_sound(_pcm(0.2), RATE)
    assert _wait_quiet(sp)
    assert len(cap.calls) == 1


def test_끼어들면_대기중인_발성이_버려진다():
    cap = Captured()
    sp = _speaker(cap)
    for _ in range(4):
        sp.play_sound(_pcm(0.4), RATE)
    sp.stop()
    assert _wait_quiet(sp)
    assert len(cap.calls) < 4, "끊었는데 대기 중이던 발성이 전부 재생됐다"


def test_발성은_자기_목소리_대조에_들어가지_않는다():
    """`said_recently` 는 전사와 **문장**을 대조한다 — 가사 없는 발성은 넣을 것이 없다."""
    cap = Captured()
    sp = _speaker(cap)
    sp.play_sound(_pcm(0.2), RATE)
    assert _wait_quiet(sp)
    assert sp.said_recently("안녕하세요 반갑습니다") is False


def test_발성과_발화가_순서대로_나간다():
    """스피커가 하나뿐이라 섞이면 안 된다 — 큐가 순서를 지킨다."""
    cap = Captured()
    sp = tts_mod.Speaker(play_pcm=cap, cmd=["true"])  # say 경로 강제(합성 안 함)
    sp.play_sound(_pcm(0.2), RATE)
    sp.speak("안녕하세요")
    assert _wait_quiet(sp)
    # 발성만 _play_pcm 을 탄다. 발화는 cmd 경로라 여기 안 잡힌다 —
    # 둘이 같은 큐를 쓴다는 것은 speaking 이 끝까지 유지된 것으로 확인된다.
    assert len(cap.calls) == 1


def test_빈_발성은_큐에_넣지_않는다():
    cap = Captured()
    sp = _speaker(cap)
    sp.play_sound(b"", RATE)
    assert sp.speaking is False
    assert cap.calls == []


# ── 자르기·페이드 ──────────────────────────────────────────────


def test_리액션_발성은_앞부분만_남는다(monkeypatch):
    monkeypatch.setattr(sound_mod, "REACTION_S", 1.2)
    out = sound_mod._trim(_pcm(5.0), RATE, 1.2)
    assert abs(len(out) / 2 / RATE - 1.2) < 0.01


def test_자른_끝은_페이드아웃한다(monkeypatch):
    """뚝 끊기면 고장난 것처럼 들린다."""
    monkeypatch.setattr(sound_mod, "FADE_S", 0.25)
    out = np.frombuffer(sound_mod._trim(_pcm(5.0), RATE, 1.2), dtype=np.int16)
    tail = np.abs(out[-int(0.01 * RATE):]).max()
    body = np.abs(out[: int(0.5 * RATE)]).max()
    assert tail < 0.1 * body, f"끝이 안 잦아든다(끝 {tail} / 본문 {body})"


def test_원본보다_길게_요구하면_그대로_둔다():
    src = _pcm(0.5)
    assert sound_mod._trim(src, RATE, 1.2) == src


def test_공연은_자르지_않는다(monkeypatch):
    """`full=True` 는 seconds=0 으로 내려가 자르기를 건너뛴다."""
    src = _pcm(5.0)
    assert sound_mod._trim(src, RATE, 0.0) == src


def test_스위치로_끌_수_있다(monkeypatch):
    monkeypatch.setattr(sound_mod, "ENABLED", False)
    assert sound_mod.load("/anything.ogg", RATE) is None
