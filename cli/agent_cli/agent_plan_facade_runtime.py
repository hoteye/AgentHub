from __future__ import annotations

from collections.abc import Callable

from cli.agent_cli.models import AgentIntent


def intent_with_protocol_path(
    intent: AgentIntent,
    *,
    kind: str,
    source: str,
    provider_used: bool,
    parity_evaluable: bool,
    reason: str,
    intent_with_protocol_path_fn: Callable[..., AgentIntent],
) -> AgentIntent:
    return intent_with_protocol_path_fn(
        intent,
        kind=kind,
        source=source,
        provider_used=provider_used,
        parity_evaluable=parity_evaluable,
        reason=reason,
    )


def degraded_fallback_intent(
    *,
    planner_fallback_text: str,
    intent_with_protocol_path_fn: Callable[..., AgentIntent],
) -> AgentIntent:
    return intent_with_protocol_path_fn(
        AgentIntent(assistant_text=planner_fallback_text, status_hint="degraded"),
        kind="provider_degraded_fallback",
        source="host",
        provider_used=False,
        parity_evaluable=False,
        reason="planner_unavailable_or_failed",
    )


def no_provider_intent(*, intent_with_protocol_path_fn: Callable[..., AgentIntent]) -> AgentIntent:
    return intent_with_protocol_path_fn(
        AgentIntent(assistant_text=("无法继续：未检测到可用的 LLM provider。")),
        kind="no_provider",
        source="host",
        provider_used=False,
        parity_evaluable=False,
        reason="provider_not_configured",
    )
