from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli import approval_contract_runtime, approval_control_protocol_runtime
from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
)
from cli.agent_cli.runtime_services import approval_continuation_runtime
from cli.agent_cli.slash_parser import SlashInvocation, slash_keyword_map, slash_switch_set
from cli.agent_cli.tools_core.apply_patch_bridge import preview_apply_patch


def _slash_parsed_args(
    slash_invocation: SlashInvocation | None,
) -> tuple[list[str], dict[str, object]] | None:
    if slash_invocation is None:
        return None
    options: dict[str, object] = dict(slash_keyword_map(slash_invocation))
    for switch_name in slash_switch_set(slash_invocation):
        options[switch_name] = True
    return [str(item) for item in slash_invocation.positionals], options


def _workspace_root_path(runtime) -> Path:
    return Path(str(getattr(runtime, "cwd", ".") or ".")).resolve()


def patch_approval_cached(runtime, *, patch_text: str) -> bool:
    try:
        workspace_root = _workspace_root_path(runtime)
        preview = preview_apply_patch(
            patch_text=patch_text,
            workspace_root=workspace_root,
        )
    except Exception:
        return False
    return approval_contract_runtime.patch_approval_is_cached(
        runtime,
        preview=preview,
        workspace_root=workspace_root,
    )


def _approval_decision_from_command(name: str, mode: object) -> str:
    normalized_name = str(name or "").strip().lower()
    normalized_mode = str(mode or "").strip().lower()
    if normalized_name == "approve":
        if normalized_mode in {"", "once", "single"}:
            return approval_contract_runtime.APPROVAL_DECISION_ACCEPT
        if normalized_mode in {"session", "allow-for-session", "for-session"}:
            return approval_contract_runtime.APPROVAL_DECISION_ACCEPT_FOR_SESSION
        if normalized_mode in {"rule", "prefix", "exec-policy", "execpolicy"}:
            return approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT
        raise ValueError("approve mode must be session|rule or omitted")
    if normalized_name == "reject":
        if normalized_mode in {"", "decline", "deny"}:
            return approval_contract_runtime.APPROVAL_DECISION_DECLINE
        if normalized_mode in {"cancel", "abort"}:
            return approval_contract_runtime.APPROVAL_DECISION_CANCEL
        raise ValueError("reject mode must be cancel or omitted")
    raise ValueError(f"unsupported approval command: {name}")


def _approval_usage_text(name: str) -> str:
    if name == "approve":
        return "Usage: /approve <approval_id> [mode session|rule] [note <text>] [no-resume] [resume-only]"
    return "Usage: /reject <approval_id> [mode cancel] [note <text>] [no-resume] [resume-only]"


def _approval_failed_event(approval_id: str, error: str) -> ToolEvent:
    return ToolEvent(
        name="approval_decision",
        ok=False,
        summary="approval decision failed",
        payload={"approval_id": approval_id, "error": error},
    )


def _approval_resume_only_result(runtime, approval_id: str, decision: str) -> dict[str, object]:
    return {
        "tool_events": [
            ToolEvent(
                name="approval_decision",
                ok=True,
                summary="approval continuation resume-only",
                payload={
                    "ok": True,
                    "approval_id": approval_id,
                    "status": "resume_only",
                    "decision_type": decision,
                },
            )
        ],
        "item_events": [],
        "turn_events": [],
        "continuation": approval_continuation_runtime.continuation_result_for_resume_only(
            runtime,
            approval_id,
        ),
    }


def _approval_fallback_tool_events(
    *,
    result: dict[str, object],
    approval_id: str,
    command_name: str,
    decision_note: str,
    decision: str,
) -> list[ToolEvent]:
    approval_ticket = result.get("approval_ticket")
    action_request = result.get("action_request")
    approval_id_text = str(getattr(approval_ticket, "approval_id", "") or "").strip()
    approval_status = str(getattr(approval_ticket, "status", "") or "").strip()
    action_payload = getattr(action_request, "payload", None)
    action_payload = dict(action_payload or {}) if isinstance(action_payload, dict) else {}
    command_text = str(action_payload.get("command") or "").strip()
    return [
        ToolEvent(
            name="approval_decision",
            ok=True,
            summary=f"{approval_status} {approval_id_text}".strip(),
            payload={
                "ok": True,
                "approval_id": approval_id_text or approval_id,
                "status": approval_status
                or ("approved" if command_name == "approve" else "rejected"),
                "action_type": str(getattr(action_request, "action_type", "") or "").strip()
                or None,
                "command": command_text or None,
                "decision_by": "cli",
                "decision_note": decision_note,
                "decision_type": decision,
            },
        )
    ]


