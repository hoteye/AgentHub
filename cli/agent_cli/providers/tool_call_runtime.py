from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from typing import Any

from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.host_platform import HostPlatform

from . import (
    anthropic_edit_tool_specs,
    tool_call_runtime_delegation_helpers,
    tool_call_runtime_helpers,
)

_BACKGROUND_SESSION_YIELD_TIME_MS = tool_call_runtime_helpers._BACKGROUND_SESSION_YIELD_TIME_MS
_CLAUDE_STYLE_AUTO_BACKGROUND_THRESHOLD_MS = (
    tool_call_runtime_helpers._CLAUDE_STYLE_AUTO_BACKGROUND_THRESHOLD_MS
)
_quote_value = tool_call_runtime_helpers.quote_value
_normalized_tool_name = tool_call_runtime_helpers.normalized_tool_name
_shell_override_for_tool_name = tool_call_runtime_helpers.shell_override_for_tool_name
_optional_bool = tool_call_runtime_helpers.optional_bool
_uses_claude_style_auto_background = tool_call_runtime_helpers.uses_claude_style_auto_background
_normalized_shell_yield_time_ms = tool_call_runtime_helpers.normalized_shell_yield_time_ms
_normalized_shell_timeout_ms = tool_call_runtime_helpers.normalized_shell_timeout_ms
_shell_family = tool_call_runtime_helpers.shell_family
_normalized_exec_command = tool_call_runtime_helpers.normalized_exec_command
_build_exec_command = tool_call_runtime_helpers.build_exec_command
_normalized_collab_items = tool_call_runtime_helpers.normalized_collab_items
_collab_item_preview = tool_call_runtime_helpers.collab_item_preview
_collab_items_preview = tool_call_runtime_helpers.collab_items_preview
_uses_legacy_spawn_agent_payload = tool_call_runtime_helpers.uses_legacy_spawn_agent_payload
_build_spawn_agent_command = tool_call_runtime_delegation_helpers.build_spawn_agent_command
_build_send_input_command = tool_call_runtime_delegation_helpers.build_send_input_command
_build_resume_agent_command = tool_call_runtime_delegation_helpers.build_resume_agent_command
_build_wait_agent_command = tool_call_runtime_delegation_helpers.build_wait_agent_command


