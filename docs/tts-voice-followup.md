# TTS 음색 — 조사 결과와 후속 과제

- 조사일: 2026-07-29
- 배경: `say -v Yuna` 음색이 Reachy Mini(작고 귀여운 데스크톱 로봇) 생김새와 맞지 않는다.
  원하는 방향은 **어린이·애니메이션 캐릭터 톤**.
- 결정: **시연은 `say` 로 진행하고 음색은 후속 과제로 미룬다.** 시연에서 증명할 것
  (반응 속도·대화·모션·확장성)은 음색과 무관하게 동작한다.

## 확인한 사실

| 경로 | 한국어 음색 | 판정 | 근거 |
|---|---|---|---|
| macOS 내장 | 9종 — Yuna, Eddy, Flo, Grandma, Grandpa, Reed, Rocko, Sandy, Shelley | 전부 부적합 | 전부 청취 |
| macOS Premium/Enhanced/Siri | 이 기계에 설치된 것 없음 | 사용 불가 | `say -v '?'` 에 미출현 |
| `say` 음높이 조정 `[[pbas N]]` | 문법은 동작 | 부적합 | 청취 |
| **Piper** | **`ko_KR/kss` 하나뿐** (`num_speakers: 1`, 성인 여성 낭독) | 캐릭터 톤 아님 | HF `rhasspy/piper-voices/ko` 트리 조회 + 모델 json |
| MeloTTS | 한국어 단일 화자 | 캐릭터 톤 아님 | 조사 |

**합성 속도 실측(같은 문장, `say -o`)**: Yuna 0.82s / 캐릭터 8종 0.46~0.56s.
캐릭터 음성이 유나보다 빠르다 — 음색만 맞으면 지연에도 유리했다.

### Piper 설치 시 걸린 문제 (재시도할 사람을 위해)

`pip install piper-tts==1.6.0` 은 되지만 macOS arm64 휠에 espeak 데이터 경로가
**빌드머신 경로로 박혀 있다**:

```
Error processing file '/Users/runner/work/piper1-gpl/.../espeak-ng-data/phontab':
No such file or directory.
```

번들 데이터는 `site-packages/piper/espeak-ng-data/` 에 실제로 존재하고
`ESPEAK_DATA_PATH` 환경변수로는 우회되지 않았다. `EspeakPhonemizer(espeak_data_dir=...)`
를 직접 넘기는 경로를 파야 한다. 다만 **고쳐도 나오는 음색은 성인 여성 낭독**이라
캐릭터 톤 목적에는 의미가 없어 더 진행하지 않았다.

## 결론

기성 한국어 TTS에는 애니메이션 캐릭터 음색이 **프리셋으로** 없다. 만들어야 한다.

## 유력 후보 — Qwen3-TTS VoiceDesign (2026-07-30 추가)

해외 사례 조사에서 나왔고, **공식 모델 카드로 직접 확인한 사실**이다.

| 항목 | 확인 내용 | 출처 |
|---|---|---|
| 라이선스 | **Apache 2.0** — 상업적 사용 가능 | HF 모델 카드 |
| 한국어 | **공식 지원 10개 언어에 포함** | 모델 카드 Overview |
| 음색 지정 | **자연어 지시로 음색·감정·운율 제어** | `generate_voice_design(instruct=...)` |
| 모델 | `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` (1.7B) | HF |
| 설치 | `pip install qwen-tts` | 모델 카드 |
| 지연 | 스트리밍 97ms 주장 (**미검증**) | 모델 카드 |

**참조 음성이 필요 없다는 것이 핵심이다.** 원하는 음색을 문장으로 묘사하면 된다.
공식 예제의 지시문이 정확히 우리가 원하는 방향이다:

```
体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显
(어리고 앳된 여자아이 목소리, 음높이가 높고 억양 변화가 뚜렷하게)
```

이로써 **어제 걸림돌로 적었던 "참조 음성 확보와 권리 문제"가 사라진다.**

음색을 매번 똑같이 유지하려면 두 단계로 쓴다 — VoiceDesign 으로 참조 음성을
한 번 생성해 파일로 두고, 이후에는 `CustomVoice` 모델에 그 파일을 물린다.
(GitHub README 의 `design_model` → `ref_audio` 예제)

### 검증 결과 (2026-07-30 실측 — 전부 이 맥에서 직접 확인)

**결론: 채택 가능하다.** 음색·속도 모두 기준을 통과했다.

#### 1. transformers + MPS 는 실격이다

| 모델 | `'안녕하세요.'` 합성 | RTF |
|---|---|---|
| 1.7B VoiceDesign, float32 | 3.02s | 1.11 |
| 1.7B VoiceDesign, bfloat16 | 3.27s | 1.46 |
| 0.6B CustomVoice, float32 | 2.64s | 0.90 |

