from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import runtime_planner_runtime
from cli.agent_cli import runtime_runtime_state_runtime
from cli.agent_cli import runtime_shell_runtime
from cli.agent_cli.runtime_structured_runtime import StructuredToolExecutor


def runtime_init_state(
    *,
    threading_module: Any,
    thread_store: Any,
    run_command_text_result_fn: Callable[[str], Any],
    interrupt_requested_fn: Callable[[], bool],
    interrupt_result_fn: Callable[[], tuple[str, list[Any]]],
    runtime_state_defaults_fn: Callable[..., dict[str, Any]],
    runtime_owner: Any | None = None,
) -> dict[str, Any]:
    return {
        **runtime_state_defaults_fn(threading_module=threading_module),
        "thread_store": thread_store,
        "_structured_tool_executor": StructuredToolExecutor(
            run_command_text_result_fn=run_command_text_result_fn,
            interrupt_requested_fn=interrupt_requested_fn,
            interrupt_result_fn=interrupt_result_fn,
            runtime_owner=runtime_owner,
        ),
    }


def approval_list_event(
    *,
    rows: list[dict[str, Any]],
    status: str | None,
    tool_event_factory: Callable[..., Any],
) -> Any:
    return runtime_shell_runtime.approval_list_event(
        rows=rows,
        status=status,
        tool_event_factory=tool_event_factory,
    )


def approval_list_rows(
    *,
    tickets: list[Any],
    get_action_request_fn: Callable[[str], Any],
) -> list[dict[str, Any]]:
    return runtime_shell_runtime.approval_list_rows(
        tickets=tickets,
        get_action_request_fn=get_action_request_fn,
    )


def slash_command_rows(specs: list[Any]) -> list[dict[str, str]]:
    return runtime_planner_runtime.slash_command_rows(specs)


def build_local_plan(*, local_plan_disabled_note: str) -> dict[str, Any]:
    return runtime_planner_runtime.build_local_plan(local_plan_disabled_note=local_plan_disabled_note)


def preview_local_plan(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    return runtime_planner_runtime.preview_local_plan(
        text=text,
        last_plan=last_plan,
        last_plan_text=last_plan_text,
        build_local_plan_fn=build_local_plan_fn,
    )


def local_plan_attempt_state(
    *,
    text: str,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], str, bool]:
    return runtime_planner_runtime.local_plan_attempt_state(
        text=text,
        build_local_plan_fn=build_local_plan_fn,
    )


def local_plan_preview_state(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    return runtime_planner_runtime.local_plan_preview_state(
        text=text,
        last_plan=last_plan,
        last_plan_text=last_plan_text,
        build_local_plan_fn=build_local_plan_fn,
    )


def local_plan_state_update(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
    preview: bool,
    local_plan_preview_state_fn: Callable[..., tuple[dict[str, Any], dict[str, Any], str]],
    local_plan_attempt_state_fn: Callable[..., tuple[dict[str, Any], str, bool]],
) -> tuple[dict[str, Any], dict[str, Any], str, bool]:
    return runtime_runtime_state_runtime.local_plan_state_update(
        text=text,
        last_plan=last_plan,
        last_plan_text=last_plan_text,
        build_local_plan_fn=build_local_plan_fn,
        preview=preview,
        local_plan_preview_state_fn=local_plan_preview_state_fn,
        local_plan_attempt_state_fn=local_plan_attempt_state_fn,
    )


def normalized_planner_input_item(
    item: Any,
    *,
    response_input_item_from_dict_fn: Callable[[dict[str, Any]], Any],
    planner_message_input_item_fn: Callable[[str, str], dict[str, Any] | None],
) -> dict[str, Any] | None:
    return runtime_planner_runtime.normalized_planner_input_item(
        item,
        response_input_item_from_dict_fn=response_input_item_from_dict_fn,
        planner_message_input_item_fn=planner_message_input_item_fn,
    )
