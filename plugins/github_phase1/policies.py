from __future__ import annotations


def build_policies(plugin_name: str = "github_phase1") -> list[dict[str, object]]:
    return [
        {
            "policy_key": "github_mutation_approval",
            "plugin_name": plugin_name,
            "display_name": "GitHub Mutation Approval",
            "version": "1",
            "policy_kind": "approval",
            "description": "All mutating GitHub Phase 1 actions should pass approval before real writeback.",
            "applies_to": ["action.request"],
            "metadata": {"provider": "github", "phase": "phase1"},
        }
    ]
