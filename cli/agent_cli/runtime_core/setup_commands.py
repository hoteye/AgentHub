from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from cli.agent_cli import provider as provider_module
from cli.agent_cli.provider_persistence_paths_runtime import (
    persist_provider_auth_value,
    resolve_private_provider_auth_write_path,
    resolve_user_provider_auth_path,
    resolve_user_provider_config_path,
)
from cli.agent_cli.runtime_core import provider_commands as provider_commands_module
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.slash_surface import compat_normalize_arg_tokens, surface_usage_text

_VALID_WRITE_SCOPES = {"user", "project"}
_SETUP_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.4",
}
_SETUP_BLOCKED_PROVIDER_STATES = {
    "auth_blocked",
    "hard_unavailable",
}


def _usage_text() -> str:
    return f"Usage: {surface_usage_text('setup')}"


def _next_setup_command(provider_name: str = "openai") -> str:
    return _stringify_command("setup", "provider", provider_name, "api-key", "YOUR_API_KEY")


def _normalized_setup_arg_text(arg_text: str) -> str:
    raw = str(arg_text or "").strip()
    if not raw:
        return ""
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError:
        return raw
    normalized = compat_normalize_arg_tokens("setup", tokens)
    return shlex.join(normalized) if normalized else ""


def _stringify_command(*parts: str) -> str:
    normalized = [str(part or "").strip() for part in parts if str(part or "").strip()]
    if not normalized:
        return "/setup"
    return "/" + " ".join(shlex.quote(part) for part in normalized)


def _default_model_selector(runtime: Any, *, provider_name: str) -> str:
    normalized_provider = str(provider_name or "").strip()
    if not normalized_provider:
        return ""
    try:
        catalog = provider_module.load_provider_catalog(cwd=getattr(runtime, "cwd", None))
    except Exception:
        return _SETUP_DEFAULT_MODELS.get(normalized_provider.lower(), "")
    try:
        entry = provider_module._default_model_entry(normalized_provider, catalog)
    except Exception:
        entry = None
    resolved = str(getattr(entry, "model_id", "") or "").strip()
    if resolved:
        return resolved
    return _SETUP_DEFAULT_MODELS.get(normalized_provider.lower(), "")


def _resolved_api_key_env(provider_name: str) -> str:
    resolved = str(
        provider_commands_module._resolved_connect_api_key_env(
            provider_name=str(provider_name or "").strip(),
            auth_mode="api_key",
            api_key_env="",
        )
        or ""
    ).strip()
    if resolved:
        return resolved
    normalized_provider = str(provider_name or "").strip().upper().replace("-", "_")
    return f"{normalized_provider}_API_KEY" if normalized_provider else "OPENAI_API_KEY"


def _persist_api_key_secret(*, auth_path: Path, auth_key_name: str, api_key: str) -> None:
    persist_provider_auth_value(
        key=auth_key_name,
        value=api_key,
        path=auth_path,
    )


def _setup_status_text(runtime: Any) -> str:
    try:
        snapshot = provider_module.load_provider_management_snapshot(
            cwd=getattr(runtime, "cwd", None)
        )
    except Exception as exc:
        return f"setup status\nstate=error\nerror={exc}"

    selected = getattr(snapshot, "selected_config", None)
    resolution = getattr(snapshot, "resolution", None)
    config_path = Path(getattr(resolution, "config_path", resolve_user_provider_config_path()))
    auth_path = Path(getattr(resolution, "auth_path", resolve_user_provider_auth_path()))
    config_exists = bool(getattr(resolution, "config_exists", config_path.exists()))
    auth_exists = bool(getattr(resolution, "auth_exists", auth_path.exists()))
    provider_name = str(getattr(selected, "provider_name", "") or "").strip()
    model = str(getattr(selected, "model", "") or "").strip()
    auth_mode = str(getattr(selected, "auth_mode", "") or "").strip().lower() or "-"
    has_api_key = bool(str(getattr(selected, "api_key", "") or "").strip())
    provider_status: dict[str, Any] = {}
    provider_status_fn = getattr(getattr(runtime, "agent", None), "provider_status", None)
    if callable(provider_status_fn):
        try:
            provider_status = dict(provider_status_fn() or {})
        except Exception:
            provider_status = {}
    provider_state = str(provider_status.get("provider_status_state") or "").strip().lower()
    provider_hard_unavailable = (
        str(provider_status.get("provider_hard_unavailable") or "").strip().lower() == "true"
    )

    if selected is None:
        state = "unconfigured" if not config_exists and not auth_exists else "recoverable"
        next_action = "/setup"
    elif auth_mode == "api_key" and not has_api_key:
        state = "missing_api_key"
        next_action = _next_setup_command(provider_name or "openai")
    elif provider_hard_unavailable or provider_state in _SETUP_BLOCKED_PROVIDER_STATES:
        state = provider_state or "hard_unavailable"
        next_action = _next_setup_command(provider_name or "openai")
    else:
        state = "ready"
        next_action = "/provider verbose"

    lines = [
        "setup status",
        f"state={state}",
        f"config_path={config_path}",
        f"auth_path={auth_path}",
        f"config_exists={'true' if config_exists else 'false'}",
        f"auth_exists={'true' if auth_exists else 'false'}",
        f"provider_name={provider_name or '-'}",
        f"model={model or '-'}",
        f"auth_mode={auth_mode}",
        f"next_action={next_action}",
    ]
    return "\n".join(lines)


