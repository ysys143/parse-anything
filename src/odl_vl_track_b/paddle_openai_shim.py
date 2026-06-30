"""OpenAI-compatible shim in front of the Paddle job API, so docling can use Paddle as a B-1 VLM.

docling's VlmPipeline (B-1) calls an OpenAI-compatible POST /v1/chat/completions with the page as
a base64 image_url. The Paddle official API speaks a different protocol (job submit -> poll ->
jsonl), so it can't be an ApiVlmOptions backend directly. This shim bridges the two: it accepts the
chat/completions request, extracts the image, runs the injected Paddle transcriber, and returns the
Markdown in OpenAI choices[0].message.content shape. Runs in a daemon thread on an ephemeral port.

This makes "B-1 paddle" possible (docling structures Paddle's transcription via VlmPipeline) to
test whether docling's table shaping helps Paddle the way it helps Gemini (0.571->0.789).
"""
from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


def _make_handler(transcribe: Callable[[bytes], str]):
    class _ShimHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base signature
            return

        def do_GET(self) -> None:  # health probes
            self.send_response(200)
            self.end_headers()

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                body = {}
            png = _extract_image(body)
            try:
                content = transcribe(png) if png else ""
            except Exception as exc:  # surface as empty content, never 500 the pipeline
                content = ""
                self.log_error("shim transcribe failed: %s", type(exc).__name__)
            resp = {
                "id": "paddle-shim",
                "object": "chat.completion",
                "created": 0,  # docling's OpenAiApiResponse requires id/choices/created
                "model": "paddle",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
            payload = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return _ShimHandler


def _extract_image(body: dict[str, Any]) -> bytes | None:
    """Pull the first base64 image_url out of an OpenAI chat/completions request body."""
    for msg in body.get("messages", []):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if "," in url:  # data:image/png;base64,XXXX
                    try:
                        return base64.b64decode(url.split(",", 1)[1])
                    except (ValueError, TypeError):
                        return None
    return None


def serve_shim_background(transcribe: Callable[[bytes], str], *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Start the shim on an ephemeral port in a daemon thread. Read server.server_address[1] for it."""
    server = ThreadingHTTPServer((host, port), _make_handler(transcribe))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
