from __future__ import annotations

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.anthropic_claude import anthropic_tool_specs
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.system_prompts import build_chat_completions_system_prompt


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


def _claude_code_config() -> ProviderConfig:
    return ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        provider_name="anthropic",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
        interaction_profile="claude_code",
        interaction_profile_source="test",
    )


def test_claude_code_parity_contract_keeps_prompt_layers_source_aligned() -> None:
    prompt = build_chat_completions_system_prompt(
        host_platform=_host_platform(),
        config=_claude_code_config(),
    )

    assert prompt.startswith("You are Claude Code, Anthropic's official CLI for Claude.")
    assert "Write Agent tool description and prompt arguments in English" in prompt
    assert "The user-facing answer can still follow the user's language" in prompt
    assert "Do not overdo it. Be extra concise." in prompt
    assert "when your task will clearly require more than 3 queries" in prompt
    assert "concise report with an explicit length bound" in prompt

    assert "You are a coding agent running in the Codex CLI" not in prompt
    assert "If expert_review is exposed in this session" not in prompt
    assert "Use Agent only for bounded side tasks" not in prompt
    assert "Use wait_agent only when the next step explicitly depends" not in prompt
    assert "Do not describe or emit raw apply_patch grammar" not in prompt


def test_claude_code_parity_contract_keeps_agent_tool_surface_source_aligned() -> None:
    specs = anthropic_tool_specs(_claude_code_config(), _host_platform())
    names = {str(spec.get("name") or "") for spec in specs}

    assert {"Agent", "SendMessage", "Bash", "Read", "Glob", "Grep", "Write", "Edit"}.issubset(names)
    assert (
        not {
            "spawn_agent",
            "send_input",
            "resume_agent",
            "wait_agent",
            "agent_workflow",
            "recover_agent",
            "close_agent",
            "apply_patch",
            "request_user_input",
        }
        & names
    )

    agent_spec = next(spec for spec in specs if spec.get("name") == "Agent")
    schema = agent_spec["input_schema"]
    properties = schema["properties"]

    assert schema["required"] == ["description", "prompt"]
    assert properties["description"]["description"].startswith("Optional short 3-5 word English")
    assert "Write this prompt in English" in properties["prompt"]["description"]
    assert (
        "parent response to the user can still use the user's language"
        in properties["prompt"]["description"]
    )
    assert properties["subagent_type"]["enum"] == ["Explore"]
    assert properties["model"]["enum"] == ["sonnet", "opus", "haiku"]
    assert "provider" not in properties
    assert "reasoning_effort" not in properties
    assert "timeout" not in properties

    assert "not visible to the user" in agent_spec["description"]
    assert "description and prompt in English" in agent_spec["description"]
    assert "concise report with an explicit length bound" in agent_spec["description"]

    bash_spec = next(spec for spec in specs if spec.get("name") == "Bash")
    assert "File search: Use Glob (NOT find or ls)" in bash_spec["description"]
    assert "Content search: Use Grep (NOT grep or rg)" in bash_spec["description"]
