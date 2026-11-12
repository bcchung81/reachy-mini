# OpenAI LLM·STT 실측 — 로봇 대화를 옮겨도 되는가, 어떤 모델로 (측정 계획)

2026-11-12. 병렬 작업자 B1. 근거: `docs/handoff/2026-11-12-after-elevenlabs-subscription.md` A7 · `docs/handoff/2026-11-10-frontier-ai-transition.md` §3·§6.
**제품 코드는 건드리지 않는다** — 측정 도구 두 개와 결과 보고만 만든다. 결과는 B2(게이트웨이)의 기본값이 된다.

## 확인한 사실 (착수 전, 2026-11-12)

| 사실 | 값 | 어떻게 |
|---|---|---|
| 계정 모델 | `gpt-6-luna`·`gpt-6-sol`·`gpt-6.1-sol`·`gpt-6.1-terra`·`gpt-6-astra`·`gpt-transcribe` 모두 있음(목록 96개) | `GET /v1/models` |
| LLM 가격(표준, 100만 토큰당 입력/캐시 입력/출력) | luna $0.10/$0.01/$0.50 · 6-sol $2/$0.20/$10 · 6.1-sol $2/$0.10/$10 · 6.1-terra $1/$0.05/$5 · astra $10/$1/$50 | developers.openai.com/api/docs/pricing |
| 사고 끄기(`reasoning_effort:"none"`) | **가능**: luna·6-sol·6.1-terra. **불가**: 6.1-sol(최저 `low`, 기본 medium) · astra(`none` 이면 400). 기본값은 모두 medium — 안 보내면 사고한다 | 모델 페이지·reasoning 가이드 |
| STT | `gpt-transcribe` 분당 $0.0045. **`language` 대신 `languages` 배열**(`-F languages[]=ko`), 둘 다 보내면 거절. 응답에 `languages:[{code}]`. `prompt`·`keywords` 지원. whisper-1·gpt-4o(-mini)-transcribe 는 2027-02-26 종료 | speech-to-text 가이드 |
| 로컬 LLM | `llamactl reach-llm` = `llama-server -hf unsloth/gemma-4-E4B-it-GGUF:Q4_K_M -ngl 99 --ctx-size 24576 --parallel 3 --no-kv-unified --reasoning off`. 모델은 HF 캐시에 있음, 서버는 꺼져 있음 | `~/workspace/llamactl.sh` |
| 로컬 STT | `stt_server.py`(mlx-whisper large-v3-turbo), 앱은 `language=auto`(기본) 로 16 kHz WAV 를 보낸다 | `apps/voice_chat/voice_chat/stt.py` |
| 실제 관람객 질문 | 로그(`.demo-logs/*.log`) 의 사용자 발화 70여 줄은 **전부 개발자 시험 발화**("대본", "너는 누구야?", "오늘 날씨는 어때?" 등) — 전시 질문 0개 | `나(STT…)>` 줄 집계 |
| 실제 관람객 녹음 | 없음(`docs/samples/*.wav` 3개는 로봇 TTS 샘플) | `find` |

## 무엇을 재나

