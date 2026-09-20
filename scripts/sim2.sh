#!/usr/bin/env bash
# 시뮬 2대 시연 — 사회자(mc) + 도슨트(docent) 를 한 맥에서 띄운다.
#
#   ./scripts/sim2.sh            기동. 끝나면 **무대감독 콘솔**이 이 터미널에 뜬다
#   ./scripts/sim2.sh stop       이 스크립트가 띄운 것을 내린다
#   ./scripts/sim2.sh status     지금 뭐가 떠 있는지
#
# 왜 감독이 전면인가: 시연은 콘솔 키(s 시작 / n 다음 / p 이전 / a 비상정지)로
# 몬다. 감독을 백그라운드로 돌리면 `run_console` 이 EOF 를 받아 "콘솔 없이
# 계속 돈다" 로 빠져 키를 못 쓴다(`stage/console.py` 참고). 그래서 나머지를
# 전부 뒤로 돌리고 감독만 앞에 둔다.
#
# 앱을 감독보다 **먼저** 띄우는 이유: 앱은 감독에 붙을 때까지 재접속을 계속
# 시도한다. 실기에서도 로봇이 먼저 켜져 있고 감독이 나중에 뜨는 일이 흔하다.
#
# ⚠️ 이 경로는 **시뮬 전용**이다. 실기는 로봇 두 대가 각자 데몬을 갖고
#    `./reachy.sh robot up` 으로 올린다 — `docs/install.md` 참고.

set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
LOG_DIR=".demo-logs"
P="$LOG_DIR/sim2"                      # pid·로그 접두

DIRECTOR_URL="${REACHY_DIRECTOR_URL:-ws://127.0.0.1:8777}"
LEVEL="${REACHY_AUDIENCE_LEVEL:-}"     # 비면 감독 기본값(일반)
MC_PORT=8000                           # ⚠️ 사회자는 반드시 8000 — 아래 주석 참고
DOCENT_PORT=8001
# 출력 장치. 같은 스피커로 나가면 도슨트 소리가 사회자 마이크로 되돌아와
# 자기목소리 루프가 실기보다 훨씬 쉽게 난다. 이름은 sounddevice 가 받는 것
# (장치 이름의 일부 또는 인덱스). 목록:
#   .venv/bin/python -c "import sounddevice; print(sounddevice.query_devices())"
MC_OUT="${REACHY_MC_AUDIO_OUT:-MacBook Pro 스피커}"
DOCENT_OUT="${REACHY_DOCENT_AUDIO_OUT:-}"   # 비면 기본 출력(= 섞인다, 경고한다)

c_ok=$'\033[32m'; c_bad=$'\033[31m'; c_warn=$'\033[33m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
step() { printf "\n%s▸ %s%s\n" "$c_dim" "$1" "$c_off"; }
ok()   { printf "   %s✓%s %s\n" "$c_ok" "$c_off" "$1"; }
bad()  { printf "   %s✗%s %s\n" "$c_bad" "$c_off" "$1"; }
warn() { printf "   %s⚠%s %s\n" "$c_warn" "$c_off" "$1"; }

up() { curl -sf --max-time 2 "$1" >/dev/null 2>&1; }

wait_for() {  # url label timeout_s
  local url=$1 label=$2 limit=${3:-60} n=0
  printf "   %s 대기" "$label"
  while ! up "$url"; do
    n=$((n + 1))
    if [ "$n" -ge "$limit" ]; then printf " %s시간초과%s\n" "$c_bad" "$c_off"; return 1; fi
    printf "."; sleep 1
  done
  printf " %s준비됨%s\n" "$c_ok" "$c_off"
}

kill_pid() {  # pidfile label
  local f=$1 label=$2
  [ -f "$f" ] || return 0
  local pid; pid=$(cat "$f" 2>/dev/null || true)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    ok "$label 내림 (pid $pid)"
  fi
  rm -f "$f"
}

stop_sim2() {
  step "정지"
  kill_pid "$P-app-mc.pid"      "사회자 앱"
  kill_pid "$P-app-docent.pid"  "도슨트 앱"
  kill_pid "$P-daemon-mc.pid"   "사회자 데몬(:$MC_PORT)"
  kill_pid "$P-daemon-docent.pid" "도슨트 데몬(:$DOCENT_PORT)"
  # 손으로 띄운 고아까지 쓸어낸다 — pid 파일만 믿으면 살아남는 것이 있다(실측).
  pkill -f "reachy_mini.daemon.app.main --mockup-sim" 2>/dev/null || true
  pkill -f "apps/voice_chat/voice_chat/main.py"       2>/dev/null || true
  ok "정리 완료"
  echo "   ${c_dim}추론 서버(LLM/STT/TTS)는 그대로 둔다 — 내리려면 ./reachy.sh stop${c_off}"
}

