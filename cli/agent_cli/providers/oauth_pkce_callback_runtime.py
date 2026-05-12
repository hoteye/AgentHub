from __future__ import annotations

import http.server
import socketserver
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

ERROR_INVALID_REDIRECT_URI = "pkce_invalid_redirect_uri"
ERROR_CALLBACK_TIMEOUT = "pkce_callback_timeout"
ERROR_CALLBACK_BIND_FAILED = "pkce_callback_bind_failed"
ERROR_CALLBACK_RESPONSE_INVALID = "pkce_callback_invalid_payload"


def _as_str(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class _ListenerTarget:
    bind_host: str
    public_host: str
    port: int
    path: str


class _SingleUseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def _listener_target_from_redirect_uri(redirect_uri: str) -> _ListenerTarget | None:
    parsed = urllib.parse.urlparse(_as_str(redirect_uri))
    if parsed.scheme.lower() != "http":
        return None
    host = _as_str(parsed.hostname)
    if not host:
        return None
    if ":" in host:
        return None
    if host == "localhost":
        bind_host = "127.0.0.1"
    else:
        bind_host = host
    port = int(parsed.port or 80)
    if port <= 0 or port > 65535:
        return None
    path = _as_str(parsed.path) or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return _ListenerTarget(
        bind_host=bind_host,
        public_host=host,
        port=port,
        path=path,
    )


def wait_for_pkce_callback(
    *,
    redirect_uri: str,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    target = _listener_target_from_redirect_uri(redirect_uri)
    if target is None:
        return {
            "status": "error",
            "error_code": ERROR_INVALID_REDIRECT_URI,
            "error_hint": "redirect_uri must be http://<host>:<port>/<path>",
        }

    timeout_value = max(1, int(timeout_seconds or 120))
    payload: dict[str, str] = {}

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            request_target = urllib.parse.urlparse(str(self.path or ""))
            request_path = _as_str(request_target.path) or "/"
            if request_path != target.path:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not Found")
                return
            query = urllib.parse.parse_qs(str(request_target.query or ""), keep_blank_values=False)
            payload["code"] = _as_str((query.get("code") or [""])[0])
            payload["state"] = _as_str((query.get("state") or [""])[0])
            payload["error"] = _as_str((query.get("error") or [""])[0])
            payload["error_description"] = _as_str((query.get("error_description") or [""])[0])
            has_code = bool(payload["code"])
            self.send_response(200 if has_code else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            if has_code:
                self.wfile.write(b"AgentHub auth callback received. You can close this page.")
            else:
                self.wfile.write(b"AgentHub auth callback received without authorization code.")

        def log_message(self, *_args: Any) -> None:
            return

    try:
        with _SingleUseTCPServer((target.bind_host, target.port), _CallbackHandler) as server:
            server.timeout = 0.2
            deadline = time.time() + timeout_value
            while time.time() < deadline:
                server.handle_request()
                if payload:
                    break
    except Exception as exc:
        return {
            "status": "error",
            "error_code": ERROR_CALLBACK_BIND_FAILED,
            "error_hint": str(exc),
            "redirect_uri": redirect_uri,
        }

    if not payload:
        return {
            "status": "timeout",
            "error_code": ERROR_CALLBACK_TIMEOUT,
            "redirect_uri": redirect_uri,
            "timeout_seconds": timeout_value,
        }
    callback_error = _as_str(payload.get("error"))
    if callback_error:
        return {
            "status": "error",
            "error_code": callback_error,
            "error_hint": _as_str(payload.get("error_description")),
            "redirect_uri": redirect_uri,
        }
    callback_code = _as_str(payload.get("code"))
    if not callback_code:
        return {
            "status": "error",
            "error_code": ERROR_CALLBACK_RESPONSE_INVALID,
            "error_hint": "authorization code missing in callback query",
            "redirect_uri": redirect_uri,
        }
    return {
        "status": "ok",
        "code": callback_code,
        "state": _as_str(payload.get("state")),
        "redirect_uri": redirect_uri,
    }
