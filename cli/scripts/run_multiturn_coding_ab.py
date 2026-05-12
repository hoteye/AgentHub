#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

try:
    from cli.scripts.run_multiturn_coding_ab_evaluation_helpers import (
        _agenthub_turn_summary,
        _attempt_success,
        _looks_like_provider_unavailable,
        _parse_codex_stdout,
        _render_markdown,
        _run_validation,
    )
    from cli.scripts.run_multiturn_coding_ab_model_io_helpers import (
        DEFAULT_CASE,
        CaseSpec,
        _inventory,
        _now_iso,
        _write_json,
        _write_text,
    )
    from cli.scripts.run_multiturn_coding_ab_runtime_helpers import (
        AGENTHUB_MAIN,
        CLI_ROOT,
        CODEX_BIN,
        CODEX_REF_ROOT,
        _SCRIPT_PATHS,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        _codex_exec_command,
        _prepare_agenthub_home,
        _prepare_codex_home,
        _run_agenthub_case,
        _run_attempt,
        _run_codex_case,
        _wait_for_json_line,
        resolve_codex_source_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_multiturn_coding_ab_evaluation_helpers import (  # type: ignore[no-redef]
        _agenthub_turn_summary,
        _attempt_success,
        _looks_like_provider_unavailable,
        _parse_codex_stdout,
        _render_markdown,
        _run_validation,
    )
    from run_multiturn_coding_ab_model_io_helpers import (  # type: ignore[no-redef]
        DEFAULT_CASE,
        CaseSpec,
        _inventory,
        _now_iso,
        _write_json,
        _write_text,
    )
    from run_multiturn_coding_ab_runtime_helpers import (  # type: ignore[no-redef]
        AGENTHUB_MAIN,
        CLI_ROOT,
        CODEX_BIN,
        CODEX_REF_ROOT,
        _SCRIPT_PATHS,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        _codex_exec_command,
        _prepare_agenthub_home,
        _prepare_codex_home,
        _run_agenthub_case,
        _run_attempt,
        _run_codex_case,
        _wait_for_json_line,
        resolve_codex_source_paths,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/run_multiturn_coding_ab.py",
        description="Run a multi-turn complex coding A/B between AgentHub headless serve and Codex Ref.",
    )
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--out-root",
        default="",
        help="Optional output directory. Defaults to a new /tmp temp directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    out_root = (
        Path(args.out_root).resolve()
        if str(args.out_root or "").strip()
        else Path(tempfile.mkdtemp(prefix="agenthub_codex_multiturn_coding_", dir="/tmp"))
    )
    out_root.mkdir(parents=True, exist_ok=True)

    case = DEFAULT_CASE
    final_report: dict[str, Any] | None = None
    for attempt_index in range(1, max(int(args.retry_attempts), 1) + 1):
        attempt_root = out_root / f"attempt_{attempt_index:02d}"
        print(f"[attempt {attempt_index}] start -> {attempt_root}", flush=True)
        report = _run_attempt(
            root=attempt_root,
            case=case,
            reasoning_effort=str(args.reasoning_effort or "").strip() or "xhigh",
            timeout_seconds=max(int(args.timeout_seconds), 1),
        )
        report["attempt_index"] = attempt_index
        _write_json(attempt_root / "report.json", report)
        if bool(report.get("success")):
            final_report = report
            break
        print(f"[attempt {attempt_index}] incomplete; see {attempt_root / 'report.json'}", flush=True)
        final_report = report

    if final_report is None:
        parser.error("no attempt executed")

    overall_summary = {
        "root": str(out_root),
        "case_name": case.name,
        "attempts_used": int(final_report.get("attempt_index") or 0),
        "started_at": _now_iso(),
        "ended_at": _now_iso(),
        "reasoning_effort": str(args.reasoning_effort or "").strip() or "xhigh",
        "success": bool(final_report.get("success")),
        "final_attempt_dir": str(Path(final_report["root"])),
        "final_report_path": str(Path(final_report["root"]) / "report.json"),
        "final_summary_path": str(Path(final_report["root"]) / "summary.md"),
    }
    _write_json(out_root / "overall_summary.json", overall_summary)
    print("FINAL_REPORT", overall_summary["final_report_path"], flush=True)
    print("FINAL_SUMMARY", overall_summary["final_summary_path"], flush=True)
    return 0 if bool(final_report.get("success")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
