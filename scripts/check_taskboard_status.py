from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOWED_STATUSES: tuple[str, ...] = (
    "draft",
    "ready",
    "in_progress",
    "blocked",
    "completed",
    "archived",
    "superseded",
)

TASK_LINE_STATUS_RE = re.compile(r"^- `Task [^`]+`[：:]\s*([a-z_]+)\s*$", re.MULTILINE)
TASK_CARD_STATUS_RE = re.compile(r"^Status:\s*([a-z_]+)\s*$", re.MULTILINE)
WAVE_STATUS_RE = re.compile(r"^Wave status:\s*([a-z_]+)\s*$", re.MULTILINE)
CLOSURE_REQUIRED_STATUSES = {"completed", "archived", "superseded"}
ACTIVE_STATUSES = {"draft", "ready", "in_progress", "blocked"}


def governance_wave_dirs(root: Path) -> list[Path]:
    taskboard_dir = root / "taskboard"
    if not taskboard_dir.exists():
        return []
    return sorted(
        path
        for path in taskboard_dir.iterdir()
        if path.is_dir() and path.name.startswith("repository_governance_wave_")
    )


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    allowed = set(ALLOWED_STATUSES)

    root_taskboard_readme = root / "taskboard/README.md"
    if not root_taskboard_readme.exists():
        errors.append("missing required file: taskboard/README.md")
    else:
        root_taskboard_text = root_taskboard_readme.read_text(encoding="utf-8")
        for status in ALLOWED_STATUSES:
            token = f"`{status}`"
            if token not in root_taskboard_text:
                errors.append(f"taskboard/README.md missing status token: {token}")

    lifecycle_policy = root / "docs/AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md"
    if not lifecycle_policy.exists():
        errors.append("missing required file: docs/AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md")
    else:
        lifecycle_text = lifecycle_policy.read_text(encoding="utf-8")
        for status in ALLOWED_STATUSES:
            token = f"`{status}`"
            if token not in lifecycle_text:
                errors.append(
                    "docs/AGENTHUB_DOCS_TASKBOARD_LIFECYCLE_POLICY.md missing status token: "
                    f"{token}"
                )

    wave_dirs = governance_wave_dirs(root)
    if not wave_dirs:
        errors.append("no governance wave directory found under taskboard/")
        return errors

    for wave_dir in wave_dirs:
        wave_readme = wave_dir / "README.md"
        wave_prefix = wave_dir.relative_to(root).as_posix()

        if not wave_readme.exists():
            errors.append(f"{wave_prefix}: missing README.md")
            continue

        wave_text = wave_readme.read_text(encoding="utf-8")
        if "Last updated:" not in wave_text:
            errors.append(f"{wave_prefix}/README.md missing 'Last updated:'")
        wave_status_match = WAVE_STATUS_RE.search(wave_text)
        if not wave_status_match:
            errors.append(f"{wave_prefix}/README.md missing 'Wave status:'")
            wave_status = ""
        else:
            wave_status = wave_status_match.group(1)
            if wave_status not in allowed:
                errors.append(f"{wave_prefix}/README.md has unsupported wave status '{wave_status}'")
        if "AGENTHUB_REPOSITORY_GOVERNANCE_TASKBOOK.md" not in wave_text:
            errors.append(
                f"{wave_prefix}/README.md missing link to AGENTHUB_REPOSITORY_GOVERNANCE_TASKBOOK.md"
            )

        readme_statuses = TASK_LINE_STATUS_RE.findall(wave_text)
        if not readme_statuses:
            errors.append(f"{wave_prefix}/README.md missing task status lines")
        for status in readme_statuses:
            if status not in allowed:
                errors.append(
                    f"{wave_prefix}/README.md has unsupported task status '{status}'"
                )

        closure_report = wave_dir / "CLOSURE_REPORT.md"
        if wave_status in CLOSURE_REQUIRED_STATUSES:
            if not closure_report.exists():
                errors.append(f"{wave_prefix} missing CLOSURE_REPORT.md for wave status '{wave_status}'")
            else:
                closure_text = closure_report.read_text(encoding="utf-8")
                if "Last updated:" not in closure_text:
                    errors.append(f"{wave_prefix}/CLOSURE_REPORT.md missing 'Last updated:'")
            active_task_statuses = sorted(status for status in readme_statuses if status in ACTIVE_STATUSES)
            if active_task_statuses:
                errors.append(
                    f"{wave_prefix}/README.md has active task status under closed wave: "
                    + ", ".join(active_task_statuses)
                )

        task_cards = sorted(wave_dir.glob("TASK_*.md"))
        if not task_cards:
            errors.append(f"{wave_prefix}: no TASK_*.md files found")
            continue

        for task_card in task_cards:
            relpath = task_card.relative_to(root).as_posix()
            task_text = task_card.read_text(encoding="utf-8")
            for required_token in ("Last updated:", "Priority:", "Owner scope:", "Do not edit:"):
                if required_token not in task_text:
                    errors.append(f"{relpath} missing '{required_token}'")

            status_match = TASK_CARD_STATUS_RE.search(task_text)
            if not status_match:
                errors.append(f"{relpath} missing 'Status:'")
            else:
                status = status_match.group(1)
                if status not in allowed:
                    errors.append(f"{relpath} has unsupported status '{status}'")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate governance taskboard status and minimal metadata."
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
        print(f"[taskboard-status] FAILED ({len(errors)} issue(s))")
        for message in errors:
            print(f"- {message}")
        return 1

    print("[taskboard-status] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
