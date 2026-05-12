from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.builtin_provider_tool_specs import builtin_provider_tool_specs
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.delegation_policy import (
    DELEGATION_MODE_VALUES,
    DELEGATION_TASK_SHAPES,
    RECOVER_AGENT_ACTION_VALUES,
    SPAWN_AGENT_REASON_CODES,
    WAIT_AGENT_REASON_CODES,
)
from cli.agent_cli.providers.tool_specs import (
    merged_provider_tool_specs,
    provider_tool_names,
    responses_provider_tool_specs,
)


def _provider_config() -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
    )


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


def _provider_description(name: str) -> str:
    return f"desc:{name}"


def _provider_action_names(name: str) -> tuple[str, ...]:
    if name == "browser":
        return ("open", "click")
    return ()


def _native_web_search_capability(
    main_loop_spec_kind: str = "function",
    *,
    effective_mode: str = "live",
) -> SimpleNamespace:
    return SimpleNamespace(main_loop_spec_kind=main_loop_spec_kind, effective_mode=effective_mode)


def test_builtin_provider_tool_specs_preserves_delegation_family_contract() -> None:
    specs = builtin_provider_tool_specs(
        _provider_config(),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(),
        browser_provider_actions=("open",),
    )

    by_name = {
        entry["function"]["name"]: entry for entry in specs if entry.get("type") == "function"
    }

    spawn = by_name["spawn_agent"]["function"]["parameters"]["properties"]
    assert spawn["reason"]["enum"] == list(SPAWN_AGENT_REASON_CODES)
    assert spawn["mode"]["enum"] == list(DELEGATION_MODE_VALUES)
    assert spawn["task_shape"]["enum"] == list(DELEGATION_TASK_SHAPES)
    spawn_child = by_name["spawn_child_tab"]["function"]["parameters"]
    assert spawn_child["required"] == ["task"]
    assert "task_name" in spawn_child["properties"]
    send_child = by_name["send_child_tab"]["function"]["parameters"]
    assert send_child["required"] == ["target", "message"]
    wait_child = by_name["wait_child_tasks"]["function"]["parameters"]
    assert wait_child["properties"]["timeout_ms"]["type"] == "integer"
    assert wait_child["properties"]["wait_for"]["enum"] == ["all", "any"]
    request_orchestration = by_name["request_orchestration"]["function"]["parameters"]
    assert request_orchestration["required"] == [
        "source_text",
        "goal",
        "reason",
        "needs_confirmation",
    ]
    assert request_orchestration["properties"]["risk_level"]["enum"] == ["low", "medium", "high"]

    wait = by_name["wait_agent"]["function"]["parameters"]["properties"]
    assert wait["reason"]["enum"] == list(WAIT_AGENT_REASON_CODES)

    recover = by_name["recover_agent"]["function"]["parameters"]["properties"]
    assert recover["action"]["enum"] == list(RECOVER_AGENT_ACTION_VALUES)


def test_builtin_provider_tool_specs_keeps_web_search_inserted_before_update_plan() -> None:
    plain_specs = builtin_provider_tool_specs(
        _provider_config(),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(),
        browser_provider_actions=("open",),
    )
    plain_names = [
        entry["function"]["name"] for entry in plain_specs if entry.get("type") == "function"
    ]
    assert plain_names[10] == "web_search"
    assert plain_names[3] == "request_orchestration"
    assert plain_names[4] == "spawn_child_tab"
    assert plain_names[5] == "send_child_tab"
    assert plain_names[6] == "wait_child_tasks"
    assert plain_names[9] == "wait_agent"
    assert plain_names[11] == "agent_workflow"
    assert plain_names[12] == "recover_agent"
    assert plain_names.index("web_search") < plain_names.index("update_plan")

    native_specs = builtin_provider_tool_specs(
        _provider_config(),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(
            "openai_responses_native"
        ),
        browser_provider_actions=("open",),
    )
    assert native_specs[10] == {"type": "web_search", "external_web_access": True}
    native_names = [
        entry["function"]["name"] for entry in native_specs if entry.get("type") == "function"
    ]
    assert native_names[3] == "request_orchestration"
    assert native_names[4] == "spawn_child_tab"
    assert native_names[5] == "send_child_tab"
    assert native_names[6] == "wait_child_tasks"
    assert native_names[9] == "wait_agent"
    assert native_names[10] == "agent_workflow"
    assert native_names[11] == "recover_agent"
    assert native_names.index("update_plan") > native_names.index("recover_agent")


