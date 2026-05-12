from __future__ import annotations

from collections.abc import Callable
from typing import Any

SurfaceUsageTextFn = Callable[[str], str]
ContractMetadataFn = Callable[..., dict[str, Any]]
StaticContractMetadataFn = Callable[[], dict[str, Any]]


def runtime_and_delegation_tool_specs(
    *,
    surface_usage_text_fn: SurfaceUsageTextFn,
    command_execution_contract_metadata: ContractMetadataFn,
    apply_patch_contract_metadata: StaticContractMetadataFn,
) -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "exec_command",
            "label": "Exec Command",
            "description": "Runs a command in a PTY, returning output or a session ID for ongoing interaction.",
            "usage_text": f"Usage: {surface_usage_text_fn('exec_command')}",
            "provider_description": "Runs a command in a PTY, returning output or a session ID for ongoing interaction.",
            **command_execution_contract_metadata(tool_name="exec_command", tool_role="primary"),
        },
        {
            "name": "write_stdin",
            "label": "Write Stdin",
            "description": "Writes characters to an existing unified exec session and returns recent output.",
            "usage_text": f"Usage: {surface_usage_text_fn('write_stdin')}",
            "provider_description": "Writes characters to an existing unified exec session and returns recent output.",
            **command_execution_contract_metadata(
                tool_name="write_stdin", tool_role="continuation"
            ),
        },
        {
            "name": "spawn_agent",
            "label": "Spawn Agent",
            "description": (
                "Run a delegated subagent or teammate task synchronously and return its result. "
                "Use this for bounded side tasks that should reuse the current workspace and toolchain."
            ),
            "usage_text": (
                "Usage: /spawn_agent "
                '\'{"task":"...","role":"subagent|teammate","model":"inherit|selector",'
                '"provider":"name","reasoning_effort":"low|medium|high|xhigh","timeout":30,"async":true,'
                '"reason":"research_side_task","mode":"background","wait_required":false,"task_shape":"read_only"}\''
            ),
            "provider_description": (
                "Run a delegated subagent or teammate task synchronously and return its result, "
                "or start it in background when async=true. "
                "When model is omitted, use the current delegation contract for the selected role. "
                "Use this only for bounded side tasks that can run semi-independently from the mainline. "
                "Typical good fits are independent research, parallel verification, or long-running benchmark/exec work. "
                "Prefer sync delegation, or staying local, for context-sensitive follow-ups and workspace-mutating tasks. "
                "Do not delegate tightly coupled mainline reasoning or immediate code-edit decisions. "
                "Use async=true only when the child can finish later without blocking the immediate next step."
            ),
        },
        {
            "name": "request_orchestration",
            "label": "Request Orchestration",
            "description": (
                "Escalate the current request into taskbook-based orchestration with preview and confirmation. "
                "Use this only for whole-task escalation, not for ordinary planning, single delegated side tasks, "
                "or one-off clarification questions."
            ),
            "usage_text": (
                "Usage: /request_orchestration "
                '\'{"source_text":"...","goal":"...","reason":"...","needs_confirmation":true}\''
            ),
            "provider_description": (
                "Escalate the current request into taskbook-based orchestration with preview and user confirmation. "
                "Use this only when the task is multi-phase or requires explicit card dependencies, owned-file boundaries, "
                "acceptance criteria, or review gates. "
                "This tool upgrades the whole task into orchestration; do not use it for lightweight planning "
                "(use update_plan), bounded side-task delegation (use spawn_agent), or local question collection "
                "(use request_user_input). "
                "After this tool is called, enter preview/confirm flow instead of running full execution immediately."
            ),
            "model_default_exposure": "internal_only",
        },
        {
            "name": "spawn_child_tab",
            "label": "Spawn Child Tab",
            "description": (
                "Fork or create one visible child tab, queue a bounded assignment, and return its tab/run handle. "
                "Use this for visible subagent work where the user should be able to watch or steer the child tab."
            ),
            "usage_text": (
                "Usage: /__spawn_child_tab "
                '\'{"task":"...","task_name":"optional label","metadata":{}}\''
            ),
            "provider_description": (
                "Fork or create one visible AgentHub child tab and queue the first assignment into that child. "
                "The child tab remains visible and manually steerable; its completion is reported through normalized TaskRun records. "
                "Use this for bounded visible subagent work, not for hidden background delegation. "
                "Do not use spawn_agent or native/local spawn_agent as the entry point for visible child tabs; "
                "those tools are hidden/native delegation surfaces. "
                "After spawning, use wait_child_tasks to consume structured status and summary instead of scraping the child transcript."
            ),
        },
        {
            "name": "send_child_tab",
            "label": "Send Child Tab",
            "description": "Queue one follow-up instruction into an existing visible child tab.",
            "usage_text": (
                "Usage: /__send_child_tab "
                '\'{"target":"tab-2","message":"...","interrupt":false}\''
            ),
            "provider_description": (
                "Queue one follow-up instruction into an existing visible child tab by tab id, visible tab label, or latest child selector. "
                "Use this only after spawn_child_tab has created a child. "
                "The follow-up creates a new child TaskRun or queued continuation; use wait_child_tasks to inspect normalized status."
            ),
        },
        {
            "name": "wait_child_tasks",
            "label": "Wait Child Tasks",
            "description": (
                "Return structured visible-child TaskRun snapshots and optionally wait briefly for terminal child results."
            ),
            "usage_text": (
                "Usage: /__wait_child_tasks "
                '\'{"targets":["tab-2"],"timeout_ms":250,"wait_for":"all","include_all":true}\''
            ),
            "provider_description": (
                "Return structured TaskRun snapshots for visible child tabs. "
                "For tab selectors, this inspects each selected tab's latest/current TaskRun rather than stale historical runs. "
                "Optionally wait up to timeout_ms for matching child tasks to reach a terminal state; use wait_for=all to join every selected child, or wait_for=any for progressive summarization when the first child returns. "
                "Use this as the master join/status surface; do not infer completion from child transcript text."
            ),
        },
        {
            "name": "send_input",
            "label": "Send Input",
            "description": "Queue one follow-up message for an existing delegated agent session.",
            "usage_text": f"Usage: {surface_usage_text_fn('send_input')}",
            "provider_description": (
                "Queue one follow-up message for an existing delegated agent session. "
                "Use interrupt=true to preempt the active turn and prioritize this message ahead of queued input. "
                "Use this only after a delegated agent already exists; it is not a replacement for normal main-thread reasoning."
            ),
        },
        {
            "name": "resume_agent",
            "label": "Resume Agent",
            "description": "Reopen a previously closed delegated agent session so it can accept follow-up input again.",
            "usage_text": "Usage: /resume_agent <agent_id>",
            "provider_description": (
                "Reopen a previously closed delegated agent session so it can accept follow-up input again. "
                "Use this only to continue an existing child workflow, not as a substitute for spawning a fresh task or doing main-thread reasoning."
            ),
        },
        {
            "name": "wait_agent",
            "label": "Wait Agent",
            "description": "Wait for a delegated agent session to reach a terminal state or timeout, then return its latest result.",
            "usage_text": f"Usage: {surface_usage_text_fn('wait_agent')}",
            "provider_description": (
                "Wait for a delegated agent session to reach a terminal state or timeout, then return its latest result. "
                "Use this only when the next step explicitly depends on that delegated result. "
                "When wait_required=false, only fetch the latest child status snapshot without blocking. "
                "Planner-side execution may service non-blocking snapshots via agent_workflow instead of a true wait join. "
                "Prefer agent_workflow when you only need non-blocking child status or recovery options. "
                "Do not busy-wait on background agents without a clear join plan."
            ),
        },
        {
            "name": "agent_workflow",
            "label": "Agent Workflow",
            "description": "Inspect delegated workflow state, recent steps, checkpoints, and available recovery actions without blocking execution.",
            "usage_text": f"Usage: {surface_usage_text_fn('agent_workflow')}",
            "provider_description": (
                "Inspect delegated workflow state, recent steps, checkpoints, and available recovery actions without blocking execution. "
                "Use this when you need a child status snapshot or recovery options before deciding whether to wait, recover, or close the delegated workflow."
            ),
        },
        {
            "name": "recover_agent",
            "label": "Recover Agent",
            "description": "Apply one recovery action to a delegated workflow, including retrying a failed step inside the same child session.",
            "usage_text": f"Usage: {surface_usage_text_fn('recover_agent')}",
            "provider_description": (
                "Apply one recovery action to a delegated workflow. "
                "Prefer action=retry_step when the workflow exposes a recoverable failed step and retrying the same child preserves context better than spawning a duplicate task."
            ),
        },
        {
            "name": "close_agent",
            "label": "Close Agent",
            "description": "Close one delegated agent session and reject future follow-up input until resumed.",
            "usage_text": "Usage: /close_agent <agent_id>",
            "provider_description": (
                "Close one delegated agent session and reject future follow-up input until resumed. "
                "Use this when a child is no longer useful, stale, or should stop consuming budget; do not use it as a normal planning step when the task still belongs in the main thread."
            ),
        },
        {
            "name": "update_plan",
            "label": "Update Plan",
            "description": (
                "Updates the task plan. Provide an optional explanation and a list of plan items, each with a "
                "step and status. At most one step can be in_progress at a time."
            ),
            "usage_text": 'Usage: /update_plan \'{"plan": [{"step": "...", "status": "pending"}]}\'',
            "provider_description": (
                "Updates the task plan. Provide an optional explanation and a list of plan items, each with a "
                "step and status. At most one step can be in_progress at a time."
            ),
        },
        {
            "name": "request_user_input",
            "label": "Request User Input",
            "description": (
                "Request user input for one to three short questions and wait for the response. "
                "Availability depends on collaboration mode. It is always available in Plan mode "
                "and may also be enabled in Default mode."
            ),
            "usage_text": "Usage: /request_user_input '{\"questions\": [...]}'",
            "provider_description": (
                "Request user input for one to three short questions and wait for the response. "
                "Availability depends on collaboration mode. It is always available in Plan mode "
                "and may also be enabled in Default mode."
            ),
        },
        {
            "name": "shell",
            "label": "Shell",
            "description": "Run a local shell command and capture stdout/stderr.",
            "usage_text": (
                "Usage: /shell <command>\n"
                "       /shell start <command>\n"
                "       /shell write <session_id> <chars>\n"
                "       /shell terminate <session_id>"
            ),
            "provider_description": (
                "Legacy compatibility alias for local shell execution. "
                "Prefer exec_command for session start or one-shot execution and write_stdin for interactive continuation."
            ),
            **command_execution_contract_metadata(
                tool_name="shell",
                tool_role="compatibility_alias",
                compatibility_alias_for="exec_command",
                model_default_exposure="compatibility_alias",
            ),
        },
        {
            "name": "apply_patch",
            "label": "Apply Patch",
            "description": "Apply a structured workspace patch using Reference-style patch grammar instead of shell redirection.",
            "usage_text": "Usage: /apply_patch <patch>",
            "provider_description": (
                "Apply a Reference-style structured patch to workspace files. "
                "Use this for file edits instead of shell redirection or ad-hoc echo commands."
            ),
            **apply_patch_contract_metadata(),
        },
    )
