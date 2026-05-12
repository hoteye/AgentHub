from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def commands_for_mode(mode: str, python_executable: str) -> tuple[tuple[str, ...], ...]:
    fast_commands: tuple[tuple[str, ...], ...] = (
        (python_executable, "scripts/check_owners_coverage.py"),
        (python_executable, "scripts/check_governance_doc_links.py"),
        (python_executable, "scripts/check_taskboard_status.py"),
        (python_executable, "scripts/check_governance_workflow_coverage.py"),
    )
    if mode == "fast":
        return fast_commands
    if mode == "ci":
        return fast_commands + (
            (
                python_executable,
                "-m",
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "tests/test_owners_coverage_guard.py",
                "tests/test_governance_doc_links_guard.py",
                "tests/test_taskboard_status_guard.py",
                "tests/test_governance_workflow_coverage_guard.py",
                "cli/tests/test_changed_files_test_gate.py",
                "cli/tests/test_provider_config_boundary_guard.py",
            ),
            (
                python_executable,
                "cli/scripts/changed_files_test_gate.py",
                "--working-dir",
                "cli",
                "--changed",
                ".github/workflows/governance-guards.yml",
            ),
            (
                python_executable,
                "cli/scripts/provider_config_boundary_guard.py",
                "--root",
                ".",
            ),
        )
    raise ValueError(f"unsupported mode: {mode}")


def run_commands(commands: tuple[tuple[str, ...], ...], root: Path) -> int:
    for command in commands:
        print(f"[governance-runner] run: {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=root, check=False)
        if completed.returncode != 0:
            print(f"[governance-runner] failed: {' '.join(command)}", flush=True)
            return completed.returncode
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local or CI governance guard bundle."
    )
    parser.add_argument(
        "--mode",
        choices=("fast", "ci"),
        default="fast",
        help="Select guard bundle mode.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    commands = commands_for_mode(args.mode, sys.executable)
    return run_commands(commands, args.root.resolve())


if __name__ == "__main__":
    sys.exit(main())
