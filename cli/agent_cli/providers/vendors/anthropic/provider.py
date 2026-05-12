from cli.agent_cli.providers.types import ProviderVendorSpec

ANTHROPIC_VENDOR = ProviderVendorSpec(
    name="anthropic",
    aliases=("anthropic", "claude", "claude_code", "anthropic_claude"),
    default_protocol_family="anthropic_messages",
    description="Anthropic Claude provider family",
)

__all__ = ["ANTHROPIC_VENDOR"]
