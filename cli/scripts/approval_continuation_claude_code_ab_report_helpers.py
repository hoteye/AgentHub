from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import _write_text
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_codex_ref_ab_model_helpers import (
        _write_text,  # type: ignore[no-redef]
    )


def _write_summary_md(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Approval Continuation Claude Code A/B",
        "",
        f"- Created: {report.get('created_at')}",
        f"- Verdict: {report.get('verdict')}",
        f"- AgentHub: {report.get('agenthub_provider')} / {report.get('agenthub_model')}",
        f"- Claude Code model: {report.get('claude_model')}",
        f"- Dry run: {report.get('dry_run')}",
        "",
        "| Case | Verdict | Reasons |",
        "| --- | --- | --- |",
    ]
    for item in list(report.get("results") or []):
        reasons = ", ".join(str(reason) for reason in list(item.get("reasons") or []))
        lines.append(f"| {item.get('case')} | {item.get('verdict')} | {reasons or '-'} |")
    _write_text(path, "\n".join(lines) + "\n")
