from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from cli.agent_cli import agent_status_projection, provider_source_semantics_runtime
from cli.agent_cli.agent_provider_resolution import public_provider_name as _public_provider_name
from cli.agent_cli.provider_persistence_paths_runtime import (
    load_user_provider_selection,
    resolve_user_provider_auth_path,
    resolve_user_provider_config_path,
)
from cli.agent_cli.providers import availability_feature_config_runtime
from cli.agent_cli.providers.availability_projection import (
    append_availability_surface,
    get_availability_registry,
)
from cli.agent_cli.providers.config.paths import AGENTHUB_PROVIDER_HOME_ENV
from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES, STANDARD_ROUTE_NAMES
from cli.agent_cli.providers.provider_status_management_runtime import (
    provider_management_surface_fields,
)
from cli.agent_cli.runtime_services.provider_availability_refresh_runtime import (
    refresh_controller_surface_fields,
)

_SESSION_PROVIDER_OVERRIDE_KEYS = {
    "AGENT_CLI_PROVIDER",
    "AGENT_CLI_MODEL",
    "AGENT_CLI_BASE_URL",
    "AGENT_CLI_REASONING_EFFORT",
    "AGENT_CLI_AUTH_MODE",
}


def _provider_selection_path() -> str:
    try:
        return str(resolve_user_provider_config_path())
    except Exception:
        return ""


def _has_session_provider_override(agent: Any) -> bool:
    overrides = dict(getattr(agent, "_session_provider_env_overrides", {}) or {})
    return any(str(overrides.get(key) or "").strip() for key in _SESSION_PROVIDER_OVERRIDE_KEYS)


def _append_session_provider_override_source(agent: Any, status: dict[str, Any]) -> dict[str, Any]:
    if str(status.get("provider_source") or "").strip() != "env":
        return status
    if not _has_session_provider_override(agent):
        return status
    status["provider_source"] = "session_override"
    status["provider_source_raw"] = "env"
    status["provider_session_override_active"] = True
    return status


def _append_provider_source_semantics(status: dict[str, Any]) -> dict[str, Any]:
    try:
        user_config_path = resolve_user_provider_config_path()
    except Exception:
        user_config_path = None
    try:
        user_auth_path = resolve_user_provider_auth_path()
    except Exception:
        user_auth_path = None
    selection_payload = load_user_provider_selection()
    status.update(
        provider_source_semantics_runtime.provider_source_semantics_fields(
            raw_source=status.get("provider_source"),
            config_path=status.get("provider_config_path"),
            auth_path=status.get("provider_auth_path"),
            selection_path=status.get("provider_selection_path"),
            selection_present=bool(selection_payload),
            user_config_path=user_config_path,
            user_auth_path=user_auth_path,
            runtime_home=os.environ.get(AGENTHUB_PROVIDER_HOME_ENV),
        )
    )
    return status


