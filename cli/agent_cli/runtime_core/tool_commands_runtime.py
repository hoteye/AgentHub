from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events


def runtime_policy_text(prefix: str, status: dict[str, Any]) -> str:
    lines = [prefix]
    for key, value in status.items():
        lines.append(f"{key}={value}")
    return "\n".join(lines)


def tools_text(payload: dict[str, Any]) -> str:
    tools = payload.get("tools") or []
    lines = [f"tools={len(tools)}"]
    for item in tools:
        lines.append(f"- {item.get('name')}: {item.get('description') or item.get('label') or '-'}")
    workspace_trust = str(payload.get("workspace_trust") or "").strip()
    if workspace_trust:
        lines.append(f"workspace_trust={workspace_trust}")
    mcp_servers = payload.get("mcp_servers") or {}
    if isinstance(mcp_servers, dict):
        lines.append(f"mcp_servers={len(mcp_servers)}")
    app_connectors = payload.get("app_connectors") or []
    if isinstance(app_connectors, list):
        lines.append(f"app_connectors={len(app_connectors)}")
    if payload.get("registry_error"):
        lines.append(f"registry_error={payload['registry_error']}")
    return "\n".join(lines)


def plugins_text(event: ToolEvent) -> str:
    plugins = (event.payload or {}).get("plugins") or []
    lines = [f"plugins: {len(plugins)}"]
    for item in plugins:
        status = "enabled" if item.get("enabled") else "disabled"
        lines.append(f"- {item.get('name')} [{status}] v{item.get('version')}")
    return "\n".join(lines)


def plugins_result(event: ToolEvent, *, structured: CommandExecutionResult | None) -> CommandExecutionResult | tuple[str, list[ToolEvent]]:
    assistant_text = plugins_text(event)
    if structured is not None:
        structured.assistant_text = assistant_text
        return structured
    return CommandExecutionResult(
        assistant_text=assistant_text,
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name="plugins",
            arguments=None,
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )


def blocked_single_event_result(
    *,
    assistant_text: str,
    event_name: str,
    summary: str,
    error: str,
    arguments: dict[str, Any],
    error_event: Any,
    single_event_result: Any,
    payload: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    return single_event_result(
        assistant_text,
        error_event(
            event_name,
            summary,
            error=error,
            **dict(payload or {}),
        ),
        arguments=arguments,
    )


def click_arguments(positionals: list[str]) -> dict[str, Any]:
    ref_id = positionals[0]
    link_id = int(positionals[1])
    return {"ref_id": ref_id, "id": link_id}


def find_arguments(positionals: list[str]) -> dict[str, Any]:
    return {
        "ref_id": positionals[0],
        "pattern": " ".join(positionals[1:]).strip(),
    }