def _build_connect_arg_text(
    *,
    provider_name: str,
    model: str,
    base_url: str,
    auth_key_name: str,
    write_scope: str,
    check_only: bool,
) -> str:
    parts = [
        "--provider",
        provider_name,
        "--model",
        model,
        "--auth-mode",
        "api_key",
        "--api-key-env",
        auth_key_name,
        "--write",
        write_scope,
    ]
    if str(base_url or "").strip():
        parts.extend(["--base-url", str(base_url).strip()])
    if check_only:
        parts.append("--check")
    return shlex.join(parts)


def handle_setup_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
) -> tuple[str, list[Any]] | None:
    if name != "setup":
        return None
    normalized_arg_text = _normalized_setup_arg_text(arg_text)
    positionals, options = parse_args(normalized_arg_text)
    if positionals:
        if positionals == ["status"]:
            return (_setup_status_text(runtime), [])
        return (_usage_text(), [])

    if not normalized_arg_text:
        return (
            "\n".join(
                [
                    "setup",
                    "mode=api_key",
                    "required=provider,api-key",
                    "optional=base-url,model,user|project,check",
                    f"next_action={_next_setup_command()}",
                ]
            ),
            [],
        )

    provider_name = str(options.get("provider") or "").strip()
    model = str(options.get("model") or "").strip()
    base_url = str(options.get("base-url") or "").strip()
    api_key = str(options.get("api-key") or "").strip()
    write_scope = str(options.get("write") or "user").strip().lower() or "user"
    check_only = bool(options.get("check"))

    if write_scope not in _VALID_WRITE_SCOPES:
        return (f"{_usage_text()}\nerror=invalid write scope", [])

    if not model:
        model = _default_model_selector(runtime, provider_name=provider_name)
    auth_key_name = _resolved_api_key_env(provider_name)

    missing: list[str] = []
    if not provider_name:
        missing.append("provider")
    if not api_key:
        missing.append("api-key")
    if not model:
        missing.append("model")

    lines = [
        "setup summary",
        f"provider_name={provider_name or '-'}",
        f"model={model or '-'}",
        f"base_url={base_url or '-'}",
        f"write_scope={write_scope}",
        f"check_only={'true' if check_only else 'false'}",
    ]
    if missing:
        lines.append(f"missing_args={','.join(missing)}")
        lines.append(f"next_action={_next_setup_command(provider_name or 'openai')}")
        return ("\n".join(lines), [])

    connect_arg_text = _build_connect_arg_text(
        provider_name=provider_name,
        model=model,
        base_url=base_url,
        auth_key_name=auth_key_name,
        write_scope=write_scope,
        check_only=check_only,
    )
    connect_result = provider_commands_module.handle_provider_command(
        runtime,
        name="connect",
        arg_text=connect_arg_text,
        switch_disabled_result=lambda exc: (str(exc), []),
    )
    if connect_result is None:
        return ("setup failed\nerror=connect handler unavailable", [])
    connect_text, events = connect_result
    connect_text = str(connect_text or "")
    if check_only:
        return (f"{connect_text}\nauth_persisted=false", list(events or []))

    auth_path = resolve_private_provider_auth_write_path()
    _persist_api_key_secret(
        auth_path=auth_path,
        auth_key_name=auth_key_name,
        api_key=api_key,
    )
    return (
        "\n".join(
            [
                connect_text,
                f"auth_path={auth_path}",
                f"auth_key={auth_key_name}",
                "auth_persisted=true",
            ]
        ),
        list(events or []),
    )