def test_builtin_provider_tool_specs_uses_effective_cached_mode_for_openai_native_web_search() -> (
    None
):
    native_specs = builtin_provider_tool_specs(
        _provider_config(),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(
            "openai_responses_native",
            effective_mode="cached",
        ),
        browser_provider_actions=("open",),
    )

    assert native_specs[10] == {"type": "web_search", "external_web_access": False}


def test_builtin_provider_tool_specs_exposes_anthropic_native_web_search() -> None:
    specs = builtin_provider_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
        ),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(
            "anthropic_native"
        ),
        browser_provider_actions=("open",),
    )

    web_search = next(entry for entry in specs if entry.get("name") == "web_search")
    assert web_search["type"] == "web_search_20250305"
    assert web_search["max_uses"] == 8


def test_builtin_provider_tool_specs_exposes_glm_native_web_search_shape() -> None:
    specs = builtin_provider_tool_specs(
        ProviderConfig(
            model="glm-5",
            api_key="test-key",
            provider_name="glm",
            planner_kind="openai_chat",
        ),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(
            "glm_native"
        ),
        browser_provider_actions=("open",),
    )

    web_search = next(entry for entry in specs if entry.get("type") == "web_search")
    assert web_search["web_search"]["enable"] is True
    assert web_search["web_search"]["search_engine"] == "search_pro"
    assert web_search["function"]["name"] == "web_search"


def test_builtin_provider_tool_specs_keeps_function_web_search_for_non_native_anthropic_wire() -> (
    None
):
    specs = builtin_provider_tool_specs(
        ProviderConfig(
            model="glm-5",
            api_key="test-key",
            provider_name="glm-claude-mode",
            planner_kind="anthropic_messages",
            wire_api="anthropic_messages",
        ),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(),
        browser_provider_actions=("open",),
    )

    web_search = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "web_search"
    )
    assert web_search["function"]["parameters"]["required"] == ["query"]
    assert "query" in web_search["function"]["parameters"]["properties"]


def test_builtin_provider_tool_specs_routes_web_search_through_unified_builder_path() -> None:
    config = _provider_config()
    sentinel_spec = {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "sentinel",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }

    with patch(
        "cli.agent_cli.providers.builtin_provider_tool_specs_runtime.web_search_provider_spec",
        return_value=sentinel_spec,
    ) as builder:
        specs = builtin_provider_tool_specs(
            config,
            _host_platform(),
            provider_description=_provider_description,
            provider_action_names=_provider_action_names,
            resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(),
            browser_provider_actions=("open",),
        )

    assert specs[10] == sentinel_spec
    builder.assert_called_once()
    call_kwargs = builder.call_args.kwargs
    assert call_kwargs["config"] is config
    assert callable(call_kwargs["resolve_native_web_search_capability_fn"])


def test_builtin_provider_tool_specs_keeps_function_web_search_for_openai_without_mixed_tools_opt_in() -> (
    None
):
    specs = builtin_provider_tool_specs(
        _provider_config(),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(),
        browser_provider_actions=("open",),
    )

    web_search = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "web_search"
    )
    assert web_search["function"]["parameters"]["required"] == ["query"]
    assert "query" in web_search["function"]["parameters"]["properties"]


def test_builtin_provider_tool_specs_keeps_function_web_search_when_effective_mode_disabled() -> (
    None
):
    specs = builtin_provider_tool_specs(
        _provider_config(),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: SimpleNamespace(
            main_loop_spec_kind="openai_responses_native",
            effective_mode="disabled",
        ),
        browser_provider_actions=("open",),
    )

    web_search = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "web_search"
    )
    assert web_search["function"]["parameters"]["required"] == ["query"]


