from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from cli.agent_cli.startup_debug import startup_timer


def provider_loader_kwargs(agent: Any) -> dict[str, Path]:
    cwd = getattr(agent, "cwd", None)
    return {"cwd": cwd} if cwd is not None else {}


def reload_planner(
    agent: Any,
    *,
    resolve_provider_paths_fn: Callable[..., Any],
    load_provider_config_fn: Callable[..., Any],
    build_planner_fn: Callable[..., Any],
) -> None:
    with startup_timer("agent_config.reload_planner"):
        provider_review_gate_fn = getattr(agent, "provider_review_gate", None)
        preserved_reviewer_gate: dict[str, Any] = {}
        if callable(provider_review_gate_fn) and getattr(agent, "_planner", None) is not None:
            try:
                preserved_reviewer_gate = dict(provider_review_gate_fn() or {})
            except Exception:
                preserved_reviewer_gate = {}
        if getattr(agent, "_planner", None) is not None and not bool(
            getattr(agent, "_planner_managed", False)
        ):
            agent._planner_error = None
            agent._planner_runtime_error = None
            agent._planner_runtime_error_diagnostics = None
            return
        agent._planner = None
        agent._planner_managed = False
        agent._planner_config = None
        agent._planner_build_pending = False
        agent._planner_error = None
        agent._planner_runtime_error = None
        agent._planner_runtime_error_diagnostics = None
        loader_kwargs = provider_loader_kwargs(agent)
        with startup_timer("agent_config.reload_planner.resolve_provider_paths"):
            agent._provider_paths = resolve_provider_paths_fn(**loader_kwargs)
        with startup_timer("agent_config.reload_planner.load_provider_config"):
            config = load_provider_config_fn(
                **loader_kwargs,
                env_overrides=dict(getattr(agent, "_session_provider_env_overrides", {}) or {}),
            )
        if config is None:
            return
        session_route_overrides = dict(getattr(agent, "_session_route_overrides", {}) or {})
        if session_route_overrides:
            config = agent._config_with_session_route_overrides(config, session_route_overrides)
        session_delegation_overrides = dict(
            getattr(agent, "_session_delegation_overrides", {}) or {}
        )
        if session_delegation_overrides:
            config = agent._config_with_session_delegation_overrides(
                config, session_delegation_overrides
            )
        runtime_policy_overrides = dict(getattr(agent, "_runtime_policy_overrides", {}) or {})
        if runtime_policy_overrides and hasattr(config, "raw_provider"):
            merged_provider = dict(getattr(config, "raw_provider", {}) or {})
            merged_provider.update(runtime_policy_overrides)
            try:
                config = replace(config, raw_provider=merged_provider)
            except Exception:
                pass
        if callable(provider_review_gate_fn) and hasattr(config, "raw_provider"):
            reviewer_gate = dict(preserved_reviewer_gate or {})
            if not reviewer_gate:
                try:
                    reviewer_gate = dict(provider_review_gate_fn() or {})
                except Exception:
                    reviewer_gate = {}
            if reviewer_gate:
                merged_provider = dict(getattr(config, "raw_provider", {}) or {})
                merged_provider.update(reviewer_gate)
                merged_provider["expert_review_gate_snapshot"] = dict(reviewer_gate)
                try:
                    config = replace(config, raw_provider=merged_provider)
                except Exception:
                    pass
        try:
            cwd = getattr(agent, "cwd", None)
            plugin_manager_factory = getattr(agent, "_plugin_manager_factory", None)
            with startup_timer("agent_config.reload_planner.build_planner"):
                agent._planner = build_planner_fn(
                    config,
                    host_platform=agent.host_platform,
                    cwd=cwd,
                    plugin_manager_factory=plugin_manager_factory,
                )
            agent._planner_managed = agent._planner is not None
        except Exception as exc:
            agent._planner_error = str(exc)


