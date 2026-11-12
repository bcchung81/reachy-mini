# LLM·STT 를 OpenAI 로 — PC 게이트웨이 (구현 계획)

2026-11-12. 근거: `docs/handoff/2026-11-10-frontier-ai-transition.md` §2·§9(구조) · `docs/handoff/2026-11-12-after-elevenlabs-subscription.md` A7.
**로봇 재배포 없음** — 로봇·감독은 지금처럼 PC 주소(`REACHY_LLM_URL` `:8080` · `REACHY_STT_URL` `:8090`)만 안다.
PC 의 게이트웨이가 키를 붙여 OpenAI 로 넘긴다. **스위치를 안 켜면 지금과 같은 구성**(llama-server `:8080` · stt_server `:8090` 직결)이다.
본보기는 TTS 쪽 선례 — `tts_cache_proxy.py`(로봇 주소에 프록시, 안쪽 포트에 로컬 서버, 실패 정책·경고) · `tts_elevenlabs.py`(키 읽기).

## 지금 보내는 요청 — 코드로 읽음

| 누가 | 어디로 | 본문 | 응답을 어떻게 읽나 |
|---|---|---|---|
| 로봇 앱(`apps/voice_chat/voice_chat/llm.py::LLMClient.chat_stream`) — 혼자 대화 | `POST {REACHY_LLM_URL}/v1/chat/completions` | `{model:"local", messages:[system, 이력…, user], stream:true, temperature:0.7, max_tokens:200}`. 카메라 질문이면 user `content` 가 `[{type:text},{type:image_url, data:image/jpeg;base64}]` | `requests` `iter_lines()` 로 `data: ` 줄만, `[DONE]` 에서 멈춤, `json.loads(...)["choices"][0]["delta"]["content"]` — **`choices` 가 빈 줄이 오면 `IndexError`** · 타임아웃 10초(연결·바이트 사이) · keep-alive `Session` |
| 감독(`stage/__main__.py::build_generate`) — 시나리오 공연 | 같음(같은 `LLMClient` 를 가져다 쓴다) | 위와 같고 `max_tokens = level.max_tokens`(`max_chars*2+64`), 시스템 프롬프트 = `build_system_prompt(role, level)`, 이미지 없음 | 절을 모두 모은 뒤 이력의 원문을 쓴다(`reply_text`). 예외면 "LLM 생성 실패 — 폴백" 경고 + 큐시트 폴백 |
| 예열(`scripts/warmup.py`)·측정(`scripts/measure_latency.py`) | 같음 | `{model:"local", stream:true, temperature:0.7, max_tokens:8, …}` | 첫 `data:` 줄까지 시간 |
| 로봇 앱(`stt.py::transcribe`) | `POST {REACHY_STT_URL}`(`…/v1/audio/transcriptions`) | multipart: `file`=`utt.wav`(16 kHz·mono·s16), `language`=`REACHY_STT_LANG`(기본 **`auto`**) | `r.json()["text"]` 만. 실패(연결·HTTP 오류)면 빈 문자열 = 침묵 · 타임아웃 15초 |
| 로컬 STT(`stt_server.py`) 가 하던 일 | — | `auto` → whisper 자동 감지. 단 **1초 미만은 `ko`**(0.3초 "예"→"Yay!"), 감지가 허용 언어(`STT_ALLOWED_LANGS` 기본 ko,en) 밖이면 **`ko` 로 다시 전사**("네"→베트남어). 값이 없으면 `ko` | `{"text", "language"}` |

## 실측한 사실 (2026-11-12, 이 계정 API — 탐침 7건, 1센트 미만)

| 사실 | 값 |
|---|---|
| `gpt-6-luna` + `max_tokens` | **400** `Unsupported parameter: 'max_tokens' … Use 'max_completion_tokens'` — 로봇 본문 그대로는 못 보낸다 |
| `temperature:0.7` + `reasoning_effort:"none"` | 200 — 받는다 |
| `temperature:0.7` + `reasoning_effort:"low"` | **400** `Only the default (1) value is supported` — 사고를 켜면 `temperature` 를 빼야 한다(공식 changelog: GPT-6 Astra 는 `none` 자체를 안 받는다) |
| 스트림 모양 | `data: {"choices":[{"delta":{"role":"assistant","content":"","refusal":null}}],"obfuscation":"…"}` … `data: [DONE]` — 로봇 파서가 그대로 읽는다. **`stream_options.include_usage` 를 켜면 마지막 줄의 `choices` 가 비어 로봇이 `IndexError`** → 게이트웨이는 그것을 넣지 않는다 |
| 첫 바이트(새 연결, 이 맥 → OpenAI) | 사고 끔 1.58초 · 기본(medium) 1.76초 — 한 번씩이라 지연 수치는 스모크에서 다시 잰다 |
| `gpt-transcribe` + `languages[]=ko`,`en` | 200, 4.2초 오디오 1.3초, 원문과 글자까지 같다. 응답 `{"text","languages":[{"code":"ko"}],"usage":{…}}` |
| `gpt-transcribe` + 옛 `language=ko` | 200(거절하지 않는다) — 그래도 문서대로 `languages` 로 바꾼다("둘 다 보내지 말 것", `auto` 는 ISO 코드가 아니다) |
| `keywords[]` 상한(후속, 1초 오디오 탐침 9건) | 공식 문서(레퍼런스·STT 가이드·마이그레이션 쿡북)는 **수치가 없고** 금지 문자(`<`·`>`·CR·LF — 하나라도 있으면 요청 전체 거절)만 밝힌다. 실측: 50·100·200·300·**500개 200**, **1,000개 400 `Could not parse multipart form`**(요청 전체 실패) · 한 낱말 60·200·1,000자 200 · 300개를 실어도 지연 변화 없음(0.87~1.14초) |
| `service_tier:"fast"`(후속) | gpt-6-luna 가 받는다(200). B1 실측: 첫 글자 p90 1.04 대 1.26초, 요금 2배 |

