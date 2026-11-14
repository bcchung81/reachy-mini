# 공연 준비 갈래 C — 웹툰(초등·중고등) 하이라이트 7큐 확장 · 진행 보고

C 칸(2026-11-14). 근거: `2026-11-14-show-readiness.md` §5 · `2026-11-12-webtoon-stage.md`. 사용자 결정 U7 ①(하이라이트 7큐) · U8 ①(03 먼저 확인).
범위: 콘티(`storyboard.yaml`)와 그림 함수(`scenes.js`)만 늘린다 — 엔진(`template.html`)·빌더(`build.py`)는 그대로.
고치는 파일: `scripts/handout_webtoon/**` · `docs/design/webtoon-stage.html`(생성물) · `tests/test_handout_webtoon.py` · 이 보고 파일.

## 시작 확인

- 캐시: 7큐 × 초등·중고등 문장이 ElevenLabs 캐시(`~/.local/share/reachy-mini-tts/cache-elevenlabs`)에 **모두 있다** —
  빌더의 `utterances()` 로 큐시트와 글 대조까지 통과(합성 없이 읽기만). 새 합성 0.
- 기존 빌드가 커밋된 생성물과 **바이트 단위로 같다**(빌더를 출력 경로만 바꿔 다시 돌려 `cmp`). 테스트 21개 통과.
- 01·02 기준 캡처 78장(두 수준 × 01·02, 칸마다 말 75% 지점 + 칸 사이 이동 가운데) — 03 을 넣은 뒤 같은 시각을 다시 찍어 픽셀로 대조한다.
- `scenes.js` 큐별 파일 나누기(§5 할 일 2, 선택)는 **하지 않았다** — 서브에이전트를 붙이지 않으므로 얻는 것이 없고, 빌더를 고쳐야 한다.

## 진행

### 03 전파 이론(초등·중고등) — 끝, 사용자 확인 받음(2026-11-14, 조율자 전달 — 방향·세부 결정 셋 모두 권장안)

```
TTS_CACHE_DIR=~/.local/share/reachy-mini-tts/cache-elevenlabs .venv/bin/python -m scripts.handout_webtoon.build
초등 03-theory 68.2s · 칸 11 · 문장 14     중고등 03-theory 75.6s · 칸 11 · 문장 16
wrote docs/design/webtoon-stage.html — 2,911,238 bytes   (01·02 만일 때 1,908,444 → 03 두 수준에 +1.0 MB)
```

콘티(두 수준 모두 11칸 — 대사가 같은 사회자 칸은 그림도 같고, 도슨트 칸만 수준마다 다르다)

| # | 발화 | 칸 | 그림 | 초등 | 중고등 |
|---|---|---|---|---|---|
| 1 | 오프닝 | 넓은 칸 | `lab` | 칠판에 분필 물결이 그려져 나간다 · 이름표 '원리' · '도대체 뭐예요?' 에 큰 물음표 | 같음 |
| 2 | 도슨트 0 | 보통 | `ghost` / `emwave` | 내민 손을 흐린 물결이 그냥 지나가고, '만져지지도' 에 손을 쥐어도 안 잡힌다 · 빗금 친 눈 | 전기(세로)·자기(비스듬히 누운) 물결이 함께 흐른다 · 이름표 '전기'·'자기'·카드 '전자기파' |
| 3 | 도슨트 0 | 보통 | `pond` / `vacuum` | 연못 물결은 가장자리에서 멈추고, 안테나 전파는 물 없는 밤하늘('텅 빈 곳')로 줄지 않고 간다 · 카드 '물결' | 공기 뺀 유리 종 속 종소리는 곧 사라지고 '못 가' 에 빨간 X · 위성 → 지구로 전파('우주') |
| 4 | 질문 1 | 띠 | `ask` v3 | 다이얼을 돌리면 물결이 촘촘해졌다 성겨졌다 | 같음 |
| 5 | 도슨트 1 | 보통 | `bob` | 부표가 출렁이고 초시계 한 바퀴 동안 마루 세 번을 눈금으로 센다 · 카드 '주파수' | 같음 + 이름표 '1초' · 카드 '주파수 (Hz)' |
| 6 | 도슨트 1 | 보통 | `fastslow` / `hertz` | '빠르게'·'천천히' 두 줄 물결(같은 빠르기로 흐르니 빠른 쪽이 촘촘) | 초상과 이름판 '헤르츠' · 02 의 불꽃 실험('증명') |
| 7 | 질문 2 | 띠 | `ask` v4 | 마루와 마루 사이를 재는 괄호 | 같음 |
| 8 | 도슨트 2 | 보통 | `ruler` | 마루에서 다음 마루까지 괄호가 자라고 점이 그 길을 간다 · 카드 '파장' | 같음 |
| 9 | 도슨트 2 | **기울어진 칸** | `squeeze` | 긴 물결(위)·짧은 물결(아래), 줄 이름표 = 카드 `visual.low`·`visual.high` 그대로 | 같음(이름표는 중고등 카드) + 여백 왼쪽에 카드 `visual.formula` '주파수 ↑ → 파장 ↓ (반비례)' |
| 10 | — | 침묵 칸 | `compare` | 비교 자: 긴 물결 하나(위)와 빈 자리(아래) | 같음 |
| 11 | 받아치기 | 테두리 없는 칸 | `finale` v2 | 두 로봇 위로 흐린 점선 물결이 '풀어' 에 왼쪽부터 또렷해진다 | 같음 |

