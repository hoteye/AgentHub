from __future__ import annotations

import sys
import tempfile
import unittest
import hashlib
from pathlib import Path

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.provider import build_planner
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.workspace_context import (
    build_workspace_reference_context_item,
    build_workspace_reference_snapshot,
    build_workspace_prompt_context,
    discover_project_doc_paths,
    explicitly_mentioned_skills,
    render_explicit_skill_injections,
    render_workspace_context_update_message,
    workspace_contract,
    workspace_reference_diff,
)

class WorkspaceContextTest(unittest.TestCase):
    def test_project_docs_concatenate_from_root_to_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "workspace" / "crate_a"
            nested.mkdir(parents=True)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AENGTHUB.md").write_text("root doc", encoding="utf-8")
            (nested / "AENGTHUB.md").write_text("crate doc", encoding="utf-8")

            context = build_workspace_prompt_context(nested)

        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("root doc\n\ncrate doc"))

    def test_project_root_markers_are_honored_for_agents_and_skill_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "dir1"
            nested.mkdir(parents=True)
            (root / ".agent_cli_legacy-root").write_text("", encoding="utf-8")
            (nested / ".git").mkdir()
            (root / "AENGTHUB.md").write_text("parent doc", encoding="utf-8")
            (nested / "AENGTHUB.md").write_text("child doc", encoding="utf-8")
            config_dir = nested / ".config"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text('project_root_markers = [".agent_cli_legacy-root"]\n', encoding="utf-8")
            skill_dir = root / ".agents" / "skills" / "linting"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: linting\ndescription: run clippy\n---\n# linting\n",
                encoding="utf-8",
            )

            context = build_workspace_prompt_context(nested)
            paths = discover_project_doc_paths(nested)

        self.assertEqual(paths, [(root / "AENGTHUB.md").resolve(), (nested / "AENGTHUB.md").resolve()])
        self.assertIn("parent doc\n\nchild doc", context.instructions_text)
        self.assertIn("- linting: run clippy", context.instructions_text)

    def test_aengthub_override_is_preferred_over_aengthub_md(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AENGTHUB.md").write_text("versioned", encoding="utf-8")
            (root / "AENGTHUB.override.md").write_text("local", encoding="utf-8")

            paths = discover_project_doc_paths(root)
            context = build_workspace_prompt_context(root)

        self.assertEqual(paths, [(root / "AENGTHUB.override.md").resolve()])
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("local"))

    def test_aengthub_is_preferred_over_legacy_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AENGTHUB.md").write_text("primary", encoding="utf-8")
            (root / "AGENTS.md").write_text("legacy", encoding="utf-8")

            paths = discover_project_doc_paths(root)
            context = build_workspace_prompt_context(root)

        self.assertEqual(paths, [(root / "AENGTHUB.md").resolve()])
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("primary"))

    def test_legacy_agents_md_falls_back_when_aengthub_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AGENTS.md").write_text("legacy", encoding="utf-8")

            paths = discover_project_doc_paths(root)
            context = build_workspace_prompt_context(root)

        self.assertEqual(paths, [(root / "AGENTS.md").resolve()])
        self.assertIn("## Active Workspace", context.instructions_text)
        self.assertTrue(context.instructions_text.endswith("legacy"))

    def test_empty_workspace_gets_default_scaffold_root_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            context = build_workspace_prompt_context(root)

        self.assertIn("## Workspace Defaults", context.instructions_text)
        self.assertIn("treat the current directory as the project root", context.instructions_text)
        self.assertIn("Do not create an extra top-level subdirectory", context.instructions_text)

    def test_planner_system_prompt_does_not_inline_workspace_docs_and_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            (root / "AENGTHUB.md").write_text("base doc", encoding="utf-8")
            skill_dir = root / ".agents" / "skills" / "pdf-processing"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: pdf-processing\ndescription: extract from pdfs\n---\n# pdf-processing\n",
                encoding="utf-8",
            )

            planner = build_planner(
                ProviderConfig(
                    model="gpt-5.4",
                    api_key="sk-test",
                    provider_name="openai",
                    planner_kind="openai_responses",
                    base_url="https://api.openai.com/v1",
                ),
                host_platform=detect_host_platform(system_name="Linux", sys_platform="linux"),
                cwd=root,
            )

        self.assertNotIn("base doc", planner.system_prompt)
        self.assertNotIn("## Skills", planner.system_prompt)
        self.assertNotIn("- pdf-processing: extract from pdfs", planner.system_prompt)

    def test_explicit_skill_mentions_inject_skill_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / ".agents" / "skills" / "linting"
            skill_dir.mkdir(parents=True)
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text(
                "---\nname: linting\ndescription: run clippy\n---\n# linting\nUse cargo clippy.\n",
                encoding="utf-8",
            )

            context = build_workspace_prompt_context(root)
            selected = explicitly_mentioned_skills("请使用 $linting 处理这个仓库", context.skills)
            injection = render_explicit_skill_injections("请使用 $linting 处理这个仓库", context.skills)

        self.assertEqual([item.name for item in selected], ["linting"])
        assert injection is not None
        self.assertIn("SKILL_INSTRUCTIONS:", injection)
        self.assertIn("Use cargo clippy.", injection)

    def test_planner_compose_user_text_appends_explicit_skill_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / ".agents" / "skills" / "linting"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: linting\ndescription: run clippy\n---\n# linting\nUse cargo clippy.\n",
                encoding="utf-8",
            )
            planner = build_planner(
                ProviderConfig(
                    model="gpt-5.4",
                    api_key="sk-test",
                    provider_name="openai",
                    planner_kind="openai_responses",
                    base_url="https://api.openai.com/v1",
                ),
                host_platform=detect_host_platform(system_name="Linux", sys_platform="linux"),
                cwd=root,
            )

            composed = planner._compose_user_text("use $linting on this repo", [])

        self.assertIn("SKILL_INSTRUCTIONS:", composed)
        self.assertIn("Use cargo clippy.", composed)

    def test_extra_skill_roots_include_hidden_system_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            home_skills = root / "agent_cli_home" / "skills" / ".system" / "demo"
            home_skills.mkdir(parents=True)
            (home_skills / "SKILL.md").write_text(
                "---\nname: demo\ndescription: hidden system skill\n---\n# demo\n",
                encoding="utf-8",
            )

            context = build_workspace_prompt_context(
                root,
                extra_skill_roots=[root / "agent_cli_home" / "skills"],
            )

        self.assertIn("- demo: hidden system skill", context.instructions_text)
        self.assertEqual([item.name for item in context.skills], ["demo"])

    def test_workspace_reference_snapshot_and_diff_emit_incremental_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            doc_path = root / "AENGTHUB.md"
            doc_path.write_text("v1 instructions", encoding="utf-8")
            skill_dir = root / ".agents" / "skills" / "audit"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: audit\ndescription: run audit checks\n---\n# audit\n",
                encoding="utf-8",
            )

            snapshot1 = build_workspace_reference_snapshot(root)
            diff_initial = workspace_reference_diff(None, snapshot1)
            message_initial = render_workspace_context_update_message(None, snapshot1)
            item_initial = build_workspace_reference_context_item(None, snapshot1)

            self.assertTrue(diff_initial["changed"])
            self.assertTrue(diff_initial["is_initial"])
            assert message_initial is not None
            self.assertIn("REFERENCE_CONTEXT_BASELINE:", message_initial)
            self.assertIn("## Active Workspace", message_initial)
            self.assertIn("v1 instructions", message_initial)
            assert item_initial is not None
            self.assertEqual(item_initial["item_type"], "workspace_context")
            self.assertEqual(item_initial["label"], "workspace_context_baseline")

            snapshot2 = build_workspace_reference_snapshot(root)
            diff_same = workspace_reference_diff(snapshot1, snapshot2)
            self.assertFalse(diff_same["changed"])
            self.assertIsNone(render_workspace_context_update_message(snapshot1, snapshot2))
            self.assertIsNone(build_workspace_reference_context_item(snapshot1, snapshot2))

            doc_path.write_text("v2 instructions", encoding="utf-8")
            snapshot3 = build_workspace_reference_snapshot(root)
            diff_updated = workspace_reference_diff(snapshot2, snapshot3)
            message_updated = render_workspace_context_update_message(snapshot2, snapshot3)
            item_updated = build_workspace_reference_context_item(snapshot2, snapshot3)

            self.assertTrue(diff_updated["changed"])
            self.assertFalse(diff_updated["is_initial"])
            self.assertTrue(diff_updated["docs_updated"])
            assert message_updated is not None
            self.assertIn("REFERENCE_CONTEXT_UPDATE:", message_updated)
            self.assertIn("UPDATED_INSTRUCTIONS_EXCERPT:", message_updated)
            assert item_updated is not None
            self.assertEqual(item_updated["label"], "workspace_context_update")
            self.assertEqual(
                item_updated["metadata"]["instructions_digest"],
                snapshot3["instructions_digest"],
            )

    def test_workspace_reference_snapshot_uses_full_digest_even_when_excerpt_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".git").write_text("", encoding="utf-8")
            full_text = "A" * 128 + "B" * 128
            (root / "AENGTHUB.md").write_text(full_text, encoding="utf-8")

            context = build_workspace_prompt_context(root)
            snapshot = build_workspace_reference_snapshot(root, max_chars=32)
            contract = workspace_contract(snapshot)

        self.assertTrue(snapshot["instructions_truncated"])
        self.assertEqual(snapshot["instructions_text"], context.instructions_text[:32])
        self.assertEqual(
            snapshot["instructions_digest"],
            hashlib.sha1(context.instructions_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(snapshot["workspace_digest"], contract["workspace_digest"])
