from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from cli.agent_cli.memory_extraction_runtime import (
    extract_memory_candidates_from_last_turn,
    preview_payload_from_candidate,
)
from cli.agent_cli.memory_store import MemoryStore
from cli.agent_cli import memory_types
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.runtime_core import memory_commands_helpers as _memory_commands_helpers


def _memory_store(runtime: Any) -> MemoryStore:
    store = getattr(runtime, "_memory_store", None)
    if isinstance(store, MemoryStore):
        return store
    fallback = getattr(runtime, "memory_store", None)
    if isinstance(fallback, MemoryStore):
        setattr(runtime, "_memory_store", fallback)
        return fallback
    created = MemoryStore.default()
    setattr(runtime, "_memory_store", created)
    return created


def _normalized_scope(raw_scope: Any) -> str:
    scope = str(raw_scope or "").strip()
    if not scope:
        return "project"
    return memory_types.normalize_memory_scope(scope)


def _scope_store(runtime: Any, *, scope: str) -> Tuple[Optional[MemoryStore], Optional[str]]:
    normalized_scope = _normalized_scope(scope)
    if normalized_scope != "user":
        return _memory_store(runtime), None
    try:
        user_store = MemoryStore.default(scope="user")
    except PermissionError:
        return (
            None,
            "memory user scope requires explicit opt-in; set AGENTHUB_MEMORY_USER_SCOPE_ENABLED=true",
        )
    return user_store, None


def _safe_parse_args(runtime: Any, arg_text: str) -> Tuple[List[str], Dict[str, Any]]:
    parser = getattr(runtime, "_parse_args", None)
    if callable(parser):
        return parser(arg_text)
    return parse_args(arg_text)


def _positional_option_value(positionals: List[str], *, key: str) -> Optional[str]:
    return _memory_commands_helpers.positional_option_value(positionals, key=key)


def _option_text(
    options: Dict[str, Any],
    positionals: List[str],
    *,
    key: str,
    default: str = "",
) -> str:
    return _memory_commands_helpers.option_text(
        options,
        positionals,
        key=key,
        default=default,
    )


def _trimmed(text: Any, *, max_chars: int = 200) -> str:
    return _memory_commands_helpers.trimmed(text, max_chars=max_chars)


def _latest_turn(runtime: Any) -> Optional[Dict[str, Any]]:
    turns = list(getattr(runtime, "history_turns", []) or [])
    for turn in reversed(turns):
        if isinstance(turn, dict):
            return turn
    return None


def _extract_path_hints(runtime: Any, *, limit: int = 5) -> List[str]:
    hints: List[str] = []
    seen: set[str] = set()
    for item in reversed(list(getattr(runtime, "reference_context_items", []) or [])):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        hints.append(path)
        if len(hints) >= limit:
            break
    hints.reverse()
    return hints


def _writeback_policy(runtime: Any) -> Dict[str, Any]:
    policy = getattr(runtime, "_memory_auto_writeback_policy", None)
    if isinstance(policy, dict):
        return dict(policy)
    fallback = getattr(runtime, "memory_auto_writeback_policy", None)
    if isinstance(fallback, dict):
        return dict(fallback)
    return {}


