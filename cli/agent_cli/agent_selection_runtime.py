from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, Optional

from cli.agent_cli.providers.model_routing import resolve_delegation_config


def validated_route_name(route_name: str, *, standard_route_names: tuple[str, ...]) -> str:
    normalized = str(route_name or "").strip()
    if normalized not in standard_route_names:
        choices = ", ".join(standard_route_names)
        raise ValueError(f"unsupported route: {route_name}. expected one of: {choices}")
    return normalized


def validated_delegation_name(role_name: str, *, standard_delegation_names: tuple[str, ...]) -> str:
    normalized = str(role_name or "").strip()
    if normalized not in standard_delegation_names:
        choices = ", ".join(standard_delegation_names)
        raise ValueError(f"unsupported delegation role: {role_name}. expected one of: {choices}")
    return normalized


def validated_route_timeout(timeout: Any) -> int:
    try:
        value = int(str(timeout).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be a positive integer") from exc
    if value <= 0:
        raise ValueError("timeout must be a positive integer")
    return value


def selection_override_payload(
    override: Dict[str, Any],
    *,
    validate_reasoning_effort: Callable[[str], str],
    override_source: str,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if "provider" in override:
        provider_value = override.get("provider")
        payload["provider"] = "" if provider_value in (None, "") else str(provider_value).strip()
    model_value = override.get("model")
    if model_value not in (None, ""):
        payload["model"] = str(model_value).strip()
        if "provider" not in payload:
            payload["provider"] = ""
    reasoning_value = override.get("reasoning_effort")
    if reasoning_value not in (None, ""):
        payload["reasoning_effort"] = validate_reasoning_effort(str(reasoning_value))
    timeout_value = override.get("timeout")
    if timeout_value not in (None, ""):
        payload["timeout"] = validated_route_timeout(timeout_value)
    if payload:
        payload["source"] = str(override_source or "").strip()
    return payload


def route_override_payload(
    route_name: str,
    override: Dict[str, Any],
    *,
    validate_reasoning_effort: Callable[[str], str],
    override_source: str,
) -> Dict[str, Any]:
    del route_name
    return selection_override_payload(
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
    del role_name
    return selection_override_payload(
        override,
        validate_reasoning_effort=validate_reasoning_effort,
        override_source=override_source,
    )


def config_with_session_block_overrides(
    config: Any,
    *,
    block_key: str,
    allowed_names: tuple[str, ...],
    overrides: Dict[str, Dict[str, Any]],
    session_model_default_tokens: set[str],
) -> Any:
    raw_model = dict(getattr(config, "raw_model", {}) or {})
    existing_blocks = raw_model.get(block_key)
    blocks = dict(existing_blocks or {}) if isinstance(existing_blocks, dict) else {}
    for block_name, raw_override in dict(overrides or {}).items():
        if block_name not in allowed_names or not isinstance(raw_override, dict):
            continue
        base_block = blocks.get(block_name)
        merged_block = dict(base_block or {}) if isinstance(base_block, dict) else {}
        model_text = str(raw_override.get("model") or "").strip().lower()
        for key, value in dict(raw_override).items():
            if key == "provider" and value in (None, ""):
                merged_block.pop("provider", None)
                continue
            merged_block[key] = value
        if (
            block_key == "delegation"
            and model_text in session_model_default_tokens
            and "reasoning_effort" not in raw_override
        ):
            merged_block.pop("reasoning_effort", None)
        if merged_block:
            blocks[block_name] = merged_block
    raw_model[block_key] = blocks
    try:
        return replace(config, raw_model=raw_model)
    except Exception:
        return config


def config_with_session_route_overrides(
    config: Any,
    overrides: Dict[str, Dict[str, Any]],
    *,
    standard_route_names: tuple[str, ...],
    session_model_default_tokens: set[str],
) -> Any:
    return config_with_session_block_overrides(
        config,
        block_key="routes",
        allowed_names=standard_route_names,
        overrides=overrides,
        session_model_default_tokens=session_model_default_tokens,
    )


def config_with_session_delegation_overrides(
    config: Any,
    overrides: Dict[str, Dict[str, Any]],
    *,
    standard_delegation_names: tuple[str, ...],
    session_model_default_tokens: set[str],
) -> Any:
    return config_with_session_block_overrides(
        config,
        block_key="delegation",
        allowed_names=standard_delegation_names,
        overrides=overrides,
        session_model_default_tokens=session_model_default_tokens,
    )


def resolve_delegate_execution(
    *,
    role_name: str,
    planner: Any,
    cwd: Optional[str],
    model: str | None,
    provider: str | None,
    reasoning_effort: str | None,
    timeout: Any,
    standard_delegation_names: tuple[str, ...],
    validate_reasoning_effort: Callable[[str], str],
    session_model_default_tokens: set[str],
    session_override_source: str,
    call_override_source: str = "call_override",
):
    normalized_role = validated_delegation_name(
        role_name,
        standard_delegation_names=standard_delegation_names,
    )
    planner_config = getattr(planner, "config", None)
    if planner is None or planner_config is None:
        raise RuntimeError("delegated agent unavailable: current provider is not configured")
    config = planner_config
    has_explicit_override = any(
        value not in (None, "")
        for value in (model, provider, reasoning_effort, timeout)
    )
    if has_explicit_override:
        override = delegation_override_payload(
            normalized_role,
            {
                "model": str(model or "").strip() or None,
                "provider": provider,
                "reasoning_effort": reasoning_effort,
                "timeout": timeout,
            },
            validate_reasoning_effort=validate_reasoning_effort,
            override_source=session_override_source,
        )
        if override:
            override["source"] = call_override_source
            config = config_with_session_delegation_overrides(
                config,
                {normalized_role: override},
                standard_delegation_names=standard_delegation_names,
                session_model_default_tokens=session_model_default_tokens,
            )
    return resolve_delegation_config(
        config,
        normalized_role,
        cwd=cwd,
    )
