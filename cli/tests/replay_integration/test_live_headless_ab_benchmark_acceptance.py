from __future__ import annotations

import json
import io
from pathlib import Path
from typing import Any

from cli.replay_integration.benchmark_acceptance import (
    build_acceptance_row,
    build_acceptance_readout,
    get_benchmark_case_spec,
    list_benchmark_case_specs,
    main as benchmark_acceptance_main,
    project_live_headless_ab_report_to_row,
    required_surfaces_for_benchmark,
    render_acceptance_readout_markdown,
    score_acceptance_row,
    score_acceptance_rows,
    summarize_acceptance_rows,
    write_acceptance_readout,
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


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_acceptance_rows(
        rows,
        required_surfaces=required_surfaces_for_benchmark(),
    )


def _score_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return score_acceptance_rows(
        rows,
        expected_case_ids=[case.case_id for case in _benchmark_cases()],
        required_surfaces=required_surfaces_for_benchmark(),
    )


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


def test_benchmark_bundle_covers_required_tool_surfaces() -> None:
    surfaces = {case.surface for case in _benchmark_cases()}
    assert surfaces == {"shell", "write", "edit", "search", "agent_delegation"}


def test_benchmark_row_contract_contains_required_acceptance_fields() -> None:
    case = _benchmark_cases()[0]
    row = build_acceptance_row(case.case_id, _payload_for_case(case))

    assert row == {
        "case_id": "shell_pwd",
        "surface": "shell",
        "tool_name_expected": "exec_command",
        "tool_name_actual": "exec_command",
        "tool_name_correct": True,
        "arguments_correct": True,
        "result_usable": True,
        "time_to_first_event_ms": 120,
        "time_to_first_tool_ms": 180,
        "evidence_level": "synthetic",
        "evidence_pass_level": "contract",
        "acceptance_passed": True,
    }


def test_score_acceptance_row_returns_quantitative_native_parity_breakdown() -> None:
    case = _benchmark_cases()[0]
    row = build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="operator_live")

    scored = score_acceptance_row(row)

    assert scored["case_id"] == "shell_pwd"
    assert scored["surface"] == "shell"
    assert scored["acceptance_passed"] is True
    assert scored["parity_score"] == 100.0
    assert scored["native_parity_score"] == 100.0
    assert scored["score"] == 100.0
    assert scored["confidence_weight"] == 1.0
    assert scored["contract_failures"] == []
    assert scored["component_scores"]["tool_name_correct"]["score"] == 35.0
    assert scored["component_scores"]["arguments_correct"]["score"] == 20.0
    assert scored["component_scores"]["result_usable"]["score"] == 25.0
    assert scored["component_scores"]["time_to_first_event_ms"]["score"] == 10.0
    assert scored["component_scores"]["time_to_first_tool_ms"]["score"] == 10.0


def test_score_acceptance_row_preserves_partial_credit_when_contract_fields_are_missing() -> None:
    case = _benchmark_cases()[0]
    row = build_acceptance_row(case.case_id, _payload_for_case(case))
    del row["time_to_first_tool_ms"]

    scored = score_acceptance_row(row)

    assert scored["acceptance_passed"] is True
    assert scored["contract_failures"] == ["missing:time_to_first_tool_ms"]
    assert scored["parity_score"] == 90.0
    assert scored["native_parity_score"] == 63.0
    assert scored["component_scores"]["time_to_first_tool_ms"]["score"] == 0.0


def test_benchmark_summary_fails_when_any_required_axis_regresses() -> None:
    rows = [build_acceptance_row(case.case_id, _payload_for_case(case)) for case in _benchmark_cases()]
    rows[2]["arguments_correct"] = False
    rows[2]["acceptance_passed"] = False

    summary = _summarize_rows(rows)

    assert summary["rows_total"] == 5
    assert summary["rows_passed"] == 4
    assert summary["contract_passed"] is True
    assert summary["required_surface_coverage_passed"] is True
    assert summary["required_surfaces"] == ["agent_delegation", "edit", "search", "shell", "write"]
    assert summary["surfaces_covered"] == ["agent_delegation", "edit", "search", "shell", "write"]
    assert summary["evidence_pass_level"] == "contract"
    assert summary["evidence_pass_levels_covered"] == ["contract"]
    assert summary["evidence_levels_covered"] == ["synthetic"]
    assert summary["bundle_passed"] is False
    assert summary["operator_passed"] is False


