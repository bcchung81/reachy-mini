# 핸드오프 — 추론 3종의 프론티어 API 전환과 수준별 모션 교육자료 (2026-11-10)

> **이어지는 문서**: ElevenLabs 구독 이후의 할 일·순서·완료 기준은 [2026-11-12 핸드오프](2026-11-12-after-elevenlabs-subscription.md)에 있다. 이 문서는 배경과 근거다.

이 문서 하나로 다음 작업자가 이어받을 수 있게 쓴다. **코드는 아직 한 줄도 바꾸지 않았다**(종이 무대 교육자료 제외 — §8).
착수 전에 규약대로 `plan.md` 승인을 받는다(CLAUDE.md 작업 규약).

표기: **[결정]** 사용자가 정한 것 · **[권장]** 조사 근거로 권하는 것(미승인) · **[미결]** 측정·결정 필요 · **[확인]** 공식 문서로 확인한 사실(날짜 2026-11-10).

---

## 0. 한눈에

| 항목 | 상태 |
|---|---|
| 방향 | **[결정]** 오픈웨이트 외부 서빙이 아니라 **프론티어 모델 API**로 옮긴다. 그중 **차선안**(TTS = ElevenLabs)으로 간다 |
| 배포 | **[결정]** 실기(Reachy Mini Wireless)에 배포해 운영할 수 있어야 한다 |
| 구조 | **[권장]** PC 게이트웨이형 — 로봇 앱 코드 수정 0, API 키는 PC에만 |
| LLM | **[미결]** OpenAI `gpt-6-luna`(사고 끔) vs Claude Haiku 5.5(사고 끔) — 실제 질문으로 실측해 결정 |
| STT | **[미결]** OpenAI `gpt-transcribe`(경로 그대로) vs Azure Speech Korea Central(국내 처리). ElevenLabs Scribe는 무보존이 엔터프라이즈 전용이라 후순위 |
| TTS | **[결정]** ElevenLabs. 고정 대사 굽기 = `eleven_v4`, 실시간 답 = `eleven_v4_turbo` **[권장]** |
| 목소리 | **[권장]** 사회자 Jennie, 도슨트 Seulki — 오디션으로 확정 **[미결]** |
| 요금제 | ElevenLabs **구독 완료**(2026-11-12, 사용자 보고 — 권장안 Creator 월 $22, 요금제 이름은 구독 화면으로 확인). 1~2개월 사용량을 보고 Pro 승급 판단 |
| 교육자료 | **[결정]** 일반 = 종이 무대 24번(완성) → **음성만 ElevenLabs로 교체**. 초중등 = **웹툰 칸 연출 157번**, 전문가 = **분해도 148번** 기법으로 새로 제작(§7) |

---

## 1. 왜 바꾸나 — 결정 이력

1. 지금은 맥북 한 대가 추론 3종을 돈다: LLM `llama-server`(Gemma 4 E4B, 사고 끔, 자유대화 평균 1.9초), STT `stt_server.py`(mlx-whisper large-v3-turbo), TTS CrispASR(Qwen3-TTS 1.7B CustomVoice, 사회자 `serena`·도슨트 `sohee`) + 결과 캐시 프록시.
2. 1차 조사: 같은 오픈웨이트 모델을 외부에서 서빙(DeepInfra Gemma 4·Groq Whisper·DeepInfra Qwen3-TTS). E4B는 외부 제공처가 없어 26B-A4B로 올라가야 했다.
3. 2차 조사(사용자 요청): **프론티어 모델로**. 사실 확인 결과 —
   - OpenAI 단독 TTS(`gpt-4o-mini-tts`·`tts-1`·`tts-1-hd`)는 **2027-01-06 종료** [확인]. 대체 Realtime은 대본 글자 그대로 읽기를 보장하지 않는다 → TTS 후보 제외.
   - Gemini 3.x 텍스트 모델은 사고를 끌 수 없어 첫 토큰 4~5초 [확인] → LLM 후보 제외.
   - Anthropic은 STT·TTS API가 없다.
   - 실시간 음성-음성 API(OpenAI Realtime·Gemini Live)는 대본을 글자 그대로 읽는 보장이 없어 **공연에 부적합**.
4. 사용자가 **차선안(ElevenLabs 목소리)**으로 실기 배포까지 가기로 했다.

---

## 2. 목표 구조 — PC 게이트웨이형 [권장]

