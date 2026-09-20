# 2대 구성 설계 — 사회자 + 도슨트

- 작성일: 2026-09-11
- 대상: Reachy Mini **Wireless 2대** + 노트북 1대 (전파체험관 도슨트 시연)
- 상태: **설계 승인됨(구조·프로토콜). 구현 착수 전.**
- 근거: SDK `reachy-mini` 1.9.0 소스 대조 + 이 맥에서의 실측(§8)

---

## 1. 목적

전파체험관 큐시트(`docs/exhibit-guide.md`, 19섹션, 2026-09-09 정본)를
**사회자 로봇 1대 + 도슨트 로봇 1대**가 주고받으며 진행한다.
관람객은 사회자에게 말을 걸고, 사회자가 도슨트에게 넘긴다.

기존 1대 구성(`apps/voice_chat`)의 **오디오·추론 경로를 바꾸지 않는 것**이 설계 목표다.
새로 생기는 것은 노트북의 무대감독 서버와 제어 메시지 채널 하나뿐이다.

## 2. 확정된 결정 (사용자 승인)

| 결정 | 선택 | 대안을 버린 이유 |
|---|---|---|
| 대화 앱 실행 위치 | **로봇 온보드 앱 2개 + 노트북 무대감독** | 노트북 단일 오케스트레이터(WEBRTC)는 오디오를 WiFi로 왕복시키고 CLAUDE.md의 `main.py` 단일 진입점 규칙과 충돌 |
| 대사 소스 | **하이브리드** — 뼈대는 대본, 살은 LLM | 완전 대본은 재방문 관람객에게 들통남. 전면 LLM은 사실오류·지연 누적 |
| 관람객 참여 | **사회자가 단일 창구** | 양쪽 청취는 "누구에게 한 말인가" 판정과 동시응답 중재가 추가로 필요 |
| 진행 신호 | **관람객 발화**(`다음`·`계속`류) | 수동은 안전하지만 운영자가 상주해야 함. **오인식 대비 수동 오버라이드를 폴백으로 병설**(§7) |

## 3. 구조

```
                          노트북 (PC)
 ┌──────────────────────────────────────────────────────────┐
 │  LLM :8080      STT :8090      TTS :8099   ← 기존 그대로   │
 │                                                          │
 │  ┌────────────────────────────────────────────────────┐  │
 │  │  무대감독 stage_director  :8777       ← 신규         │  │
 │  │   · 큐시트 로더                                      │  │
 │  │   · 턴 상태기계 (불변식 2개, §4)                      │  │
 │  │   · LLM 호출 독점 — 대화 이력이 하나여야 하므로         │  │
 │  │   · 비상 수동 오버라이드 콘솔                          │  │
 │  └───────────┬──────────────────────┬─────────────────┘  │
 └──────────────┼──────────────────────┼────────────────────┘
           WS   │                      │   WS
    ┌───────────┘                      └───────────┐
 ┌──┴─────────────────┐             ┌──────────────┴──────┐
 │ 사회자 로봇           │             │ 도슨트 로봇           │
 │ main.py (ReachyMiniApp)            │ main.py (동일 코드)    │
 │ 마이크 ● 열림 (단일 창구) │             │ 마이크 ○ 닫힘          │
 │ STT·TTS 호출 → PC     │             │ TTS 호출 → PC        │
 └────────────────────┘             └─────────────────────┘
```

**경계 규칙: 로봇 앱은 "무엇을 말할지" 모른다.**

| | 로봇 앱 | 무대감독 |
|---|---|---|
| 입력 | 마이크 → STT → **텍스트 업로드** | 텍스트 수신 → 의도 판정 |
| 판단 | 없음 | 큐시트 진행 / LLM 생성 / 게이팅 |
| 출력 | **수신 텍스트** → TTS → 스피커 + 모션 | 텍스트 + 감정·시선 힌트 하달 |

- **TTS는 로봇에 남긴다** — 두 로봇의 목소리가 달라야 하고, 합성 오디오를 네트워크로
  또 넘기면 지연만 는다.
- **LLM은 감독이 독점한다** — 사회자와 도슨트가 하나의 대화 이력을 봐야 말이 이어진다.

### 3.1 기존 코드에 요구되는 변경

`session.py`의 `respond(user, llm, speaker, player)`가 지금 **LLM → TTS → 모션**을
한 덩어리로 묶고 있다. 둘로 가른다.

