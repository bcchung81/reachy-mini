"""대화 세션의 공통부 — 시뮬(demo.py)과 실기(main.py)가 **똑같이** 쓴다.

진입점만 둘이고 로직은 여기 하나뿐이다. 진입점이 다른 이유는 두 가지다:

- 실기는 `ReachyMini` 인스턴스를 프레임워크가 주입한다(`build(mini=...)`).
  시뮬은 직접 만들어 컨텍스트로 잡는다.
- 실기는 `stop_event` 로, 시뮬은 Ctrl-C 로 끝난다.

**대화 로직을 고칠 때는 이 파일만 고친다.** 진입점에 복사하지 말 것.
"""

import audio_setup
import camera_in
import config
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import emotions
import selfintro
import vision
from clauses import split_sentences
from driver import RobotDriver
from idler import Idler
from llm import LLMClient
from motion import NO_MOTION, MotionPlayer, MoveLibrary, classify
from tts import Speaker

HERE = Path(__file__).parent


def prompt_path() -> Path:
    """시스템 프롬프트 파일. **설정 사다리로 고른다**(환경변수 → config.json → 기본값).

    해설 모드(`prompt_exhibit.md`)로 바꾸려면 실기에서 `config.json` 에
    `REACHY_PROMPT` 한 줄이면 되고 앱 재배포가 필요 없다 — §10 사다리를 그대로 쓴다.
    (환경변수는 systemd 데몬의 자식인 앱에 닿지 않으므로 파일 단이 정답 경로다.)

    파일명만 취한다. `config.json` 은 사람이 손으로 고치는 파일이라 오타 하나로
    앱 밖을 가리키게 두지 않는다. 없는 파일이면 **경고하고** 기본값으로 되돌린다 —
    조용히 폴백하면 해설 모드로 켰다고 믿는데 일반 미니가 도는, 가장 찾기 어려운
    실패가 된다.
    """
    name = Path(config.get("REACHY_PROMPT", "prompt.md")).name
    p = HERE / name
    if not p.exists():
        print(f"  [프롬프트 경고] {name} 를 찾을 수 없다 — prompt.md 로 되돌린다", flush=True)
        return HERE / "prompt.md"
    return p
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
            # 상수가 아니라 함수로 읽는다 — 역할별 음성(설계 §11)은 import
            # 뒤에 정해지므로 상수를 찍으면 **실제로 나가는 목소리와 다른 것**을
            # 기동 로그에 적는다. 그 로그를 믿고 시연에 들어가면 못 잡는다.
            print(f"목소리: Qwen3-TTS '{tts_mod.qwen_voice()}' "
                  f"({tts_mod.QWEN_URL}, x{tts_mod.qwen_speed()})")
        else:
            print(f"목소리: ⚠ Qwen3-TTS 응답 없음 → 유나(say)로 폴백 중 — {tts_mod.QWEN_URL}")
    else:
        print(f"목소리: macOS {tts_mod.DEFAULT_VOICE} (TTS_BACKEND=say)")


def announce_endpoints() -> None:
    """세 주소와 출처를 기동 로그에 밝힌다 — 실기에서 loopback 이면 경고.

    §10 방어선의 출력 부분이다. 주소가 틀려도 앱은 조용히 돌기 때문에
    (STT 빈 문자열·LLM 폴백 한 줄) 원인이 로그 첫 줄에 보여야 한다.
    """
    import config

    config.announce()


