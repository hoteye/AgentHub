from __future__ import annotations

from cli.agent_cli.slash_parser import (
    is_slash_command_text,
    legacy_handler_arg_text,
    parse_slash_invocation,
    split_slash_like_tokens,
)
from cli.agent_cli.slash_surface import normalize_command_text


def test_parse_slash_invocation_models_keywords_and_positionals() -> None:
    invocation = parse_slash_invocation("/model gpt_54 high user")

    assert invocation.command_name == "model"
    assert invocation.positionals == ("gpt_54",)
    assert invocation.keywords == (("reasoning-effort", "high"), ("write", "user"))
    assert invocation.switches == ()
    assert invocation.legacy_compat_used is False
    assert legacy_handler_arg_text(invocation) == "gpt_54 --reasoning-effort high --write user"


def test_parse_slash_invocation_supports_legacy_flags_without_normalize_entrypoint() -> None:
    invocation = parse_slash_invocation("/provider --verbose")

    assert invocation.command_name == "provider"
    assert invocation.positionals == ()
    assert invocation.switches == ("verbose",)
    assert invocation.legacy_compat_used is True
    assert legacy_handler_arg_text(invocation) == "--verbose"


def test_parse_slash_invocation_supports_exec_command_legacy_cmd_flag() -> None:
    invocation = parse_slash_invocation('/exec_command --cmd "python -V" --yield-time-ms 250')

    assert invocation.command_name == "exec_command"
    assert invocation.positionals == ()
    assert invocation.keywords == (("cmd", "python -V"), ("yield-time-ms", "250"))
    assert invocation.legacy_compat_used is True
    assert legacy_handler_arg_text(invocation) == "--cmd 'python -V' --yield-time-ms 250"


def test_parse_slash_invocation_supports_exec_command_extended_legacy_flags() -> None:
    invocation = parse_slash_invocation(
        "/exec_command 'ls -la' --timeout-ms 30000 --sandbox-permissions use_default "
        "--justification inspect --prefix-rule git,pull"
    )

    assert invocation.command_name == "exec_command"
    assert invocation.positionals == ("ls -la",)
    assert invocation.keywords == (
        ("timeout-ms", "30000"),
        ("sandbox-permissions", "use_default"),
        ("justification", "inspect"),
        ("prefix-rule", "git,pull"),
    )
    assert invocation.legacy_compat_used is True
    assert legacy_handler_arg_text(invocation) == (
        "'ls -la' --timeout-ms 30000 --sandbox-permissions use_default "
        "--justification inspect --prefix-rule git,pull"
    )


def test_parse_slash_invocation_supports_exec_command_additional_permissions_json_flag() -> None:
    invocation = parse_slash_invocation(
        "/exec_command 'ls -la' --additional-permissions-json "
        '\'{"file_system":{"write":["/tmp/out"]}}\''
    )

    assert invocation.command_name == "exec_command"
    assert invocation.positionals == ("ls -la",)
    assert invocation.keywords == (
        ("additional-permissions-json", '{"file_system":{"write":["/tmp/out"]}}'),
    )
    assert invocation.legacy_compat_used is True
    assert legacy_handler_arg_text(invocation) == (
        '\'ls -la\' --additional-permissions-json \'{"file_system":{"write":["/tmp/out"]}}\''
    )


def test_split_slash_like_tokens_handles_slash_plain_and_malformed_quotes() -> None:
    assert split_slash_like_tokens("/provider verbose") == ("provider", "verbose")
    assert split_slash_like_tokens("provider") == ("provider",)
    assert split_slash_like_tokens('/provider "oops') == ("provider", '"oops')
    assert is_slash_command_text("   /help") is True
    assert is_slash_command_text("provider") is False


def test_parse_slash_invocation_preserves_quoted_newline_in_positionals_and_legacy_text() -> None:
    invocation = parse_slash_invocation("/write_stdin session_1 'stop\n' --yield-time-ms 300")

    assert invocation.command_name == "write_stdin"
    assert invocation.positionals == ("session_1", "stop\n")
    assert invocation.keywords == (("yield-time-ms", "300"),)
    assert legacy_handler_arg_text(invocation) == "session_1 'stop\n' --yield-time-ms 300"
    assert normalize_command_text("/write_stdin session_1 'stop\n' --yield-time-ms 300") == (
        "/write_stdin session_1 'stop\n' --yield-time-ms 300"
    )


def test_legacy_handler_arg_text_preserves_orchestrate_markdown() -> None:
    markdown = (
        "# Demo orchestration run\n\n"
        "### CARD-001: Research workflow surface\n"
        "- goal: capture workflow surface\n"
        "- owned_files: docs/research.md\n"
        "- acceptance_criteria: findings captured\n"
    )
    invocation = parse_slash_invocation(f"/orchestrate {markdown}")

    assert invocation.command_name == "orchestrate"
    assert "### CARD-001" in invocation.raw_arg_text
    assert legacy_handler_arg_text(invocation) == markdown.strip()


def test_legacy_handler_arg_text_preserves_unquoted_json_for_json_commands() -> None:
    invocation = parse_slash_invocation(
        '/__request_orchestration {"source_text": "x", "needs_confirmation": true}'
    )

    assert invocation.command_name == "__request_orchestration"
    assert legacy_handler_arg_text(invocation) == '{"source_text": "x", "needs_confirmation": true}'
