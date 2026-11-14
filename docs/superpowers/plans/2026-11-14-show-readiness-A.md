# 공연 준비 — 갈래 A(안정화) 진행 보고 (2026-11-14, A 칸)

계획: `docs/superpowers/plans/2026-11-14-show-readiness.md` §3. 사용자 결정 U1 ① · U2 10,000/2,000 · U3 ② · U4 ①.
규칙: 고친 파일은 §2.2 A 열뿐, git·굽기·로봇·외부 API 호출 없음, 테스트는 A 소유 파일만 돌렸다.

## A-1(P0-2) 외부 API 사전 점검 — 끝

| 고친 곳 | 무엇 |
|---|---|
| `openai_gateway.py` | `upstream_kind()`(401·429·5xx·4xx·connect·timeout·other) · `GatewayError.kind` · 외부 전용 502 의 본문 `upstream` + 머리 `X-Reachy-Upstream`. **메시지 글은 싣지 않는다**(OpenAI 401 이 키 조각을 되돌려 준다). OpenAI 를 부르지 않은 502(모르는 경로)에는 싣지 않는다 |
| `tts_cache_proxy.py` | 외부 전용 wav 502 에 같은 표지(`upstream_kind()` — 게이트웨이와 같은 이름·갈래). 덤으로 `synth` 가 감싸지 않는 본문 읽기 끊김(OSError·HTTPException)도 잡아 502 로 — 전에는 처리기가 죽어 502 도 없이 연결이 끊겼다 |
| `scripts/warmup.py` | `main(env)`. 외부 전용이면 LLM·TTS·STT 실패를 **점검 실패**로: 종류별 할 일(401 키 / 429 잔액·한도 둘 다 / connect·timeout 인터넷 / 5xx 일시 / 서버 안 뜸 / 그 밖 로그 경로) + "안 되는 것"(관람객 질문 답 · 음성인식 · 관람객 답 목소리) + 끝에 "대본 공연은 구운 캐시로 계속된다". `TTS_ENGINE=elevenlabs` 면 크레딧 줄(10,000 아래 호박 · 2,000 아래 빨강 + "답 약 N개분", 조회 실패는 경고 한 줄). 결과를 `REACHY_PREFLIGHT_OUT`(`등급\t글`)에 실행마다 새로 쓴다. 로컬 구성 문구는 그대로 |
| `reachy.sh` | `robot_warmup` 이 `$LOG_DIR/preflight.txt` 를 먼저 지우고 예열 → `preflight_show`(FAIL/WARN 묶음). `start_director` 가 콘솔 직전에 한 번 더 보이고 감독 로그 머리에 `사전 점검 실패:/경고:` 줄. `REACHY_PREFLIGHT=stop` 이면 실패(빨강)에서 멈춘다(기본 warn — U1 ①) |
| `run-app.sh` | `has_key` 옆에 "키가 맞는지는 기동의 예열이 본다" 주석 |

테스트(새로 쓴 것, 먼저 써서 실패 확인 후 구현):
- `tests/test_openai_gateway.py::test_외부_전용_502_는_실패_종류를_싣고_메시지는_싣지_않는다`(5 종류 × LLM·STT) · `::test_실패_종류는_상태_코드를_다섯_갈래로_줄인다` · `::test_실패_종류는_예외로도_가른다` · `::test_외부_전용_다른_경로는_502`(종류 없음 단언 추가)
- `tests/test_tts_elevenlabs.py::test_외부_전용_wav_실패는_실패_종류를_싣는다`(5 종류) — 가짜 ElevenLabs 에 `fail_status`·`hang` 추가
- `tests/test_warmup.py`(새 파일, 14개) — `test_외부_전용_예열_실패는_종류와_안_되는_것을_말한다` · `test_크레딧이_문턱_아래면_경고한다` · `test_로컬_구성의_예열_문구는_그대로다` 외
- `tests/test_reachy_start.py::test_외부_전용_예열이_실패하면_빨간_묶음으로_다시_보이고_감독_로그_머리에_남긴다` · `::test_점검이_깨끗하면_묶음도_로그_줄도_없다` · `::test_사전_점검_stop_이면_실패에서_멈춘다`

화면 예(가짜 서버, LLM 401 · TTS 연결 실패 · STT 429 · 크레딧 1,500):
```
   LLM  프리픽스 캐시 점검 실패 — OpenAI 키가 틀렸거나 만료(401): .env 의 OPENAI_API_KEY 를 확인한다
        → 안 되는 것: 관람객 질문 답(사과문으로 대신한다)
   TTS  음성 리소스   점검 실패 — 인터넷 연결: ElevenLabs 에 못 닿았다(connect). 전시장 망의 인터넷을 확인한다
        → 안 되는 것: 관람객 답 목소리(즉석 답이 안내 한 번 + 무음이 된다)
   TTS  크레딧 남음 1,500 / 131,000 — 2,000 아래: 관람객 답 약 15개분. 충전하지 않으면 관람객 답 목소리가 곧 끊긴다(대본은 구운 캐시로 계속)
   STT  전사 경로     점검 실패 — OpenAI 잔액 부족 또는 한도 초과(429): 결제·사용량을 확인한다(분당 한도면 잠시 뒤 풀린다)
        → 안 되는 것: 음성인식(관람객 질문과 '다음' 같은 음성 명령 — 조정실·콘솔로 진행한다)
   외부 API 점검 실패 3건 — 안 되는 것: 관람객 질문 답 · 관람객 답 목소리 · 음성인식. 대본 공연은 구운 캐시로 계속된다
```

남은 실측(조율자 — 외부 호출): `.env` 키를 일부러 틀린 값으로 둔 채 예비 포트 기동 → 빨간 줄 확인, 키 조각이 화면·로그에 없는지 `grep`.

