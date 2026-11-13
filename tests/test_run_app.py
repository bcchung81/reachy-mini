"""실행 메뉴(`run-app.sh`, 단순판 2026-11-13) — 번호 하나로 알맞은 스위치를 붙여 `./reachy.sh` 를 부른다.

`RUN_APP_DRY=1` 이면 실행하지 않고 고른 명령만 찍는다 — 그것으로 선택지마다 어떤 명령이 나가는지 박제한다.
macOS 기본 bash 3.2(`/bin/bash`)로 돌린다 — 운영자 맥이 그것이다.

단순판인 이유: 실기 첫 구동에서 운영자가 하위 질문을 거쳐 띄운 뒤 감독 창에서 `s`(공연 시작)를 몰라 로봇이 한 마디도 안 했다.
질문을 없애고, 띄우기 직전에 시작하는 법을 크게 보여 준다.
"""

import os
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "run-app.sh"
BASH = "/bin/bash" if pathlib.Path("/bin/bash").exists() else "bash"
STRIP = ("ELEVENLABS_API_KEY", "OPENAI_API_KEY", "REACHY_MC_HOST", "REACHY_DOCENT_HOST", "REACHY_DASHBOARD_PORT",
         "TTS_ENGINE", "REACHY_LLM_ENGINE", "REACHY_STT_ENGINE", "REACHY_LOCAL_MODELS")
# 키가 둘 다 있으면 외부 API 전용 — 로컬 모델(Gemma·Whisper·Qwen TTS)을 띄우지 않는다(2026-11-13 사용자 결정).
EXTERNAL = "TTS_ENGINE=elevenlabs REACHY_LLM_ENGINE=openai REACHY_STT_ENGINE=openai REACHY_LOCAL_MODELS=off"


def run(inp, *args, keys=("ELEVENLABS_API_KEY", "OPENAI_API_KEY"), tmp_path=None, extra=None):
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    envf = tmp_path / "fake.env"
    envf.write_text("".join(f"{k}=가짜값\n" for k in keys), encoding="utf-8")   # 있는지만 본다 — 값은 아무거나
    env.update(RUN_APP_DRY="1", RUN_APP_ENV_FILE=str(envf), **(extra or {}))
    r = subprocess.run([BASH, str(SCRIPT), *args], input=inp, capture_output=True, text=True, cwd=ROOT, env=env, timeout=30)
    return r.returncode, r.stdout + r.stderr


def cmd(out):
    m = re.search(r"실행할 명령: ?(.*)", out)
    return m.group(1).strip() if m else None


def test_문법이_맞고_변수_바로_뒤에_멀티바이트가_없다():
    assert subprocess.run([BASH, "-n", str(SCRIPT)]).returncode == 0
    for n, ln in enumerate(SCRIPT.read_text(encoding="utf-8").splitlines(), 1):
        assert not re.search(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]", ln), f"{n}: {ln}"   # bash 3.2 가 이름으로 읽는다
    assert os.access(SCRIPT, os.X_OK)


def test_메뉴는_네_가지뿐이고_Enter_면_실기_공연(tmp_path):
    code, out = run("\n", tmp_path=tmp_path)
    assert [l.strip()[:2] for l in out.splitlines() if re.match(r"\s+[1-4q]\)", l)] == ["1)", "2)", "3)", "4)", "q)"]
    assert code == 0 and cmd(out) == f"{EXTERNAL} ./reachy.sh start --robot"


def test_공연은_묻지_않고_바로_띄우며_s_로_시작하는_법을_보여_준다(tmp_path):
    code, out = run("1\n", tmp_path=tmp_path)
    # 질문은 `번호 [1]: ` 꼴이다 — 안내 문구의 [공연 시작]·[프로젝터로 띄우기] 같은 버튼 이름은 세지 않는다.
    assert len(re.findall(r"\[[^\]]*\]: ", out)) == 1, "하위 질문이 없어야 한다(번호 질문 하나뿐)"
    assert "s → Enter = 공연 시작" in out and "시작하기 전에는 로봇이 말하지 않는다" in out
    # 조정실 하나만 연다 — 시연 화면이 그 안에 있다(2026-11-13: 탭 두 개가 따로 놀았다). 프로젝터는 조정실 버튼으로.
    assert "조정실이 뜨면 연다: http://127.0.0.1:8778/\n" in out and "/stage/auto 새 창" in out
    assert "시연 화면은 조정실 안에 있다" in out
    assert "로봇: 사회자 192.168.0.4 · 도슨트 192.168.0.5" in out


def test_공연_연습은_시뮬(tmp_path):
    code, out = run("2\n", tmp_path=tmp_path)
    assert cmd(out) == f"{EXTERNAL} ./reachy.sh start --sim" and "로봇:" not in out


def test_키가_둘_다_있으면_외부_API_전용이고_그렇다고_말한다(tmp_path):
    code, out = run("1\n", tmp_path=tmp_path)
    assert "REACHY_LOCAL_MODELS=off" in cmd(out)
    assert "외부 API 전용(이 맥에 로컬 모델을 띄우지 않는다)" in out and "즉석 답·음성인식만 멈춘다" in out
    assert "로컬 모델을 띄운다" not in out


