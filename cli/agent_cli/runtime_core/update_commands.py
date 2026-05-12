from __future__ import annotations

from typing import Any

from cli.agent_cli import update_runtime
from cli.agent_cli.runtime_core.command_parsing import parse_args
from cli.agent_cli.slash_surface import surface_usage_text


def _usage_text() -> str:
    return f"Usage: {surface_usage_text('update')}"


def _dismiss_text() -> str:
    cache = update_runtime.dismiss_cached_update()
    latest = update_runtime.normalize_release_version(cache.get("latest_version")) or "-"
    return "\n".join(
        [
            "update dismissed",
            f"dismissed_version={latest}",
            f"cache_path={update_runtime.update_cache_path()}",
        ]
    )


def handle_update_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
) -> tuple[str, list[Any]] | None:
    del runtime
    if name != "update":
        return None
    positionals, options = parse_args(arg_text)
    refresh = bool(options.get("refresh"))
    if not positionals:
        return (update_runtime.update_status_text(refresh=refresh), [])
    if len(positionals) != 1:
        return (_usage_text(), [])
    action = str(positionals[0] or "").strip().lower()
    if action == "status":
        return (update_runtime.update_status_text(refresh=refresh), [])
    if action in {"check", "refresh"}:
        return (update_runtime.update_status_text(refresh=True), [])
    if action == "dismiss":
        return (_dismiss_text(), [])
    return (_usage_text(), [])
