from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class CliWorkflowTriggerPathAlignmentTest(unittest.TestCase):
    def test_push_and_pull_request_paths_remain_identical(self) -> None:
        workflow_path = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "cli-cross-platform.yml"
        )
        payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

        # PyYAML may parse "on" as boolean True (YAML 1.1 legacy behavior).
        on_section = dict(payload.get("on") or payload.get(True) or {})

        push_paths = list(dict(on_section.get("push") or {}).get("paths") or [])
        pull_request_paths = list(dict(on_section.get("pull_request") or {}).get("paths") or [])
        expected_paths = [
            ".github/workflows/cli-cross-platform.yml",
            ".github/workflows/release-executables.yml",
            "pyproject.toml",
            ".pre-commit-config.yaml",
            ".editorconfig",
            "requirements-dev.txt",
            "docs/DEPENDENCY_MANAGEMENT.md",
            "docs/TESTING_LAYOUT_RULES.md",
            "docs/AGENTHUB_CHANGE_TEST_GATE_POLICY.md",
            "cli/scripts/changed_files_test_gate.py",
            "cli/scripts/provider_config_boundary_guard.py",
            "cli/**",
            "plugins/**",
            "internal_policy_docs/**",
            "shared/document_tools/**",
        ]

        self.assertEqual(push_paths, pull_request_paths)
        self.assertEqual(push_paths, expected_paths)
