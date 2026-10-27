"""A scripted stand-in for the Anthropic Messages API, for tests that must not spend money or need secrets.

Each scripted step is the list of content blocks the "model" answers with; after the script the fake answers
with a plain end of turn. Every request body is recorded so tests can assert what the model was shown.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def text(value):
    return {"type": "text", "text": value}


def call(tool_id, name, tool_input):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def _stream(blocks, stop_reason):
    out = []

    def event(name, data):
        out.append(f"event: {name}\ndata: {json.dumps(data)}\n\n")

    event("message_start", {"type": "message_start", "message": {
        "id": "msg_fake", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}})
    for index, block in enumerate(blocks):
        if block["type"] == "text":
            event("content_block_start", {"type": "content_block_start", "index": index,
                                          "content_block": {"type": "text", "text": ""}})
            event("content_block_delta", {"type": "content_block_delta", "index": index,
                                          "delta": {"type": "text_delta", "text": block["text"]}})
        else:
            event("content_block_start", {"type": "content_block_start", "index": index, "content_block": {
                "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}})
            event("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {
                "type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
        event("content_block_stop", {"type": "content_block_stop", "index": index})
    event("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                            "usage": {"output_tokens": 5}})
    event("message_stop", {"type": "message_stop"})
    return "".join(out).encode()


class FakeApi:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self._step = 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                fake.requests.append(body)
                if "count_tokens" in self.path:
                    payload = b'{"input_tokens": 10}'
                    self.send_response(200)
                    self.send_header("content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                offers_agent_tools = "Write" in {t.get("name") for t in body.get("tools", [])}
                if offers_agent_tools and fake._step < len(fake.script):
                    blocks, stop = fake.script[fake._step], "tool_use"
                    fake._step += 1
                else:
                    blocks, stop = [text("done")], "end_turn"
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(_stream(blocks, stop))

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