def provider_status(
    agent: Any,
    *,
    session_route_overrides_fn: Callable[[Any], dict[str, dict[str, Any]]],
    session_delegate_overrides_fn: Callable[[Any], dict[str, dict[str, Any]]],
    resolution_status_label_fn: Callable[[Any], str],
) -> dict[str, str]:
    def _append_management_surface(
        status: dict[str, Any],
        *,
        api_key_present: bool = False,
        active_provider_ready: Any | None = None,
    ) -> dict[str, Any]:
        _append_provider_source_semantics(status)
        _append_session_provider_override_source(agent, status)
        status.update(
            provider_management_surface_fields(
                auth_mode=status.get("auth_mode"),
                auth_status=status.get("auth_status"),
                api_key_present=api_key_present,
                no_auth_guardrail_pass=status.get("no_auth_guardrail_pass"),
                active_provider_ready=(
                    status.get("provider_ready")
                    if active_provider_ready is None
                    else active_provider_ready
                ),
                availability_status=status.get("availability_status"),
                availability_failure_code=status.get("availability_failure_code"),
                availability_retry_after_seconds=status.get("availability_retry_after_seconds"),
            )
        )
        provider_review_gate_fn = getattr(agent, "provider_review_gate", None)
        if callable(provider_review_gate_fn):
            try:
                status.update(dict(provider_review_gate_fn() or {}))
            except Exception:
                pass
        status.update(refresh_controller_surface_fields(agent))
        return status

    config_path = str(agent._provider_paths.config_path)
    auth_path = str(agent._provider_paths.auth_path)
    selection_path = _provider_selection_path()
    availability_registry = get_availability_registry(agent)
    availability_settings = (
        availability_feature_config_runtime.provider_availability_feature_settings(agent)
    )
    stale_after_seconds = int(availability_settings.get("stale_after_seconds") or 0)
    planner = getattr(agent, "_planner", None)
    pending_config = getattr(agent, "_planner_config", None) if planner is None else None
    if planner is not None or pending_config is not None:
        summary = (
            planner.public_summary() if planner is not None else pending_config.public_summary()
        )
        status = agent_status_projection.build_ready_provider_status(
            summary,
            config_path=config_path,
            auth_path=auth_path,
            selection_path=selection_path,
            host_platform=agent.host_platform,
            public_provider_name_fn=_public_provider_name,
        )
        api_key_present = bool(summary.get("api_key_present"))
        if (
            planner is None
            and str(status.get("auth_mode") or "").strip().lower() == "api_key"
            and not api_key_present
        ):
            status["provider_ready"] = "false"
        if planner is not None:
            agent_status_projection.append_route_and_delegate_resolution_labels(
                status,
                summary,
                route_names=STANDARD_ROUTE_NAMES,
                delegation_names=STANDARD_DELEGATION_NAMES,
                resolution_status_label_fn=resolution_status_label_fn,
            )
        route_overrides = session_route_overrides_fn(agent)
        delegation_overrides = session_delegate_overrides_fn(agent)
        agent_status_projection.append_override_counts(
            status,
            route_overrides=route_overrides,
            delegation_overrides=delegation_overrides,
        )
        diagnostic_lines = (
            agent._planner_runtime_error_diagnostic_lines() if agent._planner_runtime_error else []
        )
        agent_status_projection.append_runtime_state(
            status,
            runtime_error=agent._planner_runtime_error,
            diagnostic_lines=diagnostic_lines,
        )
        ready_model = str(status.get("provider_model") or "").strip()
        if ready_model in {"", "-"}:
            ready_model = str(status.get("model_key") or "").strip()
        if ready_model in {"", "-"}:
            ready_model = str(
                agent._session_provider_env_overrides.get("AGENT_CLI_MODEL") or ""
            ).strip()
        append_availability_surface(
            status,
            availability_registry,
            provider_name=str(status.get("provider_name") or ""),
            model=ready_model,
            stale_after_seconds=stale_after_seconds,
        )
        return _append_management_surface(
            status,
            api_key_present=api_key_present,
            active_provider_ready=planner is not None,
        )
    status = agent_status_projection.build_pending_provider_status(
        agent._session_provider_env_overrides,
        planner_error=agent._planner_error,
        config_path=config_path,
        auth_path=auth_path,
        selection_path=selection_path,
        host_platform=agent.host_platform,
        public_provider_name_fn=_public_provider_name,
    )
    route_overrides = session_route_overrides_fn(agent)
    delegation_overrides = session_delegate_overrides_fn(agent)
    agent_status_projection.append_override_counts(
        status,
        route_overrides=route_overrides,
        delegation_overrides=delegation_overrides,
    )
    pending_model = str(status.get("provider_model") or "").strip()
    if pending_model in {"", "-"}:
        pending_model = str(status.get("model_key") or "").strip()
    if pending_model in {"", "-"}:
        pending_model = str(
            agent._session_provider_env_overrides.get("AGENT_CLI_MODEL") or ""
        ).strip()
    append_availability_surface(
        status,
        availability_registry,
        provider_name=str(status.get("provider_name") or ""),
        model=pending_model,
        stale_after_seconds=stale_after_seconds,
    )
    return _append_management_surface(status, active_provider_ready=False)
