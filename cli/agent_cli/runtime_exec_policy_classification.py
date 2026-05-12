from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli import (
    runtime_policy_normalization_helpers_runtime as policy_normalization_service,
)
from cli.agent_cli.runtime_exec_policy_classification_segment_helpers_runtime import (
    APPROVAL_POLICY_PROMPT_ALLOWED as _APPROVAL_POLICY_PROMPT_ALLOWED,
)
from cli.agent_cli.runtime_exec_policy_classification_segment_helpers_runtime import (
    normalize_command_segments,
)
from cli.agent_cli.runtime_exec_policy_classification_segment_helpers_runtime import (
    policy_rule_entry as _policy_rule_entry,
)
from cli.agent_cli.runtime_exec_policy_classification_segment_helpers_runtime import (
    proposed_rule_for_segments as _proposed_rule_for_segments,
)
from cli.agent_cli.runtime_exec_policy_rules import match_runtime_exec_policy_rule

try:
    from cli.agent_cli.runtime_exec_policy_models import CommandApprovalDecision
except ImportError:

    @dataclass(frozen=True, slots=True)
    class CommandApprovalDecision:
        decision: str
        reason_code: str
        reason_text: str
        matched_rules: list[dict[str, Any]]
        proposed_rule: dict[str, Any] | None
        normalized_segments: tuple[str, ...]


COMMAND_APPROVAL_DECISIONS = ("allow", "prompt", "forbidden")