def test_expert_review_hidden_from_model_surface_without_gate_snapshot() -> None:
    config = _provider_config()

    names = provider_tool_names(config, _host_platform())
    specs = merged_provider_tool_specs(config, _host_platform())
    responses_specs = responses_provider_tool_specs(
        config, _host_platform(), plugin_manager_factory=lambda: None
    )

    assert "expert_review" not in names
    assert "expert_review" not in {
        entry["function"]["name"] for entry in specs if entry.get("type") == "function"
    }
    assert "expert_review" not in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }


def test_expert_review_visible_in_model_surface_when_gate_snapshot_available() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        raw_provider={"expert_review_available": True},
    )

    names = provider_tool_names(config, _host_platform())
    specs = merged_provider_tool_specs(config, _host_platform())
    responses_specs = responses_provider_tool_specs(
        config, _host_platform(), plugin_manager_factory=lambda: None
    )

    assert "expert_review" in names
    expert_review = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "expert_review"
    )
    properties = expert_review["function"]["parameters"]["properties"]
    assert expert_review["function"]["parameters"]["required"] == ["task"]
    assert sorted(properties.keys()) == ["task"]
    assert any(
        entry.get("type") == "function" and entry.get("name") == "expert_review"
        for entry in responses_specs
    )


def test_codex_openai_reference_surface_hides_expert_review_even_when_gate_snapshot_available() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        interaction_profile="codex_openai",
        interaction_profile_source="test",
        raw_provider={"expert_review_available": True},
    )

    names = provider_tool_names(config, _host_platform())
    responses_specs = responses_provider_tool_specs(
        config, _host_platform(), plugin_manager_factory=lambda: None
    )

    assert "expert_review" not in names
    assert not any(
        entry.get("type") == "function" and entry.get("name") == "expert_review"
        for entry in responses_specs
    )


def test_command_surface_projection_omits_apply_patch_for_unknown_model_fallback() -> None:
    config = ProviderConfig(
        model="unlisted-reference-model",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        interaction_profile="codex_openai",
        interaction_profile_source="test",
    )

    names = provider_tool_names(config, _host_platform())

    assert "exec_command" in names
    assert "write_stdin" in names
    assert "apply_patch" not in names
    assert "Write" not in names
    assert "Edit" not in names
    assert "Bash" not in names
    assert "PowerShell" not in names
    assert "shell" not in names


def test_command_surface_projection_keeps_apply_patch_for_codex_models() -> None:
    config = ProviderConfig(
        model="gpt-5-codex",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        interaction_profile="codex_openai",
        interaction_profile_source="test",
    )

    names = provider_tool_names(config, _host_platform())

    assert "exec_command" in names
    assert "write_stdin" in names
    assert "apply_patch" in names
    assert "Write" not in names
    assert "Edit" not in names


def test_delegation_surface_projection_exposes_codex_openai_default_responses_collab_tools() -> (
    None
):
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        interaction_profile="codex_openai",
        interaction_profile_source="test",
    )

    names = provider_tool_names(config, _host_platform())
    specs = merged_provider_tool_specs(config, _host_platform())
    responses_specs = responses_provider_tool_specs(
        config, _host_platform(), plugin_manager_factory=lambda: None
    )

    assert "spawn_agent" not in names
    assert "send_input" not in names
    assert "resume_agent" not in names
    assert "wait" not in names
    assert "close_agent" not in names
    assert "request_orchestration" not in names
    assert "wait_agent" not in names
    assert "agent_workflow" not in names
    assert "recover_agent" not in names

    function_names = {
        entry["function"]["name"] for entry in specs if entry.get("type") == "function"
    }
    assert "spawn_agent" not in function_names
    assert "send_input" not in function_names
    assert "resume_agent" not in function_names
    assert "wait" not in function_names
    assert "close_agent" not in function_names
    assert "request_orchestration" not in function_names
    assert "wait_agent" not in function_names
    assert "agent_workflow" not in function_names
    assert "recover_agent" not in function_names

    response_names = {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "spawn_agent" in response_names
    assert "send_input" in response_names
    assert "resume_agent" in response_names
    assert "wait" not in response_names
    assert "close_agent" in response_names
    assert "wait_agent" in response_names
    assert "agent_workflow" not in response_names
    assert "recover_agent" not in response_names


def test_command_surface_projection_keeps_generic_chat_conservative_exec_pair() -> None:
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_chat",
        interaction_profile="generic_chat",
        interaction_profile_source="test",
    )

    names = provider_tool_names(config, _host_platform())

    assert "exec_command" in names
    assert "write_stdin" in names
    assert "apply_patch" in names
    assert "Write" not in names
    assert "Edit" not in names
    assert "Bash" not in names
    assert "PowerShell" not in names
    assert "shell" not in names


