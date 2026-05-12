from __future__ import annotations

import hashlib
import http.client
import json
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from .claude_request_capture_proxy_config_helpers import ProxyConfig
    from .claude_request_capture_proxy_config_helpers import _write_json
    from .claude_request_capture_proxy_http_helpers import _HOP_BY_HOP_HEADERS
    from .claude_request_capture_proxy_http_helpers import _decode_body
    from .claude_request_capture_proxy_http_helpers import _header_items
    from .claude_request_capture_proxy_http_helpers import _join_upstream_path
    from .claude_request_capture_proxy_http_helpers import _now_iso
    from .claude_request_capture_proxy_http_helpers import _upstream_target_url
except ImportError:
    from claude_request_capture_proxy_config_helpers import ProxyConfig
    from claude_request_capture_proxy_config_helpers import _write_json
    from claude_request_capture_proxy_http_helpers import _HOP_BY_HOP_HEADERS
    from claude_request_capture_proxy_http_helpers import _decode_body
    from claude_request_capture_proxy_http_helpers import _header_items
    from claude_request_capture_proxy_http_helpers import _join_upstream_path
    from claude_request_capture_proxy_http_helpers import _now_iso
    from claude_request_capture_proxy_http_helpers import _upstream_target_url


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class CaptureProxyServer(_ThreadedHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_cls: type[BaseHTTPRequestHandler],
        *,
        config: ProxyConfig,
    ) -> None:
        super().__init__(server_address, handler_cls)
        self.capture_config = config
        self._counter_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._request_counter = 0
        (config.out_dir / "requests").mkdir(parents=True, exist_ok=True)
        (config.out_dir / "responses").mkdir(parents=True, exist_ok=True)

    def next_request_id(self) -> str:
        with self._counter_lock:
            self._request_counter += 1
            return f"{self._request_counter:06d}"

    def append_event(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        with self._log_lock:
            with (self.capture_config.out_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def build_capture_proxy_handler(config: ProxyConfig) -> type[BaseHTTPRequestHandler]:
    upstream = urlsplit(config.upstream_base_url)
    if not upstream.scheme or not upstream.netloc:
        raise ValueError(f"invalid upstream base url: {config.upstream_base_url!r}")
    if upstream.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported upstream scheme: {upstream.scheme!r}")

    class CaptureProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_POST(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_PUT(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_PATCH(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_HEAD(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            return

        def _request_body(self) -> bytes:
            content_length = int(self.headers.get("Content-Length") or "0")
            if content_length <= 0:
                return b""
            return self.rfile.read(content_length)

        def _handle_proxy_request(self) -> None:
            server = self.server
            if not isinstance(server, CaptureProxyServer):
                raise RuntimeError("unexpected server type")
            request_id = server.next_request_id()
            started = time.time()
            body = self._request_body()
            parsed_body_text, parsed_body_json = _decode_body(body)
            path_only, _, query = self.path.partition("?")
            upstream_path = _join_upstream_path(upstream, path_only)
            upstream_url = _upstream_target_url(upstream, upstream_path, query)
            request_body_path = server.capture_config.out_dir / "requests" / f"{request_id}.body.bin"
            request_body_path.write_bytes(body)
            request_record = {
                "request_id": request_id,
                "ts": _now_iso(),
                "client_address": self.client_address[0],
                "method": self.command,
                "path": path_only,
                "query": query,
                "upstream_url": upstream_url,
                "headers": _header_items(self.headers),
                "body_length": len(body),
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "body_utf8": parsed_body_text,
                "body_json": parsed_body_json,
                "body_path": str(request_body_path),
            }
            _write_json(server.capture_config.out_dir / "requests" / f"{request_id}.json", request_record)
            server.append_event({"kind": "request", **request_record})

            upstream_headers: dict[str, str] = {}
            for name, value in self.headers.items():
                if str(name).lower() == "host":
                    continue
                upstream_headers[str(name)] = str(value)
            connection_cls = http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
            connection = connection_cls(
                upstream.hostname,
                upstream.port,
                timeout=float(server.capture_config.upstream_timeout_seconds),
            )
            preview = bytearray()
            try:
                target = upstream_path + (f"?{query}" if query else "")
                connection.request(self.command, target, body=body or None, headers=upstream_headers)
                response = connection.getresponse()
                response_headers = response.getheaders()
                chunked = "chunked" in str(response.getheader("Transfer-Encoding") or "").lower()
                self.send_response(response.status, response.reason)
                for name, value in response_headers:
                    lower = str(name).lower()
                    if lower in _HOP_BY_HOP_HEADERS:
                        continue
                    if chunked and lower == "content-length":
                        continue
                    self.send_header(name, value)
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        remaining = server.capture_config.response_preview_bytes - len(preview)
                        if remaining > 0:
                            preview.extend(chunk[:remaining])
                        self.wfile.write(chunk)
                        self.wfile.flush()
                elapsed_ms = round((time.time() - started) * 1000, 3)
                preview_path = server.capture_config.out_dir / "responses" / f"{request_id}.preview.bin"
                preview_path.write_bytes(bytes(preview))
                preview_text, _ = _decode_body(bytes(preview))
                response_record = {
                    "request_id": request_id,
                    "ts": _now_iso(),
                    "upstream_url": upstream_url,
                    "status": int(response.status),
                    "reason": str(response.reason or ""),
                    "headers": [{"name": str(name), "value": str(value)} for name, value in response_headers],
                    "preview_length": len(preview),
                    "preview_sha256": hashlib.sha256(bytes(preview)).hexdigest(),
                    "preview_utf8": preview_text,
                    "preview_path": str(preview_path),
                    "elapsed_ms": elapsed_ms,
                }
                _write_json(server.capture_config.out_dir / "responses" / f"{request_id}.json", response_record)
                server.append_event({"kind": "response", **response_record})
            except Exception as exc:
                elapsed_ms = round((time.time() - started) * 1000, 3)
                error_record = {
                    "request_id": request_id,
                    "ts": _now_iso(),
                    "upstream_url": upstream_url,
                    "error": repr(exc),
                    "elapsed_ms": elapsed_ms,
                }
                _write_json(server.capture_config.out_dir / "responses" / f"{request_id}.json", error_record)
                server.append_event({"kind": "proxy_error", **error_record})
                body_text = json.dumps(
                    {
                        "error": "proxy_forward_failed",
                        "detail": str(exc),
                        "request_id": request_id,
                    },
                    ensure_ascii=False,
                )
                encoded = body_text.encode("utf-8")
                self.send_response(502, "Bad Gateway")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Connection", "close")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(encoded)
                    self.wfile.flush()
            finally:
                connection.close()
                self.close_connection = True

    return CaptureProxyHandler


def create_capture_proxy_server(
    *,
    host: str,
    port: int,
    upstream_base_url: str,
    out_dir: Path,
    response_preview_bytes: int = 8192,
    upstream_timeout_seconds: float = 300.0,
) -> CaptureProxyServer:
    config = ProxyConfig(
        upstream_base_url=str(upstream_base_url),
        out_dir=Path(out_dir).resolve(),
        response_preview_bytes=max(int(response_preview_bytes), 0),
        upstream_timeout_seconds=max(float(upstream_timeout_seconds), 1.0),
    )
    handler_cls = build_capture_proxy_handler(config)
    return CaptureProxyServer((host, port), handler_cls, config=config)
