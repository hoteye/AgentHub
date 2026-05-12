#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.scripts.apply_patch_wave01_acceptance_case_helpers import (
    DEFAULT_CASES,
    DEFAULT_CASES_BY_ID,
    _case_edit_replace_all_after_read,
    _case_edit_requires_read_before_edit,
    _case_edit_stale_rejection_after_read,
    _case_edit_unique_after_read,
    _case_path_traversal_rejection,
    _case_raw_forced_create,
    _case_raw_multi_file_patch,
    _case_verification_failure_no_side_effects,
    _case_write_create,
    _case_write_overwrite_after_read,
    _case_write_requires_read_before_overwrite,
    _case_write_stale_rejection_after_read,
    _edit_payload,
    _write_payload,
)
from cli.scripts.apply_patch_wave01_acceptance_model_helpers import (
    DEFAULT_OUT_ROOT_PREFIX,
    CaseSpec,
    _case_report,
    _compact_payload,
    _completed_item_rows,
    _file_expectation_rows,
    _normalized_file_content,
    _now_iso,
    _registry,
    _step_report,
    _write_json,
    _write_text,
)
from cli.scripts.apply_patch_wave01_acceptance_projection_helpers import (
    CLAUDE_REFERENCE_FILES,
    CODEX_REFERENCE_FILES,
    RELEVANT_SURFACE_TOOLS,
    _reference_snapshot,
    _regression_bundle,
    _surface_runtime,
    _surface_snapshot,
)
from cli.scripts.apply_patch_wave01_acceptance_reporting_helpers import (
    _markdown_report,
    _selected_cases,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/apply_patch_wave01_acceptance.py",
        description="Run the local apply_patch Wave 01 acceptance bundle for the current Wave 01 closure state.",
    )
    parser.add_argument("--case", action="append", default=[], help="Optional case id filter.")
    parser.add_argument("--out-dir", default="", help="Output directory. Defaults to /tmp bundle root.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    selected_cases = _selected_cases(list(args.case or []))
    out_dir = (
        Path(args.out_dir).resolve()
        if str(args.out_dir or "").strip()
        else Path(tempfile.mkdtemp(prefix=DEFAULT_OUT_ROOT_PREFIX, dir="/tmp"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    case_reports: list[dict[str, Any]] = []
    for case in selected_cases:
        case_root = out_dir / case.case_id
        case_root.mkdir(parents=True, exist_ok=True)
        case_reports.append(case.execute(case_root))

    report = {
        "suite": "apply_patch_wave01_acceptance",
        "generated_at": _now_iso(),
        "out_dir": str(out_dir),
        "surface_matrix": [
            _surface_snapshot("codex_openai", model="gpt-5.4"),
            _surface_snapshot("codex_openai", model="gpt-5.1"),
            _surface_snapshot("claude_code", model="claude-sonnet-4-6"),
        ],
        "reference_systems": _reference_snapshot(),
        "cases": case_reports,
        "regression_bundle": _regression_bundle(),
        "open_gaps": [
            "Broader live command-execution coverage still belongs to the unified exec/write_stdin wave; inline apply_patch heredoc interception itself is now closed.",
        ],
        "passed": all(bool(case.get("passed")) for case in case_reports),
    }

    json_path = out_dir / "apply_patch_wave01_acceptance.report.json"
    md_path = out_dir / "apply_patch_wave01_acceptance.report.md"
    _write_json(json_path, report)
    _write_text(md_path, _markdown_report(report))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"out_dir={out_dir}")
        print(f"json_report={json_path}")
        print(f"markdown_report={md_path}")
        print(f"passed={report['passed']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
