from __future__ import annotations

import asyncio
import sys
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CLI_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import ActivityEvent


OUTPUT_PATH = CLI_ROOT / "artifacts" / "agent_cli_ui_smoke.svg"


async def _capture() -> Path:
    app = AgentCliApp()

    async with app.run_test() as pilot:
        app._write_system_notice("Ready. Start with /provider, /plugins, or /tools.")
        app._write_user_prompt("List available tools, then run a shell command to show the current Python version.")
        app._write_activity_event(
            ActivityEvent(
                title="Updated Plan",
                status="info",
                kind="plan",
                detail="1. /tools\n2. /shell python -V",
            )
        )
        app._write_activity_event(ActivityEvent(title="tools", status="running", kind="tool"))
        app._write_activity_event(
            ActivityEvent(
                title="Listed local capabilities",
                status="success",
                kind="tool",
                detail="shell, office_skills, office_run",
            )
        )
        app._write_activity_event(ActivityEvent(title="python -V", status="running", kind="command"))
        app._write_activity_event(
            ActivityEvent(
                title="Python 3.11.9",
                status="info",
                kind="command_output",
                detail="stdout",
            )
        )
        app._write_activity_event(
            ActivityEvent(
                title="Ran python -V",
                status="success",
                kind="command",
                detail="exit 0 | 0.12s",
            )
        )
        app._write_assistant_reply(
            "Capabilities listed.\nShell command completed successfully."
        )
        app._update_status(
            {
                "session_started": "2026-03-22 10:00:00",
                "prompt_count": "3",
                "provider_model": "gpt-5.4",
                "provider_ready": "true",
                "selected_conversation": "-",
                "last_tool": "shell",
                "last_ok": "true",
                "send_ready": "false",
                "provider_config_path": "C:/project/AgentHub/cli/.agent_cli/config.toml",
                "provider_auth_path": "C:/project/AgentHub/cli/.agent_cli/auth.json",
            }
        )
        await pilot.pause()
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        app.save_screenshot(str(OUTPUT_PATH))
        return OUTPUT_PATH


def main() -> int:
    output = asyncio.run(_capture())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
