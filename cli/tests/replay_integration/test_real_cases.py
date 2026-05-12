from __future__ import annotations

from cli.agent_cli.host_platform import detect_host_platform
from cli.replay_integration.real_cases import (
    get_real_case_spec,
    list_live_compatible_case_ids,
    list_real_case_ids,
    load_real_case_cassette,
    load_real_case_turn_logs,
)

def test_real_case_specs_define_explicit_parity_targets() -> None:
    for case_id in list_real_case_ids():
        spec = get_real_case_spec(case_id)
        assert spec.parity_targets
        assert "behavioral_parity_required" in spec.parity_targets

def test_real_case_specs_cover_protocol_path_cases() -> None:
    protocol_required = {
        case_id
        for case_id in list_real_case_ids()
        if "protocol_path_parity_required" in get_real_case_spec(case_id).parity_targets
    }

    assert "tool_followup_pwd_memory" in protocol_required
    assert "error_recovery_after_tool_failure" in protocol_required
    assert "simple_date_time_3turn" in protocol_required

def test_load_real_case_cassette_carries_case_metadata_into_manifest() -> None:
    cassette = load_real_case_cassette("simple_date_time_3turn")

    assert cassette.manifest.case_id == "simple_date_time_3turn"
    assert "protocol_path_parity_required" in cassette.manifest.parity_targets
    assert "provider_native_search" in cassette.manifest.coverage_tags


def test_real_case_specs_include_memory_followup_cases() -> None:
    case_ids = set(list_real_case_ids())
    assert "memory_project_constraint_followup" in case_ids
    assert "memory_user_preference_followup" in case_ids
    assert "memory_reference_link_followup" in case_ids

    project_case = get_real_case_spec("memory_project_constraint_followup")
    user_case = get_real_case_spec("memory_user_preference_followup")
    reference_case = get_real_case_spec("memory_reference_link_followup")
    assert "memory_project_constraint" in project_case.coverage_tags
    assert "memory_user_preference" in user_case.coverage_tags
    assert "memory_reference_link" in reference_case.coverage_tags


def test_real_case_specs_include_phase2_memory_contract_tags() -> None:
    project_case = get_real_case_spec("memory_project_constraint_followup")
    user_case = get_real_case_spec("memory_user_preference_followup")
    reference_case = get_real_case_spec("memory_reference_link_followup")

    assert "phase2_memory_preview_apply_contract" in project_case.coverage_tags
    assert "phase2_memory_ranking_explainability_contract" in project_case.coverage_tags
    assert "phase2_memory_preview_apply_contract" in user_case.coverage_tags
    assert "phase2_memory_user_scope_opt_in_contract" in user_case.coverage_tags
    assert "phase2_memory_ranking_explainability_contract" in user_case.coverage_tags
    assert "phase2_memory_preview_apply_contract" in reference_case.coverage_tags
    assert "phase2_memory_ranking_explainability_contract" in reference_case.coverage_tags

def test_list_live_compatible_case_ids_filters_platform_sensitive_cases() -> None:
    linux = detect_host_platform(system_name="Linux", sys_platform="linux")
    windows = detect_host_platform(system_name="Windows", sys_platform="win32")

    linux_cases = set(list_live_compatible_case_ids(linux))
    windows_cases = set(list_live_compatible_case_ids(windows))

    assert "tool_followup_pwd_memory" in linux_cases
    assert "error_recovery_after_tool_failure" in linux_cases
    assert "tool_followup_pwd_memory" not in windows_cases
    assert "error_recovery_after_tool_failure" not in windows_cases
    assert "simple_date_time_3turn" in windows_cases
    assert "memory_2turn_name" in windows_cases

def test_load_real_case_turn_logs_prefers_host_specific_prefix_when_present(tmp_path) -> None:
    windows = detect_host_platform(system_name="Windows", sys_platform="win32")
    for suffix in ("stdout.jsonl", "stderr.jsonl"):
        for turn_index in (1, 2):
            path = tmp_path / f"20260401_real_pwd_followup_windows_turn{turn_index}.{suffix}"
            path.write_text("{}", encoding="utf-8")

    turn_logs = load_real_case_turn_logs(
        "tool_followup_pwd_memory",
        host_platform=windows,
        prefer_host_variant=True,
        log_root=tmp_path,
    )

    assert all("20260401_real_pwd_followup_windows" in str(item.stdout_path) for item in turn_logs)
    assert all("20260401_real_pwd_followup_windows" in str(item.stderr_path) for item in turn_logs)

def test_list_live_compatible_case_ids_includes_shell_case_when_host_variant_logs_exist(tmp_path) -> None:
    windows = detect_host_platform(system_name="Windows", sys_platform="win32")
    for suffix in ("stdout.jsonl", "stderr.jsonl"):
        for turn_index in (1, 2):
            path = tmp_path / f"20260401_real_error_recovery_windows_turn{turn_index}.{suffix}"
            path.write_text("{}", encoding="utf-8")

    windows_cases = set(list_live_compatible_case_ids(windows, log_root=tmp_path))

    assert "error_recovery_after_tool_failure" in windows_cases