### LLM — `scripts/measure_openai_llm.py`
- **질문 30개**: 실제 질문이 없으므로 큐시트 19섹션 주제로 만든 질문 + `tests/test_stage_retrieval.py` 의 개발자 작성 질문. 모든 질문에 출처 표지(`합성`/`테스트예시`)를 단다. 각 질문은 "그 섹션이 진행 중일 때 들어온 질문"(`cue_id`)이다. 단독 모드는 재지 않는다(팟캐스트 질문 답이 주 경로).
- **프롬프트는 앱 경로 그대로**: 시스템 = `stage.prompts.build_system_prompt("docent", level)`, 지시문 = 실제 큐시트로 띄운 `Director._answer()` 가 만든 브리프(감독을 띄워 생성 콜백에서 가로챈다). 이력은 그 큐의 고정 대사(사회자 오프닝·턴 질문·도슨트 설명·받아치기)를 `_remember` 로 미리 쌓아 실제 공연과 비슷하게 한다. 메시지 조립은 `history_for` + `build_generate` 의 "끝의 user 를 지시문 앞으로" 규칙. 요청 본문은 `LLMClient.chat_stream` 과 같은 필드(`temperature 0.7`, `max_tokens = level.max_tokens`, `stream`)에 OpenAI 만 `reasoning_effort` 를 더한다. **OpenAI 가 `max_tokens`·`temperature` 를 거절하면 그 오류문을 기록**하고 `max_completion_tokens` 로 바꿔 재시도한다 — 게이트웨이(B2)가 번역해야 할 항목이다.
- **후처리도 앱 그대로**: `build_generate` 와 같은 순서(`strip_speaker_labels` → `cap_length` → `speakable` → `written_endings`)로 돌리고 각 단계의 발동을 센다.
- **잰다**: 첫 글자 지연(TTFT)·전체 지연(스트리밍, 한국 PC 에서), 답 길이(원문·잘린 뒤), 토큰 사용량(OpenAI `stream_options.include_usage`), 규칙 위반.
- **규칙 검사**(저장소 함수 재사용): 분량 상한 초과(`cap_length`), 하한 미달(`level.min_chars` — 감독의 `_warn_if_short` 와 같은 기준), 이름표, 기호(`speakable`), 글말(`written_endings`). 수준 규칙: 초등 = 숫자(아라비아 숫자, 교육자료 검증기 `scripts/handout_hud/cards.py` 의 초등 규칙과 같은 판정) + 영문 약어(전문 용어 대용 지표) · 중고등 = 연도 아닌 숫자. 모든 수준: **근거에 없는 숫자**(답의 숫자 ⊄ 브리프+이력의 숫자 — 지어낸 수치 의심). 사람이 볼 나란히 표(모델 순서를 섞은 블라인드 HTML)를 저장소 밖에 만든다.
- **비교 대상**: 로컬 Gemma 4 E4B(임시 포트 18080 에 같은 옵션으로 단독 기동, 끝나면 끈다) vs `gpt-6-luna`(none). 수준마다 예열 호출은 통계에서 뺀다(로컬은 슬롯 3개를 채우게 3번).
- **전문가 상위 모델**: 사고를 끌 수 있는 것 중 글쓰기 위주·저가인 `gpt-6.1-terra`(none) 와, 최상위급 중 사고를 최소로 줄인 `gpt-6.1-sol`(low) 두 개만 전문가 질문 30개로 잰다. `low` 는 사고 토큰이 상한을 먹으므로 상한을 넉넉히 주고 사고 토큰 수를 기록한다(게이트웨이 상한 설계 근거).

### STT — `scripts/measure_openai_stt.py`
- **시험 세트**: 관람객 질문 문장(LLM 질문에서 고름) × ElevenLabs 목소리 6개(라이브러리 한국어 중 **어린 목소리 2개 이상** — `GET /v1/shared-voices` 의 age·설명으로 고른다, 성인 남녀, 나이 든 목소리) → `eleven_v4_turbo` `pcm_24000` → **16 kHz 모노 16-bit** 로 내려 로봇 입력과 맞춘다(앞뒤 무음 0.3초, 음량 정규화). 조건 두 가지: 깨끗함 · 잡음 섞음(SNR 15 dB 분홍 잡음 — 전시장 대용). **무음·잡음만 있는 조각**도 넣어 환각을 본다.
- **비교**: 로컬 `stt_server.py`(임시 포트 18090, 같은 모델) `language=auto`(앱 기본)·`ko` vs `gpt-transcribe` `languages` 없음·`languages[]=ko`.
- **잰다**: CER(띄어쓰기·문장부호 무시, 숫자·단위는 `scripts/tts_review.py::spoken` 으로 읽는 소리로 편 뒤 글자 편집 거리) · 발음 CER(`phonetic`) · 지연(요청~응답) · 환각(무음에 글자가 나오나). 목소리별(어린 목소리 따로)·조건별로 나눈다.

