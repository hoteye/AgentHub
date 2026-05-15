from __future__ import annotations

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
)
from cli.agent_cli.runtime_core.background_task_commands import handle_background_task_command
from cli.agent_cli.runtime_core.browser_commands import handle_browser_command
from cli.agent_cli.runtime_core.command_handlers_approval_helpers_runtime import (
    handle_approval_command,
)
from cli.agent_cli.runtime_core.command_handlers_core_helpers_runtime import (
    handle_apply_patch_command,
    handle_expert_review_command,
    handle_help_command,
    handle_manual_compact_command,
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
        return handle_help_command(
            runtime,
            arg_text=arg_text,
            slash_invocation=slash_invocation,
        )
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
        return handle_manual_compact_command(
            runtime,
            arg_text=arg_text,
            decode_raw_text_arg=_decode_raw_text_arg,
            single_event_result=_single_event_result,
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
        return handle_expert_review_command(
            runtime,
            arg_text=arg_text,
            parse_json_tool_arg=_parse_json_tool_arg,
            text_only_result=_text_only_result,
            error_result=_error_result,
            error_event=_error_event,
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
        return handle_apply_patch_command(
            runtime,
            arg_text=arg_text,
            workspace_root=_file_workspace_root(runtime),
            decode_raw_text_arg=_decode_raw_text_arg,
            approval_request_text=_approval_request_text,
            call_structured=_call_structured,
            single_event_result=_single_event_result,
            text_only_result=_text_only_result,
            error_event=_error_event,
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
