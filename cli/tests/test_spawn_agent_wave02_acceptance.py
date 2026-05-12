from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "spawn_agent_wave02_acceptance.py"
    )
    spec = importlib.util.spec_from_file_location("spawn_agent_wave02_acceptance", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_dry_run_writes_acceptance_bundle_reports(tmp_path: Path) -> None:
    module = _load_module()

    exit_code = module.main(
        [
            "--dry-run",
            "--out-dir",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == 0
    report = json.loads(
        (tmp_path / "spawn_agent_wave02_acceptance.report.json").read_text(encoding="utf-8")
    )
    assert report["suite"] == "spawn_agent_wave02_live_acceptance"
    assert report["contract_version"] == "wave02_task_c_live_cross_system_bundle_v1"
    assert report["dry_run"] is True
    assert report["task_b_state"] == "in_flight"
    assert report["selected_cases"] == list(module.ALL_CASE_IDS)
    surface_by_lane = {row["lane_id"]: row for row in report["surface_matrix"]}
    assert surface_by_lane["agenthub_codex_openai"]["delegation_tool_surface"] == []
    assert surface_by_lane["agenthub_claude_code"]["delegation_tool_surface"] == [
        "Agent",
        "SendMessage",
    ]
    assert surface_by_lane["agenthub_generic_chat"]["delegation_tool_surface"] == [
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait_agent",
        "agent_workflow",
        "recover_agent",
        "close_agent",
    ]
    assert surface_by_lane["codex_ref"]["delegation_tool_surface"] == [
        "spawn_agent",
        "send_input",
        "resume_agent",
        "wait",
        "close_agent",
    ]
    assert surface_by_lane["claude_code_ref"]["delegation_tool_surface"] == [
        "Agent",
        "SendMessage",
        "TaskStop",
    ]

    case_by_id = {case["case_id"]: case for case in report["cases"]}
    case_d_lanes = {
        lane["lane_id"]: lane for lane in case_by_id["case_d_stop_or_close_surface"]["lanes"]
    }
    assert case_d_lanes["agenthub_claude_code"]["supported"] is False
    assert case_d_lanes["agenthub_claude_code"]["difference_kind"] == "unsupported_capability"
    assert case_d_lanes["agenthub_claude_code"]["outcome_classification"] == {
        "classification": "unsupported",
        "reason": "AgentHub claude_code exposes no TaskStop or close_agent parity surface for this stop/close case.",
        "inferred": False,
    }
    case_e_lanes = {
        lane["lane_id"]: lane for lane in case_by_id["case_e_agenthub_control_plane"]["lanes"]
    }
    assert case_e_lanes["agenthub_generic_chat"]["supported"] is True
    assert case_e_lanes["codex_ref"]["supported"] is False
    assert case_e_lanes["claude_code_ref"]["supported"] is False

    markdown = (tmp_path / "spawn_agent_wave02_acceptance.report.md").read_text(encoding="utf-8")
    assert "## Test Method" in markdown
    assert "## AgentHub Surface Snapshot" in markdown
    assert "## Parity Gaps" in markdown
    assert "### case_b_background_join" in markdown
    assert "command_template" in markdown


def test_selected_cases_filters_known_case_ids() -> None:
    module = _load_module()

    selected = module._selected_cases(
        ["case_e_agenthub_control_plane", "case_a_one_shot_read_only"]
    )

    assert [case.case_id for case in selected] == [
        "case_a_one_shot_read_only",
        "case_e_agenthub_control_plane",
    ]


def test_selected_lanes_and_gap_notes_stay_source_backed() -> None:
    module = _load_module()

    selected_lanes = module._selected_lanes(["claude_code_ref", "agenthub_codex_openai", "missing"])

    assert selected_lanes == ["agenthub_codex_openai", "claude_code_ref"]
    assert module.PARITY_GAP_NOTES[0]["gap_id"] == "codex_multi_wait_ids"
    assert module.PARITY_GAP_NOTES[0]["difference_kind"] == "unsupported_capability"
    assert "ids[]" in module.PARITY_GAP_NOTES[0]["reference_behavior"]
