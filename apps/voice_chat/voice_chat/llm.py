"""LLM 스트리밍 채팅 — OpenAI 호환. 절 단위 yield + 대화 이력 유지.

이력은 3쌍 유지, 넘치면 2쌍씩 뭉텅이로 잘라 llama.cpp 프리픽스 캐시
파손 빈도를 낮춘다(매 턴 1쌍씩 자르면 매번 깨진다).
"""

import base64
import json
from collections.abc import Iterator

import requests

from clauses import ClauseBuffer


# 실기에서는 PC 를 가리켜야 한다 — REACHY_LLM_URL=http://<PC>:8080
# 사다리: 환경변수 → 설정파일 → 기본값 (근거는 config.py 머리말)
import config

DEFAULT_BASE_URL = config.get("REACHY_LLM_URL", "http://127.0.0.1:8080")

# keep-alive 연결 재사용. localhost 에서는 차이가 없지만 실기 분리 배치에서는
# 턴마다 WiFi 위 TCP 핸드셰이크를 새로 하는 비용이 응답 지연에 그대로 얹힌다.
_session = requests.Session()


class LLMClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = "local",
        system_prompt: str = "",
        history_pairs: int = 3,
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.history: list[dict] = []
        self.history_pairs = history_pairs
        self.timeout = timeout

    def chat_stream(
        self, user_text: str, image_jpeg: bytes | None = None
    ) -> Iterator[str]:
        """사용자 발화 → 절 단위 스트림. 정상 종료 시 이력에 한 쌍 추가.

        `image_jpeg` 를 주면 **이번 요청에만** 이미지를 싣는다(카메라 질문).

        두 가지를 지킨다:

        1. **이미지가 없으면 content 는 문자열 그대로 둔다.** 항상 리스트로 만들면
           이미지 없는 턴의 프롬프트 문자열이 달라져 **기존 프리픽스 캐시가 통째로
           무효화된다**(실측: 미예열이면 2.5k 토큰 프롬프트가 0.089s → 2.512s).
        2. **이력에는 텍스트만 남긴다.** base64 를 이력에 넣으면 매 턴 앞부분이
           바뀌어 캐시가 계속 깨지고 — 이력을 2쌍씩 뭉텅이로 자르는 이유가
           무의미해진다 — 무엇보다 **3턴 전 장면을 지금 질문의 근거로 삼게 된다.**
        """
        if image_jpeg is None:
            content: object = user_text
        else:
            b64 = base64.b64encode(image_jpeg).decode("ascii")
            content = [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]
        messages = (
            [{"role": "system", "content": self.system_prompt}]
            + self.history
            + [{"role": "user", "content": content}]
        )
        r = _session.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "temperature": 0.7,
                "max_tokens": 200,
            },
            stream=True,
            timeout=self.timeout,
        )
        r.raise_for_status()

        cb = ClauseBuffer()
        parts: list[str] = []
        # 바이트로 줄을 나눈 뒤 줄 단위로 디코드한다. decode_unicode=True 는 청크
        # 경계에서 한글 멀티바이트를 쪼개 JSONDecodeError 를 낸다(M0 실측 확인).
        for raw in r.iter_lines():
            if not raw or not raw.startswith(b"data: "):
                continue
            data = raw[len(b"data: ") :].decode("utf-8")
            if data == "[DONE]":
                break
            delta = json.loads(data)["choices"][0].get("delta", {}).get("content") or ""
            if not delta:
                continue
            parts.append(delta)
            yield from cb.feed(delta)
        tail = cb.flush()
        if tail:
            yield tail

        self.history += [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "".join(parts)},
        ]
        if len(self.history) > self.history_pairs * 2:
            del self.history[:4]  # 2쌍씩 절단