def test_benchmark_summary_distinguishes_bundle_pass_from_operator_pass() -> None:
    rows = [
        build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="fixture_live")
        for case in _benchmark_cases()
    ]

    summary = _summarize_rows(rows)

    assert summary["contract_passed"] is True
    assert summary["bundle_passed"] is True
    assert summary["operator_passed"] is False
    assert summary["evidence_pass_level"] == "bundle"
    assert summary["evidence_pass_levels_covered"] == ["bundle"]
    assert summary["evidence_levels_covered"] == ["fixture_live"]


def test_benchmark_summary_requires_operator_live_evidence_for_operator_pass() -> None:
    rows = [
        build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="operator_live")
        for case in _benchmark_cases()
    ]

    summary = _summarize_rows(rows)

    assert summary["contract_passed"] is True
    assert summary["bundle_passed"] is True
    assert summary["operator_passed"] is True
    assert summary["evidence_pass_level"] == "operator"
    assert summary["evidence_pass_levels_covered"] == ["operator"]
    assert summary["evidence_levels_covered"] == ["operator_live"]


def test_benchmark_summary_uses_bundle_floor_when_fixture_and_operator_evidence_mix() -> None:
    rows = [
        build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="operator_live")
        for case in _benchmark_cases()[:2]
    ]
    rows.extend(
        build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="fixture_live")
        for case in _benchmark_cases()[2:]
    )

    summary = _summarize_rows(rows)

    assert summary["contract_passed"] is True
    assert summary["bundle_passed"] is True
    assert summary["operator_passed"] is False
    assert summary["evidence_pass_level"] == "bundle"
    assert summary["evidence_pass_levels_covered"] == ["bundle", "operator"]
    assert summary["evidence_levels_covered"] == ["fixture_live", "operator_live"]


def test_score_acceptance_rows_exposes_row_surface_and_overall_contract() -> None:
    rows = [
        build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="fixture_live")
        for case in _benchmark_cases()
    ]

    scoring = _score_rows(rows)

    assert scoring["model"] == "native_interaction_parity_v1"
    assert len(scoring["row_scores"]) == 5
    assert len(scoring["surface_scores"]) == 5
    assert scoring["overall"]["native_parity_score"] == 85.0
    assert scoring["overall"]["parity_score"] == 100.0
    assert scoring["overall"]["coverage_ratio"] == 1.0
    assert scoring["overall"]["case_coverage_ratio"] == 1.0
    assert scoring["overall"]["surface_coverage_ratio"] == 1.0
    assert scoring["overall"]["accepted_row_ratio"] == 1.0
    assert scoring["overall"]["contract_valid_row_ratio"] == 1.0
    assert scoring["overall"]["evidence_pass_level_floor"] == "bundle"
    assert scoring["overall"]["component_scores"]["time_to_first_tool_ms"]["score_ratio"] == 1.0
    assert scoring["surface_scores"][0]["surface"] == "agent_delegation"
    assert scoring["surface_scores"][0]["native_parity_score"] == 85.0
    assert scoring["surface_scores"][0]["case_coverage_ratio"] == 1.0


def test_score_acceptance_rows_penalizes_missing_surface_coverage_and_lower_evidence() -> None:
    rows = [
        build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="operator_live")
        for case in _benchmark_cases()[:2]
    ]
    rows.extend(
        build_acceptance_row(case.case_id, _payload_for_case(case), evidence_level="fixture_live")
        for case in _benchmark_cases()[2:4]
    )

    scoring = _score_rows(rows)
    missing_surface = next(item for item in scoring["surface_scores"] if item["surface"] == "agent_delegation")

    assert scoring["overall"]["native_parity_score"] == 74.0
    assert scoring["overall"]["coverage_ratio"] == 0.8
    assert scoring["overall"]["case_coverage_ratio"] == 0.8
    assert scoring["overall"]["surface_coverage_ratio"] == 0.8
    assert scoring["overall"]["evidence_weight_average"] == 0.925
    assert scoring["overall"]["evidence_weight_floor"] == 0.85
    assert scoring["overall"]["evidence_pass_level_floor"] == "bundle"
    assert scoring["overall"]["missing_case_ids"] == ["delegate_probe"]
    assert scoring["overall"]["missing_surfaces"] == ["agent_delegation"]
    assert missing_surface["rows_scored"] == 0
    assert missing_surface["native_parity_score"] == 0.0
    assert missing_surface["missing_case_ids"] == ["delegate_probe"]


