"""음성 일상대화 데모. --text: 키보드 입력(오디오 없음, 안전 폴백)."""

import argparse
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import selfintro
from animator import Animator
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

        # 말하는 동안 흔들리고 조용할 때 숨 쉬게 한다. 감정 모션이 끝난 뒤
        # 답변이 이어지는 구간에서 로봇이 굳어 보이는 것을 막는다.
        animator = Animator(mini, lambda: speaker.speaking, lambda: player.busy)
        animator.start()
        stack.callback(animator.stop)
    return llm, speaker, player


def respond(user: str, llm: LLMClient, speaker: Speaker, player) -> None:
    """한 턴: 모션 즉시 + LLM 스트림 → 절 단위 TTS. 구간 지연을 로그로 남긴다."""
    t0 = time.time()

    # 구성을 묻는 질문은 LLM 에 맡기지 않는다 — 모델명과 수치를 지어낼 수 있다.
    # 검증된 대본을 그대로 읽는다(약 57초).
    if selfintro.matches(user):
        if player:
            player.play_for("curious", force=True)
        print(f"  [자기소개 대본 {len(selfintro.SCRIPT)}문장]")
        for line in selfintro.SCRIPT:
            print(f"미니> {line}")
        speaker.speak_many(selfintro.SCRIPT)
        llm.history += [
            {"role": "user", "content": user},
            {"role": "assistant", "content": selfintro.HISTORY_SUMMARY},
        ]
        speaker.wait_idle(timeout=180)
        return

    category = classify(user)
    # 공연(노래·춤)은 요청 자체가 목적이라 진행 중인 모션을 끊고서라도 보여준다
    name = player.play_for(category, force=(category == "perform")) if player else None
    print(f"  [모션 {category}/{name} +{time.time() - t0:.2f}s]")

    # 첫 절만 즉시 발화하고 나머지는 묶어서 한 번에 보낸다.
    # say 비용은 대부분 프로세스 고정비라 길이와 거의 무관한데(M0 실측),
    # 절마다 따로 띄우면 문장 사이에 공백과 억양 초기화가 생겨 뚝뚝 끊겨 들린다.
    # 첫 절을 말하는 3초 남짓 동안 스트림(~1.5초)이 끝나므로 공백은 생기지 않는다.
    spoke = False
    rest: list[str] = []
    try:
        for clause in llm.chat_stream(user):
            print(f"미니> {clause}")
            if not spoke:
                print(f"  [첫 절 +{time.time() - t0:.2f}s]")
                speaker.speak(clause)
                spoke = True
            else:
                rest.append(clause)
    except Exception as exc:
        print(f"  [LLM 실패: {type(exc).__name__} — 폴백]")
        if not spoke:
            speaker.speak(FALLBACK_LINE)
    if rest:
        # 같은 음성끼리만 묶는다. 전부 합치면 한글 우선 규칙에 걸려
        # 한국어 음성이 중국어·일본어까지 읽어 발음이 깨진다.
        speaker.speak_many(rest)
    speaker.wait_idle(timeout=60)


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
