from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli.agent_cli.runtime_core.command_dispatch import (
        execute_agent_intent,
        execute_agent_intent_result,
        run_command_text,
        run_command_text_result,
        single_event,
    )
    from cli.agent_cli.runtime_core.command_parsing import parse_args, split_command
    from cli.agent_cli.runtime_core.event_rendering import (
        activity_detail_for_event,
        activity_events_for_tool_event,
        detail_for_event,
    )
    from cli.agent_cli.runtime_core.local_plan_execution import try_execute_local_plan
    from cli.agent_cli.runtime_core.local_routing import (
        extract_conversation_name,
        extract_first_url,
        looks_like_confirm_send_request,
        looks_like_file_reference_prompt,
        looks_like_policy_question,
        looks_like_prepare_send_request,
        plan_step_names,
        references_current_conversation,
        text_has_any,
    )
    from cli.agent_cli.runtime_core.run_lifecycle import (
        active_run_token,
        begin_run,
        finish_run,
        has_active_run,
        interrupt_active_run,
        interrupt_event,
        interrupt_tuple,
        is_interrupt_requested,
    )
    from cli.agent_cli.runtime_core.state import (
        apply_tool_state,
        build_status_payload,
        snapshot_thread_state_payload,
        state_value,
    )
    from cli.agent_cli.runtime_core.thread_session import (
        list_threads,
        restore_provider_state,
        resume_thread,
        start_thread,
    )


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "active_run_token": (".run_lifecycle", "active_run_token"),
    "activity_detail_for_event": (".event_rendering", "activity_detail_for_event"),
    "activity_events_for_tool_event": (".event_rendering", "activity_events_for_tool_event"),
    "apply_tool_state": (".state", "apply_tool_state"),
    "begin_run": (".run_lifecycle", "begin_run"),
    "build_status_payload": (".state", "build_status_payload"),
    "detail_for_event": (".event_rendering", "detail_for_event"),
    "execute_agent_intent": (".command_dispatch", "execute_agent_intent"),
    "execute_agent_intent_result": (".command_dispatch", "execute_agent_intent_result"),
    "extract_conversation_name": (".local_routing", "extract_conversation_name"),
    "extract_first_url": (".local_routing", "extract_first_url"),
    "finish_run": (".run_lifecycle", "finish_run"),
    "has_active_run": (".run_lifecycle", "has_active_run"),
    "interrupt_active_run": (".run_lifecycle", "interrupt_active_run"),
    "interrupt_event": (".run_lifecycle", "interrupt_event"),
    "interrupt_tuple": (".run_lifecycle", "interrupt_tuple"),
    "is_interrupt_requested": (".run_lifecycle", "is_interrupt_requested"),
    "list_threads": (".thread_session", "list_threads"),
    "looks_like_confirm_send_request": (".local_routing", "looks_like_confirm_send_request"),
    "looks_like_file_reference_prompt": (".local_routing", "looks_like_file_reference_prompt"),
    "looks_like_policy_question": (".local_routing", "looks_like_policy_question"),
    "looks_like_prepare_send_request": (".local_routing", "looks_like_prepare_send_request"),
    "parse_args": (".command_parsing", "parse_args"),
    "plan_step_names": (".local_routing", "plan_step_names"),
    "references_current_conversation": (".local_routing", "references_current_conversation"),
    "restore_provider_state": (".thread_session", "restore_provider_state"),
    "run_command_text": (".command_dispatch", "run_command_text"),
    "run_command_text_result": (".command_dispatch", "run_command_text_result"),
    "resume_thread": (".thread_session", "resume_thread"),
    "single_event": (".command_dispatch", "single_event"),
    "snapshot_thread_state_payload": (".state", "snapshot_thread_state_payload"),
    "split_command": (".command_parsing", "split_command"),
    "start_thread": (".thread_session", "start_thread"),
    "state_value": (".state", "state_value"),
    "text_has_any": (".local_routing", "text_has_any"),
    "try_execute_local_plan": (".local_plan_execution", "try_execute_local_plan"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> object:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
