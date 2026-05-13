from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.gateway_core import ActionRequest
from cli.agent_cli.runtime_kernels.codex_sidecar.protocol import JsonObject


def approval_response_for_decision(
    decision: Any,
    *,
    action_request: ActionRequest | None = None,
) -> JsonObject:
    normalized = approval_contract_runtime.normalize_approval_decision(decision)
    decision_type = str(normalized.get("type") or "").strip()
    kind = ""
    if action_request is not None:
        kind = str((action_request.metadata or {}).get("approval_kind") or "").strip()
    if kind == "permissions":
        return permission_response_for_decision(normalized, action_request=action_request)
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT:
        return {"decision": "accept"}
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION:
        return {"decision": "acceptForSession"}
    if (
        decision_type
        == approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT
    ):
        proposed_rule = normalized.get("proposed_rule")
        if isinstance(proposed_rule, dict) and proposed_rule:
            amendment = codex_execpolicy_amendment_from_rule(proposed_rule)
            if not amendment:
                return {"decision": "acceptForSession"}
            return {
                "decision": {
                    "acceptWithExecpolicyAmendment": {
                        "execpolicy_amendment": amendment,
                    }
                }
            }
        return {"decision": "acceptForSession"}
    if decision_type == approval_contract_runtime.APPROVAL_DECISION_CANCEL:
        return {"decision": "cancel"}
    return {"decision": "decline"}


def codex_execpolicy_amendment_from_rule(proposed_rule: dict[str, Any]) -> list[str]:
    raw_tokens = proposed_rule.get("command_tokens")
    if isinstance(raw_tokens, list):
        tokens = [str(token or "").strip() for token in raw_tokens if str(token or "").strip()]
        if tokens:
            return tokens
    raw_command = proposed_rule.get("command")
    if isinstance(raw_command, list):
        tokens = [str(token or "").strip() for token in raw_command if str(token or "").strip()]
        if tokens:
            return tokens
    normalized_command = str(
        proposed_rule.get("normalized_command")
        or proposed_rule.get("command")
        or proposed_rule.get("command_pattern")
        or proposed_rule.get("pattern")
        or ""
    ).strip()
    if not normalized_command:
        return []
    try:
        import shlex

        tokens = [
            str(token or "").strip()
            for token in shlex.split(normalized_command, posix=True)
            if str(token or "").strip()
        ]
    except ValueError:
        tokens = []
    return tokens or [normalized_command]


def permission_response_for_decision(
    decision: dict[str, Any],
    *,
    action_request: ActionRequest | None,
) -> JsonObject:
    decision_type = str(decision.get("type") or "").strip()
    accepting = approval_contract_runtime.is_approval_accepting(decision)
    requested: JsonObject = {}
    if action_request is not None:
        payload = dict(action_request.payload or {})
        requested = dict(payload.get("permissions") or {})
    scope = (
        "session"
        if decision_type
        in {
            approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION,
            approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
        }
        else "turn"
    )
    return {
        "permissions": requested if accepting else {},
        "scope": scope,
    }