- **칸 깨기**: 짧은 물결(빠르게 출렁이는 쪽)의 끝 한 묶음(`BRK.packet`)이 떨어져 나가 칸을 뚫고 여백을 건너 침묵 칸 비교 자의 빈 자리에 가로로 눕는다
  — 긴 물결 아래에 놓여 "빠를수록 물결 하나가 짧다" 를 말 없이 보여 준다. 묶음의 파장·진폭·흐름은 그 줄과 같아서 떨어지는 순간 이음매가 맞는다.
- **그림이 대사를 거스르지 않게**: 화면의 물결은 모두 같은 빠르기로 오른쪽으로 흐르는 식이다 — 파장이 짧은 줄일수록 한자리에서 더 자주
  출렁인다(주파수 칸과 파장 칸이 같은 물리). 부표 칸의 '세 번' 은 그 식에서 나온 수이고 화면에 숫자로 쓰지 않는다.
- **글**: 이름표는 그 수준 카드(items·visual)와 그 큐 대사 낱말(`sc.word`)뿐. 초등 화면에 숫자 없음('1초' 는 중고등 대사에만 있어 중고등에만 뜬다).
  기울어진 칸의 줄 이름표·반비례 식은 카드 `visual.low/high/formula` 를 그대로 썼다 — 01·02 가 쓴 `visual.facts/from/to/label` 과 같은
  검증된 카드 필드다(아래 '결정 필요' 1).
- 01·02 쪽은 `ask`·`finale` 에 **새 변형 번호(v3·v4, v2)만 덧붙였다** — 기존 번호의 그림은 그대로.

확인
- `?check=1`: `data-warn = []`, `data-issues = []`(처음 빌드부터). 여백 풀이: 모든 경계에서 이동 시간 = 빌더가 넣은 쉼(0.95/0.16/1.25/1.5/0.9).
- **01·02 회귀**: 고치기 전에 찍은 기준 78장과 같은 시각을 새 빌드로 다시 찍어 무대 영역(위 막대 제외 — 03 이 생겨 '다음 장' 단추 상태만 다르다)을
  픽셀 대조 → **78장 모두 같음**.
- **결정성**: 두 수준 × 49시각(칸 깨기 비행 9시각 포함)을 차례·거꾸로·섞은 순서로 그려 캔버스 해시가 모두 같다.
- **공연 모드**(가짜 공연 `fake_show.py --port 18793 --cues 03-theory --level 초등`, CDP 3초 간격 29컷): 화면이 03 으로 넘어가 발화마다 따라가고
  (말하는 로봇·턴 일치, 시계 0 → 68.17초), 카드·제목·기억해 두기가 제때 뜸, JS 오류 0. 끝난 뒤 18793 포트·프로세스 내려간 것 확인.
- 조정실 매니페스트(`DashboardServer.stage_manifest()`, 읽기만): `webtoon: ['01-intro', '02-history', '03-theory']` — 빌드만으로 따라온다.

헤드리스로 보고 고친 것(1차 캡처 → 2차)
1. 손 내민 칸: 아이와 손이 멀어 팔이 214px 고무줄처럼 늘어남 → 아이를 손 가까이(팔 약 130px), 눈 표지를 머리 옆으로 키움(물결 높이를 피해).
2. 파장 칸: 괄호를 낱말 '길이'(문장 끝 70%)에 묶었더니 다 자라기 전에 화면이 다음 칸으로 떠남(같은 발화 칸 나눔 = 0.16초 뒤, 이동은 0.44초 앞당겨 출발)
   → 칸 시작 + 0.5초에 재기 시작, 칸 길이에 맞춰 자란다. (lessons 후보 — 아래)
