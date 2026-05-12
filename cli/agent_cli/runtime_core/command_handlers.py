from __future__ import annotations

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
)
from cli.agent_cli.runtime_core.background_task_commands import handle_background_task_command
from cli.agent_cli.runtime_core.browser_commands import handle_browser_command
from cli.agent_cli.runtime_core.command_handlers_approval_helpers_runtime import (
    handle_approval_command,
    patch_approval_cached,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    approval_request_text as _approval_request_text,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    bool_option as _bool_option,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    call_structured as _call_structured,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    compact_arguments as _compact_arguments,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    decode_raw_text_arg as _decode_raw_text_arg,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    error_event as _error_event,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    error_result as _error_result,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    handle_request_user_input_command,
    handle_update_plan_command,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    int_option as _int_option,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    parse_json_tool_arg as _parse_json_tool_arg,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    single_event_result as _single_event_result,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    switch_disabled_result as _switch_disabled_result,
)
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    text_only_result as _text_only_result,
)
from cli.agent_cli.runtime_core.command_usage import (
    _apply_patch_usage_text,
    _command_usage_text,
)
from cli.agent_cli.runtime_core.init_commands import handle_init_command
from cli.agent_cli.runtime_core.mcp_commands import handle_mcp_command
from cli.agent_cli.runtime_core.memory_commands import handle_memory_command
from cli.agent_cli.runtime_core.orchestration_commands import handle_orchestration_command
from cli.agent_cli.runtime_core.provider_commands import handle_provider_command
from cli.agent_cli.runtime_core.setup_commands import handle_setup_command
from cli.agent_cli.runtime_core.shell_command_handlers import handle_shell_command
from cli.agent_cli.runtime_core.thread_commands import handle_thread_and_agent_command
from cli.agent_cli.runtime_core.tool_commands import (
    handle_cd_command,
    handle_runtime_policy_command,
    handle_tool_command,
)
from cli.agent_cli.runtime_core.update_commands import handle_update_command
from cli.agent_cli.slash_commands import slash_command_help_text
from cli.agent_cli.slash_parser import SlashInvocation


def _file_workspace_root(runtime):
    getter = getattr(getattr(runtime, "tools", None), "file_workspace_root", None)
    if callable(getter):
        return getter()
    return runtime.cwd


