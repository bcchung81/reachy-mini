#!/usr/bin/env bash
# Reachy Mini 전파체험관 — 실행 메뉴(단순판). 번호 하나만 고르면 알맞은 스위치를 붙여 ./reachy.sh 를 부른다.
#
#   ./run-app.sh            메뉴(Enter = 1번 실기 공연)
#   ./run-app.sh 1          1번을 바로
#   RUN_APP_DRY=1 ./run-app.sh   실행하지 않고 고른 명령만 보여 준다(점검·테스트용)
#
#   1) 공연 — 실기 로봇 2대(사회자 REACHY_MC_HOST·도슨트 REACHY_DOCENT_HOST, 기본 192.168.0.4 / .5)
#   2) 공연 연습 — 시뮬(이 맥 하나에서 두 대)
#   3) 상태 확인   4) 모두 끄기
#
# 엔진은 묻지 않는다 — .env 에 키가 있으면 외부 API(목소리 ElevenLabs · 대화·음성인식 OpenAI), 없는 것은 로컬로 돌고 그렇다고 한 줄 알린다.
# **키가 둘 다 있으면 외부 API 전용**(REACHY_LOCAL_MODELS=off) — 이 맥에 로컬 모델(Gemma·Whisper·Qwen TTS)을 띄우지 않는다.
#   대본 공연은 구워 둔 음성 캐시로 돌고, 인터넷이 끊기면 즉석 답·음성인식만 멈춘다(경고가 남는다). docs/real-robot-deployment.md §15.13
#   띄우기 직전에 `./reachy.sh clean-local` 로 **지난 실행의 로컬 모델과 설정이 다른 서버를 먼저 내린다**(같은 설정의 외부 전용 서버는 남긴다.
#   감독이 떠 있으면 공연 중일 수 있어 아무것도 안 내리고 멈춘다. MCP·시뮬 데몬은 안 건드린다).
# **공연은 띄운 뒤 감독 창에서 s → Enter 로 시작한다**(조정실의 [공연 시작] 버튼도 같다). 시작 전에는 로봇이 말하지 않는다.
# 띄우면 조정실을 자동으로 연다 — **시연 화면(교육자료 모션)은 조정실 안에 있다**: 관람객 수준을 고르고 [공연 시작]을 누르면 그 자리에서
# 화면이 바뀌고 로봇을 따라간다. 프로젝터에는 조정실의 [프로젝터로 띄우기](= /stage/auto 새 창). ~~조정실과 /stage/auto 를 따로 연다~~
# (2026-11-13 오전) — 두 탭이 따로 놀아 조정하는 동안 화면이 안 보였다.
#
# 메뉴에서 뺀 것(직접 실행):
#   TTS_ENGINE=elevenlabs ./reachy.sh bake [--check|--retake-readings]   고정 대사 굽기
#   .venv/bin/python scripts/tts_review.py                              구운 대사 검수
#   .venv/bin/python scripts/handout_live/fake_show.py                  로봇 없이 교육자료 화면 확인
#   ./reachy.sh demo · ./reachy.sh logs                                 1대 자유 대화 · 로그
#
# 실제 기동·종료는 전부 ./reachy.sh 가 한다 — 이 파일은 고르는 일만 한다. 키는 **있는지만** 본다(값은 읽지도 출력하지도 않는다).
# macOS 기본 bash 3.2 로 돈다. 변수 바로 뒤에 한글·기호가 오면 ${VAR} 로 감싼다(docs/lessons.md).
set -uo pipefail
cd "$(dirname "$0")" || exit 1

DRY="${RUN_APP_DRY:-0}"
ENV_FILE="${RUN_APP_ENV_FILE:-.env}"          # 테스트가 가짜 .env 를 줄 때만 바꾼다
DASH="http://127.0.0.1:${REACHY_DASHBOARD_PORT:-8778}"

say() { printf '%s\n' "$*"; }

ask() {  # ask "질문" "기본값" → ANSWER. 입력이 끝나면(파이프가 닫히면) 매달리지 않고 나간다.
  local ans=""
  printf '%s [%s]: ' "$1" "$2"
  if ! IFS= read -r ans; then say; say "입력이 끝났다 — 나간다"; exit 1; fi
  ANSWER="${ans:-$2}"
}

has_key() {  # 환경변수나 .env 에 **있는지만**
  local k="$1"
  [ -n "${!k:-}" ] && return 0
  grep -Eq "^(export[[:space:]]+)?${k}=.+" "$ENV_FILE" 2>/dev/null
}

open_when_up() {  # 조정실이 뜨면 주소들을 연다(뒤에서 기다린다 — 감독 콘솔이 이 터미널을 차지한다)
  if [ "$DRY" = "1" ]; then say "  (점검) 조정실이 뜨면 연다: $*"; return 0; fi
  (
    for _ in $(seq 1 240); do
      if curl -fs -o /dev/null "$1" 2>/dev/null; then
        for u in "$@"; do
          case "$(uname)" in
            Darwin) open "$u" ;;
            *) command -v xdg-open >/dev/null 2>&1 && xdg-open "$u" >/dev/null 2>&1 ;;
          esac
        done
        exit 0
      fi
      sleep 1
    done
  ) &
}

