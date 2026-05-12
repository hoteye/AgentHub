from __future__ import annotations

from typing import Any, Callable, Mapping

from .tool_projection import project_mcp_tool_descriptors

ConnectionLookup = Callable[[str], Any | None]


def call_projected_mcp_tool(
    *,
    payload: Mapping[str, Any],
    projected_name: str,
    arguments: Mapping[str, Any] | None,
    connection_lookup: ConnectionLookup,
) -> dict[str, Any]:
    target_name = str(projected_name or "").strip()
    descriptor = next(
        (item for item in project_mcp_tool_descriptors(payload) if str(item.get("name") or "").strip() == target_name),
        None,
    )
    if descriptor is None:
        return {"ok": False, "error": "unknown projected mcp tool", "projected_name": target_name}
    server_name = str(descriptor.get("server_name") or "").strip()
    remote_name = str(descriptor.get("remote_name") or "").strip()
    handle = connection_lookup(server_name)
    session = getattr(handle, "session", None)
    tools_call = getattr(session, "tools_call", None)
    if not callable(tools_call):
        return {
            "ok": False,
            "error": "mcp session unavailable",
            "projected_name": target_name,
            "server_name": server_name,
            "remote_name": remote_name,
        }
    try:
        result = tools_call(name=remote_name, arguments=dict(arguments or {}))
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "projected_name": target_name,
            "server_name": server_name,
            "remote_name": remote_name,
        }
    return {
        "ok": not bool(result.get("isError")),
        "projected_name": target_name,
        "server_name": server_name,
        "remote_name": remote_name,
        "result": dict(result),
    }


def format_projected_mcp_tool_call(payload: Mapping[str, Any]) -> str:
    data = dict(payload or {}) if isinstance(payload, Mapping) else {}
    result = data.get("result")
    result_payload = dict(result) if isinstance(result, Mapping) else {}
    content = result_payload.get("content")
    text = ""
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("type") or "").strip() != "text":
                continue
            text = str(item.get("text") or "").strip()
            if text:
                break
    lines = ["mcp tool call"]
    lines.append(f"ok={'true' if bool(data.get('ok')) else 'false'}")
    lines.append(f"projected_name={str(data.get('projected_name') or '-').strip() or '-'}")
    lines.append(f"server={str(data.get('server_name') or '-').strip() or '-'}")
    lines.append(f"remote_name={str(data.get('remote_name') or '-').strip() or '-'}")
    if data.get("error"):
        lines.append(f"error={str(data.get('error') or '').strip()}")
    if text:
        lines.append(f"text={text}")
    return "\n".join(lines)
