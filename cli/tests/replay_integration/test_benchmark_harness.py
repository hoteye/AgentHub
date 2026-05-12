from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from cli.replay_integration.benchmark_acceptance import get_benchmark_case_spec, list_benchmark_case_specs
from cli.replay_integration.benchmark_harness import (
    build_benchmark_harness_report,
    main as benchmark_harness_main,
    write_benchmark_harness_report,
)


def _benchmark_cases():
    return list_benchmark_case_specs()


def _payload_for_case(case) -> dict[str, Any]:
    return {
        "assistant_text": f"completed {case.case_id} with {case.expected_result_fragment}",
        "response_items": [
            {
                "type": "function_call",
                "call_id": f"{case.case_id}_call",
                "name": case.expected_tool_name,
                "arguments": json.dumps(dict(case.expected_argument_subset), ensure_ascii=False),
            },
            {
                "type": "function_call_output",
                "call_id": f"{case.case_id}_call",
                "output": case.expected_result_fragment,
                "success": True,
            },
        ],
        "tool_events": [
            {
                "name": case.expected_tool_name,
                "ok": True,
                "payload": {
                    "time_to_first_event_ms": 120,
                    "time_to_first_tool_ms": 180,
                },
            }
        ],
        "status": {
            "time_to_first_event_ms": 120,
            "time_to_first_tool_ms": 180,
        },
    }


def _write_live_headless_ab_case_artifacts(
    base_dir: Path,
    *,
    case_id: str,
    case_source_kind: str = "fixture_live",
) -> Path:
    case = get_benchmark_case_spec(case_id)
    case_dir = base_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    live_results_path = case_dir / "agenthub.live.json"
    diff_report_path = case_dir / "diff_report.json"
    summary_path = case_dir / "summary.md"
    live_results_path.write_text(
        json.dumps([_payload_for_case(case)], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    diff_report = {
        "case_id": case.case_id,
        "case_source_kind": case_source_kind,
        "surface_family": case.surface,
        "case_pack": "operator_live_surface_v1" if case_source_kind == "fixture_live" else "",
        "behavioral_passed": True,
        "protocol_path_passed": True,
        "mismatch_count": 0,
        "recording_variant_source": "fixture" if case_source_kind == "fixture_live" else "host",
        "live_results_path": str(live_results_path),
        "diff_report_path": str(diff_report_path),
        "summary_path": str(summary_path),
    }
    diff_report_path.write_text(json.dumps(diff_report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(f"# {case.case_id}\n", encoding="utf-8")
    return case_dir


def test_build_benchmark_harness_report_adds_scoring_to_readout(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id, case_source_kind="fixture_live")

    report = build_benchmark_harness_report([bundle_root], required_pass_level="bundle")

    assert report["required_pass_level"] == "bundle"
    assert report["pass_level_satisfied"] is True
    assert report["summary"]["bundle_passed"] is True
    assert report["scoring"]["model"] == "native_interaction_parity_v1"
    assert report["scoring"]["overall"]["score"] == 85.0
    assert report["scoring"]["overall"]["max_score"] == 100.0
    assert report["scoring"]["overall"]["score_ratio"] == 0.85
    assert report["scoring"]["overall"]["parity_score"] == 100.0
    assert report["scoring"]["overall"]["parity_score_ratio"] == 1.0
    assert report["scoring"]["overall"]["coverage_ratio"] == 1.0
    assert report["scoring"]["overall"]["evidence_pass_level_floor"] == "bundle"
    assert report["scoring"]["overall"]["expected_case_count"] == 5
    assert report["scoring"]["overall"]["rows_scored"] == 5
    assert report["scoring"]["overall"]["missing_case_ids"] == []
    assert report["scoring"]["overall"]["missing_surfaces"] == []


def test_write_benchmark_harness_report_writes_combined_report_and_summary(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id, case_source_kind="fixture_live")
    report = build_benchmark_harness_report([bundle_root], required_pass_level="bundle")

    written = write_benchmark_harness_report(report, out_dir=tmp_path / "out")

    assert Path(written["report_path"]).exists()
    assert Path(written["summary_path"]).exists()
    persisted = json.loads(Path(written["report_path"]).read_text(encoding="utf-8"))
    assert persisted["scoring"]["overall"]["score"] == 85.0
    assert persisted["scoring"]["overall"]["parity_score"] == 100.0
    markdown = Path(written["summary_path"]).read_text(encoding="utf-8")
    assert "# Benchmark Acceptance Readout" in markdown
    assert "## Harness Summary" in markdown
    assert "model: `native_interaction_parity_v1`" in markdown
    assert "score: `85.0`" in markdown
    assert "parity_score: `100.0`" in markdown


def test_benchmark_harness_cli_accepts_explicit_diff_report_inputs(tmp_path) -> None:
    diff_reports: list[str] = []
    for case in _benchmark_cases():
        case_dir = _write_live_headless_ab_case_artifacts(
            tmp_path / "cases",
            case_id=case.case_id,
            case_source_kind="recorded",
        )
        diff_reports.append(str(case_dir / "diff_report.json"))
    stdout = io.StringIO()
    stderr = io.StringIO()
    argv: list[str] = ["--out-dir", str(tmp_path / "out")]
    for diff_report in diff_reports:
        argv.extend(["--input", diff_report])

    code = benchmark_harness_main(argv, stdout=stdout, stderr=stderr)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert stderr.getvalue() == ""
    assert payload["scoring"]["overall"]["score"] == 100.0
    assert payload["scoring"]["overall"]["evidence_pass_level_floor"] == "operator"
    assert payload["summary"]["operator_passed"] is True
    assert Path(payload["report_path"]).exists()
    assert Path(payload["summary_path"]).exists()


def test_benchmark_harness_cli_returns_three_when_required_level_not_met(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id, case_source_kind="fixture_live")
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = benchmark_harness_main(
        ["--input", str(bundle_root), "--require-pass-level", "operator"],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 3
    assert stderr.getvalue() == ""
    assert payload["pass_level_satisfied"] is False
    assert payload["scoring"]["overall"]["score"] == 85.0
    assert payload["scoring"]["overall"]["evidence_pass_level_floor"] == "bundle"
