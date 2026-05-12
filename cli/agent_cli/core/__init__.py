from typing import TYPE_CHECKING, Any

from cli.agent_cli.core.provider_session import (
    ProviderSession,
    ProviderSessionResult,
    ProviderToolCall,
    default_tool_result_items,
    tool_result_payload,
)

if TYPE_CHECKING:
    from cli.agent_cli.core.turn_engine import TurnEngine

# Backward-compatible aliases for older imports that still expect these names
# from cli.agent_cli.core.
ToolCall = ProviderToolCall
TurnStepResult = ProviderSessionResult

__all__ = [
    "ProviderSession",
    "ProviderSessionResult",
    "ProviderToolCall",
    "ToolCall",
    "TurnEngine",
    "TurnStepResult",
    "default_tool_result_items",
    "tool_result_payload",
]


def __getattr__(name: str) -> Any:
    if name == "TurnEngine":
        from cli.agent_cli.core.turn_engine import TurnEngine

        return TurnEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
