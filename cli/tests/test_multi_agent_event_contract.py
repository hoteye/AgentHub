from __future__ import annotations

import io
import json

from cli.agent_cli.app_server import AgentCliAppServer
from workers.actions import ActionResult


class _Runtime:
    def __init__(self) -> None:
        self.agent = type(
            "Agent",
            (),
            {
                "provider_status": staticmethod(
                    lambda: {
                        "platform_family": "linux",
                        "platform_os": "linux",
                        "shell_kind": "bash",
                        "provider_label": "test-provider",
                    }
                )
            },
        )()

    @staticmethod
    def has_active_run() -> bool:
        return False


class _CapturingWorker:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def execute(self, request):
        payload = dict(request) if isinstance(request, dict) else request.to_dict()
        self.requests.append(payload)
        return ActionResult(
            ok=True,
            action=str(payload.get("action") or ""),
            summary="ok",
            output={"echo": True},
            request_id=str(payload.get("request_id") or "") or None,
            correlation_id=str(payload.get("correlation_id") or "") or None,
            run_id=str(payload.get("run_id") or "") or None,
            agent_id=str(payload.get("agent_id") or "") or None,
        )


def _server(worker: _CapturingWorker) -> tuple[AgentCliAppServer, io.StringIO]:
    stdout = io.StringIO()
    server = AgentCliAppServer(runtime=_Runtime(), action_worker=worker, stdin=io.StringIO(), stdout=stdout)
    server.state.initialized = True
    server.state.initialized_notification_received = True
    return server, stdout


def test_action_execute_projects_run_and_agent_ids_from_flat_params() -> None:
    worker = _CapturingWorker()
    server, stdout = _server(worker)

    server._handle_line(
        json.dumps(
            {
                "id": "action-flat",
                "method": "action/execute",
                "params": {
                    "action": "noop",
                    "parameters": {"mode": "dry_run"},
                    "requestId": "req-1",
                    "runId": "run-1",
                    "agentId": "agent-1",
                },
            }
        )
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    result = next(item for item in lines if item.get("id") == "action-flat")

    assert worker.requests[0]["request_id"] == "req-1"
    assert worker.requests[0]["run_id"] == "run-1"
    assert worker.requests[0]["agent_id"] == "agent-1"
    assert result["result"]["actionResult"]["request_id"] == "req-1"
    assert result["result"]["actionResult"]["run_id"] == "run-1"
    assert result["result"]["actionResult"]["agent_id"] == "agent-1"


def test_action_execute_normalizes_request_payload_run_and_agent_ids() -> None:
    worker = _CapturingWorker()
    server, stdout = _server(worker)

    server._handle_line(
        json.dumps(
            {
                "id": "action-request-payload",
                "method": "action/execute",
                "params": {
                    "request": {
                        "action": "noop",
                        "parameters": {"mode": "dry_run"},
                        "requestId": "req-2",
                        "runId": "run-2",
                        "agentId": "agent-2",
                    }
                },
            }
        )
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    result = next(item for item in lines if item.get("id") == "action-request-payload")

    assert worker.requests[0]["request_id"] == "req-2"
    assert worker.requests[0]["run_id"] == "run-2"
    assert worker.requests[0]["agent_id"] == "agent-2"
    assert result["result"]["actionResult"]["request_id"] == "req-2"
    assert result["result"]["actionResult"]["run_id"] == "run-2"
    assert result["result"]["actionResult"]["agent_id"] == "agent-2"
