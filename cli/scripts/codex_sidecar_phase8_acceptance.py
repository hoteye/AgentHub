#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402
import argparse
import subprocess
import sys
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CLI_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.scripts.codex_sidecar_phase8_acceptance_checks import (
    FAKE_CODEX_BIN,
    PROTOTYPE_PROBE,
    TUI_SMOKE_PROBE,
    run_fake_acceptance,
    run_real_agenthub_sidecar,
    run_real_codex_ref_probe,
    run_tui_smoke,
)
from cli.scripts.codex_sidecar_phase8_acceptance_report import (
    CheckResult,
    CheckStatus,
    _skip,
    print_results,
    write_report,
)

__all__ = [
    "CheckResult",
    "CheckStatus",
    "FAKE_CODEX_BIN",
    "PROTOTYPE_PROBE",
    "TUI_SMOKE_PROBE",
    "main",
    "parse_args",
    "print_results",
    "run_fake_acceptance",
    "run_real_agenthub_sidecar",
    "run_real_codex_ref_probe",
    "run_tui_smoke",
    "subprocess",
    "write_report",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Phase 8 Codex sidecar acceptance gate. The default path is "
            "offline and uses the fake Codex sidecar."
        )
    )
    parser.add_argument(
        "--include-tui",
        action="store_true",
        help="Also run cli/scripts/tui_tab_smoke_probe.py --quiet.",
    )
    parser.add_argument(
        "--skip-tui",
        action="store_true",
        help="Do not run the TUI smoke probe. This is the default.",
    )
    parser.add_argument(
        "--real-codex-bin",
        type=Path,
        default=None,
        help="Optional real Codex ref binary used for AgentHub-vs-native app-server A/B.",
    )
    parser.add_argument(
        "--live-turn",
        default=None,
        help="Optional live prompt for the real Codex ref binary. Omitted by default.",
    )
    parser.add_argument(
        "--real-fork",
        action="store_true",
        help="After a real live turn, verify thread/fork through both probes.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=REPO_ROOT,
        help="Working directory passed to sidecar thread/start.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=5.0,
        help="JSON-RPC request timeout for fake and real AgentHub-sidecar checks.",
    )
    parser.add_argument(
        "--turn-timeout",
        type=float,
        default=120.0,
        help="Live turn timeout passed to the direct Codex ref probe.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for a machine-readable acceptance report.",
    )
    args = parser.parse_args(argv)
    if args.include_tui and args.skip_tui:
        parser.error("--include-tui and --skip-tui cannot be used together")
    if (args.live_turn or args.real_fork) and args.real_codex_bin is None:
        parser.error("--live-turn and --real-fork require --real-codex-bin")
    if args.real_fork and not args.live_turn:
        parser.error("--real-fork requires --live-turn so Codex has a rollout to fork")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or []))
    results: list[CheckResult] = []
    results.extend(run_fake_acceptance(cwd=args.cwd, request_timeout=args.request_timeout))
    if args.include_tui:
        results.append(run_tui_smoke())
    else:
        results.append(_skip("tui_tab_smoke_probe", "pass --include-tui to run it"))
    if args.real_codex_bin is not None:
        results.append(
            run_real_agenthub_sidecar(
                codex_bin=args.real_codex_bin,
                cwd=args.cwd,
                request_timeout=args.request_timeout,
                turn_timeout=args.turn_timeout,
                live_turn=args.live_turn,
                real_fork=args.real_fork,
            )
        )
        results.append(
            run_real_codex_ref_probe(
                codex_bin=args.real_codex_bin,
                cwd=args.cwd,
                request_timeout=args.request_timeout,
                turn_timeout=args.turn_timeout,
                live_turn=args.live_turn,
                real_fork=args.real_fork,
            )
        )
    else:
        results.append(
            _skip(
                "real_codex_ref_ab_probe",
                "pass --real-codex-bin to run AgentHub-vs-Codex-ref A/B",
            )
        )
    print_results(results)
    if args.output_json is not None:
        write_report(args.output_json, results)
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
