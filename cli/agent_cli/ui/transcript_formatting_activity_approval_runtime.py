from __future__ import annotations

APPROVED_MARK = "\u2714"
REJECTED_MARK = "\u2717"
DETAIL_PREFIX = "  \u2514 "


def format_patch_approval_lines(
    *,
    summary: str,
    approval_id: str,
    count_text: str,
    commands: list[str] | None = None,
) -> list[str]:
    lines = [summary]
    if approval_id and count_text:
        label = "file" if count_text == "1" else "files"
        lines.append(f"{DETAIL_PREFIX}{approval_id} ({count_text} {label})")
    elif approval_id:
        lines.append(f"{DETAIL_PREFIX}{approval_id}")
    lines.extend(f"    {command}" for command in list(commands or []) if str(command).strip())
    return lines


def format_shell_approval_lines(
    *,
    summary: str,
    approval_id: str,
    command_text: str,
    commands: list[str] | None = None,
) -> list[str]:
    lines = [summary]
    if approval_id and command_text:
        lines.append(f"{DETAIL_PREFIX}{approval_id}")
        lines.append(f"    {command_text}")
    elif approval_id:
        lines.append(f"{DETAIL_PREFIX}{approval_id}")
    lines.extend(f"    {command}" for command in list(commands or []) if str(command).strip())
    return lines


def format_action_approval_lines(
    *,
    summary: str,
    approval_id: str,
    lead_text: str,
    commands: list[str] | None = None,
) -> list[str]:
    lines = [summary]
    if approval_id and lead_text:
        lines.append(f"{DETAIL_PREFIX}{approval_id}")
        lines.append(f"    {lead_text}")
    elif approval_id:
        lines.append(f"{DETAIL_PREFIX}{approval_id}")
    elif lead_text:
        lines.append(f"{DETAIL_PREFIX}{lead_text}")
    lines.extend(f"    {command}" for command in list(commands or []) if str(command).strip())
    return lines


def format_approval_list_lines(
    *,
    summary: str,
    count_text: str,
    status_text: str,
) -> list[str]:
    lines = [summary]
    if count_text and status_text:
        label = "approval" if count_text == "1" else "approvals"
        lines.append(f"{DETAIL_PREFIX}{count_text} {status_text} {label}")
    elif count_text:
        label = "approval" if count_text == "1" else "approvals"
        lines.append(f"{DETAIL_PREFIX}{count_text} {label}")
    return lines


def format_approval_decision_lines(
    *,
    summary: str,
    approval_id: str,
    continuation_status: str = "",
    raw: str,
    action_type: str = "",
    status_text: str = "",
    decision_type: str = "",
    command_text: str = "",
) -> list[str]:
    command_decision_line = _format_command_approval_decision_line(
        action_type=action_type,
        status_text=status_text,
        decision_type=decision_type,
        command_text=command_text,
    )
    if command_decision_line:
        return [command_decision_line]
    lines = [summary]
    if approval_id:
        lines.append(f"{DETAIL_PREFIX}{approval_id}")
        if continuation_status == "completed":
            lines.append("    Continuing after approval: completed")
        elif continuation_status:
            lines.append(f"    Continuing after approval: {continuation_status}")
        return lines
    raw_lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if raw_lines:
        lines.append(f"{DETAIL_PREFIX}{raw_lines[0]}")
    if continuation_status == "completed":
        lines.append("    Continuing after approval: completed")
    elif continuation_status:
        lines.append(f"    Continuing after approval: {continuation_status}")
    return lines


def _format_command_approval_decision_line(
    *,
    action_type: str,
    status_text: str,
    decision_type: str,
    command_text: str,
) -> str:
    if str(action_type or "").strip() != "shell_command":
        return ""
    command = _truncate_inline(str(command_text or "").strip(), max_chars=96)
    if not command:
        return ""
    status = str(status_text or "").strip().lower()
    decision = str(decision_type or "").strip().lower()
    if status == "approved":
        if decision == "accept_for_session":
            return (
                f"{APPROVED_MARK} You approved AgentHub to run {command} " "every time this session"
            )
        if decision == "accept_with_execpolicy_amendment":
            return (
                f"{APPROVED_MARK} You approved AgentHub to always run commands that start "
                f"with {command}"
            )
        return f"{APPROVED_MARK} You approved AgentHub to run {command} this time"
    if status == "rejected":
        if decision == "cancel":
            return f"{REJECTED_MARK} You canceled the request to run {command}"
        return f"{REJECTED_MARK} You did not approve AgentHub to run {command}"
    return ""


def _truncate_inline(value: str, *, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 4)].rstrip() + " ..."
