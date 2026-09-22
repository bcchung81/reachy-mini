# 대시보드 카메라·대기모드 — 로봇 실시간 영상(H.264 + WebRTC) + 로봇별 대기 전환 설계

2026-09-22. 선행: 무대감독 대시보드(`2026-09-21-stage-dashboard-design.md` — 카메라 칸은 자리표시자로
남겨 두었다), 2대 구성(`2026-09-11-two-robot-mc-docent-design.md` §4 프로토콜).

이 문서는 카메라(본문)와 **대기모드 토글**(부록, 아래) 둘을 담는다. 두 기능은 독립적이지만 같은 배선
(감독→로봇 메시지, 콘솔 명령, 대시보드 카드 버튼)을 늘리는 자리가 같아 한 계획·한 배포로 묶는다.

## 목표

`./reachy.sh start --robot` 으로 띄운 대시보드의 CAM 1(사회자)·CAM 2(도슨트) 칸에 **두 로봇의 카메라
영상을 실시간으로** 띄운다. 로봇 CPU 를 거의 쓰지 않고(하드웨어 H.264), 마이크 경로(`no_media`)를 건드리지
않으며, 영상이 안 나오면 **이유를 칸에 띄운다** — 조용히 멈춘 화면으로 두지 않는다.

## 사용자 결정 (브레인스토밍, 2026-09-22)

| 항목 | 결정 | 근거 |
|---|---|---|
| 표시 내용 | 실시간 영상. 비전 질문 장면은 **이월** | 시연 모드에서는 로봇이 비전 질문을 처리하지 않는다 — 감독 `generate(role, brief, history)` 는 텍스트만이라 보일 장면이 없다 |
| 켜는 조건 | **대시보드가 붙어 있으면 자동**, 카메라 칸마다 끄기 | 보는 사람이 없으면 인코딩·전송을 안 한다 |
| 전송 방식 | **H.264 + WebRTC**(로봇 → 브라우저 직접) | 가장 부드럽고 대역폭이 적다. JPEG 를 감독 소켓에 싣는 안은 기각 — 사용자 선택 |
| 시그널링 | **기존 두 소켓을 잇는다**(대시보드↔감독 8778, 감독↔로봇 8777) | 새 서버·새 포트 없음. 감독은 SDP·ICE 를 중계만 한다 |
| 데몬 WebRTC | **쓰지 않는다** | 쓰려면 `no_media` 를 되돌려야 하고, 그러면 마이크 이중 점유(`real-robot-deployment.md` §8)가 돌아온다 |

## 스파이크 결과 (사회자 로봇 192.168.0.4 실측, 코드는 버렸다)

| 확인 | 결과 |
|---|---|
| `libcamerasrc(YUY2) → v4l2h264enc` 협상 | 통과. 640x480@15 에서 인코딩 프로세스 CPU 7.7%(코어 1개 기준) |
| 스트림 켬 부하(전체 CPU, 4코어 합) | 기준 14.9% → **19.1%** (+4.2%p ≈ 코어 0.17개) — 목표(+0.2) 안. loadavg 는 소음이 커서 판단에 쓰지 않는다 |
| `webrtcbin` offer ↔ Chrome 153 answer | H.264 constrained-baseline 합의(로봇 `42c01f` / Chrome `42e01f`, `packetization-mode=1`) |
| Chrome 이 자기 주소를 `….local` 로 가린 채 ICE | 로봇 호스트 후보(192.168.0.4)로 **0.1초 만에** 연결. STUN·TURN 불필요 |
| 품질 | 640x480 **15fps**, ≈1.3Mbps, 84초 손실 0, 지터 버퍼 ≈5ms |
| 로봇 GStreamer | 1.26.2 — `webrtcbin`·`nicesrc`·`dtlssrtpenc`·`rtph264pay`·`h264parse`·`v4l2h264enc` 있음, **`webrtcsink` 없음**. 앱 venv 에 GstWebRTC·GstSdp 타입 있음 |
| 맥(개발) GStreamer | 1.28.5 — `webrtcbin`·`x264enc`·`openh264enc`·`avdec_h264`·`videotestsrc` 있음 → **로봇 없이 송수신 통합 테스트 가능** |

## 구조

