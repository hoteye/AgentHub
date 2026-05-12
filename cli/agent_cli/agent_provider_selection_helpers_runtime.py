from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli import agent_provider_runtime_helpers
from cli.agent_cli import agent_provider_status_runtime
from cli.agent_cli.agent_provider_resolution import (
    public_provider_name as _public_provider_name,
    resolution_status_label as _resolution_status_label,
)
from cli.agent_cli.provider import (
    _default_model_entry,
)
from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES, STANDARD_ROUTE_NAMES
from cli.agent_cli.providers.registry import vendor_for_name


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
    return agent_provider_runtime_helpers.configure_model_selection_impl(
        agent,
        model=model,
        reasoning_effort=reasoning_effort,
        session_model_default_tokens=session_model_default_tokens,
        load_provider_catalog_fn=load_provider_catalog_fn,
        provider_status_fn=provider_status,
        persist=persist,
        write_scope=write_scope,
    )


def set_reasoning_effort(
    agent: Any,
    reasoning_effort: str,
    *,
    session_model_default_tokens: set[str],
) -> Dict[str, str]:
    return configure_model_selection(
        agent,
        reasoning_effort=reasoning_effort,
        session_model_default_tokens=session_model_default_tokens,
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
    return agent_provider_runtime_helpers.switch_provider_impl(
        agent,
        provider_name,
        persist=persist,
        write_scope=write_scope,
        load_provider_catalog_fn=load_provider_catalog_fn,
        supplement_catalog_fn=supplement_catalog_fn,
        public_provider_name_fn=_public_provider_name,
        default_model_entry_fn=_default_model_entry,
        vendor_for_name_fn=vendor_for_name,
        provider_status_fn=provider_status,
    )


def switch_model(
    agent: Any,
    selector: str,
    *,
    session_model_default_tokens: set[str],
) -> Dict[str, str]:
    return configure_model_selection(
        agent,
        model=selector,
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
    return agent_provider_runtime_helpers.configure_named_override_selection_impl(
        agent,
        route_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
        validate_name_fn=agent._validated_route_name,
        override_payload_fn=agent._route_override_payload,
        store_attr="_session_route_overrides",
        empty_override_error="route override requires at least one of: model, --provider, --reasoning-effort, --timeout",
        provider_status_fn=provider_status,
    )


def session_route_overrides(agent: Any) -> Dict[str, Dict[str, Any]]:
    return agent_provider_runtime_helpers.session_route_overrides(agent)


def set_session_route_overrides(
    agent: Any,
    overrides: Dict[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    return agent_provider_runtime_helpers.set_session_named_overrides_impl(
        agent,
        overrides,
        allowed_names=STANDARD_ROUTE_NAMES,
        override_payload_fn=agent._route_override_payload,
        store_attr="_session_route_overrides",
        read_back_fn=session_route_overrides,
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
    return agent_provider_runtime_helpers.configure_named_override_selection_impl(
        agent,
        role_name,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        clear=clear,
        validate_name_fn=agent._validated_delegation_name,
        override_payload_fn=agent._delegation_override_payload,
        store_attr="_session_delegation_overrides",
        empty_override_error="delegation override requires at least one of: model, --provider, --reasoning-effort, --timeout",
        provider_status_fn=provider_status,
    )


def session_delegate_overrides(agent: Any) -> Dict[str, Dict[str, Any]]:
    return agent_provider_runtime_helpers.session_delegate_overrides(agent)


def set_session_delegate_overrides(
    agent: Any,
    overrides: Dict[str, Any] | None,
) -> Dict[str, Dict[str, Any]]:
    return agent_provider_runtime_helpers.set_session_named_overrides_impl(
        agent,
        overrides,
        allowed_names=STANDARD_DELEGATION_NAMES,
        override_payload_fn=agent._delegation_override_payload,
        store_attr="_session_delegation_overrides",
        read_back_fn=session_delegate_overrides,
    )


def switch_provider_line(agent: Any, line: str) -> Dict[str, str]:
    return agent_provider_runtime_helpers.switch_provider_line_impl(
        agent,
        line,
        provider_status_fn=provider_status,
    )


def provider_status(agent: Any) -> Dict[str, str]:
    return agent_provider_status_runtime.provider_status(
        agent,
        session_route_overrides_fn=session_route_overrides,
        session_delegate_overrides_fn=session_delegate_overrides,
        resolution_status_label_fn=_resolution_status_label,
    )
