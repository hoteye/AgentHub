from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import runtime_runtime_facade_runtime


def build_local_plan(*, local_plan_disabled_note: str) -> dict[str, Any]:
    return runtime_runtime_facade_runtime.build_local_plan(local_plan_disabled_note=local_plan_disabled_note)


def preview_local_plan(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    return runtime_runtime_facade_runtime.preview_local_plan(
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
    return runtime_runtime_facade_runtime.local_plan_attempt_state(
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
    return runtime_runtime_facade_runtime.local_plan_preview_state(
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
    return runtime_runtime_facade_runtime.local_plan_state_update(
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
    return runtime_runtime_facade_runtime.normalized_planner_input_item(
        item,
        response_input_item_from_dict_fn=response_input_item_from_dict_fn,
        planner_message_input_item_fn=planner_message_input_item_fn,
    )
