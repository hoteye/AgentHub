from __future__ import annotations

from typing import Any, Callable, Dict, List


def _reference_collab_input_items_schema(
    *,
    scalar_schema_fn: Callable[..., Dict[str, Any]],
    array_schema_fn: Callable[..., Dict[str, Any]],
    object_schema_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    return array_schema_fn(
        description=(
            "Structured input items. Use this to pass explicit mentions "
            "(for example app:// connector paths)."
        ),
        items=object_schema_fn(
            properties={
                "image_url": scalar_schema_fn(
                    "string",
                    "Image URL when type is image.",
                ),
                "name": scalar_schema_fn(
                    "string",
                    "Display name when type is skill or mention.",
                ),
                "path": scalar_schema_fn(
                    "string",
                    "Path when type is local_image/skill, or structured mention target such as app://<connector-id> or plugin://<plugin-name>@<marketplace-name> when type is mention.",
                ),
                "text": scalar_schema_fn(
                    "string",
                    "Text content when type is text.",
                ),
                "type": {
                    "type": "string",
                    "description": "Input item type: text, image, local_image, skill, or mention.",
                },
            },
        ),
    )


def reference_collab_tool_specs(
    *,
    function_tool_fn: Callable[..., Dict[str, Any]],
    scalar_schema_fn: Callable[..., Dict[str, Any]],
    array_schema_fn: Callable[..., Dict[str, Any]],
    object_schema_fn: Callable[..., Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        function_tool_fn(
            name="spawn_agent",
            description=(
                "Spawn a sub-agent for a well-scoped task. Returns the agent id "
                "(and user-facing nickname when available) to use to communicate "
                "with this agent."
            ),
            properties={
                "agent_type": scalar_schema_fn(
                    "string",
                    "Optional type name for the new agent.",
                ),
                "fork_context": scalar_schema_fn(
                    "boolean",
                    "When true, fork the current thread history into the new agent before sending the initial prompt. This must be used when you want the new agent to have exactly the same context as you.",
                ),
                "items": _reference_collab_input_items_schema(
                    scalar_schema_fn=scalar_schema_fn,
                    array_schema_fn=array_schema_fn,
                    object_schema_fn=object_schema_fn,
                ),
                "message": scalar_schema_fn(
                    "string",
                    "Initial plain-text task for the new agent. Use either message or items.",
                ),
            },
            required=[],
        ),
        function_tool_fn(
            name="send_input",
            description=(
                "Send a message to an existing agent. Use interrupt=true to redirect work immediately."
            ),
            properties={
                "interrupt": scalar_schema_fn(
                    "boolean",
                    "When true, stop the agent's current task and handle this immediately. When false (default), queue this message.",
                ),
                "items": _reference_collab_input_items_schema(
                    scalar_schema_fn=scalar_schema_fn,
                    array_schema_fn=array_schema_fn,
                    object_schema_fn=object_schema_fn,
                ),
                "message": scalar_schema_fn(
                    "string",
                    "Legacy plain-text message to send to the agent. Use either message or items.",
                ),
                "target": scalar_schema_fn("string", "Agent id to message (from spawn_agent)."),
            },
            required=["target"],
        ),
        function_tool_fn(
            name="resume_agent",
            description=(
                "Resume a previously closed agent by id so it can receive send_input and wait calls."
            ),
            properties={"id": scalar_schema_fn("string", "Agent id to resume.")},
            required=["id"],
        ),
        function_tool_fn(
            name="wait_agent",
            description=(
                "Wait for agents to reach a final status. Completed statuses may include the agent's final message. "
                "Returns empty status when timed out."
            ),
            properties={
                "targets": array_schema_fn(
                    items=scalar_schema_fn("string"),
                    description="Agent ids to wait on. Pass multiple ids to wait for whichever finishes first.",
                ),
                "timeout_ms": scalar_schema_fn(
                    "number",
                    "Optional timeout in milliseconds before returning pending status.",
                ),
            },
            required=["targets"],
        ),
        function_tool_fn(
            name="close_agent",
            description=(
                "Close an agent when it is no longer needed and return its last known status."
            ),
            properties={"target": scalar_schema_fn("string", "Agent id to close (from spawn_agent).")},
            required=["target"],
        ),
    ]
