import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.integrations import HttpClient, HttpClientError, HttpRequest, OpenAPIClient, OperationSpec, RetryPolicy
from shared.integrations.auth import (
    apply_api_key_headers,
    build_basic_auth_header,
    build_bearer_auth_headers,
    redact_headers,
)
from shared.integrations.schemas import SchemaValidationError, coerce_str_mapping, pick_keys, require_keys

class _FakeResponse:
    def __init__(self, *, url: str, status_code: int, body: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._status_code = status_code
        self._body = body.encode("utf-8")
        self.headers = headers or {"Content-Type": "application/json; charset=utf-8"}

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self._status_code

    def geturl(self) -> str:
        return self._url

class HttpClientTest(unittest.TestCase):
    def test_request_json_encodes_body_and_query(self) -> None:
        captured: dict[str, object] = {}

        def _open(request, *, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = dict(request.header_items())
            captured["body"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return _FakeResponse(
                url=request.full_url,
                status_code=200,
                body=json.dumps({"ok": True, "echo": "done"}),
            )

        client = HttpClient(default_headers={"User-Agent": "AgentHub-Test"}, open_url=_open)
        response = client.request_json(
            "POST",
            "https://api.example.com/jobs",
            query={"status": "open"},
            json_body={"name": "nightly"},
            headers={"X-Trace-Id": "abc123"},
        )

        self.assertEqual(captured["url"], "https://api.example.com/jobs?status=open")
        self.assertEqual(captured["method"], "POST")
        self.assertIn(("User-agent", "AgentHub-Test"), captured["headers"].items())
        self.assertIn(("X-trace-id", "abc123"), captured["headers"].items())
        self.assertEqual(json.loads(str(captured["body"])), {"name": "nightly"})
        self.assertTrue(response.ok)
        self.assertEqual(response.json_data["echo"], "done")

    def test_request_retries_retryable_status(self) -> None:
        calls = {"count": 0}

        def _open(request, *, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                return _FakeResponse(
                    url=request.full_url,
                    status_code=503,
                    body=json.dumps({"ok": False}),
                )
            return _FakeResponse(
                url=request.full_url,
                status_code=200,
                body=json.dumps({"ok": True}),
            )

        client = HttpClient(
            open_url=_open,
            retry_policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0.0, retry_statuses=(503,)),
        )
        response = client.request(HttpRequest(method="GET", url="https://api.example.com/status"))

        self.assertEqual(calls["count"], 2)
        self.assertEqual(response.status_code, 200)

    def test_request_raises_error_for_unexpected_status(self) -> None:
        def _open(request, *, timeout):
            return _FakeResponse(
                url=request.full_url,
                status_code=404,
                body=json.dumps({"error": "missing"}),
            )

        client = HttpClient(open_url=_open, retry_policy=RetryPolicy(max_attempts=1))

        with self.assertRaises(HttpClientError) as ctx:
            client.request(HttpRequest(method="GET", url="https://api.example.com/missing"))

        self.assertEqual(ctx.exception.response.status_code, 404)

    def test_openapi_client_renders_path_params(self) -> None:
        captured: dict[str, object] = {}

        def _open(request, *, timeout):
            captured["url"] = request.full_url
            return _FakeResponse(
                url=request.full_url,
                status_code=200,
                body=json.dumps({"ticket_id": "INC-001"}),
            )

        client = OpenAPIClient("https://itsm.example.com/api", http_client=HttpClient(open_url=_open))
        operation = OperationSpec(
            name="ticket_get",
            method="GET",
            path_template="/tickets/{ticket_id}",
            expected_statuses=(200,),
        )
        response = client.call(operation, path_params={"ticket_id": "INC-001"}, query={"expand": "comments"})

        self.assertEqual(captured["url"], "https://itsm.example.com/api/tickets/INC-001?expand=comments")
        self.assertEqual(response.json_data["ticket_id"], "INC-001")

    def test_auth_and_schema_helpers(self) -> None:
        headers = build_bearer_auth_headers("secret-token", headers={"X-Trace-Id": "trace-1"})
        headers = apply_api_key_headers("key-123", headers=headers)

        self.assertTrue(build_basic_auth_header("alice", "pw").startswith("Basic "))
        self.assertEqual(headers["Authorization"], "Bearer secret-token")
        self.assertEqual(headers["X-API-Key"], "key-123")
        self.assertEqual(redact_headers(headers)["Authorization"], "***")
        self.assertEqual(require_keys({"a": 1, "b": 2}, ("a", "b")), {"a": 1, "b": 2})
        self.assertEqual(pick_keys({"a": 1, "b": 2}, ("b",)), {"b": 2})
        self.assertEqual(coerce_str_mapping({"x": 1}), {"x": "1"})

        with self.assertRaises(SchemaValidationError):
            require_keys({"a": 1}, ("a", "b"))