- `speak(text, speaker, player)` — 로봇에 남는다 (TTS + 모션)
- LLM 호출부 — 무대감독으로 올라간다

CLAUDE.md의 *"대화 로직은 `session.py` 하나뿐이다"* 는 유지된다. 로봇 쪽 로직은
여전히 한 파일이고, 감독은 그 위층의 새 컴포넌트다. 진입점도 `main.py` 하나 그대로다.

## 4. 프로토콜과 상태기계

WebSocket + JSON. 메시지 9종(로봇→감독 5, 감독→로봇 4).

**로봇 → 감독**

| 메시지 | 내용 | 이유 |
|---|---|---|
| `hello` | `{role, unit_id, version}` | 역할 자기신고. `unit_id` 불일치면 **기동 실패**(사회자/도슨트 뒤바뀜을 시연 전에 잡는다). `None`이면 경고 후 통과 — §6.3·§8.2 |
| `heard` | `{text, t}` | STT 결과 (사회자만) |
| `speaking_started` / `speaking_ended` | `{cue_id, seq}` | **실제 발성 경계.** 게이팅의 진실은 여기뿐. `seq` 는 `say` 에서 받은 발화 번호를 그대로 되돌린다 — 콘솔 `r` 이 같은 `cue_id` 를 재발행하므로 이것 없이는 중단된 발화의 늦은 종료 보고를 못 가른다(2026-09-14, 리뷰 A2) |
| `error` | `{where, detail}` | 조용한 실패 금지 |

**감독 → 로봇**

| 메시지 | 내용 |
|---|---|
| `say` | `{cue_id, seq, text}` — `gaze` 는 별도 메시지로 간다(구현이 그렇다) |
| `mic` | `{open: bool}` |
| `gaze` | `{target: "partner" \| "audience"}` |
| `abort` | 즉시 중단 |

### 4.1 상태기계

```
IDLE ──시작──▶ MC_SPEAKING(cue.mc)
MC_SPEAKING(cue.mc) ──ended──▶ DOCENT_SPEAKING(:docent)   ← 사회자가 말하는 동안 생성
DOCENT_SPEAKING(:docent) ──ended──▶ MC_SPEAKING(:after, cue.mc_after) ──ended──▶ LISTENING
                                     (mc_after 가 없으면 곧장 LISTENING)
LISTENING ──heard("다음"류)──▶ 다음 큐 ──▶ MC_SPEAKING(cue.mc)
LISTENING ──침묵 8초(QUESTION_WAIT_S)──▶ 다음 큐 ──▶ MC_SPEAKING(cue.mc)
LISTENING ──heard(질문)──▶ MC_SPEAKING(:ack, 확인 멘트)   ← 이 동안 LLM 이 답을 생성(락 밖)
MC_SPEAKING(:ack) ──ended──▶ DOCENT_SPEAKING(:qa)
DOCENT_SPEAKING(:qa) ──ended──▶ MC_SPEAKING(:reask, 고정 질문 유도) ──ended──▶ LISTENING
```

(2026-09-14 갱신) 받아치기 `mc_after` 와 질문 확인 멘트 `:ack` 는 **관람객에게 창구가 열렸음을
말로 알리고, 그 시간에 LLM 지연을 숨긴다** — 둘 다 큐 전환의 "고정 대사로 지연 은닉" 과 같은 수법이다.

(2026-09-21 갱신) 그 "말로 알린다" 를 **끝까지 밀었다.** 예전에는 섹션이 끝나면 마이크만 열리고
관람객이 **'다음' 이라는 낱말을 알아야** 진행됐다 — 아무도 그 규칙을 모른다. 이제 ① 받아치기에
질문 유도가 없으면 감독이 고정 문장을 붙이고(`Director._ensure_visitor_cue`), ② 도슨트 답이
끝나면 사회자가 짧게 다시 묻고(`:reask`, 고정 문장이라 지연 0), ③ 그래도 조용하면 8초 뒤
감독이 스스로 다음 섹션으로 간다. `is_advance` 는 그대로 산다 — 아는 사람은 즉시 넘길 수 있다.

**관람객 대기 기한은 발화 타임아웃(`_deadline`)과 별도 필드다**(`_question_deadline`).
앞은 "관람객이 조용하다"(정상 → 진행, 경고 없음), 뒤는 "말하라고 보냈는데 보고가 안 온다"
(고장 → 강제 복구, 경고). 섞으면 침묵할 때마다 "응답이 없다" 가 찍혀 진짜 고장을 못 가린다.