## A-2(P0-3) 사과문 굽기 목록 — 끝(굽기는 조율자)

- `scripts/bake_tts.py::fixed_lines` 에 `QA_FALLBACK`(도슨트) · `SOLO_FALLBACK`(사회자)을 넣었다. 감정은 감독이 실제로 보내는
  `QA_ANSWER_EMOTION`("설명", `Director._deliver`), 수준은 None(수준 공통).
- **전수 조사 결과**: 감독을 실제 큐시트로 돌리고 생성을 일부러 실패시켜 감독이 내보내는 say 를 모두 모았다(팟캐스트 질문 4번 —
  확인 멘트·재질문 한 바퀴, 단독 질문 3번 + 가벼운 말 1번). 굽기 계획에 없던 것은 **사과문 둘(4문장)뿐**이었다.
  확인 멘트·재질문·단독 확인 멘트·큐시트 대사는 역할·감정까지 키가 맞았다. 단독 거절 문구(`_solo_refusal_locked`)는
  콘솔 경고라 말하지 않는다 — 굽지 않는다. 받아치기 생성물 보정(`_ensure_visitor_cue`)은 고정 대본 전환으로 쓰이지 않는다.
- 테스트: `tests/test_bake_tts.py::test_감독이_LLM_없이_말하는_고정_문장은_전부_굽기_목록에_있다`(감독을 돌려 캐시 키로 대조 —
  다음에 생기는 고정 대사도 잡는다) · `::test_사과문은_감독이_보내는_역할과_감정으로_굽는다` ·
  `::test_고정_대사는_큐시트와_감독_고정_멘트를_모두_덮는다`(사과문까지 넓힘, 도슨트 수준 단언은 큐시트 설명으로 좁힘).
- `bake_tts.py --check --engine elevenlabs`(합성 없음) 결과: **534문장 중 530개 구움, 빠진 4문장 = 사과문 둘**.
  → **굽기 필요**: `TTS_ENGINE=elevenlabs ./reachy.sh bake`(약 73자 × 0.5 ≈ 40 크레딧). A-5 의 되묻기 대사와 한 번에 구우면 된다.

## A-3(P0-4) 공연 중 화면 잠자기 막기 — 끝

- `reachy.sh` — `keep_awake`(`caffeinate -dis -w $$` — reachy.sh 자신의 수명, 출력은 버림) · `keep_awake_stop`(정리에서 한 번 더) ·
  `start_sim`/`start_robot` 이 `start_director` 바로 앞에서 부른다. `caffeinate` 가 없으면(리눅스 PC) `WARN 화면 잠자기를 못 막았다 …`
  만 찍고 띄운다. 끄는 스위치 `REACHY_KEEP_AWAKE=0`.
- 테스트: `tests/test_reachy_start.py::test_공연_동안_화면_잠자기를_막는다` · `::test_caffeinate_가_없으면_경고만_하고_띄운다` ·
  `::test_잠자기_방지는_스위치로_끈다` · `::test_잠자기_방지는_감독_바로_앞에서_건다`. `_source` 기본 환경에 `REACHY_KEEP_AWAKE=0`
  (다른 테스트가 진짜 caffeinate 를 띄우지 않게 — 위 테스트만 켠다).
- 실측(이 맥, 1초): 실행 중 `pmset -g assertions` 에 그 pid 로 `PreventUserIdleSystemSleep`·`PreventUserIdleDisplaySleep`·
  `PreventSystemSleep` 세 줄, 실행이 끝난 뒤 그 pid 의 단언 없음·프로세스 끝남. (이 맥에는 다른 프로그램의 300초짜리
  caffeinate 둘이 따로 돌고 있었다 — "우연히 막고 있던" 그것으로 보인다. pid 로 갈라 봤다.)

## A-4(P0-5) 실기 리허설 점검표 — 끝(조율자 검수 필요)

- 새 파일 `docs/rehearsal-checklist.md`. 머리(구성·커밋·주소·크레딧·굽기 현황) → 이번 계획의 새 항목(A-1 빨간 줄 · A-2 사과문 두 번 ·
  A-3 20분 방치 · A-5 되묻기 · A-6 주소 찾기 · C·D 하이라이트 끝까지) → 11-13 의 9가지 → §15.10~15.15 "실기에서 확인할 것" 11줄 →
  E 사전 확인(`probe_hand_raise.py`) → 실패 항목 로그 발췌 칸.
- "로그에서 볼 줄" 은 전부 코드에서 복사했다(`stage/director.py`·`stage/server.py`·`stage/__main__.py`·`reachy.sh`·`tts_cache_proxy.py`·
  `stage/dashboard_page.html`·`apps/voice_chat/voice_chat/voice_loop.py`). 확인하다 안 것: **감독 로그에는 관람객 질문 글이 남지 않는다**
  (조정실 이벤트 로그 `관람객> …` 와 로봇 앱 `나(STT +…s)> …` 에만) — 점검표 ①에 그렇게 적었다. 되묻기 줄(A-5)에는 글이 남는다.
- 조정실 문구(1인 모드 띠·시연 화면 머리 줄)는 B 칸이 조정실을 고치면 달라질 수 있다 — 조율자가 B 를 합친 뒤 ④·⑤ 문구를 한 번 대조한다.

## A-5(P1-6) 질문 판정 — 끝(되묻기 대사 굽기는 조율자)

### 1. 먼저 잰 것
표본: `.demo-logs/*.log` 의 실제 전사(감독 `들린 말을 버린다`·`관람객 질문으로 보지 않는다` 줄 221 + 1대 대화 `나(STT)>` 줄 79,
고유 186 → 진행어·잡음 거른 뒤 129, 그중 짧은 것 92건을 손으로 라벨) + **전시 관람객을 가정한 손 표본 55건**.
실제 로그는 사무실 잡담과 예전 로컬 Whisper 전사라 **전시 관람객의 실제 말이 없다** — 그래서 손 표본을 더했다(물음표 없는 꼴도
넣어 최악을 쟀다). Q = 답해야 한다 44, C = 되물어도 된다 103.

