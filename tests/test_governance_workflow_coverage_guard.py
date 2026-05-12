from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_governance_workflow_coverage.py"
SPEC = importlib.util.spec_from_file_location("check_governance_workflow_coverage", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_check_repository_passes_for_minimal_valid_workflow(tmp_path: Path) -> None:
    body = "\n".join([*MODULE.REQUIRED_PATH_TOKENS, *MODULE.REQUIRED_RUN_TOKENS])
    _write(tmp_path / MODULE.WORKFLOW_PATH, body)

    errors = MODULE.check_repository(tmp_path)

    assert errors == []


def test_check_repository_reports_missing_tokens(tmp_path: Path) -> None:
    _write(tmp_path / MODULE.WORKFLOW_PATH, "# incomplete\n")

    errors = MODULE.check_repository(tmp_path)

    assert any("missing required path token" in message for message in errors)
    assert any("missing required run token" in message for message in errors)
