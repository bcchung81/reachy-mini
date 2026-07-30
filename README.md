# Reachy Mini 음성 일상대화

말을 걸면 알아듣고, 감정 모션으로 즉시 반응하며, 캐릭터 음색으로 답한다.
**추론 3종(STT·LLM·TTS)이 전부 로컬에서 돈다** — 대화 내용이 장비 밖으로 나가지 않는다.

- 개발·시연: MuJoCo 시뮬레이터 (실기 없이)
- 검증 환경: macOS 26.5 / Apple M5 Pro / Python 3.12 (uv)
- 기동: `./scripts/demo.sh` — 없는 서버만 띄우고 예열까지 마친 뒤 음성 모드로 들어간다

```bash
./scripts/demo.sh              # 음성 모드 (기본)
./scripts/demo.sh --text       # 키보드 모드 — 마이크가 말썽일 때
./scripts/demo.sh --no-robot   # 데몬 없이 대화·음성만 — 최후 폴백
./scripts/demo.sh --check      # 상태만 확인
./scripts/demo.sh --stop       # 띄운 서버 전부 종료 (고아까지)
```

---

## 파이프라인 — 한 번의 대화에 무슨 일이 일어나나

```
   🎤 마이크
    │  GStreamer(autoaudiosrc) → 16kHz mono float32, 30ms 프레임
    ▼
┌─────────────┐   말이 끝났는지 판단한다. RMS 임계 0.010,
│ ① VAD       │   침묵이 0.70초 이어지면 한 발화로 잘라 낸다.
│ audio_in.py │   ← 0.30초로는 문장 중간에 끊겼다(실측). 이 0.70초가
└─────────────┘     전체 지연에서 가장 큰 단일 항목이다.
    │  발화 WAV
    ▼
┌─────────────┐   HTTP POST :8090 (OpenAI 호환)
│ ② STT       │   Whisper Large V3 Turbo (MLX, Apple Silicon 최적화)
│ stt.py      │   언어 자동감지 — 영어로 말하면 영어로 알아듣는다
└─────────────┘   ⏱ 0.35~0.49초
    │  텍스트
    ▼
┌─────────────────────────────────────────────────────┐
│ ③ 분기 — session.respond()                          │
│                                                     │
│  "어떻게 만들어졌어?" → 고정 대본 (LLM 안 씀)        │
│      모델명·수치를 지어내면 안 되므로 가로챈다       │
│                                                     │
│  "슬픈 표정 지어봐"   → 감정 연기 18종 중 재생       │
│                                                     │
│  그 외                → LLM 으로                    │
└─────────────────────────────────────────────────────┘
    │
    ├──────────────┐
    ▼              ▼
┌─────────────┐  ┌──────────────┐  모션은 **LLM 을 기다리지 않는다.**
│ ④ LLM       │  │ ④' 모션      │  사용자 발화만 보고 즉시 고른다 —
│ llm.py      │  │ motion.py    │  그래서 0.95초에 반응이 보인다.
│             │  │ animator.py  │  감정 라이브러리 85종.
│ Gemma 4 E4B │  └──────────────┘
│ Q4_K_M      │
│ :8080 스트림 │  ⏱ 첫 토큰 0.03~0.08초 / 첫 절 0.07~0.55초
└─────────────┘
    │  토큰 스트림
    ▼
┌─────────────┐   문장이 완성되기 전에 **절 단위로 잘라 먼저 보낸다.**
│ ⑤ 절 분할   │   첫 절은 쉼표에서도 끊는다 — 첫 소리를 앞당기려고.
│ clauses.py  │   폭주 방지 120자.
└─────────────┘
    │  "안녕하세요," / "오늘 기분이 좋아요."
    ▼
┌─────────────┐   HTTP POST :8099 (OpenAI 호환)
│ ⑥ TTS       │   Qwen3-TTS 1.7B CustomVoice, 화자 `serena`, speed 1.2
│ tts.py      │   GGUF + CrispASR(Metal) — transformers/MPS 대비 5.6배
└─────────────┘   ⏱ 첫 절 0.31초 (HTTP 왕복, 3회 편차 0)
    │  PCM 24kHz mono s16
    ▼
┌─────────────┐   PortAudio 스트림을 **한 번만 열고 재사용**한다.
│ ⑦ 재생      │   발화마다 afplay 를 띄우면 길이와 무관하게 0.8초
│ StreamPlayer│   고정비가 붙었다(실측) — 그걸 없앤 것이다.
└─────────────┘
    │
    ▼  🔊 스피커 ─── 재생 중에는 마이크 입력을 통째로 버린다(half-duplex).
                     하드웨어 에코캔슬이 없어서다. 재생 후 0.3초 잔향 가드.
```