def runtime_tool_call_command(
    name: str,
    arguments: dict[str, Any],
    host_platform: HostPlatform,
    *,
    quote_arg_fn: Callable[[Any], str],
) -> str | None:
    if name == "exec_command":
        command = _build_exec_command(
            arguments.get("cmd") or arguments.get("command"),
            workdir=arguments.get("workdir"),
            shell=arguments.get("shell"),
            tty=arguments.get("tty"),
            login=arguments.get("login") if "login" in arguments else None,
            yield_time_ms=arguments.get("yield_time_ms"),
            timeout_ms=_normalized_shell_timeout_ms(arguments),
            max_output_tokens=arguments.get("max_output_tokens"),
            host_platform=host_platform,
            quote_arg_fn=quote_arg_fn,
        )
        if command is None:
            return None
        additional_permissions = arguments.get("additional_permissions")
        sandbox_permissions = str(arguments.get("sandbox_permissions") or "").strip()
        if not sandbox_permissions and isinstance(additional_permissions, dict):
            sandbox_permissions = "with_additional_permissions"
        if sandbox_permissions:
            command += f" --sandbox-permissions {quote_arg_fn(sandbox_permissions)}"
        justification = str(arguments.get("justification") or "").strip()
        if justification:
            command += f" --justification {quote_arg_fn(justification)}"
        prefix_rule = arguments.get("prefix_rule")
        if isinstance(prefix_rule, list | tuple):
            normalized_prefix = ",".join(
                str(item).strip() for item in prefix_rule if str(item).strip()
            )
            if normalized_prefix:
                command += f" --prefix-rule {quote_arg_fn(normalized_prefix)}"
        if isinstance(additional_permissions, dict):
            command += " --additional-permissions-json " + quote_arg_fn(
                json.dumps(additional_permissions, ensure_ascii=True, sort_keys=True)
            )
        return command

    if name == "write_stdin":
        session_id = arguments.get("session_id")
        if session_id is None:
            return None
        command = f"/write_stdin {quote_arg_fn(str(session_id))}"
        chars = arguments.get("chars")
        if chars is not None:
            command += f" {quote_arg_fn(str(chars))}"
        yield_time_ms = arguments.get("yield_time_ms")
        if yield_time_ms is not None:
            command += f" --yield-time-ms {_quote_value(yield_time_ms, quote_arg_fn)}"
        max_output_tokens = arguments.get("max_output_tokens")
        if max_output_tokens is not None:
            command += f" --max-output-tokens {_quote_value(max_output_tokens, quote_arg_fn)}"
        if timeline_debug_enabled():
            log_timeline(
                "tool.provider.write_stdin.command_built",
                **json_ready(
                    {
                        "tool_name": name,
                        "session_id_raw": session_id,
                        "session_id_type": type(session_id).__name__,
                        "arguments": dict(arguments or {}),
                        "runtime_command": command,
                    }
                ),
            )
        return command

    if name == "spawn_agent":
        return _build_spawn_agent_command(
            arguments,
            quote_arg_fn=quote_arg_fn,
            normalized_collab_items_fn=_normalized_collab_items,
            uses_legacy_spawn_agent_payload_fn=_uses_legacy_spawn_agent_payload,
        )

    if name == "send_input":
        return _build_send_input_command(
            arguments,
            quote_arg_fn=quote_arg_fn,
            normalized_collab_items_fn=_normalized_collab_items,
        )

    if name == "resume_agent":
        return _build_resume_agent_command(arguments, quote_arg_fn=quote_arg_fn)

    if name in {"wait", "wait_agent"}:
        return _build_wait_agent_command(
            arguments,
            quote_arg_fn=quote_arg_fn,
            quote_value_fn=_quote_value,
        )

    if name == "expert_review":
        task = str(arguments.get("task") or "").strip()
        if not task:
            return None
        payload: dict[str, Any] = {"task": task}
        scope = str(arguments.get("scope") or "").strip()
        if scope:
            payload["scope"] = scope
        focus = arguments.get("focus")
        if isinstance(focus, list | tuple):
            normalized_focus = [str(item).strip() for item in focus if str(item).strip()]
            if normalized_focus:
                payload["focus"] = normalized_focus
        artifact_paths = arguments.get("artifact_paths")
        if isinstance(artifact_paths, list | tuple):
            normalized_artifacts = [
                str(item).strip() for item in artifact_paths if str(item).strip()
            ]
            if normalized_artifacts:
                payload["artifact_paths"] = normalized_artifacts
        max_findings = arguments.get("max_findings")
        if max_findings is not None:
            payload["max_findings"] = max_findings
        strictness = str(arguments.get("strictness") or "").strip()
        if strictness:
            payload["strictness"] = strictness
        return f"/expert_review {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    if name == "agent_workflow":
        target = str(
            arguments.get("target") or arguments.get("agent_id") or arguments.get("id") or ""
        ).strip()
        if not target:
            return None
        command = f"/agent_workflow {quote_arg_fn(target)}"
        steps = arguments.get("steps")
        if steps is not None:
            command += f" --steps {_quote_value(steps, quote_arg_fn)}"
        checkpoints = arguments.get("checkpoints")
        if checkpoints is not None:
            command += f" --checkpoints {_quote_value(checkpoints, quote_arg_fn)}"
        return command

    if name == "recover_agent":
        target = str(
            arguments.get("target") or arguments.get("agent_id") or arguments.get("id") or ""
        ).strip()
        if not target:
            return None
        command = f"/recover_agent {quote_arg_fn(target)}"
        action = str(arguments.get("action") or arguments.get("recovery_action") or "").strip()
        if action:
            command += f" --action {quote_arg_fn(action)}"
        step_id = str(arguments.get("step_id") or arguments.get("step") or "").strip()
        if step_id:
            command += f" --step-id {quote_arg_fn(step_id)}"
        return command

    if name == "close_agent":
        target = str(
            arguments.get("target") or arguments.get("agent_id") or arguments.get("id") or ""
        ).strip()
        return f"/close_agent {quote_arg_fn(target)}" if target else None

    if name == "update_plan":
        plan = arguments.get("plan")
        if not isinstance(plan, list):
            return None
        payload: dict[str, Any] = {"plan": plan}
        explanation = str(arguments.get("explanation") or "").strip()
        if explanation:
            payload["explanation"] = explanation
        return f"/update_plan {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    if name in {"request_user_input", "AskUserQuestion"}:
        questions = arguments.get("questions")
        if not isinstance(questions, list):
            return None
        payload = {"questions": questions}
        return f"/request_user_input {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    if name == "request_orchestration":
        source_text = str(
            arguments.get("source_text")
            or arguments.get("task")
            or arguments.get("prompt")
            or arguments.get("message")
            or ""
        ).strip()
        if not source_text:
            return None
        payload: dict[str, Any] = {
            "source_text": source_text,
            "goal": str(arguments.get("goal") or "").strip(),
            "reason": str(arguments.get("reason") or "").strip(),
            "proposed_scope": str(arguments.get("proposed_scope") or "").strip(),
            "risk_level": str(arguments.get("risk_level") or "").strip(),
            "needs_confirmation": bool(arguments.get("needs_confirmation", True)),
        }
        planning_adjustments = arguments.get("planning_adjustments")
        if isinstance(planning_adjustments, dict) and planning_adjustments:
            payload["planning_adjustments"] = dict(planning_adjustments)
        return f"/__request_orchestration {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    if name == "spawn_child_tab":
        task = str(
            arguments.get("task") or arguments.get("prompt") or arguments.get("message") or ""
        ).strip()
        if not task:
            return None
        payload = {
            "task": task,
            "task_name": str(arguments.get("task_name") or arguments.get("label") or "").strip(),
            "parent": str(arguments.get("parent") or arguments.get("parent_tab") or "").strip(),
        }
        metadata = arguments.get("metadata")
        if isinstance(metadata, dict) and metadata:
            payload["metadata"] = dict(metadata)
        return f"/__spawn_child_tab {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    if name == "send_child_tab":
        target = str(
            arguments.get("target") or arguments.get("tab_id") or arguments.get("id") or ""
        ).strip()
        message = str(
            arguments.get("message") or arguments.get("text") or arguments.get("prompt") or ""
        ).strip()
        if not target or not message:
            return None
        payload = {
            "target": target,
            "message": message,
            "interrupt": bool(arguments.get("interrupt")),
        }
        metadata = arguments.get("metadata")
        if isinstance(metadata, dict) and metadata:
            payload["metadata"] = dict(metadata)
        return f"/__send_child_tab {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    if name == "wait_child_tasks":
        payload: dict[str, Any] = {}
        targets = arguments.get("targets")
        if targets is None:
            target = str(
                arguments.get("target") or arguments.get("tab_id") or arguments.get("id") or ""
            ).strip()
            if target:
                targets = [target]
        if isinstance(targets, list | tuple):
            normalized_targets = [str(item).strip() for item in targets if str(item).strip()]
            if normalized_targets:
                payload["targets"] = normalized_targets
        timeout_ms = arguments.get("timeout_ms")
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        wait_for = str(arguments.get("wait_for") or "").strip()
        if wait_for:
            payload["wait_for"] = wait_for
        if "include_all" in arguments and arguments.get("include_all") is not None:
            payload["include_all"] = bool(arguments.get("include_all"))
        if "terminal_only" in arguments and arguments.get("terminal_only") is not None:
            payload["terminal_only"] = bool(arguments.get("terminal_only"))
        return f"/__wait_child_tasks {quote_arg_fn(json.dumps(payload, ensure_ascii=True))}"

    explicit_shell_override = _shell_override_for_tool_name(name)
    if explicit_shell_override is not None:
        argv = arguments.get("argv")
        if isinstance(argv, list | tuple):
            raw_command = " ".join(shlex.quote(str(item)) for item in argv if str(item).strip())
        else:
            raw_command = arguments.get("command")
        sandbox_permissions = str(arguments.get("sandbox_permissions") or "").strip()
        if (
            not sandbox_permissions
            and _optional_bool(arguments.get("dangerouslyDisableSandbox")) is True
        ):
            sandbox_permissions = "require_escalated"
        justification = str(arguments.get("justification") or "").strip()
        if not justification and sandbox_permissions == "require_escalated":
            justification = str(arguments.get("description") or "").strip()
        command = _build_exec_command(
            raw_command,
            workdir=arguments.get("workdir") or arguments.get("cwd"),
            shell=explicit_shell_override,
            tty=arguments.get("tty"),
            login=arguments.get("login") if "login" in arguments else None,
            yield_time_ms=_normalized_shell_yield_time_ms(arguments, tool_name=name),
            timeout_ms=_normalized_shell_timeout_ms(arguments),
            max_output_tokens=arguments.get("max_output_tokens"),
            host_platform=host_platform,
            quote_arg_fn=quote_arg_fn,
        )
        if command is None:
            return None
        if sandbox_permissions:
            command += f" --sandbox-permissions {quote_arg_fn(sandbox_permissions)}"
        if justification:
            command += f" --justification {quote_arg_fn(justification)}"
        return command

    if name == "shell":
        argv = arguments.get("argv")
        if isinstance(argv, list | tuple):
            # Prefer the pre-built command string (operators already unquoted) over
            # re-quoting argv, which would turn shell operators into quoted literals
            # and defeat security classification (e.g. '>' no longer seen as redirect).
            raw_command = arguments.get("command") or " ".join(
                shlex.quote(str(item)) for item in argv if str(item).strip()
            )
        else:
            raw_command = arguments.get("command")
        return _build_exec_command(
            raw_command,
            workdir=arguments.get("workdir") or arguments.get("cwd"),
            shell=arguments.get("shell"),
            tty=bool(arguments.get("tty")) if "tty" in arguments else None,
            login=arguments.get("login") if "login" in arguments else None,
            yield_time_ms=arguments.get("yield_time_ms"),
            timeout_ms=_normalized_shell_timeout_ms(arguments),
            max_output_tokens=arguments.get("max_output_tokens"),
            host_platform=host_platform,
            quote_arg_fn=quote_arg_fn,
        )

    if name == "list_mcp_resources":
        # MCP resource tools currently execute through the host slash-command path
        # rather than a persistent remote MCP client session.
        command = "/mcp_resource list"
        server_name = str(arguments.get("server_name") or arguments.get("server") or "").strip()
        if server_name:
            command += f" server {quote_arg_fn(server_name)}"
        return command

    if name == "read_mcp_resource":
        server_name = str(arguments.get("server_name") or arguments.get("server") or "").strip()
        uri = str(arguments.get("uri") or "").strip()
        if not server_name or not uri:
            return None
        return f"/mcp_resource read server {quote_arg_fn(server_name)} uri {quote_arg_fn(uri)}"

    if name.startswith("mcp__"):
        payload = json.dumps(dict(arguments or {}), ensure_ascii=True, sort_keys=True)
        return f"/mcp_tool_call projected-name {quote_arg_fn(name)} arguments-json {quote_arg_fn(payload)}"

    if name in {"apply_patch", "file_write", "file_edit", "Write", "Edit"}:
        projected_arguments = dict(arguments or {})
        if name == "Write":
            projected_arguments["__projected_tool_name"] = "Write"
        if name == "Edit":
            projected_arguments["__projected_tool_name"] = "Edit"
        return anthropic_edit_tool_specs.structured_edit_tool_call_command(
            name=name,
            arguments=projected_arguments,
            quote_arg_fn=quote_arg_fn,
        )

    return None
