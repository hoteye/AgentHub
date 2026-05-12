from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli import runtime_runtime


def context_snapshot_overrides(
    *,
    environment_snapshot: dict[str, Any] | None = None,
    workspace_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        dict(environment_snapshot or {}) if isinstance(environment_snapshot, dict) else {},
        dict(workspace_snapshot or {}) if isinstance(workspace_snapshot, dict) else {},
    )


def response_runtime_snapshot(runtime: Any) -> dict[str, Any]:
    provider_status = dict(runtime.agent.provider_status() or {})
    runtime_policy = runtime.runtime_policy_status()
    return runtime_runtime.response_runtime_snapshot(
        cwd=getattr(runtime, "cwd", "") or "",
        provider_status=provider_status,
        runtime_policy=runtime_policy,
    )


def describe_thread(
    runtime: Any,
    *,
    thread: dict[str, Any] | None = None,
    thread_id: str | None = None,
    status: str | None = None,
    turns: list[dict[str, Any]] | None = None,
    metadata_overrides: dict[str, Any] | None = None,
    cli_version: str,
) -> dict[str, Any]:
    normalized_status = (
        str(status or ("idle" if turns is not None else "not_loaded")).strip() or "not_loaded"
    )
    thread_store = runtime.thread_store
    if thread_store is not None:
        if thread is not None:
            return thread_store.describe_thread_record(
                thread,
                status=normalized_status,
                turns=turns,
                metadata_overrides=metadata_overrides,
            )
        resolved_thread_id = str(thread_id or runtime.thread_id or "").strip()
        if resolved_thread_id:
            return thread_store.describe_thread(
                resolved_thread_id,
                status=normalized_status,
                turns=turns,
                metadata_overrides=metadata_overrides,
            )
    provider_status = dict(runtime.agent.provider_status() or {})
    runtime_policy = runtime.runtime_policy_status()
    return runtime_runtime.describe_thread_fallback(
        thread=thread,
        thread_id=str(thread_id or runtime.thread_id or "").strip(),
        thread_name=runtime.thread_name,
        cwd=getattr(runtime, "cwd", "") or "",
        turns=turns,
        normalized_status=normalized_status,
        provider_status=provider_status,
        runtime_policy=runtime_policy,
        metadata_overrides=metadata_overrides,
        cli_version=cli_version,
    )


def approval_status(*, list_approval_tickets_fn: Callable[..., list[Any]]) -> dict[str, str]:
    pending = list_approval_tickets_fn(limit=1000, status="pending")
    latest = pending[0] if pending else None
    return {
        "pending_approvals": str(len(pending)),
        "latest_pending_approval_id": str(latest.approval_id or "-") if latest is not None else "-",
    }


def slash_command_catalog_rows(
    *,
    plugin_manager: Any,
    slash_command_specs_fn: Callable[..., list[Any]],
    locale: str | None = None,
) -> list[dict[str, str]]:
    return runtime_runtime.slash_command_rows(
        slash_command_specs_fn(plugin_manager=plugin_manager, locale=locale)
    )


def slash_command_match_rows(
    *,
    prefix: str,
    plugin_manager: Any,
    match_slash_commands_fn: Callable[..., list[Any]],
    locale: str | None = None,
) -> list[dict[str, str]]:
    return runtime_runtime.slash_command_rows(
        match_slash_commands_fn(prefix, plugin_manager=plugin_manager, locale=locale)
    )


def preview_local_plan(
    *,
    text: str,
    last_plan: dict[str, Any] | None,
    last_plan_text: str | None,
    build_local_plan_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    return runtime_runtime.preview_local_plan(
        text=text,
        last_plan=last_plan,
        last_plan_text=last_plan_text,
        build_local_plan_fn=build_local_plan_fn,
    )