### 총 지연 — 발화 종료부터

| 구간 | 실측 | 비중 |
|---|---|---|
| VAD hangover | 0.70s | 설정값 — **가장 크다** |
| STT | 0.49s | |
| **LLM 첫 절** | **0.07s** | **3%** |
| TTS 합성 | 0.31s | 1.7B CustomVoice/serena, speed 1.2 |
| 재생 스트림 | 0.00s | 상주(afplay 0.8초 고정비를 없앴다) |
| **구간 합** | **약 1.6초** | |
| → 모션 | 약 0.95초 | LLM 을 안 기다린다 |

구간 합은 각각을 따로 잰 값을 더한 것이다. **끝단 실측은 1.80초**였는데
그때 TTS 가 0.54초였다(`docs/latency-m0.md`). 지금 구성은 그보다 빠르지만
끝단으로 다시 재지는 않았다.

설계 초기에는 LLM 을 지배적 병목으로 봤지만 **실측하니 3%였다.** 스키마 제약을
걷어낸 뒤로 그 가정은 무효다. 지금 가장 큰 것은 VAD 대기 시간이고, 그건 품질을
위해 의도적으로 늘린 값이다(0.30초로는 질문이 중간에 잘렸다).

---

## 프로덕션 구조

### 배치 — 무엇이 어디서 도나

```
┌──────────── 로봇 (Reachy Mini / Pi5) ────────────┐
│                                                  │
│   VoiceChat(ReachyMiniApp)   ← main.py           │
│     ├ 마이크 캡처 (GStreamer)                     │
│     ├ VAD · 절 분할 · 모션 재생                   │
│     └ 스피커 출력                                 │
│                                                  │
│   * 오디오가 네트워크를 타지 않는다               │
└──────────────────────┬───────────────────────────┘
                       │ HTTP (WiFi)
                       │ 발화당 파일 하나 — 지터에 강하다
                       │ 전송 실측 14~27ms
┌──────────────────────┴───────────────────────────┐
│                     PC (맥)                       │
│                                                  │
│   :8080  LLM   llama.cpp · Gemma 4 E4B Q4_K_M    │
│   :8090  STT   stt_server.py · Whisper v3 Turbo  │
│   :8099  TTS   CrispASR · Qwen3-TTS 1.7B         │
│                                                  │
│   * 1.7B TTS 는 Pi5 에 무리라 어차피 PC 몫이다    │
└──────────────────────────────────────────────────┘
```

세 주소는 **코드 수정 없이** 환경변수로 옮긴다:

```bash
REACHY_LLM_URL=http://<PC>:8080
REACHY_STT_URL=http://<PC>:8090/v1/audio/transcriptions
TTS_QWEN_URL=http://<PC>:8099/v1/audio/speech
```

### 진입점이 둘인 이유

| | 파일 | 쓰임 |
|---|---|---|
| 정상 | `main.py` | `ReachyMiniApp` — **실기가 실행하는 것.** 시연도 이것으로 돈다 |
| 폴백 | `demo.py` | `--text` / `--no-robot` — `ReachyMiniApp` 이 표현 못 하는 모드 |

`demo.sh` 의 기본 경로가 `main.py` 다 — **시연에서 돌리는 것과 배포하는 것을
같게** 두려는 것이다. 예전에는 데모가 `demo.py` 만 태워서 `main.py` 가 생성
템플릿인 채로 방치된 것을 아무도 몰랐다.

