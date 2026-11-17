# 시뮬 사회자 마이크 기동 실패 — M 칸 진행 기록(2026-11-17)

문제: 16:39:57 `./run-app.sh` 시뮬 기동에서 사회자(mc) 앱이
`[경고] 청취 루프가 죽었다(RuntimeError: 마이크 파이프라인을 기동하지 못했다)` → 그 세션 내내 사회자가 못 들었다.
도슨트는 오류 없음. 직전 16:06:55 세션은 정상.

## 1. 로그에서 본 것

- `start-app-mc.log`: `[마이크 닫힘]` 다음에 위 경고. **`[마이크 경고] 파이프라인을 만들지 못했다` 도, AEC 폴백 경고도 없다** →
  `parse_launch` 는 됐고(REACHY_AEC 꺼짐 — 시도 한 번), `_start` 의 `get_state(5초)` 가 PLAYING 을 못 봤다.
- 앱 환경(`ps eww 94370`): `GST_PLUGIN_SCANNER`·`GST_REGISTRY`·`GST_PLUGIN_FEATURE_RANK` 가 **없다** — `start --sim` 은
  이 셋을 export 하지 않는다(`run_sim` 만 한다). 조율자 시험(이 셋을 켬)과 앱 환경이 달랐다. 아래 재현은 앱과 같은 환경(셋 없음)으로 했다.
- 도슨트는 마이크를 아예 안 연다 — `main.py` `if role == "mc":` 에서만 청취 스레드를 띄운다(과제 1-(c) 코드 확인).

## 2. macOS 통합 로그(`/usr/bin/log show`)·전원 로그(`pmset -g log`)에서 본 것 — 결정적

실패한 사회자 앱(pid 94370, 16:39:57 기동)의 CoreAudio 기록:

| 시각 | 무엇 |
|---|---|
| 16:39:44 | `Display is turned off` |
| 16:39:49 | `Entering Sleep state due to 'Clamshell Sleep' … Using Batt (Charge:62%)` — **배터리에서 덮개를 닫았다**. coreaudiod: `OldState: DarkWakeSilenceBuffers, NewState: Sleeping` |
| 16:39:52 | `DarkWake` (이 짧은 깸 동안 데몬·앱이 조금씩 떴다) |
| 16:39:59.85 | 앱이 내장 마이크(장치 79) 입력을 켜려 함(`SetStreamUsage: Input stream … ENABLED`) |
| 16:39:59 | `Entering Sleep state due to 'Maintenance Sleep'` — **같은 초에 맥이 다시 잠듦**. coreaudiod `config change 789~793`(내장 마이크·스피커 전원 내림) |
| 16:40:02.09 | coreaudiod `Calling master mute setter ON on built-in microphone input` — 덮개 닫힘의 내장 마이크 차단 |
| 16:40:02.32 | 앱: `HALB_IOThread::_Start: IO is still disabled after waiting` |
| 16:40:02.44 | `DarkWake` · `Completed config change 789` |
| 16:40:02.64 | 앱: `there already is a thread`(E) 다음 `setPlayState Started Input` |
| 16:40:04.91 | 앱: `IOWorkLoop: ending the transport` → 입력 멈춤 = 입력을 켜고 **5.07초** 뒤, `get_state(5초)` 만료 후 `set_state(NULL)` |
| 16:40:07 ~ 17:20 | 2~10초 간격으로 Maintenance Sleep ↔ DarkWake 반복(약 40분) |
| 17:20:44 | `USB-C_plug … DarkWake to FullWake … Using AC` · `Display is turned on` — 전원 연결·깨어남 |

- 대조(정상 16:06 세션, 앱 pid 79176): 16:06:58.20 입력 요청 → 16:06:58.30 `Started Input`(0.1초). 그때 맥은 깨어 있었다
  (16:05:36 `Wake … lid`, 다음 잠듦은 16:12:41 Clamshell).
