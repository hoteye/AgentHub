#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.agent_cli.acceptance_support.spawn_agent_wave02_support import (
    ALL_CASE_IDS,
    ALL_LANES,
    CLAUDE_REFERENCE_FILES,
    CODEX_REFERENCE_FILES,
    CONTRACT_VERSION,
    DEFAULT_OUT_DIR,
    DIFFERENCE_TAXONOMY,
    PARITY_GAP_NOTES,
    REPO_ROOT,
    SUITE_NAME,
    TASK_B_BLOCKED_ASSUMPTIONS,
    _case_report,
    _markdown_report,
    _now_iso,
    _selected_cases,
    _selected_lanes,
    _surface_matrix,
    _write_json,
    _write_text,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit the source-backed Task C live acceptance bundle for spawn_agent Wave 02."
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--lane", action="append", dest="lanes")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--sandbox-mode", default="danger-full-access")
    parser.add_argument("--approval-policy", default="never")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected_cases = _selected_cases(args.cases)
    selected_lanes = _selected_lanes(args.lanes)
    if not selected_cases:
        raise SystemExit("no matching cases selected")
    if not selected_lanes:
        raise SystemExit("no matching lanes selected")

    report = {
        "suite": SUITE_NAME,
        "contract_version": CONTRACT_VERSION,
        "generated_at": _now_iso(),
        "dry_run": bool(args.dry_run),
        "task_b_state": "in_flight",
        "task_b_blocked_assumptions": list(TASK_B_BLOCKED_ASSUMPTIONS),
        "difference_taxonomy": list(DIFFERENCE_TAXONOMY),
        "parity_gap_notes": list(PARITY_GAP_NOTES),
        "reference_files": {
            "codex_ref": list(CODEX_REFERENCE_FILES),
            "claude_code_ref": list(CLAUDE_REFERENCE_FILES),
        },
        "run_conditions": {
            "workspace_root": str(REPO_ROOT),
            "sandbox_mode": str(args.sandbox_mode),
            "approval_policy": str(args.approval_policy),
            "network_access": "required_for_live_runs",
            "host": {
                "os": "linux",
                "shell": "bash",
            },
        },
        "selected_cases": [case.case_id for case in selected_cases],
        "selected_lanes": list(selected_lanes),
        "surface_matrix": _surface_matrix(),
        "cases": [
            _case_report(
                case,
                lane_ids=selected_lanes,
                dry_run=bool(args.dry_run),
                sandbox_mode=str(args.sandbox_mode),
                approval_policy=str(args.approval_policy),
            )
            for case in selected_cases
        ],
    }

    out_dir = Path(str(args.out_dir)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "spawn_agent_wave02_acceptance.report.json"
    md_path = out_dir / "spawn_agent_wave02_acceptance.report.md"
    _write_json(json_path, report)
    _write_text(md_path, _markdown_report(report))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"report_json={json_path}")
        print(f"report_markdown={md_path}")
        print(f"cases={len(report['cases'])}")
        print(f"lanes={len(selected_lanes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
