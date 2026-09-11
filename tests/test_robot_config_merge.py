"""로봇 config.json 병합 — 실기에서 앱에 값이 닿는 **유일한 길**이다.

Wireless 의 앱은 `POST /api/apps/start-app/` 로 데몬이 낳는 자식 프로세스라
운영자 셸의 export 가 건너오지 않는다. 그래서 `REACHY_ROLE` 이 이 파일에
안 실리면 두 로봇이 조용히 1대 모드로 뜬다 — 로그는 정상으로 보인다(리뷰 C2).
셸 안의 한 줄 파이썬이었다면 이 테스트를 못 썼다.
"""

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import robot_config_merge as merge_mod  # noqa: E402

_BASE = {"LANIP": "192.168.0.10", "TTSPORT": "8099"}


def merge(current=None, **env):
    return merge_mod.merge(current or {}, {**_BASE, **env})


def test_추론_3종_주소가_노트북을_가리킨다():
    d, _ = merge()
    assert d["REACHY_LLM_URL"] == "http://192.168.0.10:8080"
    assert d["REACHY_STT_URL"] == "http://192.168.0.10:8090/v1/audio/transcriptions"
    assert d["TTS_QWEN_URL"] == "http://192.168.0.10:8099/v1/audio/speech"


def test_현장에서_손으로_넣은_키는_보존한다():
    d, _ = merge({"REACHY_VAD_FACTOR": "2.5"})
    assert d["REACHY_VAD_FACTOR"] == "2.5"


def test_역할을_주면_역할과_무대감독_주소가_실린다():
    d, notes = merge(ROLESEL="mc")
    assert d["REACHY_ROLE"] == "mc"
    assert d["REACHY_DIRECTOR_URL"] == "ws://192.168.0.10:8777"
    assert any("사회자" in n or "mc" in n for n in notes)


def test_무대감독_주소를_직접_주면_그것이_이긴다():
    d, _ = merge(ROLESEL="docent", DIRURL="ws://10.0.0.5:9000")
    assert d["REACHY_DIRECTOR_URL"] == "ws://10.0.0.5:9000"


def test_포트를_바꾸면_주소에_반영된다():
    d, _ = merge(ROLESEL="docent", DIRPORT="9999")
    assert d["REACHY_DIRECTOR_URL"] == "ws://192.168.0.10:9999"


def test_대문자와_공백을_받아준다():
    d, _ = merge(ROLESEL=" MC ")
    assert d["REACHY_ROLE"] == "mc"


def test_모르는_역할은_소리_내서_실패한다():
    """오타 하나로 로봇이 조용히 1대 모드가 되면 시연장에서 못 찾는다."""
    with pytest.raises(SystemExit, match="REACHY_ROLE"):
        merge(ROLESEL="사회자")


def test_역할이_없으면_지난_시연의_역할을_지우고_말한다():
    """낡은 역할이 남으면 1대 모드로 돌리려던 로봇이 계속 감독을 기다린다.
    지우는 것 자체보다 **지웠다고 말하는 것**이 중요하다."""
    d, notes = merge({"REACHY_ROLE": "mc", "REACHY_DIRECTOR_URL": "ws://old:8777"})
    assert "REACHY_ROLE" not in d
    assert "REACHY_DIRECTOR_URL" not in d
    assert any("REACHY_ROLE" in n for n in notes)


def test_프롬프트는_주었을_때만_바꾼다():
    assert "REACHY_PROMPT" not in merge()[0]
    assert merge(PROMPTSEL="exhibit")[0]["REACHY_PROMPT"] == "exhibit"


def test_스크립트로_직접_돌려도_같다():
    """reachy.sh 가 부르는 방식 그대로 — stdin → stdout 파이프."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/robot_config_merge.py")],
        input=json.dumps({"REACHY_VAD_FACTOR": "2.5"}),
        capture_output=True,
        text=True,
        env={**_BASE, "ROLESEL": "docent", "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["REACHY_ROLE"] == "docent"
    assert d["REACHY_VAD_FACTOR"] == "2.5"
    # 메모는 stderr 로 — stdout 은 순수 JSON 이어야 셸이 파일로 그대로 붓는다.
    assert "docent" in r.stderr


def test_reachy_sh_가_이_스크립트를_쓴다():
    """셸에 로직이 되살아나면 이 테스트가 먼저 실패한다."""
    src = (ROOT / "reachy.sh").read_text()
    assert "scripts/robot_config_merge.py" in src
    assert 'ROLESEL="${REACHY_ROLE:-}"' in src
