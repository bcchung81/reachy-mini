#!/usr/bin/env bash
# 2대 시연 환경변수. 로봇에 올리기 전에 이 값들을 채운다.
#
#   사회자 로봇에서:  source scripts/stage-env.sh mc
#   도슨트 로봇에서:  source scripts/stage-env.sh docent
#
# 주소는 **고정 IP** 를 쓴다. 두 로봇 모두 hostname 이 reachy-mini 라
# reachy-mini.local 이 어느 쪽을 가리키는지 보장되지 않는다(설계 §6.1).
set -eu

ROLE="${1:?사용법: source scripts/stage-env.sh {mc|docent}}"
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
