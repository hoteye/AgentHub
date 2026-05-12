from __future__ import annotations

import http.server
import importlib.util
import json
import socketserver
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "cli" / "scripts" / "previous_response_id_rejection_live_harness.py"
SPEC = importlib.util.spec_from_file_location("previous_response_id_rejection_live_harness", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


class _UpstreamHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else b""
        type(self).requests.append(
            {
                "path": self.path,
                "body_json": json.loads(body.decode("utf-8")) if body else {},
            }
        )
        encoded = json.dumps({"ok": True, "path": self.path}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return


def _start_upstream() -> tuple[_ThreadedHTTPServer, str]:
    _UpstreamHandler.requests = []
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_analyze_observed_requests_recognizes_expected_rejection_and_replay_flow() -> None:
    requests = [
        MODULE.ObservedRequest(
            sequence=1,
            method="POST",
            path="/responses",
            query="",
            previous_response_id="",
            input_types=["message:user"],
            tool_names=["lookup_constant"],
            injected_rejection=False,
            forwarded_url="http://upstream/v1/responses",
        ),
        MODULE.ObservedRequest(
            sequence=2,
            method="POST",
            path="/responses",
            query="",
            previous_response_id="resp_1",
            input_types=["function_call_output"],
            tool_names=["lookup_constant"],
            injected_rejection=True,
            forwarded_url="http://upstream/v1/responses",
        ),
        MODULE.ObservedRequest(
            sequence=3,
            method="POST",
            path="/responses",
            query="",
            previous_response_id="",
            input_types=["message:user", "function_call", "function_call_output"],
            tool_names=["lookup_constant"],
            injected_rejection=False,
            forwarded_url="http://upstream/v1/responses",
        ),
    ]

    analysis = MODULE.analyze_observed_requests(requests)

    assert analysis["verdict"] == "pass"
    assert analysis["reasons"] == []
    assert analysis["rejected_request"]["previous_response_id"] == "resp_1"
    assert analysis["full_replay_request"]["input_types"] == [
        "message:user",
        "function_call",
        "function_call_output",
    ]
    assert analysis["post_rejection_request"]["previous_response_id"] == ""


def test_analyze_observed_requests_rejects_cursor_bearing_replay_after_rejection() -> None:
    requests = [
        MODULE.ObservedRequest(
            sequence=1,
            method="POST",
            path="/responses",
            query="",
            previous_response_id="",
            input_types=["message:user"],
            tool_names=["lookup_constant"],
            injected_rejection=False,
            forwarded_url="http://upstream/v1/responses",
        ),
        MODULE.ObservedRequest(
            sequence=2,
            method="POST",
            path="/responses",
            query="",
            previous_response_id="resp_1",
            input_types=["function_call_output"],
            tool_names=["lookup_constant"],
            injected_rejection=True,
            forwarded_url="http://upstream/v1/responses",
        ),
        MODULE.ObservedRequest(
            sequence=3,
            method="POST",
            path="/responses",
            query="",
            previous_response_id="resp_1",
            input_types=["message:user", "function_call", "function_call_output"],
            tool_names=["lookup_constant"],
            injected_rejection=False,
            forwarded_url="http://upstream/v1/responses",
        ),
        MODULE.ObservedRequest(
            sequence=4,
            method="POST",
            path="/responses",
            query="",
            previous_response_id="",
            input_types=["message:user", "function_call", "function_call_output"],
            tool_names=["lookup_constant"],
            injected_rejection=False,
            forwarded_url="http://upstream/v1/responses",
        ),
    ]

    analysis = MODULE.analyze_observed_requests(requests)

    assert analysis["verdict"] == "fail"
    assert "post_rejection_request_unexpected_previous_response_id" in analysis["reasons"]
    assert "missing_direct_full_replay_without_previous_response_id" in analysis["reasons"]


def test_proxy_injects_previous_response_id_rejection_only_once_and_then_forwards(tmp_path: Path) -> None:
    upstream_server, upstream_base = _start_upstream()
    proxy_server = MODULE.create_previous_response_id_proxy_server(
        host="127.0.0.1",
        port=0,
        upstream_base_url=f"{upstream_base}/relay",
        out_dir=tmp_path / "capture",
        upstream_timeout_seconds=5.0,
    )
    proxy_thread = threading.Thread(target=proxy_server.serve_forever, daemon=True)
    proxy_thread.start()
    host, port = proxy_server.server_address
    proxy_base = f"http://{host}:{port}"
    try:
        def _post(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
            request = urllib.request.Request(
                f"{proxy_base}/v1/responses",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer sk-test"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=5.0) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read().decode("utf-8"))

        status1, body1 = _post({"model": "gpt-5.4", "input": [{"role": "user", "content": "hi"}]})
        status2, body2 = _post({"model": "gpt-5.4", "previous_response_id": "resp_1", "input": [{"type": "function_call_output"}]})
        status3, body3 = _post({"model": "gpt-5.4", "previous_response_id": "resp_1", "input": [{"type": "function_call_output"}]})

        assert status1 == 200
        assert body1 == {"ok": True, "path": "/relay/v1/responses"}
        assert status2 == 400
        assert body2["error"]["param"] == "previous_response_id"
        assert status3 == 200
        assert body3 == {"ok": True, "path": "/relay/v1/responses"}
        assert len(_UpstreamHandler.requests) == 2
        assert [item.injected_rejection for item in proxy_server.observed_requests] == [False, True, False]
        assert proxy_server.observed_requests[1].previous_response_id == "resp_1"
    finally:
        proxy_server.shutdown()
        proxy_server.server_close()
        proxy_thread.join(timeout=5.0)
        upstream_server.shutdown()
        upstream_server.server_close()
