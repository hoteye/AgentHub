from __future__ import annotations

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events


def _demo_ping(arg_text: str, runtime) -> CommandExecutionResult:
    message = str(arg_text or "").strip() or "pong"
    event = runtime.tools.invoke_plugin_tool("demo_echo", text=message)
    return CommandExecutionResult(
        assistant_text=f"demo_plugin responded: {message}",
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name="demo_echo",
            arguments={"text": message},
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )


def register_commands(registry) -> None:
    registry.add_command(
        name="demo_ping",
        usage="/demo_ping [text]",
        description="run the demo plugin command path",
        handler=_demo_ping,
    )
