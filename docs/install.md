# 실기 2대 설치 — 사회자 + 도슨트

Reachy Mini Wireless **두 대**에 전파체험관 팟캐스트 구성을 처음 올리는 절차다.
기기를 새로 받았을 때 한 번만 하는 일을 모았다. 매 시연마다 하는 일은
`docs/two-robot-offline-test.md` 에 있다.

- 설계 근거: `docs/superpowers/specs/2026-09-11-two-robot-mc-docent-design.md`
- 실기 위험: `docs/real-robot-deployment.md` §15
- 밟은 지뢰: `docs/lessons.md`

**⚠️ 설치에는 인터넷이 필요하다.** 6단계의 `pip install` 이 로봇에서 패키지를 내려받는다.
시연장에 들고 가기 **전에**, 인터넷이 되는 곳에서 6단계까지 끝내 둔다. 시연 당일에는
인터넷 없이 기동만 한다.

---

## 0. 준비물

| | |
|---|---|
| Reachy Mini **Wireless 2대** | 사회자용 / 도슨트용 |
| 노트북 (Apple Silicon) | 무대감독 + 추론 3종이 여기서 돈다 |
| **전용 무선공유기 1대** | 5GHz 권장. 이유는 §1 |
| Reachy Mini Control 앱 | https://hf.co/reachy-mini/#/download |
| 라벨·매직 | 두 로봇의 겉모습이 같다. 물리적으로 표시한다 |

---

## 1. 네트워크 — 전용 공유기

**시연장 공용 WiFi 를 쓰지 않는다.** 두 가지 이유가 공식 문서로 확인된다.

- 공용 AP 는 **client isolation** 이 켜진 경우가 많다. Pollen 공식 FAQ 의 문장 그대로다.
  *"Many conference and hotel WiFi networks enable client isolation, which prevents devices
  on the same network from communicating with each other."* 양쪽 다 연결돼 있고 같은
  서브넷 IP 를 받았는데 서로의 HTTP 에 못 닿는다.
- 로봇 데몬의 REST/WebSocket API 에 **인증이 없다.** Wireless 는 `0.0.0.0` 에 바인드한다.
  공용망에 올리면 누구나 로봇을 조작할 수 있다.

공유기는 로봇 가까이 둔다. Wireless 안테나는 2.79 dBi 패치 하나뿐이다.

### 대안 — 노트북을 AP 로 (공유기가 없을 때)

macOS 인터넷 공유로 맥이 AP 가 될 수 있다. 상자가 하나 줄고, 맥 주소가 `192.168.2.1` 로
항상 고정이라 로봇 설정이 영원히 같아지는 이점이 있다.

**⚠️ 지금 이 경로는 코드가 지원하지 않는다.** `reachy.sh` 의 `lan_ip()` 가 인터페이스를
`en0 en1 en7` 만 훑는데, 맥이 AP 가 되면 `en0` 이 `bridge100` 으로 묶이며 IPv4 주소를
잃는다. `robot up` 이 "맥의 LAN 주소를 찾지 못했다" 로 멈춘다. 쓰려면 그 목록에
`bridge100` 을 더해야 한다. 두 곳이다 — `lan_ip()` 함수와 `run_serve` 안의 같은 루프.

절차는 이렇다. 먼저 **WiFi 가 아닌 원본 인터페이스**가 있어야 한다. 무선이 하나뿐이라
WiFi 에서 WiFi 로는 공유가 안 된다. 아이폰 USB 테더링이나 USB 이더넷 어댑터를 붙인다.

1. 시스템 설정 → 일반 → 공유 → **인터넷 공유** 의 ⓘ
2. **다음으로부터 연결 공유** 를 iPhone USB 또는 USB 이더넷으로 바꾼다
3. 그러면 아래 목록에 **Wi-Fi 가 나타난다.** 체크한다
4. **Wi-Fi 옵션** — 이름, 5GHz 채널, WPA2 개인용, 암호 8자 이상
5. 스위치를 켠다. 맥의 기존 WiFi 연결은 끊어진다

확인은 한 줄이다.

```bash
ifconfig bridge100 | grep "inet "     # inet 192.168.2.1 이 나와야 한다
```

### 되지 않는 방법 — 로봇 핫스팟 2개에 각각 붙기

"노트북이 A 핫스팟과 B 핫스팟에 동시에 붙으면 공유기가 필요 없지 않나" 는 안 된다.
다섯 가지가 동시에 막는다. 하나만 있어도 안 되는데 다섯이다.

