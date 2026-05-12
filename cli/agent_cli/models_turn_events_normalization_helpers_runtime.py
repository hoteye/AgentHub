from __future__ import annotations

from typing import Any

from cli.agent_cli.models_turn_events_pure_helpers_runtime import (
    mapping_dict,
    normalized_slug,
    normalized_text,
)


_PLUGIN_DECLARATION_CANONICAL_KEY = "plugin_capability_declaration"
_PLUGIN_DECLARATION_COMPATIBILITY_KEYS = (
    "pluginCapabilityDeclaration",
    "x_agenthub_plugin_capability",
    "x_plugin_capability",
)
_PLUGIN_DECLARATION_TOP_LEVEL_FIELDS = frozenset(
    {
        "capability_id",
        "tool_name",
        "plugin_name",
        "config_name",
        "source_kind",
        "kind",
        "canonical_family",
        "canonical_family_source",
        "canonical_family_owner",
        "canonical_family_alias_input",
        "tool_capability_kind",
        "tool_runtime_binding",
        "canonical_family_record",
    }
)
_PLUGIN_RESULT_CONTAINER_KEYS = ("result", "data", "output")
_PLUGIN_OBSERVABILITY_CONTRACT = "dynamic_plugin_tool_v1"


def _plugin_declaration_contract_metadata(declaration: dict[str, Any]) -> dict[str, Any]:
    record_mapping = mapping_dict(declaration.get("canonical_family_record"))
    return {
        "canonical_family": normalized_text(declaration.get("canonical_family") or record_mapping.get("canonical_family")),
        "canonical_family_source": normalized_text(
            declaration.get("canonical_family_source") or record_mapping.get("family_source")
        ),
        "canonical_family_owner": normalized_text(
            declaration.get("canonical_family_owner") or record_mapping.get("family_owner")
        ),
        "canonical_family_alias_input": normalized_text(declaration.get("canonical_family_alias_input")),
        "tool_capability_kind": normalized_text(
            declaration.get("tool_capability_kind") or record_mapping.get("tool_capability_kind")
        ),
        "tool_runtime_binding": normalized_text(
            declaration.get("tool_runtime_binding") or record_mapping.get("tool_runtime_binding")
        ),
    }


def _plugin_declaration_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get(_PLUGIN_DECLARATION_CANONICAL_KEY)
    if isinstance(candidate, dict):
        return dict(candidate)
    for key in _PLUGIN_DECLARATION_COMPATIBILITY_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            return dict(candidate)
    provider_raw_item = payload.get("provider_raw_item")
    if isinstance(provider_raw_item, dict):
        for key in ("x_agenthub_plugin_capability", "x_plugin_capability"):
            candidate = provider_raw_item.get(key)
            if isinstance(candidate, dict):
                return dict(candidate)
    if any(key in payload for key in _PLUGIN_DECLARATION_TOP_LEVEL_FIELDS):
        return {key: value for key, value in dict(payload or {}).items() if key in _PLUGIN_DECLARATION_TOP_LEVEL_FIELDS}
    return {}


def _plugin_result_structured_payload(payload: dict[str, Any]) -> dict[str, Any]:
    explicit = payload.get("structured_payload")
    if isinstance(explicit, dict):
        return dict(explicit)
    for key in _PLUGIN_RESULT_CONTAINER_KEYS:
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def _plugin_observable_origin(*, tool_capability_kind: str, tool_runtime_binding: str, source_kind: str) -> str:
    if tool_capability_kind == "provider_native_tool" or tool_runtime_binding == "provider_native":
        return "provider_native"
    if tool_capability_kind == "message_native_capability":
        return "message_native"
    if tool_capability_kind == "ui_only_capability":
        return "ui_only"
    if tool_runtime_binding == "plugin_mcp_server" or source_kind == "mcp_server":
        return "mcp_server"
    return "local_runtime"