def test_benchmark_summary_reports_contract_failures_explicitly() -> None:
    case = _benchmark_cases()[0]
    rows = [build_acceptance_row(case.case_id, _payload_for_case(case))]
    del rows[0]["time_to_first_tool_ms"]

    summary = _summarize_rows(rows)

    assert summary["contract_passed"] is False
    assert summary["bundle_passed"] is False
    assert summary["operator_passed"] is False
    assert summary["contract_failures"] == [
        {
            "case_id": "shell_pwd",
            "surface": "shell",
            "failures": ["missing:time_to_first_tool_ms"],
        }
    ]


def test_build_acceptance_row_normalizes_custom_tool_call_apply_patch_input() -> None:
    case = get_benchmark_case_spec("write_readme")
    patch_text = "*** Begin Patch\n*** Add File: README.md\n+hello\n*** End Patch"
    payload = {
        "assistant_text": "README.md",
        "response_items": [
            {
                "type": "custom_tool_call",
                "call_id": "call_write",
                "name": "apply_patch",
                "input": patch_text,
            },
            {
                "type": "function_call_output",
                "call_id": "call_write",
                "output": "README.md",
                "success": True,
            },
        ],
        "tool_events": [
            {
                "name": "apply_patch",
                "ok": True,
                "payload": {
                    "time_to_first_event_ms": 120,
                    "time_to_first_tool_ms": 180,
                },
            }
        ],
    }

    row = build_acceptance_row(case.case_id, payload, evidence_level="fixture_live")

    assert row["tool_name_actual"] == "apply_patch"
    assert row["arguments_correct"] is True
    assert row["result_usable"] is True
    assert row["evidence_pass_level"] == "bundle"
    assert row["acceptance_passed"] is True