- 직전 세션 앱은 **16:07:38 에 이미 끝났다**(audiomxd `Monitored process died, pid = 79176`) — 새 앱이 마이크를 연 16:39:59 보다 32분 전.
  "직전 세션을 끝내고 곧바로 다시 띄웠다" 는 아니었다.
- 지금(17:5x) 덮개 열림(`AppleClamshellState = No`)·AC 전원.

## 3. 재현 시도(과제 1) — 앱과 같은 환경(.venv 파이썬, GST_* 없음), 스크립트 `scratchpad/panes/M/exp/open_mic.py`

| 시도 | 결과 |
|---|---|
| 단독 열기 2회 | 2/2 성공, 열기 0.19~0.22초 |
| (a) 마이크를 쥔 프로세스에 SIGTERM 직후 다른 프로세스에서 열기 ×3 | 3/3 성공, 0.19~0.20초 |
| (a) 같은 것 SIGKILL ×3 | 3/3 성공, 0.19~0.20초 |
| (b) 두 프로세스 동시 열기 ×5 | 10/10 성공, 0.26~0.28초 |
| (b) 셋째가 쥔 채 두 프로세스 동시 열기 | 2/2 성공, 0.23~0.24초 |

→ "직전 앱이 마이크를 안 놓았다"·"두 앱 동시 열기" 가설은 기각. 레지스트리 재스캔도 아니다(통합 로그상 AUHAL 까지 갔다 —
파이프라인 생성·상태 전환은 됐고 CoreAudio 입력 IO 가 잠자기로 멈춰 있었다).
**맥을 재우는 재현은 하지 않았다** — 사용자 시뮬 공연이 같이 멈춘다.

## 4. 원인

- **확정(로그 대조, 실험 재현 아님)**: 시뮬 기동 도중 배터리 상태에서 덮개를 닫아 맥이 Clamshell Sleep → Maintenance Sleep/DarkWake 를
  오갔다. 사회자 앱이 마이크를 켠 순간(16:39:59.85)이 잠드는 순간과 겹쳐 CoreAudio 입력 IO 가 약 2.8초 꺼져 있었고(`IO is still disabled
  after waiting`), `MicCapture._start` 의 PLAYING 확인 5초가 넘어 `RuntimeError` → `run_listener` 가 경고하고 청취 스레드가 끝났다.
- **세션 내내 못 들은 이유(확정, 코드)**: 청취 루프는 한 번 죽으면 다시 열지 않는다(`main.run_listener` 는 알리고 끝난다). 17:20:44 맥이
  깨어난 뒤에도 사회자는 그대로 귀머거리였다.
- 덧붙임: 맥북 내장 마이크는 덮개가 닫히면 하드웨어로 끊긴다(16:40:02 coreaudiod `master mute setter ON`). 덮개가 닫힌 동안은
  파이프라인이 떴더라도 무음이었다. `caffeinate -dis`(keep_awake)는 배터리에서 덮개 닫힘 잠자기를 막지 못하고, 그나마 앱을 띄운 **뒤**에 걸린다.

## 5. 고침

- [x] F1 `reachy.sh` start --sim(로봇 재배포 없음): 기동 직후(추론 서버·예열 전) 배터리면·덮개가 닫혀 있으면 소리 내서 경고
  (`sim_power_check`). 막지는 않는다. `pmset`·`ioreg` 가 없으면(리눅스) 말없이 건너뛴다. 시험 5개 먼저 — 빨강 5 → 초록 5.
  실제 맥(AC·덮개 열림)에서 읽기 전용으로 돌려 출력 없음·rc=0 확인, 가짜 출력 형식이 실제 `pmset -g batt`·`ioreg` 출력과 같음을 대조.
- [ ] F2(앱, 로봇 재배포 필요): 청취 루프가 마이크를 못 열면 간격을 두고 다시 연다 — **결정 필요로 남긴다**(아래 조율자에게)

## 6. 다음에 "마이크가 안 열렸다" 가 나오면 볼 것(진단 순서)

