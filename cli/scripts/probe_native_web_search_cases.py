from __future__ import annotations

import argparse
from dataclasses import dataclass

from cli.scripts.script_runtime_helpers import apply_provider_home_override_env


DEFAULT_CASES = (
    ("claude", "claude-sonnet-4-6"),
    ("deepseek", "deepseek-chat"),
    ("glm", "glm-5"),
    ("glm-claude-mode", "glm-5"),
    ("openai", "gpt-5.4"),
    ("openai", "gpt-5.3-reference"),
)


@dataclass(frozen=True)
class ProbeCase:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"

    def env_overrides(self, *, provider_home: str = "") -> dict[str, str]:
        env = {
            "AGENT_CLI_PROVIDER": self.provider,
            "AGENT_CLI_MODEL": self.model,
        }
        return apply_provider_home_override_env(env, provider_home=provider_home)


def parse_case(value: str) -> ProbeCase:
    text = str(value or "").strip()
    provider, sep, model = text.partition(":")
    if not sep or not provider.strip() or not model.strip():
        raise argparse.ArgumentTypeError(f"invalid --case {value!r}; expected provider:model")
    return ProbeCase(provider=provider.strip(), model=model.strip())


def default_cases() -> list[ProbeCase]:
    return [ProbeCase(provider=provider, model=model) for provider, model in DEFAULT_CASES]
