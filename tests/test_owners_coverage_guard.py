from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "check_owners_coverage.py"

SPEC = importlib.util.spec_from_file_location("check_owners_coverage", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_repo_files(
    tmp_path: Path,
    *,
    owners_scope_rows: list[str],
    blueprint_scope_rows: list[str],
    codeowners_lines: list[str],
) -> None:
    (tmp_path / ".github").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)

    owners_body = "\n".join(
        [
            "# AgentHub OWNERS",
            "",
            "## Directory Ownership Baseline",
            "",
            "| Scope | Primary | Backup | Notes |",
            "| --- | --- | --- | --- |",
            *owners_scope_rows,
            "",
        ]
    )
    (tmp_path / "OWNERS.md").write_text(owners_body, encoding="utf-8")

    blueprint_body = "\n".join(
        [
            "# AgentHub Directory Blueprint",
            "",
            "## Governance Owner Mapping Baseline",
            "",
            "| Scope | Owner |",
            "| --- | --- |",
            *blueprint_scope_rows,
            "",
        ]
    )
    (tmp_path / "docs" / "DIRECTORY_BLUEPRINT.md").write_text(blueprint_body, encoding="utf-8")

    (tmp_path / ".github" / "CODEOWNERS").write_text("\n".join(codeowners_lines), encoding="utf-8")


def _baseline_owners_rows() -> list[str]:
    return [
        "| /cli/ | @lyc | @lyc | cli |",
        "| /gui/ | @lyc | @lyc | gui |",
        "| /plugins/ | @lyc | @lyc | plugins |",
        "| /shared/ | @lyc | @lyc | shared |",
        "| /workers/ | @lyc | @lyc | workers |",
        "| /docs/ | @lyc | @lyc | docs |",
        "| /taskboard/ | @lyc | @lyc | taskboard |",
        "| /.github/workflows/ | @lyc | @lyc | workflows |",
        "| Repository root configs | @lyc | @lyc | root |",
    ]


def _baseline_blueprint_rows() -> list[str]:
    return [
        "| /cli/ | @lyc |",
        "| /gui/ | @lyc |",
        "| /plugins/ | @lyc |",
        "| /shared/ | @lyc |",
        "| /workers/ | @lyc |",
        "| /docs/ | @lyc |",
        "| /taskboard/ | @lyc |",
        "| /.github/workflows/ | @lyc |",
        "| root governance/config files | @lyc |",
    ]


def _baseline_codeowners_lines() -> list[str]:
    return [
        "* @lyc",
        "/cli/ @lyc",
        "/gui/ @lyc",
        "/plugins/ @lyc",
        "/shared/ @lyc",
        "/workers/ @lyc",
        "/docs/ @lyc",
        "/taskboard/ @lyc",
        "/.github/workflows/ @lyc",
        "/README.md @lyc",
        "/OWNERS.md @lyc",
        "/.github/CODEOWNERS @lyc",
    ]


def test_validate_repo_passes_when_baseline_is_aligned(tmp_path: Path) -> None:
    _write_repo_files(
        tmp_path,
        owners_scope_rows=_baseline_owners_rows(),
        blueprint_scope_rows=_baseline_blueprint_rows(),
        codeowners_lines=_baseline_codeowners_lines(),
    )

    errors = MODULE.validate_repo(tmp_path)

    assert errors == []


def test_validate_repo_fails_on_owner_drift(tmp_path: Path) -> None:
    blueprint_rows = _baseline_blueprint_rows()
    blueprint_rows[0] = "| /cli/ | @other_owner |"
    _write_repo_files(
        tmp_path,
        owners_scope_rows=_baseline_owners_rows(),
        blueprint_scope_rows=blueprint_rows,
        codeowners_lines=_baseline_codeowners_lines(),
    )

    errors = MODULE.validate_repo(tmp_path)

    assert any("owner drift for scope /cli/" in item for item in errors)


def test_validate_repo_fails_when_codeowners_required_path_is_missing(tmp_path: Path) -> None:
    codeowners_lines = [
        line for line in _baseline_codeowners_lines() if not line.startswith("/workers/")
    ]
    _write_repo_files(
        tmp_path,
        owners_scope_rows=_baseline_owners_rows(),
        blueprint_scope_rows=_baseline_blueprint_rows(),
        codeowners_lines=codeowners_lines,
    )

    errors = MODULE.validate_repo(tmp_path)

    assert any("/workers/" in item for item in errors)
