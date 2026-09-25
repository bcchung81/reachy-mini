# TTS 결과 캐시 — PC 캐시 프록시 + `bake` (구현 계획)

2026-09-25. 결정: `docs/superpowers/specs/2026-09-25-next-steps-decisions.md`(Q&A). 진행 방식(사용자 지시):
TDD 없이 직접 구현, 구현 뒤 회귀 테스트로 박제. **로봇 재배포 없음**(로봇은 지금 주소 `:8099` 그대로).

## 실측한 사실 (설계의 전제)

| 사실 | 값 | 어떻게 |
|---|---|---|
| 로봇 요청 | `session.speak` → `clauses.split_sentences` → 문장마다 `tts._qwen_body(s, None, stream=True)` = `{input, model:"tts", voice, speed(float), instructions?, stream:true, response_format:"pcm"}` | 코드 읽기 |
| 화자·배속·어조 출처 | 요청마다 설정 사다리. 무대 모드는 `main.apply_role_voice(role)` 가 `ROLE_VOICE` 를 환경변수로(설정파일 값이 있으면 그것이 이김). 감정 어조는 `REACHY_EMOTION_TTS`(기본 꺼짐) | 코드 읽기 |
| 스트리밍 응답 | `200 · Transfer-Encoding: chunked · Content-Type: audio/pcm`, `X-Sample-Rate` 없음(로봇은 24000 기본) | 임시 CrispASR 실측 |
| **결정성** | 같은 요청 두 번의 PCM SHA1 동일 — 캐시 재생 = 실시간 합성과 바이트 단위로 같다 | 실측 |
| 굽기 분량 | 고정 대사 526문장(사회자 113 + 도슨트 4수준 413), 오디오 약 64분, 굽기 약 38분(RTF 0.6 가정) | 큐시트 집계 |

## 구조

```
로봇 ──POST :8099──▶ tts_cache_proxy.py ──(빗나감: 스트리밍 그대로)──▶ CrispASR 127.0.0.1:8098
                         │ 적중: 캐시 PCM 을 audio/pcm 청크로(합성 서버를 안 거친다)
                         └ ~/.local/share/reachy-mini-tts/cache/{키}.pcm · index.json
scripts/bake_tts.py ──(로봇 함수로 본문을 만들어 업스트림에 직접)──▶ 캐시에 씀
```

## 결정 세부

| 항목 | 결정 |
|---|---|
| 키 | 본문 JSON 을 파싱해 `sort_keys` 로 다시 직렬화한 SHA-256. 키 함수는 프록시 모듈 **한 곳**, 굽기가 import |
| 저장 | 스트리밍 PCM 요청만(로봇 기본 경로). 비스트리밍(wav)은 늘 통과 |
| 적중 응답 | `audio/pcm` chunked, 4096바이트 청크, `X-TTS-Cache: hit` |
| 빗나감 | 업스트림으로 스트리밍 통과(받는 대로 씀), 저장하지 않음, `X-TTS-Cache: miss` |
| 드리프트 경고 | 굽기가 남긴 색인에 있는 **고정 대사인데 키가 다르면** 문장당 한 번 경고(굽기 화자·배속·어조 vs 요청) — 로봇 설정이 바뀌어 조용히 전부 빗나가는 것을 막는다 |
| 색인 갱신 | 프록시가 `index.json` mtime 을 보고 다시 읽는다 — `bake` 뒤 재기동 불필요 |
| 업스트림 장애 | `/health` 503, 합성 502 + 경고. 로봇은 지금과 같은 TTS 실패 경로 |
| 프록시 기동 실패 | 경고하고 CrispASR 를 예전처럼 `:8099` 에 직접(캐시만 꺼진 원래 구성) |
| 옛 구성 감지 | `:8099` 가 떠 있는데 `/health` 에 프록시 표지가 없으면 "캐시 없이 돈다 — stop 후 다시" 경고 |
| 굽기 | 역할마다 `TTS_QWEN_VOICE/SPEED/INSTRUCT` 를 **지우고** `ROLE_VOICE` 로 다시 넣는다(apply_role_voice 의 "이미 있으면 안 덮음" 때문에 안 지우면 도슨트가 사회자 목소리로 구워진다). 임시 파일에 받은 뒤 rename. 있는 키는 건너뜀. `--check` 는 합성 없이 센다 |
| reachy.sh | CrispASR `127.0.0.1:8098`, 프록시 `$BIND_HOST:8099`. `stop`·기동 실패 정리가 프록시도 내린다. `bake` 하위 명령. `start` 는 예열 뒤 `--check` 로 적중률을 찍고 비었으면 경고. `status` 에 캐시 수. dry-run PLAN 줄은 그대로 |

## 작업

1. `tts_cache_proxy.py` — 키 함수, 캐시 읽기, 적중·통과·health·드리프트 경고, 로그
2. `scripts/bake_tts.py` — 고정 대사 목록, 로봇 함수로 본문, 업스트림 직접 합성, 색인, `--check`/`--limit`/`--level`
3. `reachy.sh` — 포트 분리·프록시 기동/폴백/정지, `bake`, `start` 점검, `status`
4. 테스트 — 키, 굽기 본문 = 로봇 함수, 가짜 업스트림 조합(적중·통과·드리프트·장애·중도 끊김)
5. 실측 — 진짜 CrispASR + 프록시로 몇 문장 굽고 로봇 경로 요청이 적중·PCM 동일인지
6. 문서 — `docs/lessons.md`, `docs/real-robot-deployment.md`, CLAUDE.md 명령 블록

## 범위 밖

청취 검수 페이지(다음 단계, 이 캐시를 입력으로 쓴다), 관람객 답 캐시, 감정 어조별 굽기(스위치가 켜질 때만 의미).