```
 로봇(앱만)                       PC(GPU 불필요)                         외부
 ───────────                      ─────────────────────────────          ──────────────
 REACHY_LLM_URL  ───────────────► 게이트웨이 /v1/chat/completions ─────► LLM(Claude 또는 OpenAI)
 REACHY_STT_URL  ───────────────► 게이트웨이 /v1/audio/transcriptions ─► STT(OpenAI 또는 Azure)
 TTS_QWEN_URL    ───────────────► tts_cache_proxy(넓힘) ─┬─ 캐시 적중 → 고정 대사 PCM(오프라인)
                                                          └─ 미스 → ElevenLabs(pcm_24000 스트림)
                                  · API 키 주입  · 형식 번역  · 실패 시 경고 + 폴백
```

- 로봇은 지금처럼 PC 세 주소만 안다(`docs/real-robot-deployment.md` §실기 토폴로지). **로봇 앱 코드·키 변경 없음** → "주소만 바꿔 옮긴다" 규칙 그대로.
- Claude가 OpenAI 호환이 아니어도 번역은 게이트웨이 안에서 끝난다(Claude는 공식 `anthropic` SDK로 부른다 — OpenAI 호환 shim 금지).
- 대안(로봇 직결형)은 PC를 없앨 수 있지만 키·SDK·캐시(약 123 MB)를 로봇에 올려야 하고, 오프라인이면 실시간 답이 통째로 죽는다(CM4 4 GB라 로컬 폴백 불가). **채택하지 않는다.**

---

## 3. 역할별 결정과 근거

### LLM [미결 — 실측으로 결정]

| 후보 | 100만 토큰당 입/출 | 첫 토큰 | 붙이는 법 | 주의 |
|---|---|---|---|---|
| OpenAI `gpt-6-luna` | $0.10 / $0.50 | 사고 끔 0.74~1.37초(AA) | OpenAI 호환 그대로 | `reasoning_effort:"none"` 필수(기본 medium이면 5초대). 공개 지능 지수 9(중앙값 14) — 도슨트 정확성 위험 |
| Claude Haiku 5.5 (`claude-haiku-5-5`) | $0.10 / $0.50(10만 토큰 이하) | 사고 끈 상태 **미측정** | `anthropic` SDK, 시스템 프롬프트 캐싱 | `temperature` 보내면 400. 사고 끄기는 effort high 이하에서만 |
| (품질 경로) Claude Sonnet 5.5 | $2 / $10 | 미측정 | 동일 | 전문가 수준 답·감독 애드리브 후보(§6) |

결정 방법: `.demo-logs/app.log`의 실제 관람객 질문 20~50개 × 4수준으로 블라인드 비교(정확성·수준 규칙 준수·한국어) + 한국에서의 지연 실측.

### STT [미결]

| 후보 | 가격 | 장점 | 주의 |
|---|---|---|---|
| OpenAI `gpt-transcribe` | 분당 $0.0045 | `/v1/audio/transcriptions` 그대로 | `language` → `languages` 배열. 서버의 자동 감지·한국어 재시도 로직은 게이트웨이로 옮겨야 함 |
| Azure Speech Korea Central | 빠른 전사 시간당 $0.36 | **국내에서 처리**(관람객 음성이 나라 밖으로 안 나감) | 자체 API — 게이트웨이 번역 필요 |

### TTS [결정: ElevenLabs]

- 모델: 고정 대사는 `eleven_v4`($0.08/1천 자, 지연 무관·품질 우선), 실시간 답은 `eleven_v4_turbo`($0.04/1천 자, 약 100 ms). **두 모델의 소리 차이가 크면 고정 대사도 Turbo로 굽는다** [미결: 청취].
- 출력: `pcm_24000` — 지금 로봇이 받는 형식과 같다(기본은 MP3라 반드시 지정).
- v4는 **속도 숫자·SSML 미지원**(사회자 1.27·도슨트 1.13 배속을 못 준다), 감정은 본문 안 오디오 태그(`[excited]` 등).
- 목소리: serena·sohee는 어느 업체에도 없다. v4의 복제는 **실제 화자의 검증된 동의**가 필요 → Qwen 프리셋은 복제 불가. **새 목소리로 바뀐다.**

---

## 4. 운영 흐름

### 4.1 대본 읽기(고정 대사) — 미리 굽기

