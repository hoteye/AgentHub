from __future__ import annotations

from typing import Any

from cli.agent_cli import agent_provider_runtime, agent_runtime, agent_runtime_helpers
from cli.agent_cli.agent_constants import (
    REASONING_EFFORT_LEVELS as _REASONING_EFFORT_LEVELS,
)
from cli.agent_cli.agent_provider_coordination import (
    SESSION_MODEL_DEFAULT_TOKENS,
    SESSION_ROUTE_OVERRIDE_SOURCE,
    STANDARD_DELEGATION_NAMES,
    STANDARD_ROUTE_NAMES,
)
from cli.agent_cli.agent_selection_runtime import (
    config_with_session_delegation_overrides as _selection_config_with_session_delegation_overrides,
)
from cli.agent_cli.agent_selection_runtime import (
    config_with_session_route_overrides as _selection_config_with_session_route_overrides,
)
from cli.agent_cli.models import AgentIntent


def _validated_reasoning_effort(reasoning_effort: str) -> str:
    return agent_provider_runtime.validated_reasoning_effort(
        reasoning_effort, reasoning_effort_levels=_REASONING_EFFORT_LEVELS
    )


def _validated_route_name(route_name: str) -> str:
    return agent_provider_runtime.validated_route_name(
        route_name, standard_route_names=STANDARD_ROUTE_NAMES
    )


def _validated_delegation_name(role_name: str) -> str:
    return agent_provider_runtime.validated_delegation_name(
        role_name, standard_delegation_names=STANDARD_DELEGATION_NAMES
    )


def _selection_override_payload(override: dict[str, Any]) -> dict[str, Any]:
    return agent_runtime_helpers.selection_override_payload(
        override,
        validate_reasoning_effort=_validated_reasoning_effort,
        override_source=SESSION_ROUTE_OVERRIDE_SOURCE,
    )


def _route_override_payload(route_name: str, override: dict[str, Any]) -> dict[str, Any]:
    return agent_runtime_helpers.route_override_payload(
        route_name,
        override,
        validate_reasoning_effort=_validated_reasoning_effort,
        override_source=SESSION_ROUTE_OVERRIDE_SOURCE,
    )


def _delegation_override_payload(role_name: str, override: dict[str, Any]) -> dict[str, Any]:
    return agent_runtime_helpers.delegation_override_payload(
        role_name,
        override,
        validate_reasoning_effort=_validated_reasoning_effort,
        override_source=SESSION_ROUTE_OVERRIDE_SOURCE,
    )


def _config_with_session_block_overrides(
    config: Any,
    *,
    block_key: str,
    allowed_names: tuple[str, ...],
    overrides: dict[str, dict[str, Any]],
) -> Any:
    return agent_runtime_helpers.config_with_session_block_overrides(
        config,
        block_key=block_key,
        allowed_names=allowed_names,
        overrides=overrides,
        config_with_session_route_overrides_fn=_selection_config_with_session_route_overrides,
        config_with_session_delegation_overrides_fn=_selection_config_with_session_delegation_overrides,
        session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
    )


def _config_with_session_route_overrides(config: Any, overrides: dict[str, dict[str, Any]]) -> Any:
    return agent_runtime_helpers.config_with_session_route_overrides(
        config,
        overrides,
        standard_route_names=STANDARD_ROUTE_NAMES,
        session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
        config_with_session_route_overrides_fn=_selection_config_with_session_route_overrides,
    )


def _config_with_session_delegation_overrides(
    config: Any, overrides: dict[str, dict[str, Any]]
) -> Any:
    return agent_runtime_helpers.config_with_session_delegation_overrides(
        config,
        overrides,
        standard_delegation_names=STANDARD_DELEGATION_NAMES,
        session_model_default_tokens=SESSION_MODEL_DEFAULT_TOKENS,
        config_with_session_delegation_overrides_fn=_selection_config_with_session_delegation_overrides,
    )


def _protocol_path_payload(
    *,
    kind: str,
    source: str,
    provider_used: bool,
    parity_evaluable: bool,
    reason: str,
) -> dict[str, Any]:
    return agent_runtime.protocol_path_payload(
        kind=kind,
        source=source,
        provider_used=provider_used,
        parity_evaluable=parity_evaluable,
        reason=reason,
    )


def _intent_with_protocol_path(
    cls,
    intent: AgentIntent,
    *,
    kind: str,
    source: str,
    provider_used: bool,
    parity_evaluable: bool,
    reason: str,
) -> AgentIntent:
    del cls
    return agent_runtime.intent_with_protocol_path(
        intent,
        kind=kind,
        source=source,
        provider_used=provider_used,
        parity_evaluable=parity_evaluable,
        reason=reason,
    )
