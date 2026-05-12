from __future__ import annotations

FILE_TOOL_CANONICAL_TRIO: tuple[str, ...] = (
    "grep_files",
    "read_file",
    "list_dir",
)

FILE_TOOL_COMPAT_ALIASES: tuple[str, ...] = (
    "file_search",
    "file_read",
    "file_list",
)

COMMAND_EXECUTION_CANONICAL_FAMILY = "command_execution"

COMMAND_EXECUTION_PRIMARY_TOOLS: tuple[str, ...] = ("exec_command",)

COMMAND_EXECUTION_CONTINUATION_TOOLS: tuple[str, ...] = ("write_stdin",)

COMMAND_EXECUTION_TOOL_CANONICAL_APIS: tuple[str, ...] = (
    *COMMAND_EXECUTION_PRIMARY_TOOLS,
    *COMMAND_EXECUTION_CONTINUATION_TOOLS,
)

COMMAND_EXECUTION_TOOL_COMPAT_ALIASES: tuple[str, ...] = ("shell",)

COMMAND_EXECUTION_EVENT_PROJECTION_NAME = "commandExecution"

COMMAND_EXECUTION_EVENT_PROJECTION_SCOPES: tuple[str, ...] = (
    "tool_events",
    "turn_events",
    "transcript",
    "headless",
    "tui",
    "app_server",
)

EDITING_DOMAIN_NAME = "workspace_editing"

APPLY_PATCH_CANONICAL_FAMILY = "apply_patch"

EDITING_DOMAIN_CANONICAL_OPERATIONS: tuple[str, ...] = (
    "apply_patch",
    "file_write",
    "file_edit",
)

APPLY_PATCH_CODEX_PRIMARY_TOOLS: tuple[str, ...] = ("apply_patch",)

APPLY_PATCH_CLAUDE_PRIMARY_TOOLS: tuple[str, ...] = ("Write", "Edit")

APPLY_PATCH_PROJECTION_VARIANTS: tuple[str, ...] = ("freeform", "function")

EXPERT_REVIEW_CANONICAL_FAMILY = "expert_review"

EXPERT_REVIEW_RUNTIME_BINDING = "delegated_read_only_reviewer"

SHELL_TOOL_CANONICAL_APIS: tuple[str, ...] = COMMAND_EXECUTION_TOOL_CANONICAL_APIS

SHELL_TOOL_COMPAT_ALIASES: tuple[str, ...] = COMMAND_EXECUTION_TOOL_COMPAT_ALIASES

BROWSER_TOOL_CANONICAL_PRIMARY: tuple[str, ...] = ("browser",)

BROWSER_TOOL_COMPAT_ALIASES: tuple[str, ...] = (
    "open",
    "click",
    "find",
)

MODEL_HIDDEN_BUILTIN_COMPAT_ALIASES: tuple[str, ...] = (
    *FILE_TOOL_COMPAT_ALIASES,
    *SHELL_TOOL_COMPAT_ALIASES,
    *BROWSER_TOOL_COMPAT_ALIASES,
)

BUILTIN_TOOL_ORDER: tuple[str, ...] = (
    "exec_command",
    "write_stdin",
    "spawn_agent",
    "request_orchestration",
    "spawn_child_tab",
    "send_child_tab",
    "wait_child_tasks",
    "send_input",
    "resume_agent",
    "wait_agent",
    "agent_workflow",
    "recover_agent",
    "close_agent",
    "update_plan",
    "request_user_input",
    "shell",
    "apply_patch",
    "grep_files",
    "read_file",
    "list_dir",
    "file_search",
    "file_read",
    "file_list",
    "office_skills",
    "office_run",
    "web_search",
    "view_image",
    "expert_review",
    "web_fetch",
    "browser",
    "open",
    "click",
    "find",
    "policy_doc_import",
    "policy_doc_list",
    "policy_doc_search",
    "policy_doc_read",
)

MODEL_FACING_BUILTIN_TOOL_ORDER: tuple[str, ...] = tuple(
    name for name in BUILTIN_TOOL_ORDER if name not in set(MODEL_HIDDEN_BUILTIN_COMPAT_ALIASES)
)

RESPONSES_MINIMAL_TOOL_ORDER: tuple[str, ...] = (
    "exec_command",
    "write_stdin",
    "spawn_agent",
    "request_orchestration",
    "spawn_child_tab",
    "send_child_tab",
    "wait_child_tasks",
    "send_input",
    "resume_agent",
    "wait_agent",
    "agent_workflow",
    "recover_agent",
    "close_agent",
    "update_plan",
    "request_user_input",
    "apply_patch",
    "web_search",
    "view_image",
    "expert_review",
)

BROWSER_RUNTIME_ACTIONS: tuple[str, ...] = (
    "status",
    "start",
    "stop",
    "profiles",
    "tabs",
    "open",
    "focus",
    "close",
    "navigate",
    "snapshot",
    "screenshot",
    "pdf",
    "download",
    "wait_download",
    "console",
    "errors",
    "requests",
    "highlight",
    "trace_start",
    "trace_stop",
    "cookies",
    "storage",
    "storage_state",
    "act",
    "evaluate",
    "upload",
    "dialog",
    "open_legacy",
    "click_legacy",
    "find_legacy",
)

BROWSER_PROVIDER_ACTIONS: tuple[str, ...] = (
    "status",
    "start",
    "stop",
    "profiles",
    "tabs",
    "open",
    "focus",
    "close",
    "navigate",
    "snapshot",
    "screenshot",
    "pdf",
    "download",
    "wait_download",
    "console",
    "errors",
    "requests",
    "highlight",
    "trace_start",
    "trace_stop",
    "cookies",
    "cookies_get",
    "cookies_set",
    "cookies_clear",
    "storage_state",
    "storage_get",
    "storage_set",
    "storage_clear",
    "act",
    "upload",
    "dialog",
)
