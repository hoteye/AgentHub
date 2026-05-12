from __future__ import annotations

from typing import Any, Mapping


def handle_auth_login(
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    login_mode = str(state.get("login_mode") or "").strip().lower()
    if login_mode == "device_code":
        return _handle_auth_login_device_code(state=state, deps=deps)
    return _handle_auth_login_browser_pkce(state=state, deps=deps)


def _handle_auth_login_device_code(
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    options = dict(state.get("options") or {})
    store = state.get("store")
    config_provider_name = str(state.get("config_provider_name") or "")
    token_ref = str(state.get("token_ref") or "")
    provider_name = str(state.get("provider_name") or "-")
    auth_mode = str(state.get("auth_mode") or "-")
    context = dict(state.get("context") or {})
    endpoints = dict(state.get("endpoints") or {})
    build_auth_status_lines_fn = deps["build_auth_status_lines_fn"]
    auth_command_hint_fn = deps["auth_command_hint_fn"]
    is_truthy_fn = deps["is_truthy_fn"]
    safe_int_fn = deps["safe_int_fn"]

    if is_truthy_fn(options.get("poll")):
        pending = store.get(config_provider_name, token_ref)
        pending_metadata = dict(pending.metadata or {}) if pending is not None else {}
        device_code = str(pending_metadata.get("device_code") or "").strip()
        token_endpoint = str(
            pending_metadata.get("token_endpoint") or endpoints.get("token_endpoint") or ""
        ).strip()
        client_id = str(pending_metadata.get("client_id") or endpoints.get("client_id") or "").strip()
        if not device_code or not token_endpoint or not client_id:
            lines = build_auth_status_lines_fn(
                subcommand="login",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status="missing",
                next_action=auth_command_hint_fn(
                    "login",
                    provider_name=provider_name,
                    mode="device_code",
                ),
            )
            lines.append("error_code=no_pending_device_flow")
            return ("\n".join(lines), [])
        poll_result = dict(
            deps["poll_device_flow_fn"](
                token_endpoint=token_endpoint,
                client_id=client_id,
                client_secret=str(endpoints.get("client_secret") or "").strip() or None,
                device_code=device_code,
                scope=str(endpoints.get("scope") or "").strip() or None,
            )
            or {}
        )
        poll_status = str(poll_result.get("status") or "").strip()
        if poll_status == "authorized":
            metadata = dict(pending_metadata)
            metadata.pop("device_code", None)
            metadata["token_endpoint"] = token_endpoint
            metadata["client_id"] = client_id
            saved = deps["save_session_from_oauth_result_fn"](
                store=store,
                context=context,
                token_ref=token_ref,
                oauth_result=poll_result,
                metadata=metadata,
            )
            lines = build_auth_status_lines_fn(
                subcommand="login",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status=deps["ensure_auth_session_status_fn"](
                    deps["auth_session_status_fn"](saved)
                ),
                next_action=auth_command_hint_fn("status", provider_name=provider_name),
            )
            lines.append(f"token_ref={token_ref}")
            return ("\n".join(lines), [])
        if poll_status in {"pending", "slow_down"}:
            lines = build_auth_status_lines_fn(
                subcommand="login",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status=poll_status,
                next_action=auth_command_hint_fn(
                    "login",
                    provider_name=provider_name,
                    mode="device_code",
                    poll=True,
                ),
            )
            lines.append(f"retry_after_seconds={safe_int_fn(poll_result.get('retry_after_seconds'), 0)}")
            lines.append(f"error_code={str(poll_result.get('error_code') or poll_status)}")
            return ("\n".join(lines), [])
        if poll_status == "expired":
            lines = build_auth_status_lines_fn(
                subcommand="login",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status="expired",
                next_action=auth_command_hint_fn(
                    "login",
                    provider_name=provider_name,
                    mode="device_code",
                ),
            )
            lines.append(f"error_code={str(poll_result.get('error_code') or 'expired_token')}")
            return ("\n".join(lines), [])
        lines = build_auth_status_lines_fn(
            subcommand="login",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action=auth_command_hint_fn(
                "login",
                provider_name=provider_name,
                mode="device_code",
            ),
        )
        lines.append(f"error_code={str(poll_result.get('error_code') or 'oauth_poll_error')}")
        lines.append(f"error_hint={str(poll_result.get('error_description') or '').strip()}")
        return ("\n".join(lines), [])

    device_endpoint = str(endpoints.get("device_authorization_endpoint") or "").strip()
    token_endpoint = str(endpoints.get("token_endpoint") or "").strip()
    client_id = str(endpoints.get("client_id") or "").strip()
    if not device_endpoint or not token_endpoint or not client_id:
        lines = build_auth_status_lines_fn(
            subcommand="login",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action="ensure client_id/token_endpoint/device_authorization_endpoint are configured",
        )
        lines.append("error_code=missing_device_flow_endpoints")
        return ("\n".join(lines), [])
    start_result = dict(
        deps["start_device_flow_fn"](
            device_authorization_endpoint=device_endpoint,
            client_id=client_id,
            scope=str(endpoints.get("scope") or "").strip() or None,
        )
        or {}
    )
    if str(start_result.get("status") or "").strip() != "ok":
        lines = build_auth_status_lines_fn(
            subcommand="login",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action=auth_command_hint_fn(
                "login",
                provider_name=provider_name,
                mode="device_code",
            ),
        )
        lines.append(f"error_code={str(start_result.get('error_code') or 'oauth_device_start_error')}")
        lines.append(f"error_hint={str(start_result.get('error_description') or '').strip()}")
        return ("\n".join(lines), [])
    pending_session = deps["auth_session_factory"](
        provider_name=config_provider_name,
        token_ref=token_ref,
        metadata={
            "login_mode": "device_code",
            "device_code": str(start_result.get("device_code") or "").strip(),
            "token_endpoint": token_endpoint,
            "client_id": client_id,
            "scope": str(endpoints.get("scope") or "").strip(),
            "interval_seconds": safe_int_fn(start_result.get("interval"), 5),
        },
    )
    store.put(pending_session)
    lines = build_auth_status_lines_fn(
        subcommand="login",
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status="authorization_pending",
        next_action=auth_command_hint_fn(
            "login",
            provider_name=provider_name,
            mode="device_code",
            poll=True,
        ),
    )
    lines.append(f"verification_uri={str(start_result.get('verification_uri') or '').strip()}")
    lines.append(f"user_code={str(start_result.get('user_code') or '').strip()}")
    lines.append(f"token_ref={token_ref}")
    return ("\n".join(lines), [])


def _handle_auth_login_browser_pkce(
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    options = dict(state.get("options") or {})
    store = state.get("store")
    config_provider_name = str(state.get("config_provider_name") or "")
    token_ref = str(state.get("token_ref") or "")
    provider_name = str(state.get("provider_name") or "-")
    auth_mode = str(state.get("auth_mode") or "-")
    context = dict(state.get("context") or {})
    endpoints = dict(state.get("endpoints") or {})
    build_auth_status_lines_fn = deps["build_auth_status_lines_fn"]
    auth_command_hint_fn = deps["auth_command_hint_fn"]
    is_truthy_fn = deps["is_truthy_fn"]
    safe_int_fn = deps["safe_int_fn"]

    auth_code = str(options.get("auth-code") or "").strip()
    callback_state = ""
    wait_callback = is_truthy_fn(options.get("wait-callback")) or is_truthy_fn(options.get("listen"))
    callback_timeout_seconds = max(1, safe_int_fn(options.get("callback-timeout-seconds"), 120))
    redirect_uri = str(
        options.get("redirect-uri")
        or endpoints.get("redirect_uri")
        or "http://127.0.0.1:8765/callback"
    ).strip()
    token_endpoint = str(endpoints.get("token_endpoint") or "").strip()
    authorization_endpoint = str(endpoints.get("authorization_endpoint") or "").strip()
    client_id = str(endpoints.get("client_id") or "").strip()
    if not auth_code:
        if not authorization_endpoint or not token_endpoint or not client_id:
            lines = build_auth_status_lines_fn(
                subcommand="login",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status="error",
                next_action="ensure client_id/token_endpoint/authorization_endpoint are configured",
            )
            lines.append("error_code=missing_pkce_endpoints")
            return ("\n".join(lines), [])
        start_pkce = dict(
            deps["start_pkce_authorization_fn"](
                authorization_endpoint=authorization_endpoint,
                client_id=client_id,
                redirect_uri=redirect_uri,
                scope=str(endpoints.get("scope") or "").strip(),
            )
            or {}
        )
        if str(start_pkce.get("status") or "").strip() != "ok":
            lines = build_auth_status_lines_fn(
                subcommand="login",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status="error",
                next_action=auth_command_hint_fn(
                    "login",
                    provider_name=provider_name,
                    mode="browser_pkce",
                ),
            )
            lines.append(f"error_code={str(start_pkce.get('error_code') or 'pkce_start_error')}")
            return ("\n".join(lines), [])
        pending_session = deps["auth_session_factory"](
            provider_name=config_provider_name,
            token_ref=token_ref,
            metadata={
                "login_mode": "browser_pkce",
                "token_endpoint": token_endpoint,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": str(endpoints.get("scope") or "").strip(),
                "state": str(start_pkce.get("state") or "").strip(),
                "code_verifier": str(start_pkce.get("code_verifier") or "").strip(),
            },
        )
        store.put(pending_session)
        if wait_callback:
            callback_result = dict(
                deps["wait_for_pkce_callback_fn"](
                    redirect_uri=redirect_uri,
                    timeout_seconds=callback_timeout_seconds,
                )
                or {}
            )
            callback_status = str(callback_result.get("status") or "").strip().lower()
            if callback_status == "ok":
                auth_code = str(callback_result.get("code") or "").strip()
                callback_state = str(callback_result.get("state") or "").strip()
            elif callback_status == "timeout":
                lines = build_auth_status_lines_fn(
                    subcommand="login",
                    provider_name=provider_name,
                    auth_mode=auth_mode,
                    auth_status="authorization_pending",
                    next_action=auth_command_hint_fn(
                        "login",
                        provider_name=provider_name,
                        mode="browser_pkce",
                        auth_code="<code>",
                        state=str(start_pkce.get("state") or "").strip(),
                    ),
                )
                lines.append(f"authorization_url={str(start_pkce.get('authorization_url') or '').strip()}")
                lines.append(f"state={str(start_pkce.get('state') or '').strip()}")
                lines.append(f"token_ref={token_ref}")
                lines.append(
                    f"error_code={str(callback_result.get('error_code') or 'pkce_callback_timeout')}"
                )
                lines.append(f"error_hint=callback_timeout_seconds:{callback_timeout_seconds}")
                return ("\n".join(lines), [])
            else:
                lines = build_auth_status_lines_fn(
                    subcommand="login",
                    provider_name=provider_name,
                    auth_mode=auth_mode,
                    auth_status="error",
                    next_action=auth_command_hint_fn(
                        "login",
                        provider_name=provider_name,
                        mode="browser_pkce",
                    ),
                )
                lines.append(f"error_code={str(callback_result.get('error_code') or 'pkce_callback_error')}")
                lines.append(f"error_hint={str(callback_result.get('error_hint') or '').strip()}")
                lines.append(f"authorization_url={str(start_pkce.get('authorization_url') or '').strip()}")
                lines.append(f"state={str(start_pkce.get('state') or '').strip()}")
                lines.append(f"token_ref={token_ref}")
                return ("\n".join(lines), [])
            if not auth_code:
                lines = build_auth_status_lines_fn(
                    subcommand="login",
                    provider_name=provider_name,
                    auth_mode=auth_mode,
                    auth_status="error",
                    next_action=auth_command_hint_fn(
                        "login",
                        provider_name=provider_name,
                        mode="browser_pkce",
                    ),
                )
                lines.append("error_code=pkce_callback_missing_code")
                return ("\n".join(lines), [])
        else:
            lines = build_auth_status_lines_fn(
                subcommand="login",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status="authorization_url_ready",
                next_action=auth_command_hint_fn(
                    "login",
                    provider_name=provider_name,
                    mode="browser_pkce",
                    auth_code="<code>",
                    state=str(start_pkce.get("state") or "").strip(),
                ),
            )
            lines.append(f"authorization_url={str(start_pkce.get('authorization_url') or '').strip()}")
            lines.append(f"state={str(start_pkce.get('state') or '').strip()}")
            lines.append(f"token_ref={token_ref}")
            return ("\n".join(lines), [])

    pending = store.get(config_provider_name, token_ref)
    pending_metadata = dict(pending.metadata or {}) if pending is not None else {}
    pkce_result = dict(
        deps["exchange_pkce_authorization_code_fn"](
            token_endpoint=str(pending_metadata.get("token_endpoint") or token_endpoint).strip(),
            client_id=str(pending_metadata.get("client_id") or client_id).strip(),
            client_secret=str(endpoints.get("client_secret") or "").strip() or None,
            code=auth_code,
            redirect_uri=str(pending_metadata.get("redirect_uri") or redirect_uri).strip(),
            code_verifier=str(pending_metadata.get("code_verifier") or "").strip(),
            expected_state=str(pending_metadata.get("state") or "").strip() or None,
            returned_state=str(options.get("state") or callback_state or "").strip() or None,
        )
        or {}
    )
    if str(pkce_result.get("status") or "").strip() != "ok":
        lines = build_auth_status_lines_fn(
            subcommand="login",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action=auth_command_hint_fn(
                "login",
                provider_name=provider_name,
                mode="browser_pkce",
            ),
        )
        lines.append(f"error_code={str(pkce_result.get('error_code') or 'pkce_exchange_error')}")
        lines.append(f"error_hint={str(pkce_result.get('error_description') or '').strip()}")
        return ("\n".join(lines), [])
    metadata = dict(pending_metadata)
    metadata.pop("code_verifier", None)
    metadata.pop("state", None)
    saved = deps["save_session_from_oauth_result_fn"](
        store=store,
        context=context,
        token_ref=token_ref,
        oauth_result=pkce_result,
        metadata=metadata,
    )
    lines = build_auth_status_lines_fn(
        subcommand="login",
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=deps["ensure_auth_session_status_fn"](deps["auth_session_status_fn"](saved)),
        next_action=auth_command_hint_fn("status", provider_name=provider_name),
    )
    lines.append(f"token_ref={token_ref}")
    return ("\n".join(lines), [])