기준(1.2초)의 2배 이상이다. **모델을 줄여도 12% 밖에 안 준다** — 병목이 모델
크기가 아니라 MPS 자기회귀 생성이다. `qwen-tts` 패키지에 **진짜 스트리밍이 없다**
(소스 확인: `non_streaming_mode=False` 는 텍스트 입력을 흉내낼 뿐).

#### 2. GGUF + CrispASR 이 답이다 — 5.6배 빠르다

**순수 llama.cpp 로는 안 된다.** 러너는 [CrispASR](https://github.com/CrispStrobe/CrispASR)
(whisper.cpp 파생 포크)이고, **오디오 코덱 GGUF 가 별도로 반드시 필요하다**
(`qwen3-tts-tokenizer-12hz.gguf`, f16 342MB). 코덱은 양자화하지 말 것(문서 권고).

상주 서버 HTTP 왕복 실측(0.6B CustomVoice, `voice=ryan`):

| 문장 | 왕복 | 비교: `say` | 비교: MPS |
|---|---|---|---|
| `안녕하세요.` | **0.47s** | 0.51s | 2.64s |
| `좋아요, 보여드릴게요.` | **0.74s** | 0.51s | — |
| `오늘 기분이 아주 좋아요.` | **1.00s** | 0.51s | — |

서버 기동은 2초, 가중치를 mmap 하므로 모델 크기와 거의 무관하다.

---

## 채택 설정 (2026-07-30 확정) — ⚠ 폐기됨

> **이 절의 VoiceDesign 설정은 더 이상 쓰지 않는다.** 문장마다 음색이 달라지는
> 문제로 `2894bcc` 에서 **CustomVoice 화자 `serena`** 로 교체했다.
> 현재 설정과 실측치는 아래 [최종 채택 설정](#최종-채택-설정--customvoice-serena-2026-07-30-야간-재측정) 절을 보라.
> 이 절은 왜 옮겼는지의 기록으로 남긴다.

음색 후보 5종을 청취해 **3번(로봇친구) 계열**을 골랐고, 발화가 느린 문제를
지시문 수정으로 잡았다.

**모델**: `Qwen3-TTS-12Hz-1.7B-VoiceDesign` q8_0 + 코덱 f16
**지시문 (V3 — 상수로 고정할 것)**:

```
작은 데스크톱 로봇의 목소리. 어린아이처럼 높고 맑고 친근하다.
또박또박 빠르게 말하고 문장을 간결하게 끊는다.
```

**배속**: `speed = 1.2`

### 이 설정의 실측치

| | 원본 3번 지시문 | **V3 + 1.2배속** |
|---|---|---|
| 첫 절 `안녕하세요.` 왕복 | 1.19s | **0.69s** |
| 그 재생 길이 | 3.52s | **1.67s** |
| 긴 문장 왕복 | 1.93s | **1.39s** |
| 그 재생 길이 | 5.76s | **3.47s** |

첫 절 0.69초는 `say`(0.51초)와 실용상 동급이고 기준 1.2초 안이다.
`speed` 는 합성 후 리샘플러라 **합성 시간은 안 줄고 재생 길이만 준다**(음높이 상승).

### ⚠ 지시문의 속도 제어는 불안정하다 — CustomVoice 에도 해당한다

같은 "빠르게" 취지인데 표현에 따라 결과가 뒤집힌다. VoiceDesign 실측:

| 변형 | 오디오 길이 |
|---|---|
| V1 원본 | 5.76s |
| V2 "말이 빠르고 경쾌하며 말끝을 늘이지 않는다" | 6.08s ↑ |
| **V3 "또박또박 빠르게, 간결하게 끊는다"** | **4.40s** ↓ |
| V4 "군더더기 없이 짧게 말한다" | 7.44s ↑ |

**이 경고는 지금도 유효하다.** CustomVoice 는 지시문 없이 쓰지만
`instructions` 를 넣으면 **먹는다** — `TTS_QWEN_INSTRUCT` 는 죽은 설정이 아니다.
같은 문장에 `"밝고 씩씩하게 아주 빠르게"` 를 붙인 실측: **209882B → 91484B**
(오디오가 절반 이하로 줄었다). 즉 `QWEN_INSTRUCT` 를 채우면 **모든 문장의 길이와
운율이 바뀌고 `selfintro.SEEDS` 도 무효가 된다.** 손대려면 대본 전체를 다시 재라.

### 교체 작업 범위 — 전부 끝났다

`tts.py` 의 `Speaker._worker` 를 HTTP 호출로 바꾸고, `scripts/demo.sh` 에 TTS 서버
기동·헬스체크·예열을 넣는 것이 범위였다. 둘 다 완료됐다.

당시 "`group_by_voice()` 의 언어별 음성 선택은 재설계가 필요하다"고 적었는데
**재설계는 필요 없었다.** `speak_many` 가 qwen 경로에서 early-return 해 절마다 따로
보내므로 `group_by_voice()` 는 호출되지 않는다(`tts.Speaker.speak_many` 의 early-return).
`pick_voice` 결과는 `_qwen_synth` 가 무시하고 **say 폴백 음성 선택에만 쓰인다**
(`tts.Speaker._worker`) — 맞는
동작이다. 근거는 아래 [문자체계 커버리지](#문자체계-커버리지--한-목소리로-전부-읽는다) 절.

*(이 절의 재현 방법·남은 리스크는 아래 최종 절로 옮겼다 — 중복 제거)*

## 최종 채택 설정 — CustomVoice 'serena' (2026-07-30 야간 재측정)

앞의 GGUF 검증은 **0.6B CustomVoice / `ryan`** 과 **1.7B VoiceDesign** 으로 한 것이라
`tts.py` 가 실제로 쓰는 조합이 아니었다. 코드의 현재 설정 그대로 다시 측정했다.

**모델**: `cstr/qwen3-tts-1.7b-customvoice-GGUF` → `qwen3-tts-12hz-1.7b-customvoice-q8_0.gguf`
(1.9 GB) + 코덱 `qwen3-tts-tokenizer-12hz.gguf` (f16, 342 MB)
**백엔드 이름**: `qwen3-tts-1.7b-customvoice` · **화자**: `serena` (spk_id 3066) · **speed**: 1.2

`serena` 는 실재한다. 런타임이 찍는 화자 목록:
`aiden, dylan, eric, ono_anna, ryan, serena, sohee, uncle_fu, vivian` (9종).

### 실측치 — 지금까지 재본 조합 중 가장 빠르다

상주 서버 HTTP 왕복. 각 3회, 편차 ±10 ms.

| 문장 | 왕복(speed 1.0) | 왕복(**speed 1.2** = 프로덕션) | 재생 길이 | 순수 합성 |
|---|---|---|---|---|
| `안녕하세요.` | 0.33s | **0.36s** | 0.80s | 342 ms (RTF 0.36) |
| `좋아요, 보여드릴게요.` | 0.64s | **0.64s** | 1.60s | 649 ms |
| `오늘 기분이 아주 좋아요.` | 0.93s | **0.92s** | 2.33s | 952 ms |

콜드 스타트(기동 → `/health`) **0.48s**. `speed` 가 합성 시간을 바꾸지 않는다는
기존 결론도 재확인됐다(0.33 → 0.36s, 재생만 0.96 → 0.80s).

첫 절 **0.36초**는 기준(1.2초)의 3분의 1이고 `say`(0.51s)보다 빠르다.

| `안녕하세요.` 경로별 순수 합성 | | |
|---|---|---|
| MPS float32 1.7B VoiceDesign | 3.02s | ✗ |
| GGUF 1.7B VoiceDesign | 547 ms | ✓ |
| GGUF 0.6B CustomVoice / ryan | 455 ms | ✓ |
| **GGUF 1.7B CustomVoice / serena** | **342 ms** | **✓** |

serena 가 가장 빠른 건 모델이 작아서가 아니라 **발화가 짧아서**다(같은 문장 오디오
0.96s, ryan·VoiceDesign 은 1.6s). 생성할 코덱 프레임이 적다. RTF 자체는 거의 같다.

### 음색 드리프트가 없다 — `tts.QWEN_VOICE` 주석의 판단이 실측으로 확인됐다

`4844946` 에서 시드로 우회했던 문제의 재발 여부를 봤다.

- **같은 문장 5회, seed 미지정**: median F0·centroid·길이 전부 동일. **CV 0.0%**
- **같은 문장 3회, seed=42**: PCM 샘플 비교 **max|diff| = 0, 불일치 0/46080**

즉 **CustomVoice 는 주어진 텍스트에 대해 결정론적이다. 시드를 안 줘도 그렇다.**
`QWEN_VOICE="serena"` 로 옮긴 결정이 맞았다. (VoiceDesign 쪽의 비결정성은 이번에
따로 재보지 않았다 — `tts.py` 주석의 실경험을 반박하지도 확인하지도 않았다.)

대본 8절 사이 median F0 CV 는 9.4% (264–353 Hz, speed 1.2 기준)로 나오지만
**이건 드리프트가 아니라 정상 억양**이다. 근거: 같은 문장 반복은 편차가 정확히 0인데
다른 문장 사이에서만 벌어지고, 편차의 방향이 문형과 맞는다.

| 절 | 텍스트 | 길이 | medF0 | centroid |
|---|---|---|---|---|
| c01 | 안녕하세요. | 0.80s | 281 Hz | 2214 |
| c02 | 저는 리치 미니예요. | 1.87s | 312 Hz | 2425 |
| c03 | 오늘은 뭘 해볼까요? | 1.47s | **353 Hz** ← 최고(의문) | 1711 |
| c04 | 좋아요, 보여드릴게요. | 1.60s | 308 Hz | 1906 |
| c05 | 이렇게 고개를 돌릴 수 있어요. | 1.87s | 282 Hz | 1955 |
| c06 | 안테나도 움직여요. | 1.27s | **264 Hz** ← 최저(평서) | 1620 |
| c07 | 재미있죠? | 0.80s | 333 Hz | 2216 |
| c08 | 또 놀러 오세요. | 0.93s | 333 Hz | 1692 |

최고 3개가 의문문 2개(c03 353, c07 333)와 청유문(c08 333)이고 최저가 평서문(c06 264)이다.

**speed 1.2 는 리샘플러라 음높이를 함께 올린다** — 절 평균 F0 265 → 308 Hz (×1.16).
청취 판정은 반드시 speed 1.2 로 뽑은 것으로 해야 한다.

### 문자체계 커버리지 — 한 목소리로 전부 읽는다

**Yuna 와 성격이 다르다.** macOS 음성은 언어에 묶여 있어 영문·일문을 읽으면 발음이
깨진다 — `pick_voice()` / `group_by_voice()` 가 존재하는 이유다. serena 는
**다국어 모델 위의 화자 임베딩**이라 언어가 아니라 목소리만 지정한다.

10종 실측 (speed 1.2, ASR 역전사 병기):

| 종류 | 입력 | 왕복 | 역전사 |
|---|---|---|---|
| 한국어 | 안녕하세요, 반가워요. | 0.64s | ✓ |
| 순수 영문 | Hello, nice to meet you. | 0.69s | `Hello! Nice to meet you!` ✓ |
| 숫자 | 지금 3시 15분이고 2026년이에요. | 1.18s | 그대로 ✓ |
| 기호·단위 | 배터리가 85% 남았고 온도는 23도예요. | 1.19s | 그대로 ✓ |
| 일본어 | こんにちは、はじめまして。 | 0.64s | 그대로 ✓ |
| 중국어 | 你好，很高兴见到你。 | 0.59s | 그대로 ✓ |
| 이모지 | 정말 좋아요 😀 신나요! | 0.95s | 이모지는 **소리 없이 건너뛴다** (잡음 없음) ✓ |
| 긴 절 (45자) | 저는 작은 데스크톱 로봇이고… | 2.12s | 그대로 ✓ |

**→ 문자체계로 음성을 갈아탈 이유가 없다.** `pick_voice` 는 say 폴백용으로만 남는다.

#### 걸리는 것 — 고유명사 압축

`Reachy Mini` 가 뭉개진다. 표기·문맥을 바꿔도 마찬가지다:

| 입력 | ASR(ko) | ASR(en) |
|---|---|---|
| `Reachy Mini` (단독) | 리치 미니 | **Richie Minnie** ← 단독은 제대로 |
| `제 이름은 Reachy Mini 예요.` | 리지민 | Rijimin |
| `제 이름은 리치 미니예요.` | 리치민 | Rich Min |
| `My name is Reachy Mini.` | Rijimini | Rijiminny |

**언어 전환 실패가 아니다** — 전체 영문에서도, 한글 표기로도 똑같이 뭉개진다.
문장 안에 들어가면 두 단어가 붙어 압축된다. `LLM 을 씁니다.` → `LLM의 신문화` 로
받힌 사례도 있다.

**이게 TTS 발음 오류인지 whisper 오인식인지는 ASR 만으로 가릴 수 없다(미판정).**
`docs/samples/serena_propernoun_6cases.wav` 를 귀로 확인할 것.
Yuna 대비 퇴보는 아니다 — Yuna 도 한글이 섞인 절 전체를 읽으므로 같은 문제를 겪는다.

### 대본의 영어 고유명사 — 음차가 대부분 낫다 (A/B 실측)

serena 가 영문을 읽을 수 있으니 `selfintro.SCRIPT` 의 한글 음차 표기를 영문으로
바꿔봤다. **6개 중 2개만 영문이 낫고 4개는 악화된다.**

| 대상 | 음차 | 영문 | 판정 |
|---|---|---|---|
| Whisper | 위스퍼 라지 브이쓰리 터보 | `Whisper Large V3 Turbo` 역전사 정확 | **영문 채택** |
| Metal | 메탈 | `Metal` 역전사 동일, 0.13s 짧음 | **영문 채택** |
| Apple Silicon | 애플 실리콘 ✓ | 문장 안에서 `알퍼/에폰 실리콘` (2회 재현) | 음차 유지 |
| Gemma | 젬마 사 이사비 | **단독조차** `잠시 / how much` | 음차 유지 |
| Qwen | 큐원 쓰리 티티에스 | 단독 `퀀퀀 TPS`, 띄워도 `퀴산 TPS` | 음차 유지 |
| 4비트 | 사비트 → 역전사 `4비트` ✓ | **`셋 비트 / Set bit` — 숫자가 틀린다** | 음차 유지 |

`Apple Silicon` 은 **단독으로는 완벽**한데(`Apple Silicon` 그대로) 문장에 넣으면
깨진다 — 붙여쓰기·띄어쓰기 둘 다, 2회 반복 재현. 문장 내 임베딩이 문제다.

가장 위험한 건 `4비트` 다. 아라비아 숫자가 인접 한글과 섞여 **"삼비트"로 읽히고**,
같은 문장 뒤쪽의 `0.05초` 까지 `0.40여초` 로 오염됐다. 숫자 자체는 단독으로는
정확하므로(`첫 응답이 0.05초에 나와요.` ✓) 오염원은 `4비트` 다.

**→ 영문 표기는 한 단어씩 A/B 하고 ASR 로 되받은 뒤에만 바꾼다.** 근거와 함께
`selfintro.py` 의 `SCRIPT` 위 주석에 남겼다.

#### 대본 전체 회귀 (최종 상태, `SEEDS` 적용)

13문장 총 재생 **47.9초**, F0 mean 282.7 Hz / sd 15.5 Hz / **CV 5.5%**, F0 이상치 없음.
(시드를 안 쓴 임의 8절이 CV 9.4% 였으므로 `SEEDS` 고정이 실제로 듣고 있다.)

역전사 불일치 표시는 대부분 ASR 의 숫자 정규화다 — `사십억`→`40억`,
`여든다섯 가지`→`85가지`, `여섯 축`→`6축` 로 **내용은 정확하다.**
다만 6번 `젬마 사 이사비` 가 `젠마 423B` 로 받혔다 — 발음이 모호할 수 있어
`docs/samples/selfintro_english_final.wav` 에서 확인이 필요하다(미판정).

### 배포 자산에서 잡은 버그 2건 (2026-07-30)

`scripts/demo.sh` 를 실제로 태워보니 **시연이 조용히 유나 목소리로 돌아가고 있었다.**

#### 1. crispasr 바이너리의 rpath 가 삭제된 빌드 디렉토리를 가리킨다

`~/.local/share/reachy-mini-tts/crispasr-bin/` 로 바이너리와 dylib 을 함께 복사했지만
**rpath 를 안 고쳤다.** 4개 항목 전부 사라진 스크래치 빌드 경로를 가리킨다:

```
dyld[…]: Library not loaded: @rpath/libcrispasr.1.dylib
  Reason: tried: '…/scratchpad/gguf-test/CrispASR/build/src/libcrispasr.1.dylib' (no such file), …
```

증상이 고약하다 — 기동이 **조용히** 실패하고 헬스체크 시간초과 뒤 `say` 폴백으로
넘어간다. 로그를 열지 않으면 목소리가 바뀐 것만 보인다.

**`DYLD_LIBRARY_PATH` 로는 못 고친다.** macOS SIP 가 `nohup` 처럼 보호된 바이너리를
exec 할 때 `DYLD_*` 를 전부 지운다 — 직접 실행은 되고 `nohup` 경유만 실패해서
원인을 오해하기 쉽다(실제로 한 번 헤맸다).

해결: 바이너리에 `@loader_path` rpath 를 박아 dylib 을 자기 옆에서 찾게 한다.
`demo.sh` 의 `ensure_crispasr()` 가 기동 전에 검사하고 필요하면 자동으로 넣는다
(재배포로 rpath 가 되돌아가도 다시 고친다). rpath 를 지워 깨진 상태를 만들고
복구를 확인했다.

#### 2. 서버 기동 시 화자를 안 넘겨 기본값이 'aiden' 이었다

`demo.sh` 가 `--voice` 없이 띄우고 있었다. `tts.py` 는 요청마다 `voice: serena` 를
보내므로 정상 경로는 문제가 없지만, **voice 필드 없이 들어온 요청은 전부 `aiden`**
으로 나간다(실측: 같은 문장이 43482B vs 56280B). 기동 시에도 `--voice` 를 넘겨
서버 기본값을 코드와 일치시켰다. 화자 값은 `tts.QWEN_VOICE` 에서 읽어 단일 출처로 뒀다.

참고로 기동 경고 `--voice-dir not set; … will reject requests with a 'voice' field`
는 **오해를 부르는 문구다.** CustomVoice 화자 이름은 거부되지 않는다(HTTP 200,
로그에 `CustomVoice speaker = 'serena'`). 이 경고는 voice-dir 파일 조회에만 해당한다.

#### 배포 구성(0.6B + serena) 실측 — 처음 측정했다

앞의 수치는 전부 1.7B 기준이었다. 실제 배포된 0.6B CustomVoice + `serena`:

| 문장 | 왕복(speed 1.2) | 재생 |
|---|---|---|
| `안녕하세요.` | **0.40s** | 1.13s |
| `좋아요, 보여드릴게요.` | 0.62s | 1.87s |
| `오늘 기분이 아주 좋아요.` | 1.44s | 4.33s |

첫 절 0.40초로 기준을 통과한다. `serena` 는 0.6B 에도 있다(9화자 동일 목록).
셋째 문장이 1.7B(0.92s)보다 느린 건 0.6B 가 그 문장을 훨씬 길게 읽기 때문이다(4.33s vs 2.80s).

`models/` 에 `qwen3-tts-12hz-1.7b-voicedesign-q8_0.gguf`(2.0GB)와
`voices/mini-boy.wav` 가 남아 있다 — 폐기한 VoiceDesign 경로의 잔여물이고 쓰이지 않는다.

### 음질 — ASR 역전사 11/11

`whisper-large-v3-turbo`(MLX) 로 되받아 벤치 3문장 + 대본 8절 전부 일치.
고유명사 1건만 표기 차이(`저는 리치 미니예요.` → `저는 리치민이에요`) — whisper 쪽
정규화로 보이지만 **고유명사 발음은 귀로 확인할 대상이다.**

### Metal JIT 캐시는 모델 셰이프별이다 (기존 리스크 1 보강)

`~/Library/Caches/ggml-metal/Apple_M5_Pro.archive` 가 이미 있는 상태에서도
1.7B CustomVoice **첫 실행은 10.02초**였다(합성 자체는 539 ms).
0.6B 로 예열해둔 캐시가 1.7B 에는 쓸모없다.

→ **예열은 반드시 실제 서비스할 모델·화자로 해야 한다.** 아니면 첫 발화가 10초다.

### 커밋 고정은 선택이 아니다 (기존 리스크 2 보강)

같은 날 오전과 야간, 약 10시간 사이에 양쪽이 다 움직였다.

| | 오전 검증 | 야간 검증 |
|---|---|---|
| CrispASR | `9cde22b0b60a0d4b7d524c1186f7ab5dc6d1caa4` | `705e355bb12b7be2ff8dce99a74ff45ccfd16e0c` |
| ggml 포크 | `14b4971d3fe190ca817158d32c5be167dbe00af8` | `a0f7289df00020cf50200f970c9c3ec91107984c` |

### 워터마크 — 끌 수는 있으나 동의 게이트가 있다

출력에 AI 콘텐츠 워터마크 + C2PA 프로버넌스가 기본으로 붙는다. 같은 입력의 wav 들이
md5 는 다른데 **PCM 은 bit-identical** 이므로 차이는 C2PA 메타데이터(타임스탬프/UUID)
뿐이고 가청 영향은 없다(역전사 정상). 끄려면:

```
crispasr: error: --no-watermark requires --accept-marking-responsibility.
  Disabling AI-content provenance marking shifts the marking/disclosure
  duty to you, the operator.
```

고지 의무가 운영자로 이전되는 **정책 사안이라 켜지 않았다.** 판단이 필요하다.
합성 결과를 캐싱할 거면 wav 바이트가 매번 달라진다는 점만 감안하면 된다(키는 텍스트로).

### 재현

```bash
git clone https://github.com/CrispStrobe/CrispASR && cd CrispASR
git checkout 705e355bb12b7be2ff8dce99a74ff45ccfd16e0c        # 고정 필수
git submodule update --init --depth 1 ggml third_party/c2pa-audio   # 둘 다 필요
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON
cmake --build build -j 10 --target crispasr                  # 607 타깃, 약 1분

crispasr --server --port 8099 --backend qwen3-tts-1.7b-customvoice \
  -m qwen3-tts-12hz-1.7b-customvoice-q8_0.gguf \
  --codec-model qwen3-tts-tokenizer-12hz.gguf --voice serena
```

`response_format: "pcm"` 을 쓰면 헤더 없는 raw s16 24 kHz 가 와서
`35ad172` 의 상주 오디오 스트림에 그대로 흘려넣을 수 있다(왕복 0.33s 확인).

### ⚠ 1.7B 로 잰 수치는 배포된 0.6B 에 그대로 옮겨지지 않는다

이 문서의 앞부분 수치는 대부분 **1.7B CustomVoice** 기준이고, 실제 배포는
**0.6B** 다(`demo.sh` 의 `TTS_MODEL`). 같은 대본을 두 모델로 돌려보니 차이가 컸다.

| | 1.7B | 배포된 0.6B |
|---|---|---|
| 대본 13문장 총 재생 | 50.4s | **56.9s** |
| 3번 문장 | 3.87s | **5.33s** |
| `Whisper Large V3 Turbo` 역전사 | 정확 | '위스퍼올라즈 V3 터보' |
| `Alibaba 의 Qwen3-TTS` | '알리바바의 QN3TTS' | '아리바바의 QSPTS' |

**그리고 시드가 모델에 종속된다 — 여기서 사고가 났다.** 1.7B 에서 고른
`SEEDS[11] = 2` 를 0.6B 에 그대로 뒀더니 11번 문장이 3.4초가 아니라 **10.07초로
늘고 뒤에 환각 발화가 붙었다** — "흥, 계곡 아대티에 떠나싸며. 그 시녀이, 난
가사니라지야." 그 시드에서만 재현됐고(다른 6개 시드는 전부 정상 3.3초 내외),
경영진 앞에서 헛소리가 나갈 수 있었다.

**조치**: 13문장 × 시드 7종을 배포 모델로 전수 합성해 재선정했다. 선택 기준을
①길이 이상치 배제 → ②ASR 일치 → ③F0 근접 순으로 두어 환각을 구조적으로 걸러낸다
(1·6·11번에서 실제로 걸러졌다). 결과 **F0 CV 6.4% → 2.1%**.

품질만 보면 1.7B 가 낫다(2.0 GB). 올릴지는 판단이 필요하고, 올린다면 **시드를
다시 전수 재선정해야 한다.**

### 배포 환경 (2026-07-30 정리 후)

`~/.local/share/reachy-mini-tts/` — **talker 를 1.7B 로 올리고 VoiceDesign 을 지웠다.**

| | 크기 | |
|---|---|---|
| `crispasr-bin/` (바이너리 + dylib) | 45 MB | **쓴다** |
| `models/qwen3-tts-12hz-1.7b-customvoice-q8_0.gguf` | 1.9 GB | **쓴다** (채택) |
| `models/qwen3-tts-tokenizer-12hz.gguf` | 342 MB | **쓴다** (f16 유지 필수) |
| `models/qwen3-tts-12hz-0.6b-customvoice-q8_0.gguf` | 923 MB | 폴백/비교용으로 남김 |
| ~~`models/…-1.7b-voicedesign-q8_0.gguf`~~ | ~~1.9 GB~~ | **삭제됨** — 폐기한 경로 |
| `models/tok/` | 619 MB | 코덱 저장소 통째 다운로드 잔여(다른 quant) |
| `voices/mini-boy.wav` | 156 KB | VoiceDesign 시도 잔여. **지우지 말 것** — 커스텀 음색 베이킹의 참조 후보다(3.27초 24 kHz, 대사 "저는 인터넷에 연결되어 있지 않아요." STT 로 확인). 위 [향후 계획](#향후-계획--커스텀-음색을-만들려면) 참고 |
| `bin/`, `models/.cache/` | 0 B, 16 KB | 빈 디렉토리 |

`demo.sh` 는 1.7B + 코덱 + 바이너리만 참조한다. 0.6B 를 지우면 실사용은 2.3 GB 다.
`models/tok/` 619 MB 도 지울 수 있다(같은 코덱의 다른 quant 뿐).

**백엔드 이름이 모델 크기에 종속된다** — 0.6B 는 `qwen3-tts-customvoice`,
1.7B 는 `qwen3-tts-1.7b-customvoice`. 모델만 바꾸고 이걸 안 바꾸면 기동이 깨지므로
`demo.sh` 가 파일명에서 유추한다(`TTS_QWEN_BACKEND` 로 재정의 가능).

#### 새 기계에 배포할 때 필요한 것

1. `crispasr` 바이너리 + `crispasr-bin/` 의 dylib 전부 (같은 디렉토리에)
2. talker `0.6b-customvoice-q8_0.gguf` + 코덱 `tokenizer-12hz.gguf` (f16)
3. **rpath 확인** — 빌드 디렉토리에서 복사해 오면 `@rpath` 가 깨진다.
   `demo.sh` 의 `ensure_crispasr()` 가 `@loader_path` 를 자동으로 넣지만,
   `install_name_tool -add_rpath "@loader_path" crispasr` 를 배포 시점에 해두면 깔끔하다
4. 첫 기동 후 **예열 1회 필수** — Metal JIT 캐시(`~/Library/Caches/ggml-metal/`)는
   기계·모델별이라 새 기계에서는 다시 컴파일된다(실측 8.5~10.0초)

## `serena` 는 내장 화자다 — 우리가 만든 음색이 아니다 (2026-07-30 확인)

질문이 나와 확인했다. 런타임이 직접 밝힌다:

```
qwen3_tts: selected CustomVoice speaker 'serena' (spk_id=3066)
crispasr[qwen3-tts]: CustomVoice speaker = 'serena'
  (available: aiden, dylan, eric, ono_anna, ryan, serena, sohee, uncle_fu, vivian)
```

`spk_id=3066` 은 **모델 가중치에 학습돼 있는 화자 임베딩**이다. 9명 중 이름으로
골라 쓴 것뿐이고, `tts.py` 는 `{"voice": "serena"}` 라는 **문자열만** 보낸다 —
참조 음성을 쓰는 경로가 코드에 없다.

**그래서 "음색을 생성한 로직" 은 존재하지 않는다.** 뽑아낼 것이 없다.
`selfintro.py` 9번 문장이 한때 "원하는 목소리를 문장으로 설명해서 만든 음색"
이라고 읽던 것이 사실과 달랐던 이유가 이것이다(정정 완료).

### 향후 계획 — 커스텀 음색을 만들려면

**하지 않기로 했다. 필요해지면 이 절대로 진행한다.**

CrispASR 에 도구가 있다 — `models/bake-qwen3-tts-voice-pack.py`.

```
참조 WAV(3~15초) + 정확한 대사
   ↓ ECAPA-TDNN 화자 인코더  → ref_spk_embedding (1024-d float32)
   ↓ 12 Hz RVQ 코덱 인코더    → ref_code (T×16 int32)
   ↓
voice-pack.gguf  →  qwen3-tts **Base** 백엔드 + `--voice my-voice.gguf`
```

**핵심 제약: CustomVoice 는 화자 이름만 받는다.** 커스텀 음색을 쓰려면
**Base 모델로 갈아타야 한다** — 지금 안정화해 둔 경로가 아니다.

| 필요한 것 | 현재 | 비용 |
|---|---|---|
| Base 모델 | 없음 | 0.6B ~1.3 GB / 1.7B ~2.07 GB 추가 다운로드 |
| `qwen-tts`, `transformers` | 없음 | **베이킹 시에만** 필요(합성 시엔 불필요) |
| `torch` | 있음 | |
| 참조 WAV | `voices/mini-boy.wav` 하나 있음 | 아래 참고 |

참조 음성을 얻는 세 갈래: ① 기존 `mini-boy.wav` 재사용 ② VoiceDesign 으로 새로
생성(지운 1.9 GB 재다운로드) ③ 실제 사람 녹음(권리 문제 — CrispASR 에
`--i-have-rights` 게이트가 있다).

> ⚠ **가장 큰 위험은 재측정이다.** 지금 TTS 는 1.7B CustomVoice/serena 기준으로
> 시드 12개·모델명 표기·지연을 전부 맞춰 놓은 상태다. Base + 보이스팩으로 옮기면
> **그게 전부 무효가 된다** — 시드가 모델에 종속된다는 것은 이번에 사고로 확인했다
> (11번 문장 환각). 옮긴다면 보이스팩을 **별도 백엔드로 붙이고 환경변수로 전환**해
> 기존 경로를 건드리지 않는 편이 안전하다.

### 미측정

- **음색의 주관적 품질** — `docs/samples/selfintro_english_final.wav` 를 들어야 한다
- VoiceDesign 의 비결정성 재현 (`tts.QWEN_VOICE` 주석의 실경험)
- 로봇 데몬 동시 실행 시 GPU 경합 하의 지연
- 절이 200 코덱 프레임(~600자) 한계에 가까울 때의 거동
- 대안 러너 3종, `CRISPASR_QWEN3_TTS_O15` 등 최적화 스위치

## 교체 방법 (음색이 정해지면)

코드 변경은 작다.

- 한국어 음성만 바꾸는 경우: `REACHY_VOICE` 환경변수. 예)
  `REACHY_VOICE="Rocko (한국어(한국))" ./scripts/demo.sh`
  (Yuna 외에는 `"이름 (한국어(한국))"` 전체 이름이라야 로케일이 맞는다)
- 엔진 자체를 바꾸는 경우: `apps/voice_chat/voice_chat/tts.py` 의 `Speaker._worker`
  안 `subprocess.run` 만 교체한다. 나머지 코드는 `speak(text)` 만 쓴다.
- **신경망 TTS 는 반드시 상주 서버로 띄운다.** 발화마다 모델을 올리면 지연이 무너진다.
  `stt_server.py` 가 같은 패턴의 참고 구현이다.

### 실기 배포 시 TTS 를 어디에 둘까 (2026-07-30 결론)

**PC(맥)에 둔다.** `say` 를 버릴 필요가 없다 — 운영 토폴로지에서 PC 가 이미 맥이고
LLM·STT 를 거기서 돌리므로, TTS 도 같은 자리에서 HTTP 서버로 감싸면 된다.

실측한 전송 비용:

| 발화 길이 | 합성 | WAV 크기 | WiFi 전송(100Mbps) |
|---|---|---|---|
| 4.0초 | 0.58s | 174KB | 14ms |
| 6.4초 | 0.53s | 281KB | 23ms |
| 7.4초 | 0.56s | 324KB | 27ms |

**합성 시간이 안 바뀌고 전송 25ms 만 늘어난다.** 마이크는 연속 스트림이라 지터에
취약하지만 TTS 는 발화당 파일 하나라 한 번에 던지고 끝나므로 성격이 다르다.

이 배치의 부수 이점: 나중에 Qwen3-TTS 로 바꿔도 **배포 구조가 안 바뀐다.**
1.7B 모델은 Pi5 에 무리이므로 어차피 PC 에서 돌려야 한다.

전제: **운영 PC 가 맥이어야 한다.** 윈도우면 `say` 가 없어 그때 엔진을 바꿔야 하는데,
Pi5 가 아니라 PC 라 성능 여유는 크다.

### 수용 기준

현재 예산은 `VAD 0.70 + STT 0.25 + LLM 첫문장 0.17~0.55 + TTS 합성` 이다.

| TTS 합성 | 첫 오디오 | 판정 |
|---|---|---|
| ~0.9s (현재 `say`) | 2.0~2.35s | 기준선 |
| ≤1.2s | ~2.4~2.7s | 수용 가능 |
| ≥2.0s | 3.2s+ | 부적합 — 스트리밍 합성이 필요하다 |
