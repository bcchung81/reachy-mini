#!/usr/bin/env bash
# Reachy Mini 단일 진입점 — 시뮬레이터도 시연 스택도 여기서 띄운다.
#
#   ./reachy.sh start --sim|--robot   시연 전부 기동(추론 3종·로봇 2대·무대감독+대시보드). --dry-run 은 계획만
#   ./reachy.sh sim                    시뮬 데몬만 (3D 뷰어 + 오디오 + 카메라)
#   ./reachy.sh sim --scene minimal    테이블 + 사과/크루아상/오리
#   ./reachy.sh sim --headless         3D 창 없이  (⚠ 카메라 스트림도 꺼진다)
#   ./reachy.sh sim --no-media         오디오·카메라 끄고 모션만
#   ./reachy.sh demo                   전체 스택(LLM·STT·TTS·데몬) + 마이크 대화
#   ./reachy.sh demo --text            키보드로 대화 — 마이크가 말썽일 때
#   ./reachy.sh demo --no-robot        시뮬 없이 대화·음성만 — 최후 폴백
#   ./reachy.sh demo --exit-clean      앱을 나갈 때 서버까지 함께 내린다
#   ./reachy.sh serve                  추론 3종(LLM·STT·TTS)만 — 실기 배포용, LAN 에 연다
#   ./reachy.sh robot up               실기 1대 기동: 백엔드 확인 → serve → 예열 → config 동기화 → 기상 → 앱
#   ./reachy.sh robot down [--keep-servers]   실기 정지 — 앱 + 맥 추론 3종·MCP 까지 정리
#   ./reachy.sh robot deploy|logs|status|fix  실기 운영 — 재배포·실시간 로그·상태·복구
#   ./reachy.sh check                  기동하지 않고 상태만 확인
#   ./reachy.sh logs [줄수]            마지막 세션 로그 + **실시간 이어보기** (--no-follow 로 끔)
#   ./reachy.sh stop                   띄운 것 전부 종료 (감독·대시보드 포함, 고아까지 쓸어낸다)
#   ./reachy.sh warmup                 시연 직전 예열 (LLM 캐시·TTS JIT·STT·모션)
#   ./reachy.sh bake [--check|--level 일반|--limit N|--force|--prune]   고정 대사를 TTS 캐시에 굽기(4수준 약 38분, 바뀐 문장만 다시)
#   ./reachy.sh measure aec|latency    실측 — AEC 잔여 에코 / TTFT·첫 절 지연
#
# `start` 는 시연 한 벌이고 나머지는 **부품**이다(1대 개발·실기 운영에 쓴다). `start` 는
# 무대감독 콘솔이 이 터미널에 뜬다 — q/Ctrl-C 로 끝내면 이 실행이 띄운 것(시뮬: 데몬·앱,
# 실기: 두 로봇의 앱 — 나중에 `robot up` 으로 합류시킨 것까지)만 내리고 추론 3종은 남긴다.
# `sim` 은 포그라운드다(Ctrl-C 로 끝). `demo` 는 없는 서버만 띄우고 앱으로 들어간다 —
# 앱을 Ctrl-C 로 나가도 서버는 살려 둔다(재진입이 빨라야 한다). 완전히 내리려면 stop.

# ↑ 위 주석 덩어리가 곧 `usage` 다(빈 줄에서 끝난다). 줄 범위를 박아 두면 한 줄 늘 때마다
#   쓰임새 끝이 잘리거나 이 줄들까지 딸려 나온다.
#
# set -e 는 쓰지 않는다. 헬스체크 실패를 직접 잡아 안내해야 한다.
set -uo pipefail
cd "$(dirname "$0")"
SELF="$PWD/$(basename "$0")"

LLAMACTL="$HOME/workspace/llamactl.sh"   # `llama` 는 셸 별칭이라 스크립트에서 못 쓴다

# 추론 3종(LLM·STT·TTS)이 **어느 주소로 듣는지.** 기본은 loopback 이다.
#
# 시뮬은 전부 이 맥 한 대에서 도니까 loopback 이 정답이고, 기본값을 0.0.0.0 으로
# 두면 개발 PC 의 모델 서버가 사내망에 그냥 열린다. 반대로 실기(Wireless)는
# **앱이 로봇 위에서 돌고 추론 3종은 이 PC 에 남으므로** 로봇에서 닿아야 한다 —
# 그 구성은 `serve` 가 0.0.0.0 으로 올린다. "시뮬에서만 필요한 것을 기본값으로
# 만들지 않는다" 의 반대 방향이지만 이유는 같다: 위험한 쪽을 기본으로 두지 않는다.
#
# 헬스체크는 언제나 localhost 로 한다 — 0.0.0.0 바인드는 localhost 로도 응답한다.
BIND_HOST="${REACHY_BIND_HOST:-127.0.0.1}"
# REACHY_PY 는 테스트용 구멍이다 — `start --dry-run` 이 파이썬을 안 건드린다는 것을
# 없는(가짜) 인터프리터로 바꿔 증명한다(tests/test_reachy_start.py). 평소에는 비워 둔다.
PY="${REACHY_PY:-.venv/bin/python}"
LOG_DIR=".demo-logs"
APP_LOG="$LOG_DIR/app.log"      # 앱(대화) 출력 — 세션 구분자와 함께 누적된다
# `start` 의 무대감독 출력 — 세션 구분자와 함께 누적된다. 앱·데몬은 start-{app,daemon}-<역할>.log
# (start 마다 새로 쓴다 — `--robot` 은 앱이 로봇 위에 있어 로봇 로그를 보는 명령 한 줄로 덮는다).
# `logs` 가 이것들도 본다.
START_DIRECTOR_LOG="$LOG_DIR/start-director.log"
SIM_PID_FILE="$LOG_DIR/sim.pid"
TTS_PID_FILE="$LOG_DIR/tts.pid"
TTS_PROXY_PID_FILE="$LOG_DIR/tts-proxy.pid"   # TTS 결과 캐시 프록시(tts_cache_proxy.py)
SCENE="minimal"

c_ok=$'\033[32m'; c_bad=$'\033[31m'; c_warn=$'\033[33m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
say_ok()   { echo "${c_ok}OK${c_off}   $1"; }
say_bad()  { echo "${c_bad}FAIL${c_off} $1"; }
say_warn() { echo "${c_warn}WARN${c_off} $1"; }   # 멈추지 않고 계속 간다 — 그래도 소리는 낸다
say_step() { echo; echo "▶ $1"; }

# 머리 주석 덩어리(2행부터 첫 비주석 줄 앞까지)를 찍는다. 예전에는 `sed -n '2,23p'` 로
# 범위를 박아 뒀다 — 명령 한 줄을 더하면 쓰임새 끝이 조용히 잘린다.
usage() { awk 'NR == 1 { next } /^#/ { print; next } { exit }' "$SELF" | sed 's/^# \{0,1\}//'; }

# ════════════════════════════════════════════════════════════════
#  sim — 시뮬레이터 데몬 (구 run-sim.sh)
# ════════════════════════════════════════════════════════════════
# 이 셋을 빼먹으면 macOS 에서 데몬이 멈춘다.
#
# 1) mjpython 런처
#    MuJoCo 뷰어는 Cocoa GUI 호출을 메인스레드에서 해야 해서 전용 런처가 필요하다.
#    `reachy-mini-daemon --sim` 으로 실행하면 다음 예외가 난다:
#      RuntimeError: `launch_passive` requires that the Python script be run under `mjpython` on macOS
#    SDK 는 이를 자동 처리하지 않는다 (pollen-robotics/reachy_mini#79, open).
#
# 2) GST_PLUGIN_SCANNER
#    미지정 시 "External plugin loader failed" 경고와 함께 플러그인을 in-process 로
#    로드하다 데몬이 정지한다. 외부 스캐너 프로세스에 위임하면 경고로 격리된다.
#
# 3) GST_PLUGIN_FEATURE_RANK — 3D 뷰어와 오디오를 동시에 쓰기 위한 핵심
#    미디어를 켜면 GStreamer 장치 모니터가 CoreAudio 를 프로브하다 교착된다
#    (gst_device_monitor_start → gst_osx_audio_device_provider_probe → gst_core_audio_bind_device).
#    mjpython 이 macOS 메인스레드를 Cocoa GUI 용으로 점유하는데 CoreAudio 장치 조회도
#    메인 런루프를 요구하기 때문이다. 마이크 권한(TCC) 문제가 아니다 —
#    같은 프로브를 일반 python 으로 돌리면 장치 3개가 즉시 잡힌다(실측).
#
#    해결: 교착을 일으키는 것은 *장치 프로바이더*(osxaudiodeviceprovider)이고,
#    실제 입출력 요소(osxaudiosrc/osxaudiosink)는 별개 팩토리다. 프로바이더 랭크만
#    NONE 으로 내리면 장치 모니터가 이를 건너뛰고(GstDeviceMonitor 는 RANK_MARGINAL=64
#    미만을 제외), 오디오 자체는 그대로 동작한다. 카메라 쪽 avfdeviceprovider 도 같다.
#    → 3D 뷰어 + 오디오 + 시뮬 카메라 스트림이 한 프로세스에서 공존한다.
#
# 근거: claudian vault
#   acquired/fetched/reachy-mini-시뮬-macos설치/2026-07-29_시뮬레이션-실행-mjpython-macos함정.md
#   topics/Reachy Mini 시뮬레이터 개발환경 (macOS·2026-07).md
run_sim() {
  source .venv/bin/activate

  export GST_PLUGIN_SCANNER="$PWD/.venv/lib/python3.12/site-packages/gstreamer_libs/libexec/gstreamer-1.0/gst-plugin-scanner"
  export GST_REGISTRY="$PWD/.gst-registry.bin"   # 레지스트리 캐시 — 매 기동 재스캔 방지
  export GST_PLUGIN_FEATURE_RANK="osxaudiodeviceprovider:NONE,avfdeviceprovider:NONE"

  # 인자는 배열에 담지 않고 "$@" 로 바로 넘긴다. macOS 기본 bash 3.2 는 `set -u`
  # 상태에서 빈 배열을 확장하면 죽는다(위치 인자 $@/$* 는 예외).
  echo "▶ mjpython -m reachy_mini.daemon.app.main --sim $*"
  exec mjpython -m reachy_mini.daemon.app.main --sim "$@"
}

# ════════════════════════════════════════════════════════════════
#  demo — 전체 스택 (구 scripts/demo.sh)
# ════════════════════════════════════════════════════════════════
# TTS 는 LLM·STT 와 함께 기본으로 서빙한다(채택 음색 = Qwen3-TTS 화자 'serena').
# macOS 유나로 되돌리려면 TTS_BACKEND=say ./reachy.sh demo
#
# 자산은 아래 표준 위치에서 자동으로 찾는다(3.8GB). 세션 임시 폴더에 두면
# 사라지므로 반드시 영구 경로여야 한다. 옮겼다면 TTS_ASSETS 로 지정한다.
TTS_BACKEND="${TTS_BACKEND:-qwen}"
TTS_PORT="${TTS_QWEN_PORT:-8099}"
TTS_ASSETS="${TTS_ASSETS:-$HOME/.local/share/reachy-mini-tts}"
# **TTS 결과 캐시**(2026-09-25, 계획 docs/superpowers/plans/2026-09-25-tts-result-cache.md).
# 로봇이 부르는 주소(:$TTS_PORT)에는 캐시 프록시가 서고, CrispASR 는 안쪽 포트에 **loopback 으로만**
# 뜬다 — 프록시 말고는 부를 일이 없다. 로봇 설정·앱은 그대로다(주소가 안 바뀐다).
# 캐시는 TTS 자산 옆(저장소 밖) — `./reachy.sh bake` 가 고정 대사를 여기에 굽는다.
TTS_UPSTREAM_PORT="${TTS_QWEN_UPSTREAM_PORT:-8098}"
TTS_CACHE_DIR="${TTS_CACHE_DIR:-$TTS_ASSETS/cache}"
CRISPASR="${CRISPASR_BIN:-$TTS_ASSETS/crispasr-bin/crispasr}"
# CustomVoice 를 쓴다 — 화자 이름으로 음색이 고정된다(VoiceDesign 은 매 요청 달라짐).
#
# 2026-07-30: 0.6B → **1.7B** 로 올렸다. 0.6B 는 모델명 발음이 무너졌다
# (`Whisper Large V3 Turbo` → '위스퍼올라즈', `E4B` → '4A4B',
# `Qwen3-TTS` → '코안슴'). 대본이 모델명을 정확히 읽는 것이 목적이라 품질을 택했다.
TTS_MODEL="${TTS_QWEN_MODEL:-$TTS_ASSETS/models/qwen3-tts-12hz-1.7b-customvoice-q8_0.gguf}"
TTS_CODEC="${TTS_QWEN_CODEC:-$TTS_ASSETS/models/qwen3-tts-tokenizer-12hz.gguf}"

# **백엔드 이름은 모델 크기에 따라 다르다** — 0.6B 는 `qwen3-tts-customvoice`,
# 1.7B 는 `qwen3-tts-1.7b-customvoice` 다. 모델만 바꾸고 이걸 안 바꾸면 기동이 깨진다.
# 파일명에서 유추해 사고를 막는다.
case "$TTS_MODEL" in
  *1.7b-customvoice*) TTS_BACKEND_NAME="qwen3-tts-1.7b-customvoice" ;;
  *)                  TTS_BACKEND_NAME="qwen3-tts-customvoice" ;;
esac
TTS_BACKEND_NAME="${TTS_QWEN_BACKEND:-$TTS_BACKEND_NAME}"

