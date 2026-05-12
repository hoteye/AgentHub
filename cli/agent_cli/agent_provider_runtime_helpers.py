from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from cli.agent_cli import agent_provider_catalog_runtime
from cli.agent_cli import provider_catalog_runtime
from cli.agent_cli.provider_persistence_paths_runtime import (
    resolve_project_provider_config_write_path,
)
from cli.agent_cli.provider import _find_model_entry, save_user_model_selection
from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES, STANDARD_ROUTE_NAMES
from cli.agent_cli.providers.registry import infer_vendor, model_selector_for_line


_SELECTION_WRITE_SCOPES = {"session", "user", "project"}


def _resolved_selection_write_scope(*, write_scope: str | None = None, persist: bool = False) -> str:
    normalized = str(write_scope or "").strip().lower()
    if normalized:
        if normalized not in _SELECTION_WRITE_SCOPES:
            raise ValueError(f"invalid write scope: {write_scope}")
        return normalized
    return "user" if persist else "session"


def _project_selection_config_path(agent: Any) -> Path:
    loader_kwargs = agent._provider_loader_kwargs()
    return resolve_project_provider_config_write_path(
        cwd=loader_kwargs.get("cwd"),
    )


def _persist_selection_updates(
    agent: Any,
    *,
    write_scope: str,
    persistence_updates: Dict[str, str],
    operation_name: str,
) -> None:
    if write_scope == "session" or not persistence_updates:
        return
    try:
        if write_scope == "user":
            save_user_model_selection(**persistence_updates)
            return
        provider_catalog_runtime.save_user_model_selection(
            path=_project_selection_config_path(agent),
            **persistence_updates,
        )
    except OSError as exc:
        raise RuntimeError(f"failed to persist {operation_name}: {exc}") from exc


def _current_planner_selection(agent: Any) -> tuple[str, str]:
    planner = getattr(agent, "_planner", None)
    summary_getter = getattr(planner, "public_summary", None)
    if not callable(summary_getter):
        return "", ""
    try:
        summary = dict(summary_getter() or {})
    except Exception:
        return "", ""
    return (
        str(summary.get("provider_name") or "").strip(),
        str(summary.get("model_key") or summary.get("model") or "").strip(),
    )


def _selection_matches_current(agent: Any, *, provider_name: str, model: str) -> bool:
    provider = str(provider_name or "").strip()
    model_name = str(model or "").strip()
    if not provider or not model_name:
        return False
    current_provider = str(agent._session_provider_env_overrides.get("AGENT_CLI_PROVIDER") or "").strip()
    current_model = str(agent._session_provider_env_overrides.get("AGENT_CLI_MODEL") or "").strip()
    if not current_provider or not current_model:
        current_provider, current_model = _current_planner_selection(agent)
    return current_provider == provider and current_model == model_name