1. **맥에 WiFi 무선이 하나뿐이다.** 하나는 한 번에 한 망에만 붙는다.
2. **Apple Silicon 에 WiFi 어댑터를 더 못 꽂는다.** Apple 이 USB WiFi 용 OS 드라이버를
   허용하지 않는다. NetworkingDriverKit 이 이더넷만 지원한다.
3. **로봇은 핫스팟과 클라이언트를 동시에 못 한다.** SDK 의 `WifiMode` 가 배타적이다
   (`HOTSPOT` | `WLAN` | `DISCONNECTED` | `BUSY`). 핫스팟을 켠 로봇은 다른 어떤 망에도 없다.
4. **두 핫스팟의 SSID 와 비밀번호가 같다.** 소스에 박혀 있다 —
   `HOTSPOT_SSID = "reachy-mini-ap"`, `HOTSPOT_PASSWORD = "reachy-mini"`.
5. **두 핫스팟의 IP 대역까지 같다.** nmcli 공유 모드가 `10.42.0.1/24` 를 쓴다.
   두 인터페이스가 같은 게이트웨이를 가져 라우팅이 무너진다.

---

## 2. WiFi 등록 — ⚠️ 반드시 한 대씩

**두 로봇의 핫스팟 SSID 가 같다**(§1 의 4번). 둘을 동시에 켜두면 노트북이 어느 쪽에
붙었는지 알 수 없고, 사회자 설정이 도슨트에 들어간다.

1. **A 만 켠다.** B 는 전원을 끈 채로 둔다.
2. 노트북에서 Reachy Mini Control 실행 → 하단 **"First time connecting…"**
3. 안내대로 로봇 핫스팟(`reachy-mini-ap`)에 노트북을 접속한다
4. 공유기의 SSID·비밀번호를 입력한다. 로봇이 그 망으로 옮겨 간다
5. 연결을 확인하고 **A 를 끈다**
6. **B 만 켜고** 2~4 를 반복한다
7. 둘 다 켠다. 본체에 **사회자 / 도슨트 라벨**을 붙인다

핫스팟이 안 보이면 Control 앱의 "Try the Bluetooth Console" 로 간다. Chrome·Edge·Opera 에서
Web Bluetooth 로 붙어 핫스팟을 리셋할 수 있다.

> 한 대씩 켜는 규칙은 **이 단계에만** 적용된다. 공유기 망에 붙은 뒤로는 동시에 켜도 된다.

---

## 3. 고정 IP — `reachy-mini.local` 을 믿지 않는다

두 로봇의 hostname 이 **둘 다 `reachy-mini`** 다. SDK 소스가 mDNS 등록에
`socket.gethostname()` 을 그대로 쓰고(`utils/discovery.py:133`), `robot_name` 기본값도
모든 기기에서 `reachy_mini` 다. 두 대를 켜면 같은 이름을 주장한다.

공유기 관리페이지에서 **MAC 기준 DHCP 고정 IP** 를 배정한다.

```
사회자  192.168.0.4
도슨트  192.168.0.5
노트북  192.168.0.10
```

사회자·도슨트 두 주소가 `./reachy.sh start --robot` 의 **기본값**이다. 대역이 달라 다른 주소를
주면 **적어두고** 기동할 때 `REACHY_MC_HOST`/`REACHY_DOCENT_HOST` 로 덮어쓴다. 이 뒤로 두 로봇을
가르는 것은 IP 하나뿐이다. MAC 주소는 여기서만 쓰고 다시 볼 일이 없다.

확인:

```bash
curl -s http://192.168.0.4:8000/api/daemon/status | head -c 200
curl -s http://192.168.0.5:8000/api/daemon/status | head -c 200
```

둘 다 JSON 이 나와야 한다.

---

## 4. SSH 공개키 등록 — ⚠️ 빠뜨리면 배포가 안 된다

`reachy.sh` 의 SSH 헬퍼(`rssh`)와 로그 팔로우가 `BatchMode=yes` 로 붙는다.
**비밀번호를 아예 묻지 않고 그냥 실패한다.** 공개키가 미리 등록돼 있어야 한다.
스크립트에 이 준비 단계가 없으므로 손으로 한다.

(`robot deploy` 의 rsync 는 BatchMode 가 아니라 암호를 물을 수는 있다. 그래도 두 대에
매번 치게 되고, 같은 명령 안의 `rssh` 단계에서 어차피 막힌다. 키를 넣는 것이 맞다.)

```bash
ssh-copy-id pollen@192.168.0.4
ssh-copy-id pollen@192.168.0.5
```

비밀번호는 `root` 다. 확인:

