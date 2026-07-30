"""음성 모드 — VAD 발화 검출 → STT → respond(). half-duplex 게이팅 포함.

하드웨어 AEC 가 없으므로 로봇이 소리를 내는 동안에는 마이크 입력을 통째로 버린다.
버리는 동안 VAD 를 reset() 한다 — 무음 프레임을 먹이면 발화 중이던 상태기계가
hangover 를 채우고 가짜 발화를 뱉는다.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audio_in import EnergyVAD, MicCapture
from stt import transcribe

POST_PLAYBACK_GUARD_S = 0.3  # 재생 종료 후 잔향이 VAD에 잡히지 않게


def voice_loop(llm, speaker, player, respond, should_stop=None) -> None:
    """`should_stop` 은 매 프레임 확인하는 종료 조건이다(실기의 stop_event.is_set).

    프레임이 30ms 마다 오므로 그 간격으로 반응한다. 다만 `respond()` 안에서는
    확인하지 않는다 — 자기소개 대본은 한 번 시작하면 약 50초간 이어진다.
    """
    mic, vad = MicCapture(), EnergyVAD()
    print("음성 모드 — 말을 걸어보세요 (Ctrl-C 종료)", flush=True)
    guard_until = 0.0
    try:
        for frame in mic.frames():
            if should_stop is not None and should_stop():
                break
            # 게이팅: TTS 재생 중, 모션(자체 사운드) 중이면 버리고 가드를 갱신한다
            if speaker.speaking or (player is not None and player.busy):
                vad.reset()
                guard_until = time.time() + POST_PLAYBACK_GUARD_S
                continue
            if time.time() < guard_until:  # 재생 직후 잔향 구간
                vad.reset()
                continue

            utterance = vad.feed(frame)
            if utterance is None:
                continue

            t0 = time.time()
            text = transcribe(utterance)
            print(f"나(STT +{time.time() - t0:.2f}s)> {text}", flush=True)
            if not text:
                continue  # 침묵·잡음 — 다시 듣기
            respond(text, llm, speaker, player)
            guard_until = time.time() + POST_PLAYBACK_GUARD_S
    except KeyboardInterrupt:
        pass
    finally:
        mic.close()
