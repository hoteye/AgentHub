from __future__ import annotations

from cli.agent_cli.providers import tool_family_mapping_runtime
from cli.agent_cli.providers import tool_family_metadata_runtime
from cli.agent_cli.providers.tool_specs import base_capability_specs, builtin_tool_metadata, canonical_tool_registry


def test_command_execution_metadata_distinguishes_canonical_tools_alias_and_event_projection() -> None:
    exec_metadata = builtin_tool_metadata("exec_command")
    write_metadata = builtin_tool_metadata("write_stdin")
    shell_metadata = builtin_tool_metadata("shell")

    assert exec_metadata is not None
    assert write_metadata is not None
    assert shell_metadata is not None

    assert exec_metadata["canonical_family"] == tool_family_mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY
    assert exec_metadata["command_execution_role"] == "primary"
    assert exec_metadata["canonical_tool_name"] == "exec_command"
    assert exec_metadata["command_execution_primary_tools"] == tool_family_mapping_runtime.COMMAND_EXECUTION_PRIMARY_TOOLS
    assert (
        exec_metadata["command_execution_continuation_tools"]
        == tool_family_mapping_runtime.COMMAND_EXECUTION_CONTINUATION_TOOLS
    )
    assert (
        exec_metadata["command_execution_event_projection"]
        == tool_family_mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_NAME
    )
    assert exec_metadata["event_projection_is_model_tool"] is False

    assert write_metadata["canonical_family"] == tool_family_mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY
    assert write_metadata["command_execution_role"] == "continuation"
    assert write_metadata["canonical_tool_name"] == "write_stdin"
    assert (
        write_metadata["command_execution_event_projection"]
        == tool_family_mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_NAME
    )

    assert shell_metadata["canonical_family"] == tool_family_mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY
    assert shell_metadata["command_execution_role"] == "compatibility_alias"
    assert shell_metadata["model_default_exposure"] == "compatibility_alias"
    assert shell_metadata["compatibility_alias_for"] == "exec_command"
    assert (
        shell_metadata["command_execution_compatibility_aliases"]
        == tool_family_mapping_runtime.COMMAND_EXECUTION_TOOL_COMPAT_ALIASES
    )


def test_command_execution_event_projection_is_not_registered_as_a_model_tool() -> None:
    base_names = {item["name"] for item in base_capability_specs()}
    registry_names = {item["name"] for item in canonical_tool_registry()}

    assert tool_family_mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_NAME not in base_names
    assert tool_family_mapping_runtime.COMMAND_EXECUTION_EVENT_PROJECTION_NAME not in registry_names
    assert "exec_command" in registry_names
    assert "write_stdin" in registry_names
    assert "shell" in registry_names


def test_apply_patch_metadata_freezes_canonical_family_and_editing_domain_boundary() -> None:
    metadata = builtin_tool_metadata("apply_patch")

    assert metadata is not None
    assert metadata["canonical_family"] == tool_family_mapping_runtime.APPLY_PATCH_CANONICAL_FAMILY
    assert metadata["canonical_tool_name"] == "apply_patch"
    assert metadata["editing_domain"] == tool_family_mapping_runtime.EDITING_DOMAIN_NAME
    assert (
        metadata["editing_domain_canonical_operations"]
        == tool_family_mapping_runtime.EDITING_DOMAIN_CANONICAL_OPERATIONS
    )
    assert metadata["codex_model_primary_tools"] == tool_family_mapping_runtime.APPLY_PATCH_CODEX_PRIMARY_TOOLS
    assert metadata["claude_model_primary_tools"] == tool_family_mapping_runtime.APPLY_PATCH_CLAUDE_PRIMARY_TOOLS
    assert metadata["projection_variants"] == tool_family_mapping_runtime.APPLY_PATCH_PROJECTION_VARIANTS
    assert metadata["model_default_exposure"] == "profile_declared"


def test_expert_review_metadata_freezes_canonical_family_and_runtime_binding() -> None:
    metadata = builtin_tool_metadata("expert_review")
    assert metadata is not None
    assert metadata["canonical_family"] == tool_family_mapping_runtime.EXPERT_REVIEW_CANONICAL_FAMILY
    assert metadata["canonical_tool_name"] == "expert_review"
    assert metadata["expert_review_runtime_binding"] == tool_family_mapping_runtime.EXPERT_REVIEW_RUNTIME_BINDING
    assert metadata["model_default_exposure"] == "conditional_gate"
    assert metadata["description"] == "Request a read-only expert review from a secondary eligible provider."
    assert metadata["usage_text"] == "Usage: /expert_review '{\"task\":\"...\"}'"
    assert "critical read-only review of the current mainline work" in metadata["provider_description"]
    assert "Do not use it as a substitute for normal mainline reasoning" in metadata["provider_description"]

    registry = {
        item["canonical_family"]: item
        for item in tool_family_metadata_runtime.builtin_canonical_family_registry()
    }
    expert_review = registry[tool_family_mapping_runtime.EXPERT_REVIEW_CANONICAL_FAMILY]
    assert expert_review["canonical_tool_names"] == ("expert_review",)
    assert expert_review["tool_runtime_binding"] == tool_family_mapping_runtime.EXPERT_REVIEW_RUNTIME_BINDING


def test_policy_tool_provider_descriptions_stay_english_only() -> None:
    import_spec = builtin_tool_metadata("policy_doc_import")
    list_spec = builtin_tool_metadata("policy_doc_list")
    search_spec = builtin_tool_metadata("policy_doc_search")
    read_spec = builtin_tool_metadata("policy_doc_read")

    assert import_spec is not None
    assert list_spec is not None
    assert search_spec is not None
    assert read_spec is not None

    assert "rule document" in import_spec["provider_description"]
    assert "rule documents" in list_spec["provider_description"]
    assert "policy basis, clause, procedure" in search_spec["provider_description"]
    assert "policy, clause, and procedure questions" in read_spec["provider_description"]


def test_builtin_canonical_family_registry_groups_tools_and_compatibility_aliases() -> None:
    registry = {
        item["canonical_family"]: item
        for item in tool_family_metadata_runtime.builtin_canonical_family_registry()
    }

    command_execution = registry[tool_family_mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY]
    assert command_execution["canonical_tool_names"] == ("exec_command", "write_stdin")
    assert command_execution["compatibility_aliases"] == ("shell",)
    assert command_execution["tool_capability_kind"] == "local_runtime_tool"
    assert command_execution["tool_runtime_binding"] == "local_runtime"

    browser = registry["browser"]
    assert browser["canonical_tool_names"] == ("browser",)
    assert browser["compatibility_aliases"] == ("open", "click", "find")


def test_builtin_canonical_family_resolution_requires_explicit_opt_in_for_aliases() -> None:
    assert tool_family_metadata_runtime.resolve_builtin_canonical_family("shell") is None

    resolved = tool_family_metadata_runtime.resolve_builtin_canonical_family(
        "shell",
        allow_compat_aliases=True,
    )

    assert resolved is not None
    assert resolved["canonical_family"] == tool_family_mapping_runtime.COMMAND_EXECUTION_CANONICAL_FAMILY
    assert resolved["resolved_from"] == "compatibility_alias"
