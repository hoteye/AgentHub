from __future__ import annotations

import http.client
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

try:
    from cli.scripts.previous_response_id_rejection_live_harness_model_helpers import (
        _HOP_BY_HOP_HEADERS,
        _REJECTION_BODY,
        ObservedRequest,
        ProxyConfig,
        _body_item_types,
        _decode_body,
        _join_upstream_path,
        _now_iso,
        _redacted_headers,
        _tool_names,
        _upstream_target_url,
        _write_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct helper import
    from previous_response_id_rejection_live_harness_model_helpers import (  # type: ignore[no-redef]
        _HOP_BY_HOP_HEADERS,
        _REJECTION_BODY,
        ObservedRequest,
        ProxyConfig,
        _body_item_types,
        _decode_body,
        _join_upstream_path,
        _now_iso,
        _redacted_headers,
        _tool_names,
        _upstream_target_url,
        _write_json,
    )


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class PreviousResponseIdProxyServer(_ThreadedHTTPServer):
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
        self._records_lock = threading.Lock()
        self._request_counter = 0
        self._rejection_injected = False
        self.observed_requests: list[ObservedRequest] = []
        (config.out_dir / "requests").mkdir(parents=True, exist_ok=True)
        (config.out_dir / "responses").mkdir(parents=True, exist_ok=True)

    def next_sequence(self) -> int:
        with self._counter_lock:
            self._request_counter += 1
            return self._request_counter

    def append_request(self, record: ObservedRequest) -> None:
        with self._records_lock:
            self.observed_requests.append(record)

    def should_inject_rejection(self, *, previous_response_id: str) -> bool:
        with self._records_lock:
            if not previous_response_id or self._rejection_injected:
                return False
            self._rejection_injected = True
            return True


def build_previous_response_id_proxy_handler(config: ProxyConfig) -> type[BaseHTTPRequestHandler]:
    upstream = urlsplit(config.upstream_base_url)
    if not upstream.scheme or not upstream.netloc:
        raise ValueError(f"invalid upstream base url: {config.upstream_base_url!r}")
    if upstream.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported upstream scheme: {upstream.scheme!r}")

    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def do_GET(self) -> None:  # noqa: N802
            self._handle_proxy_request()

        def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
            return

        def _handle_proxy_request(self) -> None:
            server = self.server
            assert isinstance(server, PreviousResponseIdProxyServer)
            sequence = server.next_sequence()
            request_id = f"{sequence:06d}"
            content_length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(content_length) if content_length > 0 else b""
            body_text, body_json = _decode_body(body)
            request_url = urlsplit(self.path)
            previous_response_id = (
                str(body_json.get("previous_response_id") or "").strip()
                if isinstance(body_json, dict)
                else ""
            )
            inject_rejection = server.should_inject_rejection(
                previous_response_id=previous_response_id,
            )
            upstream_path = _join_upstream_path(upstream, request_url.path)
            forwarded_url = _upstream_target_url(upstream, upstream_path, request_url.query)
            input_types = _body_item_types(body_json)
            tool_names = _tool_names(body_json)
            request_meta = {
                "ts": _now_iso(),
                "sequence": sequence,
                "method": self.command,
                "path": request_url.path,
                "query": request_url.query,
                "headers": _redacted_headers(self.headers),
                "body_text": body_text,
                "body_json": body_json,
                "previous_response_id": previous_response_id,
                "input_types": input_types,
                "tool_names": tool_names,
                "decision": "inject_rejection" if inject_rejection else "forward",
                "forwarded_url": forwarded_url,
            }
            _write_json(server.capture_config.out_dir / "requests" / f"{request_id}.json", request_meta)
            (server.capture_config.out_dir / "requests" / f"{request_id}.body.bin").write_bytes(body)
            record = ObservedRequest(
                sequence=sequence,
                method=self.command,
                path=request_url.path,
                query=request_url.query,
                previous_response_id=previous_response_id,
                input_types=input_types,
                tool_names=tool_names,
                injected_rejection=inject_rejection,
                forwarded_url=forwarded_url,
            )
            server.append_request(record)
            if inject_rejection:
                self._send_injected_rejection(server=server, sequence=sequence, request_id=request_id)
                return
            self._forward_to_upstream(
                server=server,
                request_url=request_url,
                upstream_path=upstream_path,
                body=body,
                request_id=request_id,
                sequence=sequence,
            )

        def _send_injected_rejection(
            self,
            *,
            server: PreviousResponseIdProxyServer,
            sequence: int,
            request_id: str,
        ) -> None:
            response_body = json.dumps(_REJECTION_BODY, ensure_ascii=False).encode("utf-8")
            response_meta = {
                "ts": _now_iso(),
                "sequence": sequence,
                "status": 400,
                "headers": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Content-Length", "value": str(len(response_body))},
                ],
                "preview_utf8": response_body.decode("utf-8"),
                "injected_rejection": True,
            }
            _write_json(server.capture_config.out_dir / "responses" / f"{request_id}.json", response_meta)
            (server.capture_config.out_dir / "responses" / f"{request_id}.body.bin").write_bytes(response_body)
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def _forward_to_upstream(
            self,
            *,
            server: PreviousResponseIdProxyServer,
            request_url,
            upstream_path: str,
            body: bytes,
            request_id: str,
            sequence: int,
        ) -> None:
            connection_cls = http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
            forwarded_headers = {
                str(name): str(value)
                for name, value in list(self.headers.items())
                if str(name).strip().lower() not in _HOP_BY_HOP_HEADERS.union({"host"})
            }
            connection = connection_cls(
                upstream.netloc,
                timeout=server.capture_config.upstream_timeout_seconds,
            )
            try:
                target = upstream_path
                if request_url.query:
                    target = f"{target}?{request_url.query}"
                connection.request(
                    self.command,
                    target,
                    body=body if body else None,
                    headers=forwarded_headers,
                )
                upstream_response = connection.getresponse()
                response_body = upstream_response.read()
                response_meta = {
                    "ts": _now_iso(),
                    "sequence": sequence,
                    "status": int(upstream_response.status),
                    "reason": str(upstream_response.reason or ""),
                    "headers": _redacted_headers(upstream_response.headers),
                    "preview_utf8": _decode_body(response_body)[0],
                    "injected_rejection": False,
                }
                _write_json(server.capture_config.out_dir / "responses" / f"{request_id}.json", response_meta)
                (server.capture_config.out_dir / "responses" / f"{request_id}.body.bin").write_bytes(response_body)
                self.send_response(upstream_response.status, upstream_response.reason)
                for name, value in list(upstream_response.headers.items()):
                    lowered = str(name).strip().lower()
                    if lowered in _HOP_BY_HOP_HEADERS:
                        continue
                    if lowered == "content-length":
                        continue
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
            finally:
                connection.close()

    return ProxyHandler


def create_previous_response_id_proxy_server(
    *,
    host: str,
    port: int,
    upstream_base_url: str,
    out_dir: Path,
    upstream_timeout_seconds: float = 180.0,
) -> PreviousResponseIdProxyServer:
    config = ProxyConfig(
        upstream_base_url=str(upstream_base_url).strip(),
        out_dir=out_dir,
        upstream_timeout_seconds=float(upstream_timeout_seconds),
    )
    return PreviousResponseIdProxyServer(
        (host, port),
        build_previous_response_id_proxy_handler(config),
        config=config,
    )
