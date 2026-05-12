from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def handle_auth_refresh(
    runtime: Any,
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    options = dict(state.get("options") or {})
    is_truthy_fn = deps["is_truthy_fn"]
    if is_truthy_fn(options.get("auto")):
        return _handle_auth_refresh_auto(runtime, state=state, deps=deps)
    return _handle_auth_refresh_session(state=state, deps=deps)


def _handle_auth_refresh_auto(
    runtime: Any,
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    options = dict(state.get("options") or {})
    provider_name = str(state.get("provider_name") or "-")
    provider_override = str(state.get("provider_override") or "")
    auth_mode = str(state.get("auth_mode") or "-")
    store = state.get("store")
    context = dict(state.get("context") or {})
    refresh_window_seconds = deps["safe_int_fn"](options.get("refresh-window-seconds"), 300)
    daemon_action = str(options.get("daemon") or "").strip().lower()
    build_auth_status_lines_fn = deps["build_auth_status_lines_fn"]
    auth_command_hint_fn = deps["auth_command_hint_fn"]
    is_truthy_fn = deps["is_truthy_fn"]
    safe_int_fn = deps["safe_int_fn"]

    if daemon_action:
        daemon_mode = "managed" if is_truthy_fn(options.get("managed")) else "in_process"
        if daemon_action not in {"start", "status", "stop"}:
            lines = build_auth_status_lines_fn(
                subcommand="refresh",
                provider_name=provider_name,
                auth_mode=auth_mode,
                auth_status="error",
                next_action=auth_command_hint_fn("refresh", auto=True, daemon="status"),
            )
            lines.append("error_code=invalid_daemon_action")
            lines.append("error_hint=use --daemon <start|status|stop>")
            return ("\n".join(lines), [])
        if daemon_mode == "managed":
            managed_store_path = Path(
                str(getattr(store, "store_path", context.get("provider_auth_path") or ""))
            )
            if daemon_action == "start":
                daemon_result = deps["start_managed_refresh_daemon_fn"](
                    store_path=managed_store_path,
                    contexts=deps["collect_refresh_contexts_fn"](
                        runtime,
                        provider_filter=provider_override,
                    ),
                    interval_seconds=safe_int_fn(options.get("interval-seconds"), 60),
                    refresh_window_seconds=refresh_window_seconds,
                )
            elif daemon_action == "stop":
                daemon_result = deps["stop_managed_refresh_daemon_fn"](
                    store_path=managed_store_path,
                    timeout_seconds=float(max(1, safe_int_fn(options.get("timeout-seconds"), 3))),
                    force=is_truthy_fn(options.get("force")),
                )
            else:
                daemon_result = {
                    "result": "status",
                    **deps["managed_refresh_daemon_status_fn"](store_path=managed_store_path),
                }
        else:
            daemon_handle = deps["refresh_daemon_handle_fn"](runtime)
            if daemon_action == "start":
                daemon_result = deps["start_refresh_daemon_fn"](
                    handle=daemon_handle,
                    store=store,
                    contexts_provider=lambda: deps["collect_refresh_contexts_fn"](
                        runtime,
                        provider_filter=provider_override,
                    ),
                    interval_seconds=safe_int_fn(options.get("interval-seconds"), 60),
                    refresh_window_seconds=refresh_window_seconds,
                    refresh_fn=deps["refresh_oauth_token_fn"],
                )
            elif daemon_action == "stop":
                daemon_result = deps["stop_refresh_daemon_fn"](
                    handle=daemon_handle,
                    timeout_seconds=float(max(1, safe_int_fn(options.get("timeout-seconds"), 2))),
                )
            else:
                daemon_result = {
                    "status": "status",
                    **deps["refresh_daemon_status_fn"](handle=daemon_handle),
                }
        daemon_state = str(daemon_result.get("daemon_status") or "").strip().lower() or "stopped"
        if daemon_state == "running" and daemon_mode == "managed":
            next_action = auth_command_hint_fn("refresh", auto=True, daemon="stop", managed=True)
        elif daemon_state == "running":
            next_action = auth_command_hint_fn("refresh", auto=True, daemon="stop")
        elif daemon_mode == "managed":
            next_action = auth_command_hint_fn("refresh", auto=True, daemon="start", managed=True)
        else:
            next_action = auth_command_hint_fn("refresh", auto=True, daemon="start")
        lines = build_auth_status_lines_fn(
            subcommand="refresh",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="running" if daemon_state == "running" else "stopped",
            next_action=next_action,
        )
        lines.append(f"daemon_mode={daemon_mode}")
        lines.append(f"daemon_action={daemon_action}")
        lines.append(
            f"daemon_result={str(daemon_result.get('result') or daemon_result.get('status') or '').strip() or '-'}"
        )
        lines.append(f"daemon_status={daemon_state}")
        lines.append(f"daemon_running={'true' if is_truthy_fn(daemon_result.get('running')) else 'false'}")
        lines.append(f"interval_seconds={safe_int_fn(daemon_result.get('interval_seconds'), 0)}")
        lines.append(
            f"refresh_window_seconds={safe_int_fn(daemon_result.get('refresh_window_seconds'), refresh_window_seconds)}"
        )
        lines.append(f"loop_count={safe_int_fn(daemon_result.get('loop_count'), 0)}")
        if daemon_mode == "managed":
            lines.append(f"healthy={'true' if is_truthy_fn(daemon_result.get('healthy')) else 'false'}")
            lines.append(f"alert_level={str(daemon_result.get('alert_level') or '-').strip() or '-'}")
            alert_reason = str(daemon_result.get("alert_reason") or "").strip()
            if alert_reason:
                lines.append(f"alert_reason={alert_reason}")
            pid = safe_int_fn(daemon_result.get("pid"), 0)
            if pid > 0:
                lines.append(f"pid={pid}")
            state_path = str(daemon_result.get("state_path") or "").strip()
            if state_path:
                lines.append(f"state_path={state_path}")
        if daemon_result.get("started_at") is not None:
            lines.append(f"started_at={int(float(daemon_result.get('started_at') or 0.0))}")
        if daemon_result.get("last_run_at") is not None:
            lines.append(f"last_run_at={int(float(daemon_result.get('last_run_at') or 0.0))}")
        summary_status = str(daemon_result.get("summary_status") or "").strip()
        if summary_status:
            lines.append(f"summary_status={summary_status}")
        lines.append(f"contexts={safe_int_fn(daemon_result.get('contexts'), 0)}")
        lines.append(f"refreshed={safe_int_fn(daemon_result.get('refreshed'), 0)}")
        lines.append(f"skipped={safe_int_fn(daemon_result.get('skipped'), 0)}")
        lines.append(f"failed={safe_int_fn(daemon_result.get('failed'), 0)}")
        error_text = str(daemon_result.get("last_error") or "").strip()
        if error_text:
            lines.append(f"error_hint={error_text}")
        return ("\n".join(lines), [])

    contexts = deps["collect_refresh_contexts_fn"](runtime, provider_filter=provider_override)
    summary = deps["refresh_due_sessions_fn"](
        store=store,
        contexts=contexts,
        refresh_window_seconds=refresh_window_seconds,
    )
    lines = build_auth_status_lines_fn(
        subcommand="refresh",
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=str(summary.get("status") or "ok"),
        next_action=auth_command_hint_fn("status", provider_name=provider_name),
    )
    lines.append(f"contexts={safe_int_fn(summary.get('contexts'), 0)}")
    lines.append(f"refreshed={safe_int_fn(summary.get('refreshed'), 0)}")
    lines.append(f"skipped={safe_int_fn(summary.get('skipped'), 0)}")
    lines.append(f"failed={safe_int_fn(summary.get('failed'), 0)}")
    return ("\n".join(lines), [])


def _handle_auth_refresh_session(
    *,
    state: Mapping[str, Any],
    deps: Mapping[str, Any],
) -> tuple[str, list]:
    store = state.get("store")
    config_provider_name = str(state.get("config_provider_name") or "")
    token_ref = str(state.get("token_ref") or "")
    provider_name = str(state.get("provider_name") or "-")
    auth_mode = str(state.get("auth_mode") or "-")
    login_mode = str(state.get("login_mode") or "")
    context = dict(state.get("context") or {})
    endpoints = dict(state.get("endpoints") or {})
    build_auth_status_lines_fn = deps["build_auth_status_lines_fn"]
    auth_command_hint_fn = deps["auth_command_hint_fn"]

    session = store.get(config_provider_name, token_ref)
    if session is None:
        lines = build_auth_status_lines_fn(
            subcommand="refresh",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="missing",
            next_action=auth_command_hint_fn(
                "login",
                provider_name=provider_name,
                mode=login_mode,
            ),
        )
        lines.append("error_code=missing_session")
        return ("\n".join(lines), [])
    refresh_token_value = str(session.refresh_token or "").strip()
    if not refresh_token_value:
        lines = build_auth_status_lines_fn(
            subcommand="refresh",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action=auth_command_hint_fn(
                "login",
                provider_name=provider_name,
                mode=login_mode,
            ),
        )
        lines.append("error_code=missing_refresh_token")
        return ("\n".join(lines), [])
    token_endpoint = str(endpoints.get("token_endpoint") or session.metadata.get("token_endpoint") or "").strip()
    client_id = str(endpoints.get("client_id") or session.metadata.get("client_id") or "").strip()
    if not token_endpoint or not client_id:
        lines = build_auth_status_lines_fn(
            subcommand="refresh",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action="ensure token_endpoint and client_id are configured",
        )
        lines.append("error_code=missing_refresh_endpoints")
        return ("\n".join(lines), [])
    refresh_result = dict(
        deps["refresh_oauth_token_fn"](
            token_endpoint=token_endpoint,
            client_id=client_id,
            client_secret=str(endpoints.get("client_secret") or "").strip() or None,
            refresh_token=refresh_token_value,
            scope=str(endpoints.get("scope") or "").strip() or None,
        )
        or {}
    )
    if str(refresh_result.get("status") or "").strip() != "ok":
        lines = build_auth_status_lines_fn(
            subcommand="refresh",
            provider_name=provider_name,
            auth_mode=auth_mode,
            auth_status="error",
            next_action=auth_command_hint_fn(
                "login",
                provider_name=provider_name,
                mode=login_mode,
            ),
        )
        lines.append(f"error_code={str(refresh_result.get('error_code') or 'oauth_refresh_error')}")
        lines.append(f"error_hint={str(refresh_result.get('error_description') or '').strip()}")
        return ("\n".join(lines), [])
    metadata = dict(session.metadata or {})
    metadata["token_endpoint"] = token_endpoint
    metadata["client_id"] = client_id
    saved = deps["save_session_from_oauth_result_fn"](
        store=store,
        context=context,
        token_ref=token_ref,
        oauth_result=refresh_result,
        metadata=metadata,
    )
    lines = build_auth_status_lines_fn(
        subcommand="refresh",
        provider_name=provider_name,
        auth_mode=auth_mode,
        auth_status=deps["ensure_auth_session_status_fn"](deps["auth_session_status_fn"](saved)),
        next_action=auth_command_hint_fn("status", provider_name=provider_name),
    )
    lines.append(f"token_ref={token_ref}")
    return ("\n".join(lines), [])