def _approval_item_events(
    *,
    tool_events: list[ToolEvent],
    approval_id: str,
    decision: str,
    decision_note: str,
) -> list[dict[str, object]]:
    if not tool_events:
        return []
    first_event = tool_events[0]
    return generic_tool_call_item_events(
        tool_name=str(first_event.name or "approval_decision"),
        arguments={
            "approval_id": approval_id,
            "decision": decision,
            "note": decision_note or None,
        },
        ok=bool(first_event.ok),
        summary=str(first_event.summary or ""),
        structured_content=dict(first_event.payload or {}),
    )


def _approval_assistant_text(tool_events: list[ToolEvent]) -> str:
    assistant_text = ""
    if tool_events:
        last_payload = dict(tool_events[-1].payload or {})
        summary_text = str(last_payload.get("summary_text") or "").strip()
        if summary_text:
            assistant_text = summary_text
    return assistant_text


def execute_approval_decision(
    runtime,
    *,
    approval_id: str,
    decision: str,
    decision_note: str = "",
    decided_by: str = "cli",
    no_resume: bool = False,
    resume_only: bool = False,
    command_name: str | None = None,
) -> CommandExecutionResult:
    normalized_command_name = str(command_name or "").strip().lower()
    if not normalized_command_name:
        normalized_command_name = (
            "approve" if approval_contract_runtime.is_approval_accepting(decision) else "reject"
        )
    if resume_only:
        result = _approval_resume_only_result(runtime, approval_id, decision)
    else:
        result = runtime.decide_approval(
            approval_id,
            decision=decision,
            decided_by=decided_by,
            decision_note=decision_note,
        )

    tool_events = [
        item for item in list(result.get("tool_events") or []) if isinstance(item, ToolEvent)
    ]
    if not tool_events:
        tool_events = _approval_fallback_tool_events(
            result=result,
            approval_id=approval_id,
            command_name=normalized_command_name,
            decision_note=decision_note,
            decision=decision,
        )
    approval_item_events = _approval_item_events(
        tool_events=tool_events,
        approval_id=approval_id,
        decision=decision,
        decision_note=decision_note,
    )
    item_events = list(approval_item_events)
    turn_events: list[dict[str, object]] = []

    assistant_text = _approval_assistant_text(tool_events)
    continuation = dict(result.get("continuation") or {})
    resumed_intent = None
    if not no_resume:
        resumed_intent = approval_continuation_runtime.resume_after_approval(
            runtime,
            continuation_result=continuation,
        )
    if continuation:
        approval_continuation_runtime.persist_continuation_result(
            runtime,
            approval_id,
            continuation,
        )
    if continuation:
        for event in tool_events:
            event.payload["continuation"] = dict(continuation)
    if resumed_intent is not None:
        resumed_text = str(getattr(resumed_intent, "assistant_text", "") or "").strip()
        if resumed_text:
            assistant_text = resumed_text
        tool_events.extend(
            [
                item
                for item in list(getattr(resumed_intent, "tool_events", []) or [])
                if isinstance(item, ToolEvent)
            ]
        )
        item_events.extend(
            [
                dict(item)
                for item in list(getattr(resumed_intent, "item_events", []) or [])
                if isinstance(item, dict)
            ]
        )
        resumed_turn_events = [
            dict(item)
            for item in list(getattr(resumed_intent, "turn_events", []) or [])
            if isinstance(item, dict)
        ]
        turn_events = _merge_approval_display_turn_events(
            approval_item_events=approval_item_events,
            resumed_turn_events=resumed_turn_events,
        )
    return CommandExecutionResult(
        assistant_text=assistant_text,
        tool_events=tool_events,
        item_events=item_events,
        turn_events=turn_events,
    )


def execute_approval_control_response(
    runtime,
    message: dict[str, object],
    *,
    decided_by: str = "control",
    no_resume: bool = False,
    resume_only: bool = False,
) -> CommandExecutionResult:
    decision_payload = approval_control_protocol_runtime.approval_decision_from_control_response(
        message
    )
    approval_id = str(decision_payload.get("approval_id") or "").strip()
    decision = str(decision_payload.get("decision") or "").strip()
    decision_note = str(decision_payload.get("decision_note") or "").strip()
    if not approval_id:
        raise ValueError("control_response approval_id is empty")
    if not decision:
        raise ValueError("control_response decision is empty")
    return execute_approval_decision(
        runtime,
        approval_id=approval_id,
        decision=decision,
        decision_note=decision_note,
        decided_by=decided_by,
        no_resume=no_resume,
        resume_only=resume_only,
    )


