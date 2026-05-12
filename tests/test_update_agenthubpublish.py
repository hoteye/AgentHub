from __future__ import annotations

from pathlib import Path

from scripts import update_agenthubpublish


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_export_excludes_commercial_psbc_plugin(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _touch(source / "cli" / "agent_cli" / "__init__.py")
    _touch(source / "plugins" / "psbc_policy" / "manifest.py")
    _touch(source / "plugins" / "psbc_policy" / "README.md")
    _touch(source / "plugins" / "demo_plugin" / "manifest.py")

    copied = {
        relative.as_posix() for _, relative in update_agenthubpublish.iter_candidate_files(source)
    }

    assert "plugins/demo_plugin/manifest.py" in copied
    assert not any(item.startswith("plugins/psbc_policy/") for item in copied)


def test_export_keeps_public_docs_but_excludes_internal_docs(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _touch(source / "cli" / "agent_cli" / "__init__.py")
    _touch(source / "README.md", "# AgentHub\n")
    _touch(source / "CHANGELOG.md", "# Changelog\n")
    _touch(source / "CONTRIBUTING.md", "# Contributing\n")
    _touch(source / "docs" / "AGENTHUB_GO_TO_MARKET_PLAN.md")
    _touch(source / "cli" / "docs" / "CLI_RELEASE_TODO.md")
    _touch(source / "cli" / "agent_cli" / "prompts" / "README.md")

    copied = {
        relative.as_posix() for _, relative in update_agenthubpublish.iter_candidate_files(source)
    }

    assert "README.md" in copied
    assert "CHANGELOG.md" in copied
    assert "CONTRIBUTING.md" in copied
    assert "cli/agent_cli/prompts/README.md" in copied
    assert "docs/AGENTHUB_GO_TO_MARKET_PLAN.md" not in copied
    assert "cli/docs/CLI_RELEASE_TODO.md" not in copied


def test_export_excludes_local_runtime_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _touch(source / "cli" / "agent_cli" / "__init__.py")
    _touch(source / ".web_automation_state" / "profile.json")
    _touch(source / ".agent_cli" / "state.json")
    _touch(source / "logs" / "agenthub.log")
    _touch(source / "runtime" / "codex" / "linux-x86_64" / "current" / "codex-app-server")

    copied = {
        relative.as_posix() for _, relative in update_agenthubpublish.iter_candidate_files(source)
    }

    assert ".web_automation_state/profile.json" not in copied
    assert ".agent_cli/state.json" not in copied
    assert "logs/agenthub.log" not in copied
    assert "runtime/codex/linux-x86_64/current/codex-app-server" not in copied


def test_export_excludes_internal_governance_workflow(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _touch(source / "cli" / "agent_cli" / "__init__.py")
    _touch(source / ".github" / "workflows" / "cli-cross-platform.yml")
    _touch(source / ".github" / "workflows" / "governance-guards.yml")
    _touch(source / ".github" / "workflows" / "release-executables.yml")

    copied = {
        relative.as_posix() for _, relative in update_agenthubpublish.iter_candidate_files(source)
    }

    assert ".github/workflows/release-executables.yml" in copied
    assert ".github/workflows/cli-cross-platform.yml" not in copied
    assert ".github/workflows/governance-guards.yml" not in copied
