from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.agent_cli.tools_core.command_execution_acceptance_runtime import (
    run_command_execution_wave02_acceptance,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Wave 02 long-session acceptance suite for unified command execution."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full acceptance report as JSON.",
    )
    parser.add_argument(
        "--python",
        dest="python_executable",
        default=None,
        help="Override the Python executable used by the acceptance cases.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_command_execution_wave02_acceptance(
        python_executable=args.python_executable,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        host = report.get("host") or {}
        print("Wave 02 command execution acceptance")
        print(f"  host: {host.get('os')} ({host.get('family')}), shell={host.get('shell_kind')}")
        for case in report.get("cases") or []:
            status = "PASS" if case.get("passed") else "FAIL"
            print(f"  - {case.get('name')}: {status}")
        print(f"  overall: {'PASS' if report.get('passed') else 'FAIL'}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