## 구조

```
                                   (스위치를 켰을 때만)
로봇·감독 ─POST :8080─▶ openai_gateway.py ─┬ OpenAI /v1/chat/completions (키 주입·번역, SSE 받는 대로)
                         (BIND_HOST)        └ 실패·키 없음 → 로컬 llama-server 127.0.0.1:8081 (원래 본문)
로봇     ─POST :8090─▶ openai_gateway.py ─┬ OpenAI /v1/audio/transcriptions (gpt-transcribe, languages)
                                            └ 실패·키 없음 → 로컬 stt_server 127.0.0.1:8091 (원래 본문)

스위치 꺼짐(기본): 지금 그대로 — llama-server :8080 · stt_server :8090 를 BIND_HOST 로 직접(게이트웨이 프로세스 없음)
```

- 게이트웨이를 켜면 **두 포트를 다 맡는다**(한 프로세스, 리스너 둘). 한쪽만 OpenAI 면 다른 쪽은 그대로 안쪽 로컬로 넘긴다(통과).
  서비스마다 위상을 달리하면 `reachy.sh` 의 조합이 넷으로 갈리고 "이미 떠 있다" 판정이 복잡해진다 — 통과 한 홉(loopback, 수 ms)이 더 싸다.
- 로컬 서버(llamactl `reach-llm`)는 게이트웨이를 켜도 **안쪽 loopback 포트에 그대로 띄운다** — OpenAI 실패 시 폴백 자리다(llamactl 이
  `LLM_PORT`/`STT_PORT`/`LLM_HOST`/`STT_HOST` 를 이미 받는다).

## 결정 세부

