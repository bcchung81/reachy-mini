# voice_chat — 계획

공식 `AGENTS.md`("Always Create plan.md Before Coding")가 요구하는 문서다.

**작성 시점이 규약과 어긋난다.** 원래는 코딩 **전에** 세워야 하는데, 이 문서는
2026-08-12 에 **사후**로 만들었다. 그 전까지의 작업(커밋 `bdc33da`·`5abad73`·
`927d52e`)은 대화형 승인만 받고 진행했다. 그래서 성격이 "착수 전 계획서"가 아니라
**"확정된 결정 + 남은 일"** 문서다. 다음 작업부터는 착수 전에 §4 를 먼저 채운다.

수치는 전부 이 저장소에서 실측하거나 소스로 대조한 것이다. 확인하지 못한 것은
"미확인"이라고 적었다 — 추정을 사실처럼 적지 않는다.

---

## 1. 무엇을 만드는가

말을 걸면 알아듣고, 감정 모션으로 즉시 반응하며, 캐릭터 음색으로 답하는 데스크톱
로봇 앱. 추론 3종(STT·LLM·TTS)은 전부 로컬에서 돈다.

- 개발·시연: MuJoCo 시뮬레이터 (실기 없이)
- 배포 대상: **Reachy Mini Wireless** (2026-08-11 구매 확정, 미도착)
- 진입점: `voice_chat/main.py` (`ReachyMiniApp`) — 실기가 실행하는 것과 시연에서
  돌리는 것이 같다. `demo.py` 는 `--text`/`--no-robot` 폴백 전용이고 대화 로직은
  `session.py` 하나뿐이다.

---

## 2. 확정 사항 — 재론하지 않는다

각 항목의 근거는 소스·실측이다. 뒤집으려면 그 근거부터 반박해야 한다.

### 2.1 배포 대상은 Wireless / 컴퓨트는 CM4

- 온보드는 **CM4104016 — RAM 4 GB / eMMC 16 GB**. Pi 5 가 아니다(최초 발표
  자료에만 Pi 5 가 있었고 출하품은 CM4). 문서 7곳의 "Pi5" 표기를 정정했다.
- RAM 4 GB 라 온보드 sLLM 이 성립하지 않는다 → 추론 3종이 PC 에 남는 것은
  선택이 아니라 전제다.
- 오디오는 XMOS XVF3800(하드웨어 AEC·리니어-4 마이크). 따라서 `REACHY_AEC`
  (시뮬용 소프트웨어 AEC)는 실기에서 켜지 않는다.

### 2.2 오디오 장치는 앱이 직접 연다 — `request_media_backend = "no_media"`

- 근거(SDK 소스 `reachy_mini.py:343-351`): `"no_media"` 일 때만 `release_media()`
  가 호출된다. 그 docstring 원문 — *"the camera and microphone are available for
  direct access via OpenCV / sounddevice / etc."*
- 기본값(`None` → `"default"`)이면 SDK 미디어 백엔드가 장치를 쥔 채 우리
  `MicCapture` 가 같은 장치를 또 연다.
- 앱 종료 시 `ReachyMini.__exit__` 이 `acquire_media()` 로 되돌린다(idempotent).
- **부작용을 함께 처리했다** — §2.4.

### 2.3 로봇에 쓰는 스레드는 하나 (`driver.RobotDriver`)

공식 `skills/control-loops.md`: *"One control loop, one place calling
`set_target()` … Never call `set_target()` from multiple threads."*

- primary(녹화 모션 `move.evaluate(t)`) + secondary(sway·호흡)를 100 Hz 로 합성.
  `play_move()` 를 쓰지 않는 이유는 그것이 자기 스레드에서 로봇을 몰기 때문이다.
- 진입·이탈·취소 전부 0.3 초 블렌드(SDK `linear_pose_interpolation` 위임 + clamp).
- 시계는 `time.monotonic()`.
- 실측(실제 녹화 모션 4종, 2,246 프레임): **쓰는 스레드 1개**, 비정상 회전행렬
  **0개**, 틱 간 최대 변화 **2.56°**.

### 2.4 모션 발성은 우리 재생 경로로 (`sound.py` → `Speaker`)

- 실측: 감정 라이브러리 **85개 중 84개가 `.ogg` 보유**, `CATEGORY_MOVES` 가 쓰는
  **17개는 전부** 보유. `no_media` 로 두면 이 전부가 무음이 된다
  (`media_manager.play_sound` 가 `audio is None` 이면 경고만 남기고 반환).
