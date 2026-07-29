#!/usr/bin/env bash
# 시연용 원커맨드 기동 — 없는 것만 띄우고, 준비되면 바로 음성 모드로 들어간다.
#
#   ./scripts/demo.sh              마이크로 대화 (기본, 시연용)
#   ./scripts/demo.sh --text       키보드로 대화 (마이크 문제 시 폴백)
#   ./scripts/demo.sh --no-robot   시뮬 없이 대화·음성만 (데몬 죽었을 때 최후 폴백)
#   ./scripts/demo.sh --check      기동하지 않고 상태만 확인
#   ./scripts/demo.sh --stop       띄운 서버 전부 종료
#
# 이미 떠 있는 것은 건드리지 않는다. 앱을 Ctrl-C 로 나가도 서버는 살려 둔다 —
# 시연 중 재진입이 빨라야 하기 때문이다. 완전히 내리려면 --stop.
#
# set -e 는 쓰지 않는다. 헬스체크 실패를 직접 잡아 안내해야 한다.
set -uo pipefail
cd "$(dirname "$0")/.."

LLAMACTL="$HOME/workspace/llamactl.sh"   # `llama` 는 셸 별칭이라 스크립트에서 못 쓴다
PY=".venv/bin/python"
LOG_DIR=".demo-logs"
SIM_PID_FILE="$LOG_DIR/sim.pid"
SCENE="minimal"

mkdir -p "$LOG_DIR"

c_ok=$'\033[32m'; c_bad=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
say_ok()   { echo "${c_ok}OK${c_off}   $1"; }
say_bad()  { echo "${c_bad}FAIL${c_off} $1"; }
say_step() { echo; echo "▶ $1"; }

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
  say -v '?' | grep -q Yuna                    && say_ok "TTS  Yuna"  || say_bad "TTS  Yuna"
}

stop_all() {
  say_step "종료"
  if [ -f "$SIM_PID_FILE" ]; then
    local pid; pid=$(cat "$SIM_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null && echo "   시뮬 데몬 종료 (pid $pid)"; fi
    rm -f "$SIM_PID_FILE"
  else
    echo "   ${c_dim}시뮬 데몬은 이 스크립트가 띄우지 않았다 — 직접 Ctrl-C 로 끈다${c_off}"
  fi
  "$LLAMACTL" stop
}

case "${1:-}" in
  --check) say_step "상태"; status; exit 0 ;;
  --stop)  stop_all; exit 0 ;;
esac

# ── 1. LLM + STT ────────────────────────────────────────────────
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

# ── 2. 시뮬레이터 데몬 ──────────────────────────────────────────
say_step "시뮬레이터 데몬(:8000)"
WANT_ROBOT=1
for a in "$@"; do [ "$a" = "--no-robot" ] && WANT_ROBOT=0; done

if [ "$WANT_ROBOT" = "0" ]; then
  echo "   ${c_dim}--no-robot 이므로 건너뛴다${c_off}"
elif up http://localhost:8000/api/state/full; then
  echo "   ${c_dim}이미 떠 있다 — 건너뛴다${c_off}"
else
  echo "   3D 뷰어 창이 뜬다. 로그: $LOG_DIR/sim.log"
  nohup ./run-sim.sh --scene "$SCENE" > "$LOG_DIR/sim.log" 2>&1 &
  echo $! > "$SIM_PID_FILE"
  if ! wait_for http://localhost:8000/api/state/full "데몬" 120; then
    say_bad "데몬 기동 실패 — tail -30 $LOG_DIR/sim.log 로 확인"
    tail -15 "$LOG_DIR/sim.log"
    exit 1
  fi
fi

# ── 3. 예열 ─────────────────────────────────────────────────────
# 첫 질문에서 프리필 비용을 물지 않도록 더미 요청을 한 번 보낸다.
say_step "예열"
curl -sf --max-time 60 http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"local","max_tokens":1,"messages":[{"role":"user","content":"안녕"}]}' \
  > /dev/null 2>&1 && echo "   LLM 프리필 예열 완료" || echo "   ${c_dim}예열 건너뜀${c_off}"

# 모션 데이터셋은 앱이 처음 로드할 때 내려받는다. 미리 캐시에 올려 둔다.
$PY - <<'PYEOF' 2>/dev/null && echo "   모션 카탈로그 준비 완료" || echo "   ${c_dim}모션 카탈로그 예열 건너뜀${c_off}"
from reachy_mini.motion.recorded_move import RecordedMoves
RecordedMoves("pollen-robotics/reachy-mini-emotions-library").list_moves()
PYEOF

# ── 4. 최종 점검 후 앱 진입 ─────────────────────────────────────
say_step "최종 점검"
status
echo
if [ "$WANT_ROBOT" = "1" ] && ! up http://localhost:8000/api/state/full; then
  say_bad "데몬이 없다. --no-robot 으로 대화만 하거나 로그를 확인한다"
  exit 1
fi

MODE_ARGS=()
for a in "$@"; do
  case "$a" in --text|--no-robot) MODE_ARGS+=("$a") ;; esac
done

if [ ${#MODE_ARGS[@]} -eq 0 ]; then
  say_step "음성 모드 — 말을 걸어보세요 (Ctrl-C 종료)"
  echo "   ${c_dim}로봇이 대답을 끝낸 뒤에 다음 말을 한다 (한 번에 한 사람씩)${c_off}"
else
  say_step "실행: demo.py ${MODE_ARGS[*]}"
fi
echo

# macOS 기본 bash 는 3.2 다. set -u 아래에서 원소 0개인 배열을 "${A[@]}" 로 펼치면
# unbound variable 로 죽는다(bash 4.4 부터 고쳐진 동작). 빈 경우를 아예 분기한다.
if [ ${#MODE_ARGS[@]} -eq 0 ]; then
  $PY apps/voice_chat/voice_chat/demo.py
else
  $PY apps/voice_chat/voice_chat/demo.py "${MODE_ARGS[@]}"
fi

echo
echo "${c_dim}서버는 계속 떠 있다. 다시 들어가려면 ./scripts/demo.sh, 완전 종료는 ./scripts/demo.sh --stop${c_off}"
