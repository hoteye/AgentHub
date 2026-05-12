from __future__ import annotations

import os
from typing import Any, Callable


LEGACY_PROVIDER_TOOL_SPECS_MODEL_VISIBLE_ENV = "AGENTHUB_LEGACY_PROVIDER_TOOL_SPECS_MODEL_VISIBLE"
_MODEL_VISIBLE_VALUES = frozenset({"model_visible", "model-visible", "visible"})


def _truthy(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def provider_tool_function_name(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    function_block = item.get("function")
    if isinstance(function_block, dict):
        function_name = str(function_block.get("name") or "").strip()
        if function_name:
            return function_name
    return str(item.get("name") or "").strip()


def _normalized_plugin_capability_rows(plugin: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attr_name in ("capability_declarations", "plugin_capability_declarations"):
        items = getattr(plugin, attr_name, None)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                rows.append(dict(item))
    return rows


def plugin_declared_model_visible_tool_names(plugin: Any) -> set[str]:
    declared: set[str] = set()
    for item in _normalized_plugin_capability_rows(plugin):
        tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
        if not tool_name:
            continue
        profiles = item.get("supported_profiles")
        visibility = str(item.get("default_visibility") or "").strip().lower()
        if isinstance(profiles, (list, tuple)) and any(str(v or "").strip() for v in profiles) and visibility in _MODEL_VISIBLE_VALUES:
            declared.add(tool_name)
    return declared


def _has_declared_provider_tool_capability(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    capability_id = str(item.get("capability_id") or "").strip()
    if capability_id:
        return True
    capability_block = item.get("capability")
    if isinstance(capability_block, dict):
        if str(capability_block.get("capability_id") or "").strip():
            return True
        profiles = capability_block.get("supported_profiles")
        if isinstance(profiles, (list, tuple)) and any(str(v or "").strip() for v in profiles):
            return True
        visibility = str(capability_block.get("default_visibility") or "").strip().lower()
        if visibility in _MODEL_VISIBLE_VALUES:
            return True
    profiles = item.get("supported_profiles")
    if isinstance(profiles, (list, tuple)) and any(str(v or "").strip() for v in profiles):
        return True
    visibility = str(item.get("default_visibility") or "").strip().lower()
    if visibility in _MODEL_VISIBLE_VALUES:
        return True
    return False


def provider_tool_model_visible(
    item: Any,
    *,
    declared_tool_names: set[str] | None = None,
) -> tuple[bool, str]:
    function_name = provider_tool_function_name(item)
    if function_name and function_name in (declared_tool_names or set()):
        return True, "external_declaration"
    if _has_declared_provider_tool_capability(item):
        return True, "declared_capability"
    if _truthy(os.environ.get(LEGACY_PROVIDER_TOOL_SPECS_MODEL_VISIBLE_ENV)):
        return True, "legacy_override"
    return False, "legacy_hidden_undeclared"


def provider_tool_compat_warning(*, plugin_name: str, tool_name: str, reason: str) -> str:
    return (
        "plugin legacy provider_tool_specs hidden from model-facing tools: "
        f"plugin={plugin_name or '-'} tool={tool_name or '-'} reason={reason}"
    )


def collect_hidden_legacy_provider_tool_warnings(
    plugins: list[Any],
    *,
    hook_items_fn: Callable[[Any, str], list[Any]],
) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for plugin in plugins:
        if not plugin.is_active():
            continue
        plugin_name = str(getattr(plugin, "plugin_name", "") or "").strip()
        declared_tool_names = plugin_declared_model_visible_tool_names(plugin)
        for item in hook_items_fn(plugin.provider_hooks, "tool_specs"):
            tool_name = provider_tool_function_name(item)
            visible, reason = provider_tool_model_visible(item, declared_tool_names=declared_tool_names)
            if visible:
                continue
            warning = provider_tool_compat_warning(
                plugin_name=plugin_name,
                tool_name=tool_name,
                reason=reason,
            )
            if warning in seen:
                continue
            seen.add(warning)
            warnings.append(warning)
    return warnings