```bash
ssh -o BatchMode=yes pollen@192.168.0.4 echo ok     # ok 가 나와야 한다
ssh -o BatchMode=yes pollen@192.168.0.5 echo ok
```

빠뜨리면 `robot up` 이 설정 동기화 단계에서 "config 를 쓰지 못했다" 로 멈춘다.
소리 내서 죽으니 조용한 실패는 아니지만, 시연 준비 중에 처음 만나면 시간을 쓴다.

---

## 5. 기기 식별자(`hardware_id`) 채취

무대감독이 기동할 때 이 값을 대조해 **사회자 자리에 도슨트가 있으면 거부**한다.
시연장에서 "왜 얘가 저 대사를 하지" 를 추적하는 것보다 기동에서 막는 게 싸다.

```bash
curl -s http://192.168.0.4:8000/api/daemon/status | python3 -c "import sys,json;print(json.load(sys.stdin)['hardware_id'])"
curl -s http://192.168.0.5:8000/api/daemon/status | python3 -c "import sys,json;print(json.load(sys.stdin)['hardware_id'])"
```

나온 값을 적어둔다. §8 의 `REACHY_MC_UNIT` / `REACHY_DOCENT_UNIT` 에 들어간다.

`null` 이 나오면 그 로봇은 오디오 장치가 안 잡힌 것이다. `get_hardware_id()` 가 리눅스
sysfs 를 읽으므로 시뮬에서는 언제나 `null` 이지만 실기에서는 값이 있어야 한다.

---

## 6. 첫 앱 설치 — ⚠️ `apps_venv` 가 아직 없다

**여기가 갓 받은 로봇에서 가장 많이 막히는 자리다.**

`./reachy.sh robot deploy` 는 `/venvs/apps_venv/.../site-packages/voice_chat` 에 rsync 한다.
그런데 그 디렉토리는 **데몬이 앱을 처음 설치할 때 생긴다.** 앱을 한 번도 안 깐 로봇의
`/venvs` 에는 `mini_daemon` 뿐이다. 그래서 첫 설치만 손으로 한다.

그리고 **REST API 로는 못 넣는다.** `POST /api/apps/install` 의 설치 경로는 HF Space
전용이고, 로컬 경로는 `"source_kind 'local' is not installable via the API"` 로 거절된다.
대시보드의 Install 버튼도 같은 길이다. SSH 직접 설치가 유일한 경로다.

### 6.1 로봇에 `apps_venv` 를 만든다 (두 대 모두)

데몬 버전을 먼저 읽는다. **데몬과 같은 버전으로 고정**해야 데몬이 띄우는 서브프로세스와
어긋나지 않는다.

```bash
ssh pollen@192.168.0.4
/venvs/mini_daemon/bin/python -c "from importlib.metadata import version; print(version('reachy-mini'))"
```

나온 값을 `<버전>` 에 넣는다. **데몬과 같은 파이썬으로** venv 를 만든다.

```bash
/venvs/mini_daemon/bin/python -m venv /venvs/apps_venv
/venvs/apps_venv/bin/pip install "reachy-mini==<버전>"
exit
```

### 6.2 앱을 설치한다 (노트북에서, 두 대 모두)

```bash
rsync -az --exclude '__pycache__/' --exclude 'build/' --exclude '*.egg-info/' \
  apps/voice_chat/ pollen@192.168.0.4:/home/pollen/voice_chat/
ssh pollen@192.168.0.4 "/venvs/apps_venv/bin/pip install /home/pollen/voice_chat"
```

데몬은 `reachy_mini_apps` 엔트리포인트로 앱을 찾는다. `pyproject.toml` 이 선언한다 —
`voice_chat = "voice_chat.main:VoiceChat"`.

### 6.3 확인

```bash
curl -s http://192.168.0.4:8000/api/apps/list-available/installed
ssh pollen@192.168.0.4 "ls -d /venvs/apps_venv/lib/python*/site-packages/voice_chat"
```

목록에 `voice_chat` 이 보여야 한다. 그리고 두 번째 명령이 찍는 경로가 **`python3.12`**
여야 한다. `reachy.sh` 의 `ROBOT_SITE` 가 그 버전을 박아 두고 있다. 다르면 그 변수를 고친다.

> **⚠️ `POST /cache/reset-apps` 를 부르지 않는다.** 이름은 캐시 정리처럼 보이지만 실제
> 동작은 `apps_venv` 삭제다. 20분 걸려 깐 469MB 가 통째로 사라진다. 설치 확인은 읽기
> 전용인 `GET /api/apps/list-available/installed` 로 한다.