```
 로봇(각 대)                       노트북 — 무대감독 프로세스                 브라우저(대시보드)
 ─────────────                    ──────────────────────────────           ─────────────────
 camera_rtc.RtcStreamer            stage/camera.CameraRelay                 dashboard_page.html
   libcamerasrc → v4l2h264enc        시청자 id · 켤 조건 · 라우팅             RTCPeerConnection ×2
   → rtph264pay → tee                 │                                      (역할마다)
       ├ queue → webrtcbin(v1) ◀─┐   │  8777 camera/rtc          8778 rtc   │
       └ queue → webrtcbin(v2)   └───┼──── stage_client ◀──▶ server ◀──▶ dashboard ◀──▶ page
                                      │
   ═══════════ 영상(RTP/SRTP, UDP) — 로봇에서 브라우저로 **직접** ═══════════▶ <video>
```

## 프로토콜 (2대 설계서 §4 표에 추가 — 양쪽 짝 관리)

**로봇 → 감독**

| 메시지 | 내용 |
|---|---|
| `hello.caps` 에 `"camera"` | 스트림을 **실제로** 만들 수 있을 때만(`RtcStreamer.available()`). 옛 앱은 안 싣는다 → 감독은 그 로봇에 카메라 지시를 보내지 않는다 |
| `rtc` | `{viewer, sdp: {type: "offer", sdp}}` 또는 `{viewer, candidate, sdpMLineIndex}` |
| `error` (기존) | `{where: "camera", detail}` — 파이프라인·협상 실패 |

**감독 → 로봇**

| 메시지 | 내용 |
|---|---|
| `camera` | `{viewer, on: bool}` — 그 시청자의 분기를 세우거나 닫는다 |
| `rtc` | `{viewer, sdp: {type: "answer", sdp}}` 또는 `{viewer, candidate, sdpMLineIndex}` |

**페이지 ↔ 대시보드 서버**(기존 `/ws` 위)

| 방향 | 모양 |
|---|---|
| 페이지 → 서버 | `{"rtc": {"role", "sdp"}}` · `{"rtc": {"role", "candidate", "sdpMLineIndex"}}` · `{"rtc": {"role", "restart": true}}` |
| 서버 → 페이지 | `{"kind": "rtc", "role", "sdp"}` · `{"kind": "rtc", "role", "candidate", "sdpMLineIndex"}` · `{"kind": "rtc", "role", "bye": true}` |
| 스냅샷 | `cameras: {mc: {available, enabled, reason}, docent: {…}}` |
| 명령 | 콘솔과 같은 `c <mc\|docent>` — 운영자 끄기/켜기(토글) |

**페이지는 자기 시청자 id 를 모른다** — 소켓이 곧 신원이다. 서버가 그 연결의 id 를 붙여 로봇에 보낸다.
다른 시청자를 사칭할 길이 없다.

## 로봇 앱 — `camera_rtc.py` (새 모듈)

- **파이프라인 하나를 시청자가 나눠 쓴다.** 첫 시청자에서 소스·인코더·페이로더·`tee` 를 세우고, 시청자마다
  `tee → queue(leaky) → webrtcbin` 분기를 붙인다(`bundle-policy=max-bundle`, 트랜시버 `sendonly`).
  마지막 시청자가 나가면 파이프라인을 NULL 로 내린다. 감독과 연결이 끊기면(`on_link_down`) 전부 닫는다.
- **소스**: `REACHY_CAMERA_SRC`(기본 `libcamerasrc` — `camera_in` 이 이미 쓰는 변수). libcamerasrc 면
  SDK 와 같은 캡스(`format=YUY2,colorimetry=bt709,interlace-mode=progressive`)를 붙인다.
- **인코더 사다리**: `v4l2h264enc`(실기 하드웨어, constrained-baseline 3.1) → `x264enc` → `openh264enc`.
  하드웨어가 아니면 **경고한다**(CPU 를 문다). 셋 다 없으면 `available()` 가 False.
- **기본값**(스파이크 값): `REACHY_CAMERA_STREAM_WIDTH/HEIGHT/FPS/KBPS` = 640 / 480 / 15 / 2000.
  I-프레임 간격 = fps(1초) — 새 시청자의 첫 화면이 1초 안에 뜨게. 분기를 붙일 때 업스트림
  force-key-unit 이벤트도 보낸다.