3. 두 줄 칸: 줄 물결 끝의 부표가 읽히지 않음 → 구슬로.
4. 중고등 반비례 식(여백 글)이 날아가는 묶음 위에 덮임(DOM 글이 캔버스 위) → 묶음 경로가 없는 여백 왼쪽(x 160)으로. 02 의 여백 글도 왼쪽(x 170)이었다.
5. 기울어진 칸 아래쪽이 비어 보임 → 두 줄을 아래로 내림.
6. (캡처 전에 잡음) 부표 칸 눈금이 한 바퀴 뒤 3 → 2 로 줄어드는 셈 → `[T, T+한 바퀴)` 안의 마루 수로.

## 조율자에게

**03 을 두 수준으로 끝내고 멈췄다(U8 ① — 사용자가 실제 화면으로 확인).** 04 → 07 → 14 → 17 → 18 → 19 는 확인을 받은 뒤 같은 순서로 한다.

사용자에게 여는 법: `open docs/design/webtoon-stage.html` → 위 막대 [초등|중고등] → 장 고르기에서 '03 전파 이론 — 주파수와 파장' → ▶ 재생
(캐시 음성이 나온다). 한 순간만 보려면 `…/webtoon-stage.html?lv=중고등&cue=03&t=61.6`(칸 깨기 직후) 같은 주소. 한눈에 보는 캡처는 아래 시트 두 장.

### 1. 바꾼 파일(git 쓰기 안 함)
- `scripts/handout_webtoon/storyboard.yaml` — 03 콘티(초등·중고등 각 11칸)
- `scripts/handout_webtoon/scenes.js` — 03 그림 11종(`lab`·`ghost`·`pond`·`emwave`·`vacuum`·`bob`·`fastslow`·`hertz`·`ruler`·`squeeze`·`compare`)
  + 칸 깨기 물체 `BRK.packet` + 도구(`band2`·`flow`·`span`·`buoy`·`sayAt`) · 기존 `ask` 에 v3·v4, `finale` 에 v2 덧붙임(기존 번호 그림 그대로)
- `docs/design/webtoon-stage.html` — 생성물(1,908,444 → 2,911,238 bytes)
- `tests/test_handout_webtoon.py` — 새 테스트 3개 + 기존 1개 강화
- `docs/superpowers/plans/2026-11-14-show-readiness-C.md`(새 파일, 이 보고)
- 엔진(`template.html`)·빌더(`build.py`)는 안 고쳤다. 조율자 파일(`scripts/handout_live/`·`stage/`)은 읽기·실행만.

### 2. 테스트·캡처
- `.venv/bin/python -m pytest -q tests/test_handout_webtoon.py` → **23 passed, 1 xfailed, 6.4초**.
  - 새: `test_콘티의_큐는_하이라이트_코스_안에서_큐시트_순서다`, `test_카드마다_그_포인트를_말하는_칸이_콘티에_있다`(카드 i 가 콘티의 card/item 칸에
    묶였는지 — lessons '턴 번호 ≠ 포인트 번호' 를 콘티 단계에서 막는다), `test_하이라이트_코스의_모든_큐가_두_수준으로_있다`(**`xfail(strict=True)` —
    진행 중 표시.** 7큐를 다 넣으면 XPASS 로 실패하니 그때 표시를 지운다. 전체 묶음에서 'x' 하나로 보이는 것은 정상).
  - 강화: `test_생성물_check_경고와_배치_문제가_없다` 가 `?check=1` 이 콘티의 **모든** 큐 × 두 수준을 실제로 지었는지도 본다(`data-gaps`).
- 다른 칸·조율자 테스트는 안 돌렸다. **`tests/test_live_stage.py` 는 빌드된 웹툰을 읽는다** — 03 이 생겼으니 조율자가 돌려 볼 것
  (계획서 §9-5 의 '초등 03 = 웹툰' 통합 테스트도 이제 붙일 수 있다).
- 캡처(저장소 밖, `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/`):
  - `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-03-초등.png` ·
    `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-03-중고등.png`
    — 최종 03 칸마다(말 75% 지점 + 칸 사이 이동, 수준마다 22컷, 스트립 열)
  - `…/panes/C/shots/r2/`(위 시트의 원본 1600×948) · `…/panes/C/shots/r2brk/`·`r2brk-e.png`·`r2brk-m.png`(칸 깨기 8컷 × 2수준) ·
    `…/panes/C/shots/full2.png`(옆 열 포함 전체 무대 2장) · `…/panes/C/shots/r1-*.png`(고치기 전 1차)
  - `…/panes/C/fake-e/`(가짜 공연 29컷·`sheet.png`·`show.log`) · `…/panes/C/fake-e.log`(컷마다 큐·시계·말하는 로봇·배지)
  - `…/panes/C/base/`(01·02 기준 78장)·`…/panes/C/shots/reg/`(회귀 78장) · `…/panes/C/bin/`(캡처·회귀·결정성 도구 — `build_to.py` 는 빌더를
    출력 경로만 바꿔 돌려 저장소 생성물을 건드리지 않고 시험한다)