def _last_turn_candidates(
    runtime: Any,
    *,
    memory_type: str = "project",
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    turn = _latest_turn(runtime)
    if not isinstance(turn, dict):
        return None, []
    candidates = extract_memory_candidates_from_last_turn(
        turn=turn,
        memory_type=memory_type,
        paths=_extract_path_hints(runtime),
    )
    return turn, candidates


def _render_preview_candidate(candidate: Dict[str, Any]) -> str:
    preview = preview_payload_from_candidate(candidate)
    normalized = dict(candidate or {})
    tags = ",".join(str(item) for item in list(preview.get("tags") or []) if str(item).strip()) or "-"
    paths = ",".join(str(item) for item in list(preview.get("paths") or []) if str(item).strip()) or "-"
    reasons = ",".join(str(item) for item in list(preview.get("reasons") or []) if str(item).strip()) or "-"
    blocked_reason = str(preview.get("blocked_reason") or "").strip() or "-"
    decision = str(normalized.get("decision") or "review").strip() or "review"
    decision_reason = str(normalized.get("decision_reason") or "low_signal_short_content").strip() or "low_signal_short_content"
    return (
        "memory preview\n"
        f"type={preview.get('memory_type') or '-'}\n"
        f"title={preview.get('title') or '-'}\n"
        f"summary={preview.get('summary') or '-'}\n"
        f"paths={paths}\n"
        f"tags={tags}\n"
        f"reasons={reasons}\n"
        f"blocked_sensitive={'true' if preview.get('blocked_sensitive') else 'false'}\n"
        f"blocked_reason={blocked_reason}\n"
        f"decision={decision}\n"
        f"decision_reason={decision_reason}"
    )


def _preview_from_last_turn(runtime: Any, *, memory_type: str = "project") -> Tuple[str, List[Any]]:
    _turn, candidates = _last_turn_candidates(runtime, memory_type=memory_type)
    if not candidates:
        return ("memory preview failed: latest turn has no extractable candidate", [])
    candidate = dict(candidates[0])
    return (_render_preview_candidate(candidate), [])


def _save_from_last_turn(
    runtime: Any,
    *,
    memory_type: str = "project",
    scope: str = "project",
    store: Optional[MemoryStore] = None,
    auto_writeback: bool = False,
) -> Tuple[str, List[Any]]:
    turn, candidates = _last_turn_candidates(runtime, memory_type=memory_type)
    if not isinstance(turn, dict):
        return ("memory save failed: no completed turn available", [])
    if not candidates:
        return ("memory save failed: latest turn has no extractable candidate", [])
    candidate = dict(candidates[0])
    candidate_type = str(candidate.get("memory_type") or memory_type or "project")
    decision = str(candidate.get("decision") or "review").strip() or "review"
    decision_reason = str(candidate.get("decision_reason") or "low_signal_short_content").strip() or "low_signal_short_content"
    if auto_writeback and not memory_types.memory_auto_writeback_enabled(
        scope=scope,
        memory_type=candidate_type,
        policy=_writeback_policy(runtime),
    ):
        return ("memory save blocked: auto_writeback_policy_disabled", [])
    if decision == "block" or bool(candidate.get("blocked_sensitive")):
        blocked_reason = str(candidate.get("blocked_reason") or "").strip() or decision_reason or "contains_sensitive_content"
        return (f"memory save blocked: {blocked_reason}", [])
    payload: Dict[str, Any] = {
        "scope": _normalized_scope(scope),
        "memory_type": candidate_type,
        "title": str(candidate.get("title") or "").strip(),
        "summary": str(candidate.get("summary") or "").strip(),
        "body": str(candidate.get("body") or "").strip(),
        "tags": list(candidate.get("tags") or []),
        "paths": list(candidate.get("paths") or []),
        "source_thread_id": str(getattr(runtime, "thread_id", "") or "").strip(),
        "source_turn_id": str(turn.get("turn_id") or "").strip(),
        "status": "active",
        "salience": 0.5,
        "metadata": {
            "writeback_decision": decision,
            "writeback_reason": decision_reason,
            "writeback_mode": "auto" if auto_writeback else "manual",
        },
    }
    target_store = store if isinstance(store, MemoryStore) else _memory_store(runtime)
    saved = target_store.upsert_memory(payload)
    return (
        "memory saved\n"
        f"memory_id={saved.get('memory_id') or '-'}\n"
        f"scope={saved.get('scope') or '-'}\n"
        f"type={saved.get('memory_type') or '-'}\n"
        f"title={saved.get('title') or '-'}",
        [],
    )


def _render_memory_list(items: List[Dict[str, Any]]) -> str:
    return _memory_commands_helpers.render_memory_list(items)


def _render_memory_show(item: Dict[str, Any]) -> str:
    return _memory_commands_helpers.render_memory_show(item)


def _render_recalled_memory_debug(runtime: Any, *, limit: int = 20) -> str:
    return _memory_commands_helpers.render_recalled_memory_debug(runtime, limit=limit)


def handle_memory_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
) -> Optional[Tuple[str, List[Any]]]:
    if name != "memory":
        return None
    positionals, options = _safe_parse_args(runtime, arg_text)
    if not positionals:
        return ("Usage: /memory <list|show|preview|save|delete|debug> [args]", [])
    action = str(positionals[0] or "").strip().lower()
    store = _memory_store(runtime)
    if action == "list":
        limit = int(_option_text(options, positionals, key="limit", default="20") or 20)
        status = _option_text(options, positionals, key="status", default="active") or "active"
        scope = _normalized_scope(_option_text(options, positionals, key="scope", default="project"))
        scoped_store, error_text = _scope_store(runtime, scope=scope)
        if scoped_store is None:
            return (error_text or "memory list failed", [])
        memory_type = _option_text(options, positionals, key="type", default="") or None
        items = scoped_store.list_memories(limit=limit, status=status, scope=scope, memory_type=memory_type)
        return (_render_memory_list(items), [])
    if action == "show":
        memory_id = str(positionals[1] if len(positionals) > 1 else "").strip()
        if not memory_id:
            return ("Usage: /memory show <memory_id>", [])
        scope = _normalized_scope(_option_text(options, positionals, key="scope", default="project"))
        scoped_store, error_text = _scope_store(runtime, scope=scope)
        if scoped_store is None:
            return (error_text or "memory show failed", [])
        item = scoped_store.get_memory(memory_id)
        if not isinstance(item, dict):
            return (f"memory not found: {memory_id}", [])
        return (_render_memory_show(item), [])
    if action == "preview":
        from_last_turn = bool(options.get("from-last-turn"))
        if not from_last_turn:
            return ("Usage: /memory preview from-last-turn [type <project|user|reference|feedback>]", [])
        memory_type = str(options.get("type") or "project").strip() or "project"
        return _preview_from_last_turn(runtime, memory_type=memory_type)
    if action == "save":
        from_last_turn = bool(options.get("from-last-turn"))
        if not from_last_turn:
            return ("Usage: /memory save from-last-turn [type <project|user|reference|feedback>]", [])
        scope = _normalized_scope(_option_text(options, positionals, key="scope", default="project"))
        scoped_store, error_text = _scope_store(runtime, scope=scope)
        if scoped_store is None:
            return (error_text or "memory save failed", [])
        memory_type = _option_text(options, positionals, key="type", default="project") or "project"
        normalized_type = memory_types.normalize_memory_type(memory_type)
        if scope == "user" and normalized_type != "user":
            return ("memory save failed: scope user requires type user", [])
        return _save_from_last_turn(
            runtime,
            memory_type=normalized_type,
            scope=scope,
            store=scoped_store,
        )
    if action == "delete":
        memory_id = str(positionals[1] if len(positionals) > 1 else "").strip()
        if not memory_id:
            return ("Usage: /memory delete <memory_id>", [])
        deleted = store.delete_memory(memory_id)
        if not deleted:
            return (f"memory delete failed: {memory_id}", [])
        return (f"memory deleted: {memory_id}", [])
    if action == "debug":
        limit = int(str(options.get("limit") or "20").strip() or 20)
        return (_render_recalled_memory_debug(runtime, limit=limit), [])
    return ("Usage: /memory <list|show|preview|save|delete|debug> [args]", [])
