from __future__ import annotations

from typing import Any


def snake_to_camel(value: str) -> str:
    text = str(value or "").strip()
    if not text or "_" not in text:
        return text
    first, *rest = text.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest if part)


def booleanish(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def status_value(value: Any) -> Any:
    normalized = str(value or "").strip().lower()
    mapping = {
        "in_progress": "inProgress",
        "not_loaded": "notLoaded",
        "system_error": "systemError",
    }
    return mapping.get(normalized, snake_to_camel(normalized))


def thread_status_value(value: Any) -> Any:
    if isinstance(value, dict):
        payload = dict(value)
        item_type = str(payload.get("type") or "").strip().lower()
        if item_type == "active":
            flags = [
                snake_to_camel(str(item or ""))
                for item in list(payload.get("active_flags") or [])
                if str(item or "").strip()
            ]
            return {"type": "active", "activeFlags": flags}
        return payload
    return status_value(value)


def thread_source_value(value: Any) -> Any:
    if isinstance(value, dict):
        payload = dict(value)
        sub_agent = str(payload.get("subAgent") or payload.get("sub_agent") or "").strip().lower()
        return {"subAgent": sub_agent} if sub_agent else "unknown"
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "cli"
    if normalized in {"cli", "vscode", "exec", "unknown"}:
        return normalized
    if normalized == "vs_code":
        return "vscode"
    if normalized in {"mcp", "app_server", "appserver"}:
        return "appServer"
    if normalized.startswith("sub_agent:") or normalized.startswith("subagent:"):
        _, _, suffix = normalized.partition(":")
        suffix = suffix.strip()
        if suffix:
            return {"subAgent": suffix}
    if normalized in {"review", "compact", "memory_consolidation"}:
        return {"subAgent": normalized}
    return "unknown"


def turn_status_value(turn: dict[str, Any]) -> str:
    status = dict(turn.get("status") or {})
    if bool(status.get("interrupted")):
        return "interrupted"
    if status.get("error") not in (None, "", False):
        return "failed"
    return "completed"


def turn_item_type(value: str) -> str:
    mapping = {
        "agent_message": "agentMessage",
        "command_execution": "commandExecution",
        "mcp_tool_call": "mcpToolCall",
        "todo_list": "todoList",
        "function_call": "functionCall",
        "function_call_output": "functionCallOutput",
        "custom_tool_call": "customToolCall",
        "custom_tool_call_output": "customToolCallOutput",
        "shell_call": "shellCall",
        "shell_call_output": "shellCallOutput",
        "local_shell_call": "localShellCall",
        "local_shell_call_output": "localShellCallOutput",
        "user_message": "userMessage",
    }
    normalized = str(value or "").strip().lower()
    return mapping.get(normalized, snake_to_camel(normalized))


def string_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    items: list[str] = []
    for raw_item in values:
        if isinstance(raw_item, dict):
            text = str(raw_item.get("text") or "").strip()
        else:
            text = str(raw_item or "").strip()
        if text:
            items.append(text)
    return items


def reasoning_content_list(payload: dict[str, Any]) -> list[str]:
    content = payload.get("content")
    items = string_list(content)
    if items:
        return items
    text = str(payload.get("text") or "").strip()
    return [text] if text else []


def reasoning_summary_list(payload: dict[str, Any]) -> list[str]:
    summary = payload.get("summary")
    items = string_list(summary)
    if items:
        return items
    text = str(payload.get("text") or "").strip()
    return [text] if text else []


def reasoning_effort_options(
    item: dict[str, Any],
    *,
    supports_reasoning: bool,
) -> list[dict[str, Any]]:
    raw_items = item.get("supported_reasoning_efforts")
    if not isinstance(raw_items, list):
        raw_items = item.get("supportedReasoningEfforts")
    explicit_list_declared = isinstance(raw_items, list)
    values: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        for raw_entry in raw_items:
            if isinstance(raw_entry, dict):
                effort = str(
                    raw_entry.get("reasoningEffort") or raw_entry.get("reasoning_effort") or ""
                ).strip().lower()
                description = str(raw_entry.get("description") or "").strip()
            else:
                effort = str(raw_entry or "").strip().lower()
                description = ""
            if not effort:
                continue
            values.append(
                {
                    "reasoningEffort": effort,
                    "description": description or f"{effort} reasoning effort.",
                }
            )
    if explicit_list_declared:
        return values
    if not supports_reasoning:
        return []
    return [
        {"reasoningEffort": "low", "description": "Low reasoning effort."},
        {"reasoningEffort": "medium", "description": "Medium reasoning effort."},
        {"reasoningEffort": "high", "description": "High reasoning effort."},
    ]


def input_modalities(item: dict[str, Any]) -> list[str]:
    raw_items = item.get("input_modalities")
    if not isinstance(raw_items, list):
        raw_items = item.get("inputModalities")
    values = [str(raw_item or "").strip().lower() for raw_item in list(raw_items or [])]
    normalized = [value for value in values if value in {"text", "image"}]
    return normalized or ["text"]


def reasoning_effort_value(value: Any, *, default: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        return normalized
    return default


def camelized_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {snake_to_camel(str(key)): camelized_mapping(item) for key, item in value.items()}
    if isinstance(value, list):
        return [camelized_mapping(item) for item in value]
    return value


def observable_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    normalized_result = dict(result or {})
    structured_content = normalized_result.get("structuredContent")
    if isinstance(structured_content, dict):
        next_structured = dict(structured_content)
        plugin_observability = next_structured.pop("plugin_observability", None)
        if isinstance(plugin_observability, dict):
            next_structured["pluginObservability"] = camelized_mapping(plugin_observability)
        structured_payload = next_structured.pop("structured_payload", None)
        if structured_payload is not None:
            next_structured["structuredPayload"] = structured_payload
        normalized_result["structuredContent"] = next_structured
    return normalized_result


def model_list_entry_payload(
    item: dict[str, Any],
    *,
    current_model_tokens: set[str],
    default_reasoning_effort: str,
) -> dict[str, Any]:
    model_key = str(item.get("model_key") or "").strip()
    model_id = str(item.get("model_id") or "").strip()
    display_name = str(item.get("display_name") or model_id or model_key).strip()
    provider_name = str(item.get("provider_name") or "").strip()
    supports_reasoning = booleanish(item.get("supports_reasoning"))
    hidden = booleanish(item.get("hidden"))
    if "show_in_picker" in item:
        hidden = not booleanish(item.get("show_in_picker"), default=True)
    supported_reasoning_efforts = reasoning_effort_options(
        item,
        supports_reasoning=supports_reasoning,
    )
    default_effort = reasoning_effort_value(
        item.get("default_reasoning_effort") or item.get("defaultReasoningEffort"),
        default=str(default_reasoning_effort or "medium"),
    )
    if not supported_reasoning_efforts:
        default_effort = ""
    availability_nux = item.get("availability_nux")
    upgrade_info = item.get("upgrade_info")
    return {
        "id": model_key or model_id,
        "model": model_id or model_key,
        "displayName": display_name,
        "description": f"{provider_name} | {str(item.get('planner_kind') or '-').strip()}",
        "hidden": hidden,
        "supportedReasoningEfforts": supported_reasoning_efforts,
        "defaultReasoningEffort": default_effort,
        "inputModalities": input_modalities(item),
        "supportsPersonality": booleanish(item.get("supports_personality")),
        "isDefault": bool({model_key, model_id} & current_model_tokens),
        "availabilityNux": dict(availability_nux) if isinstance(availability_nux, dict) else None,
        "upgrade": str(item.get("upgrade") or "").strip() or None,
        "upgradeInfo": dict(upgrade_info) if isinstance(upgrade_info, dict) else None,
        "providerName": provider_name,
        "modelKey": model_key,
        "wireApi": str(item.get("wire_api") or ""),
        "plannerKind": str(item.get("planner_kind") or ""),
    }


def mcp_server_status_entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    status = str(entry.get("status") or entry.get("projection_state") or "").strip().lower()
    auth_status = "unsupported"
    if "auth" in status or "login" in status:
        auth_status = "notLoggedIn"
    return {
        "name": str(entry.get("name") or ""),
        "tools": {},
        "resources": [],
        "resourceTemplates": [],
        "authStatus": auth_status,
        "rawStatus": str(entry.get("status") or ""),
        "enabled": bool(entry.get("enabled", True)),
        "scope": str(entry.get("scope") or ""),
        "source": str(entry.get("source") or ""),
    }