| 단계 | 할 일 | 함정 |
|---|---|---|
| 굽기 | `bake_tts.py`에 ElevenLabs 경로 추가 후 528문장 굽기 | **반드시 새 캐시 폴더(`TTS_CACHE_DIR`).** 캐시 키는 로봇 요청 본문의 sha256뿐이고 엔진이 안 들어간다(`tts_cache_proxy.py::cache_key`) — 같은 폴더면 옛 Qwen 소리가 그대로 나간다. 새 폴더면 되돌리기도 폴더만 바꾸면 된다 |
| 속도 | 굽는 시점에 시간 늘이기·줄이기로 맞추거나, 자연 속도를 받아들이고 감독 분량 환산(`CHARS_PER_SEC = 4.0`, `data/levels.yaml` 주석)을 재보정 | HUD 템플릿의 `CPS = 4.0`도 같이 |
| 어조 | 게이트웨이가 `instructions`(감정 어조, 스위치 뒤 기본 꺼짐)를 오디오 태그로 번역 | 한국어에서 태그 효과는 청취로 확인 |
| 발음 | 틀리게 읽은 문장은 **읽기용 표기**만 바꿔 다시 굽기(예: "GMDSS" → "지엠디에스에스"). 대본 원문·캐시 키는 그대로, 표기 사전은 게이트웨이에 | 대본(`data/cues.yaml`)을 고치지 않는다 — 검증기·카드가 원문을 본다 |
| 검수 | 528문장 재청취 | 실제 비용은 이것 |

공연 중 고정 대사는 캐시에서 바로 나간다 → **네트워크가 끊겨도 대본 공연은 계속된다.**

### 4.2 자유질문 대응 — 실시간 합성

관람객 말 → STT → LLM 절 단위 스트림 → 로봇이 절마다 TTS 요청 → 게이트웨이 캐시 미스 → ElevenLabs 스트리밍 → 로봇 재생.

- 첫 절을 짧게, 첫 소리 전에는 **미리 구운 맞장구**("좋은 질문이에요")를 같은 목소리로 즉시 재생.
- 속도: 실시간 시간 늘이기는 지연·음질을 해친다 → 고정 대사도 자연 속도로 통일하길 권함.
- 발음: 답은 미리 못 들으니 게이트웨이에서 숫자·약어 읽기 규칙 적용(ElevenLabs 발음 사전의 v4 지원은 **[미결]**).
- 실패 정책 **[미결]**: ① 같은 목소리로 미리 구운 "잠깐 연결이 불안정해요" 재생 후 넘김(권장, 목소리 유지) ② 로컬 Qwen으로 계속(목소리 바뀜, 경고 필수).
- TTS로 나가는 건 로봇이 할 말(텍스트)뿐 — 관람객 음성보다 개인정보 부담이 작다.

---

## 5. 목소리·요금제

### 목소리 후보 [권장 — 오디션으로 확정]

| 역할 | 1순위 | 다른 후보 | 남성 대안 |
|---|---|---|---|
| 사회자(밝은 진행자) | **Jennie** `z6Kj0hecH20CdetSElRT` | Anna Kim, Stella | KKC(밝은 젊은 남성) |
| 도슨트(차분한 해설) | **Seulki** `ksaI0TCD9BstzEzlxj4q` | Selly Han `ETPP7D0aZVdEj12Aa7ho`, Hyein | Jeonggi `HCANy6ACvOWyndVWS0gV`, Hyun Bin `s07IwTCOrCDCaETjUVjx` |

- 설명·ID 일부는 제3자 정리(json2video) 출처 — ElevenLabs 앱에서 다시 확인한다.
- **기본 제공 목소리(Sarah·Roger 등)는 2026-12-31 만료** [확인] — 쓰지 않는다.
- 라이브러리 목소리는 주인이 공유를 그만두면 사라진다(예고 기간 0~2년) [확인] → **예고 기간 1년 이상** 필터. 구운 고정 대사는 목소리가 사라져도 계속 쓸 수 있다.
- 별도 요율(custom rate) 목소리는 뺀다. 라이브러리 목소리는 모두 v4에서 쓸 수 있다 [확인].
- 오디션 문장: "1901년 12월 12일"(02) · "VLF·EHF"(06) · "GMDSS"(07) · "100메가헤르츠"(03) · 초등 대사 1개. **로봇 스피커로 재생해 듣는다.**

### 요금제 [권장: Creator]

| 요금제 | 월 | v4 Turbo 포함량 | v4 계열 동시 요청 | 판단 |
|---|---|---|---|---|
| Free | $0 | 2만 자 | 2 | 불가 — API로 라이브러리 목소리 사용 불가 [확인] |
| Starter | $6 | 15만 자 | 3 | 로봇 2대에 빠듯 |
| **Creator** | **$22**(첫 달 $11, 연간 월 $18.33) | **55만 자** | **5** | 추정 사용량(월 약 33만 자) 충당, 전문 복제 가능 |
| Pro | $99 | 약 247만 자 | 10 | 월 55만 자 초과·로봇 3대 이상 |
| Enterprise | 견적 | 협의 | 협의 | DPA·SLA·무보존 요구 시 |

