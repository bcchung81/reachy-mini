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