| 후보 | 놓친 질문(Q 를 되묻기) | 되물은 잡담(C 중) |
|---|---:|---:|
| ① 무엇이든 답(지금) | 0/44 | 0/103 |
| ③ 질문 같지 않으면 전부(`not looks_like_question`) | 22/44 | 97/103 |
| ② 길이 ≤5 | 3/44 | 54/103 |
| ② 길이 ≤6 | 9/44 | 59/103 |
| ② 길이 ≤8 | 15/44 | 68/103 |
| ② 길이 ≤10 | 19/44 | 76/103 |
| ② 길이 ≤6 + 요청어(듣고 싶·말해·얘기해·가르쳐·해 줘) | 7/44 | 59/103 |
| ② 길이 ≤6 + 요청어 + 물음 어미(나요·까요·가요·는지·니·냐·던데요·잖아요·는요·은요) | 6/44 | 59/103 |
| ② 길이 ≤6 + 넓힌 요청어(+모르겠·이해가 안·다시) + 넓힌 어미(+봐·줘·주세요·는·은) | 1/44 | 55/103 (손 표본 반응 25/28) |
| **② 길이 ≤7 + 넓힌 요청어·어미 — 채택** | **1/44** | **60/103 (손 표본 반응 26/28)** |
| ② 길이 ≤8 + 넓힌 | 2/44 | 64/103 |
| ② 길이 ≤10 + 넓힌 | 4/44 | 71/103 |

(길이 = 공백·문장부호를 뺀 글자 수.) 남은 놓침 1 = "춤 춰보기"(명사형 요청). ≤8 부터 "휴대폰도 전파 써요"(물음표 없음)를 놓친다.
**주의(과적합)**: 손 표본과 넓힌 요청어·어미를 같은 사람(A 칸)이 만들었다 — 이 표는 방향을 정하는 데 쓰고, 리허설 감독 로그의
`질문으로 보지 않고 되묻는다` 줄로 다시 잰다(점검표 1-4). 측정 스크립트: 스크래치
`/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/A/measure.py`.

### 2. 바꾼 것
- `stage/cues.py` — `needs_reprompt(text)`(물음표·물음말·요청어·물음 어미가 없고 ≤7자일 때만 참) · `REPROMPT_MAX_CHARS = 7` ·
  `QA_REPROMPT_LINES`(사회자 2문장, 돌아가며): "궁금한 점이 있으면 편하게 물어봐 주세요. 이어가려면 '다음'이라고 해 주세요." /
  "무엇이든 편하게 물어봐 주세요. 이어가려면 '다음'이라고 해 주세요."
- `stage/director.py` — 팟캐스트 `on_heard` 에서 진행어·잡음을 거른 뒤 `needs_reprompt` 면 `_reprompt`: 라벨 **`<큐>:reask`(기존 재질문
  라벨)**·감정 `QUESTION_PROMPT_EMOTION` 그대로, 경고 `질문으로 보지 않고 되묻는다: '…' (연달아 한 번 더 말하면 답한다 · 끄기 REACHY_QA_REPROMPT=0)`,
  이력에 관람객 말·되묻기 대사. 그 발화가 끝나면 기존 마지막 갈래가 침묵 기한을 새로 건다. **연달아 두 번째는 답한다**(`_reprompted` —
  답(`_answer`)이나 새 큐(`_begin_cue`)에서 지운다). 단독 모드는 그대로(되묻지 않는다).
  스위치 `REACHY_QA_REPROMPT`(기본 켜짐, `0/off/no/false/끄기` 면 지금 동작, 모르는 값은 켠 채 경고) — `stage/__main__.py` 를 E 전에
  고치지 않으려고 감독 생성자가 직접 읽는다(인자 `qa_reprompt` 가 있으면 그것이 먼저 — 테스트용). 조정실은 건드리지 않았다.
- `scripts/bake_tts.py::fixed_lines` — 되묻기 2문장(사회자, `QUESTION_PROMPT_EMOTION`, where "되묻기").

### 3. 테스트
- `tests/test_stage_cues.py::test_짧은_추임새는_되묻고_평서형_긴_말은_질문으로_둔다`(27) · `::test_질문이나_요청이면_짧아도_되묻지_않는다`(25) ·
  `::test_되묻기_문턱은_한_곳에서_정한다` · `::test_되묻기_대사는_질문을_권하고_다음을_안내한다`
- `tests/test_stage_director.py::test_질문_같지_않은_짧은_말에는_사회자가_되묻고_도슨트는_답하지_않는다` · `::test_되묻기는_기존_재질문_라벨을_쓴다`
  (`stage.say_label.parse_say_label` 로 `reask` 확인) · `::test_연달아_두_번째는_답한다` · `::test_답한_뒤나_새_큐에서는_다시_되묻는다` ·
  `::test_질문이면_짧아도_바로_답한다` · `::test_스위치를_끄면_무엇이든_답한다[인자/환경변수]` · `::test_되묻기_스위치는_기본_켜짐이다` ·
  `::test_단독_모드는_되묻지_않는다`
- 기존 감독 테스트 7개의 자리표시 질문("질문"·"첫 질문"·"둘째 질문"·"질문 있어요"·"질문이요"·"c1 첫/둘째 질문")에 물음표를 붙였다 —
  기본 켜짐에서 물음표·물음말 없는 짧은 말은 되묻기로 가기 때문이다(그 테스트들은 생성 경합·회전·지시문을 본다 — 판정이 아니다).
  하네스 주석에 이유를 남겼다.
