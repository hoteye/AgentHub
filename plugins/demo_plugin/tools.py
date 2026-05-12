from __future__ import annotations

from cli.agent_cli.models import ToolEvent


def _demo_echo(*, text: str = "pong") -> ToolEvent:
    value = str(text or "").strip() or "pong"
    return ToolEvent(
        name="demo_echo",
        ok=True,
        summary=f"demo echo: {value}",
        payload={
            "ok": True,
            "plugin_name": "demo_plugin",
            "text": value,
        },
    )


def register_tools(registry) -> None:
    registry.add_tool(
        name="demo_echo",
        label="Demo Echo",
        description="Minimal demo-plugin tool used to validate plugin tool exposure.",
        handler=_demo_echo,
        mutates_ui=False,
        requires_confirmation=False,
    )