| 항목 | 결정 |
|---|---|
| 스위치 | `REACHY_LLM_ENGINE=local\|openai` · `REACHY_STT_ENGINE=local\|openai` (기본 `local` = 지금 구성). 모르는 값은 멈춘다(조용히 넘기지 않는다). `TTS_ENGINE` 처럼 **`reachy.sh` 를 부르는 명령 앞에** 붙인다 — 자식(게이트웨이·감독)이 같이 물려받는다 |
| 모델 | `REACHY_OPENAI_LLM_MODEL`(기본 `gpt-6-luna`) · `REACHY_OPENAI_LLM_EFFORT`(기본 `none` — medium 이면 첫 토큰이 수 초) · `REACHY_OPENAI_STT_MODEL`(기본 `gpt-transcribe`) |
| 전문가 라우팅 | `REACHY_OPENAI_LLM_MODEL_EXPERT`(기본 **비어 있음 = 라우팅 안 함**, B1 이 정한다) · `REACHY_OPENAI_LLM_EFFORT_EXPERT`(기본 = 위 effort). **표지**: 감독이 전문가 수준 클라이언트를 만들 때 `model` 필드를 `"reachy-expert"` 로 싣는다(`LLMClient(model=…)` 이미 있는 인자 — 로봇 앱 수정 없음). **`REACHY_LLM_ENGINE=openai` 일 때만** 싣는다 → 스위치를 끄면 감독 요청도 지금과 바이트 동일. 게이트웨이는 표지를 보고 상위 모델로, 로컬로 넘길 때는 `model` 을 `"local"` 로 되돌린다(llama-server 가 이름을 보든 말든 지금과 같은 값). 전문가 모델이 비면 표지가 와도 기본 모델로 |
| LLM 번역 | `model` 교체 · `reasoning_effort` 추가(요청에 있으면 그대로) · **`max_tokens` → `max_completion_tokens`**(400 실측) · `temperature` 는 effort 가 `none` 일 때만 남긴다(400 실측) · effort 가 `none` 이 아니면 `max_completion_tokens` 에 사고 몫(기본 2,000 토큰)을 더한다 — 상한이 사고 토큰까지 세므로 로봇의 200 으로는 답이 비어 나온다 · llama.cpp 전용 필드(`cache_prompt`·`top_k`·`min_p`·`repeat_penalty`·`n_predict`·`id_slot`·`samplers`·`grammar`·`chat_template_kwargs`·`reasoning_format` 등)는 버리고 필드마다 한 번 경고 · `stream_options` 는 넣지 않는다(위 `IndexError`) |
| 스트리밍 | OpenAI 응답을 **받는 대로**(`read1`) 청크로 흘린다. 첫 바이트를 받기 전 실패(연결·HTTP 오류·시간 초과)는 로컬로 넘긴다 — 그래서 첫 청크를 받은 뒤에야 로봇에게 머리를 보낸다. 흐르는 도중 끊기면 되돌릴 수 없다 → 경고 + **연결을 끝맺지 않고 닫는다**(정상 종료로 보이면 잘린 답을 완성된 답으로 읽는다; 감독은 예외를 받아 폴백 대사로 간다) |
| 연결 재사용 | OpenAI 로 가는 HTTPS 연결을 풀에 남겨 다시 쓴다 — 새 연결마다 TLS 왕복이 첫 토큰 앞에 얹힌다. 로봇 쪽 keep-alive 도 살린다(`Connection: close` 를 보내지 않는다, 응답은 chunked 로 끝맺는다) |
| 시간 상한 | `REACHY_OPENAI_LLM_TIMEOUT_S`(기본 5초) — 연결·보내기·응답 머리·첫 바이트를 **합친 마감**이다(소켓 상한은 단계마다 새로 걸려 하나만 주면 그 몇 배를 기다린다 — 구현 중 고침). 첫 바이트 뒤로는 바이트 사이 간격 상한. 로봇·감독의 10초 안에 로컬 폴백(1~2초)까지 들어가게. **LLM 은 다시 보내지 않는다**(관람객이 기다린다). ~~`REACHY_OPENAI_STT_TIMEOUT_S`(기본 8초, 언어 재전사까지 합쳐서)~~ → **후속(B1 실측 반영)**: STT 는 **시도당** `REACHY_OPENAI_STT_TIMEOUT_S`(기본 5초) × `REACHY_OPENAI_STT_RETRIES`(기본 1번 더) — **요청을 보낸 뒤 응답이 늦을 때만** 다시 보낸다(B1: 27.4초 1/1,940, 다시 하면 정상). 연결 실패·HTTP 오류는 다시 해도 같으니 바로 로컬. 5초 × 2 + 로컬 약 1초 < 로봇 15초 |
| STT 번역 | multipart 를 풀어(직접 — `cgi` 는 3.13 에서 사라진다) `file` 은 그대로, `model`, `languages[]`: 값 없음·빈 값 → `ko` · `auto`/`detect` → ~~허용 언어(`STT_ALLOWED_LANGS`, 기본 `ko,en`)~~ **`REACHY_OPENAI_STT_LANGUAGES`(기본 `ko` 하나 — B1: 비우거나 넓히면 "다음" → `Palum.`)**, 목록을 넓혔을 때만 1초 미만은 `ko`(`STT_AUTO_MIN_S`)·감지 언어가 목록 밖이면 `ko` 로 한 번 더 · 그 밖 → 그 언어 하나. 응답은 로컬 서버 모양 `{"text","language"}` |
| STT 키워드(후속) | **큐시트에서 기동 때 한 번 만든다**(손으로 적은 목록 없음 — B1 의 16개는 시험 문장에서 골랐다). 순서: ① 부르고 멈추는 말 — 역할 이름(`stage.director.SPEAKER_LABEL`: 사회자·도슨트), 끼어들기 호출어(PC 의 `REACHY_BARGE_IN_WAKE`, 없으면 로봇 앱 `voice_loop.py` 소스의 기본값: 미니야·그만·잠깐만·스톱 — 앱이 STT 결과에서 이 말을 찾는다) ② 큐 순서대로 K1 라틴 약어(GMDSS·VLF·ICAO·5G — 단위·규격 번호 제외) · K2 가운뎃점 나열("맥스웰·헤르츠·마르코니") · K3 사람이 쓴 라벨(큐 제목·주제, 카드 항목 제목·그림 라벨 — 지도 출발·도착 "폴듀 (영국)"·"뉴펀들랜드")의 1~2어절 명사구. 조사는 **받침 규칙**으로 뗀다("패러데이" 는 안 깎는다). 출처는 감독과 같은 로더(`stage.cues.load_cues`, `REACHY_CUES_PATH`) + `data/handout-cards/`. 지금 248개(부르는 말 6 + 대본 242). 상한 `REACHY_OPENAI_STT_KEYWORDS_MAX`(기본 300 — 실측 500 받음·1,000 거절), 한 낱말 40자, 금지 문자 — 넘거나 걸리면 거르고 **경고 한 줄**. 큐시트를 못 읽으면 경고 한 줄 + 키워드 없이. `REACHY_OPENAI_STT_KEYWORDS=off` 로 끈다. **못 줍는 것**: 대사 문장 속에만 나오는 이름(카르파티아호·쿨롱·김학우 등 — 문장에서 이름을 가르려면 형태소 분석이 필요하다) |
| `service_tier`(후속) | `REACHY_OPENAI_LLM_SERVICE_TIER`(기본 비움 = 보내지 않음). `fast` 면 LLM 요청에 싣는다(요청에 이미 있으면 그대로). STT 에는 싣지 않는다 |
| 실패 정책 | OpenAI 실패(연결·4xx·5xx·429·시간 초과) → **로컬 서버로 원래 본문을 넘기고 경고 한 줄**(요청마다 한 줄, 상태 코드와 서버 오류 요약). 로컬도 없으면 502 → 로봇은 지금과 같은 오류(LLM: 예외 / STT: 빈 문자열). 키가 없으면 기동 때 경고 한 줄 + **외부 호출 0**, 전부 로컬로 |
| 키 | 환경변수 `OPENAI_API_KEY` 가 먼저, 없으면 저장소 루트 `.env` 의 **그 한 줄만**(`tts_elevenlabs.load_api_key` 와 같은 방식, 그 함수는 고치지 않는다). `reachy.sh` 는 export 하지 않는다 — 게이트웨이 프로세스만 읽는다. 로그·예외에는 "설정됨/없음"만. OpenAI 401 메시지는 키 일부(`sk-…abcd`)를 되돌려 주므로 **오류 요약에서 키와 `sk-…` 꼴을 지운다** |
| 로그 | `.demo-logs/openai-gateway.log` — 요청마다 서비스·모델·첫 바이트·전체 시간·경로(openai/local/fallback). **본문(질문·전사문)은 남기지 않는다**(앱 로그에 이미 있고, 개인정보 권장 — 11-10 §10) |
| 헬스 | `GET /health` — `{"status","gateway":"openai","service","engine","key","model",…,"local"}`. OpenAI 쪽이고 키가 있으면 로컬이 죽어도 200(외부는 부르지 않는다), 아니면 로컬 헬스를 그대로. `reachy.sh` 는 `"gateway"` 표지로 "누가 그 포트에 떠 있나" 를 가른다 |
| `reachy.sh` | `start_llm_stt` 만 갈린다. 꺼짐 → 기존 코드 그대로(+ 게이트웨이가 남아 있으면 경고). 켜짐 → llamactl 을 안쪽(`REACHY_LLM_INNER_PORT` 8081 · `REACHY_STT_INNER_PORT` 8091, loopback)에 → 게이트웨이를 `:8080`·`:8090`(BIND_HOST)에. `:8080`/`:8090` 에 게이트웨이가 아닌 것이 떠 있으면 멈추고 `./reachy.sh stop` 을 권한다(게이트웨이가 그 포트를 못 잡는다). `stop` 은 게이트웨이와 안쪽 포트의 llama-server·STT 도 내린다(스위치와 상관없이 — 끄고 `stop` 해도 남지 않게). `start --dry-run` 은 켜졌을 때만 `PLAN gateway …` 한 줄을 더 찍는다(꺼짐이면 지금과 같은 4줄) |

