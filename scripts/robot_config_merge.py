"""로봇의 `config.json` 을 갱신한다 — 표준입력으로 현재 파일, 표준출력으로 새 파일.

`reachy.sh` 의 `robot_sync_config` 가 부른다. **셸 안의 한 줄짜리 파이썬이 아니라
파일로 둔 이유는 하나다: 테스트로 박제하기 위해서다.** 여기서 빠뜨리는 키 하나가
실기에서 "앱은 떴는데 조용히 반쪽으로 돈다" 로 나타난다 — 시뮬에서는 절대 안 보인다.

왜 환경변수가 아니라 파일인가: Wireless 에서 앱은 `POST /api/apps/start-app/` 로
**systemd 데몬이 낳는 자식**이라 운영자 셸의 export 가 닿지 않는다
(`apps/voice_chat/voice_chat/config.py` 머리말). 앱이 읽는 사다리는
환경변수 → 이 파일 → 기본값이고, 실기에서 실제로 닿는 단은 이 파일뿐이다.

기존 키(`REACHY_VAD_FACTOR` 등 현장에서 손으로 넣은 것)는 보존하고, 이 스크립트가
책임지는 키만 갱신한다.
"""

import json
import os
import sys

ROLES = ("mc", "docent")

# 이 스크립트가 소유하는 키. 값이 안 주어지면 **지운다** — 낡은 값이 남아
# 조용히 지난 시연의 배선으로 도는 것이 가장 찾기 어렵다.
_STAGE_KEYS = ("REACHY_ROLE", "REACHY_DIRECTOR_URL")


def merge(current: dict, env: dict) -> tuple[dict, list[str]]:
    """현재 설정에 이번 기동의 값을 얹는다. (새 설정, 사람이 읽을 메모) 를 준다."""
    d = dict(current)
    notes: list[str] = []

    ip = env["LANIP"]
    d["REACHY_LLM_URL"] = "http://%s:8080" % ip
    d["REACHY_STT_URL"] = "http://%s:8090/v1/audio/transcriptions" % ip
    d["TTS_QWEN_URL"] = "http://%s:%s/v1/audio/speech" % (ip, env["TTSPORT"])

    sel = (env.get("PROMPTSEL") or "").strip()
    if sel:
        d["REACHY_PROMPT"] = sel

    role = (env.get("ROLESEL") or "").strip().lower()
    if role:
        if role not in ROLES:
            raise SystemExit(
                f"REACHY_ROLE 이 {role!r} 다 — 쓸 수 있는 값: {', '.join(ROLES)}"
            )
        d["REACHY_ROLE"] = role
        d["REACHY_DIRECTOR_URL"] = (env.get("DIRURL") or "").strip() or (
            "ws://%s:%s" % (ip, env.get("DIRPORT") or "8777")
        )
        notes.append(f"2대 모드: 역할 {role} · 무대감독 {d['REACHY_DIRECTOR_URL']}")
    else:
        # 지난 시연의 역할이 남아 있으면 1대 모드로 돌리려던 로봇이 계속
        # 감독을 기다린다. 지우되 **지웠다고 말한다.**
        dropped = [k for k in _STAGE_KEYS if k in d]
        for k in dropped:
            del d[k]
        if dropped:
            notes.append(
                "REACHY_ROLE 이 없어 로봇 설정에서 " + "·".join(dropped) + " 를 지웠다 (1대 모드)"
            )
    return d, notes


def main() -> None:
    try:
        current = json.load(sys.stdin)
        if not isinstance(current, dict):
            current = {}
    except Exception:
        current = {}
    new, notes = merge(current, os.environ)
    for n in notes:
        print(n, file=sys.stderr)
    print(json.dumps(new, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
