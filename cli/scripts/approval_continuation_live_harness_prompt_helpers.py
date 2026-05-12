from __future__ import annotations

import json

try:
    from cli.scripts.approval_continuation_live_harness_model_helpers import LiveCase
except ModuleNotFoundError:  # pragma: no cover - direct helper import
    from approval_continuation_live_harness_model_helpers import LiveCase  # type: ignore[no-redef]


def _prompt_for_case(case: LiveCase) -> str:
    if case.tool_name == "apply_patch":
        patch = (
            "*** Begin Patch\n"
            f"*** Add File: {case.target_file}\n"
            f"+{case.expected_content}\n"
            "*** End Patch"
        )
        return (
            "Use the `apply_patch` tool exactly once with this exact patch in the current workspace:\n"
            f"{patch}\n"
            "Do not use exec_command, write_file, or any other file-writing tool. "
            "Do not answer before the tool returns. "
            "After the tool returns, briefly state whether the patch result was approved and visible."
        )
    command = f"printf '{case.expected_content}\\n' > {case.target_file}"
    return (
        "Use the `exec_command` tool exactly once to run this exact command in the current workspace:\n"
        f"{command}\n"
        "Do not use apply_patch, write_file, or any other file-writing tool. "
        "Do not answer before the tool returns. "
        "After the tool returns, briefly state whether the command result was approved and visible."
    )


def _prompt_for_case_provider(case: LiveCase, *, provider: str) -> str:
    normalized_provider = str(provider or "").strip().lower()
    if case.tool_name == "apply_patch" and normalized_provider in {"anthropic", "claude", "claude_code"}:
        write_args = {"file_path": case.target_file, "content": f"{case.expected_content}\n"}
        return (
            "Use the `Write` tool exactly once in the current workspace with this exact JSON input:\n"
            f"{json.dumps(write_args, ensure_ascii=False)}\n"
            "Do not use Bash, exec_command, apply_patch, or any other file-writing tool. "
            "Do not answer before the tool returns. "
            "After the tool returns, briefly state whether the write result was approved and visible."
        )
    if case.tool_name == "exec_command" and normalized_provider in {"anthropic", "claude", "claude_code"}:
        bash_args = {"command": f"printf '{case.expected_content}\\n' > {case.target_file}"}
        return (
            "Use the `Bash` tool exactly once in the current workspace with this exact JSON input:\n"
            f"{json.dumps(bash_args, ensure_ascii=False)}\n"
            "Do not use write_stdin, Write, Edit, exec_command, apply_patch, or any other file-writing tool. "
            "Do not answer before the tool returns. "
            "After the tool returns, briefly state whether the command result was approved and visible."
        )
    return _prompt_for_case(case)
