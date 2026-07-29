# Reachy Mini 시뮬레이터 바이브코딩 프로젝트

실기 없이 **MuJoCo 시뮬레이터**만으로 Reachy Mini 앱을 개발하는 작업공간이다.
macOS 26.5.2 / Apple Silicon / Python 3.12.13(uv 관리) 기준으로 검증됐다.

## 시작하기 전에 읽을 것

1. `agents.local.md` — 이 환경의 제약(무엇이 되고 무엇이 안 되는지). **먼저 읽는다.**
2. `harness/AGENTS.md` — Pollen 공식 에이전트 가이드. v1.9.0 태그로 고정해 받아뒀다.
3. `harness/skills/*.md` — 작업 유형별 공식 스킬 13종. 해당하는 것만 골라 읽는다.

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
./run-sim.sh                  # 시뮬레이터 기동 (빈 씬, 미디어 비활성)
./run-sim.sh --scene minimal  # 테이블 + 사과/크루아상/오리
.venv/bin/python your.py      # SDK 스크립트 실행 (데몬이 떠 있어야 함)
curl -s localhost:8000/api/state/full   # 로봇 상태 확인
open http://localhost:8000/docs         # REST API 문서 (OpenAPI)
```

데몬은 별도 터미널에서 계속 띄워둔다. 한 번에 앱 하나만 실행된다.

## 이 환경의 하드 제약

`agents.local.md`에 근거와 함께 정리돼 있다. 요약하면:

- **인터프리터는 `.venv/bin/python`(3.12) 하나뿐이다.** 시스템 `python3`는 3.14라 SDK가 설치되지 않는다.
- **데몬은 `./run-sim.sh`로만 띄운다.** `reachy-mini-daemon --sim`은 macOS에서 RuntimeError로 죽는다.
- **오디오는 된다 — 단 `./run-sim.sh`로 띄웠을 때만.** 스크립트가 GStreamer 장치 프로바이더 교착을 우회한다. 데몬을 직접 `mjpython ...`으로 띄우면 미디어 초기화에서 멈춘다. DoA(음원 방향)는 마이크 어레이가 없어 기대하지 않는다.
- **손으로 움직여 모션 녹화 불가**(컴플라이언트 모드 no-op). 녹화 모션 *재생*은 된다.
- **JS(Live/Web) 앱 경로를 쓰지 않는다.** 시뮬 연동 근거가 없다. Python 앱으로 만든다.
- **앱 폴더는 `reachy-mini-app-assistant create`로 만든다.** 손으로 디렉토리를 만들지 않는다.

## 작업 규약

- 코드를 쓰기 전에 `plan.md`로 접근을 정리하고 사용자 승인을 받는다(공식 AGENTS.md 규칙).
- 앱은 `apps/` 아래에 만든다.
- 동작을 바꾼 뒤에는 시뮬레이터에서 실제로 돌려보고, `GET /api/state/full`로 결과를 되읽어 확인한다.
  안전 한계(머리 pitch/roll ±40°, 머리-몸 yaw 차 65°)에 걸리면 목표값이 조용히 잘린다.
