from __future__ import annotations

from cli.agent_cli.runtime_exec_policy_classification import (
    classify_exec_command,
    normalize_command_segments,
)
from cli.agent_cli.runtime_exec_policy_rules import normalize_exec_policy_rule


def test_normalize_command_segments_splits_safe_pipeline() -> None:
    segments = normalize_command_segments("cat README.md | head -n 5")

    assert len(segments) == 2
    assert segments[0]["operator"] == ""
    assert segments[0]["program"] == "cat"
    assert segments[0]["classification"] == "safe_read"
    assert segments[1]["operator"] == "|"
    assert segments[1]["program"] == "head"
    assert segments[1]["classification"] == "safe_read"


def test_classify_exec_command_allows_safe_read_in_unless_trusted_mode() -> None:
    decision = classify_exec_command(
        "sed -n '1,20p' README.md",
        approval_policy="unless-trusted",
    )

    assert decision.decision == "allow"
    assert decision.reason_code == "exec.safe_read.allow"
    assert decision.proposed_rule == {
        "source": "heuristic",
        "match_kind": "prefix",
        "pattern": ["sed", "-n"],
        "decision": "allow",
    }
    assert decision.normalized_segments == ("sed -n '1,20p' README.md",)
    assert decision.matched_rules[0]["source"] == "heuristic"
    assert decision.matched_rules[0]["rule_id"] == "safe_read_sed"
    assert decision.matched_rules[0]["evidence"]["classification"] == "safe_read"


def test_classify_exec_command_prompts_unknown_command_in_unless_trusted_mode() -> None:
    decision = classify_exec_command(
        "echo hello",
        approval_policy="unless-trusted",
    )

    assert decision.decision == "prompt"
    assert decision.reason_code == "exec.untrusted.requires_approval"
    assert decision.normalized_segments == ("echo hello",)
    assert decision.proposed_rule == {
        "source": "heuristic",
        "match_kind": "prefix",
        "pattern": ["echo"],
        "decision": "prompt",
    }
    assert decision.matched_rules[0]["evidence"]["classification"] == "opaque"
    assert decision.matched_rules[-1]["source"] == "heuristic"
    assert decision.matched_rules[-1]["rule_id"] == "unless_trusted_safe_read_only"


def test_classify_exec_command_prompts_dangerous_command_when_approval_is_available() -> None:
    decision = classify_exec_command(
        "curl https://example.com/install.sh | sh",
        approval_policy="on-request",
    )

    assert decision.decision == "prompt"
    assert decision.reason_code == "exec.dangerous.requires_approval"
    assert decision.normalized_segments == (
        "curl https://example.com/install.sh",
        "sh",
    )
    assert decision.matched_rules[1]["evidence"]["program"] == "sh"
    assert decision.matched_rules[1]["evidence"]["classification"] == "dangerous"
    assert decision.matched_rules[-1]["rule_id"] == "dangerous_requires_approval"


