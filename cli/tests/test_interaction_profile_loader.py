from __future__ import annotations

import json
from pathlib import Path
import textwrap

import pytest

from cli.agent_cli.providers.interaction_profile_loader import (
    load_bundled_interaction_profile,
    load_bundled_interaction_profiles,
    load_interaction_profiles,
)
from cli.agent_cli.providers.interaction_profile_models import InteractionProfileLoadError


def _write_minimal_schema(profile_root: Path) -> None:
    schema_path = profile_root / "schema" / "interaction_profile.schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["schema_version", "profile", "tool_families", "fallback_profile"],
                "properties": {},
            }
        ),
        encoding="utf-8",
    )


def _minimal_profile_toml(
    *,
    profile: str,
    fallback_profile: str,
    web_search_projection: str,
    include_web_fallback: bool,
    exec_family_name: str = "exec_command",
) -> str:
    fallback_line = 'fallback_backend = "local"\n' if include_web_fallback else ""
    return textwrap.dedent(
        f"""
        schema_version = 1
        profile = "{profile}"
        display_name = "Test Profile"
        base_prompt_profile = "test_prompt"
        tool_surface_profile = "test_surface"
        context_prelude_policy = "test_context"
        tool_result_projection_policy = "test_projection"
        continuation_policy = "test_continuation"
        turn_protocol_policy = "test_turn_policy"
        fallback_profile = "{fallback_profile}"

        [required_capabilities]
        tool_calling = true

        [tool_families.{exec_family_name}]
        exposure = "enabled"
        projection = "canonical"

        [tool_families.web_search]
        exposure = "enabled"
        projection = "{web_search_projection}"
        {fallback_line}
        """
    ).strip() + "\n"


def test_load_bundled_interaction_profiles_success() -> None:
    profiles = load_bundled_interaction_profiles()
    assert set(profiles.keys()) == {"codex_openai", "claude_code", "generic_chat"}
    codex_exec = profiles["codex_openai"].tool_families["exec_command"]
    claude_exec = profiles["claude_code"].tool_families["exec_command"]
    generic_exec = profiles["generic_chat"].tool_families["exec_command"]

    assert codex_exec.canonical_family == "command_execution"
    assert codex_exec.projection_surface_family == "canonical_exec_pair"
    assert codex_exec.projected_primary_tools == ("exec_command",)
    assert codex_exec.projected_continuation_tools == ("write_stdin",)
    assert codex_exec.compatibility_aliases == ("shell",)
    assert codex_exec.event_projection_name == "commandExecution"

    assert claude_exec.canonical_family == "command_execution"
    assert claude_exec.projection_surface_family == "claude_shell_split"
    assert claude_exec.projected_primary_tools == ("Bash", "PowerShell")
    assert claude_exec.projected_continuation_tools == ("write_stdin",)
    assert claude_exec.compatibility_aliases == ("shell",)
    assert claude_exec.event_projection_name == "commandExecution"

    assert generic_exec.canonical_family == "command_execution"
    assert generic_exec.projection_surface_family == "canonical_exec_pair"
    assert generic_exec.projected_primary_tools == ("exec_command",)
    assert generic_exec.projected_continuation_tools == ("write_stdin",)
    assert generic_exec.compatibility_aliases == ("shell",)
    assert generic_exec.event_projection_name == "commandExecution"

    assert profiles["codex_openai"].tool_families["web_search"].projection == "native_if_available"
    assert profiles["codex_openai"].tool_families["web_search"].fallback_backend == "local"
    assert profiles["codex_openai"].optional_capabilities["native_web_search_runtime"] is True
    assert profiles["claude_code"].tool_families["web_search"].projection == "native_if_available"
    assert profiles["claude_code"].tool_families["web_search"].fallback_backend == "local"
    assert profiles["claude_code"].optional_capabilities["native_web_search_runtime"] is True
    assert profiles["generic_chat"].tool_families["web_search"].projection == "function"
    assert profiles["generic_chat"].optional_capabilities["native_web_search_runtime"] is False
    assert profiles["claude_code"].fallback_profile == "generic_chat"
    assert profiles["generic_chat"].fallback_profile == "none"

def test_load_bundled_interaction_profile_unknown_raises_hard_error() -> None:
    with pytest.raises(InteractionProfileLoadError, match="unknown interaction profile"):
        load_bundled_interaction_profile("missing_profile")


