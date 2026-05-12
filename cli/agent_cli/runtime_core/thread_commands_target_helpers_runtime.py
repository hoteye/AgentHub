from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from cli.agent_cli.runtime_core import thread_commands_agent_runtime

ParsedArgs = tuple[list[Any], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SendInputCommandValues:
    agent_id: str
    message_text: str
    input_items: list[dict[str, Any]] | None
    interrupt: bool
    codex_style: bool
    message_items_conflict: bool


@dataclass(frozen=True, slots=True)
class SingleTargetCommandValues:
    agent_id: str
    codex_style: bool


@dataclass(frozen=True, slots=True)
class WaitCommandValues:
    ids: list[str]
    agent_id: str
    timeout_ms: Any
    reason: str | None
    wait_required: Any


@dataclass(frozen=True, slots=True)
class AgentWorkflowCommandValues:
    agent_id: str
    steps: Any
    checkpoints: Any


@dataclass(frozen=True, slots=True)
class RecoverAgentCommandValues:
    agent_id: str
    action: str | None
    step_id: str | None


def resolve_send_input_command_values(
    *,
    payload: dict[str, Any],
    parsed_args: ParsedArgs,
    bool_option: Callable[..., bool],
) -> SendInputCommandValues:
    if payload:
        agent_id = thread_commands_agent_runtime.target_from_payload(payload)
        input_items = thread_commands_agent_runtime._normalized_collab_items(payload.get("items"))
        source_message_text = str(payload.get("message") or payload.get("text") or payload.get("prompt") or "").strip()
        message_items_conflict = bool(source_message_text and input_items)
        message_text = source_message_text
        if not message_text and input_items is not None:
            message_text = thread_commands_agent_runtime.collab_items_preview(input_items)
        return SendInputCommandValues(
            agent_id=agent_id,
            message_text=message_text,
            input_items=input_items,
            interrupt=(
                bool_option(payload.get("interrupt"), default=False)
                if "interrupt" in payload and not message_items_conflict
                else False
            ),
            codex_style="id" in payload or input_items is not None,
            message_items_conflict=message_items_conflict,
        )
    positionals, options = parsed_args
    return SendInputCommandValues(
        agent_id=str(positionals[0] or "").strip() if positionals else "",
        message_text=" ".join(positionals[1:]).strip() if len(positionals) > 1 else "",
        input_items=None,
        interrupt=bool_option(options.get("interrupt"), default=False) if len(positionals) > 1 else False,
        codex_style=False,
        message_items_conflict=False,
    )


def send_input_arguments(
    *,
    use_id_style: bool,
    agent_id: str,
    message_text: str,
    input_items: list[dict[str, Any]] | None,
    interrupt: bool,
) -> dict[str, Any]:
    if use_id_style:
        return {
            "id": agent_id,
            **({"message": message_text} if input_items is None else {}),
            **({"items": [dict(item) for item in list(input_items or []) if isinstance(item, dict)]} if input_items is not None else {}),
            **({"interrupt": True} if interrupt else {}),
        }
    return {"target": agent_id, "message": message_text, **({"interrupt": True} if interrupt else {})}


def resolve_single_target_command_values(
    *,
    payload: dict[str, Any],
    parsed_args: ParsedArgs,
) -> SingleTargetCommandValues:
    if payload:
        return SingleTargetCommandValues(
            agent_id=thread_commands_agent_runtime.target_from_payload(payload),
            codex_style="id" in payload,
        )
    positionals, _ = parsed_args
    return SingleTargetCommandValues(
        agent_id=str(positionals[0] or "").strip() if positionals else "",
        codex_style=False,
    )


def target_arguments(*, agent_id: str, codex_style: bool) -> dict[str, Any]:
    return {"id": agent_id} if codex_style else {"target": agent_id}


def resolve_wait_command_values(
    *,
    payload: dict[str, Any],
    parsed_args: ParsedArgs,
) -> WaitCommandValues:
    if payload:
        return WaitCommandValues(
            ids=[str(item).strip() for item in list(payload.get("ids") or []) if str(item).strip()],
            agent_id=thread_commands_agent_runtime.target_from_payload(payload),
            timeout_ms=payload.get("timeout_ms", payload.get("timeout")),
            reason=str(payload.get("reason") or "").strip() or None,
            wait_required=payload.get("wait_required") if "wait_required" in payload else True,
        )
    positionals, options = parsed_args
    return WaitCommandValues(
        ids=[],
        agent_id=str(positionals[0] or "").strip() if positionals else "",
        timeout_ms=options.get("timeout-ms"),
        reason=str(options.get("reason") or "").strip() or None,
        wait_required=options.get("wait-required") if "wait-required" in options else True,
    )


def select_wait_agent_ids(command_values: WaitCommandValues) -> list[str]:
    if command_values.ids:
        return command_values.ids
    if command_values.agent_id:
        return [command_values.agent_id]
    return []


def validate_wait_timeout_text(
    *,
    ids: list[str],
    timeout_ms: Any,
    int_option: Callable[..., int | None],
) -> str | None:
    if timeout_ms in (None, ""):
        return None
    timeout_default = None if ids else 250
    timeout_ms_value = int_option(timeout_ms, default=timeout_default)
    return str(timeout_ms_value) if timeout_ms_value is not None else None


def wait_ids_arguments(
    *,
    agent_ids: list[str],
    timeout_ms_text: str | None,
    reason: str | None = None,
    wait_required: Any = None,
) -> dict[str, Any]:
    return {
        "ids": agent_ids,
        **({"timeout_ms": timeout_ms_text} if timeout_ms_text is not None else {}),
        **({"reason": reason} if reason else {}),
        **({"wait_required": wait_required} if wait_required is not None else {}),
    }


def wait_target_arguments(
    *,
    agent_id: str,
    timeout_ms_text: str | None,
    reason: str | None,
    wait_required: Any,
) -> dict[str, Any]:
    return {
        "target": agent_id,
        **({"timeout_ms": timeout_ms_text} if timeout_ms_text is not None else {}),
        **({"reason": reason} if reason else {}),
        **({"wait_required": wait_required} if wait_required is not None else {}),
    }


def resolve_agent_workflow_command_values(
    *,
    payload: dict[str, Any],
    parsed_args: ParsedArgs,
) -> AgentWorkflowCommandValues:
    if payload:
        return AgentWorkflowCommandValues(
            agent_id=thread_commands_agent_runtime.target_from_payload(payload),
            steps=payload.get("steps"),
            checkpoints=payload.get("checkpoints"),
        )
    positionals, options = parsed_args
    return AgentWorkflowCommandValues(
        agent_id=str(positionals[0] or "").strip() if positionals else "",
        steps=options.get("steps"),
        checkpoints=options.get("checkpoints"),
    )


def validate_agent_workflow_limits(
    *,
    steps: Any,
    checkpoints: Any,
    int_option: Callable[..., int | None],
) -> tuple[int, int]:
    return (int_option(steps, default=8) or 8, int_option(checkpoints, default=8) or 8)


def agent_workflow_arguments(*, agent_id: str, steps_limit: int, checkpoints_limit: int) -> dict[str, Any]:
    return {"target": agent_id, "steps": steps_limit, "checkpoints": checkpoints_limit}


def resolve_recover_agent_command_values(
    *,
    payload: dict[str, Any],
    parsed_args: ParsedArgs,
) -> RecoverAgentCommandValues:
    if payload:
        return RecoverAgentCommandValues(
            agent_id=thread_commands_agent_runtime.target_from_payload(payload),
            action=str(payload.get("action") or "").strip() or None,
            step_id=str(payload.get("step_id") or payload.get("step") or "").strip() or None,
        )
    positionals, options = parsed_args
    return RecoverAgentCommandValues(
        agent_id=str(positionals[0] or "").strip() if positionals else "",
        action=str(options.get("action") or "").strip() or None,
        step_id=str(options.get("step-id") or "").strip() or None,
    )


def recover_agent_arguments(*, agent_id: str, action: str | None, step_id: str | None) -> dict[str, Any]:
    return {
        "target": agent_id,
        **({"action": action} if action else {}),
        **({"step_id": step_id} if step_id else {}),
    }