def test_키가_없는_엔진은_로컬로_돌고_한_줄_알린다(tmp_path):
    """조용히 로컬로 바꾸면 '목소리가 왜 바뀌었나' 를 시연장에서 못 찾는다 — 알리기는 하되 묻지는 않는다.
    하나라도 로컬이면 외부 전용(REACHY_LOCAL_MODELS=off)을 켜지 않는다 — 켜면 reachy.sh 가 계획 단계에서 멈춘다."""
    code, out = run("1\n", keys=("ELEVENLABS_API_KEY",), tmp_path=tmp_path)
    assert cmd(out) == "TTS_ENGINE=elevenlabs ./reachy.sh start --robot"
    assert "OPENAI_API_KEY 가 .env 에 없다" in out and "목소리 ElevenLabs · 대화·음성인식 로컬" in out
    assert "로컬 모델을 띄운다 — 외부 API 전용이 아니다" in out
    code, out = run("1\n", keys=(), tmp_path=tmp_path)
    assert cmd(out) == "./reachy.sh start --robot" and "ELEVENLABS_API_KEY 가 .env 에 없다" in out


def test_로봇_주소는_환경변수를_따른다(tmp_path):
    code, out = run("1\n", tmp_path=tmp_path, extra={"REACHY_MC_HOST": "10.0.0.7"})
    assert "사회자 10.0.0.7" in out


def test_키_값은_출력하지_않는다(tmp_path):
    code, out = run("1\n", tmp_path=tmp_path)
    assert "가짜값" not in out


@pytest.mark.parametrize("inp,want", [("3\n", "./reachy.sh check"), ("4\ny\n", "./reachy.sh stop")])
def test_상태_확인과_끄기(tmp_path, inp, want):
    code, out = run(inp, tmp_path=tmp_path)
    assert cmd(out) == want


def test_끄기는_확인을_받는다(tmp_path):
    code, out = run("4\n\n", tmp_path=tmp_path)                           # 기본 n
    assert cmd(out) is None and "취소했다" in out


def test_범위_밖_번호는_다시_묻고_입력이_끝나면_매달리지_않는다(tmp_path):
    code, out = run("9\nx\n3\n", tmp_path=tmp_path)
    assert out.count("1~4 또는 q") == 2 and cmd(out) == "./reachy.sh check"
    code, out = run("", tmp_path=tmp_path)                                # 번호 질문 도중 입력이 끝남
    assert code == 1 and "입력이 끝났다" in out


def test_번호를_인자로_주면_메뉴를_건너뛴다(tmp_path):
    code, out = run("", "3", tmp_path=tmp_path)
    assert cmd(out) == "./reachy.sh check" and "전파체험관" not in out


def test_도움말에_메뉴에서_뺀_도구가_있다(tmp_path):
    code, out = run("", "--help", tmp_path=tmp_path)
    assert code == 0 and "RUN_APP_DRY=1" in out and "bake" in out and "fake_show.py" in out and "s → Enter" in out


def test_외부_전용이면_띄우기_전에_정리부터_한다(tmp_path):
    """지난 실행의 로컬 구성(폴백 낀 게이트웨이·로컬 모델)이 남아 있으면 start 가 "stop 후 다시" 로 멈춘다(2026-11-13 실측) —
    운영자에게 넘기지 않고 run-app 이 먼저 내린다. 대상(--robot/--sim)을 같이 넘긴다 — 바인드가 달라 남길지가 달라진다."""
    for inp, target in (("1\n", "--robot"), ("2\n", "--sim")):
        code, out = run(inp, tmp_path=tmp_path)
        assert f"정리할 명령: ./reachy.sh clean-local {target}" in out
        assert out.index("정리할 명령") < out.index("실행할 명령")
    code, out = run("1\n", keys=("ELEVENLABS_API_KEY",), tmp_path=tmp_path)
    assert "정리할 명령" not in out                                     # 로컬 모델이 필요한 구성은 건드리지 않는다


def test_정리가_멈추면_띄우지_않는다(tmp_path):
    """가짜 reachy.sh 로 실제로 돌린다(점검 모드가 아니다) — 정리가 실패(감독이 떠 있다 등)하면 start 를 부르지 않는다."""
    work = tmp_path / "w"
    work.mkdir()
    (work / "run-app.sh").write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    calls = tmp_path / "calls.txt"
    fake = work / "reachy.sh"
    fake.write_text(f'#!/bin/sh\necho "reachy $*" >> "{calls}"\n[ "$1" = clean-local ] && exit 1\nexit 0\n')
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    envf = tmp_path / "fake.env"
    envf.write_text("ELEVENLABS_API_KEY=가짜값\nOPENAI_API_KEY=가짜값\n", encoding="utf-8")
    env.update(RUN_APP_ENV_FILE=str(envf))
    r = subprocess.run([BASH, str(work / "run-app.sh"), "1"], capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 1 and "정리에서 멈췄다" in r.stdout, r.stdout + r.stderr
    assert calls.read_text().splitlines() == ["reachy clean-local --robot"]       # start 는 안 불렸다