# 서버 기동 시 화자를 못 박는다. 이걸 빼면 서버 기본값이 'aiden' 이 되고,
# voice 필드 없이 들어온 요청은 전부 그 목소리로 나간다(실측). 정본은 tts.py 다.
#
# **쓰는 자리(start_tts·status)에서 처음 한 번 읽는다.** 예전에는 파일 머리에서 읽어
# `logs`·`stop`·`start --dry-run` 같은 파이썬이 필요 없는 명령까지 매번 인터프리터를
# 띄웠다 — dry-run 은 아무것도 건드리지 않아야 한다(tests/test_reachy_start.py).
TTS_VOICE="${TTS_QWEN_VOICE:-}"
resolve_tts_voice() {
  [ -n "$TTS_VOICE" ] && return 0
  TTS_VOICE="$("$PY" -c \
    "import sys;sys.path.insert(0,'apps/voice_chat/voice_chat');import tts;print(tts.qwen_voice())" \
    2>/dev/null || echo serena)"
}

# crispasr 바이너리의 @rpath 는 **빌드 디렉토리를 가리킨다.** 자산 폴더로 복사만
# 하면 dylib 을 옆에 둬도 dyld 가 못 찾아 기동에서 죽는다. 실측으로 겪은 증상:
# 빌드 디렉토리가 지워진 뒤 `Library not loaded: @rpath/libcrispasr.1.dylib` 로
# **조용히** 실패 → 헬스체크 시간초과 → say 폴백. 시연이 엉뚱한 목소리로 돌아간다.
#
# DYLD_LIBRARY_PATH 로는 못 고친다 — macOS SIP 가 `nohup` 같은 보호된 바이너리를
# exec 할 때 DYLD_* 를 전부 지운다(직접 실행은 되고 nohup 경유만 실패해서 헷갈린다).
# 그래서 바이너리에 @loader_path 를 박아 dylib 을 자기 옆에서 찾게 한다.
ensure_crispasr() {
  [ -x "$CRISPASR" ] || return 1
  "$CRISPASR" --version >/dev/null 2>&1 && return 0
  echo "   ${c_dim}dylib 을 못 찾는다 — @loader_path rpath 를 넣어 고친다${c_off}"
  install_name_tool -add_rpath "@loader_path" "$CRISPASR" 2>/dev/null
  "$CRISPASR" --version >/dev/null 2>&1
}

up() { curl -sf --max-time 2 "$1" >/dev/null 2>&1; }

wait_for() {  # url label timeout_s
  local url=$1 label=$2 limit=${3:-120} n=0
  printf "   %s 대기" "$label"
  while ! up "$url"; do
    n=$((n + 1))
    if [ "$n" -ge "$limit" ]; then echo " ${c_bad}시간초과${c_off}"; return 1; fi
    printf "."
    sleep 1
  done
  echo " ${c_ok}준비됨${c_off} (${n}초)"
}

status() {
  up http://localhost:8080/health              && say_ok "LLM  :8080" || say_bad "LLM  :8080"
  up http://localhost:8090/health              && say_ok "STT  :8090" || say_bad "STT  :8090"
  up http://localhost:8000/api/state/full      && say_ok "데몬 :8000" || say_bad "데몬 :8000"
  if [ "$TTS_BACKEND" = "qwen" ]; then
    resolve_tts_voice
    if up "http://localhost:$TTS_PORT/health"; then
      say_ok "TTS  Qwen3(:$TTS_PORT) 화자 $TTS_VOICE"
      tts_cache_status
    else
      say_bad "TTS  Qwen3(:$TTS_PORT)"
      # 안 떠 있으면 바이너리가 실행 가능한지까지 봐준다. dylib 문제는 조용히
      # 실패해 say 폴백으로 넘어가므로, 여기서 짚어주지 않으면 원인을 못 찾는다.
      if [ -x "$CRISPASR" ] && ! "$CRISPASR" --version >/dev/null 2>&1; then
        echo "     ${c_bad}바이너리가 실행되지 않는다${c_off} — dylib rpath 문제다:"
        "$CRISPASR" --version 2>&1 | head -2 | sed 's/^/       /'
        echo "       ${c_dim}기동 시 ensure_crispasr 가 @loader_path 를 넣어 자동 복구한다${c_off}"
      fi
    fi
  else
    say -v '?' | grep -q Yuna                  && say_ok "TTS  Yuna(say)" || say_bad "TTS  Yuna(say)"
  fi
}

kill_pidfile() {  # file label
  local f=$1 label=$2 pid
  [ -f "$f" ] || return 1
  pid=$(cat "$f")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "   $label 종료 (pid $pid)"
  fi
  rm -f "$f"
  return 0
}

# PID 파일만으로는 부족하다 — 손으로 띄운 것, 이전 실행이 남긴 것, PID 파일이
# 지워진 것은 안 잡힌다(실측으로 고아가 남았다). 패턴으로 한 번 더 쓸어낸다.
sweep() {  # pattern label
  local pat=$1 label=$2 pids
  pids=$(pgrep -f "$pat" 2>/dev/null)
  [ -n "$pids" ] || return 0
  echo "   ${c_dim}남은 $label 정리: $(echo $pids | tr '\n' ' ')${c_off}"
  kill $pids 2>/dev/null
  sleep 1
  pids=$(pgrep -f "$pat" 2>/dev/null)
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null   # 안 죽으면 강제
  return 0
}

# 마지막 '세션 시작' 이후만 보여준다. 구분자가 없으면 꼬리만.
last_session() {  # file n
  if grep -q "════════ 세션 시작" "$1"; then
    awk '/════════ 세션 시작/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "$1" | tail -"$2"
  else
    tail -"$2" "$1"
  fi
}

# **기본이 실시간이다.** 로그를 보는 이유는 대개 "지금 무슨 일이 나는지"를 보려는
# 것인데, 한 번 찍고 끝나면 다시 치게 된다. 한 번만 보려면 --no-follow 다.
#
# `start` 세션도 본다. 예전에는 app.log(demo)만 봐서, 시연 한 벌을 `start` 로 띄운 날에는
# "로그부터 읽는다"(CLAUDE.md) 가 빈손이었다 — 감독 출력은 터미널에만, 앱 출력은
# start-app-*.log 에만 있었다.
show_logs() {  # [줄수] [--no-follow]
  local n=80 follow=1 a f
  for a in "$@"; do
    case "$a" in
      --no-follow|-n) follow=0 ;;
      ""|*[!0-9]*)    ;;   # 숫자가 아닌 인자는 무시한다
      *)              n="$a" ;;
    esac
  done
  if [ -f "$APP_LOG" ]; then
    say_step "마지막 세션 (demo 앱) — $APP_LOG"
    last_session "$APP_LOG" "$n"
  fi
  if [ -f "$START_DIRECTOR_LOG" ]; then
    say_step "마지막 start 세션 (무대감독) — $START_DIRECTOR_LOG"
    last_session "$START_DIRECTOR_LOG" "$n"
    for f in "$LOG_DIR/start-app-mc.log" "$LOG_DIR/start-app-docent.log"; do
      [ -f "$f" ] || continue
      say_step "$(basename "$f") 끝부분 ${c_dim}(start 마다 새로 쓴다)${c_off}"
      tail -"$n" "$f"
    done
  fi
  if [ ! -f "$APP_LOG" ] && [ ! -f "$START_DIRECTOR_LOG" ]; then
    echo "   ${c_dim}앱 로그가 없다 — 아직 ./reachy.sh demo 도 start 도 돌린 적이 없다${c_off}"
  fi
  # tts-proxy.log — TTS 결과 캐시 프록시. "고정 대사인데 캐시 키가 다르다"(로봇 설정이 굽기와 달라져
  # 구운 소리가 조용히 안 쓰인다)가 여기에 WARNING 으로 남는다.
  for f in "$LOG_DIR/tts.log" "$LOG_DIR/tts-proxy.log" "$LOG_DIR/sim.log" \
           "$LOG_DIR/start-daemon-mc.log" "$LOG_DIR/start-daemon-docent.log"; do
    [ -f "$f" ] || continue
    say_step "$(basename "$f") 끝부분"
    grep -iE "error|traceback|경고|실패|warn" "$f" | tail -10 || tail -5 "$f"
  done

  [ "$follow" = "1" ] || return 0
  # 더 최근에 돈 쪽을 따라간다. app.log 가 없으면 `-nt` 는 참이다.
  if [ -f "$START_DIRECTOR_LOG" ] && [ "$START_DIRECTOR_LOG" -nt "$APP_LOG" ]; then
    set -- "$START_DIRECTOR_LOG"
    for f in "$LOG_DIR/start-app-mc.log" "$LOG_DIR/start-app-docent.log"; do
      [ -f "$f" ] && set -- "$@" "$f"
    done
    say_step "실시간 (start: 감독·앱) — 새 줄이 나오는 대로 이어 붙는다 ${c_dim}(Ctrl-C 로 종료)${c_off}"
    tail -f "$@"
  elif [ -f "$APP_LOG" ]; then
    say_step "실시간 — 새 줄이 나오는 대로 이어 붙는다 ${c_dim}(Ctrl-C 로 종료)${c_off}"
    tail -f "$APP_LOG"
  fi
}

stop_all() {
  say_step "종료"
  kill_pidfile "$TTS_PROXY_PID_FILE" "TTS 캐시 프록시"
  kill_pidfile "$TTS_PID_FILE" "TTS 서버"
  kill_pidfile "$SIM_PID_FILE" "시뮬 데몬"
  "$LLAMACTL" stop
  # llamactl 이 관리하지 않는 것 + 고아. 시뮬 데몬을 PID 파일로만 잡으면
  # 손으로 띄운 것이 살아남는다(실측: `stop` 후에도 :8000 이 응답했다).
  sweep "crispasr --server"            "CrispASR"
  sweep "tts_cache_proxy.py"           "TTS 캐시 프록시"
  sweep "stt_server.py"                "STT 서버"
  sweep "reachy_mini.daemon.app.main"  "시뮬 데몬"
  # 아래 둘은 `demo`/`sim` 이 띄우는 것이 아니라 **따로 붙어 사는 것들**이라
  # 예전 목록에서 빠져 있었다. 실측으로 `reachy-mini-mcp` 가 19시간 떠 있었다.
  sweep "mjpython -m reachy_mini"      "mjpython 데몬"
  sweep "reachy-mini-mcp"              "MCP 서버"
  # `start --sim` 이 뒤로 띄운 앱 2대. 보통은 `start` 의 trap 이 내리지만, 그 셸이 kill -9
  # 로 죽거나 터미널째 날아가면 trap 이 못 돈다 — 앱이 마이크를 쥔 채 남는다. 예전에는
  # `scripts/sim2.sh stop` 이 이 자리였다(모의 데몬은 위의 daemon.app.main 이 쓸어낸다).
  sweep "$APP_PROC_PAT" "앱"
  # ~~start-{daemon,app}-<역할>.pid~~ — `start --sim` 이 쓰기만 하고 아무도 안 읽어서 없앴다(최종
  # 리뷰 M6). `stop` 이 그 pid 로 죽이게 하는 길도 있었지만, 위 두 sweep(데몬 `daemon.app.main`·
  # 앱 $APP_PROC_PAT)이 이미 같은 프로세스를 잡고, 낡은 pid 파일은 **재사용된 남의 pid** 를 죽일
  # 수 있다(kill_pidfile 은 그 pid 가 무엇인지 안 본다). 예전 실행이 남긴 파일만 치운다.
  rm -f "$LOG_DIR"/start-*.pid
}

# **최상위 `stop` 전용이다 — `robot_down` 은 안 부른다.** `robot down` 도 `stop_all` 을 지나는데,
# 시연 중 한 대를 내렸다 올리려다 옆 터미널의 감독 콘솔까지 죽이면 안 된다(원래 `start_ports_free`
# 의 경고가 이 이유로 8777/8778 을 stop 이 안 건드린다고 했다). 하지만 운영자가 **직접**
# `./reachy.sh stop` 을 친 것은 "전부 내려라" 는 뜻이므로, 그 경로에서만 감독·대시보드도 함께
# 쓸어낸다. 패턴(`python -m stage`, `-u` 유무 상관없이 끝이 `-m stage`)과 포트(8777/8778) 둘 다
# 본다 — 패턴이 못 잡는 변형 실행도 포트 쪽이 잡는다.
stop_director_dashboard() {
  sweep "[-]m stage$" "무대감독"
  local p pid
  for p in 8777 8778; do
    pid=$(lsof -tnP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null)
    [ -n "$pid" ] || continue
    echo "   ${c_dim}:$p 를 쥔 것 정리: $pid${c_off}"
    kill $pid 2>/dev/null
  done
}

# 앱 프로세스를 찾는 패턴 — **파이썬이 그 파일을 돌리는 것만.** 경로만 보면 `pgrep -f` 가
# argv 어디든 그 경로가 든 프로세스를 잡는다(그 파일을 연 `vim` 까지). sweep 은 안 죽으면
# kill -9 로 올리므로 편집 중인 버퍼가 날아간다. `robot down`·`demo --exit-clean` 도 여기를 지난다.
# (pgrep 의 패턴은 확장 정규식이다 — tests/test_reachy_start.py 가 grep -E 로 같은 식을 본다.)
APP_PROC_PAT='python[^ ]* .*apps/voice_chat/voice_chat/main\.py'

# 기동 도중 Ctrl-C 나 실패로 빠져나갈 때, **이 실행이 띄운 것만** 정리한다.
STARTED_TTS=0
cleanup_partial() {
  [ "$STARTED_TTS" = "1" ] || return 0
  echo
  echo "   ${c_dim}기동이 끝나지 않아 이 실행이 띄운 TTS 서버를 정리한다${c_off}"
  kill_pidfile "$TTS_PROXY_PID_FILE" "TTS 캐시 프록시"
  kill_pidfile "$TTS_PID_FILE" "TTS 서버"
  STARTED_TTS=0
}

