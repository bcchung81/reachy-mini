# ElevenLabs TTS 전환 — 키 배선·오디션·굽기·실시간 (구현 계획)

2026-11-12. 근거: `docs/handoff/2026-11-10-frontier-ai-transition.md`(배경) · `docs/handoff/2026-11-12-after-elevenlabs-subscription.md`(할 일 A1~A6).
**로봇 재배포 없음** — 로봇은 지금 주소(`:8099`)·지금 요청 본문 그대로다. 바뀌는 것은 전부 PC 쪽이다.

## 실측한 사실 (2026-11-12, 이 계정 API로 읽음)

| 사실 | 값 | 어떻게 |
|---|---|---|
| 구독 | `creator` · active · **월 131,000 크레딧** · 갱신 2026-12-12 · 다음 청구 $22 | `GET /v1/user/subscription` |
| 초과 사용 | **불가**(`can_extend_character_limit: False`) — 한도가 바닥나면 합성이 실패한다 | 같은 응답 |
| 모델 배수 | `eleven_v4` 글자당 **1.0** 크레딧 · `eleven_v4_turbo` **0.5**. 둘 다 한국어, 요청당 최대 1만 자, 동시성 그룹 `standard_eleven_v4` 공유 | `GET /v1/models` |
| 환산 | v4로 월 13.1만 자, Turbo로 26.2만 자. **11-10 문서의 "Creator 55만 자"는 틀렸다** | 위 두 값 |
| 굽기 비용 | 528문장 19,127자 → v4 약 1.9만 크레딧(월 15%) · Turbo 약 1만(7%) | 캐시 색인 집계(11-10) |
| 실시간 추정 | 11-10 문서 가정(월 33만 자 = 하루 6회 × 22일 × 2,500자)을 Turbo로 바꾸면 16.5만 크레딧 → **Creator 한도를 넘는다.** 실제 운영 횟수로 다시 셈해야 한다(가정이 틀렸을 수 있다) | 계산 |
| 목소리 | 라이브러리 한국어 300개 중 예고 기간 730일이 281개. Seulki·Selly Han·Hyein·Anna Kim·Stella·Jeonggi 모두 730일. **Jennie(Narrational)는 예고 기간 미설정** | `GET /v1/shared-voices` |
| 내 목소리 | 0 / 30 슬롯 | 구독 응답 |
| 로봇 요청 | `{input, model:"tts", voice:"serena"/"sohee", speed, instructions?, stream:true, response_format:"pcm"}` | `tts._qwen_body` |

## 범위와 멈추는 자리

| 단계 | 할 일 | 멈추는 자리 |
|---|---|---|
| **1단계(승인 즉시)** | A1 키 배선 · A2 오디션 | **사용자 청취** — 목소리·굽기 모델·속도를 정해야 다음으로 간다 |
| 2단계(목소리 확정 뒤 이어서) | A3 굽기 엔진 + 528문장 굽기 · A4 프록시 실시간 경로 · A5 종이 무대 재빌드 | 사용자 재청취(발음) · 종이 무대 확인 |
| 3단계(실기 일정) | A6 리허설 | — |

## 구조

```
로봇 ─POST :8099─▶ tts_cache_proxy.py ─ 적중 → cache-elevenlabs/{키}.pcm(지금과 같은 응답 형식)
                      └ 빗나감 ─┬ TTS_ENGINE=elevenlabs → tts_elevenlabs.py → api.elevenlabs.io(pcm_24000 스트림)
                                └ 기본(crispasr)        → 지금처럼 CrispASR 127.0.0.1:8098
scripts/bake_tts.py --engine elevenlabs ─ 같은 번역 함수 ─▶ cache-elevenlabs/
scripts/el_audition.py ─ 후보 × 대본 문장 × 모델 ─▶ 저장소 밖 WAV + 나란히 듣는 HTML
```

## 결정 세부

