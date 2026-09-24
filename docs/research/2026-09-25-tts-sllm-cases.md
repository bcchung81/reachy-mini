# TTS·sLLM 실사용 사례와 이 프로덕션의 대조 (2026-09-25)

조사 도구: ego-lite 브라우저(차단 페이지 포함) + 웹 검색. 수치는 **출처가 적은 그대로**이고, 우리 환경에서
재지 않은 것은 "미검증" 으로 둔다.

## 우리 스택 (확인)

| 층 | 지금 | 근거 |
|---|---|---|
| LLM | llama-server · `gemma-4-E4B-it Q4_K_M` · `--reasoning off` · 관람객 질문 답에만 | `docs/latency-m0.md`, `reachy.sh` |
| STT | `mlx-whisper large-v3-turbo`(:8090) | `stt_server.py` |
| TTS | CrispASR 서버 · `Qwen3-TTS 12Hz 1.7B CustomVoice Q8_0 GGUF` · 화자 serena/sohee · 청크 PCM 스트리밍 | `reachy.sh` |
| 해설 | 사람이 검수한 고정 대본(19큐×4수준), 생성 없음 | 커밋 c78363d |
| 로봇 | Reachy Mini Wireless 2대, 앱은 로봇·추론은 PC | CLAUDE.md |

## 외부 사례 — 확인한 사실

| # | 사례 | 요지 | 출처 |
|---|---|---|---|
| 1 | Hugging Face "Reachy Mini goes fully local"(2026) | 공식 로컬 스택 = Silero VAD v5 → Parakeet-TDT 0.6B v3(영어 강점) → **llama.cpp + Gemma 4** → **Qwen3-TTS**. 병목은 LLM 추론이라고만 하고 지연 수치는 없다 | [HF 블로그](https://huggingface.co/blog/local-reachy-mini-conversation) |
| 2 | Reachy Mini 두뇌 조사(hermes-body, 2026-05) | 커뮤니티 표준: 모션은 HF 감정·춤 라이브러리를 데이터로, **툴 호출이 오디오를 막지 않는다**, 1차 동작+발화 흔들림 레이어 합성. 로컬 앱 종단 지연 < 2.5~3초 | [보고서](https://github.com/The-Focus-AI/hermes-body/blob/main/reports/2026-05-04-reachy-mini-llm-brains.md) |
| 3 | Qwen3-TTS 스트리밍 토론 | 모델 카드의 97ms 스트리밍은 공식 파이썬 도구로 안 되고, 직접 구현자는 **음색 흔들림 때문에 첫 ~3초(38토큰)를 버퍼링** | [HF 토론](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base/discussions/4) |
| 4 | 한국어 TTS CPU 비교(korean-voice, 2026-09-12) | Qwen3-TTS 0.6B CustomVoice **sohee**: RTF 4.07, 의미 CER 6.1%, 적재 22.9초, 5.7GB / Supertonic u5: RTF 0.42, CER 3.3%, 0.6초, 0.58GB → **Qwen 은 실시간이 아닌 '굽기(bake)' 후보로만.** 같은 대본은 결과 캐시에서 즉시, 합성 전 정규화(범위 `~`·소수·퍼센트·기호) | [PR #57](https://github.com/quddnr0107-lgtm/korean-voice/pull/57), 저장소 README |
| 5 | Supertonic 3(Supertone) | 약 99M 파라미터 ONNX, 한국어 포함 31개 언어, 온디바이스, 모델 OpenRAIL-M. 기본은 고정 프리셋 음색 | [모델 카드](https://huggingface.co/Supertone/supertonic-3) |
| 6 | 서울 박물관 3곳 sLLM 도슨트(MDPI Applied Sciences 2025) | Gemma2-9B LoRA + FAISS RAG(해설 19.9만·QA 10.2만, **8개 페르소나**), 정확도 85.55%. TTS 는 클라우드(Clova·OpenAI)에 **고유명사·전문용어 발음 사전**, STT 는 소음 전처리. 110명 만족 4.24/5. 한계: 배경지식이 부족하면 충실도 저하 | [논문](https://www.mdpi.com/2076-3417/15/17/9398) |
| 7 | 국립현대미술관 로봇 가이드 vs 앱(1,705명, 2025) | 로봇 이용자 **59.4% 가 몇 작품만** 들었다. 체화 인터페이스는 주의를 끌지만 인지 부담도 준다. 소음 속 **음성 상호작용이 최대 난점**. 앱+로봇 병행이 만족 최고. 기술의 새로움보다 **내용의 질·명료성** | [Museum Management and Curatorship](https://www.tandfonline.com/doi/full/10.1080/09647775.2025.2562849) |

## 대조 — 이미 사례와 같은 것

- 모션을 데이터 라이브러리로(감정 85 + 춤 19), 오디오 비차단, 단일 쓰기 스레드 레이어 합성(`driver.py`).
- LLM 생각 모드 끔. 해설은 고정 대본 — 사례 6(RAG 생성)보다 보수적이고 환각 원천이 없다.
- 수준별 설명(4수준) — 사례 6 의 페르소나와 같은 발상.
- STT 는 한국어에서 Whisper 가 맞다(사례 1 의 Parakeet 은 영어 강점).

## 갭과 조치

| 갭 | 조치 | 상태 |
|---|---|---|
| 생성 답에 합성 전 정규화 없음, 고정 대본에 `~` | `speech_text.speakable`, 데이터 테스트에 `~`·`%`·`/` | **반영(2026-09-25)** |
| 질문 답 근거가 지금 섹션 하나 | 2-gram·IDF 색인으로 되물은 섹션 하나를 근거에(`stage/retrieval.py`) | **반영** |
| 공연 끝 되감기 없음 | 마이크 닫고 첫 큐로 | **반영** |
| **TTS 결과 캐시·사전 굽기 없음** — 사례 4 는 Qwen 을 굽기 전용으로 쓴다. 우리는 고정 259줄을 공연마다 1.7B 로 실시간 합성(`tts.log` RTF 0.49~0.94) | PC 쪽 캐시 프록시 + 예열 굽기 + 청취 검수. 캐시 키는 로봇 요청 본문과 바이트 동일해야 한다 | 제안 — 계획 승인 필요 |
| 발음 사전 없음(사례 6) | 청취 검수로 오독 목록(루노호트·QST·소수점 주파수 등) → 대본 표기 수정 또는 치환 사전 | 제안 — 청취 먼저 |
| 공연 20~27분, 로봇 이용자는 일부만 듣는다(사례 7) | 코스(하이라이트) + 관람객용 보조 화면(사례 7 의 병행 효과) | 설계 과제 |
| 소음 속 음성 상호작용(사례 7) | 잡음 게이트(반영됨) 다음 단계: 질문 창 VAD 온셋 신호 | 로봇 재배포 필요 |
| 실시간 TTS 대안 | Supertonic 3 을 관람객 답(생성) 전용 빠른 경로로 — 한국어 음색·라이선스·로봇 목소리 일관성 청취 필요 | 미검증, 실험 후보 |