### 4.2 불변식 — 이 설계의 전부

1. **`*_SPEAKING` 상태에서는 어느 로봇의 마이크도 열리지 않는다.**
   게이트 개방은 `LISTENING` 진입 시점 단 한 곳.
2. **`say`는 직전 `speaking_ended`를 받기 전에 다시 보내지 않는다.**

①이 자기목소리 루프를 **음향이 아니라 구조로** 막는다.
도슨트 목소리는 사회자 입장에서 진짜 외부 소리라 **XMOS AEC가 지워주지 않는다** —
AEC에 기대는 설계는 여기서 반드시 깨진다.
②가 동시 발화를 막는다.

**타임아웃**: `speaking_ended`가 (예상 발화 길이 + 여유) 안에 안 오면 강제 `LISTENING`
복귀 + **경고 로그**.

**진행 신호 판정**: LLM 호출 전에 값싼 키워드 매칭 먼저(`다음`·`계속`·`넘어가`).
걸리면 LLM 왕복 없이 즉시 다음 큐. 안 걸리면 LLM에 의도분류+응답을 한 번에 요청.

## 5. 대사 파이프라인

`docs/exhibit-guide.md`는 산문 원장이라 기계가 진행 단위로 못 읽는다.
그 위에 **진행 단위 한 겹**을 얹는다 (`cues.yaml`):

```yaml
- id: "02-history"
  title: "전파의 발견 역사"
  mc: "여기서부터는 전파가 어떻게 발견됐는지 봅니다. 도슨트, 맥스웰부터 부탁해요."
  docent_brief: "맥스웰 예측 → 헤르츠 실증 → 마르코니 실용화. 3문장 이내."
  gaze: partner
```

- `mc` — **고정 대사.** 사회자가 화제를 열고 넘긴다
- `docent_brief` — LLM에게 주는 **지시**이지 대사가 아니다. 여기서 살이 붙는다
- 관람객 질문 — 현재 섹션 id를 컨텍스트로 LLM 호출, 답변자는 도슨트

### 5.1 왜 사회자를 고정하고 도슨트를 생성으로 두는가

사회자는 **진행(transition)** 을 책임지므로 결정적이어야 시연이 안 무너진다.
도슨트는 **내용**을 말하므로 생성이 이득이다.

그리고 결정적인 이유가 하나 더 있다 — **지연 은닉.**
사회자 대사가 고정이면 관람객이 "다음"이라 말한 즉시 받아칠 수 있고,
그 발화가 흐르는 3~5초 동안 도슨트 대사를 생성한다.
**LLM 지연이 섹션 전환에 실리지 않는다.** 이게 하이브리드의 진짜 이득이다.

### 5.2 LLM 컨텍스트

이력은 **하나**. 발화는 `사회자:` / `도슨트:` / `관람객:` 접두로 구분.
역할 시스템 프롬프트는 도슨트용 하나면 된다(사회자는 고정 대사).
도슨트 응답은 3~4문장 캡. `docs/exhibit-guide.md`의 "걷어낸 것" 규칙을 그대로 유지한다.

## 6. 주소·기동·WiFi

### 6.1 WiFi 온보딩 (Wireless 2대)

공식 절차: **Reachy Mini Control** 앱 → 하단 "First time connecting…" →
로봇 AP(`reachy-mini-ap`) 접속 → 대상 WiFi 입력.
안 잡히면 **Bluetooth 콘솔** 폴백(Chrome/Edge/Opera, Web Bluetooth).
내부적으로 `POST /api/wifi/connect`(또는 PSK 봉인 `/connect_sealed`) → `nmcli`.
SSH도 열려 있다 — `pollen` / `root`.

**2대일 때만 생기는 함정 3가지**

1. **반드시 한 대씩 온보딩한다.** 두 로봇 AP는 **SSID가 같다**(`reachy-mini-ap`,
   `daemon/app/routers/wifi_config.py:25`). 동시에 켜면 어느 쪽에 붙었는지 알 수 없고
   사회자 설정이 도슨트에 들어간다. → A 설정 → **A 끄고** → B 설정 → 둘 다 켠다.