### 3. `docs/lessons.md` 초안(배포 문서에 넣을 것은 없다 — PC 의 정적 HTML, 로봇·데몬 무관)
- **같은 발화의 다음 칸으로 곧 넘어가는 칸에서 그림을 낱말 시각에 묶으면 다 그리기 전에 화면이 떠난다(작업자 C, 웹툰 03).**
  증상: 파장 칸의 괄호가 '길이' 에서 자라기 시작해 칸을 떠날 때 3분의 1만 자라 있었다. 원인: 같은 발화 안 칸 나눔은 쉼이 `GAP_SENT`(0.16초)라
  이동이 앞 문장 끝을 0.44초 앞당겨 출발한다 — 문장 끝 70% 에 있는 낱말을 기다리면 남은 시간이 1초도 안 된다. 규칙: 칸 나눔(`split`) 앞 칸의
  움직임은 칸 시작에 묶고 칸 길이(`pn.t1 − pn.t0`)에 맞춰 끝낸다. 낱말 시각(`sc.w`)은 그 칸이 발화의 마지막 칸이거나 낱말이 문장 앞쪽일 때만.
  (테스트로는 못 박음 — 헤드리스 캡처로 확인)
- **여백 글(DOM)은 캔버스 위에 그려진다 — 깨고 나오는 물체의 경로에 두면 날아가는 물체를 덮는다(작업자 C, 웹툰 03).** 규칙: 여백 글은 물체 경로의
  반대편에(웹툰은 물체가 기울어진 칸 오른쪽 아래에서 떠나 침묵 칸 가운데로 내려오므로 왼쪽 x 160~170).

### 4. 결정 필요 — 권장안으로 진행함
1. **카드 `visual.low/high/formula` 를 이름표로 썼다.** `scenes.js` 머리 규칙은 "카드 items[].t · visual 의 facts/from/to/label" 인데, 03 카드에는
   그 필드가 없고 다이얼용 `low`·`high`·`formula` 가 있다. 같은 `handout-hud` 의 검증된 카드 글이라 그대로 썼다(낱말 대조를 거치지 않는 쪽).
   권장: 이대로 두고 `scenes.js` 머리 규칙 주석을 "visual 의 글 필드" 로 넓힌다(04 부터 같은 일이 생긴다). 싫으면 대사 낱말('빠르게'·'천천히')로 바꾼다.
2. **초등 기울어진 칸 문장은 "…짧아지고, 천천히 출렁일수록 길어지거든요" 로 '긴 쪽' 에서 끝나는데 칸 깨기 물체는 '짧은 물결' 이다.** 짧은 쪽이
   이 큐의 결론(기억해 두기 "빠르게 출렁일수록 물결 하나는 짧아져요")이라 그쪽을 날렸다. 권장: 이대로.
3. **중고등 `hertz` 칸의 초상은 일반 인물 그림이다**(실제 헤르츠 얼굴을 닮게 그리지 않았다 — 이름판 '헤르츠' 는 대사 낱말). 권장: 이대로.
4. 사용자가 03 그림 방향(분필 칠판·손·연못/유리 종·부표·두 줄·비교 자)을 보고 바꾸고 싶은 칸이 있으면 04 전에 받는다.

### 5. 남은 일 · 본 것
- 04 → 07 → 14 → 17 → 18 → 19(초등·중고등) — 확인 뒤. 캐시는 7큐 × 두 수준 모두 이미 있다(새 합성 0). 그다음 가짜 공연 9큐 × 두 수준(--qa),
  생성물 크기·처음 뜨는 시간 측정, xfail 표시 지우기. 어림: 큐·수준당 약 0.5 MB → 9큐 약 8.5 MB.
- 03 공연 모드 확인은 초등만 했다(중고등은 같은 엔진·같은 콘티 모양이라 9큐 가짜 공연 때 함께 본다).
- (조율자 파일, 참고) `fake_show.py` 가 끝나면 서버도 내려가 화면 배지가 '공연 신호 끊김 — 다시 연결하는 중…' 이 된다 — 의도대로로 보인다(기록만).
- (작업 트리 참고) `docs/design/exploded-stage.html` 도 03 을 갖고 있다(D 칸) — 매니페스트가 웹툰·분해도 둘 다 03 을 읽는다.