def _turn_item_index(item_id: Any) -> int | None:
    raw_id = str(item_id or "").strip()
    if not raw_id.startswith("item_"):
        return None
    try:
        return int(raw_id.split("_", 1)[1])
    except (TypeError, ValueError):
        return None


def _next_turn_item_index(events: list[dict[str, object]]) -> int:
    highest = -1
    for raw_event in list(events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        index = _turn_item_index(item.get("id"))
        if index is not None:
            highest = max(highest, index)
    return highest + 1


def _rebase_turn_item_ids(
    events: list[dict[str, object]],
    *,
    offset: int,
) -> list[dict[str, object]]:
    if offset <= 0:
        return [dict(item) for item in list(events or []) if isinstance(item, dict)]
    rebased: list[dict[str, object]] = []
    for raw_event in list(events or []):
        if not isinstance(raw_event, dict):
            continue
        event = dict(raw_event)
        item = event.get("item")
        if isinstance(item, dict):
            projected_item = dict(item)
            index = _turn_item_index(projected_item.get("id"))
            if index is not None:
                projected_item["id"] = f"item_{index + offset}"
            event["item"] = projected_item
        rebased.append(event)
    return rebased


def _merge_approval_display_turn_events(
    *,
    approval_item_events: list[dict[str, object]],
    resumed_turn_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    normalized_approval_events = [
        dict(item) for item in list(approval_item_events or []) if isinstance(item, dict)
    ]
    normalized_resumed_events = [
        dict(item) for item in list(resumed_turn_events or []) if isinstance(item, dict)
    ]
    if not normalized_resumed_events:
        return []
    if not normalized_approval_events:
        return normalized_resumed_events

    offset = _next_turn_item_index(normalized_approval_events)
    rebased_resumed_events = _rebase_turn_item_ids(
        normalized_resumed_events,
        offset=offset,
    )
    resumed_body = [
        dict(event)
        for event in rebased_resumed_events
        if str(event.get("type") or "").strip() != "turn.started"
    ]
    return [
        {"type": "turn.started"},
        *normalized_approval_events,
        *resumed_body,
    ]


def handle_approval_command(
    runtime,
    *,
    name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
    single_event_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
) -> CommandExecutionResult | None:
    if name == "approvals":
        slash_args = _slash_parsed_args(slash_invocation)
        if slash_args is not None:
            _, options = slash_args
        else:
            _, options = runtime._parse_args(arg_text)
        limit_value = options.get("limit")
        limit = int(limit_value) if limit_value is not None else 20
        status = str(options.get("status") or "").strip() or None
        return single_event_result(
            "List approval tickets.",
            runtime.approvals_event(limit=limit, status=status),
            arguments={"limit": limit, "status": status},
        )
    if name not in {"approve", "reject"}:
        return None

    slash_args = _slash_parsed_args(slash_invocation)
    if slash_args is not None:
        positionals, options = slash_args
    else:
        positionals, options = runtime._parse_args(arg_text)
    approval_id = " ".join(positionals).strip()
    if not approval_id:
        return text_only_result(_approval_usage_text(name))

    decision_mode = str(options.get("mode") or "").strip()
    decision_note = str(options.get("note") or "").strip()
    resume_only = bool(options.get("resume-only"))
    no_resume = bool(options.get("no-resume"))
    try:
        decision = _approval_decision_from_command(name, decision_mode)
    except ValueError as exc:
        return single_event_result(
            "Approval decision failed.",
            _approval_failed_event(approval_id, str(exc)),
            arguments={"approval_id": approval_id, "decision": decision_mode or name},
        )

    try:
        return execute_approval_decision(
            runtime,
            approval_id=approval_id,
            decision=decision,
            decision_note=decision_note,
            decided_by="cli",
            no_resume=no_resume,
            resume_only=resume_only,
            command_name=name,
        )
    except ValueError as exc:
        return single_event_result(
            "Approval decision failed.",
            _approval_failed_event(approval_id, str(exc)),
            arguments={"approval_id": approval_id, "decision": decision_mode or name},
        )