- `tests/test_bake_tts.py::test_감독이_LLM_없이_말하는_고정_문장은_전부_굽기_목록에_있다` — 시나리오에 되묻기(추임새 → 되묻기, 연달아 → 답,
  다시 → 둘째 되묻기)를 더했다. 넣기 전에는 되묻기 첫 문장 둘이 "굽기 목록에 없다" 로 실패했다.

### 4. 종단 확인(진짜 감독, 예비 포트 18777/18778, 가짜 로봇 두 대, LLM 주소는 죽은 포트 — 외부 호출 0)
```
관람객> 와 신기하다
   say mc     01-intro:reask     궁금한 점이 있으면 편하게 물어봐 주세요. 이어가려면 '다음'이라고 해 주세요.
관람객> 전파가 뭐예요?
   say mc     01-intro:ack       좋은 질문이네요. 도슨트, 답해 줄래요?
   say docent 01-intro:qa        죄송합니다, 지금은 답을 찾지 못했습니다. 다음으로 넘어가 볼까요?
   say mc     01-intro:reask     궁금한 점 있으실까요? 이어가려면 '다음'이라고 해 주세요.
```
감독 로그: `질문으로 보지 않고 되묻는다: '와 신기하다' (연달아 한 번 더 말하면 답한다 · 끄기 REACHY_QA_REPROMPT=0)` →
`[01-intro:qa] LLM 생성 실패(ConnectionError: …) — 폴백`. 감독 종료코드 0, 18777/18778 비었음, 남은 감독 프로세스 없음.
스크립트·로그: 스크래치 `…/panes/A/e2e_reprompt.py`·`e2e_director.log`. `./reachy.sh start --sim` 한 바퀴는 조율자 몫으로 남긴다(고정 포트·추론 서버를 쓴다).

### 5. 굽기 필요
`bake_tts.py --check --engine elevenlabs`(합성 없음): **536문장 중 530개 구움 — 빠진 6문장 = 사과문 4 + 되묻기 첫 문장 2**
("궁금한 점이 있으면 편하게 물어봐 주세요." · "무엇이든 편하게 물어봐 주세요."). 둘째 문장은 재질문과 같아 이미 있다.
→ `TTS_ENGINE=elevenlabs ./reachy.sh bake` 한 번(약 111자 × 0.5 ≈ 56 크레딧).

## A-6(P1-7) 로봇 주소 — 끝(가짜로만 확인, 실측은 리허설)

- `reachy.sh` — `robot_bringup_one` 이 "안 잡혀서 실패" 를 `ROBOT_LAST_UNREACHABLE` 로 남긴다. `start_robot` 이 그때만 `robot_find_role`:
  `REACHY_ROBOT_FIND_NAMES`(기본 `reachy-mini.local reachy-mini-2.local`)를 `robot_resolve`(파이썬 `socket.getaddrinfo` 를 2초 상한 스레드로 —
  플랫폼 중립, `dns-sd`·`avahi-resolve` 를 박지 않는다)로 풀고, 데몬이 응답하는 주소(`robot_api_up`)마다 **로봇 config 의 REACHY_ROLE**
  (`robot_role_at` — `ssh … cat config.json`, 호스트 키 확인은 끄지 않는다)로 배역을 확인해 **알리기만** 한다:
  `WARN 사회자 로봇이 <빠진 주소> 에 없다 — <주소>(<이름>)에서 찾았다(config 배역 mc). 그 주소로 띄우려면:` +
  `      REACHY_MC_HOST=<찾은 주소> REACHY_DOCENT_HOST=<도슨트 주소> ./reachy.sh start --robot`(**항상 두 주소** — §15.14).
  상대 배역이면 `… 는 config 배역 docent — 사회자가 아니다`, 못 읽으면 `… 에 로봇이 있다 — 배역 미확인(config 를 못 읽었다). 이름으로 추측하지 않는다`,
  찾은 로봇이 상대 자리 주소에 있으면 "두 로봇 주소가 뒤바뀌었을 수 있다(DHCP 예약 확인)", 아무것도 없으면 `이름(… · …)으로도 못 찾았다 — 전원·Wi-Fi 와 공유기 DHCP 예약을 확인한다`.
  **찾은 주소를 쓰지 않는다** — 감독·정리는 원래 배역 주소 그대로, 건너뛰기·1인 모드 안내도 그대로.
- 테스트: `tests/test_reachy_start.py::test_배역_주소가_안_잡히면_이름으로_찾아_새_주소를_알린다` · `::test_찾은_주소를_자동으로_쓰지_않는다` ·
  `::test_배역을_확인_못_하면_추측하지_않는다` · `::test_이름으로도_못_찾으면_그렇게_말한다` · `::test_닿기는_하는데_다른_이유로_못_올리면_찾지_않는다` ·
  `::test_이름_풀기는_플랫폼_중립이고_시간_상한이_있다`(진짜 `localhost` 풀기 + 없는 이름이 상한 안에 끝남).
- 점검표 1-5 에 실측 방법(없는 사회자 주소로 띄우기, 켜는 순서를 바꿔 `-2` 가 바뀌는지 적기)을 넣었다.

## 덤 — 고치다 찾은 것

- `tts_cache_proxy.py::_el_wav` 가 `tts_elevenlabs.synth` 의 **본문 읽기 중 시간 초과**(머리를 받은 뒤 — `ElevenLabsError` 로 감싸지 않는다)를
  못 잡아 처리기가 죽고 **502 도 없이** 연결이 끊겼다. 잡아서 502 + `upstream: timeout` 으로. 테스트
  `tests/test_tts_elevenlabs.py::test_외부_전용_wav_본문이_도중에_끊겨도_502_로_답한다` — 고치기 전 코드로 되돌려 빨간 것을 확인했다.
