from __future__ import annotations

import inspect
import os
from typing import Any, Callable, Dict

from cli.agent_cli import agent_provider_runtime
from cli.agent_cli import agent_runtime
from cli.agent_cli.agent_selection_runtime import resolve_delegate_execution as _resolve_delegate_execution
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import AgentIntent, ToolEvent


def config_with_session_block_overrides(
    config: Any,
    *,
    block_key: str,
    allowed_names: tuple[str, ...],
    overrides: Dict[str, Dict[str, Any]],
    config_with_session_route_overrides_fn: Callable[..., Any],
    config_with_session_delegation_overrides_fn: Callable[..., Any],
    session_model_default_tokens: int,
) -> Any:
    if block_key == "routes":
        return config_with_session_route_overrides_fn(
            config,
            overrides,
            standard_route_names=allowed_names,
            session_model_default_tokens=session_model_default_tokens,
        )
    if block_key == "delegation":
        return config_with_session_delegation_overrides_fn(
            config,
            overrides,
            standard_delegation_names=allowed_names,
            session_model_default_tokens=session_model_default_tokens,
        )
    return config


def config_with_session_route_overrides(
    config: Any,
    overrides: Dict[str, Dict[str, Any]],
    *,
    standard_route_names: tuple[str, ...],
    session_model_default_tokens: int,
    config_with_session_route_overrides_fn: Callable[..., Any],
) -> Any:
    return config_with_session_route_overrides_fn(
        config,
        overrides,
        standard_route_names=standard_route_names,
        session_model_default_tokens=session_model_default_tokens,
    )


def config_with_session_delegation_overrides(
    config: Any,
    overrides: Dict[str, Dict[str, Any]],
    *,
    standard_delegation_names: tuple[str, ...],
    session_model_default_tokens: int,
    config_with_session_delegation_overrides_fn: Callable[..., Any],
) -> Any:
    return config_with_session_delegation_overrides_fn(
        config,
        overrides,
        standard_delegation_names=standard_delegation_names,
        session_model_default_tokens=session_model_default_tokens,
    )


def selection_override_payload(
    override: Dict[str, Any],
    *,
    validate_reasoning_effort: Callable[[str], str],
    override_source: str,
) -> Dict[str, Any]:
    return agent_provider_runtime.selection_override_payload(
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def route_override_payload(
    route_name: str,
    override: Dict[str, Any],
    *,
    validate_reasoning_effort: Callable[[str], str],
    override_source: str,
) -> Dict[str, Any]:
    return agent_provider_runtime.route_override_payload(
        route_name,
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def delegation_override_payload(
    role_name: str,
    override: Dict[str, Any],
    *,
    validate_reasoning_effort: Callable[[str], str],
    override_source: str,
) -> Dict[str, Any]:
    return agent_provider_runtime.delegation_override_payload(
        role_name,
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def set_env_value(name: str, value: str | None) -> None:
    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)


def filter_callable_kwargs(handler: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return kwargs
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def resolve_delegate_execution(
    *,
    role_name: str,
    planner: Any,
    cwd: str | None,
    model: str | None,
    provider: str | None,
    reasoning_effort: str | None,
    timeout: Any,
    standard_delegation_names: tuple[str, ...],
    validate_reasoning_effort: Callable[[str], str],
    session_model_default_tokens: int,
    session_override_source: str,
) -> Any:
    return _resolve_delegate_execution(
        role_name=role_name,
        planner=planner,
        cwd=cwd,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        standard_delegation_names=standard_delegation_names,
        validate_reasoning_effort=validate_reasoning_effort,
        session_model_default_tokens=session_model_default_tokens,
        session_override_source=session_override_source,
    )


def match_shell_intent(
    *,
    text: str,
    normalized: str,
    host_platform: HostPlatform,
    list_dir_keys: tuple[str, ...],
    pwd_keys: tuple[str, ...],
    python_version_keys: tuple[str, ...],
) -> AgentIntent | None:
    return agent_runtime.match_shell_intent(
        text=text,
        normalized=normalized,
        host_platform=host_platform,
        list_dir_keys=list_dir_keys,
        pwd_keys=pwd_keys,
        python_version_keys=python_version_keys,
    )


def summarize_live_web_result(query: str, event: ToolEvent) -> str:
    return agent_runtime.summarize_live_web_result(query, event)


def interrupt_active_provider_stream(planner: Any) -> bool:
    interrupter = getattr(planner, "interrupt_active_stream", None)
    if not callable(interrupter):
        return False
    try:
        return bool(interrupter())
    except Exception:
        return False