사용량 추정 근거: 공연 하루 6회 × 22일 × 회당 실시간 약 2,500자(가정 — 실제 운영 계획으로 갱신). 미사용분은 최대 2개월 이월. 초과 과금 방식은 **[미결]**(가입 화면 확인).

---

## 6. 수준별 관점 — 무엇이 바뀌나

수준은 "사실이 아니라 말하는 방식만" 가른다(`stage/levels.py`). 고정 대사 캐시(2026-11-10 실측):

| 수준 | 고정 대사 | 말하는 방식(`data/levels.yaml`) |
|---|---|---|
| 사회자(공통) | 116문장 · 2,476자 · 4.8분 | — |
| 초등 | 99문장 · 3,278자 · 7.4분 | 비유 중심, 연도·수치 말하지 않음 |
| 중고등 | 105문장 · 3,796자 · 8.8분 | 비유 + 원리 한 겹, 연도만 |
| 일반 | 106문장 · 4,409자 · 10.6분 | 원리 설명, 연도와 개략 수치 |
| 전문가 | 103문장 · 5,194자 · 13.0분 | 정밀(근거 포함) |

### 초중등(초등·중고등)

- **목소리**: 로봇이 같으니 목소리도 같다. 다만 v4는 속도를 숫자로 못 주므로, 초등 대사가 빠르게 들리면 **굽는 시점에만** 늦춘다(실시간 답은 자연 속도).
- **STT**: 아이 목소리 인식률이 가장 큰 위험 — 후보 STT로 초등 연령 녹음 샘플을 실측한다 **[미결]**.
- **LLM**: 초등 규칙("연도·수치를 말하지 않는다")을 새 모델이 지키는지 회귀 확인(지금 `tests/`의 수준 규칙 테스트를 프론티어 응답으로 재실행).
- **교육자료**: 웹툰 칸 연출(157)로 새 HTML을 만든다(§7.3).

### 일반

- **교육자료**: 종이 무대(`docs/design/paper-stage.html`) 완성본 — **음성만 ElevenLabs로 바꿔 다시 빌드**(§8).
- **LLM**: 기본 경로(§3).

### 전문가

- **LLM**: 답의 정확성 요구가 가장 높다 → **전문가 수준 답만 Sonnet 5.5로 라우팅**하는 안을 지연과 함께 실측 **[미결]**(감독이 수준을 알고 있다 — `stage/__main__.py`의 `build_system_prompt(r, level)`).
- **TTS**: 대사가 가장 길다(13분) — 굽기·검수량 최대. 전문 용어·약어 발음 사전이 가장 많이 필요.
- **교육자료**: 분해도(148)로 새 HTML을 만든다(§7.4).

---

## 7. 수준별 모션 교육자료

### 7.1 공통 규칙

