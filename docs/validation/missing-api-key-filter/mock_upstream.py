#!/usr/bin/env python3
import hashlib
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

UPSTREAM_KEY = os.environ.get("MOCK_UPSTREAM_KEY", "mock-upstream-key")
LOG_PATH = os.environ.get("MOCK_LOG", "/logs/mock-upstream.jsonl")


def _body(model: str) -> dict:
    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "mock upstream ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def _record(self, status: int, model: str, started: float) -> None:
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else auth
        record = {
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": self.command,
            "path": urlsplit(self.path).path,
            "status": status,
            "model": model,
            "latency_ms": round((time.time() - started) * 1000, 2),
            "auth_present": bool(token),
            "auth_sha256": hashlib.sha256(token.encode()).hexdigest() if token else "",
        }
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        started = time.time()
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode() or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._record(400, "", started)
            self._send(400, {"error": {"message": "bad request body", "type": "invalid_request_error"}})
            return

        model = str(payload.get("model") or "mock-chat")
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else auth
        if token != UPSTREAM_KEY:
            self._record(401, model, started)
            self._send(401, {"error": {"message": "invalid upstream key", "type": "authentication_error"}})
            return

        self._record(200, model, started)
        self._send(200, _body(model))


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