1. `pmset -g log | grep -E "Sleep|Wake|Display is turned"` — 그 시각에 맥이 잠들었나(Clamshell/Maintenance Sleep·DarkWake). 앱 로그만으로는 안 보인다.
2. `ioreg -r -k AppleClamshellState -d 4 | grep AppleClamshellState` · `pmset -g batt` — 덮개·전원.
3. `/usr/bin/log show --start … --end … --style compact --predicate 'processID == <앱 pid>'` — CoreAudio 가 입력을 켰는지
   (`setPlayState Started Input`), `IO is still disabled after waiting` 가 있는지. **통합 로그는 며칠 뒤 지워진다 — 바로 뜬다.**
4. 앱 pid 는 `ps -axo pid,lstart,command | grep voice_chat/main.py`, 앱 환경은 `ps eww <pid>`(조율자 시험과 앱의 GST_* 환경이 달랐다).

## 조율자에게

### 재현 시도와 결과
- (a) 마이크를 쥔 프로세스 SIGTERM/SIGKILL 직후 다른 프로세스에서 열기 6회, (b) 두 프로세스 동시 열기 5회 + 셋째가 쥔 채 동시 열기 1회 —
  **18번 모두 0.19~0.28초에 성공**. 앱과 같은 환경(.venv, GST_* 없음)으로 했다. 표는 §3. 스크립트:
  `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/M/exp/open_mic.py`
- (c) 도슨트는 마이크를 안 연다(`main.py` 의 `if role == "mc":`) — 두 앱이 마이크를 두고 다툴 일이 없다.
- 맥을 재우는 재현은 안 했다(사용자 시뮬 공연이 같이 멈춘다). 대신 macOS 통합 로그·전원 로그로 그 순간을 초 단위로 맞췄다(§2).
  저장해 둔 원본: 같은 폴더의 `fail-94370.log`(실패한 앱의 CoreAudio 기록)·`sys-1639.log`(16:39:59~16:40:03 전체)·`cfgchg.log`.

### 원인
- **확정(로그 대조)**: 16:39:44~49 **배터리 상태에서 덮개를 닫아** 맥이 Clamshell Sleep 에 들고, 이후 40분 동안 2~10초 간격으로
  Maintenance Sleep ↔ DarkWake 를 오갔다. 사회자 앱이 마이크를 켠 16:39:59.85 가 잠드는 순간(16:39:59)과 겹쳐 CoreAudio 입력이 2.8초
  꺼져 있었고, `MicCapture._start` 의 `get_state(5초)` 가 넘어 `RuntimeError` → 청취 스레드가 끝났다. 입력을 켜고 끄기까지 5.07초.
- **확정(코드)**: 청취 루프는 한 번 죽으면 다시 열지 않는다 → 17:20:44 전원을 꽂고 맥이 깬 뒤에도 사회자는 세션 내내 귀머거리.
- **기각**: 조율자 가설("직전 세션 앱이 마이크를 안 놓았다") — 직전 앱은 16:07:38 에 이미 끝나 있었다(32분 전, audiomxd 기록).
  "곧바로 다시 띄웠다" 도 아니었다. 동시 열기·레지스트리 재스캔도 아니다(통합 로그상 AUHAL 입력 켜기까지 갔다).
- 덧붙임(확정): 맥북 내장 마이크는 덮개가 닫히면 하드웨어로 끊긴다(16:40:02.09 coreaudiod `master mute setter ON`). 덮개가 닫힌 채면
  마이크가 열려도 무음이고 오류가 없다. `keep_awake`(`caffeinate -dis`)는 배터리의 덮개 닫힘 잠자기를 못 막고, 앱을 띄운 **뒤**에 걸린다.
- 덧붙임(관찰, 고칠 것 아님): `start --sim` 은 앱에 `GST_PLUGIN_SCANNER`·`GST_REGISTRY`·`GST_PLUGIN_FEATURE_RANK` 를 주지 않는다
  (`run_sim` 만 준다). 앱은 그냥 python 이라 없어도 돈다(오늘 18회 확인). 조율자 17:2x 시험은 이 셋을 켜서 앱과 환경이 달랐다.