## 진행 (2차) — 04 · 07 · 14 · 17 · 18 · 19(초등·중고등)

03 확인(조율자 전달: 방향 그대로, 세부 결정 셋 권장안) 뒤 같은 순서로 만들었다. 엔진·빌더는 그대로, 콘티와 그림 함수만.
`scenes.js` 머리 규칙은 결정 1 대로 "카드 visual 의 글 필드(facts/from/to/label/low/high/formula 등)" 로 넓혔다.

```
TTS_CACHE_DIR=~/.local/share/reachy-mini-tts/cache-elevenlabs .venv/bin/python -m scripts.handout_webtoon.build
wrote docs/design/webtoon-stage.html — 7,846,719 bytes   (9큐 × 2수준 = 18장면)
```

| 큐 | 초등 | 중고등 | 깨고 나오는 물체 → 도착 | 그림(새 함수) | 고친 것(헤드리스로 보고) |
|---|---|---|---|---|---|
| 04 모스 | 68.8초 · 칸 10 · 문장 14 | 74.7초 · 칸 10 · 문장 15 | 불꽃 틈에서 나온 전파 한 덩이(`sparkwave`) → 떨어진 고리 앞 | zone · tap · dotdash(초) · three(중) · codebook(초) · frequent · factpair(중) · hertzlab · ring, 질문 v5·v6, 끝 v3 | 줄 가운데 `//` 가 질문 띠 v5 뒤 코드를 삼킴(문법 오류로 바로 드러남) · 누르는 손이 종이띠 인쇄 머리를 가림 → 왼쪽 위에서 · 불꽃 틈 막대 12px → 위로 올림 |
| 07 해상 | 67.0초 · 칸 11 · 문장 14 | 72.8초 · 칸 11 · 문장 14 | 물에 뜬 자동 장치의 구조 신호(`call`) → 이웃 배 돛대 끝 | sea · sos · rescue · watch · nearby(초) · rulebook(중) · device · beacon · rescueship, 질문 v7·v8, 끝 v4 | **조사 자료 A 등급(구조선은 침몰 뒤 구명정의 사람들을 건졌다)대로 구조 칸에 가라앉는 배를 그리지 않음** · 기운 배의 안테나 고리 자리를 회전에 맞춤 · 구조선이 구명정에 겹침 · 장치를 물에 반쯤 잠긴 뜬 장치로 · 끝 칸 배가 로봇을 덮는 안 → 구명 튜브 · 중고등 '물러나는 옛 전건'(하늘에 뜬 것처럼 보임) 빼고 '1999년' 만 |
| 14 이동통신 | 61.5초 · 칸 10 · 문장 14 | 69.7초 · 칸 10 · 문장 15 | 5세대 기지국의 영상 한 장(`video`) → 손 안 스마트폰 화면 | phones · carphone · scale · shrink(초) · gens · years(중) · many5g · phone, 질문 v9·v10, 끝 v5 | 차가 뒤로 달림(배경이 오른쪽으로 흐름) · 폴더폰 화면 아이콘 어긋남 · 세대 이름표를 전화 아래로 · **차 칸의 save/restore 짝 어긋남 — 그 칸이 보이는 프레임에서 아래 칸·말풍선·레일이 잘려 안 그려졌다(아래 lessons 1)** |
| 17 탐사 | 61.9초 · 칸 11 · 문장 13 | 72.5초 · 칸 11 · 문장 14 | 관제실 접시 안테나의 명령 꼬투리(`command`) → 달 위 탐사차 안테나 | planet · remote · drive · delay · careful(초) · moonmars · moonnear(중) · control · moonrover(중고등은 월면차도), 질문 v11·v12, 끝 v6 | 카드 visual.facts 의 달·화성 짝을 내용으로 찾음(수준마다 순서가 반대) · 관제실 이름표끼리 겹칠 자리 미리 옮김 · 두 줄 칸 지구가 카드 꼬리표 밑 → 줄 내림 |
| 18 과학 | 47.2초 · 칸 8 · 문장 10 | 50.0초 · 칸 8 · 문장 10 | 테레민 막대 끝의 음표(`note`) → 오선지 높은 자리(손이 가까이 = 높은 소리) | labtable · theremin · pitch(초) · sensor(중) · magic(초) · notantenna(중) · field · staff, 질문 v13, 끝 v7 | 손 방향이 거꾸로(막대로 다가가는 손끝이 반대쪽) · 연주자 왼손이 얼굴을 가림 · 중고등 카드 꼬리표와 같은 낱말 이름표가 겹쳐 나옴('테레민' 두 번) → 꼬리표에 든 낱말이면 뺀다(`dupTag`) |
| 19 마무리 | 32.6초 · 칸 5 · 문장 8 | 36.6초 · 칸 5 · 문장 9 | **01 의 전파 띠(`ribbon`)** → 관람객 머리 위 — 첫 큐와 끝 큐가 같은 물체로 닫힌다 | 01 의 hall 을 저녁(v 1)으로 · bow · found · crowd, 끝 v8 | — |

