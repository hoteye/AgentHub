from __future__ import annotations

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_loader import load_bundled_interaction_profiles
from cli.agent_cli.providers.reference_parity_tool_specs import (
    reference_parity_responses_minimal_tool_specs,
)
from cli.agent_cli.providers.responses_tool_specs import (
    responses_minimal_provider_tool_specs,
    responses_provider_tool_specs,
)
from cli.agent_cli.providers.tool_specs import responses_minimal_provider_tool_names


def test_responses_provider_tool_specs_legacy_alias_keeps_reference_tools_first() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        raw_provider={"reference_parity": True},
    )

    def _merged_provider_tool_specs(*args, **kwargs):
        return [
            {
                "type": "function",
                "function": {
                    "name": "plugin_lookup",
                    "description": "plugin lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ]

    specs = responses_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        merged_provider_tool_specs_fn=_merged_provider_tool_specs,
    )

    reference_specs = reference_parity_responses_minimal_tool_specs(config)
    assert specs[: len(reference_specs)] == reference_specs
    assert specs[-1]["name"] == "plugin_lookup"


def test_responses_minimal_provider_tool_specs_explicit_codex_openai_routes_to_parity_specs() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )
    responses_specs_called = False

    def _responses_provider_tool_specs(*args, **kwargs):
        nonlocal responses_specs_called
        responses_specs_called = True
        return []

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=_responses_provider_tool_specs,
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    assert responses_specs_called is False
    assert specs == reference_parity_responses_minimal_tool_specs(config)


def test_codex_openai_collab_tools_appear_on_full_and_minimal_surface() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        raw_provider={"reference_parity": True, "collab_tools": True, "web_search_mode": "live"},
    )

    provider_specs = responses_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        merged_provider_tool_specs_fn=lambda *_args, **_kwargs: [],
    )
    minimal_specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=lambda *_args, **_kwargs: [],
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    assert [(item.get("type"), item.get("name")) for item in provider_specs] == [
        ("function", "exec_command"),
        ("function", "write_stdin"),
        ("function", "update_plan"),
        ("function", "request_user_input"),
        ("custom", "apply_patch"),
        ("web_search", None),
        ("function", "view_image"),
        ("function", "spawn_agent"),
        ("function", "send_input"),
        ("function", "resume_agent"),
        ("function", "wait_agent"),
        ("function", "close_agent"),
    ]
    assert [(item.get("type"), item.get("name")) for item in minimal_specs] == [
        ("function", "exec_command"),
        ("function", "write_stdin"),
        ("function", "update_plan"),
        ("function", "request_user_input"),
        ("custom", "apply_patch"),
        ("web_search", None),
        ("function", "view_image"),
        ("function", "spawn_agent"),
        ("function", "send_input"),
        ("function", "resume_agent"),
        ("function", "wait_agent"),
        ("function", "close_agent"),
    ]


