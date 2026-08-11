#!/usr/bin/env bash
# Reachy Mini 단일 진입점 — 시뮬레이터도 시연 스택도 여기서 띄운다.
#
#   ./reachy.sh sim                    시뮬 데몬만 (3D 뷰어 + 오디오 + 카메라)
#   ./reachy.sh sim --scene minimal    테이블 + 사과/크루아상/오리
#   ./reachy.sh sim --headless         3D 창 없이  (⚠ 카메라 스트림도 꺼진다)
#   ./reachy.sh sim --no-media         오디오·카메라 끄고 모션만
#   ./reachy.sh demo                   전체 스택(LLM·STT·TTS·데몬) + 마이크 대화
#   ./reachy.sh demo --text            키보드로 대화 — 마이크가 말썽일 때
#   ./reachy.sh demo --no-robot        시뮬 없이 대화·음성만 — 최후 폴백
#   ./reachy.sh demo --exit-clean      앱을 나갈 때 서버까지 함께 내린다
#   ./reachy.sh check                  기동하지 않고 상태만 확인
#   ./reachy.sh logs [줄수]            마지막 세션 로그 (앱 + 서버 오류) — 문제 생기면 여기부터
#   ./reachy.sh stop                   띄운 것 전부 종료 (고아까지 쓸어낸다)
#
# `sim` 은 포그라운드다(Ctrl-C 로 끝). `demo` 는 없는 서버만 띄우고 앱으로 들어간다 —
# 앱을 Ctrl-C 로 나가도 서버는 살려 둔다(재진입이 빨라야 한다). 완전히 내리려면 stop.
#
# set -e 는 쓰지 않는다. 헬스체크 실패를 직접 잡아 안내해야 한다.
set -uo pipefail
cd "$(dirname "$0")"
SELF="$PWD/$(basename "$0")"

LLAMACTL="$HOME/workspace/llamactl.sh"   # `llama` 는 셸 별칭이라 스크립트에서 못 쓴다
PY=".venv/bin/python"
LOG_DIR=".demo-logs"
APP_LOG="$LOG_DIR/app.log"      # 앱(대화) 출력 — 세션 구분자와 함께 누적된다
SIM_PID_FILE="$LOG_DIR/sim.pid"
TTS_PID_FILE="$LOG_DIR/tts.pid"
SCENE="minimal"

c_ok=$'\033[32m'; c_bad=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
say_ok()   { echo "${c_ok}OK${c_off}   $1"; }
say_bad()  { echo "${c_bad}FAIL${c_off} $1"; }
say_step() { echo; echo "▶ $1"; }

usage() { sed -n '2,17p' "$SELF" | sed 's/^# \{0,1\}//'; }

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
TTS_VOICE="${TTS_QWEN_VOICE:-$("$PY" -c \
  "import sys;sys.path.insert(0,'apps/voice_chat/voice_chat');import tts;print(tts.QWEN_VOICE)" \
  2>/dev/null || echo serena)}"

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
    if up "http://localhost:$TTS_PORT/health"; then
      say_ok "TTS  Qwen3(:$TTS_PORT) 화자 $TTS_VOICE"
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

show_logs() {  # [줄수]
  local n=${1:-80}
  if [ -f "$APP_LOG" ]; then
    say_step "마지막 세션 (앱) — $APP_LOG"
    # 마지막 '세션 시작' 이후만 보여준다. 없으면 꼬리만.
    if grep -q "════════ 세션 시작" "$APP_LOG"; then
      awk '/════════ 세션 시작/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "$APP_LOG" | tail -"$n"
    else
      tail -"$n" "$APP_LOG"
    fi
  else
    echo "   ${c_dim}앱 로그가 없다 — 아직 ./reachy.sh demo 를 돌린 적이 없다${c_off}"
  fi
  for f in "$LOG_DIR/tts.log" "$LOG_DIR/sim.log"; do
    [ -f "$f" ] || continue
    say_step "$(basename "$f") 끝부분"
    grep -iE "error|traceback|경고|실패|warn" "$f" | tail -10 || tail -5 "$f"
  done
}

stop_all() {
  say_step "종료"
  kill_pidfile "$TTS_PID_FILE" "TTS 서버"
  kill_pidfile "$SIM_PID_FILE" "시뮬 데몬"
  "$LLAMACTL" stop
  # llamactl 이 관리하지 않는 것 + 고아. 시뮬 데몬을 PID 파일로만 잡으면
  # 손으로 띄운 것이 살아남는다(실측: `stop` 후에도 :8000 이 응답했다).
  sweep "crispasr --server"            "CrispASR"
  sweep "stt_server.py"                "STT 서버"
  sweep "reachy_mini.daemon.app.main"  "시뮬 데몬"
}

# 기동 도중 Ctrl-C 나 실패로 빠져나갈 때, **이 실행이 띄운 것만** 정리한다.
STARTED_TTS=0
cleanup_partial() {
  [ "$STARTED_TTS" = "1" ] || return 0
  echo
  echo "   ${c_dim}기동이 끝나지 않아 이 실행이 띄운 TTS 서버를 정리한다${c_off}"
  kill_pidfile "$TTS_PID_FILE" "TTS 서버"
  STARTED_TTS=0
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
  say_step "LLM(:8080) · STT(:8090)"
  if up http://localhost:8080/health && up http://localhost:8090/health; then
    echo "   ${c_dim}이미 떠 있다 — 건너뛴다${c_off}"
  else
    if [ ! -x "$LLAMACTL" ]; then
      say_bad "$LLAMACTL 을 찾을 수 없다"; exit 1
    fi
    "$LLAMACTL" reach-llm || { say_bad "LLM/STT 기동 실패"; exit 1; }
    wait_for http://localhost:8080/health "LLM" 120 || exit 1
    wait_for http://localhost:8090/health "STT" 180 || exit 1   # 모델 예열이 오래 걸린다
  fi

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
  if [ "$TTS_BACKEND" = "qwen" ]; then
    say_step "TTS 서버(:$TTS_PORT) — Qwen3-TTS"
    if up "http://localhost:$TTS_PORT/health"; then
      echo "   ${c_dim}이미 떠 있다 — 건너뛴다${c_off}"
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
      echo "   기동 중 ($TTS_BACKEND_NAME, 화자 $TTS_VOICE)... 로그: $LOG_DIR/tts.log"
      nohup "$CRISPASR" --server --port "$TTS_PORT" --backend "$TTS_BACKEND_NAME" \
        -m "$TTS_MODEL" --codec-model "$TTS_CODEC" --voice "$TTS_VOICE" \
        > "$LOG_DIR/tts.log" 2>&1 &
      echo $! > "$TTS_PID_FILE"
      STARTED_TTS=1   # 기동 실패 시 trap 이 이것만 보고 정리한다
      if ! wait_for "http://localhost:$TTS_PORT/health" "TTS" 90; then
        say_bad "TTS 서버 기동 실패 — tail -30 $LOG_DIR/tts.log"
        echo "   ${c_dim}→ 유나(say) 목소리로 계속 진행한다${c_off}"
        TTS_BACKEND=say
      fi
    fi
  fi
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
mkdir -p "$LOG_DIR"

cmd="${1:-}"
[ $# -gt 0 ] && shift
case "$cmd" in
  sim)   run_sim "$@" ;;
  demo)  run_demo "$@" ;;
  check) say_step "상태"; status ;;
  stop)  stop_all ;;
  logs)  show_logs "$@" ;;
  ""|-h|--help|help) usage ;;
  *)     say_bad "모르는 명령: $cmd"; echo; usage; exit 2 ;;
esac
