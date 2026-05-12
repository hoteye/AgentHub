from pathlib import Path
from types import SimpleNamespace

from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_core.tool_commands import handle_runtime_policy_command


class _StatusAgent:
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "glm",
            "provider_public_name": "glm",
            "model_key": "glm_5",
            "provider_planner": "openai_chat",
            "provider_model": "glm-5",
            "provider_reasoning_effort": "high",
            "provider_tools": "tool-calls",
            "session_line": "glm-tools",
            "provider_label": "glm | glm-5 | tool-calls",
            "provider_base_url": "https://open.bigmodel.cn/api/paas/v4",
            "provider_source": "test",
            "model_context_window": "100000",
        }


def test_status_command_reports_codex_style_runtime_card(tmp_path: Path) -> None:
    (tmp_path / "AENGTHUB.md").write_text("# instructions\n", encoding="utf-8")
    runtime = SimpleNamespace(
        agent=_StatusAgent(),
        cwd=str(tmp_path),
        thread_id="thread_status",
        collaboration_mode="default",
        history_turns=[],
        runtime_policy_status=lambda: {
            "approval_policy": "on-request",
            "sandbox_mode": "workspace-write",
            "network_access": "enabled",
        },
    )

    result = handle_runtime_policy_command(runtime, name="status", arg_text="")

    assert isinstance(result, CommandExecutionResult)
    assert "╭" in result.assistant_text
    assert ">_ AgentHub" in result.assistant_text
    assert "Model:" in result.assistant_text
    assert "glm-5 (reasoning high, summaries auto)" in result.assistant_text
    assert "Model provider:" in result.assistant_text
    assert "Directory:" in result.assistant_text
    assert "Permissions:" in result.assistant_text
    assert "Agents.md:" in result.assistant_text
    assert "AENGTHUB.md" in result.assistant_text
    assert "Collaboration mode:" in result.assistant_text
    assert "Session:" in result.assistant_text
    assert "thread_status" in result.assistant_text
    assert "Token usage:" in result.assistant_text
    assert "Context window:" in result.assistant_text
    assert "Limits:" in result.assistant_text
    assert result.assistant_text.strip() != "runtime status"
