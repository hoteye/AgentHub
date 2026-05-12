from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any, Callable, Dict, List, Tuple


def normalize_mapping_registration(
    item: Any,
    *,
    plugin_name: str,
    registration_type: type,
    from_mapping_fn: Callable[[Dict[str, Any]], Any],
) -> Any | None:
    if isinstance(item, registration_type):
        registration = item
    elif isinstance(item, dict):
        payload = dict(item)
        payload.setdefault("plugin_name", plugin_name)
        registration = from_mapping_fn(payload)
    else:
        return None
    if not getattr(registration, "plugin_name", None):
        registration = replace(registration, plugin_name=plugin_name)
    return registration


def normalize_workflow_handler_registration(
    item: Any,
    *,
    plugin_name: str,
    workflow_handler_type: type,
) -> Any | None:
    if isinstance(item, workflow_handler_type):
        registration = item
    elif isinstance(item, dict):
        handler = item.get("handler")
        if not callable(handler):
            return None
        registration = workflow_handler_type(
            workflow_name=str(item.get("workflow_name") or "").strip(),
            plugin_name=str(item.get("plugin_name") or plugin_name).strip(),
            handler=handler,
            description=str(item.get("description") or "").strip(),
        )
    else:
        return None
    if not registration.workflow_name or not callable(registration.handler):
        return None
    if not registration.plugin_name:
        registration = replace(registration, plugin_name=plugin_name)
    return registration


def call_runtime_builder(builder: Callable[..., Any], *, plugin_name: str) -> List[Any]:
    try:
        signature = inspect.signature(builder)
    except (TypeError, ValueError):
        result = builder()
        return list(result or [])
    kwargs: Dict[str, Any] = {}
    if "plugin_name" in signature.parameters:
        kwargs["plugin_name"] = plugin_name
    result = builder(**kwargs) if kwargs else builder()
    return list(result or [])


def ensure_unique_registration(
    seen: Dict[str, Any],
    *,
    key_name: str,
    key_value: str,
    plugin_name: str,
    item: Any,
    conflict_error_type: type[Exception],
) -> None:
    existing = seen.get(key_value)
    if existing is not None:
        existing_plugin = str(getattr(existing, "plugin_name", "") or "?")
        raise conflict_error_type(
            f"duplicate {key_name} '{key_value}' for plugin '{plugin_name}'; "
            f"already registered by plugin '{existing_plugin}'"
        )
    seen[key_value] = item


def collect_runtime_registration_items(
    *,
    runtime_hooks: Any,
    loaded_plugin_name: str,
    builder_name: str,
    normalize_fn: Callable[..., Any | None],
    key_attr: str,
    key_name: str,
    seen: Dict[str, Any],
    conflict_error_type: type[Exception],
) -> List[Any]:
    items: List[Any] = []
    builder = getattr(runtime_hooks, builder_name, None)
    if not callable(builder):
        return items
    for item in call_runtime_builder(builder, plugin_name=loaded_plugin_name):
        normalized = normalize_fn(item, plugin_name=loaded_plugin_name)
        key_value = str(getattr(normalized, key_attr, "") or "").strip() if normalized is not None else ""
        if normalized is None or not key_value:
            continue
        ensure_unique_registration(
            seen,
            key_name=key_name,
            key_value=key_value,
            plugin_name=normalized.plugin_name,
            item=normalized,
            conflict_error_type=conflict_error_type,
        )
        items.append(normalized)
    return items


def collect_workflow_handler_items(
    *,
    runtime_hooks: Any,
    loaded_plugin_name: str,
    workflow_handler_type: type,
    seen_workflow_handlers: Dict[Tuple[str, str], Any],
    conflict_error_type: type[Exception],
) -> List[Any]:
    items: List[Any] = []
    builder = getattr(runtime_hooks, "build_workflow_handlers", None)
    if not callable(builder):
        return items
    for item in call_runtime_builder(builder, plugin_name=loaded_plugin_name):
        normalized = normalize_workflow_handler_registration(
            item,
            plugin_name=loaded_plugin_name,
            workflow_handler_type=workflow_handler_type,
        )
        if normalized is None:
            continue
        workflow_key = (normalized.plugin_name, normalized.workflow_name)
        existing = seen_workflow_handlers.get(workflow_key)
        if existing is not None:
            raise conflict_error_type(
                f"duplicate workflow_name '{normalized.workflow_name}' for plugin '{normalized.plugin_name}'"
            )
        seen_workflow_handlers[workflow_key] = normalized
        items.append(normalized)
    return items
