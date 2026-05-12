from __future__ import annotations

from .real_cases_model_helpers import (
    ROOT,
    _OPERATOR_LIVE_CASE_PACK,
    _RECORDED_CASE_ROOT,
    RealReplayCasePackSpec,
    RealReplayCaseSpec,
)


def _operator_recorded_case_dir(case_id: str) -> str:
    return str((_RECORDED_CASE_ROOT / _OPERATOR_LIVE_CASE_PACK / str(case_id or "").strip()).resolve())


def _operator_live_seed_dir(case_id: str) -> str:
    return str((ROOT / "cli" / "replay_integration" / "live_workspace_seeds" / _OPERATOR_LIVE_CASE_PACK / case_id).resolve())


_REAL_CASE_SPECS = [
    RealReplayCaseSpec(
        case_id="shell_pwd",
        recording_prefix="operator_live_surface_v1/shell_pwd",
        turn_count=1,
        cassette_name="operator-live-shell-pwd",
        coverage_tags=("operator_live_surface", "shell", "benchmark_case_pack"),
        live_supported_host_families=("unix",),
        live_working_cwd_policy="recorded",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
        cassette_dir=_operator_recorded_case_dir("shell_pwd"),
        source_kind="recorded",
        surface_family="shell",
        case_pack=_OPERATOR_LIVE_CASE_PACK,
        source_description="recorded operator/live shell case aligned to benchmark acceptance",
        live_working_cwd="/tmp/agenthub_operator_live/shell_pwd",
        live_reset_workspace=True,
    ),
    RealReplayCaseSpec(
        case_id="write_readme",
        recording_prefix="operator_live_surface_v1/write_readme",
        turn_count=1,
        cassette_name="operator-live-write-readme",
        coverage_tags=("operator_live_surface", "write", "benchmark_case_pack"),
        live_supported_host_families=("unix",),
        live_working_cwd_policy="recorded",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
        cassette_dir=_operator_recorded_case_dir("write_readme"),
        source_kind="recorded",
        surface_family="write",
        case_pack=_OPERATOR_LIVE_CASE_PACK,
        source_description="recorded operator/live write case aligned to benchmark acceptance",
        live_working_cwd="/tmp/agenthub_operator_live/write_readme",
        live_reset_workspace=True,
    ),
    RealReplayCaseSpec(
        case_id="edit_settings",
        recording_prefix="operator_live_surface_v1/edit_settings",
        turn_count=1,
        cassette_name="operator-live-edit-settings",
        coverage_tags=("operator_live_surface", "edit", "benchmark_case_pack"),
        live_supported_host_families=("unix",),
        live_working_cwd_policy="recorded",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
        cassette_dir=_operator_recorded_case_dir("edit_settings"),
        source_kind="recorded",
        surface_family="edit",
        case_pack=_OPERATOR_LIVE_CASE_PACK,
        source_description="recorded operator/live edit case aligned to benchmark acceptance",
        live_working_cwd="/tmp/agenthub_operator_live/edit_settings",
        live_workspace_seed_dir=_operator_live_seed_dir("edit_settings"),
        live_reset_workspace=True,
    ),
    RealReplayCaseSpec(
        case_id="search_weather",
        recording_prefix="operator_live_surface_v1/search_weather",
        turn_count=1,
        cassette_name="operator-live-search-weather",
        coverage_tags=("operator_live_surface", "search", "benchmark_case_pack"),
        live_supported_host_families=("unix",),
        live_working_cwd_policy="recorded",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
        cassette_dir=_operator_recorded_case_dir("search_weather"),
        source_kind="recorded",
        surface_family="search",
        case_pack=_OPERATOR_LIVE_CASE_PACK,
        source_description="recorded operator/live search case aligned to benchmark acceptance",
        live_working_cwd="/tmp/agenthub_operator_live/search_weather",
        live_reset_workspace=True,
    ),
    RealReplayCaseSpec(
        case_id="delegate_probe",
        recording_prefix="operator_live_surface_v1/delegate_probe",
        turn_count=1,
        cassette_name="operator-live-delegate-probe",
        coverage_tags=("operator_live_surface", "agent_delegation", "benchmark_case_pack"),
        live_supported_host_families=("unix",),
        live_working_cwd_policy="recorded",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
        cassette_dir=_operator_recorded_case_dir("delegate_probe"),
        source_kind="recorded",
        surface_family="agent_delegation",
        case_pack=_OPERATOR_LIVE_CASE_PACK,
        source_description="recorded operator/live delegation case aligned to benchmark acceptance",
        live_working_cwd="/tmp/agenthub_operator_live/delegate_probe",
        live_reset_workspace=True,
    ),
    RealReplayCaseSpec(
        case_id="tool_followup_pwd_memory",
        recording_prefix="20260331_real_pwd_followup",
        turn_count=2,
        cassette_name="real-pwd-followup",
        parity_targets=("behavioral_parity_required", "protocol_path_parity_required"),
        coverage_tags=("shell_tool_followup", "tool_loop"),
        live_supported_host_families=("unix",),
        live_supported_host_oses=("linux",),
        recording_prefix_by_host_os={
            "macos": "20260401_real_pwd_followup_macos",
            "windows": "20260401_real_pwd_followup_windows",
        },
    ),
    RealReplayCaseSpec(
        case_id="error_recovery_after_tool_failure",
        recording_prefix="20260331_real_error_recovery",
        turn_count=2,
        cassette_name="real-error-recovery",
        parity_targets=("behavioral_parity_required", "protocol_path_parity_required"),
        coverage_tags=("failed_tool_followup", "tool_loop"),
        live_supported_host_families=("unix",),
        live_supported_host_oses=("linux",),
        recording_prefix_by_host_os={
            "macos": "20260401_real_error_recovery_macos",
            "windows": "20260401_real_error_recovery_windows",
        },
    ),
    RealReplayCaseSpec(
        case_id="memory_2turn_name",
        recording_prefix="20260331_real_memory_2turn_name",
        turn_count=2,
        cassette_name="real-memory-2turn-name",
        coverage_tags=("memory_2turn",),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="reference_person_pronoun",
        recording_prefix="20260331_real_reference_person_pronoun",
        turn_count=2,
        cassette_name="real-reference-person-pronoun",
        coverage_tags=("reference_pronoun",),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="history_compression_summary",
        recording_prefix="20260331_real_history_compression_summary",
        turn_count=3,
        cassette_name="real-history-compression-summary",
        coverage_tags=("history_compression",),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="reference_path_followup",
        recording_prefix="20260331_real_reference_path_followup",
        turn_count=2,
        cassette_name="real-reference-path-followup",
        coverage_tags=("reference_path",),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="reference_variable_value",
        recording_prefix="20260331_real_reference_variable_value",
        turn_count=2,
        cassette_name="real-reference-variable-value",
        coverage_tags=("reference_variable",),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="memory_3turn_facts",
        recording_prefix="20260331_real_memory_3turn_facts",
        turn_count=3,
        cassette_name="real-memory-3turn-facts",
        coverage_tags=("memory_3turn",),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="memory_5turn_profile",
        recording_prefix="20260331_real_memory_5turn_profile",
        turn_count=5,
        cassette_name="real-memory-5turn-profile",
        coverage_tags=("memory_5turn",),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="memory_project_constraint_followup",
        recording_prefix="20260331_real_reference_path_followup",
        turn_count=2,
        cassette_name="real-memory-project-constraint-followup",
        coverage_tags=(
            "memory_project_constraint",
            "memory_project",
            "phase2_memory_preview_apply_contract",
            "phase2_memory_ranking_explainability_contract",
        ),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="memory_user_preference_followup",
        recording_prefix="20260331_real_memory_2turn_name",
        turn_count=2,
        cassette_name="real-memory-user-preference-followup",
        coverage_tags=(
            "memory_user_preference",
            "memory_user",
            "phase2_memory_preview_apply_contract",
            "phase2_memory_user_scope_opt_in_contract",
            "phase2_memory_ranking_explainability_contract",
        ),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="memory_reference_link_followup",
        recording_prefix="20260331_real_reference_variable_value",
        turn_count=2,
        cassette_name="real-memory-reference-link-followup",
        coverage_tags=(
            "memory_reference_link",
            "memory_reference",
            "phase2_memory_preview_apply_contract",
            "phase2_memory_ranking_explainability_contract",
        ),
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
    RealReplayCaseSpec(
        case_id="simple_date_time_3turn",
        recording_prefix="20260331_real_simple_date_time_3turn",
        turn_count=3,
        cassette_name="real-simple-date-time-3turn",
        parity_targets=("behavioral_parity_required", "protocol_path_parity_required"),
        coverage_tags=("provider_native_search", "time_query", "environment_sensitive"),
        frozen_current_dt="2026-03-31T22:27:38+08:00",
        frozen_timezone="Asia/Shanghai",
        live_working_cwd_policy="current",
        live_environment_contract_mode="current",
        live_workspace_contract_mode="current",
    ),
]

REAL_CASES_BY_ID = {item.case_id: item for item in _REAL_CASE_SPECS}

REAL_CASE_PACKS_BY_ID = {
    _OPERATOR_LIVE_CASE_PACK: RealReplayCasePackSpec(
        pack_id=_OPERATOR_LIVE_CASE_PACK,
        title="Operator/live benchmark surface pack",
        current_state="full_operator_live_pack",
        target_state="full_operator_live_pack",
        notes=(
            "This pack is backed by checked-in recorded cassettes plus stable /tmp working "
            "directories so live_headless_ab can produce operator_live evidence without "
            "depending on external reference_baseline logs."
        ),
    )
}


def list_real_case_ids() -> list[str]:
    return [item.case_id for item in _REAL_CASE_SPECS]


def list_operator_live_case_ids() -> list[str]:
    return [item.case_id for item in _REAL_CASE_SPECS if item.case_pack == _OPERATOR_LIVE_CASE_PACK]


def get_real_case_pack_spec(pack_id: str) -> RealReplayCasePackSpec:
    spec = REAL_CASE_PACKS_BY_ID.get(str(pack_id or "").strip())
    if spec is None:
        available = ", ".join(sorted(REAL_CASE_PACKS_BY_ID))
        raise KeyError(f"unknown real replay case pack {pack_id!r}; available: {available}")
    return spec


def get_real_case_spec(case_id: str) -> RealReplayCaseSpec:
    spec = REAL_CASES_BY_ID.get(str(case_id or "").strip())
    if spec is None:
        available = ", ".join(list_real_case_ids())
        raise KeyError(f"unknown real replay case {case_id!r}; available: {available}")
    return spec
