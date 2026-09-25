# Reachy Mini 시뮬레이터 바이브코딩 프로젝트

실기 없이 **MuJoCo 시뮬레이터**만으로 Reachy Mini 앱을 개발하는 작업공간이다.
macOS 26.5.2 / Apple Silicon / Python 3.12.13(uv 관리) 기준으로 검증됐다.

## 시작하기 전에 읽을 것

1. `agents.local.md` — 이 환경의 제약(무엇이 되고 무엇이 안 되는지). **먼저 읽는다.**
2. `docs/lessons.md` — **이 저장소에서 실제로 밟은 지뢰.** 같은 자리에 두 번 빠지지 않으려면 읽는다.
3. `harness/AGENTS.md` — Pollen 공식 에이전트 가이드. v1.9.0 태그로 고정해 받아뒀다.
4. `harness/skills/*.md` — 작업 유형별 공식 스킬 13종. 해당하는 것만 골라 읽는다.

| 하려는 일 | 읽을 스킬 |
|---|---|
| 새 앱 만들기 | `harness/skills/create-app.md` |
| 앱 테스트 | `harness/skills/testing-apps.md` |
| 부드러운 동작 설계 | `harness/skills/motion-philosophy.md` |
| 실시간 반응 루프 | `harness/skills/control-loops.md` |
| LLM 연동 앱 | `harness/skills/ai-integration.md` |
| 안테나·머리를 입력장치로 | `harness/skills/interaction-patterns.md` |
| 수학적 모션 정의 | `harness/skills/symbolic-motion.md` |
| REST API 직접 호출 | `harness/skills/rest-api.md` |
| 막혔을 때 | `harness/skills/debugging.md` |

`harness/`는 참조 전용이다 — 수정하지 않는다. 갱신이 필요하면 새 태그에서 다시 받는다.

## 명령

```bash
./reachy.sh start --sim          # 시연 전부(추론 3종·시뮬 2대·무대감독+대시보드)
./reachy.sh start --robot        # 시연 전부 — 실기 2대(REACHY_MC_HOST / REACHY_DOCENT_HOST, 기본 192.168.0.4 / .5)
./reachy.sh sim                  # 시뮬레이터 기동 (빈 씬, 미디어 비활성)
./reachy.sh sim --scene minimal  # 테이블 + 사과/크루아상/오리
./reachy.sh bake                 # 고정 대사를 TTS 캐시에 굽기(대본을 고친 뒤 — 바뀐 문장만). --check 는 현황만
.venv/bin/python your.py      # SDK 스크립트 실행 (데몬이 떠 있어야 함)
curl -s localhost:8000/api/state/full   # 로봇 상태 확인
open http://localhost:8000/docs         # REST API 문서 (OpenAPI)
```

데몬은 별도 터미널에서 계속 띄워둔다. 한 번에 앱 하나만 실행된다.

## 이 환경의 하드 제약

`agents.local.md`에 근거와 함께 정리돼 있다. 요약하면:

- **인터프리터는 `.venv/bin/python`(3.12) 하나뿐이다.** 시스템 `python3`는 3.14라 SDK가 설치되지 않는다.
- **데몬은 `./reachy.sh sim`로만 띄운다.** `reachy-mini-daemon --sim`은 macOS에서 RuntimeError로 죽는다.
  2대 시연은 `./reachy.sh start --sim` 이 `--mockup-sim`(MuJoCo 없음)으로 두 대를 띄운다 — 그래서 한 맥에 공존한다.
- **오디오는 된다 — 단 `./reachy.sh sim`로 띄웠을 때만.** 스크립트가 GStreamer 장치 프로바이더 교착을 우회한다. 데몬을 직접 `mjpython ...`으로 띄우면 미디어 초기화에서 멈춘다. DoA(음원 방향)는 마이크 어레이가 없어 기대하지 않는다.
- **손으로 움직여 모션 녹화 불가**(컴플라이언트 모드 no-op). 녹화 모션 *재생*은 된다.
- **JS(Live/Web) 앱 경로를 쓰지 않는다.** 시뮬 연동 근거가 없다. Python 앱으로 만든다.
- **앱 폴더는 `reachy-mini-app-assistant create`로 만든다.** 손으로 디렉토리를 만들지 않는다.

## 배포 가능성은 타협 대상이 아니다

**시뮬레이터에서 검증한 기능은 코드 수정 없이 실기(Reachy Mini Wireless / CM4)에 배포될 수 있어야 한다.**
시뮬은 개발 수단이지 목표가 아니다. 여기서만 도는 물건을 만들면 그건 완성이 아니라 부채다.

아래는 예외 없는 규칙이다.

- **진입점은 `main.py`(`ReachyMiniApp`) 하나다.** 실기가 실행하는 것과 시연에서 돌리는 것이
  같아야 한다. `demo.py`는 프레임워크가 표현 못 하는 폴백(`--text` / `--no-robot`) 전용이고,
  **대화 로직은 `session.py` 하나뿐이다** — 진입점에 복사하지 않는다.
- **플랫폼 전용 요소는 폴백 사다리 안에만 둔다.** `say`·`afplay`·`osxaudiosrc`·`install_name_tool`
  같은 macOS 전용을 기본 경로에 박지 않는다. 기본은 `autoaudiosrc`/`autoaudiosink`처럼 중립인 것.
  macOS 이름을 기본 경로에 박았다가 실기에서 `FileNotFoundError`가 예외에 삼켜져
  **소리도 로그도 없이 벙어리가 된 전례가 있다.**
