from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .benchmark_acceptance_case_helpers import (
    PASS_LEVEL_FIELDS,
    _sorted_rows,
    list_benchmark_case_ids,
    required_surfaces_for_benchmark,
)
from .benchmark_acceptance_projection_helpers import project_live_headless_ab_report_to_row
from .benchmark_acceptance_scoring_helpers import score_acceptance_rows, summarize_acceptance_rows


def _write_text(path: str | Path, text: str) -> str:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(str(text or ""), encoding="utf-8")
    return str(destination)


def _write_json(path: str | Path, payload: Any) -> str:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(destination)


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path!r}")
    return dict(payload)


def _resolve_readout_report_paths(inputs: Sequence[str | Path]) -> list[Path]:
    if not inputs:
        raise ValueError("benchmark acceptance readout requires at least one input path")
    resolved_paths: list[Path] = []
    seen: set[Path] = set()
    for raw_input in list(inputs):
        candidate = Path(raw_input).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(f"benchmark acceptance input does not exist: {raw_input}")
        candidate = candidate.resolve()
        discovered: list[Path] = []
        if candidate.is_file():
            discovered = [candidate]
        else:
            direct_report = candidate / "diff_report.json"
            if direct_report.exists():
                discovered = [direct_report.resolve()]
            else:
                discovered = sorted(item.resolve() for item in candidate.rglob("diff_report.json") if item.is_file())
        if not discovered:
            raise FileNotFoundError(f"benchmark acceptance input has no diff_report.json: {raw_input}")
        for discovered_path in discovered:
            if discovered_path in seen:
                continue
            seen.add(discovered_path)
            resolved_paths.append(discovered_path)
    return resolved_paths


def build_acceptance_readout(
    inputs: Sequence[str | Path],
    *,
    required_pass_level: str = "bundle",
) -> dict[str, Any]:
    normalized_level = str(required_pass_level or "bundle").strip().lower()
    if normalized_level not in PASS_LEVEL_FIELDS:
        raise ValueError(f"unsupported required_pass_level: {required_pass_level!r}")

    report_paths = _resolve_readout_report_paths(inputs)
    rows: list[dict[str, Any]] = []
    case_to_report_path: dict[str, str] = {}
    for report_path in report_paths:
        report_payload = _load_json_object(report_path)
        row = project_live_headless_ab_report_to_row(report_payload)
        case_id = str(row.get("case_id") or "").strip()
        previous_path = case_to_report_path.get(case_id)
        if previous_path:
            raise ValueError(
                f"duplicate benchmark case_id {case_id!r} from {previous_path!r} and {str(report_path)!r}"
            )
        case_to_report_path[case_id] = str(report_path)
        rows.append(row)

    sorted_rows = _sorted_rows(rows)
    summary = summarize_acceptance_rows(sorted_rows, required_surfaces=required_surfaces_for_benchmark())
    case_ids_expected = list_benchmark_case_ids()
    case_ids_covered = [str(item.get("case_id") or "").strip() for item in sorted_rows if str(item.get("case_id") or "").strip()]
    missing_case_ids = [case_id for case_id in case_ids_expected if case_id not in case_ids_covered]
    failed_case_ids = [
        str(item.get("case_id") or "").strip()
        for item in sorted_rows
        if item.get("acceptance_passed") is not True and str(item.get("case_id") or "").strip()
    ]
    summary["case_ids_expected"] = case_ids_expected
    summary["case_ids_covered"] = case_ids_covered
    summary["missing_case_ids"] = missing_case_ids
    summary["failed_case_ids"] = failed_case_ids
    scoring = score_acceptance_rows(
        sorted_rows,
        expected_case_ids=case_ids_expected,
        required_surfaces=required_surfaces_for_benchmark(),
    )

    pass_field = PASS_LEVEL_FIELDS[normalized_level]
    return {
        "required_pass_level": normalized_level,
        "pass_level_satisfied": bool(summary.get(pass_field)),
        "report_paths": [str(path) for path in report_paths],
        "rows": sorted_rows,
        "summary": summary,
        "scoring": scoring,
    }