- **`available()`** = `REACHY_VISION` 이 꺼지지 않음 + 소스 요소 + 인코더 하나 + `webrtcbin`·`rtph264pay`·
  `h264parse` + GstWebRTC·GstSdp 타입. 맥 시뮬은 libcamerasrc 가 없어 **기본으로 False**.
  `REACHY_CAMERA_SRC="videotestsrc is-live=true"` 를 주면 시뮬에서 테스트 패턴이 뜬다 — 시뮬 전용 우회는
  스위치 뒤, 기본 꺼짐(CLAUDE.md).
- **카메라 배타**: 스트림을 열기 전에 `camera_in.close()`. 스트림 중 `grab_jpeg()` 는 경고하고 None
  ("시각 없이 답한다" 기존 경로). 둘이 같이 필요해지는 4단계에서 `tee` 로 JPEG 를 떼어 낸다(이월).
- **스레드**: GStreamer 시그널(offer·ICE)은 스트리밍 스레드에서 온다. 송신은 `StageClient` 가 한다
  (websockets sync `send` 는 내부 뮤텍스로 여러 스레드에서 안전).

## 감독 — `stage/camera.py` `CameraRelay` (새 모듈, 순수 로직)

- **입력**: `add_viewer(deliver) → "v1"` / `remove_viewer(id)` / `on_viewer_rtc(id, msg)` /
  `on_robot_hello(role, caps)` / `on_robot_disconnect(role)` / `on_robot_rtc(role, msg)` /
  `on_robot_error(role, detail)` / `toggle(role)` / `snapshot()`.
- **출력**: 콜백 두 개뿐 — `send_robot(role, type, fields)`, 시청자별 `deliver(ev)`. 네트워크 없이 단위 테스트된다.
- **켤 조건**(역할·시청자 쌍마다): 시청자 있음 ∧ 운영자 on ∧ 로봇 연결 ∧ `caps` 에 camera. 조건을 다시
  계산해 **바뀐 쌍에만** `camera{on}` 을 보낸다. 로봇이 다시 붙어 hello 하면 다시 켠다. 로봇이 끊기면 그
  역할의 쌍을 비우고 페이지에 `bye` 를 준다(로봇 앱은 스스로 닫는다).
- **자기 락**을 쓰고, 로봇 송신·deliver 는 **락을 놓은 뒤에** 한다(느린 소켓이 다른 시청자를 막지 않게).
- **검증**: `sdp` ≤ 64KB·`type` 이 방향에 맞음(로봇은 offer, 페이지는 answer), `candidate` ≤ 2KB,
  모르는 역할·시청자 → 경고(원인별 한 번)하고 그 메시지만 버린다. 연결은 끊지 않는다.
- **사유 문구**(`reason`, 칸에 그대로 뜬다): 로봇 미연결 → OFFLINE(기존 탤리), caps 없음 →
  "카메라 없음 — 시뮬이거나 로봇 앱이 카메라를 모른다(재배포 필요)", 운영자 끔 → "카메라 꺼짐",
  로봇 오류 → "카메라 오류: <detail>"(다음에 켜질 때 지운다).

## 감독 배선

- `server.py`: hello 의 caps → relay, 끊김 → relay, 로봇 `rtc` → relay, `error{where:"camera"}` → relay(기존
  감독 경로도 그대로). **`camera`·`rtc` 는 허브 `sent`/`recv` 에 싣지 않는다** — ICE 는 초당 수십 개, SDP 는
  수 KB 라 이력 200칸을 밀어낸다. relay 가 상태 변화만 `camera` 이벤트 한 줄로 남긴다
  ("[mc] 영상 연결 요청 (v2)", "[mc] 카메라 오류: …").
- `dashboard.py`: 연결마다 `add_viewer(deliver=그 연결의 구독 큐에 넣기)` — **펌프가 유일한 송신자**라는
  규칙을 지킨다. 넘치면 기존 `sub.dropped` 로 센다. `{"rtc": …}` → `on_viewer_rtc`, 닫히면(비정상 포함)
  `remove_viewer`. 스냅샷에 `cameras` 를 덧붙인다(감독 스냅샷은 건드리지 않는다).
- `console.py`: `c <mc|docent>` → `relay.toggle`. `dispatch(director, cmd, out, camera=None)` — 카메라가
  없는 호출부(기존 테스트)는 그대로 돈다. 대시보드 버튼도 이 명령을 보낸다(명령 경로 하나).
- `__main__.py`: relay 를 만들어 서버·대시보드·콘솔에 넘긴다.