**대화 로직은 `session.py` 하나뿐이다.** 진입점에 복사하지 않는다.

### 모듈

```
apps/voice_chat/voice_chat/
├ main.py        실기 진입점 (ReachyMiniApp, stop_event 로 종료)
├ demo.py        폴백 진입점 (--text / --no-robot)
├ session.py     ★ 대화 로직 — build() / respond() / announce_voice()
├ voice_loop.py  마이크 루프 + half-duplex 게이팅
│
├ audio_in.py    GStreamer 캡처 + 에너지 VAD
├ stt.py         → STT 서버
├ llm.py         → LLM 서버 (스트리밍, 이력 3쌍)
├ clauses.py     토큰 스트림 → 절 분할
├ tts.py         → TTS 서버 + 상주 오디오 스트림 + 폴백 사다리
│
├ motion.py      발화 → 모션 카테고리 분류
├ emotions.py    감정 연기 18종 · 대기 모션
├ animator.py    말할 때 흔들림 / 조용할 때 숨쉬기
├ idler.py       12~25초마다 혼자 감정 표현
├ selfintro.py   "어떻게 만들어졌어?" 고정 대본 + 문장별 시드
└ prompt.md      성격 정의
```

### 고장나도 말은 한다 — 폴백 사다리

```
TTS 서버 (Qwen3-TTS)
   └ 실패 → 로컬 합성기: say(macOS) → espeak-ng → espeak
              └ 없음 → 경고 로그 (조용히 넘어가지 않는다)

오디오 스트림 (PortAudio)
   └ 못 열면 → 외부 재생기: afplay → paplay → aplay
                 └ 없음 → 경고 로그

LLM 서버
   └ 실패 → 고정 폴백 대사 + 모션은 계속 동작
```

`TTS_BACKEND=say` 로 통째로 macOS 음성으로 되돌릴 수도 있다.

### 바꿔 끼우는 지점

| 바꿀 것 | 건드릴 곳 |
|---|---|
| 성격·말투 | `prompt.md` |
| 음색 | `TTS_QWEN_VOICE` (9화자) 또는 `tts.py` |
| 감정 매핑 | `motion.py` / `emotions.py` |
| 클라우드 LLM | `REACHY_LLM_URL` — OpenAI 호환이라 주소만 바꾼다 |
| 자기소개 대본 | `selfintro.py` (표기 규칙은 `apps/voice_chat/selfintro-script.md`) |

---

## 문서

| | |
|---|---|
| [`docs/demo-runbook.md`](docs/demo-runbook.md) | 시연 런북 — 기동·시나리오·장애 대응 |
| [`docs/latency-m0.md`](docs/latency-m0.md) | 지연 실측과 그 해석 |
| [`docs/tts-voice-followup.md`](docs/tts-voice-followup.md) | 음색 선정 과정과 TTS 실측 전량 |
| [`docs/real-robot-deployment.md`](docs/real-robot-deployment.md) | **실기 배포 검증** — 남은 미검증 항목 |
| [`apps/voice_chat/selfintro-script.md`](apps/voice_chat/selfintro-script.md) | 자기소개 대본과 표기 규칙 |
| [`CLAUDE.md`](CLAUDE.md) · [`agents.local.md`](agents.local.md) | 개발 규약과 이 환경의 제약 |

## 알려진 한계

- **끼어들기 불가** — 로봇이 말하는 중에는 듣지 않는다. 시뮬에 하드웨어
  에코캔슬이 없어서이고, 실기의 XMOS AEC 에서는 해소 가능하다.
- **사용자는 한국어로만 말한다** — STT 입력은 한국어 기준이다. 로봇이 영어·일본어·
  중국어로 *답하는* 것은 된다(같은 목소리로 읽는다).
- **절 단위 직렬 재생** — 합성과 재생이 겹치지 않아 절 사이에 합성 시간만큼 빈다.
  한 절 앞서 미리 합성하면 사라진다(미적용).
- **실기 스피커 출력 경로 미검증** — `docs/real-robot-deployment.md` 참고.
