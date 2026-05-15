from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.providers.auth_session_runtime import (
    AuthSession,
    auth_session_status,
    ensure_auth_session_status,
)
from cli.agent_cli.providers.auth_token_encryption_runtime import decrypt_session_payload
from cli.agent_cli.providers.auth_token_store_runtime import token_store_key


def candidate_api_key_names(
    provider_name: str,
    provider_block: dict[str, Any],
    model: str,
    base_url: str | None,
) -> list[str]:
    names: list[str] = []
    fingerprint = " ".join(filter(None, (provider_name, model, base_url or ""))).lower()
    anthropic_like = "anthropic" in fingerprint or "claude" in fingerprint
    if anthropic_like:
        names.append("ANTHROPIC_AUTH_TOKEN")
    explicit_name = str(
        provider_block.get("api_key_env") or provider_block.get("auth_key_name") or ""
    ).strip()
    if explicit_name:
        names.append(explicit_name)
    if provider_name:
        names.append(f"{provider_name.upper().replace('-', '_')}_API_KEY")
    if anthropic_like:
        names.append("ANTHROPIC_API_KEY")
    if "deepseek" in fingerprint:
        names.append("DEEPSEEK_API_KEY")
    names.append("AGENT_CLI_API_KEY")
    if not explicit_name or explicit_name == "OPENAI_API_KEY":
        names.append("OPENAI_API_KEY")
    unique: list[str] = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    return unique


def first_configured_key(mapping: Mapping[str, Any], names: list[str]) -> str:
    for name in names:
        value = str(mapping.get(name) or "").strip()
        if value:
            return value
    return ""


def first_configured_key_name(mapping: Mapping[str, Any], names: list[str]) -> str:
    for name in names:
        value = str(mapping.get(name) or "").strip()
        if value:
            return name
    return ""


def _first_env_value(env_mapping: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = str(env_mapping.get(name) or "").strip()
        if value:
            return value
    return ""


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _aliased_mapping_value(mapping: Mapping[str, Any], snake_key: str, camel_key: str) -> Any:
    if snake_key in mapping:
        return mapping.get(snake_key)
    if camel_key in mapping:
        return mapping.get(camel_key)
    return None


def _resolve_token_ref(provider_block: Mapping[str, Any]) -> str:
    auth_block = provider_block.get("auth")
    auth_mapping = auth_block if isinstance(auth_block, Mapping) else {}
    for key in ("token_ref", "session", "session_ref", "session_id"):
        value = str(auth_mapping.get(key) or provider_block.get(key) or "").strip()
        if value:
            return value
    return ""


def _session_from_payload(payload: Any, *, auth_path: Path | None) -> AuthSession | None:
    if not isinstance(payload, Mapping):
        return None
    normalized_payload = (
        decrypt_session_payload(payload, store_path=auth_path)
        if auth_path is not None
        else dict(payload)
    )
    if not isinstance(normalized_payload, Mapping):
        return None
    try:
        session = AuthSession.from_mapping(normalized_payload)
    except Exception:
        return None
    if not session.provider_name or not session.token_ref:
        return None
    return session


def _resolve_oauth_access_token(
    *,
    provider_name: str,
    provider_block: Mapping[str, Any],
    auth_mode: str,
    auth_data: Mapping[str, Any],
    auth_path: Path | None,
) -> tuple[str, str, str]:
    if auth_mode not in {"oauth", "wellknown"}:
        return "", "", ""
    token_ref = _resolve_token_ref(provider_block)
    if not token_ref:
        return "", "missing", ""

    sessions_block = auth_data.get("sessions")
    if not isinstance(sessions_block, Mapping):
        return "", "missing", "token_store.sessions"

    primary_key = token_store_key(provider_name, token_ref)
    candidate_payload = sessions_block.get(primary_key)
    source = "token_store.sessions"
    if not isinstance(candidate_payload, Mapping):
        fallback_payload = sessions_block.get(token_ref)
        if isinstance(fallback_payload, Mapping):
            candidate_payload = fallback_payload
            source = "token_store.sessions_fallback"
    session = _session_from_payload(candidate_payload, auth_path=auth_path)
    if session is None:
        return "", "missing", source

    status = ensure_auth_session_status(auth_session_status(session))
    if status == "ready" and session.access_token:
        return session.access_token, status, source
    return "", status, source
