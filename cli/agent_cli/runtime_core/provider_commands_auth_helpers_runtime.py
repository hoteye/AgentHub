from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


def provider_loader_kwargs(runtime: Any) -> dict[str, Any]:
    getter = getattr(getattr(runtime, "agent", None), "_provider_loader_kwargs", None)
    if callable(getter):
        try:
            return dict(getter() or {})
        except Exception:
            return {}
    cwd = getattr(runtime, "cwd", None)
    return {"cwd": cwd} if cwd is not None else {}


def load_provider_catalog(runtime: Any) -> Any | None:
    agent = getattr(runtime, "agent", None)
    if agent is None:
        return None
    loader = getattr(agent, "_load_provider_catalog", None)
    if not callable(loader):
        return None
    try:
        catalog = loader(**provider_loader_kwargs(runtime))
    except Exception:
        return None
    supplement = getattr(agent, "_supplement_provider_catalog", None)
    if callable(supplement):
        try:
            catalog = supplement(catalog)
        except Exception:
            pass
    return catalog


def provider_alias_maps(
    runtime: Any, *, catalog: Any
) -> tuple[dict[str, set[str]], dict[str, str]]:
    alias_to_configs: dict[str, set[str]] = {}
    public_by_config: dict[str, str] = {}
    for config_name in sorted(getattr(catalog, "providers", {}).keys()):
        alias_to_configs.setdefault(config_name, set()).add(config_name)
        public_by_config.setdefault(config_name, config_name)
    available_providers = getattr(getattr(runtime, "agent", None), "available_providers", None)
    if callable(available_providers):
        try:
            for item in list(available_providers() or []):
                if not isinstance(item, dict):
                    continue
                public_name = str(item.get("provider_name") or "").strip()
                config_name = str(item.get("config_provider_name") or public_name).strip()
                if not config_name:
                    continue
                alias_to_configs.setdefault(config_name, set()).add(config_name)
                if public_name:
                    alias_to_configs.setdefault(public_name, set()).add(config_name)
                    public_by_config[config_name] = public_name
        except Exception:
            pass
    return alias_to_configs, public_by_config


def resolve_context_auth_mode(auth_mode: Any, *, allowed_modes: set[str]) -> str:
    mode = str(auth_mode or "").strip().lower()
    if mode in allowed_modes:
        return mode
    return "-"


def resolve_auth_provider_context(
    runtime: Any,
    *,
    provider_override: str,
    default_auth_path: Path,
    allowed_modes: set[str],
) -> dict[str, Any]:
    status_getter = getattr(getattr(runtime, "agent", None), "provider_status", None)
    status = dict(status_getter() or {}) if callable(status_getter) else {}
    provider_auth_path = str(status.get("provider_auth_path") or default_auth_path).strip()
    provider_config_scope = str(status.get("provider_config_scope") or "").strip()
    provider_source = str(status.get("provider_source") or "").strip()
    provider_auth_write_path = (
        str(default_auth_path)
        if provider_config_scope == "project_local" or provider_source == "project_local"
        else provider_auth_path
    )
    requested = str(provider_override or "").strip()
    if not requested:
        for key in (
            "provider_route_name",
            "provider_public_name",
            "provider_name",
            "provider_label",
        ):
            candidate = str(status.get(key) or "").strip()
            if candidate and candidate != "-":
                requested = candidate
                break
    context = {
        "provider_name": requested or "-",
        "config_provider_name": requested or "-",
        "auth_mode": resolve_context_auth_mode(
            status.get("auth_mode"), allowed_modes=allowed_modes
        ),
        "auth": {},
        "base_url": str(status.get("provider_base_url") or "").strip(),
        "provider_auth_path": provider_auth_path,
        "provider_auth_write_path": provider_auth_write_path,
        "catalog_loaded": False,
    }
    catalog = load_provider_catalog(runtime)
    if catalog is None:
        return context
    context["catalog_loaded"] = True
    alias_to_configs, public_by_config = provider_alias_maps(runtime, catalog=catalog)
    candidates: set[str] = set()
    token = str(requested or "").strip().lower()
    if token:
        for alias, config_names in alias_to_configs.items():
            if str(alias).strip().lower() == token:
                candidates.update(config_names)
        if str(requested).strip() in getattr(catalog, "providers", {}):
            candidates.add(str(requested).strip())
    route_name = str(status.get("provider_route_name") or "").strip()
    if not candidates and route_name and route_name in getattr(catalog, "providers", {}):
        candidates.add(route_name)
    if not candidates:
        configured = str(status.get("provider_name") or "").strip()
        if configured and configured in getattr(catalog, "providers", {}):
            candidates.add(configured)
    if not candidates:
        return context
    config_name = sorted(candidates)[0]
    entry = getattr(catalog, "providers", {}).get(config_name)
    if entry is None:
        return context
    auth = dict(getattr(entry, "auth", {}) or {})
    context.update(
        {
            "provider_name": public_by_config.get(config_name, config_name),
            "config_provider_name": config_name,
            "auth_mode": resolve_context_auth_mode(
                getattr(entry, "auth_mode", context["auth_mode"]),
                allowed_modes=allowed_modes,
            ),
            "auth": auth,
            "base_url": str(getattr(entry, "base_url", "") or ""),
        }
    )
    return context


