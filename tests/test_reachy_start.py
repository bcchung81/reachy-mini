"""`./reachy.sh start --sim | --robot` 의 기동 계획(`--dry-run`)을 본다.

실제 기동은 추론 3종·데몬·로봇까지 건드려 테스트에서 못 돌린다. 대신 `--dry-run` 이
**무엇을 어디에 띄울지**를 `PLAN ` 줄로 찍고, 그 줄이 계약이다 — 대상·포트·역할·바인드가
바뀌면 여기서 먼저 깨진다(설계 `docs/superpowers/specs/2026-09-21-launch-and-modes-design.md` 1-1).

셸은 `bash` 그대로다 — macOS 기본 bash 3.2 에서 돈다는 것도 같이 본다.
"""

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 계획에 들어가는 값을 바꾸는 환경변수. 개발자 셸에 export 돼 있으면(문서가 `export
# REACHY_DIRECTOR_PORT=8777` 을 권한다) 테스트가 그 값을 따라가 엉뚱하게 깨진다 —
# 계획의 **기본값**을 보려는 테스트는 이것들을 지우고 시작한다.
_PLAN_ENV = (
    "REACHY_BIND_HOST",
    "REACHY_DIRECTOR_PORT",
    "REACHY_DASHBOARD_PORT",
    "REACHY_DASHBOARD_HOST",
    "REACHY_MC_HOST",
    "REACHY_DOCENT_HOST",
    "TTS_QWEN_PORT",
    "REACHY_PY",
)