### 바꾼 파일
- `reachy.sh` — `sim_power_check()` 새 함수(시뮬 기동 절, `start_sim` 바로 위) + `start_sim` 에서 포트 점검·도슨트 출력 경고 다음,
  `start_traps`/추론 서버 **앞**에 한 번 부른다. 배터리면 "덮개를 닫으면 맥이 잠들어 … 사회자가 마이크를 못 연다", 덮개가 닫혀 있으면
  "내장 마이크가 꺼져 사회자가 못 듣는다(외부 마이크면 무시)". 경고만, rc 는 언제나 0. `--robot` 경로·공용 함수는 안 건드렸다.
- `tests/test_reachy_start.py` — 끝에 시험 5개(`_fake_power` 가짜 `pmset`·`ioreg`).
- `docs/superpowers/plans/2026-11-17-sim-errors-M.md` — 이 기록.
- 앱 파일(`audio_in.py`·`voice_loop.py`·`main.py`)은 **안 고쳤다**.

### 시험 결과
- 새 시험 5개: 고치기 전 5 failed → 고친 뒤 5 passed.
- `tests/test_reachy_start.py` 전체 **65 passed**(12.9초), `tests/test_run_app.py` **16 passed**(run-app.sh 가 `start --sim` 을 부른다).
- `bash -n reachy.sh` 통과, 시험은 macOS 기본 bash 3.2.57 로 돌았다.

### 로봇 재배포 필요 여부
- **없다.** 바뀐 것은 PC 쪽 `reachy.sh`(시뮬 기동) 뿐이다.

### docs/lessons.md 항목 초안
```markdown
### 시뮬 기동 중 덮개를 닫으면(배터리) 맥이 잠들어 사회자 마이크 열기가 실패한다 — 그리고 청취 루프는 다시 열지 않는다(2026-11-17, M 칸)
- 증상: 16:39 `./run-app.sh` 시뮬에서 사회자 앱이 `청취 루프가 죽었다(RuntimeError: 마이크 파이프라인을 기동하지 못했다)` → 세션 내내
  못 들었다. 도슨트는 멀쩡했다(마이크를 안 연다).
- 원인(맥 통합 로그·`pmset -g log` 대조 — 실험 재현은 아니다): 기동 55초 만에 배터리에서 덮개를 닫아 'Clamshell Sleep', 이후
  2~10초 간격으로 Maintenance Sleep ↔ DarkWake. 마이크를 켠 16:39:59.85 가 잠드는 순간과 겹쳐 CoreAudio 입력이 2.8초 꺼져 있었고
  (`IO is still disabled after waiting`), `MicCapture._start` 의 PLAYING 확인 5초가 넘었다. 청취 루프는 한 번 죽으면 다시 열지 않아
  맥이 깬 뒤에도 귀머거리였다. "직전 앱이 마이크를 안 놓았다"·"두 앱 동시 열기" 는 실험 18회가 모두 0.2초대에 열려 기각했다
  (직전 앱은 32분 전에 끝나 있었다 — 로그를 보기 전의 "곧바로 다시 띄웠다" 는 사실이 아니었다).
- 규칙: 시뮬 리허설은 **전원 연결·덮개 열림**. `caffeinate` 는 배터리의 덮개 닫힘 잠자기를 못 막고, 맥북 내장 마이크는 덮개가 닫히면
  하드웨어로 끊긴다(오류 없이 무음). "마이크가 안 열렸다" 는 앱 로그만으로는 원인이 안 보인다 — 먼저
  `pmset -g log | grep -E "Sleep|Wake|Display is turned"` 로 그 시각에 맥이 잠들었는지 보고, 통합 로그(`log show --predicate 'processID == <pid>'`)는
  며칠 뒤 지워지니 바로 뜬다. 재현 시험은 **앱과 같은 환경**으로 한다(`ps eww <pid>` — `start --sim` 앱에는 GST_* 가 없다).
- 테스트: `tests/test_reachy_start.py::test_시뮬_기동은_배터리면_덮개를_닫지_말라고_경고한다`,
  `::test_시뮬_기동은_덮개가_닫혀_있으면_내장_마이크가_꺼진다고_경고한다`, `::test_전원_점검은_시뮬_기동에서_추론_서버보다_먼저_한다`
```

