from __future__ import annotations

import json
import shlex
from typing import Any

from cli.agent_cli.models import PromptResponse
from cli.agent_cli.runtime_core.command_parsing import parse_args as _parse_command_args
from cli.agent_cli.runtime_kernels.codex_sidecar.dynamic_tools import (
    internal_command_for_dynamic_tool,
)
from cli.agent_cli.slash_parser import is_slash_command_text, slash_name_and_rest

_AGENTHUB_ADAPTER_COMMANDS = {
    "__request_orchestration",
    "__spawn_child_tab",
    "__send_child_tab",
    "__wait_child_tasks",
    "exit",
    "quit",
    "close",
    "help",
    "lang",
    "theme",
    "setup",
    "plan",
    "tab_rename",
    "tab_new",
    "approval_inbox",
    "preview",
    "fork",
    "master",
    "fork_child",
    "providers",
    "tools",
    "plugins",
    "memory",
    "init",
    "orchestrate",
    "orchestrate_confirm",
    "orchestrate_dispatch",
    "orchestrate_progress",
    "orchestrate_continue",
    "orchestrate_apply",
    "orchestrate_reject",
}


class CodexSidecarRuntimeCommandsMixin:
    """AgentHub command and dynamic-tool helpers extracted from CodexSidecarRuntimeAdapter."""

    @staticmethod
    def _parse_args(arg_text: str) -> tuple[list[str], dict[str, Any]]:
        return _parse_command_args(arg_text)

    def _run_command_text_result(self, text: str) -> Any:
        from cli.agent_cli.runtime_core.command_dispatch import run_command_text_result

        return run_command_text_result(self, text)

    def _agenthub_command_prompt_response(self, text: str) -> PromptResponse | None:
        if not is_slash_command_text(text):
            return None
        try:
            command_name, _arg_text = slash_name_and_rest(text)
        except ValueError:
            return None
        if command_name not in _AGENTHUB_ADAPTER_COMMANDS:
            return None
        result = self._run_command_text_result(text)
        return PromptResponse(
            user_text=str(text or ""),
            assistant_text=str(result.assistant_text or ""),
            tool_events=list(result.tool_events or []),
            handled_as_command=True,
            turn_events=[
                dict(item) for item in list(result.turn_events or []) if isinstance(item, dict)
            ],
            command_display_text=str(result.command_display_text or ""),
            status={
                "runtime_kernel": "codex_sidecar",
                "command": command_name,
            },
        )

    def _handle_dynamic_tool_call(self, envelope: Any) -> dict[str, object]:
        params = dict(getattr(envelope, "params", {}) or {})
        command_name = internal_command_for_dynamic_tool(
            namespace=str(params.get("namespace") or ""),
            tool=str(params.get("tool") or ""),
        )
        if not command_name:
            return _dynamic_tool_response(
                f"unsupported AgentHub dynamic tool: {params.get('namespace') or '-'}."
                f"{params.get('tool') or '-'}",
                success=False,
            )
        arguments = params.get("arguments")
        payload = arguments if isinstance(arguments, dict) else {}
        payload_text = shlex.quote(json.dumps(payload, ensure_ascii=True))
        result = self._run_command_text_result(f"/{command_name} {payload_text}")
        ok = True
        for event in list(getattr(result, "tool_events", []) or []):
            if not bool(getattr(event, "ok", True)):
                ok = False
                break
        text = str(getattr(result, "assistant_text", "") or "").strip()
        if not text:
            text = f"{params.get('tool') or 'dynamic_tool'} completed"
        return _dynamic_tool_response(text, success=ok)


def _dynamic_tool_response(text: str, *, success: bool) -> dict[str, object]:
    return {
        "contentItems": [
            {
                "type": "inputText",
                "text": str(text or ""),
            }
        ],
        "success": bool(success),
    }
