from __future__ import annotations

import pytest

import cli.agent_cli.providers.reference_parity as reference_parity
from cli.agent_cli.providers.config_catalog import ProviderConfig


def _config(
    *,
    raw_model: dict | None = None,
    raw_provider: dict | None = None,
    provider_name: str = "",
    model_key: str = "",
    model: str = "gpt-5.4",
    base_url: str | None = None,
    interaction_profile: str = "",
) -> ProviderConfig:
    return ProviderConfig(
        model=model,
        api_key="test-key",
        provider_name=provider_name,
        model_key=model_key,
        base_url=base_url,
        interaction_profile=interaction_profile,
        raw_model=dict(raw_model or {}),
        raw_provider=dict(raw_provider or {}),
    )


@pytest.fixture(autouse=True)
def _clear_parity_caches() -> None:
    reference_parity.load_reference_base_prompt.cache_clear()
    reference_parity.load_reference_apply_patch_grammar.cache_clear()
    yield
    reference_parity.load_reference_base_prompt.cache_clear()
    reference_parity.load_reference_apply_patch_grammar.cache_clear()


def test_reference_parity_enabled_prefers_model_explicit_flag() -> None:
    config = _config(
        raw_model={"reference_parity": False},
        raw_provider={"reference_parity": True},
    )

    assert reference_parity.reference_parity_enabled(config) is False


def test_reference_parity_enabled_uses_provider_explicit_flag_when_model_missing() -> None:
    config = _config(raw_provider={"reference_parity": True})

    assert reference_parity.reference_parity_enabled(config) is True


def test_reference_parity_enabled_uses_model_explicit_flag_when_present() -> None:
    config = _config(raw_model={"reference_parity": True})

    assert reference_parity.reference_parity_enabled(config) is True


def test_reference_parity_enabled_defaults_false_without_explicit_flag() -> None:
    config = _config(
        provider_name="openai",
        model_key="gpt54",
        model="gpt-5.4",
        base_url="https://relay.example.com/reference/v1",
    )

    assert reference_parity.reference_parity_enabled(config) is False


def test_load_reference_base_prompt_returns_non_empty_text() -> None:
    prompt = reference_parity.load_reference_base_prompt()

    assert prompt.strip()
    assert "You are Codex" in prompt
    assert "coding agent" in prompt


def test_load_reference_base_prompt_uses_first_non_empty_existing_candidate(
    monkeypatch, tmp_path
) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("   \n", encoding="utf-8")
    selected = tmp_path / "selected.md"
    selected.write_text("reference prompt body", encoding="utf-8")
    missing = tmp_path / "missing.md"

    monkeypatch.setattr(
        reference_parity,
        "_REFERENCE_BASE_PROMPT_CANDIDATES",
        (missing, empty, selected),
    )
    reference_parity.load_reference_base_prompt.cache_clear()

    assert reference_parity.load_reference_base_prompt() == "reference prompt body"


def test_load_reference_base_prompt_raises_when_all_candidates_missing_or_empty(
    monkeypatch, tmp_path
) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    missing = tmp_path / "missing.md"

    monkeypatch.setattr(
        reference_parity,
        "_REFERENCE_BASE_PROMPT_CANDIDATES",
        (missing, empty),
    )
    reference_parity.load_reference_base_prompt.cache_clear()

    with pytest.raises(FileNotFoundError):
        reference_parity.load_reference_base_prompt()


def test_load_reference_apply_patch_grammar_returns_non_empty_text() -> None:
    grammar = reference_parity.load_reference_apply_patch_grammar()

    assert grammar.strip()
    assert "start: begin_patch hunk+ end_patch" in grammar
    assert "*** Begin Patch" in grammar


def test_load_reference_apply_patch_grammar_uses_first_non_empty_existing_candidate(
    monkeypatch, tmp_path
) -> None:
    fallback = tmp_path / "fallback.lark"
    fallback.write_text('start: token\ntoken: "ok"\n', encoding="utf-8")
    missing = tmp_path / "missing.lark"

    monkeypatch.setattr(
        reference_parity,
        "_REFERENCE_APPLY_PATCH_GRAMMAR_CANDIDATES",
        (missing, fallback),
    )
    reference_parity.load_reference_apply_patch_grammar.cache_clear()

    assert reference_parity.load_reference_apply_patch_grammar().startswith("start: token")


@pytest.mark.parametrize(
    "raw_model,raw_provider,expected",
    [
        ({"apply_patch_tool_type": "freeform"}, {}, "freeform"),
        ({}, {"reference_apply_patch_tool_type": "function"}, "function"),
        ({"apply_patch_tool_type": " disabled "}, {}, None),
        ({"apply_patch_tool_type": "none"}, {}, None),
    ],
)
def test_reference_apply_patch_tool_type_explicit_values(
    raw_model: dict,
    raw_provider: dict,
    expected: str | None,
) -> None:
    config = _config(raw_model=raw_model, raw_provider=raw_provider)

    assert reference_parity.reference_apply_patch_tool_type(config) == expected