| 항목 | 결정 |
|---|---|
| 키 읽기 | `tts_elevenlabs.load_api_key()` — 환경변수 `ELEVENLABS_API_KEY`가 먼저, 없으면 저장소 루트 `.env`에서 **그 한 줄만** 파싱한다(파일을 `source` 하지 않는다). 키를 쓰는 프로세스는 프록시·굽기·오디션뿐이다. `reachy.sh`는 셸에 export 하지 않는다 → 앱·로봇 쪽으로 새지 않는다. 로그·예외에는 "설정됨/없음"만 |
| 스위치 | `TTS_ENGINE=elevenlabs`(기본 `crispasr` = **지금과 바이트 동일**). 켰는데 키가 없으면 경고 한 줄 + crispasr로 물러난다(실패는 소리 내서) |
| 캐시 폴더 | 엔진이 elevenlabs면 기본 `$TTS_ASSETS/cache-elevenlabs`. `index.json`에 `"engine"` 표지를 둔다. 굽기는 **다른 엔진 표지가 있는 폴더에는 굽지 않는다**. 프록시는 기동 때 엔진과 폴더 표지가 다르면 경고한다(옛 Qwen 소리와 섞이는 사고 방지) |
| 번역 | 로봇 본문 → ElevenLabs 요청. 목소리 이름 → ID(`TTS_EL_VOICES="serena=<id>,sohee=<id>"`), 모델(굽기 `TTS_EL_MODEL_BAKE` 기본 `eleven_v4`, 실시간 `TTS_EL_MODEL_LIVE` 기본 `eleven_v4_turbo`), `output_format=pcm_24000`. `speed`는 v4가 받으면 쓰고 아니면 버린다(오디션에서 확인). `instructions`는 이번엔 쓰지 않고 한 번 경고한다(어조 스위치는 기본 꺼짐). **캐시 키는 번역 전 로봇 본문으로** 계산한다 |
| 읽기 표기 | `data/tts_readings.yaml` — 원문 낱말 → 읽는 표기(예: GMDSS → 지엠디에스에스). 번역할 때만 적용한다. 캐시 키·대본은 그대로 |
| 굽기 | 한 번에 1건(동시성 5개 중 실시간 몫을 남긴다), 429·5xx는 지수 대기 3회, 지원되면 `seed` 고정. 진행 줄에 크레딧 누계. `--check`·`--limit`·`--level` 그대로. **`--force`는 엔진이 elevenlabs면 확인 문구 없이는 거부**(검수 끝난 테이크가 날아간다) |
| `reachy.sh` | `TTS_ENGINE`를 프록시·`bake`에 넘긴다. elevenlabs면 `bake`가 CrispASR를 띄우지 않는다. 기동 화면에 "TTS 엔진 elevenlabs · 키 설정됨 · 캐시 …(n/528)" 한 줄 |
| 헬스 | elevenlabs 모드의 `/health`는 키가 있고 캐시 폴더가 열리면 200. 요청마다 외부를 부르지 않는다. `engine` 필드를 싣는다 |
| 실시간 실패 | **[결정 2026-11-12] 기본 = ① `notice`** — 미리 구운 같은 목소리 안내 한 번("잠시 연결이 고르지 않네요. 다시 이어 갈게요." — 문구 확인 필요) 뒤, 15초 안의 나머지 문장은 빈 소리로 넘긴다. ② `local`(CrispASR·Qwen으로 계속, 목소리가 바뀜)은 `TTS_EL_ON_FAIL=local`로만 켠다. 어느 쪽이든 경고 한 줄 |
| 오디션 | `scripts/el_audition.py` — 후보 × **실제 대본 문장**(고정 대사에서 "1901"·"VLF"·"GMDSS"·"메가헤르츠"가 든 문장, 초등 1문장, 사회자 오프닝 1문장) × `eleven_v4`·`eleven_v4_turbo` → WAV, 나란히 듣는 HTML 한 장. 출력은 `~/.local/share/reachy-mini-tts/audition/2026-11-12/`(저장소 밖). 라이브러리 목소리를 API에서 바로 못 쓰면 "내 목소리"에 추가한다(30슬롯 중 10개 이하, 확정 뒤 안 쓰는 것은 지운다). `speed`·`language_code`를 v4가 받는지도 여기서 한 번 잰다 |

