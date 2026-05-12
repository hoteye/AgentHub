from __future__ import annotations

from dataclasses import replace
from typing import Any

from cli.agent_cli.mcp.config_sources import (
    McpConfigSourceItem,
    canonical_config_fingerprint,
    collect_mcp_config_sources,
)
from cli.agent_cli.mcp.policy import McpPolicy, policy_filter_mcp_items


def _blocked_item(item: McpConfigSourceItem, *, reason: str, detail: str = "") -> dict[str, Any]:
    payload = {
        "name": item.name,
        "source": item.source,
        "reason": reason,
    }
    if detail:
        payload["detail"] = detail
    return payload


def _validated_item(item: McpConfigSourceItem) -> tuple[McpConfigSourceItem | None, dict[str, Any] | None]:
    config = dict(item.config)
    metadata = dict(item.metadata)

    registry_error = str(metadata.get("registry_error") or "").strip()
    if registry_error:
        return None, _blocked_item(item, reason="registry.lookup_failed", detail=registry_error)

    mcpb = config.get("mcpb")
    if mcpb is not None:
        if not isinstance(mcpb, dict):
            return None, _blocked_item(item, reason="mcpb.invalid_metadata", detail="mcpb must be an object")
        mcpb_uri = str(mcpb.get("uri") or mcpb.get("package") or "").strip()
        if not mcpb_uri:
            return None, _blocked_item(item, reason="mcpb.missing_uri", detail="mcpb.uri is required")

    headers_helper = config.get("headers_helper")
    if headers_helper is not None:
        if not isinstance(headers_helper, dict):
            return None, _blocked_item(
                item,
                reason="headers_helper.invalid_config",
                detail="headers_helper must be an object",
            )
        helper_type = str(headers_helper.get("type") or "env").strip().lower()
        if helper_type != "env":
            return None, _blocked_item(
                item,
                reason="headers_helper.unsupported_type",
                detail=f"type={helper_type or '-'}",
            )
        trusted_only = bool(headers_helper.get("trusted_only", True))
        trust_level = str(metadata.get("workspace_trust") or config.get("workspace_trust") or "unknown").strip().lower()
        if trusted_only and trust_level != "trusted":
            return None, _blocked_item(
                item,
                reason="headers_helper.untrusted_workspace",
                detail=f"trust={trust_level or 'unknown'}",
            )
        mapping = headers_helper.get("map")
        if not isinstance(mapping, dict):
            mapping = headers_helper.get("headers")
        if not isinstance(mapping, dict):
            mapping = headers_helper.get("mappings")
        if not isinstance(mapping, dict) or not mapping:
            return None, _blocked_item(
                item,
                reason="headers_helper.invalid_map",
                detail="headers_helper.map must be a non-empty object",
            )
        headers = dict(config.get("headers") or {}) if isinstance(config.get("headers"), dict) else {}
        for header_name_raw, env_name_raw in mapping.items():
            header_name = str(header_name_raw or "").strip()
            env_name = str(env_name_raw or "").strip()
            if not header_name or not env_name:
                return None, _blocked_item(
                    item,
                    reason="headers_helper.invalid_map",
                    detail="header name and env key are required",
                )
            headers[header_name] = f"$env:{env_name}"
        config["headers"] = headers

    return replace(item, config=config, metadata=metadata), None


def _apply_enabled_state(
    item: McpConfigSourceItem,
    *,
    enabled_state: dict[str, bool] | None,
) -> McpConfigSourceItem:
    if not enabled_state:
        return item
    if item.name not in enabled_state:
        return item
    return replace(item, enabled=bool(enabled_state[item.name]))


def effective_mcp_configs(
    *,
    user: Any = None,
    workspace: Any = None,
    plugin: Any = None,
    runtime_dynamic: Any = None,
    enabled_state: dict[str, bool] | None = None,
    policy: McpPolicy | dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = collect_mcp_config_sources(
        user=user,
        workspace=workspace,
        plugin=plugin,
        runtime_dynamic=runtime_dynamic,
    )
    blocked: list[dict[str, Any]] = []

    normalized: list[McpConfigSourceItem] = []
    for item in merged:
        current = _apply_enabled_state(item, enabled_state=enabled_state)
        validated, blocked_payload = _validated_item(current)
        if blocked_payload is not None:
            blocked.append(blocked_payload)
            continue
        if validated is not None:
            normalized.append(validated)

    by_name: dict[str, McpConfigSourceItem] = {}
    for item in normalized:
        winner = by_name.get(item.name)
        if winner is None:
            by_name[item.name] = item
            continue
        blocked.append(
            {
                "name": item.name,
                "source": item.source,
                "reason": "dedup.shadowed_by_precedence",
                "winner_source": winner.source,
            }
        )

    unique_by_name: list[McpConfigSourceItem] = sorted(by_name.values(), key=lambda item: (item.precedence, item.name))

    by_fingerprint: dict[str, McpConfigSourceItem] = {}
    deduped: list[McpConfigSourceItem] = []
    for item in unique_by_name:
        fingerprint = canonical_config_fingerprint(
            {
                "config": item.config,
                "enabled": bool(item.enabled),
                "metadata": item.metadata,
            }
        )
        winner = by_fingerprint.get(fingerprint)
        if winner is None:
            by_fingerprint[fingerprint] = item
            deduped.append(item)
            continue
        blocked.append(
            {
                "name": item.name,
                "source": item.source,
                "reason": "dedup.duplicate_content",
                "winner_name": winner.name,
                "winner_source": winner.source,
            }
        )

    allowed, policy_blocked = policy_filter_mcp_items(deduped, policy=policy)
    blocked.extend(policy_blocked)

    effective: dict[str, dict[str, Any]] = {}
    for item in allowed:
        if not item.enabled:
            continue
        effective[item.name] = dict(item.config)

    entries = [
        {
            "name": item.name,
            "source": item.source,
            "precedence": item.precedence,
            "enabled": item.enabled,
            "config": dict(item.config),
            "metadata": dict(item.metadata),
        }
        for item in allowed
    ]
    return {
        "effective": effective,
        "entries": entries,
        "blocked": blocked,
        "enabled_state": {entry["name"]: bool(entry["enabled"]) for entry in entries},
    }
