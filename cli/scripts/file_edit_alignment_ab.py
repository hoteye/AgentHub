#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from file_write_alignment_ab import (
    DEFAULT_TIMEOUT_SECONDS,
    CaseSpec,
    add_claude_observability_args,
    _run_agenthub_case,
    _run_claude_case,
    _run_codex_case,
    _write_json,
    _write_text,
)


DEFAULT_OUT_ROOT_PREFIX = "agenthub_file_edit_ab_"

DEFAULT_CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        name="unique_edit_single_turn",
        initial_files=(("f.txt", "Status: TODO\n"),),
        prompts=(
            "把 `f.txt` 中唯一出现的 `TODO` 替换成 `DONE`。完成后只回复 `done`。",
        ),
        expected_files=(("f.txt", "Status: DONE"),),
    ),
    CaseSpec(
        name="replace_all_single_turn",
        initial_files=(("f.txt", "TODO\nTODO\n"),),
        prompts=(
            "把 `f.txt` 中所有 `TODO` 都替换成 `DONE`。如果需要，使用 replace_all。完成后只回复 `done`。",
        ),
        expected_files=(("f.txt", "DONE\nDONE"),),
    ),
    CaseSpec(
        name="read_then_edit_multi_turn",
        initial_files=(("f.txt", "Status: TODO\n"),),
        prompts=(
            "读取 `f.txt` 并告诉我当前内容。",
            "现在把 `f.txt` 中的 `TODO` 改成 `DONE`。完成后只回复 `done`。",
        ),
        expected_files=(("f.txt", "Status: DONE"),),
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/file_edit_alignment_ab.py",
        description="Run file_edit alignment acceptance across AgentHub, Codex, and Claude Code.",
    )
    parser.add_argument("--out-root", default="", help="Optional output directory.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--agenthub-model", default="claude-sonnet-4-6")
    parser.add_argument("--claude-model", default="claude-sonnet-4-6")
    parser.add_argument("--claude-effort", default="high")
    parser.add_argument("--agenthub-reasoning-effort", default="high")
    add_claude_observability_args(parser)
    parser.add_argument("--case", action="append", default=[], help="Case name to run. Repeat to restrict the suite.")
    return parser


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _selected_cases(case_filters: list[str]) -> list[CaseSpec]:
    if not case_filters:
        return list(DEFAULT_CASES)
    wanted = {text.strip() for text in case_filters if text.strip()}
    selected = [case for case in DEFAULT_CASES if case.name in wanted]
    if not selected:
        raise SystemExit(f"no matching cases for --case: {sorted(wanted)}")
    return selected


def _render_case_markdown(case_report: dict[str, Any]) -> str:
    case = case_report["case"]
    lines = [f"## {case}", ""]
    for system_name in ("agenthub", "codex", "claude_code"):
        system = case_report["systems"][system_name]
        lines.append(f"### {system_name}")
        lines.append("")
        lines.append(f"- success: {'yes' if system['success'] else 'no'}")
        if system_name == "agenthub":
            lines.append(f"- request_tool_names: {system.get('request_tool_names') or []}")
        if system_name == "claude_code":
            lines.append(f"- system_tools: {system.get('system_tools') or []}")
            lines.append(f"- base_url: {system.get('base_url') or '-'}")
            lines.append(f"- settings_file: {system.get('settings_file') or '-'}")
            lines.append(f"- debug: {system.get('debug') or '-'}")
            lines.append(f"- include_hook_events: {bool(system.get('include_hook_events'))}")
            lines.append(f"- include_partial_messages: {bool(system.get('include_partial_messages'))}")
        lines.append("- turns:")
        for turn in system.get("turns", []):
            if system_name == "agenthub":
                observed = turn.get("provider_tool_names") or turn.get("tool_event_names") or []
            elif system_name == "claude_code":
                observed = turn.get("tool_use_names") or []
            else:
                observed = turn.get("tool_like_items") or []
            lines.append(
                f"  - turn {turn['turn']}: observed={observed} answer={str(turn.get('assistant_text') or '').replace(chr(10), ' ')[:160]}"
            )
        lines.append("- file_results:")
        for item in system.get("file_results", []):
            lines.append(
                f"  - {item['path']}: ok={item['ok']} expected={item['expected']!r} actual={item['actual']!r}"
            )
        lines.append("")
    return "\n".join(lines)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# File Edit Alignment A/B",
        "",
        f"- started_at: {report['started_at']}",
        f"- ended_at: {report['ended_at']}",
        f"- out_root: `{report['out_root']}`",
        f"- agenthub_model: `{report['agenthub_model']}`",
        f"- claude_model: `{report['claude_model']}`",
        f"- claude_settings_file: `{report['claude_settings_file']}`",
        f"- claude_base_url: `{report['claude_base_url']}`",
        f"- claude_debug: `{report['claude_debug']}`",
        "",
        "## Summary",
        "",
        "| case | agenthub | codex | claude_code |",
        "| --- | --- | --- | --- |",
    ]
    for case_report in report["cases"]:
        lines.append(
            "| {case} | {agenthub} | {codex} | {claude} |".format(
                case=case_report["case"],
                agenthub="pass" if case_report["systems"]["agenthub"]["success"] else "fail",
                codex="pass" if case_report["systems"]["codex"]["success"] else "fail",
                claude="pass" if case_report["systems"]["claude_code"]["success"] else "fail",
            )
        )
    lines.append("")
    for case_report in report["cases"]:
        lines.append(_render_case_markdown(case_report))
    return "\n".join(lines).rstrip() + "\n"


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
