from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Sequence, TextIO

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.mcp import serve_runtime_helpers as _helpers

if TYPE_CHECKING:
    from cli.agent_cli.runtime import AgentCliRuntime


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class McpServePolicy:
    allowed_tools: set[str] | None = None
    blocked_tools: set[str] = field(default_factory=set)

    def permits(self, tool_name: str) -> bool:
        if tool_name in self.blocked_tools:
            return False
        if self.allowed_tools is None:
            return True
        return tool_name in self.allowed_tools


@dataclass(frozen=True)
class _McpToolDef:
    name: str
    description: str
    input_schema: JsonDict
    handler: Callable[[JsonDict], CommandExecutionResult]

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
        }


class McpServeServer:
    def __init__(self, *, runtime: Any, policy: McpServePolicy | None = None) -> None:
        self._runtime = runtime
        self._policy = policy or McpServePolicy()
        self._initialized = False
        all_tools = self._build_tool_defs()
        self._tool_defs: dict[str, _McpToolDef] = {
            name: tool_def
            for name, tool_def in all_tools.items()
            if self._policy.permits(name)
        }

    def handle_message(self, message: JsonDict) -> JsonDict | None:
        if not isinstance(message, dict):
            return _error_response(
                request_id=None,
                code=-32600,
                message="Invalid Request",
                data={"detail": "message must be an object"},
            )

        method = str(message.get("method") or "").strip()
        request_id = message.get("id")
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _error_response(
                request_id=request_id,
                code=-32602,
                message="Invalid params",
                data={"detail": "params must be an object"},
            )
        if not method:
            return _error_response(
                request_id=request_id,
                code=-32600,
                message="Invalid Request",
                data={"detail": "method is required"},
            )

        if method == "initialize":
            return _result_response(request_id, self._handle_initialize(params))
        if method == "initialized":
            self._initialized = True
            return None
        if method == "tools/list":
            if not self._initialized:
                return _error_response(
                    request_id=request_id,
                    code=-32002,
                    message="Not initialized",
                    data={"detail": "send initialize then initialized first"},
                )
            return _result_response(request_id, self._handle_tools_list())
        if method == "tools/call":
            if not self._initialized:
                return _error_response(
                    request_id=request_id,
                    code=-32002,
                    message="Not initialized",
                    data={"detail": "send initialize then initialized first"},
                )
            try:
                result_payload = self._handle_tools_call(params)
            except ValueError as exc:
                return _error_response(
                    request_id=request_id,
                    code=-32602,
                    message="Invalid params",
                    data={"detail": str(exc)},
                )
            except Exception as exc:
                return _error_response(
                    request_id=request_id,
                    code=-32010,
                    message="Tool call failed",
                    data={"detail": f"{type(exc).__name__}: {exc}"},
                )
            return _result_response(request_id=request_id, result=result_payload)

        return _error_response(
            request_id=request_id,
            code=-32601,
            message="Method not found",
            data={"detail": method},
        )

    def _build_tool_defs(self) -> dict[str, _McpToolDef]:
        return {
            "agenthub.list_dir": _McpToolDef(
                name="agenthub.list_dir",
                description="List files under a directory in the current workspace.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string"},
                        "offset": {"type": "integer", "minimum": 1},
                        "limit": {"type": "integer", "minimum": 1},
                        "depth": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
                handler=self._call_list_dir,
            ),
            "agenthub.file_read": _McpToolDef(
                name="agenthub.file_read",
                description="Read a file from the current workspace.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "max_chars": {"type": "integer", "minimum": 1},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                handler=self._call_file_read,
            ),
        }

    def _handle_initialize(self, _params: JsonDict) -> JsonDict:
        return {
            "serverInfo": {"name": "agenthub_mcp_server", "version": "0.1"},
            "capabilities": {
                "tools": {"listChanged": False},
            },
        }

    def _handle_tools_list(self) -> JsonDict:
        tools = [tool_def.to_dict() for tool_def in sorted(self._tool_defs.values(), key=lambda item: item.name)]
        return {"tools": tools}

    def _handle_tools_call(self, params: JsonDict) -> JsonDict:
        tool_name = str(params.get("name") or "").strip()
        if not tool_name:
            raise ValueError("params.name is required")
        tool_def = self._tool_defs.get(tool_name)
        if tool_def is None:
            raise ValueError(f"tool not allowed: {tool_name}")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError("params.arguments must be an object")
        result = tool_def.handler(dict(arguments))
        return _command_result_to_mcp_payload(result)

    def _call_list_dir(self, arguments: JsonDict) -> CommandExecutionResult:
        offset = _coerce_int(arguments.get("offset"), default=1, minimum=1)
        limit = _coerce_int(arguments.get("limit"), default=25, minimum=1)
        depth = _coerce_int(arguments.get("depth"), default=2, minimum=1)
        dir_path = str(arguments.get("dir_path") or "").strip() or None
        return self._runtime.tools.list_dir_result(
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
        )

    def _call_file_read(self, arguments: JsonDict) -> CommandExecutionResult:
        path = str(arguments.get("path") or "").strip()
        if not path:
            raise ValueError("tool agenthub.file_read requires arguments.path")
        return self._runtime.tools.file_read_result(
            path=path,
            offset=_optional_int(arguments.get("offset")),
            limit=_optional_int(arguments.get("limit")),
            max_chars=_optional_int(arguments.get("max_chars"), minimum=1),
        )


def run_stdio_server(
    *,
    runtime: Any,
    policy: McpServePolicy | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    server = McpServeServer(runtime=runtime, policy=policy)

    for raw_line in input_stream:
        line = str(raw_line or "").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error_response(
                request_id=None,
                code=-32700,
                message="Parse error",
                data={"detail": str(exc)},
            )
            output_stream.write(json.dumps(response, ensure_ascii=True) + "\n")
            output_stream.flush()
            continue
        response = server.handle_message(message)
        if response is None:
            continue
        output_stream.write(json.dumps(response, ensure_ascii=True) + "\n")
        output_stream.flush()
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime: AgentCliRuntime | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parsed = _helpers.parse_cli_args(argv, stderr=stderr)
    if parsed is None:
        return 2
    allow_list, deny_list = parsed
    policy = McpServePolicy(
        allowed_tools=allow_list or None,
        blocked_tools=deny_list,
    )
    server_runtime = runtime or AgentCliRuntime()
    return run_stdio_server(
        runtime=server_runtime,
        policy=policy,
        stdin=stdin,
        stdout=stdout,
    )


def _coerce_int(value: Any, *, default: int, minimum: int | None = None) -> int:
    return _helpers.coerce_int(value, default=default, minimum=minimum)


def _optional_int(value: Any, *, minimum: int | None = None) -> int | None:
    return _helpers.optional_int(value, minimum=minimum)


def _tool_event_to_dict(event: ToolEvent) -> JsonDict:
    return _helpers.tool_event_to_dict(event)


def _command_result_to_mcp_payload(result: CommandExecutionResult) -> JsonDict:
    return _helpers.command_result_to_mcp_payload(result, tool_event_to_dict_fn=_tool_event_to_dict)


def _result_response(request_id: Any, result: JsonDict) -> JsonDict:
    return _helpers.result_response(request_id, result)


def _error_response(request_id: Any, *, code: int, message: str, data: JsonDict | None = None) -> JsonDict:
    return _helpers.error_response(request_id, code=code, message=message, data=data)
