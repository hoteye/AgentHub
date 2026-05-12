from cli.agent_cli.providers.types import ProviderVendorSpec

GLM_VENDOR = ProviderVendorSpec(
    name="glm",
    aliases=("glm", "zhipu"),
    default_protocol_family="openai_chat",
    description="GLM OpenAI-compatible chat family",
)

__all__ = ["GLM_VENDOR"]
