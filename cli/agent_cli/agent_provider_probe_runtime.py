from __future__ import annotations

import time
from typing import Any, Dict, List

from cli.agent_cli import agent_provider_catalog_runtime
from cli.agent_cli import agent_provider_probe_normalization_helpers_runtime as probe_normalization_helpers
from cli.agent_cli import agent_provider_probe_projection_helpers_runtime as probe_projection_helpers
from cli.agent_cli import agent_provider_probe_pure_helpers_runtime as probe_pure_helpers
from cli.agent_cli import provider_catalog_runtime
from cli.agent_cli import workspace_context
from cli.agent_cli.agent_provider_resolution import public_provider_name as _public_provider_name
from cli.agent_cli.provider import (
    _default_model_entry,
)
from cli.agent_cli.providers import availability_feature_config_runtime
from cli.agent_cli.providers import availability_runtime as provider_availability_runtime
from cli.agent_cli.providers import expert_review_feature_config_runtime
from cli.agent_cli.providers import provider_status_management_runtime
from cli.agent_cli.providers.availability_projection import get_availability_registry
from cli.agent_cli.providers.registry import vendor_for_name
from cli.agent_cli.runtime_services.gateway_runtime_helper_runtime import filter_handler_kwargs


_PROBE_PROMPT = "Reply with exactly OK and nothing else."


def _availability_registry_signature(agent: Any) -> tuple[Any, ...]:
    registry = get_availability_registry(agent)
    if registry is None:
        return ()
    records = getattr(registry, "_records", None)
    if not isinstance(records, dict):
        return (id(registry),)
    lock = getattr(registry, "_lock", None)

    def _signature_from_records() -> tuple[Any, ...]:
        signature: list[tuple[str, str, str, str]] = []
        for key, record in sorted(records.items(), key=lambda item: item[0]):
            status = getattr(record, "status", "")
            signature.append(
                (
                    str(key[0] if isinstance(key, tuple) and len(key) > 0 else ""),
                    str(key[1] if isinstance(key, tuple) and len(key) > 1 else ""),
                    str(getattr(status, "value", status) or ""),
                    str(getattr(record, "checked_at", "") or ""),
                )
            )
        return tuple(signature)

    if lock is not None:
        try:
            with lock:
                return _signature_from_records()
        except Exception:
            return (id(registry),)
    try:
        return _signature_from_records()
    except Exception:
        return (id(registry),)


def _provider_review_gate_cache_key(
    agent: Any,
    *,
    min_eligible_providers: int | None,
    prefer_cross_vendor: bool | None,
    allow_same_vendor_fallback: bool | None,
) -> tuple[Any, ...]:
    loader_kwargs_getter = getattr(agent, "_provider_loader_kwargs", None)
    try:
        loader_kwargs = dict(loader_kwargs_getter() or {}) if callable(loader_kwargs_getter) else {}
    except Exception:
        loader_kwargs = {}
    return (
        tuple(sorted((str(key), str(value)) for key, value in loader_kwargs.items())),
        tuple(sorted((str(key), str(value)) for key, value in dict(_session_provider_env_overrides(agent) or {}).items())),
        tuple(sorted((str(key), str(value)) for key, value in dict(getattr(agent, "_runtime_policy_overrides", {}) or {}).items())),
        _availability_registry_signature(agent),
        min_eligible_providers,
        prefer_cross_vendor,
        allow_same_vendor_fallback,
    )


def _effective_home_provider_config_path(*, cwd: Any) -> Any:
    from cli.agent_cli.provider_persistence_paths_runtime import (
        resolve_effective_home_provider_config_path,
    )

    return resolve_effective_home_provider_config_path(cwd=cwd)


def _session_provider_env_overrides(agent: Any) -> Dict[str, str | None]:
    return probe_normalization_helpers.session_provider_env_overrides(agent)


def _merged_provider_env_mapping(agent: Any) -> Dict[str, str]:
    return probe_normalization_helpers.merged_provider_env_mapping(agent)


def _current_probe_target(agent: Any) -> tuple[str, str]:
    return probe_normalization_helpers.current_probe_target(agent)


def _provider_public_name_from_config(config: Any) -> str:
    return probe_projection_helpers.provider_public_name_from_config(
        config,
        public_provider_name_fn=_public_provider_name,
    )


def _probe_owner(agent: Any) -> Any:
    return probe_pure_helpers.probe_owner(
        agent,
        availability_registry=get_availability_registry(agent),
    )


