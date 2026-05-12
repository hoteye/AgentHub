from __future__ import annotations

import tempfile
from pathlib import Path

from cli.agent_cli.init_scan_runtime import build_init_scan_summary


def test_init_scan_runtime_detects_python_repo_legacy_instruction_source_and_rules() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").write_text("", encoding="utf-8")
        (root / "README.md").write_text("# Demo\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("Legacy guidance", encoding="utf-8")
        (root / "pyproject.toml").write_text(
            "\n".join(
                [
                    "[project]",
                    'name = "demo-repo"',
                    'dependencies = ["fastapi>=0.100", "pytest>=8", "ruff>=0.5"]',
                    "",
                    "[build-system]",
                    'requires = ["setuptools>=68"]',
                    'build-backend = "setuptools.build_meta"',
                ]
            ),
            encoding="utf-8",
        )
        (root / "tests").mkdir()
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "ci.yml").write_text("name: ci\n", encoding="utf-8")
        (root / ".github" / "copilot-instructions.md").write_text("copilot", encoding="utf-8")
        rules_dir = root / ".agenthub" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "python.md").write_text("# Python Rule\n", encoding="utf-8")

        summary = build_init_scan_summary(root)

    assert summary["project_root"] == str(root.resolve())
    assert summary["legacy_project_doc_path"].endswith("AGENTS.md")
    assert summary["languages"][:1] == ["python"]
    assert "fastapi" in summary["frameworks"]
    assert "pytest" in summary["frameworks"]
    assert "ruff" in summary["frameworks"]
    assert "pip" in summary["package_managers"]
    assert any("pytest" in command for command in summary["command_groups"]["test"])
    assert any("ruff check ." in command for command in summary["command_groups"]["lint"])
    assert summary["readme_paths"] == ["README.md"]
    assert summary["ci_paths"] == [".github/workflows/ci.yml"]
    assert ".agenthub/rules/python.md" in summary["rule_paths"]
    assert ".github/copilot-instructions.md" in summary["ai_instruction_sources"]
    assert ".agenthub/rules/python.md" in summary["ai_instruction_sources"]
    assert "AGENTS.md" in summary["ai_instruction_sources"]