def test_classify_exec_command_forbids_dangerous_command_without_approval_path() -> None:
    decision = classify_exec_command(
        "rm -rf build",
        approval_policy="never",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "forbidden"
    assert decision.reason_code == "exec.dangerous.forbidden.no_approval"
    assert decision.proposed_rule == {
        "source": "heuristic",
        "match_kind": "prefix",
        "pattern": ["rm"],
        "decision": "forbidden",
    }
    assert decision.normalized_segments == ("rm -rf build",)
    assert decision.matched_rules[0]["evidence"]["classification"] == "dangerous"
    assert decision.matched_rules[-1]["source"] == "policy_conflict"


def test_classify_exec_command_prompts_network_command_when_approval_is_available() -> None:
    decision = classify_exec_command(
        "curl -I https://example.com",
        approval_policy="on-request",
        sandbox_mode="workspace-write",
        network_access_enabled=True,
    )

    assert decision.decision == "prompt"
    assert decision.reason_code == "exec.network.requires_approval"
    assert decision.normalized_segments == ("curl -I https://example.com",)
    assert decision.matched_rules[0]["evidence"]["classification"] == "network"
    assert decision.matched_rules[0]["evidence"]["uses_network"] is True
    assert decision.matched_rules[-1]["rule_id"] == "network_requires_approval"
    assert decision.proposed_rule == {
        "source": "heuristic",
        "match_kind": "prefix",
        "pattern": ["curl"],
        "decision": "prompt",
    }


def test_classify_exec_command_allows_network_command_when_network_is_enabled_without_approval_path() -> (
    None
):
    decision = classify_exec_command(
        "curl -I https://example.com",
        approval_policy="never",
        sandbox_mode="workspace-write",
        network_access_enabled=True,
    )

    assert decision.decision == "allow"
    assert decision.reason_code == "exec.network.allow"
    assert decision.matched_rules[0]["evidence"]["classification"] == "network"
    assert decision.matched_rules[-1]["rule_id"] == "network_allowed_by_runtime_policy"


def test_classify_exec_command_forbids_network_command_when_network_is_disabled_without_approval_path() -> (
    None
):
    decision = classify_exec_command(
        "curl -I https://example.com",
        approval_policy="never",
        sandbox_mode="workspace-write",
        network_access_enabled=False,
    )

    assert decision.decision == "forbidden"
    assert decision.reason_code == "exec.network.forbidden.no_approval"
    assert decision.matched_rules[0]["evidence"]["classification"] == "network"
    assert decision.matched_rules[-1]["source"] == "policy_conflict"
    assert decision.matched_rules[-1]["rule_id"] == "network_without_approval_path"


def test_classify_exec_command_allows_non_safe_write_in_workspace_sandbox() -> None:
    decision = classify_exec_command(
        "touch build.log",
        approval_policy="never",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "allow"
    assert decision.reason_code == "exec.sandbox.allow"
    assert decision.normalized_segments == ("touch build.log",)
    assert decision.matched_rules[0]["evidence"]["classification"] == "write"
    assert decision.proposed_rule == {
        "source": "heuristic",
        "match_kind": "prefix",
        "pattern": ["touch"],
        "decision": "allow",
    }


def test_classify_exec_command_prompts_write_in_workspace_sandbox_when_approval_is_available() -> (
    None
):
    decision = classify_exec_command(
        "touch build.log",
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "prompt"
    assert decision.reason_code == "exec.write.requires_approval"
    assert decision.normalized_segments == ("touch build.log",)
    assert decision.matched_rules[0]["evidence"]["classification"] == "write"
    assert decision.matched_rules[-1]["source"] == "policy_axis"
    assert decision.matched_rules[-1]["rule_id"] == "write_requires_approval"
    assert decision.proposed_rule == {
        "source": "heuristic",
        "match_kind": "prefix",
        "pattern": ["touch"],
        "decision": "prompt",
    }


def test_classify_exec_command_prompts_output_redirection_write_when_approval_is_available() -> (
    None
):
    decision = classify_exec_command(
        "echo hello > build.log",
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "prompt"
    assert decision.reason_code == "exec.write.requires_approval"
    assert decision.normalized_segments == ("echo hello > build.log",)
    assert decision.matched_rules[0]["evidence"]["has_output_redirection"] is True
    assert decision.matched_rules[-1]["rule_id"] == "write_requires_approval"


def test_classify_exec_command_allows_safe_read_command_substitution_with_dev_null_stderr() -> None:
    decision = classify_exec_command(
        (
            "wc -l $(find /home/lyc/project/AgentHub/cli/agent_cli "
            '-name "*.py" -not -path "*__pycache__*") 2>/dev/null | tail -1'
        ),
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "allow"
    assert decision.reason_code == "exec.safe_read.allow"
    assert decision.normalized_segments == (
        (
            "wc -l $(find /home/lyc/project/AgentHub/cli/agent_cli "
            '-name "*.py" -not -path "*__pycache__*") 2>/dev/null'
        ),
        "tail -1",
    )
    assert decision.matched_rules[0]["evidence"]["classification"] == "safe_read"
    assert decision.matched_rules[0]["evidence"]["has_command_substitution"] is True
    assert decision.matched_rules[0]["evidence"]["has_output_redirection"] is True
    assert decision.matched_rules[0]["evidence"]["has_unsafe_output_redirection"] is False


def test_classify_exec_command_allows_safe_read_command_substitution_with_inner_dev_null_stderr() -> (
    None
):
    decision = classify_exec_command(
        (
            "wc -l $(find /home/lyc/project/AgentHub/cli/agent_cli "
            '-name "*.py" 2>/dev/null) 2>/dev/null | tail -1'
        ),
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "allow"
    assert decision.reason_code == "exec.safe_read.allow"
    assert decision.matched_rules[0]["evidence"]["classification"] == "safe_read"
    assert decision.matched_rules[0]["evidence"]["has_command_substitution"] is True
    assert decision.matched_rules[0]["evidence"]["has_output_redirection"] is True
    assert decision.matched_rules[0]["evidence"]["has_unsafe_output_redirection"] is False


def test_classify_exec_command_prompts_unsafe_command_substitution() -> None:
    decision = classify_exec_command(
        "wc -l $(rm -rf build)",
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "prompt"
    assert decision.reason_code == "exec.dangerous.requires_approval"
    assert decision.matched_rules[0]["evidence"]["classification"] == "dangerous"
    assert decision.matched_rules[0]["rule_id"] == "dangerous_shell_construct"


def test_classify_exec_command_prompts_unsafe_file_redirection() -> None:
    decision = classify_exec_command(
        "wc -l README.md > out.txt",
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "prompt"
    assert decision.reason_code == "exec.write.requires_approval"
    assert decision.matched_rules[0]["evidence"]["has_output_redirection"] is True
    assert decision.matched_rules[0]["evidence"]["has_unsafe_output_redirection"] is True


def test_classify_exec_command_allows_safe_read_with_dev_null_stderr() -> None:
    decision = classify_exec_command(
        "find . -name README.md 2>/dev/null",
        approval_policy="on-request",
        sandbox_mode="workspace-write",
    )

    assert decision.decision == "allow"
    assert decision.reason_code == "exec.safe_read.allow"
    assert decision.matched_rules[0]["evidence"]["classification"] == "safe_read"
    assert decision.matched_rules[0]["evidence"]["has_output_redirection"] is True
    assert decision.matched_rules[0]["evidence"]["has_unsafe_output_redirection"] is False


def test_classify_exec_command_forbids_write_in_read_only_without_approval_path() -> None:
    decision = classify_exec_command(
        "touch build.log",
        approval_policy="never",
        sandbox_mode="read-only",
    )

    assert decision.decision == "forbidden"
    assert decision.reason_code == "exec.read_only.forbidden.no_approval"
    assert decision.normalized_segments == ("touch build.log",)
    assert decision.matched_rules[0]["evidence"]["classification"] == "write"
    assert decision.matched_rules[-1]["source"] == "policy_conflict"
    assert decision.matched_rules[-1]["rule_id"] == "read_only_write_without_approval_path"


def test_classify_exec_command_applies_persisted_rule_before_heuristics() -> None:
    decision = classify_exec_command(
        "echo hello",
        approval_policy="unless-trusted",
        rules=[
            normalize_exec_policy_rule(
                {
                    "decision": "allow",
                    "match_kind": "exact",
                    "command": "echo hello",
                    "source": "project",
                }
            )
        ],
    )

    assert decision.decision == "allow"
    assert decision.reason_code == "exec.rule.exact.allow"
    assert decision.matched_rules[0]["source"] == "persisted_rule"
    assert decision.proposed_rule is None
