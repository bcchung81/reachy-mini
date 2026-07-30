"""시뮬·개발용 진입점 — 실기가 못 하는 폴백 모드를 제공한다.

**정상 경로는 `main.py` 다**(실기와 같은 `ReachyMiniApp`). `scripts/demo.sh` 도
기본으로 그것을 띄운다 — 시연에서 돌리는 것과 배포하는 것을 같게 두기 위해서다.

이 파일은 `main.py` 로는 안 되는 두 가지를 위해 남아 있다:

    --text       키보드 입력 (마이크가 말썽일 때)
    --no-robot   데몬 없이 대화·음성만 (데몬이 죽었을 때 최후 폴백)

대화 로직은 여기 없다 — `session.py` 하나뿐이다.
"""

import argparse
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from session import announce_voice, build, respond


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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", action="store_true", help="키보드 입력 모드")
    ap.add_argument("--no-robot", action="store_true", help="데몬 없이 (대화·TTS만)")
    args = ap.parse_args()
    with contextlib.ExitStack() as stack:
        announce_voice()
        llm, speaker, player = build(stack, no_robot=args.no_robot)
        if args.text:
            text_loop(llm, speaker, player)
        else:
            from voice_loop import voice_loop

            voice_loop(llm, speaker, player, respond)
    print("종료했습니다.")
