from __future__ import annotations

import os
from typing import Any, Dict


def session_provider_env_overrides(agent: Any) -> Dict[str, str | None]:
    return dict(getattr(agent, "_session_provider_env_overrides", {}) or {})


def merged_provider_env_mapping(agent: Any) -> Dict[str, str]:
    env_mapping: Dict[str, str] = dict(os.environ)
    for key, value in session_provider_env_overrides(agent).items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        if value is None:
            env_mapping.pop(normalized_key, None)
            continue
        env_mapping[normalized_key] = str(value)
    return env_mapping


def current_probe_target(agent: Any) -> tuple[str, str]:
    summary: Dict[str, Any] = {}
    planner = getattr(agent, "_planner", None)
    if planner is not None:
        public_summary = getattr(planner, "public_summary", None)
        if callable(public_summary):
            try:
                summary = dict(public_summary() or {})
            except Exception:
                summary = {}
    provider_name = str(summary.get("provider_name") or "").strip()
    model = str(summary.get("model") or "").strip()
    session_overrides = session_provider_env_overrides(agent)
    if not provider_name:
        provider_name = str(session_overrides.get("AGENT_CLI_PROVIDER") or "").strip()
    if not model:
        model = str(session_overrides.get("AGENT_CLI_MODEL") or "").strip()
    return provider_name, model


def resolve_probe_request(
    agent: Any,
    *,
    provider_name: str | None = None,
    model: str | None = None,
) -> tuple[str, str, Dict[str, str | None]]:
    selected_provider, selected_model = current_probe_target(agent)
    explicit_provider = str(provider_name or "").strip()
    explicit_model = str(model or "").strip()
    if explicit_provider:
        selected_provider = explicit_provider
    if explicit_model:
        selected_model = explicit_model

    env_overrides = session_provider_env_overrides(agent)
    if selected_provider:
        env_overrides["AGENT_CLI_PROVIDER"] = selected_provider
    if selected_model:
        env_overrides["AGENT_CLI_MODEL"] = selected_model
    return selected_provider, selected_model, env_overrides
