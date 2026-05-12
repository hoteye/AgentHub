from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_governance_doc_links.py"
SPEC = importlib.util.spec_from_file_location("check_governance_doc_links", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_required_files(tmp_path: Path) -> None:
    for relpath in MODULE.REQUIRED_FILES:
        _write(tmp_path / relpath, "# stub\n")


def test_check_repository_passes_for_minimal_valid_layout(tmp_path: Path) -> None:
    _seed_required_files(tmp_path)

    _write(
        tmp_path / "docs/README.md",
        "\n".join(
            [
                "# Docs",
                *[f"- x {token}" for token in MODULE.DOCS_README_LINK_TOKENS],
            ]
        ),
    )
    _write(
        tmp_path / "docs/AGENTHUB_REPOSITORY_GOVERNANCE.md",
        "\n".join(
            [
                "# Governance",
                *[f"- `{token}`" for token in MODULE.GOVERNANCE_OVERVIEW_TOKENS],
            ]
        ),
    )

    errors = MODULE.check_repository(tmp_path)
    assert errors == []


def test_check_repository_reports_missing_link_and_reference(tmp_path: Path) -> None:
    _seed_required_files(tmp_path)
    _write(tmp_path / "docs/README.md", "# Docs\n")
    _write(tmp_path / "docs/AGENTHUB_REPOSITORY_GOVERNANCE.md", "# Governance\n")

    errors = MODULE.check_repository(tmp_path)

    assert any("docs/README.md missing governance link token" in message for message in errors)
    assert any(
        "docs/AGENTHUB_REPOSITORY_GOVERNANCE.md missing reference token" in message
        for message in errors
    )