def token_ref_from_auth(auth: dict[str, Any], *, override: str = "") -> str:
    explicit = str(override or "").strip()
    if explicit:
        return explicit
    for key in ("token_ref", "session", "session_ref", "session_id"):
        token_ref = str(auth.get(key) or "").strip()
        if token_ref:
            return token_ref
    return "default"


def scope_text(auth: dict[str, Any]) -> str:
    scopes = auth.get("scopes")
    if isinstance(scopes, list):
        joined = " ".join(str(item).strip() for item in scopes if str(item).strip()).strip()
        if joined:
            return joined
    if isinstance(scopes, str) and scopes.strip():
        return scopes.strip()
    return str(auth.get("scope") or "").strip()


def resolve_oauth_endpoints(
    context: dict[str, Any],
    *,
    login_mode: str,
    force_discovery: bool,
    discovery_ttl_seconds: int,
    default_auth_path: Path,
    discover_wellknown_metadata_fn: Callable[..., dict[str, Any]],
) -> tuple[dict[str, str], dict[str, Any] | None]:
    auth = dict(context.get("auth") or {})
    token_endpoint = str(auth.get("token_endpoint") or "").strip()
    device_endpoint = str(auth.get("device_authorization_endpoint") or "").strip()
    authorization_endpoint = str(auth.get("authorization_endpoint") or "").strip()
    client_id = str(auth.get("client_id") or "").strip()
    client_secret = str(auth.get("client_secret") or "").strip()
    redirect_uri = str(auth.get("redirect_uri") or "").strip()
    scope = scope_text(auth)
    issuer = str(auth.get("issuer") or "").strip()
    metadata_url = str(auth.get("metadata_url") or "").strip()
    needs_discovery = bool(issuer or metadata_url) and (
        force_discovery
        or not token_endpoint
        or (login_mode == "device_code" and not device_endpoint)
        or (login_mode == "browser_pkce" and not authorization_endpoint)
    )
    discovery_payload: dict[str, Any] | None = None
    if needs_discovery:
        cache_base_path = Path(
            str(
                context.get("provider_auth_write_path")
                or context.get("provider_auth_path")
                or default_auth_path
            )
        )
        discovery_payload = discover_wellknown_metadata_fn(
            cache_path=cache_base_path.with_name("wellknown_cache.json"),
            issuer=issuer,
            metadata_url=metadata_url,
            ttl_seconds=max(60, int(discovery_ttl_seconds or 3600)),
        )
        if str(discovery_payload.get("status") or "").strip() in {"ok", "fallback_cached"}:
            token_endpoint = (
                token_endpoint or str(discovery_payload.get("token_endpoint") or "").strip()
            )
            device_endpoint = (
                device_endpoint
                or str(discovery_payload.get("device_authorization_endpoint") or "").strip()
            )
            authorization_endpoint = (
                authorization_endpoint
                or str(discovery_payload.get("authorization_endpoint") or "").strip()
            )
            issuer = issuer or str(discovery_payload.get("issuer") or "").strip()
            metadata_url = metadata_url or str(discovery_payload.get("metadata_url") or "").strip()
    return (
        {
            "token_endpoint": token_endpoint,
            "device_authorization_endpoint": device_endpoint,
            "authorization_endpoint": authorization_endpoint,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "issuer": issuer,
            "metadata_url": metadata_url,
        },
        discovery_payload,
    )


