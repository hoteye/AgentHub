from __future__ import annotations

import asyncio
import sys
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = CLI_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.demo_runtime_support import build_demo_runtime

OUTPUT_PATH = CLI_ROOT / "artifacts" / "agent_cli_ui_prompt_smoke.svg"
PROMPT_TEXT = "Show the available office skills and the current Python version."


async def _capture() -> Path:
    app = AgentCliApp(runtime=build_demo_runtime())

    async with app.run_test() as pilot:
        await pilot.resize_terminal(120, 40)
        await pilot.click("#prompt_composer")
        app._set_prompt_text(PROMPT_TEXT)
        await app.action_submit_prompt()
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