def classify_exec_command(
    command: str,
    *,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
    network_access_enabled: str | bool | None = None,
    network_access_requested: bool = False,
    rules: list[object] | None = None,
) -> CommandApprovalDecision:
    normalized_policy = _normalized_approval_policy(approval_policy)
    normalized_sandbox = policy_normalization_service.normalize_sandbox_mode(sandbox_mode)
    normalized_network_access = policy_normalization_service.normalize_network_access(
        network_access_enabled,
        default=True,
    )
    segment_details = normalize_command_segments(command)

    if not segment_details:
        return CommandApprovalDecision(
            decision="forbidden",
            reason_code="exec.empty.forbidden",
            reason_text="Empty commands cannot be classified for execution.",
            matched_rules=[],
            proposed_rule=None,
            normalized_segments=(),
        )

    matched_rules = [
        dict(segment["matched_rule"])
        for segment in segment_details
        if isinstance(segment.get("matched_rule"), dict)
    ]
    dangerous_segments = [
        segment
        for segment in segment_details
        if str(segment.get("classification") or "") == "dangerous"
    ]
    non_safe_segments = [
        segment
        for segment in segment_details
        if str(segment.get("classification") or "") != "safe_read"
    ]
    write_segments = [
        segment
        for segment in segment_details
        if bool(segment.get("writes_to_filesystem"))
        or bool(segment.get("has_unsafe_output_redirection"))
    ]
    network_segments = [segment for segment in segment_details if bool(segment.get("uses_network"))]
    can_prompt = normalized_policy in _APPROVAL_POLICY_PROMPT_ALLOWED
    normalized_segment_text = tuple(str(segment.get("text") or "") for segment in segment_details)
    persisted_rule = match_runtime_exec_policy_rule(command, rules=rules)

    if persisted_rule is not None:
        return CommandApprovalDecision(
            decision=str(persisted_rule.decision or "").strip().lower() or "prompt",
            reason_code=f"exec.rule.{persisted_rule.match_kind}.{persisted_rule.decision}",
            reason_text=(
                "A persisted exec policy rule matched this command and overrode heuristic classification."
            ),
            matched_rules=(
                {
                    "source": "persisted_rule",
                    "rule_id": persisted_rule.rule_id,
                    "decision": persisted_rule.decision,
                    "evidence": {
                        "match_kind": persisted_rule.match_kind,
                        "normalized_command": persisted_rule.normalized_command,
                        "command_tokens": list(persisted_rule.command_tokens),
                        "scope": persisted_rule.scope,
                        "source": persisted_rule.source,
                        "source_metadata": dict(persisted_rule.source_metadata),
                    },
                },
            ),
            proposed_rule=None,
            normalized_segments=normalized_segment_text,
        )

    if dangerous_segments:
        focal_segment = dangerous_segments[0]
        if can_prompt:
            reason_code = "exec.dangerous.requires_approval"
            reason_text = (
                "Command includes dangerous constructs and should be approved before execution."
            )
            decision = "prompt"
            matched_rules.append(
                _policy_rule_entry(
                    rule_id="dangerous_requires_approval",
                    decision=decision,
                    source="heuristic",
                    evidence={
                        "approval_policy": normalized_policy,
                        "focal_program": focal_segment.get("program"),
                    },
                )
            )
        else:
            reason_code = "exec.dangerous.forbidden.no_approval"
            reason_text = (
                "Command includes dangerous constructs, and the current approval policy cannot "
                "request approval before execution."
            )
            decision = "forbidden"
            matched_rules.append(
                _policy_rule_entry(
                    rule_id="dangerous_without_approval_path",
                    decision=decision,
                    source="policy_conflict",
                    evidence={
                        "approval_policy": normalized_policy,
                        "focal_program": focal_segment.get("program"),
                    },
                )
            )
        return CommandApprovalDecision(
            decision=decision,
            reason_code=reason_code,
            reason_text=reason_text,
            matched_rules=matched_rules,
            proposed_rule=_proposed_rule_for_segments(
                segment_details,
                decision=decision,
            ),
            normalized_segments=normalized_segment_text,
        )

    if normalized_policy == "unless-trusted" and non_safe_segments:
        focal_segment = non_safe_segments[0]
        matched_rules.append(
            _policy_rule_entry(
                rule_id="unless_trusted_safe_read_only",
                decision="prompt",
                source="heuristic",
                evidence={
                    "approval_policy": normalized_policy,
                    "focal_program": focal_segment.get("program"),
                },
            )
        )
        return CommandApprovalDecision(
            decision="prompt",
            reason_code="exec.untrusted.requires_approval",
            reason_text=(
                "Approval policy unless-trusted only auto-allows known safe read commands."
            ),
            matched_rules=matched_rules,
            proposed_rule=_proposed_rule_for_segments(
                segment_details,
                decision="prompt",
            ),
            normalized_segments=normalized_segment_text,
        )

    if network_segments or network_access_requested:
        focal_segment = network_segments[0] if network_segments else segment_details[0]
        if can_prompt:
            decision = "prompt"
            reason_code = "exec.network.requires_approval"
            reason_text = "Command uses or explicitly requests network access and should be approved before execution."
            source = "policy_axis"
            rule_id = "network_requires_approval"
        elif not normalized_network_access:
            decision = "forbidden"
            reason_code = "exec.network.forbidden.no_approval"
            reason_text = "Command uses or requests network access, but the current policy cannot approve network execution."
            source = "policy_conflict"
            rule_id = "network_without_approval_path"
        else:
            decision = "allow"
            reason_code = "exec.network.allow"
            reason_text = "Command uses network access, and the current runtime policy allows it without extra approval."
            source = "policy_axis"
            rule_id = "network_allowed_by_runtime_policy"
        matched_rules.append(
            _policy_rule_entry(
                rule_id=rule_id,
                decision=decision,
                source=source,
                evidence={
                    "approval_policy": normalized_policy,
                    "sandbox_mode": normalized_sandbox,
                    "network_access_enabled": normalized_network_access,
                    "requested_network_access": bool(network_access_requested),
                    "focal_program": focal_segment.get("program"),
                },
            )
        )
        return CommandApprovalDecision(
            decision=decision,
            reason_code=reason_code,
            reason_text=reason_text,
            matched_rules=matched_rules,
            proposed_rule=_proposed_rule_for_segments(
                segment_details,
                decision=decision,
            ),
            normalized_segments=normalized_segment_text,
        )

    if normalized_sandbox == "read-only" and write_segments:
        focal_segment = write_segments[0]
        if can_prompt:
            decision = "prompt"
            reason_code = "exec.read_only.requires_approval"
            reason_text = "Command writes to the filesystem and needs approval to leave the read-only sandbox."
            source = "sandbox_requirement"
            rule_id = "read_only_write_requires_approval"
        else:
            decision = "forbidden"
            reason_code = "exec.read_only.forbidden.no_approval"
            reason_text = "Command writes to the filesystem, but the current policy cannot leave the read-only sandbox."
            source = "policy_conflict"
            rule_id = "read_only_write_without_approval_path"
        matched_rules.append(
            _policy_rule_entry(
                rule_id=rule_id,
                decision=decision,
                source=source,
                evidence={
                    "approval_policy": normalized_policy,
                    "sandbox_mode": normalized_sandbox,
                    "focal_program": focal_segment.get("program"),
                },
            )
        )
        return CommandApprovalDecision(
            decision=decision,
            reason_code=reason_code,
            reason_text=reason_text,
            matched_rules=matched_rules,
            proposed_rule=_proposed_rule_for_segments(
                segment_details,
                decision=decision,
            ),
            normalized_segments=normalized_segment_text,
        )

    if write_segments and can_prompt:
        focal_segment = write_segments[0]
        matched_rules.append(
            _policy_rule_entry(
                rule_id="write_requires_approval",
                decision="prompt",
                source="policy_axis",
                evidence={
                    "approval_policy": normalized_policy,
                    "sandbox_mode": normalized_sandbox,
                    "focal_program": focal_segment.get("program"),
                },
            )
        )
        return CommandApprovalDecision(
            decision="prompt",
            reason_code="exec.write.requires_approval",
            reason_text=(
                "Command writes to the filesystem and should be approved before execution."
            ),
            matched_rules=matched_rules,
            proposed_rule=_proposed_rule_for_segments(
                segment_details,
                decision="prompt",
            ),
            normalized_segments=normalized_segment_text,
        )

    if non_safe_segments:
        return CommandApprovalDecision(
            decision="allow",
            reason_code="exec.sandbox.allow",
            reason_text=(
                "Command is not on the safe-read allowlist, but it can run inside the current sandbox "
                "without approval."
            ),
            matched_rules=matched_rules,
            proposed_rule=_proposed_rule_for_segments(
                segment_details,
                decision="allow",
            ),
            normalized_segments=normalized_segment_text,
        )

    return CommandApprovalDecision(
        decision="allow",
        reason_code="exec.safe_read.allow",
        reason_text="All command segments matched the safe read allowlist.",
        matched_rules=matched_rules,
        proposed_rule=_proposed_rule_for_segments(
            segment_details,
            decision="allow",
        ),
        normalized_segments=normalized_segment_text,
    )


def _normalized_approval_policy(value: str | None) -> str:
    normalized = policy_normalization_service.normalize_approval_policy(
        value,
        default="unless-trusted",
    )
    return "unless-trusted" if normalized == "untrusted" else normalized


__all__ = [
    "COMMAND_APPROVAL_DECISIONS",
    "CommandApprovalDecision",
    "classify_exec_command",
    "normalize_command_segments",
]
