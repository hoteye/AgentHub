from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from cli.agent_cli.environment_context import (
    build_environment_context_snapshot,
    local_datetime_with_timezone,
    render_environment_context_update_message,
)
from cli.agent_cli.memory_context_runtime import memory_context_turn_update
from cli.agent_cli.models import ReferenceContextItem
from cli.agent_cli.tools_core import tool_registry_runtime
from cli.agent_cli.workspace_context import (
    agent_cli_home_skill_roots,
    build_workspace_reference_context_item,
    build_workspace_reference_snapshot,
    render_workspace_context_update_message,
)


def workspace_skill_roots(runtime: Any) -> List[str]:
    roots = list(agent_cli_home_skill_roots())
    manager = getattr(runtime.tools, "_plugin_manager", None)
    if manager is None:
        return roots
    getter = getattr(manager, "effective_skill_roots", None)
    if not callable(getter):
        return roots
    try:
        roots.extend(str(item) for item in list(getter() or []))
    except Exception:
        return roots
    deduped: List[str] = []
    seen: set[str] = set()
    for item in roots:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def normalized_history_item(item: Any) -> Optional[Dict[str, str]]:
    if not isinstance(item, dict):
        return None
    role = str(item.get("role") or "").strip().lower()
    content = str(item.get("content") or "").strip()
    if role not in {"system", "developer", "user", "assistant"}:
        role = "user"
    if not content:
        return None
    return {"role": role, "content": content}


def restore_workspace_context_state(
    runtime: Any,
    state: Dict[str, Any],
    context_items: Optional[List[Dict[str, Any]]] = None,
) -> None:
    snapshot = state.get("workspace_context_snapshot")
    runtime._workspace_context_snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}
    context_history: List[Dict[str, str]] = []
    for item in list(state.get("context_update_history") or []):
        normalized = normalized_history_item(item)
        if normalized is not None:
            context_history.append(normalized)
    runtime._context_update_history = context_history[-16:]
    if runtime._workspace_context_snapshot:
        return
    latest_workspace_item = None
    for item in list(context_items or [])[::-1]:
        if not isinstance(item, dict):
            continue
        if str(item.get("item_type") or "").strip() != "workspace_context":
            continue
        latest_workspace_item = item
        break
    if not isinstance(latest_workspace_item, dict):
        return
    metadata = latest_workspace_item.get("metadata")
    if not isinstance(metadata, dict):
        return
    docs = [entry for entry in list(metadata.get("docs") or []) if isinstance(entry, dict)]
    skills = [entry for entry in list(metadata.get("skills") or []) if isinstance(entry, dict)]
    runtime._workspace_context_snapshot = {
        "cwd": str(latest_workspace_item.get("path") or runtime.cwd),
        "workspace_root": str(metadata.get("workspace_root") or latest_workspace_item.get("path") or runtime.cwd),
        "trust_level": str(metadata.get("trust_level") or ""),
        "instructions_text": str(metadata.get("instructions_excerpt") or ""),
        "instructions_digest": str(metadata.get("instructions_digest") or ""),
        "instructions_truncated": False,
        "docs": docs,
        "skills": skills,
    }


def restore_environment_context_state(runtime: Any, state: Dict[str, Any]) -> None:
    snapshot = state.get("environment_context_snapshot")
    runtime._environment_context_snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}
    history: List[Dict[str, str]] = []
    for item in list(state.get("environment_context_history") or []):
        normalized = normalized_history_item(item)
        if normalized is not None:
            history.append(normalized)
    runtime._environment_context_history = history[-16:]


def restore_memory_context_state(runtime: Any, state: Dict[str, Any]) -> None:
    snapshot = state.get("memory_context_snapshot")
    runtime._memory_context_snapshot = dict(snapshot) if isinstance(snapshot, dict) else {}


def restore_file_read_guard_state(runtime: Any, state: Dict[str, Any]) -> None:
    tool_registry_runtime.restore_file_read_guard_state(getattr(runtime, "tools", None), state)


def current_datetime(runtime: Any) -> datetime:
    provider = runtime._current_dt_provider
    if callable(provider):
        current_dt = provider()
        if isinstance(current_dt, datetime):
            return current_dt
    return local_datetime_with_timezone()