def test_command_surface_projection_projects_claude_code_to_bash_only_on_unix() -> None:
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )

    names = provider_tool_names(config, _host_platform())
    specs = merged_provider_tool_specs(config, _host_platform())
    responses_specs = responses_provider_tool_specs(
        config, _host_platform(), plugin_manager_factory=lambda: None
    )

    assert "Bash" in names
    assert "PowerShell" not in names
    assert "Agent" in names
    assert "SendMessage" in names
    assert "exec_command" not in names
    assert "write_stdin" in names
    assert "Write" in names
    assert "Edit" in names
    assert "AskUserQuestion" in names
    assert "apply_patch" not in names
    assert "request_user_input" not in names
    assert "spawn_agent" not in names
    assert "send_input" not in names
    assert "resume_agent" not in names
    assert "wait_agent" not in names
    assert "agent_workflow" not in names
    assert "recover_agent" not in names
    assert "close_agent" not in names
    assert "shell" not in names

    bash_spec = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "Bash"
    )
    assert bash_spec["function"]["parameters"]["required"] == ["command"]
    assert "run_in_background" in bash_spec["function"]["parameters"]["properties"]
    assert (
        "write_stdin later to poll or continue that session"
        in bash_spec["function"]["parameters"]["properties"]["run_in_background"]["description"]
    )
    assert (
        "initial wait budget"
        in bash_spec["function"]["parameters"]["properties"]["timeout"]["description"]
    )

    bash_responses_spec = next(
        entry
        for entry in responses_specs
        if entry.get("type") == "function" and entry.get("name") == "Bash"
    )
    assert bash_responses_spec["parameters"]["required"] == ["command"]
    write_spec = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "Write"
    )
    assert write_spec["function"]["parameters"]["required"] == ["file_path", "content"]
    assert (
        "Use Read first before overwriting an existing file."
        in write_spec["function"]["description"]
    )
    assert (
        "Prefer Edit for targeted changes to existing files"
        in write_spec["function"]["description"]
    )
    assert "Reference-style structured patch" not in write_spec["function"]["description"]
    edit_spec = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "Edit"
    )
    assert edit_spec["function"]["parameters"]["required"] == [
        "file_path",
        "old_string",
        "new_string",
    ]
    assert "Use Read before editing." in edit_spec["function"]["description"]
    assert "smallest clearly unique span" in edit_spec["function"]["description"]
    assert "Reference-style structured patch" not in edit_spec["function"]["description"]
    write_responses_spec = next(
        entry
        for entry in responses_specs
        if entry.get("type") == "function" and entry.get("name") == "Write"
    )
    assert (
        "Use Read first before overwriting an existing file." in write_responses_spec["description"]
    )
    edit_responses_spec = next(
        entry
        for entry in responses_specs
        if entry.get("type") == "function" and entry.get("name") == "Edit"
    )
    assert "match exactly once unless replace_all=true" in edit_responses_spec["description"]
    write_responses_spec = next(
        entry
        for entry in responses_specs
        if entry.get("type") == "function" and entry.get("name") == "Write"
    )
    assert write_responses_spec["parameters"]["required"] == ["file_path", "content"]
    edit_spec = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "Edit"
    )
    assert edit_spec["function"]["parameters"]["required"] == [
        "file_path",
        "old_string",
        "new_string",
    ]
    edit_responses_spec = next(
        entry
        for entry in responses_specs
        if entry.get("type") == "function" and entry.get("name") == "Edit"
    )
    assert edit_responses_spec["parameters"]["required"] == [
        "file_path",
        "old_string",
        "new_string",
    ]
    agent_spec = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "Agent"
    )
    assert agent_spec["function"]["parameters"]["required"] == ["description", "prompt"]
    agent_properties = agent_spec["function"]["parameters"]["properties"]
    assert "run_in_background" in agent_properties
    assert "English task label" in agent_properties["description"]["description"]
    assert "Write this prompt in English" in agent_properties["prompt"]["description"]
    assert agent_properties["model"]["enum"] == ["sonnet", "opus", "haiku"]
    assert "provider" not in agent_properties
    assert "reasoning_effort" not in agent_properties
    assert "timeout" not in agent_properties
    send_message_spec = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "SendMessage"
    )
    assert send_message_spec["function"]["parameters"]["required"] == ["to", "message"]
    ask_user_question_spec = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "AskUserQuestion"
    )
    assert ask_user_question_spec["function"]["parameters"]["required"] == ["questions"]
    ask_user_question_responses_spec = next(
        entry
        for entry in responses_specs
        if entry.get("type") == "function" and entry.get("name") == "AskUserQuestion"
    )
    assert ask_user_question_responses_spec["parameters"]["required"] == ["questions"]
    assert "exec_command" not in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "write_stdin" in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "Agent" in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "SendMessage" in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "spawn_agent" not in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "send_input" not in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "apply_patch" not in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }
    assert "request_user_input" not in {
        entry.get("name") for entry in responses_specs if entry.get("type") == "function"
    }