## 테스트 — `tests/test_openai_gateway.py`

가짜 OpenAI 서버(HTTP, 스크립트대로 응답)·가짜 로컬 서버로 게이트웨이를 실제로 띄워 로봇의 `LLMClient`·`stt.transcribe` 로 부른다.

- 키 없으면 외부 호출 0(가짜 OpenAI 가 요청을 하나도 못 받는다) + 기동 경고 한 줄 + 로컬로
- 스트리밍이 **받는 대로** 흐른다(가짜 서버가 두 번째 청크 전에 멈춰 있는 동안 첫 청크가 로봇에 닿는다)
- 필드 번역: `max_tokens`→`max_completion_tokens`, `reasoning_effort`, 모델, `temperature`(none 일 때만), llama.cpp 필드 제거
- 전문가 라우팅: 표지 + 모델 설정 → 상위 모델·그 effort / 모델 비면 기본 모델 / 로컬로 갈 때 `model:"local"`
- 감독: `REACHY_LLM_ENGINE=openai` + 전문가 수준일 때만 `model="reachy-expert"`, 아니면 지금과 같은 인자
- 실패(500·연결 거부·시간 초과) → 로컬 답 + 경고 정확히 한 줄 / 도중에 끊기면 로봇 쪽이 예외를 받는다
- 로그·오류에 키 값이 없다(가짜 서버가 오류 본문에 키를 되돌려 줘도)
- STT: `auto`→`languages[]=ko,en`, 1초 미만 → `ko`, 허용 밖 감지 → `ko` 로 한 번 더, 응답 모양
- 스위치 꺼짐 = 기존 동작: `start --dry-run` 이 지금과 같은 4줄, `start_llm_stt` 가 지금과 같은 llamactl 호출(포트·호스트), `bash -n`
- 켜짐: llamactl 이 안쪽 loopback 포트로, 게이트웨이가 바깥 포트로 / 바깥 포트에 로컬이 떠 있으면 멈춘다 / `stop` 이 게이트웨이·안쪽 포트를 내린다

## 실제 OpenAI 스모크 (예산 $0.50)

게이트웨이를 임시 포트(18080·18090, 로컬 폴백은 비어 있는 포트)로 띄워 — 로봇 모양(`LLMClient` 혼자 대화) · 감독 모양
(일반·전문가 시스템 프롬프트, `max_tokens = level.max_tokens`) · STT(구운 고정 대사 PCM 을 16 kHz WAV 로, `language=auto`)를
한두 번씩. 첫 토큰·첫 절·전체 시간과 연결 재사용 효과를 적는다. 끝나면 끈다.

## 바꾸는 파일

- 신규: `openai_gateway.py` · `tests/test_openai_gateway.py` · 이 계획서
- 수정: `reachy.sh`(LLM·STT 기동·정리·dry-run 만) · `stage/__main__.py`(`build_generate` 의 클라이언트 인자 한 곳)
- 안 바꾼다: `apps/`(로봇 재배포 없음) · `tts_*` · `scripts/bake_tts.py` · `scripts/measure_openai_*`

## 실기에 올리면 무엇이 깨지나

- 로봇: 아무것도 — 주소·요청·응답 모양이 그대로다(`text` 만 읽는다, SSE 줄 모양 같다).
- PC: 인터넷이 끊기면 요청마다 OpenAI 시간 상한(LLM 5초)만큼 늦게 로컬로 간다 — 로봇의 10초 안이지만 답이 그만큼 늦다.
  끊긴 채 공연한다면 스위치를 끄고 다시 띄운다(`./reachy.sh stop` → 스위치 없이 `start`).
- 지연: STT 가 로컬(mlx-whisper, 이 맥)보다 느릴 수 있다(탐침 4.2초 오디오 1.3~1.8초) — 스모크로 재고 결정은 B1 실측과 함께.

## 진행 기록 (2026-11-12, 작업자 B2)

1. **코드 읽기** — 로봇 `llm.py`·`stt.py`, 감독 `stage/__main__.py::build_generate`, `scripts/warmup.py`, `stt_server.py`(언어 규칙),
   `reachy.sh`·`~/workspace/llamactl.sh`(포트·호스트 환경변수), TTS 선례. 결과는 위 「지금 보내는 요청」.
2. **탐침 7건**(이 계정, 1센트 미만) — 위 「실측한 사실」. 계획을 바꾼 것: `max_tokens` 400 → 번역 필수, 사고를 켜면 `temperature` 400.
3. **구현** — `openai_gateway.py`(새 파일), `reachy.sh`(LLM·STT 기동·정리·dry-run·`status` 한 줄·`logs` 목록에 게이트웨이 로그),
   `stage/__main__.py`(`client_model_kw` + `build_generate` 인자 한 곳). 로봇 앱(`apps/`)은 손대지 않았다.