def test_build_acceptance_row_reads_structured_write_arguments_from_function_call_output() -> None:
    case = get_benchmark_case_spec("write_readme")
    payload = {
        "assistant_text": "README.md",
        "response_items": [
            {
                "type": "custom_tool_call",
                "call_id": "call_write",
                "name": "apply_patch",
                "input": "",
            },
            {
                "type": "function_call_output",
                "call_id": "call_write",
                "output": json.dumps(
                    {
                        "function_call_name": "Write",
                        "function_call_arguments": {
                            "file_path": "/tmp/agenthub_operator_live/write_readme/README.md",
                            "content": "hello",
                        },
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
        ],
        "status": {
            "time_to_first_event_ms": 120,
            "time_to_first_tool_ms": 180,
        },
    }

    row = build_acceptance_row(case.case_id, payload, evidence_level="operator_live")

    assert row["tool_name_actual"] == "apply_patch"
    assert row["arguments_correct"] is True
    assert row["result_usable"] is True
    assert row["acceptance_passed"] is True


def test_build_acceptance_row_prefers_expected_tool_when_read_file_precedes_edit() -> None:
    case = get_benchmark_case_spec("edit_settings")
    payload = {
        "assistant_text": "settings.toml",
        "response_items": [
            {
                "type": "function_call",
                "call_id": "call_read",
                "name": "read_file",
                "arguments": json.dumps(
                    {"file_path": "/tmp/agenthub_operator_live/edit_settings/settings.toml"},
                    ensure_ascii=False,
                ),
            },
            {
                "type": "custom_tool_call",
                "call_id": "call_edit",
                "name": "apply_patch",
                "input": "",
            },
            {
                "type": "function_call_output",
                "call_id": "call_read",
                "output": 'L1: mode = "dev"',
                "success": True,
            },
            {
                "type": "function_call_output",
                "call_id": "call_edit",
                "output": json.dumps(
                    {
                        "function_call_name": "Edit",
                        "function_call_arguments": {
                            "file_path": "/tmp/agenthub_operator_live/edit_settings/settings.toml",
                            "old_string": 'mode = "dev"',
                            "new_string": 'mode = "prod"',
                        },
                    },
                    ensure_ascii=False,
                ),
                "success": True,
            },
        ],
        "status": {
            "time_to_first_event_ms": 120,
            "time_to_first_tool_ms": 180,
        },
        "tool_events": [
            {"name": "read_file", "ok": True, "payload": {}},
            {"name": "apply_patch", "ok": True, "payload": {}},
        ],
    }

    row = build_acceptance_row(case.case_id, payload, evidence_level="operator_live")

    assert row["tool_name_actual"] == "apply_patch"
    assert row["arguments_correct"] is True
    assert row["result_usable"] is True
    assert row["acceptance_passed"] is True


def test_project_live_headless_ab_report_to_row_uses_fixture_case_metadata(tmp_path) -> None:
    case = get_benchmark_case_spec("search_weather")
    live_results_path = tmp_path / "agenthub.live.json"
    live_results_path.write_text(
        json.dumps([_payload_for_case(case)], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "case_id": case.case_id,
        "case_source_kind": "fixture_live",
        "surface_family": case.surface,
        "case_pack": "operator_live_surface_v1",
        "behavioral_passed": True,
        "protocol_path_passed": True,
        "mismatch_count": 0,
        "recording_variant_source": "fixture",
        "live_results_path": str(live_results_path),
        "diff_report_path": str(tmp_path / "diff_report.json"),
        "summary_path": str(tmp_path / "summary.md"),
    }

    row = project_live_headless_ab_report_to_row(report)

    assert row["case_id"] == "search_weather"
    assert row["surface"] == "search"
    assert row["evidence_level"] == "fixture_live"
    assert row["evidence_pass_level"] == "bundle"
    assert row["case_source_kind"] == "fixture_live"
    assert row["surface_family"] == "search"
    assert row["case_pack"] == "operator_live_surface_v1"
    assert row["recording_variant_source"] == "fixture"
    assert row["protocol_path_passed"] is True
    assert row["acceptance_passed"] is True


def test_project_live_headless_ab_report_to_row_maps_recorded_source_to_operator_live(tmp_path) -> None:
    case = get_benchmark_case_spec("shell_pwd")
    live_results = [_payload_for_case(case)]
    live_results_path = tmp_path / "agenthub.live.json"
    live_results_path.write_text(json.dumps(live_results, ensure_ascii=False), encoding="utf-8")
    report = {
        "case_id": case.case_id,
        "case_source_kind": "recorded",
        "surface_family": case.surface,
        "case_pack": "",
        "behavioral_passed": True,
        "protocol_path_passed": True,
        "mismatch_count": 0,
        "live_results_path": str(live_results_path),
        "diff_report_path": str(tmp_path / "diff_report.json"),
        "summary_path": str(tmp_path / "summary.md"),
    }

    row = project_live_headless_ab_report_to_row(report)

    assert row["evidence_level"] == "operator_live"
    assert row["evidence_pass_level"] == "operator"
    assert row["tool_name_actual"] == "exec_command"
    assert row["arguments_correct"] is True
    assert row["result_usable"] is True
    assert row["acceptance_passed"] is True
    assert row["live_results_path"] == str(Path(live_results_path))


def test_build_acceptance_readout_aggregates_recursive_fixture_bundle(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id, case_source_kind="fixture_live")

    report = build_acceptance_readout([bundle_root], required_pass_level="bundle")

    assert report["required_pass_level"] == "bundle"
    assert report["pass_level_satisfied"] is True
    assert [row["case_id"] for row in report["rows"]] == [case.case_id for case in _benchmark_cases()]
    assert report["summary"]["evidence_pass_level"] == "bundle"
    assert report["summary"]["evidence_pass_levels_covered"] == ["bundle"]
    assert report["summary"]["evidence_levels_covered"] == ["fixture_live"]
    assert report["summary"]["bundle_passed"] is True
    assert report["summary"]["operator_passed"] is False
    assert report["summary"]["case_ids_covered"] == [case.case_id for case in _benchmark_cases()]
    assert report["summary"]["missing_case_ids"] == []
    assert report["scoring"]["overall"]["native_parity_score"] == 85.0
    assert len(report["scoring"]["row_scores"]) == 5
    assert len(report["scoring"]["surface_scores"]) == 5


def test_build_acceptance_readout_attaches_quantitative_scoring(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id, case_source_kind="fixture_live")

    report = build_acceptance_readout([bundle_root], required_pass_level="bundle")

    assert report["scoring"]["model"] == "native_interaction_parity_v1"
    assert report["scoring"]["overall"]["score"] == 85.0
    assert report["scoring"]["overall"]["parity_score"] == 100.0
    assert report["scoring"]["overall"]["coverage_ratio"] == 1.0
    assert report["scoring"]["overall"]["accepted_row_ratio"] == 1.0
    assert report["scoring"]["overall"]["evidence_pass_level_floor"] == "bundle"
    assert report["scoring"]["overall"]["component_scores"]["tool_name_correct"]["score"] == 35.0
    assert report["scoring"]["row_scores"][0]["confidence_weight"] == 0.85


def test_build_acceptance_readout_rejects_duplicate_case_ids(tmp_path) -> None:
    input_a = _write_live_headless_ab_case_artifacts(tmp_path / "a", case_id="shell_pwd")
    input_b = _write_live_headless_ab_case_artifacts(tmp_path / "b", case_id="shell_pwd")

    try:
        build_acceptance_readout([input_a, input_b])
    except ValueError as exc:
        assert "duplicate benchmark case_id" in str(exc)
    else:
        raise AssertionError("expected duplicate case_id error")


def test_write_acceptance_readout_writes_report_and_summary(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id)
    report = build_acceptance_readout([bundle_root])

    written = write_acceptance_readout(report, out_dir=tmp_path / "out")

    assert Path(written["report_path"]).exists()
    assert Path(written["summary_path"]).exists()
    persisted = json.loads(Path(written["report_path"]).read_text(encoding="utf-8"))
    assert persisted["required_pass_level"] == "bundle"
    assert persisted["summary"]["evidence_pass_level"] == "bundle"
    assert persisted["summary"]["bundle_passed"] is True
    assert persisted["scoring"]["overall"]["native_parity_score"] == 85.0
    assert "summary_path" in persisted
    markdown = Path(written["summary_path"]).read_text(encoding="utf-8")
    assert "# Benchmark Acceptance Readout" in markdown
    assert "evidence_pass_level: `bundle`" in markdown
    assert "bundle_passed: `true`" in markdown


def test_render_acceptance_readout_markdown_lists_rows_and_missing_cases(tmp_path) -> None:
    bundle_root = tmp_path / "partial"
    _write_live_headless_ab_case_artifacts(bundle_root, case_id="shell_pwd")
    report = build_acceptance_readout([bundle_root], required_pass_level="bundle")

    rendered = render_acceptance_readout_markdown(report)

    assert "## Scoring" in rendered
    assert "model: `native_interaction_parity_v1`" in rendered
    assert "parity_score: `100.0`" in rendered
    assert "evidence_pass_level: `bundle`" in rendered
    assert "evidence_levels_covered: `fixture_live`" in rendered
    assert "case_ids_covered: `shell_pwd`" in rendered
    assert "missing_case_ids:" in rendered
    assert "`shell_pwd` | surface=`shell` | evidence_pass_level=`bundle` | evidence_level=`fixture_live`" in rendered


def test_benchmark_acceptance_cli_writes_bundle_readout_and_returns_zero(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id, case_source_kind="fixture_live")
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = benchmark_acceptance_main(
        ["--input", str(bundle_root), "--out-dir", str(tmp_path / "out"), "--require-pass-level", "bundle"],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert stderr.getvalue() == ""
    assert payload["pass_level_satisfied"] is True
    assert payload["summary"]["evidence_pass_level"] == "bundle"
    assert payload["summary"]["bundle_passed"] is True
    assert payload["scoring"]["overall"]["native_parity_score"] == 85.0
    assert Path(payload["report_path"]).exists()
    assert Path(payload["summary_path"]).exists()


def test_benchmark_acceptance_cli_returns_three_when_operator_level_required(tmp_path) -> None:
    bundle_root = tmp_path / "bundle"
    for case in _benchmark_cases():
        _write_live_headless_ab_case_artifacts(bundle_root, case_id=case.case_id, case_source_kind="fixture_live")
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = benchmark_acceptance_main(
        ["--input", str(bundle_root), "--require-pass-level", "operator"],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 3
    assert stderr.getvalue() == ""
    assert payload["summary"]["evidence_pass_level"] == "bundle"
    assert payload["summary"]["bundle_passed"] is True
    assert payload["summary"]["operator_passed"] is False
    assert payload["scoring"]["overall"]["native_parity_score"] == 85.0
    assert payload["pass_level_satisfied"] is False