## 페이지

- CAM 칸의 자리표시자 자리에 `<video autoplay muted playsinline>`. 역할마다 `RTCPeerConnection`(ICE 서버 없음).
  offer 가 오면 answer, ICE 는 양방향 트리클. `bye` 면 연결을 닫고 사유를 띄운다.
- 칸마다 **카메라 끄기/켜기** 버튼 → `c <역할>`.
- **끊김을 드러낸다**: `connectionState` 가 `failed`/`disconnected` 이거나, 켜져 있는데 `framesDecoded` 가
  3초간 안 늘면 "영상 끊김" 덮개 + `restart` 를 2초 → 5초 간격으로(최대 5초) 보낸다.
- 스냅샷 `cameras.<역할>.reason` 이 있으면 칸에 그대로 띄운다. 외부 리소스·`innerHTML` 금지(기존 검사).

## 구현 규칙 — 스파이크에서 밟은 것 (`docs/lessons.md`)

1. PyGObject: `reply = promise.get_reply()` 로 **붙잡고**, offer·promise·reply 를 연결이 사는 동안 들고 있는다.
   SDP 텍스트는 `set-local-description` **전에** 뽑는다. (한 줄로 꺼내면 SDP 가 비거나 프로세스가 말없이 죽었다.)
2. 로봇 원격 정리는 pid 기반. 원격 명령 줄에 대상 이름을 그대로 쓰지 않는다.

## 테스트

| 단위 | 무엇을 | 어떻게 |
|---|---|---|
| 프로토콜 | 새 3종 · 양쪽 상수 짝 | `tests/test_stage_protocol.py`, `tests/test_stage_client.py` |
| `CameraRelay` | 켤 조건표 · 바뀔 때만 송신 · 라우팅(자기 시청자에게만) · 검증 · 재연결 · 스냅샷 사유 | 순수 단위 |
| server | caps→relay, rtc 가 허브 이력에 안 쌓임, `error{camera}` | 기존 가짜 허브 방식 |
| dashboard | 시청자 등록·해제(비정상 종료 포함), 페이지 rtc→로봇, 로봇 rtc→그 페이지만, `cameras` 스냅샷 | 기존 가짜 감독 방식 |
| console | `c <역할>` | 기존 방식 |
| stage_client | 새 콜백, 끊기면 `on_link_down`, `rtc` 송신, hello caps | 기존 가짜 소켓 방식 |
| `camera_rtc` | 파이프라인 문자열 · 인코더 사다리 경고 · `available()` | 가짜 요소 조회기 |
| `camera_rtc` 통합 | `videotestsrc+x264enc` 송신 ↔ 테스트 수신 `webrtcbin` 이 실제로 프레임을 디코딩 · 시청자 2명 · 마지막 시청자 뒤 파이프라인 NULL | 맥 GStreamer, 요소가 없으면 skip |
| `camera_in` | 스트림 중 `grab_jpeg` → None + 경고 | 기존 방식 |
| E2E | 진짜 `StageServer`+대시보드+가짜 로봇 소켓: 시청자 붙음 → `camera on` → offer 중계 → answer 역중계 → 시청자 닫힘 → `camera off` | `tests/test_dashboard_e2e.py` 방식 |
| 페이지 | `<video>`·`RTCPeerConnection`·`rtc` 메시지·`c` 명령·사유 표시·끊김 덮개 | 정적 검사 |

**최종 검증**: ① 시뮬(`REACHY_CAMERA_SRC="videotestsrc is-live=true"`)에서 두 칸에 테스트 패턴 ② 두 로봇에
재배포 후 `start --robot` 으로 두 칸 실영상 + 스트림 중 로봇 전체 CPU 사용률 ③ 칸 끄기·대시보드 닫기·감독 종료
각각에서 로봇 로그로 분기 해제 확인 ④ 시청자 2명(노트북 + 두 번째 창).

## 범위 밖 · 이월

- **시연 모드 비전 장면**(감독이 비전 질문에 최신 프레임을 붙여 답하고 그 장면을 띄운다) — 별도 단계.
- **4단계 손들기 감지**: 이제 프레임이 PC 에 이미지로 닿지 않는다. 로봇이 요청을 받아 JPEG 스냅샷을 보내는
  메시지를 따로 둔다(`tee` 에서 JPEG 분기). 비전 캡처와 스트림의 공존도 그때 같이 푼다.
