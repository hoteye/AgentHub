from __future__ import annotations


def _command_usage_text(name: str) -> str:
    from cli.agent_cli.providers.tool_specs import command_usage_text

    return command_usage_text(name)


def _shell_usage_text() -> str:
    return _command_usage_text("shell") or (
        "Usage: /shell <command>\n"
        "       /shell start <command>\n"
        "       /shell write <session_id> <chars>\n"
        "       /shell terminate <session_id>"
    )


def _apply_patch_usage_text() -> str:
    return _command_usage_text("apply_patch") or "Usage: /apply_patch <patch>"


def _spawn_agent_usage_text() -> str:
    return _command_usage_text("spawn_agent") or (
        "Usage: /spawn_agent "
        "'{\"task\":\"...\",\"role\":\"subagent|teammate\",\"model\":\"inherit|selector\","
        "\"provider\":\"name\",\"reasoning_effort\":\"level\",\"timeout\":30,\"async\":true,"
        "\"reason\":\"research_side_task\",\"mode\":\"background\",\"wait_required\":false,\"task_shape\":\"read_only\"}'"
    )


def _send_input_usage_text() -> str:
    return _command_usage_text("send_input") or "Usage: /send_input <agent_id> <message> [interrupt]"


def _resume_agent_usage_text() -> str:
    return _command_usage_text("resume_agent") or "Usage: /resume_agent <agent_id>"


def _wait_agent_usage_text() -> str:
    return _command_usage_text("wait_agent") or "Usage: /wait_agent <agent_id> [timeout-ms <n>] [reason <wait_for_child_result>] [wait-required <true|false>]  # false => status snapshot only"


def _close_agent_usage_text() -> str:
    return _command_usage_text("close_agent") or "Usage: /close_agent <agent_id>"


def _agent_workflow_usage_text() -> str:
    return _command_usage_text("agent_workflow") or "Usage: /agent_workflow <agent_id> [steps <n>] [checkpoints <n>]"


def _recover_agent_usage_text() -> str:
    return _command_usage_text("recover_agent") or "Usage: /recover_agent <agent_id> [action <retry_step|resume_session|close_session>] [step-id <id>]"