2. **`reachy-mini.local`이 충돌한다.** 둘 다 hostname이 같다. 해결 순위:
   - **권장: 공유기 DHCP 고정 IP**(MAC 기준) → 결정적이고 mDNS가 막혀도 동작
   - 보조: `find_robots()` + TXT `unit_id`로 역할 검증
   - 근본: SSH `hostnamectl set-hostname` — mDNS 등록이 `socket.gethostname()`을
     그대로 쓰므로(`utils/discovery.py:133`) 광고 이름까지 바뀐다. 단 펌웨어 업데이트가
     되돌릴 수 있다
3. **시연장 공용 WiFi에 얹지 않는다.** ① 데몬 API에 **인증이 없다**
   (`daemon/app/main.py:110-119`가 Wireless에서 `0.0.0.0` 바인드) ② 공용 AP는
   **AP isolation**이 켜진 경우가 많아 노트북↔로봇 통신이 아예 차단된다.
   → **전용 라우터(5GHz) 한 대**에 노트북·로봇 2대만 올린다. Wireless 안테나는
   2.79 dBi 패치 하나뿐이라 라우터를 가까이 두는 것도 실효가 있다.

### 6.2 설정 (기존 config 사다리 재사용)

```
REACHY_MC_HOST=192.168.0.41
REACHY_MC_UNIT=<hardware_id>
REACHY_DOCENT_HOST=192.168.0.42
REACHY_DOCENT_UNIT=<hardware_id>
REACHY_DIRECTOR_URL=ws://192.168.0.10:8777
REACHY_LLM_URL / REACHY_STT_URL / TTS_QWEN_URL     # 기존 그대로
```

### 6.3 기동 순서

라우터 → 로봇 2대(WiFi 연결 확인) → PC 추론 3종 → 무대감독 → 로봇 앱 2개.

**기동 검증(fail loud)**: 감독이 `hello`의 `unit_id`를 기대값과 대조한다.
불일치면 즉시 실패하고 사람이 읽을 수 있는 메시지를 낸다.
단 `unit_id`가 `None`이면 **경고 후 통과**한다 — 시뮬에서는 항상 `None`이다(§8.2).

### 6.4 로봇 온보드 앱 슬롯을 비운다

`daemon/robot_app_lock.py:1-16` — *"SDK clients talking to the daemon directly over
LAN/WebSocket bypass it entirely."* 우리 앱은 온보드에서 도니 락을 잡지만,
**대시보드 startup-app이 켜져 있으면 모터를 두고 싸운다.** 두 로봇 다 비워둔다.

## 7. 실패 모드와 폴백

| 실패 | 감지 | 폴백 |
|---|---|---|
| 로봇 1대 WS 끊김 | 하트비트 / WS close | 남은 1대가 양쪽 대사를 읽는 **1인 모드**로 강등 + 경고 |
| `speaking_ended` 미도착 | 타임아웃 | 강제 `LISTENING` + 경고 |
| STT 오인식으로 진행 폭주 | 섹션 급전환 / 반복 | **수동 오버라이드**로 되돌림 |
| LLM 지연·실패 | 타임아웃 | `docent_brief`를 그대로 읽는 축약 대사 + 경고 |
| TTS 실패 | 기존 사다리 | 기존과 동일 (경고 필수) |
| 동시 발화 | 불변식 ② 위반 감지 | 양쪽 `abort` + 상태 리셋 |

전부 **경고 로그를 남긴다.** 조용히 성능이 떨어진 채 도는 것이 가장 나쁘다.

## 8. 개발·테스트 경로 — **실측 검증됨 (2026-09-11)**

### 8.1 시뮬 2대 구성

```bash
.venv/bin/python -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
  --fastapi-port 8000 --robot-name mc
.venv/bin/python -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
  --fastapi-port 8001 --robot-name docent
```

`--mockup-sim`은 MuJoCo가 필요 없어 **mjpython/Cocoa 메인스레드 제약을 우회한다.**
실측 결과:

- 두 데몬 공존 OK (`/api/daemon/status` 둘 다 200, `robot_name`이 각각 `mc`/`docent`)
- **한 프로세스에서 2대 독립 제어 OK** — 동시에 head yaw `+25°` / `-25°` 지시,
  되읽어 각각 정확히 반영됨. 목표가 섞이지 않는다
- `find_robots()`가 **2대를 구분해서 찾음** (`robot_name` 기준)

시각 확인이 필요하면 한 대만 `./reachy.sh sim`(mjpython + 뷰어, :8000),
나머지는 mockup(:8001)으로 둔다.

### 8.1.1 앱 2개까지 붙인 종단 구동 — **실측 검증됨 (2026-09-20)**

