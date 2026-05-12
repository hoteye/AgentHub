from __future__ import annotations

__all__ = [
    "AnthropicClaudePlanner",
    "load_claude_provider_config",
    "should_use_claude_provider",
]


def __getattr__(name: str):
    if name in __all__:
        from .planner import (
            AnthropicClaudePlanner,
            load_claude_provider_config,
            should_use_claude_provider,
        )

        exports = {
            "AnthropicClaudePlanner": AnthropicClaudePlanner,
            "load_claude_provider_config": load_claude_provider_config,
            "should_use_claude_provider": should_use_claude_provider,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