4. **테스트** — `tests/test_openai_gateway.py` **47개 통과**(4.8초). 가짜 OpenAI·가짜 로컬 서버를 세우고 로봇의 `LLMClient`·`stt.transcribe`
   로 부른다: 키 없으면 외부 호출 0 + 경고 서비스당 1줄 · 받는 대로 흐름(가짜 서버가 둘째 청크 전에 막혀 있는 동안 첫 절 도착) ·
   필드 번역 · 연결 재사용(요청 3번 → OpenAI 연결 1개) · 전문가 라우팅(모델 비면 라우팅 없음, 로컬로 갈 때 `"local"`) · 감독 인자(스위치 꺼짐 =
   지금과 같은 인자) · 실패 4종(500·429·시간 초과·**합쳐서 느림**) → 로컬 + 경고 1줄 · 연결 거부 · 도중 끊김 → 로봇이 예외 · 로컬도 없으면
   지금과 같은 오류 · 키가 로그·헬스·로컬 요청 어디에도 없음 · STT 언어 규칙 5종 · multipart 파서 · `reachy.sh` 배선 9종(꺼짐 = 지금과 같은
   llamactl 호출·dry-run 4줄 / 켜짐 = 안쪽 loopback + 바깥 게이트웨이 / 충돌 3종 / stop) · `bash -n` · 변수 뒤 멀티바이트 금지.
   함께 돌린 기존 테스트: `test_reachy_start.py` 42 · `test_stage_main.py` · `test_llm.py` — 4파일 합계 **137 통과**.
5. **실제 OpenAI 스모크**(게이트웨이를 임시 포트 18180·18190 에 단독으로, 끝나고 내림. 추정 비용 $0.10 미만):

   | 요청 모양 | 모델 | 첫 글자(첫 절) | 전체 |
   |---|---|---|---|
   | 로봇 혼자 대화(`LLMClient`, `prompt.md`, 2턴 × 2회) | gpt-6-luna | 첫 절 0.94~1.44초 | 1.23~1.58초 |
   | 감독 일반(도슨트 시스템 프롬프트, `max_tokens = level.max_tokens`) | gpt-6-luna | 0.87·1.06초 | 1.66·1.76초 |
   | 감독 전문가(`model:"reachy-expert"`, 전문가 모델 `gpt-6-sol` 로 시험) | **gpt-6-sol 로 라우팅 확인** | 0.94·1.04초 | 1.49·1.93초 |
   | STT `auto`(구운 고정 대사 → 16 kHz WAV) | gpt-transcribe | 1.0~4.2초 오디오 → 0.75~1.55초 | 3문장 중 2문장 글자까지 같음, 1문장 문장부호만 다름("여러분!" → "여러분.") |
   | 실패(없는 모델 이름 → OpenAI 404) | — | 경고 1줄 + 로컬 폴백 0.44초 | 로그에 `sk-` 꼴 0건 |

   비교 기준(이 맥 로컬): Gemma E4B 자유대화 평균 1.9초(llamactl 주석), TTS 캐시 미스 첫 소리 276~316 ms(§15.10). 연결 재사용의 지연 이득은
   이 표본(턴 2개)으로는 가려지지 않았다 — 테스트로 재사용 자체만 확인했다.
   `gpt-6-sol` 은 `reasoning_effort:"none"` + `temperature:0.7` 을 받는다(200).

## 진행 기록 — 후속(B1 실측 반영, 2026-11-12 저녁)

조율자 브리프 `B2-followup.md`. 근거: B1 `docs/research/2026-11-12-openai-llm-stt-measure.md` · `…/plans/2026-11-12-openai-measure.md`.

1. **STT `languages` 기본 `ko` 하나**(`REACHY_OPENAI_STT_LANGUAGES`). 넓혔을 때만 1초 미만 규칙·허용 밖 재전사가 돈다.
2. **STT `keywords` 를 큐시트에서**(위 「결정 세부」). 규칙을 세 번 시험해 고쳤다: 한두 큐에 몰린 낱말 규칙은 657개에 동사 활용형투성이라 버렸고,
   괄호 원어 꼴은 마르코니·폴듀를 못 잡아 버렸다. 남긴 것은 약어·가운뎃점 나열·사람이 쓴 라벨 + 받침 규칙 조사 떼기.
   **품질 확인**(실제 API, 구운 고정 대사 40문장 — 이름 든 문장 22·용어 든 문장 8·없는 문장 10): 키워드 없음 CER 1.25% · 242개 1.42%(17/1,200자
   — 차이는 "고요/구요"·"도슨트/노스트" 같은 흔들림), **없는 키워드가 끼어든 받아쓰기 0건/40**, 지연 중앙 0.99초 같음. 루노호트는 키워드로
   고쳐졌다(루모호트 → 루노호트). 깨끗한 합성 음성이라 둘 다 이미 낮다 — 이득이 큰 자리는 B1 의 잡음·아이 근사(5.6% → 2.1%)다.
3. **STT 느린 응답 1회 재전송**(시도당 5초). LLM 은 다시 보내지 않는다(테스트로 박제 — 실패 4종 모두 OpenAI 요청 1번).
4. **`service_tier` 스위치**(기본 꺼짐).
5. **테스트** `tests/test_openai_gateway.py` **62개 통과**(7.5초) — 새로 15개: languages 기본 ko·환경변수 · 넓혔을 때 1초 규칙 · 키워드를 싣는다 ·
   큐시트에서 고유명사 20개가 나오고 잡음 12종이 안 나온다 · 부르는 말 먼저 · 받침 규칙 · 기동 때 만들고 스위치로 끈다 · 상한 초과 → 자르고 경고 1줄
   (앞이 남는다) · 금지 문자 거르기 · 큐시트를 못 읽으면 경고 1줄 · STT 늦음 → 재전송 성공 경고 1줄 / 두 번 늦음 → 로컬 경고 1줄 / 연결 안 됨 →
   재전송 없음 · HTTP 오류 재전송 없음 · LLM 재전송 없음 · service_tier 꺼짐/켜짐 · **로봇 두 대(사회자·도슨트)가 LLM·STT 를 동시에** — 가짜 OpenAI 가
   두 요청이 다 와야 답하도록 막아 둔다(게이트웨이를 한 줄 처리로 바꾼 돌연변이에서는 이 테스트가 끝나지 않는 것을 확인했다 — keep-alive 연결
   하나가 서버를 붙잡는다). 함께 돌린 `test_reachy_start.py`·`test_stage_main.py`·`test_llm.py` 포함 **152 통과**, `bash -n` 통과.
