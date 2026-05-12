from __future__ import annotations

from pathlib import Path

from cli.scripts import provider_config_boundary_guard as guard


def test_scan_file_reports_direct_provider_config_access(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("cli/scripts/business_probe.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from cli.agent_cli.provider import load_provider_management_snapshot\n"
        "CONFIG = 'cli/.config/config.toml'\n"
        "AUTH = '.agent_cli/auth.json'\n"
        "ENV = 'AGENTHUB_PROVIDER_HOME'\n",
        encoding="utf-8",
    )

    violations = guard.scan_file(target)

    assert [item.lineno for item in violations] == [1, 2, 3, 4]
    assert "load_provider_management_snapshot" in violations[0].message
    assert "cli/.config/config.toml" in violations[1].message
    assert ".agent_cli/auth.json" in violations[2].message
    assert "AGENTHUB_PROVIDER_HOME" in violations[3].message


def test_scan_file_allows_unified_provider_facade_usage(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("cli/scripts/business_probe.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from cli.scripts.script_runtime_helpers import resolve_script_provider_run_settings\n"
        "settings = resolve_script_provider_run_settings(cwd='.')\n",
        encoding="utf-8",
    )

    assert guard.scan_file(target) == []


def test_scan_file_allows_provider_boundary_owners(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    provider_target = Path("cli/agent_cli/provider.py")
    provider_target.parent.mkdir(parents=True, exist_ok=True)
    provider_target.write_text("CONFIG = 'cli/.config/config.toml'\n", encoding="utf-8")
    provider_test = Path("cli/tests/test_provider_paths.py")
    provider_test.parent.mkdir(parents=True, exist_ok=True)
    provider_test.write_text("AUTH = '.agent_cli/auth.json'\n", encoding="utf-8")

    assert guard.scan_file(provider_target) == []
    assert guard.scan_file(provider_test) == []


def test_scan_file_flags_low_level_script_helper_import(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("cli/scripts/business_probe.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from cli.scripts.script_runtime_helpers import load_script_provider_management_snapshot\n",
        encoding="utf-8",
    )

    violations = guard.scan_file(target)

    assert len(violations) == 1
    assert "load_script_provider_management_snapshot" in violations[0].message


def test_scan_markdown_reports_provider_config_locations(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("docs/RUNBOOK.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "Edit cli/.config/config.toml for the provider.\n"
        "Set AGENTHUB_PROVIDER_HOME before launching the probe.\n"
        "Compare ~/.codex/auth.json when debugging auth.\n",
        encoding="utf-8",
    )

    violations = guard.scan_file(target)

    assert [item.lineno for item in violations] == [1, 2, 3]
    assert "cli/.config/config.toml" in violations[0].message
    assert "AGENTHUB_PROVIDER_HOME" in violations[1].message
    assert "~/.codex/auth.json" in violations[2].message


def test_scan_markdown_allows_unified_provider_design_doc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("docs/AGENTHUB_UNIFIED_PROVIDER_MANAGEMENT.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "The design doc may record cli/.config/config.toml and AGENTHUB_PROVIDER_HOME.\n",
        encoding="utf-8",
    )

    assert guard.scan_file(target) == []


def test_scan_markdown_allows_reader_facing_unified_provider_usage(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = Path("docs/AGENTHUB_PROVIDER_USAGE.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "Scripts call resolve_script_provider_run_settings() and consume provider/model/base_url.\n",
        encoding="utf-8",
    )

    assert guard.scan_file(target) == []


def test_repository_test_files_respect_provider_config_boundary(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo_root)

    failures = []
    for path in sorted([*Path("cli/tests").rglob("*.py"), *Path("tests").rglob("*.py")]):
        for violation in guard.scan_file(path):
            failures.append(f"{path.as_posix()}:{violation.lineno} {violation.message}")

    assert failures == []
