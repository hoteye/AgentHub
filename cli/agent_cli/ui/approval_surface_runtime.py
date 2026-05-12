from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime


def approval_commands(
    *,
    approval_id: str,
    available_decisions: Any = None,
    raw: str = "",
    allow_generic_fallback: bool = True,
) -> list[str]:
    normalized_id = str(approval_id or "").strip()
    if not normalized_id:
        return []
    commands = approval_contract_runtime.approval_option_commands(
        normalized_id,
        available_decisions,
    )
    if commands:
        return commands
    parsed = _commands_from_raw_detail(raw)
    if parsed:
        return parsed
    if not allow_generic_fallback:
        return []
    return [
        f"/approve {normalized_id}",
        f"/reject {normalized_id}",
    ]


def approval_id_from_detail(raw: str) -> str:
    for line in str(raw or "").splitlines():
        text = str(line).strip()
        if not text or text.startswith(("/", "files=", "count=", "status=", "decision=")):
            continue
        return text
    return ""


def _commands_from_raw_detail(raw: str) -> list[str]:
    commands: list[str] = []
    seen: set[str] = set()
    for line in str(raw or "").splitlines():
        text = str(line).strip()
        if not text.startswith(("/approve ", "/reject ")):
            continue
        if text in seen:
            continue
        seen.add(text)
        commands.append(text)
    return commands

