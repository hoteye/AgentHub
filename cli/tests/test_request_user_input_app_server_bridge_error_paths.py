import json
import threading
import unittest

from cli.agent_cli.app_server import main as app_server_main
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli.tools import ToolRegistry
from cli.tests.test_app_server_protocol import _AppServerAgent, _AsyncInputPipe, _ObservedOutputBuffer


class RequestUserInputAppServerBridgeErrorPathsTest(unittest.TestCase):
    @staticmethod
    def _runtime() -> AgentCliRuntime:
        runtime = AgentCliRuntime(
            agent=_AppServerAgent(),
            tools=ToolRegistry(),
            runtime_policy=RuntimePolicy.normalized(approval_policy="never"),
        )
        runtime.collaboration_mode = "plan"
        # Ensure app-server session runtime installs bridge handler path.
        runtime.request_user_input_handler = None
        return runtime

    @staticmethod
    def _request_prompt() -> str:
        return (
            '/request_user_input \'{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
            '"options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]}]}\''
        )

    def test_bridge_non_object_result_is_cancelled_and_emits_bridge_request(self) -> None:
        runtime = self._runtime()
        stdin = _AsyncInputPipe()
        stdout = _ObservedOutputBuffer()
        server_thread = threading.Thread(
            target=app_server_main,
            kwargs={"runtime": runtime, "stdin": stdin, "stdout": stdout},
            daemon=True,
        )
        server_thread.start()
        stdin.push_json({"id": "init", "method": "initialize", "params": {}})
        stdin.push_json({"method": "initialized", "params": {}})
        stdin.push_json(
            {
                "id": "run-malformed-bridge",
                "method": "session/start",
                "params": {"prompt": self._request_prompt(), "stream": True},
            }
        )

        start_result = stdout.wait_for_line(lambda line: line.get("id") == "run-malformed-bridge")
        self.assertTrue(start_result["result"]["accepted"])
        server_request = stdout.wait_for_line(lambda line: line.get("method") == "item/tool/requestUserInput")
        request_id = server_request["id"]
        self.assertEqual(server_request["params"]["threadId"], "thread_run-malformed-bridge")
        self.assertEqual(server_request["params"]["questions"][0]["id"], "confirm_path")

        stdin.push_json({"id": request_id, "result": ["bad-payload"]})
        resolved = stdout.wait_for_line(
            lambda line: line.get("method") == "serverRequest/resolved"
            and line.get("params", {}).get("requestId") == request_id
        )
        completed = stdout.wait_for_line(
            lambda line: line.get("method") == "session/completed"
            and line.get("params", {}).get("requestId") == "run-malformed-bridge"
        )
        stdin.close()
        server_thread.join(timeout=2)

        self.assertFalse(server_thread.is_alive())
        self.assertEqual(resolved["params"]["threadId"], "thread_run-malformed-bridge")
        response = completed["params"]["response"]
        self.assertEqual(response["tool_events"][-1]["name"], "request_user_input")
        self.assertFalse(response["tool_events"][-1]["ok"])
        self.assertEqual(response["assistant_text"], "request_user_input was cancelled before receiving a response")
        completed_item = next(
            event
            for event in response["turn_events"]
            if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "mcp_tool_call"
        )
        self.assertEqual(completed_item["item"]["tool"], "request_user_input")
        self.assertEqual(str(completed_item["item"].get("status") or "").lower(), "failed")
        self.assertIn(
            "cancelled before receiving a response",
            str(((completed_item["item"].get("error") or {}).get("message") or "")).lower(),
        )

    def test_bridge_client_error_then_follow_up_run_succeeds(self) -> None:
        runtime = self._runtime()
        stdin = _AsyncInputPipe()
        stdout = _ObservedOutputBuffer()
        server_thread = threading.Thread(
            target=app_server_main,
            kwargs={"runtime": runtime, "stdin": stdin, "stdout": stdout},
            daemon=True,
        )
        server_thread.start()
        stdin.push_json({"id": "init", "method": "initialize", "params": {}})
        stdin.push_json({"method": "initialized", "params": {}})

        stdin.push_json(
            {
                "id": "run-bridge-error",
                "method": "session/start",
                "params": {"prompt": self._request_prompt(), "stream": True},
            }
        )
        first_start = stdout.wait_for_line(lambda line: line.get("id") == "run-bridge-error")
        self.assertTrue(first_start["result"]["accepted"])
        req1 = stdout.wait_for_line(lambda line: line.get("method") == "item/tool/requestUserInput")
        req1_id = req1["id"]
        stdin.push_json({"id": req1_id, "error": {"code": -32042, "message": "operator cancelled"}})
        stdout.wait_for_line(
            lambda line: line.get("method") == "serverRequest/resolved"
            and line.get("params", {}).get("requestId") == req1_id
        )
        completed_first = stdout.wait_for_line(
            lambda line: line.get("method") == "session/completed"
            and line.get("params", {}).get("requestId") == "run-bridge-error"
        )
        first_response = completed_first["params"]["response"]
        self.assertFalse(first_response["tool_events"][-1]["ok"])
        self.assertEqual(first_response["assistant_text"], "request_user_input was cancelled before receiving a response")

        stdin.push_json(
            {
                "id": "run-bridge-follow-up",
                "method": "session/start",
                "params": {"prompt": self._request_prompt(), "stream": True},
            }
        )
        second_start = stdout.wait_for_line(lambda line: line.get("id") == "run-bridge-follow-up")
        self.assertTrue(second_start["result"]["accepted"])
        req2 = stdout.wait_for_line(
            lambda line: line.get("method") == "item/tool/requestUserInput"
            and line.get("params", {}).get("threadId") == "thread_run-bridge-follow-up"
        )
        req2_id = req2["id"]
        stdin.push_json({"id": req2_id, "result": {"answers": {"confirm_path": {"answers": ["yes"]}}}})
        stdout.wait_for_line(
            lambda line: line.get("method") == "serverRequest/resolved"
            and line.get("params", {}).get("requestId") == req2_id
        )
        completed_second = stdout.wait_for_line(
            lambda line: line.get("method") == "session/completed"
            and line.get("params", {}).get("requestId") == "run-bridge-follow-up"
        )
        stdin.close()
        server_thread.join(timeout=2)

        self.assertFalse(server_thread.is_alive())
        second_response = completed_second["params"]["response"]
        self.assertEqual(second_response["tool_events"][-1]["name"], "request_user_input")
        self.assertTrue(second_response["tool_events"][-1]["ok"])
        normalized = json.loads(second_response["assistant_text"])
        self.assertEqual(normalized["answers"]["confirm_path"]["answers"], ["yes"])
