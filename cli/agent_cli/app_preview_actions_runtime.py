from __future__ import annotations

from typing import Any

from cli.agent_cli import app_event_helpers


def action_toggle_latest_web_item(app: Any) -> None:
    app_event_helpers.action_toggle_latest_web_item(app)


__all__ = ["action_toggle_latest_web_item"]
