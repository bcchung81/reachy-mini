#!/usr/bin/env bash
# 2대 시연 환경변수. 로봇에 올리기 전에 이 값들을 채운다.
#
#   사회자 로봇에서:  source scripts/stage-env.sh mc
#   도슨트 로봇에서:  source scripts/stage-env.sh docent
#
# 주소는 **고정 IP** 를 쓴다. 두 로봇 모두 hostname 이 reachy-mini 라
# reachy-mini.local 이 어느 쪽을 가리키는지 보장되지 않는다(설계 §6.1).
#
# `set -eu` 를 쓰지 않는다. 이 파일은 **source** 되므로 셸 옵션이 운영자의 세션에
# 그대로 남고, 그 뒤 실패하는 명령 하나(`grep` 불일치, 오타)에 SSH 세션이 끊긴다
# (리뷰 A7c, 실측). 인자 검사는 return/exit 로 한다 — `${1:?}` 도 쓰지 않는다:
# errexit 아래서는 그것도 셸을 끝내고, 메시지에 `{`/`}` 를 넣으면 bash 가 중첩
# 중괄호로 세어 값 뒤에 `}` 가 붙는 함정도 있었다(REACHY_ROLE="mc}", 옛 테스트).
if [ -z "${1:-}" ]; then
  echo "사용법: source scripts/stage-env.sh mc 또는 docent" >&2
  return 1 2>/dev/null || exit 1
fi
ROLE="$1"
PC_IP="${PC_IP:-192.168.0.10}"

export REACHY_ROLE="$ROLE"
export REACHY_DIRECTOR_URL="ws://${PC_IP}:8777"
export REACHY_LLM_URL="http://${PC_IP}:8080"
export REACHY_STT_URL="http://${PC_IP}:8090/v1/audio/transcriptions"
export TTS_QWEN_URL="http://${PC_IP}:8099/v1/audio/speech"

# 실기는 XMOS 하드웨어 AEC 가 그 자리를 대신한다 — 시뮬 전용 우회를 켜지 않는다.
export REACHY_AEC="${REACHY_AEC:-0}"

echo "역할=$ROLE  무대감독=$REACHY_DIRECTOR_URL  추론=$PC_IP"
echo "음성은 main.py 가 역할에 맞춰 넣는다(TTS_QWEN_VOICE 를 여기서 정하면 그것이 이긴다)"
