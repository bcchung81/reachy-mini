# 실기(Reachy Mini) 배포 전 검증

- 검증일: 2026-07-30(1차) · 2026-08-11(2차, SDK 소스 대조)
- **실기가 없으므로 정적 분석 + 이 맥에서 재현 가능한 실험으로만 확인했다.**
  하드웨어가 필요한 항목은 아래 "미검증"에 따로 적었다.

## 배포 대상 — **Reachy Mini Wireless** (2026-08-11 구매 확정)

이게 정해져야 아래 판단이 갈린다. Wireless 는 다음을 뜻한다.

- **앱이 로봇 위에서 돈다.** 온보드 **CM4104016 — RAM 4 GB / eMMC 16 GB**(Pi 5 아님).
  추론 3종은 PC 에 남는다. 온보드 sLLM 은 RAM 4 GB 라 애초에 성립하지 않는다.
- **주소 3종이 네트워크를 탄다.** WiFi 안테나는 2.79 dBi 패치 하나 — 타임아웃 설계가
  loopback 전제로 남아 있으면 안 된다(아래 7번).
- **USB 데이터 연결이 없다.** Wireless 의 USB-C 는 출력(호스트) 방향이라 랩톱 직결이
  안 된다. 접속은 로봇 자체 AP / 내부 무선망 / USB-C→이더넷 셋 중 하나다.
- 오디오 장치는 **XMOS XVF3800**(하드웨어 AEC·리니어-4 마이크·DoA 180°).
  `REACHY_AEC` 는 시뮬 전용이므로 실기에서 켜지 않는다.

## 요약

| | 항목 | 상태 |
|---|---|---|
| ~~차단~~ | `main.py` 가 생성 템플릿 그대로 | **고침** — `VoiceChat.run` 이 대화 루프를 돌린다 |
| ~~차단~~ | `osxaudiosrc` 하드코딩 | **고침** — `autoaudiosrc`(+ `REACHY_MIC_SRC`) |
| ~~차단~~ | 의존성 미선언 | **고침** — numpy·requests·sounddevice·PyGObject 선언 |
| ~~차단~~ | SDK 와 오디오 장치 이중 점유 | **고침(2026-08-11)** — `request_media_backend="no_media"` (§8) |
| ~~차단~~ | `PyGObject` 를 조건 없이 선언 | **고침(2026-08-11)** — Linux 마커 + SDK 핀 일치 (§9) |
| ~~높음~~ | TTS 실패 시 조용히 벙어리 | **고침** — 플랫폼별 폴백 + 경고 로그 |
| ~~높음~~ | STT·LLM 주소 고정 | **고침** — `REACHY_STT_URL`·`REACHY_LLM_URL` |
| 높음 | 환경변수가 데몬 유닛에 없으면 조용히 loopback 으로 붙는다 | 남음 (§10) |
| ~~높음~~ | TTS 24 kHz 출력 vs 장치 16 kHz | **고침(2026-08-11)** — 장치 레이트로 리샘플 (§11) |
| ~~차단~~ | `no_media` 가 감정 모션 발성을 죽인다 | **고침(2026-08-11)** — 발성을 우리 재생 경로로 (§13) |
| ~~중간~~ | 응답 모션 동안 마이크를 통째로 버린다(춤 18초) | **고침(2026-08-11)** — 게이팅을 사운드로 (§14) |
| ~~중간~~ | `set_target` 을 두 스레드가 부른다(공식 규칙 위반) | **고침(2026-08-11)** — 단일 컨트롤 루프 `driver.py` |
| 중간 | 사용자 발화 중에도 모터가 돈다(소음) | 남음 (§12) |
| 중간 | `reachy.sh` 가 macOS 전용 | 남음 — PC 쪽 스크립트로 쓰면 문제 없다 |
| 중간 | 네트워크 단절 시 90초 행 | 남음 — 실기 네트워크에서 재조정 필요 |
| **미검증** | 스피커 출력 경로, CM4 성능 | 하드웨어 필요 |

**아래 1~5 는 수정 전 진단 기록이다.** 무엇을 왜 고쳤는지 남긴다.

---

## 1. [차단] 실기가 실행하는 앱에 음성대화가 없다

