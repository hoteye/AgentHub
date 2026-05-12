from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORKFLOW_PATH = ".github/workflows/governance-guards.yml"

REQUIRED_PATH_TOKENS: tuple[str, ...] = (
    ".github/workflows/governance-guards.yml",
    "scripts/check_owners_coverage.py",
    "scripts/check_governance_doc_links.py",
    "scripts/check_taskboard_status.py",
    "scripts/check_governance_workflow_coverage.py",
    "scripts/run_governance_guards.py",
    "scripts/governance/change_test_gate_rules.yaml",
    "cli/scripts/changed_files_test_gate.py",
    "cli/scripts/provider_config_boundary_guard.py",
    "cli/tests/test_changed_files_test_gate.py",
    "cli/tests/test_provider_config_boundary_guard.py",
    "tests/test_owners_coverage_guard.py",
    "tests/test_governance_doc_links_guard.py",
    "tests/test_taskboard_status_guard.py",
    "tests/test_governance_workflow_coverage_guard.py",
    "docs/AGENTHUB_REPOSITORY_GOVERNANCE.md",
    "docs/AGENTHUB_REPOSITORY_GOVERNANCE_TASKBOOK.md",
    "docs/**",
    ".pre-commit-config.yaml",
    "taskboard/**",
)

REQUIRED_RUN_TOKENS: tuple[str, ...] = (
    "python -m pip install -r requirements-dev.txt",
    "python scripts/run_governance_guards.py --mode ci",
)


def check_repository(root: Path) -> list[str]:
    workflow = root / WORKFLOW_PATH
    if not workflow.exists():
        return [f"missing required workflow: {WORKFLOW_PATH}"]

    text = workflow.read_text(encoding="utf-8")
    errors: list[str] = []

    for token in REQUIRED_PATH_TOKENS:
        if token not in text:
            errors.append(f"{WORKFLOW_PATH} missing required path token: {token}")

    for token in REQUIRED_RUN_TOKENS:
        if token not in text:
            errors.append(f"{WORKFLOW_PATH} missing required run token: {token}")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate governance workflow trigger and execution coverage."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = check_repository(args.root.resolve())
    if errors:
        print(f"[governance-workflow] FAILED ({len(errors)} issue(s))")
        for message in errors:
            print(f"- {message}")
        return 1

    print("[governance-workflow] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