6. **실제 OpenAI 스모크**(게이트웨이 기본값 + `service_tier=fast`, 임시 포트, 끝나고 내림): 기동 줄 "키워드 248개(예: 사회자, 도슨트, 미니야, 그만 …)
   · 시도당 5초 × 2번". 로봇 혼자 대화(fast) 첫 절 0.93~1.69초 · STT 0.67~0.99초, 루노호트·폴듀·뉴펀들랜드 정확, **테레민은 키워드가 있는데도
   "테르민"**(키워드는 힌트일 뿐 — 합성 음성의 발음 탓인지는 가리지 못했다) · 로그 `sk-` 0건. 후속 전체 비용 추정 $0.05 미만
   (상한 탐침 9건 + 품질 확인 80건 + 스모크 10건).

## 조율자에게

### 공용 문서에 넣을 것

**`docs/real-robot-deployment.md` 새 절(§15.10 다음) — 초안**

> ### 15.11 LLM·STT 게이트웨이(OpenAI) — 로봇 재배포 없음, 키는 PC 에만(2026-11-12)
> 계획 `docs/superpowers/plans/2026-11-12-openai-gateway.md`. **`REACHY_LLM_ENGINE=openai REACHY_STT_ENGINE=openai ./reachy.sh start --robot`**
> 이면 PC 의 `:8080`·`:8090` 에 `openai_gateway.py` 가 서고, llama-server·stt_server 는 안쪽 `127.0.0.1:8081`·`:8091` 로 옮긴다(폴백 자리).
> 로봇 config(`REACHY_LLM_URL`·`REACHY_STT_URL`)·요청·응답 모양이 그대로라 **재배포가 필요 없다.** 기본은 `local`(지금 구성, 게이트웨이 없음).
> - 모델: LLM `gpt-6-luna`(`reasoning_effort:"none"`), STT `gpt-transcribe`. 전문가 수준만 `REACHY_OPENAI_LLM_MODEL_EXPERT` 로(감독이
>   `model:"reachy-expert"` 표지를 싣는다 — 스위치를 켰을 때만). 비어 있으면 전문가도 기본 모델 — **B1 결론: 비워 둔다**(라우팅 불필요).
> - STT: `languages` 는 **한국어 하나**(B1: 비우면 "다음" 이 `Palum.`). 영어 관람객을 받는 날은 `REACHY_OPENAI_STT_LANGUAGES=ko,en`.
>   **키워드**는 기동 때 큐시트·교육자료 카드에서 만든다(전시 고유명사·약어 + 역할 이름·끼어들기 호출어, 지금 248개) — 대본을 고치면 다시 띄우면
>   따라온다. 로봇 config 에서 `REACHY_BARGE_IN_WAKE` 를 바꿨다면 PC 에도 같은 값을 준다.
> - 꼬리 지연이 거슬리면 `REACHY_OPENAI_LLM_SERVICE_TIER=fast`(요금 2배, B1: 첫 글자 p90 1.26 → 1.04초). 기본 꺼짐.
> - 키: 저장소 루트 `.env` 의 `OPENAI_API_KEY` 를 게이트웨이 프로세스만 읽는다. 없으면 경고 한 줄 + 전부 로컬(외부 호출 0).
> - 실패: OpenAI 실패·시간 초과(LLM 첫 바이트까지 5초 — 다시 보내지 않음, STT 시도당 5초 — 응답이 늦을 때만 한 번 더) → 로컬 서버로
>   원래 요청 + `openai-gateway.log` 에 경고 한 줄. 흐르는 도중
>   끊기면 되돌릴 수 없다 — 연결을 끝맺지 않고 닫아 감독은 폴백 대사로 간다. 로컬도 없으면 지금과 같은 오류.
> - **PC 인터넷이 끊기면** 요청마다 5초 늦게 로컬로 간다(로봇 10초 안). 끊긴 채 공연한다면 스위치를 끄고 다시 띄운다.
> - 실측(이 맥 → OpenAI): 감독 해설 첫 글자 0.87~1.06초, 로봇 첫 절 0.93~1.69초, STT 0.67~1.55초(키워드 248개를 실어도 같다).
> - 실기에서 확인할 것: 두 로봇 동시 질문, PC 인터넷 끊김 때 답이 5초 늦게라도 나오는지, `./reachy.sh logs` 에 폴백 경고가 보이는지.

**`docs/lessons.md` — 이번에 밟은/막은 지뢰(증상 → 원인 → 규칙)** — 후속 2개(8·9)를 끝에 더했다.

1. **bash 3.2 는 변수 뒤에 붙은 멀티바이트 글자를 이름으로 읽는다.** 증상: 게이트웨이 기동 줄에서 `LLM_INNER_PORT\xc2: unbound variable`(`set -u`)로
   `start_llm_stt` 가 죽었다. 원인: `"… :$LLM_INNER_PORT·:…"` — macOS 기본 bash 3.2 가 `·`(UTF-8 첫 바이트 `\xc2`)까지 변수 이름에 넣는다.
   `bash -n` 은 못 잡는다. 규칙: 변수 바로 뒤에 ASCII 가 아닌 글자가 오면 `${VAR}` 로 감싼다.
   테스트 `tests/test_openai_gateway.py::test_변수_바로_뒤에_한글_기호를_붙이지_않는다`(파일 전체를 훑는다).
