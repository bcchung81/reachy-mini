# 실기(Reachy Mini) 배포 전 검증

- 검증일: 2026-07-30 · 시뮬 개발 코드를 실기에 올릴 때 무엇이 깨지는지 확인
- **실기가 없으므로 정적 분석 + 이 맥에서 재현 가능한 실험으로만 확인했다.**
  하드웨어가 필요한 항목은 아래 "미검증"에 따로 적었다.

## 요약 — 코드 쪽 차단 요인은 해소됐다 (2026-07-30 수정)

| | 항목 | 상태 |
|---|---|---|
| ~~차단~~ | `main.py` 가 생성 템플릿 그대로 | **고침** — `VoiceChat.run` 이 대화 루프를 돌린다 |
| ~~차단~~ | `osxaudiosrc` 하드코딩 | **고침** — `autoaudiosrc`(+ `REACHY_MIC_SRC`) |
| ~~차단~~ | 의존성 미선언 | **고침** — numpy·requests·sounddevice·PyGObject 선언 |
| ~~높음~~ | TTS 실패 시 조용히 벙어리 | **고침** — 플랫폼별 폴백 + 경고 로그 |
| ~~높음~~ | STT·LLM 주소 고정 | **고침** — `REACHY_STT_URL`·`REACHY_LLM_URL` |
| 중간 | `demo.sh`·`check_env.sh` 가 macOS 전용 | 남음 — PC 쪽 스크립트로 쓰면 문제 없다 |
| 중간 | 네트워크 단절 시 90초 행 | 남음 — 실기 네트워크에서 재조정 필요 |
| **미검증** | 스피커 출력 경로, Pi5 성능, 샘플레이트 | 하드웨어 필요 |

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

`audio_in.py:88`:

```python
Gst.parse_launch(
    "osxaudiosrc ! audioconvert ! audioresample "
    ...
```

`osxaudiosrc` 는 macOS 전용이다. Pi5(Linux)에는 없어 `Gst.parse_launch` 가 실패한다.

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

- `tts.py:274` — qwen 실패 시 `["say", "-v", voice]`
- `tts.py:126` — 스트림을 못 열면 `["afplay", ...]`

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

- `demo.sh`: `install_name_tool`(rpath 자가치유), `say -v '?'`(상태 점검)
- `check_env.sh`: `say -v '?' | grep -q Yuna`

로봇에서는 이 스크립트를 쓸 수 없다. 다만 실기 토폴로지에서 **TTS·LLM·STT 는 PC 에
남으므로** `demo.sh` 는 PC 쪽 기동 스크립트로 그대로 쓰고, 로봇에는 앱만 설치하는
분리가 자연스럽다. 그 경우 `demo.sh` 에서 앱 실행 부분만 떼면 된다.

## 7. [중간] 네트워크가 끊기면 오래 매달린다

`tts.py:38` 의 `QWEN_TIMEOUT` 기본값이 **90초**다. 같은 파일 주석에 이유가 있다 —
"타임아웃으로 연결을 끊으면 서버가 그 소켓에 쓰다 죽는다(실측)".

로컬호스트에서는 타임아웃이 날 일이 거의 없어 안전한 값이었지만, **WiFi 를 타면
사정이 다르다.** 끊기면 한 발화가 90초를 매달리고, 짧게 잡으면 서버가 죽는다.
실기 이전 시 이 균형을 다시 봐야 한다(서버 측 수정이 필요할 수도 있다).

## 미검증 — 하드웨어가 있어야 확인된다

1. **스피커 출력 경로.** 현재 `StreamPlayer` 는 `sounddevice`(PortAudio)로 직접
   출력한다. 그런데 SDK 에는 `reachy_mini.media.play_sound()` 가 있고
   `main.py` 템플릿도 그걸 쓴다. 로봇의 스피커가 PortAudio 로 잡히는지, 아니면
   데몬/미디어 백엔드를 거쳐야만 하는지 확인해야 한다. **후자면 재생 경로를
   통째로 바꿔야 한다.**
2. **`request_media_backend`.** `main.py` 주석에 "wireless 에서는
   `gstreamer_no_video` 로 CPU 를 아끼라"고 돼 있다. 현재 `None` 이다.
3. **Pi5 성능.** 앱 자체(VAD·절 분할·모션)는 가볍지만 실측한 적이 없다.
   추론 3종은 PC 로 빠지므로 병목은 아닐 것으로 보이나 확인이 필요하다.
4. **마이크 어레이·XMOS AEC.** 시뮬에는 없어 끼어들기(half-duplex) 제약을 그대로
   뒀다. 실기에서 AEC 가 되면 이 설계를 다시 볼 수 있다.
5. **오디오 샘플레이트.** TTS 출력이 24 kHz 다. 로봇 스피커가 받는 레이트와
   맞는지, 리샘플이 필요한지 미확인.

## 적용한 수정 (2026-07-30)

1. **`main.py`** — `VoiceChat.run(reachy_mini, stop_event)` 이 `demo.py` 의
   `build`/`respond`/`voice_loop` 를 그대로 쓴다. 대화 로직은 한 곳에만 있다.
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