def _run(*args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in _PLAN_ENV}
    env.update(env_extra or {})
    return subprocess.run(["bash", str(ROOT / "reachy.sh"), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=30)


def _plan(stdout):
    return [l for l in stdout.splitlines() if l.startswith("PLAN ")]


def test_start_sim_dry_run_은_시뮬_두_대와_루프백_계획을_찍는다():
    r = _run("start", "--sim", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert _plan(r.stdout) == [
        "PLAN infer bind=127.0.0.1 ports=8080,8090,8099",
        "PLAN robot role=mc target=sim port=8000",
        "PLAN robot role=docent target=sim port=8001",
        "PLAN director bind=127.0.0.1 port=8777 dashboard=http://127.0.0.1:8778/",
    ]


def test_start_robot_dry_run_은_환경변수의_로봇_주소를_쓴다():
    """기본값(192.168.0.4/.5)이 아닌 주소로 본다 — 함정 ③."""
    r = _run("start", "--robot", "--dry-run",
             env_extra={"REACHY_MC_HOST": "10.9.8.21", "REACHY_DOCENT_HOST": "10.9.8.22"})
    assert r.returncode == 0, r.stderr
    assert _plan(r.stdout) == [
        "PLAN infer bind=0.0.0.0 ports=8080,8090,8099",
        "PLAN robot role=mc target=10.9.8.21",
        "PLAN robot role=docent target=10.9.8.22",
        "PLAN director bind=0.0.0.0 port=8777 dashboard=http://127.0.0.1:8778/",
    ]


def test_start_robot_dry_run_은_주소가_없으면_고정_IP_기본값을_쓴다():
    """두 로봇의 hostname 이 둘 다 `reachy-mini` 라 `.local` 은 못 믿는다 — 고정 IP 가 기본이다."""
    r = _run("start", "--robot", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert _plan(r.stdout)[1:3] == [
        "PLAN robot role=mc target=192.168.0.4",
        "PLAN robot role=docent target=192.168.0.5",
    ]


def test_start_는_감독과_대시보드_포트를_환경변수에서_읽는다():
    """감독(`python -m stage`)이 같은 변수를 읽는다 — 계획이 기본값을 박아 두면 앱은 8777 로
    붙으러 가는데 감독은 다른 포트에 떠서 조용히 못 만난다."""
    r = _run("start", "--sim", "--dry-run",
             env_extra={"REACHY_DIRECTOR_PORT": "9777", "REACHY_DASHBOARD_PORT": "9778"})
    assert r.returncode == 0, r.stderr
    assert _plan(r.stdout)[-1] == (
        "PLAN director bind=127.0.0.1 port=9777 dashboard=http://127.0.0.1:9778/"
    )


def test_start_는_대상_없이_부르면_쓰임새를_찍고_2로_끝난다():
    r = _run("start", "--dry-run")
    assert r.returncode == 2
    assert "--sim" in (r.stdout + r.stderr) and "--robot" in (r.stdout + r.stderr)
    assert _plan(r.stdout) == []


def test_start_는_두_대상을_함께_받지_않는다():
    r = _run("start", "--sim", "--robot", "--dry-run")
    assert r.returncode == 2
    assert _plan(r.stdout) == []


def test_start_는_모르는_인자를_거절한다():
    r = _run("start", "--sim", "--dryrun")
    assert r.returncode == 2
    assert "--dryrun" in r.stdout
    assert _plan(r.stdout) == []


def test_dry_run_은_아무것도_띄우지_않는다(tmp_path):
    """`PY` 를 없는 인터프리터로 바꿔도 dry-run 은 성공해야 한다 — 파이썬·네트워크를 안 건드린다는 증거."""
    r = _run("start", "--sim", "--dry-run", env_extra={"REACHY_PY": str(tmp_path / "없음")})
    assert r.returncode == 0, r.stderr


# ── 부작용 명령을 정말 안 부르는지 ─────────────────────────────────
# 위 테스트는 "파이썬이 **없어도** 성공한다" 까지만 본다 — 파일 머리에서 파이썬을 불렀다가
# 실패를 삼키는 코드(예전 `TTS_VOICE` 조회)도 통과한다. 여기서는 부작용이 있는 명령을
# 전부 가짜로 바꿔 **불렸는지**를 기록한다. (`kill` 은 bash 내장이라 PATH 로 못 바꾼다 —
# 넣어 봐야 헛통과만 는다.)
_SIDE_EFFECT_CMDS = ("curl", "ping", "ssh", "lsof", "open", "xdg-open", "nohup",
                     "mkdir", "ipconfig", "pgrep", "pkill")


def _fake_path(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "불림.txt"
    for name in (*_SIDE_EFFECT_CMDS, "python"):
        f = bindir / name
        f.write_text(f'#!/bin/sh\necho "{name} $*" >> "{marker}"\nexit 1\n')
        f.chmod(0o755)
    env = {"PATH": f"{bindir}:{os.environ['PATH']}", "REACHY_PY": str(bindir / "python")}
    return env, marker


def test_가짜_명령은_불리면_기록된다(tmp_path):
    """대조군 — 아래 테스트의 "기록 없음" 이 가짜 명령이 안 먹어서 생긴 헛통과가 아님을 본다.
    `check` 는 헬스체크(curl)와 화자 조회(파이썬)를 실제로 부른다."""
    env, marker = _fake_path(tmp_path)
    env["TTS_ASSETS"] = str(tmp_path / "자산없음")   # 진짜 crispasr 를 건드리지 않게
    _run("check", env_extra=env)
    called = marker.read_text().splitlines()
    assert any(l.startswith("curl ") for l in called), called
    assert any(l.startswith("python ") for l in called), called


def test_dry_run_은_부작용_명령을_하나도_부르지_않는다(tmp_path):
    env, marker = _fake_path(tmp_path)
    for target in ("--sim", "--robot"):
        r = _run("start", target, "--dry-run", env_extra=env)
        assert r.returncode == 0, r.stderr
        assert len(_plan(r.stdout)) == 4
    assert not marker.exists(), marker.read_text()


# ── 실제 기동 경로 — 부작용 명령을 셸 함수로 가려서 본다 ──────────────
# 실기·데몬·추론 서버 없이는 `start` 를 끝까지 못 돌린다. `reachy.sh` 를 source 하면
# 함수만 정의되고(맨 끝의 BASH_SOURCE 검사), 그 위에 가짜 함수를 덮어써 **순서와 대상**을
# 기록한다. 가짜로 덮는 것은 바깥(망·프로세스)에 닿는 자리뿐이고, 조립 로직은 진짜다.
_SOURCE_ENV = (*_PLAN_ENV, "REACHY_DIRECTOR_URL", "REACHY_ROLE", "REACHY_ROBOT_HOST",
               "REACHY_ROBOT_APP", "REACHY_PROMPT", "REACHY_AUDIO_OUT")

# 로봇 쪽 호출을 기록하는 가짜. `$ROBOT_HOST` 를 같이 적어 **어느 로봇을 향했는지** 본다.
_FAKE_ROBOT = r'''
sleep() { :; }
robot_reachable() { echo "reach $ROBOT_HOST $ROBOT_API" >> "$CALLS"; }
rget() {
  echo "get $ROBOT_HOST $1" >> "$CALLS"
  case "$1" in
    /api/daemon/status) echo '{"state":"running"}' ;;
    /api/motors/status) echo '{"mode":"enabled"}' ;;
  esac
}
rpost() { echo "post $ROBOT_HOST $1" >> "$CALLS"; }
rssh() {
  echo "ssh $ROBOT_HOST $*" >> "$CALLS"
  case "$*" in
    cat\ *) echo '{}' ;;
    *curl*) echo 200 ;;
    *)      cat > "$WROTE.$ROBOT_HOST" ;;
  esac
}
'''


def _source(script, tmp_path, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in _SOURCE_ENV}
    env.update({"CALLS": str(tmp_path / "calls.txt"), "WROTE": str(tmp_path / "wrote"),
                "REACHY_PY": sys.executable})
    env.update(env_extra or {})
    body = f'source ./reachy.sh\nLOG_DIR="{tmp_path}"\n{script}'
    return subprocess.run(["bash", "-c", body], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=30)


def _calls(tmp_path):
    p = tmp_path / "calls.txt"
    return p.read_text().splitlines() if p.exists() else []


def test_정리는_이_실행이_띄운_프로세스와_그_자식만_내린다(tmp_path):
    """이름 패턴(pkill -f)으로 쓸면 옆 터미널에서 손으로 띄운 앱까지 죽는다."""
    r = _source(r'''
sleep 30 & mine=$!
( sleep 31.7; true ) & sub=$!
sleep 30 & other=$!
START_PIDS=" $mine:데몬-mc $sub:브라우저대기"
start_stop_pids 2>/dev/null
kill -0 $mine 2>/dev/null && echo "살아있음 mine"
kill -0 $sub  2>/dev/null && echo "살아있음 sub"
sleep 0.3; pgrep -f "sleep 31.7" >/dev/null && echo "살아있음 자식"
kill -0 $other 2>/dev/null && echo "살아있음 other"
kill $other
''', tmp_path)
    assert r.returncode == 0, r.stderr
    alive = [l for l in r.stdout.splitlines() if l.startswith("살아있음")]
    assert alive == ["살아있음 other"]
    assert "데몬-mc 내림" in r.stdout and "브라우저대기 내림" in r.stdout


def test_로봇별_단계는_그_로봇만_향하고_전역_주소를_되돌린다(tmp_path):
    r = _source(_FAKE_ROBOT + r'''
ROBOT_HOST=orig.host; ROBOT_API=http://orig.host:8000
robot_bringup_one 10.9.8.22 docent 10.9.8.10; echo "rc=$?"
echo "after $ROBOT_HOST $ROBOT_API"
echo "started [$ROBOT_APPS_STARTED]"
''', tmp_path)
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    assert "after orig.host http://orig.host:8000" in r.stdout
    assert "started [ 10.9.8.22]" in r.stdout
    calls = _calls(tmp_path)
    assert {c.split()[1] for c in calls} == {"10.9.8.22"}
    assert calls[0] == "reach 10.9.8.22 http://10.9.8.22:8000"
    # 순서가 곧 교훈이다: 모터 → 기상 → 앱. 모터가 꺼진 채 wake_up 을 틀면 헛돈다.
    assert [c.split()[2] for c in calls if c.startswith("post ")] == [
        "/api/motors/set_mode/enabled", "/api/move/play/wake_up", "/api/apps/start-app/voice_chat",
    ]
    reach_checks = [c for c in calls if "curl" in c]
    assert [c.split("http://10.9.8.10:")[1].split("/")[0] for c in reach_checks] == [
        "8080", "8090", "8099"]
    cfg = json.loads((tmp_path / "wrote.10.9.8.22").read_text())
    assert cfg["REACHY_ROLE"] == "docent"
    assert cfg["REACHY_LLM_URL"] == "http://10.9.8.10:8080"


def test_robot_up_은_백엔드를_먼저_보고_전역_호스트와_역할로_한_대를_올린다(tmp_path):
    """`robot up` 동작 유지 — 백엔드 점검이 추론 3종보다 앞이다(2026-09-09 헛일 교훈)."""
    r = _source(r'''
robot_reachable()     { echo "reach $ROBOT_HOST" >> "$CALLS"; }
robot_backend_ready() { echo "backend $ROBOT_HOST" >> "$CALLS"; }
start_llm_stt()       { echo "llm_stt $BIND_HOST" >> "$CALLS"; }
start_tts()           { echo "tts" >> "$CALLS"; }
lan_ip()              { echo 10.9.8.10; }
robot_warmup()        { echo "warmup" >> "$CALLS"; }
robot_bringup_one()   { echo "bringup $*" >> "$CALLS"; }
robot_status()        { :; }
robot_logs()          { :; }
robot_up
''', tmp_path, env_extra={"REACHY_ROBOT_HOST": "10.9.8.31", "REACHY_ROLE": "mc"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert _calls(tmp_path) == [
        "reach 10.9.8.31", "backend 10.9.8.31", "llm_stt 0.0.0.0", "tts", "warmup",
        "bringup 10.9.8.31 mc 10.9.8.10",
    ]


def test_start_robot_은_안_닿는_로봇을_건너뛰고_띄운_앱만_정리한다(tmp_path):
    """사회자만 닿는다 → 도슨트는 경고하고 건너뛰고, 감독은 뜨고, 끝나면 사회자 앱만 멈춘다.
    운영자 셸에 남은 시뮬 감독 주소(loopback)는 로봇에 들어가면 안 된다."""
    r = _source(_FAKE_ROBOT + r'''
robot_reachable() {
  [ "$ROBOT_HOST" = 10.9.8.21 ] || { echo "unreachable $ROBOT_HOST" >> "$CALLS"; return 1; }
  echo "reach $ROBOT_HOST $ROBOT_API" >> "$CALLS"
}
start_ports_free() { echo "ports $*" >> "$CALLS"; }
start_llm_stt()    { echo "llm_stt $BIND_HOST" >> "$CALLS"; }
start_tts()        { :; }
up()               { return 0; }
lan_ip()           { echo 10.9.8.10; }
robot_warmup()     { echo "warmup" >> "$CALLS"; }
start_director()   { echo "director $*" >> "$CALLS"; }
start_robot 0.0.0.0 9777 9778 http://127.0.0.1:9778/ 10.9.8.21 10.9.8.22
''', tmp_path, env_extra={"REACHY_DIRECTOR_URL": "ws://127.0.0.1:8777"})
    assert r.returncode == 0, r.stdout + r.stderr
    calls = _calls(tmp_path)
    assert calls[:3] == ["ports 9777 9778", "llm_stt 0.0.0.0", "warmup"]
    assert "unreachable 10.9.8.22" in calls
    assert not any(c.startswith(("post 10.9.8.22", "get 10.9.8.22", "ssh 10.9.8.22")) for c in calls)
    director = calls.index("director 0.0.0.0 9777 http://127.0.0.1:9778/")
    assert calls.index("post 10.9.8.21 /api/apps/start-app/voice_chat") < director
    # 정리(EXIT trap)는 감독 뒤에, 앱을 띄운 사회자에게만 간다.
    assert [c for c in calls[director:] if c.startswith("post ")] == [
        "post 10.9.8.21 /api/apps/stop-current-app"]
    assert "도슨트 로봇(10.9.8.22)을 건너뛴다" in r.stdout
    cfg = json.loads((tmp_path / "wrote.10.9.8.21").read_text())
    assert cfg["REACHY_DIRECTOR_URL"] == "ws://10.9.8.10:9777"
    assert "REACHY_DIRECTOR_URL=ws://127.0.0.1:8777 는 쓰지 않는다" in r.stdout


def test_시뮬_앱은_역할마다_포트와_출력장치를_따로_받는다(tmp_path):
    """장치 이름의 공백이 단어 분리로 깨지지 않는다(`${out:+VAR=$out}` 함정). 비운 쪽은
    운영자 셸의 REACHY_AUDIO_OUT 을 물려받지 않는다 — 그러면 두 앱이 같은 장치로 간다."""
    fake_py = tmp_path / "py"
    fake_py.write_text('#!/bin/sh\necho "ROLE=$REACHY_ROLE PORT=$REACHY_DAEMON_PORT '
                       'URL=$REACHY_DIRECTOR_URL OUT=[${REACHY_AUDIO_OUT-없음}] ARGS=$*"\n')
    fake_py.chmod(0o755)
    r = _source(r'''
start_sim_app mc     8000 "USB 스피커 A" ws://127.0.0.1:9777
start_sim_app docent 8001 ""             ws://127.0.0.1:9777
wait
cat "$LOG_DIR/start-app-mc.log" "$LOG_DIR/start-app-docent.log"
''', tmp_path, env_extra={"REACHY_PY": str(fake_py), "REACHY_AUDIO_OUT": "운영자 장치"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[-2:] == [
        "ROLE=mc PORT=8000 URL=ws://127.0.0.1:9777 OUT=[USB 스피커 A] "
        "ARGS=-u apps/voice_chat/voice_chat/main.py",
        "ROLE=docent PORT=8001 URL=ws://127.0.0.1:9777 OUT=[없음] "
        "ARGS=-u apps/voice_chat/voice_chat/main.py",
    ]
