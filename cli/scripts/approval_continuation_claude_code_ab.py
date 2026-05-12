#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import ensure_script_import_paths
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import ensure_script_import_paths  # type: ignore[no-redef]


_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
LIVE_HARNESS = CLI_ROOT / "scripts" / "approval_continuation_live_harness.py"

try:
    from cli.scripts.approval_continuation_claude_code_ab_claude_helpers import (
        _claude_prompt_for_case as _claude_prompt_for_case,
    )
    from cli.scripts.approval_continuation_claude_code_ab_claude_helpers import (
        _permission_response_for_case as _permission_response_for_case,
    )
    from cli.scripts.approval_continuation_claude_code_ab_claude_helpers import (
        _run_claude_code_case as _run_claude_code_case,
    )
    from cli.scripts.approval_continuation_claude_code_ab_claude_helpers import (
        _summarize_claude_lines as _summarize_claude_lines,
    )
    from cli.scripts.approval_continuation_claude_code_ab_report_helpers import (
        _write_summary_md,
    )
    from cli.scripts.approval_continuation_claude_code_ab_runtime_helpers import (
        _agenthub_report_for_case as _agenthub_report_for_case,
    )
    from cli.scripts.approval_continuation_claude_code_ab_runtime_helpers import (
        _case_verdict as _case_verdict,
    )
    from cli.scripts.approval_continuation_claude_code_ab_runtime_helpers import (
        _coerce_process_text as _coerce_process_text,
    )
    from cli.scripts.approval_continuation_claude_code_ab_runtime_helpers import (
        _run_case,
    )
    from cli.scripts.approval_continuation_claude_code_ab_runtime_helpers import (
        _run_command as _run_command,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_case_helpers import (
        CASES as _CODEX_REF_AB_CASES,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_case_helpers import (
        AbCase as AbCase,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_case_helpers import (
        _selected_cases,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        CommandResult as CommandResult,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        _file_state as _file_state,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        _now_iso,
        _write_json,
    )
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import (
        _write_text as _write_text,
    )
    from cli.scripts.approval_continuation_live_harness_model_helpers import (
        DEFAULT_TIMEOUT_SECONDS,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_claude_code_ab_claude_helpers import (  # type: ignore[no-redef]
        _claude_prompt_for_case as _claude_prompt_for_case,
    )
    from approval_continuation_claude_code_ab_claude_helpers import (
        _permission_response_for_case as _permission_response_for_case,
    )
    from approval_continuation_claude_code_ab_claude_helpers import (
        _run_claude_code_case as _run_claude_code_case,
    )
    from approval_continuation_claude_code_ab_claude_helpers import (
        _summarize_claude_lines as _summarize_claude_lines,
    )
    from approval_continuation_claude_code_ab_report_helpers import (  # type: ignore[no-redef]
        _write_summary_md,
    )
    from approval_continuation_claude_code_ab_runtime_helpers import (  # type: ignore[no-redef]
        _agenthub_report_for_case as _agenthub_report_for_case,
    )
    from approval_continuation_claude_code_ab_runtime_helpers import (
        _case_verdict as _case_verdict,
    )
    from approval_continuation_claude_code_ab_runtime_helpers import (
        _coerce_process_text as _coerce_process_text,
    )
    from approval_continuation_claude_code_ab_runtime_helpers import (
        _run_case,
    )
    from approval_continuation_claude_code_ab_runtime_helpers import (
        _run_command as _run_command,
    )
    from approval_continuation_codex_ref_ab_case_helpers import (  # type: ignore[no-redef]
        CASES as _CODEX_REF_AB_CASES,
    )
    from approval_continuation_codex_ref_ab_case_helpers import (
        AbCase as AbCase,
    )
    from approval_continuation_codex_ref_ab_case_helpers import (
        _selected_cases,
    )
    from approval_continuation_codex_ref_ab_model_helpers import (  # type: ignore[no-redef]
        CommandResult as CommandResult,
    )
    from approval_continuation_codex_ref_ab_model_helpers import (
        _file_state as _file_state,
    )
    from approval_continuation_codex_ref_ab_model_helpers import (
        _now_iso,
        _write_json,
    )
    from approval_continuation_codex_ref_ab_model_helpers import (
        _write_text as _write_text,
    )
    from approval_continuation_live_harness_model_helpers import (  # type: ignore[no-redef]
        DEFAULT_TIMEOUT_SECONDS,
    )


CASES = _CODEX_REF_AB_CASES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run AgentHub Anthropic approval continuation vs Claude Code stdio approval A/B cases.",
    )
    parser.add_argument(
        "--out-root", default="", help="Output root. Defaults to a new /tmp directory."
    )
    parser.add_argument("--agenthub-provider", default="anthropic")
    parser.add_argument("--agenthub-model", default="claude_sonnet_46")
    parser.add_argument("--agenthub-reasoning-effort", default="high")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--claude-model", default="sonnet")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--case", action="append", default=[], help="Case name to run. Repeat to restrict."
    )
    parser.add_argument(
        "--run-live",
        action="store_true",
        help="Actually call live providers. Omitted means dry-run.",
    )
    return parser


def run_harness(args: argparse.Namespace) -> dict[str, Any]:
    out_root = (
        Path(args.out_root).expanduser().resolve()
        if str(args.out_root or "").strip()
        else Path(
            tempfile.mkdtemp(prefix="approval_continuation_claude_code_ab_", dir="/tmp")
        ).resolve()
    )
    out_root.mkdir(parents=True, exist_ok=True)
    dry_run = not bool(args.run_live)
    cases = _selected_cases([str(item) for item in list(args.case or [])])
    results = [
        _run_case(
            case=case,
            case_root=out_root / case.name,
            agenthub_provider=str(args.agenthub_provider or "").strip(),
            agenthub_model=str(args.agenthub_model or "").strip(),
            agenthub_reasoning_effort=str(args.agenthub_reasoning_effort or "").strip(),
            claude_bin=str(args.claude_bin or "claude"),
            claude_model=str(args.claude_model or "").strip(),
            timeout_seconds=int(args.timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
            dry_run=dry_run,
        )
        for case in cases
    ]
    pass_count = sum(1 for item in results if item.get("verdict") == "pass")
    fail_count = sum(1 for item in results if item.get("verdict") not in {"pass", "dry_run"})
    report = {
        "schema_version": "approval_continuation_claude_code_ab_v1",
        "created_at": _now_iso(),
        "dry_run": dry_run,
        "out_root": str(out_root),
        "agenthub_provider": str(args.agenthub_provider or "").strip(),
        "agenthub_model": str(args.agenthub_model or "").strip(),
        "agenthub_reasoning_effort": str(args.agenthub_reasoning_effort or "").strip(),
        "claude_bin": str(args.claude_bin or "claude"),
        "claude_model": str(args.claude_model or "").strip(),
        "case_count": len(results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "verdict": "dry_run" if dry_run else "pass" if fail_count == 0 else "fail",
        "results": results,
    }
    _write_json(out_root / "report.json", report)
    _write_summary_md(out_root / "summary.md", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    report = run_harness(build_parser().parse_args(argv))
    return 0 if report.get("verdict") in {"pass", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