- **주소는 전부 환경변수다.** `REACHY_LLM_URL` / `REACHY_STT_URL` / `TTS_QWEN_URL`.
  로봇에는 앱만 올라가고 추론 3종은 PC에 남는다 — 코드 수정 없이 주소만 바꿔 옮길 수 있어야 한다.
- **시뮬 전용 우회는 스위치 뒤에 두고 기본을 꺼짐으로 한다.** 예: `REACHY_AEC`는 시뮬에
  하드웨어 에코캔슬이 없어서 필요한 것이고, 실기는 XMOS AEC가 그 자리를 대신하므로
  켜지 않는다. "시뮬에서만 필요한 것"은 켜야 동작하게 만들지, 기본값으로 만들지 않는다.
- **실기에 없는 것에 의존하지 않는다.** MuJoCo 씬의 물체 좌표, 시뮬 카메라의 내부파라미터,
  `mjpython`, 3D 뷰어 창 — 앱 로직이 이런 것을 전제하면 실기에서 그대로 깨진다.
- **SDK가 대체할 자리를 알고 쓴다.** `audio_in.py`는 실기 배포 시 SDK 미디어 백엔드로
  통째로 교체되는 파일이다. 그 경계를 넘는 가정을 다른 모듈에 퍼뜨리지 않는다.
- **실패는 소리 내서 실패한다.** 폴백으로 물러날 때는 반드시 경고를 남긴다. 조용히 성능이
  떨어진 채 도는 것이 가장 나쁘다 — 시연장에서 원인을 찾을 수 없다.

새 기능을 넣기 전에 스스로 답한다: **이걸 실기에 올리면 무엇이 깨지나?** 답이 "아무것도"가
아니면, 깨지는 부분을 스위치 뒤로 보내거나 폴백을 만들고 `docs/real-robot-deployment.md`에 적는다.

## 작업 규약

- **모든 작업은 `main` 브랜치에서 한다**(2026-09-24 사용자 지시). 기능 브랜치·git 워크트리를
  만들지 않고, 서브에이전트에도 워크트리 격리(`isolation: "worktree"`)를 쓰지 않는다. 커밋은
  `main` 에 바로 한다. 스킬(예: using-git-worktrees·finishing-a-development-branch)이 브랜치를
  권해도 이 규칙이 우선한다. 푸시는 사용자가 요청할 때만 한다.
- 코드를 쓰기 전에 `plan.md`로 접근을 정리하고 사용자 승인을 받는다(공식 AGENTS.md 규칙).
- 앱은 `apps/` 아래에 만든다.
- 동작을 바꾼 뒤에는 시뮬레이터에서 실제로 돌려보고, `GET /api/state/full`로 결과를 되읽어 확인한다.
  안전 한계(머리 pitch/roll ±40°, 머리-몸 yaw 차 65°)에 걸리면 목표값이 조용히 잘린다.

### 문제 보고를 받으면 로그부터 읽는다

사용자가 로그를 붙여넣기를 기다리지 않는다. **`./reachy.sh logs` 로 마지막 세션을 직접 읽는다.**

- `.demo-logs/app.log` — 앱(대화) 출력. 세션 구분자(`════ 세션 시작 …`)와 그때의 환경변수
  (`REACHY_AEC`/`REACHY_BARGE_IN`/임계값)가 함께 적힌다. `logs` 는 **마지막 세션만** 잘라 보여준다.
- `.demo-logs/start-director.log`(무대감독, 세션 구분자로 누적)·`start-app-{mc,docent}.log` — `start` 로
  띄운 시연 한 벌. `logs` 가 이것도 보여 주고, 더 최근에 돈 쪽(demo 또는 start)을 실시간으로 따라간다.
- `.demo-logs/tts.log`·`tts-proxy.log`·`sim.log` — 서버 쪽. `logs` 가 오류·경고 줄만 추려 준다.
  `tts-proxy.log` 의 "고정 대사인데 캐시 키가 다르다" 는 로봇 목소리 설정이 굽기와 달라졌다는 뜻이다.
- "이상하다"는 보고를 받으면 순서는 하나다: **로그 확인 → 재현 → 원인 → 고침 → 테스트로 박제.**
  로그를 안 보고 추측으로 고치지 않는다. 이번 세션의 자기 목소리 루프도 로그의 한 줄
  (`나(STT)> 제가 어떻게 만들어졌는지…`)이 없었으면 못 찾았다.

### 실수는 그 자리에서 박제한다

`harness/`는 공식 문서라 고칠 수 없다. **여기서 겪은 실수는 `docs/lessons.md`에 남긴다.**

- **버그를 하나 잡을 때마다** 항목을 추가한다 — 증상 → 원인 → 규칙 순으로. 원인 없는 규칙은 무시된다.
- **가능하면 테스트로 고정한다.** 문서는 잊히지만 테스트는 실패한다. 테스트를 붙였으면
  대장 항목에 `tests/…::이름`을 적는다. 재발 방지가 목적이지 기록이 목적이 아니다.
- 코드 옆 주석에도 **왜 그렇게 짰는지**를 남긴다. 특히 "이렇게 안 하면 무엇이 깨지는지".
  이 저장소의 주석 대부분이 그런 근거다 — 지우지 말고 갱신한다.
- 고쳐서 사라진 제약은 삭제하지 말고 취소선으로 남긴다. 그게 지금 구조의 근거다.
