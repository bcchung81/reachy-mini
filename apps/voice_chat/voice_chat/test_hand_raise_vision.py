"""손들기 인식 실현 가능성 진단 — 런다운 큐 마무리 단계용(4단계, 아직 미구현) 사전 점검.

`docs/superpowers/specs/2026-09-21-launch-and-modes-design.md`가 정해 둔 설계를 그대로 따른다:
"손들기 감지 | 비전 LLM(사회자 카메라 스냅샷 → PC gemma4) | 새 의존성 없음·오프라인."
즉 새 CV 모델을 붙이지 않고, 이미 있는 `camera_in.grab_jpeg()` + `llm.LLMClient`(비전 질의,
`vision.py`가 쓰는 것과 같은 경로)를 그대로 재사용해 "지금 카메라로 손 든 사람을 알아볼 수
있는가"만 실측한다. 기존 모듈은 import만 하고 손대지 않는다.

**mc 로봇(Linux, CM4) 위에서만 실행된다** — `camera_in.py`가 macOS에서는 항상 None을
반환하도록 짜여 있다(§harness skills/testing-apps.md: "Simulation can't test: Camera-based
tracking"). 시뮬에서는 이 스크립트도 그냥 즉시 끝난다.

실행:
    REACHY_LLM_URL=http://<PC-LAN-IP>:8080 \
    /venvs/apps_venv/bin/python3.12 test_hand_raise_vision.py [반복횟수] [간격초]

사람이 실제로 카메라 앞에서 손을 들었다 내렸다 하는 동안 한 줄씩 판정을 찍는다 — 정답은
이 스크립트가 아니라 그 사람이 안다. 실기 전용 진단이라 pytest가 수집해도 아무 일도
하지 않도록(모듈 최상단에서 부작용 없음) `if __name__ == "__main__":` 뒤에만 둔다.
"""

import platform
import sys
import time
from datetime import datetime

import camera_in
import llm

PROMPT = (
    "이 사진 속에 정면을 향해 손(손바닥이나 팔)을 위로 든 사람이 있는지만 판정해. "
    "있으면 정확히 '손듦'이라고만, 없으면 정확히 '없음'이라고만 답해. "
    "다른 설명·문장부호를 절대 덧붙이지 마."
)
SYSTEM_PROMPT = "너는 카메라 이미지 한 장을 보고 손들기 여부만 짧게 답하는 비전 판정기다."


def _classify(raw: str) -> str:
    t = raw.strip()
    if t.startswith("손듦"):
        return "손듦"
    if t.startswith("없음"):
        return "없음"
    return f"(형식 이탈) {t!r}"


def _once() -> None:
    t0 = time.monotonic()
    jpeg = camera_in.grab_jpeg()
    t_cap = time.monotonic()
    if jpeg is None:
        print(f"[{datetime.now():%H:%M:%S}] 캡처 실패 — 프레임을 못 얻었다", flush=True)
        return
    try:
        client = llm.LLMClient(system_prompt=SYSTEM_PROMPT, max_tokens=20, timeout=15.0)
        answer = "".join(client.chat_stream(PROMPT, image_jpeg=jpeg))
    except Exception as e:  # noqa: BLE001 — 진단 루프 한 번의 실패로 전체를 죽이지 않는다
        print(
            f"[{datetime.now():%H:%M:%S}] 추론 실패({type(e).__name__}: {e})"
            f" — 캡처는 {t_cap - t0:.2f}s, 프레임 {len(jpeg)}B",
            flush=True,
        )
        return
    t1 = time.monotonic()
    print(
        f"[{datetime.now():%H:%M:%S}] "
        f"캡처 {t_cap - t0:.2f}s + 추론 {t1 - t_cap:.2f}s = {t1 - t0:.2f}s  |  "
        f"프레임 {len(jpeg)}B  |  판정: {_classify(answer)}",
        flush=True,
    )


def main() -> None:
    if platform.system() != "Linux":
        print("시뮬/맥에서는 카메라를 못 연다 — mc 로봇(Linux)에서 실행해라.", flush=True)
        return
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    interval_s = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    print(
        f"손들기 인식 진단 시작 — {n}회, {interval_s:.1f}초 간격 "
        f"(LLM: {llm.DEFAULT_BASE_URL}, 출처: 이 프로세스의 REACHY_LLM_URL)",
        flush=True,
    )
    try:
        for i in range(n):
            _once()
            if i < n - 1:
                time.sleep(interval_s)
    finally:
        camera_in.close()
        print("끝 — 카메라를 닫았다.", flush=True)


if __name__ == "__main__":
    main()
