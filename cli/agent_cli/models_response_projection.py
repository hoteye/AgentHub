from __future__ import annotations

import json
from typing import Any, Dict, List

from cli.agent_cli.models import ResponseInputItem, ToolEvent
from cli.agent_cli.models_response_projection_replay_helpers_runtime import (
    reasoning_input_items_from_turn_events as _reasoning_input_items_from_turn_events,
    replay_input_items_from_turn_events as _replay_input_items_from_turn_events,
    shared_replay_reasoning_retention_diagnostics as _shared_replay_reasoning_retention_diagnostics,
)
from cli.agent_cli.models_response_projection_response_items_helpers_runtime import (
    response_items_with_tool_outputs as _response_items_with_tool_outputs,
)
from cli.agent_cli.models_response_projection_helpers_runtime import (
    apply_call_id_overrides as _apply_call_id_overrides,
    call_id_needs_tool_event_override as _call_id_needs_tool_event_override,
    command_family_call_id as _command_family_call_id,
    dedupe_tool_projection_items as _dedupe_tool_projection_items,
    function_call_input_items_from_turn_events_projection as _function_call_input_items_from_turn_events_projection,
    is_tool_call_input_item_type as _is_tool_call_input_item_type,
    is_tool_call_output_item_type as _is_tool_call_output_item_type,
    normalized_mcp_call_arguments as _normalized_mcp_call_arguments,
    projected_structured_call_items_from_turn_events as _projected_structured_call_items_from_turn_events,
    projection_response_item_tool_key as _projection_response_item_tool_key,
    provider_tool_call_input_items_from_turn_events as _provider_tool_call_input_items_from_turn_events,
    reasoning_retention_diagnostic_key as _reasoning_retention_diagnostic_key,
    response_input_call_id_overrides as _response_input_call_id_overrides,
    sanitize_tool_input_item as _sanitize_tool_input_item,
    shared_replay_reasoning_projection as _shared_replay_reasoning_projection,
    tool_call_arguments_conflict as _tool_call_arguments_conflict,
    tool_call_arguments_for_matching as _tool_call_arguments_for_matching,
    tool_event_call_id_overrides as _tool_event_call_id_overrides,
    tool_output_input_items_from_turn_events_projection as _tool_output_input_items_from_turn_events_projection,
    turn_event_tool_history_available as _turn_event_tool_history_available,
)
from cli.agent_cli.models_tool_io import (
    function_call_input_items_from_tool_events,
    tool_output_input_items_from_tool_events,
)
from cli.agent_cli.models_turn_events import (
    _reasoning_turn_event_key,
    _turn_event_content_types,
    reasoning_input_item_from_turn_event_item,
    reasoning_replay_projection_from_turn_event_item,
)
from cli.agent_cli.web_search_argument_projection_runtime import (
    response_input_item_from_web_search_turn_item as _response_input_item_from_web_search_turn_item_shared,
)


def tool_output_input_items_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _tool_output_input_items_from_turn_events_projection(turn_events)


def shared_replay_reasoning_projection(
    item: Dict[str, Any],
    *,
    source: str = "tool_history_projection",
) -> Dict[str, Any]:
    return _shared_replay_reasoning_projection(item, source=source)


def shared_replay_reasoning_retention_diagnostics(turn: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _shared_replay_reasoning_retention_diagnostics(
        turn,
        reasoning_retention_diagnostic_key_fn=_reasoning_retention_diagnostic_key,
        shared_replay_reasoning_projection_fn=_shared_replay_reasoning_projection,
        turn_event_tool_history_available_fn=_turn_event_tool_history_available,
        reasoning_replay_projection_from_turn_event_item_fn=reasoning_replay_projection_from_turn_event_item,
    )


def function_call_input_items_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _function_call_input_items_from_turn_events_projection(turn_events)


def replay_input_items_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _replay_input_items_from_turn_events(
        turn_events,
        reasoning_turn_event_key_fn=_reasoning_turn_event_key,
        reasoning_replay_projection_from_turn_event_item_fn=reasoning_replay_projection_from_turn_event_item,
        response_input_item_from_web_search_turn_item_fn=_response_input_item_from_web_search_turn_item_shared,
        sanitize_tool_input_item_fn=_sanitize_tool_input_item,
        function_call_input_items_from_turn_events_fn=function_call_input_items_from_turn_events,
        tool_output_input_items_from_turn_events_fn=tool_output_input_items_from_turn_events,
        provider_tool_call_input_items_from_turn_events_fn=_provider_tool_call_input_items_from_turn_events,
        projected_structured_call_items_from_turn_events_fn=_projected_structured_call_items_from_turn_events,
        response_input_call_id_overrides_fn=_response_input_call_id_overrides,
        apply_call_id_overrides_fn=_apply_call_id_overrides,
        dedupe_tool_projection_items_fn=_dedupe_tool_projection_items,
    )


def reasoning_input_items_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _reasoning_input_items_from_turn_events(
        turn_events,
        reasoning_input_item_from_turn_event_item_fn=reasoning_input_item_from_turn_event_item,
        reasoning_turn_event_key_fn=_reasoning_turn_event_key,
    )


def response_items_with_tool_outputs(
    response_items: List[ResponseInputItem] | List[Dict[str, Any]],
    turn_events: List[Dict[str, Any]],
    tool_events: List[ToolEvent] | List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    return _response_items_with_tool_outputs(
        response_items,
        turn_events,
        tool_events,
        turn_event_tool_history_available_fn=_turn_event_tool_history_available,
        provider_tool_call_input_items_from_turn_events_fn=_provider_tool_call_input_items_from_turn_events,
        projected_structured_call_items_from_turn_events_fn=_projected_structured_call_items_from_turn_events,
        response_input_call_id_overrides_fn=_response_input_call_id_overrides,
        apply_call_id_overrides_fn=_apply_call_id_overrides,
        dedupe_tool_projection_items_fn=_dedupe_tool_projection_items,
        tool_event_call_id_overrides_fn=_tool_event_call_id_overrides,
        projection_response_item_tool_key_fn=_projection_response_item_tool_key,
        command_family_call_id_fn=_command_family_call_id,
        sanitize_tool_input_item_fn=_sanitize_tool_input_item,
        shared_replay_reasoning_projection_fn=_shared_replay_reasoning_projection,
        is_tool_call_input_item_type_fn=_is_tool_call_input_item_type,
        is_tool_call_output_item_type_fn=_is_tool_call_output_item_type,
        turn_event_content_types_fn=_turn_event_content_types,
        function_call_input_items_from_tool_events_fn=function_call_input_items_from_tool_events,
        tool_output_input_items_from_tool_events_fn=tool_output_input_items_from_tool_events,
        function_call_input_items_from_turn_events_fn=function_call_input_items_from_turn_events,
        tool_output_input_items_from_turn_events_fn=tool_output_input_items_from_turn_events,
    )
