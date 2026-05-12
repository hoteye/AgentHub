#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any

try:
    from cli.scripts.approval_continuation_live_harness_model_helpers import (
        DEFAULT_CASES,
        DEFAULT_TIMEOUT_SECONDS,
        LiveCase,
    )
    from cli.scripts.approval_continuation_live_harness_runtime_helpers import (
        run_approval_continuation_harness,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_live_harness_model_helpers import (  # type: ignore[no-redef]
        DEFAULT_CASES,
        DEFAULT_TIMEOUT_SECONDS,
        LiveCase,
    )
    from approval_continuation_live_harness_runtime_helpers import (  # type: ignore[no-redef]
        run_approval_continuation_harness,
    )

__all__ = [
    "DEFAULT_CASES",
    "DEFAULT_TIMEOUT_SECONDS",
    "LiveCase",
    "build_parser",
    "run_harness",
    "main",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run live headless approval continuation checks for approve/reject shell and apply_patch flows.",
    )
    parser.add_argument(
        "--out-root", default="", help="Output root. Defaults to a new /tmp directory."
    )
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt_54")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--case", action="append", default=[], help="Case name to run. Repeat to restrict."
    )
    parser.add_argument(
        "--approval-transport",
        choices=("slash", "control"),
        default="slash",
        help="Approval decision transport used for the second serve request.",
    )
    return parser


def run_harness(args: argparse.Namespace) -> dict[str, Any]:
    return run_approval_continuation_harness(args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_harness(args)
    return 0 if summary.get("verdict") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
