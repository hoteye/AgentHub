from __future__ import annotations

from typing import Any


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
        if system_name == "codex":
            lines.append(
                f"- configured_model/provider: {system.get('configured_model') or '-'} / {system.get('configured_provider') or '-'}"
            )
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
        "# File Write Alignment A/B",
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
