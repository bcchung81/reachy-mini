# 실기(Reachy Mini) 배포 전 검증

- 검증일: 2026-07-30 · 시뮬 개발 코드를 실기에 올릴 때 무엇이 깨지는지 확인
- **실기가 없으므로 정적 분석 + 이 맥에서 재현 가능한 실험으로만 확인했다.**
  하드웨어가 필요한 항목은 아래 "미검증"에 따로 적었다.

## 요약 — 지금 상태로는 배포되지 않는다

| | 항목 | 근거 |
|---|---|---|
| **차단** | `main.py` 가 생성 템플릿 그대로 — 음성대화가 없다 | 코드 확인 |
| **차단** | `osxaudiosrc` 하드코딩 — Linux 에 없는 엘리먼트 | 코드 + 엘리먼트 조회 |
| **차단** | 의존성 미선언 — `pyproject` 에 `reachy-mini` 만 | import 대조 |
| **높음** | TTS 실패 시 **조용히 벙어리** (폴백이 macOS 전용) | 재현 실험 |
| **높음** | STT·LLM 주소를 환경변수로 못 바꾼다 | 코드 확인 |
| 중간 | `demo.sh`·`check_env.sh` 가 macOS 전용 | 코드 확인 |
| 중간 | 네트워크 단절 시 90초 행 + 서버 사망 위험 | 코드 + 기존 실측 주석 |

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

## 권장 순서

1. `main.py` 에 `demo.py` 루프 이식 (**이게 없으면 나머지는 의미 없다**)
2. `osxaudiosrc` → `autoaudiosrc`, `pyproject` 의존성 채우기
3. STT·LLM 주소 환경변수화
4. TTS 실패를 로그로 남기고, Linux 폴백 또는 사전 녹음 안내음 결정
5. 실기에서 스피커 출력 경로 확인 → 필요하면 `StreamPlayer` 교체
