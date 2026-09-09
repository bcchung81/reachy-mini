import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
from llm import LLMClient

# 한글이 여러 청크에 걸쳐 오는 상황을 재현한다 — 바이트 경계 디코딩 회귀 방지
CHUNKS = ["오늘", " 기분", " 최고예요", ".", " 당신은요?"]


class Stub(BaseHTTPRequestHandler):
    last_body = None

    def do_POST(self):
        Stub.last_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for c in CHUNKS:
            ev = {"choices": [{"delta": {"content": c}}]}
            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *a):
        pass


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def test_절_단위로_yield하고_이력을_남긴다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    out = list(c.chat_stream("안녕"))
    assert out == ["오늘 기분 최고예요.", "당신은요?"]
    assert c.history == [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "오늘 기분 최고예요. 당신은요?"},
    ]


def test_이력이_3쌍을_넘으면_2쌍씩_잘린다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템", history_pairs=3)
    for i in range(4):
        list(c.chat_stream(f"질문{i}"))
    assert len(c.history) == 4  # 4쌍 → 앞 2쌍 삭제 → 2쌍
    assert c.history[0]["content"] == "질문2"


def test_요청에_시스템과_이력이_순서대로_실린다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    list(c.chat_stream("첫질문"))
    list(c.chat_stream("둘째질문"))
    roles = [m["role"] for m in Stub.last_body["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


# ── 카메라 이미지 (2026-09-09) ───────────────────────────────────
FAKE_JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


def test_이미지가_있으면_content가_리스트가_된다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    list(c.chat_stream("이게 뭐야", image_jpeg=FAKE_JPEG))
    msg = Stub.last_body["messages"][-1]
    assert isinstance(msg["content"], list)
    assert [p["type"] for p in msg["content"]] == ["text", "image_url"]
    assert msg["content"][0]["text"] == "이게 뭐야"
    assert msg["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_이미지는_이력에_남지_않는다():
    """이력에 base64 를 남기면 **프리픽스 캐시가 매 턴 깨지고**, 3턴 전 장면을
    지금 질문의 근거로 삼게 된다. 이력을 2쌍씩 뭉텅이로 자르는 이유가 무의미해진다."""
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    list(c.chat_stream("이게 뭐야", image_jpeg=FAKE_JPEG))
    assert c.history[0] == {"role": "user", "content": "이게 뭐야"}
    assert "base64" not in json.dumps(c.history, ensure_ascii=False)


def test_이미지가_없으면_content는_문자열_그대로():
    """항상 리스트로 만들면 이미지 없는 턴의 프롬프트 문자열이 달라져
    **기존 프리픽스 캐시가 통째로 무효화된다**(미예열 비용 2.5초)."""
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    list(c.chat_stream("안녕"))
    assert Stub.last_body["messages"][-1]["content"] == "안녕"


def test_이미지_턴_다음_요청도_전부_문자열이다():
    c = LLMClient(base_url=_serve(), system_prompt="시스템")
    list(c.chat_stream("이게 뭐야", image_jpeg=FAKE_JPEG))
    list(c.chat_stream("그럼 저건?"))
    assert all(isinstance(m["content"], str) for m in Stub.last_body["messages"])
