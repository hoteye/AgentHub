from __future__ import annotations

from typing import Optional

from cli.agent_cli.models import AgentIntent, ToolEvent
from cli.agent_cli.runtime import AgentCliRuntime


def _event(name: str, *, ok: bool = True, summary: str = "ok", payload: dict | None = None) -> ToolEvent:
    return ToolEvent(name=name, ok=ok, summary=summary, payload=payload or {})


class DemoAgent:
    def provider_status(self) -> dict[str, str]:
        return {
            "provider_ready": "true",
            "provider_name": "deepseek",
            "provider_planner": "deepseek_reasoner",
            "provider_model": "deepseek-reasoner",
            "provider_tools": "tool-calls",
            "session_line": "reasoner",
            "provider_label": "deepseek | deepseek-reasoner | tool-calls",
            "provider_base_url": "https://api.deepseek.com",
            "provider_source": "project_local",
            "provider_config_path": "C:/project/AgentHub/cli/.agent_cli/config.toml",
            "provider_auth_path": "C:/project/AgentHub/cli/.agent_cli/auth.json",
            "platform_family": "windows",
            "platform_os": "windows",
            "shell_kind": "powershell",
        }

    def plan(self, text: str, history=None, *, tool_executor=None, attachments=None):
        normalized = text.strip().lower()
        if "python version" in normalized or "python -v" in normalized:
            return AgentIntent(
                assistant_text="Recognized as a Python version query. Preparing shell execution.",
                command_text="/shell python -V",
                status_hint="tool",
            )
        if "office skill" in normalized:
            return AgentIntent(
                assistant_text="Recognized as an office skill query. Preparing skill listing.",
                command_text="/office_skills",
                status_hint="tool",
            )
        return AgentIntent(assistant_text=f"echo: {text}")


class DemoTools:
    def capabilities(self) -> dict:
        return {
            "ok": True,
            "tools": [
                {"name": "shell", "description": "shell"},
                {"name": "office_skills", "description": "office skills"},
                {"name": "office_run", "description": "office run"},
            ],
        }

    def shell(self, command: str) -> ToolEvent:
        return _event(
            "shell",
            summary=f"shell ok: {command}",
            payload={
                "command": command,
                "returncode": 0,
                "stdout": "Python 3.11.9\n" if command == "python -V" else "",
                "stderr": "",
                "duration_ms": 12,
            },
        )

    def office_skills(self) -> ToolEvent:
        return _event(
            "office_skills",
            summary="office_skills=1",
            payload={"ok": True, "count": 1, "skills": [{"name": "read_docx_markdown"}]},
        )

    def office_run(self, skill_name: str, *, args=None) -> ToolEvent:
        return _event(
            "office_run",
            summary=skill_name,
            payload={"ok": True, "skill_name": skill_name, "args": args or {}},
        )


def build_demo_runtime(target_conversation: Optional[str] = None) -> AgentCliRuntime:
    _ = target_conversation
    return AgentCliRuntime(tools=DemoTools(), agent=DemoAgent())