## 비용 상한과 지키는 법
- OpenAI **$3**: 두 스크립트 모두 `--dry-run`(호출 없이 질문 수·예상 비용)을 먼저 돌린다. 실제 사용량은 응답의 `usage` 로 합산해 보고한다. 예상: luna 120회 ≈ $0.05, terra·sol 30회씩 ≈ $0.4, STT 약 25분 ≈ $0.11.
- ElevenLabs **1,500 크레딧**: 시작 전 `tts_elevenlabs.credits_left` 를 읽고, 합성 예정 크레딧(글자 × 0.5)이 1,400 을 넘으면 문장 수를 줄인다. 끝나고 다시 읽어 실제 사용량을 적는다.

## 하지 않는 것
- 제품 코드(`stage/`·`apps/`·`tts_*.py`·`reachy.sh`·게이트웨이) 수정, Claude 모델 호출(채점 포함), `./reachy.sh` 기동, 기본 포트 사용, git 쓰기.
- 키 출력. 키는 `.env` 의 그 한 줄만 파싱한다(`tts_elevenlabs.load_api_key` 방식).

## 산출물
- 도구: `scripts/measure_openai_common.py` · `scripts/measure_openai_llm.py` · `scripts/measure_openai_stt.py`
- 원시 결과·음성·나란히 표: `~/.local/share/reachy-mini-measure/2026-11-12/`(저장소 밖)
- 결과 보고: `docs/research/2026-11-12-openai-llm-stt-measure.md`

## 진행 기록

2026-11-12 저녁(21~23시), 이 맥·한국 회선. 결과 전문은 `docs/research/2026-11-12-openai-llm-stt-measure.md`.

1. **사실 확인**: 계정 모델 목록·OpenAI 공식 문서(가격·모델·reasoning·STT 가이드)를 읽어 위 표를 채웠다.
2. **LLM 도구**(`scripts/measure_openai_llm.py`): 실제 큐시트로 띄운 `Director._answer()` 의 지시문을 가로채고, `build_generate` 를 그대로 부르며 `llm._session` 만 가짜 게이트웨이로 바꿨다. `--preflight` 로 로봇 본문을 그대로 보내 보니 **luna·terra·sol 모두 `max_tokens` 를 400 으로 거절**, sol 은 `temperature 0.7` 도 거절 → `max_completion_tokens` 로 바꿔 쟀다.
3. **로컬 Gemma** 를 임시 포트 18080 에 `reach-llm` 과 같은 옵션으로 띄워(약 3분 로드) 32질문 × 4수준을 luna 와 번갈아 쟀다. 끝나고 껐다(18080 닫힘 확인).
   - 지연(q01 제외): 첫 글자 중앙 로컬 0.59 / luna 1.18초, 끝 1.55 / 1.68초. luna 는 약 3분 흔들림 구간에서 첫 글자 최대 7.88초(5초 초과 4/128).
   - 규칙: 분량 상한 잘림 로컬 12/128 · luna 0. 수준 숫자 위반 luna 2(초등 "1984년" 명백, 중고등 "약 3,500킬로미터" 경미) · 로컬 0. 근거 밖 숫자 0. 금지 표현("10개"·"캐나다"·"695") 0/416.
4. **전문가 상위 후보** `gpt-6.1-terra`(none)·`gpt-6.1-sol`(low) 32문항: 첫 글자 1.22 / 1.41초, 호출당 $0.0017 / $0.0036. luna 보다 뚜렷이 낫지 않음 → 라우팅 불필요로 권장.
5. **흔들림 시험**(일반 32 × 셋 번갈아): 표준 0.96/1.26/1.88초(중앙/p90/최대), Fast 0.87/1.04/1.25, 새 연결 0.94/1.30/2.10.
6. **STT 시험 세트**: ElevenLabs 라이브러리 한국어 6목소리 × 30문장(질문 24 + 짧은 말 6) → 16 kHz 485조각. 아이 목소리 디자인은 **403 `blocked_generation`**(안전 정책)이라 젊은 목소리 2개를 음높이·포먼트 +4/+5반음으로 근사했다(우회 시도는 하지 않았다).
7. **로컬 STT** 를 임시 포트 18090 에 띄워 `auto`·`ko` 로 쟀고 끝나고 껐다(18090 닫힘 확인). OpenAI 는 `languages` 없음·`ko`·`ko,en`·`ko`+keywords 4가지.
   - 성인 깨끗함 CER: 로컬 1.5% · OpenAI 없음 5.7% · ko 0.9% · ko,en 1.2% · ko+kw 0.1%. 아이 근사: 3.0% · 15.1% · 5.6% · 6.3% · 2.1%.
   - `languages` 없음은 "다음" → `Palum.`·`さん。` 등 5/8 — 쓸 수 없다. 잡음·무음 환각: 로컬은 상용구(앱 거르개가 버림), OpenAI 20/20 빈 문자열.
   - 지연 중앙 로컬 0.22(ko)~0.39(auto) · OpenAI 0.73초. OpenAI 27.4초 1건/1,940.