def test_loader_rejects_fallback_profile_self_reference(tmp_path: Path) -> None:
    _write_minimal_schema(tmp_path)
    bad_path = tmp_path / "bad.toml"
    bad_path.write_text(
        _minimal_profile_toml(
            profile="codex_openai",
            fallback_profile="codex_openai",
            web_search_projection="function",
            include_web_fallback=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(InteractionProfileLoadError, match="fallback_profile"):
        load_interaction_profiles(profile_root=tmp_path, profile_filenames=("bad.toml",))


def test_loader_rejects_native_projection_without_fallback_backend(tmp_path: Path) -> None:
    _write_minimal_schema(tmp_path)
    bad_path = tmp_path / "bad.toml"
    bad_path.write_text(
        _minimal_profile_toml(
            profile="codex_openai",
            fallback_profile="generic_chat",
            web_search_projection="native_if_available",
            include_web_fallback=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(InteractionProfileLoadError, match="native_if_available"):
        load_interaction_profiles(profile_root=tmp_path, profile_filenames=("bad.toml",))


def test_loader_allows_terminal_fallback_profile_none(tmp_path: Path) -> None:
    _write_minimal_schema(tmp_path)
    good_path = tmp_path / "generic.toml"
    good_path.write_text(
        _minimal_profile_toml(
            profile="generic_chat",
            fallback_profile="none",
            web_search_projection="function",
            include_web_fallback=False,
        ),
        encoding="utf-8",
    )

    profiles = load_interaction_profiles(profile_root=tmp_path, profile_filenames=("generic.toml",))

    assert profiles["generic_chat"].fallback_profile == "none"


def test_loader_projects_request_user_input_to_ask_user_question_for_claude_code_profile(tmp_path: Path) -> None:
    _write_minimal_schema(tmp_path)
    claude_path = tmp_path / "claude_code.toml"
    claude_path.write_text(
        textwrap.dedent(
            """
            schema_version = 1
            profile = "claude_code"
            display_name = "Claude Code"
            base_prompt_profile = "claude_code"
            tool_surface_profile = "claude_code"
            context_prelude_policy = "test_context"
            tool_result_projection_policy = "test_projection"
            continuation_policy = "test_continuation"
            turn_protocol_policy = "test_turn_policy"
            fallback_profile = "generic_chat"

            [required_capabilities]
            tool_calling = true

            [tool_families.exec_command]
            exposure = "enabled"
            projection = "claude_shell_split"

            [tool_families.request_user_input]
            exposure = "enabled"
            projection = "canonical"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    generic_path = tmp_path / "generic_chat.toml"
    generic_path.write_text(
        _minimal_profile_toml(
            profile="generic_chat",
            fallback_profile="none",
            web_search_projection="function",
            include_web_fallback=False,
        ),
        encoding="utf-8",
    )

    profiles = load_interaction_profiles(
        profile_root=tmp_path,
        profile_filenames=("claude_code.toml", "generic_chat.toml"),
    )

    request_user_input = profiles["claude_code"].tool_families["request_user_input"]
    assert request_user_input.projected_primary_tools == ("AskUserQuestion",)
    assert request_user_input.projection_surface_family == "claude_ask_user_question"


def test_loader_rejects_shell_alias_as_tool_family(tmp_path: Path) -> None:
    _write_minimal_schema(tmp_path)
    bad_path = tmp_path / "bad.toml"
    bad_path.write_text(
        _minimal_profile_toml(
            profile="generic_chat",
            fallback_profile="none",
            web_search_projection="function",
            include_web_fallback=False,
            exec_family_name="shell",
        ),
        encoding="utf-8",
    )

    with pytest.raises(InteractionProfileLoadError, match="compatibility alias"):
        load_interaction_profiles(profile_root=tmp_path, profile_filenames=("bad.toml",))


def test_loader_rejects_command_execution_event_name_as_tool_family(tmp_path: Path) -> None:
    _write_minimal_schema(tmp_path)
    bad_path = tmp_path / "bad.toml"
    bad_path.write_text(
        _minimal_profile_toml(
            profile="generic_chat",
            fallback_profile="none",
            web_search_projection="function",
            include_web_fallback=False,
            exec_family_name="commandExecution",
        ),
        encoding="utf-8",
    )

    with pytest.raises(InteractionProfileLoadError, match="event projection"):
        load_interaction_profiles(profile_root=tmp_path, profile_filenames=("bad.toml",))
