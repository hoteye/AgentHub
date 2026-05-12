from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
import time
import urllib.request
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from claude_request_capture_proxy import create_capture_proxy_server
from claude_request_capture_proxy import load_claude_home_config
from claude_request_capture_proxy import resolve_upstream_base_url
from claude_request_capture_proxy import write_claude_proxy_settings


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class _UpstreamHandler(http.server.BaseHTTPRequestHandler):
    last_request: dict[str, object] = {}

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else b""
        type(self).last_request = {
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body_text": body.decode("utf-8"),
        }
        encoded = json.dumps({"ok": True, "path": self.path}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return


def _start_upstream() -> tuple[_ThreadedHTTPServer, str]:
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _start_proxy(tmp_path: Path, upstream_base_url: str):
    server = create_capture_proxy_server(
        host="127.0.0.1",
        port=0,
        upstream_base_url=upstream_base_url,
        out_dir=tmp_path / "capture",
        response_preview_bytes=256,
        upstream_timeout_seconds=5.0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _wait_for_path(path: Path, timeout_seconds: float = 2.0) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists():
            return path
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {path}")


def test_proxy_forwards_request_and_persists_raw_capture(tmp_path: Path) -> None:
    upstream_server, upstream_base = _start_upstream()
    proxy_server, proxy_base = _start_proxy(tmp_path, upstream_base_url=f"{upstream_base}/relay")
    try:
        payload = {"model": "claude-sonnet-4-6", "system": "hello", "messages": []}
        request = urllib.request.Request(
            f"{proxy_base}/v1/messages?debug=1",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-test-header": "abc123",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5.0) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert body == {"ok": True, "path": "/relay/v1/messages?debug=1"}
        assert _UpstreamHandler.last_request["path"] == "/relay/v1/messages?debug=1"
        assert _UpstreamHandler.last_request["body_text"] == json.dumps(payload, ensure_ascii=False)

        request_meta = json.loads(
            _wait_for_path(tmp_path / "capture" / "requests" / "000001.json").read_text(encoding="utf-8")
        )
        response_meta = json.loads(
            _wait_for_path(tmp_path / "capture" / "responses" / "000001.json").read_text(encoding="utf-8")
        )
        request_body = (tmp_path / "capture" / "requests" / "000001.body.bin").read_bytes()
        events = (tmp_path / "capture" / "events.jsonl").read_text(encoding="utf-8").splitlines()

        assert request_meta["method"] == "POST"
        assert request_meta["path"] == "/v1/messages"
        assert request_meta["query"] == "debug=1"
        assert request_meta["body_json"] == payload
        assert request_body.decode("utf-8") == json.dumps(payload, ensure_ascii=False)
        assert any(item["name"].lower() == "x-test-header" and item["value"] == "abc123" for item in request_meta["headers"])
        assert response_meta["status"] == 200
        assert json.loads(response_meta["preview_utf8"]) == {"ok": True, "path": "/relay/v1/messages?debug=1"}
        assert len(events) == 2
    finally:
        proxy_server.shutdown()
        proxy_server.server_close()
        upstream_server.shutdown()
        upstream_server.server_close()


def test_resolve_upstream_base_url_uses_current_claude_home_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://gaccode.com/claudecode",
                    "_ANTHROPIC_API_KEY": "sk-hidden",
                },
                "skipDangerousModePermissionPrompt": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (claude_dir / "config.json").write_text(
        json.dumps({"primaryApiKey": "sk-config"}, ensure_ascii=False),
        encoding="utf-8",
    )

    config = load_claude_home_config(home_dir=home)
    upstream, source, current = resolve_upstream_base_url(explicit_upstream_base_url="", home_dir=home)

    assert config is not None
    assert config.api_key == "sk-hidden"
    assert config.base_url == "https://gaccode.com/claudecode"
    assert upstream == "https://gaccode.com/claudecode"
    assert source == "claude_home"
    assert current is not None
    assert current.settings_path == claude_dir / "settings.json"


def test_write_claude_proxy_settings_preserves_existing_env_and_repoints_base_url(tmp_path: Path) -> None:
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://gaccode.com/claudecode",
                    "CUSTOM_FLAG": "1",
                },
                "skipDangerousModePermissionPrompt": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (claude_dir / "config.json").write_text(
        json.dumps({"primaryApiKey": "sk-config"}, ensure_ascii=False),
        encoding="utf-8",
    )

    output_path = tmp_path / "claude_proxy_settings.json"
    result = write_claude_proxy_settings(
        output_path=output_path,
        proxy_base_url="http://127.0.0.1:8787",
        home_dir=home,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    env = dict(payload.get("env") or {})

    assert result["resolved_source_base_url"] == "https://gaccode.com/claudecode"
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8787"
    assert env["ANTHROPIC_API_KEY"] == "sk-config"
    assert env["CUSTOM_FLAG"] == "1"
    assert payload["skipDangerousModePermissionPrompt"] is True