def test_command_surface_projection_projects_claude_code_to_bash_and_powershell_on_windows() -> (
    None
):
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )
    windows_host = HostPlatform(
        family="windows",
        os="windows",
        shell_kind="powershell",
        shell_program="powershell.exe",
        list_dir_command="Get-ChildItem -Force",
        print_working_dir_command="Get-Location",
        python_version_command="python -V",
    )

    names = provider_tool_names(config, windows_host)
    responses_specs = responses_provider_tool_specs(
        config, windows_host, plugin_manager_factory=lambda: None
    )

    assert "Bash" in names
    assert "PowerShell" in names
    assert "Agent" in names
    assert "SendMessage" in names
    assert "exec_command" not in names
    assert "write_stdin" in names
    assert "Write" in names
    assert "Edit" in names
    assert "AskUserQuestion" in names
    assert "apply_patch" not in names
    assert "request_user_input" not in names
    assert "spawn_agent" not in names
    assert "send_input" not in names

    powershell_spec = next(
        entry
        for entry in responses_specs
        if entry.get("type") == "function" and entry.get("name") == "PowerShell"
    )
    assert powershell_spec["parameters"]["required"] == ["command"]
    assert "dangerouslyDisableSandbox" in powershell_spec["parameters"]["properties"]
    assert (
        "approval justification"
        in powershell_spec["parameters"]["properties"]["description"]["description"]
    )
    assert any(
        entry.get("name") == "Agent" for entry in responses_specs if entry.get("type") == "function"
    )
    assert any(
        entry.get("name") == "SendMessage"
        for entry in responses_specs
        if entry.get("type") == "function"
    )
    assert any(
        entry.get("name") == "Write" for entry in responses_specs if entry.get("type") == "function"
    )
    assert any(
        entry.get("name") == "Edit" for entry in responses_specs if entry.get("type") == "function"
    )
    assert any(
        entry.get("name") == "AskUserQuestion"
        for entry in responses_specs
        if entry.get("type") == "function"
    )


def test_builtin_provider_tool_specs_apply_patch_accepts_structured_edit_arguments() -> None:
    specs = builtin_provider_tool_specs(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
        ),
        _host_platform(),
        provider_description=_provider_description,
        provider_action_names=_provider_action_names,
        resolve_native_web_search_capability_fn=lambda _: _native_web_search_capability(),
        browser_provider_actions=("open",),
    )

    apply_patch = next(
        entry
        for entry in specs
        if entry.get("type") == "function" and entry["function"]["name"] == "apply_patch"
    )
    properties = apply_patch["function"]["parameters"]["properties"]
    parameters = apply_patch["function"]["parameters"]
    assert "patch" in properties
    assert "operation" in properties
    assert properties["operation"]["enum"] == ["patch", "file_write", "file_edit"]
    assert "file_path" in properties
    assert "content" in properties
    assert "old_string" in properties
    assert "new_string" in properties
    assert "replace_all" in properties
    assert "minProperties" not in parameters
    assert "anyOf" not in parameters