def test_codex_openai_apply_patch_profile_contract_projects_to_tool_surface_for_codex_models() -> (
    None
):
    profiles = load_bundled_interaction_profiles()
    apply_patch_family = profiles["codex_openai"].tool_families["apply_patch"]
    config = ProviderConfig(
        model="gpt-5-codex",
        api_key="test",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=lambda *_args, **_kwargs: [],
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    assert apply_patch_family.exposure == "enabled"
    assert apply_patch_family.projection == "capability_driven"
    assert any(item.get("type") == "custom" and item.get("name") == "apply_patch" for item in specs)
    assert not any(item.get("name") in {"Write", "Edit"} for item in specs)


def test_codex_openai_gpt51_default_surface_includes_apply_patch() -> None:
    config = ProviderConfig(
        model="gpt-5.1",
        api_key="test",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=lambda *_args, **_kwargs: [],
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    assert any(item.get("name") == "apply_patch" for item in specs)
    assert not any(item.get("name") in {"Write", "Edit"} for item in specs)


def test_codex_openai_gpt54_default_surface_includes_apply_patch_from_reference_snapshot() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=lambda *_args, **_kwargs: [],
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    assert any(item.get("type") == "custom" and item.get("name") == "apply_patch" for item in specs)
    assert not any(item.get("name") in {"Write", "Edit"} for item in specs)


def test_codex_openai_experimental_file_tools_surface_matches_reference_order_and_required_fields() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4-filetools",
        api_key="test",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
        raw_model={
            "experimental_supported_tools": ["grep_files", "read_file", "list_dir"],
        },
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=lambda *_args, **_kwargs: [],
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    names = [(item.get("type"), item.get("name")) for item in specs]
    assert names == [
        ("function", "exec_command"),
        ("function", "write_stdin"),
        ("function", "update_plan"),
        ("function", "request_user_input"),
        ("custom", "apply_patch"),
        ("function", "grep_files"),
        ("function", "read_file"),
        ("function", "list_dir"),
        ("web_search", None),
        ("function", "view_image"),
    ]
    assert responses_minimal_provider_tool_names(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    ) == [
        "exec_command",
        "write_stdin",
        "update_plan",
        "request_user_input",
        "apply_patch",
        "grep_files",
        "read_file",
        "list_dir",
        "view_image",
    ]
    grep_spec = next(item for item in specs if item.get("name") == "grep_files")
    read_spec = next(item for item in specs if item.get("name") == "read_file")
    list_spec = next(item for item in specs if item.get("name") == "list_dir")
    assert any(item.get("type") == "custom" and item.get("name") == "apply_patch" for item in specs)
    assert grep_spec["parameters"]["required"] == ["pattern"]
    assert read_spec["parameters"]["required"] == ["file_path"]
    assert list_spec["parameters"]["required"] == ["dir_path"]
    assert read_spec["parameters"]["properties"]["indentation"]["additionalProperties"] is False
    assert "path" not in read_spec["parameters"]["properties"]


def test_codex_openai_apply_patch_can_be_explicitly_disabled_for_surface_escape_hatch() -> None:
    config = ProviderConfig(
        model="gpt-5-codex",
        api_key="test",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
        raw_model={"apply_patch_tool_type": "disabled"},
    )

    specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=lambda *_args, **_kwargs: [],
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    assert not any(item.get("name") == "apply_patch" for item in specs)
    assert not any(item.get("name") in {"Write", "Edit"} for item in specs)


def test_responses_tool_specs_generic_path_preserves_flatten_filter_behavior() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        interaction_profile="generic_chat",
        interaction_profile_source="model.interaction_profile",
    )

    provider_specs = responses_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        merged_provider_tool_specs_fn=lambda *_args, **_kwargs: [
            {
                "type": "function",
                "strict": "true",
                "function": {
                    "name": "z_tool",
                    "description": "z desc",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "name": "exec_command",
                "description": "run",
                "strict": "0",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {"type": "web_search", "external_web_access": True},
        ],
    )

    assert [item.get("name") for item in provider_specs if item.get("type") == "function"] == [
        "z_tool",
        "exec_command",
    ]
    assert provider_specs[0].get("strict") is True
    assert provider_specs[1].get("strict") is False

    minimal_specs = responses_minimal_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        responses_provider_tool_specs_fn=lambda *_args, **_kwargs: list(provider_specs),
        responses_minimal_tool_order=("exec_command", "write_stdin"),
    )

    assert [(item.get("type"), item.get("name")) for item in minimal_specs] == [
        ("function", "exec_command"),
        ("web_search", None),
    ]


def test_responses_provider_tool_specs_incompatible_explicit_profile_falls_back_to_generic_surface() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test",
        planner_kind="openai_chat",
        wire_api="openai_chat",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )
    merged_called = False

    def _merged_provider_tool_specs(*_args, **_kwargs):
        nonlocal merged_called
        merged_called = True
        return [
            {
                "type": "function",
                "strict": True,
                "function": {
                    "name": "demo_lookup",
                    "description": "demo desc",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ]

    specs = responses_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
        merged_provider_tool_specs_fn=_merged_provider_tool_specs,
    )

    assert merged_called is True
    assert specs == [
        {
            "type": "function",
            "name": "demo_lookup",
            "description": "demo desc",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            "strict": True,
        }
    ]