def configure_model_selection_impl(
    agent: Any,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    session_model_default_tokens: set[str],
    load_provider_catalog_fn,
    provider_status_fn,
    persist: bool = False,
    write_scope: str | None = None,
) -> Dict[str, str]:
    changed = False
    selection_write_scope = _resolved_selection_write_scope(write_scope=write_scope, persist=persist)
    session_updates: Dict[str, str] = {}
    session_removals: set[str] = set()
    persistence_updates: Dict[str, str] = {}
    catalog = None
    resolved_model_profile: Dict[str, Any] | None = None
    current_status = None
    target_model_uncertain = False
    if model is not None:
        selector = str(model or "").strip()
        if not selector:
            raise ValueError("model must be a non-empty string")
        if selector.lower() in session_model_default_tokens:
            session_removals.update({"AGENT_CLI_PROVIDER", "AGENT_CLI_MODEL"})
            persistence_updates["provider_name"] = ""
            persistence_updates["model"] = ""
            target_model_uncertain = True
            changed = True
        else:
            catalog = load_provider_catalog_fn(**agent._provider_loader_kwargs())
            preferred_provider = str(agent._session_provider_env_overrides.get("AGENT_CLI_PROVIDER") or "").strip() or None
            if preferred_provider is None:
                current_status = provider_status_fn(agent)
                if str(current_status.get("provider_ready") or "").strip().lower() == "true":
                    preferred_provider = str(current_status.get("provider_name") or "").strip() or None
            entry = _find_model_entry(selector, catalog, preferred_provider=preferred_provider)
            if entry is None and preferred_provider is not None:
                entry = _find_model_entry(selector, catalog)
            if entry is None:
                raise ValueError(f"unknown model selector: {selector}")
            resolved_model = entry.key or entry.model_id
            session_updates["AGENT_CLI_PROVIDER"] = entry.provider_name
            session_updates["AGENT_CLI_MODEL"] = resolved_model
            persistence_updates["provider_name"] = entry.provider_name
            persistence_updates["model"] = resolved_model
            resolved_model_profile = provider_catalog_runtime.model_catalog_reasoning_profile(
                catalog=catalog,
                provider_name=entry.provider_name,
                model=resolved_model,
            )
            changed = True
    if reasoning_effort is not None:
        effort = str(reasoning_effort or "").strip().lower()
        if not effort:
            raise ValueError("reasoning_effort must be a non-empty string")
        if effort in session_model_default_tokens:
            session_removals.add("AGENT_CLI_REASONING_EFFORT")
            persistence_updates["reasoning_effort"] = ""
            changed = True
        else:
            if resolved_model_profile is None and not target_model_uncertain:
                catalog = catalog or load_provider_catalog_fn(**agent._provider_loader_kwargs())
                current_status = current_status or provider_status_fn(agent)
                target_provider_name = (
                    str(session_updates.get("AGENT_CLI_PROVIDER") or "").strip()
                    or str(agent._session_provider_env_overrides.get("AGENT_CLI_PROVIDER") or "").strip()
                    or str(current_status.get("provider_name") or "").strip()
                )
                target_model = (
                    str(session_updates.get("AGENT_CLI_MODEL") or "").strip()
                    or str(agent._session_provider_env_overrides.get("AGENT_CLI_MODEL") or "").strip()
                    or str(current_status.get("model_key") or "").strip()
                    or str(current_status.get("provider_model") or "").strip()
                )
                if target_model:
                    resolved_model_profile = provider_catalog_runtime.model_catalog_reasoning_profile(
                        catalog=catalog,
                        provider_name=target_provider_name,
                        model=target_model,
                    )
            if resolved_model_profile is not None:
                supported_reasoning_efforts = tuple(resolved_model_profile.get("supported_reasoning_efforts") or ())
                target_model_id = str(resolved_model_profile.get("model_id") or "").strip() or str(
                    resolved_model_profile.get("model_key") or ""
                ).strip()
                if not supported_reasoning_efforts:
                    raise ValueError(f"model does not support reasoning_effort: {target_model_id or '-'}")
                if effort not in supported_reasoning_efforts:
                    choices = ", ".join((*supported_reasoning_efforts, "default"))
                    raise ValueError(
                        f"unsupported reasoning_effort for model {target_model_id or '-'}: {effort}. expected one of: {choices}"
                    )
                validated_effort = effort
            else:
                validated_effort = agent._validated_reasoning_effort(effort)
            session_updates["AGENT_CLI_REASONING_EFFORT"] = validated_effort
            persistence_updates["reasoning_effort"] = validated_effort
            changed = True
    _persist_selection_updates(
        agent,
        write_scope=selection_write_scope,
        persistence_updates=persistence_updates,
        operation_name="model selection",
    )
    for key in session_removals:
        agent._session_provider_env_overrides.pop(key, None)
    agent._session_provider_env_overrides.update(session_updates)
    if changed:
        agent._reload_planner()
    return provider_status_fn(agent)


def switch_provider_impl(
    agent: Any,
    provider_name: str,
    *,
    persist: bool = False,
    write_scope: str | None = None,
    load_provider_catalog_fn,
    supplement_catalog_fn,
    public_provider_name_fn,
    default_model_entry_fn,
    vendor_for_name_fn,
    provider_status_fn,
) -> Dict[str, str]:
    provider = str(provider_name or "").strip()
    if not provider:
        raise ValueError("provider_name must be a non-empty string")
    selection_write_scope = _resolved_selection_write_scope(write_scope=write_scope, persist=persist)
    catalog = supplement_catalog_fn(
        load_provider_catalog_fn(**agent._provider_loader_kwargs())
    )
    entry = agent_provider_catalog_runtime.resolve_switch_provider_entry(
        provider,
        catalog=catalog,
        public_provider_name_fn=public_provider_name_fn,
        default_model_entry_fn=default_model_entry_fn,
        vendor_for_name_fn=vendor_for_name_fn,
    )
    if entry is None:
        raise ValueError(f"unknown provider: {provider}")
    resolved_model = entry.key or entry.model_id
    selection_changed = not _selection_matches_current(
        agent,
        provider_name=entry.provider_name,
        model=resolved_model,
    )
    _persist_selection_updates(
        agent,
        write_scope=selection_write_scope,
        persistence_updates={
            "provider_name": entry.provider_name,
            "model": resolved_model,
        },
        operation_name="provider selection",
    )
    agent._session_provider_env_overrides["AGENT_CLI_PROVIDER"] = entry.provider_name
    agent._session_provider_env_overrides["AGENT_CLI_MODEL"] = resolved_model
    if selection_changed:
        agent._provider_review_gate_cache = None
        agent._reload_planner()
    return provider_status_fn(agent)


