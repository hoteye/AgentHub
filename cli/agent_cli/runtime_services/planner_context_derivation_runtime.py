from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.environment_context import (
    render_environment_context_update_message,
)
from cli.agent_cli.workspace_context import (
    build_workspace_reference_context_item,
    render_workspace_reference_context_item_message,
    render_workspace_context_update_message,
)


def workspace_snapshot_has_context(snapshot: Optional[Dict[str, Any]]) -> bool:
    payload = dict(snapshot or {})
    return bool(
        str(payload.get("instructions_digest") or "").strip()
        or list(payload.get("docs") or [])
        or list(payload.get("skills") or [])
    )


def planner_environment_context_items(
    runtime: Any,
    *,
    snapshot_override: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    snapshot = dict(snapshot_override or runtime._environment_context_snapshot or {})
    if snapshot:
        message = render_environment_context_update_message(None, snapshot)
        normalized = runtime._normalized_history_item({"role": "user", "content": message})
        if normalized is not None:
            return [normalized]
    normalized_items: List[Dict[str, str]] = []
    for item in runtime._environment_context_history[-1:]:
        normalized = runtime._normalized_history_item(item)
        if normalized is not None:
            normalized_items.append(normalized)
    return normalized_items


def planner_workspace_context_items(
    runtime: Any,
    *,
    snapshot_override: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    snapshot = dict(snapshot_override or runtime._workspace_context_snapshot or {})
    if snapshot and workspace_snapshot_has_context(snapshot):
        context_item = build_workspace_reference_context_item(None, snapshot)
        message = render_workspace_reference_context_item_message(
            context_item or {}
        ) or render_workspace_context_update_message(
            None,
            snapshot,
        )
        normalized = runtime._normalized_history_item({"role": "user", "content": message})
        if normalized is not None:
            return [normalized]
    normalized_items: List[Dict[str, str]] = []
    for item in runtime._context_update_history[-1:]:
        normalized = runtime._normalized_history_item(item)
        if normalized is not None:
            normalized_items.append(normalized)
    return normalized_items


def planner_history_with_context_updates(
    runtime: Any,
    *,
    planner_history: Optional[List[Dict[str, str]]] = None,
    environment_snapshot: Optional[Dict[str, Any]] = None,
    workspace_snapshot: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    merged.extend(
        planner_environment_context_items(
            runtime,
            snapshot_override=environment_snapshot,
        )
    )
    merged.extend(
        planner_workspace_context_items(
            runtime,
            snapshot_override=workspace_snapshot,
        )
    )
    for item in list(planner_history or runtime._planner_history() or []):
        normalized = runtime._normalized_history_item(item)
        if normalized is not None:
            merged.append(normalized)
    return merged
