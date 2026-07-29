#!/bin/bash
# 시연 전 환경 점검 — 전부 OK여야 데모 가능
ok=0; fail=0
chk() { if eval "$2" >/dev/null 2>&1; then echo "OK   $1"; ok=$((ok+1)); else echo "FAIL $1  ← $3"; fail=$((fail+1)); fi }
chk "데몬(:8000)"  "curl -sf --max-time 2 localhost:8000/api/state/full"          "./run-sim.sh 실행"
chk "LLM(:8080)"   "curl -sf --max-time 2 localhost:8080/health"                  "llama reach-llm 실행"
chk "STT(:8090)"   "curl -sf --max-time 2 localhost:8090/health"                  ".venv/bin/python stt_server.py 실행"
chk "TTS(Yuna)"    "say -v '?' | grep -q Yuna"                                    "macOS 한국어 음성 설치"
echo "---- $ok OK / $fail FAIL"
exit $fail