- 옮긴 결과 셋: ① 마이크 게이팅이 모션 길이가 아니라 **사운드 길이**를 따라간다
  (실측: **9개 모션은 사운드가 모션보다 길다**, 최대 `welcoming1` +1.43 초)
  ② 발성이 에코 프로브·출력 레벨을 타므로 끼어들기가 그 구간에도 판정한다
  ③ §2.5 리샘플러를 함께 탄다.
- **길이 정책**(사용자 결정, 2026-08-11): 리액션 발성은 **앞 1.2 초 + 0.25 초
  페이드아웃**, 공연(춤)은 전체. 근거 — 리액션 발성이 2~12 초(실측
  `curious1` 9.93s / `sad1` 6.89s)라 통째로 붙이면 답변이 그만큼 늦는다.
  발성의 원래 역할은 LLM 지연 구간을 메우는 것이다.
- 디코딩(GStreamer, 새 의존성 없음): 실측 **7~23 ms**, 이후 캐시.

### 2.5 출력 레이트는 장치에 맞춘다

- 근거 둘: 탑재 펌웨어 `ua_io16_lin` 의 `io16` = USB 입출력 16 kHz /
  SDK `media/audio_base.py:59` `SAMPLE_RATE = 16000`. TTS 출력은 24 kHz.
- `_open_output()` 이 **원본 레이트를 먼저 시도**하고(맥은 그대로 열려 회귀 없음),
  안 되면 `16000 → 48000 → 44100` 으로 내려가며 리샘플한다. 물러날 때 경고를 남긴다.
- 리샘플러는 청크 경계에서 FIR 상태·데시메이션 위상을 잇는다(numpy 전용).
  실측: 필터 감쇠 **−69 dB @10 kHz**, 청크 분할 vs 일괄 오차 **≤1 LSB**,
  비용 **실시간 대비 0.05 %**(청크당 0.042 ms).

### 2.6 주소는 3단 사다리 (`config.py`)

`환경변수 → 설정파일 → 기본값`. 키 이름은 환경변수와 동일하다. 파일 위치는
platformdirs 가 정하므로 플랫폼마다 다르다 — 실기(Linux)는
`~/.config/reachy-mini-voice-chat/config.json`, 개발 맥은
`~/Library/Application Support/reachy-mini-voice-chat/config.json`(실측).

- 근거(SDK 소스 `apps/manager.py:159`): 앱은 `os.environ.copy()` 로 **데몬
  프로세스의** 환경을 상속한다. Wireless 에서 데몬은 systemd 유닛이므로 운영자
  셸의 export 가 닿지 않는다.
- 기동 첫 줄이 세 주소와 출처를 찍고, **Linux 에서 loopback 이면 경고**한다.
  시뮬(맥)에서는 loopback 이 정답이라 침묵한다.

### 2.7 사용자 발화 중에는 몸을 접는다 (`REACHY_MOTOR_QUIET`, 기본 켬)

- XVF3800 의 AEC 는 스피커 반향만 지운다 — 서보 소음은 별개다.
- `vad.active` 를 매 프레임 넘겨 sway·호흡을 포락선으로 접고(접기 0.15s /
  펴기 0.5s), 대기 모션은 끊고, Idler 는 새로 시작하지 않는다.
  **응답 모션은 두다** — 로봇 발화 턴의 정당한 동작이다.
- 기본 켬인 이유: 실기에서만 필요한 것을 꺼짐 기본으로 두면 켜는 걸 잊는다
  (`REACHY_AEC` 와 반대 방향).

### 2.8 실행 진입점은 `./reachy.sh` 하나

`sim` / `demo` / `check` / `logs` / `stop` / `warmup` / `measure aec|latency`.
파이썬 도구는 `scripts/` 에 두되 인터프리터(`.venv` 강제)·작업 디렉토리를
진입점이 보장한다.

---

## 3. 현재 상태 (2026-08-12)

- 테스트 **193건 통과**
- 커밋 3개: `bdc33da`(실기 정합·단일 루프·리뷰 결함) → `5abad73`(진입점 통합·
  파일 정리) → `927d52e`(§10·§12)
- `docs/real-robot-deployment.md` §1~§14 전부 해소. 남은 것은 "미검증" 절뿐.
- 실기 미도착 — 아래 §4.1 은 하드웨어가 있어야 답이 나온다.

---

## 4. 남은 일

### 4.1 실기 도착 후에만 확인 가능 — **답변란**

착수 전에 여기부터 채운다. (`docs/real-robot-deployment.md` "미검증" 절과 같은 목록)