def _noop_turn_event_callback(_event: Dict[str, Any]) -> None:
    return probe_pure_helpers.noop_turn_event_callback(_event)


def probe_provider(
    agent: Any,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    load_provider_config_fn,
    build_planner_fn,
    writeback_availability: bool = True,
) -> Dict[str, Any]:
    selected_provider, selected_model, env_overrides = probe_normalization_helpers.resolve_probe_request(
        agent,
        provider_name=provider_name,
        model=model,
    )

    config = load_provider_config_fn(
        cwd=getattr(agent, "cwd", None),
        env_overrides=env_overrides,
    )
    if config is None:
        return probe_projection_helpers.probe_not_configured_payload(
            selected_provider=selected_provider,
            selected_model=selected_model,
        )

    probe_planner = probe_pure_helpers.probe_planner_placeholder(config)
    started_at = time.monotonic()
    try:
        planner = build_planner_fn(
            config,
            host_platform=getattr(agent, "host_platform", None),
            cwd=getattr(agent, "cwd", None),
            plugin_manager_factory=getattr(agent, "_plugin_manager_factory", None),
        )
        probe_planner = planner
        probe_plan_kwargs = filter_handler_kwargs(
            planner.plan,
            {
                "history": [],
                "turn_event_callback": _noop_turn_event_callback,
            },
        )
        intent = planner.plan(
            _PROBE_PROMPT,
            **probe_plan_kwargs,
        )
        latency_ms = max(0, int(round((time.monotonic() - started_at) * 1000.0)))
        if writeback_availability:
            provider_availability_runtime.mark_provider_success(
                _probe_owner(agent),
                planner=probe_planner,
                diagnostics={"planner_elapsed_ms": latency_ms},
            )
        return probe_projection_helpers.probe_success_payload(
            config,
            intent=intent,
            latency_ms=latency_ms,
            public_provider_name_fn=_public_provider_name,
        )
    except Exception as exc:
        latency_ms = max(0, int(round((time.monotonic() - started_at) * 1000.0)))
        if writeback_availability:
            provider_availability_runtime.mark_provider_failure(
                _probe_owner(agent),
                planner=probe_planner,
                exc=exc,
                diagnostics={"planner_elapsed_ms": latency_ms},
            )
        return probe_projection_helpers.probe_failure_payload(
            config,
            selected_provider=selected_provider,
            selected_model=selected_model,
            exc=exc,
            latency_ms=latency_ms,
            public_provider_name_fn=_public_provider_name,
        )


def available_providers(
    agent: Any,
    *,
    load_provider_catalog_fn,
    load_provider_inputs_fn,
    supplement_catalog_fn,
) -> List[Dict[str, str]]:
    catalog = supplement_catalog_fn(
        load_provider_catalog_fn(**agent._provider_loader_kwargs())
    )
    env_mapping: Dict[str, Any] | None = None
    auth_data: Dict[str, Any] | None = None
    auth_path = None
    try:
        resolution, _, auth_data = load_provider_inputs_fn(**agent._provider_loader_kwargs())
        auth_path = resolution.auth_path
        env_mapping = _merged_provider_env_mapping(agent)
    except Exception:
        env_mapping = None
        auth_data = None
        auth_path = None
    availability_settings = availability_feature_config_runtime.provider_availability_feature_settings(agent)
    return agent_provider_catalog_runtime.available_provider_items(
        catalog,
        public_provider_name_fn=_public_provider_name,
        default_model_entry_fn=_default_model_entry,
        vendor_for_name_fn=vendor_for_name,
        env_mapping=env_mapping,
        auth_data=auth_data,
        auth_path=auth_path,
        availability_registry=get_availability_registry(agent),
        stale_after_seconds=int(availability_settings.get("stale_after_seconds") or 0),
    )


def probe_providers(
    agent: Any,
    *,
    load_provider_catalog_fn,
    load_provider_inputs_fn,
    supplement_catalog_fn,
    load_provider_config_fn,
    build_planner_fn,
    writeback_availability: bool = True,
) -> List[Dict[str, Any]]:
    items = available_providers(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
    )
    results: List[Dict[str, Any]] = []
    for item in items:
        config_provider_name = str(item.get("config_provider_name") or item.get("provider_name") or "").strip()
        probe_model = str(item.get("provider_default_model_id") or item.get("default_model") or "").strip()
        probe = probe_provider(
            agent,
            provider_name=config_provider_name or None,
            model=probe_model or None,
            load_provider_config_fn=load_provider_config_fn,
            build_planner_fn=build_planner_fn,
            writeback_availability=writeback_availability,
        )
        results.append(probe_pure_helpers.merge_probe_item(item, probe))
    return results