- **공통**: 질문 띠·마지막 칸은 변형 표(`ASKV[v]`·`FINV[v]`)로 꽂는다 — 01~03 의 기존 번호 그림은 함수 안에 그대로. 수준마다 낱말이 다른 칸은
  `wordIn`(그 칸에서 말한 낱말 중 첫 것)·`sayAt`(시각만, 경고 없음)으로 고르고, 이름표 글은 늘 `sc.word`·카드 글을 거친다.
- **글**: 이름표 = 그 수준 카드(items·visual)와 그 큐 대사 낱말뿐. 초등 화면 숫자 0(`?check=1` 이 본다). 중고등 연도('1984년'·'1999년'·'2019년'·'1970년'·'1920년')는
  그 칸 대사에 있을 때만.
- **사실**: 그림 소재는 대사·카드의 것만(전화 넷·여객선·구명정·테레민 막대와 고리·바퀴 여덟 탐사차·월면차). 실존 인물(헤르츠·김학우·루노호트 관제팀)은 일반 인물
  그림 + 대사/카드 글(결정 3 과 같은 방식).

확인
- `?check=1`(18장면): `data-warn = []`, `data-issues = []`.
- **회귀**: 01·02 기준 78장 · 03 확인 시점 44장과 같은 시각을 최종 빌드로 다시 찍어 무대 영역 픽셀 대조 → **모두 같음**.
- **결정성**: 18장면 × 21시각(칸 깨기 비행 5시각 포함)을 차례·거꾸로 그려 캔버스 해시가 같고, 그릴 때마다 save/restore 짝이 맞는다 — 테스트로 박제
  (`test_모든_장면은_save_restore_짝이_맞고_순서를_바꿔_그려도_같다`). 이 탐침이 14 의 버그를 찾았다(처음엔 초등 14 만 순서에 따라 달랐다).
  버그가 있던 빌드에 이 테스트를 돌리면 `['초등 14-mobile t=3.85', …, '중고등 14-mobile t=17.42']` 로 실패하는 것까지 확인했다.
- **가짜 공연 9큐 × 두 수준(--qa)**: `fake_show.py --cues <하이라이트 9큐> --qa` 를 포트 18795(초등)·18797(중고등)에서, CDP 로 3초마다 캡처
  (초등 230컷·중고등 253컷). 두 수준 모두 01 → 19 를 차례로 따라감 — 큐마다 장면 시계가 그 큐 길이 가까이까지 가고(예: 초등 03 66.9/68.2초, 중고등 19 35.6/36.6초),
  말하는 로봇의 턴이 발화와 맞고, 큐마다 관람객 질문 흐름 배지('관람객 질문에 답하는 중')와 그동안 시계 정지, **JS 오류 0**. 끝난 뒤 두 포트·프로세스 내려간 것 확인.
- **크기·처음 뜨는 시간**(이 맥, 헤드리스 Chrome, 3회, `data-ready` 까지):

  | 빌드 | 크기 | 기본(01) | 중고등 19 로 바로 | `?check=1`(18장면 다 짓기) | JS 힙 |
  |---|---|---|---|---|---|
  | 01·02 (커밋된 것) | 1,908,444 B | 57~58 ms | — | — | 10 MB |
  | 01~03 | 2,911,238 B | 59~62 ms | — | — | 10 MB |
  | 9큐 | 7,846,719 B | 68~80 ms | 70~72 ms | 321~324 ms | 10~18 MB |

  장면은 처음 볼 때 짓는다(`getScene` 지연) — 큐가 늘어도 처음 뜨는 시간은 거의 그대로. 큐·수준당 약 0.44 MB(계획서 어림 0.5 MB). 종이 무대(8.4 MB)와 비슷하다.
- 테스트: `.venv/bin/python -m pytest -q tests/test_handout_webtoon.py` → **26 passed, 10.2초**. xfail(진행 중 표시) 지움 — `test_하이라이트_코스의_모든_큐가_두_수준으로_있다` 가 이제 통과.

## 조율자에게 (2차)