def auth_store_for_context(
    context: dict[str, Any],
    *,
    default_auth_path: Path,
    store_factory: Callable[..., Any],
) -> Any:
    auth_path = Path(
        str(
            context.get("provider_auth_write_path")
            or context.get("provider_auth_path")
            or default_auth_path
        )
    )
    return store_factory(store_path=auth_path)


def status_contract_for_non_session_mode(
    auth_mode: str,
    *,
    auth_command_hint_fn: Callable[..., str],
) -> tuple[str, str]:
    normalized = str(auth_mode or "").strip().lower()
    if normalized == "api_key":
        return (
            "api_key_external",
            "manage API key via env var and use /connect to update provider auth settings",
        )
    if normalized == "none":
        return ("not_required", "no auth token is required for the current provider mode")
    if normalized == "wellknown":
        return (
            "missing",
            f"run {auth_command_hint_fn('login', mode='browser_pkce')} to establish a session token",
        )
    if normalized == "oauth":
        return (
            "missing",
            f"run {auth_command_hint_fn('login', mode='device_code')} to establish a session token",
        )
    return ("unknown", "set auth mode with /connect, then run /auth status again")


def collect_refresh_contexts(
    runtime: Any,
    *,
    provider_filter: str,
    refresh_provider_context_factory: Callable[..., Any],
) -> list[Any]:
    catalog = load_provider_catalog(runtime)
    if catalog is None:
        return []
    alias_to_configs, _ = provider_alias_maps(runtime, catalog=catalog)
    filter_token = str(provider_filter or "").strip().lower()
    allowed: set[str] = set()
    if filter_token:
        for alias, config_names in alias_to_configs.items():
            if str(alias).strip().lower() == filter_token:
                allowed.update(config_names)
    contexts: list[Any] = []
    for config_name, entry in getattr(catalog, "providers", {}).items():
        if allowed and config_name not in allowed:
            continue
        auth_mode = str(getattr(entry, "auth_mode", "") or "").strip().lower()
        if auth_mode not in {"oauth", "wellknown"}:
            continue
        auth = dict(getattr(entry, "auth", {}) or {})
        token_ref = token_ref_from_auth(auth)
        token_endpoint = str(auth.get("token_endpoint") or "").strip()
        client_id = str(auth.get("client_id") or "").strip()
        if not token_endpoint or not client_id:
            continue
        contexts.append(
            refresh_provider_context_factory(
                provider_name=config_name,
                token_ref=token_ref,
                token_endpoint=token_endpoint,
                client_id=client_id,
                client_secret=str(auth.get("client_secret") or "").strip(),
                scope=scope_text(auth),
            )
        )
    return contexts


__all__ = [
    "auth_store_for_context",
    "collect_refresh_contexts",
    "load_provider_catalog",
    "provider_alias_maps",
    "provider_loader_kwargs",
    "resolve_auth_provider_context",
    "resolve_context_auth_mode",
    "resolve_oauth_endpoints",
    "scope_text",
    "status_contract_for_non_session_mode",
    "token_ref_from_auth",
]
