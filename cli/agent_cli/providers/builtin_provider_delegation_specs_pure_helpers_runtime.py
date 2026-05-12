from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime
from cli.agent_cli.providers.builtin_provider_delegation_surface_helpers import (
    _CLAUDE_AGENT_TOOL_NAME,
    _CLAUDE_SEND_MESSAGE_TOOL_NAME,
    _CODEX_WAIT_TOOL_NAME,
)
from cli.agent_cli.providers.delegation_policy import (
    DELEGATION_MODE_VALUES,
    DELEGATION_TASK_SHAPES,
    RECOVER_AGENT_ACTION_VALUES,
    SPAWN_AGENT_REASON_CODES,
    WAIT_AGENT_REASON_CODES,
)

ProviderDescription = Callable[[str], str]

_REASONING_EFFORT_VALUES = ["low", "medium", "high", "xhigh", "default", "inherit"]
_RISK_LEVEL_VALUES = ["low", "medium", "high"]

_CODEX_WAIT_DESCRIPTION = (
    "Wait for agents to reach a final status. Completed statuses may include the agent's final message. "
    "Returns empty status when timed out. "
    "Use this only when the next step explicitly depends on that delegated result. "
    "Prefer longer waits (minutes) to avoid busy polling."
)

_CLAUDE_AGENT_DESCRIPTION = builtin_agent_profiles_runtime.claude_agent_tool_description()

_CLAUDE_SEND_MESSAGE_DESCRIPTION = (
    "Send one follow-up message to an existing delegated child identified by agent id. "
    "Use this as the continuation surface for an existing child; AgentHub does not expose a separate Claude-style "
    "wait or TaskStop tool on this profile."
)

