"""음성 일상대화 데모. --text: 키보드 입력(오디오 없음, 안전 폴백)."""

import argparse
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import LLMClient
from motion import MotionPlayer, classify
from tts import Speaker

HERE = Path(__file__).parent
FALLBACK_LINE = "음, 잠깐 생각이 안 나요. 다시 한 번 말해 줄래요?"


def build(stack: contextlib.ExitStack, no_robot: bool = False):
    """ReachyMini 는 반드시 컨텍스트로 잡는다.

    __enter__ 는 self 만 돌려주지만 __exit__ 이 media_manager.close() 와
    client.disconnect() 를 한다. 이걸 빠뜨리면 대화가 끝나도 살아남은
    스레드가 프로세스를 붙잡아 종료되지 않는다.
    """
    llm = LLMClient(system_prompt=(HERE / "prompt.md").read_text())
    speaker = Speaker()
    player = None
    if not no_robot:
        from reachy_mini import ReachyMini
        from reachy_mini.motion.recorded_move import RecordedMoves

        moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
        mini = stack.enter_context(ReachyMini())
        player = MotionPlayer(mini, moves)
    return llm, speaker, player


def respond(user: str, llm: LLMClient, speaker: Speaker, player) -> None:
    """한 턴: 모션 즉시 + LLM 스트림 → 절 단위 TTS. 구간 지연을 로그로 남긴다."""
    t0 = time.time()
    category = classify(user)
    name = player.play_for(category) if player else None
    print(f"  [모션 {category}/{name} +{time.time() - t0:.2f}s]")

    spoke = False
    try:
        for clause in llm.chat_stream(user):
            if not spoke:
                print(f"  [첫 절 +{time.time() - t0:.2f}s]")
                spoke = True
            print(f"미니> {clause}")
            speaker.speak(clause)
    except Exception as exc:
        print(f"  [LLM 실패: {type(exc).__name__} — 폴백]")
        if not spoke:
            speaker.speak(FALLBACK_LINE)
    speaker.wait_idle(timeout=30)


def text_loop(llm, speaker, player) -> None:
    print("텍스트 모드 — 빈 줄 또는 q 로 종료")
    while True:
        try:
            user = input("나> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user in ("", "q", "quit"):
            break
        respond(user, llm, speaker, player)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true", help="키보드 입력 모드")
    ap.add_argument("--no-robot", action="store_true", help="데몬 없이 (대화·TTS만)")
    args = ap.parse_args()
    with contextlib.ExitStack() as stack:
        llm, speaker, player = build(stack, no_robot=args.no_robot)
        if args.text:
            text_loop(llm, speaker, player)
        else:
            from voice_loop import voice_loop

            voice_loop(llm, speaker, player, respond)
    print("종료했습니다.")
