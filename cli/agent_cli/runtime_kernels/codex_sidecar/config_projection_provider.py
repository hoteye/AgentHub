from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from cli.agent_cli.providers.config.catalog import ProviderCatalogEntry
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection_models import (
    CODEX_AUTH_JSON_API_KEY,
    DEFAULT_SCRUBBED_AUTH_ENV_KEYS,
)

_BUILT_IN_CODEX_PROVIDER_IDS = frozenset(
    {
        "openai",
        "azure",
        "codex",
        "oss",
        "ollama",
        "lmstudio",
        "amazon-bedrock",
    }
)


def _project_provider_block(
    provider_name: str,
    provider: ProviderCatalogEntry,
    *,
    uses_codex_auth: bool,
) -> dict[str, Any]:
    raw_provider = dict(provider.raw_provider or {})
    projected: dict[str, Any] = {}
    display_name = str(provider.display_name or raw_provider.get("name") or provider_name).strip()
    if display_name:
        projected["name"] = display_name
    base_url = str(provider.base_url or raw_provider.get("base_url") or "").strip()
    if base_url:
        projected["base_url"] = base_url
    for source_key, target_key in (
        ("request_max_retries", "request_max_retries"),
        ("stream_max_retries", "stream_max_retries"),
        ("stream_idle_timeout_ms", "stream_idle_timeout_ms"),
        ("websocket_connect_timeout_ms", "websocket_connect_timeout_ms"),
        ("supports_websockets", "supports_websockets"),
    ):
        if source_key in raw_provider:
            projected[target_key] = raw_provider[source_key]
    for source_key in ("query_params", "http_headers"):
        value = raw_provider.get(source_key)
        if isinstance(value, Mapping) and value:
            projected[source_key] = dict(value)
    wire_api = str(provider.wire_api or raw_provider.get("wire_api") or "responses").strip().lower()
    projected["wire_api"] = "responses" if wire_api in {"", "openai_responses"} else wire_api
    projected["requires_openai_auth"] = _requires_openai_auth(
        provider,
        raw_provider,
        uses_codex_auth=uses_codex_auth,
    )
    return projected


def _provider_env_key(provider: ProviderCatalogEntry) -> str:
    keys = _provider_env_keys(provider)
    return keys[0] if keys else ""


def _provider_env_keys(provider: ProviderCatalogEntry) -> tuple[str, ...]:
    raw_provider = dict(provider.raw_provider or {})
    auth = provider.auth if isinstance(provider.auth, Mapping) else {}
    raw_auth = raw_provider.get("auth") if isinstance(raw_provider.get("auth"), Mapping) else {}
    raw_keys = (
        provider.api_key_env,
        auth.get("env_var"),
        auth.get("api_key_env"),
        raw_auth.get("env_var"),
        raw_auth.get("api_key_env"),
        raw_provider.get("api_key_env"),
        raw_provider.get("auth_key_name"),
    )
    keys: list[str] = []
    for raw_key in raw_keys:
        key = str(raw_key or "").strip()
        if key and key not in keys:
            keys.append(key)
    if _raw_requires_openai_auth(raw_provider) and CODEX_AUTH_JSON_API_KEY not in keys:
        keys.append(CODEX_AUTH_JSON_API_KEY)
    return tuple(keys)


def _project_auth_json(
    provider: ProviderCatalogEntry,
    *,
    auth_data: Mapping[str, Any] | None,
) -> dict[str, str]:
    for env_key in _provider_env_keys(provider):
        value = _auth_store_value(auth_data or {}, env_key)
        if value:
            return {CODEX_AUTH_JSON_API_KEY: value}
    return {}


def _sidecar_scrub_env_keys(provider: ProviderCatalogEntry) -> tuple[str, ...]:
    return _normalized_scrubbed_env_keys(
        (*DEFAULT_SCRUBBED_AUTH_ENV_KEYS, *_provider_env_keys(provider))
    )


def _normalized_scrubbed_env_keys(raw_keys: Any) -> tuple[str, ...]:
    keys: list[str] = []
    for raw_key in raw_keys or ():
        key = str(raw_key or "").strip()
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _auth_store_value(auth_data: Mapping[str, Any], env_key: str) -> str:
    normalized_env_key = str(env_key or "").strip()
    if not normalized_env_key:
        return ""
    value = str(auth_data.get(normalized_env_key) or "").strip()
    if value:
        return value
    api_keys = auth_data.get("api_keys")
    if isinstance(api_keys, Mapping):
        value = str(api_keys.get(normalized_env_key) or "").strip()
        if value:
            return value
    providers = auth_data.get("providers")
    if isinstance(providers, Mapping):
        for provider_payload in providers.values():
            if not isinstance(provider_payload, Mapping):
                continue
            value = str(provider_payload.get(normalized_env_key) or "").strip()
            if value:
                return value
            auth_payload = provider_payload.get("auth")
            if isinstance(auth_payload, Mapping):
                value = str(auth_payload.get(normalized_env_key) or "").strip()
                if value:
                    return value
    return ""


def _codex_provider_id(provider_name: str, provider: ProviderCatalogEntry) -> str:
    raw_provider = dict(provider.raw_provider or {})
    configured = str(
        raw_provider.get("codex_provider")
        or raw_provider.get("codex_provider_id")
        or raw_provider.get("sidecar_provider")
        or ""
    ).strip()
    if configured:
        return _slug(configured)
    normalized = _slug(provider_name)
    if normalized in _BUILT_IN_CODEX_PROVIDER_IDS and _provider_needs_custom_codex_id(provider):
        return f"agenthub-{normalized}"
    return normalized


def _provider_needs_custom_codex_id(provider: ProviderCatalogEntry) -> bool:
    raw_provider = dict(provider.raw_provider or {})
    return bool(
        str(provider.base_url or raw_provider.get("base_url") or "").strip()
        or str(provider.api_key_env or raw_provider.get("api_key_env") or "").strip()
        or str(raw_provider.get("auth_key_name") or "").strip()
        or raw_provider.get("requires_openai_auth") is False
    )


def _requires_openai_auth(
    provider: ProviderCatalogEntry,
    raw_provider: Mapping[str, Any],
    *,
    uses_codex_auth: bool,
) -> bool:
    if uses_codex_auth:
        return True
    raw_requires_auth = _raw_requires_openai_auth(raw_provider)
    if raw_requires_auth is not None:
        return raw_requires_auth
    return bool(_provider_env_keys(provider))


def _raw_requires_openai_auth(raw_provider: Mapping[str, Any]) -> bool | None:
    value = raw_provider.get("requires_openai_auth")
    if isinstance(value, bool):
        return value
    if "requires_openai_auth" in raw_provider:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
    return None


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower())
    normalized = normalized.strip("-_")
    return normalized or "agenthub-provider"
