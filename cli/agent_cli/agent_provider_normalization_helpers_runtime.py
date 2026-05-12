from __future__ import annotations

from typing import Any, Dict, Optional

from cli.agent_cli.agent_selection_runtime import (
    delegation_override_payload as _delegation_override_payload,
    route_override_payload as _route_override_payload,
    selection_override_payload as _selection_override_payload,
    validated_delegation_name as _validated_delegation_name,
    validated_route_name as _validated_route_name,
)


def validated_reasoning_effort(
    reasoning_effort: str,
    *,
    reasoning_effort_levels: tuple[str, ...],
) -> str:
    effort = str(reasoning_effort or "").strip().lower()
    if not effort:
        raise ValueError("reasoning_effort must be a non-empty string")
    if effort not in reasoning_effort_levels:
        choices = ", ".join(reasoning_effort_levels)
        raise ValueError(f"unsupported reasoning_effort: {reasoning_effort}. expected one of: {choices}, default")
    return effort


def validated_route_name(
    route_name: str,
    *,
    standard_route_names: tuple[str, ...],
) -> str:
    return _validated_route_name(
        route_name,
        standard_route_names=standard_route_names,
    )


def validated_delegation_name(
    role_name: str,
    *,
    standard_delegation_names: tuple[str, ...],
) -> str:
    return _validated_delegation_name(
        role_name,
        standard_delegation_names=standard_delegation_names,
    )


def selection_override_payload(
    override: Dict[str, Any],
    *,
    validate_reasoning_effort,
    override_source: str,
) -> Dict[str, Any]:
    return _selection_override_payload(
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def route_override_payload(
    route_name: str,
    override: Dict[str, Any],
    *,
    validate_reasoning_effort,
    override_source: str,
) -> Dict[str, Any]:
    return _route_override_payload(
        route_name,
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def delegation_override_payload(
    role_name: str,
    override: Dict[str, Any],
    *,
    validate_reasoning_effort,
    override_source: str,
) -> Dict[str, Any]:
    return _delegation_override_payload(
        role_name,
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def _session_provider_env_overrides(agent: Any) -> Dict[str, Optional[str]]:
    return dict(getattr(agent, "_session_provider_env_overrides", {}) or {})