def expert_review_feature_settings(agent: Any) -> Dict[str, Any]:
    cwd = probe_pure_helpers.resolve_agent_cwd(agent)
    home_config_paths = (
        [_effective_home_provider_config_path(cwd=cwd)]
        if cwd is not None
        else []
    )
    merged_config = probe_pure_helpers.read_workspace_feature_config(
        agent,
        read_merged_project_toml_fn=workspace_context.read_merged_project_toml,
        home_config_paths=home_config_paths,
    )
    return expert_review_feature_config_runtime.expert_review_feature_settings_from_config(merged_config)


def provider_review_gate(
    agent: Any,
    *,
    load_provider_catalog_fn,
    load_provider_inputs_fn,
    supplement_catalog_fn,
    min_eligible_providers: int | None = None,
    prefer_cross_vendor: bool | None = None,
    allow_same_vendor_fallback: bool | None = None,
) -> Dict[str, Any]:
    cache_key = _provider_review_gate_cache_key(
        agent,
        min_eligible_providers=min_eligible_providers,
        prefer_cross_vendor=prefer_cross_vendor,
        allow_same_vendor_fallback=allow_same_vendor_fallback,
    )
    cached = getattr(agent, "_provider_review_gate_cache", None)
    if (
        isinstance(cached, tuple)
        and len(cached) == 2
        and cached[0] == cache_key
        and isinstance(cached[1], dict)
    ):
        return dict(cached[1])
    provider_items = available_providers(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
    )
    feature_settings = expert_review_feature_settings(agent)
    active_provider_name, active_provider_public_name = probe_projection_helpers.active_provider_identity(
        agent,
        public_provider_name_fn=_public_provider_name,
        session_provider_env_overrides_fn=_session_provider_env_overrides,
    )
    gate = provider_status_management_runtime.provider_reviewer_gate_fields(
        provider_items,
        active_provider_name=active_provider_name,
        active_provider_public_name=active_provider_public_name,
        min_eligible_providers=(
            feature_settings["min_eligible_providers"]
            if min_eligible_providers is None
            else min_eligible_providers
        ),
        prefer_cross_vendor=(
            feature_settings["prefer_cross_vendor"]
            if prefer_cross_vendor is None
            else prefer_cross_vendor
        ),
        allow_same_vendor_fallback=(
            feature_settings["allow_same_vendor_fallback"]
            if allow_same_vendor_fallback is None
            else allow_same_vendor_fallback
        ),
        feature_enabled=feature_settings["enabled"],
        feature_source=feature_settings["config_source"],
        required_reasoning_effort=feature_settings["required_reasoning_effort"],
        reasoning_effort_source=feature_settings["reasoning_effort_source"],
        reviewer_capability_policy=feature_settings["reviewer_capability_policy"],
        reviewer_capability_policy_source=feature_settings["reviewer_capability_policy_source"],
        reasoning_capability_validation=feature_settings["reasoning_capability_validation"],
        vendor_for_name_fn=vendor_for_name,
    )
    agent._provider_review_gate_cache = (cache_key, dict(gate))
    return gate


def available_models(
    agent: Any,
    provider_name: str | None = None,
    *,
    include_hidden: bool = False,
    load_provider_catalog_fn,
    supplement_catalog_fn,
) -> List[Dict[str, str]]:
    loader_kwargs = agent._provider_loader_kwargs()
    catalog = supplement_catalog_fn(
        load_provider_catalog_fn(**loader_kwargs)
    )
    remote_model_items_by_provider = probe_pure_helpers.load_remote_model_items_by_provider(
        catalog,
        cwd=loader_kwargs.get("cwd"),
        refresh_remote_model_catalog_fn=provider_catalog_runtime.refresh_remote_model_catalog,
        load_cached_remote_models_fn=provider_catalog_runtime.load_cached_remote_models,
    )
    return agent_provider_catalog_runtime.available_model_items(
        catalog,
        provider_name=provider_name,
        include_hidden=include_hidden,
        remote_model_items_by_provider=remote_model_items_by_provider,
        public_provider_name_fn=_public_provider_name,
        default_model_entry_fn=_default_model_entry,
        vendor_for_name_fn=vendor_for_name,
    )