# ── 추론 3종 기동 ────────────────────────────────────────────────
# demo(시뮬 전체 스택)와 serve(실기용 서버만)가 **같은 코드를 쓴다.** 갈라 두면
# 한쪽만 고쳐지고 시연장에서 어긋난다 — main.py 가 생성 템플릿인 채로 방치됐던
# 것과 같은 종류의 사고다.

# 이미 떠 있는 서버가 BIND_HOST 로 **실제로** 듣는지 두드릴 주소를 준다.
#
# 0.0.0.0 은 두드릴 주소가 아니다 — macOS·리눅스는 0.0.0.0 으로의 connect 를 loopback 으로
# 보내서, loopback 전용으로 떠 있는 서버도 "0.0.0.0 에서 응답한다" 로 보인다. 예전 가드가
# 그랬다: `start --sim`(loopback)으로 띄워 남겨 둔 서버를 `start --robot`·`robot up` 이 그대로
# 재사용하고, 로봇마다 ":8080 — 로봇에서 안 보인다" 로 떨어져 원인이 방화벽처럼 보였다
# (리뷰 I2). LAN 주소로 두드려야 가려진다. 주소를 못 찾으면 1 — 확인을 못 했다고 말한다.
bind_probe_addr() {
  if [ "$BIND_HOST" = "0.0.0.0" ]; then lan_ip; else echo "$BIND_HOST"; fi
}

# 떠 있는 서버(포트들)가 BIND_HOST 로 듣는지. 0 = 듣는다(또는 loopback 바인드라 볼 것이 없다).
already_up_binds_right() {  # label port...
  local label="$1" addr p; shift
  [ "$BIND_HOST" = "127.0.0.1" ] && return 0
  if ! addr="$(bind_probe_addr)" || [ -z "$addr" ]; then
    say_warn "LAN 주소를 못 찾아, 떠 있는 $label 가 $BIND_HOST 로 듣는지 확인하지 못했다"
    return 0
  fi
  for p in "$@"; do
    up "http://$addr:$p/health" && continue
    say_bad "이미 떠 있는 $label 가 $BIND_HOST 로 듣지 않는다 (loopback 전용 — $addr:$p 무응답) — ./reachy.sh stop 후 다시"
    return 1
  done
}

