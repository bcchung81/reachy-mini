"""`scripts/stage-env.sh` 자체의 동작을 확인한다.

`${1:?...}` 의 기본 메시지 안에 `{`/`}` 를 넣으면 bash 가 그것을 중첩 중괄호로
세어 `${...}` 확장을 조기 종료시킨다 — 인자를 정상적으로 줘도 값 뒤에 `}` 가
그대로 붙는다(REACHY_ROLE="mc}"). 코드를 읽어서는 못 잡고, 실제로 source 해서
값을 읽어야 잡힌다.
"""

import pathlib
import subprocess

SCRIPT = pathlib.Path(__file__).parent.parent / "scripts/stage-env.sh"

_KEYS = (
    "REACHY_ROLE",
    "REACHY_DIRECTOR_URL",
    "REACHY_LLM_URL",
    "REACHY_STT_URL",
    "TTS_QWEN_URL",
    "REACHY_AEC",
)
_MARKER = "___ENV___"


def _sourced_env(role: str) -> dict[str, str]:
    """스크립트를 실제로 source 한 뒤 우리가 보는 환경변수만 뽑아 돌려준다."""
    prints = "\n".join(
        f'printf "{_MARKER}{k}=%s\\n" "${{{k}:-}}"' for k in _KEYS
    )
    result = subprocess.run(
        ["bash", "-c", f"source {SCRIPT} {role} >/dev/null; {prints}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if line.startswith(_MARKER):
            k, _, v = line[len(_MARKER):].partition("=")
            out[k] = v
    return out


def test_REACHY_ROLE_이_정확히_mc_다():
    # 예전엔 `${1:?...{mc|docent}}` 의 중괄호 때문에 "mc}" 로 오염됐다.
    assert _sourced_env("mc")["REACHY_ROLE"] == "mc"


def test_REACHY_ROLE_이_정확히_docent_다():
    assert _sourced_env("docent")["REACHY_ROLE"] == "docent"


def test_인자가_없으면_소리_내서_실패한다():
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0
    assert "stage-env.sh" in result.stderr


def test_기본_주소들이_고정_IP_로_채워진다():
    # 설계 §6.1 — 두 로봇 모두 hostname 이 reachy-mini 라 .local 을 못 믿는다.
    env = _sourced_env("mc")
    assert env["REACHY_DIRECTOR_URL"] == "ws://192.168.0.10:8777"
    assert env["REACHY_LLM_URL"] == "http://192.168.0.10:8080"
    assert env["REACHY_STT_URL"] == "http://192.168.0.10:8090/v1/audio/transcriptions"
    assert env["TTS_QWEN_URL"] == "http://192.168.0.10:8099/v1/audio/speech"
    assert env["REACHY_AEC"] == "0"
