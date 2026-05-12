import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.integrations import HttpClient
from workers.actions.protocol import ActionError, ActionRequest
from workers.actions.worker import ControlledActionWorker

class ControlledActionWorkerTest(unittest.TestCase):
    def test_noop_action_returns_payload(self) -> None:
        worker = ControlledActionWorker()

        result = worker.execute(
            ActionRequest(
                action="noop",
                parameters={"mode": "dry_run"},
                request_id="req-1",
                correlation_id="corr-1",
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "noop")
        self.assertEqual(result.output["parameters"]["mode"], "dry_run")
        self.assertEqual(result.request_id, "req-1")

    def test_write_json_file_stays_within_allowed_root(self) -> None:
        worker = ControlledActionWorker()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = worker.execute(
                {
                    "action": "write_json_file",
                    "parameters": {
                        "allowed_root": str(root),
                        "path": "audit/result.json",
                        "data": {"ok": True, "stage": "approval"},
                    },
                }
            )

            output_path = Path(result.output["path"])
            self.assertTrue(output_path.exists())
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["stage"], "approval")

    def test_append_jsonl_records(self) -> None:
        worker = ControlledActionWorker()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worker.execute(
                {
                    "action": "append_jsonl",
                    "parameters": {
                        "allowed_root": str(root),
                        "path": "audit/events.jsonl",
                        "record": {"stage": "ingress"},
                    },
                }
            )
            worker.execute(
                {
                    "action": "append_jsonl",
                    "parameters": {
                        "allowed_root": str(root),
                        "path": "audit/events.jsonl",
                        "record": {"stage": "approved"},
                    },
                }
            )

            lines = (root / "audit" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[1])["stage"], "approved")

    def test_path_escape_is_rejected(self) -> None:
        worker = ControlledActionWorker()
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ActionError):
                worker.execute(
                    {
                        "action": "write_json_file",
                        "parameters": {
                            "allowed_root": tmpdir,
                            "path": "../outside.json",
                            "data": {"bad": True},
                        },
                    }
                )

    def test_http_request_action_calls_allowlisted_host(self) -> None:
        captured: dict[str, object] = {}

        class _FakeResponse:
            def __init__(self, *, url: str, status_code: int, body: str) -> None:
                self._url = url
                self._status_code = status_code
                self._body = body.encode("utf-8")
                self.headers = {"Content-Type": "application/json; charset=utf-8"}

            def read(self) -> bytes:
                return self._body

            def getcode(self) -> int:
                return self._status_code

            def geturl(self) -> str:
                return self._url

        def _open(request, *, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = dict(request.header_items())
            captured["body"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return _FakeResponse(
                url=request.full_url,
                status_code=200,
                body=json.dumps({"ok": True, "ticket": "INC-1"}),
            )

        worker = ControlledActionWorker(http_client=HttpClient(open_url=_open))
        with patch.dict(os.environ, {"PM_GITHUB_TOKEN": "secret"}, clear=False):
            result = worker.execute(
                {
                    "action": "http_request",
                    "parameters": {
                        "method": "POST",
                        "url": "https://api.example.com/tickets",
                        "allowed_hosts": ["api.example.com"],
                        "headers": {"X-Test": "1"},
                        "auth": {"type": "bearer_env", "token_env": "PM_GITHUB_TOKEN"},
                        "query": {"expand": "comments"},
                        "json_body": {"title": "hello"},
                        "timeout_seconds": 3,
                    },
                    "request_id": "req-1",
                }
            )

        self.assertTrue(result.ok)
        self.assertEqual(captured["url"], "https://api.example.com/tickets?expand=comments")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(json.loads(str(captured["body"])), {"title": "hello"})
        self.assertEqual(result.output["status_code"], 200)
        self.assertEqual(result.output["json_data"]["ticket"], "INC-1")
        self.assertEqual(result.output["request_headers"]["Authorization"], "***")

    def test_http_request_auth_requires_env_value(self) -> None:
        worker = ControlledActionWorker()

        with self.assertRaises(ActionError):
            worker.execute(
                {
                    "action": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": "https://api.example.com/tickets",
                        "allowed_hosts": ["api.example.com"],
                        "auth": {"type": "bearer_env", "token_env": "MISSING_GITHUB_TOKEN"},
                    },
                }
            )

    def test_http_request_rejects_non_allowlisted_host(self) -> None:
        worker = ControlledActionWorker()

        with self.assertRaises(ActionError):
            worker.execute(
                {
                    "action": "http_request",
                    "parameters": {
                        "method": "GET",
                        "url": "https://blocked.example.com/tickets",
                        "allowed_hosts": ["api.example.com"],
                    },
                }
            )
