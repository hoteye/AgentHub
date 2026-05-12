from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.runtime_core import (
    provider_commands_auth_login_helpers_runtime as provider_auth_login_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    provider_commands_auth_refresh_helpers_runtime as provider_auth_refresh_helpers_runtime,
)


def handle_auth_command(
    runtime: Any,
    *,
    arg_text: str,
    slash_invocation: Any | None = None,
    deps: Mapping[str, Any],
    auth_subcommands: set[str],
) -> tuple[str, list]:
    slash_inputs = deps["slash_invocation_inputs_fn"](slash_invocation)
    if slash_inputs is not None:
        _raw_tokens, positionals, options, _extras = slash_inputs
    else:
        parser = getattr(runtime, "_parse_args", None)
        if callable(parser):
            positionals, options = parser(arg_text)
        else:
            positionals, options = deps["parse_generic_args_fn"](arg_text)
    options = dict(options or {})

    if len(positionals) > 1:
        return (
            f"{deps['auth_usage_text_fn']()}\nerror_code=invalid_args\nerror_hint=expected at most one subcommand",
            [],
        )
    subcommand = str(positionals[0] if positionals else "status").strip().lower() or "status"
    if subcommand not in auth_subcommands:
        return (
            f"{deps['auth_usage_text_fn']()}\n"
            "error_code=invalid_subcommand\n"
            "error_hint=supported subcommands: status, login, refresh, logout\n"
            "next_action=/auth status",
            [],
        )

    provider_override = str(options.get("provider") or "").strip()
    context = deps["resolve_auth_provider_context_fn"](
        runtime,
        provider_override=provider_override,
    )
    provider_name = str(context.get("provider_name") or "-")
    config_provider_name = (
        str(context.get("config_provider_name") or provider_name).strip() or provider_name
    )
    auth_mode = deps["resolve_context_auth_mode_fn"](context.get("auth_mode"))
    auth = dict(context.get("auth") or {})
    token_ref = deps["token_ref_from_auth_fn"](
        auth,
        override=str(options.get("token-ref") or ""),
    )
    store = deps["auth_store_for_context_fn"](context)
    state: dict[str, Any] = {
        "subcommand": subcommand,
        "provider_override": provider_override,
        "context": context,
        "provider_name": provider_name,
        "config_provider_name": config_provider_name,
        "auth_mode": auth_mode,
        "auth": auth,
        "token_ref": token_ref,
        "store": store,
        "options": options,
    }

    if subcommand == "status":
        return _handle_auth_status(state=state, deps=deps)
    if subcommand == "logout":
        return _handle_auth_logout(state=state, deps=deps)

    if auth_mode not in {"oauth", "wellknown"}:
        lines = deps["build_auth_status_lines_fn"](
            subcommand=subcommand,
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="action_not_executed",
            next_action="/connect provider <name> model <selector> base-url <url> auth-mode oauth user",
        )
        lines.append("error_code=auth_mode_not_oauth")
        lines.append(
            f"error_hint=current auth_mode={auth_mode}; /auth {subcommand} requires oauth or wellknown mode"
        )
        return ("\n".join(lines), [])

    login_mode = str(options.get("mode") or "").strip().lower() or (
        "browser_pkce" if auth_mode == "wellknown" else "device_code"
    )
    if login_mode not in {"device_code", "browser_pkce"}:
        return (
            "\n".join(
                deps["build_auth_status_lines_fn"](
                    subcommand=subcommand,
                    provider_name=provider_name,
                    auth_mode=auth_mode,
                    auth_status="invalid",
                    next_action="use mode device_code or mode browser_pkce",
                )
                + ["error_code=invalid_mode"]
            ),
            [],
        )
    endpoints, discovery_payload = deps["resolve_oauth_endpoints_fn"](
        context,
        login_mode=login_mode,
        force_discovery=(auth_mode == "wellknown"),
        discovery_ttl_seconds=deps["safe_int_fn"](options.get("wellknown-ttl"), 3600),
    )
    if (
        discovery_payload is not None
        and str(discovery_payload.get("status") or "").strip() == "error"
    ):
        lines = deps["build_auth_status_lines_fn"](
            subcommand=subcommand,
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action="check wellknown issuer/metadata_url configuration and retry",
        )
        lines.append(
            f"error_code={str(discovery_payload.get('error') or 'wellknown_discovery_error')}"
        )
        return ("\n".join(lines), [])
    state["login_mode"] = login_mode
    state["endpoints"] = endpoints
    state["discovery_payload"] = discovery_payload

    if subcommand == "login":
        return provider_auth_login_helpers_runtime.handle_auth_login(state=state, deps=deps)
    if subcommand == "refresh":
        return provider_auth_refresh_helpers_runtime.handle_auth_refresh(
            runtime,
            state=state,
            deps=deps,
        )

    lines = deps["build_auth_status_lines_fn"](
        subcommand=subcommand,
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status="unknown",
        next_action="/auth status",
    )
    lines.append("error_code=unhandled_auth_command")
    return ("\n".join(lines), [])


def _handle_auth_status(
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    provider_name = str(state.get("provider_name") or "-")
    config_provider_name = str(state.get("config_provider_name") or provider_name)
    auth_mode = str(state.get("auth_mode") or "-")
    token_ref = str(state.get("token_ref") or "default")
    store = state.get("store")
    context = dict(state.get("context") or {})

    if auth_mode in {"oauth", "wellknown"}:
        session = store.get(config_provider_name, token_ref)
        status_value = deps["ensure_auth_session_status_fn"](
            deps["auth_session_status_fn"](session)
        )
        if status_value == "ready":
            next_action = deps["auth_command_hint_fn"]("refresh", provider_name=provider_name)
        elif status_value == "expired":
            next_action = deps["auth_command_hint_fn"]("refresh", provider_name=provider_name)
        elif auth_mode == "wellknown":
            next_action = deps["auth_command_hint_fn"](
                "login",
                provider_name=provider_name,
                mode="browser_pkce",
            )
        else:
            next_action = deps["auth_command_hint_fn"](
                "login",
                provider_name=provider_name,
                mode="device_code",
            )
        lines = deps["build_auth_status_lines_fn"](
            subcommand="status",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status=status_value,
            next_action=next_action,
        )
        lines.append(f"token_ref={token_ref}")
        store_path = str(
            getattr(store, "store_path", "")
            or context.get("provider_auth_write_path")
            or context.get("provider_auth_path")
            or ""
        )
        lines.append(f"token_source={store_path}:sessions")
        if session is not None and session.expires_at is not None:
            lines.append(f"expires_at={int(session.expires_at)}")
        return ("\n".join(lines), [])
    status_value, next_action = deps["status_contract_for_non_session_mode_fn"](auth_mode)
    lines = deps["build_auth_status_lines_fn"](
        subcommand="status",
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=status_value,
        next_action=next_action,
    )
    return ("\n".join(lines), [])


def _handle_auth_logout(
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    provider_name = str(state.get("provider_name") or "-")
    config_provider_name = str(state.get("config_provider_name") or provider_name)
    auth_mode = str(state.get("auth_mode") or "-")
    token_ref = str(state.get("token_ref") or "default")
    store = state.get("store")

    deleted = store.delete(config_provider_name, token_ref)
    lines = deps["build_auth_status_lines_fn"](
        subcommand="logout",
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status="logged_out" if deleted else "missing",
        next_action=deps["auth_command_hint_fn"]("status", provider_name=provider_name),
    )
    lines.append(f"token_ref={token_ref}")
    return ("\n".join(lines), [])
