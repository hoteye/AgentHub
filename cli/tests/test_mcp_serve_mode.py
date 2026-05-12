from __future__ import annotations

import io
import json
from typing import Any

from cli.agent_cli.mcp.serve import McpServePolicy, McpServeServer, main as mcp_serve_main
from cli.agent_cli.models import CommandExecutionResult, ToolEvent


class _ToolsStub:
    def list_dir_result(
        self,
        *,
        dir_path: str | None = None,
        offset: int = 1,
        limit: int = 25,
        depth: int = 2,
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            assistant_text=f"listed path={dir_path or '.'} offset={offset} limit={limit} depth={depth}",
            tool_events=[
                ToolEvent(
                    name="list_dir",
                    ok=True,
                    summary="list_dir ok",
                    payload={"dir_path": dir_path, "offset": offset, "limit": limit, "depth": depth},
                )
            ],
        )

    def file_read_result(
        self,
        path: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
        max_chars: int | None = None,
    ) -> CommandExecutionResult:
        return CommandExecutionResult(
            assistant_text=f"read path={path} offset={offset} limit={limit} max_chars={max_chars}",
            tool_events=[
                ToolEvent(
                    name="file_read",
                    ok=True,
                    summary="file_read ok",
                    payload={"path": path, "offset": offset, "limit": limit, "max_chars": max_chars},
                )
            ],
        )


class _RuntimeStub:
    def __init__(self) -> None:
        self.tools = _ToolsStub()


class _FailingToolsStub(_ToolsStub):
    def file_read_result(
        self,
        path: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
        max_chars: int | None = None,
    ) -> CommandExecutionResult:
        raise RuntimeError(f"boom:{path}:{offset}:{limit}:{max_chars}")


class _FailingRuntimeStub:
    def __init__(self) -> None:
        self.tools = _FailingToolsStub()


