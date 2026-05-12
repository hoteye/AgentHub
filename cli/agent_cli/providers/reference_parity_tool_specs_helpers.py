from __future__ import annotations

from typing import Any, Callable, Dict, List


def delegation_tool_specs(
    *,
    function_tool_fn: Callable[..., Dict[str, Any]],
    scalar_schema_fn: Callable[..., Dict[str, Any]],
    delegation_mode_values: List[str],
    delegation_task_shapes: List[str],
    spawn_agent_reason_codes: List[str],
    wait_agent_reason_codes: List[str],
    recover_agent_action_values: List[str],
) -> List[Dict[str, Any]]:
    return [
        function_tool_fn(
            name="spawn_agent",
            description=(
                "Run a delegated subagent or teammate task synchronously and return its result, "
                "or start it in background when async=true. "
                "When model is omitted, use the current delegation contract for the selected role. "
                "Use this only for bounded side tasks such as independent research, parallel verification, "
                "or long-running benchmark/exec work. "
                "Prefer sync delegation, or staying local, for context-sensitive follow-ups and workspace-mutating tasks."
            ),
            properties={
                "task": scalar_schema_fn("string", "Delegated task prompt."),
                "role": scalar_schema_fn("string", "Delegation role. Use subagent or teammate."),
                "model": scalar_schema_fn("string", "Optional model selector. Use inherit to follow the current main model."),
                "provider": scalar_schema_fn("string", "Optional provider override."),
                "reasoning_effort": scalar_schema_fn("string", "Optional reasoning effort override."),
                "timeout": scalar_schema_fn("number", "Optional delegated request timeout in seconds."),
                "async": scalar_schema_fn("boolean", "When true, start the delegated agent in background and return its agent id."),
                "reason": {"type": "string", "description": "Optional delegation reason code for traceability.", "enum": spawn_agent_reason_codes},
                "mode": {"type": "string", "description": "Optional delegation mode hint. Use sync or background.", "enum": delegation_mode_values},
                "wait_required": scalar_schema_fn("boolean", "Optional hint describing whether the parent expects to wait for this child result."),
                "task_shape": {"type": "string", "description": "Optional task-shape hint for delegation policy and observability.", "enum": delegation_task_shapes},
            },
            required=["task"],
        ),
        function_tool_fn(
            name="send_input",
            description=(
                "Queue one follow-up message for an existing delegated agent session. "
                "Use interrupt=true to preempt the active turn and prioritize this message ahead of queued input. "
                "Use this only after a delegated agent already exists; it is not a replacement for main-thread reasoning."
            ),
            properties={
                "target": scalar_schema_fn("string", "Delegated agent id."),
                "message": scalar_schema_fn("string", "Follow-up message to queue."),
                "interrupt": scalar_schema_fn("boolean", "When true, prioritize this message ahead of other queued input."),
            },
            required=["target", "message"],
        ),
        function_tool_fn(
            name="resume_agent",
            description=(
                "Reopen a previously closed delegated agent session so it can accept follow-up input again. "
                "Use this only to continue an existing child workflow, not as a substitute for spawning a fresh task."
            ),
            properties={"target": scalar_schema_fn("string", "Delegated agent id.")},
            required=["target"],
        ),
        function_tool_fn(
            name="wait_agent",
            description=(
                "Wait for a delegated agent session to reach a terminal state or timeout, then return its latest result. "
                "Use this only when the next step explicitly depends on that delegated result. "
                "When wait_required=false, return only the latest status snapshot without blocking. "
                "Planner-side execution may service non-blocking snapshots via agent_workflow instead of a true wait join. "
                "Prefer agent_workflow when you only need child status or recovery options."
            ),
            properties={
                "target": scalar_schema_fn("string", "Delegated agent id."),
                "timeout_ms": scalar_schema_fn("number", "How long to wait in milliseconds before returning pending status."),
                "reason": {"type": "string", "description": "Optional wait reason code for traceability.", "enum": wait_agent_reason_codes},
                "wait_required": scalar_schema_fn("boolean", "Optional hint confirming that the parent currently depends on the child result."),
            },
            required=["target"],
        ),
        function_tool_fn(
            name="agent_workflow",
            description=("Inspect delegated workflow state, recent steps, checkpoints, and available recovery actions without blocking execution."),
            properties={
                "target": scalar_schema_fn("string", "Delegated agent id."),
                "steps": scalar_schema_fn("number", "Optional max number of recent steps to include."),
                "checkpoints": scalar_schema_fn("number", "Optional max number of recent checkpoints to include."),
            },
            required=["target"],
        ),
        function_tool_fn(
            name="recover_agent",
            description=(
                "Apply one recovery action to a delegated workflow. "
                "Prefer action=retry_step when retrying the same child preserves context better than spawning a duplicate task."
            ),
            properties={
                "target": scalar_schema_fn("string", "Delegated agent id."),
                "action": {"type": "string", "description": "Optional recovery action. retry_step is the default when omitted.", "enum": recover_agent_action_values},
                "step_id": scalar_schema_fn("string", "Optional failed/cancelled step id to recover explicitly."),
            },
            required=["target"],
        ),
        function_tool_fn(
            name="close_agent",
            description=(
                "Close one delegated agent session and reject future follow-up input until resumed. "
                "Use this when a child is stale or no longer useful, not as a normal planning step for main-thread work."
            ),
            properties={"target": scalar_schema_fn("string", "Delegated agent id.")},
            required=["target"],
        ),
    ]


