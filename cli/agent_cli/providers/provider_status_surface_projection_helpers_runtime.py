from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict

from cli.agent_cli.providers import (
    provider_status_surface_normalization_helpers_runtime as normalization_helpers,
)
from cli.agent_cli.providers import provider_status_surface_pure_helpers_runtime as pure_helpers
from cli.agent_cli.providers.availability_models import DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS


def provider_auth_readiness_fields(
    *,
    auth_mode: Any,
    auth_status: Any = "",
    api_key_present: bool = False,
    no_auth_guardrail_pass: Any = False,
    active_provider_ready: Any = False,
) -> Dict[str, Any]:
    mode = pure_helpers._normalized_text(auth_mode)
    status = pure_helpers._normalized_text(auth_status)
    planner_ready = pure_helpers._boolish(active_provider_ready)

    auth_ready = False
    auth_reason = ""

    if mode == "api_key":
        auth_ready = bool(api_key_present) or planner_ready or status == "ready"
        auth_reason = "auth_ready" if auth_ready else "auth_missing_api_key"
    elif mode in {"oauth", "wellknown"}:
        auth_ready = status == "ready"
        if auth_ready:
            auth_reason = "auth_ready"
        elif status in {"", "-", "missing", "logged_out"}:
            auth_reason = "auth_not_ready"
        else:
            auth_reason = f"auth_{status}"
    elif mode == "none":
        auth_ready = pure_helpers._boolish(no_auth_guardrail_pass)
        auth_reason = "auth_ready" if auth_ready else "auth_guardrail_blocked"
    elif not mode or mode == "-":
        auth_ready = planner_ready
        auth_reason = "auth_ready" if auth_ready else "auth_mode_unknown"
    else:
        auth_ready = planner_ready
        auth_reason = "auth_ready" if auth_ready else "auth_mode_unknown"

    return {
        "provider_auth_ready": auth_ready,
        "provider_auth_reason": auth_reason,
    }


def provider_management_surface_fields(
    *,
    auth_mode: Any,
    auth_status: Any = "",
    api_key_present: bool = False,
    no_auth_guardrail_pass: Any = False,
    active_provider_ready: Any = False,
    availability_status: Any = "",
    availability_failure_code: Any = "",
    availability_retry_after_seconds: Any = None,
) -> Dict[str, Any]:
    auth_fields = provider_auth_readiness_fields(
        auth_mode=auth_mode,
        auth_status=auth_status,
        api_key_present=api_key_present,
        no_auth_guardrail_pass=no_auth_guardrail_pass,
        active_provider_ready=active_provider_ready,
    )
    auth_ready = bool(auth_fields["provider_auth_ready"])
    auth_reason = str(auth_fields["provider_auth_reason"] or "").strip() or "auth_unknown"
    availability = pure_helpers._normalized_text(availability_status)
    failure_code = pure_helpers._normalized_text(availability_failure_code)
    retry_after_seconds = availability_retry_after_seconds
    try:
        retry_after_int = int(retry_after_seconds) if retry_after_seconds not in (None, "") else None
    except (TypeError, ValueError):
        retry_after_int = None

    state = "unknown"
    reason = "availability_unknown"
    soft_blocked = False
    hard_unavailable = False

    if not auth_ready:
        state = "auth_blocked"
        reason = auth_reason
        hard_unavailable = True
    elif availability == "available":
        state = "ready"
        reason = "provider_ready"
    elif availability == "unavailable":
        if pure_helpers.failure_code_is_soft(failure_code) or (
            retry_after_int is not None and retry_after_int > 0
        ):
            state = "soft_blocked"
            reason = failure_code or "provider_soft_blocked"
            soft_blocked = True
        else:
            state = "hard_unavailable"
            reason = failure_code or "provider_hard_unavailable"
            hard_unavailable = True
    elif availability == "unknown":
        state = "unknown"
        reason = "availability_unknown"

    base_eligible = auth_ready and state in {"ready", "unknown"}
    base_eligibility_reason = "eligible" if base_eligible else reason

    payload = {
        "state": state,
        "reason": reason,
        "soft_blocked": soft_blocked,
        "hard_unavailable": hard_unavailable,
        "base_eligible": base_eligible,
        "base_eligibility_reason": base_eligibility_reason,
        "auth_ready": auth_ready,
        "auth_reason": auth_reason,
    }
    return {
        **auth_fields,
        "provider_status_state": state,
        "provider_status_reason": reason,
        "provider_soft_blocked": soft_blocked,
        "provider_hard_unavailable": hard_unavailable,
        "provider_base_eligible": base_eligible,
        "provider_base_eligibility_reason": base_eligibility_reason,
        "provider_status_management": payload,
    }


def provider_catalog_entry_status_fields(
    *,
    provider_name: str,
    provider_entry: Any,
    default_model_entry: Any,
    env_mapping: Mapping[str, Any] | None,
    auth_data: Mapping[str, Any] | None,
    auth_path: Path | None,
    availability_registry: Any | None,
    stale_after_seconds: int = DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
) -> Dict[str, Any]:
    normalized = normalization_helpers.normalized_provider_catalog_entry_status_inputs(
        provider_name=provider_name,
        provider_entry=provider_entry,
        default_model_entry=default_model_entry,
        env_mapping=env_mapping,
        auth_data=auth_data,
        auth_path=auth_path,
        availability_registry=availability_registry,
        stale_after_seconds=stale_after_seconds,
    )
    management_fields = provider_management_surface_fields(
        auth_mode=normalized.auth_mode,
        auth_status=normalized.auth_status,
        api_key_present=normalized.provider_api_key_present,
        no_auth_guardrail_pass=normalized.no_auth_guardrail_pass,
        availability_status=normalized.availability_fields.get("availability_status"),
        availability_failure_code=normalized.availability_fields.get("availability_failure_code"),
        availability_retry_after_seconds=normalized.availability_fields.get(
            "availability_retry_after_seconds"
        ),
    )
    return {
        "auth_mode": normalized.auth_mode or "-",
        "auth_status": normalized.auth_status or "-",
        "token_source": normalized.token_source or "-",
        "no_auth_guardrail_reason": normalized.no_auth_guardrail_reason or "-",
        "no_auth_guardrail_pass": normalized.no_auth_guardrail_pass,
        "provider_default_model_id": normalized.provider_default_model_id or "-",
        "provider_api_key_present": normalized.provider_api_key_present,
        **normalized.availability_fields,
        **management_fields,
    }


__all__ = [
    "provider_auth_readiness_fields",
    "provider_catalog_entry_status_fields",
    "provider_management_surface_fields",
]
