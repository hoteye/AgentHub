from __future__ import annotations

from typing import Any, Callable, Dict

from . import anthropic_edit_tool_specs

_EXPERT_REVIEW_SCOPE_VALUES = ("latest_turn", "current_task", "selected_artifacts")
_EXPERT_REVIEW_FOCUS_VALUES = (
    "correctness",
    "risk",
    "regression",
    "evidence",
    "completeness",
    "policy",
    "code_quality",
)
_EXPERT_REVIEW_STRICTNESS_VALUES = ("low", "medium", "high")


def _shell_command_tool_properties(command_description: str) -> Dict[str, Dict[str, Any]]:
    return {
        "command": {"type": "string", "description": command_description},
        "timeout": {
            "type": "integer",
            "description": (
                "Optional initial wait budget in milliseconds before this unified exec call yields. "
                "This is a yield budget compatibility alias, not a hard process execution timeout. "
                "The underlying command may continue running after the tool returns."
            ),
        },
        "description": {
            "type": "string",
            "description": (
                "Optional concise active-voice description of what this command does. "
                "When escalated execution is requested, this is reused as the approval justification."
            ),
        },
        "run_in_background": {
            "type": "boolean",
            "description": (
                "Set to true to return quickly from the initial unified exec call while the session keeps running. "
                "Use write_stdin later to poll or continue that session."
            ),
        },
        "dangerouslyDisableSandbox": {
            "type": "boolean",
            "description": (
                "Set to true to request running without sandbox restrictions when policy allows it."
            ),
        },
    }


def exec_command_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="exec_command",
        description=provider_description("exec_command"),
        properties={
            "cmd": {"type": "string", "description": "Shell command to execute."},
            "workdir": {
                "type": "string",
                "description": (
                    "Optional working directory to run the command in; defaults to the turn cwd. "
                    "Prefer setting this instead of prepending `cd` to the command."
                ),
            },
            "shell": {
                "type": "string",
                "description": "Shell binary to launch. Defaults to the user's default shell.",
            },
            "tty": {
                "type": "boolean",
                "description": (
                    "Whether to allocate a TTY for the command. Defaults to false (plain pipes); "
                    "set to true to open a PTY and access TTY process."
                ),
            },
            "login": {
                "type": "boolean",
                "description": "Whether to run the shell with -l/-i semantics. Defaults to true.",
            },
            "yield_time_ms": {
                "type": "integer",
                "description": "How long to wait (in milliseconds) for output before yielding.",
            },
            "max_output_tokens": {
                "type": "integer",
                "description": "Maximum number of tokens to return. Excess output will be truncated.",
            },
            "sandbox_permissions": {
                "type": "string",
                "description": (
                    "Sandbox permissions for the command. Set to \"require_escalated\" to request "
                    "running without sandbox restrictions; defaults to \"use_default\"."
                ),
            },
            "justification": {
                "type": "string",
                "description": (
                    "Only set if sandbox_permissions is \"require_escalated\". Request approval from the "
                    "user to run this command outside the sandbox."
                ),
            },
            "prefix_rule": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Only specify when sandbox_permissions is require_escalated. "
                    "Suggest a reusable prefix command pattern."
                ),
            },
        },
        required=["cmd"],
    )


def write_stdin_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="write_stdin",
        description=provider_description("write_stdin"),
        properties={
            "session_id": {
                "type": "string",
                "description": "Identifier of the running unified exec session.",
            },
            "chars": {
                "type": "string",
                "description": "Bytes to write to stdin (may be empty to poll).",
            },
            "yield_time_ms": {
                "type": "integer",
                "description": "How long to wait (in milliseconds) for output before yielding.",
            },
            "max_output_tokens": {
                "type": "integer",
                "description": "Maximum number of tokens to return. Excess output will be truncated.",
            },
        },
        required=["session_id"],
    )