**하이라이트 7큐(03·04·07·14·17·18·19) × 초등·중고등을 다 넣고 멈췄다.** 하이라이트 코스 9큐가 처음부터 끝까지 웹툰 전용 화면으로 간다
(`/stage/manifest` 가 빌드된 페이지에서 `webtoon: 01·02·03·04·07·14·17·18·19` 를 읽는다 — `stage/` 수정 없음). 새 합성 0, 외부 호출 0, git 쓰기 0.

사용자에게 여는 법: `open docs/design/webtoon-stage.html` → [초등|중고등] → 장 고르기에서 큐 → ▶ 재생. 한눈에 보는 칸별 시트는 아래 2.

### 1. 바꾼 파일(1차 이후)
- `scripts/handout_webtoon/storyboard.yaml` — 04·07·14·17·18·19 콘티(수준마다 5~11칸)
- `scripts/handout_webtoon/scenes.js` — 그림 함수 46개 + 새 칸 깨기 물체 5개(`sparkwave`·`call`·`video`·`command`·`note` — 19 는 01 의 `ribbon` 재사용) +
  변형 표 `ASKV`·`FINV` + 도구. 기존 함수는 `ask`·`finale` 에 표를 부르는 한 줄씩, `hall` 에 저녁 변형(v 1) 한 갈래만 더했다(01~03 픽셀 그대로 — 회귀 확인). 머리 글자 규칙 주석 넓힘.
- `docs/design/webtoon-stage.html` — 생성물(2,911,238 → 7,846,719 bytes)
- `tests/test_handout_webtoon.py` — 새 테스트 2개 + xfail 지움(아래)
- `docs/superpowers/plans/2026-11-14-show-readiness-C.md` — 이 보고(새 파일)
- 엔진(`template.html`)·빌더(`build.py`) 안 고침. 조율자 파일(`scripts/handout_live/`·`stage/`)은 읽기·실행만.

### 2. 테스트·캡처
- `tests/test_handout_webtoon.py` → **26 passed, 10.2초**(1차 23 + xfail 이던 1개가 통과 + 새 2개).
  - 새: `test_장면_코드에_줄_가운데_주석이_뒤_코드를_삼키지_않는다`(정적) · `test_모든_장면은_save_restore_짝이_맞고_순서를_바꿔_그려도_같다`(헤드리스 — 18장면 × 21시각).
  - xfail 지움: `test_하이라이트_코스의_모든_큐가_두_수준으로_있다` — 이제 코스 = 콘티(순서까지).
- **조율자가 돌릴 것**: 빌드된 웹툰을 읽는 `tests/test_live_stage.py`(계획서 §9-5 '초등 03 = 웹툰' 등 통합 테스트도 이제 03~19 로 붙일 수 있다) · 전체 묶음.
- 칸별 시트(최종 빌드, 칸마다 말 75% 지점 + 칸 사이 이동, 스트립 열):
  - `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-04-초등.png` · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-04-중고등.png`
  - `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-07-초등.png` · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-07-중고등.png`
  - `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-14-초등.png` · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-14-중고등.png`
  - `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-17-초등.png` · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-17-중고등.png`
  - `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-18-초등.png` · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-18-중고등.png`
  - `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-19-초등.png` · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/sheet-19-중고등.png`
  - (03 은 1차 시트 그대로 — 픽셀 같음) 원본: `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/shots/final/`(220장, 1600×948)
- 가짜 공연 9큐 × 두 수준: `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/fake9-e/`(초등 230컷 · `sheet.png` 큐마다 한 컷 + 질문 흐름) · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/fake9-m/`(중고등 253컷 · `sheet.png`) ·
  `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/fake9-e.log`·`/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/fake9-m.log`(컷마다 큐·시계·말하는 턴·배지, 끝 줄 `JS 오류: []`) · `fake9-*/show.log`(fake_show 진행)
- 회귀·결정성 도구: `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/bin/regress.py`(01·02)·`/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/bin/regress2.py`(아무 기준 폴더) · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/det9.html`(18장면 결정성) · `/private/tmp/claude-501/-Users-bcchung81-workspace-reachy-mini/34ccc93c-5a2f-42e6-a4b0-7a7643501a05/scratchpad/panes/C/bin/loadtime.py`(처음 뜨는 시간)

