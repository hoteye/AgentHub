#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from cli.scripts.run_multiturn_planning_probe_case_helpers import (
        CASES,
        CaseSpec,
        SeedFile,
        ValidationCommand,
        _selected_cases,
    )
    from cli.scripts.run_multiturn_planning_probe_evaluation_helpers import (
        _agenthub_turn_summary,
        _all_plan_steps_completed,
        _evaluate_case,
        _latest_open_todo_item,
        _latest_todo_item,
        _looks_like_provider_unavailable,
        _max_in_progress_count,
        _plan_from_todo_item,
        _plan_signature,
        _todo_events,
    )
    from cli.scripts.run_multiturn_planning_probe_process_helpers import (
        _run_case_once,
        _run_case_with_retries,
        _shutdown_serve_process,
        _wait_for_json_line,
        _write_optional_text,
    )
    from cli.scripts.run_multiturn_planning_probe_reporting_helpers import _summary_markdown
    from cli.scripts.run_multiturn_planning_probe_runtime_helpers import (
        AGENTHUB_MAIN,
        CLI_ROOT,
        ScriptProviderSelectionOverride,
        _SCRIPT_PATHS,
        _inventory,
        _now_iso,
        _prepare_agenthub_home,
        _run_validation,
        _seed_workspace,
        _write_json,
        _write_text,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        resolve_agenthub_selection,
        resolve_model_and_reasoning_settings,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_multiturn_planning_probe_case_helpers import (  # type: ignore[no-redef]
        CASES,
        CaseSpec,
        SeedFile,
        ValidationCommand,
        _selected_cases,
    )
    from run_multiturn_planning_probe_evaluation_helpers import (  # type: ignore[no-redef]
        _agenthub_turn_summary,
        _all_plan_steps_completed,
        _evaluate_case,
        _latest_open_todo_item,
        _latest_todo_item,
        _looks_like_provider_unavailable,
        _max_in_progress_count,
        _plan_from_todo_item,
        _plan_signature,
        _todo_events,
    )
    from run_multiturn_planning_probe_process_helpers import (  # type: ignore[no-redef]
        _run_case_once,
        _run_case_with_retries,
        _shutdown_serve_process,
        _wait_for_json_line,
        _write_optional_text,
    )
    from run_multiturn_planning_probe_reporting_helpers import _summary_markdown  # type: ignore[no-redef]
    from run_multiturn_planning_probe_runtime_helpers import (  # type: ignore[no-redef]
        AGENTHUB_MAIN,
        CLI_ROOT,
        ScriptProviderSelectionOverride,
        _SCRIPT_PATHS,
        _inventory,
        _now_iso,
        _prepare_agenthub_home,
        _run_validation,
        _seed_workspace,
        _write_json,
        _write_text,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        resolve_agenthub_selection,
        resolve_model_and_reasoning_settings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/run_multiturn_planning_probe.py",
        description="Run a multi-turn AgentHub planning acceptance probe over headless serve.",
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
    selection_override = resolve_agenthub_selection(
        provider=str(args.agenthub_provider),
        model=str(args.agenthub_model),
        reasoning_effort=str(args.reasoning_effort),
        interaction_profile=str(args.agenthub_interaction_profile),
    )
    selected_cases = _selected_cases(args.cases)
    out_root = Path(args.out_root) if args.out_root else Path(
        tempfile.mkdtemp(prefix="agenthub_multiturn_planning_probe_", dir="/tmp")
    )
    out_root.mkdir(parents=True, exist_ok=True)

    case_results: list[dict[str, Any]] = []
    for case in selected_cases:
        case_results.append(
            _run_case_with_retries(
                root_dir=out_root,
                case=case,
                selection_override=selection_override,
                timeout_seconds=int(args.timeout_seconds),
                retry_attempts=int(args.retry_attempts),
            )
        )

    report = {
        "generated_at": _now_iso(),
        "provider": selection_override.provider_name,
        "model": selection_override.model,
        "reasoning_effort": selection_override.reasoning_effort,
        "interaction_profile": str(args.agenthub_interaction_profile),
        "selected_cases": [case.name for case in selected_cases],
        "cases": case_results,
    }
    report_path = out_root / "report.json"
    report["report_path"] = str(report_path)
    _write_json(report_path, report)
    summary_path = out_root / "summary.md"
    _write_text(summary_path, _summary_markdown(report))
    print(
        json.dumps(
            {
                "out_root": str(out_root),
                "report_path": str(report_path),
                "summary_path": str(summary_path),
                "case_results": [
                    {
                        "case_name": item.get("case_name"),
                        "passed": item.get("evaluation", {}).get("passed"),
                        "issues": item.get("evaluation", {}).get("issues"),
                    }
                    for item in case_results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