def build(stack: contextlib.ExitStack, no_robot: bool = False, mini=None, idle_moves=None):
    """대화에 필요한 것들을 만든다.

    `mini` 를 주면 **그것을 쓰고 닫지 않는다** — 실기에서는 ReachyMiniApp
    프레임워크가 인스턴스의 생성·해제를 책임지므로 우리가 컨텍스트로 잡으면
    이중 해제가 된다.

    직접 만드는 경우(시뮬)에는 반드시 컨텍스트로 잡는다. `__enter__` 는 self 만
    돌려주지만 `__exit__` 이 media_manager.close() 와 client.disconnect() 를 한다.
    이걸 빠뜨리면 대화가 끝나도 살아남은 스레드가 프로세스를 붙잡아 종료되지 않는다.
    """
    # **오디오 장치를 열기 전에** 볼륨을 맞춘다. 실기 스피커는 62%(-23dB)로
    # 출고돼 목소리가 안 들린다(2026-09-09 실측). 시뮬(macOS)에서는 no-op 다.
    audio_setup.maximize_volume()

    llm = LLMClient(system_prompt=prompt_path().read_text())
    speaker = Speaker()
    player = None
    if not no_robot:
        from reachy_mini.motion.recorded_move import RecordedMoves

        # 감정 라이브러리(발성 있음)가 본체다. 춤 라이브러리(소리 없는 짧은 동작)는 대본 감정
        # 태그의 끄덕·움찔·감탄 후보를 넓히는 **덤**이라(계획 2026-09-24-emotion-vocabulary),
        # 못 읽으면 경고하고 빼고 간다 — 그 범주 후보에서 춤 동작만 빠진다. 데몬이 기동 때 두
        # 라이브러리를 **같이** 받으므로(SDK `DEFAULT_DATASETS`) 실기에서 새 의존성은 아니다.
        libraries = [RecordedMoves("pollen-robotics/reachy-mini-emotions-library")]
        try:
            libraries.append(RecordedMoves("pollen-robotics/reachy-mini-dances-library"))
        except Exception as exc:  # noqa: BLE001 — 덤이 본체를 막으면 안 된다
            print(
                f"  [경고] 춤 라이브러리를 못 읽었다({type(exc).__name__}: {exc}) — "
                "감정 라이브러리만으로 돈다(끄덕·움찔 후보가 줄어든다)",
                flush=True,
            )
        moves = MoveLibrary(libraries)
        if mini is None:
            from reachy_mini import ReachyMini

            mini = stack.enter_context(ReachyMini())

        # **로봇에 쓰는 스레드는 이것 하나다**(공식 control-loops 규칙).
        # 말할 때 흔들리고 조용할 때 숨 쉬는 것도, 녹화 모션을 도는 것도 여기서
        # 합성한다 — 예전처럼 애니메이터와 모션이 각자 set_target 을 쓰지 않는다.
        driver = RobotDriver(mini, lambda: speaker.speaking)
        driver.start()
        stack.callback(driver.stop)

        # 모션 발성은 speaker 로 나간다 — SDK 미디어를 안 쓰기 때문이기도 하고
        # (`main.py` 의 no_media), 그래야 에코 프로브·마이크 게이팅이 인지한다.
        player = MotionPlayer(driver, moves, speaker)

        # 아무도 말을 걸지 않을 때 혼자 감정 표현을 한다(소리 없이).
        # `idle_moves` — 무대 모드는 듣는 자세 목록(`emotions.STAGE_IDLE_MOVES`)을 넘긴다.
        # 1대 모드(None)는 지금 목록 그대로다.
        idler = Idler(
            player,
            lambda: speaker.speaking,
            on_play=lambda n: print(f"  [대기 모션 {n}]"),
            moves=idle_moves,
        )
        idler.start()
        stack.callback(idler.stop)

    # 카메라 파이프라인은 열려 있을 수 있다(REACHY_CAMERA_IDLE_S>0). 종료 경로에서
    # 반드시 닫는다 — 안 닫으면 앱이 끝나도 장치를 쥔 채 남아 다음 기동이 깨진다.
    stack.callback(camera_in.close)
    return llm, speaker, player