def prepare_lazy_planner(
    agent: Any,
    *,
    resolve_provider_paths_fn: Callable[..., Any],
    load_provider_config_fn: Callable[..., Any],
    apply_review_gate: bool = True,
) -> None:
    with startup_timer("agent_config.prepare_lazy_planner"):
        if getattr(agent, "_planner", None) is not None and not bool(
            getattr(agent, "_planner_managed", False)
        ):
            agent._planner_error = None
            agent._planner_runtime_error = None
            agent._planner_runtime_error_diagnostics = None
            return
        agent._planner = None
        agent._planner_managed = False
        agent._planner_error = None
        agent._planner_runtime_error = None
        agent._planner_runtime_error_diagnostics = None
        agent._planner_config = None
        agent._planner_build_pending = False
        loader_kwargs = provider_loader_kwargs(agent)
        with startup_timer("agent_config.prepare_lazy_planner.resolve_provider_paths"):
            agent._provider_paths = resolve_provider_paths_fn(**loader_kwargs)
        with startup_timer("agent_config.prepare_lazy_planner.load_provider_config"):
            config = load_provider_config_fn(
                **loader_kwargs,
                env_overrides=dict(getattr(agent, "_session_provider_env_overrides", {}) or {}),
            )
        if config is None:
            return
        session_route_overrides = dict(getattr(agent, "_session_route_overrides", {}) or {})
        if session_route_overrides:
            config = agent._config_with_session_route_overrides(config, session_route_overrides)
        session_delegation_overrides = dict(
            getattr(agent, "_session_delegation_overrides", {}) or {}
        )
        if session_delegation_overrides:
            config = agent._config_with_session_delegation_overrides(
                config, session_delegation_overrides
            )
        runtime_policy_overrides = dict(getattr(agent, "_runtime_policy_overrides", {}) or {})
        if runtime_policy_overrides and hasattr(config, "raw_provider"):
            merged_provider = dict(getattr(config, "raw_provider", {}) or {})
            merged_provider.update(runtime_policy_overrides)
            try:
                config = replace(config, raw_provider=merged_provider)
            except Exception:
                pass
        provider_review_gate_fn = getattr(agent, "provider_review_gate", None)
        if (
            apply_review_gate
            and callable(provider_review_gate_fn)
            and hasattr(config, "raw_provider")
        ):
            try:
                reviewer_gate = dict(provider_review_gate_fn() or {})
            except Exception:
                reviewer_gate = {}
            if reviewer_gate:
                merged_provider = dict(getattr(config, "raw_provider", {}) or {})
                merged_provider.update(reviewer_gate)
                merged_provider["expert_review_gate_snapshot"] = dict(reviewer_gate)
                try:
                    config = replace(config, raw_provider=merged_provider)
                except Exception:
                    pass
        agent._planner_config = config
        agent._planner_build_pending = True


def build_pending_planner(
    agent: Any,
    *,
    build_planner_fn: Callable[..., Any],
) -> Any | None:
    if getattr(agent, "_planner", None) is not None:
        return agent._planner
    if not bool(getattr(agent, "_planner_build_pending", False)):
        return None
    config = getattr(agent, "_planner_config", None)
    if config is None:
        agent._planner_build_pending = False
        return None
    provider_review_gate_fn = getattr(agent, "provider_review_gate", None)
    if callable(provider_review_gate_fn) and hasattr(config, "raw_provider"):
        try:
            reviewer_gate = dict(provider_review_gate_fn() or {})
        except Exception:
            reviewer_gate = {}
        if reviewer_gate:
            merged_provider = dict(getattr(config, "raw_provider", {}) or {})
            merged_provider.update(reviewer_gate)
            merged_provider["expert_review_gate_snapshot"] = dict(reviewer_gate)
            try:
                config = replace(config, raw_provider=merged_provider)
            except Exception:
                pass
            agent._planner_config = config
    try:
        cwd = getattr(agent, "cwd", None)
        plugin_manager_factory = getattr(agent, "_plugin_manager_factory", None)
        with startup_timer("agent_config.lazy_build_planner"):
            agent._planner = build_planner_fn(
                config,
                host_platform=agent.host_platform,
                cwd=cwd,
                plugin_manager_factory=plugin_manager_factory,
            )
        agent._planner_managed = agent._planner is not None
        agent._planner_build_pending = False
        agent._planner_error = None
        agent._planner_runtime_error = None
        agent._planner_runtime_error_diagnostics = None
        return agent._planner
    except Exception as exc:
        agent._planner = None
        agent._planner_managed = False
        agent._planner_config = None
        agent._planner_build_pending = False
        agent._planner_error = str(exc)
        return None


def set_cwd(
    agent: Any,
    cwd: str | Path,
    *,
    reload_planner_fn: Callable[[], None],
) -> Path:
    next_cwd = Path(cwd).resolve()
    if getattr(agent, "cwd", None) == next_cwd:
        return next_cwd
    agent.cwd = next_cwd
    reload_planner_fn()
    return agent.cwd


def set_plugin_manager_factory(
    agent: Any,
    factory: Callable[[], Any] | None,
    *,
    reload_planner_fn: Callable[[], None],
) -> None:
    if getattr(agent, "_plugin_manager_factory", None) is factory:
        return
    agent._plugin_manager_factory = factory
    reload_planner_fn()


def set_runtime_policy_overrides(
    agent: Any,
    overrides: dict[str, Any] | None,
    *,
    reload_planner_fn: Callable[[], None],
) -> None:
    payload = set_runtime_policy_overrides_payload(agent, overrides)
    if payload is None:
        return
    reload_planner_fn()


def set_runtime_policy_overrides_payload(
    agent: Any,
    overrides: dict[str, Any] | None,
) -> dict[str, Any] | None:
    payload = {
        str(key): value for key, value in dict(overrides or {}).items() if value not in (None, "")
    }
    if dict(getattr(agent, "_runtime_policy_overrides", {}) or {}) == payload:
        return None
    agent._runtime_policy_overrides = payload
    return payload


def set_planner_override(agent: Any, planner: Any, *, managed: bool = False) -> None:
    agent._planner = planner
    agent._planner_config = None
    agent._planner_build_pending = False
    agent._planner_managed = bool(planner is not None and managed)
    agent._planner_error = None
    agent._planner_runtime_error = None
    agent._planner_runtime_error_diagnostics = None
