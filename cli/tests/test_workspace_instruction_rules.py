from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cli.agent_cli.workspace_context import build_workspace_prompt_context, discover_project_doc_paths


class WorkspaceInstructionRulesTest(unittest.TestCase):
    def test_discovers_agenthub_aengthub_doc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            (root / ".agenthub").mkdir(parents=True, exist_ok=True)
            (root / ".agenthub" / "AENGTHUB.md").write_text("agenthub doc", encoding="utf-8")

            paths = discover_project_doc_paths(root)
            context = build_workspace_prompt_context(root)

        self.assertEqual(paths, [(root / ".agenthub" / "AENGTHUB.md").resolve()])
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("agenthub doc"))

    def test_rule_docs_are_loaded_when_path_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "mobile" / "app"
            nested.mkdir(parents=True)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AENGTHUB.md").write_text("root doc", encoding="utf-8")
            rules = root / ".agenthub" / "rules"
            rules.mkdir(parents=True)
            (rules / "mobile.md").write_text(
                "---\npaths:\n  - mobile/**\nenabled: true\npriority: 50\n---\nmobile rule",
                encoding="utf-8",
            )

            paths = discover_project_doc_paths(nested)
            context = build_workspace_prompt_context(nested)

        self.assertEqual(
            paths,
            [
                (root / "AENGTHUB.md").resolve(),
                (rules / "mobile.md").resolve(),
            ],
        )
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("root doc\n\nmobile rule"))

    def test_rule_docs_respect_enabled_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "mobile" / "app"
            nested.mkdir(parents=True)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AENGTHUB.md").write_text("root doc", encoding="utf-8")
            rules = root / ".agenthub" / "rules"
            rules.mkdir(parents=True)
            (rules / "disabled.md").write_text(
                "---\npaths: [mobile/**]\nenabled: false\npriority: 50\n---\ndisabled rule",
                encoding="utf-8",
            )

            paths = discover_project_doc_paths(nested)
            context = build_workspace_prompt_context(nested)

        self.assertEqual(paths, [(root / "AENGTHUB.md").resolve()])
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("root doc"))

    def test_rule_docs_respect_priority_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "mobile" / "app"
            nested.mkdir(parents=True)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AENGTHUB.md").write_text("root doc", encoding="utf-8")
            rules = root / ".agenthub" / "rules"
            rules.mkdir(parents=True)
            (rules / "high.md").write_text(
                "---\npaths: [mobile/**]\npriority: 200\n---\nhigh rule",
                encoding="utf-8",
            )
            (rules / "low.md").write_text(
                "---\npaths: [mobile/**]\npriority: 10\n---\nlow rule",
                encoding="utf-8",
            )

            paths = discover_project_doc_paths(nested)
            context = build_workspace_prompt_context(nested)

        self.assertEqual(
            paths,
            [
                (root / "AENGTHUB.md").resolve(),
                (rules / "low.md").resolve(),
                (rules / "high.md").resolve(),
            ],
        )
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("root doc\n\nlow rule\n\nhigh rule"))

    def test_legacy_agents_fallback_remains_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AGENTS.md").write_text("legacy", encoding="utf-8")

            paths = discover_project_doc_paths(root)
            context = build_workspace_prompt_context(root)

        self.assertEqual(paths, [(root / "AGENTS.md").resolve()])
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("legacy"))
