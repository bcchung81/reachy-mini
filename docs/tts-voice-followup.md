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

기성 한국어 TTS에는 애니메이션 캐릭터 음색이 없다. **voice cloning 이 필요하다.**

## 후속 과제

1. **참조 음성 확보가 선결 조건이다.** 3~10초짜리 원하는 음색 샘플이 있어야 한다.
   실제 성우 목소리를 복제해 사내에 쓰는 것은 권리 문제가 생길 수 있으니
   출처를 먼저 정리한다.
2. 후보: **CosyVoice2**(Apache 2.0, 3~5초 복제, 감정 태그) 또는 GPT-SoVITS.
   둘 다 설치가 무겁고 macOS 실행 사례가 불확실하다 — 여유 있을 때 검증한다.
3. 상용 API(Typecast·네이버 클로바·수퍼톤)는 캐릭터 음성을 기본 제공하지만
   **"전 구간 로컬" 이라는 설득 포인트가 깨진다.** 채택 시 그 트레이드오프를 명시할 것.

## 교체 방법 (음색이 정해지면)

코드 변경은 작다.

- 한국어 음성만 바꾸는 경우: `REACHY_VOICE` 환경변수. 예)
  `REACHY_VOICE="Rocko (한국어(한국))" ./scripts/demo.sh`
  (Yuna 외에는 `"이름 (한국어(한국))"` 전체 이름이라야 로케일이 맞는다)
- 엔진 자체를 바꾸는 경우: `apps/voice_chat/voice_chat/tts.py` 의 `Speaker._worker`
  안 `subprocess.run` 만 교체한다. 나머지 코드는 `speak(text)` 만 쓴다.
- **신경망 TTS 는 반드시 상주 서버로 띄운다.** 발화마다 모델을 올리면 지연이 무너진다.
  `stt_server.py` 가 같은 패턴의 참고 구현이다.

### 수용 기준

현재 예산은 `VAD 0.70 + STT 0.25 + LLM 첫문장 0.17~0.55 + TTS 합성` 이다.

| TTS 합성 | 첫 오디오 | 판정 |
|---|---|---|
| ~0.9s (현재 `say`) | 2.0~2.35s | 기준선 |
| ≤1.2s | ~2.4~2.7s | 수용 가능 |
| ≥2.0s | 3.2s+ | 부적합 — 스트리밍 합성이 필요하다 |
