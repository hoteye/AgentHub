from cli.agent_cli.providers.types import ProviderVendorSpec

OPENAI_VENDOR = ProviderVendorSpec(
    name="openai",
    aliases=("openai", "reference"),
    default_protocol_family="openai_responses",
    description="OpenAI/Reference-style provider family",
)

__all__ = ["OPENAI_VENDOR"]