status_sim2() {
  step "상태"
  for spec in "LLM:8080:/health" "STT:8090:/health" "TTS:8099:/health" \
              "사회자 데몬:$MC_PORT:/api/daemon/status" "도슨트 데몬:$DOCENT_PORT:/api/daemon/status"; do
    IFS=: read -r name port path <<<"$spec"
    if up "http://localhost:$port$path"; then ok "$name (:$port)"; else bad "$name (:$port) 없음"; fi
  done
  pgrep -f "stage(/__main__.py)?$|python -m stage" >/dev/null 2>&1 \
    && ok "무대감독" || bad "무대감독 없음"
  # `$n개` 처럼 변수 뒤에 한글이 바로 붙으면 bash 가 한글 바이트를 변수명에
  # 끌어들여 `unbound variable` 이 난다(macOS bash 3.2 실측). 중괄호로 끊는다.
  # macOS 의 pgrep 에는 -c 가 없어 wc 로 센다.
  local n; n=$(pgrep -f "apps/voice_chat/voice_chat/main.py" 2>/dev/null | wc -l | tr -d " ")
  [ "${n:-0}" -ge 2 ] && ok "앱 ${n}개" || bad "앱 ${n}개 (2개여야 한다)"
}

case "${1:-start}" in
  stop)   stop_sim2; exit 0 ;;
  status) status_sim2; exit 0 ;;
  start)  ;;
  *) echo "쓰임: $0 [start|stop|status]"; exit 2 ;;
esac

mkdir -p "$LOG_DIR"

# ── 0. 사전 점검 ──────────────────────────────────────────────
step "사전 점검"
[ -x "$PY" ] || { bad "$PY 가 없다 — 이 저장소는 .venv 파이썬 하나만 쓴다"; exit 1; }
ok "인터프리터 $($PY -V 2>&1)"

# 수준·페르소나는 계획의 Task 3·4 가 만든다. 아직 없으면 **경고만** 하고 진행한다 —
# 없으면 감독이 지금까지 쓰던 고정 대사 경로로 돌 뿐 시연 자체는 된다.
if [ -f data/levels.yaml ]; then ok "수준 프로필 있음"; else
  warn "data/levels.yaml 이 없다 — 관람객 수준 기능은 아직 꺼져 있다(계획 Task 3)"; fi
if [ -f data/personas/mc.md ] && [ -f data/personas/docent.md ]; then
  ok "LLM 페르소나 있음 (사회자·도슨트)"
else
  warn "data/personas/*.md 가 없다 — 사회자는 큐시트 고정 대사로 말한다(계획 Task 4)"
fi
# 목소리 페르소나는 지금도 동작한다 — main.py 의 ROLE_VOICE 가 넣는다.
ok "목소리: 사회자 serena(1.27) / 도슨트 sohee(1.13)  ${c_dim}(main.py ROLE_VOICE)${c_off}"

if [ -z "$DOCENT_OUT" ]; then
  warn "도슨트 출력 장치가 지정되지 않았다 — 두 목소리가 **같은 스피커**로 나간다."
  echo "      ${c_dim}도슨트 소리가 사회자 마이크로 되돌아와 자기목소리 루프가 쉽게 난다.${c_off}"
  echo "      ${c_dim}갈라 주려면: REACHY_DOCENT_AUDIO_OUT='장치이름' $0${c_off}"
fi

# ── 1. 추론 3종 ───────────────────────────────────────────────
step "추론 서버 (LLM:8080 / STT:8090 / TTS:8099)"
if up http://localhost:8080/health && up http://localhost:8090/health && up http://localhost:8099/health; then
  ok "셋 다 이미 떠 있다"
else
  echo "   ${c_dim}없는 것이 있어 ./reachy.sh serve 로 띄운다 (모델 적재에 시간이 걸린다)${c_off}"
  # `serve` 는 끝에서 LAN 주소를 찾아 로봇용 설정을 찍는데, 시뮬에는 필요 없고
  # WiFi 가 꺼져 있으면 거기서 exit 1 한다. 서버는 그 **앞에서** 이미 떠 있으므로
  # 실패를 삼키고 아래에서 포트로 직접 확인한다.
  REACHY_BIND_HOST=127.0.0.1 ./reachy.sh serve || true
  for spec in "LLM:8080" "STT:8090" "TTS:8099"; do
    IFS=: read -r name port <<<"$spec"
    up "http://localhost:$port/health" || { bad "$name(:$port) 이 뜨지 않았다 — tail -30 $LOG_DIR/*.log"; exit 1; }
  done
  ok "셋 다 준비됨"
