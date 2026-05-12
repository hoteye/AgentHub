from __future__ import annotations

__all__ = [
    "AnthropicClaudePlanner",
    "ChatCompletionsPlanner",
    "DeepSeekPlanner",
    "OpenAIPlanner",
]


def __getattr__(name: str):
    if name == "AnthropicClaudePlanner":
        from .anthropic_messages import AnthropicClaudePlanner

        return AnthropicClaudePlanner
    if name in {"ChatCompletionsPlanner", "DeepSeekPlanner"}:
        from .openai_chat import ChatCompletionsPlanner, DeepSeekPlanner

        exports = {
            "ChatCompletionsPlanner": ChatCompletionsPlanner,
            "DeepSeekPlanner": DeepSeekPlanner,
        }
        return exports[name]
    if name == "OpenAIPlanner":
        from .openai_responses import OpenAIPlanner

        return OpenAIPlanner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