prep() {  # prep 명령… — 띄우기 전 단계. 보여 주고 실행하고, 실패하면 띄우지 않고 나간다(이유는 그 명령이 찍었다)
  say "정리할 명령: $*"
  if [ "$DRY" = "1" ]; then return 0; fi
  "$@" || { say "  ⚠ 정리에서 멈췄다 — 위 이유를 보고 다시 ./run-app.sh"; exit 1; }
}

launch() {  # launch [할당…] -- 명령…  — 보여 주고 실행한다
  local envs=""
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do envs="$envs $1"; shift; done
  [ $# -gt 0 ] && shift
  say "실행할 명령:${envs} $*"
  if [ "$DRY" = "1" ]; then exit 0; fi
  # shellcheck disable=SC2086 — 할당 목록을 낱말로 나눠 env 에 넘긴다(값에 공백이 없다)
  exec env $envs "$@"
}

show() {  # show --robot|--sim
  local engines="" voice="로컬 Qwen" talk="로컬" external=0
  if has_key ELEVENLABS_API_KEY; then engines="TTS_ENGINE=elevenlabs"; voice="ElevenLabs"; fi
  if has_key OPENAI_API_KEY; then engines="$engines REACHY_LLM_ENGINE=openai REACHY_STT_ENGINE=openai"; talk="OpenAI"; fi
  say ""
  if has_key ELEVENLABS_API_KEY && has_key OPENAI_API_KEY; then
    # 셋 다 외부면 로컬 모델은 폴백 자리로만 떠서 메모리·발열만 쓴다(Qwen TTS 3.2 GB) — 띄우지 않는다.
    engines="$engines REACHY_LOCAL_MODELS=off"
    external=1
    say "엔진: 목소리 ${voice} · 대화·음성인식 ${talk} — 외부 API 전용(이 맥에 로컬 모델을 띄우지 않는다)"
    say "  인터넷이 끊기면: 대본 공연은 구워 둔 음성으로 계속, 즉석 답·음성인식만 멈춘다(경고가 남는다)"
  else
    say "엔진: 목소리 ${voice} · 대화·음성인식 ${talk}"
    has_key ELEVENLABS_API_KEY || say "  ⚠ ELEVENLABS_API_KEY 가 .env 에 없다 — 목소리가 로컬(Qwen)로 돈다"
    has_key OPENAI_API_KEY || say "  ⚠ OPENAI_API_KEY 가 .env 에 없다 — 대화·음성인식이 로컬로 돈다"
    say "  ⚠ 키가 다 있지 않아 로컬 모델을 띄운다 — 외부 API 전용이 아니다"
  fi
  [ "$1" = "--robot" ] && say "로봇: 사회자 ${REACHY_MC_HOST:-192.168.0.4} · 도슨트 ${REACHY_DOCENT_HOST:-192.168.0.5}"
  # 지난 실행의 로컬 구성이 남아 있으면 start 가 "stop 후 다시" 로 멈추고 로컬 모델이 메모리를 쥔다 — 먼저 내린다.
  [ "$external" = "1" ] && prep ./reachy.sh clean-local "$1"
  say ""
  say "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  say "  로봇 2대가 붙으면(\"두 로봇이 다 붙었다\") 이 창에 s → Enter = 공연 시작"
  say "  시작하기 전에는 로봇이 말하지 않는다. 끝내기: q"
  say "  조정실(공연 시작 버튼): ${DASH}/"
  say "  시연 화면은 조정실 안에 있다 — 수준을 고르고 [공연 시작]을 누르면 화면이 바뀌고 로봇을 따라간다"
  say "  프로젝터: 조정실의 [프로젝터로 띄우기] (= ${DASH}/stage/auto 새 창, 전체 화면 ⌃⌘F)"
  say "  ↑ 조정실은 감독이 뜨면 자동으로 연다"
  say "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  open_when_up "${DASH}/"
  # shellcheck disable=SC2086
  launch $engines -- ./reachy.sh start "$1"
}

main() {
  local choice="${1:-}"
  case "$choice" in
    -h|--help|help) awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; exit 0 ;;
  esac
  if [ -z "$choice" ]; then
    say ""
    say "Reachy Mini 전파체험관"
    say "  1) 공연 — 실기 로봇 2대"
    say "  2) 공연 연습 — 시뮬(이 맥)"
    say "  3) 상태 확인"
    say "  4) 모두 끄기"
    say "  q) 나가기"
    while :; do
      ask "번호" 1
      case "$ANSWER" in [1-4]|q|Q) choice="$ANSWER"; break ;; esac
      say "  1~4 또는 q 를 고른다."
    done
  fi
  case "$choice" in
    1) show --robot ;;
    2) show --sim ;;
    3) launch -- ./reachy.sh check ;;
    4) ask "띄운 것을 전부 끈다(감독·대시보드·추론 서버 포함). 계속할까 (y/n)" n
       case "$ANSWER" in y|Y) launch -- ./reachy.sh stop ;; *) say "취소했다." ;; esac ;;
    q|Q) say "나갔다." ;;
    *) say "모르는 번호: $choice — ./run-app.sh 로 메뉴를 본다"; exit 2 ;;
  esac
}

main "$@"
