from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

_AUTH_MODES = {"api_key", "oauth", "wellknown", "none"}


@dataclass(frozen=True)
class ProviderAuthSchema:
    auth_mode: str
    auth: Dict[str, Any]


def normalize_auth_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in _AUTH_MODES:
        return mode
    return "api_key"


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _scopes(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def provider_auth_schema(provider_block: Mapping[str, Any]) -> ProviderAuthSchema:
    auth_block = dict(_as_mapping(provider_block.get("auth")))
    mode = normalize_auth_mode(provider_block.get("auth_mode") or auth_block.get("mode"))
    if not str(provider_block.get("auth_mode") or "").strip():
        if _as_str(provider_block.get("api_key_env") or provider_block.get("auth_key_name")):
            mode = "api_key"
        elif _as_str(provider_block.get("oauth_token_endpoint") or provider_block.get("oauth_client_id")):
            mode = "oauth"
        elif _as_str(provider_block.get("wellknown_issuer") or provider_block.get("wellknown_metadata_url")):
            mode = "wellknown"
        elif str(provider_block.get("allow_no_auth") or "").strip().lower() in {"1", "true", "yes", "on"}:
            mode = "none"

    if mode == "api_key":
        env_var = (
            _as_str(auth_block.get("env_var"))
            or _as_str(auth_block.get("api_key_env"))
            or _as_str(provider_block.get("api_key_env") or provider_block.get("auth_key_name"))
        )
        value_ref = _as_str(auth_block.get("value_ref"))
        auth: Dict[str, Any] = {}
        if env_var:
            auth["env_var"] = env_var
        if value_ref:
            auth["value_ref"] = value_ref
        return ProviderAuthSchema(auth_mode="api_key", auth=auth)

    if mode == "oauth":
        client_id = _as_str(auth_block.get("client_id") or provider_block.get("oauth_client_id"))
        client_secret = _as_str(auth_block.get("client_secret") or provider_block.get("oauth_client_secret"))
        token_endpoint = _as_str(auth_block.get("token_endpoint") or provider_block.get("oauth_token_endpoint"))
        device_authorization_endpoint = _as_str(
            auth_block.get("device_authorization_endpoint")
            or provider_block.get("oauth_device_authorization_endpoint")
            or provider_block.get("device_authorization_endpoint")
        )
        authorization_endpoint = _as_str(
            auth_block.get("authorization_endpoint")
            or provider_block.get("oauth_authorization_endpoint")
            or provider_block.get("authorization_endpoint")
        )
        redirect_uri = _as_str(auth_block.get("redirect_uri") or provider_block.get("oauth_redirect_uri"))
        scopes = _scopes(auth_block.get("scopes") or provider_block.get("oauth_scopes"))
        auth = {}
        if client_id:
            auth["client_id"] = client_id
        if client_secret:
            auth["client_secret"] = client_secret
        if token_endpoint:
            auth["token_endpoint"] = token_endpoint
        if device_authorization_endpoint:
            auth["device_authorization_endpoint"] = device_authorization_endpoint
        if authorization_endpoint:
            auth["authorization_endpoint"] = authorization_endpoint
        if redirect_uri:
            auth["redirect_uri"] = redirect_uri
        if scopes:
            auth["scopes"] = scopes
        return ProviderAuthSchema(auth_mode="oauth", auth=auth)

    if mode == "wellknown":
        issuer = _as_str(auth_block.get("issuer") or provider_block.get("wellknown_issuer"))
        metadata_url = _as_str(auth_block.get("metadata_url") or provider_block.get("wellknown_metadata_url"))
        client_id = _as_str(auth_block.get("client_id") or provider_block.get("oauth_client_id"))
        client_secret = _as_str(auth_block.get("client_secret") or provider_block.get("oauth_client_secret"))
        redirect_uri = _as_str(auth_block.get("redirect_uri") or provider_block.get("oauth_redirect_uri"))
        token_endpoint = _as_str(auth_block.get("token_endpoint") or provider_block.get("oauth_token_endpoint"))
        device_authorization_endpoint = _as_str(
            auth_block.get("device_authorization_endpoint")
            or provider_block.get("oauth_device_authorization_endpoint")
            or provider_block.get("device_authorization_endpoint")
        )
        authorization_endpoint = _as_str(
            auth_block.get("authorization_endpoint")
            or provider_block.get("oauth_authorization_endpoint")
            or provider_block.get("authorization_endpoint")
        )
        scopes = _scopes(auth_block.get("scopes") or provider_block.get("oauth_scopes"))
        auth = {}
        if issuer:
            auth["issuer"] = issuer
        if metadata_url:
            auth["metadata_url"] = metadata_url
        if client_id:
            auth["client_id"] = client_id
        if client_secret:
            auth["client_secret"] = client_secret
        if redirect_uri:
            auth["redirect_uri"] = redirect_uri
        if token_endpoint:
            auth["token_endpoint"] = token_endpoint
        if device_authorization_endpoint:
            auth["device_authorization_endpoint"] = device_authorization_endpoint
        if authorization_endpoint:
            auth["authorization_endpoint"] = authorization_endpoint
        if scopes:
            auth["scopes"] = scopes
        return ProviderAuthSchema(auth_mode="wellknown", auth=auth)

    return ProviderAuthSchema(auth_mode="none", auth={})


def apply_typed_auth_to_provider_block(provider_block: Mapping[str, Any]) -> Dict[str, Any]:
    projected = dict(provider_block)
    schema = provider_auth_schema(provider_block)
    projected["auth_mode"] = schema.auth_mode
    projected["auth"] = dict(schema.auth)
    if schema.auth_mode == "api_key":
        env_var = str(schema.auth.get("env_var") or "").strip()
        if env_var:
            projected["api_key_env"] = env_var
    return projected