- 태블릿·Safari 는 최종 검증에서 확인만(Safari 호환 캡스는 SDK 와 같은 constrained-baseline 3.1).
- 녹화·저장 없음(영상은 디스크에 남기지 않는다).

---

## 부록 — 대기모드 토글 (로봇별 on/off)

### 사용자 결정

대시보드 카드에서 로봇 한 대를 **대기모드**로 넣고 뺀다. "대기모드 진입" = 로봇이 잠자기 자세로
움직이고 모터가 풀린다(`goto_sleep()` + `disable_motors()` — 앱이 로봇을 재운 채로 끝났을 때와 같은
상태). "해제" = 기상(`enable_motors()` → 3초 → `wake_up()` — `reachy.sh` 의 `robot_wake()` 와 같은
순서·간격, 새로 만들지 않는다).

### 턴 진행과의 관계 — **가장 단순한 재사용**

대기 중인 로봇은 진행에서 빠진다. 새 상태기계를 만들지 않는다 — **`solo_role`(1인 모드) 판정을
`len(self._connected)` 대신 `len(self._connected - self._standby)` 로 바꾼다.** 이러면 "로봇이 끊겼을 때"
쓰던 모든 길(듣는 역할 재배정, 마이크 재동기화, 경고 문구, 기존 테스트)이 "대기 중일 때"에도 그대로
맞는다 — 새 분기를 만들지 않는다.

- **전환은 항상 먼저 멈춘다.** `set_mode` 와 같은 패턴(`_abort_locked()`)을 그대로 쓴다 — 그 역할이
  지금 말하는 중인지 따로 검사하지 않는다(부분 중단이라는 새 개념을 만들지 않는다). 상대 로봇이 말하던
  줄도 함께 끊긴다 — `set_mode` 가 이미 받아들인 트레이드오프와 같다.
- **둘 다 대기로 두는 것은 거절한다** — 진행할 로봇이 없어진다. `_solo_refusal_locked` 와 같은 자리에
  경고 문구로 남긴다("대기모드로 둘 다 두면 진행할 로봇이 없다").
- 로봇이 끊기면(`on_disconnect`) 그 역할의 `_standby` 도 지운다 — 능력과 같은 수명(`_caps` 처리와 같은
  자리·같은 이유: 다시 붙는 앱은 새로 판단한다).

### 프로토콜 (2대 설계서 §4 표에 추가)

| 방향 | 메시지 | 내용 |
|---|---|---|
| 감독 → 로봇 | `standby` | `{on: bool}` |

### 로봇 앱

`on_standby(on: bool)` 핸들러(`on_abort` 와 같은 자리). SDK 호출(`goto_sleep`·`wake_up`)은 수 초가
걸리는 블로킹 호출이라 **감독 메시지를 받는 스레드에서 직접 부르지 않는다** — `SayRunner` 와 같은 모양의
작은 워커 스레드에서 돌린다. 진입 시 `speaker.stop(); player.cancel()` 로 소리·모션부터 끊은 뒤(감독이
이미 `abort` 를 먼저 보냈으므로 이중 방어선), `goto_sleep()` → `disable_motors()`. 해제 시
`enable_motors()` → 3초 대기 → `wake_up()`.

### 감독 배선

- `Director`: `_standby: set[str]`, `toggle_standby(role)`(검증·`_abort_locked`·거절·송신·마이크
  재동기화를 한 메서드에 — `set_mode` 와 같은 모양). `snapshot()` 에 `standby: sorted(self._standby)`.
- `console.py`: `z <mc|docent>` — 콘솔·대시보드 공통 경로(기존 원칙).
- 대시보드 카드: CAM 칸에 "대기 진입/해제" 버튼. `standby` 스냅샷으로 상태를 그린다.

### 테스트

`Director` 단위 테스트(연결 2·1·0대 조합 × 대기 조합에서 `solo_role`·거절·마이크 재동기화),
`toggle_standby` 가 말하는 중이면 먼저 멈추는지, 둘 다 거절하는지, 끊기면 `_standby` 를 지우는지.
`console.py::z`. `stage_client`: `on_standby` 콜백, 블로킹 호출이 수신 스레드를 막지 않는지(가짜 SDK로
지연을 주입해 그동안 다른 메시지를 받는지 확인). 페이지 정적 검사(버튼·`z` 명령·상태 표시).
