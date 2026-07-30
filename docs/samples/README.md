# 음성 청취 샘플

`docs/tts-voice-followup.md` 와 `apps/voice_chat/selfintro-script.md` 에서 참조한다.
전부 **Qwen3-TTS CustomVoice 화자 `serena`, `speed=1.2`** — 프로덕션과 같은 조건이다.
절 단위로 개별 합성해 이어붙였다(앱이 재생하는 형태).

| 파일 | 길이 | 무엇을 검증하나 |
|---|---|---|
| `selfintro_english_final.wav` | 50.4s | **`selfintro.SCRIPT` 최종 상태 전문.** 음색 판정과 모델명 발음 확인 |
| `serena_multilingual_10cases.wav` | 29.2s | 한국어·영문·혼합·약어·숫자·기호·일본어·중국어·이모지·긴절 (케이스 간 450ms) |
| `serena_propernoun_6cases.wav` | 12.0s | `Reachy Mini` 표기·문맥 6종 — 고유명사 압축 확인 |

들을 때 볼 것:

1. **어린이·캐릭터 톤인가** — 이게 `say -v Yuna` 를 버린 유일한 이유다
2. 절 사이 음색이 유지되는가 (실측상 같은 텍스트는 bit-identical, 절 간 F0 차이는 억양)
3. **모델명 발음** — `Whisper Large V3 Turbo` / `Apple Silicon` / `Gemma four E4B` /
   `4-bit` / `Alibaba 의 Qwen3-TTS` / `Metal`. 특히 Qwen 은 어떤 표기로도 깨끗하지
   않아 '알리바바의 QN3 TTS' 로 들린다 — 되돌릴지 판단이 필요하다
4. 기존 `say -v Yuna` 와의 A/B

재생성: TTS 서버를 띄우고 `POST /v1/audio/speech` 에
`{"input": "…", "voice": "serena", "speed": 1.2}` 로 절마다 요청해 이어붙인다.
