from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli import provider_catalog_runtime
from cli.agent_cli.provider_persistence_paths_runtime import (
    resolve_project_provider_config_write_path,
    resolve_user_provider_config_path,
)
from cli.agent_cli.slash_surface import surface_usage_text

_VALID_AUTH_MODES = {"api_key", "oauth", "wellknown", "none"}
_VALID_WRITE_SCOPES = {"user", "project"}
_CONNECT_OFFICIAL_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "auth_mode": "api_key",
        "api_key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "auth_mode": "api_key",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
}


def _usage_text() -> str:
    return f"Usage: {surface_usage_text('connect')}"


def _provider_defaults(provider_name: str) -> dict[str, str]:
    normalized = str(provider_name or "").strip().lower()
    defaults = _CONNECT_OFFICIAL_PROVIDER_DEFAULTS.get(normalized)
    return dict(defaults or {})


def _resolved_auth_mode(*, provider_name: str, auth_mode: str) -> str:
    normalized = str(auth_mode or "").strip().lower()
    if normalized:
        return normalized
    return _provider_defaults(provider_name).get("auth_mode", "")


def _resolved_api_key_env(*, provider_name: str, auth_mode: str, api_key_env: str) -> str:
    normalized = str(api_key_env or "").strip()
    if normalized:
        return normalized
    if str(auth_mode or "").strip().lower() != "api_key":
        return ""
    return _provider_defaults(provider_name).get("api_key_env", "")


def _requires_base_url(provider_name: str) -> bool:
    return not bool(_provider_defaults(provider_name))


def _next_action(
    *,
    provider_name: str,
    model: str,
    base_url: str,
    auth_mode: str,
    api_key_env: str,
    write_scope: str,
) -> str:
    parts = ["/connect", f"provider {provider_name or '<name>'}", f"model {model or '<selector>'}"]
    has_defaults = bool(_provider_defaults(provider_name))
    explicit_auth_mode = str(auth_mode or "").strip().lower()
    explicit_api_key_env = str(api_key_env or "").strip()
    resolved_auth_mode = _resolved_auth_mode(provider_name=provider_name, auth_mode=explicit_auth_mode)
    resolved_api_key_env = _resolved_api_key_env(
        provider_name=provider_name,
        auth_mode=resolved_auth_mode,
        api_key_env=explicit_api_key_env,
    )

    if base_url or _requires_base_url(provider_name):
        parts.append(f"base-url {base_url or '<url>'}")
    if explicit_auth_mode:
        parts.append(f"auth-mode {explicit_auth_mode}")
    elif not has_defaults:
        parts.append("auth-mode <mode>")

    if explicit_api_key_env:
        parts.append(f"api-key-env {explicit_api_key_env}")
    elif explicit_auth_mode == "api_key":
        parts.append(f"api-key-env {resolved_api_key_env or '<ENV>'}")
    elif not explicit_auth_mode and not has_defaults:
        parts.append("api-key-env <ENV>")

    parts.append(write_scope)
    return " ".join(parts)


def _resolve_write_path(runtime: Any, write_scope: str) -> Path:
    normalized = str(write_scope or "").strip().lower() or "user"
    if normalized == "project":
        return resolve_project_provider_config_write_path(
            cwd=getattr(runtime, "cwd", None),
        )
    return resolve_user_provider_config_path()


def _parse_connect_args(runtime: Any, arg_text: str) -> tuple[list[str], dict[str, Any]]:
    parse_args = getattr(runtime, "_parse_args", None)
    if callable(parse_args):
        return parse_args(arg_text)
    return [], {}


def handle_connect_command(runtime: Any, *, arg_text: str) -> tuple[str, list[Any]]:
    positionals, options = _parse_connect_args(runtime, arg_text)
    if positionals:
        return (_usage_text(), [])

    provider_name = str(options.get("provider") or "").strip()
    model = str(options.get("model") or "").strip()
    base_url = str(options.get("base-url") or "").strip()
    auth_mode = str(options.get("auth-mode") or "").strip().lower()
    api_key_env = str(options.get("api-key-env") or "").strip()
    resolved_auth_mode = _resolved_auth_mode(provider_name=provider_name, auth_mode=auth_mode)
    resolved_api_key_env = _resolved_api_key_env(
        provider_name=provider_name,
        auth_mode=resolved_auth_mode,
        api_key_env=api_key_env,
    )
    write_scope = str(options.get("write") or "user").strip().lower() or "user"
    check_only = bool(options.get("check"))

    if write_scope not in _VALID_WRITE_SCOPES:
        return (f"{_usage_text()}\ninvalid_write_scope={write_scope or '-'}", [])
    if auth_mode and auth_mode not in _VALID_AUTH_MODES:
        return (f"{_usage_text()}\ninvalid_auth_mode={auth_mode}", [])

    missing: list[str] = []
    if not provider_name:
        missing.append("provider")
    if not model:
        missing.append("model")
    if _requires_base_url(provider_name) and not base_url:
        missing.append("base-url")
    if not resolved_auth_mode:
        missing.append("auth-mode")
    if resolved_auth_mode == "api_key" and not resolved_api_key_env:
        missing.append("api-key-env")

    if missing:
        return (
            "\n".join(
                [
                    "connect summary",
                    f"provider_name={provider_name or '-'}",
                    f"model={model or '-'}",
                    f"base_url={base_url or '-'}",
                    f"auth_mode={resolved_auth_mode or '-'}",
                    f"write_scope={write_scope}",
                    f"check_only={'true' if check_only else 'false'}",
                    f"missing_args={','.join(missing)}",
                    f"next_action={_next_action(provider_name=provider_name, model=model, base_url=base_url, auth_mode=auth_mode, api_key_env=api_key_env, write_scope=write_scope)}",
                ]
            ),
            [],
        )

    auth_payload: dict[str, Any] = {}
    if resolved_auth_mode == "api_key" and resolved_api_key_env:
        auth_payload["env_var"] = resolved_api_key_env

    target_path = _resolve_write_path(runtime, write_scope)
    if check_only:
        return (
            "\n".join(
                [
                    "connect summary",
                    f"provider_name={provider_name}",
                    f"model={model}",
                    f"base_url={base_url or '-'}",
                    f"auth_mode={resolved_auth_mode}",
                    f"write_scope={write_scope}",
                    f"config_path={target_path}",
                    "check_only=true",
                    "connect_persisted=false",
                    "next_action=run without check to persist",
                ]
            ),
            [],
        )

    provider_catalog_runtime.save_user_model_selection(
        path=target_path,
        provider_name=provider_name,
        model=model,
        provider_base_url=base_url or None,
        provider_name_for_auth=provider_name,
        auth_mode=resolved_auth_mode,
        auth=auth_payload,
    )

    return (
        "\n".join(
            [
                "connect summary",
                "connect_persisted=true",
                f"config_path={target_path}",
                f"provider_name={provider_name}",
                f"model={model}",
                f"base_url={base_url or '-'}",
                f"auth_mode={resolved_auth_mode}",
                f"write_scope={write_scope}",
                "next_action=/provider verbose",
            ]
        ),
        [],
    )