첫 설치가 끝나면 그 뒤로는 `./reachy.sh robot deploy` 가 rsync 로 밀어 넣는다.

---

## 7. startup-app 비우기 (두 대 모두)

로봇 브라우저 대시보드(`http://192.168.0.4:8000`)에서 **자동 시작 앱을 없음**으로 둔다.

LAN 으로 붙는 SDK 클라이언트는 로봇의 앱 락을 우회한다. 온보드 앱이 켜져 있으면 우리
앱과 모터를 두고 싸운다.

---

## 8. 노트북 준비

무대감독은 노트북에서 직접 실행하는 프로세스라 셸 `export` 가 그대로 먹는다.

```bash
export REACHY_MC_UNIT=<§5 의 사회자 hardware_id>
export REACHY_DOCENT_UNIT=<§5 의 도슨트 hardware_id>
export REACHY_DIRECTOR_PORT=8777
```

추론 3종을 LAN 에 열고 예열한다.

```bash
./reachy.sh serve      # LLM :8080 · STT :8090 · TTS :8099
./reachy.sh warmup     # Qwen3-TTS Metal JIT 등
```

> **예열을 건너뛰지 않는다.** Qwen3-TTS 첫 합성은 Metal 커널 JIT 로 8.5초가 걸린다.
> 감독의 타임아웃 여유분을 15초로 잡아 헛타임아웃은 막아 뒀지만 그건 방어선이지
> 대체재가 아니다. 시연 첫 인상이 걸린 구간이다.

`REACHY_AEC` 는 **켜지 않는다.** 실기는 XMOS 하드웨어 AEC 가 그 자리를 대신한다.

---

## 9. 로봇 설정과 기동

**로봇에서 `export` 하지 않는다.** 로봇의 앱은 `POST /api/apps/start-app/` 로 데몬(systemd)이
낳는 자식 프로세스다. SSH 로 들어가 `export REACHY_ROLE=mc` 를 해도 그 값은 앱에 닿지 않는다.
역할이 안 닿으면 로봇은 **조용히 1대 모드로** 뜬다.

노트북에서 로봇마다 한 번씩 돌린다. 역할·무대감독 주소·추론 3종 주소가 로봇의
`~/.config/reachy-mini-voice-chat/config.json` 에 들어간다.

```bash
.venv/bin/python -m stage          # 무대감독 — 이 터미널이 콘솔이다

REACHY_ROLE=mc     REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh robot up
REACHY_ROLE=docent REACHY_ROBOT_HOST=192.168.0.5 ./reachy.sh robot up
```

`robot up` 하나가 **백엔드 확인 → 추론 3종 → 예열 → config 동기화 → 로봇→맥 도달 확인 → 기상 →
앱 기동** 을 순서대로 한다. 두 대를 한 번에 올리려면 `./reachy.sh start --robot`
(`REACHY_MC_HOST`/`REACHY_DOCENT_HOST`) — `docs/two-robot-setup.md` §7.

`REACHY_ROLE` 없이 돌리면 그 로봇의 역할 설정을 **지운다**(1대 모드로 되돌린다).
지웠다는 줄이 화면에 뜬다.

### 기동 로그에서 확인할 것

| 줄 | 뜻 |
|---|---|
| `역할: mc (설정파일)` | 정상. `(기본값)` 이면 역할이 안 닿았다 |
| `무대감독: ws://192.168.0.10:8777 (설정파일)` | 정상 |
| `주소: LLM http://192.168.0.10:8080 …` | 정상. `[주소 경고] … loopback` 이면 §9 를 다시 |
| `[mc] 붙었다` (감독 콘솔) | 로봇이 감독에 접속했다 |
| `[mc] 거부됨 — … 뒤바뀌었는지` | 두 대가 바뀌었다. 라벨을 보고 바꿔 건다 |

---

## 10. 배포와 관리 — 맥북에서 두 대를 다루는 법

대상은 **환경변수 하나**로 갈린다. 두 대를 각각 부른다.

```bash
REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh robot deploy   # 사회자
REACHY_ROBOT_HOST=192.168.0.5 ./reachy.sh robot deploy   # 도슨트
```

채널은 둘이다. 용도에 따라 다른 길로 간다.

| 하는 일 | 방식 | 포트 |
|---|---|---|
| 소스 배포 | SSH 위의 rsync | 22 |
| 설정 파일 쓰기 | SSH | 22 |
| 로그 실시간 보기 | SSH + `journalctl -f` | 22 |
| 앱 기동·정지, 기상, 상태 | REST API | 8000 |
| 웹 대시보드 | 브라우저 | 8000 |

