from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def handle_connect_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: Any | None = None,
    parse_connect_args_fn: Callable[[str], tuple[list[str], dict[str, Any]]],
    slash_invocation_inputs_fn: Callable[[Any | None], tuple[list[str], list[str], dict[str, Any], list[str]] | None],
    connect_usage_text_fn: Callable[[], str],
    resolved_connect_auth_mode_fn: Callable[..., str],
    resolved_connect_api_key_env_fn: Callable[..., str],
    connect_requires_base_url_fn: Callable[[str], bool],
    connect_next_action_hint_fn: Callable[..., str],
    resolve_connect_write_path_fn: Callable[[Any, str], Path],
    save_user_model_selection_fn: Callable[..., Any],
    load_toml_document_text_fn: Callable[[Path], str],
    write_toml_document_text_fn: Callable[[Path, str], Path],
    upsert_provider_profile_fn: Callable[..., str],
    provider_profile_name_fn: Callable[..., str],
    upsert_provider_base_url_fn: Callable[..., str],
    upsert_provider_auth_fields_fn: Callable[..., str],
    clear_connect_provider_fields_fn: Callable[..., str],
    upsert_model_entry_fn: Callable[..., str],
    slash_command_text_fn: Callable[..., str],
    connect_auth_modes: set[str],
    connect_write_scopes: set[str],
) -> tuple[str, list]:
    slash_inputs = slash_invocation_inputs_fn(slash_invocation)
    if slash_inputs is not None:
        _raw_tokens, positionals, options, _extras = slash_inputs
    else:
        positionals, options = parse_connect_args_fn(arg_text)
    if positionals:
        return (connect_usage_text_fn(), [])
    provider_name = str(options.get("provider") or "").strip()
    model_selector = str(options.get("model") or "").strip()
    base_url = str(options.get("base-url") or "").strip()
    auth_mode = str(options.get("auth-mode") or "").strip().lower()
    api_key_env = str(options.get("api-key-env") or "").strip()
    resolved_auth_mode = resolved_connect_auth_mode_fn(
        provider_name=provider_name,
        auth_mode=auth_mode,
    )
    resolved_api_key_env = resolved_connect_api_key_env_fn(
        provider_name=provider_name,
        auth_mode=resolved_auth_mode,
        api_key_env=api_key_env,
    )
    write_scope = str(options.get("write") or "user").strip().lower() or "user"
    check_only = bool(options.get("check"))

    invalid_messages: list[str] = []
    if auth_mode and auth_mode not in connect_auth_modes:
        invalid_messages.append("invalid auth_mode")
    if write_scope not in connect_write_scopes:
        invalid_messages.append("invalid write scope")
    if invalid_messages:
        return (f"{connect_usage_text_fn()}\nerror={'; '.join(invalid_messages)}", [])

    missing: list[str] = []
    if not provider_name:
        missing.append("provider")
    if not model_selector:
        missing.append("model")
    if connect_requires_base_url_fn(provider_name) and not base_url:
        missing.append("base-url")
    if not resolved_auth_mode:
        missing.append("auth-mode")
    if resolved_auth_mode == "api_key" and not resolved_api_key_env:
        missing.append("api-key-env")

    lines = [
        "connect summary",
        f"provider_name={provider_name or '-'}",
        f"model={model_selector or '-'}",
        f"base_url={base_url or '-'}",
        f"auth_mode={resolved_auth_mode or '-'}",
        f"write_scope={write_scope}",
        f"check_only={'true' if check_only else 'false'}",
    ]
    next_action = connect_next_action_hint_fn(
        provider_name=provider_name,
        model_selector=model_selector,
        base_url=base_url,
        auth_mode=auth_mode,
        api_key_env=api_key_env,
        write_scope=write_scope,
    )
    if missing:
        lines.append(f"missing_args={','.join(missing)}")
        lines.append(f"next_action={next_action}")
        return ("\n".join(lines), [])

    write_path = resolve_connect_write_path_fn(runtime, write_scope)
    user_write_path = (
        write_path
        if write_scope == "user"
        else resolve_connect_write_path_fn(runtime, "user")
    )
    provider_profile = provider_profile_name_fn(
        provider_name=provider_name,
        base_url=base_url,
    )
    lines.append(f"config_path={write_path}")
    if user_write_path != write_path:
        lines.append(f"user_config_path={user_write_path}")
    lines.append(f"provider_profile={provider_profile}")
    if check_only:
        lines.append("connect_persisted=false")
        lines.append("next_action=run without check to persist")
        return ("\n".join(lines), [])

    if write_scope == "project":
        save_user_model_selection_fn(
            path=write_path,
            provider_name="",
            model=model_selector,
            provider_profile=provider_profile,
            default_provider_profile="",
        )
    else:
        save_user_model_selection_fn(
            path=write_path,
            provider_name=provider_name,
            model=model_selector,
            provider_profile="",
            default_provider_profile=provider_profile,
        )
    selection_existing = load_toml_document_text_fn(write_path)
    selection_updated = selection_existing
    selection_updated = clear_connect_provider_fields_fn(
        selection_updated,
        provider_name=provider_name,
        keys=("base_url", "auth_mode", "api_key_env"),
    )
    if write_scope != "project":
        selection_updated = upsert_model_entry_fn(
            selection_updated,
            provider_name=provider_name,
            model_selector=model_selector,
        )
    if selection_updated != selection_existing:
        write_toml_document_text_fn(write_path, selection_updated)

    if user_write_path == write_path:
        private_existing = selection_updated
    else:
        private_existing = load_toml_document_text_fn(user_write_path)
    private_updated = upsert_provider_base_url_fn(
        private_existing,
        provider_name=provider_name,
        base_url=base_url,
    )
    private_updated = upsert_provider_auth_fields_fn(
        private_updated,
        provider_name=provider_name,
        auth_mode=resolved_auth_mode,
        api_key_env=resolved_api_key_env,
    )
    private_updated = upsert_provider_profile_fn(
        private_updated,
        profile_name=provider_profile,
        provider_name=provider_name,
        model=model_selector,
        base_url=base_url,
        auth_mode=resolved_auth_mode,
        auth={"env_var": resolved_api_key_env},
    )
    if private_updated != private_existing:
        write_toml_document_text_fn(user_write_path, private_updated)
    lines.append("connect_persisted=true")
    lines.append(f"next_action={slash_command_text_fn('provider', 'verbose')}")
    return ("\n".join(lines), [])
