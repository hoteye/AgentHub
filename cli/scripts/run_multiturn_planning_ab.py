#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from cli.scripts import run_multiturn_planning_probe as planning_probe
    from cli.scripts.run_multiturn_planning_ab_execution_helpers import (
        _evaluate_system_case,
        _run_agenthub_case_once,
        _run_case_once,
        _run_codex_case_once,
    )
    from cli.scripts.run_multiturn_planning_ab_projection_helpers import (
        _all_plan_steps_completed,
        _codex_todo_events,
        _latest_open_todo_item,
        _latest_todo_item,
        _max_in_progress_count,
        _parse_codex_stdout,
        _plan_from_todo_item,
        _plan_signature,
    )
    from cli.scripts.run_multiturn_planning_ab_reporting_helpers import _render_summary
    from cli.scripts.run_multiturn_planning_ab_runtime_helpers import (
        CLI_ROOT,
        CODEX_BIN,
        CODEX_REF_ROOT,
        _SCRIPT_PATHS,
        _codex_exec_command,
        _inventory,
        _now_iso,
        _prepare_codex_home,
        _write_json,
        _write_text,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        resolve_codex_source_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    import run_multiturn_planning_probe as planning_probe  # type: ignore[no-redef]
    from run_multiturn_planning_ab_execution_helpers import (  # type: ignore[no-redef]
        _evaluate_system_case,
        _run_agenthub_case_once,
        _run_case_once,
        _run_codex_case_once,
    )
    from run_multiturn_planning_ab_projection_helpers import (  # type: ignore[no-redef]
        _all_plan_steps_completed,
        _codex_todo_events,
        _latest_open_todo_item,
        _latest_todo_item,
        _max_in_progress_count,
        _parse_codex_stdout,
        _plan_from_todo_item,
        _plan_signature,
    )
    from run_multiturn_planning_ab_reporting_helpers import _render_summary  # type: ignore[no-redef]
    from run_multiturn_planning_ab_runtime_helpers import (  # type: ignore[no-redef]
        CLI_ROOT,
        CODEX_BIN,
        CODEX_REF_ROOT,
        _SCRIPT_PATHS,
        _codex_exec_command,
        _inventory,
        _now_iso,
        _prepare_codex_home,
        _write_json,
        _write_text,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        resolve_codex_source_paths,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/run_multiturn_planning_ab.py",
        description="Run a multi-turn planning A/B between AgentHub headless serve and codex_ref.",
    )
    parser.add_argument("--agenthub-provider", default="openai")
    parser.add_argument("--agenthub-model", default="gpt-5.4")
    parser.add_argument("--agenthub-interaction-profile", default="codex_openai")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--retry-attempts", type=int, default=1)
    parser.add_argument(
        "--cases",
        default="",
        help="Comma-separated case names. Defaults to all planning cases.",
    )
    parser.add_argument(
        "--out-root",
        default="",
        help="Optional output directory. Defaults to a new /tmp temp directory.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    selection_override = planning_probe.resolve_agenthub_selection(
        provider=str(args.agenthub_provider),
        model=str(args.agenthub_model),
        reasoning_effort=str(args.reasoning_effort),
        interaction_profile=str(args.agenthub_interaction_profile),
    )
    out_root = Path(args.out_root) if args.out_root else Path(
        tempfile.mkdtemp(prefix="agenthub_codex_multiturn_planning_ab_", dir="/tmp")
    )
    out_root.mkdir(parents=True, exist_ok=True)
    selected_cases = planning_probe._selected_cases(args.cases)

    results: list[dict[str, Any]] = []
    for case in selected_cases:
        case_root = out_root / case.name / "attempt_01"
        result = _run_case_once(
            attempt_root=case_root,
            case=case,
            selection_override=selection_override,
            timeout_seconds=int(args.timeout_seconds),
        )
        results.append(result)

    report = {
        "generated_at": _now_iso(),
        "agenthub_provider": selection_override.provider_name,
        "agenthub_model": selection_override.model,
        "reasoning_effort": selection_override.reasoning_effort,
        "agenthub_interaction_profile": str(args.agenthub_interaction_profile),
        "cases": results,
    }
    report_path = out_root / "report.json"
    summary_path = out_root / "summary.md"
    _write_json(report_path, report)
    _write_text(summary_path, _render_summary(report))
    print(
        json.dumps(
            {
                "out_root": str(out_root),
                "report_path": str(report_path),
                "summary_path": str(summary_path),
                "cases": [
                    {
                        "case_name": item.get("case_name"),
                        "agenthub_passed": item["systems"]["agenthub"]["evaluation"]["passed"],
                        "codex_passed": item["systems"]["codex"]["evaluation"]["passed"],
                    }
                    for item in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
