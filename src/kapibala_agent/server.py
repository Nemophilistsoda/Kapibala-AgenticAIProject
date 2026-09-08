"""Minimal stdlib HTTP backend for the frontend demo.

Wiring (same boundaries as the CLI, no new execution paths):
- POST /api/chat -> AgentService.handle_customer_message (customer channel)
- POST /api/admin/reactivate -> OperatorService.reactivate (operator channel)
- GET / serves frontend/index.html so the page and API share one origin.

Only stdlib + existing project deps. The transport is a null sink because the
HTTP response body carries the customer-visible text; the SQLite-backed rate
limit / state machine / audit path is identical to `cli.py chat`.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .audit import JsonlAuditSink
from .executor import Executor
from .llm import LLMError
from .service import AgentService, OperatorService
from .store import SessionStore

MAX_BODY_BYTES = 16 * 1024
MAX_MESSAGE_CHARS = 2000


class _NullTransport:
    """HTTP carries the reply; nothing else may send."""

    def send(self, customer_id: str, text: str) -> None:
        return None


def build_services() -> tuple[AgentService, OperatorService]:
    """Shared singletons: customer and operator must see the same SQLite rows."""
    from .llm import GeminiLLM

    load_dotenv()
    store = SessionStore(os.getenv("AGENT_DB_PATH", "agent.db"))
    audit = JsonlAuditSink(Path(os.getenv("AUDIT_LOG_PATH", "audit.jsonl")))
    llm = GeminiLLM()
    executor = Executor(
        store,
        _NullTransport(),
        window_seconds=float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
        canary=llm.canary,
    )
    return AgentService(store, llm, executor, audit), OperatorService(store, audit)


def _frontend_dir() -> Path:
    # server.py 在 <repo>/src/kapibala_agent/ 下，parents[2] 即仓库根。
    return Path(__file__).resolve().parents[2] / "frontend"


def _outcome_payload(outcome: Any) -> dict[str, Any]:
    action = getattr(outcome, "executed_action", None)
    return {
        "executed_action": action.value if action is not None else None,
        "status": outcome.status.value,
        "reason": outcome.reason,
        "customer_visible_text": outcome.customer_visible_text,
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "KapibalaAgent/1.0"

    def log_message(self, fmt: str, *args: object) -> None:  # quieter stdlib logs
        pass

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("invalid body length")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            page = _frontend_dir() / "index.html"
            if not page.exists():
                self._send_json(404, {"error": "frontend/index.html not found"})
                return
            body = page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/health":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            if self.path == "/api/chat":
                data = self._read_json()
                customer_id = str(data.get("customer_id", "")).strip()
                message = str(data.get("message", "")).strip()
                if not customer_id or not message:
                    self._send_json(400, {"error": "customer_id and message must be non-empty"})
                    return
                if len(message) > MAX_MESSAGE_CHARS:
                    self._send_json(400, {"error": "message too long"})
                    return
                raw_message_id = data.get("message_id")
                message_id: str | None = None
                if raw_message_id is not None:
                    message_id = str(raw_message_id).strip()
                    if not message_id:
                        self._send_json(
                            400, {"error": "message_id must be non-empty when provided"}
                        )
                        return
                service: AgentService = self.server.customer_service  # type: ignore[attr-defined]
                outcome = service.handle_customer_message(
                    customer_id, message, message_id=message_id
                )
                self._send_json(200, _outcome_payload(outcome))
                return
            if self.path == "/api/admin/reactivate":
                data = self._read_json()
                customer_id = str(data.get("customer_id", "")).strip()
                if not customer_id:
                    self._send_json(400, {"error": "customer_id must be non-empty"})
                    return
                operator: OperatorService = self.server.operator_service  # type: ignore[attr-defined]
                outcome = operator.reactivate(customer_id)
                self._send_json(200, _outcome_payload(outcome))
                return
            self._send_json(404, {"error": "not found"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception:
            # Never leak provider details / keys through HTTP.
            self._send_json(500, {"error": "internal error"})


def serve(host: str = "127.0.0.1", port: int = 8000) -> int:
    try:
        customer_service, operator_service = build_services()
    except LLMError as exc:
        print(f"配置错误：{exc}")
        return 2
    server = ThreadingHTTPServer((host, port), _Handler)
    server.customer_service = customer_service  # type: ignore[attr-defined]
    server.operator_service = operator_service  # type: ignore[attr-defined]
    print(f"KapibalaAI serving frontend + api on http://{host}:{port} (Ctrl+C 停止)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