## 오디션 후보 — 예고 730일, 별도 요율 없음

| 역할 | 후보 |
|---|---|
| 사회자(밝은 진행) | Stella "Steady, Clear and Cheerful" `1YzIw7PZ7iaD4alelyHY` · JY "Trendy, upbeat" `bQlkYuipD5BHEhntA5iz` · Yooni "Natural & Clear" `n2fbxG88jqAoaVPUy3IG` · Jennie "Narrational" `z6Kj0hecH20CdetSElRT`(**예고 미설정** — 비교용만) |
| 도슨트(차분한 해설) | Seulki `ksaI0TCD9BstzEzlxj4q` · Selly Han `ETPP7D0aZVdEj12Aa7ho` · Hyein `6Vgh4FaCc0SCcWPwcyXa` · Anna Kim `uyVNoMrnUku1dZyVEXwD` |
| 남성 대안 | Jeonggi(교육) `HCANy6ACvOWyndVWS0gV` · Juan "Deep, Clear, Edu" `hjCvGtSCRPyjYwe2lDf1` |

비용: 목소리 10개 × 문장 약 200자 × (v4 1.0 + Turbo 0.5) ≈ 3천 크레딧(월 2~3%).

## 이번 달 크레딧 예산

오디션 약 3천 + 굽기 약 1.9만(v4) + 발음 다시 굽기 약 3천 + 실시간 시험 약 5천 ≈ **3만 / 13.1만**. 굽기 전에 남은 크레딧을 읽어 모자라면 멈춘다.

## 테스트 — `tests/test_tts_elevenlabs.py`(새 파일) + 기존 확장

- 키: 환경변수가 먼저 · `.env`에서 그 한 줄만 · 없으면 None · **로그·예외 문자열에 키 값이 없다**
- 기본(스위치 없음): 기존 `test_tts_cache_proxy.py`·`test_bake_tts.py`가 그대로 통과(지금과 같은 동작)
- 번역: serena→ID, 모델, `pcm_24000`, 읽기 표기 적용, 목소리 매핑이 없으면 크게 실패
- 캐시 키: 엔진·읽기 표기와 무관하게 로봇 본문으로 같다
- 엔진 표지: 다른 엔진 폴더에 굽기 거부 · 프록시가 불일치를 경고
- 프록시 elevenlabs 모드(가짜 ElevenLabs 서버): 적중은 지금과 같다 · 빗나감은 가짜 서버의 PCM을 스트리밍으로 · 서버가 죽으면 정책대로 + 경고 한 줄
- 스위치를 켰는데 키가 없음: 경고 + crispasr로

## 바꾸는 파일

- 신규: `tts_elevenlabs.py` · `scripts/el_audition.py` · `data/tts_readings.yaml` · `tests/test_tts_elevenlabs.py`
- 수정: `tts_cache_proxy.py` · `scripts/bake_tts.py` · `reachy.sh` · `docs/real-robot-deployment.md`(§15.9 다음 새 절) · 핸드오프 문서 2개(요금 환산 정정)
- **안 바꾼다**: `apps/`(로봇 앱) · `data/cues.yaml`(대본) · 옛 캐시 `cache/`

## 실기에 올리면 무엇이 깨지나

없다. 로봇은 주소·본문이 그대로고 키도 모른다. PC가 인터넷을 잃으면 고정 대사는 캐시로 계속 나가고, 실시간 답은 D4 정책대로 간다. 경고는 `tts-proxy.log`에 남는다.