`pyproject.toml` 의 엔트리포인트는 이렇다:

```toml
[project.entry-points."reachy_mini_apps"]
voice_chat = "voice_chat.main:VoiceChat"
```

그런데 `main.py` 의 `VoiceChat.run()` 은 **`reachy-mini-app-assistant create` 가 만든
템플릿 그대로**다 — 머리를 사인파로 흔들고 안테나를 움직이고, 설정 페이지에서
버튼을 누르면 `wake_up.wav` 를 재생하는 것이 전부다. STT·LLM·TTS·VAD 어느 것도 없다.

**음성대화 앱 전체는 `demo.py` 에 있고, 그건 `ReachyMiniApp` 이 아니라 독립 실행
스크립트다**(`if __name__ == "__main__"` + argparse). 즉 로봇에 설치하면
**머리만 흔드는 앱이 돈다.**

→ `demo.py` 의 루프를 `VoiceChat.run(reachy_mini, stop_event)` 안으로 옮겨야 한다.
`stop_event` 기반 종료, `ReachyMini` 인스턴스를 **주입받는 형태**(현재 `demo.py` 는
직접 `ReachyMini()` 를 컨텍스트로 잡는다)로 바꾸는 것이 핵심이다.

## 2. [차단] 마이크가 안 열린다 — `osxaudiosrc`

`audio_in.MicCapture` 의 파이프라인:

```python
Gst.parse_launch(
    "osxaudiosrc ! audioconvert ! audioresample "
    ...
```

`osxaudiosrc` 는 macOS 전용이다. 실기(CM4/Linux)에는 없어 `Gst.parse_launch` 가 실패한다.

이 맥에서 엘리먼트 존재 여부를 조회한 결과:

| 엘리먼트 | 이 맥 |
|---|---|
| `osxaudiosrc` | 있음 |
| `autoaudiosrc` | **있음** |
| `alsasrc` / `pulsesrc` | 없음 (Linux 전용) |

**`autoaudiosrc` 로 바꾸면 된다** — 플랫폼에 맞는 소스를 GStreamer 가 고른다.
이 맥에서 같은 파이프라인으로 실제 캡처가 성공하는 것까지 확인했으므로
**시뮬 쪽 회귀 없이 한 단어만 바꾸면 되는 수정**이다.

## 3. [차단] 의존성이 선언돼 있지 않다

`pyproject.toml` 의 `dependencies = ["reachy-mini"]` 뿐인데, 실제로 앱이 쓰는 외부
패키지는 다음과 같다:

```
numpy, requests, sounddevice, pydantic, gi(PyGObject), reachy_mini
```

로봇에 설치하면 `import numpy` 부터 깨진다. 시뮬에서는 `.venv` 에 이미 다 깔려 있어
드러나지 않았다.

## 4. [높음] TTS 가 실패하면 **소리 없이 벙어리가 된다**

폴백 사다리가 macOS 전용이다.

- `tts.Speaker._worker` — qwen 실패 시 `["say", "-v", voice]`
- `tts._afplay` — 스트림을 못 열면 `["afplay", ...]`

Linux 에는 둘 다 없다. `subprocess.run` 이 `FileNotFoundError` 를 던지고
`_worker` 의 `except Exception: pass` 가 삼킨다.

재현했다 — 폴백 명령을 없는 경로로, TTS 서버를 닫힌 포트로 두고:

```
재생된 오디오: []        (아무 소리도 안 났다)
워커 생존=True, 0.02초
```

**로그도 안 남는다.** 실기에서 TTS 서버가 죽거나 WiFi 가 끊기면 로봇이 조용해지고,
운영자는 이유를 알 방법이 없다.

→ 최소한 실패를 **로그로 남겨야** 한다. 폴백 음성이 필요하면 Linux 경로
(`espeak-ng` 등)를 두거나, `reachy_mini.media.play_sound()` 로 "지금 대답할 수 없어요"
같은 사전 녹음을 재생하는 편이 현실적이다.

## 5. [높음] STT·LLM 주소를 설정으로 못 바꾼다

실기 토폴로지는 **앱이 로봇에서, 추론은 PC 에서** 도는 것이다. 그러면 세 주소가
전부 PC 를 가리켜야 하는데, 환경변수를 지원하는 것은 TTS 하나뿐이다.

