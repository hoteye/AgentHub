from __future__ import annotations

import argparse
import json
import mimetypes
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from cli.agent_cli.gateway_server.control_ui_contract import (
    CONTROL_UI_BOOTSTRAP_CONFIG_PATH,
    build_control_ui_bootstrap,
    build_control_ui_state_snapshot,
)
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_factory import build_persistent_runtime
from shared.web_automation.artifacts import resolve_existing_artifact_path
from shared.web_automation.client import replace_service
from shared.web_automation.proxy import BrowserProxyExecutor
from shared.web_automation.service import BrowserService

from .gateway_ws import gateway_ws_poll
from .gui_bridge_api import dispatch_gui_bridge_action
from .gui_http_server_runtime import execute_browser_proxy_http, synthesize_gui_bridge_events


@dataclass
class GuiBridgeEventEnvelope:
    cursor: int
    payload: dict[str, Any]


class GuiBridgeEventBus:
    def __init__(self, *, max_events: int = 500) -> None:
        self._events: deque[GuiBridgeEventEnvelope] = deque(maxlen=max_events)
        self._next_cursor = 1

    def append_many(self, events: Iterable[dict[str, Any]]) -> None:
        for item in events:
            self._events.append(
                GuiBridgeEventEnvelope(cursor=self._next_cursor, payload=dict(item))
            )
            self._next_cursor += 1

    def list_since(self, cursor: int) -> dict[str, Any]:
        safe_cursor = max(0, int(cursor))
        items = [item.payload for item in self._events if item.cursor > safe_cursor]
        next_cursor = self._events[-1].cursor if self._events else safe_cursor
        return {"events": items, "next_cursor": next_cursor}


