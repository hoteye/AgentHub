from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.gateway_api.auth import resolve_gateway_auth_context as _resolve_gateway_auth_context_impl
from cli.agent_cli.gateway_protocol.auth_context import GatewayAuthContext, anonymous_auth_context
from cli.agent_cli.gateway_server.request_scope import gateway_request_scope
from cli.agent_cli.providers.model_routing import STANDARD_DELEGATION_NAMES

JsonMap = dict[str, Any]


def first_text(params: JsonMap, *names: str) -> str:
    for name in names:
        value = params.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
    return ""


def first_int(
    params: JsonMap,
    *names: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    for name in names:
        value = params.get(name)
        if value is None or value == "":
            continue
        try:
            return max(minimum, min(int(value), maximum))
        except (TypeError, ValueError):
            break
    return max(minimum, min(int(default), maximum))


def config_requested_runtime_policy(params: JsonMap) -> JsonMap:
    runtime_policy_raw = params.get("runtimePolicy")
    runtime_policy = dict(runtime_policy_raw) if isinstance(runtime_policy_raw, dict) else {}
    requested: JsonMap = {}
    for field in ("approval_policy", "sandbox_mode", "web_search_mode", "network_access"):
        if field in runtime_policy:
            requested[field] = runtime_policy[field]
        elif field in params:
            requested[field] = params[field]
    return requested


def config_requested_reasoning_effort(params: JsonMap) -> Any:
    if "reasoningEffort" in params:
        return params.get("reasoningEffort")
    if "reasoning_effort" in params:
        return params.get("reasoning_effort")
    return None


def config_requested_delegation_models(params: JsonMap) -> JsonMap:
    if "delegationModels" in params and isinstance(params.get("delegationModels"), dict):
        return dict(params.get("delegationModels") or {})
    if "delegation_models" in params and isinstance(params.get("delegation_models"), dict):
        return dict(params.get("delegation_models") or {})
    return {}


def delegation_requested_reasoning_effort(payload: JsonMap) -> Any:
    if "reasoningEffort" in payload:
        return payload.get("reasoningEffort")
    if "reasoning_effort" in payload:
        return payload.get("reasoning_effort")
    return None


def session_delegate_overrides(runtime: Any) -> JsonMap:
    getter = getattr(getattr(runtime, "agent", None), "session_delegate_overrides", None)
    if not callable(getter):
        return {}
    try:
        payload = getter()
    except Exception:
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def delegation_override_timeout(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def delegation_settings_snapshot(runtime: Any) -> JsonMap:
    provider_status = dict(getattr(runtime.agent, "provider_status", lambda: {})() or {})
    overrides = session_delegate_overrides(runtime)
    snapshot: JsonMap = {}
    for role_name in STANDARD_DELEGATION_NAMES:
        override = overrides.get(role_name)
        if not isinstance(override, dict):
            override = {}
        snapshot[role_name] = {
            "status": str(provider_status.get(f"delegate_{role_name}") or ""),
            "overrideActive": bool(override),
            "model": str(override.get("model") or ""),
            "provider": str(override.get("provider") or ""),
            "reasoningEffort": str(override.get("reasoning_effort") or ""),
            "timeout": delegation_override_timeout(override.get("timeout")),
            "source": str(override.get("source") or ""),
        }
    return snapshot


def known_model_tokens(runtime: Any) -> set[str]:
    available_models_getter = getattr(runtime.agent, "available_models", None)
    available_models = list(available_models_getter() or []) if callable(available_models_getter) else []
    return {
        str(item.get("model_key") or "").strip()
        for item in available_models
        if str(item.get("model_key") or "").strip()
    } | {
        str(item.get("model_id") or "").strip()
        for item in available_models
        if str(item.get("model_id") or "").strip()
    }


def normalized_delegation_signature(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    normalized: JsonMap = {}
    if bool(payload.get("clear")):
        normalized["clear"] = True
    else:
        if "model" in payload:
            normalized["model"] = str(payload.get("model") or "")
        if "provider" in payload:
            normalized["provider"] = str(payload.get("provider") or "")
        reasoning_effort = delegation_requested_reasoning_effort(payload)
        if reasoning_effort is not None:
            normalized["reasoningEffort"] = str(reasoning_effort or "")
        if "timeout" in payload:
            normalized["timeout"] = payload.get("timeout")
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False)


def current_delegation_signature(current_role: JsonMap) -> str:
    if not isinstance(current_role, dict) or not bool(current_role.get("overrideActive")):
        return normalized_delegation_signature({"clear": True})
    return normalized_delegation_signature(
        {
            "model": current_role.get("model"),
            "provider": current_role.get("provider"),
            "reasoningEffort": current_role.get("reasoningEffort"),
            "timeout": current_role.get("timeout"),
        }
    )


def resolve_gateway_auth_context(client_info: JsonMap | None) -> GatewayAuthContext:
    if client_info is None:
        return anonymous_auth_context(client_type="gateway")

    payload = dict(client_info or {})
    auth_payload = payload.get("gatewayAuth")
    if not isinstance(auth_payload, dict):
        auth_payload = payload.get("auth")
    if not isinstance(auth_payload, dict):
        auth_payload = payload

    has_explicit_auth = any(
        key in auth_payload
        for key in (
            "actorId",
            "actor_id",
            "role",
            "roles",
            "scopes",
            "authenticated",
            "authSource",
            "auth_source",
            "trustLevel",
            "trust_level",
        )
    )
    if not has_explicit_auth:
        actor_id = first_text(payload, "name", "clientId", "client_id") or "local-operator"
        return _resolve_gateway_auth_context_impl(
            actor_id=actor_id,
            role="operator",
            auth_source="local-app-server",
            trust_level="trusted",
            client_id=first_text(payload, "clientId", "client_id") or None,
            client_type=first_text(payload, "clientType", "client_type") or "app_server",
            metadata={"client_info": payload},
        )

    roles = auth_payload.get("roles")
    scopes = auth_payload.get("scopes")
    return _resolve_gateway_auth_context_impl(
        actor_id=first_text(auth_payload, "actorId", "actor_id") or "gateway-client",
        role=first_text(auth_payload, "role") or None,
        roles=roles if isinstance(roles, list) else None,
        scopes=scopes if isinstance(scopes, list) else None,
        tenant_id=first_text(auth_payload, "tenantId", "tenant_id") or None,
        auth_source=first_text(auth_payload, "authSource", "auth_source") or "gateway",
        trust_level=first_text(auth_payload, "trustLevel", "trust_level") or None,
        client_id=first_text(auth_payload, "clientId", "client_id") or first_text(payload, "name") or None,
        client_type=first_text(auth_payload, "clientType", "client_type") or "gateway",
        authenticated=bool(auth_payload.get("authenticated", True)),
        metadata={"client_info": payload},
    )


def build_gateway_request_scope(
    *,
    method: str,
    params: JsonMap,
    request_id: Any,
    client_info: JsonMap | None,
    auth: GatewayAuthContext,
):
    payload = dict(client_info or {})
    trace_id = first_text(params, "traceId", "trace_id") or first_text(payload, "traceId", "trace_id") or None
    correlation_id = (
        first_text(params, "correlationId", "correlation_id")
        or first_text(payload, "correlationId", "correlation_id")
        or str(request_id or "").strip()
        or None
    )
    return gateway_request_scope(
        request_id=str(request_id or method),
        method=method,
        ingress_kind="gateway_dispatcher",
        actor_id=auth.actor_id or "gateway-client",
        trace_id=trace_id,
        correlation_id=correlation_id,
        client_id=auth.client_id or first_text(payload, "clientId", "client_id") or None,
        conn_id=first_text(payload, "connId", "conn_id") or None,
        auth=auth.to_dict(),
        metadata={"client_info": payload},
    )