- `tests/test_reachy_start.py::test_공연_동안_화면_잠자기를_막는다` 가 A 파일 묶음과 함께 돌 때 한 번 빨개졌다(단독 5회는 초록) —
  가짜 caffeinate 의 기록·종료를 고정 0.3/0.2초로 기다렸다. 최대 3초 폴링으로 바꿨다.

---

## 조율자에게

### 1. 바꾼 파일 (모두 §2.2 A 열 — 표 밖 파일은 고치지 않았다)
| 파일 | 갈래 |
|---|---|
| `openai_gateway.py` | A-1 |
| `tts_cache_proxy.py` | A-1(+ 본문 끊김 502) |
| `scripts/warmup.py` | A-1 |
| `reachy.sh` | A-1 · A-3 · A-6 |
| `run-app.sh` | A-1(주석 한 줄) |
| `scripts/bake_tts.py` | A-2 · A-5 |
| `stage/cues.py` | A-5 |
| `stage/director.py` | A-5 |
| `tests/test_openai_gateway.py` · `tests/test_tts_elevenlabs.py` · `tests/test_reachy_start.py` · `tests/test_bake_tts.py` · `tests/test_stage_cues.py` · `tests/test_stage_director.py` | 테스트 |
| **새 파일** `tests/test_warmup.py` | A-1 테스트(계획 A-1 3에 "새 `tests/test_warmup.py`(A 소유)" 로 적혀 있다) |
| **새 파일** `docs/rehearsal-checklist.md` | A-4 |
| **새 파일** `docs/superpowers/plans/2026-11-14-show-readiness-A.md` | 이 보고 |

`tests/test_tts_cache_proxy.py` 는 돌리기만 했고 고치지 않았다. git 은 건드리지 않았다.

### 2. 돌린 테스트 · 실측 · 캡처
- A 소유 9개 파일 한 번에: `.venv/bin/python -m pytest -q tests/test_stage_director.py tests/test_stage_cues.py tests/test_bake_tts.py tests/test_reachy_start.py tests/test_run_app.py tests/test_openai_gateway.py tests/test_tts_elevenlabs.py tests/test_tts_cache_proxy.py tests/test_warmup.py`
  → **747 passed, 70.3초**. `bash -n reachy.sh`·`run-app.sh` 통과. 새 테스트는 전부 먼저 써서 빨간 것을 보고 구현했다.
- **전체 묶음은 안 돌렸다**(규칙). 감독 기본 동작이 바뀌었다(되묻기 기본 켜짐) — A 밖에서 감독에 `on_heard` 를 넣는 테스트를 grep 했고
  (`tests/test_stage_server.py` "마르코니가 누구예요"·"다음"·hello 전 "안녕", `tests/test_stage_main.py` "그건 왜 그런가요?", `tests/test_research.py` 질문,
  `tests/test_say_label.py` "다음") 짧은 비질문은 없었다 — 그래도 전체 묶음에서 한 번 봐 달라.
- 실측(외부 호출 0):
  - A-3: 진짜 `caffeinate` 1초 — 실행 중 그 pid 의 잠자기 방지 단언 3줄, 끝난 뒤 없음(위 A-3 절).
  - A-5: 진짜 감독을 예비 포트 18777/18778 로 띄워 가짜 로봇 두 대로 종단 확인(위 A-5 4절). 끝난 뒤 포트 비었음·프로세스 없음.
  - A-2·A-5: `bake_tts.py --check --engine elevenlabs`(합성 없음) — 536문장 중 530 구움, 빠진 6 = 사과문 4 + 되묻기 2.
- 스크래치(저장소 밖): `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/A/`
  — `measure.py`(A-5 표), `filter.py`·`stt_app.txt`·`stt_director.txt`(로그에서 뽑은 전사), `e2e_reprompt.py`·`e2e_director.log`(종단 확인), `show_warmup.py`(A-1 화면 예).

### 3. `docs/lessons.md` 초안
1. **예열 실패를 "건너뜀" 한 줄로 삼키면 공연 직전에 키 만료·잔액 부족을 모른다(2026-11-14)**
   - 증상: 외부 전용에서 OpenAI 키가 틀려도 기동 화면은 흐린 `LLM … 건너뜀 (HTTPError)` + "일부 예열을 건너뛰었다" 뿐이었다(계획 조사).
   - 원인: 게이트웨이가 외부 전용 502 에 이유를 싣지 않아(`{"error":"no-local"}`) 예열 쪽에서 401·429·연결 실패를 가를 수 없었다. 이유는 게이트웨이 로그에만.
   - 규칙: 실패를 돌려주는 서버는 **종류**(401·429·5xx·4xx·connect·timeout)를 본문·머리(`X-Reachy-Upstream`)에 싣고 **메시지 글은 싣지 않는다**(키 조각).
     예열은 외부 전용에서 종류별 할 일 + "안 되는 것" 을 빨간 줄로, 감독 콘솔 직전·감독 로그 머리에 한 번 더. 멈추지는 않는다(대본은 캐시로 돈다).
   - 테스트: `tests/test_openai_gateway.py::test_외부_전용_502_는_실패_종류를_싣고_메시지는_싣지_않는다`, `tests/test_tts_elevenlabs.py::test_외부_전용_wav_실패는_실패_종류를_싣는다`,
     `tests/test_warmup.py::test_외부_전용_예열_실패는_종류와_안_되는_것을_말한다`, `tests/test_reachy_start.py::test_외부_전용_예열이_실패하면_빨간_묶음으로_다시_보이고_감독_로그_머리에_남긴다`