def _request(request_id: str | int | None, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    return payload


def test_mcp_serve_main_starts_server_and_round_trips_tools_list_and_call() -> None:
    runtime = _RuntimeStub()
    input_messages = [
        _request("init", "initialize", {"clientInfo": {"name": "test"}}),
        _request(None, "initialized", {}),
        _request("list", "tools/list", {}),
        _request(
            "call",
            "tools/call",
            {"name": "agenthub.list_dir", "arguments": {"dir_path": ".", "offset": 1, "limit": 5, "depth": 1}},
        ),
    ]
    stdin = io.StringIO("\n".join(json.dumps(item, ensure_ascii=True) for item in input_messages) + "\n")
    stdout = io.StringIO()

    exit_code = mcp_serve_main(["serve"], runtime=runtime, stdin=stdin, stdout=stdout)

    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    responses = [json.loads(line) for line in lines]
    assert exit_code == 0
    assert len(responses) == 3
    assert responses[0]["id"] == "init"
    assert responses[0]["result"]["serverInfo"]["name"] == "agenthub_mcp_server"
    assert responses[1]["id"] == "list"
    tool_names = [item["name"] for item in responses[1]["result"]["tools"]]
    assert "agenthub.list_dir" in tool_names
    assert "agenthub.file_read" in tool_names
    assert responses[2]["id"] == "call"
    call_result = responses[2]["result"]
    assert call_result["isError"] is False
    assert "listed path=." in call_result["content"][0]["text"]
    assert call_result["structuredContent"]["tool_events"][0]["name"] == "list_dir"


def test_tools_call_supports_file_read() -> None:
    server = McpServeServer(runtime=_RuntimeStub())
    _ = server.handle_message(_request("init", "initialize", {}))
    _ = server.handle_message(_request(None, "initialized", {}))

    response = server.handle_message(
        _request(
            "call_file_read",
            "tools/call",
            {"name": "agenthub.file_read", "arguments": {"path": "README.md", "offset": 1, "limit": 10}},
        )
    )

    assert response is not None
    assert response["id"] == "call_file_read"
    result = response["result"]
    assert result["isError"] is False
    assert "read path=README.md" in result["content"][0]["text"]
    assert result["structuredContent"]["tool_events"][0]["name"] == "file_read"


def test_policy_can_hide_tools_and_reject_disallowed_call() -> None:
    server = McpServeServer(
        runtime=_RuntimeStub(),
        policy=McpServePolicy(allowed_tools={"agenthub.file_read"}),
    )
    _ = server.handle_message(_request("init", "initialize", {}))
    _ = server.handle_message(_request(None, "initialized", {}))

    list_response = server.handle_message(_request("list", "tools/list", {}))
    assert list_response is not None
    tool_names = [item["name"] for item in list_response["result"]["tools"]]
    assert tool_names == ["agenthub.file_read"]

    denied = server.handle_message(
        _request(
            "call_denied",
            "tools/call",
            {"name": "agenthub.list_dir", "arguments": {"dir_path": "."}},
        )
    )
    assert denied is not None
    assert denied["id"] == "call_denied"
    assert denied["error"]["code"] == -32602
    assert "tool not allowed" in denied["error"]["data"]["detail"]


def test_tools_list_requires_initialized_notification() -> None:
    server = McpServeServer(runtime=_RuntimeStub())
    _ = server.handle_message(_request("init", "initialize", {}))

    denied = server.handle_message(_request("list_before_init", "tools/list", {}))

    assert denied is not None
    assert denied["id"] == "list_before_init"
    assert denied["error"]["code"] == -32002
    assert denied["error"]["message"] == "Not initialized"


def test_run_stdio_server_reports_parse_error_and_invalid_request_shape() -> None:
    runtime = _RuntimeStub()
    stdin = io.StringIO("{bad json\n42\n")
    stdout = io.StringIO()

    exit_code = mcp_serve_main(["serve"], runtime=runtime, stdin=stdin, stdout=stdout)

    responses = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert exit_code == 0
    assert [item["error"]["code"] for item in responses] == [-32700, -32600]
    assert responses[0]["error"]["message"] == "Parse error"
    assert responses[1]["error"]["message"] == "Invalid Request"


def test_initialize_rejects_non_object_params() -> None:
    server = McpServeServer(runtime=_RuntimeStub())

    denied = server.handle_message({"jsonrpc": "2.0", "id": "bad_params", "method": "initialize", "params": []})

    assert denied is not None
    assert denied["id"] == "bad_params"
    assert denied["error"]["code"] == -32602
    assert denied["error"]["data"]["detail"] == "params must be an object"


def test_tools_call_requires_initialized_notification() -> None:
    server = McpServeServer(runtime=_RuntimeStub())
    _ = server.handle_message(_request("init", "initialize", {}))

    denied = server.handle_message(
        _request("call_before_init", "tools/call", {"name": "agenthub.list_dir", "arguments": {"dir_path": "."}})
    )

    assert denied is not None
    assert denied["id"] == "call_before_init"
    assert denied["error"]["code"] == -32002
    assert denied["error"]["message"] == "Not initialized"


def test_tools_call_rejects_non_object_arguments() -> None:
    server = McpServeServer(runtime=_RuntimeStub())
    _ = server.handle_message(_request("init", "initialize", {}))
    _ = server.handle_message(_request(None, "initialized", {}))

    denied = server.handle_message(
        _request("call_bad_args", "tools/call", {"name": "agenthub.file_read", "arguments": ["README.md"]})
    )

    assert denied is not None
    assert denied["id"] == "call_bad_args"
    assert denied["error"]["code"] == -32602
    assert denied["error"]["data"]["detail"] == "params.arguments must be an object"


def test_tools_call_handler_exception_maps_to_tool_call_failed() -> None:
    server = McpServeServer(runtime=_FailingRuntimeStub())
    _ = server.handle_message(_request("init", "initialize", {}))
    _ = server.handle_message(_request(None, "initialized", {}))

    failed = server.handle_message(
        _request("call_fail", "tools/call", {"name": "agenthub.file_read", "arguments": {"path": "README.md"}})
    )

    assert failed is not None
    assert failed["id"] == "call_fail"
    assert failed["error"]["code"] == -32010
    assert failed["error"]["message"] == "Tool call failed"
    assert "RuntimeError: boom:README.md:None:None:None" in failed["error"]["data"]["detail"]
