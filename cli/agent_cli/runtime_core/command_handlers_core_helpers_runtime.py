from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
)
from cli.agent_cli.runtime_core.command_handlers_approval_helpers_runtime import (
    patch_approval_cached,
)
from cli.agent_cli.runtime_core.command_usage import (
    _apply_patch_usage_text,
    _command_usage_text,
)
from cli.agent_cli.slash_commands import slash_command_help_text
from cli.agent_cli.slash_commands_i18n_runtime import localized_message
from cli.agent_cli.slash_parser import SlashInvocation


def handle_help_command(
    runtime,
    *,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
) -> tuple[str, list[ToolEvent]]:
    help_tokens = [
        str(token).strip().lower()
        for token in list(getattr(slash_invocation, "positionals", ()) or ())
        if str(token).strip()
    ]
    if not help_tokens and str(arg_text or "").strip():
        help_tokens = [part.strip().lower() for part in str(arg_text or "").split() if part.strip()]
    include_advanced = any(
        token in {"all", "advanced", "verbose", "--all", "-a"} for token in help_tokens
    )
    text = slash_command_help_text(
        plugin_manager=getattr(getattr(runtime, "tools", None), "_plugin_manager", None),
        include_advanced=include_advanced,
        locale=getattr(runtime, "presentation_locale", None),
    )
    text += shortcut_help_text(locale=getattr(runtime, "presentation_locale", None))
    return (text, [])


def shortcut_help_text(*, locale: str | None = None) -> str:
    from cli.agent_cli.app_bindings_runtime import APP_BINDINGS

    action_label_keys = {
        "ctrl_c": ("help.shortcuts.action.quit", "Quit"),
        "focused_undo_or_noop": ("help.shortcuts.action.undo", "Undo"),
        "clear_logs": ("help.shortcuts.action.clear_screen", "Clear screen"),
        "toggle_transcript": (
            "help.shortcuts.action.toggle_transcript",
            "Toggle transcript mode",
        ),
        "submit_prompt": ("help.shortcuts.action.send_prompt", "Send prompt"),
        "refresh_state": (
            "help.shortcuts.action.show_provider_status",
            "Show provider status",
        ),
        "show_tools": ("help.shortcuts.action.show_tools", "Show tools"),
        "toggle_latest_web_item": (
            "help.shortcuts.action.toggle_web_details",
            "Toggle web details",
        ),
        "paste_prompt": (
            "help.shortcuts.action.paste_from_clipboard",
            "Paste from clipboard",
        ),
        "new_tab": ("help.shortcuts.action.new_tab", "New tab"),
        "fork_tab": ("help.shortcuts.action.fork_current_tab", "Fork current tab"),
        "close_tab": ("help.shortcuts.action.close_current_tab", "Close current tab"),
        "next_tab": ("help.shortcuts.action.switch_to_next_tab", "Switch to next tab"),
        "prev_tab": (
            "help.shortcuts.action.switch_to_previous_tab",
            "Switch to previous tab",
        ),
        "split_open": ("help.shortcuts.action.split_pane_open", "Split pane open"),
        "split_close": ("help.shortcuts.action.split_pane_close", "Split pane close"),
    }
    shortcuts = []
    for b in APP_BINDINGS:
        key = b[0] if isinstance(b, tuple) else getattr(b, "key", "")
        action = b[1] if isinstance(b, tuple) and len(b) > 1 else getattr(b, "action", "")
        label_key, fallback = action_label_keys.get(action, ("", action))
        label = localized_message(label_key, fallback, locale=locale) if label_key else fallback
        if key:
            shortcuts.append(f"  {key} - {label}")
    if shortcuts:
        heading = localized_message(
            "help.shortcuts.heading",
            "keyboard shortcuts:",
            locale=locale,
        )
        return f"\n\n{heading}\n" + "\n".join(shortcuts)
    return ""


def handle_manual_compact_command(
    runtime,
    *,
    arg_text: str,
    decode_raw_text_arg: Callable[[str], str],
    single_event_result: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    instructions = decode_raw_text_arg(arg_text)
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
        return single_event_result(
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
    return single_event_result(
        "Context compacted.\n"
        f"replacement_history_count={result.get('replacement_history_count') or 0}\n"
        "reason=manual_compact",
        event,
        arguments={"instructions": instructions},
    )


def handle_expert_review_command(
    runtime,
    *,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], dict],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    from cli.agent_cli.runtime_services.expert_review_execution_runtime import (
        parse_expert_review_command_payload,
        run_expert_review,
    )

    if not arg_text:
        return text_only_result(_command_usage_text("expert_review"))
    try:
        payload = parse_expert_review_command_payload(parse_json_tool_arg(arg_text))
    except ValueError as exc:
        return error_result(
            error_event(
                "expert_review",
                "expert_review parse failed",
                error=str(exc),
            ),
        )
    try:
        return run_expert_review(runtime, **payload)
    except Exception as exc:
        return error_result(
            error_event(
                "expert_review",
                "expert_review failed",
                error=str(exc),
            ),
            arguments=payload,
            tool_name="expert_review",
        )


def handle_apply_patch_command(
    runtime,
    *,
    arg_text: str,
    workspace_root: Path,
    decode_raw_text_arg: Callable[[str], str],
    approval_request_text: Callable[[str, ToolEvent], str],
    call_structured: Callable[..., CommandExecutionResult | None],
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    from cli.agent_cli.runtime_action_policy_runtime import evaluate_apply_patch_action_policy

    patch_text = decode_raw_text_arg(arg_text)
    if not patch_text:
        return text_only_result(_apply_patch_usage_text())
    policy_state = evaluate_apply_patch_action_policy(
        runtime,
        patch_text=patch_text,
        workspace_root=workspace_root,
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
        return single_event_result(
            "Patch blocked.",
            error_event(
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
                assistant_text=approval_request_text("Request patch approval.", event),
                tool_events=[event],
                item_events=generic_tool_call_item_events(
                    tool_name="patch_approval_requested",
                    arguments={"patch": patch_text},
                    ok=bool(event.ok),
                    summary=str(event.summary or ""),
                    structured_content=dict(event.payload or {}),
                ),
            )
    structured = call_structured(runtime.tools, "apply_patch_result", patch_text)
    if structured is not None:
        if structured.tool_events:
            structured.tool_events[0].payload.update(policy_payload)
        return structured
    event = runtime.tools.apply_patch(patch_text)
    event.payload.update(policy_payload)
    return single_event_result("Apply workspace patch.", event, arguments={"patch": patch_text})
