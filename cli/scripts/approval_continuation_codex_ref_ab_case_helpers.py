from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AbCase:
    name: str
    live_case: str
    codex_command: str
    target_file: str
    expected_content: str
    decision: str
    tool_kind: str


CASES: tuple[AbCase, ...] = (
    AbCase(
        name="approve_exec_command",
        live_case="approve_exec_command",
        codex_command="trigger-cmd-approval",
        target_file="approval_live_approve.txt",
        expected_content="approval-approved",
        decision="approve",
        tool_kind="command",
    ),
    AbCase(
        name="reject_exec_command",
        live_case="reject_exec_command",
        codex_command="reject-cmd-approval",
        target_file="approval_live_reject.txt",
        expected_content="approval-rejected",
        decision="reject",
        tool_kind="command",
    ),
    AbCase(
        name="approve_apply_patch",
        live_case="approve_apply_patch",
        codex_command="trigger-patch-approval",
        target_file="approval_patch_approve.txt",
        expected_content="approval-patch-approved",
        decision="approve",
        tool_kind="file_change",
    ),
    AbCase(
        name="reject_apply_patch",
        live_case="reject_apply_patch",
        codex_command="reject-patch-approval",
        target_file="approval_patch_reject.txt",
        expected_content="approval-patch-rejected",
        decision="reject",
        tool_kind="file_change",
    ),
)


def _selected_cases(names: list[str]) -> list[AbCase]:
    if not names:
        return list(CASES)
    by_name = {case.name: case for case in CASES}
    selected: list[AbCase] = []
    for name in names:
        normalized = str(name or "").strip()
        if normalized not in by_name:
            raise SystemExit(
                f"unknown case `{normalized}`; available: {', '.join(sorted(by_name))}"
            )
        selected.append(by_name[normalized])
    return selected


def _prompt_for_case(case: AbCase) -> str:
    if case.tool_kind == "file_change":
        patch = (
            "*** Begin Patch\n"
            f"*** Add File: {case.target_file}\n"
            f"+{case.expected_content}\n"
            "*** End Patch"
        )
        return (
            "Use the apply_patch tool exactly once with this exact patch in the current workspace:\n"
            f"{patch}\n"
            "Do not use shell commands or any other file-writing tool. "
            "After the patch tool returns, briefly state whether the patch result is approved and visible."
        )
    command = f"printf '{case.expected_content}\\n' > {case.target_file}"
    return (
        "Use the shell tool exactly once to run this exact command in the current workspace:\n"
        f"{command}\n"
        "Do not use apply_patch or any other file-writing tool. "
        "After the command returns, briefly state whether the command result is approved and visible."
    )
