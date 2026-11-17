"""시연 직전 예열 — 첫 질문이 느려지지 않도록 모든 경로를 한 번씩 태운다.

핵심은 LLM 프리픽스 캐시다. llama.cpp 는 **실제 토큰 접두사**로 캐시를 잡으므로,
앱이 보내는 것과 같은 시스템 블록으로 예열해야 한다. 시스템 프롬프트 없이
"안녕"만 보내면 접두사가 달라 앱의 첫 요청이 프리필 비용을 그대로 문다.

실행: ./reachy.sh warmup   (demo 가 자동으로 태우지만 단독 실행도 된다)

**외부 API 사전 점검**(2026-11-14, 계획 `docs/superpowers/plans/2026-11-14-show-readiness.md` A-1): 외부 전용
(`REACHY_LOCAL_MODELS=off`)에서는 LLM·STT·TTS 단계의 실패를 "건너뜀" 이 아니라 **점검 실패**로 찍는다 — 실패 종류
(게이트웨이·TTS 프록시가 502 머리 `X-Reachy-Upstream` 에 싣는다)로 할 일(키·잔액/한도·인터넷)을, 그리고 그래서 공연에서
**무엇이 안 되는지**를 줄마다 말한다. 멈추지는 않는다(U1 ① — 대본 공연은 구운 캐시로 돈다). `TTS_ENGINE=elevenlabs` 면
남은 크레딧도 찍는다(U2 문턱 10,000 호박 · 2,000 빨강). 점검 결과는 `REACHY_PREFLIGHT_OUT` 파일(`등급\t글`)에도 써서
`reachy.sh` 가 감독 콘솔 위로 밀리기 전에 빨간 묶음으로 다시 보이게 한다.
로컬 구성(스위치 없음)의 문구는 예전 그대로다 — 로컬 예열 실패는 "첫 응답이 느려질 뿐" 이다.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import wave
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps/voice_chat/voice_chat"
sys.path.insert(0, str(APP))
sys.path.insert(1, str(ROOT))      # tts_elevenlabs·tts_cache_proxy(크레딧 조회·실패 종류) — PC 에서만 돈다


def _prompt() -> Path:
    """앱이 실제로 쓸 프롬프트 파일. **session 과 같은 것을 골라야 한다.**

    여기서 prompt.md 로 고정해 두면 해설 모드(REACHY_PROMPT)일 때 예열이
    엉뚱한 접두사를 데워 **캐시가 헛돈다.** 실측(2026-09-09): 2.5k 토큰 프롬프트가
    예열되면 0.089s, 안 되면 2.512s 다. 조용히 느려지는 종류라 반드시 맞춘다.
    """
    import session

    return session.prompt_path()
# **앱과 같은 환경변수를 읽는다**(CLAUDE.md: "주소는 전부 환경변수다").
# 하드코딩하면 실기 분리 배치(앱은 로봇, 추론은 PC)에서 예열이 엉뚱한 호스트를
# 조용히 데우고 — _step 이 실패를 '건너뜀'으로 삼킨다 — 첫 발화가 콜드스타트를
# 그대로 문다(리뷰 확인). 예열의 존재 이유가 사라지는 실패다.
LLM_URL = os.environ.get("REACHY_LLM_URL", "http://127.0.0.1:8080").rstrip("/") + "/v1/chat/completions"
STT_URL = os.environ.get("REACHY_STT_URL", "http://127.0.0.1:8090/v1/audio/transcriptions")
# 언어도 앱과 같게 — 다르면 다른 디코드 경로를 데운다.
STT_LANG = os.environ.get("REACHY_STT_LANG", "auto")
# TTS_BACKEND=say 폴백 경로에서만 쓰는 macOS 음성 이름.
VOICE = os.environ.get("REACHY_VOICE", "Yuna")


def _step(label: str, fn, service: str | None = None, preflight: "Preflight | None" = None) -> bool:
    """한 단계를 태운다. `preflight` 가 있고(외부 전용) `service` 가 외부 API 를 타는 단계면 실패를 **점검 실패**로 찍는다."""
    t0 = time.time()
    try:
        detail = fn()
    except Exception as exc:
        if preflight is not None and service is not None:
            preflight.failed(label, service, upstream_of(exc))
        else:
            print(f"   {label} 건너뜀 ({type(exc).__name__})")
        return False
    print(f"   {label} {time.time() - t0:5.2f}s{'  ' + detail if detail else ''}")
    return True


# ── 외부 API 사전 점검(외부 전용) ──────────────────────────────────
# U2(2026-11-14 사용자 결정): 일반 수준 답 하나가 약 100 크레딧(210자 × 0.5). 2,000 이면 답 20개 남짓 — 하루 공연이 위험한 선.
CREDITS_WARN = 10_000
CREDITS_BAD = 2_000
CREDITS_PER_ANSWER = 100

# 서비스별 — 이름, 무엇이 안 되나, 로그. "안 되는 것" 을 줄마다 붙이는 이유: 운영자가 "공연을 해도 되나" 를 그 자리에서
# 정해야 한다. 대본(고정 대사)은 구운 캐시에서 나가므로 셋 다 실패해도 공연은 돈다(§15.13).
_SERVICES = {
    "llm": ("OpenAI", "관람객 질문 답(사과문으로 대신한다)", "게이트웨이(:8080)", ".demo-logs/openai-gateway.log",
            "OPENAI_API_KEY"),
    "stt": ("OpenAI", "음성인식(관람객 질문과 '다음' 같은 음성 명령 — 조정실·콘솔로 진행한다)", "게이트웨이(:8090)",
            ".demo-logs/openai-gateway.log", "OPENAI_API_KEY"),
    "tts": ("ElevenLabs", "관람객 답 목소리(즉석 답이 안내 한 번 + 무음이 된다)", "TTS 프록시(:8099)",
            ".demo-logs/tts-proxy.log", "ELEVENLABS_API_KEY"),
}


def upstream_of(exc: BaseException) -> str:
    """예열이 받은 예외 → 실패 종류. 게이트웨이·프록시가 502 에 실은 `X-Reachy-Upstream` 을 그대로 쓴다(`401`·`429`·`5xx`·
    `4xx`·`connect`·`timeout`·`other`). 그 머리 없는 HTTP 오류는 `http`, 이 PC 의 서버에 못 닿았으면 `server`."""
    headers = None
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        headers = exc.response.headers
    elif isinstance(exc, urllib.error.HTTPError):
        headers = exc.headers
    if headers is not None:
        return headers.get("X-Reachy-Upstream") or "http"
    if isinstance(exc, (requests.ConnectionError, requests.Timeout, urllib.error.URLError, OSError)):
        return "server"
    return "other"


def explain(service: str, kind: str) -> str:
    """실패 종류 → 운영자가 할 일 한 줄. **메시지 원문은 쓰지 않는다** — 게이트웨이도 싣지 않는다(키 조각, lessons 2026-11-12)."""
    vendor, _, server, log, key_name = _SERVICES[service]
    if kind == "401":
        why = f"{vendor} 키가 틀렸거나 만료(401): .env 의 {key_name} 를 확인한다"
        if service == "tts":
            # ElevenLabs 는 크레딧이 바닥나도 401 을 줄 수 있다(실측 안 함) — 키만 의심하게 두지 않는다.
            why += "(크레딧이 바닥나도 401 일 수 있다 — 아래 크레딧 줄을 본다)"
        return why
    if kind == "429":
        # 429 본문은 "분당 한도" 와 "잔액 없음" 으로 갈리는데 종류만 받으니 둘을 못 가른다 — 둘 다 적는다(계획 A-1 위험).
        return f"{vendor} 잔액 부족 또는 한도 초과(429): 결제·사용량을 확인한다(분당 한도면 잠시 뒤 풀린다)"
    if kind == "connect":
        return f"인터넷 연결: {vendor} 에 못 닿았다(connect). 전시장 망의 인터넷을 확인한다"
    if kind == "timeout":
        # connect 와 **가른다**(2026-11-17): 맥이 덮개 닫힘으로 잠들었다 깬 뒤 게이트웨이가 죽은 연결을 다시 써 응답이 안 왔을 때 예전 문구
        # "인터넷 연결: 못 닿았다 … 전시장 망의 인터넷을 확인한다" 가 운영자를 엉뚱한 곳에 보냈다 — 인터넷은 멀쩡했고 같은 때 STT 는
        # 1.45초에 성공했다. timeout 은 "보냈는데 응답이 상한 안에 안 왔다" 다(게이트웨이는 연결 단계의 시간 초과를 connect 로 싣는다).
        # 인터넷 탓이라고 단정하지 않고, 일시적일 수 있음 + 그 서버 로그를 가리킨다. TTS 프록시의 timeout 은 연결 단계 시간 초과도
        # 담는다(`tts_cache_proxy.upstream_kind` — "timed out" 글로 가른다) — 그래서 "계속되면 인터넷도" 를 남긴다.
        return (f"{vendor} 응답이 시간 상한 안에 오지 않았다(timeout) — 일시적일 수 있다(회선·{vendor} 쪽 지연). "
                f"{log} 를 보고 다시 점검한다. 계속되면 인터넷과 {vendor} 상태를 본다")
    if kind == "5xx":
        return f"{vendor} 쪽 일시 오류(5xx): 잠시 뒤 다시 띄운다. 계속되면 {vendor} 상태 페이지를 본다"
    if kind == "server":
        return f"이 PC 의 {server}가 응답하지 않는다: {log} 를 본다"
    return f"원인을 가르지 못했다({kind}): {log} 를 본다"


def el_key() -> str | None:
    import tts_elevenlabs as el

    return el.load_api_key()


def credits_left(key: str) -> tuple[int, int]:
    """(쓴 크레딧, 한도) — 구독 조회(GET, 합성 아님 — 크레딧을 쓰지 않는다)."""
    import tts_elevenlabs as el

    return el.credits_left(key)


_COLORS = {"bad": "\033[31m", "warn": "\033[33m"}


class Preflight:
    """외부 API 점검 결과를 모은다 — 화면에 줄마다 찍고, 끝에 묶어서 `REACHY_PREFLIGHT_OUT` 파일로 남긴다."""

    def __init__(self, color: bool) -> None:
        self.color = color
        self.items: list[tuple[str, str]] = []       # (등급 bad|warn, 글)
        self.broken: list[str] = []

    def paint(self, level: str, text: str) -> str:
        return f"{_COLORS[level]}{text}\033[0m" if self.color else text

    def failed(self, label: str, service: str, kind: str) -> None:
        why = explain(service, kind)
        broken = _SERVICES[service][1]
        print(self.paint("bad", f"   {label} 점검 실패 — {why}"))
        print(f"        → 안 되는 것: {broken}")
        name = {"llm": "LLM", "stt": "STT", "tts": "TTS"}[service]
        self.items.append(("bad", f"{name}({_SERVICES[service][0]}) 점검 실패 — {why} → 안 되는 것: {broken}"))
        self.broken.append(broken.split("(")[0])

    def note(self, level: str, line: str, item: str) -> None:
        print(self.paint(level, line) if level in _COLORS else line)
        if level in _COLORS:
            self.items.append((level, item))


def check_credits(pf: Preflight) -> None:
    """남은 ElevenLabs 크레딧을 한 줄로. 조회 실패는 예열 실패가 아니다(합성은 따로 봤다) — 경고 한 줄."""
    key = el_key()
    if not key:
        pf.note("warn", "   TTS  크레딧을 볼 수 없다 — ElevenLabs 키가 없다", "ElevenLabs 키가 없어 크레딧을 못 봤다")
        return
    try:
        used, limit = credits_left(key)
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 한 줄 경고로 끝낸다(공연을 막지 않는다)
        from tts_cache_proxy import upstream_kind

        kind = upstream_kind(exc)
        pf.note("warn", f"   TTS  크레딧을 확인하지 못했다({kind}) — ElevenLabs 키·인터넷을 확인한다",
                f"ElevenLabs 크레딧을 확인하지 못했다({kind})")
        return
    left = max(0, limit - used)
    head = f"   TTS  크레딧 남음 {left:,} / {limit:,}"
    if left < CREDITS_BAD:
        msg = (f"{CREDITS_BAD:,} 아래: 관람객 답 약 {left // CREDITS_PER_ANSWER}개분. 충전하지 않으면 관람객 답 목소리가 "
               "곧 끊긴다(대본은 구운 캐시로 계속)")
        pf.note("bad", f"{head} — {msg}", f"ElevenLabs 크레딧 {left:,} 남음 — {msg}")
    elif left < CREDITS_WARN:
        msg = f"{CREDITS_WARN:,} 아래: 공연 전에 충전·플랜을 확인한다(관람객 답 하나 약 {CREDITS_PER_ANSWER})"
        pf.note("warn", f"{head} — {msg}", f"ElevenLabs 크레딧 {left:,} 남음 — {msg}")
    else:
        pf.note("ok", head, "")


# llama-server 는 슬롯 여러 개로 뜬다(현재 구성 parallel=2). 한 번만 예열하면
# 슬롯 하나만 캐시가 차서, 다른 슬롯으로 간 요청이 0.09s → 0.40s 로 튄다(실측).
# 슬롯 수보다 넉넉히 태워 전부 채운다. 한 번에 0.1s 남짓이라 비용이 싸다.
LLM_WARM_ROUNDS = 3


def _llm_ttft(system: str, user: str) -> float | None:
    t0 = time.time()
    r = requests.post(
        LLM_URL,
        json={
            "model": "local",
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 8,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        stream=True,
        timeout=120,
    )
    r.raise_for_status()
    ttft = None
    for raw in r.iter_lines():
        if raw and raw.startswith(b"data: ") and raw[6:] != b"[DONE]":
            if ttft is None:
                ttft = time.time() - t0
    r.close()
    return ttft


def warm_llm() -> str:
    """앱과 동일한 시스템 블록으로 모든 슬롯의 프리픽스 캐시를 채운다."""
    system = _prompt().read_text()
    times = [_llm_ttft(system, f"안녕{i}") for i in range(LLM_WARM_ROUNDS)]
    done = [t for t in times if t is not None]
    if not done:
        return ""
    return f"(TTFT {done[0]:.2f}s → {done[-1]:.2f}s, 슬롯 {LLM_WARM_ROUNDS}회)"


def _tts_mod():
    """앱의 tts 모듈. 요청 본문을 여기서 다시 짜면 tts.py 와 갈라진다."""
    sys.path.insert(0, str(ROOT / "apps/voice_chat/voice_chat"))
    import tts as tts_mod

    return tts_mod


def warm_tts(external: bool = False) -> str:
    """첫 호출은 리소스를 올리느라 느리다. 소리 없이 한 번 태운다.

    Qwen3-TTS 는 **첫 실행에 Metal 커널 JIT 로 8.5초**가 걸린다(실측).
    예열을 빠뜨리면 시연 첫 발화가 그만큼 늦는다. **Metal JIT 캐시는 모델·화자별**
    이라 조건이 어긋나면 예열이 헛돈다(0.6B 로 예열한 캐시가 1.7B 에는 안 먹혔다,
    실측 10.0초) — 그래서 앱이 쓰는 함수를 그대로 부른다.

    `external`(외부 전용): `_qwen_synth` 는 실패를 None 으로 삼켜 실패 종류(502 머리)를 잃는다. 같은 본문 함수
    (`_qwen_body`)·같은 여는 함수(`_qwen_open`)로 직접 열어 예외를 그대로 올린다 — 요청은 앱과 같다.
    """
    if os.environ.get("TTS_BACKEND", "qwen") != "say":
        tts_mod = _tts_mod()
        if external:
            with tts_mod._qwen_open(tts_mod._qwen_body("준비되었습니다.", None, stream=False)) as r:
                r.read()
        elif tts_mod._qwen_synth("준비되었습니다.") is None:
            raise RuntimeError(f"TTS 서버 응답 없음: {tts_mod.QWEN_URL}")
        # 엔진 이름은 reachy.sh 가 물려주는 TTS_ENGINE 으로 — "(Qwen3-TTS)" 로 박아 두면 ElevenLabs 로 돌 때도 그렇게 찍혀
        # 어느 목소리가 데워졌는지 화면이 거짓말을 한다(2026-11-13 외부 전용 실측에서 봤다).
        return "(ElevenLabs)" if os.environ.get("TTS_ENGINE") == "elevenlabs" else "(Qwen3-TTS)"

    # TTS_BACKEND=say 로 명시했을 때만 온다 — 그 경로는 macOS 전용이다.
    cmd = shutil.which("say")
    if cmd is None:
        raise RuntimeError("TTS_BACKEND=say 인데 `say` 가 없다(macOS 전용)")
    subprocess.run([cmd, "-v", VOICE, "-o", "/dev/null", "준비"], check=True)
    return "(say)"


def _probe_wav() -> bytes:
    """STT 예열용 16 kHz mono WAV.

    **플랫폼 전용 합성기에 의존하지 않는다.** 예전에는 macOS `say -o` 로 만들어
    리눅스 PC 에서는 예열이 통째로 건너뛰어졌다. 지금은 우리 TTS 서버(앱이 쓰는
    바로 그 경로)로 만들고, 그마저 없으면 톤으로 대신한다 — 무음은 쓰지 않는다
    (Whisper 가 무음에서 환각을 뱉는다, `voice_loop._WHISPER_FILLER` 참조).
    """
    try:
        tts_mod = _tts_mod()
        pcm = tts_mod._qwen_synth("안녕하세요")
        if pcm:
            return pcm  # 서버는 wav 를 준다
    except Exception:  # noqa: BLE001
        pass
    # 폴백: 440 Hz 톤 1초. 전사 내용은 의미 없고 **디코드 경로를 태우는 것**이 목적이다.
    import numpy as np

    t = np.arange(16000) / 16000
    pcm16 = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as o:
        o.setnchannels(1)
        o.setsampwidth(2)
        o.setframerate(16000)
        o.writeframes(pcm16.tobytes())
    return buf.getvalue()


def warm_stt() -> str:
    """무음이 아니라 실제 음성으로 전사 경로를 태운다."""
    r = requests.post(
        STT_URL,
        files={"file": ("w.wav", _probe_wav(), "audio/wav")},
        data={"language": STT_LANG},
        timeout=120,
    )
    r.raise_for_status()
    return f"({r.json().get('text', '')!r})"


def warm_moves() -> str:
    from reachy_mini.motion.recorded_move import RecordedMoves

    moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
    return f"({len(moves.list_moves())}개)"


def main(env: dict | None = None) -> int:
    """0 = 다 됐다, 1 = 하나라도 실패(로컬은 '건너뜀', 외부 전용은 '점검 실패'). 공연을 막지 않는다 — 부르는 쪽이 정한다."""
    env = os.environ if env is None else env
    external = (env.get("REACHY_LOCAL_MODELS") or "on").strip().lower() == "off"
    color = sys.stdout.isatty() and not env.get("NO_COLOR")
    pf = Preflight(color) if external else None
    out = env.get("REACHY_PREFLIGHT_OUT")
    if out:
        # 실행마다 새로 쓴다 — 지난 실행의 빨간 줄을 reachy.sh 가 이번 것처럼 다시 보이면 안 된다.
        Path(out).write_text("", encoding="utf-8")
    results = [
        _step("LLM  프리픽스 캐시", warm_llm, "llm", pf),
        _step("TTS  음성 리소스  ", lambda: warm_tts(external), "tts", pf),
    ]
    credit_pf = pf or Preflight(color)
    if (env.get("TTS_ENGINE") or "").strip().lower() == "elevenlabs":
        # 로컬 모델이 켜진 섞인 구성(TTS 만 ElevenLabs)에서도 크레딧은 본다 — 관람객 답이 ElevenLabs 로 나간다.
        check_credits(credit_pf)
    results += [
        _step("STT  전사 경로    ", warm_stt, "stt", pf),
        _step("모션 카탈로그     ", warm_moves),
    ]
    if pf is not None and pf.broken:
        print(pf.paint("bad", f"   외부 API 점검 실패 {len(pf.broken)}건 — 안 되는 것: {' · '.join(pf.broken)}."
                               " 대본 공연은 구운 캐시로 계속된다"))
    if out and credit_pf.items:
        Path(out).write_text("".join(f"{lvl}\t{text}\n" for lvl, text in credit_pf.items), encoding="utf-8")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
