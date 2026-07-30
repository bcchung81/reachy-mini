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

## 채택 설정 (2026-07-30 확정)

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

### ⚠ 지시문의 속도 제어는 불안정하다

같은 "빠르게" 취지인데 표현에 따라 결과가 뒤집힌다. 실측:

| 변형 | 오디오 길이 |
|---|---|
| V1 원본 | 5.76s |
| V2 "말이 빠르고 경쾌하며 말끝을 늘이지 않는다" | 6.08s ↑ |
| **V3 "또박또박 빠르게, 간결하게 끊는다"** | **4.40s** ↓ |
| V4 "군더더기 없이 짧게 말한다" | 7.44s ↑ |

**지시문을 코드 상수로 고정하고, 손댈 때마다 길이를 다시 재라.**

### 재현 방법

```bash
# 빌드 (cmake 가 이 맥에 없어 pip 로 넣었다. --recursive 없이 clone 하면 configure 실패)
git clone --recursive https://github.com/CrispStrobe/CrispASR
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON
cmake --build build -j 10 --target crispasr

# 서버 기동
crispasr --server --port 8099 --backend qwen3-tts-1.7b-voicedesign \
  -m qwen3-tts-12hz-1.7b-voicedesign-q8_0.gguf \
  --codec-model qwen3-tts-tokenizer-12hz.gguf

# 호출 (OpenAI 호환)
POST /v1/audio/speech  {"input": "...", "instructions": "<V3>", "speed": 1.2}
```

CLI 로 쓸 때의 플래그는 `--tts` / `--tts-output` / `--codec-model` / `--instruct` 다.

### 남은 리스크

1. **첫 실행 Metal 커널 JIT 약 8.5초** — 기동 시 예열 요청을 반드시 한 번 보낸다
   (`scripts/warmup.py` 에 STT·LLM 과 같이 넣으면 된다).
2. **단일 메인테이너 포크 의존** — CrispASR 은 mainline 이 아니다. 채택하면
   **커밋을 고정**할 것. 검증 커밋 `9cde22b0b60a0d4b7d524c1186f7ab5dc6d1caa4` (v0.8.24).
3. **진짜 스트리밍 없음** (`docs/server.md:508` Pending). 우리 앱은 이미 절 단위로
   끊어 보내므로 그 파이프라이닝으로 우회된다.
4. 대안 러너 3종(HaujetZhao/Qwen3-TTS-GGUF, Danmoreng/qwen3-tts-cpp,
   hans00 GGUF)은 **미측정**. CrispASR 로 기준을 통과해 파보지 않았다.

### 교체 작업 범위 (시연 이후)

`tts.py` 의 `Speaker._worker` 안 `subprocess.run(["say", ...])` 를 HTTP 호출로
바꾸는 것이 전부다. `speak()` / `speak_many()` 인터페이스는 그대로 두면 된다.
`group_by_voice()` 의 언어별 음성 선택은 **재설계가 필요하다** — Qwen3-TTS 는
언어를 지시문/입력으로 처리하므로 macOS 음성 이름 매핑이 의미가 없어진다.
`scripts/demo.sh` 에 TTS 서버 기동·헬스체크·예열을 추가한다.

### 대안

- **CosyVoice2**(Apache 2.0) — 3~5초 참조 음성으로 복제. 참조 음성이 필요해
  VoiceDesign 보다 번거롭다.
- 상용 API(ElevenLabs·Typecast·네이버 클로바) — 캐릭터 음성이 풍부하지만
  **"전 구간 로컬" 이라는 설득 포인트가 깨진다.** 채택 시 그 대가를 명시할 것.

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
