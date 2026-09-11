# 2대 구성 — 오프라인 준비 절차

시연 전에 **사람이 해야 하는 일**만 모았다. 코드는 다 됐고, 여기서부터는 기기·네트워크·확인이다.
근거는 `docs/superpowers/specs/2026-09-11-two-robot-mc-docent-design.md` §6·§9.

---

## 0. 준비물

| | |
|---|---|
| Reachy Mini **Wireless 2대** | 사회자용 / 도슨트용 |
| 노트북 | 무대감독 + LLM·STT·TTS 3종이 여기서 돈다 |
| **전용 무선공유기 1대** | 시연장 공용 WiFi를 쓰지 않는다 — 이유는 §2 |
| Reachy Mini Control 앱 | https://hf.co/reachy-mini/#/download |
| 라벨·매직 | 로봇 본체에 역할을 물리적으로 표시한다 |

---

## 1. WiFi 등록 — ⚠️ **반드시 한 대씩**

두 로봇 모두 처음 켜면 자기 핫스팟을 띄우는데, **SSID가 `reachy-mini-ap` 로 똑같다**
(`daemon/app/routers/wifi_config.py:25`). 둘을 동시에 켜두면 노트북이 어느 쪽에 붙었는지
알 방법이 없고, 사회자 설정이 도슨트에 들어간다.

### 순서

1. **A만 켠다.** B는 전원을 끈 채로 둔다.
2. 노트북에서 **Reachy Mini Control** 실행 → 하단 **"First time connecting…"**
3. 안내대로 로봇 핫스팟(`reachy-mini-ap`)에 노트북을 접속
4. 전용 공유기의 SSID·비번 입력 → 로봇이 그 망으로 재접속
5. 연결 확인 후 **A를 끈다**
6. **B만 켜고** 2~4를 반복
7. 둘 다 켠다

> **핫스팟이 안 보이면** — Control 앱의 "Try the Bluetooth Console" 로 간다.
> Chrome·Edge·Opera 에서 Web Bluetooth 로 붙어 핫스팟 리셋·네트워크 상태를 볼 수 있다.

### 왜 전용 공유기인가

- 시연장 공용 AP는 **AP isolation** 이 켜진 경우가 많다 → 노트북↔로봇 통신이 아예 막힌다
- 로봇 데몬의 REST/WebSocket API에 **인증이 없다**. Wireless 는 `0.0.0.0` 에 바인드한다
  (`daemon/app/main.py:119`) — 공용망에 올리면 누구나 로봇을 조작할 수 있다
- Wireless 안테나는 2.79 dBi 패치 하나뿐이다. 공유기를 로봇 가까이 둔다. 5GHz 권장

---

## 2. 고정 IP 배정 — ⚠️ `reachy-mini.local` 을 믿지 않는다

두 로봇의 hostname이 **둘 다 `reachy-mini`** 다. `.local` 이 어느 쪽을 가리키는지
보장되지 않고, 부팅 순서에 따라 바뀐다.

공유기 관리페이지에서 **MAC 기준 DHCP 고정 IP**를 배정한다.

```
사회자  192.168.0.41
도슨트  192.168.0.42
노트북  192.168.0.10        (무대감독·추론 3종이 여기)
```

주소는 예시다. 실제 대역에 맞춰 정하고 **적어둔다** — 다음 단계에서 쓴다.

### 확인

```bash
curl -s http://192.168.0.41:8000/api/daemon/status | head -c 200
curl -s http://192.168.0.42:8000/api/daemon/status | head -c 200
```

둘 다 JSON이 나와야 한다. 안 나오면 IP가 틀렸거나 같은 망이 아니다.

---

## 3. 기기 식별자(`unit_id`) 채취 — 두 대가 뒤바뀌는 사고를 막는다

로봇마다 하드웨어 고유 ID가 있다. 무대감독이 기동할 때 이 값을 대조해서
**사회자 자리에 도슨트가 있으면 즉시 실패**한다. 시연장에서 "왜 얘가 저 대사를 하지"를
추적하는 것보다 기동에서 막는 게 싸다.

```bash
curl -s http://192.168.0.41:8000/api/daemon/status | python3 -c "import sys,json;print(json.load(sys.stdin)['hardware_id'])"
curl -s http://192.168.0.42:8000/api/daemon/status | python3 -c "import sys,json;print(json.load(sys.stdin)['hardware_id'])"
```

나온 값을 적어둔다. **`null` 이 나오면** 그 로봇은 Wireless 가 아니거나 오디오 장치가
안 잡힌 것이다 — 시뮬에서는 언제나 `null` 이지만 실기에서는 값이 있어야 한다.