`robot deploy` 가 하는 일은 이렇다. REST 로 현재 앱을 멈춘다. rsync 로 **두 벌**을 민다 —
재설치용 소스와 지금 도는 설치본이다. 끝으로 바이트코드 캐시를 지운다. 안 지우면 고친
코드가 안 먹는다.

### 관리자 콘솔

```bash
REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh robot logs      # 실시간 로그
REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh robot status    # 데몬·모터·앱 상태
REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh robot fix       # 복구
REACHY_ROBOT_HOST=192.168.0.4 ./reachy.sh robot down      # 정지
```

직접 붙으려면 평범한 SSH 다.

```bash
ssh pollen@192.168.0.4
```

브라우저로는 `http://192.168.0.4:8000` 이 대시보드, `http://192.168.0.4:8000/docs` 가
REST API 문서다.

### 무대감독 콘솔 (노트북)

| 키 | |
|---|---|
| `s` | 시작 |
| `n` | 다음 큐 — 발화 중이든 `a` 로 멈춘 뒤든 먹는다 |
| `p` | 이전 큐 — 오인식으로 넘어가 버렸을 때 |
| `r` | 현재 큐 다시 |
| `a` | 즉시 중단 |
| `q` | 종료 |

콘솔은 비상용이다. 정상 진행은 관람객이 "다음"·"계속" 이라고 말하면 된다.

---

## 11. 설치 확인 체크리스트

- [ ] 두 로봇 다 `curl .../api/daemon/status` 가 JSON
- [ ] `ssh -o BatchMode=yes pollen@<IP> echo ok` 가 두 대 모두 `ok`
- [ ] `hardware_id` 두 개를 적어 뒀고 서로 다르다
- [ ] `GET /api/apps/list-available/installed` 에 `voice_chat` 이 보인다 (두 대)
- [ ] 두 로봇 startup-app 비어 있음
- [ ] 기동 로그에 `역할: … (설정파일)` — `(기본값)` 아님
- [ ] 감독 콘솔에 `[mc] 붙었다` 와 `[docent] 붙었다`
- [ ] `REACHY_AEC` 꺼짐

여기까지 되면 시연 리허설로 넘어간다 — `docs/two-robot-offline-test.md` 의 ⑧ 시연 리허설.

---

## 12. 막혔을 때

| 증상 | 원인과 조치 |
|---|---|
| `robot up` 이 "config 를 쓰지 못했다" | SSH 공개키가 없다. §4 |
| rsync 가 `No such file or directory` | `apps_venv` 가 없다. §6 |
| `POST /api/apps/install` 이 `not installable via the API` | 로컬 앱은 REST 로 안 된다. §6 |
| 앱이 조용히 1대 모드로 뜬다 | 역할이 안 닿았다. 로봇에서 export 하지 않는다. §9 |
| `[주소 경고] … loopback` | 설정파일 주소가 맥을 안 가리킨다. §9 를 다시 |
| 로봇을 못 찾는다 | `.local` 을 쓰지 않는다. 공유기 DHCP 목록에서 IP 를 확인한다 |
| 두 기기가 서로 안 보인다 | 공용 WiFi 의 client isolation. 전용 공유기를 쓴다. §1 |
| `[mc] 거부됨` | 두 대가 뒤바뀌었다. 라벨과 `hardware_id` 를 대조한다 |
| 첫 발화가 8초 넘게 안 나온다 | 예열이 빠졌다. `./reachy.sh warmup` |

로그를 먼저 읽는다. 순서는 하나다 — **로그 확인 → 재현 → 원인 → 고침 → 테스트로 박제.**

---

## 13. 아직 실기에서 확인하지 못한 것

이 문서의 절차는 SDK 소스와 공식 문서, 그리고 시뮬 검증에 근거한다. 로봇 두 대로
끝까지 돌려 본 적은 없다. 특히 아래는 실기에서 처음 실행된다.

- **`hardware_id` 불일치 거부** — 시뮬에서는 값이 언제나 `null` 이라 "없으면 통과" 쪽만 돌았다
- **두 스피커 간 잔향** — 도슨트 마지막 문장의 잔향이 마이크 개방 뒤 0.7초 안에 사회자
  VAD 를 다시 깨우는지
- **사회자 1.27배속 / 도슨트 1.13배속의 청감 대비**
- **CM4(RAM 4GB)에서 앱 + 무대감독 클라이언트 동시 구동 시 메모리**
- **PC 추론 부하** — 단일 창구라 1대분으로 예상하나 실측하지 않았다
