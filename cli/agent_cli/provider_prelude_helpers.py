from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli import provider_prelude_runtime as _provider_prelude_runtime


MarkerOffsetFn = Callable[[List[Dict[str, Any]]], int | None]


def build_ordered_request_prelude_items(
    *,
    developer_item: Dict[str, Any] | None,
    environment_items: List[Dict[str, Any]] | None = None,
    workspace_reference_items: List[Dict[str, Any]] | None = None,
    workspace_message_items: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    return _provider_prelude_runtime.build_ordered_request_prelude_items(
        developer_item=developer_item,
        environment_items=environment_items,
        workspace_reference_items=workspace_reference_items,
        workspace_message_items=workspace_message_items,
    )


def request_prelude_contract(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn: MarkerOffsetFn,
    environment_context_marker_offset_fn: MarkerOffsetFn,
) -> Dict[str, Any]:
    return _provider_prelude_runtime.request_prelude_contract(
        items,
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    )


def extract_current_turn_prelude_items(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn: MarkerOffsetFn,
    environment_context_marker_offset_fn: MarkerOffsetFn,
) -> List[Dict[str, Any]]:
    return _provider_prelude_runtime.extract_current_turn_prelude_items(
        items,
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    )


def extract_current_turn_prelude_contract(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn: MarkerOffsetFn,
    environment_context_marker_offset_fn: MarkerOffsetFn,
) -> Dict[str, Any]:
    return _provider_prelude_runtime.extract_current_turn_prelude_contract(
        items,
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    )