start_llm_stt() {
  say_step "LLM(:8080) · STT(:8090) — bind $BIND_HOST"
  if up http://localhost:8080/health && up http://localhost:8090/health; then
    # 떠 있다고 원하는 주소로 듣는다는 보장이 없다. loopback 으로 떠 있던 것을
    # 그대로 두면 로봇에서 조용히 못 붙는다.
    already_up_binds_right "LLM/STT" 8080 8090 || return 1
    echo "   ${c_dim}이미 떠 있다 — 건너뛴다${c_off}"
    return 0
  fi
  [ -x "$LLAMACTL" ] || { say_bad "$LLAMACTL 을 찾을 수 없다"; return 1; }
  # llamactl 은 `--host 127.0.0.1` 을 박아 두고 STT 에는 --host 를 아예 안 넘겼다.
  # LLM_HOST/STT_HOST 를 읽도록 고쳐 뒀다(기본값은 그대로 127.0.0.1).
  #
  # REACH_HOME 도 함께 넘긴다 — llamactl 의 기본값 ~/workspace/reach-mini 는
  # **존재하지 않는 경로**라 STT 가 "python 없음" 으로 죽는다. 이 저장소가 그 자리다.
  # 사용자가 환경변수로 지정했으면 그쪽이 이긴다.
  #
  # STT_PYTHON 은 절대경로여야 한다(llamactl 이 다른 디렉토리에서 부른다). PY 가 이미
  # 절대경로면(REACHY_PY) 앞에 $PWD 를 붙이면 `/repo//opt/…` 로 깨진다.
  local py_abs="$PY"
  case "$PY" in /*) ;; *) py_abs="$PWD/$PY" ;; esac
  REACH_HOME="${REACH_HOME:-$PWD}" \
  STT_PYTHON="${STT_PYTHON:-$py_abs}" \
  STT_SERVER="${STT_SERVER:-$PWD/stt_server.py}" \
  LLM_HOST="$BIND_HOST" STT_HOST="$BIND_HOST" \
    "$LLAMACTL" reach-llm || { say_bad "LLM/STT 기동 실패"; llm_stt_log_hint; return 1; }
  wait_for http://localhost:8080/health "LLM" 120 || { llm_stt_log_hint; return 1; }
  wait_for http://localhost:8090/health "STT" 180 || { llm_stt_log_hint; return 1; }   # 모델 예열이 오래 걸린다
}

# llamactl 로그 안내는 **기동이 실패한 자리에서만** 찍는다. 예전에는 start_infer 가 실패 이유와
# 상관없이 끝에 붙여서, 거절(loopback 전용으로 떠 있다·llamactl 없음 — 이유를 이미 찍었다) 뒤에도
# "로그: /tmp/llamactl…" 이 나와 엉뚱한 로그를 뒤지게 했다(최종 리뷰 M9). 경로는 llamactl.sh 의
# LOGFILE/STT_LOGFILE 이다.
llm_stt_log_hint() {
  echo "   ${c_dim}로그: /tmp/llamactl-8080.log (LLM) · /tmp/llamactl-stt-8090.log (STT)${c_off}"
}

start_tts() {
  if [ "$TTS_BACKEND" = "qwen" ]; then
    resolve_tts_voice
    say_step "TTS 서버(:$TTS_PORT) — Qwen3-TTS, bind $BIND_HOST"
    if up "http://localhost:$TTS_PORT/health"; then
      already_up_binds_right "TTS" "$TTS_PORT" || return 1
      echo "   ${c_dim}이미 떠 있다 — 건너뛴다${c_off}"
      tts_proxy_marker_check
    elif [ ! -x "$CRISPASR" ] || [ ! -f "$TTS_MODEL" ] || [ ! -f "$TTS_CODEC" ]; then
      # 자산이 없다고 시연을 막지 않는다 — say 로 물러나 계속 진행한다
      say_bad "TTS 자산을 찾을 수 없다: $TTS_ASSETS"
      [ -x "$CRISPASR" ]   || echo "   없음: $CRISPASR"
      [ -f "$TTS_MODEL" ]  || echo "   없음: $TTS_MODEL"
      [ -f "$TTS_CODEC" ]  || echo "   없음: $TTS_CODEC"
      echo "   ${c_dim}→ 유나(say) 목소리로 계속 진행한다${c_off}"
      TTS_BACKEND=say
    elif ! ensure_crispasr; then
      say_bad "crispasr 바이너리가 실행되지 않는다 (dylib 문제를 자동 복구하지 못했다)"
      "$CRISPASR" --version 2>&1 | head -3 | sed 's/^/   /'
      echo "   ${c_dim}→ 유나(say) 목소리로 계속 진행한다${c_off}"
      TTS_BACKEND=say
    else
      # CrispASR 는 **안쪽 포트에 loopback 으로만** — 로봇은 프록시(:$TTS_PORT)를 부른다.
      # 안쪽이 이미 살아 있으면(프록시만 죽었던 경우) 그대로 쓴다.
      if ! up "http://127.0.0.1:$TTS_UPSTREAM_PORT/health"; then
        echo "   기동 중 ($TTS_BACKEND_NAME, 화자 $TTS_VOICE, 안쪽 :$TTS_UPSTREAM_PORT)... 로그: $LOG_DIR/tts.log"
        start_crispasr 127.0.0.1 "$TTS_UPSTREAM_PORT"
        STARTED_TTS=1   # 기동 실패 시 trap 이 이것만 보고 정리한다
        if ! wait_for "http://127.0.0.1:$TTS_UPSTREAM_PORT/health" "TTS" 90; then
          say_bad "TTS 서버 기동 실패 — tail -30 $LOG_DIR/tts.log"
          echo "   ${c_dim}→ 유나(say) 목소리로 계속 진행한다${c_off}"
          TTS_BACKEND=say
          return 0
        fi
      fi
      if ! start_tts_proxy; then
        # **캐시만 꺼진 원래 구성으로 물러난다 — 소리 내서.** 프록시가 못 뜬다고 시연을 막지
        # 않는다: CrispASR 를 예전처럼 로봇이 부르는 주소에 직접 띄운다(구운 대사가 안 쓰일 뿐).
        say_bad "TTS 캐시 프록시가 뜨지 않았다 — tail -20 $LOG_DIR/tts-proxy.log"
        echo "   ${c_dim}→ 캐시 없이 CrispASR 를 :$TTS_PORT 에 직접 띄운다(예전 구성)${c_off}"
        kill_pidfile "$TTS_PROXY_PID_FILE" "TTS 캐시 프록시"
        kill_pidfile "$TTS_PID_FILE" "TTS 서버"
        start_crispasr "$BIND_HOST" "$TTS_PORT"
        if ! wait_for "http://localhost:$TTS_PORT/health" "TTS" 90; then
          say_bad "TTS 서버 기동 실패 — tail -30 $LOG_DIR/tts.log"
          echo "   ${c_dim}→ 유나(say) 목소리로 계속 진행한다${c_off}"
          TTS_BACKEND=say
        fi
      fi
    fi
  fi
}

# CrispASR 서버 하나를 띄운다(PID 는 $TTS_PID_FILE). 호스트·포트만 다르다 — 보통은 안쪽
# loopback, 프록시 폴백 때만 로봇이 부르는 주소.
start_crispasr() {
  nohup "$CRISPASR" --server --host "$1" --port "$2" --backend "$TTS_BACKEND_NAME" \
    -m "$TTS_MODEL" --codec-model "$TTS_CODEC" --voice "$TTS_VOICE" \
    > "$LOG_DIR/tts.log" 2>&1 &
  echo $! > "$TTS_PID_FILE"
}

# 캐시 프록시를 로봇이 부르는 주소에 띄운다. /health 는 안쪽이 살아 있을 때만 200 이라
# 기다림이 곧 "프록시 + CrispASR 둘 다 선다" 의 확인이다.
start_tts_proxy() {
  echo "   캐시 프록시 :$TTS_PORT → 안쪽 :$TTS_UPSTREAM_PORT ${c_dim}(캐시 $TTS_CACHE_DIR · 로그 $LOG_DIR/tts-proxy.log)${c_off}"
  nohup "$PY" -u tts_cache_proxy.py --host "$BIND_HOST" --port "$TTS_PORT" \
    --upstream "http://127.0.0.1:$TTS_UPSTREAM_PORT" --cache-dir "$TTS_CACHE_DIR" \
    > "$LOG_DIR/tts-proxy.log" 2>&1 &
  echo $! > "$TTS_PROXY_PID_FILE"
  wait_for "http://localhost:$TTS_PORT/health" "TTS 캐시 프록시" 20
}

# :$TTS_PORT 가 이미 떠 있을 때 — 프록시인가, 예전처럼 CrispASR 가 직접 떠 있나.
# 직접이면 시연은 되지만 구운 대사가 **조용히** 안 쓰인다. 그래서 말한다.
tts_proxy_marker_check() {
  if curl -s -m 3 "http://localhost:$TTS_PORT/health" 2>/dev/null | grep -q '"proxy"'; then
    tts_cache_status
  else
    say_warn "TTS(:$TTS_PORT) 가 캐시 프록시 없이 떠 있다(예전 구성) — 구운 대사가 안 쓰인다. ./reachy.sh stop 후 다시 띄운다"
  fi
}

# 캐시 적중 현황 한 줄 — 합성 없이 센다. 비었으면 bake 를 권한다(`scripts/bake_tts.py --check`).
tts_cache_status() {
  "$PY" scripts/bake_tts.py --check --cache-dir "$TTS_CACHE_DIR" 2>&1 | sed 's/^/   /'
}

# ── serve — 실기(Wireless) 구성 ─────────────────────────────────
# **앱은 로봇 위에서 돌고 추론 3종만 이 PC 에 남는다.** 그래서 시뮬 데몬도 앱도
# 띄우지 않는다. 로봇이 닿아야 하므로 이 모드만 기본 바인드가 0.0.0.0 이다.
run_serve() {
  BIND_HOST="${REACHY_BIND_HOST:-0.0.0.0}"

  trap 'cleanup_partial; exit 130' INT TERM
  start_llm_stt || exit 1
  start_tts
  STARTED_TTS=0        # 여기부터는 기동이 끝났다 — 서버를 남겨 두는 것이 정상이다
  trap - INT TERM

  say_step "상태"
  status

  # 로봇에 넣을 주소를 **직접 만들어 준다.** 손으로 IP 를 옮겨 적다 틀리면
  # 앱은 기본값(loopback)으로 붙어 조용히 벙어리가 된다(§10).
  local lan_ip=""
  local i
  for i in en0 en1 en7; do
    lan_ip="$(ipconfig getifaddr "$i" 2>/dev/null || true)"
    [ -n "$lan_ip" ] && break
  done
  echo
  if [ -z "$lan_ip" ]; then
    say_bad "이 맥의 LAN 주소를 찾지 못했다 — Wi-Fi 가 켜져 있는지 확인한다"
    exit 1
  fi
  say_step "로봇에 넣을 설정 — /home/pollen/.config/reachy-mini-voice-chat/config.json"
  cat <<JSON
{
  "REACHY_LLM_URL": "http://$lan_ip:8080",
  "REACHY_STT_URL": "http://$lan_ip:8090/v1/audio/transcriptions",
  "TTS_QWEN_URL":   "http://$lan_ip:$TTS_PORT/v1/audio/speech"
}
JSON
  echo
  echo "${c_dim}서버는 계속 떠 있다. 내리려면 ./reachy.sh stop${c_off}"
}

run_demo() {
  trap 'cleanup_partial; exit 130' INT TERM

  local EXIT_CLEAN=0 WANT_ROBOT=1
  local MODE_ARGS=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --exit-clean) EXIT_CLEAN=1 ;;
      --no-robot)   WANT_ROBOT=0; MODE_ARGS+=("$1") ;;
      --text)       MODE_ARGS+=("$1") ;;
      --scene)      SCENE="$2"; shift ;;
      *)            say_bad "모르는 인자: $1"; usage; exit 2 ;;
    esac
    shift
  done

  # ── 1. LLM + STT ──────────────────────────────────────────────
  start_llm_stt || exit 1

  # ── 2. 시뮬레이터 데몬 ────────────────────────────────────────
  say_step "시뮬레이터 데몬(:8000)"
  if [ "$WANT_ROBOT" = "0" ]; then
    echo "   ${c_dim}--no-robot 이므로 건너뛴다${c_off}"
  elif up http://localhost:8000/api/state/full; then
    echo "   ${c_dim}이미 떠 있다 — 건너뛴다${c_off}"
  else
    echo "   3D 뷰어 창이 뜬다. 로그: $LOG_DIR/sim.log"
    nohup "$SELF" sim --scene "$SCENE" > "$LOG_DIR/sim.log" 2>&1 &
    echo $! > "$SIM_PID_FILE"
    if ! wait_for http://localhost:8000/api/state/full "데몬" 120; then
      say_bad "데몬 기동 실패 — tail -30 $LOG_DIR/sim.log 로 확인"
      tail -15 "$LOG_DIR/sim.log"
      exit 1
    fi
  fi

  # ── 3. TTS 서버 ───────────────────────────────────────────────
  start_tts
  export TTS_BACKEND   # 앱(main.py/demo.py)이 같은 백엔드를 쓰도록 물려준다

  # ── 4. 예열 ───────────────────────────────────────────────────
  # 첫 질문이 느려지지 않도록 LLM·TTS·STT·모션 경로를 한 번씩 태운다.
  # LLM 은 반드시 앱과 같은 시스템 블록으로 태워야 프리픽스 캐시가 맞는다.
  say_step "예열"
  $PY scripts/warmup.py || echo "   ${c_dim}일부 예열을 건너뛰었다 — 첫 응답이 느릴 수 있다${c_off}"

  # ── 5. 최종 점검 후 앱 진입 ───────────────────────────────────
  say_step "최종 점검"
  status
  echo
  if [ "$WANT_ROBOT" = "1" ] && ! up http://localhost:8000/api/state/full; then
    say_bad "데몬이 없다. --no-robot 으로 대화만 하거나 로그를 확인한다"
    exit 1
  fi

  # 정상 경로는 **실기와 같은 진입점(main.py = ReachyMiniApp)** 으로 띄운다.
  # 시연에서 돌리는 것과 로봇에 배포하는 것을 같게 두려는 것이다 — 예전에는 데모가
  # demo.py 만 태워서, main.py 가 생성 템플릿인 채로 방치된 것을 아무도 몰랐다.
  #
  # --text / --no-robot 은 ReachyMiniApp 이 표현할 수 없는 폴백이라(프레임워크가
  # ReachyMini 를 무조건 잡는다) demo.py 로 내린다. 대화 로직은 둘 다 session.py 다.
  if [ ${#MODE_ARGS[@]} -eq 0 ]; then
    say_step "음성 모드 — 말을 걸어보세요 (Ctrl-C 종료)"
    echo "   ${c_dim}로봇이 대답을 끝낸 뒤에 다음 말을 한다 (한 번에 한 사람씩)${c_off}"
    echo "   ${c_dim}진입점: main.py (실기와 동일)${c_off}"
  else
    say_step "실행: demo.py ${MODE_ARGS[*]} ${c_dim}(폴백 모드)${c_off}"
  fi
  echo

  # 여기부터는 기동이 끝났다 — Ctrl-C 는 앱을 나가는 뜻이므로 부분정리를 끈다.
  STARTED_TTS=0
  trap - INT TERM

  # macOS 기본 bash 는 3.2 다. set -u 아래에서 원소 0개인 배열을 "${A[@]}" 로 펼치면
  # unbound variable 로 죽는다(bash 4.4 부터 고쳐진 동작). 빈 경우를 아예 분기한다.
  # 앱 출력을 파일로도 남긴다. 사용자가 붙여넣지 않아도 마지막 세션을 읽고
  # 무엇이 잘못됐는지 확인할 수 있어야 한다(./reachy.sh logs).
  #
  # PYTHONUNBUFFERED 가 없으면 stdout 이 파이프가 되는 순간 블록 버퍼링으로 바뀌어
  # 터미널에 아무것도 안 보인다 — flush=True 를 안 붙인 print 가 섞여 있다.
  export PYTHONUNBUFFERED=1
  # 무한정 쌓이지 않게 — 2MB 넘으면 한 세대만 남기고 넘긴다
  if [ -f "$APP_LOG" ] && [ "$(wc -c < "$APP_LOG")" -gt 2000000 ]; then
    mv "$APP_LOG" "$APP_LOG.1"
  fi
  {
    echo
    echo "════════ 세션 시작 $(date '+%Y-%m-%d %H:%M:%S') ════════"
    echo "인자: ${MODE_ARGS[*]:-(음성 모드)}  |  TTS_BACKEND=$TTS_BACKEND"
    echo "환경: REACHY_AEC=${REACHY_AEC:-0} REACHY_BARGE_IN=${REACHY_BARGE_IN:-0}" \
         "MIC_GAIN=${REACHY_MIC_GAIN:-1.0} RMS=${REACHY_BARGE_IN_RMS:-기본}" \
         "FRAMES=${REACHY_BARGE_IN_FRAMES:-기본} WAKE=${REACHY_BARGE_IN_WAKE:-기본}"
  } >> "$APP_LOG"

  if [ ${#MODE_ARGS[@]} -eq 0 ]; then
    $PY apps/voice_chat/voice_chat/main.py 2>&1 | tee -a "$APP_LOG"
  else
    $PY apps/voice_chat/voice_chat/demo.py "${MODE_ARGS[@]}" 2>&1 | tee -a "$APP_LOG"
  fi
  echo "════════ 세션 종료 $(date '+%Y-%m-%d %H:%M:%S') ════════" >> "$APP_LOG"

  if [ "$EXIT_CLEAN" = "1" ]; then
    stop_all
    echo
    echo "${c_dim}--exit-clean 이므로 서버까지 내렸다.${c_off}"
  else
    echo
    echo "${c_dim}서버는 계속 떠 있다. 다시 들어가려면 ./reachy.sh demo, 완전 종료는 ./reachy.sh stop${c_off}"
    echo "${c_dim}앱과 서버를 한 번에 내리려면 ./reachy.sh demo --exit-clean${c_off}"
  fi
}


# ════════════════════════════════════════════════════════════════
#  robot — 실기(Reachy Mini Wireless) 운영
# ════════════════════════════════════════════════════════════════
# 실기는 **앱만 로봇에서 돌고 추론 3종은 이 맥에 남는다.** 그래서 기동이 두 곳에
# 걸쳐 있고, 순서를 틀리면 조용히 실패한다:
#   · config 를 안 맞추면 앱이 기본값 loopback 으로 붙어 벙어리가 된다(§10)
#   · 예열을 빠뜨리면 첫 발화가 2.5초 늦는다(실측: 2.5k 토큰 프롬프트 기준)
#   · 예열은 **앱과 같은 프롬프트**여야 한다 — 해설 모드면 REACHY_PROMPT 를 준다
# 그 순서를 손으로 기억하지 않게 여기 묶어 둔다.
ROBOT_HOST="${REACHY_ROBOT_HOST:-reachy-mini.local}"
ROBOT_USER="${REACHY_ROBOT_USER:-pollen}"
ROBOT_APP="${REACHY_ROBOT_APP:-voice_chat}"
ROBOT_SITE="/venvs/apps_venv/lib/python3.12/site-packages/$ROBOT_APP"
ROBOT_CFG="/home/$ROBOT_USER/.config/reachy-mini-voice-chat/config.json"
ROBOT_API="http://$ROBOT_HOST:8000"

rssh() { ssh -o BatchMode=yes -o ConnectTimeout=10 "$ROBOT_USER@$ROBOT_HOST" "$@"; }
rget() { curl -s -m "${2:-10}" "$ROBOT_API$1"; }
rpost() { curl -s -m "${2:-30}" -X POST "$ROBOT_API$1"; }

# 맥의 LAN 주소. 로봇이 이 주소로 추론 3종에 붙는다.
lan_ip() {
  local i
  for i in en0 en1 en7; do
    ipconfig getifaddr "$i" 2>/dev/null && return 0
  done
  return 1
}

robot_reachable() {
  if ! ping -c 1 -W 2000 "$ROBOT_HOST" >/dev/null 2>&1; then
    say_bad "로봇($ROBOT_HOST)이 안 잡힌다 — 전원·Wi-Fi 를 확인한다"
    return 1
  fi
  up "$ROBOT_API/api/daemon/status" || { say_bad "데몬 API 가 응답하지 않는다"; return 1; }
  return 0
}

# **config 를 매번 맞춘다.** 망이 바뀌면 맥 IP 가 달라지는데, 로봇의 config 는
# 그대로라 앱이 죽은 주소로 붙는다. 실제로 그 실패를 두 번 겪었다.
# 기존 키(REACHY_VAD_FACTOR 등)는 보존하고 주소·프롬프트·역할만 갱신한다.
#
# **2대 구성의 REACHY_ROLE 도 여기로 간다.** 로봇의 앱은 데몬이 낳는 자식이라
# 운영자 셸의 export 가 닿지 않는다 — `source scripts/stage-env.sh mc` 를 해도
# 로봇 위의 앱은 그 값을 못 본다. 파일 단이 실기에서 유일하게 닿는 길이다.
#
#   REACHY_ROLE=mc ./reachy.sh robot up        # 사회자 로봇
#   REACHY_ROLE=docent REACHY_ROBOT_HOST=192.168.0.5 ./reachy.sh robot up
#
# 병합 로직은 scripts/robot_config_merge.py 에 있다 — 테스트로 박제하기 위해서다.
robot_sync_config() {
  local ip="$1" cur new
  cur="$(rssh "cat '$ROBOT_CFG' 2>/dev/null || echo '{}'")"
  new="$(printf '%s' "$cur" | LANIP="$ip" TTSPORT="$TTS_PORT" \
    PROMPTSEL="${REACHY_PROMPT:-}" ROLESEL="${REACHY_ROLE:-}" \
    DIRURL="${REACHY_DIRECTOR_URL:-}" DIRPORT="${REACHY_DIRECTOR_PORT:-8777}" \
    "$PY" scripts/robot_config_merge.py)" || return 1
  printf '%s\n' "$new" | rssh "mkdir -p '$(dirname "$ROBOT_CFG")' && cat > '$ROBOT_CFG'" || return 1
  echo "   ${c_dim}$(printf '%s' "$new" | tr -d '\n ' | cut -c1-100)…${c_off}"
}

robot_status() {
  say_step "실기 상태 ($ROBOT_HOST)"
  rget /api/daemon/status | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("   데몬 응답 없음"); raise SystemExit
b = d.get("backend_status") or {}
s = b.get("control_loop_stats") or {}
print("   데몬 %s | 백엔드 %s | 모터 %s | %s Hz | nb_error %s"
      % (d.get("state"), b.get("ready"), b.get("motor_control_mode"),
         round(s.get("mean_control_loop_frequency", 0), 1), s.get("nb_error")))
print("   미디어 released=%s | wlan %s | ver %s"
      % (d.get("media_released"), d.get("wlan_ip"), d.get("version")))'
  rget /api/apps/current-app-status | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = None
print("   앱 %s" % ("(없음)" if not d else "%s -> %s%s"
      % (d["info"]["name"], d["state"], "  err: %s" % d["error"] if d.get("error") else "")))'
}

# 일회성 — `robot up` 이 마지막에 부른다. 여기서 팔로우로 바꾸면 기동이 안 끝난다.
robot_logs() {
  local n=${1:-40}
  say_step "실기 앱 로그 (마지막 $n 줄)"
  # 데몬 로그는 HTTP 접근 로그로 시끄럽다 — 앱 출력만 추린다.
  rssh "sudo journalctl -u reachy-mini-daemon -n 400 --no-pager 2>/dev/null" \
    | sed -n 's/.*manager\.runner - [A-Z]* - //p' \
    | grep -vE 'onnxruntime|pa_linux_alsa|PaAlsa' | tail -"$n"
}

# 사람이 치는 경로. **기본이 실시간이다.**
# 필터를 파이프로 물리면 블록 버퍼링에 걸려 새 줄이 한참 뒤에야 나온다 —
# `sed -u`·`grep --line-buffered` 로 줄 단위로 흘린다(로봇은 GNU coreutils 다).
# `ssh -t` 는 Ctrl-C 가 원격 journalctl 까지 닿게 한다.
robot_logs_follow() {
  local n=40 follow=1 a
  for a in "$@"; do
    case "$a" in
      --no-follow|-n) follow=0 ;;
      ""|*[!0-9]*)    ;;
      *)              n="$a" ;;
    esac
  done
  [ "$follow" = "1" ] || { robot_logs "$n"; return; }
  say_step "실기 앱 로그 — 실시간 ${c_dim}(Ctrl-C 로 종료)${c_off}"
  ssh -t -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=20 \
    "$ROBOT_USER@$ROBOT_HOST" \
    "sudo journalctl -u reachy-mini-daemon -n $n -f --no-pager 2>/dev/null \
       | sed -u -n 's/.*manager\.runner - [A-Z]* - //p' \
       | grep --line-buffered -vE 'onnxruntime|pa_linux_alsa|PaAlsa'"
}

# **완전 정리가 기본이다.** 로봇 앱만 내리면 맥의 추론 3종(모델이 올라가 있어 RAM 을
# 크게 문다)과 MCP 서버가 남는다. 시연이 끝났는데 남아 있으면 다음 사람이 원인을
# 못 찾는다. 서버를 살려 두고 앱만 재시작할 때는 --keep-servers 다
# (모델 재적재 + 예열이 10초 넘게 걸리므로 반복 배포 중에는 이쪽이 낫다).
robot_down() {
  local keep=0 a
  for a in "$@"; do [ "$a" = "--keep-servers" ] && keep=1; done

  rpost /api/apps/stop-current-app 25 >/dev/null 2>&1
  say_ok "로봇 앱 정지"
  robot_status

  if [ "$keep" = "1" ]; then
    echo
    echo "   ${c_dim}--keep-servers — 맥 추론 3종은 살려 둔다${c_off}"
    return 0
  fi
  stop_all
}

robot_deploy() {
  say_step "실기 배포"
  robot_reachable || return 1
  rpost /api/apps/stop-current-app 25 >/dev/null 2>&1
  # 소스와 설치본을 **둘 다** 민다. 소스는 재설치용, 설치본은 지금 도는 것.
  # (공식 development_workflow: site-packages 에는 안쪽 패키지만 넣는다)
  #
  # `--delete-excluded` 가 필요하다. `--delete` 만 쓰면 rsync 가 **제외한 파일을
  # 수신 측에서 보호해서** 안 지운다 — 첫 배포 때 올라간 build/ 와 egg-info/ 가
  # 로봇에 그대로 남아 있었다(build/lib/build/lib/… 로 중첩된 것까지, 옛 prompt.md
  # 사본 포함). 그 상태로 재설치하면 낡은 산출물을 집을 수 있다.
  rsync -az --delete --delete-excluded \
    --exclude '__pycache__/' --exclude 'build/' --exclude '*.egg-info/' \
    apps/voice_chat/ "$ROBOT_USER@$ROBOT_HOST:/home/$ROBOT_USER/voice_chat/" || return 1
  # 설치본도 --delete 다. 안 그러면 이름을 바꾸거나 지운 모듈이 로봇에 남아
  # 계속 임포트된다 — 고쳤는데 안 고쳐진 것처럼 보이는 종류의 사고다.
  rsync -az --delete --exclude '__pycache__/' \
    apps/voice_chat/voice_chat/ "$ROBOT_USER@$ROBOT_HOST:$ROBOT_SITE/" || return 1
  # 바이트코드를 안 지우면 고친 코드가 안 먹는다(공식 문서의 함정 목록).
  rssh "find '$ROBOT_SITE' -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true"
  say_ok "소스·설치본 동기화"
}

# 오늘 실제로 밟은 장애를 순서대로 자동화한다. 각 단계는 앞 단계가 실패했을 때만 의미가 있다.
robot_fix() {
  say_step "실기 복구 사다리"
  robot_reachable || return 1
  rpost /api/apps/stop-current-app 25 >/dev/null 2>&1

  echo "   1) 백엔드 기동 (죽어 있으면 살린다)"
  rpost "/api/daemon/start?wake_up=true" 90 >/dev/null 2>&1
  sleep 12
  if ! rget /api/daemon/status | grep -q '"state":"running"'; then
    echo "   2) 데몬 완전 재시작 — 미디어 스택이 꼬였을 때의 공식 처방"
    rssh "sudo systemctl restart reachy-mini-daemon" || return 1
    echo "      ${c_dim}45초 대기${c_off}"; sleep 45
  fi
  # **순서가 중요하다**: 모터가 꺼진 상태에서 wake_up 을 재생하면 헛돈다(robot_wake).
  # 앱은 다시 띄우지 않는다 — 위에서 멈췄다. 앱까지 살리려면 `robot up`.
  echo "   3) 모터 활성화 → wake_up"
  robot_wake
  robot_status
}

# ── 0. 백엔드 상태 — 죽어 있으면 여기서 고친다 ─────────────────
# 예전에는 이 검사가 없어서, 백엔드가 죽은 로봇에 서버를 띄우고 config 를 맞추고
# 예열까지 다 한 다음 앱을 띄우고 나서야 실패했다(실측 2026-09-09). 헛일을
# 하지 않고, 고칠 수 있으면 여기서 고친다. 고치지 못하면 1 — 부르는 쪽이 멈출지
# (robot up) 그 로봇만 건너뛸지(start --robot) 정한다.
robot_backend_ready() {
  rget /api/daemon/status | grep -q '"state":"running"' && return 0
  say_bad "로봇($ROBOT_HOST) 백엔드가 내려가 있다 — 앱을 띄우기 전에 복구부터 한다"
  robot_fix
  if ! rget /api/daemon/status | grep -q '"state":"running"'; then
    say_bad "복구하지 못했다. 전원과 케이블을 확인한 뒤 다시 시도한다"
    return 1
  fi
  say_ok "백엔드 복구됨 — 기동을 이어간다"
}

# 로봇 **한 대**를 앱까지 올린다 — `robot up`(1대)과 `start --robot`(2대)이 같이 쓴다.
# 갈라 두면 한쪽만 고쳐지고 시연장에서 어긋난다(추론 3종 기동을 demo/serve 가 공유하는
# 것과 같은 이유). 추론 3종·예열은 **맥 쪽 일**이라 여기 넣지 않는다 — 두 대를 올릴 때
# 한 번만 하면 된다. 실패하면 exit 가 아니라 1 을 돌려준다(부르는 쪽이 정한다).
#
# ROBOT_HOST·ROBOT_API 를 **지역 변수로 가린다.** rget/rpost/rssh/robot_fix/
# robot_sync_config 가 전역 이름을 그대로 읽는데, bash 는 동적 스코프라 이 함수 안에서
# 부르는 것은 전부 이 로봇을 향하고 돌아가면 원래 값이 되살아난다 — 두 대를 차례로
# 돌려도 서로 섞이지 않는다. REACHY_ROLE 도 같은 방법으로 robot_sync_config 에 닿는다.
# 이 실행이 앱을 띄운 호스트들. ~~`start --robot` 의 정리가 이것만 내린다~~ — 나중에 합류시킨
# 로봇(다른 터미널의 `robot up`)이 빠져서, 정리는 배역 자리 전부(START_ROBOT_HOSTS)로 넓혔다(최종 리뷰 F2).
ROBOT_APPS_STARTED=""
robot_bringup_one() {  # host role mac_ip   (role 이 비면 1대 모드 — 로봇 config 의 역할을 지운다)
  local ROBOT_HOST="$1" REACHY_ROLE="$2" ip="$3"
  local ROBOT_API="http://$ROBOT_HOST:8000"
  local bad=0 p

  say_step "로봇 ${REACHY_ROLE:-(역할 없음)} — $ROBOT_HOST"
  robot_reachable || return 1
  robot_backend_ready || return 1

  # ── 2. 로봇 config 동기화 ─────────────────────────────────
  say_step "로봇 config 동기화 (맥 $ip)"
  robot_sync_config "$ip" || { say_bad "config 를 쓰지 못했다"; return 1; }

  # ── 3. 로봇에서 맥이 실제로 보이는지 ──────────────────────
  say_step "로봇 → 맥 도달 확인"
  for p in 8080 8090 "$TTS_PORT"; do
    if rssh "curl -s -m 5 -o /dev/null -w '%{http_code}' http://$ip:$p/health" 2>/dev/null | grep -q 200; then
      say_ok "  :$p"
    else
      say_bad "  :$p — 로봇에서 안 보인다"; bad=1
    fi
  done
  [ "$bad" = "0" ] || { say_bad "맥 방화벽이나 망 분리를 확인한다"; return 1; }

  # ── 4. 기상 — **앱 기동 전에** 모터를 켠다 ────────────────
  # 앱이 로봇을 깨우지 않는다. 자고 있으면 SDK 가 "Robot is asleep; leaving it
  # limp in the sleep pose" 만 남기고 몸은 처진 채로 대화만 한다 — 말은 하는데
  # 안 움직이는 그 상태다(2026-09-09 반복해서 겪었다).
  # **조건부로 건너뛰지 않는다.** 앱을 정지하면 로봇이 몇 초 뒤 절전에 드는데,
  # 여기서 "이미 켜져 있다"를 보고 건너뛰면 **그 직후 잠들어** 말은 하는데 안
  # 움직이는 상태로 앱이 올라온다(deploy 직후 실제로 그랬다 — 관절 변동폭 0).
  # set_mode 와 wake_up 은 둘 다 멱등이라 매번 걸어도 부작용이 없다.
  #
  # **순서가 중요하다**: 모터가 꺼진 상태에서 wake_up 을 재생하면 헛돈다(robot_wake).
  say_step "기상"
  robot_wake
  if rget /api/motors/status | grep -q '"enabled"'; then
    say_ok "모터 활성화"
  else
    say_bad "모터가 안 켜진다 — 전원을 확인하고 ./reachy.sh robot fix 를 쓴다"
  fi

  # (5. 예열은 맥 쪽 일이라 부르는 쪽이 이 함수 **앞에서** 한 번 한다 — robot_warmup)

  # ── 6. 앱 기동 ────────────────────────────────────────────
  say_step "앱 기동 ($ROBOT_APP)"
  # 정리(`start --robot` 의 trap)가 이 로봇의 앱을 내리도록 **띄우기 전에** 적는다 —
  # 아래 14초 대기 중에 Ctrl-C 가 와도 앱이 로봇에 남지 않는다.
  ROBOT_APPS_STARTED="$ROBOT_APPS_STARTED $ROBOT_HOST"
  if ! robot_start_app; then
    robot_forget_started "$ROBOT_HOST"   # 띄운 것이 없다 — 정리가 남의 앱을 멈추지 않게
    return 1
  fi
  sleep 14

  # **앱이 올라온 뒤에 한 번 더 본다.** 기상과 앱 기동 사이에 절전으로 빠지면
  # 로봇은 말만 하고 몸이 굳는데, 로그만 봐서는 정상으로 보인다. 조용히 반쪽으로
  # 도는 것이 가장 찾기 어렵다.
  # 권하는 처방은 `robot up` 이다 — ~~`robot fix`~~ 는 앱을 **멈추고** 깨우기만 해서, 따라 하면
  # 로봇이 앱 없이 남는다(최종 리뷰 F1). `robot up` 은 다시 깨우고 앱까지 새로 띄운다(이미 도는
  # 앱이면 robot_start_app 이 멈춘 뒤 한 번 더 깨운다).
  if ! rget /api/motors/status | grep -q '"enabled"'; then
    say_bad "앱은 떴는데 모터가 꺼져 있다 — 말은 하지만 몸이 안 움직인다"
    echo "   ${c_dim}되살리기: ${REACHY_ROLE:+REACHY_ROLE=$REACHY_ROLE }REACHY_ROBOT_HOST=$ROBOT_HOST ./reachy.sh robot up${c_off}"
  fi
  return 0
}

# 기상 — 모터를 켜고(set_mode/enabled) 3초 뒤 wake_up 을 틀고 8초 기다린다. 기상 단계와
# robot_start_app 의 재기동 분기가 **같은 순서**를 쓰도록 한 자리에 둔다(갈라 두면 한쪽만 고쳐진다).
# **순서가 중요하다**: 모터가 꺼진 상태에서 wake_up 을 재생하면 헛돈다. 둘 다 멱등이다.
robot_wake() {
  rpost /api/motors/set_mode/enabled 20 >/dev/null 2>&1
  sleep 3
  rpost /api/move/play/wake_up 60 >/dev/null 2>&1
  sleep 8
}

# 앱을 띄우고 **응답을 본다.** 데몬은 앱이 이미 돌고 있으면 400 `{"detail":"An app is
# already running"}` 으로 거절하고, 옛 앱이 **옛 config**(지난 시연의 역할·감독 주소)로 계속
# 돈다 — 응답을 버리던 예전 코드는 그것을 성공으로 찍었다(리뷰 M8). 이미 돌면 멈추고 한 번
# 더 띄운다. 성공 응답은 AppStatus(`"state":"starting"|"running"`)다(reachy_mini/apps/manager.py).
#
# **멈췄으면 다시 깨운다**(최종 리뷰 F1). 앱을 정지하면 로봇이 몇 초 뒤 절전에 드는데(위 기상
# 단계 주석의 실측), 기상 단계는 이 분기보다 **앞**이다 — 그대로 띄우면 새 앱이 막 잠든 로봇
# 위에서 떠 말은 하는데 몸이 안 움직인다. 정지 → 3초 → robot_wake(모터 → wake_up) → 띄운다.
robot_start_app() {
  local resp
  resp="$(rpost "/api/apps/start-app/$ROBOT_APP" 40)"
  if printf '%s' "$resp" | grep -q 'An app is already running'; then
    say_warn "로봇($ROBOT_HOST)에 앱이 이미 돌고 있다 — 옛 config 로 도는 것이라 멈추고 다시 깨워 띄운다"
    rpost /api/apps/stop-current-app 25 >/dev/null 2>&1
    sleep 3
    robot_wake
    resp="$(rpost "/api/apps/start-app/$ROBOT_APP" 40)"
  fi
  printf '%s' "$resp" | grep -Eq '"state": ?"(starting|running)"' && return 0
  say_bad "앱을 띄우지 못했다 ($ROBOT_HOST): $(printf '%s' "${resp:-응답 없음}" | head -c 200)"
  echo "   ${c_dim}./reachy.sh robot fix 로 되살리거나 REACHY_ROBOT_HOST=$ROBOT_HOST ./reachy.sh robot logs 를 본다${c_off}"
  return 1
}

robot_forget_started() {  # host — ROBOT_APPS_STARTED 에서 뺀다(연관 배열 없이, bash 3.2)
  local x rest=""
  for x in $ROBOT_APPS_STARTED; do [ "$x" = "$1" ] || rest="$rest $x"; done
  ROBOT_APPS_STARTED="$rest"
}

# ── 5. 예열 (앱과 같은 프롬프트로) ────────────────────────────
# 로봇별 단계에서 떼어 냈다 — 맥의 추론 3종을 데우는 일이라 로봇이 두 대여도 한 번이면
# 된다. **앱 기동 전에만** 끝나면 되므로 로봇별 단계 앞에 둔다(예전 `robot up` 은 기상과
# 앱 기동 사이에 뒀다 — 앞으로 옮기면 기상→앱 사이가 짧아져 그 틈에 절전으로 빠질 여지를 줄인다).
robot_warmup() {
  say_step "예열${REACHY_PROMPT:+ — $REACHY_PROMPT}"
  "$PY" scripts/warmup.py || echo "   ${c_dim}일부 예열을 건너뛰었다${c_off}"
  # 구운 고정 대사가 얼마나 있는지 — 비어 있으면 해설이 공연마다 실시간 합성으로 나간다.
  # 기동을 막지는 않는다(결정: 굽기는 별도 명령, start 는 알리기만).
  [ "$TTS_BACKEND" = "qwen" ] && tts_cache_status
  return 0
}

# ── bake — 고정 대사를 TTS 캐시에 굽는다 ─────────────────────────
# CrispASR(안쪽 :$TTS_UPSTREAM_PORT)에 **직접** 합성을 요청해 캐시 폴더에 쓴다. 프록시는 폴더를 요청마다
# 보므로 다시 띄울 필요가 없다. 서버가 없으면 loopback 으로 띄운다(끝나도 남겨 둔다 — `start` 가 재사용).
run_bake() {
  local a
  for a in "$@"; do
    if [ "$a" = "--check" ]; then
      exec "$PY" scripts/bake_tts.py --check --cache-dir "$TTS_CACHE_DIR"
    fi
  done
  trap 'cleanup_partial; exit 130' INT TERM
  start_tts || exit 1
  STARTED_TTS=0
  if [ "$TTS_BACKEND" != "qwen" ]; then
    say_bad "Qwen3-TTS 가 없다 — 굽지 못한다(위 로그 참고)"
    exit 1
  fi
  if ! up "http://127.0.0.1:$TTS_UPSTREAM_PORT/health"; then
    say_bad "안쪽 CrispASR(:$TTS_UPSTREAM_PORT)가 없다 — TTS 가 예전 구성(:$TTS_PORT 직결)으로 떠 있다. ./reachy.sh stop 후 다시"
    exit 1
  fi
  say_step "굽기 — 고정 대사 → $TTS_CACHE_DIR"
  export TTS_BACKEND
  exec "$PY" scripts/bake_tts.py --upstream "http://127.0.0.1:$TTS_UPSTREAM_PORT" \
    --cache-dir "$TTS_CACHE_DIR" "$@"
}

robot_up() {
  local ip
  robot_reachable || exit 1

  # ── 0. 백엔드 상태를 **가장 먼저** 본다 ───────────────────────
  # 추론 3종·예열보다 앞이다 — 백엔드가 죽은 로봇에 서버부터 띄우는 헛일을 막는다
  # (robot_backend_ready 주석). robot_bringup_one 이 한 번 더 보지만 살아 있으면
  # GET 한 번이라 싸다.
  robot_backend_ready || exit 1

  # ── 1. 맥: 추론 3종을 LAN 에 ──────────────────────────────
  # `serve` 를 통째로 부르지 않는다 — 그쪽은 config 블록까지 찍어서 아래 3단계와
  # 중복된다. 기동 함수만 쓴다(코드는 공유하므로 갈라지지 않는다).
  BIND_HOST="${REACHY_BIND_HOST:-0.0.0.0}"
  trap 'cleanup_partial; exit 130' INT TERM
  start_llm_stt || exit 1
  start_tts
  STARTED_TTS=0
  trap - INT TERM

  ip="$(lan_ip)" || { say_bad "맥의 LAN 주소를 찾지 못했다"; exit 1; }

  robot_warmup

  # ── 0·2·3·4·6. 로봇별 단계 (한 대) ───────────────────────────
  robot_bringup_one "$ROBOT_HOST" "${REACHY_ROLE:-}" "$ip" || exit 1

  robot_status
  echo
  robot_logs 12
  echo
  echo "${c_dim}정지: ./reachy.sh robot down   로그: ./reachy.sh robot logs   복구: ./reachy.sh robot fix${c_off}"
}

run_robot() {
  local sub="${1:-}"; [ $# -gt 0 ] && shift
  case "$sub" in
    up)     robot_up "$@" ;;
    down)   robot_down "$@" ;;
    deploy) robot_deploy && robot_up ;;
    logs)   robot_logs_follow "$@" ;;
    status) robot_status ;;
    fix)    robot_fix ;;
    *)      say_bad "robot 서브커맨드는 up | down | deploy | logs | status | fix 다"; exit 2 ;;
  esac
}

# ════════════════════════════════════════════════════════════════
#  start — 시연 한 벌: 추론 3종 · 로봇 2대 · 무대감독 + 대시보드
# ════════════════════════════════════════════════════════════════
# 설계: docs/superpowers/specs/2026-09-21-launch-and-modes-design.md 1-1·1-3.
#
# 예전에는 한 벌을 여러 스크립트로 손으로 띄웠다(시뮬은 scripts/sim2.sh, 실기는
# `robot up` 두 번 + `python -m stage`). 순서를 사람이 기억해야 했고, 한 단계를
# 빠뜨리면 조용히 반쪽으로 돈다. 그 순서를 여기 하나로 묶는다. 부품(sim/demo/serve/
# robot…)은 그대로 둔다 — 1대 개발·실기 운영에 여전히 쓴다.
#
# **대상 인자는 필수다.** 실기와 시뮬을 기본값 하나로 뭉개면 시연장에서 엉뚱한 쪽이 뜬다.
#
# **감독은 전면이다.** 콘솔 키(s 시작 / n 다음 / a 비상정지 / q 종료)가 대시보드가
# 죽었을 때의 비상 폴백이다. 감독을 뒤로 돌리면 `run_console` 이 EOF 를 받아 "콘솔
# 없이 계속 돈다" 로 빠진다(stage/console.py). 그리고 `exec` 하지 않는다 — exec 하면
# 이 셸이 사라져 아래 trap(정리)이 돌 자리가 없다.
#
# **정리는 이 실행이 띄운 것만.** 감독이 끝나면(q / Ctrl-C / 터미널 닫힘) --sim 은
# 데몬·앱, --robot 은 두 배역 자리(사회자·도슨트 주소) 로봇의 앱만 내린다 — 건너뛰었다가
# 나중에 합류시킨 로봇까지(START_ROBOT_HOSTS). 이름 패턴으로 쓸지 않는다 — 옆 터미널에서
# 손으로 띄운 것까지 죽인다. 추론 3종은 남긴다: 모델 재적재·예열이 오래 걸려 다시
# 들어오기가 느려진다(`demo` 와 같은 관례). 전부 내리려면 ./reachy.sh stop.
#
# **--dry-run 은 PLAN 줄만 찍는다** — 파이썬·curl·ping·ssh·lsof·mkdir 어느 것도 안
# 부른다(tests/test_reachy_start.py 가 가짜 명령으로 지켜본다). 줄 모양이 테스트 계약이다.

# ⚠️ 시뮬 사회자는 반드시 8000 이다. SDK 의 `_check_daemon_on_localhost(port=8000)` 이
#    8000 고정이라, 8000 이 없으면 앱이 network 모드로 빠져 `reachy-mini.local` 을
#    찾다 실패한다. 도슨트는 REACHY_DAEMON_PORT 로 8001 을 받는다.
START_MC_PORT=8000
START_DOCENT_PORT=8001

START_PIDS=""        # "pid:이름 …" — 이 실행이 띄운 데몬·앱·브라우저 대기자(정리는 이것만 본다)
# `start --robot` 의 **배역 자리** 호스트(사회자·도슨트) — 정리가 여기 전부에 앱 정지를 보낸다.
# 건너뛴 로봇도 들어간다: 문서의 복구 절차(다른 터미널에서 `robot up`)로 나중에 합류한 앱은
# ROBOT_APPS_STARTED 에 없어서, 예전에는 `q` 뒤에도 마이크를 쥐고 재접속을 시도하며 남았다
# (최종 리뷰 F2). 그 로봇은 이 실행의 사회자/도슨트 자리다 — 거기 도는 앱은 이 시연의 것이다.
START_ROBOT_HOSTS=""
START_INFER_UP=0     # 추론 3종까지 올라왔는가 — 정리 안내 문구만 가른다
START_CLEANED=0

# 포트를 쥔 것이 있으면 **무엇인지 보여 주고 멈춘다.** 그냥 띄우면 새 데몬·감독이
# "address already in use" 로 뒤에서 죽고, 앱은 **남의 데몬·감독**(지난 실행의 고아,
# 손으로 띄운 `./reachy.sh sim`)에 붙어 조용히 엉뚱하게 돈다.
start_ports_free() {  # port...
  local p held bad=0
  if ! command -v lsof >/dev/null 2>&1; then
    say_warn "lsof 가 없어 포트 점검을 건너뛴다 — 충돌하면 데몬·감독 로그에 'address already in use' 로 드러난다"
    return 0
  fi
  for p in "$@"; do
    held="$(lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null)"
    if [ -n "$held" ]; then
      say_bad ":$p 를 이미 쥔 것이 있다"
      printf '%s\n' "$held" | sed 's/^/       /'
      bad=1
    else
      say_ok ":$p 비어 있음"
    fi
  done
  [ "$bad" = "0" ] && return 0
  # **`./reachy.sh stop` 이 감독·대시보드(8777/8778)까지 쓸어낸다** — 단 `robot down`(한 대만
  # 내리고 옆 시연은 살려 둬야 하는 경로)이 지나는 `stop_all` 안에는 없다, `stop` 커맨드 자신의
  # 몫(`stop_director_dashboard`)으로 따로 뗐다. 그러니 옆 터미널에서 시연 중인 감독을 이 창에서
  # 실수로 죽이지 않으려면 `stop` 대신 그 감독 터미널에서 q 로 끝낸다.
  echo "   ${c_dim}위 프로세스를 내린 뒤 다시 — 데몬·앱(8000/8001)이면 ./reachy.sh stop 이 쓸어낸다.${c_off}"
  echo "   ${c_dim}감독·대시보드(8777/8778)도 ./reachy.sh stop 이 쓸어낸다 — 옆 시연을 살려 두려면 그 감독 터미널에서 q, 터미널이 없으면 위 PID 를 kill${c_off}"
  return 1
}

# 이 실행이 띄운 프로세스만 내린다. TERM 은 **한꺼번에** 보낸다 — 앱에는 TERM 처리가
# 없어(파이썬 기본 동작, finally 없이 즉시 끝난다) 데몬보다 먼저 내려 얻는 것이 없다.
# 역순(늦게 띄운 것부터)은 "내림" 줄의 순서일 뿐이다. (SDK 의 우아한 정지는 SIGINT 인데,
# 뒤로 띄운 것은 SIGINT 를 무시한 채 시작된다 — 비대화형 셸의 `&`. 그래서 Ctrl-C 도
# 안 닿는다 — 여기서 TERM 을 보내야 내려간다.)
start_stop_pids() {
  local e pid rev="" kids="" n=0 alive
  [ -n "$START_PIDS" ] || return 0
  for e in $START_PIDS; do rev="$e $rev"; done
  for e in $rev; do
    pid="${e%%:*}"
    kill -0 "$pid" 2>/dev/null || continue
    # 자식은 **먼저 적어 둔다** — 부모가 죽으면 launchd 로 넘어가 `pgrep -P` 로 못 찾는다.
    kids="$kids $(pgrep -P "$pid" 2>/dev/null | tr '\n' ' ')"
    kill "$pid" 2>/dev/null && echo "   ${e#*:} 내림 (pid $pid)"
  done
  # 5초까지 기다린다 — 데몬(uvicorn)은 TERM 에 정상 종료한다. 버티는 것만 강제로.
  while [ "$n" -lt 10 ]; do
    alive=0
    for e in $rev; do kill -0 "${e%%:*}" 2>/dev/null && alive=1; done
    [ "$alive" = "0" ] && break
    sleep 0.5
    n=$((n + 1))
  done
  for e in $rev; do
    pid="${e%%:*}"
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null
      say_warn "${e#*:} 가 TERM 에 안 내려가 강제 종료했다 (pid $pid)"
    fi
  done
  # shellcheck disable=SC2086  # 공백으로 나뉜 pid 목록이다
  [ -n "${kids// /}" ] && kill $kids 2>/dev/null
  START_PIDS=""
}

# curl -s 는 HTTP 400("No app is currently running" 등)에도 0 이다 — 여기서 실패는 **안 닿았다**는
# 뜻이다. 건너뛴 로봇이 끝까지 꺼져 있으면 당연히 실패하지만, 켜져 있는데 못 멈췄을 수도 있어
# 조용히 넘기지 않고 한 줄 남긴다(그 로봇의 앱이 마이크를 쥐고 남는다).
robot_stop_app_on() {  # host — robot_down 과 같은 호출(stop-current-app)
  local ROBOT_HOST="$1"
  local ROBOT_API="http://$ROBOT_HOST:8000"
  if rpost /api/apps/stop-current-app 25 >/dev/null 2>&1; then
    say_ok "로봇 앱 정지 ($ROBOT_HOST)"
  else
    say_bad "로봇 앱 정지 실패 ($ROBOT_HOST) — 안 닿는다. 켜져 있으면: REACHY_ROBOT_HOST=$ROBOT_HOST ./reachy.sh robot down --keep-servers"
  fi
}

start_cleanup() {
  local h hosts
  [ "$START_CLEANED" = "1" ] && return 0   # INT 트랩 뒤 EXIT 트랩이 한 번 더 부른다
  START_CLEANED=1
  # 정리 도중의 Ctrl-C 는 무시한다 — 조급하게 한 번 더 누르면 정리가 반쯤에서 끊겨
  # 앱이 마이크를 쥔 채 남는다. 정리는 시간 상한이 있다(로컬 5초, 로봇마다 25초).
  trap '' INT TERM HUP
  cleanup_partial   # 추론 서버 기동 도중에 끊겼으면 이 실행이 띄운 TTS 만
  # 로봇: 배역 자리 전부(START_ROBOT_HOSTS) + 이 실행이 앱을 띄운 곳(보통 그 부분집합이다 —
  # 배역 자리는 로봇을 건드리기 **직전**에 적으므로). 겹치면 한 번만 보낸다(연관 배열 없이, bash 3.2).
  hosts="$START_ROBOT_HOSTS"
  for h in $ROBOT_APPS_STARTED; do
    case " $hosts " in *" $h "*) ;; *) hosts="$hosts $h" ;; esac
  done
  if [ -n "$START_PIDS" ] || [ -n "${hosts// /}" ]; then
    say_step "정리 — 이 실행이 띄운 것(과 배역 자리 로봇의 앱)만 내린다"
  fi
  # stderr 를 버리는 이유: bash 가 TERM 으로 죽인 백그라운드 작업마다 "line N: 1234
  # Terminated: 15 nohup …" 를 찍는다 — 우리가 방금 "내림" 이라고 말한 것의 소음이다.
  start_stop_pids 2>/dev/null
  for h in $hosts; do robot_stop_app_on "$h"; done
  ROBOT_APPS_STARTED=""
  START_ROBOT_HOSTS=""
  if [ "$START_INFER_UP" = "1" ]; then
    echo "   ${c_dim}추론 3종(LLM·STT·TTS)은 남겨 둔다 — 다시 start 하면 바로 붙는다. 전부 내리려면 ./reachy.sh stop${c_off}"
  fi
}

start_traps() {
  trap 'start_cleanup; exit 130' INT
  trap 'start_cleanup; exit 143' TERM
  trap 'start_cleanup; exit 129' HUP
  trap 'start_cleanup' EXIT
}

# ① 추론 3종 — 없는 것만. LLM 없이는 시연할 수 없으므로 여기서 실패하면 전체를 멈춘다.
start_infer() {
  # 어느 로그를 볼지는 start_llm_stt 가 실패한 그 자리에서 말한다(llm_stt_log_hint) — 여기서
  # 덧붙이면 거절 뒤에도 붙는다(M9). ~~$LOG_DIR/tts.log~~ 도 뺐다 — TTS 는 아직 띄우기 전이다.
  start_llm_stt || {
    say_bad "추론 서버를 쓸 수 없다 — LLM·STT 없이는 시연할 수 없어 멈춘다"
    return 1
  }
  # start_tts 가 1 을 주는 것은 "떠 있는 TTS 가 원하는 주소로 안 듣는다" 하나뿐이다(자산
  # 없음·기동 실패는 say 로 물러나고 0). 그 경우는 이유를 이미 찍었다 — 여기서 멈춘다.
  start_tts || return 1
  STARTED_TTS=0        # 여기부터는 기동이 끝났다 — 서버를 남겨 두는 것이 정상이다
  START_INFER_UP=1
  # 앱(시뮬)·예열이 같은 백엔드를 쓰도록 물려준다 — say 로 물러났으면 그것까지.
  export TTS_BACKEND
}

# ⑥ 대시보드가 뜨면 브라우저로 연다. 감독은 전면이라 그 **앞에서** 뒤로 띄워 둔다.
start_open_dashboard() {  # url
  local url="$1" opener=""
  # 리눅스의 `open` 은 openvt 인 경우가 있다 — 맥에서만 open, 나머지는 xdg-open.
  case "$(uname -s)" in
    Darwin) opener=open ;;
    *)      command -v xdg-open >/dev/null 2>&1 && opener=xdg-open ;;
  esac
  if [ -z "$opener" ]; then
    echo "   대시보드: $url  ${c_dim}(브라우저를 여는 명령이 없다 — 주소를 직접 연다)${c_off}"
    return 0
  fi
  echo "   대시보드: $url  ${c_dim}(뜨면 브라우저로 연다)${c_off}"
  (
    n=0
    while ! up "$url"; do
      n=$((n + 1))
      if [ "$n" -ge 60 ]; then
        echo "   ${c_bad}대시보드가 60초 안에 안 떴다${c_off} — 감독 출력의 대시보드 경고를 본다 ($url)"
        exit 0
      fi
      sleep 1
    done
    "$opener" "$url" >/dev/null 2>&1 || echo "   ${c_bad}브라우저를 못 열었다${c_off} — $url 을 직접 연다"
  ) &
  START_PIDS="$START_PIDS $!:브라우저대기"
}

# ⑦ 무대감독 — 전면. 돌아오면 그 종료코드로 끝난다(EXIT trap 이 정리한다).
#
# 출력을 **로그 파일에도** 남긴다($START_DIRECTOR_LOG, `./reachy.sh logs` 가 본다). 예전에는
# 터미널에만 나가서 "로그부터 읽는다"(CLAUDE.md) 가 start 세션에서는 빈손이었다(리뷰 M7).
# 콘솔은 그대로 산다 — 표준입력은 터미널 그대로이고, 표준출력만 tee 를 지난다:
#   · PYTHONUNBUFFERED=1 — 출력이 파이프가 되면 flush 없는 print 가 블록 버퍼에 갇혀
#     콘솔에 안 보인다(프롬프트 `무대감독> ` 은 input() 이 스스로 flush 한다).
#   · tee 는 SIGINT 를 무시한다 — Ctrl-C 가 tee 를 먼저 죽이면 감독이 정리하며 찍는 줄이
#     깨진 파이프로 사라진다. 감독이 끝나 파이프가 닫히면 tee 도 끝난다.
#   · 종료코드는 감독 것이다(pipefail — tee 는 0 이다).
# 파이프 뒤라 줄 편집(방향키)은 안 된다 — 콘솔은 한 글자 명령이라 잃는 것이 없다.
#
# 머리줄에 **대상**(target=sim | target=robot mc=… docent=…)을 적는다(최종 리뷰 M3) — 같은 파일에
# 시뮬·실기 세션이 섞여 쌓이는데, 머리줄이 같으면 `logs` 를 읽는 사람이 어느 쪽이었는지 모른다.
start_director() {  # bind port dashboard_url target
  local target="${4:-target=?}"
  say_step "무대감독 + 대시보드 — 이 터미널이 콘솔이다"
  start_open_dashboard "$3"
  echo "   ${c_ok}로봇이 붙으면 아래에 '붙었다' 가 뜬다. 그 뒤 s(또는 대시보드의 시작)로 시작한다.${c_off}"
  echo "   ${c_dim}s 시작 · n 다음 · p 이전 · a 비상정지 · r 재시작 · q 종료(이 실행이 띄운 것도 함께 내린다)${c_off}"
  echo "   ${c_dim}감독 출력은 $START_DIRECTOR_LOG 에도 남는다 (./reachy.sh logs)${c_off}"
  echo
  # 무한정 쌓이지 않게 — 2MB 넘으면 한 세대만 남기고 넘긴다(app.log 와 같다)
  if [ -f "$START_DIRECTOR_LOG" ] && [ "$(wc -c < "$START_DIRECTOR_LOG")" -gt 2000000 ]; then
    mv "$START_DIRECTOR_LOG" "$START_DIRECTOR_LOG.1"
  fi
  {
    echo
    echo "════════ 세션 시작 $(date '+%Y-%m-%d %H:%M:%S') ════════"
    echo "start: $target | 감독 $1:$2 | 대시보드 $3 | TTS_BACKEND=$TTS_BACKEND"
    echo "환경: REACHY_AUDIENCE_LEVEL=${REACHY_AUDIENCE_LEVEL:-기본}" \
         "REACHY_MC_UNIT=${REACHY_MC_UNIT:-없음} REACHY_DOCENT_UNIT=${REACHY_DOCENT_UNIT:-없음}"
  } >> "$START_DIRECTOR_LOG"
  REACHY_DIRECTOR_HOST="$1" REACHY_DIRECTOR_PORT="$2" PYTHONUNBUFFERED=1 \
    "$PY" -m stage 2>&1 | ( trap '' INT; exec tee -a "$START_DIRECTOR_LOG" )
}

# ── --sim: 이 맥 한 대에 모의 데몬 2대 + 앱 2대 (구 scripts/sim2.sh) ──────────
# `--mockup-sim` 은 MuJoCo 가 필요 없어 mjpython/Cocoa 메인스레드 제약을 우회한다.
# 그래서 한 맥에서 두 개가 공존한다(`./reachy.sh sim` 은 두 번 못 띄운다).
start_sim_daemon() {  # role port
  local role="$1" port="$2"
  local log="$LOG_DIR/start-daemon-$role.log"
  nohup "$PY" -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
    --fastapi-port "$port" --robot-name "$role" > "$log" 2>&1 &
  START_PIDS="$START_PIDS $!:데몬-$role"
  if ! wait_for "http://localhost:$port/api/daemon/status" "$role 데몬(:$port)" 60; then
    say_bad "$role 데몬이 뜨지 않았다 — tail -30 $log"
    tail -15 "$log" | sed 's/^/     /'
    return 1
  fi
}

# 앱은 감독보다 **먼저** 띄운다 — 붙을 때까지 재접속을 계속 시도한다. 실기에서도
# 로봇이 먼저 켜져 있고 감독이 나중에 뜨는 일이 흔하다.
start_sim_app() {  # role port audio_out director_url
  local role="$1" port="$2" out="$3" url="$4"
  local log="$LOG_DIR/start-app-$role.log"
  # **`${out:+VAR="$out"}` 를 쓰지 않는다.** 확장 결과가 따옴표 밖이라 값에 공백이
  # 있으면(기본값이 "MacBook Pro 스피커" 다) 단어 분리가 나 `Pro` 가 명령어로 간다.
  # 서브셸에서 export 하면 값이 통째로 전달된다.
  (
    export REACHY_ROLE="$role"
    export REACHY_DAEMON_PORT="$port"
    export REACHY_DIRECTOR_URL="$url"
    # 비었으면 **지운다** — 운영자 셸의 REACHY_AUDIO_OUT 이 새어 들면 두 앱이 같은
    # 장치로 가는데, 위 경고는 "기본 출력" 이라고 말하게 된다.
    if [ -n "$out" ]; then export REACHY_AUDIO_OUT="$out"; else unset REACHY_AUDIO_OUT; fi
    exec "$PY" -u apps/voice_chat/voice_chat/main.py > "$log" 2>&1
  ) &
  START_PIDS="$START_PIDS $!:앱-$role"
  say_ok "$role 앱 → 데몬 :$port${out:+, 출력 '$out'}  ${c_dim}로그: $log${c_off}"
}

start_sim() {  # director_port dashboard_port dashboard_url
  local dir_port="$1" dash_port="$2" dash_url="$3"
  # 출력 장치. 같은 스피커로 나가면 도슨트 소리가 사회자 마이크로 되돌아와
  # 자기목소리 루프가 실기보다 훨씬 쉽게 난다. 이름은 sounddevice 가 받는 것
  # (장치 이름의 일부 또는 인덱스). 목록:
  #   .venv/bin/python -c "import sounddevice; print(sounddevice.query_devices())"
  # 맥 전용 이름이 기본값이지만 **시뮬 경로에서만** 쓴다(앱이 이 맥에서 돈다). 없는
  # 장치면 앱이 경고하고 기본 출력으로 낸다(tts.py `REACHY_AUDIO_OUT`). 실기는 이
  # 변수를 안 쓴다 — 두 로봇이 물리적으로 떨어져 있다.
  local mc_out="${REACHY_MC_AUDIO_OUT:-MacBook Pro 스피커}"
  local docent_out="${REACHY_DOCENT_AUDIO_OUT:-}"

  say_step "포트 점검"
  start_ports_free "$START_MC_PORT" "$START_DOCENT_PORT" "$dir_port" "$dash_port" || exit 1
  [ -x "$PY" ] || { say_bad "$PY 가 없다 — 이 저장소는 .venv 파이썬 하나만 쓴다"; exit 1; }

  if [ -z "$docent_out" ]; then
    say_warn "도슨트 출력 장치가 지정되지 않았다 — 두 목소리가 **같은 스피커**로 나간다."
    echo "      ${c_dim}도슨트 소리가 사회자 마이크로 되돌아와 자기목소리 루프가 쉽게 난다.${c_off}"
    echo "      ${c_dim}갈라 주려면: REACHY_DOCENT_AUDIO_OUT='장치이름' ./reachy.sh start --sim${c_off}"
  fi

  start_traps
  BIND_HOST=127.0.0.1   # 시뮬은 전부 이 맥 안이다 — 망에 열 이유가 없다
  start_infer || exit 1
  if [ "$TTS_BACKEND" != "qwen" ]; then
    say_warn "TTS 가 say(유나)로 물러났다 — 두 로봇이 **같은 목소리**로 말한다(역할 목소리는 Qwen3-TTS 가 낸다)"
  fi

  # 첫 합성은 Metal 커널 JIT 로 8.5초가 걸린다(실측). 예열을 빠뜨리면 첫 큐가
  # 헛타임아웃 나고 그 경로로 자기목소리 루프가 되살아난다(director.py 주석).
  robot_warmup

  say_step "모의 데몬 2대 (사회자 :$START_MC_PORT · 도슨트 :$START_DOCENT_PORT)"
  start_sim_daemon mc     "$START_MC_PORT"     || exit 1
  start_sim_daemon docent "$START_DOCENT_PORT" || exit 1

  say_step "앱 2대 (역할·데몬포트·출력장치를 짝지어 준다)"
  start_sim_app mc     "$START_MC_PORT"     "$mc_out"     "ws://127.0.0.1:$dir_port"
  start_sim_app docent "$START_DOCENT_PORT" "$docent_out" "ws://127.0.0.1:$dir_port"

  start_director 127.0.0.1 "$dir_port" "$dash_url" "target=sim"
}

# ── --robot: 실기 2대 (사회자·도슨트 각각 robot_bringup_one) ──────────────────
start_robot() {  # bind director_port dashboard_port dashboard_url mc_host docent_host
  local bind="$1" dir_port="$2" dash_port="$3" dash_url="$4" mc_host="$5" docent_host="$6"
  local ip n_up=0

  say_step "포트 점검 (무대감독 · 대시보드)"
  start_ports_free "$dir_port" "$dash_port" || exit 1
  [ -x "$PY" ] || { say_bad "$PY 가 없다 — 이 저장소는 .venv 파이썬 하나만 쓴다"; exit 1; }

  start_traps
  BIND_HOST="$bind"
  start_infer || exit 1
  # 로봇 앱은 **이 맥의 TTS 로만** 말한다 — 로봇에는 say 폴백이 없다. 맥에서 say 로
  # 물러난 채 가면 로봇마다 "로봇 → 맥 도달 확인" 에서 :8099 로 떨어져 원인이 방화벽처럼
  # 보인다. 진짜 원인을 여기서 말하고 멈춘다.
  if ! up "http://localhost:$TTS_PORT/health"; then
    say_bad "TTS 서버(:$TTS_PORT)가 없다 — 로봇 앱은 이 맥의 TTS 로만 말한다. 멈춘다"
    echo "   ${c_dim}tail -30 $LOG_DIR/tts.log${c_off}"
    exit 1
  fi

  ip="$(lan_ip)" || { say_bad "맥의 LAN 주소를 찾지 못했다 — 전용 공유기 망에 붙어 있는지 확인한다"; exit 1; }

  # **로봇이 붙을 바로 그 주소로** 맥에서 먼저 두드려 본다. `start --sim`·`demo` 가
  # loopback 으로 띄워 남겨 둔 서버를 재사용하면 로봇마다 ":8080 — 로봇에서 안 보인다" 로
  # 떨어져 원인이 방화벽처럼 보인다(리뷰 I2). 위 가드(already_up_binds_right)가 같은 것을
  # 보지만, 로봇 config 에 써 넣을 주소가 이 $ip 이므로 마지막 확인은 이 주소로 한다.
  local p
  for p in 8080 8090 "$TTS_PORT"; do
    up "http://$ip:$p/health" && continue
    say_bad "추론 서버가 $ip:$p 에서 안 보인다 — loopback 전용(start --sim/demo 가 띄운 것) — ./reachy.sh stop 후 다시"
    exit 1
  done

  # 로봇에 넣는 감독 주소는 **이 실행이 띄우는 감독**이어야 한다. 운영자 셸에 시뮬 때의
  # REACHY_DIRECTOR_URL(ws://127.0.0.1:…)이 남아 있으면 robot_sync_config 가 그것을
  # 로봇에 써 넣어 두 로봇이 조용히 못 붙는다. 지역 변수로 가려 robot_sync_config 에 닿게 한다.
  local want="ws://$ip:$dir_port"
  if [ -n "${REACHY_DIRECTOR_URL:-}" ] && [ "$REACHY_DIRECTOR_URL" != "$want" ]; then
    say_warn "REACHY_DIRECTOR_URL=$REACHY_DIRECTOR_URL 는 쓰지 않는다 — 감독을 이 맥에 띄우므로 로봇에 $want 를 넣는다"
  fi
  local REACHY_DIRECTOR_URL="$want"

  # ── 여기부터 이 실행은 **실기 세션**이다 ─────────────────────────
  # 지난 `start --sim` 의 start-{app,daemon}-*.log 가 남아 있으면 `./reachy.sh logs` 가 그것을
  # 이번 세션처럼 붙여 보인다(최종 리뷰 M3) — 실기의 앱·데몬은 로봇 위에서 돌아 이 맥에 출력이
  # 없다. 로봇 쪽 로그를 보는 명령 한 줄로 덮는다. 위에서 멈추는 실행(포트·추론 서버)은 지난
  # 로그를 건드리지 않는다 — 감독 로그의 마지막 세션도 그대로라 둘이 어긋나지 않는다.
  start_robot_log_pointer mc "$mc_host"
  start_robot_log_pointer docent "$docent_host"
  # 배역 자리를 **로봇을 건드리기 전에** 적는다 — 기동 중 Ctrl-C 에도 정리가 두 자리에 간다(F2).
  START_ROBOT_HOSTS="$mc_host $docent_host"

  robot_warmup

  # 한 대가 안 닿으면 **경고하고 건너뛴다** — 감독에 이미 1인 모드가 있다(남은 로봇이
  # 양쪽 대사를 읽는다). 한 대 때문에 시연 전체를 세우지 않는다. 건너뛸 때마다 합류 명령을
  # 찍는다 — 예전에는 두 대 다 못 올렸을 때만 찍어서, 한 대만 빠지면 복구 명령을 찾아야 했다(F2).
  # 그렇게 합류한 앱도 `q` 가 멈춘다(START_ROBOT_HOSTS).
  if robot_bringup_one "$mc_host" mc "$ip"; then n_up=$((n_up + 1)); else
    start_robot_skipped mc "$mc_host" "사회자"
  fi
  if robot_bringup_one "$docent_host" docent "$ip"; then n_up=$((n_up + 1)); else
    start_robot_skipped docent "$docent_host" "도슨트"
  fi
  if [ "$n_up" = "0" ]; then
    say_bad "두 로봇 모두 못 올렸다 — 감독만 띄운다. 로봇을 살린 뒤 위 명령으로 붙인다"
  fi

  start_director 0.0.0.0 "$dir_port" "$dash_url" "target=robot mc=$mc_host docent=$docent_host"
}

start_robot_log_pointer() {  # role host
  local line="실기 — 앱 로그는 REACHY_ROBOT_HOST=$2 ./reachy.sh robot logs"
  printf '%s\n' "$line" > "$LOG_DIR/start-app-$1.log"
  printf '%s\n' "$line" > "$LOG_DIR/start-daemon-$1.log"
}

start_robot_skipped() {  # role host 이름
  say_warn "$3 로봇($2)을 건너뛴다 — 감독은 남은 로봇으로 돈다"
  echo "   ${c_dim}살린 뒤 다른 터미널에서 합류: REACHY_ROLE=$1 REACHY_ROBOT_HOST=$2 ./reachy.sh robot up${c_off}"
  echo "   ${c_dim}(합류한 앱도 이 콘솔의 q 가 함께 멈춘다)${c_off}"
}

run_start() {
  local target="" dry=0 a
  for a in "$@"; do
    case "$a" in
      --sim|--robot)
        if [ -n "$target" ] && [ "$target" != "${a#--}" ]; then
          say_bad "start 대상은 하나만 — --sim 또는 --robot"; echo; usage; exit 2
        fi
        target="${a#--}" ;;
      --dry-run) dry=1 ;;
      *) say_bad "모르는 인자: $a"; echo; usage; exit 2 ;;
    esac
  done
  if [ -z "$target" ]; then
    say_bad "start 는 대상이 필수다 — --sim(이 맥의 시뮬 2대) 또는 --robot(실기 2대)"
    echo "   ${c_dim}기본값을 두지 않는다 — 실기와 시뮬을 하나로 뭉개면 시연장에서 엉뚱한 쪽이 뜬다${c_off}"
    echo; usage; exit 2
  fi

  # 감독·대시보드 포트는 감독(`python -m stage`)이 읽는 **같은 변수**에서 읽는다.
  # 여기서 8777 을 박아 두면 운영자가 포트를 바꿨을 때 앱은 8777 로 붙으러 가고
  # 감독은 다른 포트에 떠서 조용히 못 만난다.
  local dir_port="${REACHY_DIRECTOR_PORT:-8777}"
  local dash_port="${REACHY_DASHBOARD_PORT:-8778}"
  # 대시보드는 **여는 주소**를 찍는다. 0.0.0.0(모든 주소로 받는다)은 열 수 있는 주소가
  # 아니고, 비었으면 감독이 127.0.0.1 로 띄운다(stage/__main__.py).
  local dash_host="${REACHY_DASHBOARD_HOST:-}"
  case "$dash_host" in ""|0.0.0.0) dash_host=127.0.0.1 ;; esac
  local dash_url="http://$dash_host:$dash_port/"
  # 실기 두 대의 hostname 이 둘 다 `reachy-mini` 라 `.local` 은 못 믿는다 — 고정 IP 가 기본.
  local mc_host="${REACHY_MC_HOST:-192.168.0.4}"
  local docent_host="${REACHY_DOCENT_HOST:-192.168.0.5}"
  # 두 역할이 **같은 로봇**이면 사회자 config 를 쓰고 곧바로 도슨트 config 로 덮어써 사회자가 조용히
  # 사라진다(최종 리뷰 M7) — 감독은 도슨트 하나만 붙은 1인 모드로 돈다. 쓰임새 오류(2)로 멈춘다.
  # dry-run 도 여기를 지난다 — 계획이 "된다" 고 찍으면 안 된다. 시뮬은 로봇 주소를 안 쓰므로
  # 셸에 남은 실기 값 때문에 막지 않는다.
  if [ "$target" = "robot" ] && [ "$mc_host" = "$docent_host" ]; then
    say_bad "사회자와 도슨트가 같은 로봇($mc_host)이다 — 도슨트 config 가 사회자를 덮어써 사회자가 사라진다"
    echo "   ${c_dim}REACHY_MC_HOST / REACHY_DOCENT_HOST 를 확인한다 (기본 192.168.0.4 / 192.168.0.5)${c_off}"
    exit 2
  fi
  # 추론 3종 바인드: 시뮬은 loopback 고정(전부 이 맥 안), 실기는 LAN — 로봇이 닿아야
  # 한다. 실기 쪽은 `serve`·`robot up` 과 같이 REACHY_BIND_HOST 로 좁힐 수 있다.
  local bind
  if [ "$target" = "sim" ]; then bind=127.0.0.1; else bind="${REACHY_BIND_HOST:-0.0.0.0}"; fi

  if [ "$dry" = "1" ]; then
    echo "PLAN infer bind=$bind ports=8080,8090,$TTS_PORT"
    if [ "$target" = "sim" ]; then
      echo "PLAN robot role=mc target=sim port=$START_MC_PORT"
      echo "PLAN robot role=docent target=sim port=$START_DOCENT_PORT"
      echo "PLAN director bind=127.0.0.1 port=$dir_port dashboard=$dash_url"
    else
      echo "PLAN robot role=mc target=$mc_host"
      echo "PLAN robot role=docent target=$docent_host"
      echo "PLAN director bind=0.0.0.0 port=$dir_port dashboard=$dash_url"
    fi
    exit 0
  fi

  mkdir -p "$LOG_DIR"
  if [ "$target" = "sim" ]; then
    start_sim "$dir_port" "$dash_port" "$dash_url"
  else
    start_robot "$bind" "$dir_port" "$dash_port" "$dash_url" "$mc_host" "$docent_host"
  fi
  # 감독의 종료코드로 끝낸다 — 정리는 EXIT trap 이 한다.
  exit $?
}

# ════════════════════════════════════════════════════════════════
# `source reachy.sh` 로 불리면 함수만 정의하고 돌아간다. 실기·데몬 없이는 못 돌리는
# 정리(trap)·로봇별 단계를 테스트가 가짜 명령으로 돌려 본다(tests/test_reachy_start.py).
# 실행(`./reachy.sh …`)에서는 BASH_SOURCE 와 $0 이 같아 그냥 지나간다.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0

# 로그 폴더는 여기서 만든다 — 단 `start` 는 빼고 스스로 만든다. `start --dry-run` 은
# 아무것도 건드리지 않아야 한다(폴더 하나라도).
cmd="${1:-}"
[ $# -gt 0 ] && shift
[ "$cmd" = "start" ] || mkdir -p "$LOG_DIR"
case "$cmd" in
  start) run_start "$@" ;;
  sim)   run_sim "$@" ;;
  demo)  run_demo "$@" ;;
  serve) run_serve "$@" ;;
  robot) run_robot "$@" ;;
  check) say_step "상태"; status ;;
  stop)  stop_all; stop_director_dashboard ;;
  logs)  show_logs "$@" ;;
  # 측정·예열도 이 진입점 하나로 통한다 — 파이썬 도구는 scripts/ 에 있지만
  # 인터프리터(.venv 강제)·작업 디렉토리·환경을 여기서 보장해 주는 것이 안전하다.
  #
  # **TTS_BACKEND 를 export 해야 한다.** 셸 변수로만 두면 하위 스크립트가 못 보고
  # macOS `say` 경로로 떨어진다 — 예열에서는 Qwen3-TTS 의 Metal JIT 8.5초(예열의
  # 최대 항목)가 통째로 빠지고(실측: `(say)` 로 예열됨), 측정에서는 프로덕션과
  # 무관한 수치가 나온다. 기본값은 위에서 qwen 으로 잡힌다.
  # (분기마다 따로 export 한다 — `;;&` 폴스루는 bash 4.0+ 이고 macOS 기본은 3.2 다.)
  warmup)
    export TTS_BACKEND
    exec "$PY" scripts/warmup.py "$@" ;;
  bake)  run_bake "$@" ;;
  measure)
    export TTS_BACKEND
    sub="${1:-}"; [ $# -gt 0 ] && shift
    case "$sub" in
      aec)     exec "$PY" scripts/measure_aec.py "$@" ;;
      latency) exec "$PY" scripts/measure_latency.py "$@" ;;
      *) say_bad "measure 대상은 aec | latency 다"; exit 2 ;;
    esac ;;
  ""|-h|--help|help) usage ;;
  *)     say_bad "모르는 명령: $cmd"; echo; usage; exit 2 ;;
esac