2. **굽기 목록을 손으로 맞추면 고정 대사가 빠진다 — 사과문 둘이 그렇게 빠졌다(2026-11-14)**
   - 증상: 인터넷이 끊기면 두 번째 질문부터 무음(LLM 실패 → 사과문 → 캐시 빗나감 → ElevenLabs 실패 → 안내는 15초에 한 번).
   - 원인: `fixed_lines` 가 큐시트·확인 멘트·재질문·단독 멘트를 이름으로 나열했고 사과문 상수(`QA_FALLBACK`·`SOLO_FALLBACK`)는 감독 모듈에 따로 있었다.
   - 규칙: 고정 대사 전수는 **감독을 돌려서** 잰다 — 생성을 일부러 실패시키면 감독이 내보내는 say 는 전부 고정 문장이다. 그 (역할·문장·감정)의 캐시 키가 굽기 계획에 있어야 한다.
   - 테스트: `tests/test_bake_tts.py::test_감독이_LLM_없이_말하는_고정_문장은_전부_굽기_목록에_있다`
3. **`tts_elevenlabs.synth` 는 본문 읽기 중 끊김을 감싸지 않는다 — 프록시 처리기가 죽어 502 도 없이 끊겼다(2026-11-14)**
   - 원인: `open_stream` 은 머리까지의 실패만 `ElevenLabsError` 로 감싼다. `synth` 의 `r.read()` 시간 초과는 맨 `TimeoutError` 로 나온다.
   - 규칙: 외부 호출을 감싸는 자리는 `OSError`·`HTTPException` 까지 잡아 실패 경로(502 + 종류)로 보낸다.
   - 테스트: `tests/test_tts_elevenlabs.py::test_외부_전용_wav_본문이_도중에_끊겨도_502_로_답한다`(고치기 전 빨강 확인)
4. **감독 로그에 관람객 질문 글이 없다 — 질문 판정 문턱을 잴 표본이 없었다(2026-11-14)**
   - 증상: A-5 측정에서 `start-director.log` 의 전사는 "듣는 중이 아닐 때 버린 말"·"잡음" 뿐이었다. 답한 질문의 글은 조정실 이벤트(`관람객> …`)·로봇 앱 로그에만 남는다.
   - 규칙(이번에 한 것): 판정이 답하지 않은 말은 감독 로그에 글째 남긴다(`질문으로 보지 않고 되묻는다: '…'`). 답한 질문도 남길지는 아래 "결정 필요" 6.
5. **셸 테스트에서 가짜 백그라운드 프로세스를 고정 시간으로 기다리면 묶음 실행에서 빨개진다(2026-11-14)**
   - 규칙: 기록·종료를 최대 N초 폴링으로 기다린다. 테스트 `tests/test_reachy_start.py::test_공연_동안_화면_잠자기를_막는다`

### `docs/real-robot-deployment.md` 초안
- **§15.13 끝에 — 사전 점검·사과문(2026-11-14)**: 기동 예열이 외부 API 를 실제로 한 번씩 부른다. 외부 전용에서 실패하면 빨간 `FAIL` 묶음으로 무엇이 왜 안 되는지
  (401 = `.env` 키, 429 = 잔액 또는 분당 한도, connect/timeout = 인터넷, 5xx = 업체 일시 오류)와 공연에서 안 되는 것(관람객 질문 답 · 음성인식 · 관람객 답 목소리)을
  말하고 **계속 띄운다**(대본은 캐시). 같은 줄이 감독 콘솔 직전과 감독 로그 머리(`사전 점검 실패: …`)에도 남는다. 멈추게 하려면 `REACHY_PREFLIGHT=stop`.
  `TTS_ENGINE=elevenlabs` 면 남은 크레딧을 찍는다(10,000 아래 WARN, 2,000 아래 FAIL — 관람객 답 하나 약 100). 사과문 둘(질문 답 · 단독 답)도 굽기 목록에 있다 —
  인터넷이 끊겨도 사과문이 매번 들린다(1인 모드 + 인터넷 끊김은 남은 로봇 목소리라 캐시가 빗나가 안내 한 번 뒤 무음 — 알려진 한계).
- **§15.12 또는 §15.13 에 — 공연 PC 잠자기**: `start` 가 감독 바로 앞에서 `caffeinate -dis -w <reachy.sh pid>` 를 건다(끝나면 풀린다). 맥이 아니면 경고만 —
  공연 PC 의 OS 설정에서 화면 끄기·잠자기를 끈다. 끄는 스위치 `REACHY_KEEP_AWAKE=0`.
- **§15.14 에 — 주소 찾기와 DHCP 예약**: 배역 주소가 핑 3번에 안 잡히면 `reachy-mini.local`·`reachy-mini-2.local` 을 풀어 응답하는 로봇의 **config 배역**(REACHY_ROLE)을
  읽어 알린다 — 찾은 주소는 쓰지 않는다(두 대의 hostname 이 같아 `-2` 는 켠 순서로 바뀔 수 있다). 새 주소는 ssh 호스트 키가 없어 "배역 미확인" 일 수 있다 —
  `ssh pollen@<주소>` 로 한 번 붙어 키를 받는다.
  **공유기 DHCP 예약(사용자 작업, U4 ①)**: 공유기 관리 화면 → DHCP(주소 할당) → 고정 할당(예약) → 로봇 Wi-Fi 의 MAC 주소(로봇에서 `ip link show wlan0` 의
  `link/ether` 값)를 사회자 192.168.0.4 · 도슨트 192.168.0.5 에 묶는다 → 로봇을 재부팅하고 `ping 192.168.0.4`·`.5` 로 확인 → 리허설 점검표 1-5(b).
  hostname 을 서로 다르게 바꾸는 것(U4 ③)은 다음 재배포 때.