2. **`set -o pipefail` 아래에서 함수 끝의 "보여 주기" 파이프가 함수의 실패가 된다.** 증상: 게이트웨이가 떴는데 `start_gateway` 가 1.
   원인: 마지막 줄 `grep … | sed …` 에서 grep 이 못 찾으면 파이프 전체가 1. 규칙: 출력만 하는 파이프로 함수를 끝내면 `return 0` 을 붙인다.
   테스트 `…::test_스위치_켜짐이면_로컬은_안쪽_loopback_게이트웨이는_바깥`.
3. **소켓 시간 상한은 단계마다 새로 걸린다.** 증상(리뷰로 잡음): 상한 5초를 줬는데 느린 서버면 연결·응답 머리·첫 바이트에 각각 5초 — 최악
   15초로 로봇의 10초를 넘겨 로컬 폴백이 쓸모없어진다. 규칙: "첫 바이트까지" 같은 예산은 마감 시각(monotonic)으로 주고 단계마다 남은 시간으로
   다시 건다. 테스트 `…::test_OpenAI_LLM_실패는_로컬로_넘기고_경고_한_줄[합쳐서_느림]`.
4. **OpenAI 401 메시지는 키 일부를 되돌려 준다**(`Incorrect API key provided: sk-…abcd`). 오류 요약을 로그에 그대로 쓰면 키 조각이 남는다.
   규칙: 외부 오류 문구는 키와 `sk-…` 꼴을 지운 뒤 쓴다. 테스트 `…::test_로그_오류_로컬요청_헬스_어디에도_키가_없다`.
5. **`stream_options.include_usage` 를 켜면 로봇이 죽는다.** 마지막 SSE 줄의 `choices` 가 비어 `llm.py` 의 `["choices"][0]` 이 `IndexError`.
   규칙: 게이트웨이는 그것을 넣지 않는다(비용 집계가 필요하면 다른 길로). 테스트 `…::test_로봇_본문을_OpenAI_형식으로_번역하고_키를_붙인다`.
6. **gpt-6 계열은 `max_tokens` 를 400 으로 거절하고, 사고를 켜면 `temperature` 도 거절한다**(실측). 로봇 본문을 그대로 넘기면 모든 답이
   폴백으로 떨어진다. 규칙: `max_completion_tokens` 로 바꾸고, effort 가 none 이 아니면 샘플링 필드를 빼고 상한에 사고 몫을 더한다.
7. **헬스 503 은 "안 떠 있다" 가 아니다.** 안쪽 로컬이 죽은 통과 모드 게이트웨이는 503 을 주는데 `up`(200 만 본다)으로 판정하면 새 게이트웨이가
   포트를 못 잡고 옛 설정이 그대로 돈다. 규칙: "그 포트에 누가 있나" 는 응답 본문(표지)으로 가른다. 테스트 `…::test_503_을_주는_옛_게이트웨이도_떠_있는_것으로_본다`.

8. **(후속) `gpt-transcribe` 의 `keywords` 는 문서에 개수 상한이 없지만 실제로는 있다.** 증상(탐침): 1,000개를 실으면 400
   `Could not parse multipart form` — **요청 전체가** 실패한다(500개는 받는다). 원인: 멀티파트 필드 수 한계로 보인다(문서는 금지 문자만 밝힌다).
   규칙: 키워드는 보내기 전에 개수·길이·금지 문자를 걸러 낸다(기본 300개, 넘치면 자르고 경고). 테스트 `…::test_키워드_상한을_넘으면_자르고_경고_한_줄`·
   `…::test_금지_문자나_너무_긴_키워드는_보내기_전에_뺀다`.
9. **(후속) 한국어 조사 떼기는 받침을 봐야 이름을 안 깎는다.** 증상(추출 시험): 끝 글자로만 떼면 "패러데이" → "패러데", "LTE로" 는 그대로,
   "ICT기금" → "ICT". 원인: '이·은·을·과' 는 받침 뒤, '가·는·를·와' 는 받침 없는 말 뒤에만 조사다; 라틴 꼬리는 조사 목록에 있을 때만 조사다.
   규칙: 받침 규칙 + 떼고 한 글자가 남으면 버림(빛이) + '의' 처럼 받침과 무관한 조사는 두 글자를 지킨다(회의). 테스트
   `…::test_조사_떼기는_받침_규칙을_지킨다`. (돌연변이 시험 메모: 게이트웨이를 한 줄 처리로 바꾸면 두 로봇 동시 시험이 **끝나지 않는다** —
   keep-alive 연결 하나가 서버를 붙잡는다. `ThreadingHTTPServer` 를 바꾸면 안 되는 이유다.)

**`CLAUDE.md`**: 명령 표에 `REACHY_LLM_ENGINE=openai REACHY_STT_ENGINE=openai ./reachy.sh start --robot`(LLM·STT 를 OpenAI 로, 키는 `.env`) 한 줄,
"문제 보고를 받으면" 의 서버 쪽 로그 목록에 `.demo-logs/openai-gateway.log`(`logs` 가 경고 줄을 추린다).

**11-10 핸드오프 §11**: "LLM·STT 게이트웨이 구현" 체크 — 스위치 뒤 기본 꺼짐으로 구현·테스트·스모크 완료. 모델 결정(품질·수준 규칙)은 B1 실측.

### 결정 필요 (권장안으로 진행함)

