"""Tests for compound command splitting and validation in command_policy_runtime."""

from __future__ import annotations

import pytest

from cli.agent_cli.runtime_services.command_policy_runtime import (
    CompoundCommandValidation,
    evaluate_command_policy,
    split_compound_command,
    validate_compound_command_segments,
    COMMAND_POLICY_MODE_ENV,
)


class TestSplitCompoundCommand:
    def test_simple_and(self):
        assert split_compound_command("ls && pwd") == ["ls", "pwd"]

    def test_multiple_operators(self):
        result = split_compound_command("ls && pwd || echo hi ; date")
        assert result == ["ls", "pwd", "echo hi", "date"]

    def test_pipe_not_split(self):
        result = split_compound_command("ls | grep foo && echo done")
        assert result == ["ls | grep foo", "echo done"]

    def test_quoted_operators_preserved(self):
        result = split_compound_command('echo "a && b" && pwd')
        assert result == ['echo "a && b"', "pwd"]

    def test_single_quoted_operators_preserved(self):
        result = split_compound_command("echo 'a && b' && pwd")
        assert result == ["echo 'a && b'", "pwd"]

    def test_single_command_no_split(self):
        assert split_compound_command("ls -la") == ["ls -la"]

    def test_trailing_operator(self):
        result = split_compound_command("ls &&")
        assert result == ["ls"]

    def test_empty_command(self):
        assert split_compound_command("") == []
        assert split_compound_command("   ") == []

    def test_semicolon_split(self):
        result = split_compound_command("echo hello ; echo world")
        assert result == ["echo hello", "echo world"]

    def test_or_operator(self):
        result = split_compound_command("ls || echo fallback")
        assert result == ["ls", "echo fallback"]


class TestValidateCompoundCommandSegments:
    def test_safe_compound(self):
        result = validate_compound_command_segments("ls && pwd")
        assert result.safe is True
        assert result.segments == ["ls", "pwd"]
        assert result.dangerous_constructs == []

    def test_subshell_rejected(self):
        result = validate_compound_command_segments("ls && (rm -rf /)")
        assert result.safe is False
        assert result.error_code == "compound_command_dangerous_construct"
        assert any("subshell" in c for c in result.dangerous_constructs)

    def test_command_substitution_dollar_paren(self):
        result = validate_compound_command_segments("ls && echo $(whoami)")
        assert result.safe is False
        assert any("command substitution" in c for c in result.dangerous_constructs)

    def test_backtick_substitution(self):
        result = validate_compound_command_segments("ls && echo `whoami`")
        assert result.safe is False
        assert any("backtick" in c for c in result.dangerous_constructs)

    def test_variable_expansion(self):
        result = validate_compound_command_segments("ls && echo $HOME")
        assert result.safe is False
        assert any("variable expansion" in c for c in result.dangerous_constructs)

    def test_variable_expansion_braces(self):
        result = validate_compound_command_segments("ls && echo ${HOME}")
        assert result.safe is False
        assert any("variable expansion" in c for c in result.dangerous_constructs)

    def test_eval_rejected(self):
        result = validate_compound_command_segments('eval "rm -rf /"')
        assert result.safe is False
        assert any("dangerous builtin" in c for c in result.dangerous_constructs)

    def test_source_rejected(self):
        result = validate_compound_command_segments("source ~/.bashrc && ls")
        assert result.safe is False
        assert any("dangerous builtin" in c for c in result.dangerous_constructs)

    def test_single_quoted_variable_safe(self):
        """Variables inside single quotes are literal, should be safe."""
        result = validate_compound_command_segments("echo '$HOME' && pwd")
        assert result.safe is True

    def test_empty_command(self):
        result = validate_compound_command_segments("")
        assert result.safe is True
        assert result.segments == []

    def test_pipe_with_safe_commands(self):
        result = validate_compound_command_segments("ls | grep foo && echo done")
        assert result.safe is True
        assert result.segments == ["ls | grep foo", "echo done"]


class TestEvaluateCommandPolicyCompound:
    """Test that evaluate_command_policy integrates compound validation."""

    def _env(self, **overrides: str) -> dict[str, str]:
        base = {COMMAND_POLICY_MODE_ENV: "standard"}
        base.update(overrides)
        return base

    def test_safe_compound_allowed(self):
        decision = evaluate_command_policy("ls && pwd", environ=self._env())
        assert decision.allowed is True
        assert decision.metadata.get("compound_segments") == ["ls", "pwd"]
        assert decision.metadata.get("compound_segments_count") == 2

    def test_dangerous_compound_denied(self):
        decision = evaluate_command_policy("ls && echo $(whoami)", environ=self._env())
        assert decision.allowed is False
        assert decision.error_code == "compound_command_dangerous_construct"

    def test_non_compound_passthrough(self):
        decision = evaluate_command_policy("ls -la", environ=self._env())
        assert decision.allowed is True
        assert "compound_segments" not in (decision.metadata or {})

    def test_no_policy_mode_passthrough(self):
        """Without policy mode set, compound commands pass through without validation."""
        decision = evaluate_command_policy("ls && echo $HOME", environ={})
        assert decision.allowed is True
