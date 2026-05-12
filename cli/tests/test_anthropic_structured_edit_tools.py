from __future__ import annotations

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.anthropic_claude import anthropic_tool_specs
from cli.agent_cli.providers.config_catalog import ProviderConfig


def _host_platform() -> HostPlatform:
    return HostPlatform(
        family="unix",
        os="linux",
        shell_kind="bash",
        shell_program="/bin/bash",
        list_dir_command="ls -la",
        print_working_dir_command="pwd",
        python_version_command="python -V",
    )


def test_anthropic_tool_specs_project_flat_apply_patch_schema_for_provider_compat() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        ),
        _host_platform(),
    )

    apply_patch = next(spec for spec in specs if spec.get("name") == "apply_patch")
    schema = apply_patch["input_schema"]

    assert "patch" in schema["properties"]
    assert "operation" in schema["properties"]
    assert schema["properties"]["operation"]["enum"] == ["patch", "file_write", "file_edit"]
    assert "file_path" in schema["properties"]
    assert "content" in schema["properties"]
    assert "old_string" in schema["properties"]
    assert "new_string" in schema["properties"]
    assert "replace_all" in schema["properties"]
    assert "minProperties" not in schema
    assert "anyOf" not in schema


def test_anthropic_tool_specs_keep_single_apply_patch_entry_without_new_global_tool_names() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        ),
        _host_platform(),
    )

    names = [str(spec.get("name") or "") for spec in specs]
    assert names.count("apply_patch") == 1
    assert "file_write" not in names
    assert "file_edit" not in names


def test_anthropic_tool_specs_project_write_for_claude_code_profile() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
        _host_platform(),
    )

    names = [str(spec.get("name") or "") for spec in specs]
    assert "Write" in names
    assert "Edit" in names
    assert "apply_patch" not in names

    write_spec = next(spec for spec in specs if spec.get("name") == "Write")
    schema = write_spec["input_schema"]
    assert schema["required"] == ["file_path", "content"]
    assert "file_path" in schema["properties"]
    assert "content" in schema["properties"]

    edit_spec = next(spec for spec in specs if spec.get("name") == "Edit")
    edit_schema = edit_spec["input_schema"]
    assert edit_schema["required"] == ["file_path", "old_string", "new_string"]
    assert "file_path" in edit_schema["properties"]
    assert "old_string" in edit_schema["properties"]
    assert "new_string" in edit_schema["properties"]
    assert "replace_all" in edit_schema["properties"]
    assert "match exactly once unless replace_all=true" in edit_schema["properties"]["old_string"]["description"]


def test_anthropic_tool_specs_project_ask_user_question_for_claude_code_profile() -> None:
    specs = anthropic_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="sk-claude",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            interaction_profile="claude_code",
            interaction_profile_source="test",
        ),
        _host_platform(),
    )

    names = [str(spec.get("name") or "") for spec in specs]
    assert "AskUserQuestion" in names
    assert "request_user_input" not in names

    ask_user_question_spec = next(spec for spec in specs if spec.get("name") == "AskUserQuestion")
    schema = ask_user_question_spec["input_schema"]
    assert schema["required"] == ["questions"]
    assert "questions" in schema["properties"]