- **§15.15 에 — 되묻기**: 질문 창에서 짧고(공백·문장부호 빼고 7자 이하) 질문 같지 않은 말(물음표·물음말·요청어·물음 어미 없음 — "와 신기하다"·"감사합니다")에는
  도슨트 답 대신 사회자가 "궁금한 점이 있으면 편하게 물어봐 주세요. 이어가려면 '다음'이라고 해 주세요." 로 되묻는다. 연달아 한 번 더 말하면 답한다.
  감독 로그 `질문으로 보지 않고 되묻는다: '…'` 로 놓친 질문을 찾는다. 끄기 `REACHY_QA_REPROMPT=0`(명령 앞에). 발화 라벨은 재질문(`:reask`) 그대로라 화면은 바뀐 것이 없다.

`CLAUDE.md` 명령 표에 넣을 만한 것(바뀐 것만): `REACHY_QA_REPROMPT=0 ./run-app.sh`(되묻기 끄기) · `REACHY_PREFLIGHT=stop`(사전 점검 실패에서 멈춤) ·
`REACHY_KEEP_AWAKE=0`(잠자기 방지 끄기) · `docs/rehearsal-checklist.md`(리허설 점검표).

### 4. 결정 필요 — 권장안으로 진행한 것
1. **되묻기 문턱**(A-5): 측정의 무릎점 "≤7자 + 넓힌 요청어·어미" 로 했다. 손 표본·규칙을 같은 사람이 만들어 과적합 위험 — **리허설 로그로 다시 잰다**(점검표 1-4).
2. **되묻기 대사 문구 2개**: "궁금한 점이 있으면 편하게 물어봐 주세요. 이어가려면 '다음'이라고 해 주세요." / "무엇이든 편하게 물어봐 주세요. 이어가려면 '다음'이라고 해 주세요."
   — 계획의 예를 그대로 + 하나. **굽기 전에** 사용자가 문구를 보고 싶으면 지금 바꾸는 것이 싸다(구운 뒤 바꾸면 다시 굽는다).
3. `REACHY_PREFLIGHT=stop` 스위치를 만들었다(U1 ②를 고를 수 있게 — 기본은 warn = U1 ①).
4. 크레딧 줄은 외부 전용만이 아니라 `TTS_ENGINE=elevenlabs` 면 섞인 구성에서도 찍는다(관람객 답이 ElevenLabs 로 나가므로).
5. 주소 찾기의 ssh 는 **호스트 키 확인을 끄지 않았다** — 새 주소면 "배역 미확인" 이 될 수 있다(그때 손으로 한 번 붙으면 된다). 끄면 편하지만 공유기 밖 기계에도 키 없이 붙는다.
6. (제안) 감독 로그에 **답한 관람객 질문 글**도 한 줄 남길지 — 문턱을 다시 잴 표본이 생긴다. 관람객 말이 로그 파일에 남는 것이라(이미 조정실 이벤트·로봇 앱 로그에는 있다)
   사용자 결정이 필요하고, 고칠 곳은 `stage/server.py`(A 밖)다.

### 5. 남은 일 · 다른 칸/조율자 파일에서 본 것
- **굽기(조율자, 외부 호출)**: `TTS_ENGINE=elevenlabs ./reachy.sh bake --check` → 빠진 6문장 확인 → `TTS_ENGINE=elevenlabs ./reachy.sh bake`(약 56 크레딧). 결정 4-2 문구가 확정된 뒤.
- **A-1 실측(조율자, 외부 호출)**: `.env` 키를 일부러 틀린 값으로 둔 채 예비 포트 기동 → 빨간 줄 3종 · 감독 로그 머리 · `grep sk- .demo-logs/*.log` 새 줄 0.
- **A-5 시뮬 한 바퀴**: `./reachy.sh start --sim` 에서 "와 신기하다" → 되묻기, "전파가 뭐예요" → 답(고정 포트·추론 서버를 써서 조율자와 시간을 맞춰야 한다 — 나는 예비 포트 종단 확인으로 대신했다).
- **A-4 점검표 검수**: 조정실 문구(④ 시연 화면 머리 줄, ⑤ 1인 모드 띠)는 B 가 조정실을 고치면 바뀔 수 있다 — B 를 합친 뒤 한 번 대조.
- **화면(조율자 소유 `live_follow.js`·`tests/test_live_stage.py`)**: 되묻기는 확인 멘트·답 없이 **`<큐>:reask` 하나만** 나간다. `reask` 는 이미 질문 흐름 라벨(`stage/say_label.py::QA_TURNS`)이라
  화면이 장면을 멈추고 배지를 바꿀 것으로 보지만, "ack·qa 없이 reask 만" 오는 순서를 화면이 받아 다음 큐에서 다시 따라가는지는 **확인하지 못했다** —
  통합 테스트에 한 경우 넣어 볼 만하다. `fake_show.py --qa` 는 이 순서를 흘리지 않는다.
- **`tts_elevenlabs.py`(A 밖)**: `synth()` 가 본문 읽기 끊김을 `ElevenLabsError` 로 감싸지 않는다 — 프록시는 이번에 잡았지만 **굽기**(`bake_tts.py` → `synth`)에서는 그 끊김이
  재시도 없이 트레이스백으로 굽기를 멈출 수 있다. `synth` 안에서 감싸 재시도에 태우는 것이 근본 고침이다(파일 소유자에게).
- E(카메라 답하기)는 하지 않았다(U9 — 이번 칸들은 E 를 하지 않는다).

---

## 조율자에게 (2차) — 답한 관람객 질문을 감독 로그에 한 줄(결정 6 = 남긴다)