- 데모(aimotion, https://kstost.github.io/cokacmotion/ · 소스 `~/workspace/_repos/cokacmotion/skills/aimotion`, MIT)에서는 **기술만** 가져온다. 소재·구도·색·문구·9:16 형식은 가져오지 않는다(SKILL.md "가장 중요한 규칙").
- **외부 리소스 금지**(전시장 오프라인) — 라이브러리를 쓰는 데모(GSAP·three.js·d3·mo.js·anime.js·opentype.js)는 **원리만** 가져와 Canvas 2D·SVG로 직접 쓴다.
- 글자는 DOM `textContent`로만, 검증된 카드 데이터(`visual`의 facts·steps)와 대사에 나온 낱말만 쓴다. 그림 시각은 대사 낱말 위치로(`sc.w()` 방식 — §8).
- 수준마다 `visual` 유형이 다르다(예: 13번은 초등 keyfact, 그 외 steps / 18번은 전문가만 steps). 생성기는 facts·steps 어느 쪽이 와도 같은 자리에 놓아야 한다.

### 7.2 수준별 기준 데모 [결정 2026-11-10]

| 수준 | 기준 데모 | 링크 | 소스(로컬) | 라이브러리 |
|---|---|---|---|---|
| 초중등(초등·중고등) | **157 칸 너머로 점프 — 웹툰 칸 연출** | https://kstost.github.io/cokacmotion/157-webtoon-panels/ | `demos/157-webtoon-panels/`(NOTES.md · strip.js · main.js · art.js) | 없음(Canvas 2D) |
| 일반 | 24 종이 인형 극장 — 스톱모션(완성) | https://kstost.github.io/cokacmotion/24-paper-stopmotion/ | `scripts/handout_paper/` | 없음 |
| 전문가 | **148 손전등 속을 들여다보면 — 분해도** | https://kstost.github.io/cokacmotion/148-exploded-view/ | `demos/148-exploded-view/`(NOTES.md · main.js · parts.js) | three.js |

`demos/` = `~/workspace/_repos/cokacmotion/skills/aimotion/demos/`. 작업 전에 해당 NOTES.md를 끝까지 읽고 "기법과 원리"가 가리키는 줄을 모두 읽는다(aimotion SKILL.md "쓰는 법"). 세 HTML은 **같은 뼈대**를 쓴다 — 빌더가 검증된 카드(`docs/design/handout-hud.html`의 데이터) + 대사 + 캐시 음성을 이어 붙이고, 장면은 대사 낱말 시각(`sc.w()`)에 맞춘다(§8의 `scripts/handout_paper/build.py`·`template.html` 구조를 그대로 따른다). 수준만 다르고 대본 사실은 같다.

### 7.3 초중등 — 157 웹툰 칸 연출로 짓는 법

**가져올 기술(소재 빼고 한 줄로)**: "세로로 이어진 칸 스트립을 스크롤 위치 하나로 시간처럼 흘리고, 칸에 머무는 시간은 읽을거리로, 칸 사이 여백 높이는 쉼의 길이로 정하며(여백 위에서 스크롤 속도장이 느려진다), 칸은 다각형 clip 창이고 층마다 시차가 다르며, 가장 센 박자는 칸 테두리 위 층에 그려 여러 칸의 합집합으로만 잘라 테두리를 깨고 나온다."

| 데모의 기술 | 이 공연에 옮기는 법 |
|---|---|
| 칸에 머무는 시간 = 읽을거리(`strip.js:16`, 음절 × 0.06초) | **실제 음성 길이로 바꾼다** — 캐시 문장의 시작·끝 시각(빌더가 이미 계산)이 칸의 머무는 시간이다. 음성이 바뀌어도(ElevenLabs) 자동으로 다시 맞는다 |
| 여백 = 쉼(속도장, 여백 높이 = 쉼 × 520) | 발화 사이 쉼(빌더의 `GAP_UTT`)과 턴 경계를 여백으로. 사회자 질문 → 도슨트 답 사이 여백, '기억해 두기' 앞에 가장 긴 여백 |
| 칸 모양의 언어(넓은 칸·가로 띠·기울어진 칸·작은 침묵 칸·테두리 없는 칸) | 오프닝 = 넓은 설정 칸, 사회자 질문 = 가로 띠, 도슨트 핵심 순간 = 기울어진 액션 칸, '기억해 두기' 직전 = 침묵 칸, 마지막 = 테두리 없는 칸(해방) |
| 칸 깨기(테두리 위 층 + 합집합 clip, `main.js:315`) | 큐마다 한 번 — 전파·신호가 칸을 뚫고 다음 칸으로(예: 02 대서양을 건너는 모스 신호, 04 불꽃, 17 화성까지 가는 신호) |
| 칸 안 카메라·층 시차(`main.js:118`) | 칸마다 배경·소품 층을 굽고 시차 계수만 준다(정지 구도는 정확히 디자인) |
| 말풍선(타원 + 꼬리, 꼬리 뿌리에서 자라남) | 사회자·도슨트 말풍선. **글자는 DOM**으로 얹고(데모처럼 캔버스에 굽지 않는다 — 검증·접근성 규칙), 풍선 모양만 캔버스 |
| 오른쪽 레일(스트립 지도 + 보는 창) | 큐 진행 지도 — 아이들이 "지금 어디쯤"을 본다 |

**다시 짜야 하는 것**
- **형식**: 데모는 세로 9:16이다. 큰 가로 화면에서는 가운데에 세로 스트립 열을 두고 좌우에 로봇 아이콘·카드를 둔다(형식을 그대로 가져오지 않는다 — aimotion 규칙).
- **소재**: 고양이·옥상·나비·노을 팔레트는 쓰지 않는다. 등장인물은 대본에서(사회자·도슨트 로봇, 큐의 인물·장비), 색은 HUD 토큰(파랑·청록·호박)에서.
- **글꼴**: 데모는 웹 글꼴(Gaegu·Black Han Sans·Pretendard)을 쓴다 → 오프라인이므로 **글꼴 파일을 HTML에 내장**하거나 시스템 글꼴로 대체(라이선스 확인 — 셋 다 OFL).
- **효과음 글자**("찌릿!", "뚜-뚜-")는 사실이 아니라 연출이지만 초등 규칙(수치 금지)과 함께 검수한다.
- **두 수준**: 한 HTML 안에서 초등·중고등을 고른다(대사·카드·그림 유형이 수준마다 다르다 — 13번은 초등 keyfact, 중고등 steps).

### 7.4 전문가 — 148 분해도로 짓는 법

**가져올 기술**: "부품 표 하나(부모·조립 위치·분해 벡터·순서·지연·회전·설명선 기준점)가 장면을 정하고, 장면 그래프가 표의 부모 관계를 따라 자식이 부모와 함께 분해되며, 바깥 부품이 앞장서는 순서 곡선으로 한 동작처럼 풀렸다가 거꾸로 재조립된다. 설명선은 3D 기준점을 매 프레임 화면에 투영하고, 라벨 높이를 가중 등위 회귀(PAVA)로 정렬해 겹치지 않고 지시선이 엇갈리지 않게 한다. 강조 부품만 역방향 껍질 외곽선으로 표시한다."

| 데모의 기술 | 이 공연에 옮기는 법 |
|---|---|
| 부품 표가 장면을 정한다(`main.js:44`) | **큐마다 부품 표 하나**(YAML/JSON). 같은 코드에 표만 바꿔 19큐를 만든다. 표의 라벨 글은 검증된 카드(facts·steps·items)와 대사 낱말에서만 |
| 분해 = 도슨트 턴 시작, 재조립 = '기억해 두기' | 분해 진행은 대사 시각(`sc.w`)에 묶는다. 포인트 i를 말할 때 그 부품이 강조(역방향 껍질 외곽선 + 라벨 밝게, 나머지 65%) |
| 설명선 쌓기(PAVA, `main.js:91`) + 엇갈리지 않는 지시선 | 그대로 — 전문가 수준은 라벨이 많아(수치·근거) 겹침 방지가 핵심 |
| 딸깍(재조립 임팩트) → 점등 | '기억해 두기' 순간 = 재조립 + 그 큐의 핵심이 "켜지는" 박자 |
| 부품 만들기(선반 회전체·압출·튜브, 필렛 단면 — `parts.js`) | 큐의 장비·체계를 코드로 모델링(모델 파일 없음) |

**큐별 "무엇을 분해하나"(초안 — 대본에서 확정)**: 02 무선전신국(안테나·송신기·전건) · 03 전자기파(전기장·자기장·진행 방향을 층으로) · 04 체험 세 장치(전건·불꽃 간극·라이덴 병) · 06 대기층(지표·대류권·전리층을 층으로 분리, 경로 3가지) · 07 선박 무선국(GMDSS 장비) · 08 항공기 통신 장비(무선전화·트랜스폰더·비상위치표지) · 10 무선국 = 설비 + 사람 + 자격 · 11 IoT 구성 · 13 크로마키 합성(전경·키·배경을 층으로 분리 — 기법과 내용이 가장 잘 맞는다) · 14 세대별 단말 · 15 측정기(프로브·계측부) · 16 검사 장비 · 17 탐사 로버(안테나·바퀴·카메라) · 18 테레민(음정·음량 극판, 발진부) · 19 오늘의 줄기 전체. 01·05·09·12는 공간·기관이 주제라 "전시관 단면 분해"로 묶는다.

**다시 짜야 하는 것**
- **three.js**: 외부 리소스 금지 → CDN이 아니라 **버전 고정한 three.js(MIT)를 HTML에 내장**한다(권장 — 수백 KB, 지금 HTML 7.5 MB에 비해 작다). 2D로 다시 쓰는 대안은 품질·공수 모두 불리. 데모가 쓰는 `RoomEnvironment`·`LightProbeGenerator` 애드온도 함께 내장.
- **형식**: 9:16 → 가로 화면. 분해 기둥은 화면 가운데, 설명선 열은 좌우(사회자·도슨트 구역과 겹치지 않게).
- **소재·색**: 손전등·남색 스튜디오·크림 몸통·호박색 하나 강조를 그대로 쓰지 않는다. 강조색은 HUD 토큰에서 하나.
- **라벨**: 데모는 라벨을 캔버스 이미지로 굽는다 → 우리는 **DOM 오버레이**(투영 좌표에 붙임).
- **성능**: PBR + 환경광 — 전시장 PC에서 프레임 시간 실측(데모 수치는 헤드리스 CPU뿐).
- 수준별 그림 유형이 다르다(전문가: 15 steps4, 18 steps5 등) — 부품 표가 facts·steps 어느 쪽이든 받게 한다.

검토했던 다른 후보(채택 안 함): 124 도형 마스코트 · 138 예능 자막 · 119 아이소메트릭 설명 · 102 블록 조립 · 130 퀴즈 · 90 계측 HUD · 129 타임라인 · 128 지수 줌 · 87 센서 시점 · 40 프리즘 · 32 데이터 전환. 기준 데모 위에 보조 기법으로 일부를 빌릴 수 있다(예: 전문가 연표 큐에 129의 연도 카운터).

---

## 8. 일반 수준 종이 무대 — 음성 교체 절차

현재: `scripts/handout_paper/`(빌더·틀·장면) → `docs/design/paper-stage.html`(19큐, 일반 수준, Qwen 캐시 음성, 7.5 MB). 장면 코드는 낱말 위치로 시각을 잡으므로 **모션은 손댈 필요가 없다.**

1. 선행: ElevenLabs 키(지금 환경에 **없음**), 목소리 확정(§5), `bake_tts.py`의 ElevenLabs 경로.
2. 새 캐시 폴더에 굽기: `TTS_CACHE_DIR=~/.local/share/reachy-mini-tts/cache-elevenlabs ./reachy.sh bake`(ElevenLabs 경로 구현 후).
3. 다시 빌드: `TTS_CACHE_DIR=…/cache-elevenlabs .venv/bin/python -m scripts.handout_paper.build`
   - 빌더는 캐시 문장을 큐시트 순서로 줄 세우고 글이 다르면 멈춘다(`docs/lessons.md` — 색인 순서 ≠ 말하는 순서).
   - 폴더를 나누면 옛·새 목소리가 섞일 일이 없다(같은 색인에 둘 다 있으면 빌더가 같은 문장을 두 번 잡아 멈춘다).
4. 점검: `docs/design/paper-stage.html?check=1` → `body[data-warn]`가 `[]`인지(대사에 없는 낱말 경고), `?cue=NN&t=초`로 큐마다 캡처, `tests/test_handout_paper.py` 통과.
5. 문장 길이가 바뀌므로(속도 숫자 없음) 큐 길이가 달라진다 — 화면은 자동으로 따라간다.

---

## 9. 바꿀 코드(전부 PC 쪽) — 착수 전 `plan.md` 승인

- `tts_cache_proxy.py`: ElevenLabs 어댑터(역할→목소리 ID, 어조→태그, 읽기 표기 사전, 키 주입, `pcm_24000`), 실패 정책·경고. 캐시 키는 **원래 로봇 본문**으로 계속 계산.
- LLM·STT 게이트웨이(새 파일 또는 프록시 확장): Claude는 `anthropic` SDK, OpenAI는 키·`reasoning_effort`·`languages`.
- `scripts/bake_tts.py`: 엔진 선택 + 새 캐시 폴더. 맞장구·연결 불안정 안내 문장 추가.
- 환경변수(신규, 제안): `REACHY_GATEWAY_LLM`·`…_MODEL`·`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, `TTS_UPSTREAM=elevenlabs`, `ELEVENLABS_API_KEY`, `TTS_EL_VOICE_MC`, `TTS_EL_VOICE_DOCENT`, `TTS_EL_MODEL_BAKE`, `TTS_EL_MODEL_LIVE`. **키가 없으면 지금과 똑같이 로컬로 동작**(외부는 스위치 뒤, 기본 꺼짐).
- 테스트로 박제: 키 없으면 외부 호출 없음 / 업스트림이 바뀌어도 캐시 키 불변 / 엔진마다 캐시 폴더 분리 / 폴백 때 경고 1줄 / 수준 규칙(초등 수치 금지) 회귀.
- 문서: `docs/real-robot-deployment.md`(게이트웨이 토폴로지), `docs/lessons.md`.

---

## 10. 개인정보·법무 [검토 필요]

- 국내 처리 보장: **Azure Speech Korea Central(STT·표준 TTS)뿐**. 프론티어 LLM은 서울 처리 보장 경로가 없다(OpenAI `kr`은 저장만, Bedrock 서울의 Haiku 5.5는 Global 라우팅).
- 외부로 나가는 것: 관람객 음성(STT) · 대화 텍스트(LLM) · 카메라 이미지(비전 질문일 때 LLM) · 로봇 대사(TTS).
- 개인정보 보호법 제28조의8(국외 이전), 제25조의2(이동형 영상정보처리기기 — 로봇 카메라 해당 여부, 해당하면 지금 구성에도 적용), 만 14세 미만 관람객.
- 권장: 안내판 고지, 업체별 무보존(ZDR) 신청, 외부 모드에서 카메라 질문 스위치 검토, 요청 본문 로그 금지.

---

## 11. 미결 사항 체크리스트

- [ ] LLM 실측: Luna(사고 끔) vs Haiku 5.5(사고 끔) — 한국어 품질·수준 규칙·지연(한국 기준)
- [ ] 전문가 수준 답 Sonnet 5.5 라우팅 실측
- [ ] STT 결정(OpenAI vs Azure Korea Central) — 아이 목소리 샘플 포함
- [ ] 목소리 오디션(사회자·도슨트) — v4 vs v4 Turbo 소리 차이, 로봇 스피커 재생
- [x] ElevenLabs 가입(2026-11-12 사용자 보고)
- [ ] API 키 발급·저장소 밖 보관, 초과 과금 방식 확인, 예고 기간 1년 이상 목소리 확정 → 11-12 문서 U1~U3
- [ ] 실패 정책(같은 목소리 안내 vs Qwen 폴백)
- [ ] 속도 정책(굽기 때 늦추기 vs 자연 속도 + 분량 재보정)
- [ ] 법무 검토(국외 이전·카메라·아동)
- [ ] 초중등 웹툰 HTML: 157 NOTES·소스 정독 → 칸 문법을 턴 구조에 매핑 → 01·02 시안(동작하는 HTML, 렌더 확인 후 공유) → 19큐
- [ ] 전문가 분해도 HTML: 148 NOTES·소스 정독 → three.js 내장 방식 결정 → 큐별 부품 표 초안 → 01·02 시안 → 19큐, 전시장 PC 프레임 실측
- [ ] `plan.md` 작성·승인 → 게이트웨이 구현 → 굽기 → 종이 무대 재빌드 → 초중등·전문가 HTML

## 12. 작업 트리 상태(커밋 안 됨)

- `scripts/handout_paper/`(build.py · template.html · scenes.js) · `docs/design/paper-stage.html` · `tests/test_handout_paper.py` · `docs/lessons.md`(TTS 캐시 색인 순서 항목 추가) · 이 문서.
- 중단된 작업: 종이 무대에 수준 선택을 넣던 작업 — **방향이 바뀌어 폐기**(초중등·전문가는 다른 기법으로 별도 HTML).

## 13. 주요 출처(2026-11-10 확인)

- ElevenLabs: [요금](https://elevenlabs.io/pricing) · [API 요금](https://elevenlabs.io/pricing/api) · [동시 요청](https://help.elevenlabs.io/hc/en-us/articles/14312733311761-How-many-requests-can-I-make-and-can-I-increase-it) · [보이스 라이브러리](https://elevenlabs.io/docs/eleven-creative/voices/voice-library) · [예고 기간](https://elevenlabs.io/docs/help-center/product/voices/voice-library/what-is-a-notice-period) · [기본 목소리 만료](https://elevenlabs.io/docs/ko/help-center/product/voices/my-voices/what-are-default-voices) · [v4](https://elevenlabs.io/v4) · [v4 기능](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/eleven-v4) · [스트림 형식](https://elevenlabs.io/docs/api-reference/text-to-speech/stream)
- OpenAI: [요금](https://developers.openai.com/api/docs/pricing) · [gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna) · [종료 공지](https://developers.openai.com/api/docs/deprecations) · [STT](https://developers.openai.com/api/docs/guides/speech-to-text) · [데이터](https://developers.openai.com/api/docs/guides/your-data)
- Google: [요금](https://aistudio.google.com/docs/pricing) · [사고](https://aistudio.google.com/docs/thinking) · [데이터 레지던시](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/data-residency)
- Azure: [Speech 리전](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions) · [언어 지원](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts)
- AWS: [Bedrock Haiku 5.5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html)
- Artificial Analysis: [Luna 비추론](https://artificialanalysis.ai/models/gpt-6-luna-non-reasoning) · [TTS 순위](https://artificialanalysis.ai/text-to-speech/leaderboard) · [STT](https://artificialanalysis.ai/speech-to-text)
- Claude 모델·가격·사고 설정: claude-api 스킬(2026-11-03 캐시)
- 한국어 목소리 정리(제3자): [json2video ElevenLabs Korean](https://json2video.com/ai-voices/elevenlabs/languages/korean/)
