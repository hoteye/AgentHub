from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_exec_policy_classification_parsing_helpers_runtime import (
    _split_command_segments,
)
from cli.agent_cli.runtime_exec_policy_classification_predicates_helpers_runtime import (
    _classify_segment,
    _program_name,
    _segment_security_flags,
    _suggest_rule_prefix,
)
from cli.agent_cli.runtime_services import (
    command_policy_pure_helpers_runtime as command_policy_helpers,
)

APPROVAL_POLICY_PROMPT_ALLOWED = {"on-request", "unless-trusted"}


def normalize_command_segments(command: str) -> list[dict[str, Any]]:
    segments = _split_command_segments(command)
    normalized_segments: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        text = str(segment.get("text") or "").strip()
        argv = command_policy_helpers.safe_split_command(text)
        program = _program_name(argv)
        flags = _segment_security_flags(text)
        classification = _classify_segment(
            text,
            argv=argv,
            program=program,
            flags=flags,
        )
        normalized_segments.append(
            {
                "segment_index": index,
                "text": text,
                "operator": str(segment.get("operator") or ""),
                "argv": argv,
                "program": program,
                "classification": classification["classification"],
                "reason_code": classification["reason_code"],
                "reason_text": classification["reason_text"],
                "writes_to_filesystem": classification["writes_to_filesystem"],
                "uses_network": classification["uses_network"],
                "has_output_redirection": flags["has_output_redirection"],
                "has_unsafe_output_redirection": flags["has_unsafe_output_redirection"],
                "has_command_substitution": flags["has_command_substitution"],
                "has_backticks": flags["has_backticks"],
                "has_subshell": flags["has_subshell"],
                "has_heredoc": flags["has_heredoc"],
                "matched_rule": {
                    "source": "heuristic",
                    "rule_id": classification["rule_id"],
                    "decision": classification["base_decision"],
                    "segment_index": index,
                    "command_prefix": _suggest_rule_prefix(
                        argv,
                        classification=classification["classification"],
                    ),
                    "evidence": {
                        "program": program,
                        "argv": argv,
                        "operator": str(segment.get("operator") or ""),
                        "classification": classification["classification"],
                        "writes_to_filesystem": classification["writes_to_filesystem"],
                        "uses_network": classification["uses_network"],
                        "has_output_redirection": flags["has_output_redirection"],
                        "has_unsafe_output_redirection": flags["has_unsafe_output_redirection"],
                        "has_command_substitution": flags["has_command_substitution"],
                        "has_backticks": flags["has_backticks"],
                        "has_subshell": flags["has_subshell"],
                        "has_heredoc": flags["has_heredoc"],
                    },
                },
            }
        )
    return normalized_segments


def proposed_rule_for_segments(
    segments: list[dict[str, Any]],
    *,
    decision: str,
) -> dict[str, Any] | None:
    if len(segments) != 1:
        return None
    segment = segments[0]
    prefix = list(segment.get("matched_rule", {}).get("command_prefix") or [])
    if not prefix:
        return None
    return {
        "source": "heuristic",
        "match_kind": "prefix",
        "pattern": prefix,
        "decision": decision,
    }


def policy_rule_entry(
    *,
    rule_id: str,
    decision: str,
    source: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": source,
        "rule_id": rule_id,
        "decision": decision,
        "evidence": dict(evidence),
    }


__all__ = [
    "APPROVAL_POLICY_PROMPT_ALLOWED",
    "normalize_command_segments",
    "policy_rule_entry",
    "proposed_rule_for_segments",
]
