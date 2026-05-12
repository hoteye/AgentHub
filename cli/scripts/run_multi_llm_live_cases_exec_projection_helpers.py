from __future__ import annotations

from typing import Any


def _route_view(summary: dict[str, Any]) -> dict[str, Any]:
    routes = summary.get("routes")
    if not isinstance(routes, dict):
        return {}
    projection: dict[str, Any] = {}
    for route_name in ("tool_followup", "final_synthesis", "policy_helper"):
        payload = routes.get(route_name)
        if not isinstance(payload, dict):
            continue
        projection[route_name] = {
            "provider_name": str(payload.get("provider_name") or ""),
            "model": str(payload.get("model") or ""),
            "wire_api": str(payload.get("wire_api") or ""),
            "reasoning_effort": str(payload.get("reasoning_effort") or ""),
            "timeout": payload.get("timeout"),
            "source": str(payload.get("source") or ""),
        }
    return projection


def _delegation_view(summary: dict[str, Any]) -> dict[str, Any]:
    delegation = summary.get("delegation")
    if not isinstance(delegation, dict):
        return {}
    payload = delegation.get("roles")
    if not isinstance(payload, dict):
        payload = {
            key: value
            for key, value in delegation.items()
            if isinstance(value, dict)
        }
    if not payload:
        return {}
    return {
        "roles": {
            role: {
                "provider": str(info.get("provider") or info.get("provider_name") or ""),
                "model": str(info.get("model") or info.get("effective_model") or ""),
                "reasoning_effort": str(info.get("reasoning_effort") or ""),
                "timeout": int(info.get("timeout") or 0),
                "source": str(info.get("source") or info.get("effective_source") or ""),
            }
            for role, info in payload.items()
            if isinstance(info, dict)
        }
    }