_SPEC_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "spawn_agent": {
        "name": "spawn_agent",
        "description_name": "spawn_agent",
        "properties": {
            "task": {"type": "string", "description": "Delegated task prompt."},
            "role": {
                "type": "string",
                "description": "Delegation role. Use subagent or teammate.",
                "enum": ["subagent", "teammate"],
            },
            "model": {
                "type": "string",
                "description": "Optional model selector. Use inherit to follow the current main model.",
            },
            "provider": {"type": "string", "description": "Optional provider override."},
            "reasoning_effort": {
                "type": "string",
                "description": "Optional reasoning effort override.",
                "enum": list(_REASONING_EFFORT_VALUES),
            },
            "timeout": {
                "type": "integer",
                "description": "Optional delegated request timeout in seconds.",
            },
            "async": {
                "type": "boolean",
                "description": "When true, start the delegated agent in background and return its agent id.",
            },
            "reason": {
                "type": "string",
                "description": "Optional delegation reason code for traceability.",
                "enum": list(SPAWN_AGENT_REASON_CODES),
            },
            "mode": {
                "type": "string",
                "description": "Optional delegation mode hint. Use sync or background.",
                "enum": list(DELEGATION_MODE_VALUES),
            },
            "wait_required": {
                "type": "boolean",
                "description": "Optional hint describing whether the parent expects to wait for this child result.",
            },
            "task_shape": {
                "type": "string",
                "description": "Optional task-shape hint for delegation policy and observability.",
                "enum": list(DELEGATION_TASK_SHAPES),
            },
        },
        "required": ["task"],
    },
    "request_orchestration": {
        "name": "request_orchestration",
        "description_name": "request_orchestration",
        "properties": {
            "source_text": {
                "type": "string",
                "description": "Original task text or taskbook markdown to escalate into orchestration preview.",
            },
            "goal": {
                "type": "string",
                "description": "Short objective summary for preview UI title and confirmation context.",
            },
            "reason": {
                "type": "string",
                "description": "Why this task should be upgraded to orchestration instead of staying local.",
            },
            "proposed_scope": {
                "type": "string",
                "description": "Optional scope suggestion for planner-side preview context.",
            },
            "risk_level": {
                "type": "string",
                "description": "Optional risk hint for orchestration escalation.",
                "enum": list(_RISK_LEVEL_VALUES),
            },
            "needs_confirmation": {
                "type": "boolean",
                "description": "Whether preview must be confirmed before creating a persistent run.",
            },
        },
        "required": ["source_text", "goal", "reason", "needs_confirmation"],
    },
    "spawn_child_tab": {
        "name": "spawn_child_tab",
        "description_name": "spawn_child_tab",
        "properties": {
            "task": {
                "type": "string",
                "description": "Assignment prompt to queue into the visible child tab.",
            },
            "task_name": {
                "type": "string",
                "description": "Optional short label for the child tab and task.",
            },
            "parent": {
                "type": "string",
                "description": "Optional parent/master tab selector. Defaults to the active tab.",
            },
            "metadata": {
                "type": "object",
                "description": "Optional structured metadata for traceability.",
                "additionalProperties": True,
            },
        },
        "required": ["task"],
    },
    "send_child_tab": {
        "name": "send_child_tab",
        "description_name": "send_child_tab",
        "properties": {
            "target": {
                "type": "string",
                "description": "Visible child tab selector, such as tab id, visible tab label, latest, or last.",
            },
            "message": {"type": "string", "description": "Follow-up instruction to queue."},
            "interrupt": {
                "type": "boolean",
                "description": "When true, prioritize this message ahead of other queued child input.",
            },
            "metadata": {
                "type": "object",
                "description": "Optional structured metadata for traceability.",
                "additionalProperties": True,
            },
        },
        "required": ["target", "message"],
    },
    "wait_child_tasks": {
        "name": "wait_child_tasks",
        "description_name": "wait_child_tasks",
        "properties": {
            "targets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional visible child tab selectors to inspect.",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Optional maximum wait in milliseconds before returning current snapshots.",
            },
            "wait_for": {
                "type": "string",
                "description": "Join mode. Use all to wait for every selected latest child task, or any to return when the first selected child task reaches a terminal state.",
                "enum": ["all", "any"],
            },
            "include_all": {
                "type": "boolean",
                "description": "When true, include all visible children for the parent/master tab.",
            },
            "terminal_only": {
                "type": "boolean",
                "description": "When true, return only terminal TaskRun snapshots.",
            },
        },
        "required": [],
    },
    "send_input": {
        "name": "send_input",
        "description_name": "send_input",
        "properties": {
            "target": {"type": "string", "description": "Delegated agent id."},
            "message": {"type": "string", "description": "Follow-up message to queue."},
            "interrupt": {
                "type": "boolean",
                "description": "When true, prioritize this message ahead of other queued input.",
            },
        },
        "required": ["target", "message"],
    },
    "resume_agent": {
        "name": "resume_agent",
        "description_name": "resume_agent",
        "properties": {
            "target": {"type": "string", "description": "Delegated agent id."},
        },
        "required": ["target"],
    },
    "wait_agent": {
        "name": "wait_agent",
        "description_name": "wait_agent",
        "properties": {
            "target": {"type": "string", "description": "Delegated agent id."},
            "timeout_ms": {
                "type": "integer",
                "description": "How long to wait in milliseconds before returning pending status.",
            },
            "reason": {
                "type": "string",
                "description": "Optional wait reason code for traceability.",
                "enum": list(WAIT_AGENT_REASON_CODES),
            },
            "wait_required": {
                "type": "boolean",
                "description": "Optional hint confirming that the parent currently depends on the child result.",
            },
        },
        "required": ["target"],
    },
    "codex_wait": {
        "name": _CODEX_WAIT_TOOL_NAME,
        "description": _CODEX_WAIT_DESCRIPTION,
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Delegated agent ids to wait on. Pass multiple ids to wait for whichever finishes first.",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Optional timeout in milliseconds before returning pending status.",
            },
        },
        "required": ["ids"],
    },
    "claude_agent": {
        "name": _CLAUDE_AGENT_TOOL_NAME,
        "description": _CLAUDE_AGENT_DESCRIPTION,
        "properties": {
            "description": {
                "type": "string",
                "description": "Optional short 3-5 word English task label for transcript and status views.",
            },
            "prompt": {
                "type": "string",
                "description": (
                    "Delegated task prompt for the child agent. Write this prompt in English; "
                    "the parent response to the user can still use the user's language."
                ),
            },
            "subagent_type": {
                "type": "string",
                "description": (
                    "Specialized agent type. Use Explore for open-ended codebase exploration, broad file search, "
                    "or answering questions about how the codebase works."
                ),
                "enum": [builtin_agent_profiles_runtime.EXPLORE_AGENT_TYPE],
            },
            "model": {
                "type": "string",
                "description": (
                    "Optional model override for this agent. Takes precedence over the agent "
                    "definition's model frontmatter. If omitted, uses the agent definition's "
                    "model, or inherits from the parent."
                ),
                "enum": ["sonnet", "opus", "haiku"],
            },
            "run_in_background": {
                "type": "boolean",
                "description": "Set to true to run this agent in the background. You will be notified when it completes.",
            },
        },
        "required": ["description", "prompt"],
    },
    "claude_send_message": {
        "name": _CLAUDE_SEND_MESSAGE_TOOL_NAME,
        "description": _CLAUDE_SEND_MESSAGE_DESCRIPTION,
        "properties": {
            "to": {
                "type": "string",
                "description": "Delegated agent id returned by Agent.",
            },
            "message": {
                "type": "string",
                "description": "Follow-up message to send to that delegated child.",
            },
            "interrupt": {
                "type": "boolean",
                "description": "When true, prioritize this message ahead of other queued child input.",
            },
        },
        "required": ["to", "message"],
    },
    "agent_workflow": {
        "name": "agent_workflow",
        "description_name": "agent_workflow",
        "properties": {
            "target": {"type": "string", "description": "Delegated agent id."},
            "steps": {
                "type": "integer",
                "description": "Optional max number of recent steps to include in the workflow snapshot.",
            },
            "checkpoints": {
                "type": "integer",
                "description": "Optional max number of recent checkpoints to include in the workflow snapshot.",
            },
        },
        "required": ["target"],
    },
    "recover_agent": {
        "name": "recover_agent",
        "description_name": "recover_agent",
        "properties": {
            "target": {"type": "string", "description": "Delegated agent id."},
            "action": {
                "type": "string",
                "description": "Optional recovery action. retry_step is the default when omitted.",
                "enum": list(RECOVER_AGENT_ACTION_VALUES),
            },
            "step_id": {
                "type": "string",
                "description": "Optional failed/cancelled step id to recover explicitly.",
            },
        },
        "required": ["target"],
    },
    "close_agent": {
        "name": "close_agent",
        "description_name": "close_agent",
        "properties": {
            "target": {"type": "string", "description": "Delegated agent id."},
        },
        "required": ["target"],
    },
}


def delegation_spec_kwargs(
    name: str,
    *,
    provider_description: ProviderDescription,
) -> dict[str, Any]:
    blueprint = _SPEC_BLUEPRINTS[name]
    kwargs = copy.deepcopy(blueprint)
    description_name = str(kwargs.pop("description_name", "") or "").strip()
    if description_name:
        kwargs["description"] = provider_description(description_name)
    return kwargs