def configure_named_override_selection_impl(
    agent: Any,
    name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    clear: bool = False,
    validate_name_fn,
    override_payload_fn,
    store_attr: str,
    empty_override_error: str,
    provider_status_fn,
) -> Dict[str, str]:
    normalized_name = validate_name_fn(name)
    store = getattr(agent, store_attr)
    if clear:
        store.pop(normalized_name, None)
        agent._reload_planner()
        return provider_status_fn(agent)
    override = override_payload_fn(
        normalized_name,
        {
            "model": str(model or "").strip() or None,
            "provider": provider,
            "reasoning_effort": reasoning_effort,
            "timeout": timeout,
        },
    )
    if not override:
        raise ValueError(empty_override_error)
    store[normalized_name] = override
    agent._reload_planner()
    return provider_status_fn(agent)


def session_named_overrides(overrides: Any, *, allowed_names: tuple[str, ...]) -> Dict[str, Dict[str, Any]]:
    return {
        name: dict(payload)
        for name, payload in dict(overrides or {}).items()
        if name in allowed_names and isinstance(payload, dict) and payload
    }


def set_session_named_overrides_impl(
    agent: Any,
    overrides: Dict[str, Any] | None,
    *,
    allowed_names: tuple[str, ...],
    override_payload_fn,
    store_attr: str,
    read_back_fn,
) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for name, payload in dict(overrides or {}).items():
        if name not in allowed_names or not isinstance(payload, dict):
            continue
        override = override_payload_fn(name, payload)
        if override:
            normalized[name] = override
    setattr(agent, store_attr, normalized)
    agent._reload_planner()
    return read_back_fn(agent)


def switch_provider_line_impl(
    agent: Any,
    line: str,
    *,
    provider_status_fn,
) -> Dict[str, str]:
    normalized = str(line or "").strip().lower()
    if normalized not in {"chat", "reasoner"}:
        raise ValueError("line must be one of: chat, reasoner")
    status = provider_status_fn(agent)
    target_model = model_selector_for_line(
        line=normalized,
        provider_name=str(status.get("provider_name") or ""),
        model=str(status.get("provider_model") or ""),
        planner_kind=str(status.get("provider_planner") or ""),
        base_url=str(status.get("provider_base_url") or ""),
    )
    if target_model:
        inferred_vendor = infer_vendor(
            provider_name=str(status.get("provider_name") or ""),
            model=str(status.get("provider_model") or ""),
            planner_kind=str(status.get("provider_planner") or ""),
            base_url=str(status.get("provider_base_url") or ""),
        )
        agent._session_provider_env_overrides["AGENT_CLI_PROVIDER"] = (
            inferred_vendor.name if inferred_vendor is not None else str(status.get("provider_name") or "").strip()
        )
        agent._session_provider_env_overrides["AGENT_CLI_MODEL"] = target_model
        agent._reload_planner()
        return provider_status_fn(agent)
    provider_name = str(status.get("provider_name") or "").strip().lower()
    raise RuntimeError(f"provider line switching is not supported for provider: {provider_name or '-'}")


def session_route_overrides(agent: Any) -> Dict[str, Dict[str, Any]]:
    return session_named_overrides(
        getattr(agent, "_session_route_overrides", {}),
        allowed_names=STANDARD_ROUTE_NAMES,
    )


def session_delegate_overrides(agent: Any) -> Dict[str, Dict[str, Any]]:
    return session_named_overrides(
        getattr(agent, "_session_delegation_overrides", {}),
        allowed_names=STANDARD_DELEGATION_NAMES,
    )