| # | 확인할 것 | 답 |
|---|---|---|
| 1 | 로봇 스피커가 PortAudio(`sounddevice`)로 잡히는가? 아니면 SDK 미디어를 거쳐야 하는가 | |
| 2 | `no_media` 로 데몬이 실제로 장치를 놓고, 그 뒤 `autoaudiosrc` 가 XVF3800 을 잡는가 | |
| 3 | 출력이 16 kHz 로 열리는가(=리샘플 경고가 뜨는가), 아니면 24 kHz 가 그대로 열리는가 | |
| 4 | CM4(RAM 4 GB)에서 앱 자체의 CPU·메모리 여유 | |
| 5 | XMOS 하드웨어 AEC 가 있는 상태에서 끼어들기 임계를 어디로 둘 것인가 | |
| 6 | 모터 소음이 실제로 STT 를 얼마나 오염시키는가(§2.7 정숙의 효과 측정) | |

확인 수단: 기동 로그(주소·출처 고지, 리샘플 경고, 마이크 경고) → `./reachy.sh logs`.

### 4.2 코드 — 우선순위 순

| # | 항목 | 근거 | 규모 |
|---|---|---|---|
| 1 | `time.time()` → `time.monotonic()` | CM4 에는 배터리 백업 RTC 가 없어 부팅 후 NTP 가 붙으면 벽시계가 점프한다. 현재 앱 모듈에 **23곳**(`voice_loop` 9 · `tts` 8 · `session` 4 · `audio_in` 2). `driver` 는 이미 monotonic 5곳 | 기계적 치환 |
| 2 | 자기소개 대본이 실기에서 거짓말을 한다 | `selfintro.py:49-50` "인터넷에 연결되어 있지 않아요" / "모두 이 노트북 안에서 돕니다", `:94` `HISTORY_SUMMARY` "전부 이 노트북 안에서 돕니다" — Wireless 는 앱이 로봇에서 돌고 추론은 PC, 둘 사이는 WiFi. **고치면 F0·시드를 다시 재야 한다**(`selfintro-script.md` §3) | 대본 수정 + 재측정 |
| 3 | 하드웨어 스펙 질문에 LLM 이 지어낸다 | `_TRIGGERS` 에 "스펙" 이 있는데 대본에 하드웨어가 한 줄도 없다. `prompt.md` 에 사실 몇 줄을 박거나 대본 분기 추가 | 작음 |
| 4 | `agents.local.md` 가 낡았다 | `robot_type: simulation` / `media: enabled` 둘 다 사실이 아니다. 공식 `AGENTS.md:74-78` 이 이 파일에 로봇 기종을 적으라고 한다 | 5분 |
| 5 | 프리버퍼 플러시가 절 시작마다 `_io` 잠금을 길게 쥔다 | 끼어들기 abort 가 청크 1개(약 85 ms) 대신 프리버퍼(0.25 초분) 쓰기를 기다린다. 리뷰가 CONFIRMED 로 냈고 지연 추정치는 ~137 ms — **이 수치는 리뷰 계산이고 우리가 실측하지 않았다** | 구조 변경 |
| 6 | env-bool 파싱 **6회** 중복 / `tests/conftest.py` 부재(`sys.path.insert` 가 **17파일**) / 평면 import 충돌 위험 | 리뷰 CONFIRMED(컷). 리팩토링 성격 | 중간 |

### 4.3 기능 확장 — 착수 전 별도 계획 필요

- **RAG(안내 데스크·규정 Q&A)** — LLM 호출 직전 백엔드에서 top-3 주입이면
  로봇 코드는 손대지 않는다. 아직 없다.
- **툴콜로 제스처 트리거** — 현재 `motion.classify` 의 키워드 규칙(`_RULES`)이
  전부 한국어라 영어 입력은 규칙에 하나도 안 걸린다. 실측: `"what is your name?"`
  → `curious`(물음표 폴백에 걸린 것뿐), `"tell me a joke"`·`"hello there"` →
  `ack`. 즉 **영어에서는 인사·기쁨·놀람·거절·공연 분류가 전부 소실되고
  물음표 유무로만 갈린다.** `prompt.md` 는 영어 응답을 허용하므로 실제 불일치다.
- **`custom_app_url` 설정 페이지** — §2.6 을 파일 편집 대신 UI 로. 지금은 불필요.

---

## 5. 이 문서를 쓰는 규칙

- 결정이 확정되면 §2 로 옮기고 **근거를 한 줄 함께 적는다.** 근거 없는 결정은
  다음 사람이 되돌린다.
- §4.1 의 답은 실기에서 확인한 **날짜와 함께** 적는다.
- 새 작업은 착수 전에 §4 에 항목을 만들고, 확인이 필요하면 답변란을 비워 둔다.
- 버그를 잡으면 이 문서가 아니라 `docs/lessons.md` 에 증상→원인→규칙으로 적는다.
  여기는 "무엇을 할 것인가", 거기는 "무엇에 데였는가"다.
