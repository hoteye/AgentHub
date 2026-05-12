from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.agent_cli import agent_provider_catalog_runtime
from cli.agent_cli import agent_provider_probe_runtime
from cli.agent_cli import agent_provider_runtime_helpers
from cli.agent_cli import agent_provider_status_runtime
from cli.agent_cli import workspace_context
from cli.agent_cli.agent_provider_resolution import (
    public_provider_name as _public_provider_name,
    resolution_status_label as _resolution_status_label,
)
from cli.agent_cli.agent_selection_runtime import (
    delegation_override_payload as _delegation_override_payload,
    route_override_payload as _route_override_payload,
    selection_override_payload as _selection_override_payload,
    validated_delegation_name as _validated_delegation_name,
    validated_route_name as _validated_route_name,
)
from cli.agent_cli import agent_provider_normalization_helpers_runtime
from cli.agent_cli import agent_provider_probe_helpers_runtime
from cli.agent_cli import agent_provider_selection_helpers_runtime
from cli.agent_cli.provider import (
    _default_model_entry,
)
from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES, STANDARD_ROUTE_NAMES
from cli.agent_cli.providers.registry import vendor_for_name

_PROBE_PROMPT = agent_provider_probe_runtime._PROBE_PROMPT


def validated_reasoning_effort(
    reasoning_effort: str,
    *,
    reasoning_effort_levels: tuple[str, ...],
) -> str:
    return agent_provider_normalization_helpers_runtime.validated_reasoning_effort(
        reasoning_effort,
        reasoning_effort_levels=reasoning_effort_levels,
    )


def validated_route_name(
    route_name: str,
    *,
    standard_route_names: tuple[str, ...],
) -> str:
    return agent_provider_normalization_helpers_runtime.validated_route_name(
        route_name,
        standard_route_names=standard_route_names,
    )


def validated_delegation_name(
    role_name: str,
    *,
    standard_delegation_names: tuple[str, ...],
) -> str:
    return agent_provider_normalization_helpers_runtime.validated_delegation_name(
        role_name,
        standard_delegation_names=standard_delegation_names,
    )


def selection_override_payload(
    override: Dict[str, Any],
    *,
    validate_reasoning_effort,
    override_source: str,
) -> Dict[str, Any]:
    return agent_provider_normalization_helpers_runtime.selection_override_payload(
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def route_override_payload(
    route_name: str,
    override: Dict[str, Any],
    *,
    validate_reasoning_effort,
    override_source: str,
) -> Dict[str, Any]:
    return agent_provider_normalization_helpers_runtime.route_override_payload(
        route_name,
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def delegation_override_payload(
    role_name: str,
    override: Dict[str, Any],
    *,
    validate_reasoning_effort,
    override_source: str,
) -> Dict[str, Any]:
    return agent_provider_normalization_helpers_runtime.delegation_override_payload(
        role_name,
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def configure_model_selection(
    agent: Any,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    session_model_default_tokens: set[str],
    load_provider_catalog_fn,
    persist: bool = False,
    write_scope: str | None = None,
) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.configure_model_selection(
        agent,
        model=model,
        reasoning_effort=reasoning_effort,
        session_model_default_tokens=session_model_default_tokens,
        load_provider_catalog_fn=load_provider_catalog_fn,
        persist=persist,
        write_scope=write_scope,
    )


def set_reasoning_effort(
    agent: Any,
    reasoning_effort: str,
    *,
    session_model_default_tokens: set[str],
) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.set_reasoning_effort(
        agent,
        reasoning_effort,
        session_model_default_tokens=session_model_default_tokens,
    )


def _session_provider_env_overrides(agent: Any) -> Dict[str, Optional[str]]:
    return agent_provider_normalization_helpers_runtime._session_provider_env_overrides(agent)


def probe_provider(
    agent: Any,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    load_provider_config_fn,
    build_planner_fn,
    writeback_availability: bool = True,
) -> Dict[str, Any]:
    return agent_provider_probe_helpers_runtime.probe_provider(
        agent,
        provider_name=provider_name,
        model=model,
        load_provider_config_fn=load_provider_config_fn,
        build_planner_fn=build_planner_fn,
        writeback_availability=writeback_availability,
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
    return agent_provider_probe_helpers_runtime.probe_providers(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
        load_provider_config_fn=load_provider_config_fn,
        build_planner_fn=build_planner_fn,
        writeback_availability=writeback_availability,
    )


def available_providers(
    agent: Any,
    *,
    load_provider_catalog_fn,
    load_provider_inputs_fn,
    supplement_catalog_fn,
) -> List[Dict[str, str]]:
    return agent_provider_probe_helpers_runtime.available_providers(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
    )


def expert_review_feature_settings(agent: Any) -> Dict[str, Any]:
    return agent_provider_probe_helpers_runtime.expert_review_feature_settings(agent)


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
    return agent_provider_probe_helpers_runtime.provider_review_gate(
        agent,
        load_provider_catalog_fn=load_provider_catalog_fn,
        load_provider_inputs_fn=load_provider_inputs_fn,
        supplement_catalog_fn=supplement_catalog_fn,
        min_eligible_providers=min_eligible_providers,
        prefer_cross_vendor=prefer_cross_vendor,
        allow_same_vendor_fallback=allow_same_vendor_fallback,
    )


def available_models(
    agent: Any,
    provider_name: Optional[str] = None,
    *,
    include_hidden: bool = False,
    load_provider_catalog_fn,
    supplement_catalog_fn,
) -> List[Dict[str, str]]:
    return agent_provider_probe_helpers_runtime.available_models(
        agent,
        provider_name=provider_name,
        include_hidden=include_hidden,
        load_provider_catalog_fn=load_provider_catalog_fn,
        supplement_catalog_fn=supplement_catalog_fn,
    )


def switch_provider(
    agent: Any,
    provider_name: str,
    *,
    persist: bool = False,
    write_scope: str | None = None,
    load_provider_catalog_fn,
    supplement_catalog_fn,
) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.switch_provider(
        agent,
        provider_name,
        persist=persist,
        write_scope=write_scope,
        load_provider_catalog_fn=load_provider_catalog_fn,
        supplement_catalog_fn=supplement_catalog_fn,
    )


def switch_model(
    agent: Any,
    selector: str,
    *,
    session_model_default_tokens: set[str],
) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.switch_model(
        agent,
        selector,
        session_model_default_tokens=session_model_default_tokens,
    )


def configure_route_selection(
    agent: Any,
    route_name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    clear: bool = False,
) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.configure_route_selection(
        agent,
        route_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
    )


def session_route_overrides(agent: Any) -> Dict[str, Dict[str, Any]]:
    return agent_provider_selection_helpers_runtime.session_route_overrides(agent)


def set_session_route_overrides(
    agent: Any,
    overrides: Dict[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    return agent_provider_selection_helpers_runtime.set_session_route_overrides(
        agent,
        overrides,
    )


def configure_delegate_selection(
    agent: Any,
    role_name: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    clear: bool = False,
) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.configure_delegate_selection(
        agent,
        role_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
    )


def session_delegate_overrides(agent: Any) -> Dict[str, Dict[str, Any]]:
    return agent_provider_selection_helpers_runtime.session_delegate_overrides(agent)


def set_session_delegate_overrides(
    agent: Any,
    overrides: Dict[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    return agent_provider_selection_helpers_runtime.set_session_delegate_overrides(
        agent,
        overrides,
    )


def switch_provider_line(agent: Any, line: str) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.switch_provider_line(agent, line)


def provider_status(agent: Any) -> Dict[str, str]:
    return agent_provider_selection_helpers_runtime.provider_status(agent)
