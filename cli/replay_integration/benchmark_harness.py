from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from .benchmark_acceptance import (
    PASS_LEVEL_FIELDS,
    build_acceptance_readout,
    list_benchmark_case_ids,
    render_acceptance_readout_markdown,
)


def build_benchmark_harness_report(
    inputs: Sequence[str | Path],
    *,
    required_pass_level: str = "bundle",
) -> dict[str, Any]:
    return build_acceptance_readout(inputs, required_pass_level=required_pass_level)


def _write_json(path: str | Path, payload: Any) -> str:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(destination)


def _render_benchmark_harness_markdown(report: dict[str, Any]) -> str:
    rendered = render_acceptance_readout_markdown(report).rstrip()
    scoring = dict(report.get("scoring") or {})
    lines = [rendered, "", "## Harness Summary", ""]
    lines.append(f"- model: `{str(scoring.get('model') or '-').strip() or '-'}`")
    lines.append(f"- score: `{scoring.get('score', 0.0)}`")
    lines.append(f"- max_score: `{scoring.get('max_score', 0.0)}`")
    lines.append(f"- score_ratio: `{scoring.get('score_ratio', 0.0)}`")
    lines.append(f"- parity_score: `{scoring.get('parity_score', 0.0)}`")
    lines.append(f"- parity_score_ratio: `{scoring.get('parity_score_ratio', 0.0)}`")
    lines.append(f"- coverage_ratio: `{scoring.get('coverage_ratio', 0.0)}`")
    lines.append(f"- expected_case_count: `{scoring.get('expected_case_count', 0)}`")
    lines.append(f"- rows_scored: `{scoring.get('rows_scored', 0)}`")
    lines.append(f"- evidence_pass_level_floor: `{str(scoring.get('evidence_pass_level_floor') or '-').strip() or '-'}`")
    lines.append(f"- missing_case_ids: `{', '.join(scoring.get('missing_case_ids') or []) or '-'}`")
    lines.append(f"- missing_surfaces: `{', '.join(scoring.get('missing_surfaces') or []) or '-'}`")
    return "\n".join(lines).strip() + "\n"


def write_benchmark_harness_report(
    report: dict[str, Any],
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    target_dir = Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report or {})
    payload["report_path"] = str((target_dir / "report.json").resolve())
    payload["summary_path"] = str((target_dir / "summary.md").resolve())
    Path(payload["summary_path"]).write_text(_render_benchmark_harness_markdown(payload), encoding="utf-8")
    _write_json(payload["report_path"], payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli.replay_integration.benchmark_harness",
        description="Attach machine-readable scoring to replay/live benchmark acceptance readouts.",
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
        help="write combined report.json and summary.md into this directory",
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
        print(
            "benchmark harness error: at least one --input is required unless --list-cases is used",
            file=error_stream,
        )
        return 2

    result = build_benchmark_harness_report(args.input, required_pass_level=args.require_pass_level)
    if str(args.out_dir or "").strip():
        result = write_benchmark_harness_report(result, out_dir=str(args.out_dir).strip())

    print(json.dumps(result, ensure_ascii=False, indent=2), file=output_stream)
    return 0 if result.get("pass_level_satisfied") else 3


if __name__ == "__main__":
    raise SystemExit(main())