def bash_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    del provider_description
    return function_tool(
        name="Bash",
        description="Run shell command.",
        properties=_shell_command_tool_properties("The shell command to execute."),
        required=["command"],
    )


def powershell_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    del provider_description
    return function_tool(
        name="PowerShell",
        description="Run PowerShell command.",
        properties=_shell_command_tool_properties("The PowerShell command to execute."),
        required=["command"],
    )


def update_plan_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="update_plan",
        description=provider_description("update_plan"),
        properties={
            "explanation": {"type": "string"},
            "plan": {
                "type": "array",
                "description": "The list of steps",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {"type": "string"},
                        "status": {
                            "type": "string",
                            "description": "One of: pending, in_progress, completed",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["step", "status"],
                    "additionalProperties": False,
                },
            },
        },
        required=["plan"],
    )


def request_user_input_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _interactive_question_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="request_user_input",
    )


def ask_user_question_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return _interactive_question_spec(
        function_tool=function_tool,
        provider_description=provider_description,
        name="AskUserQuestion",
    )


def _interactive_question_spec(
    *,
    function_tool: Callable[..., Dict[str, Any]],
    provider_description: Callable[[str], str],
    name: str,
) -> Dict[str, Any]:
    description = str(provider_description("request_user_input") or "").strip()
    if name == "AskUserQuestion":
        if description:
            description = (
                f"{description} Use this tool for clarification questions or concrete user choices, "
                "not for plan approval."
            )
        else:
            description = (
                "Ask the user one to three short clarification or choice questions and wait for the response. "
                "Do not use this tool for plan approval."
            )
    return function_tool(
        name=name,
        description=description,
        properties={
            "questions": {
                "type": "array",
                "description": "Questions to show the user. Prefer 1 and do not exceed 3",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Stable identifier for mapping answers (snake_case).",
                        },
                        "header": {
                            "type": "string",
                            "description": "Short header label shown in the UI (12 or fewer chars).",
                        },
                        "question": {
                            "type": "string",
                            "description": "Single-sentence prompt shown to the user.",
                        },
                        "options": {
                            "type": "array",
                            "description": (
                                "Provide 2-3 mutually exclusive choices. Put the recommended option first "
                                "and suffix its label with \"(Recommended)\". Do not include an \"Other\" "
                                "option in this list; the client will add a free-form \"Other\" option automatically."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {
                                        "type": "string",
                                        "description": "User-facing label (1-5 words).",
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": "One short sentence explaining impact/tradeoff if selected.",
                                    },
                                },
                                "required": ["label", "description"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["id", "header", "question", "options"],
                    "additionalProperties": False,
                },
            },
        },
        required=["questions"],
    )


def apply_patch_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return anthropic_edit_tool_specs.structured_apply_patch_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def write_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return anthropic_edit_tool_specs.structured_write_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def edit_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return anthropic_edit_tool_specs.structured_edit_spec(
        function_tool=function_tool,
        provider_description=provider_description,
    )


def grep_files_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="grep_files",
        description=provider_description("grep_files"),
        properties={
            "pattern": {"type": "string"},
            "include": {"type": "string"},
            "path": {"type": "string"},
            "limit": {"type": "integer"},
        },
        required=["pattern"],
    )


def office_run_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="office_run",
        description=provider_description("office_run"),
        properties={
            "skill": {"type": "string"},
            "path": {"type": "string"},
        },
        required=["skill"],
    )


def view_image_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="view_image",
        description=provider_description("view_image"),
        properties={
            "path": {
                "type": "string",
                "description": "Local filesystem path to an image file to prepare as a continuation-ready artifact.",
            }
        },
        required=["path"],
    )


def expert_review_spec(*, function_tool: Callable[..., Dict[str, Any]], provider_description: Callable[[str], str]) -> Dict[str, Any]:
    return function_tool(
        name="expert_review",
        description=provider_description("expert_review"),
        properties={
            "task": {
                "type": "string",
                "description": "What the reviewer should check.",
            },
        },
        required=["task"],
    )
