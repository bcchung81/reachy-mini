"""LLM 스트리밍 채팅 — OpenAI 호환. 절 단위 yield + 대화 이력 유지.

이력은 3쌍 유지, 넘치면 2쌍씩 뭉텅이로 잘라 llama.cpp 프리픽스 캐시
파손 빈도를 낮춘다(매 턴 1쌍씩 자르면 매번 깨진다).
"""

import json
from collections.abc import Iterator

import requests

from clauses import ClauseBuffer


class LLMClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
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

    def chat_stream(self, user_text: str) -> Iterator[str]:
        """사용자 발화 → 절 단위 스트림. 정상 종료 시 이력에 한 쌍 추가."""
        messages = (
            [{"role": "system", "content": self.system_prompt}]
            + self.history
            + [{"role": "user", "content": user_text}]
        )
        r = requests.post(
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