fi

# 첫 합성은 Metal 커널 JIT 로 8.5초가 걸린다(실측). 예열을 빠뜨리면 첫 큐가
# 헛타임아웃 나고 그 경로로 자기목소리 루프가 되살아난다(director.py 주석).
step "예열"
$PY scripts/warmup.py 2>&1 | sed 's/^/   /' || warn "예열에 실패했다 — 첫 발화가 느릴 수 있다"

# ── 2. 데몬 2대 ───────────────────────────────────────────────
# `--mockup-sim` 은 MuJoCo 가 필요 없어 mjpython/Cocoa 메인스레드 제약을 우회한다.
# 그래서 한 맥에서 두 개가 공존한다(`./reachy.sh sim` 은 두 번 못 띄운다).
#
# ⚠️ 사회자를 8000 에 두는 이유: SDK 의 `_check_daemon_on_localhost(port=8000)` 이
#    8000 고정이라, 8000 이 없으면 앱이 network 모드로 빠져 `reachy-mini.local` 을
#    찾다 실패한다.
step "시뮬 데몬 2대"
for spec in "mc:$MC_PORT" "docent:$DOCENT_PORT"; do
  IFS=: read -r role port <<<"$spec"
  if up "http://localhost:$port/api/daemon/status"; then
    ok "$role 데몬(:$port) 이미 떠 있다"
  else
    nohup $PY -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
      --fastapi-port "$port" --robot-name "$role" > "$P-daemon-$role.log" 2>&1 &
    echo $! > "$P-daemon-$role.pid"
    wait_for "http://localhost:$port/api/daemon/status" "$role 데몬(:$port)" 60 \
      || { bad "tail -30 $P-daemon-$role.log"; exit 1; }
  fi
done

# ── 3. 앱 2대 ─────────────────────────────────────────────────
# 감독보다 먼저 띄운다 — 붙을 때까지 재접속을 계속 시도한다.
step "앱 2대 (역할·데몬포트·출력장치를 짝지어 준다)"
start_app() {  # role port audio_out
  local role=$1 port=$2 out=$3
  # **`${out:+VAR="$out"}` 를 쓰지 않는다.** 확장 결과가 따옴표 밖이라 값에 공백이
  # 있으면(기본값이 "MacBook Pro 스피커" 다) 단어 분리가 나 `Pro` 가 명령어로 간다.
  # 서브셸에서 export 하면 값이 통째로 전달된다.
  (
    export REACHY_ROLE="$role"
    export REACHY_DAEMON_PORT="$port"
    export REACHY_DIRECTOR_URL="$DIRECTOR_URL"
    [ -n "$out" ] && export REACHY_AUDIO_OUT="$out"
    exec $PY -u apps/voice_chat/voice_chat/main.py > "$P-app-$role.log" 2>&1
  ) &
  echo $! > "$P-app-$role.pid"
  ok "$role 앱 → 데몬 :$port${out:+, 출력 '$out'}"
}
start_app mc     "$MC_PORT"     "$MC_OUT"
start_app docent "$DOCENT_PORT" "$DOCENT_OUT"

# ── 4. 무대감독 — 여기서부터 이 터미널을 쓴다 ──────────────────
step "무대감독"
echo "   ${c_dim}로그: $P-*.log   (앱·데몬은 뒤에서 돈다)${c_off}"
[ -n "$LEVEL" ] && echo "   관람객 수준: $LEVEL" || echo "   ${c_dim}관람객 수준: 감독 기본값${c_off}"
echo
echo "   ${c_ok}두 로봇이 붙으면 아래 콘솔에 '붙었다' 가 뜬다. 그 뒤 s 로 시작한다.${c_off}"
echo "   ${c_dim}s 시작 · n 다음 · p 이전 · a 비상정지 · r 재시작 · q 종료${c_off}"
echo "   ${c_dim}끝나면 이 창에서 Ctrl-C, 그다음 ./scripts/sim2.sh stop${c_off}"
echo

# 감독이 죽거나 Ctrl-C 로 나가면 뒤에 남은 것들을 정리한다 — 앱이 살아 있으면
# 마이크를 계속 쥐고 있고, 다음 실행이 같은 포트에 붙어 유령 연결이 된다.
trap 'echo; stop_sim2' EXIT

export REACHY_DIRECTOR_HOST=127.0.0.1
[ -n "$LEVEL" ] && export REACHY_AUDIENCE_LEVEL="$LEVEL"
exec $PY -m stage
