import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from tts import Speaker


def test_speak은_즉시_반환하고_순차_실행된다(tmp_path):
    out = tmp_path / "log"
    # 한 줄씩 기록하는 가짜 TTS — 0.1초 걸린다
    fake = ["/bin/sh", "-c", f'sleep 0.1; echo "$0" >> {out}']
    s = Speaker(cmd=fake)
    t0 = time.time()
    s.speak("첫째")
    s.speak("둘째")
    assert time.time() - t0 < 0.05  # 비차단
    assert s.speaking  # 적재 직후부터 True (게이팅용)
    s.wait_idle(timeout=3)
    assert not s.speaking
    assert out.read_text().splitlines() == ["첫째", "둘째"]


def test_빈_문자열은_무시():
    s = Speaker(cmd=["/usr/bin/true"])
    s.speak("   ")
    assert not s.speaking
