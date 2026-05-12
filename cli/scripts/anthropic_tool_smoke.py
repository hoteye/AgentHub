#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

try:
    from cli.scripts.anthropic_tool_smoke_case_helpers import (
        CASE_BY_ID,
        CASE_DEFINITIONS,
        KNOWN_ASK_USER_DEFAULT_MODE_ERROR,
        KNOWN_ASK_USER_HEADLESS_CANCEL_ERROR,
        CaseDefinition,
        ValidatorFn,
        _populate_temp_workspace,
        _selected_cases,
        _validate_agent_one_shot,
        _validate_ask_user_question_default_mode,
        _validate_bash_pwd,
        _validate_edit_file,
        _validate_glob_find_file,
        _validate_grep_find_text,
        _validate_read_file,
        _validate_send_message_two_turn,
        _validate_update_plan_then_read,
        _validate_web_fetch,
        _validate_web_search,
        _validate_write_file,
        _validate_write_stdin_background,
    )
    from cli.scripts.anthropic_tool_smoke_payload_helpers import (
        _assistant_text,
        _canonical_tool_names,
        _dedupe,
        _projected_tool_names,
        _response_tool_names,
        _temp_path,
        _tool_event,
        _turn_item_types,
        _validation_result,
    )
    from cli.scripts.anthropic_tool_smoke_runtime_helpers import (
        CLI_ROOT,
        DEFAULT_OUT_ROOT,
        REPO_ROOT,
        _case_report,
        _launcher_prefix,
        _markdown_report,
        _parse_serve_jsonl,
        _parse_single_json,
        _run_serve_case,
        _run_single_case,
        _utc_now,
        _utc_tag,
        _write_json,
        _write_text,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from anthropic_tool_smoke_case_helpers import (  # type: ignore[no-redef]
        CASE_BY_ID,
        CASE_DEFINITIONS,
        KNOWN_ASK_USER_DEFAULT_MODE_ERROR,
        KNOWN_ASK_USER_HEADLESS_CANCEL_ERROR,
        CaseDefinition,
        ValidatorFn,
        _populate_temp_workspace,
        _selected_cases,
        _validate_agent_one_shot,
        _validate_ask_user_question_default_mode,
        _validate_bash_pwd,
        _validate_edit_file,
        _validate_glob_find_file,
        _validate_grep_find_text,
        _validate_read_file,
        _validate_send_message_two_turn,
        _validate_update_plan_then_read,
        _validate_web_fetch,
        _validate_web_search,
        _validate_write_file,
        _validate_write_stdin_background,
    )
    from anthropic_tool_smoke_payload_helpers import (  # type: ignore[no-redef]
        _assistant_text,
        _canonical_tool_names,
        _dedupe,
        _projected_tool_names,
        _response_tool_names,
        _temp_path,
        _tool_event,
        _turn_item_types,
        _validation_result,
    )
    from anthropic_tool_smoke_runtime_helpers import (  # type: ignore[no-redef]
        CLI_ROOT,
        DEFAULT_OUT_ROOT,
        REPO_ROOT,
        _case_report,
        _launcher_prefix,
        _markdown_report,
        _parse_serve_jsonl,
        _parse_single_json,
        _run_serve_case,
        _run_single_case,
        _utc_now,
        _utc_tag,
        _write_json,
        _write_text,
    )


SCRIPT_PATH = Path(__file__).resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the source-backed Anthropic Claude-style tool smoke suite against the live AgentHub provider path."
    )
    parser.add_argument("--case", action="append", dest="cases", help="Run only the selected case id. Repeat as needed.")
    parser.add_argument("--list-cases", action="store_true", help="List supported case ids and exit.")
    parser.add_argument("--out-dir", default=None, help="Write artifacts into this directory. Defaults to a timestamped directory under /tmp/agenthub_anthropic_tool_smoke.")
    parser.add_argument("--workspace", default=None, help="Reuse this temp workspace path for temp-workspace cases.")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep the populated temp workspace after the run finishes.")
    parser.add_argument("--timeout-seconds", type=int, default=420, help="Per-case subprocess timeout in seconds.")
    parser.add_argument("--approval-policy", default="never")
    parser.add_argument("--sandbox-mode", default="danger-full-access")
    parser.add_argument("--web-search-mode", default="live")
    parser.add_argument("--network-access", default="enabled")
    parser.add_argument("--json", action="store_true", help="Emit the full report as JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.list_cases:
        for case in CASE_DEFINITIONS:
            print(f"{case.case_id}: {case.title}")
        return 0

    selected_cases = _selected_cases(args.cases)
    out_dir = Path(str(args.out_dir)).resolve() if args.out_dir else DEFAULT_OUT_ROOT / f"run-{_utc_tag()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    temp_workspace_created = args.workspace is None
    temp_workspace = Path(str(args.workspace)).resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="agenthub-anthropic-tool-smoke-"))
    _populate_temp_workspace(temp_workspace)

    run_results: list[dict[str, Any]] = []
    try:
        for case in selected_cases:
            case_dir = out_dir / "cases" / case.case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            if case.mode == "single":
                run = _run_single_case(case, case_dir=case_dir, args=args, temp_workspace=temp_workspace)
            else:
                run = _run_serve_case(case, case_dir=case_dir, args=args)
            run_results.append(_case_report(case, run))
    finally:
        if temp_workspace_created and not args.keep_workspace:
            shutil.rmtree(temp_workspace, ignore_errors=True)

    passed_count = sum(1 for case in run_results if case.get("status") == "passed")
    expected_blocked_count = sum(1 for case in run_results if case.get("status") == "expected_blocked")
    failed_count = sum(1 for case in run_results if case.get("status") == "failed")
    overall_status = "passed" if failed_count == 0 else "failed"
    report = {
        "suite": "anthropic_tool_smoke",
        "generated_at": _utc_now(),
        "repo_root": str(REPO_ROOT),
        "cli_root": str(CLI_ROOT),
        "out_dir": str(out_dir),
        "workspace_kept": bool(args.keep_workspace),
        "workspace_path": str(temp_workspace),
        "approval_policy": str(args.approval_policy),
        "sandbox_mode": str(args.sandbox_mode),
        "web_search_mode": str(args.web_search_mode),
        "network_access": str(args.network_access),
        "timeout_seconds": int(args.timeout_seconds),
        "selected_cases": [case.case_id for case in selected_cases],
        "overall_status": overall_status,
        "passed_count": passed_count,
        "expected_blocked_count": expected_blocked_count,
        "failed_count": failed_count,
        "cases": run_results,
    }
    _write_json(out_dir / "report.json", report)
    _write_text(out_dir / "report.md", _markdown_report(report))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Anthropic tool smoke")
        print(f"  out_dir: {out_dir}")
        print(f"  overall: {overall_status.upper()}")
        print(f"  passed: {passed_count}")
        print(f"  expected_blocked: {expected_blocked_count}")
        print(f"  failed: {failed_count}")
        for case in run_results:
            print(f"  - {case['case_id']}: {str(case['status']).upper()} | {case['summary']}")
    return 0 if overall_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
