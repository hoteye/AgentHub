import json
import os
import threading
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.web_automation.config import load_config
from shared.web_automation.proxy_client import (
    AppServerBrowserProxyClient,
    AppServerBrowserProxyError,
    AppServerBrowserProxyTransport,
    BrowserProxyHttpAuth,
    HttpBrowserProxyClient,
    HttpBrowserProxyError,
    HttpBrowserProxyTransport,
    create_browser_proxy_transport,
    _resolve_http_proxy_auth_headers,
)

class _WritableBuffer:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, text: str) -> int:
        self.lines.append(text)
        return len(text)

    def flush(self) -> None:
        return None

class _ReadableBuffer:
    def __init__(self, payloads: list[object]) -> None:
        self._lines = [json.dumps(item, ensure_ascii=False) + "\n" for item in payloads]

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)

class _ProxyHttpHandler(BaseHTTPRequestHandler):
    responses: list[dict[str, object]] = []
    requests: list[dict[str, object]] = []
    artifact_blobs: dict[str, dict[str, object]] = {}

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None

    def _handle(self) -> None:
        if self.path.startswith("/artifact?"):
            from urllib.parse import parse_qs, urlparse

            query = parse_qs(urlparse(self.path).query)
            requested_path = str((query.get("path") or [""])[-1] or "")
            artifact = self.__class__.artifact_blobs.get(requested_path)
            if artifact is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = bytes(artifact.get("content") or b"")
            content_type = str(artifact.get("mime_type") or "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        length = int(self.headers.get("Content-Length") or "0")
        raw_body = self.rfile.read(length) if length > 0 else b""
        decoded_body = raw_body.decode("utf-8", errors="replace")
        try:
            parsed_body = json.loads(decoded_body) if decoded_body else None
        except json.JSONDecodeError:
            parsed_body = decoded_body
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "password": self.headers.get("X-AgentHub-Password"),
                "body": parsed_body,
            }
        )
        response = self.__class__.responses.pop(0) if self.__class__.responses else {"status": 200, "body": {"ok": True}}
        status = int(response.get("status") or 200)
        body = response.get("body")
        payload = json.dumps(body if isinstance(body, dict) else {}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

class _ProxyHttpServer:
    def __init__(self) -> None:
        _ProxyHttpHandler.requests = []
        _ProxyHttpHandler.responses = []
        _ProxyHttpHandler.artifact_blobs = {}
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyHttpHandler)
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_ProxyHttpServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    @property
    def requests(self) -> list[dict[str, object]]:
        return list(_ProxyHttpHandler.requests)

    def enqueue(self, *, status: int = 200, body: dict[str, object] | None = None) -> None:
        _ProxyHttpHandler.responses.append({"status": status, "body": body or {"ok": True}})

    def add_artifact(self, *, path: str, content: bytes, mime_type: str = "application/octet-stream") -> None:
        _ProxyHttpHandler.artifact_blobs[str(path)] = {"content": bytes(content), "mime_type": mime_type}