class GuiBridgeHttpHandler(BaseHTTPRequestHandler):
    runtime: AgentCliRuntime | None = None
    event_bus: GuiBridgeEventBus | None = None
    base_path: str = "/gui"
    browser_proxy: BrowserProxyExecutor | None = None

    def do_OPTIONS(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        valid_paths = {
            f"{type(self).base_path}/health",
            f"{type(self).base_path}/events",
            f"{type(self).base_path}/gateway-events",
            f"{type(self).base_path}{CONTROL_UI_BOOTSTRAP_CONFIG_PATH}",
            f"{type(self).base_path}/control-ui/state",
            f"{type(self).base_path}/requests",
            f"{type(self).base_path}/browser-proxy",
            f"{type(self).base_path}/browser-proxy/artifact",
        }
        normalized_path = parsed.path.rstrip("/")
        if normalized_path not in valid_paths and not normalized_path.startswith(
            f"{type(self).base_path}/browser-proxy/"
        ):
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()
            return
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == f"{type(self).base_path}/health":
            self._send_json(200, {"ok": True})
            return
        if parsed.path == f"{type(self).base_path}{CONTROL_UI_BOOTSTRAP_CONFIG_PATH}":
            runtime = type(self).runtime or build_persistent_runtime()
            self._send_json(
                200, build_control_ui_bootstrap(runtime, base_path=type(self).base_path)
            )
            return
        if parsed.path.rstrip("/") == f"{type(self).base_path}/control-ui/state":
            runtime = type(self).runtime or build_persistent_runtime()
            query = parse_qs(parsed.query)
            try:
                limit = _parse_int_value(query, key="limit", default=20)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            self._send_json(
                200, {"ok": True, "data": build_control_ui_state_snapshot(runtime, limit=limit)}
            )
            return
        if parsed.path.rstrip("/") == f"{type(self).base_path}/gateway-events":
            runtime = type(self).runtime or build_persistent_runtime()
            query = parse_qs(parsed.query)
            try:
                cursor = _parse_int_value(query, key="cursor", default=0)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            streams = []
            for raw in query.get("stream") or query.get("streams") or []:
                streams.extend(item.strip() for item in str(raw).split(","))
            self._send_json(
                200,
                {"ok": True, **gateway_ws_poll(runtime, cursor=cursor, streams=streams or None)},
            )
            return
        if parsed.path.rstrip("/") == f"{type(self).base_path}/browser-proxy/artifact":
            self._handle_browser_proxy_artifact_http(parsed=parsed)
            return
        if parsed.path.rstrip("/") == f"{type(self).base_path}/browser-proxy" or parsed.path.rstrip(
            "/"
        ).startswith(f"{type(self).base_path}/browser-proxy/"):
            self._handle_browser_proxy_http("GET", parsed=parsed)
            return
        if parsed.path.rstrip("/") != f"{type(self).base_path}/events":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        query = parse_qs(parsed.query)
        cursor = int((query.get("cursor") or ["0"])[0] or "0")
        event_bus = type(self).event_bus or GuiBridgeEventBus()
        self._send_json(200, {"ok": True, **event_bus.list_since(cursor)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == f"{type(self).base_path}/browser-proxy" or parsed.path.rstrip(
            "/"
        ).startswith(f"{type(self).base_path}/browser-proxy/"):
            self._handle_browser_proxy_http("POST", parsed=parsed)
            return
        if parsed.path.rstrip("/") != f"{type(self).base_path}/requests":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        content_length = int(self.headers.get("Content-Length") or "0")
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._send_json(400, {"ok": False, "error": f"invalid_json:{exc}"})
            return
        runtime = type(self).runtime or build_persistent_runtime()
        request_id = str(payload.get("request_id") or "req_gui_bridge")
        action = str(payload.get("action") or "").strip()
        response = dispatch_gui_bridge_action(
            runtime,
            action=action,
            payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            request_id=request_id,
        )
        event_bus = type(self).event_bus or GuiBridgeEventBus()
        event_bus.append_many(synthesize_gui_bridge_events(action, response))
        self._send_json(200 if response.get("ok") else 400, response)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == f"{type(self).base_path}/browser-proxy" or parsed.path.rstrip(
            "/"
        ).startswith(f"{type(self).base_path}/browser-proxy/"):
            self._handle_browser_proxy_http("DELETE", parsed=parsed)
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _handle_browser_proxy_artifact_http(self, *, parsed) -> None:
        query = parse_qs(parsed.query)
        requested_path = str((query.get("path") or [""])[-1] or "").strip()
        if not requested_path:
            self._send_json(400, {"ok": False, "error": "artifact_path_required"})
            return
        try:
            artifact_path = resolve_existing_artifact_path(requested_path)
        except Exception as exc:
            self._send_json(404, {"ok": False, "error": str(exc)})
            return
        body = artifact_path.read_bytes()
        content_type = mimetypes.guess_type(artifact_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self._send_cors_headers()
        self._send_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-AgentHub-Artifact-Path", str(artifact_path))
        self.end_headers()
        self._write_body(body)

    def _handle_browser_proxy_http(self, method: str, *, parsed) -> None:
        proxy = type(self).browser_proxy or BrowserProxyExecutor()
        try:
            result = execute_browser_proxy_http(
                proxy,
                method=method,
                parsed=parsed,
                headers=self.headers,
                rfile=self.rfile,
                base_path=type(self).base_path,
            )
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        self._send_json(200, result)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self._send_cors_headers()
        self._send_security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._write_body(body)

    def _write_body(self, body: bytes) -> None:
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_security_headers(self) -> None:
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")


def run_gui_bridge_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    base_path: str = "/gui",
    runtime: AgentCliRuntime | None = None,
) -> int:
    handler = build_gui_bridge_http_handler(
        runtime=runtime or build_persistent_runtime(),
        base_path=base_path,
    )
    server = HTTPServer((host, int(port)), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EasyClaw GUI bridge HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--base-path", default="/gui")
    args = parser.parse_args(argv)
    return run_gui_bridge_server(
        host=str(args.host), port=int(args.port), base_path=str(args.base_path)
    )


def build_gui_bridge_http_handler(
    *,
    runtime: AgentCliRuntime,
    base_path: str = "/gui",
):
    replace_service(BrowserService())
    return type(
        "BoundGuiBridgeHttpHandler",
        (GuiBridgeHttpHandler,),
        {
            "runtime": runtime,
            "event_bus": GuiBridgeEventBus(),
            "base_path": base_path.rstrip("/") or "/gui",
            "browser_proxy": BrowserProxyExecutor(),
        },
    )


def _parse_int_value(query: dict[str, list[str]], *, key: str, default: int) -> int:
    raw = (query.get(key) or [str(default)])[0] or str(default)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{key}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