def test_reference_apply_patch_tool_type_falls_back_to_provider_when_model_explicit_value_invalid() -> (
    None
):
    config = _config(
        raw_model={"apply_patch_tool_type": "unknown"},
        raw_provider={"reference_apply_patch_tool_type": "function"},
    )

    assert reference_parity.reference_apply_patch_tool_type(config) == "function"


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-5-codex", "freeform"),
        ("gpt-5.1-codex", "freeform"),
        ("gpt-5.1-codex-max", "freeform"),
        ("gpt-5.1-codex-mini", "freeform"),
        ("gpt-5.1", "freeform"),
        ("gpt-5.2", "freeform"),
        ("custom/gpt-5.2-variant", "freeform"),
        ("gpt-5.4", "freeform"),
        ("gpt-5.4-mini", "freeform"),
        ("gpt-5.5", "freeform"),
        ("gpt-5", None),
    ],
)
def test_reference_apply_patch_tool_type_uses_codex_reference_model_capability_table(
    model: str,
    expected: str | None,
) -> None:
    config = _config(model=model, interaction_profile="codex_openai")

    assert reference_parity.reference_apply_patch_tool_type(config) == expected


def test_reference_apply_patch_tool_type_explicit_disabled_overrides_codex_openai_profile() -> None:
    config = _config(
        model="gpt-5-codex",
        interaction_profile="codex_openai",
        raw_model={"apply_patch_tool_type": "disabled"},
    )

    assert reference_parity.reference_apply_patch_tool_type(config) is None


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("include_apply_patch_tool", True, "freeform"),
        ("experimental_use_freeform_apply_patch", True, "freeform"),
        ("apply_patch_freeform", "1", "freeform"),
        ("reference_apply_patch", False, None),
    ],
)
def test_reference_apply_patch_tool_type_legacy_boolean_keys(
    key: str,
    value: object,
    expected: str | None,
) -> None:
    config = _config(raw_provider={key: value})

    assert reference_parity.reference_apply_patch_tool_type(config) == expected


def test_reference_default_mode_request_user_input_supports_alias_keys_and_precedence() -> None:
    config = _config(
        raw_model={"default_mode_request_user_input": "0"},
        raw_provider={"reference_default_mode_request_user_input": True},
    )
    provider_only = _config(raw_provider={"reference_default_mode_request_user_input": True})

    assert reference_parity.reference_default_mode_request_user_input(config) is False
    assert reference_parity.reference_default_mode_request_user_input(provider_only) is True


def test_reference_default_mode_request_user_input_defaults_enabled_for_claude_code_profile() -> (
    None
):
    config = _config(
        provider_name="anthropic",
        model="claude-sonnet-4-6",
        interaction_profile="claude_code",
    )

    assert reference_parity.reference_default_mode_request_user_input(config) is True


def test_reference_collab_tools_enabled_supports_alias_keys_and_precedence() -> None:
    config = _config(
        interaction_profile="codex_openai",
        raw_model={"collab_tools": False},
        raw_provider={"reference_collab_tools": True},
    )
    provider_only = _config(raw_provider={"reference_collab_tools": "1"})

    assert reference_parity.reference_collab_tools_enabled(config) is False
    assert reference_parity.reference_collab_tools_enabled(provider_only) is True


def test_reference_collab_tools_enabled_defaults_enabled_for_codex_openai_profile() -> None:
    config = _config(interaction_profile="codex_openai")

    assert reference_parity.reference_collab_tools_enabled(config) is True


def test_reference_request_permission_enabled_supports_alias_keys_and_precedence() -> None:
    config = _config(
        raw_model={"request_permissions_enabled": False},
        raw_provider={"reference_request_permission_enabled": True},
    )
    provider_only = _config(raw_provider={"request_permission_enabled": "1"})

    assert reference_parity.reference_request_permission_enabled(config) is False
    assert reference_parity.reference_request_permission_enabled(provider_only) is True


@pytest.mark.parametrize(
    "raw_model,raw_provider,expected",
    [
        ({"external_web_access": True}, {"web_search_mode": "cached"}, True),
        ({}, {"reference_web_search_external_web_access": "1"}, True),
        ({"web_search_mode": "live"}, {}, True),
        ({"reference_web_search_mode": "cached"}, {}, False),
        ({}, {"web_search_mode": "cached", "sandbox_mode": "danger-full-access"}, True),
        ({"web_search_mode": "disabled"}, {}, False),
        ({}, {}, False),
    ],
)
def test_reference_web_search_external_web_access_resolution(
    raw_model: dict,
    raw_provider: dict,
    expected: bool,
) -> None:
    config = _config(raw_model=raw_model, raw_provider=raw_provider)

    assert reference_parity.reference_web_search_external_web_access(config) is expected
