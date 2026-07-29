#!/usr/bin/env bash
# Reachy Mini 시뮬레이터 기동 (macOS / Apple Silicon)
#
# 사용법
#   ./run-sim.sh                    빈 씬 — 3D 뷰어 + 오디오 동시 동작(기본)
#   ./run-sim.sh --scene minimal    테이블 + 사과/크루아상/오리 씬
#   ./run-sim.sh --no-media         오디오·카메라 끄고 기동 (모션만 볼 때)
#   ./run-sim.sh --headless         3D 창 없이 기동
#
# 이 스크립트가 세 가지를 대신 처리한다. 셋 다 macOS에서 빼먹으면 데몬이 멈춘다.
#
# 1) mjpython 런처
#    MuJoCo 뷰어는 Cocoa GUI 호출을 메인스레드에서 해야 해서 전용 런처가 필요하다.
#    `reachy-mini-daemon --sim`으로 실행하면 다음 예외가 난다:
#      RuntimeError: `launch_passive` requires that the Python script be run under `mjpython` on macOS
#    SDK는 이를 자동 처리하지 않는다 (pollen-robotics/reachy_mini#79, open).
#
# 2) GST_PLUGIN_SCANNER
#    미지정 시 "External plugin loader failed" 경고와 함께 플러그인을 in-process로 로드하다
#    데몬이 정지한다. 외부 스캐너 프로세스에 위임하면 깨진 플러그인이 경고로 격리된다.
#
# 3) GST_PLUGIN_FEATURE_RANK — 3D 뷰어와 오디오를 동시에 쓰기 위한 핵심
#    미디어를 켜면 GStreamer 장치 모니터가 CoreAudio를 프로브하다 교착된다
#    (gst_device_monitor_start → gst_osx_audio_device_provider_probe → gst_core_audio_bind_device).
#    mjpython이 macOS 메인스레드를 Cocoa GUI용으로 점유하는데 CoreAudio 장치 조회도
#    메인 런루프를 요구하기 때문이다. 마이크 권한(TCC) 문제가 아니다 —
#    같은 프로브를 일반 python으로 돌리면 장치 3개가 즉시 잡힌다(실측).
#
#    해결: 교착을 일으키는 것은 *장치 프로바이더*(osxaudiodeviceprovider)이고,
#    실제 입출력 요소(osxaudiosrc/osxaudiosink)는 별개 팩토리다.
#    프로바이더 랭크만 NONE으로 내리면 장치 모니터가 이를 건너뛰고
#    (GstDeviceMonitor는 RANK_MARGINAL=64 미만을 제외), 오디오 자체는 그대로 동작한다.
#    카메라 쪽 avfdeviceprovider도 같은 이유로 함께 내린다.
#    → 3D 뷰어 + 오디오 + 시뮬 카메라 스트림이 한 프로세스에서 공존한다.
#
# 근거: claudian vault
#   acquired/fetched/reachy-mini-시뮬-macos설치/2026-07-29_시뮬레이션-실행-mjpython-macos함정.md
#   topics/Reachy Mini 시뮬레이터 개발환경 (macOS·2026-07).md
set -euo pipefail
cd "$(dirname "$0")"

source .venv/bin/activate

export GST_PLUGIN_SCANNER="$PWD/.venv/lib/python3.12/site-packages/gstreamer_libs/libexec/gstreamer-1.0/gst-plugin-scanner"
export GST_REGISTRY="$PWD/.gst-registry.bin"   # 레지스트리 캐시 — 매 기동 재스캔 방지
export GST_PLUGIN_FEATURE_RANK="osxaudiodeviceprovider:NONE,avfdeviceprovider:NONE"

# --no-media를 명시하면 미디어를 끈다. 기본은 켜짐(오디오·시뮬 카메라 사용 가능).
args=("$@")

echo "▶ mjpython -m reachy_mini.daemon.app.main --sim ${args[*]}"
exec mjpython -m reachy_mini.daemon.app.main --sim "${args[@]}"
