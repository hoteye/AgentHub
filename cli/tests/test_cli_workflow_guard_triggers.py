from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowGuardTriggersTest(unittest.TestCase):
    def test_cli_cross_platform_workflow_keeps_trigger_and_path_filter_contract(self) -> None:
        workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        # PyYAML may parse "on" as boolean True (YAML 1.1 legacy behavior).
        on_section = dict(payload.get("on") or payload.get(True) or {})

        self.assertEqual(set(on_section), {"push", "pull_request", "workflow_dispatch"})

        required_paths = {
            ".github/workflows/cli-cross-platform.yml",
            "cli/scripts/provider_config_boundary_guard.py",
            "cli/**",
            "plugins/**",
            "internal_policy_docs/**",
            "shared/document_tools/**",
        }

        push_paths = set(dict(on_section["push"] or {}).get("paths") or [])
        pr_paths = set(dict(on_section["pull_request"] or {}).get("paths") or [])

        self.assertTrue(required_paths.issubset(push_paths))
        self.assertTrue(required_paths.issubset(pr_paths))