def _plugin_observable_server(
    payload: dict[str, Any],
    *,
    plugin_name: str,
    config_name: str,
    origin: str,
) -> str:
    if origin == "provider_native":
        return "provider_native"
    if origin == "mcp_server":
        provider_raw_item = mapping_dict(payload.get("provider_raw_item"))
        for candidate in (
            payload.get("server"),
            payload.get("server_name"),
            payload.get("mcp_server"),
            payload.get("mcp_server_name"),
            provider_raw_item.get("server"),
            provider_raw_item.get("server_name"),
            provider_raw_item.get("mcp_server"),
            provider_raw_item.get("mcp_server_name"),
            config_name,
            plugin_name,
            "mcp",
        ):
            text = normalized_text(candidate)
            if text:
                return text
    return normalized_text(payload.get("server")) or "local"


def normalized_plugin_observability_from_payload(
    payload: dict[str, Any] | None,
    *,
    tool_name: str,
) -> dict[str, Any] | None:
    raw_payload = dict(payload or {})
    declaration = _plugin_declaration_candidate(raw_payload)
    if not declaration:
        return None
    declaration_metadata = _plugin_declaration_contract_metadata(declaration)
    canonical_family = normalized_slug(declaration_metadata.get("canonical_family"))
    tool_capability_kind = normalized_slug(declaration_metadata.get("tool_capability_kind"))
    tool_runtime_binding = normalized_slug(declaration_metadata.get("tool_runtime_binding"))
    plugin_name = normalized_text(declaration.get("plugin_name") or raw_payload.get("plugin_name"))
    config_name = normalized_text(declaration.get("config_name") or raw_payload.get("config_name"))
    source_kind = normalized_slug(
        declaration.get("source_kind")
        or declaration.get("kind")
        or raw_payload.get("source_kind")
        or raw_payload.get("kind")
    )
    capability_id = normalized_text(declaration.get("capability_id") or raw_payload.get("capability_id"))
    resolved_tool_name = normalized_text(declaration.get("tool_name") or raw_payload.get("tool_name") or tool_name)
    canonical_family_source = normalized_slug(
        declaration.get("canonical_family_source") or declaration_metadata.get("canonical_family_source")
    )
    canonical_family_owner = normalized_text(
        declaration.get("canonical_family_owner") or declaration_metadata.get("canonical_family_owner")
    )
    canonical_family_alias_input = normalized_text(
        declaration.get("canonical_family_alias_input") or declaration_metadata.get("canonical_family_alias_input")
    )
    if not any(
        (
            canonical_family,
            tool_capability_kind,
            tool_runtime_binding,
            plugin_name,
            config_name,
            source_kind,
            capability_id,
        )
    ):
        return None
    origin = _plugin_observable_origin(
        tool_capability_kind=tool_capability_kind,
        tool_runtime_binding=tool_runtime_binding,
        source_kind=source_kind,
    )
    observable = {
        "contract": _PLUGIN_OBSERVABILITY_CONTRACT,
        "tool_name": resolved_tool_name,
        "plugin_name": plugin_name,
        "config_name": config_name,
        "source_kind": source_kind,
        "capability_id": capability_id,
        "canonical_family": canonical_family,
        "canonical_family_source": canonical_family_source,
        "canonical_family_owner": canonical_family_owner,
        "canonical_family_alias_input": canonical_family_alias_input,
        "tool_capability_kind": tool_capability_kind,
        "tool_runtime_binding": tool_runtime_binding,
        "origin": origin,
        "server_name": _plugin_observable_server(
            raw_payload,
            plugin_name=plugin_name,
            config_name=config_name,
            origin=origin,
        ),
    }
    return {key: value for key, value in observable.items() if value not in ("", None, [], {})}


def plugin_result_validation_error(
    payload: dict[str, Any] | None,
    *,
    summary: str,
    tool_name: str,
) -> str:
    plugin_observability = normalized_plugin_observability_from_payload(payload, tool_name=tool_name)
    if plugin_observability is None:
        return ""
    if not normalized_text(summary):
        return "dynamic plugin tool result missing canonical summary"
    if not _plugin_result_structured_payload(dict(payload or {})):
        return "dynamic plugin tool result missing canonical structured payload"
    return ""