8. **판정 도구 손질**(측정 중 발견, 다시 재지 않고 저장된 답으로 재판정): 질문에 나온 숫자("5G"·"1세대")는 수준 위반에서 뺐다(첫 판정 초등 위반 4건 중 3건), 근거 밖 숫자 판정에 원문자(④)·앞자리 0 정규화(첫 판정 2건 모두 표기 차이 — 사람이 브리프와 대조), 예열에 쓴 q01 은 지연 통계에서 뺐다(로컬 0.03초), 블라인드 표에서 첫 글자 시간을 접힌 칸으로 옮겼다(로컬이 드러난다). 블라인드 표는 헤드리스 Chrome 으로 렌더 확인.
9. **비용**: OpenAI 약 $0.67(상한 $3) · ElevenLabs 계정 +576 이하(상한 1,500, 다른 작업자 사용분 섞였을 수 있음).

## 조율자에게

### 결정 필요 — 권장안으로 보고서를 썼다
- **D5 LLM**: `gpt-6-luna` + `reasoning_effort:"none"`, 모든 수준. 전문가 라우팅은 **불필요**(B2 게이트웨이의 `REACHY_OPENAI_LLM_MODEL_EXPERT` 는 비워 둔 기본이 맞다). 스위치를 켠다면 `gpt-6.1-terra`(none) — sol 은 사고를 못 끄고 `temperature` 를 거절한다.
- **D6 STT**: `gpt-transcribe` + `languages` 반드시 채움(`["ko"]` 권장, B2 의 `["ko","en"]` 도 허용 범위) + **큐시트 고유명사로 만든 `keywords`**(B2 에 아직 없음). 로컬은 폴백. **아이 목소리는 열린 위험** — 합성 근사로만 쟀고 키워드 없이는 로컬보다 나빴다(5.6% vs 3.0%). 실제 아이 녹음 10~20개(보호자 동의)로 `scripts/measure_openai_stt.py` 를 한 번 더 돌려 확정하기를 권한다.
- **Fast 모드**(`service_tier:"fast"`, 2배 요금): 꼬리를 줄인다(p90 1.04 vs 1.26초). 게이트웨이 스위치로 두고 기본 꺼짐을 권장.

### B2(게이트웨이)에 넘길 수치
- 첫 글자 5초 초과: luna 4/128(한 흔들림 구간에 몰림), sol 1/32, 나머지 0/128. B2 의 `llm_timeout_s=5.0` 이면 이 몫이 실패 경로로 간다 — 그 경로가 소리 내는 실패(경고 + 로컬/고정 대사)인지 확인 필요. 로봇 쪽 한도는 10초.
- STT 27.4초 1/1,940 — B2 의 `stt_timeout_s=8.0` 이 이것을 잡는다. 재시도 1회를 권장(결과는 정상 전사였다).
- `stream_options.include_usage` 를 켜지 않는 B2 결정이 맞다 — 측정 도구에서 그 청크가 `LLMClient` 를 깨는 것을 확인했다.
- STT 청구는 요청당 초 올림(+14%).