위 §8.1 은 데몬 공존까지만 봤다. 앱 2개를 각자 데몬에 붙여 턴을 돌리는 것은
`REACHY_DAEMON_PORT` 가 생긴 뒤에야 된다 — 그전에는 `main.py` 의 `__main__` 이
`wrapped_run()` 을 인자 없이 불러 **둘 다 :8000 에 붙었다**(로봇 하나만 움직이는데
양쪽 로그는 정상으로 보인다).

터미널 넷이다.

```bash
# ① 데몬 2대 (§8.1 과 같다)
.venv/bin/python -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
  --fastapi-port 8000 --robot-name mc
.venv/bin/python -m reachy_mini.daemon.app.main --mockup-sim --headless --no-media \
  --fastapi-port 8001 --robot-name docent

# ② 무대감독 (LLM 이 있어야 한다 — 없으면 폴백 대사로 돈다)
.venv/bin/python -m stage

# ③ 앱 2개 — 역할·데몬 포트·출력 장치를 짝지어 준다
#    REACHY_AUDIO_OUT 은 sounddevice 장치 이름의 일부(또는 인덱스).
#    목록: .venv/bin/python -c "import sounddevice; print(sounddevice.query_devices())"
REACHY_ROLE=mc     REACHY_DAEMON_PORT=8000 REACHY_DIRECTOR_URL=ws://127.0.0.1:8777 \
  REACHY_AUDIO_OUT="MacBook Pro 스피커" \
  .venv/bin/python apps/voice_chat/voice_chat/main.py
REACHY_ROLE=docent REACHY_DAEMON_PORT=8001 REACHY_DIRECTOR_URL=ws://127.0.0.1:8777 \
  REACHY_AUDIO_OUT="ZoomAudioDevice" \
  .venv/bin/python apps/voice_chat/voice_chat/main.py
```

역할별 음성은 `main.py` 의 `ROLE_VOICE` 가 `apply_role_voice()` 로 넣는다 —
**사회자 `serena`(속도 1.27), 도슨트 `sohee`(속도 1.13)**. `tts.py` 는 이 값을
요청마다 사다리에서 다시 읽으므로 앱 기동 뒤에 넣어도 먹는다. 운영자가 환경변수나
설정파일에 직접 적은 값이 있으면 그쪽이 이긴다(`config.source()` 검사).
소리를 실제로 들으려면 TTS 서버가 떠 있어야 한다 — 없으면 발화가 실패하는데
**감독에게는 정상 종료로 보고되어 무음으로 진행된다**(`docs/real-robot-deployment.md` §4).

실측 결과(2026-09-20): 두 앱이 각각 붙고(`[mc] 붙었다`/`[docent] 붙었다`), 콘솔 `s`
뒤 상태가 `mc_speaking → docent_speaking → mc_speaking(받아치기) → listening` 으로
완주했다. 두 데몬의 `/api/state/full` 이 **서로 다른 머리 자세**를 보고해 독립
제어도 확인됐다(mc 는 원점 근처, docent 는 `z=-0.045`).

**⚠️ 사회자를 :8000 에 둔다.** SDK 가 8000 이 살아 있는지로 localhost/network 모드를
고른다(`ReachyMiniApp._check_daemon_on_localhost(port=8000)` 이 8000 고정). 8001 만
띄우면 network 모드로 빠져 `reachy-mini.local` 을 찾다 실패한다.

**⚠️ 출력을 갈라 주지 않으면 소리가 섞인다.** 앱은 `--no-media` 라 SDK 미디어를 안
타고 오디오를 직접 연다. `REACHY_AUDIO_OUT` 을 안 주면 두 앱이 **같은 기본 출력**을
쓰고, 도슨트 소리가 사회자 마이크로 되돌아와 자기목소리 루프가 실기보다 훨씬 쉽게
난다(실기는 두 로봇이 물리적으로 떨어져 있다). 갈라 줘도 마이크는 하나라
(`main.py` 가 `role == "mc"` 일 때만 청취 루프를 띄운다) 한 방에서 두 스피커가
울리는 것은 그대로다 — **음향 최종 판단은 실기에서 한다.** 이 경로는 턴 전환·
마이크 게이트·역할 배선·음성 구분 확인용이다.
`_afplay` 폴백과 AEC 프로브의 GStreamer sink 는 이 장치 설정을 **못 따른다.**

