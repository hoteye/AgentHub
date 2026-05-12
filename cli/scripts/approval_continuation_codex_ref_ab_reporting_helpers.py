from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

try:
    from cli.scripts.approval_continuation_codex_ref_ab_model_helpers import _write_text
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from approval_continuation_codex_ref_ab_model_helpers import _write_text  # type: ignore[no-redef]


def _redacted_settings(settings: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in settings.items() if key not in {"auth_path", "api_key"}}


def _write_summary_md(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Approval Continuation codex_ref A/B",
        "",
        f"- created_at: {report.get('created_at')}",
        f"- dry_run: {str(report.get('dry_run')).lower()}",
        f"- provider: {report.get('provider')}",
        f"- agenthub_model: {report.get('agenthub_model')}",
        f"- codex_model: {report.get('codex_model')}",
        f"- reasoning_effort: {report.get('reasoning_effort') or '-'}",
        f"- base_url: {report.get('base_url')}",
        f"- verdict: {report.get('verdict')}",
        f"- pass_count: {report.get('pass_count')}",
        f"- fail_count: {report.get('fail_count')}",
        "",
        "## Cases",
        "",
    ]
    for item in list(report.get("results") or []):
        lines.extend(
            [
                f"### {item.get('case')}",
                "",
                f"- verdict: {item.get('verdict')}",
                f"- reasons: {item.get('reasons') or []}",
                f"- agenthub_workspace: `{dict(item.get('agenthub') or {}).get('workspace')}`",
                f"- codex_workspace: `{dict(item.get('codex_ref') or {}).get('workspace')}`",
                "",
            ]
        )
    _write_text(path, "\n".join(lines).rstrip() + "\n")


def _write_commands_txt(path: Path, results: list[dict[str, Any]]) -> None:
    _write_text(
        path,
        "\n\n".join(
            shlex.join(dict(dict(item.get("agenthub") or {}).get("run") or {}).get("command") or [])
            + "\n"
            + shlex.join(dict(dict(item.get("codex_ref") or {}).get("run") or {}).get("command") or [])
            for item in results
        )
        + "\n",
    )