### 결정 필요
1. **F2 — 청취 루프의 자가 회복(앱 파일, 로봇 두 대 재배포 필요).** 이번 증상이 "세션 내내" 간 것은 이것 때문이다. F1 은 원인(덮개 닫기)을
   알릴 뿐 이미 죽은 루프를 살리지 못한다. 내 권고: **리허설 전에는 넣지 않는다** — 계기가 시뮬 전용 운영 행동이고(실기는 로봇 마이크·덮개 없음),
   실기에서 같은 "기동 순간 일시 실패" 가 난 증거가 없다(추측으로 고치지 않는다). 넣는다면 모양은 둘:
   - (가) `audio_in.MicCapture.__init__` 에서 `_start` 실패 시 1초 쉬고 2번 더(경고 + 실패 때 `get_state` 반환값·버스 ERROR 메시지·걸린 시간을
     찍는 진단 포함). 한 파일. 이번 건은 둘째 시도(16:40:06 무렵)가 DarkWake 창(16:40:02~07)에 들어 열렸을 가능성이 높지만 보장은 없다.
   - (나) `main.run_listener` 가 죽은 루프를 간격을 늘려 가며(5→30초 상한) `stop_event` 까지 다시 띄우고, 실패는 처음과 N번마다·회복은 한 번
     감독에 알린다. 이때 `make_mic_sink` 의 `has_listener` 는 "스레드가 산다" 가 아니라 "마이크가 실제로 열렸다" 여야 한다(재시도 중에도
     스레드는 살아 있다) — `voice_loop` 가 마이크를 연 뒤 켜는 표지가 필요해 `voice_loop.py` 도 고친다. 덮개 닫힘 40분 같은 긴 잠자기도 덮는다.
   시험 설계(어느 쪽이든 먼저 쓴다): 가짜 `_start` 가 처음 N번 None → 그다음 파이프라인을 주면 열리고 경고가 N번 찍힌다 / 끝내 실패하면
   지금처럼 RuntimeError / (나)는 should_stop 이 서면 재시도 대기에서 곧바로 끝난다·회복 뒤 `mic(open)` 에 "청취 루프가 없다" 경고가 안 난다.
2. **같은 점검을 `start --robot` 에도?** 실기 공연에서도 운영 맥이 배터리로 덮개가 닫히면 감독·게이트웨이·TTS 프록시가 통째로 잠든다.
   내 범위(시뮬 기동 부분) 밖이라 안 넣었다. 넣는다면 `sim_power_check` 의 배터리 줄만 쓰면 된다(덮개·내장 마이크 줄은 시뮬 전용).
3. 리허설 점검표(`docs/rehearsal-checklist.md`)·`run-app.sh` 안내에 "시뮬은 전원 연결·덮개 열림" 한 줄을 넣을지 — 내 범위 밖.

### 남은 일
- **사용자의 지금 시뮬 세션(16:39:57 기동, 앱 pid 94370)은 사회자가 여전히 못 듣는다** — 청취 루프가 16:40:04 에 죽었고 다시 열지 않는다.
  들으려면 사용자가 감독 창에서 q 로 끄고 전원·덮개를 확인한 뒤 `./run-app.sh` 로 다시 띄워야 한다. 나는 건드리지 않았다.
- lessons.md 등재(초안 위)·커밋은 조율자 몫.
- 조정실이 청취 루프 사망을 한 번만 알리는지(운영자는 40분 뒤 돌아와 몰랐다) — 감독·조정실 쪽(stage/)이라 내 범위 밖, 확인만 권한다.

## 조율자에게 (2차)

조율자 결정(2026-11-17): F2 는 지금 넣지 않는다(인계 후보 — 조율자) · `start --robot` 에 배터리 줄 승인 · 점검표·run-app 안내는 조율자.

