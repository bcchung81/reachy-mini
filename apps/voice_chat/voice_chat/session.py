"""대화 세션의 공통부 — 시뮬(demo.py)과 실기(main.py)가 **똑같이** 쓴다.

진입점만 둘이고 로직은 여기 하나뿐이다. 진입점이 다른 이유는 두 가지다:

- 실기는 `ReachyMini` 인스턴스를 프레임워크가 주입한다(`build(mini=...)`).
  시뮬은 직접 만들어 컨텍스트로 잡는다.
- 실기는 `stop_event` 로, 시뮬은 Ctrl-C 로 끝난다.

**대화 로직을 고칠 때는 이 파일만 고친다.** 진입점에 복사하지 말 것.
"""

import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import emotions
import selfintro
from animator import Animator
from idler import Idler
from llm import LLMClient
from motion import MotionPlayer, classify
from tts import Speaker

HERE = Path(__file__).parent
FALLBACK_LINE = "음, 잠깐 생각이 안 나요. 다시 한 번 말해 줄래요?"


def announce_voice() -> None:
    """어느 목소리로 도는지 화면에 밝힌다.

    폴백이 조용히 유나로 떨어지면 눈으로는 구별할 방법이 없다 —
    실제로 '음색이 안 바뀐다'는 혼란이 있었다.
    """
    import tts as tts_mod

    if tts_mod.BACKEND == "qwen":
        ok = tts_mod._qwen_synth("준비") is not None
        if ok:
            print(f"목소리: Qwen3-TTS '{tts_mod.QWEN_VOICE}' "
                  f"({tts_mod.QWEN_URL}, x{tts_mod.QWEN_SPEED})")
        else:
            print(f"목소리: ⚠ Qwen3-TTS 응답 없음 → 유나(say)로 폴백 중 — {tts_mod.QWEN_URL}")
    else:
        print(f"목소리: macOS {tts_mod.DEFAULT_VOICE} (TTS_BACKEND=say)")


def build(stack: contextlib.ExitStack, no_robot: bool = False, mini=None):
    """대화에 필요한 것들을 만든다.

    `mini` 를 주면 **그것을 쓰고 닫지 않는다** — 실기에서는 ReachyMiniApp
    프레임워크가 인스턴스의 생성·해제를 책임지므로 우리가 컨텍스트로 잡으면
    이중 해제가 된다.

    직접 만드는 경우(시뮬)에는 반드시 컨텍스트로 잡는다. `__enter__` 는 self 만
    돌려주지만 `__exit__` 이 media_manager.close() 와 client.disconnect() 를 한다.
    이걸 빠뜨리면 대화가 끝나도 살아남은 스레드가 프로세스를 붙잡아 종료되지 않는다.
    """
    llm = LLMClient(system_prompt=(HERE / "prompt.md").read_text())
    speaker = Speaker()
    player = None
    if not no_robot:
        from reachy_mini.motion.recorded_move import RecordedMoves

        moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
        if mini is None:
            from reachy_mini import ReachyMini

            mini = stack.enter_context(ReachyMini())
        player = MotionPlayer(mini, moves)

        # 말하는 동안 흔들리고 조용할 때 숨 쉬게 한다. 감정 모션이 끝난 뒤
        # 답변이 이어지는 구간에서 로봇이 굳어 보이는 것을 막는다.
        animator = Animator(mini, lambda: speaker.speaking, lambda: player.moving)
        animator.start()
        stack.callback(animator.stop)

        # 아무도 말을 걸지 않을 때 혼자 감정 표현을 한다(소리 없이).
        idler = Idler(
            player,
            lambda: speaker.speaking,
            on_play=lambda n: print(f"  [대기 모션 {n}]"),
        )
        idler.start()
        stack.callback(idler.stop)
    return llm, speaker, player


def respond(user: str, llm: LLMClient, speaker: Speaker, player) -> None:
    """한 턴: 모션 즉시 + LLM 스트림 → 절 단위 TTS. 구간 지연을 로그로 남긴다."""
    t0 = time.time()

    # 구성을 묻는 질문은 LLM 에 맡기지 않는다 — 모델명과 수치를 지어낼 수 있다.
    # 검증된 대본을 그대로 읽는다(약 49초).
    if selfintro.matches(user):
        if player:
            player.play_for("curious", force=True)
        print(f"  [자기소개 대본 {len(selfintro.SCRIPT)}문장]")
        for i, line in enumerate(selfintro.SCRIPT, 1):
            print(f"미니> {line}")
            # 음높이가 튀는 문장은 보정 시드로 고정한다(selfintro.SEEDS)
            speaker.speak(line, seed=selfintro.SEEDS.get(i))
        llm.history += [
            {"role": "user", "content": user},
            {"role": "assistant", "content": selfintro.HISTORY_SUMMARY},
        ]
        speaker.wait_idle(timeout=180)
        return

    # "슬픈 표정 지어봐" 같은 연기 요청은 그 감정을 그대로 재생한다.
    # 감정 단어만 있는 "나 슬퍼" 는 여기 걸리지 않고 LLM 이 공감으로 답한다.
    acted = emotions.find_request(user) if player else None
    if acted:
        player.play(acted, force=True)
        print(f"  [감정 연기 {acted} +{time.time() - t0:.2f}s]")
    else:
        category = classify(user)
        # 공연(노래·춤)은 요청 자체가 목적이라 진행 중인 모션을 끊고서라도 보여준다
        name = player.play_for(category, force=(category == "perform")) if player else None
        print(f"  [모션 {category}/{name} +{time.time() - t0:.2f}s]")

    # 첫 절만 즉시 발화하고 나머지는 묶어서 한 번에 보낸다.
    # 첫 절을 말하는 동안 스트림이 끝나므로 문장 사이에 공백이 생기지 않는다.
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