| | 기본값 | 환경변수 |
|---|---|---|
| TTS | `127.0.0.1:8099` | `TTS_QWEN_URL` ✓ |
| STT | `127.0.0.1:8090` | **없음** |
| LLM | `127.0.0.1:8080` | **없음** |

`docs/demo-runbook.md` 는 "오디오 백엔드·TTS·서버 주소 3가지만 바꾸면 같은 코드가
실기에서 돈다"고 적었지만, 실제로는 **`stt.py`·`llm.py` 를 고쳐야 한다.**
`REACHY_STT_URL` / `REACHY_LLM_URL` 을 받게 하면 코드 수정 없이 끝난다.

## 6. [중간] 운영 스크립트가 macOS 전용

- `reachy.sh`: `install_name_tool`(rpath 자가치유), `say -v '?'`(상태 점검), `mjpython`(시뮬)

로봇에서는 이 스크립트를 쓸 수 없다. 다만 실기 토폴로지에서 **TTS·LLM·STT 는 PC 에
남으므로** `reachy.sh` 는 PC 쪽 기동 스크립트로 그대로 쓰고, 로봇에는 앱만 설치하는
분리가 자연스럽다. 그 경우 `reachy.sh` 에서 앱 실행 부분만 떼면 된다.

## 7. [중간] 네트워크가 끊기면 오래 매달린다

`tts.QWEN_TIMEOUT` 기본값이 **90초**다. 같은 파일 주석에 이유가 있다 —
"타임아웃으로 연결을 끊으면 서버가 그 소켓에 쓰다 죽는다(실측)".

로컬호스트에서는 타임아웃이 날 일이 거의 없어 안전한 값이었지만, **WiFi 를 타면
사정이 다르다.** 끊기면 한 발화가 90초를 매달리고, 짧게 잡으면 서버가 죽는다.
실기 이전 시 이 균형을 다시 봐야 한다(서버 측 수정이 필요할 수도 있다).

---

**아래 8~14 는 2026-08-11 SDK 소스·공식 스킬 대조에서 새로 나온 것이다.**
8·9·11·13·14 는 고쳤고 10·12 는 남았다.

## 8. [차단→고침] SDK 와 오디오 장치를 이중 점유한다

`main.py` 의 `request_media_backend` 가 `None` 이었다. 이 값은 SDK 에서 `"default"` 로
해석돼(`apps/app.py:46-50`) LOCAL 또는 WEBRTC 미디어 백엔드가 뜬다
(`reachy_mini.py:355-368`). 그 상태면 **데몬이 마이크·카메라를 쥐고 있는데**
`audio_in.MicCapture` 가 `autoaudiosrc` 로 같은 장치를 또 연다. USB 오디오는 보통
캡처 클라이언트를 하나만 받는다.

SDK 에 정확한 탈출구가 있다:

```python
# reachy_mini.py:342-350
if media_backend.lower() == "no_media":
    if not getattr(daemon_status, "no_media", False) and not self._media_released:
        self.release_media()
```

`release_media()` 의 docstring 이 우리 설계를 그대로 적는다 — *"After calling this,
the camera and microphone are available for direct access via OpenCV / **sounddevice**
/ etc."* 앱이 끝나면 `ReachyMini.__exit__` 이 `acquire_media()` 로 되돌리므로
데몬 상태를 남기지 않는다(idempotent).

→ **`request_media_backend = "no_media"`.** 영상 스트리밍을 안 쓰는 만큼 CM4 의 CPU 도
같이 아낀다. 박제: `tests/test_deployment_contract.py`(SDK 가 분기 문자열을 바꾸면 실패).

## 9. [차단→고침] `PyGObject` 를 조건 없이 선언했다

`pyproject.toml` 이 `"PyGObject"` 한 줄이었다. reachy-mini 자신은 이렇게 갈라 둔다:

```
PyGObject<=3.46.0,>=3.42.2 ; sys_platform == "linux"
gstreamer-bundle==1.28.3   ; sys_platform != "linux"
```