---

## 4. 로봇 대시보드에서 startup-app 을 비운다

로봇 브라우저 대시보드(`http://<로봇IP>:8000`)에서 **자동 시작 앱을 없음으로** 둔다.

LAN 으로 붙는 SDK 클라이언트는 로봇의 앱 락을 우회한다
(`daemon/robot_app_lock.py`). 온보드 앱이 켜져 있으면 우리 앱과 모터를 두고 싸운다.

**두 대 모두** 확인한다.

---

## 5. 물리 배치와 라벨

- 두 로봇을 **서로 마주보되 관람객도 보이는** 각도로 놓는다. 시선 연출(`gaze: partner`)이
  여기 의존한다
- 로봇 본체에 **사회자 / 도슨트 라벨**을 붙인다. 겉모습이 같아서 운영 중에 헷갈린다
- 스피커 음량을 귀로 맞춘다 — 한쪽이 묻히면 대화로 안 들린다

---

## 6. 설정 파일 채우기

`scripts/stage-env.sh` 의 `PC_IP` 를 노트북 IP로 바꾸고, 채취한 `unit_id` 를 넣는다.

**노트북(무대감독)에서:**
```bash
export REACHY_MC_UNIT=<사회자 hardware_id>
export REACHY_DOCENT_UNIT=<도슨트 hardware_id>
export REACHY_DIRECTOR_PORT=8777
```

**각 로봇에서:**
```bash
PC_IP=192.168.0.10 source scripts/stage-env.sh mc       # 사회자 로봇
PC_IP=192.168.0.10 source scripts/stage-env.sh docent   # 도슨트 로봇
```

이 스크립트가 `REACHY_ROLE` · 무대감독 주소 · 추론 3종 주소를 한꺼번에 넣는다.
음성(사회자 `serena` / 도슨트 `sohee`)은 `main.py` 가 역할에 맞춰 자동으로 넣는다 —
**직접 `TTS_QWEN_VOICE` 를 지정하면 그쪽이 이긴다.**

---

## 7. 기동 순서

```
① 공유기 켜기
② 로봇 2대 켜고 WiFi 붙는 것 확인 (curl 로 status 200)
③ 노트북에서 추론 3종 기동      ./reachy.sh (LLM·STT·TTS)
④ 무대감독 기동                 .venv/bin/python -m stage
⑤ 각 로봇에서 앱 실행           (역할 환경변수를 넣은 뒤)
```

무대감독 콘솔에 두 로봇이 붙었다는 로그가 뜨면 `s` 를 눌러 시작한다.

| 키 | |
|---|---|
| `s` | 시작 |
| `n` | 다음 큐 |
| `r` | 현재 큐 다시 |
| `a` | 즉시 중단 |
| `q` | 종료 |

**콘솔은 비상용이다.** 정상 진행은 관람객이 "다음"·"계속" 이라고 말하면 된다.

---

## 8. 시연 전 마지막 확인

- [ ] 두 로봇 다 `curl .../api/daemon/status` 가 200
- [ ] `hardware_id` 두 개가 설정값과 일치 (무대감독이 기동 시 확인해준다)
- [ ] 두 로봇 startup-app 비어 있음
- [ ] `REACHY_AEC` **꺼짐** — 실기는 XMOS 하드웨어 AEC 가 그 자리를 대신한다
- [ ] 기동 로그에 추론 3종 주소가 노트북을 가리킴 (loopback 이면 경고가 뜬다)
- [ ] 한 큐를 끝까지 돌려본다: 사회자 → 도슨트 → "다음"
- [ ] **로봇 한 대를 일부러 꺼본다** — 남은 한 대가 양쪽 대사를 읽는지(1인 모드),
      경고가 누가 끊겼는지 말하는지

---

## 9. 아직 검증되지 않은 것 (실기가 있어야 한다)

- **음성 연출의 청감** — 사회자 1.27배속 / 도슨트 1.13배속은 1.2 기준으로 환산한
  값이고, 그 조합으로 들어보지 않았다. 두 목소리가 실제로 구분되는지 귀로 확인한다
- **두 로봇 스피커 간 음향 간섭** — 턴은 게이팅으로 막지만 잔향은 남는다
- **CM4(RAM 4GB)에서 기존 앱 + 무대감독 클라이언트 동시 구동 시 메모리 여유**
- **PC 추론 부하** — 단일 창구라 1대분으로 예상하나 실측하지 않았다