def canonical_plugin_tool_structured_content(
    payload: dict[str, Any] | None,
    *,
    tool_name: str,
    status: str,
    summary: str,
) -> dict[str, Any] | None:
    raw_payload = dict(payload or {})
    plugin_observability = normalized_plugin_observability_from_payload(raw_payload, tool_name=tool_name)
    if plugin_observability is None:
        return raw_payload or None
    structured_content = dict(raw_payload)
    structured_content["status"] = normalized_text(status) or "completed"
    structured_content["summary"] = normalized_text(summary)
    structured_content["structured_payload"] = _plugin_result_structured_payload(raw_payload)
    structured_content["plugin_observability"] = plugin_observability
    declaration = _plugin_declaration_candidate(raw_payload)
    if declaration:
        structured_content.setdefault(_PLUGIN_DECLARATION_CANONICAL_KEY, declaration)
    structured_content.setdefault("tool_name", normalized_text(tool_name))
    return structured_content


def _plan_step_status(value: Any) -> str:
    normalized = normalized_slug(value)
    if normalized in {"completed", "done"}:
        return "completed"
    if normalized in {"in_progress", "in-progress", "inprogress", "running", "active"}:
        return "in_progress"
    return "pending"


def _normalized_plan_steps(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    plan_items = source.get("plan")
    if not isinstance(plan_items, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in plan_items:
        if not isinstance(entry, dict):
            continue
        text = normalized_text(entry.get("step"))
        if not text:
            continue
        items.append({"step": text, "status": _plan_step_status(entry.get("status"))})
    return items


def normalized_plan_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(payload or {}) if isinstance(payload, dict) else {}
    normalized_payload: dict[str, Any] = {}
    explanation = normalized_text(source.get("explanation"))
    if explanation:
        normalized_payload["explanation"] = explanation
    plan = _normalized_plan_steps(payload)
    if plan:
        normalized_payload["plan"] = plan
    return normalized_payload


def plan_payload_from_todo_list_item(item: dict[str, Any] | None) -> dict[str, Any]:
    item_source = dict(item or {}) if isinstance(item, dict) else {}
    payload = normalized_plan_payload(item_source)
    if list(payload.get("plan") or []):
        return payload

    plan: list[dict[str, Any]] = []
    for entry in list(item_source.get("items") or []):
        if not isinstance(entry, dict):
            continue
        text = normalized_text(entry.get("text") or entry.get("step"))
        if not text:
            continue
        status_value: Any = entry.get("status")
        if status_value in (None, "") and "completed" in entry:
            status_value = "completed" if bool(entry.get("completed")) else "pending"
        plan.append({"step": text, "status": _plan_step_status(status_value)})
    if plan:
        payload["plan"] = plan
    return payload


def todo_list_items_from_plan_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in list(normalized_plan_payload(payload).get("plan") or []):
        items.append({"text": str(entry.get("step") or ""), "completed": str(entry.get("status") or "") == "completed"})
    return items


def todo_list_turn_item_from_plan_payload(payload: dict[str, Any] | None, *, item_id: str) -> dict[str, Any]:
    item = {
        "id": str(item_id or ""),
        "type": "todo_list",
        "items": todo_list_items_from_plan_payload(payload),
    }
    source_payload = dict(payload or {}) if isinstance(payload, dict) else {}
    call_id = normalized_text(source_payload.get("provider_call_id") or source_payload.get("call_id"))
    if call_id:
        item["call_id"] = call_id
    normalized_payload = normalized_plan_payload(payload)
    explanation = normalized_text(normalized_payload.get("explanation"))
    if explanation:
        item["explanation"] = explanation
    plan = list(normalized_payload.get("plan") or [])
    if plan:
        item["plan"] = plan
    return item


def todo_list_turn_event_from_plan_payload(
    payload: dict[str, Any] | None,
    *,
    item_id: str,
    event_type: str,
) -> dict[str, Any]:
    return {
        "type": str(event_type or "item.started"),
        "item": todo_list_turn_item_from_plan_payload(payload, item_id=item_id),
    }


__all__ = [
    "canonical_plugin_tool_structured_content",
    "normalized_plan_payload",
    "normalized_plugin_observability_from_payload",
    "plan_payload_from_todo_list_item",
    "plugin_result_validation_error",
    "todo_list_items_from_plan_payload",
    "todo_list_turn_event_from_plan_payload",
    "todo_list_turn_item_from_plan_payload",
]