즉 비-Linux 에서 `gi` 는 `gstreamer_bundle` 이 공급한다. 조건 없는 선언은
macOS/Windows(Lite 구성 — 데몬·앱이 PC 에서 돈다)에서 pip 를 PyGObject 소스 빌드로
몰아 설치를 깨뜨리고, 상한이 없어 3.46 초과가 잡히면 SDK 핀과 충돌한다.

→ **`PyGObject>=3.42.2,<=3.46.0; sys_platform == 'linux'`.** 비-Linux 는 SDK 가 끄는
`gstreamer-bundle` 에 맡기고 재선언하지 않는다(정확 핀이라 충돌만 만든다).
빌드한 휠 METADATA 로 확인했다. 박제: 위와 같은 파일 — SDK 핀이 바뀌면 실패한다.

## 10. [높음] 환경변수가 데몬 유닛에 없으면 조용히 loopback 으로 붙는다

앱은 데몬 프로세스의 환경을 상속한다(`apps/manager.py:159` `app_env = os.environ.copy()`).
Wireless 에서 데몬은 **systemd 유닛**이므로, 운영자가 셸에서 `export REACHY_LLM_URL=…`
해도 앱은 못 본다. 유닛 드롭인을 고쳐야 하는데 그건 SDK 업데이트가 덮어쓴다.
공개 레퍼런스도 같은 자리에서 소스를 패치해야 했다.

나쁜 건 **실패가 조용하다**는 것이다 — 기본값 `127.0.0.1` 로 붙어 STT 는 빈 문자열,
LLM 은 예외 후 폴백 한 줄. "실패는 소리 내서 실패한다" 규칙에 걸린다.

→ 사다리를 하나 더 둔다: `환경변수 → 설정파일(platformdirs, SDK 가 이미 의존) → 기본값`.
기동 시 세 주소가 loopback 이면 경고를 찍는다. `custom_app_url`(현재 `None`) 설정
페이지도 정석 경로다.

## 11. [높음→고침] TTS 24 kHz 출력 vs 장치 16 kHz

`tts.QWEN_PCM_RATE = 24000` 으로 PortAudio 스트림을 열었다. 그런데 탑재 펌웨어
`ua_io16_lin` 의 `io16` 은 **USB 입출력 16 kHz** 를 뜻하고, SDK 도
`media/audio_base.py:59` 에서 `SAMPLE_RATE = 16000`,
`get_output_audio_samplerate() → 16000` 이다.

24k 스트림을 못 열면 `_afplay` 폴백으로 떨어진다 — 절마다 프로세스 기동이
**길이와 무관하게 0.8초 고정비**라(실측) 스트리밍으로 번 첫 청크 0.23초가 통째로
사라진다. 소리는 나지만 대화 리듬이 무너진다.

**TTS 서버에 16k 를 요청하는 길은 안 된다** — Qwen3-TTS 출력은 24 kHz 고정이다.
그래서 우리가 맞춘다.

→ `tts._open_output()` 이 **원본 레이트를 먼저 시도**하고(맥에서는 그대로 열려
리샘플이 안 낀다 — 시뮬 회귀 없음), 안 되면 `16000 → 48000 → 44100` 으로 내려가며
`tts._Resampler` 를 세운다. 물러날 때는 경고를 남긴다.
`REACHY_TTS_OUT_RATE=16000` 으로 탐색을 건너뛸 수 있다.

리샘플러는 **청크 경계에서 필터 상태를 잇는다.** `scipy.signal.resample_poly` 를
청크마다 부르면 상태가 매번 0 에서 시작해 85ms 마다 클릭이 난다. numpy 만 쓰고
(새 의존성 없음) 비용은 실시간 대비 **0.05%**, 청크당 0.042ms 다(이 맥 실측).

**남은 미검증**: 로봇 스피커가 PortAudio 로 잡히는지 자체는 여전히 확인 대상이다
(미검증 1번). 잡히기만 하면 레이트는 이제 맞춰진다.

## 12. [중간] 사용자 발화 중에도 모터가 돈다

XVF3800 의 AEC 는 **스피커 반향**을 지우지 별개인 **모터 소음**은 지우지 않는다.
그런데 `driver.RobotDriver` 가 100 Hz 로 **항상** 목표를 쓴다 — 모션이 없어도
호흡(`animator.BREATH_*`)으로 계속 움직인다("illusion of life"). `Idler` 는 소리 없이
대기 모션을 돌리는데 그때도 서보 9개는 돈다.

