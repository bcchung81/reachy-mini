# Reachy Mini - Local Configuration

AI 에이전트용 로컬 설정. 공식 템플릿(`harness/agents.local.md.template`) 형식을 따르되
**실기 없이 MuJoCo 시뮬레이터만 사용하는 환경**에 맞춰 채웠다.

---

## Setup Status

- [x] Python virtual environment configured (`.venv`, Python 3.12.13, uv 관리)
- [x] reachy-mini SDK 설치 (PyPI `reachy-mini[mujoco]` 1.9.0, 저장소 clone 아님)
- [x] 공식 하네스 문서 로컬 고정 (`harness/`, v1.9.0 태그)
- [ ] Additional repos cloned (없음)

## Robot

```
robot_type: simulation          # Wireless / Lite 실기 없음. MuJoCo 시뮬레이터만.
daemon_url: http://localhost:8000
launcher: ./reachy.sh sim          # macOS는 mjpython 필수 — 아래 Notes 참조
media: enabled                  # 3D 뷰어 + 오디오 동시 동작 (아래 Notes 참조). 끄려면 --no-media
```

## Paths

```
project_root: /Users/bcchung81/workspace/reach-mini
venv: /Users/bcchung81/workspace/reach-mini/.venv
harness_docs: /Users/bcchung81/workspace/reach-mini/harness   # AGENTS.md + skills 13종 (v1.9.0 고정)
apps: /Users/bcchung81/workspace/reach-mini/apps
```

## Preferences

```
venv_tool: uv
shell: zsh
os: macos              # macOS 26.5.2 / Apple Silicon (arm64)
python: 3.12.13        # 3.14 불가 — 아래 Notes 참조
```

## Cloned Repos

| Repo | Path | Last Updated |
|------|------|--------------|
| (없음 — SDK는 PyPI 설치, 하네스 문서만 v1.9.0에서 내려받음) | — | 2026-07-29 |

## Notes

로컬 실측으로 확인한 제약이다. 에이전트는 코드를 쓰기 전에 이 항목들을 전제로 삼는다.

- **Python 3.14 사용 금지.** `reachy-mini[mujoco]`가 `mujoco==3.3.0`을 고정하는데 이 버전에 cp314 휠이 없다. 이 프로젝트의 인터프리터는 `.venv/bin/python`(3.12.13) 하나뿐이다. 시스템 `python3`(homebrew 3.14.6)로 SDK를 import하지 않는다.
- **데몬 기동은 반드시 `./reachy.sh sim`.** macOS에서 MuJoCo 뷰어는 Cocoa 메인스레드를 요구해 `mjpython` 런처가 필요하다. `reachy-mini-daemon --sim`으로 실행하면 `launch_passive requires that the Python script be run under mjpython on macOS` RuntimeError가 난다. SDK 저장소는 이를 자동 처리하지 않는다(이슈 #79 open).
- **오디오는 쓸 수 있다. 단 `./reachy.sh sim`로 띄웠을 때만이다.** mjpython으로 데몬을 그냥 띄우면 GStreamer 장치 모니터가 CoreAudio를 프로브하다 교착한다(`gst_device_monitor_start` → `gst_core_audio_bind_device`). mjpython이 Cocoa GUI용으로 메인스레드를 점유하는데 CoreAudio 장치 조회도 메인 런루프를 요구하기 때문이다(마이크 권한 문제가 아니다 — 일반 python으로는 장치가 즉시 잡힌다). `reachy.sh`가 `GST_PLUGIN_FEATURE_RANK=osxaudiodeviceprovider:NONE,avfdeviceprovider:NONE`으로 교착을 일으키는 *장치 프로바이더*만 배제하고 입출력 요소(`osxaudiosrc`/`osxaudiosink`)는 살려 둔다. 이 상태에서 3D 뷰어·오디오·시뮬 카메라 스트림이 한 프로세스에서 공존한다. 실측: 감정 모션 재생 시 `Audio system is not initialized` 0회.
- **오디오 하드웨어 대체 관계**: Reachy Mini Audio USB 카드가 없으므로 시스템 기본 마이크/스피커로 폴백하고, 하드웨어 에코캔슬(XMOS) 대신 GStreamer 소프트웨어 에코캔슬이 걸린다. `No Reachy Mini Audio USB device found!` ERROR 로그는 이 폴백의 정상 신호다.
- **DoA(음원 방향)는 기대하지 않는다.** 4채널 마이크 어레이가 없어 시뮬에서는 의미 있는 값이 나오지 않는다.
- **시뮬에서 동작하지 않는 것**: 컴플라이언트 모드(손으로 움직여 모션 녹화)는 no-op다. 녹화된 모션 *재생*은 정상. IMU는 Wireless 전용. 데몬측 얼굴추적은 시뮬 루프에서 호출되지 않는다.
- **JS(Live/Web) 앱 경로를 쓰지 않는다.** 공식 `AGENTS.md`는 JS를 기본 권장하지만 JS SDK는 wireless 펌웨어와 중앙 시그널링 서버를 전제하며 시뮬레이터 연동 근거가 없다. 이 환경에서는 **Python 앱**으로 만든다.
- **앱 폴더를 손으로 만들지 않는다.** `reachy-mini-app-assistant create`를 쓴다(공식 절대 규칙). 다만 이 CLI는 대화형이라 non-TTY 셸에서 멈출 수 있으니, 에이전트가 실행할 때는 사용자에게 터미널 실행을 요청하거나 인자를 모두 넘긴다.
- **안전 한계는 SDK가 자동 클램프한다** — 머리 pitch/roll ±40°, 머리·몸 yaw ±180°, 머리-몸 yaw 차 최대 65°. 시뮬이라 물리적 위험은 없지만 목표값이 조용히 잘릴 수 있으니 상태를 되읽어 확인한다.
