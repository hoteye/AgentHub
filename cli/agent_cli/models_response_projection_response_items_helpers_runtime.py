from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ResponseInputItem, ToolEvent


def _tool_item_call_id(item: dict[str, Any]) -> str:
    return str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()


def _drop_unpaired_tool_call_inputs(
    items: list[dict[str, Any]],
    *,
    is_tool_call_input_item_type_fn: Any,
    is_tool_call_output_item_type_fn: Any,
) -> list[dict[str, Any]]:
    normalized_items = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    output_call_ids = {
        _tool_item_call_id(item)
        for item in normalized_items
        if is_tool_call_output_item_type_fn(str(item.get("type") or "").strip().lower())
        and _tool_item_call_id(item)
    }
    filtered: list[dict[str, Any]] = []
    for item in normalized_items:
        item_type = str(item.get("type") or "").strip().lower()
        if is_tool_call_input_item_type_fn(item_type):
            call_id = _tool_item_call_id(item)
            if not call_id or call_id not in output_call_ids:
                continue
        filtered.append(item)
    return filtered


def response_items_with_tool_outputs(
    response_items: list[ResponseInputItem] | list[dict[str, Any]],
    turn_events: list[dict[str, Any]],
    tool_events: list[ToolEvent] | list[dict[str, Any]] | None = None,
    *,
    turn_event_tool_history_available_fn: Any,
    provider_tool_call_input_items_from_turn_events_fn: Any,
    projected_structured_call_items_from_turn_events_fn: Any,
    response_input_call_id_overrides_fn: Any,
    apply_call_id_overrides_fn: Any,
    dedupe_tool_projection_items_fn: Any,
    tool_event_call_id_overrides_fn: Any,
    projection_response_item_tool_key_fn: Any,
    command_family_call_id_fn: Any,
    sanitize_tool_input_item_fn: Any,
    shared_replay_reasoning_projection_fn: Any,
    is_tool_call_input_item_type_fn: Any,
    is_tool_call_output_item_type_fn: Any,
    turn_event_content_types_fn: Any,
    function_call_input_items_from_tool_events_fn: Any,
    tool_output_input_items_from_tool_events_fn: Any,
    function_call_input_items_from_turn_events_fn: Any,
    tool_output_input_items_from_turn_events_fn: Any,
) -> list[dict[str, Any]]:
    prefer_turn_events = turn_event_tool_history_available_fn(turn_events)
    provider_turn_event_call_items = (
        provider_tool_call_input_items_from_turn_events_fn(turn_events)
        if prefer_turn_events
        else []
    )
    structured_turn_event_call_items = (
        projected_structured_call_items_from_turn_events_fn(turn_events)
        if prefer_turn_events
        else []
    )
    projected_to_provider_overrides: dict[str, str] = {}
    tool_event_call_items: list[dict[str, Any]] = []
    tool_event_output_items: list[dict[str, Any]] = []
    override_destination_call_ids: set[str] = set()
    if prefer_turn_events and provider_turn_event_call_items and structured_turn_event_call_items:
        projected_to_provider_overrides = response_input_call_id_overrides_fn(
            structured_turn_event_call_items,
            provider_turn_event_call_items,
        )
        structured_turn_event_call_items = apply_call_id_overrides_fn(
            structured_turn_event_call_items,
            projected_to_provider_overrides,
        )
        provider_call_ids = {
            str(item.get("call_id") or item.get("tool_call_id") or "").strip()
            for item in list(provider_turn_event_call_items or [])
            if isinstance(item, dict)
        }
        structured_turn_event_call_items = [
            item
            for item in list(structured_turn_event_call_items or [])
            if str(item.get("call_id") or item.get("tool_call_id") or "").strip()
            not in provider_call_ids
        ]
    function_call_items = (
        dedupe_tool_projection_items_fn(
            [*provider_turn_event_call_items, *structured_turn_event_call_items]
        )
        if prefer_turn_events
        else []
    )
    if not function_call_items and tool_events:
        function_call_items = function_call_input_items_from_tool_events_fn(tool_events)
    if not function_call_items:
        function_call_items = function_call_input_items_from_turn_events_fn(turn_events)
    tool_output_items = (
        tool_output_input_items_from_turn_events_fn(turn_events) if prefer_turn_events else []
    )
    if projected_to_provider_overrides:
        tool_output_items = apply_call_id_overrides_fn(
            tool_output_items, projected_to_provider_overrides
        )
    if not tool_output_items and tool_events:
        tool_output_items = tool_output_input_items_from_tool_events_fn(tool_events)
    if not tool_output_items:
        tool_output_items = tool_output_input_items_from_turn_events_fn(turn_events)
    if prefer_turn_events and tool_events:
        tool_event_call_items = function_call_input_items_from_tool_events_fn(tool_events)
        tool_event_output_items = tool_output_input_items_from_tool_events_fn(tool_events)
        call_id_overrides = tool_event_call_id_overrides_fn(
            function_call_items,
            tool_event_call_items,
        )
        function_call_items = apply_call_id_overrides_fn(function_call_items, call_id_overrides)
        tool_event_call_items = apply_call_id_overrides_fn(tool_event_call_items, call_id_overrides)
        tool_output_items = apply_call_id_overrides_fn(tool_output_items, call_id_overrides)
        tool_event_output_items = apply_call_id_overrides_fn(
            tool_event_output_items, call_id_overrides
        )
        override_destination_call_ids = {
            str(call_id or "").strip()
            for call_id in list(call_id_overrides.values())
            if str(call_id or "").strip()
        }
        if tool_event_call_items:
            preferred_tool_event_calls_by_call_id = {
                str(item.get("call_id") or item.get("tool_call_id") or "").strip(): item
                for item in list(tool_event_call_items or [])
                if isinstance(item, dict)
                and str(item.get("call_id") or item.get("tool_call_id") or "").strip()
            }
            if preferred_tool_event_calls_by_call_id:
                merged_function_call_items: list[dict[str, Any]] = []
                for item in list(function_call_items or []):
                    call_id = str(item.get("call_id") or item.get("tool_call_id") or "").strip()
                    preferred_item = preferred_tool_event_calls_by_call_id.get(call_id)
                    merged_item = dict(preferred_item or item)
                    plugin_observability = item.get("plugin_observability")
                    if "plugin_observability" not in merged_item and isinstance(
                        plugin_observability, dict
                    ):
                        merged_item["plugin_observability"] = dict(plugin_observability)
                    merged_function_call_items.append(merged_item)
                function_call_items = merged_function_call_items
        if override_destination_call_ids and tool_event_output_items:
            preferred_tool_event_outputs = {
                projection_response_item_tool_key_fn(item): item
                for item in list(tool_event_output_items or [])
                if str(item.get("call_id") or item.get("tool_call_id") or "").strip()
                in override_destination_call_ids
            }
            if preferred_tool_event_outputs:
                merged_tool_output_items: list[dict[str, Any]] = []
                for item in list(tool_output_items or []):
                    preferred_item = preferred_tool_event_outputs.get(
                        projection_response_item_tool_key_fn(item)
                    )
                    merged_item = dict(preferred_item or item)
                    plugin_observability = item.get("plugin_observability")
                    if "plugin_observability" not in merged_item and isinstance(
                        plugin_observability, dict
                    ):
                        merged_item["plugin_observability"] = dict(plugin_observability)
                    merged_tool_output_items.append(merged_item)
                tool_output_items = merged_tool_output_items
        if tool_event_output_items:
            preferred_tool_event_outputs = {
                projection_response_item_tool_key_fn(item): item
                for item in list(tool_event_output_items or [])
                if isinstance(item, dict)
            }
            if preferred_tool_event_outputs:
                merged_tool_output_items = []
                for item in list(tool_output_items or []):
                    preferred_item = preferred_tool_event_outputs.get(
                        projection_response_item_tool_key_fn(item)
                    )
                    merged_item = dict(preferred_item or item)
                    plugin_observability = item.get("plugin_observability")
                    if "plugin_observability" not in merged_item and isinstance(
                        plugin_observability, dict
                    ):
                        merged_item["plugin_observability"] = dict(plugin_observability)
                    merged_tool_output_items.append(merged_item)
                tool_output_items = merged_tool_output_items
    normalized_response_items = [
        sanitize_tool_input_item_fn(
            ResponseInputItem.from_dict(
                item.to_dict() if isinstance(item, ResponseInputItem) else dict(item)
            ).to_dict()
        )
        for item in list(response_items or [])
        if isinstance(item, ResponseInputItem | dict)
    ]
    existing_response_call_items = [
        dict(item)
        for item in list(normalized_response_items or [])
        if is_tool_call_input_item_type_fn(str(item.get("type") or "").strip().lower())
    ]
    response_call_id_overrides = response_input_call_id_overrides_fn(
        function_call_items,
        existing_response_call_items,
    )
    function_call_items = apply_call_id_overrides_fn(
        function_call_items, response_call_id_overrides
    )
    tool_output_items = apply_call_id_overrides_fn(tool_output_items, response_call_id_overrides)
    if not function_call_items and not tool_output_items:
        return _drop_unpaired_tool_call_inputs(
            normalized_response_items,
            is_tool_call_input_item_type_fn=is_tool_call_input_item_type_fn,
            is_tool_call_output_item_type_fn=is_tool_call_output_item_type_fn,
        )

    pre_tool_items: list[dict[str, Any]] = []
    existing_tool_input_items: list[dict[str, Any]] = []
    existing_tool_output_items: list[dict[str, Any]] = []
    post_tool_items: list[dict[str, Any]] = []
    seen_existing_tool_input_keys: set[tuple[str, str]] = set()
    seen_existing_tool_output_keys: set[tuple[str, str]] = set()
    existing_tool_input_call_ids: set[str] = set()
    existing_tool_output_call_ids: set[str] = set()
    for raw_item in normalized_response_items:
        response_item = ResponseInputItem.from_dict(raw_item)
        response_item_dict = sanitize_tool_input_item_fn(response_item.to_dict())
        response_item_type = str(response_item_dict.get("type") or "").strip().lower()
        phase = str((response_item.extra or {}).get("phase") or "").strip().lower()
        content_types = turn_event_content_types_fn(getattr(response_item, "content", None))
        is_reasoning = (
            str(getattr(response_item, "item_type", "") or "").strip().lower() == "reasoning"
            or "reasoning" in content_types
        )
        if is_reasoning:
            replay_reasoning_projection = shared_replay_reasoning_projection_fn(
                response_item_dict,
                source="tool_history_projection",
            )
            replay_reasoning_item = replay_reasoning_projection.get("input_item")
            if replay_reasoning_item is not None:
                pre_tool_items.append(dict(replay_reasoning_item))
            continue
        if is_tool_call_input_item_type_fn(response_item_type):
            tool_key = projection_response_item_tool_key_fn(response_item_dict)
            if tool_key not in seen_existing_tool_input_keys:
                seen_existing_tool_input_keys.add(tool_key)
                existing_tool_input_items.append(response_item_dict)
        elif is_tool_call_output_item_type_fn(response_item_type):
            tool_key = projection_response_item_tool_key_fn(response_item_dict)
            if tool_key not in seen_existing_tool_output_keys:
                seen_existing_tool_output_keys.add(tool_key)
                existing_tool_output_items.append(response_item_dict)
        if phase not in {"", "commentary"} and not is_reasoning:
            post_tool_items.append(response_item.to_dict())
        elif (
            phase == ""
            and not is_reasoning
            and not (
                is_tool_call_input_item_type_fn(response_item_type)
                or is_tool_call_output_item_type_fn(response_item_type)
            )
        ):
            post_tool_items.append(response_item_dict)
        else:
            if not (
                is_tool_call_input_item_type_fn(response_item_type)
                or is_tool_call_output_item_type_fn(response_item_type)
            ):
                pre_tool_items.append(response_item_dict)
        command_call_id = command_family_call_id_fn(response_item_dict)
        if not command_call_id:
            continue
        if is_tool_call_input_item_type_fn(response_item_type):
            existing_tool_input_call_ids.add(command_call_id)
        if is_tool_call_output_item_type_fn(response_item_type):
            existing_tool_output_call_ids.add(command_call_id)
    existing_tool_keys = {
        projection_response_item_tool_key_fn(item)
        for item in list(normalized_response_items or [])
        if is_tool_call_input_item_type_fn(str(item.get("type") or "").strip().lower())
        or is_tool_call_output_item_type_fn(str(item.get("type") or "").strip().lower())
    }
    filtered_function_call_items = []
    for item in function_call_items:
        command_call_id = command_family_call_id_fn(item)
        if command_call_id and command_call_id in existing_tool_input_call_ids:
            continue
        if projection_response_item_tool_key_fn(item) in existing_tool_keys:
            continue
        filtered_function_call_items.append(item)
    existing_tool_keys.update(
        projection_response_item_tool_key_fn(item) for item in filtered_function_call_items
    )
    filtered_tool_output_items = []
    for item in tool_output_items:
        command_call_id = command_family_call_id_fn(item)
        if command_call_id and command_call_id in existing_tool_output_call_ids:
            continue
        if projection_response_item_tool_key_fn(item) in existing_tool_keys:
            continue
        filtered_tool_output_items.append(item)
    return _drop_unpaired_tool_call_inputs(
        [
            *pre_tool_items,
            *existing_tool_input_items,
            *filtered_function_call_items,
            *filtered_tool_output_items,
            *existing_tool_output_items,
            *post_tool_items,
        ],
        is_tool_call_input_item_type_fn=is_tool_call_input_item_type_fn,
        is_tool_call_output_item_type_fn=is_tool_call_output_item_type_fn,
    )
