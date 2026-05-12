from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cli.tests.provider_boundary_test_support import assert_provider_home_absent, assert_provider_home_env, provider_home_env


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "web_search_wave02_acceptance.py"
    spec = importlib.util.spec_from_file_location("web_search_wave02_acceptance", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_agenthub_env_omits_provider_home_when_unset(monkeypatch) -> None:
    module = _load_module()
    for key, value in provider_home_env("/tmp/stale-provider-home").items():
        monkeypatch.setenv(key, value)

    env = module._build_agenthub_env(
        module.argparse.Namespace(
            provider="openai",
            model="gpt-5.4",
            reasoning_effort="xhigh",
            provider_home="",
            openai_base_url="",
        )
    )

    assert env["AGENT_CLI_PROVIDER"] == "openai"
    assert env["AGENT_CLI_MODEL"] == "gpt-5.4"
    assert_provider_home_absent(env)


def test_build_agenthub_env_enables_strict_isolation_when_provider_home_explicit() -> None:
    module = _load_module()

    env = module._build_agenthub_env(
        module.argparse.Namespace(
            provider="openai",
            model="gpt-5.4",
            reasoning_effort="xhigh",
            provider_home="/tmp/provider-home",
            openai_base_url="",
        )
    )

    assert_provider_home_env(env, "/tmp/provider-home")


def test_main_dry_run_writes_bundle_reports(tmp_path: Path) -> None:
    module = _load_module()
    exit_code = module.main(
        [
            "--dry-run",
            "--out-dir",
            str(tmp_path),
            "--case",
            "weather_live",
            "--json",
        ]
    )
    assert exit_code == 0
    report = json.loads((tmp_path / "web_search_wave02_acceptance.report.json").read_text(encoding="utf-8"))
    assert report["suite"] == "web_search_wave02_live_acceptance"
    assert report["contract_version"] == "wave03_task_k_parity_contract_v1"
    assert report["dry_run"] is True
    assert report["provider_home_override"] == ""
    assert report["provider_home_source"] == "runtime_default"
    assert [case["case_id"] for case in report["cases"]] == ["weather_live"]
    case = report["cases"][0]
    assert case["comparison_labels"] == ["Codex-comparable", "Claude-comparable", "common-three-way"]
    assert case["request_side_variables"]["reasoning_effort"] == "xhigh"
    assert case["request_side_variables"]["web_search_mode"] == "live"
    assert case["request_side_variables"]["sandbox_mode"] == "danger-full-access"
    assert case["request_side_variables"]["effective_web_search_mode"] == "live"
    assert case["request_side_variables"]["external_web_access"] is True
    systems = {entry["system"]: entry for entry in case["systems"]}
    assert systems["agenthub"]["run"]["skipped"] is True
    assert systems["agenthub"]["run"]["skip_reason"] == "dry_run"
    assert systems["agenthub"]["request_contract"]["tool_surface"]["family_inventory"] == ["web_search(native_if_available)"]
    assert systems["agenthub"]["request_contract"]["effective_web_search_mode"] == "live"
    assert systems["agenthub"]["request_contract"]["external_web_access"] is True
    assert systems["agenthub"]["outcome_classification"]["classification"] == "not_run"
    assert systems["codex"]["run"]["skipped"] is True
    assert systems["codex"]["run"]["skip_reason"] == "dry_run"
    assert systems["codex"]["request_contract"]["tool_surface"]["family_inventory"] == ["web_search"]
    assert systems["codex"]["request_contract"]["effective_web_search_mode"] == "live"
    assert systems["codex"]["request_contract"]["external_web_access"] is True
    assert systems["codex"]["outcome_classification"]["classification"] == "not_run"
    assert systems["claude"]["run"]["skipped"] is True
    assert systems["claude"]["run"]["skip_reason"] == "claude_lane_not_requested"
    assert systems["claude"]["request_contract"]["tool_surface"]["family_inventory"] == [
        "web_search_20250305 via local WebSearchTool wrapper"
    ]
    assert systems["claude"]["outcome_classification"] == {
        "classification": "not_run",
        "reason": "claude_lane_not_requested",
        "inferred": False,
    }
    markdown = (tmp_path / "web_search_wave02_acceptance.report.md").read_text(encoding="utf-8")
    assert "## Test Method" in markdown
    assert "### weather_live" in markdown
    assert "comparison_labels" in markdown
    assert "parity evidence" in markdown


def test_main_dry_run_reports_explicit_provider_home_override(tmp_path: Path) -> None:
    module = _load_module()
    exit_code = module.main(
        [
            "--dry-run",
            "--out-dir",
            str(tmp_path),
            "--case",
            "weather_live",
            "--provider-home",
            str(tmp_path / "provider-home"),
            "--json",
        ]
    )

    assert exit_code == 0
    report = json.loads((tmp_path / "web_search_wave02_acceptance.report.json").read_text(encoding="utf-8"))
    assert report["provider_home"] == str((tmp_path / "provider-home").resolve())
    assert report["provider_home_override"] == str((tmp_path / "provider-home").resolve())
    assert report["provider_home_source"] == "explicit_override"


def test_selected_cases_filters_known_case_ids() -> None:
    module = _load_module()
    selected = module._selected_cases(["known_url_read", "weather_live"])
    assert [case.case_id for case in selected] == ["weather_live", "known_url_read"]


def test_default_openai_base_url_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("AGENTHUB_OPENAI_BASE_URL", "https://env.example/agenthub/v1")
    module = _load_module()

    assert module._default_openai_base_url() == "https://env.example/agenthub/v1"
    args = module._build_parser().parse_args([])
    assert args.openai_base_url == "https://env.example/agenthub/v1"


def test_agenthub_parity_evidence_infers_openai_native_backend_from_web_search_item() -> None:
    module = _load_module()
    args = module._build_parser().parse_args([])

    evidence = module._agenthub_parity_evidence(
        {
            "turn_item_types": ["reasoning", "web_search_call", "agent_message"],
            "response_item_types": ["reasoning", "web_search_call", "message"],
            "web_search_routes": [],
            "provider_planner": "openai_responses",
            "protocol_path": {"kind": "provider_loop", "provider_used": True},
            "has_final_message": True,
            "web_search_actions": [{"action_type": "search", "query": "weather: Beijing, China"}],
            "provider_runtime_state": "ready",
            "availability_status": "available",
        },
        args,
    )

    assert evidence["codex_comparable"]["web_search_call_seen"] is True
    assert evidence["codex_comparable"]["effective_web_search_mode"] == "live"
    assert evidence["codex_comparable"]["external_web_access"] is True
    assert evidence["agenthub"]["effective_backend_id"] == "provider_native_openai_responses_web_search"
    assert evidence["agenthub"]["execution_path"] == "openai_responses_native"
    assert evidence["agenthub"]["turn_search_phase"] == "search_results_received"


def test_effective_turn_web_search_mode_promotes_cached_to_live_under_danger_full_access() -> None:
    module = _load_module()

    assert module._effective_web_search_mode_for_turn("cached", "danger-full-access") == "live"
    assert module._external_web_access_for_turn("cached", "danger-full-access") is True
    assert module._effective_web_search_mode_for_turn("cached", "workspace-write") == "cached"
    assert module._external_web_access_for_turn("cached", "workspace-write") is False


def test_codex_parity_evidence_uses_sandbox_aware_external_web_access_derivation() -> None:
    module = _load_module()
    args = module._build_parser().parse_args(
        [
            "--web-search-mode",
            "cached",
            "--sandbox-mode",
            "danger-full-access",
        ]
    )

    evidence = module._codex_parity_evidence(
        {
            "item_counts": {"web_search_call": 1},
            "assistant_text": "answer",
            "web_search_actions": [{"action_type": "search", "query": "today"}],
        },
        args,
    )

    assert evidence["codex_comparable"]["effective_web_search_mode"] == "live"
    assert evidence["codex_comparable"]["external_web_access"] is True
    assert evidence["codex_comparable"]["external_web_access_observation"] == (
        "derived_from_effective_turn_web_search_mode_via_codex_ref_spec(requested_mode+sandbox_mode)"
    )


def test_outcome_classification_covers_codex_native_and_claude_server_tool_paths() -> None:
    module = _load_module()

    codex = module._outcome_classification(
        "codex",
        run={"skipped": False, "exit_code": 0},
        answer_quality={"assistant_text_present": True},
        parity_evidence={"codex_comparable": {"web_search_call_seen": True}},
    )
    claude = module._outcome_classification(
        "claude",
        run={"skipped": False, "exit_code": 0},
        answer_quality={"assistant_text_present": True},
        parity_evidence={"claude_comparable": {"web_search_requests": 1, "raw_block_markers_available": False}},
    )

    assert codex == {
        "classification": "native_complete",
        "reason": "codex_native_item_seen",
        "inferred": False,
    }
    assert claude == {
        "classification": "server_tool_complete",
        "reason": "usage.server_tool_use.web_search_requests > 0",
        "inferred": True,
    }
