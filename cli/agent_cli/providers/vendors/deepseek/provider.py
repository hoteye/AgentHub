from cli.agent_cli.providers.types import ProviderVendorSpec

DEEPSEEK_VENDOR = ProviderVendorSpec(
    name="deepseek",
    aliases=("deepseek",),
    default_protocol_family="openai_chat",
    description="DeepSeek OpenAI-compatible chat family",
    line_model_selectors=(
        ("chat", "deepseek-chat"),
        ("reasoner", "deepseek-reasoner"),
    ),
)

__all__ = ["DEEPSEEK_VENDOR"]