def handle_known_command(
    runtime,
    *,
    name: str,
    arg_text: str,
    text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[ToolEvent]] | CommandExecutionResult | None:
    if name == "help":
        help_tokens = [
            str(token).strip().lower()
            for token in list(getattr(slash_invocation, "positionals", ()) or ())
            if str(token).strip()
        ]
        if not help_tokens and str(arg_text or "").strip():
            help_tokens = [
                part.strip().lower() for part in str(arg_text or "").split() if part.strip()
            ]
        include_advanced = any(
            token in {"all", "advanced", "verbose", "--all", "-a"} for token in help_tokens
        )
        text = slash_command_help_text(
            plugin_manager=getattr(getattr(runtime, "tools", None), "_plugin_manager", None),
            include_advanced=include_advanced,
            locale=getattr(runtime, "presentation_locale", None),
        )
        from cli.agent_cli.app_bindings_runtime import APP_BINDINGS

        _ACTION_LABELS = {
            "ctrl_c": "Quit",
            "focused_undo_or_noop": "Undo",
            "clear_logs": "Clear screen",
            "toggle_transcript": "Toggle transcript mode",
            "submit_prompt": "Send prompt",
            "refresh_state": "Show provider status",
            "show_tools": "Show tools",
            "toggle_latest_web_item": "Toggle web details",
            "paste_prompt": "Paste from clipboard",
            "new_tab": "New tab",
            "fork_tab": "Fork current tab",
            "close_tab": "Close current tab",
            "next_tab": "Switch to next tab",
            "prev_tab": "Switch to previous tab",
        }
        shortcuts = []
        for b in APP_BINDINGS:
            key = b[0] if isinstance(b, tuple) else getattr(b, "key", "")
            action = b[1] if isinstance(b, tuple) and len(b) > 1 else getattr(b, "action", "")
            label = _ACTION_LABELS.get(action, action)
            if key:
                shortcuts.append(f"  {key} - {label}")
        if shortcuts:
            text += "\n\nkeyboard shortcuts:\n" + "\n".join(shortcuts)
        return (text, [])
    if name == "cd":
        return handle_cd_command(runtime, name=name, arg_text=arg_text)
    if name in {"runtime_status", "status"}:
        return handle_runtime_policy_command(
            runtime, name=name, arg_text=arg_text, slash_invocation=slash_invocation
        )
    init_result = handle_init_command(
        runtime,
        name=name,
        arg_text=arg_text,
    )
    if init_result is not None:
        return init_result
    setup_result = handle_setup_command(
        runtime,
        name=name,
        arg_text=arg_text,
    )
    if setup_result is not None:
        return setup_result
    update_result = handle_update_command(
        runtime,
        name=name,
        arg_text=arg_text,
    )
    if update_result is not None:
        return update_result
    orchestration_result = handle_orchestration_command(
        runtime,
        name=name,
        arg_text=arg_text,
    )
    if orchestration_result is not None:
        return orchestration_result
    background_task_result = handle_background_task_command(
        runtime,
        name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        int_option=_int_option,
    )
    if background_task_result is not None:
        return background_task_result
    thread_command_result = handle_thread_and_agent_command(
        runtime,
        name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        parse_json_tool_arg=_parse_json_tool_arg,
        int_option=_int_option,
        bool_option=_bool_option,
        decode_raw_text_arg=_decode_raw_text_arg,
        single_event_result=_single_event_result,
        text_only_result=_text_only_result,
        error_result=_error_result,
        error_event=_error_event,
    )
    if thread_command_result is not None:
        return thread_command_result
    mcp_command_result = handle_mcp_command(
        runtime,
        name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
    )
    if mcp_command_result is not None:
        return mcp_command_result
    memory_command_result = handle_memory_command(
        runtime,
        name=name,
        arg_text=arg_text,
    )
    if memory_command_result is not None:
        return memory_command_result
    if name == "runtime_config":
        return handle_runtime_policy_command(
            runtime, name=name, arg_text=arg_text, slash_invocation=slash_invocation
        )
    if name == "lang":
        return (
            "`/lang` is a TUI-local command. Use it inside the interactive TUI, or start the TUI with `--lang`.",
            [],
        )
    if name == "theme":
        return (
            "`/theme` is a TUI-local command. Use it inside the interactive TUI, or start the TUI with `--theme`.",
            [],
        )
    _is_interrupted = getattr(runtime, "_is_interrupt_requested", None)
    if (
        callable(_is_interrupted)
        and _is_interrupted()
        and name
        not in {
            "provider",
            "providers",
            "models",
            "model",
            "model-route",
            "model_route",
            "delegate-model",
            "delegate_model",
            "help",
        }
    ):
        _interrupt_fn = getattr(runtime, "_interrupt_tuple", None)
        if callable(_interrupt_fn):
            return _interrupt_fn()
    if name == "compact":
        instructions = _decode_raw_text_arg(arg_text)
        result = runtime._compact_history(
            reason="manual_compact",
            trigger="manual",
            instructions=instructions,
        )
        if not bool(result.get("ok")):
            event = ToolEvent(
                name="compact",
                ok=True,
                summary="Not enough provider conversation history to compact.",
                payload={
                    "ok": True,
                    "reason": result.get("reason") or "not_enough_history",
                    "trigger": "manual",
                    "trigger_item_count": result.get("trigger_item_count"),
                    "replacement_history_count": 0,
                },
            )
            return _single_event_result(
                "Not enough provider conversation history to compact.",
                event,
                arguments={"instructions": instructions},
            )
        event_payload = {
            "ok": True,
            "reason": result.get("reason") or "manual_compact",
            "trigger": "manual",
            "trigger_item_count": result.get("trigger_item_count"),
            "replacement_history_count": result.get("replacement_history_count"),
        }
        if instructions:
            event_payload["instructions"] = instructions
        event = ToolEvent(
            name="compact",
            ok=True,
            summary="Context compacted.",
            payload=event_payload,
        )
        return _single_event_result(
            "Context compacted.\n"
            f"replacement_history_count={result.get('replacement_history_count') or 0}\n"
            "reason=manual_compact",
            event,
            arguments={"instructions": instructions},
        )
    provider_result = handle_provider_command(
        runtime,
        name=name,
        arg_text=arg_text,
        switch_disabled_result=_switch_disabled_result,
        slash_invocation=slash_invocation,
    )
    if provider_result is not None:
        return provider_result
    if name == "expert_review":
        from cli.agent_cli.runtime_services.expert_review_execution_runtime import (
            parse_expert_review_command_payload,
            run_expert_review,
        )

        if not arg_text:
            return _text_only_result(_command_usage_text("expert_review"))
        try:
            payload = parse_expert_review_command_payload(_parse_json_tool_arg(arg_text))
        except ValueError as exc:
            return _error_result(
                _error_event(
                    "expert_review",
                    "expert_review parse failed",
                    error=str(exc),
                ),
            )
        try:
            return run_expert_review(runtime, **payload)
        except Exception as exc:
            return _error_result(
                _error_event(
                    "expert_review",
                    "expert_review failed",
                    error=str(exc),
                ),
                arguments=payload,
                tool_name="expert_review",
            )
    tool_command_result = handle_tool_command(
        runtime,
        name=name,
        arg_text=arg_text,
        command_usage_text=_command_usage_text,
        call_structured=_call_structured,
        single_event_result=_single_event_result,
        text_only_result=_text_only_result,
        error_event=_error_event,
    )
    if tool_command_result is not None:
        return tool_command_result
    if name == "plan":
        runtime.collaboration_mode = "plan"
        message = "switched to Plan mode"
        return CommandExecutionResult(
            assistant_text=message,
            command_display_text=message,
        )
    if name == "update_plan":
        return handle_update_plan_command(runtime, arg_text=arg_text)
    if name == "request_user_input":
        return handle_request_user_input_command(runtime, arg_text=arg_text)
    if name == "llm":
        if not arg_text:
            return "Usage: /llm <prompt>", []
        tool_executor = (
            getattr(runtime, "_structured_tool_executor", None) or runtime._run_command_text
        )
        intent = runtime.agent.plan(arg_text, history=runtime.history, tool_executor=tool_executor)
        assistant_text, events = runtime._execute_agent_intent(intent)
        return (assistant_text, events)
    shell_result = handle_shell_command(
        runtime,
        name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        compact_arguments=_compact_arguments,
        int_option=_int_option,
        bool_option=_bool_option,
        error_event=_error_event,
        error_result=_error_result,
        text_only_result=_text_only_result,
        single_event_result=_single_event_result,
        approval_request_text=_approval_request_text,
    )
    if shell_result is not None:
        return shell_result
    if name == "apply_patch":
        from cli.agent_cli.runtime_action_policy_runtime import evaluate_apply_patch_action_policy

        patch_text = _decode_raw_text_arg(arg_text)
        if not patch_text:
            return _text_only_result(_apply_patch_usage_text())
        policy_state = evaluate_apply_patch_action_policy(
            runtime,
            patch_text=patch_text,
            workspace_root=_file_workspace_root(runtime),
        )
        policy_payload = dict(policy_state["payload"] or {})
        requirement_name = str(
            (policy_state["action_policy_payload"] or {}).get("requirement") or ""
        ).strip()
        if requirement_name == "forbidden":
            error_text = str(policy_payload.get("reason_text") or "patch blocked")
            if str(policy_payload.get("reason_code") or "") == "apply_patch_sandbox_read_only":
                error_text = "runtime sandbox is read-only"
            event_payload = dict(policy_payload)
            event_payload.pop("error", None)
            return _single_event_result(
                "Patch blocked.",
                _error_event(
                    "apply_patch",
                    "patch blocked",
                    error=error_text,
                    **event_payload,
                ),
                arguments={"patch": patch_text},
            )
        if requirement_name == "needs_approval":
            if patch_approval_cached(runtime, patch_text=patch_text):
                policy_payload.update(
                    {
                        "approval_cache_hit": True,
                        "policy_decision": "allowed",
                        "policy_decision_reason": "approval_cached",
                    }
                )
            else:
                event = runtime.request_patch_approval(patch_text)
                event.payload.update(policy_payload)
                return CommandExecutionResult(
                    assistant_text=_approval_request_text("Request patch approval.", event),
                    tool_events=[event],
                    item_events=generic_tool_call_item_events(
                        tool_name="patch_approval_requested",
                        arguments={"patch": patch_text},
                        ok=bool(event.ok),
                        summary=str(event.summary or ""),
                        structured_content=dict(event.payload or {}),
                    ),
                )
        structured = _call_structured(runtime.tools, "apply_patch_result", patch_text)
        if structured is not None:
            if structured.tool_events:
                structured.tool_events[0].payload.update(policy_payload)
            return structured
        event = runtime.tools.apply_patch(patch_text)
        event.payload.update(policy_payload)
        return _single_event_result(
            "Apply workspace patch.", event, arguments={"patch": patch_text}
        )
    approval_result = handle_approval_command(
        runtime,
        name=name,
        arg_text=arg_text,
        slash_invocation=slash_invocation,
        single_event_result=_single_event_result,
        text_only_result=_text_only_result,
    )
    if approval_result is not None:
        return approval_result
    if name == "browser":
        return handle_browser_command(
            runtime,
            arg_text=arg_text,
            compact_arguments=_compact_arguments,
            text_only_result=_text_only_result,
            call_structured=_call_structured,
            single_event_result=_single_event_result,
        )
    return None