### 1. 바꾼 파일
| 파일 | 무엇 |
|---|---|
| `stage/director.py` | 기록 전용 채널 `note`(생성자 인자, 기본 `print(…, flush=True)`) · `_question_note()` · `_answer`(팟캐스트)와 `_solo_answer`(단독)에서 한 줄 |
| `tests/test_stage_director.py` | 하네스가 `note` 를 모은다(`h.notes`) + 새 테스트 6개 |
| `docs/rehearsal-checklist.md` | 1-4 에 `관람객 질문:` 줄과 리허설 뒤 표본 뽑는 명령 |
| 이 보고 파일 | 이 절 |

**`stage/server.py` 는 고치지 않았다** — 서버는 `heard` 를 감독에 넘길 뿐 감독이 답했는지(되묻기·진행어·잡음·듣는 중 아님)를 모른다.
"답한 말" 만 남기려면 판정이 끝나는 자리, 감독의 `_answer` 가 맞다. 서버 테스트도 그대로다.

### 2. 어떻게 남나
- 줄 모양: `관람객 질문: '전파가 뭐예요?'` · 단독 답은 `관람객 질문(단독): '…'`. **관람객 말 글만** 싣는다(녹음·키·큐 id 등 그 밖의 것 없음).
  `repr` 로 감싸 언제나 한 줄 — 전사에 줄바꿈이 섞여도 다음 줄이 감독 출력처럼 보이지 않는다.
- 되묻기·진행어("다음")·잡음·듣는 중이 아닐 때 버린 말은 **남기지 않는다**(답하지 않은 말 — 되묻기는 원래대로 경고 줄 `질문으로 보지 않고 되묻는다: '…'`).
  되묻기 뒤 연달아 답한 말은 남는다.
- **조정실 경고(warn → 허브)로 보내지 않았다.** 조정실은 `warn` 줄을 경고 모양으로 그리고(`isWarnLine`), 들은 말은 이미 `관람객> …` 로 보여 준다 —
  질문마다 경고 줄이 생기면 진짜 경고가 묻히고, B 칸의 "가린 패널 문제 표시" 와도 엉킬 수 있다. 감독 로그 파일은 감독 표준출력을
  `reachy.sh::start_director` 가 tee 로 받은 것이라 `print` 면 파일에 남는다(`stage/__main__.py` 의 "정보성 출력은 print 그대로" 와 같은 결).
  관람객 소켓(`/ws/audience`)은 원래 warn·heard 를 안 흘린다 — 종단 확인에서도 0건.
- 파일은 이 PC 의 `.demo-logs/start-director.log`(`.gitignore` 에 있다 — 저장소로 안 간다). 2MB 넘으면 한 세대만 남기고 넘긴다(기존 규칙).

### 3. 테스트(먼저 써서 빨간 것을 보고 구현)
- `tests/test_stage_director.py::test_답한_관람객_질문은_감독_로그에_한_줄_남긴다`(warn 에는 없음까지) · `::test_답하지_않은_말은_질문으로_남기지_않는다`(말하는 중·잡음·되묻기·진행어) ·
  `::test_되묻기_뒤_연달아_답한_말도_남긴다` · `::test_단독_답도_단독이라고_구분해_남긴다` · `::test_질문_줄은_언제나_한_줄이다` ·
  `::test_질문_기록은_기본으로_감독_표준출력에_찍힌다`(하네스 없이 — 기본 채널이 print 인지)
- 돌린 것(감독을 쓰는 관련 파일만): `tests/test_stage_director.py tests/test_stage_server.py tests/test_stage_main.py tests/test_research.py tests/test_say_label.py tests/test_bake_tts.py tests/test_stage_console.py`
  → **403 passed, 8.2초**. 전체 묶음은 안 돌렸다.
- 종단 확인(진짜 `python -m stage`, 예비 포트 18777/18778, 가짜 로봇 두 대, LLM 은 죽은 포트 — 외부 호출 0, 조정실 `/ws`·관람객 `/ws/audience` 도 붙여 봄):
  ```
  무대감독> 질문으로 보지 않고 되묻는다: '와 신기하다' (연달아 한 번 더 말하면 답한다 · 끄기 REACHY_QA_REPROMPT=0)
  관람객 질문: '대박'
  관람객 질문: '전파가 뭐예요?'
  ```
  조정실 소켓 warn 중 `관람객 질문` 0건(받은 메시지 102), 관람객 소켓에 질문 글 0건(41). 감독 종료코드 0, 포트 비었음, 남은 감독 없음.
  스크립트·로그: 스크래치 `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/A/e2e_question_log.py`·`e2e_director.log`.
  점검표의 표본 뽑기 명령도 그 로그로 돌려 세 줄이 나오는 것을 확인했다.

### 4. 문서 초안
- `docs/real-robot-deployment.md` §15.15 에 한 줄: "답한 관람객 질문은 감독 로그에 `관람객 질문: '…'` 한 줄로 남는다(글만 · 녹음 없음 · 조정실·관람객 화면에는 안 간다 ·
  `.demo-logs/` 는 저장소 밖). 리허설 뒤 되묻기 줄과 함께 모아 문턱을 다시 잰다 — 뽑는 명령은 `docs/rehearsal-checklist.md` 1-4."
- `docs/lessons.md`: 새 버그는 없다. (넣는다면) "판정 문턱을 잴 표본은 판정이 끝나는 자리에서 남긴다 — 서버의 heard 는 답했는지 모른다" 정도.

### 5. 결정 필요 · 남은 일
- 결정 필요 없음. 권장안으로 고른 것: 조정실 경고로는 보내지 않음(위 2), 단독 답도 `(단독)` 으로 남김(문턱 표본에서는 거르면 된다).
- 관람객 말이 PC 로그 파일에 남는다는 것을 전시장 안내문(U11)에 넣을지는 사용자·조율자 판단 — 지금 안내문 계획은 카메라(E)만 다룬다.