def _markdown_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def render_acceptance_readout_markdown(report: dict[str, Any]) -> str:
    payload = dict(report or {})
    summary = dict(payload.get("summary") or {})
    scoring = dict(payload.get("scoring") or {})
    overall_scoring = dict(scoring.get("overall") or {})
    rows = _sorted_rows(payload.get("rows") or [])
    lines = [
        "# Benchmark Acceptance Readout",
        "",
        f"- required_pass_level: `{str(payload.get('required_pass_level') or '').strip() or 'bundle'}`",
        f"- pass_level_satisfied: `{_markdown_bool(payload.get('pass_level_satisfied'))}`",
        f"- rows_total: `{summary.get('rows_total', 0)}`",
        f"- rows_passed: `{summary.get('rows_passed', 0)}`",
        f"- contract_passed: `{_markdown_bool(summary.get('contract_passed'))}`",
        f"- bundle_passed: `{_markdown_bool(summary.get('bundle_passed'))}`",
        f"- operator_passed: `{_markdown_bool(summary.get('operator_passed'))}`",
        f"- required_surface_coverage_passed: `{_markdown_bool(summary.get('required_surface_coverage_passed'))}`",
        f"- evidence_pass_level: `{str(summary.get('evidence_pass_level') or '').strip() or '-'}`",
        f"- evidence_pass_levels_covered: `{', '.join(summary.get('evidence_pass_levels_covered') or []) or '-'}`",
        f"- evidence_levels_covered: `{', '.join(summary.get('evidence_levels_covered') or []) or '-'}`",
        f"- case_ids_covered: `{', '.join(summary.get('case_ids_covered') or []) or '-'}`",
        f"- missing_case_ids: `{', '.join(summary.get('missing_case_ids') or []) or '-'}`",
        "",
        "## Scoring",
        "",
        f"- model: `{str(scoring.get('model') or '').strip() or '-'}`",
        f"- score: `{overall_scoring.get('score', 0.0)}`",
        f"- parity_score: `{overall_scoring.get('parity_score', 0.0)}`",
        f"- coverage_ratio: `{overall_scoring.get('coverage_ratio', 0.0)}`",
        f"- accepted_row_ratio: `{overall_scoring.get('accepted_row_ratio', 0.0)}`",
        f"- evidence_pass_level_floor: `{str(overall_scoring.get('evidence_pass_level_floor') or '').strip() or '-'}`",
        "",
        "## Rows",
        "",
    ]
    if rows:
        for row in rows:
            lines.append(
                "- "
                + " | ".join(
                    [
                        f"`{str(row.get('case_id') or '').strip()}`",
                        f"surface=`{str(row.get('surface') or '').strip() or '-'}`",
                        f"evidence_pass_level=`{str(row.get('evidence_pass_level') or '').strip() or '-'}`",
                        f"evidence_level=`{str(row.get('evidence_level') or '').strip() or '-'}`",
                        f"acceptance=`{_markdown_bool(row.get('acceptance_passed'))}`",
                        f"tool=`{str(row.get('tool_name_actual') or '').strip() or '-'}`",
                    ]
                )
            )
    else:
        lines.append("- no rows")
    contract_failures = list(summary.get("contract_failures") or [])
    if contract_failures:
        lines.extend(["", "## Contract Failures", ""])
        for failure in contract_failures:
            lines.append(
                "- "
                + " | ".join(
                    [
                        f"case=`{str(failure.get('case_id') or '').strip() or '-'}`",
                        f"surface=`{str(failure.get('surface') or '').strip() or '-'}`",
                        f"failures=`{', '.join(failure.get('failures') or []) or '-'}`",
                    ]
                )
            )
    failed_case_ids = list(summary.get("failed_case_ids") or [])
    if failed_case_ids:
        lines.extend(["", "## Failed Cases", ""])
        for case_id in failed_case_ids:
            lines.append(f"- `{str(case_id or '').strip()}`")
    row_scores = list(scoring.get("row_scores") or [])
    if row_scores:
        lines.extend(["", "## Lowest Scoring Cases", ""])
        for item in sorted(
            [dict(candidate or {}) for candidate in row_scores if isinstance(candidate, dict)],
            key=lambda candidate: (float(candidate.get("score") or 0.0), str(candidate.get("case_id") or "").strip()),
        )[:3]:
            lines.append(
                "- "
                + " | ".join(
                    [
                        f"case=`{str(item.get('case_id') or '').strip() or '-'}`",
                        f"surface=`{str(item.get('surface') or '').strip() or '-'}`",
                        f"score=`{item.get('score', 0.0)}`",
                        f"parity=`{item.get('parity_score', 0.0)}`",
                        f"acceptance=`{_markdown_bool(item.get('acceptance_passed'))}`",
                    ]
                )
            )
    return "\n".join(lines).strip() + "\n"


def write_acceptance_readout(
    report: dict[str, Any],
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    target_dir = Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(report or {})
    payload["report_path"] = str((target_dir / "report.json").resolve())
    payload["summary_path"] = str((target_dir / "summary.md").resolve())
    _write_text(payload["summary_path"], render_acceptance_readout_markdown(payload))
    _write_json(payload["report_path"], payload)
    return payload
