from __future__ import annotations

import unittest

from cli.agent_cli.runtime_exec_policy_bridge import (
    exec_approval_requirement_allows_execution,
    exec_approval_requirement_for_decision,
    exec_approval_requirement_from_dict,
    exec_approval_requirement_is_forbidden,
    exec_approval_requirement_requires_approval,
    exec_approval_requirement_to_dict,
)
from cli.agent_cli.runtime_exec_policy_models import (
    CommandApprovalDecision,
    CommandApprovalDecisionValue,
    Forbidden,
    NeedsApproval,
    Skip,
)


class RuntimeExecPolicyModelsTest(unittest.TestCase):
    def test_command_approval_decision_round_trips_with_serialization_safe_copies(self) -> None:
        matched_rules = [
            {
                "pattern": "rg --files",
                "decision": "allow",
                "source": "rule",
            }
        ]
        proposed_rule = {
            "pattern": "pytest cli/tests/test_runtime_exec_policy_models.py",
            "decision": "prompt",
        }
        normalized_segments = ["python -m pytest", "cli/tests/test_runtime_exec_policy_models.py"]

        decision = CommandApprovalDecision(
            decision=CommandApprovalDecisionValue.PROMPT,
            reason_code="command.unknown",
            reason_text="Unknown command requires approval.",
            matched_rules=matched_rules,
            proposed_rule=proposed_rule,
            normalized_segments=normalized_segments,
        )

        matched_rules[0]["pattern"] = "mutated"
        proposed_rule["pattern"] = "mutated"
        normalized_segments.append("mutated")

        self.assertEqual(
            decision.to_dict(),
            {
                "decision": "prompt",
                "reason_code": "command.unknown",
                "reason_text": "Unknown command requires approval.",
                "matched_rules": [
                    {
                        "pattern": "rg --files",
                        "decision": "allow",
                        "source": "rule",
                    }
                ],
                "proposed_rule": {
                    "pattern": "pytest cli/tests/test_runtime_exec_policy_models.py",
                    "decision": "prompt",
                },
                "normalized_segments": [
                    "python -m pytest",
                    "cli/tests/test_runtime_exec_policy_models.py",
                ],
            },
        )

        restored = CommandApprovalDecision.from_dict(decision.to_dict())

        self.assertEqual(restored, decision)
        self.assertEqual(restored.decision, CommandApprovalDecisionValue.PROMPT)
        self.assertIsNot(restored.proposed_rule, decision.proposed_rule)

    def test_command_approval_decision_from_dict_filters_non_contract_entries(self) -> None:
        decision = CommandApprovalDecision.from_dict(
            {
                "decision": "allow",
                "reason_code": "safe.read",
                "reason_text": "Known safe read command.",
                "matched_rules": [
                    {"pattern": "cat", "decision": "allow"},
                    "not-a-rule",
                    7,
                ],
                "proposed_rule": "not-a-rule",
                "normalized_segments": ["cat README.md", "", None, "sed -n '1,10p' README.md"],
            }
        )

        self.assertEqual(decision.decision, CommandApprovalDecisionValue.ALLOW)
        self.assertEqual(decision.matched_rules, ({"pattern": "cat", "decision": "allow"},))
        self.assertIsNone(decision.proposed_rule)
        self.assertEqual(
            decision.normalized_segments,
            ("cat README.md", "sed -n '1,10p' README.md"),
        )

    def test_command_approval_decision_rejects_unknown_decision_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected one of: allow, prompt, forbidden"):
            CommandApprovalDecision.from_dict({"decision": "ask"})

    def test_exec_approval_requirement_bridge_maps_each_decision_variant(self) -> None:
        allow_decision = CommandApprovalDecision(
            decision=CommandApprovalDecisionValue.ALLOW,
            reason_code="safe.read",
            reason_text="Safe read command.",
        )
        prompt_decision = CommandApprovalDecision(
            decision=CommandApprovalDecisionValue.PROMPT,
            reason_code="command.unknown",
            reason_text="Approval required.",
        )
        forbidden_decision = CommandApprovalDecision(
            decision=CommandApprovalDecisionValue.FORBIDDEN,
            reason_code="command.dangerous",
            reason_text="Command is forbidden.",
        )

        allow_requirement = exec_approval_requirement_for_decision(allow_decision)
        prompt_requirement = exec_approval_requirement_for_decision(prompt_decision)
        forbidden_requirement = exec_approval_requirement_for_decision(forbidden_decision)

        self.assertIsInstance(allow_requirement, Skip)
        self.assertTrue(exec_approval_requirement_allows_execution(allow_requirement))
        self.assertFalse(exec_approval_requirement_requires_approval(allow_requirement))
        self.assertFalse(exec_approval_requirement_is_forbidden(allow_requirement))

        self.assertIsInstance(prompt_requirement, NeedsApproval)
        self.assertFalse(exec_approval_requirement_allows_execution(prompt_requirement))
        self.assertTrue(exec_approval_requirement_requires_approval(prompt_requirement))
        self.assertFalse(exec_approval_requirement_is_forbidden(prompt_requirement))

        self.assertIsInstance(forbidden_requirement, Forbidden)
        self.assertFalse(exec_approval_requirement_allows_execution(forbidden_requirement))
        self.assertFalse(exec_approval_requirement_requires_approval(forbidden_requirement))
        self.assertTrue(exec_approval_requirement_is_forbidden(forbidden_requirement))

    def test_exec_approval_requirement_round_trips_through_bridge_payloads(self) -> None:
        for requirement in (Skip(), NeedsApproval(), Forbidden()):
            payload = exec_approval_requirement_to_dict(requirement)
            restored = exec_approval_requirement_from_dict(payload)
            self.assertEqual(restored, requirement)

    def test_exec_approval_requirement_from_dict_rejects_unknown_requirement(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected one of: skip, needs_approval, forbidden"):
            exec_approval_requirement_from_dict({"requirement": "allow"})