### `docs/lessons.md` 후보(증상 → 원인 → 규칙)
1. **OpenAI gpt-6 계열은 로봇 본문을 그대로 받지 않는다** — 증상: `max_tokens` 400(모든 후보), 6.1-sol 은 `temperature 0.7` 도 400. 원인: 추론 모델 계열은 `max_completion_tokens` 만 받고, 사고를 끌 수 없는 모델은 샘플링 값을 고정한다. 규칙: 외부 모델을 붙이기 전에 **로봇이 실제로 보내는 본문**으로 1회씩 preflight 한다(`measure_openai_llm.py --preflight`).
2. **`gpt-transcribe` 에 `languages` 를 비우면 짧은 한국어가 외국어가 된다** — 증상: "다음" → `Palum.`·`Thaum.`(en)·`さん。`(ja), 짧은 말 CER 24%. 원인: 1초 남짓 조각에서 자동 감지가 흔들린다(로컬 Whisper 의 "예 → Yay!" 와 같은 줄기). 규칙: 게이트웨이는 `languages` 를 늘 채운다. 감독의 진행 키워드("다음")가 여기서 깨진다.
3. **ElevenLabs 목소리 디자인은 아이 목소리를 막는다** — 증상: 403 `blocked_generation`. 원인: 안전 정책(미성년 음성 생성). 규칙: 아이 음성 STT 검증은 합성으로 못 끝낸다 — 근사(음높이·포먼트 이동)로 상대 비교만 하고, 확정은 실제 녹음으로 한다.
4. **측정 도구: 예열 입력을 표본에서 뺀다** — 증상: 로컬 첫 글자 0.03초. 원인: 예열에 쓴 지시문이 캐시에 통째로 남았다. 규칙: 예열은 표본과 다른 입력으로 하거나 그 표본을 통계에서 뺀다.
5. **측정 도구: 숫자 규칙은 질문이 말한 숫자를 빼고, 표기를 맞춘 뒤 센다** — 첫 판정의 초등 위반 4건 중 3건("5G"·"1세대" 되받기), 근거 밖 숫자 2건 전부(원문자 ④·"06")가 헛경보였다.

### 데이터 문제(제품 쪽, 내 소유 아님)
- **`data/cues.yaml` 19-closing 브리프의 "원장에 있는 기념촬영 안내"** — 원장(내부 원본 문서)이 장소처럼 새어 luna 가 일반 q32 에서 3회 모두 "원장에서 기념사진도 찍으실 수 있어요" 라고 했다(로컬은 이번 표본에서 안 냈다). 브리프 문구를 고칠지 대본 담당이 정할 일.
- 앱 기본 `REACHY_STT_LANG=auto` 는 로컬에서도 잡음 속 아이 근사(11.6% vs `ko` 6.6%)·짧은 말(10.4% vs 4.2%)에서 나쁘다 — 로컬 폴백을 쓰는 동안은 `ko` 가 낫다(제품 설정 변경은 조율자 판단).

### 공용 문서에 넣을 것
- `docs/real-robot-deployment.md`: 보고서의 「게이트웨이 번역 목록」(LLM 1~7, STT S1~S5) — 게이트웨이 절이 생기면 그 아래.
- 11-10 핸드오프 체크리스트: LLM 실측·전문가 라우팅·초등 규칙 회귀·STT 실측 4줄을 "완료(합성 질문·합성 음성 한계, 아이 실녹음 남음)" 로.

### 남은 일
- 실제 아이 녹음으로 STT 재확인(위 D6). 전시장 회선·시간대에서 LLM 지연 재측정(A6 리허설 때).
- 실제 관람객 질문이 쌓이면 `QUESTIONS` 에 `실제` 출처로 넣어 다시 돈다.

### 바꾼 파일(전부 새 파일)
- `scripts/measure_openai_common.py` · `scripts/measure_openai_llm.py` · `scripts/measure_openai_stt.py`
- `docs/research/2026-11-12-openai-llm-stt-measure.md` · `docs/superpowers/plans/2026-11-12-openai-measure.md`
- 저장소 밖: `~/.local/share/reachy-mini-measure/2026-11-12/`(63 MB — 결과 jsonl, 블라인드 표 `llm/side-by-side.html`, 음성 485조각, 로그)
- 테스트 파일은 만들지 않았다(브리프 허용 — 측정 도구, `--dry-run` 있음). 파일 이름이 `test_` 로 시작하지 않아 pytest 가 수집하지 않는다(`pytest.ini` testpaths = tests).