시뮬에는 모터 소음이 없어 구조적으로 안 드러난다. 실기에서는 VAD 적응 임계와
끼어들기 결합계수 추정이 모터 소음을 소음 바닥으로 학습해 흔들린다.

→ `vad.active`(발화 수집 중)이면 sway 진폭을 접고 Idler 를 억제한다. 단일 루프가
됐으므로 이제 **한 곳(`RobotDriver._secondary`)만 고치면 된다.**
`REACHY_AEC` 와 달리 이건 **실기에서만 필요한** 것이므로 기본 켬이 맞다.

## 13. [차단→고침] `no_media` 가 감정 모션 발성을 죽였다

§8 의 부작용이다. SDK 의 `play_move(sound=True)` 는 `media_manager.play_sound()` 로
발성을 내는데, `no_media` 면 `MediaManager.audio` 가 None 이라
*"Audio system is not initialized."* 경고 한 줄만 남기고 **조용히 무시한다**
(`media/media_manager.py:271`). 감정 라이브러리 85개 중 **84개가 `.ogg` 를 갖고
있고, 우리가 쓰는 17개는 전부** 갖는다 — 응답 모션이 전부 무음이 될 뻔했다.

→ 발성을 우리 재생 경로로 옮겼다(`sound.py` → `tts.Speaker.play_sound`). 되돌리는
것(=`no_media` 철회)은 답이 아니다 — §8 의 장치 이중 점유가 돌아온다.

옮긴 편이 원래보다 낫다. 셋이 따라온다:

1. **게이팅이 사운드 길이를 따라간다.** 예전에는 `player.busy`(=모션 길이)를 봤는데
   **9개 모션은 사운드가 모션보다 길다**(실측, 최대 `welcoming1` +1.43초). 그동안
   마이크가 자기 발성 꼬리를 주웠고 `POST_PLAYBACK_GUARD_S=0.3` 으로는 못 덮었다.
2. **끼어들기가 모션 구간에도 동작한다**(§14).
3. 발성이 §11 의 리샘플러를 타므로 실기 16 kHz 장치에서도 그대로 난다.

**길이 정책**: 리액션 발성은 2~12초라 답변 앞에 통째로 붙이면 대화가 그만큼 늦는다.
발성의 원래 역할이 LLM 지연 구간을 메우는 것이므로 앞 1.2초만 쓰고 페이드아웃한다
(`REACHY_MOTION_SOUND_S`). 공연(춤)은 요청 자체가 목적이라 16~19초 전체를 낸다.

## 14. [중간→고침] 응답 모션 동안 로봇이 귀머거리였다

`voice_loop` 가 `speaker.speaking` 과 별개로 `player.busy` 를 보고 프레임을 통째로
버렸다. 춤은 17~18초라 **끼어들기를 켜 놔도 그동안은 "미니야"조차 안 들렸다.**

원인은 모션 발성이 SDK 미디어로 나가 우리 에코 추정에 안 잡혔다는 것뿐이다.
§13 으로 발성이 `speaker` 를 타면서 `_note_output`·에코 프로브에 들어오므로
`player.busy` 하드 게이팅을 걷어냈다. 끼어들기가 걸리면 `player.cancel()` 로
**몸도 함께 멈춘다** — 소리만 끊고 18초를 마저 추면 끊긴 것이 아니다.

## 미검증 — 하드웨어가 있어야 확인된다

1. **스피커 출력 경로.** 현재 `StreamPlayer` 는 `sounddevice`(PortAudio)로 직접
   출력한다. 그런데 SDK 에는 `reachy_mini.media.play_sound()` 가 있고
   `main.py` 템플릿도 그걸 쓴다. 로봇의 스피커가 PortAudio 로 잡히는지, 아니면
   데몬/미디어 백엔드를 거쳐야만 하는지 확인해야 한다. **후자면 재생 경로를
   통째로 바꿔야 한다.**
