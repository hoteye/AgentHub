from __future__ import annotations

import argparse
import sys
from pathlib import Path


REQUIRED_FILES: tuple[str, ...] = (
    "docs/AGENTHUB_REPOSITORY_GOVERNANCE.md",
    "docs/AGENTHUB_REPOSITORY_GOVERNANCE_TASKBOOK.md",
    "docs/AGENTHUB_CHANGE_TEST_GATE_POLICY.md",
    "docs/AGENTHUB_SECURITY_RESPONSE_POLICY.md",
    "docs/AGENTHUB_SECRETS_HANDLING_POLICY.md",
    "docs/AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md",
    "docs/AGENTHUB_RELEASE_SUPPORT_POLICY.md",
    "OWNERS.md",
    ".github/CODEOWNERS",
    "taskboard/README.md",
)

DOCS_README_LINK_TOKENS: tuple[str, ...] = (
    "(AGENTHUB_REPOSITORY_GOVERNANCE.md)",
    "(AGENTHUB_REPOSITORY_GOVERNANCE_TASKBOOK.md)",
    "(AGENTHUB_CHANGE_TEST_GATE_POLICY.md)",
    "(AGENTHUB_SECURITY_RESPONSE_POLICY.md)",
    "(AGENTHUB_SECRETS_HANDLING_POLICY.md)",
    "(AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md)",
    "(AGENTHUB_RELEASE_SUPPORT_POLICY.md)",
    "(../OWNERS.md)",
    "(../.github/CODEOWNERS)",
)

GOVERNANCE_OVERVIEW_TOKENS: tuple[str, ...] = (
    "docs/README.md",
    "docs/DIRECTORY_BLUEPRINT.md",
    "OWNERS.md",
    ".github/CODEOWNERS",
    "docs/AGENTHUB_CHANGE_TEST_GATE_POLICY.md",
    "docs/AGENTHUB_SECURITY_RESPONSE_POLICY.md",
    "docs/AGENTHUB_SECRETS_HANDLING_POLICY.md",
    "docs/AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md",
    "docs/AGENTHUB_RELEASE_SUPPORT_POLICY.md",
)


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []

    for relpath in REQUIRED_FILES:
        if not (root / relpath).exists():
            errors.append(f"missing required file: {relpath}")

    docs_readme_path = root / "docs/README.md"
    if docs_readme_path.exists():
        docs_readme_text = docs_readme_path.read_text(encoding="utf-8")
        for token in DOCS_README_LINK_TOKENS:
            if token not in docs_readme_text:
                errors.append(f"docs/README.md missing governance link token: {token}")
    else:
        errors.append("missing required file: docs/README.md")

    governance_overview_path = root / "docs/AGENTHUB_REPOSITORY_GOVERNANCE.md"
    if governance_overview_path.exists():
        overview_text = governance_overview_path.read_text(encoding="utf-8")
        for token in GOVERNANCE_OVERVIEW_TOKENS:
            if token not in overview_text:
                errors.append(
                    "docs/AGENTHUB_REPOSITORY_GOVERNANCE.md missing reference token: "
                    f"{token}"
                )
    else:
        errors.append("missing required file: docs/AGENTHUB_REPOSITORY_GOVERNANCE.md")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate governance entry docs and required links."
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
    root = args.root.resolve()
    errors = check_repository(root)

    if errors:
        print(f"[governance-links] FAILED ({len(errors)} issue(s))")
        for message in errors:
            print(f"- {message}")
        return 1

    print("[governance-links] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
