from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli.mcp.config_sources import McpConfigSourceItem


@dataclass(frozen=True)
class McpPolicy:
    allow_sources: set[str] | None = None
    deny_sources: set[str] | None = None
    allow_names: set[str] | None = None
    deny_names: set[str] | None = None
    require_enabled: bool = False


def normalize_policy(policy: McpPolicy | dict[str, Any] | None) -> McpPolicy:
    if isinstance(policy, McpPolicy):
        return policy
    payload = dict(policy or {})

    def _as_set(value: Any, *, lowercase: bool = False) -> set[str] | None:
        if value is None:
            return None
        if not isinstance(value, (list, set, tuple)):
            return None
        normalized: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            normalized.add(text.lower() if lowercase else text)
        return normalized or None

    return McpPolicy(
        allow_sources=_as_set(payload.get("allow_sources"), lowercase=True),
        deny_sources=_as_set(payload.get("deny_sources"), lowercase=True),
        allow_names=_as_set(payload.get("allow_names")),
        deny_names=_as_set(payload.get("deny_names")),
        require_enabled=bool(payload.get("require_enabled", False)),
    )


def policy_filter_mcp_items(
    items: list[McpConfigSourceItem],
    *,
    policy: McpPolicy | dict[str, Any] | None = None,
) -> tuple[list[McpConfigSourceItem], list[dict[str, Any]]]:
    normalized = normalize_policy(policy)
    allowed: list[McpConfigSourceItem] = []
    blocked: list[dict[str, Any]] = []

    for item in items:
        deny_reason: str | None = None
        if normalized.deny_names and item.name in normalized.deny_names:
            deny_reason = "policy.deny_name"
        elif normalized.deny_sources and item.source in normalized.deny_sources:
            deny_reason = "policy.deny_source"
        elif normalized.allow_names is not None and item.name not in normalized.allow_names:
            deny_reason = "policy.not_in_allow_names"
        elif normalized.allow_sources is not None and item.source not in normalized.allow_sources:
            deny_reason = "policy.not_in_allow_sources"
        elif normalized.require_enabled and not item.enabled:
            deny_reason = "policy.require_enabled"

        if deny_reason is None:
            allowed.append(item)
            continue
        blocked.append(
            {
                "name": item.name,
                "source": item.source,
                "reason": deny_reason,
            }
        )
    return allowed, blocked
