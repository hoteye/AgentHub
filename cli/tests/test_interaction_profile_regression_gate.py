from __future__ import annotations

from pathlib import Path

import pytest

from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.reference_parity import reference_parity_enabled


REPO_ROOT = Path(__file__).resolve().parents[2]


def _config(
    *,
    provider_name: str = "",
    model_key: str = "",
    model: str = "gpt-5.4",
    base_url: str | None = None,
    raw_model: dict | None = None,
    raw_provider: dict | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        model=model,
        api_key="test-key",
        provider_name=provider_name,
        model_key=model_key,
        base_url=base_url,
        raw_model=dict(raw_model or {}),
        raw_provider=dict(raw_provider or {}),
    )


@pytest.mark.parametrize(
    "provider_name,model_key,model,base_url",
    [
        ("reference-proxy", "", "gpt-5.4", None),
        ("", "my-reference-model", "gpt-5.4", None),
        ("", "", "reference-model", None),
        ("", "", "gpt-5.4", "https://relay.example.com/reference/v1"),
        ("codex-provider", "codex-model", "gpt-5.4", "https://api.example.com/codex/v1"),
    ],
)
def test_reference_parity_is_not_enabled_by_provider_or_model_or_url_text(
    provider_name: str,
    model_key: str,
    model: str,
    base_url: str | None,
) -> None:
    config = _config(
        provider_name=provider_name,
        model_key=model_key,
        model=model,
        base_url=base_url,
    )
    assert reference_parity_enabled(config) is False


def test_reference_parity_remains_explicit_flag_only() -> None:
    provider_explicit = _config(raw_provider={"reference_parity": True})
    model_explicit = _config(
        raw_model={"reference_parity": False},
        raw_provider={"reference_parity": True},
    )

    assert reference_parity_enabled(provider_explicit) is True
    assert reference_parity_enabled(model_explicit) is False


def test_old_reference_fingerprint_snippets_must_not_exist_in_profile_related_sources() -> None:
    candidate_relative_paths = (
        "cli/agent_cli/providers/reference_parity.py",
        "cli/agent_cli/providers/config_catalog_selection.py",
        "cli/agent_cli/providers/interaction_profile_config.py",
        "cli/agent_cli/providers/interaction_profile_resolution.py",
        "cli/agent_cli/providers/interaction_contract.py",
    )
    forbidden_snippets = (
        '"/reference/" in fingerprint',
        '"reference" in fingerprint',
        "'reference' in fingerprint",
        '"codex" in fingerprint',
        "'codex' in fingerprint",
    )

    for relative_path in candidate_relative_paths:
        path = REPO_ROOT / relative_path
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in source, f"{relative_path} unexpectedly contains snippet: {snippet}"