- **(후속) 키워드는 대본의 라벨에서 자동으로 — 대사 문장 속 이름은 빠진다.** 카르파티아호·쿨롱·김학우·잭 필립스 같은 이름은 라벨·나열에 없어
  못 줍는다. 권장: 지금처럼 자동만(손 목록은 썩는다). 꼭 넣어야 할 이름이 생기면 대본 쪽 라벨(카드 항목 제목·그림 라벨)에 올리는 것이 길이다.
- **(후속) 영어 관람객** — 기본 `ko` 하나라 영어로 물으면 한국어로 받아쓴다(B1 권장의 대가). 영어 질문을 받아야 하는 날은
  `REACHY_OPENAI_STT_LANGUAGES=ko,en`.
- **(후속) 로컬 폴백의 언어** — 앱 기본 `REACHY_STT_LANG=auto` 는 로컬 Whisper 에서도 짧은 말·아이 근사에 나쁘다(B1). 게이트웨이는 로컬로 넘길 때
  **원래 본문**(auto)을 넘긴다 — 로봇 설정을 `ko` 로 바꿀지는 제품 결정(로봇 config, 재배포 아님).

- **전문가 상위 모델 이름** — B1 이 정한다. 넣는 곳은 `REACHY_OPENAI_LLM_MODEL_EXPERT`(비면 라우팅 없음). `gpt-6-sol` 은 none+temperature 를
  받는 것을 확인했다. **`gpt-6-astra` 를 고르면** none 을 거절하므로 `REACHY_OPENAI_LLM_EFFORT_EXPERT=low`(이상)를 함께 주고, 첫 토큰이 늦어지면
  `REACHY_OPENAI_LLM_TIMEOUT_S` 도 올려야 한다(아니면 5초 마감에 걸려 늘 로컬로 간다 — 경고가 남는다).
- **스위치 기본값** — 권장: 지금처럼 꺼짐(`local`). B1 의 품질·수준 규칙 실측 뒤 공연 명령에 붙인다.
- **게이트웨이를 켜도 로컬 서버를 필수로 띄운다**(OpenAI 실패·오프라인 폴백). GPU 없는 PC 에서는 안쪽 llamactl 이 실패해 기동이 멈춘다.
  권장: 지금은 필수 유지(전시장 오프라인 대비). GPU 없는 PC 로 옮길 때 "로컬 없이" 모드를 따로 만든다.

### 남은 일

- **`tests/test_reachy_start.py` 의 `_PLAN_ENV` 에 `REACHY_LLM_ENGINE`·`REACHY_STT_ENGINE` 추가**(조율자 파일이라 안 고쳤다). 개발자 셸에 스위치가
  export 돼 있으면 dry-run 에 `PLAN gateway …` 한 줄이 붙어 기존 정확 일치 테스트가 깨진다. (내 테스트는 그 변수들을 지우고 돈다.)
- 실기 리허설(§15.11 마지막 줄) — 로봇 두 대 동시, PC 인터넷 끊김.
- ~~STT 키워드 힌트 — 실측(B1) 뒤 판단~~ → 후속에서 구현(큐시트에서 자동, 기본 켜짐).
- (후속) **아이 실녹음으로 키워드 248개 목록을 다시 잰다** — B1 의 이득(아이 근사 5.6% → 2.1%)은 16개 목록 기준이고, 248개는 깨끗한 합성 음성
  40문장으로 "해치지 않는다(끼어듦 0)" 까지만 확인했다. `scripts/measure_openai_stt.py` 의 `openai-ko-kw` 시스템 키워드를
  `openai_gateway.cue_keywords()` 로 바꿔 돌리면 같은 비교가 된다(B1 소유 파일이라 안 고쳤다).
- (후속) 테레민이 키워드에 있는데도 "테르민" 으로 받아써졌다(스모크 1회) — 실제 관람객 발음으로 다시 본다.
- `stt_server.py` 는 아직 `cgi`(3.13 에서 제거)를 쓴다 — 내 범위 밖, 파이썬을 올릴 때 같이.
- 비용 집계: `include_usage` 를 못 쓰므로(위 5) 사용량은 OpenAI 대시보드로 본다.

### 바꾼 파일

- 신규: `openai_gateway.py` · `tests/test_openai_gateway.py` · `docs/superpowers/plans/2026-11-12-openai-gateway.md`(이 파일)
- 수정: `reachy.sh` — 스위치 변수·`gateway_on`(머리), `status` 게이트웨이 한 줄, `stop_all`(게이트웨이·안쪽 포트), `logs` 목록(게이트웨이 로그),
  `start_llm_stt`(분기 + 꺼짐 경로에 남은 게이트웨이 경고), `llm_stt_log_hint`(포트 인자, 기본 출력 같음), 새 함수 `llm_stt_engines_ok`·
  `gateway_left_warn`·`start_llm_stt_gateway`·`start_gateway`, `run_start`(엔진 검증 + 켜졌을 때만 `PLAN gateway`). **TTS 부분 무수정.**
- 수정: `stage/__main__.py` — `EXPERT_MODEL_MARK`·`EXPERT_LEVEL_NAME`·`client_model_kw` + `build_generate` 의 `LLMClient(..., **model_kw)` 한 곳.
- (후속) 같은 세 파일만 더 고쳤다 — `openai_gateway.py`(언어 기본·키워드 추출·STT 재전송·`service_tier`·기동 줄), `tests/test_openai_gateway.py`
  (15개 추가·STT 언어 테스트 갱신), 이 계획서. `reachy.sh`·`stage/` 는 후속에서 안 바꿨다.
- 저장소 밖: 스모크·탐침 스크립트와 로그는 이 세션 스크래치(`…/scratchpad/smoke_gateway.py`·`probe_openai.py`·`probe_kw.py`·`kw_eval.py`·
  `gateway-*.log`). 임시 서버·시험 프로세스는 모두 내렸다.
