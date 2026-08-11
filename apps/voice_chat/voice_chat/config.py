"""추론 서버 주소의 설정 사다리 — **환경변수 → 설정파일 → 기본값.**

환경변수만으로는 실기에서 부족하다(`docs/real-robot-deployment.md` §10).
Wireless 에서 앱은 systemd 데몬의 자식 프로세스라 **운영자 셸의 export 가
닿지 않는다** — 데몬 유닛 드롭인을 고치는 방법은 SDK 업데이트가 덮어쓴다.
공개 레퍼런스도 같은 자리에서 소스를 패치해야 했다.

그래서 파일 한 장을 사다리에 끼운다. 위치는 platformdirs(SDK 가 이미 의존)의
사용자 설정 디렉토리 — 앱 재설치(`pip install`)에도 살아남는 곳이다:

    ~/.config/reachy-mini-voice-chat/config.json      (Linux/실기)
    ~/Library/Application Support/reachy-mini-voice-chat/config.json  (macOS)

    {"REACHY_LLM_URL": "http://192.168.0.10:8080",
     "REACHY_STT_URL": "http://192.168.0.10:8090/v1/audio/transcriptions",
     "TTS_QWEN_URL":   "http://192.168.0.10:8099/v1/audio/speech"}

키 이름은 환경변수와 같다 — 정신 모델이 하나여야 한다. 환경변수가 있으면
언제나 이긴다(시뮬·테스트가 그 경로를 쓴다).
"""

import json
import os
import sys
from pathlib import Path

_LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


def path() -> Path:
    """설정파일 경로. platformdirs 가 없으면(비정상) XDG 관례로 대신한다."""
    try:
        from platformdirs import user_config_path

        return user_config_path("reachy-mini-voice-chat") / "config.json"
    except Exception:  # noqa: BLE001
        return Path.home() / ".config" / "reachy-mini-voice-chat" / "config.json"


_cache: dict | None = None


def _file() -> dict:
    """설정파일 내용(1회 로드). 없으면 빈 dict, 깨졌으면 **경고 후** 빈 dict.

    깨진 파일을 조용히 무시하면 안 된다 — 운영자는 주소를 적었다고 믿는데
    앱은 loopback 으로 붙는, §10 이 막으려는 바로 그 상황이 된다.
    """
    global _cache
    if _cache is None:
        p = path()
        _cache = {}
        try:
            if p.exists():
                loaded = json.loads(p.read_text())
                if not isinstance(loaded, dict):
                    raise ValueError("최상위가 JSON 객체가 아니다")
                _cache = loaded
        except Exception as e:  # noqa: BLE001
            print(
                f"  [설정 경고] {p} 를 읽지 못했다({type(e).__name__}: {e}) — "
                "환경변수·기본값만 쓴다",
                flush=True,
            )
    return _cache


def get(name: str, default: str) -> str:
    """사다리 순서대로 값을 준다: 환경변수 → 설정파일 → 기본값."""
    v = os.environ.get(name)
    if v:
        return v
    v = _file().get(name)
    if isinstance(v, str) and v:
        return v
    return default


def source(name: str) -> str:
    """이 키가 어느 단에서 왔는지 — 기동 로그에 출처를 밝히는 용도."""
    if os.environ.get(name):
        return "환경변수"
    v = _file().get(name)
    if isinstance(v, str) and v:
        return "설정파일"
    return "기본값"


def announce() -> None:
    """세 주소와 출처를 기동 시 밝힌다. **실기에서 loopback 이면 크게 경고한다.**

    이 함수가 §10 의 "소리 내서 실패한다" 부분이다: 주소가 잘못돼도 앱은
    STT 빈 문자열·LLM 폴백 한 줄로 조용히 도는데, 그 원인을 로그 첫 줄에서
    볼 수 있어야 시연장에서 잡는다. 실기 판별은 플랫폼으로 한다 — 배포 대상은
    Wireless(CM4/Linux)로 확정됐고 개발 맥은 darwin 이라 갈린다.
    """
    import llm as llm_mod
    import stt as stt_mod
    import tts as tts_mod

    rows = [
        ("LLM", "REACHY_LLM_URL", llm_mod.DEFAULT_BASE_URL),
        ("STT", "REACHY_STT_URL", stt_mod.DEFAULT_URL),
        ("TTS", "TTS_QWEN_URL", tts_mod.QWEN_URL),
    ]
    print(
        "주소: " + " · ".join(f"{label} {url} ({source(key)})" for label, key, url in rows),
        flush=True,
    )
    if sys.platform != "linux":
        return  # 시뮬(맥)에서는 loopback 이 정답이다
    bad = [label for label, _, url in rows if any(h in url for h in _LOOPBACK)]
    if bad:
        print(
            f"  [주소 경고] 실기(Linux)인데 {'·'.join(bad)} 주소가 loopback 이다 — "
            "추론 3종은 PC 에 있다. 데몬(systemd)의 자식에게는 셸 export 가 닿지 "
            f"않으므로 {path()} 에 주소를 적어라 (docs/real-robot-deployment.md §10)",
            flush=True,
        )
