from __future__ import annotations

import json
from typing import Any, Dict, List

from cli.agent_cli import (
    models_response_projection_normalization_helpers_runtime as normalization_service,
)


def projection_response_item_tool_key(item: Dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("type") or "").strip().lower(),
        str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip(),
    )


def dedupe_tool_projection_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for raw_item in list(items or []):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        item_type = str(item.get("type") or "").strip().lower()
        if normalization_service.is_tool_call_input_item_type(
            item_type
        ) or normalization_service.is_tool_call_output_item_type(item_type):
            key = projection_response_item_tool_key(item)
            if key in seen_keys:
                continue
            seen_keys.add(key)
        deduped.append(item)
    return deduped


def command_family_call_id(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    item_type = str(item.get("type") or "").strip().lower()
    if item_type in {"shell_call", "local_shell_call", "shell_call_output", "local_shell_call_output"}:
        return str(item.get("call_id") or item.get("id") or "").strip()
    if item_type == "function_call":
        if not normalization_service.is_command_family_function_name(str(item.get("name") or "").strip()):
            return ""
        return str(item.get("call_id") or item.get("id") or "").strip()
    if item_type == "function_call_output":
        return str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()
    if item_type == "command_execution":
        return str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()
    return ""


def call_id_needs_tool_event_override(call_id: str) -> bool:
    return normalization_service.is_synthetic_tool_item_id(call_id)


def _tool_call_types_compatible_for_matching(
    left_type: str,
    right_type: str,
    *,
    left_name: str,
    right_name: str,
) -> bool:
    normalized_left_type = str(left_type or "").strip().lower()
    normalized_right_type = str(right_type or "").strip().lower()
    if normalized_left_type == normalized_right_type:
        return True
    normalized_left_name = str(left_name or "").strip()
    normalized_right_name = str(right_name or "").strip()
    if normalized_left_name != normalized_right_name:
        return False
    if normalized_left_name != "apply_patch":
        return False
    return {normalized_left_type, normalized_right_type} <= {"custom_tool_call", "function_call"}


def tool_call_arguments_for_matching(item: Dict[str, Any]) -> Any:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "custom_tool_call":
        raw_input = str(item.get("input") or "").strip()
        return raw_input or None
    arguments = item.get("arguments")
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
    return arguments


def tool_call_arguments_conflict(left: Any, right: Any) -> bool:
    if left in (None, "", {}, []):
        return False
    if right in (None, "", {}, []):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        smaller, larger = (left, right) if len(left) <= len(right) else (right, left)
        if all(key in larger and larger.get(key) == value for key, value in smaller.items()):
            return False
    return left != right


def tool_event_call_id_overrides(
    turn_event_call_items: List[Dict[str, Any]],
    tool_event_call_items: List[Dict[str, Any]],
) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    used_tool_event_indexes: set[int] = set()
    for turn_item in list(turn_event_call_items or []):
        turn_call_id = str(turn_item.get("call_id") or turn_item.get("tool_call_id") or "").strip()
        if not turn_call_id or not call_id_needs_tool_event_override(turn_call_id):
            continue
        turn_type = str(turn_item.get("type") or "").strip().lower()
        turn_name = str(turn_item.get("name") or "").strip()
        turn_arguments = tool_call_arguments_for_matching(turn_item)
        for idx, tool_item in enumerate(list(tool_event_call_items or [])):
            if idx in used_tool_event_indexes:
                continue
            tool_type = str(tool_item.get("type") or "").strip().lower()
            tool_name = str(tool_item.get("name") or "").strip()
            if not _tool_call_types_compatible_for_matching(
                turn_type,
                tool_type,
                left_name=turn_name,
                right_name=tool_name,
            ):
                continue
            tool_call_id = str(tool_item.get("call_id") or tool_item.get("tool_call_id") or "").strip()
            if not tool_call_id:
                continue
            tool_arguments = tool_call_arguments_for_matching(tool_item)
            if tool_call_arguments_conflict(turn_arguments, tool_arguments):
                continue
            overrides[turn_call_id] = tool_call_id
            used_tool_event_indexes.add(idx)
            break
    return overrides


def response_input_call_id_overrides(
    projected_call_items: List[Dict[str, Any]],
    existing_response_call_items: List[Dict[str, Any]],
) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    used_existing_indexes: set[int] = set()
    for projected_item in list(projected_call_items or []):
        projected_call_id = str(
            projected_item.get("call_id") or projected_item.get("tool_call_id") or ""
        ).strip()
        if not projected_call_id:
            continue
        projected_type = str(projected_item.get("type") or "").strip().lower()
        projected_name = str(projected_item.get("name") or "").strip()
        projected_arguments = tool_call_arguments_for_matching(projected_item)
        for idx, existing_item in enumerate(list(existing_response_call_items or [])):
            if idx in used_existing_indexes:
                continue
            existing_type = str(existing_item.get("type") or "").strip().lower()
            existing_name = str(existing_item.get("name") or "").strip()
            if not _tool_call_types_compatible_for_matching(
                projected_type,
                existing_type,
                left_name=projected_name,
                right_name=existing_name,
            ):
                continue
            existing_call_id = str(
                existing_item.get("call_id") or existing_item.get("tool_call_id") or ""
            ).strip()
            if not existing_call_id or existing_call_id == projected_call_id:
                continue
            existing_arguments = tool_call_arguments_for_matching(existing_item)
            if tool_call_arguments_conflict(projected_arguments, existing_arguments):
                continue
            overrides[projected_call_id] = existing_call_id
            used_existing_indexes.add(idx)
            break
    return overrides


def apply_call_id_overrides(items: List[Dict[str, Any]], overrides: Dict[str, str]) -> List[Dict[str, Any]]:
    if not overrides:
        return [dict(item) for item in list(items or []) if isinstance(item, dict)]
    updated: List[Dict[str, Any]] = []
    for raw_item in list(items or []):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        call_id = str(item.get("call_id") or item.get("tool_call_id") or "").strip()
        override = overrides.get(call_id)
        if override:
            item["call_id"] = override
            if "tool_call_id" in item:
                item["tool_call_id"] = override
        updated.append(item)
    return updated