### 한 것
- `reachy.sh`
  - `mac_on_battery()` 새 도우미 — `pmset -g batt` 첫 줄이 `Battery Power` 면 0. `pmset` 이 없으면(리눅스 PC) 1("배터리 아님") — 말없이 건너뛴다.
  - `sim_power_check()` 의 배터리 줄이 이 도우미를 쓰도록 바꿨다(문구·동작 그대로, 시뮬 시험 5개 그대로 통과).
  - `robot_power_check()` 새 함수 — **배터리 줄만**: "운영 맥이 배터리로 돌고 있다 — 덮개가 닫히면 맥이 잠들어
    감독·게이트웨이·TTS 프록시가 통째로 잠든다(화면 잠자기 방지로도 못 막는다)" + 흐린 줄 "전원을 연결하고 덮개를 연 채로 둔다".
    경고만, rc 언제나 0. 덮개·내장 마이크는 묻지도 않는다(`ioreg` 를 부르지 않는다).
  - `start_robot` 에서 포트 점검·`$PY` 확인 다음, `start_traps`·추론 서버·예열·로봇 올리기 **앞**에서 한 번 부른다. 로봇에 닿는 것은 없다.
- `tests/test_reachy_start.py` 끝에 시험 4개(가짜 `pmset`·`ioreg` — 1차의 `_fake_power` 재사용):
  - `test_실기_기동은_배터리면_운영_맥이_잠들어_감독과_서버가_멈춘다고_경고한다` — 가짜가 덮개 닫힘이라고 해도 "내장 마이크" 없음·`ioreg` 안 불림
  - `test_실기_기동은_전원이_연결돼_있으면_아무_말도_안_한다`(대조군 — `pmset -g batt` 가 실제로 불렸다)
  - `test_실기_전원_점검_명령이_없으면_건너뛰고_기동을_막지_않는다`
  - `test_전원_점검은_실기_기동에서_추론_서버보다_먼저_한다` — `_FAKE_ROBOT` + `robot_bringup_one` 가짜, 순서 power → infer → director

### 시험 결과
- 새 시험 4개: 고치기 전 4 failed(순서 시험은 `['infer','director']` — 부르지 않아서 빨강) → 고친 뒤 통과.
- `tests/test_reachy_start.py` 전체 **69 passed**(13.2초), `tests/test_run_app.py` **16 passed**. `bash -n reachy.sh` 통과, bash 3.2.57.
- 실제 맥(AC·덮개 열림)에서 `robot_power_check`·`sim_power_check` 를 읽기 전용으로 돌려 출력 없음·rc=0.

### 로봇 재배포 필요 여부
- **없다.** PC 쪽 `reachy.sh` 만 바뀌었다. 앱 파일(`audio_in.py`·`voice_loop.py`·`main.py`)은 1·2차 모두 안 고쳤다.

### docs/lessons.md 초안 보탬(1차 초안의 규칙 줄 끝에 붙인다)
```markdown
  실기도 같다 — 감독·게이트웨이·TTS 프록시가 운영 맥에서 돈다. 배터리로 덮개가 닫히면 로봇은 깨어 있어도 말할 곳·물을 곳이 없다
  (같은 날 G 칸의 LLM 연결 끊김도 16:12:41~16:27:19 잠자기에서 왔다). 그래서 `start --sim`·`start --robot` 둘 다 기동 직후 배터리면 경고한다
  (덮개·내장 마이크 경고는 시뮬만).
  테스트 보탬: `tests/test_reachy_start.py::test_실기_기동은_배터리면_운영_맥이_잠들어_감독과_서버가_멈춘다고_경고한다`,
  `::test_전원_점검은_실기_기동에서_추론_서버보다_먼저_한다`
```

### 결정 필요
- 없다.

### 남은 일
- 사용자의 지금 시뮬 세션(16:39:57 기동) 사회자는 여전히 못 듣는다 — 다시 띄워야 한다(1차와 같음, 건드리지 않았다).
- F2 인계 문서·점검표·run-app 안내·lessons 등재·커밋은 조율자 몫.
