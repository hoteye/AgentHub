from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from cli.scripts.local_web_search_codex_ref_ab_cases import SearchCase
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from local_web_search_codex_ref_ab_cases import SearchCase  # type: ignore[no-redef]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _case_summary(case: SearchCase, local: dict[str, Any], codex: dict[str, Any]) -> dict[str, Any]:
    local_hit = bool(local.get("expected_hit"))
    codex_hit = bool(codex.get("expected_hit"))
    if local_hit and codex_hit:
        classification = "both_hit"
    elif local_hit:
        classification = "local_only"
    elif codex_hit:
        classification = "codex_only"
    else:
        classification = "both_miss"
    return {
        "case_id": case.case_id,
        "query": case.query,
        "expected_domains": list(case.expected_domains),
        "expected_url_substrings": list(case.expected_url_substrings),
        "local": local,
        "codex_ref": codex,
        "parity": {
            "both_hit": local_hit and codex_hit,
            "same_success_state": local_hit == codex_hit,
            "classification": classification,
        },
    }


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Local Web Search vs Codex Ref A/B",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- codex_bin: `{report['codex_bin']}`",
        f"- codex_version: `{report['codex_version']}`",
        f"- model: `{report['model']}`",
        f"- reasoning_effort: `{report['reasoning_effort'] or '-'}`",
        f"- out_dir: `{report['out_dir']}`",
        "",
        "## Summary",
        "",
    ]
    summary = report["summary"]
    for key in ("total", "both_hit", "local_only", "codex_only", "both_miss"):
        lines.append(f"- {key}: {summary[key]}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This compares observable search ability, not identical backend rankings.",
            "- AgentHub local search exposes ranked Bing RSS results; Codex ref exposes web_search actions and final model answers, but not the full provider search result list.",
            "- `both_hit` means both systems found the expected authoritative domain or URL substring.",
            "",
            "## Cases",
            "",
            "| Case | Expected | Local hit | Local top | Codex hit | Codex answer | Classification |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in report["cases"]:
        local = case["local"]
        codex = case["codex_ref"]
        top_results = local.get("top_results") or []
        top_url = str((top_results[0] if top_results else {}).get("url") or "-")
        expected = ", ".join(
            case.get("expected_url_substrings") or case.get("expected_domains") or []
        )
        answer = str(
            codex.get("answer_url")
            or codex.get("answer_domain")
            or codex.get("assistant_text")
            or "-"
        )
        answer = " ".join(answer.split())[:120]
        lines.append(
            "| {case_id} | {expected} | {local_hit} | {top_url} | {codex_hit} | {answer} | {classification} |".format(
                case_id=case["case_id"],
                expected=expected,
                local_hit="yes" if local.get("expected_hit") else "no",
                top_url=top_url,
                codex_hit="yes" if codex.get("expected_hit") else "no",
                answer=answer,
                classification=case["parity"]["classification"],
            )
        )
    lines.append("")
    return "\n".join(lines)
