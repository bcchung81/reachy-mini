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


# 계획 값은 아니지만 **어느 명령이 불리는지**를 바꾸는 것들. 셸에 `TTS_QWEN_VOICE` 가 있으면
# 화자 조회(파이썬)를 건너뛰고, `TTS_BACKEND=say` 면 `check` 가 Qwen 헬스체크 대신 `say` 로 간다 —
# 아래 대조군(`test_가짜_명령은_불리면_기록된다`)이 "파이썬이 불렸다" 를 못 보고 깨진다(리뷰 M5).
_RUN_ENV = (*_PLAN_ENV, "TTS_QWEN_VOICE", "TTS_BACKEND")


def _run(*args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in _RUN_ENV}
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


def test_start_robot_은_사회자와_도슨트가_같은_주소면_계획도_없이_2로_끝난다():
    """같은 로봇에 사회자 config 를 쓰고 곧바로 도슨트 config 로 덮어쓴다 — 사회자가 조용히
    사라진다(리뷰 M7). dry-run 도 같은 판정을 거친다(계획이 "된다" 고 말하면 안 된다)."""
    r = _run("start", "--robot", "--dry-run",
             env_extra={"REACHY_MC_HOST": "10.9.8.21", "REACHY_DOCENT_HOST": "10.9.8.21"})
    assert r.returncode == 2
    assert _plan(r.stdout) == []
    assert "사회자와 도슨트가 같은 로봇(10.9.8.21)이다" in r.stdout


