from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import ToolEvent


def build_payload_event(
    *,
    tool_name: str,
    payload: dict[str, Any],
    summary: str,
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return event_factory(tool_name, bool(payload.get("ok")), summary, payload)


def build_office_skills_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    build_payload_event_fn: Callable[..., ToolEvent],
    office_skills_summary_fn: Callable[[dict[str, Any]], str],
) -> ToolEvent:
    return build_payload_event_fn(
        tool_name="office_skills",
        payload=payload,
        summary=office_skills_summary_fn(payload),
        event_factory=event_factory,
    )


def build_office_run_event(
    *,
    skill_name: str,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    build_payload_event_fn: Callable[..., ToolEvent],
    office_run_summary_fn: Callable[..., str],
) -> ToolEvent:
    return build_payload_event_fn(
        tool_name="office_run",
        payload=payload,
        summary=office_run_summary_fn(skill_name=skill_name, payload=payload),
        event_factory=event_factory,
    )


def build_view_image_event(
    *,
    ok: bool,
    payload: dict[str, Any],
    resolved_name: str,
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    view_image_success_summary_fn: Callable[..., str],
) -> ToolEvent:
    return event_factory(
        "view_image",
        ok,
        view_image_success_summary_fn(resolved_name=resolved_name) if ok else "view image failed",
        payload,
    )


def build_policy_doc_import_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    build_payload_event_fn: Callable[..., ToolEvent],
    policy_doc_import_summary_fn: Callable[[dict[str, Any]], str],
) -> ToolEvent:
    return build_payload_event_fn(
        tool_name="policy_doc_import",
        payload=payload,
        summary=policy_doc_import_summary_fn(payload),
        event_factory=event_factory,
    )


def build_policy_doc_list_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    build_payload_event_fn: Callable[..., ToolEvent],
    policy_doc_list_summary_fn: Callable[[dict[str, Any]], str],
) -> ToolEvent:
    return build_payload_event_fn(
        tool_name="policy_doc_list",
        payload=payload,
        summary=policy_doc_list_summary_fn(payload),
        event_factory=event_factory,
    )


def build_policy_doc_search_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    build_payload_event_fn: Callable[..., ToolEvent],
    policy_doc_search_summary_fn: Callable[[dict[str, Any]], str],
) -> ToolEvent:
    return build_payload_event_fn(
        tool_name="policy_doc_search",
        payload=payload,
        summary=policy_doc_search_summary_fn(payload),
        event_factory=event_factory,
    )


def build_policy_doc_read_event(
    *,
    payload: dict[str, Any],
    event_factory: Callable[[str, bool, str, dict[str, Any]], ToolEvent],
    build_payload_event_fn: Callable[..., ToolEvent],
    policy_doc_read_summary_fn: Callable[[dict[str, Any]], str],
) -> ToolEvent:
    return build_payload_event_fn(
        tool_name="policy_doc_read",
        payload=payload,
        summary=policy_doc_read_summary_fn(payload),
        event_factory=event_factory,
    )


__all__ = [
    "build_office_run_event",
    "build_office_skills_event",
    "build_payload_event",
    "build_policy_doc_import_event",
    "build_policy_doc_list_event",
    "build_policy_doc_read_event",
    "build_policy_doc_search_event",
    "build_view_image_event",
]