def speak(text: str, speaker, player, category: str | None = None) -> None:
    """받은 텍스트를 말하고 그에 맞는 모션을 낸다. **LLM 을 부르지 않는다.**

    1대 구성에서는 `respond()` 가 LLM 스트림을 받은 뒤 이 경로로 말하고,
    2대 구성에서는 무대감독이 만든 텍스트로 이것만 쓴다.

    `category` 를 안 주면 **문장으로 고른다**(`motion.classify`). 예전 기본값
    'neutral' 은 모션 표에 없는 이름이라 2대 모드의 모든 발화가 모션 없이 나갔다
    — 로봇이 말하는 내내 몸이 가만히 있었다(리뷰 B1).

    `category=motion.NO_MOTION` 은 **모션을 아예 걸지 말라**는 뜻이다(대본의
    '설명' 태그, 설계 §12.2). `None`(=모르니 추측해라)과 반드시 구별해야 한다 —
    둘을 같은 값으로 두면 해설 대사 전부가 추측 경로로 내려가 대사마다 몸이 튄다.

    **재생 완료를 기다리지 않는다.** 기다리면 그동안 마이크 루프가 멈춰
    끼어들기 판정이 한 번도 돌지 않는다 — 재생 중 마이크를 어떻게 다룰지는
    호출부가 정한다(`voice_loop` 의 게이팅, `stage_client` 의 mic 지시).

    **문장이 둘 이상이면 문장 단위로 나눠 `speak_many()` 로 보낸다** — 무대 모드
    감독 대사(최대 280자, 40~90초 분량)를 통째로 `speak()` 하나(=TTS 요청 하나)
    로 보내던 것이 목소리가 남자 기계음으로 바뀌는 결함의 원인이었다: Qwen3-TTS
    서버는 요청을 하나씩 처리하고 클라이언트가 끊어도 끝까지 합성하므로(실측
    65.3초), 그 뒤에 밀린 다음 요청이 `QWEN_TIMEOUT`(90초)을 넘겨 로컬
    합성기(실기 Linux 는 espeak-ng — 남성 기계음)로 폴백했다. 요청 단위를
    문장으로 좁히면 끊었을 때 서버가 붙잡는 시간이 문장 하나(+선요청 하나)로
    준다. 모션은 지금처럼 **발화 전체**를 보고 한 번만 고른다 — 문장마다 다시
    고르면 한 발화 안에서 모션이 튄다.
    """
    text = (text or "").strip()
    if not text:
        # 빈 대사를 말하는 로봇이 되지 않는다. 감독 쪽 사고를 여기서 흡수한다.
        return
    if player is not None:
        if category == NO_MOTION:
            print("  [모션 없음 — 대본 감정이 '설명']")
        else:
            category = category or classify(text)
            name = player.play_for(category)
            print(f"  [모션 {category}/{name}]")
    print(f"미니> {text}")
    sentences = split_sentences(text)
    if len(sentences) > 1:
        speaker.speak_many(sentences)
    else:
        speaker.speak(text)


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
        # **여기서 재생 완료를 기다리지 않는다.** 기다리면 마이크 루프가 약 55초간
        # 멈춰 있어 대본 도중에는 끼어들 수 없었다(REACHY_BARGE_IN 이 켜져 있어도).
        # 일반 답변과 같은 규칙으로 맞춘다 — 큐에 넣고 곧바로 반환하고, 재생 중
        # 마이크를 어떻게 다룰지는 호출부(voice_loop 의 게이팅)가 정한다.
        # 끼어들기가 걸리면 speaker.stop() 이 남은 문장을 큐에서 버린다.
        return

    # ── 카메라 ────────────────────────────────────────────────────────
    # **모션보다 먼저 찍는다.** 응답 모션이 머리를 기울이면 천장이나 바닥을 찍게
    # 된다(실측으로 천장만 찍힌 프레임을 얻었다). 이 시점의 머리는 중립에 가깝다 —
    # 사용자가 말하기 시작할 때 `set_user_speaking` 이 대기 모션을 이미 끊었고,
    # 발화 수집 + STT 사이에 sway 만 남아 중립으로 돌아와 있다.
    #
    # 대신 캡처 시간만큼 모션이 늦는다. 카메라가 열려 있으면 0.001s 라 무시할 수
    # 있고, 콜드면 약 2.5s 다(자동노출 수렴 1초 포함) — 그때는 로봇이 잠깐 가만히
    # 있다가 반응하는데, "보고 나서 답한다" 는 동작으로 읽혀 어색하지 않다.
    #
    # 매 턴 찍지 않는 이유는 vision.py 참고(이미지가 붙으면 첫 토큰이
    # 0.105s → 0.4~0.6s 로 간다, 2026-09-09 실측).
    image = camera_in.grab_jpeg() if vision.wants_camera(user) else None
    if image is not None:
        print(f"  [카메라 {len(image)}B +{time.time() - t0:.2f}s]", flush=True)

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
        for clause in llm.chat_stream(user, image):
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

    # **여기서 재생 완료를 기다리지 않는다.** 기다리면 그동안 마이크 루프가 멈춰
    # 끼어들기 판정이 한 번도 돌지 않는다 — 대본은 되는데 일반 답변은 안 끊기던
    # 이유가 이 한 줄이었다(대본 분기에서는 걷어냈는데 여기를 놓쳤다).
    # 재생 중 마이크를 어떻게 다룰지는 호출부가 정한다:
    #   voice_loop  — speaking 플래그로 게이팅하거나 끼어들기로 끊는다
    #   demo.py     — 키보드 모드라 끼어들기가 없으니 거기서 wait_idle 한다