def test_start_robot_의_같은_주소_거절은_아무것도_건드리기_전이다(tmp_path):
    env, marker = _fake_path(tmp_path)
    # HOME 도 가린다 — 거절이 빠진 코드에서는 기동이 진행돼 `$HOME/workspace/llamactl.sh`(진짜
    # 추론 서버)까지 간다. 없는 경로면 거기서 멈춘다.
    env.update({"REACHY_MC_HOST": "10.9.8.21", "REACHY_DOCENT_HOST": "10.9.8.21",
                "HOME": str(tmp_path)})
    r = _run("start", "--robot", env_extra=env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "사회자와 도슨트가 같은 로봇(10.9.8.21)이다" in r.stdout
    assert not marker.exists(), marker.read_text()


def test_start_sim_은_로봇_주소가_같아도_상관하지_않는다():
    """시뮬은 로봇 주소를 안 쓴다 — 운영자 셸에 남은 실기 값 때문에 시뮬이 막히면 안 된다."""
    r = _run("start", "--sim", "--dry-run",
             env_extra={"REACHY_MC_HOST": "10.9.8.21", "REACHY_DOCENT_HOST": "10.9.8.21"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(_plan(r.stdout)) == 4


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
               "REACHY_ROBOT_APP", "REACHY_PROMPT", "REACHY_AUDIO_OUT", "REACHY_DIRECTOR_HOST",
               "REACHY_DAEMON_PORT", "REACHY_MC_AUDIO_OUT", "REACHY_DOCENT_AUDIO_OUT",
               "TTS_QWEN_VOICE", "TTS_BACKEND", "STT_PYTHON", "PYTHONUNBUFFERED")

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
rpost() {
  echo "post $ROBOT_HOST $1" >> "$CALLS"
  # 데몬의 start-app 은 성공하면 AppStatus 를 돌려준다(reachy_mini/apps/manager.py).
  case "$1" in
    /api/apps/start-app/*) echo '{"info":{"name":"voice_chat"},"state":"starting","error":null}' ;;
  esac
}
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
    # 로그 경로는 source 할 때 LOG_DIR 에서 한 번 만들어진다 — 파생 경로까지 다시 잡지 않으면
    # 테스트가 저장소의 진짜 .demo-logs 에 쓴다.
    body = (f'source ./reachy.sh\nLOG_DIR="{tmp_path}"\nAPP_LOG="$LOG_DIR/app.log"\n'
            f'START_DIRECTOR_LOG="$LOG_DIR/start-director.log"\n{script}')
    return subprocess.run(["bash", "-c", body], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=30)


def _calls(tmp_path):
    p = tmp_path / "calls.txt"
    return p.read_text().splitlines() if p.exists() else []


def test_정리는_이_실행이_띄운_프로세스와_그_자식만_내린다(tmp_path):
    """이름 패턴(pkill -f)으로 쓸면 옆 터미널에서 손으로 띄운 앱까지 죽는다.

    자식은 **pid 파일로** 본다 — 전역 `pgrep -f` 는 병렬로 도는 다른 워크트리의 같은
    테스트 자식까지 잡아 헛실패하고, 자식이 fork 되기 전에 부모를 죽이는 경쟁도 있다."""
    r = _source(r'''
sleep 30 & mine=$!
( sleep 30 & echo $! > "$LOG_DIR/kid.pid"; wait ) & sub=$!
sleep 30 & other=$!
n=0; while [ ! -s "$LOG_DIR/kid.pid" ] && [ $n -lt 50 ]; do sleep 0.1; n=$((n+1)); done
kid=$(cat "$LOG_DIR/kid.pid")
START_PIDS=" $mine:데몬-mc $sub:브라우저대기"
start_stop_pids 2>/dev/null
kill -0 $mine 2>/dev/null && echo "살아있음 mine"
kill -0 $sub  2>/dev/null && echo "살아있음 sub"
sleep 0.3; kill -0 $kid 2>/dev/null && echo "살아있음 자식"
kill -0 $other 2>/dev/null && echo "살아있음 other"
kill $other $kid 2>/dev/null
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


def test_start_robot_은_안_닿는_로봇을_건너뛰고_정리는_두_배역_자리_모두에_보낸다(tmp_path):
    """사회자만 닿는다 → 도슨트는 경고하고 건너뛰며 합류 명령을 찍고, 감독은 뜬다.
    운영자 셸에 남은 시뮬 감독 주소(loopback)는 로봇에 들어가면 안 된다.

    끝날 때는 **두 배역 자리 모두**에 앱 정지를 보낸다(리뷰 F2) — 건너뛴 로봇도 문서의 복구
    절차(다른 터미널에서 `robot up`)로 나중에 합류하는데, 그 앱은 이 실행이 띄운 목록에 없어
    `q` 뒤에도 마이크를 쥐고 남았다. 여전히 안 닿으면 조용히가 아니라 한 줄 경고."""
    r = _source(_FAKE_ROBOT + r'''
robot_reachable() {
  [ "$ROBOT_HOST" = 10.9.8.21 ] || { echo "unreachable $ROBOT_HOST" >> "$CALLS"; return 1; }
  echo "reach $ROBOT_HOST $ROBOT_API" >> "$CALLS"
}
rpost() {
  echo "post $ROBOT_HOST $1" >> "$CALLS"
  [ "$ROBOT_HOST" = 10.9.8.21 ] || return 7   # curl: 연결 실패 — 도슨트는 끝까지 꺼져 있다
  case "$1" in
    /api/apps/start-app/*) echo '{"info":{"name":"voice_chat"},"state":"starting","error":null}' ;;
  esac
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
    director = calls.index(
        "director 0.0.0.0 9777 http://127.0.0.1:9778/ target=robot mc=10.9.8.21 docent=10.9.8.22")
    # 기동 중에는 안 닿는 도슨트를 더 건드리지 않는다.
    assert not any(c.startswith(("post 10.9.8.22", "get 10.9.8.22", "ssh 10.9.8.22"))
                   for c in calls[:director])
    assert calls.index("post 10.9.8.21 /api/apps/start-app/voice_chat") < director
    # 정리(EXIT trap)는 감독 뒤에, 두 배역 자리 모두에 간다(건너뛴 도슨트 포함).
    assert [c for c in calls[director:] if c.startswith("post ")] == [
        "post 10.9.8.21 /api/apps/stop-current-app",
        "post 10.9.8.22 /api/apps/stop-current-app",
    ]
    assert "도슨트 로봇(10.9.8.22)을 건너뛴다" in r.stdout
    assert "REACHY_ROLE=docent REACHY_ROBOT_HOST=10.9.8.22 ./reachy.sh robot up" in r.stdout
    assert "로봇 앱 정지 (10.9.8.21)" in r.stdout
    assert "로봇 앱 정지 실패 (10.9.8.22)" in r.stdout
    cfg = json.loads((tmp_path / "wrote.10.9.8.21").read_text())
    assert cfg["REACHY_DIRECTOR_URL"] == "ws://10.9.8.10:9777"
    assert "REACHY_DIRECTOR_URL=ws://127.0.0.1:8777 는 쓰지 않는다" in r.stdout


def test_start_robot_은_지난_시뮬_앱_로그를_실기_안내로_덮고_감독_로그에_대상을_적는다(tmp_path):
    """`start --sim` 이 남긴 start-{app,daemon}-*.log 를 `logs` 가 이번 세션처럼 붙여 보였다(리뷰 M3) —
    실기 세션에는 이 맥에 앱 출력이 없다. 로봇 쪽 로그를 보는 명령 한 줄로 덮고, 감독 로그 머리줄에
    어느 대상으로 떴는지(로봇이면 두 주소) 적는다."""
    for name in ("start-app-mc.log", "start-app-docent.log",
                 "start-daemon-mc.log", "start-daemon-docent.log"):
        (tmp_path / name).write_text(f"지난 시뮬 {name} Traceback 줄\n")
    r = _source(_FAKE_ROBOT + r'''
start_ports_free()     { :; }
start_llm_stt()        { :; }
start_tts()            { :; }
up()                   { return 0; }
lan_ip()               { echo 10.9.8.10; }
robot_warmup()         { :; }
start_open_dashboard() { :; }
start_robot 0.0.0.0 9777 9778 http://127.0.0.1:9778/ 10.9.8.21 10.9.8.22
show_logs --no-follow
''', tmp_path, env_extra={"REACHY_PY": _recording_py(tmp_path)})
    assert r.returncode == 0, r.stdout + r.stderr
    for role, host in (("mc", "10.9.8.21"), ("docent", "10.9.8.22")):
        want = f"실기 — 앱 로그는 REACHY_ROBOT_HOST={host} ./reachy.sh robot logs\n"
        assert (tmp_path / f"start-app-{role}.log").read_text() == want, role
        assert (tmp_path / f"start-daemon-{role}.log").read_text() == want, role
    log = (tmp_path / "start-director.log").read_text()
    assert "start: target=robot mc=10.9.8.21 docent=10.9.8.22 | 감독 0.0.0.0:9777" in log
    assert "지난 시뮬" not in r.stdout
    assert "실기 — 앱 로그는 REACHY_ROBOT_HOST=10.9.8.22 ./reachy.sh robot logs" in r.stdout


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
    # 로그만 남는다 — 예전 start-app-*.pid 는 쓰기만 하고 아무도 안 읽었다(리뷰 M6).
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("start-")) == [
        "start-app-docent.log", "start-app-mc.log"]


# ── 시뮬 조립 — 감독 바인드·앱마다 역할/포트·포트 선점검 ──────────────
# 가짜 파이썬 하나가 데몬·앱·감독 셋 다를 대신하며 **받은 환경과 인자**를 적는다.
_RECORDING_PY = (
    '#!/bin/sh\n'
    'echo "py HOST=${REACHY_DIRECTOR_HOST-} PORT=${REACHY_DIRECTOR_PORT-} '
    'ROLE=${REACHY_ROLE-} DPORT=${REACHY_DAEMON_PORT-} URL=${REACHY_DIRECTOR_URL-} '
    'UNBUF=${PYTHONUNBUFFERED-} ARGS=$*" >> "$CALLS"\n'
    'echo "감독 출력 줄 $1 $2"\n'
    'exit "${FAKE_RC:-0}"\n'
)


def _recording_py(tmp_path):
    p = tmp_path / "rec-py"
    p.write_text(_RECORDING_PY)
    p.chmod(0o755)
    return str(p)


def test_start_sim_은_감독을_루프백에_두고_앱마다_역할과_포트를_짝짓는다(tmp_path):
    """인증 없는 감독을 망에 열지 않는다(127.0.0.1). 도슨트 앱이 사회자 포트로 붙으면 둘이
    한 데몬을 두고 싸운다. 포트 선점검이 빠지면 남의 데몬·감독에 조용히 붙는다."""
    r = _source(r'''
start_ports_free()     { echo "ports $*" >> "$CALLS"; }
start_llm_stt()        { echo "llm_stt $BIND_HOST" >> "$CALLS"; }
start_tts()            { :; }
up()                   { return 0; }
robot_warmup()         { echo "warmup" >> "$CALLS"; }
start_open_dashboard() { echo "dashboard $*" >> "$CALLS"; }
start_sim 9777 9778 http://127.0.0.1:9778/; rc=$?
wait
ls "$LOG_DIR" | grep '^start-' > "$LOG_DIR/listing.txt"   # 정리(EXIT trap) 전에 본다
exit $rc
''', tmp_path, env_extra={"REACHY_PY": _recording_py(tmp_path)})
    assert r.returncode == 0, r.stdout + r.stderr
    calls = _calls(tmp_path)
    assert "start: target=sim | 감독 127.0.0.1:9777" in (tmp_path / "start-director.log").read_text()
    # 로그만 남는다 — 예전 start-*.pid 는 쓰기만 하고 아무도 안 읽었다(리뷰 M6).
    assert sorted((tmp_path / "listing.txt").read_text().splitlines()) == [
        "start-app-docent.log", "start-app-mc.log", "start-daemon-docent.log",
        "start-daemon-mc.log", "start-director.log"]
    assert calls[:3] == ["ports 8000 8001 9777 9778", "llm_stt 127.0.0.1", "warmup"]
    py = [c for c in calls if c.startswith("py ")]
    # 뒤로 띄운 가짜들이 적는 순서는 경쟁이다 — 짝(포트↔역할)만 본다.
    daemons = sorted(c.split("ARGS=")[1] for c in py if "reachy_mini.daemon" in c)
    assert daemons == [
        "-m reachy_mini.daemon.app.main --mockup-sim --headless --no-media "
        "--fastapi-port 8000 --robot-name mc",
        "-m reachy_mini.daemon.app.main --mockup-sim --headless --no-media "
        "--fastapi-port 8001 --robot-name docent",
    ]
    apps = sorted(c for c in py if "voice_chat/main.py" in c)
    assert [c.split(" UNBUF=")[0] for c in apps] == [
        "py HOST= PORT= ROLE=docent DPORT=8001 URL=ws://127.0.0.1:9777",
        "py HOST= PORT= ROLE=mc DPORT=8000 URL=ws://127.0.0.1:9777",
    ]
    director = [c for c in py if c.endswith("ARGS=-m stage")]
    assert [c.split(" ROLE=")[0] for c in director] == ["py HOST=127.0.0.1 PORT=9777"]
    assert "dashboard http://127.0.0.1:9778/" in calls
    assert "도슨트 출력 장치가 지정되지 않았다" in r.stdout


def test_포트를_쥔_것이_있으면_무엇인지_보여_주고_1을_돌려준다(tmp_path):
    r = _source(r'''
lsof() {
  case "$*" in
    *TCP:8777*) printf 'COMMAND   PID USER\npython3.1 4242 me    TCP 127.0.0.1:8777 (LISTEN)\n' ;;
  esac
}
start_ports_free 8000 8777; echo "rc=$?"
start_ports_free 8000 8001; echo "rc=$?"
''', tmp_path)
    out = r.stdout
    first, second = out.split("rc=")[0], out.split("rc=")[1]
    assert "rc=1" in out and "rc=0" in out
    assert out.index("rc=1") < out.index("rc=0")
    assert ":8777 를 이미 쥔 것이 있다" in first
    assert "python3.1 4242" in first
    assert ":8000 비어 있음" in first
    # `./reachy.sh stop` 이 감독·대시보드도 쓸어낸다(stop_director_dashboard) — 다만 옆 시연을
    # 살려 두고 싶으면 그 감독 터미널에서 q 로 끝내는 길도 안내한다.
    assert "그 감독 터미널에서 q" in first and "./reachy.sh stop" in first
    assert "이미 쥔" not in second


# ── 추론 서버가 LAN 에서 보이는지 (loopback 전용 재사용 방지) ─────────
# macOS·리눅스는 0.0.0.0 으로의 connect 를 loopback 으로 보낸다. 그 동작을 가짜 `up` 에
# 그대로 옮긴다: localhost·127.0.0.1·0.0.0.0 은 응답, LAN 주소(10.9.8.10)는 무응답 —
# `start --sim`/`demo` 가 loopback 으로 띄워 남겨 둔 서버의 모양이다.
_LOOPBACK_ONLY = r'''
up() { case "$1" in http://10.9.8.10:*) return 1 ;; *) return 0 ;; esac; }
lan_ip() { echo 10.9.8.10; }
'''


def test_추론_서버_가드는_0_0_0_0_을_LAN_주소로_두드린다(tmp_path):
    r = _source(_LOOPBACK_ONLY + r'''
BIND_HOST=0.0.0.0
start_llm_stt; echo "llm_rc=$?"
start_tts; echo "tts_rc=$?"
''', tmp_path, env_extra={"TTS_QWEN_VOICE": "serena"})
    assert "llm_rc=1" in r.stdout, r.stdout
    assert "tts_rc=1" in r.stdout, r.stdout
    assert r.stdout.count("loopback 전용") == 2


def test_start_infer_는_TTS_바인드_거절에서_멈춘다(tmp_path):
    """start_tts 가 1 을 주는 것은 loopback 전용 TTS 하나뿐이다 — 버리면 로봇이 말을 못 한다."""
    r = _source(r'''
start_llm_stt() { return 0; }
start_tts()     { return 1; }
start_infer; echo "rc=$? up=$START_INFER_UP"
''', tmp_path)
    assert "rc=1 up=0" in r.stdout, r.stdout + r.stderr


def test_추론_서버_거절에는_llamactl_로그_안내를_붙이지_않는다(tmp_path):
    """거절(loopback 전용으로 떠 있다)은 이유를 이미 찍었다 — 그 뒤에 "로그: /tmp/llamactl…" 이
    붙으면 기동이 실패한 줄 알고 엉뚱한 로그를 뒤진다(리뷰 M9). 대조: 기동 실패에는 붙는다."""
    r = _source(_LOOPBACK_ONLY + r'''
BIND_HOST=0.0.0.0
start_infer; echo "rc=$?"
''', tmp_path)
    assert "rc=1" in r.stdout, r.stdout + r.stderr
    assert "loopback 전용" in r.stdout
    assert "추론 서버를 쓸 수 없다" in r.stdout
    assert "/tmp/llamactl" not in r.stdout


def test_추론_서버_기동_실패에는_llamactl_로그를_안내한다(tmp_path):
    fake_ctl = tmp_path / "llamactl"
    fake_ctl.write_text("#!/bin/sh\nexit 1\n")
    fake_ctl.chmod(0o755)
    r = _source(r'''
up() { return 1; }
LLAMACTL="$FAKE_CTL"
start_infer; echo "rc=$?"
''', tmp_path, env_extra={"FAKE_CTL": str(fake_ctl)})
    assert "rc=1" in r.stdout, r.stdout + r.stderr
    assert "LLM/STT 기동 실패" in r.stdout
    assert "/tmp/llamactl-8080.log (LLM) · /tmp/llamactl-stt-8090.log (STT)" in r.stdout


def test_start_robot_은_loopback_전용_추론_서버면_로봇을_건드리기_전에_멈춘다(tmp_path):
    r = _source(_FAKE_ROBOT + _LOOPBACK_ONLY + r'''
start_ports_free() { :; }
start_llm_stt()    { echo "llm_stt $BIND_HOST" >> "$CALLS"; }
start_tts()        { :; }
robot_warmup()     { echo "warmup" >> "$CALLS"; }
start_director()   { echo "director $*" >> "$CALLS"; }
start_robot 0.0.0.0 9777 9778 http://127.0.0.1:9778/ 10.9.8.21 10.9.8.22
''', tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "loopback 전용(start --sim/demo 가 띄운 것) — ./reachy.sh stop 후 다시" in r.stdout
    assert _calls(tmp_path) == ["llm_stt 0.0.0.0"]


# ── 이미 앱이 도는 로봇 (M8) ──────────────────────────────────────
def test_로봇에_앱이_이미_돌면_멈추고_새_config_로_다시_띄운다(tmp_path):
    """데몬은 "An app is already running" 으로 거절하고 옛 앱(옛 config)이 계속 돈다 —
    응답을 버리면 성공처럼 보인다.

    멈춘 뒤에는 **다시 깨운다**(리뷰 F1). 옛 앱을 멈추면 로봇이 몇 초 뒤 절전에 드는데, 기상
    단계는 이 재기동보다 앞이라 새 앱이 막 잠든 로봇 위에서 뜬다 — 말은 하는데 몸이 안 움직인다."""
    r = _source(_FAKE_ROBOT + r'''
rpost() {
  echo "post $ROBOT_HOST $1" >> "$CALLS"
  case "$1" in
    /api/apps/start-app/*)
      if [ -f "$LOG_DIR/stopped" ]; then
        echo '{"info":{"name":"voice_chat"},"state":"starting","error":null}'
      else
        echo '{"detail":"An app is already running"}'
      fi ;;
    /api/apps/stop-current-app) touch "$LOG_DIR/stopped" ;;
  esac
}
robot_bringup_one 10.9.8.21 mc 10.9.8.10; echo "rc=$?"
echo "started [$ROBOT_APPS_STARTED]"
''', tmp_path)
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    assert "started [ 10.9.8.21]" in r.stdout
    posts = [c.split()[2] for c in _calls(tmp_path) if c.startswith("post ")]
    assert posts == [
        "/api/motors/set_mode/enabled", "/api/move/play/wake_up",       # 기상 단계
        "/api/apps/start-app/voice_chat", "/api/apps/stop-current-app",  # 거절 → 옛 앱 정지
        "/api/motors/set_mode/enabled", "/api/move/play/wake_up",       # 다시 깨운다
        "/api/apps/start-app/voice_chat",
    ]
    assert "이미 돌고 있다" in r.stdout


def test_앱이_뜬_뒤_모터가_꺼져_있으면_앱까지_다시_띄우는_robot_up_을_권한다(tmp_path):
    """예전 안내는 `robot fix` 였다 — 그것은 앱을 **멈추고** 깨우기만 해서, 따라 하면 로봇이 앱 없이
    남는다(리뷰 F1). `robot up` 은 다시 깨우고(이미 도는 앱이면 멈춘 뒤 한 번 더) 앱까지 띄운다."""
    r = _source(_FAKE_ROBOT + r'''
rget() {
  echo "get $ROBOT_HOST $1" >> "$CALLS"
  case "$1" in
    /api/daemon/status) echo '{"state":"running"}' ;;
    /api/motors/status)
      # 앱이 뜨기 전(기상 확인)은 켜져 있고, 뜬 뒤(재확인)는 절전으로 빠졌다
      if grep -q start-app "$CALLS"; then echo '{"mode":"disabled"}'; else echo '{"mode":"enabled"}'; fi ;;
  esac
}
robot_bringup_one 10.9.8.21 mc 10.9.8.10; echo "rc=$?"
''', tmp_path)
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    assert "앱은 떴는데 모터가 꺼져 있다" in r.stdout
    assert "REACHY_ROLE=mc REACHY_ROBOT_HOST=10.9.8.21 ./reachy.sh robot up" in r.stdout


def test_앱을_못_띄우면_소리_내서_실패하고_정리_목록에서_뺀다(tmp_path):
    r = _source(_FAKE_ROBOT + r'''
rpost() {
  echo "post $ROBOT_HOST $1" >> "$CALLS"
  case "$1" in
    /api/apps/start-app/*) echo '{"detail":"The robot app slot is already in use"}' ;;
  esac
}
robot_bringup_one 10.9.8.21 mc 10.9.8.10; echo "rc=$?"
echo "started [$ROBOT_APPS_STARTED]"
''', tmp_path)
    assert "rc=1" in r.stdout, r.stdout + r.stderr
    assert "started [ ]" in r.stdout or "started []" in r.stdout
    assert "The robot app slot is already in use" in r.stdout


# ── stop 의 앱 쓸기 패턴 (M3) ─────────────────────────────────────
def test_stop_의_앱_쓸기는_파이썬_프로세스만_잡는다(tmp_path):
    """`pkill -f` 는 argv 어디든 경로가 있으면 잡는다 — 그 파일을 연 편집기까지 kill -9."""
    r = _source(r'''
printf '%s\n' \
  ".venv/bin/python -u apps/voice_chat/voice_chat/main.py" \
  "/Users/x/reachy-mini/.venv/bin/python3.12 apps/voice_chat/voice_chat/main.py" \
  "vim apps/voice_chat/voice_chat/main.py" \
  "less /tmp/python-notes/apps/voice_chat/voice_chat/main.py" \
  | grep -E "$APP_PROC_PAT"
''', tmp_path)
    assert r.stdout.splitlines() == [
        ".venv/bin/python -u apps/voice_chat/voice_chat/main.py",
        "/Users/x/reachy-mini/.venv/bin/python3.12 apps/voice_chat/voice_chat/main.py",
    ]


# ── stop 이 감독·대시보드도 쓸어낸다 ────────────────────────────────
# 사용자 요청(2026-09-22): `stop` 을 직접 치면 감독(`python -m stage`)·대시보드도 끝나야 한다.
# `robot down` 은 이 함수를 안 부른다 — 한 대만 내리고 옆 시연은 살려 둬야 하는 경로라서다.
def test_감독_스윕_패턴은_m_stage로_끝나는_것만_잡는다():
    """`-u` 유무 상관없이 실제 감독 실행은 잡되, "stage" 를 이름에 담은 무관한 프로세스는
    안 잡아야 한다 — `[-]m stage$` 가 pgrep -f 에 그대로 들어간다."""
    r = subprocess.run(
        ["bash", "-c", r'''
printf '%s\n' \
  ".venv/bin/python -m stage" \
  ".venv/bin/python -u -m stage" \
  "/Users/x/reachy-mini/.venv/bin/python3.12 -m stage" \
  "python -m stage_experiment" \
  "vim stage/__main__.py" \
  | grep -E "[-]m stage$"
'''],
        capture_output=True, text=True, timeout=10,
    )
    assert r.stdout.splitlines() == [
        ".venv/bin/python -m stage",
        ".venv/bin/python -u -m stage",
        "/Users/x/reachy-mini/.venv/bin/python3.12 -m stage",
    ]


def test_stop_director_dashboard는_감독을_쓸고_8777_8778을_쥔_것도_죽인다(tmp_path):
    r = _source(r'''
SWEPT=""
sweep() { SWEPT="$SWEPT $1"; }
lsof() {
  case "$*" in
    *TCP:8777*) echo 4242 ;;
    *TCP:8778*) echo 4343 ;;
  esac
}
KILLED=""
kill() { KILLED="$KILLED $*"; }
stop_director_dashboard
echo "SWEPT=$SWEPT"
echo "KILLED=$KILLED"
''', tmp_path)
    assert "SWEPT= [-]m stage$" in r.stdout, r.stdout
    assert "KILLED= 4242 4343" in r.stdout, r.stdout


def test_최상위_stop_명령은_stop_all과_stop_director_dashboard를_둘_다_부른다():
    """디스패처 배선 확인 — 문자열 하나가 계약이다(`case "$cmd" in … stop) …`)."""
    text = (ROOT / "reachy.sh").read_text()
    assert "stop)  stop_all; stop_director_dashboard ;;" in text


# ── 절대경로 인터프리터 (M6) ──────────────────────────────────────
def test_STT_파이썬은_절대경로_인터프리터를_그대로_쓴다(tmp_path):
    fake_ctl = tmp_path / "llamactl"
    fake_ctl.write_text('#!/bin/sh\necho "STT_PYTHON=$STT_PYTHON" >> "$CALLS"\n')
    fake_ctl.chmod(0o755)
    r = _source(r'''
up() { return 1; }
wait_for() { return 0; }
LLAMACTL="$FAKE_CTL"
start_llm_stt; echo "rc=$?"
''', tmp_path, env_extra={"REACHY_PY": "/opt/abs/bin/python", "FAKE_CTL": str(fake_ctl)})
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    assert _calls(tmp_path) == ["STT_PYTHON=/opt/abs/bin/python"]


# ── start 의 로그 (M7) ─────────────────────────────────────────────
def test_감독_출력은_터미널과_로그_파일_둘_다로_가고_종료코드를_지킨다(tmp_path):
    r = _source(r'''
start_open_dashboard() { :; }
START_DIRECTOR_LOG="$LOG_DIR/start-director.log"
start_director 127.0.0.1 9777 http://127.0.0.1:9778/; echo "rc=$?"
''', tmp_path, env_extra={"REACHY_PY": _recording_py(tmp_path), "FAKE_RC": "3"})
    assert "감독 출력 줄 -m stage" in r.stdout, r.stdout + r.stderr
    assert "rc=3" in r.stdout
    log = (tmp_path / "start-director.log").read_text()
    assert "════════ 세션 시작" in log
    assert "감독 출력 줄 -m stage" in log
    # 파이프 뒤에서는 flush 없는 print 가 블록 버퍼링에 갇혀 콘솔에 안 보인다.
    assert [c for c in _calls(tmp_path) if "ARGS=-m stage" in c][0].split("UNBUF=")[1] == (
        "1 ARGS=-m stage")


def test_logs_는_start_세션의_감독과_앱_로그를_보여_준다(tmp_path):
    (tmp_path / "start-director.log").write_text(
        "════════ 세션 시작 2026-09-21 10:00:00 ════════\n지난 세션 줄\n"
        "════════ 세션 시작 2026-09-22 10:00:00 ════════\n[mc] 붙었다\n")
    (tmp_path / "start-app-mc.log").write_text("역할: mc (환경변수)\n")
    r = _source(r'''
APP_LOG="$LOG_DIR/app.log"
START_DIRECTOR_LOG="$LOG_DIR/start-director.log"
show_logs --no-follow
''', tmp_path)
    assert r.returncode == 0, r.stderr
    assert "[mc] 붙었다" in r.stdout
    assert "지난 세션 줄" not in r.stdout
    assert "역할: mc (환경변수)" in r.stdout


# ── 문서의 로봇 주소 (I1) ─────────────────────────────────────────
def test_문서의_실기_주소_예시는_사회자_4_도슨트_5다():
    """예시가 기본값과 다르면(.41/.42) 문서를 따라 친 한 줄이 맞는 기본값을 **덮어쓴다**."""
    for name in ("docs/two-robot-setup.md", "docs/two-robot-offline-test.md", "docs/install.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "192.168.0.41" not in text and "192.168.0.42" not in text, name
        assert "192.168.0.4" in text and "192.168.0.5" in text, name
    offline = (ROOT / "docs/two-robot-offline-test.md").read_text(encoding="utf-8")
    assert "\n./reachy.sh start --robot\n" in offline