class AppServerBrowserProxyClientTest(unittest.TestCase):
    def test_load_config_reads_http_proxy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "browser_automation.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "enabled = true",
                        "",
                        "[proxy]",
                        'transport = "http"',
                        'base_url = "http://127.0.0.1:8787"',
                        'auth_token = "proxy-token"',
                        'auth_password = "proxy-password"',
                        "inject_loopback_auth = false",
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)

        self.assertEqual(config.proxy_transport, "http")
        self.assertEqual(config.proxy_base_url, "http://127.0.0.1:8787")
        self.assertEqual(config.proxy_auth_token, "proxy-token")
        self.assertEqual(config.proxy_auth_password, "proxy-password")
        self.assertFalse(config.proxy_inject_loopback_auth)

    def test_client_initializes_and_calls_browser_proxy(self) -> None:
        stdin = _WritableBuffer()
        stdout = _ReadableBuffer(
            [
                {"id": "init_browser_proxy", "result": {"ok": True}},
                {"id": "browser_proxy_123456789abc", "result": {"status": 200, "result": {"ok": True}}},
            ]
        )
        client = AppServerBrowserProxyClient(stdin=stdin, stdout=stdout)

        # Pin uuid so request ids stay deterministic for the scripted stream.
        import uuid

        original = uuid.uuid4
        uuid.uuid4 = lambda: type("U", (), {"hex": "123456789abcdeffedcba"})()
        try:
            result = client.browser_proxy(method="GET", path="/profiles", profile="openclaw")
        finally:
            uuid.uuid4 = original

        self.assertEqual(result["status"], 200)
        written = [json.loads(line) for line in stdin.lines]
        self.assertEqual(written[0]["method"], "initialize")
        self.assertEqual(written[1]["method"], "initialized")
        self.assertEqual(written[2]["method"], "browser/proxy")
        self.assertEqual(written[2]["params"]["path"], "/profiles")

    def test_client_ignores_notifications_while_waiting_for_response(self) -> None:
        stdin = _WritableBuffer()
        stdout = _ReadableBuffer(
            [
                {"id": "init_browser_proxy", "result": {"ok": True}},
                {"method": "session/activity", "params": {"title": "noop"}},
                {"id": "browser_proxy_123456789abc", "result": {"status": 200, "result": {"ok": True}}},
            ]
        )
        client = AppServerBrowserProxyClient(stdin=stdin, stdout=stdout)

        import uuid

        original = uuid.uuid4
        uuid.uuid4 = lambda: type("U", (), {"hex": "123456789abcdeffedcba"})()
        try:
            result = client.browser_proxy(method="GET", path="/")
        finally:
            uuid.uuid4 = original

        self.assertTrue(result["result"]["ok"])

    def test_client_raises_on_error_response(self) -> None:
        stdin = _WritableBuffer()
        stdout = _ReadableBuffer(
            [
                {"id": "init_browser_proxy", "result": {"ok": True}},
                {
                    "id": "browser_proxy_123456789abc",
                    "error": {"code": -32032, "message": "Browser proxy failed", "data": {"detail": "boom"}},
                },
            ]
        )
        client = AppServerBrowserProxyClient(stdin=stdin, stdout=stdout)

        import uuid

        original = uuid.uuid4
        uuid.uuid4 = lambda: type("U", (), {"hex": "123456789abcdeffedcba"})()
        try:
            with self.assertRaisesRegex(AppServerBrowserProxyError, "Browser proxy failed"):
                client.browser_proxy(method="GET", path="/snapshot")
        finally:
            uuid.uuid4 = original

    def test_transport_delegates_to_client(self) -> None:
        class _FakeClient:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def browser_proxy(self, **kwargs):
                self.calls.append(dict(kwargs))
                return {"status": 200, "result": {"ok": True}}

            def close(self) -> None:
                self.calls.append({"closed": True})

        client = _FakeClient()
        transport = AppServerBrowserProxyTransport(client=client)  # type: ignore[arg-type]

        result = transport.run(method="POST", path="/act", body={"kind": "click"})
        transport.close()

        self.assertEqual(result["status"], 200)
        self.assertEqual(client.calls[0]["path"], "/act")
        self.assertEqual(client.calls[1]["closed"], True)

    def test_http_client_injects_loopback_bearer_auth_and_profile_query(self) -> None:
        with _ProxyHttpServer() as server:
            server.enqueue(body={"ok": True, "action": "profiles"})
            client = HttpBrowserProxyClient(
                base_url=server.base_url,
                config=load_config(),
                env={"AGENTHUB_BROWSER_PROXY_TOKEN": "loopback-token"},
            )

            result = client.browser_proxy(method="GET", path="/profiles", profile="review")

        self.assertEqual(result["status"], 200)
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(server.requests[0]["authorization"], "Bearer loopback-token")
        self.assertIn("/profiles?profile=review", str(server.requests[0]["path"]))

    def test_http_auth_headers_use_explicit_password_for_non_loopback(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        headers = _resolve_http_proxy_auth_headers(
            "https://browser.example.com/profiles",
            explicit_auth=BrowserProxyHttpAuth(password="secret-password"),
            config=BrowserAutomationConfig(),
            env={},
            inject_loopback_auth=True,
        )

        self.assertEqual(headers["X-AgentHub-Password"], "secret-password")

    def test_http_transport_calls_server_and_returns_proxy_shape(self) -> None:
        with _ProxyHttpServer() as server:
            server.enqueue(body={"ok": True, "running": True})
            transport = HttpBrowserProxyTransport(base_url=server.base_url, inject_loopback_auth=False)

            result = transport.run(method="GET", path="/")

        self.assertEqual(result["status"], 200)
        self.assertEqual(result["result"]["running"], True)
        self.assertEqual(result["files"], [])

    def test_http_client_preserves_explicit_remote_files_payload(self) -> None:
        remote_file = {
            "path": "/remote/artifacts/shot.png",
            "base64": "cG5nLWJ5dGVz",
            "mimeType": "image/png",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with _ProxyHttpServer() as server:
                    server.enqueue(
                        body={
                            "status": 200,
                            "result": {"ok": True, "artifact": {"path": "/remote/artifacts/shot.png"}},
                            "files": [remote_file],
                        }
                    )
                    client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

                    result = client.browser_proxy(method="GET", path="/snapshot")
                    self.assertEqual(result["status"], 200)
                    local_artifact_path = result["result"]["artifact"]["path"]
                    self.assertNotEqual(local_artifact_path, "/remote/artifacts/shot.png")
                    self.assertTrue(Path(local_artifact_path).exists())
                    self.assertEqual(Path(local_artifact_path).read_bytes(), b"png-bytes")
            finally:
                os.chdir(old_cwd)

        local_artifact_path = result["result"]["artifact"]["path"]
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["path"], local_artifact_path)
        self.assertEqual(result["files"][0]["source_path"], "/remote/artifacts/shot.png")
        self.assertEqual(result["files"][0]["mime_type"], "image/png")

    def test_http_client_does_not_read_local_paths_from_remote_result(self) -> None:
        with _ProxyHttpServer() as server:
            server.enqueue(body={"ok": True, "artifact": {"path": "/tmp/remote-only.png"}})
            client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

            result = client.browser_proxy(method="GET", path="/snapshot")

        self.assertEqual(result["status"], 200)
        self.assertEqual(result["result"]["artifact"]["path"], "/tmp/remote-only.png")
        self.assertEqual(result["files"], [])

    def test_http_client_rewrites_nested_remote_proxy_paths_after_persisting_files(self) -> None:
        remote_file = {
            "path": "/remote/exports/report.csv",
            "base64": "YSxiCjEsMg==",
            "mimeType": "text/csv",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with _ProxyHttpServer() as server:
                    server.enqueue(
                        body={
                            "status": 200,
                            "result": {
                                "ok": True,
                                "download": {"path": "/remote/exports/report.csv"},
                                "imagePath": "/remote/exports/report.csv",
                            },
                            "files": [remote_file],
                        }
                    )
                    client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

                    result = client.browser_proxy(method="GET", path="/download")
                    rewritten_path = result["result"]["download"]["path"]
                    self.assertTrue(Path(rewritten_path).exists())
                    self.assertEqual(Path(rewritten_path).read_bytes(), b"a,b\n1,2")
            finally:
                os.chdir(old_cwd)

        rewritten_path = result["result"]["download"]["path"]
        self.assertEqual(result["result"]["imagePath"], rewritten_path)

    def test_http_client_fetches_remote_artifact_by_path_when_files_payload_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with _ProxyHttpServer() as server:
                    server.add_artifact(
                        path="/remote/traces/session.zip",
                        content=b"trace-bytes",
                        mime_type="application/zip",
                    )
                    server.enqueue(
                        body={
                            "status": 200,
                            "result": {
                                "ok": True,
                                "artifact": {"path": "/remote/traces/session.zip"},
                            },
                        }
                    )
                    client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

                    result = client.browser_proxy(method="GET", path="/trace/stop")
                    local_path = result["result"]["artifact"]["path"]
                    self.assertTrue(Path(local_path).exists())
                    self.assertEqual(Path(local_path).read_bytes(), b"trace-bytes")
            finally:
                os.chdir(old_cwd)

        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["source_path"], "/remote/traces/session.zip")
        self.assertEqual(result["files"][0]["mime_type"], "application/zip")

    def test_http_client_fetches_same_origin_artifact_by_url_when_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with _ProxyHttpServer() as server:
                    artifact_url = f"{server.base_url}/artifact?path=%2Fremote%2Fcaptures%2Fpage.png"
                    server.add_artifact(
                        path="/remote/captures/page.png",
                        content=b"page-bytes",
                        mime_type="image/png",
                    )
                    server.enqueue(
                        body={
                            "status": 200,
                            "result": {
                                "ok": True,
                                "artifact": {
                                    "kind": "screenshot",
                                    "url": artifact_url,
                                },
                            },
                        }
                    )
                    client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

                    result = client.browser_proxy(method="GET", path="/screenshot")
                    local_path = result["result"]["artifact"]["path"]
                    self.assertTrue(Path(local_path).exists())
                    self.assertEqual(Path(local_path).read_bytes(), b"page-bytes")
            finally:
                os.chdir(old_cwd)

        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["source_url"], artifact_url)
        self.assertEqual(result["files"][0]["mime_type"], "image/png")

    def test_http_client_ignores_off_origin_artifact_url(self) -> None:
        with _ProxyHttpServer() as server:
            server.enqueue(
                body={
                    "status": 200,
                    "result": {
                        "ok": True,
                        "artifact": {
                            "kind": "screenshot",
                            "url": "https://example.com/artifact?path=%2Fremote%2Fcaptures%2Fpage.png",
                        },
                    },
                }
            )
            client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

            result = client.browser_proxy(method="GET", path="/screenshot")

        self.assertEqual(result["status"], 200)
        self.assertEqual(result["files"], [])
        self.assertNotIn("path", result["result"]["artifact"])

    def test_http_client_rejects_invalid_remote_files_payload(self) -> None:
        with _ProxyHttpServer() as server:
            server.enqueue(body={"status": 200, "result": {"ok": True}, "files": [{"path": "/bad.bin"}]})
            client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

            with self.assertRaisesRegex(HttpBrowserProxyError, "requires path and base64"):
                client.browser_proxy(method="GET", path="/snapshot")

    def test_http_client_rejects_oversized_remote_file(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        oversized = "eHh4eHh4eHg="
        with _ProxyHttpServer() as server:
            server.enqueue(
                body={
                    "status": 200,
                    "result": {"ok": True},
                    "files": [{"path": "/big.bin", "base64": oversized}],
                }
            )
            client = HttpBrowserProxyClient(
                base_url=server.base_url,
                inject_loopback_auth=False,
                config=BrowserAutomationConfig(proxy_max_file_bytes=4),
            )

            with self.assertRaisesRegex(HttpBrowserProxyError, "exceeds 4 bytes"):
                client.browser_proxy(method="GET", path="/snapshot")

    def test_http_client_raises_on_http_error(self) -> None:
        with _ProxyHttpServer() as server:
            server.enqueue(status=403, body={"ok": False, "error": "forbidden"})
            client = HttpBrowserProxyClient(base_url=server.base_url, inject_loopback_auth=False)

            with self.assertRaisesRegex(HttpBrowserProxyError, "forbidden"):
                client.browser_proxy(method="GET", path="/profiles")

    def test_create_browser_proxy_transport_uses_http_mode(self) -> None:
        from shared.web_automation.config import BrowserAutomationConfig

        transport = create_browser_proxy_transport(
            config=BrowserAutomationConfig(
                proxy_transport="http",
                proxy_base_url="http://127.0.0.1:8787",
            )
        )

        self.assertIsInstance(transport, HttpBrowserProxyTransport)

    def test_client_talks_to_real_app_server_subprocess(self) -> None:
        repo_root = ROOT
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "PYTHONPATH": str(repo_root),
                "AGENTHUB_BROWSER_MODE": "synthetic",
            }
            client = AppServerBrowserProxyClient(cwd=temp_dir, env=env)
            try:
                profiles = client.browser_proxy(method="GET", path="/profiles")
                self.assertEqual(profiles["status"], 200)
                self.assertIn("result", profiles)
                profile_names = {item["name"] for item in profiles["result"].get("profiles", [])}
                self.assertIn("openclaw", profile_names)

                created = client.browser_proxy(
                    method="POST",
                    path="/profiles/create",
                    body={"name": "review", "driver": "openclaw"},
                )
                self.assertEqual(created["status"], 200)
                self.assertEqual(created["result"]["profile"], "review")

                started = client.browser_proxy(method="POST", path="/start", body={"profile": "openclaw"})
                self.assertEqual(started["status"], 200)
                self.assertTrue(started["result"]["ok"])

                opened = client.browser_proxy(
                    method="POST",
                    path="/tabs/open",
                    body={"profile": "openclaw", "url": "https://example.com/proxy-e2e"},
                )
                self.assertEqual(opened["status"], 200)
                self.assertEqual(opened["result"]["url"], "https://example.com/proxy-e2e")

                status = client.browser_proxy(method="GET", path="/", query={"profile": "openclaw"})
                self.assertEqual(status["status"], 200)
                self.assertTrue(status["result"]["running"])
                self.assertEqual(status["result"]["profile"], "openclaw")
                self.assertEqual(status["result"]["tabs"], 1)

                review_profiles = client.browser_proxy(method="GET", path="/profiles")
                review_names = {item["name"] for item in review_profiles["result"].get("profiles", [])}
                self.assertIn("review", review_names)

                reset = client.browser_proxy(method="POST", path="/reset-profile", body={"profile": "openclaw"})
                self.assertEqual(reset["status"], 200)
                self.assertTrue(reset["result"]["ok"])
                self.assertEqual(reset["result"]["profile"], "openclaw")

                deleted = client.browser_proxy(method="DELETE", path="/profiles/review")
                self.assertEqual(deleted["status"], 200)
                self.assertTrue(deleted["result"]["deleted"])
            finally:
                client.close()
