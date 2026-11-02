"""Exercise the real Anthropic SDK against a local mock server that speaks the streaming protocol.

No API key or network needed: this checks that the request parameters we send are
accepted by the SDK, that streamed tool calls are parsed, and that assistant content
(including thinking blocks) is sent back unchanged on the next request.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

anthropic = pytest.importorskip("anthropic")

from agentflow import load_agents  # noqa: E402
from agentflow.agent import AgentRunner  # noqa: E402
from agentflow.workspace import Workspace  # noqa: E402

ROOT = Path(__file__).parent.parent


def sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def tool_turn(msg_id, tool_id, name, args):
    return sse(
        [
            {"type": "message_start", "message": {"id": msg_id, "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                                                  "content": [], "stop_reason": None, "stop_sequence": None,
                                                  "usage": {"input_tokens": 10, "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": f"sig-{msg_id}"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": tool_id, "name": name, "input": {}}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": json.dumps(args)[:15]}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": json.dumps(args)[15:]}},
            {"type": "content_block_stop", "index": 1},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 30}},
            {"type": "message_stop"},
        ]
    )


@pytest.fixture
def mock_api():
    responses = [
        tool_turn("msg_1", "toolu_1", "write_file", {"path": "design/pages/home.html", "content": "<h1>Hello \"world\"</h1>"}),
        tool_turn("msg_2", "toolu_2", "complete_task",
                  {"summary": "Designed home", "files": ["design/pages/home.html"], "notes_for_next_agent": "n/a"}),
    ]
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            payload = responses.pop(0)
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", requests
    server.shutdown()


def test_agent_round_trip_through_real_sdk(tmp_path, mock_api):
    base_url, requests = mock_api
    client = anthropic.Anthropic(api_key="test-key", base_url=base_url, max_retries=0)
    spec = load_agents(ROOT / "agents")["ux_designer"]
    runner = AgentRunner(spec, client, Workspace(tmp_path))

    result = runner.start([{"type": "text", "text": "Design a home page"}])

    assert result.summary == "Designed home"
    assert (tmp_path / "design/pages/home.html").read_text() == '<h1>Hello "world"</h1>'

    first, second = requests
    assert first["path"].startswith("/v1/messages")
    assert "server-side-fallback-2026-07-01" in first["headers"].get("anthropic-beta", "")
    body = first["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": "high"}
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["stream"] is True
    assert all(t.get("eager_input_streaming") for t in body["tools"])

    # Second request: assistant turn echoed back unchanged (thinking signature kept),
    # followed by the tool result.
    assistant, tool_results = second["body"]["messages"][1:]
    assert assistant["role"] == "assistant"
    assert assistant["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-msg_1"}
    assert assistant["content"][1]["type"] == "tool_use" and assistant["content"][1]["id"] == "toolu_1"
    assert tool_results["content"][0]["tool_use_id"] == "toolu_1"
    assert runner.usage.requests == 2
