from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence, TextIO

from .benchmark_acceptance_case_helpers import (
    ALLOWED_EVIDENCE_LEVELS,
    EVIDENCE_LEVEL_PASS_LEVELS,
    PASS_LEVEL_FIELDS,
    PASS_LEVEL_ORDER,
    REQUIRED_ROW_FIELDS,
    BenchmarkCaseSpec,
    _BENCHMARK_CASE_SPECS,
    _benchmark_case_order,
    _evidence_pass_level,
    _sorted_rows,
    get_benchmark_case_spec,
    list_benchmark_case_ids,
    list_benchmark_case_specs,
    required_surfaces_for_benchmark,
    row_contract_failures,
)
from .benchmark_acceptance_projection_helpers import (
    _arguments_from_first_tool_event,
    _arguments_from_function_call_outputs,
    _arguments_from_tool_event,
    _arguments_from_tool_item,
    _coerce_dict,
    _coerce_live_results_items,
    _evidence_level_for_case_source_kind,
    _first_tool_event,
    _load_live_results,
    _metric,
    _normalized_arguments_for_matching,
    _result_text_candidates,
    _tool_arguments_from_payload,
    _tool_items,
    _tool_name_from_item,
    _tool_name_from_payload,
    _value_matches,
    build_acceptance_row,
    project_live_headless_ab_report_to_row,
)
from .benchmark_acceptance_readout_helpers import (
    _load_json_object,
    _markdown_bool,
    _resolve_readout_report_paths,
    _write_json,
    _write_text,
    build_acceptance_readout,
    render_acceptance_readout_markdown,
    write_acceptance_readout,
)
from .benchmark_acceptance_scoring_helpers import (
    EVIDENCE_LEVEL_SCORE_WEIGHTS,
    LATENCY_SCORING_WINDOWS_MS,
    SCORING_COMPONENT_MAX_SCORES,
    SCORING_MODEL_ID,
    _average_score,
    _component_score_summary,
    _evidence_pass_level_floor,
    _expected_case_ids_by_surface,
    _latency_score,
    _normalized_unique_strings,
    _round_score,
    score_acceptance_row,
    score_acceptance_rows,
    summarize_acceptance_rows,
)


__all__ = [
    "ALLOWED_EVIDENCE_LEVELS",
    "BenchmarkCaseSpec",
    "EVIDENCE_LEVEL_PASS_LEVELS",
    "EVIDENCE_LEVEL_SCORE_WEIGHTS",
    "LATENCY_SCORING_WINDOWS_MS",
    "PASS_LEVEL_FIELDS",
    "PASS_LEVEL_ORDER",
    "REQUIRED_ROW_FIELDS",
    "SCORING_COMPONENT_MAX_SCORES",
    "SCORING_MODEL_ID",
    "build_acceptance_readout",
    "build_acceptance_row",
    "build_parser",
    "get_benchmark_case_spec",
    "list_benchmark_case_ids",
    "list_benchmark_case_specs",
    "main",
    "project_live_headless_ab_report_to_row",
    "render_acceptance_readout_markdown",
    "required_surfaces_for_benchmark",
    "row_contract_failures",
    "score_acceptance_row",
    "score_acceptance_rows",
    "summarize_acceptance_rows",
    "write_acceptance_readout",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli.replay_integration.benchmark_acceptance",
        description="Aggregate live_headless_ab benchmark artifacts into an acceptance readout.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="list benchmark case ids and exit",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="diff_report.json path, case artifact directory, or bundle root containing diff_report.json files",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="write report.json and summary.md into this directory",
    )
    parser.add_argument(
        "--require-pass-level",
        choices=tuple(PASS_LEVEL_FIELDS),
        default="bundle",
        help="minimum pass level required for zero exit status",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_cases:
        print("\n".join(list_benchmark_case_ids()), file=output_stream)
        return 0
    if not args.input:
        parser.print_usage(error_stream)
        print("benchmark acceptance error: at least one --input is required unless --list-cases is used", file=error_stream)
        return 2

    report = build_acceptance_readout(
        args.input,
        required_pass_level=args.require_pass_level,
    )
    if str(args.out_dir or "").strip():
        report = write_acceptance_readout(report, out_dir=str(args.out_dir).strip())
    print(json.dumps(report, ensure_ascii=False, indent=2), file=output_stream)
    return 0 if report.get("pass_level_satisfied") else 3


if __name__ == "__main__":
    raise SystemExit(main())
