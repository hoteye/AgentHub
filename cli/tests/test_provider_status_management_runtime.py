from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.agent_provider_status_runtime import provider_status
from cli.agent_cli.providers.availability_models import AvailabilityRecord, ProbeStatus
from cli.agent_cli.providers.registry import vendor_for_name
from cli.agent_cli.providers.provider_status_management_runtime import (
    provider_management_surface_fields,
    provider_reviewer_gate_fields,
)


class _AvailabilityRegistry:
    def __init__(self, records):
        self._records = records

    def get(self, provider_name: str, model: str):
        return self._records.get((provider_name, model))

    def status(self, provider_name: str, model: str):
        record = self.get(provider_name, model)
        return record.status if record is not None else ProbeStatus.UNKNOWN


def _host_platform():
    return SimpleNamespace(
        family="unix",
        os="linux",
        shell_kind="bash",
        resolve_shell_program=lambda _default: "/bin/bash",
    )


def test_provider_management_surface_marks_missing_api_key_as_auth_blocked() -> None:
    fields = provider_management_surface_fields(
        auth_mode="api_key",
        auth_status="missing",
        api_key_present=False,
        availability_status="unknown",
    )

    assert fields["provider_auth_ready"] is False
    assert fields["provider_auth_reason"] == "auth_missing_api_key"
    assert fields["provider_status_state"] == "auth_blocked"
    assert fields["provider_hard_unavailable"] is True
    assert fields["provider_base_eligible"] is False


def test_provider_management_surface_distinguishes_soft_and_hard_failures() -> None:
    soft = provider_management_surface_fields(
        auth_mode="api_key",
        auth_status="ready",
        api_key_present=True,
        availability_status="unavailable",
        availability_failure_code="rate_limited",
        availability_retry_after_seconds=30,
    )
    hard = provider_management_surface_fields(
        auth_mode="api_key",
        auth_status="ready",
        api_key_present=True,
        availability_status="unavailable",
        availability_failure_code="subscription_expired",
    )

    assert soft["provider_status_state"] == "soft_blocked"
    assert soft["provider_soft_blocked"] is True
    assert soft["provider_base_eligible"] is False
    assert hard["provider_status_state"] == "hard_unavailable"
    assert hard["provider_hard_unavailable"] is True
    assert hard["provider_base_eligible"] is False


def test_provider_management_surface_keeps_unknown_available_for_base_routing() -> None:
    fields = provider_management_surface_fields(
        auth_mode="oauth",
        auth_status="ready",
        api_key_present=True,
        availability_status="unknown",
    )

    assert fields["provider_auth_ready"] is True
    assert fields["provider_status_state"] == "unknown"
    assert fields["provider_base_eligible"] is True


def test_provider_reviewer_gate_fields_prefer_cross_vendor_candidate() -> None:
    gate = provider_reviewer_gate_fields(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "glm",
                "config_provider_name": "glm",
                "provider_base_eligible": False,
                "availability_status": "available",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        vendor_for_name_fn=vendor_for_name,
    )

    assert gate["expert_review_available"] is True
    assert gate["eligible_provider_count"] == 2
    assert gate["reviewer_candidate_count"] == 1
    assert gate["reviewer_cross_vendor_candidate_count"] == 1
    assert gate["preferred_reviewer_candidate_names"] == ["anthropic"]


def test_provider_reviewer_gate_fields_accept_base_eligible_unknown_candidate() -> None:
    gate = provider_reviewer_gate_fields(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": True,
                "availability_status": "unknown",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        vendor_for_name_fn=vendor_for_name,
    )

    assert gate["expert_review_available"] is True
    assert gate["expert_review_unavailable_reason"] == "-"
    assert gate["eligible_provider_count"] == 2
    assert gate["reviewer_candidate_count"] == 1
    assert gate["preferred_reviewer_candidate_names"] == ["anthropic"]


def test_provider_reviewer_gate_fields_respect_feature_disable() -> None:
    gate = provider_reviewer_gate_fields(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        feature_enabled=False,
        feature_source="workspace_config",
        reviewer_capability_policy="capability_matrix_v1",
        reviewer_capability_policy_source="expert_review_reviewer_capability_matrix_v1",
        reasoning_capability_validation="static_matrix",
        vendor_for_name_fn=vendor_for_name,
    )

    assert gate["expert_review_available"] is False
    assert gate["expert_review_unavailable_reason"] == "feature_disabled"
    assert gate["expert_review_feature_enabled"] is False
    assert gate["expert_review_feature_source"] == "workspace_config"
    assert gate["expert_review_required_reasoning_effort"] == "-"
    assert gate["expert_review_reviewer_capability_policy"] == "capability_matrix_v1"
    assert gate["expert_review_reasoning_capability_validation"] == "static_matrix"
    assert gate["reviewer_candidate_count"] == 1


def test_provider_reviewer_gate_fields_still_excludes_unknown_without_base_eligibility() -> None:
    gate = provider_reviewer_gate_fields(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": False,
                "availability_status": "unknown",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        vendor_for_name_fn=vendor_for_name,
    )

    assert gate["expert_review_available"] is False
    assert gate["expert_review_unavailable_reason"] == "insufficient_eligible_providers"
    assert gate["eligible_provider_count"] == 1
    assert gate["reviewer_candidate_count"] == 0


def test_provider_status_surfaces_management_fields_for_active_provider() -> None:
    registry = _AvailabilityRegistry(
        {
            ("openai", "gpt-5.4"): AvailabilityRecord(
                provider_name="openai",
                model="gpt-5.4",
                status=ProbeStatus.UNAVAILABLE,
                failure_code="rate_limited",
                failure_reason="rate limited",
                retry_after=timedelta(seconds=45),
            ),
        }
    )
    summary = {
        "provider_name": "openai",
        "model_key": "gpt_54",
        "planner_kind": "openai_responses",
        "model": "gpt-5.4",
        "base_url": "https://api.openai.com/v1",
        "source": "project_local",
        "config_path": "/tmp/config.toml",
        "auth_path": "/tmp/auth.json",
        "auth_mode": "api_key",
        "auth_status": "ready",
        "no_auth_guardrail_pass": "false",
    }
    agent = SimpleNamespace(
        _provider_paths=SimpleNamespace(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
        ),
        _provider_availability_registry=registry,
        _planner=SimpleNamespace(public_summary=lambda: summary),
        _planner_error=None,
        _planner_runtime_error=None,
        _planner_runtime_error_diagnostic_lines=lambda: [],
        _session_provider_env_overrides={},
        host_platform=_host_platform(),
    )

    status = provider_status(
        agent,
        session_route_overrides_fn=lambda _agent: {},
        session_delegate_overrides_fn=lambda _agent: {},
        resolution_status_label_fn=lambda payload: str(payload or ""),
    )

    assert status["availability_status"] == "unavailable"
    assert status["provider_auth_ready"] is True
    assert status["provider_status_state"] == "soft_blocked"
    assert status["provider_status_reason"] == "rate_limited"
    assert status["provider_soft_blocked"] is True
    assert status["provider_base_eligible"] is False
