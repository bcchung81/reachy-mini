"""기동 시 오디오 볼륨을 최대로 맞춘다.

**실기의 스피커는 62%(-23.00dB)로 출고된다** — 실측(2026-09-09, Reachy Mini
Wireless): `PCM` 이 37/60, `Headset`(마이크)는 이미 60/60 이었다. 시연장에서
로봇 목소리가 안 들리는 원인이 이것이다. 매 기동에 맞춰 두면 누가 손으로 줄여
놓았어도 시연 전에 원복된다.

**ALSA 전용이다.** macOS(시뮬)에는 `amixer` 가 없으므로 **조용히** 건너뛴다 —
여기서 예외를 던지거나 경고를 쏟으면 시뮬 개발이 시끄러워진다. 반대로 Linux(실기)
인데 실패하면 **소리 내서 알린다**: 시연장에서 "왜 작지"를 못 찾는 것이 최악이다.

컨트롤 이름과 명령은 벤더 점검 스크립트(`/usr/local/bin/reachyminios_check`)가
쓰는 것과 같게 맞췄다. 임의로 정하면 펌웨어가 바뀔 때 조용히 어긋난다.

`alsactl store` 로 영구 저장하지 않는다 — sudo 가 필요하고, 매 기동에 거는 편이
앱만 배포하는 구조에 맞는다.
"""

import platform
import re
import shutil
import subprocess

import config

# 벤더 스크립트와 동일한 컨트롤 이름. 재생 2개 + 캡처 2개다.
PLAYBACK = ("PCM", "PCM,1")
CAPTURE = ("Headset,0", "Headset,1")


def _enabled() -> bool:
    return config.get("REACHY_AUDIO_MAX_VOLUME", "1").lower() not in ("0", "false", "no")


def _card_index() -> str:
    """오디오 카드를 **이름으로** 찾는다.

    인덱스를 0 으로 박으면 안 된다 — 실기에는 vc4hdmi 카드가 둘 더 있어서
    열거 순서가 바뀌면 엉뚱한 카드의 볼륨을 만지고 정작 스피커는 그대로다.
    """
    name = config.get("REACHY_AUDIO_CARD_NAME", "Reachy Mini Audio")
    try:
        out = subprocess.run(
            ["aplay", "-l"], capture_output=True, text=True, timeout=5
        ).stdout or ""
    except Exception:  # noqa: BLE001
        out = ""
    for line in out.splitlines():
        if name in line:
            m = re.match(r"card (\d+):", line)
            if m:
                return m.group(1)
    return config.get("REACHY_AUDIO_CARD", "0")


def maximize_volume() -> None:
    """스피커·마이크 볼륨을 100% 로 올린다. 실패해도 대화는 계속한다."""
    if not _enabled():
        return
    linux = platform.system() == "Linux"
    if not shutil.which("amixer"):
        # 시뮬(macOS)에서는 정상이다 — 실기에서만 문제다.
        if linux:
            print("  [볼륨 경고] amixer 를 찾을 수 없다 — 볼륨을 못 올렸다", flush=True)
        return
    if not linux:
        return

    card = _card_index()
    failed = []
    for control in (*PLAYBACK, *CAPTURE):
        try:
            r = subprocess.run(
                ["amixer", "-c", card, "sset", control, "100%"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                failed.append(control)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{control}({type(e).__name__})")
    if failed:
        print(f"  [볼륨 경고] 카드 {card} 에서 {', '.join(failed)} 설정 실패", flush=True)
    else:
        print(f"  볼륨 최대 (카드 {card}: 스피커·마이크 100%)", flush=True)
