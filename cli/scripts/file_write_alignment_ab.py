#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from cli.scripts.file_write_alignment_ab_case_helpers import (
        AGENTHUB_MAIN,
        CLAUDE_BIN,
        CLI_ROOT,
        CODEX_BIN,
        DEFAULT_CASES,
        DEFAULT_OUT_ROOT_PREFIX,
        DEFAULT_TIMEOUT_SECONDS,
        REPO_ROOT,
        CaseSpec,
        _selected_cases,
        add_claude_observability_args,
    )
    from cli.scripts.file_write_alignment_ab_io_helpers import (
        _collect_expected_file_results,
        _copy_workspace_files,
        _load_toml,
        _normalized_file_content,
        _now_iso,
        _wait_for_json_line,
        _write_json,
        _write_text,
    )
    from cli.scripts.file_write_alignment_ab_parser_helpers import (
        _parse_agenthub_request_tool_names,
        _parse_agenthub_turn,
        _parse_claude_stream,
        _parse_codex_stdout,
    )
    from cli.scripts.file_write_alignment_ab_reporting_helpers import (
        _render_case_markdown,
        _render_markdown,
    )
    from cli.scripts.file_write_alignment_ab_runtime_helpers import (
        _claude_command,
        _claude_env,
        _codex_exec_command,
        _prepare_agenthub_home,
        _prepare_codex_home,
        _resolved_claude_settings_file,
        _run_agenthub_case,
        _run_claude_case,
        _run_codex_case,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from file_write_alignment_ab_case_helpers import (  # type: ignore[no-redef]
        AGENTHUB_MAIN,
        CLAUDE_BIN,
        CLI_ROOT,
        CODEX_BIN,
        DEFAULT_CASES,
        DEFAULT_OUT_ROOT_PREFIX,
        DEFAULT_TIMEOUT_SECONDS,
        REPO_ROOT,
        CaseSpec,
        _selected_cases,
        add_claude_observability_args,
    )
    from file_write_alignment_ab_io_helpers import (  # type: ignore[no-redef]
        _collect_expected_file_results,
        _copy_workspace_files,
        _load_toml,
        _normalized_file_content,
        _now_iso,
        _wait_for_json_line,
        _write_json,
        _write_text,
    )
    from file_write_alignment_ab_parser_helpers import (  # type: ignore[no-redef]
        _parse_agenthub_request_tool_names,
        _parse_agenthub_turn,
        _parse_claude_stream,
        _parse_codex_stdout,
    )
    from file_write_alignment_ab_reporting_helpers import (  # type: ignore[no-redef]
        _render_case_markdown,
        _render_markdown,
    )
    from file_write_alignment_ab_runtime_helpers import (  # type: ignore[no-redef]
        _claude_command,
        _claude_env,
        _codex_exec_command,
        _prepare_agenthub_home,
        _prepare_codex_home,
        _resolved_claude_settings_file,
        _run_agenthub_case,
        _run_claude_case,
        _run_codex_case,
    )


__all__ = (
    "AGENTHUB_MAIN",
    "CLAUDE_BIN",
    "CLI_ROOT",
    "CODEX_BIN",
    "DEFAULT_CASES",
    "DEFAULT_OUT_ROOT_PREFIX",
    "DEFAULT_TIMEOUT_SECONDS",
    "REPO_ROOT",
    "CaseSpec",
    "add_claude_observability_args",
    "build_parser",
    "main",
    "_claude_command",
    "_claude_env",
    "_codex_exec_command",
    "_collect_expected_file_results",
    "_copy_workspace_files",
    "_load_toml",
    "_normalized_file_content",
    "_now_iso",
    "_parse_agenthub_request_tool_names",
    "_parse_agenthub_turn",
    "_parse_claude_stream",
    "_parse_codex_stdout",
    "_prepare_agenthub_home",
    "_prepare_codex_home",
    "_render_case_markdown",
    "_render_markdown",
    "_resolved_claude_settings_file",
    "_run_agenthub_case",
    "_run_claude_case",
    "_run_codex_case",
    "_selected_cases",
    "_wait_for_json_line",
    "_write_json",
    "_write_text",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/file_write_alignment_ab.py",
        description="Run file_write alignment acceptance across AgentHub, Codex, and Claude Code.",
    )
    parser.add_argument("--out-root", default="", help="Optional output directory.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--agenthub-model", default="claude-sonnet-4-6")
    parser.add_argument("--claude-model", default="claude-sonnet-4-6")
    parser.add_argument("--claude-effort", default="high")
    parser.add_argument("--agenthub-reasoning-effort", default="high")
    add_claude_observability_args(parser)
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Case name to run. Repeat to restrict the suite.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_root = (
        Path(args.out_root).resolve()
        if str(args.out_root or "").strip()
        else Path(tempfile.mkdtemp(prefix=DEFAULT_OUT_ROOT_PREFIX, dir="/tmp"))
    )
    out_root.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "out_root": str(out_root),
        "agenthub_model": str(args.agenthub_model),
        "claude_model": str(args.claude_model),
        "claude_settings_file": str(args.claude_settings_file),
        "claude_base_url": str(args.claude_base_url),
        "claude_debug": str(args.claude_debug),
        "cases": [],
    }
    for case in _selected_cases(list(args.case or [])):
        case_root = out_root / case.name
        case_root.mkdir(parents=True, exist_ok=True)
        case_report = {
            "case": case.name,
            "systems": {
                "agenthub": _run_agenthub_case(
                    case=case,
                    root=case_root / "agenthub",
                    timeout_seconds=max(int(args.timeout_seconds), 1),
                    model=str(args.agenthub_model),
                    reasoning_effort=str(args.agenthub_reasoning_effort),
                ),
                "codex": _run_codex_case(
                    case=case,
                    root=case_root / "codex",
                    timeout_seconds=max(int(args.timeout_seconds), 1),
                    reasoning_effort="high",
                ),
                "claude_code": _run_claude_case(
                    case=case,
                    root=case_root / "claude_code",
                    timeout_seconds=max(int(args.timeout_seconds), 1),
                    model=str(args.claude_model),
                    effort=str(args.claude_effort),
                    settings_file=str(args.claude_settings_file),
                    base_url=str(args.claude_base_url),
                    debug=str(args.claude_debug),
                    include_hook_events=bool(args.claude_include_hook_events),
                    include_partial_messages=bool(args.claude_include_partial_messages),
                ),
            },
        }
        report["cases"].append(case_report)

    report["ended_at"] = _now_iso()
    report["success"] = all(
        system["success"]
        for case_report in report["cases"]
        for system in case_report["systems"].values()
    )
    _write_json(out_root / "report.json", report)
    _write_text(out_root / "summary.md", _render_markdown(report))
    print(json.dumps({"out_root": str(out_root), "success": report["success"]}, ensure_ascii=False))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