def subagent_context_text(runtime: Any) -> str | None:
    provider_status = dict(runtime.agent.provider_status() or {})
    lines: List[str] = []
    for role_name in ("subagent", "teammate"):
        summary = str(provider_status.get(f"delegate_{role_name}") or "").strip()
        if summary:
            lines.append(f"{role_name}: {summary}")
    return "\n".join(lines) if lines else None


def delegated_planner_input_items(runtime: Any) -> List[Dict[str, Any]]:
    current_dt = current_datetime(runtime)
    _, environment_snapshot = environment_context_turn_update(runtime, current_dt=current_dt)
    pending_context_messages, pending_context_items, workspace_snapshot = workspace_context_turn_update(runtime)
    prelude_items = runtime._planner_context_input_items(
        environment_snapshot=environment_snapshot,
        workspace_snapshot=workspace_snapshot,
        pending_context_messages=pending_context_messages,
        pending_context_items=pending_context_items,
        environment_baseline_missing=True,
        workspace_baseline_missing=True,
    )
    return [
        *runtime._planner_conversation_input_items(),
        *prelude_items,
    ]


def environment_context_turn_update(
    runtime: Any,
    *,
    current_dt: datetime | None = None,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    forced_snapshot = dict(runtime._forced_environment_context_snapshot or {})
    if forced_snapshot:
        current_snapshot = forced_snapshot
    else:
        provider_status = runtime.agent.provider_status()
        shell_program = (
            str(provider_status.get("shell_program") or "").strip()
            or str(provider_status.get("shell_kind") or "").strip()
            or str(provider_status.get("platform_os") or "").strip()
            or "-"
        )
        current_snapshot = build_environment_context_snapshot(
            cwd=str(runtime.cwd),
            shell=shell_program,
            network_access=runtime.web_access_allowed(),
            current_dt=current_dt,
            subagents=subagent_context_text(runtime),
        )
    previous_snapshot = dict(runtime._environment_context_snapshot or {})
    update_message = render_environment_context_update_message(previous_snapshot, current_snapshot)
    messages: List[Dict[str, str]] = []
    if update_message:
        messages.append({"role": "user", "content": update_message})
    return messages, current_snapshot


def workspace_context_turn_update(
    runtime: Any,
) -> Tuple[List[Dict[str, str]], List[ReferenceContextItem], Dict[str, Any]]:
    forced_snapshot = dict(runtime._forced_workspace_context_snapshot or {})
    if forced_snapshot:
        current_snapshot = forced_snapshot
    else:
        current_snapshot = build_workspace_reference_snapshot(
            runtime.cwd,
            extra_skill_roots=workspace_skill_roots(runtime),
        )
    workspace_context = getattr(runtime, "thread_workspace_context", None)
    if workspace_context is not None:
        workspace_root = str(getattr(workspace_context, "workspace_root", "") or "").strip()
        if workspace_root:
            current_snapshot["workspace_root"] = workspace_root
        workspace_root_source = str(getattr(workspace_context, "workspace_root_source", "") or "").strip()
        if workspace_root_source:
            current_snapshot["workspace_root_source"] = workspace_root_source
    memory_messages, memory_items, memory_snapshot = memory_context_turn_update(runtime)
    runtime._memory_context_snapshot = dict(memory_snapshot or {})
    has_workspace_context = bool(
        str(current_snapshot.get("instructions_digest") or "").strip()
        or list(current_snapshot.get("docs") or [])
        or list(current_snapshot.get("skills") or [])
    )
    if not has_workspace_context:
        return list(memory_messages or []), list(memory_items or []), current_snapshot
    previous_snapshot = dict(runtime._workspace_context_snapshot or {})
    update_message = render_workspace_context_update_message(previous_snapshot, current_snapshot)
    context_messages: List[Dict[str, str]] = []
    if update_message:
        context_messages.append({"role": "user", "content": update_message})
    context_items: List[ReferenceContextItem] = []
    context_item_payload = build_workspace_reference_context_item(previous_snapshot, current_snapshot)
    if isinstance(context_item_payload, dict):
        context_items.append(ReferenceContextItem.from_dict(context_item_payload))
    context_messages.extend(list(memory_messages or []))
    context_items.extend(list(memory_items or []))
    return context_messages, context_items, current_snapshot