### 8.2 이 실험에서 발견한 것 — `docs/lessons.md` 등재 대상

1. **`DiscoveredRobot.host`를 쓰지 말 것.** `...local.local.` 로 `.local`이 중복돼
   나온다. **`r.addresses[0]`** 를 쓴다.
2. **macOS `dns-sd` 경로에서 TXT 값이 공백에서 잘린다.** `model`이 `"Reachy\"`로
   나왔다(`Reachy Mini Lite`가 잘린 것). `_dnssd_resolve`가 TXT 줄을 공백으로
   split하기 때문(`utils/discovery.py:330-340`).
   → **`model`로 Wireless/Lite를 판별하면 운영자 맥에서 조용히 깨진다.**
   `robot_name`·`address`·`unit_id`는 값에 공백이 없어 안전하다.
3. **`unit_id`는 macOS에서 항상 `None`.** `get_hardware_id()`가 Linux sysfs
   (`/sys/bus/usb/devices`)를 읽는다. 실기(CM4/Linux)에서는 나오지만 **시뮬에서는
   검증 불가** → `unit_id` 대조는 "없으면 경고하고 통과"로 짜야 시뮬 개발이 안 막힌다.

### 8.3 테스트 전략

무대감독 상태기계는 **로봇 없이 단위테스트한다.** 가짜 로봇 2개를 WS로 붙여
§4.2의 불변식 2개를 property test로 고정한다. 문서는 잊히지만 테스트는 실패한다.

## 9. 실기 배포 체크리스트

- [ ] 두 로봇 WiFi 온보딩 (한 대씩), 고정 IP 예약
- [ ] 두 로봇 startup-app 비움
- [ ] `unit_id` 채취 → 설정에 기록 → 기동 검증 통과 확인
- [ ] 추론 3종 주소가 PC를 가리키는지 기동 로그로 확인 (기존 `announce_endpoints()`)
- [ ] `REACHY_AEC` **끔** — 실기는 XMOS AEC가 그 자리를 대신한다
- [ ] 두 로봇 스피커 음량 균형, 물리 배치(시선 상수) 실측

## 10. 미검증 항목

- 두 로봇 동시 운용 시 PC 추론 부하 — 단일 창구라 1대분으로 예상하나 **실측 필요**
- 두 로봇 스피커 간 음향 간섭 — 게이팅으로 턴은 막지만 잔향은 남는다
- CM4(RAM 4GB)에서 기존 앱 + WS 클라이언트 동시 구동 시 메모리 여유
- WEBRTC 미디어 백엔드 실경로 — **안 B는 쓰지 않는다**(그래서 위험이 줄었다)

---

## 11. 음성 배정 — **사회자 `serena` / 도슨트 `sohee`** (2026-09-11 결정)

백엔드는 기존 그대로: CrispASR 0.8.24 + `qwen3-tts-12hz-1.7b-customvoice-q8_0.gguf`.

```
사회자  TTS_QWEN_VOICE=serena
도슨트  TTS_QWEN_VOICE=sohee
```

역할별로 다른 값을 줘야 하므로 **`TTS_QWEN_VOICE`를 로봇별 환경변수로 분리**한다.
`tts.py:95`가 이미 이 변수를 읽으므로 코드 변경은 없다. 단 `reachy.sh:329`가
**서버 기동 시 화자를 못 박으므로**(`--voice "$TTS_VOICE"`), 두 로봇이 같은 TTS
서버를 공유하는 지금 구조에서는 **요청마다 `voice` 필드를 실어 보내야 한다** —
`tts.py:175`가 이미 그렇게 하고 있다(`body = {... "voice": QWEN_VOICE ...}`).
서버 기본값은 요청에 `voice`가 빠졌을 때만 쓰인다.

### 11.1 선택 가능한 화자는 9종뿐이다

모델 메타데이터 `qwen3tts.spk_names`에서 추출(0.6B·1.7B 동일):

```
aiden · dylan · eric · ono_anna · ryan · serena · sohee · uncle_fu · vivian
```

`--list-voices` 같은 CLI 옵션은 없다. GGUF KV를 직접 파싱해야 나온다.

### 11.2 왜 남녀 대비를 포기했나 — **남성 화자는 한국어에서 무너진다**

같은 화자로 한국어/영어를 합성해 중앙 F0를 비교한 실측(YIN, 검증된 측정기):

