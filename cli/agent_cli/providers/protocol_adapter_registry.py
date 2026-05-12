from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Type

from cli.agent_cli.providers.protocols.anthropic_messages import AnthropicClaudePlanner
from cli.agent_cli.providers.protocols.openai_chat import ChatCompletionsPlanner
from cli.agent_cli.providers.protocols.openai_responses import OpenAIPlanner
from cli.agent_cli.providers.types import PlannerRuntimeFamily


@dataclass(frozen=True)
class ProtocolAdapterSpec:
    family: PlannerRuntimeFamily
    planner_class: Type[object]


OPENAI_RESPONSES_ADAPTER = ProtocolAdapterSpec(
    family=PlannerRuntimeFamily(
        name="openai_responses",
        planner_kinds=("openai_responses",),
        description="OpenAI Responses / Reference-style item loop",
    ),
    planner_class=OpenAIPlanner,
)
OPENAI_CHAT_ADAPTER = ProtocolAdapterSpec(
    family=PlannerRuntimeFamily(
        name="openai_chat",
        planner_kinds=("openai_chat", "deepseek_chat", "deepseek_reasoner"),
        description="OpenAI-compatible chat completions family",
    ),
    planner_class=ChatCompletionsPlanner,
)
ANTHROPIC_MESSAGES_ADAPTER = ProtocolAdapterSpec(
    family=PlannerRuntimeFamily(
        name="anthropic_messages",
        planner_kinds=("anthropic_messages",),
        description="Anthropic messages family",
    ),
    planner_class=AnthropicClaudePlanner,
)

_ADAPTERS: tuple[ProtocolAdapterSpec, ...] = (
    OPENAI_RESPONSES_ADAPTER,
    OPENAI_CHAT_ADAPTER,
    ANTHROPIC_MESSAGES_ADAPTER,
)

_ADAPTER_BY_FAMILY: Dict[str, ProtocolAdapterSpec] = {
    str(item.family.name or "").strip().lower(): item for item in _ADAPTERS
}
_ADAPTER_BY_PLANNER_KIND: Dict[str, ProtocolAdapterSpec] = {}
for item in _ADAPTERS:
    for planner_kind in item.family.planner_kinds:
        normalized = str(planner_kind or "").strip().lower()
        if normalized:
            _ADAPTER_BY_PLANNER_KIND[normalized] = item


def protocol_adapters() -> Tuple[ProtocolAdapterSpec, ...]:
    return _ADAPTERS


def adapter_for_family(family_name: str) -> ProtocolAdapterSpec | None:
    normalized = str(family_name or "").strip().lower()
    if not normalized:
        return None
    return _ADAPTER_BY_FAMILY.get(normalized)


def adapter_for_planner_kind(planner_kind: str) -> ProtocolAdapterSpec | None:
    normalized = str(planner_kind or "").strip().lower()
    if not normalized:
        return _ADAPTER_BY_PLANNER_KIND.get("openai_responses")
    return _ADAPTER_BY_PLANNER_KIND.get(normalized) or _ADAPTER_BY_PLANNER_KIND.get("openai_responses")


__all__ = [
    "ANTHROPIC_MESSAGES_ADAPTER",
    "OPENAI_CHAT_ADAPTER",
    "OPENAI_RESPONSES_ADAPTER",
    "ProtocolAdapterSpec",
    "adapter_for_family",
    "adapter_for_planner_kind",
    "protocol_adapters",
]