def plan_and_user_input_specs(
    *,
    config: Any,
    function_tool_fn: Callable[..., Dict[str, Any]],
    scalar_schema_fn: Callable[..., Dict[str, Any]],
    array_schema_fn: Callable[..., Dict[str, Any]],
    object_schema_fn: Callable[..., Dict[str, Any]],
    request_user_input_description_fn: Callable[[Any], str],
    update_plan_description: str,
) -> List[Dict[str, Any]]:
    return [
        function_tool_fn(
            name="update_plan",
            description=update_plan_description,
            properties={
                "explanation": scalar_schema_fn("string"),
                "plan": array_schema_fn(
                    description="The list of steps",
                    items=object_schema_fn(
                        properties={
                            "status": scalar_schema_fn("string", "One of: pending, in_progress, completed"),
                            "step": scalar_schema_fn("string"),
                        },
                        required=["step", "status"],
                    ),
                ),
            },
            required=["plan"],
        ),
        function_tool_fn(
            name="request_user_input",
            description=request_user_input_description_fn(config),
            properties={
                "questions": array_schema_fn(
                    description="Questions to show the user. Prefer 1 and do not exceed 3",
                    items=object_schema_fn(
                        properties={
                            "header": scalar_schema_fn("string", "Short header label shown in the UI (12 or fewer chars)."),
                            "id": scalar_schema_fn("string", "Stable identifier for mapping answers (snake_case)."),
                            "options": array_schema_fn(
                                description='Provide 2-3 mutually exclusive choices. Put the recommended option first and suffix its label with "(Recommended)". Do not include an "Other" option in this list; the client will add a free-form "Other" option automatically.',
                                items=object_schema_fn(
                                    properties={
                                        "description": scalar_schema_fn("string", "One short sentence explaining impact/tradeoff if selected."),
                                        "label": scalar_schema_fn("string", "User-facing label (1-5 words)."),
                                    },
                                    required=["label", "description"],
                                ),
                            ),
                            "question": scalar_schema_fn("string", "Single-sentence prompt shown to the user."),
                        },
                        required=["id", "header", "question", "options"],
                    ),
                ),
            },
            required=["questions"],
        ),
    ]


def append_apply_patch_and_tail_specs(
    *,
    specs: List[Dict[str, Any]],
    apply_patch_tool_type: str,
    apply_patch_description: str,
    load_apply_patch_grammar_fn: Callable[[], str],
    function_tool_fn: Callable[..., Dict[str, Any]],
    scalar_schema_fn: Callable[..., Dict[str, Any]],
    external_web_access: bool,
) -> None:
    if apply_patch_tool_type == "freeform":
        specs.append(
            {
                "description": apply_patch_description,
                "format": {
                    "definition": load_apply_patch_grammar_fn(),
                    "syntax": "lark",
                    "type": "grammar",
                },
                "name": "apply_patch",
                "type": "custom",
            }
        )
    elif apply_patch_tool_type == "function":
        specs.append(
            function_tool_fn(
                name="apply_patch",
                description="Use the `apply_patch` tool to edit files.",
                properties={"input": scalar_schema_fn("string", "The entire contents of the apply_patch command")},
                required=["input"],
            )
        )
    specs.extend(
        [
            {
                "external_web_access": external_web_access,
                "type": "web_search",
            },
            function_tool_fn(
                name="view_image",
                description="View a local image from the filesystem (only use if given a full filepath by the user, and the image isn't already attached to the thread context within <image ...> tags).",
                properties={"path": scalar_schema_fn("string", "Local filesystem path to an image file")},
                required=["path"],
            ),
        ]
    )