| 화자 | 한국어 | 영어 | |
|---|---|---|---|
| aiden | 177 Hz | **116 Hz** | 영어에선 명백한 남성, 한국어에서 **+61 Hz** 상승 |
| ryan | 210 Hz | 163 Hz | +47 Hz 상승 |
| serena | 281 Hz | 282 Hz | **언어 무관, 동일** |

`--instruct`로 눌러도 aiden 177→159, ryan 210→167이 한계다(남성 음역 <155 Hz에 못 미침).
**이 모델로 한국어 남성 음색은 나오지 않는다.** 여성 화자는 언어에 흔들리지 않는다.

### 11.3 ⚠️ serena와 sohee는 음높이로 갈리지 않는다

| 문장 | serena | sohee |
|---|---|---|
| 짧은 인사 | 281 Hz | 294 Hz |
| 긴 해설 대사 | 266 Hz | **250 Hz** |

**문장에 따라 순서가 뒤집힌다.** 즉 둘의 F0 차이는 문장 간 변동 폭 안에 있다.
음색 거리(LTAS 기반)도 2.49로, 전체 36쌍 중 11번째로 가깝다(중앙값 3.05).

→ **대비는 음색이 아니라 연출로 만든다.**

### 11.4 역할 연출 (대비 확대)

| | 화자 | `instructions` | 배속(샘플) | 실측 F0 |
|---|---|---|---|---|
| 사회자 | serena | `밝고 또렷하게, 진행자처럼 활기차게` | 1.06 | 266 → 269 Hz |
| 도슨트 | sohee | `차분하고 낮게, 설명하듯 또박또박` | 0.94 | 250 → **224 Hz** |

연출 전 F0 차 16 Hz → **연출 후 45 Hz.** 속도까지 다르므로 청감 대비는 그 이상이다.

#### ⚠️ 배속은 1.0이 아니라 **1.2 기준**으로 환산해야 한다

`tts.py:46` — `QWEN_SPEED = float(os.environ.get("TTS_QWEN_SPEED", "1.2"))`.
**현재 시연은 이미 1.2배속으로 돌고 있다.** 위 표의 1.06/0.94는 CLI 기본값 1.0을
기준으로 만든 샘플 값이라, 그대로 넣으면 **시연 전체가 지금보다 느려진다.**
비율로 환산해 적용한다:

```
사회자  TTS_QWEN_SPEED = 1.2 × 1.06 ≈ 1.27
도슨트  TTS_QWEN_SPEED = 1.2 × 0.94 ≈ 1.13
```

배포 전 이 값으로 다시 합성해 청감을 확인한다 — 1.2 기준의 대비는 실측하지 않았다.

#### 코드 변경은 필요 없다 — 전부 기존 환경변수다

| 항목 | 변수 | 현재 기본값 | 근거 |
|---|---|---|---|
| 화자 | `TTS_QWEN_VOICE` | `serena` | `tts.py:95` |
| 어조 | `TTS_QWEN_INSTRUCT` | `""` (비면 안 보냄) | `tts.py:98,176-177` |
| 배속 | `TTS_QWEN_SPEED` | `1.2` | `tts.py:46,175` |

셋 다 이미 요청 본문에 실린다(`tts.py:175-177`). **로봇별로 값만 다르게 주면 된다.**

**주의**: CLI `--help`는 `--tts-speed`를 `omnivoice/f5/piper/melotts/fastpitch`
전용으로 적고 있으나 **qwen3-tts에서도 정상 동작한다**(실측: 1.06/0.94 모두 반영됨).
문서를 믿고 배제하지 말 것.

### 11.5 채택하지 않은 대안

- **다른 TTS 백엔드**(melotts·piper·kokoro 등) — 한국어 남성이 있을 수 있으나,
  이 저장소가 0.6B→1.7B로 올린 이유가 *모델명 발음 붕괴*였다. 발음 품질 후퇴 위험.
- **음성 복제**(`qwen3-tts-1.7b-base`·`tada`·`f5-tts`·`indextts`) — `--i-have-rights`
  동의가 강제되고 워터마크·음성 AI 고지 프리픽스가 기본으로 붙는다. 공개 시연에 부담.
  참고로 `~/.local/share/reachy-mini-tts/voices/mini-boy.wav`는 297 Hz로 아이 목소리에
  가까워 남성 참조로 쓸 수 없다.
- **후처리 피치 시프트** — 포먼트를 같이 내리지 않으면 "느려진 목소리"로 들린다.
