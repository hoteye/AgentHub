from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.ui import transcript_shell_exploration_command_runtime


def coerce_summary(
    value: object,
    *,
    summary_type: type[Any],
    build_summary_fn: Callable[..., Any],
) -> Any | None:
    if isinstance(value, summary_type):
        return value
    if not isinstance(value, dict):
        return None
    kind = str(value.get("kind") or "").strip()
    if not kind:
        return None
    path = str(value.get("path") or "").strip() or None
    query = str(value.get("query") or "").strip() or None
    name = str(value.get("name") or "").strip() or None
    return build_summary_fn(kind=kind, path=path, query=query, name=name)


def command_execution_summaries_from_command(
    command_text: str,
    *,
    build_summary_fn: Callable[..., Any],
) -> list[Any] | None:
    return transcript_shell_exploration_command_runtime.command_execution_exploration_summaries(
        {"command": str(command_text or "").strip()},
        build_summary_fn=build_summary_fn,
    )


def command_execution_summaries_from_mapping(
    item: dict[str, Any] | None,
    *,
    summaries_key: str,
    coerce_summary_fn: Callable[[object], Any | None],
    summaries_from_command_fn: Callable[[str], list[Any] | None],
) -> list[Any] | None:
    raw_item = dict(item or {})
    raw_summaries = raw_item.get(summaries_key)
    if isinstance(raw_summaries, list):
        summaries = [coerce_summary_fn(entry) for entry in raw_summaries]
        summaries = [entry for entry in summaries if entry is not None]
        if summaries:
            return summaries
    command_text = str(raw_item.get("command") or "").strip()
    if not command_text:
        return None
    return summaries_from_command_fn(command_text)


def command_execution_summary_dicts_from_mapping(
    item: dict[str, Any] | None,
    *,
    summaries_from_mapping_fn: Callable[[dict[str, Any] | None], list[Any] | None],
) -> list[dict[str, str]] | None:
    summaries = summaries_from_mapping_fn(item)
    if not summaries:
        return None
    return [summary.to_dict() for summary in summaries]


def populate_command_execution_summary_dicts(
    item: dict[str, Any] | None,
    *,
    summaries_key: str,
    summary_dicts_from_mapping_fn: Callable[[dict[str, Any] | None], list[dict[str, str]] | None],
) -> dict[str, Any]:
    normalized = dict(item or {})
    summary_dicts = summary_dicts_from_mapping_fn(normalized)
    if summary_dicts:
        normalized[summaries_key] = summary_dicts
    else:
        normalized.pop(summaries_key, None)
    return normalized


def command_activity_params(
    item: dict[str, Any] | None,
    *,
    extra_params: dict[str, Any] | None,
    command_display_key: str,
    summaries_key: str,
    command_display_from_mapping_fn: Callable[..., str],
    summary_dicts_from_mapping_fn: Callable[[dict[str, Any] | None], list[dict[str, str]] | None],
) -> dict[str, Any]:
    params = dict(extra_params or {})
    raw_item = dict(item or {})
    call_id = str(raw_item.get("call_id") or raw_item.get("id") or "").strip()
    if call_id:
        params["call_id"] = call_id
    command_text = str(raw_item.get("command") or "").strip()
    if command_text:
        params["command"] = command_text
        command_display = command_display_from_mapping_fn(raw_item, single_line=True)
        if command_display:
            params[command_display_key] = command_display
    summary_dicts = summary_dicts_from_mapping_fn(raw_item)
    if summary_dicts:
        params[summaries_key] = summary_dicts
    return params