2. ~~**`request_media_backend`.**~~ **해소(2026-08-11, SDK 소스)** → §8.
   `"no_media"` 로 정했다. 남은 미검증은 그 값으로 데몬이 실제로 장치를 놓아 주는지,
   그 뒤 `autoaudiosrc` 가 XVF3800 을 잡는지다(1번과 같이 확인한다).
3. **CM4 성능.** 앱 자체(VAD·절 분할·모션)는 가볍지만 실측한 적이 없다. 추론 3종은
   PC 로 빠지므로 병목은 아닐 것으로 보이나, 상대는 Pi 5 가 아니라 **RAM 4 GB CM4** 다.
4. **마이크 어레이·XMOS AEC.** 시뮬에는 없어 끼어들기(half-duplex) 제약을 그대로
   뒀다. 실기에서 AEC 가 되면 이 설계를 다시 볼 수 있다. 단 AEC 는 스피커 반향만
   지운다 — 모터 소음은 §12 로 따로 다룬다.
5. ~~**오디오 샘플레이트.**~~ **해소(2026-08-11)** → §11. 안 맞는 것이 거의 확실해서
   (펌웨어 `io16` + SDK `SAMPLE_RATE = 16000`) 장치가 받는 레이트로 리샘플하게 했다.
   실기에서는 어느 경로를 탔는지 기동 로그의 리샘플 경고 유무로 확인한다.

## 적용한 수정 (2026-07-30)

1. **`main.py`** — `VoiceChat.run(reachy_mini, stop_event)` 이 대화 루프를 돌린다.
   공통 로직은 **`session.py`** 로 뽑았다(`announce_voice`/`build`/`respond`) —
   진입점이 CLI 스크립트를 import 하던 구조를 없앴다. `demo.py` 는 이제
   `--text`/`--no-robot` 폴백만 담은 얇은 래퍼다.
   **`reachy.sh` 의 기본 경로도 `main.py` 로 바꿨다** — 시연에서 돌리는 것과
   배포하는 것을 같게 두려는 것이다. 예전에는 데모가 `demo.py` 만 태워서
   `main.py` 가 생성 템플릿인 채로 방치된 것을 아무도 몰랐다.
   시뮬 데몬에 붙어 음성 모드 진입 → SIGINT 종료(코드 0)까지 확인했다.
   - `build(mini=...)` 로 주입된 인스턴스는 **컨텍스트로 잡지 않는다**(이중 해제 방지).
     직접 만드는 시뮬 경로는 종전대로 `stack.enter_context`.
   - `voice_loop(..., should_stop=stop_event.is_set)` — 프레임마다(30ms) 확인한다.
     단 `respond()` 안에서는 확인하지 않는다(자기소개 대본은 한 번 시작하면 ~50초).
2. **`audio_in.py`** — `autoaudiosrc`. 장치를 강제하려면 `REACHY_MIC_SRC`
   (예: `alsasrc device=hw:1`). macOS 에서 캡처 회귀 확인.
3. **`pyproject.toml`** — 실제 import 를 대조해 `numpy`·`requests`·`sounddevice`·
   `PyGObject` 추가. (`pydantic` 은 템플릿의 설정 페이지를 걷어내며 함께 빠졌다.)
4. **`stt.py`·`llm.py`** — `REACHY_STT_URL`·`REACHY_LLM_URL`.
   TTS 의 `TTS_QWEN_URL` 과 합쳐 **세 주소 모두 코드 수정 없이 PC 를 가리킨다.**
5. **`tts.py`** — 폴백 사다리를 `shutil.which` 로 고른다:
   합성은 `say` → `espeak-ng` → `espeak`, 재생은 `afplay` → `paplay` → `aplay`.
   아무것도 없으면 **경고를 남긴다**(발화마다 반복하지 않고 한 번). `_worker` 의
   `except Exception: pass` 도 예외를 찍도록 바꿨다 — 이게 무음의 진짜 원인이었다.

### 남은 일

- 실기에서 **스피커 출력 경로** 확인. PortAudio 로 안 잡히면 `StreamPlayer` 를
  `reachy_mini.media` 기반으로 교체해야 한다(아래 미검증 1번).
- `QWEN_TIMEOUT` 90초를 실기 네트워크에서 재조정.
- 절 단위 직렬 재생(합성↔재생이 겹치지 않음) — 오디오 49초가 68초에 재생된다.
