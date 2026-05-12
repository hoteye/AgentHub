from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(slots=True)
class ResolvedMcpServer:
    name: str
    source: str
    precedence: int
    enabled: bool
    config: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


def collect_runtime_sources(manager: Any, runtime_dynamic: Mapping[str, Any] | None = None) -> dict[str, Any]:
    user = {}
    plugin = {}
    if manager is not None:
        user_getter = getattr(manager, "user_configured_mcp_servers", None)
        if callable(user_getter):
            user = dict(user_getter() or {})
        plugin_getter = getattr(manager, "effective_mcp_servers", None)
        if callable(plugin_getter):
            plugin = dict(plugin_getter() or {})
    return {
        "user": user,
        "workspace": {},
        "plugin": plugin,
        "runtime_dynamic": dict(runtime_dynamic or {}),
    }


def resolved_servers_from_entries(result: Mapping[str, Any]) -> list[ResolvedMcpServer]:
    resolved: list[ResolvedMcpServer] = []
    for item in list(result.get("entries") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        config = dict(item.get("config") or {})
        metadata = dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {}
        resolved.append(
            ResolvedMcpServer(
                name=name,
                source=str(item.get("source") or "plugin").strip().lower() or "plugin",
                precedence=int(item.get("precedence") or 0),
                enabled=bool(item.get("enabled", True)),
                config=config,
                metadata=metadata,
            )
        )
    return resolved