### 3. `docs/lessons.md` 초안(배포 문서에 넣을 것은 없다 — PC 의 정적 HTML)
1. **한 줄에 여러 문장을 쓴 코드 가운데에 `//` 주석을 끼우면 뒤 문장이 통째로 주석이 된다 — 괄호 짝이 맞으면 문법 검사도 통과한다(작업자 C, 웹툰 04·14).**
   - 증상: 웹툰 14 의 차 칸이 보이는 프레임에서 그 아래 칸·말풍선·오른쪽 레일이 그려지지 않았다. 결정성 탐침에서 '초등 14 만 앞서 그린 시각에 따라 그림이 다르다' 로 드러났다.
   - 원인: `c.save(); c.translate(…);  // 앞 창에 수화기 c.rotate(…); …; c.restore();` — 고치며 주석을 줄 가운데에 넣어 `c.restore()` 까지 주석이 됐다.
     `save` 하나가 남아 엔진의 `restore` 가 짝을 잘못 맞추고, 그 칸의 clip·변환이 같은 프레임의 나머지 그림에 남았다. 괄호는 맞아 `node --check` 도 통과.
     (같은 날 04 에서도 같은 실수를 했는데 그때는 괄호가 어긋나 문법 오류로 바로 드러났다 — 두 번째가 조용했다.)
   - 규칙: 줄 가운데에는 `/* … */` 만, 설명은 줄 끝에. 그림은 시각 t 의 순수 함수라는 약속을 '순서를 바꿔 그려도 같은가' 로 기계 확인한다(눈 캡처는 한 프레임씩이라 못 본다).
   - 테스트: `tests/test_handout_webtoon.py::test_장면_코드에_줄_가운데_주석이_뒤_코드를_삼키지_않는다`,
     `tests/test_handout_webtoon.py::test_모든_장면은_save_restore_짝이_맞고_순서를_바꿔_그려도_같다`(버그가 있던 빌드에서 실패하는 것 확인).
2. **그림도 사실 주장이다 — 조사 자료가 구도를 정한다(작업자 C, 웹툰 07).** 대사 "그걸 들은 다른 배가 달려와 사람들을 구했답니다" 만 보면 가라앉는 배 옆에 구조선을
   그리기 쉽다. 조사 자료(07-maritime, A 등급 — 영국 난파위원회 보고서)는 구조선이 침몰 1시간 45분 뒤 도착해 구명정의 사람들을 건졌다고 적는다. 규칙: 사건 장면은
   그리기 전에 `data/cues-research` 의 해당 사실(등급 A·B)을 읽고 시간 순서·있던 것만 그린다. (테스트로는 못 박음)

### 4. 결정 필요 — 권장안으로 진행함
1. **19 는 01 을 되부른다**: 오프닝 = 01 의 전파체험관 건물을 저녁으로(`hall` v 1), 칸 깨기 = 01 의 전파 띠(`ribbon`)가 관람객 머리 위로. 첫 큐와 끝 큐가 같은 그림으로 열리고
   닫히게 했다. 권장: 이대로.
2. **14 '자동차 한 대보다 비쌌다' 를 저울로 그렸다**(전화 상자 쪽이 아래로 — 값의 비유, 이름표 '자동차 한 대'). 무게로 읽힐 수 있다. 권장: 이대로(초등 대사 그대로의 비교).
   싫으면 가격표 둘로 바꾼다(숫자는 초등에 못 쓴다 — 그림만).
3. **실존 인물·물건은 일반 그림**: 김학우(04 중고등)·루노호트 관제팀(17)·월면차 우주비행사(17)는 닮게 그리지 않고 대사/카드 글로만 이름을 단다(1차 결정 3 과 같은 방식).
   여객선(07)은 굴뚝 넷(넷째는 장식이라 연기는 앞 셋에서만)으로 그렸다 — 대사가 '타이타닉호' 라고 이름을 대므로. 권장: 이대로.
4. **18 초등 '마법' 칸**: 요술 모자·지팡이에 빨간 X. 권장: 이대로.

### 5. 남은 일 · 본 것
- 사용자 확인(6큐 실제 화면) — 바꾸고 싶은 칸이 있으면 그 칸 함수만 고친다(결정성 테스트가 지켜 준다).
- 리허설: 로봇 2대로 한 번(`?lat=`·로봇 문장 사이 간격) — 1차와 같음. 전시장 PC(Windows면 Malgun Gothic)에서 글꼴·프레임 시간 — 이 맥 헤드리스에서 처음 뜨는 시간 68~80 ms.
- 하이라이트 밖 10큐(05·06·08~13·15·16)는 U7 ① 대로 카드 화면이 잇는다(그대로).
- (참고) 가짜 공연 로그를 3초 간격으로 표본을 떠서 2초짜리 발화(예: 17 의 질문 2)는 '말하는 턴' 목록에 안 잡혔다 — 화면 문제가 아니라 표본 간격 때문.
- (참고) `scenes.js` 가 2,176줄이 됐다. 큐별 파일로 나누기(계획서 §5 할 일 2)는 빌더를 고쳐야 해서 하지 않았다 — 다음 확장(17큐 전부) 때 볼 일.
