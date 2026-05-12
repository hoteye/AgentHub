from __future__ import annotations

from dataclasses import dataclass

from cli.agent_cli.slash_surface import surface_usage_text
from cli.agent_cli.ui.theme import builtin_theme_ids

THEME_COMMAND_USAGE = f"/theme <{'|'.join(builtin_theme_ids())}>"


@dataclass(frozen=True)
class SlashCommandSpec:
    name: str
    usage: str
    description: str
    hidden: bool = False
    description_key: str = ""


SLASH_COMMAND_SPECS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec("help", "/help", "show available slash commands"),
    SlashCommandSpec("chat", "/chat", "switch to the DeepSeek chat-tools line"),
    SlashCommandSpec("reasoner", "/reasoner", "switch to the DeepSeek reasoner line"),
    SlashCommandSpec(
        "providers", surface_usage_text("providers"), "list configured model providers"
    ),
    SlashCommandSpec("models", "/models [provider]", "list configured models"),
    SlashCommandSpec(
        "connect",
        surface_usage_text("connect"),
        "onboard one provider configuration with typed auth settings",
    ),
    SlashCommandSpec(
        "setup",
        surface_usage_text("setup"),
        "run the simple API key provider setup flow",
    ),
    SlashCommandSpec(
        "update",
        surface_usage_text("update"),
        "check for AgentHub CLI updates and manage cached update notices",
    ),
    SlashCommandSpec(
        "auth",
        surface_usage_text("auth"),
        "run provider auth lifecycle actions and inspect current auth session state",
    ),
    SlashCommandSpec(
        "provider", surface_usage_text("provider"), "show current provider or switch provider"
    ),
    SlashCommandSpec("model", surface_usage_text("model"), "show current model or switch model"),
    SlashCommandSpec(
        "codex_threads",
        surface_usage_text("codex_threads"),
        "list Codex sidecar app-server threads",
    ),
    SlashCommandSpec(
        "codex_thread",
        surface_usage_text("codex_thread"),
        "show one Codex sidecar thread summary",
    ),
    SlashCommandSpec(
        "codex_rollback",
        surface_usage_text("codex_rollback"),
        "rollback the active Codex sidecar thread by completed turns",
    ),
    SlashCommandSpec(
        "codex_compact",
        surface_usage_text("codex_compact"),
        "request Codex sidecar context compaction for the active thread",
    ),
    SlashCommandSpec("cd", "/cd [path]", "change working directory, or show current directory"),
    SlashCommandSpec("status", "/status", "show current session configuration and runtime status"),
    SlashCommandSpec(
        "threads",
        surface_usage_text("threads"),
        "list persisted threads and their current load status",
    ),
    SlashCommandSpec("resume", "/resume <thread_id>", "resume a persisted thread by thread id"),
    SlashCommandSpec("resume_last", "/resume_last", "resume the last active persisted thread"),
    SlashCommandSpec(
        "resume_path", "/resume_path <rollout_path>", "resume a persisted thread by rollout path"
    ),
    SlashCommandSpec(
        "exit", "/exit", "exit the interactive session and print the current session id"
    ),
    SlashCommandSpec("quit", "/quit", "alias of /exit"),
    SlashCommandSpec("close", "/close", "close the current tab"),
    SlashCommandSpec(
        "preview",
        "/preview [open|close|toggle|status]",
        "open, close, toggle, or show the fixed split preview pane",
    ),
    SlashCommandSpec("runtime_status", "/runtime_status", "show runtime policy status"),
    SlashCommandSpec(
        "compact", "/compact [instructions]", "summarize conversation history and free context"
    ),
    SlashCommandSpec(
        "mcp",
        "/mcp [list|inspect|reconnect|enable|disable|auth] ...",
        "inspect and manage configured MCP servers",
    ),
    SlashCommandSpec(
        "mcp_inspect", "/mcp_inspect <server>", "inspect one MCP server status and scope"
    ),
    SlashCommandSpec(
        "mcp_reconnect", "/mcp_reconnect <server|all>", "reconnect one MCP server or all servers"
    ),
    SlashCommandSpec(
        "mcp_enable", "/mcp_enable <server|all>", "enable one MCP server or all servers"
    ),
    SlashCommandSpec(
        "mcp_disable", "/mcp_disable <server|all>", "disable one MCP server or all servers"
    ),
    SlashCommandSpec(
        "mcp_auth",
        surface_usage_text("mcp_auth"),
        "set MCP auth token or headers then reconnect the server",
    ),
    SlashCommandSpec(
        "mcp_auth_callback",
        surface_usage_text("mcp_auth_callback"),
        "apply one MCP auth callback payload then reconnect the server",
    ),
    SlashCommandSpec(
        "mcp_auth_clear",
        surface_usage_text("mcp_auth_clear"),
        "clear MCP auth override for one server and reconnect",
    ),
    SlashCommandSpec(
        "init",
        surface_usage_text("init"),
        "create an `AENGTHUB.md` file with instructions for AgentHub",
    ),
    SlashCommandSpec(
        "orchestrate",
        "/orchestrate <task text or taskbook markdown>",
        "create one orchestrated taskbook run from task text or markdown",
    ),
    SlashCommandSpec(
        "orchestrate_confirm",
        "/orchestrate_confirm <task text or taskbook markdown>",
        "preview a taskbook, ask for confirmation or planning adjustments, and only then create the orchestration run",
    ),
    SlashCommandSpec(
        "orchestrate_dispatch",
        "/orchestrate_dispatch <run_id>",
        "select ready cards for one orchestration run and dispatch them to delegated/background execution",
    ),
    SlashCommandSpec(
        "orchestrate_progress",
        "/orchestrate_progress <run_id>",
        "sync one orchestration run, ingest terminal card results, apply minimal acceptance, and dispatch newly-ready cards",
    ),
    SlashCommandSpec(
        "orchestrate_continue",
        surface_usage_text("orchestrate_continue"),
        "run multiple orchestration progress passes in one runtime until the run stabilizes or reaches a terminal state",
    ),
    SlashCommandSpec(
        "orchestrate_apply",
        "/orchestrate_apply <run_id> <card_id>",
        "apply one staged background teammate result for an orchestration card, then immediately re-sync the run",
    ),
    SlashCommandSpec(
        "orchestrate_reject",
        "/orchestrate_reject <run_id> <card_id>",
        "reject one staged background teammate result for an orchestration card, then immediately re-sync the run",
    ),
    SlashCommandSpec(
        "workflows",
        surface_usage_text("workflows"),
        "list delegated agent workflows plus recent non-mirrored background tasks",
    ),
    SlashCommandSpec(
        "background_tasks",
        surface_usage_text("background_tasks"),
        "list recent background tasks and current queue status",
    ),
    SlashCommandSpec(
        "background_worker_status",
        "/background_worker_status",
        "show background worker health, heartbeat, and runtime state",
    ),
    SlashCommandSpec(
        "background_worker_start",
        surface_usage_text("background_worker_start"),
        "start one detached background worker process",
    ),
    SlashCommandSpec(
        "background_worker_stop",
        surface_usage_text("background_worker_stop"),
        "stop the detached background worker process recorded in worker state",
    ),
    SlashCommandSpec(
        "background_worker_run_once",
        surface_usage_text("background_worker_run_once"),
        "run one local worker maintenance and queue-consumption pass",
    ),
    SlashCommandSpec(
        "background_benchmark",
        surface_usage_text("background_benchmark"),
        "submit one benchmark_headless_models run to the background task layer",
    ),
    SlashCommandSpec(
        "background_smoke",
        surface_usage_text("background_smoke"),
        "submit one live smoke script run to the background task layer",
    ),
    SlashCommandSpec(
        "background_teammate",
        surface_usage_text("background_teammate"),
        "run one real headless teammate turn in the background task layer",
    ),
    SlashCommandSpec(
        "background_task_status",
        "/background_task_status <task_id>",
        "show one background task status, dispatch state, and artifact pointers",
    ),
    SlashCommandSpec(
        "background_task_cancel",
        "/background_task_cancel <task_id>",
        "request cancellation for one background task",
    ),
    SlashCommandSpec(
        "background_task_retry",
        "/background_task_retry <task_id>",
        "retry one failed or cancelled background task",
    ),
    SlashCommandSpec(
        "background_task_apply",
        "/background_task_apply <task_id>",
        "apply one reviewed staged background teammate diff to the live workspace",
    ),
    SlashCommandSpec(
        "background_task_reject",
        "/background_task_reject <task_id>",
        "reject one staged background teammate diff without applying it to the live workspace",
    ),
    SlashCommandSpec(
        "runtime_config",
        surface_usage_text("runtime_config"),
        "update runtime policy settings for the current session",
    ),
    SlashCommandSpec(
        "lang",
        "/lang <en|zh-CN|ja|fr|auto>",
        "switch the interactive TUI language for the current session",
    ),
    SlashCommandSpec(
        "theme", THEME_COMMAND_USAGE, "switch the interactive TUI theme for the current session"
    ),
    SlashCommandSpec("tools", "/tools", "list local toolchain capabilities"),
    SlashCommandSpec("plugins", "/plugins", "list discovered plugins and enabled state"),
    SlashCommandSpec("plugin_enable", "/plugin_enable <name>", "enable a plugin"),
    SlashCommandSpec(
        "plugin_disable",
        surface_usage_text("plugin_disable"),
        "disable a plugin or disable all plugins",
    ),
    SlashCommandSpec(
        "plugin_reload", "/plugin_reload", "reload all plugin manifests and registrations"
    ),
    SlashCommandSpec(
        "plugin_install",
        surface_usage_text("plugin_install"),
        "install a plugin from a directory or zip archive",
    ),
    SlashCommandSpec("plugin_remove", "/plugin_remove <name>", "remove an installed plugin"),
    SlashCommandSpec(
        "plugin_marketplace",
        surface_usage_text("plugin_marketplace"),
        "manage plugin marketplace sources and lifecycle actions",
    ),
    SlashCommandSpec(
        "memory",
        surface_usage_text("memory"),
        "inspect and manage project memory records",
    ),
    SlashCommandSpec("plan", "/plan", "switch to Plan mode"),
    SlashCommandSpec(
        "tab_rename",
        "/tab_rename [label]",
        "rename the active TUI tab label, or clear the custom label when empty",
    ),
    SlashCommandSpec(
        "tab_new",
        "/tab_new [python|codex|openai]",
        "create a new TUI tab, optionally backed by the Codex sidecar runtime",
    ),
    SlashCommandSpec(
        "approval_inbox",
        "/approval_inbox [go <tab_id>]",
        "show pending approvals across TUI tabs, or switch to a tab for review",
    ),
    SlashCommandSpec("fork", "/fork", "fork the current tab into a new independent tab"),
    SlashCommandSpec("master", "/master", "mark the current tab as a visible master tab"),
    SlashCommandSpec(
        "fork_child",
        "/fork_child",
        "fork the current master tab into a visible child tab",
    ),
    SlashCommandSpec("llm", "/llm <prompt>", "force a direct LLM planning turn"),
    SlashCommandSpec(
        "spawn_agent",
        '/spawn_agent \'{"task":"...","role":"subagent|teammate","model":"inherit|selector","provider":"name","reasoning_effort":"level","timeout":30,"async":true,"reason":"research_side_task","mode":"background","wait_required":false,"task_shape":"read_only"}\'',
        "run a delegated subagent/teammate task synchronously, or start it in background when async=true",
    ),
    SlashCommandSpec(
        "send_input",
        surface_usage_text("send_input"),
        "queue one follow-up message for a delegated agent session",
    ),
    SlashCommandSpec(
        "resume_agent",
        "/resume_agent <agent_id>",
        "reopen a previously closed delegated agent session",
    ),
    SlashCommandSpec(
        "wait_agent",
        surface_usage_text("wait_agent"),
        "wait for one delegated agent session to finish, or return an immediate status snapshot when wait-required false",
    ),
    SlashCommandSpec(
        "close_agent",
        "/close_agent <agent_id>",
        "close one delegated agent session and reject future inputs",
    ),
    SlashCommandSpec(
        "expert_review",
        '/expert_review \'{"task":"..."}\'',
        "request a read-only expert review from a secondary eligible provider",
    ),
    SlashCommandSpec(
        "agent_workflow",
        surface_usage_text("agent_workflow"),
        "inspect delegated workflow state, recent steps, checkpoints, and recovery actions",
    ),
    SlashCommandSpec(
        "recover_agent",
        surface_usage_text("recover_agent"),
        "apply one recovery action to a delegated workflow, including step retry",
    ),
    SlashCommandSpec(
        "shell",
        "/shell <command> | /shell start <command> | /shell write <session_id> <chars> | /shell terminate <session_id>",
        "compatibility alias for canonical exec_command/write_stdin local shell workflows",
    ),
    SlashCommandSpec(
        "apply_patch",
        "/apply_patch <patch>",
        "apply a Reference-style structured patch to workspace files",
    ),
    SlashCommandSpec(
        "approvals",
        surface_usage_text("approvals"),
        "list approval tickets, including pending patch approvals",
    ),
    SlashCommandSpec(
        "approve", surface_usage_text("approve"), "approve a pending action or patch approval"
    ),
    SlashCommandSpec(
        "reject", surface_usage_text("reject"), "reject a pending action or patch approval"
    ),
    SlashCommandSpec(
        "glob_files",
        surface_usage_text("glob_files"),
        "structured file globbing by pattern (Claude Glob parity)",
    ),
    SlashCommandSpec(
        "grep_files",
        surface_usage_text("grep_files"),
        "canonical local code discovery (Reference-aligned)",
    ),
    SlashCommandSpec(
        "read_file",
        surface_usage_text("read_file"),
        "canonical local file slice reading (Reference-aligned)",
    ),
    SlashCommandSpec(
        "list_dir",
        surface_usage_text("list_dir"),
        "canonical local directory discovery with pagination/depth (Reference-aligned)",
    ),
    SlashCommandSpec(
        "file_list",
        surface_usage_text("file_list"),
        "compatibility alias of canonical list_dir for local workspace listing",
    ),
    SlashCommandSpec(
        "file_search",
        surface_usage_text("file_search"),
        "compatibility alias of canonical grep_files for local code discovery",
    ),
    SlashCommandSpec(
        "file_read",
        surface_usage_text("file_read"),
        "compatibility alias of canonical read_file for local file slices",
    ),
    SlashCommandSpec("office_skills", "/office_skills", "list Office and PDF skills"),
    SlashCommandSpec("office_run", surface_usage_text("office_run"), "run an Office or PDF skill"),
    SlashCommandSpec(
        "web_search",
        surface_usage_text("web_search"),
        "search the public web and return structured results",
    ),
    SlashCommandSpec(
        "view_image",
        "/view_image <path>",
        "inspect a local image file by path",
    ),
    SlashCommandSpec(
        "web_fetch",
        surface_usage_text("web_fetch"),
        "fetch one webpage and extract readable text",
    ),
    SlashCommandSpec(
        "browser",
        surface_usage_text("browser"),
        "control the managed browser session, including debug/state actions and explicit cookies/storage mutation flows",
    ),
    SlashCommandSpec(
        "open",
        surface_usage_text("open"),
        "compatibility alias for canonical browser page open/inspect flow",
    ),
    SlashCommandSpec(
        "click",
        "/click <ref-id> <id>",
        "compatibility alias for canonical browser navigation flow",
    ),
    SlashCommandSpec(
        "find",
        "/find <ref-id> <pattern>",
        "compatibility alias for canonical browser page inspection flow",
    ),
)


DISCOVERABLE_SLASH_COMMAND_NAMES: frozenset[str] = frozenset(
    {
        "help",
        "providers",
        "models",
        "setup",
        "provider",
        "model",
        "codex_threads",
        "codex_thread",
        "codex_rollback",
        "codex_compact",
        "status",
        "threads",
        "resume",
        "exit",
        "quit",
        "compact",
        "mcp",
        "init",
        "orchestrate",
        "orchestrate_confirm",
        "orchestrate_dispatch",
        "orchestrate_progress",
        "orchestrate_continue",
        "orchestrate_apply",
        "orchestrate_reject",
        "workflows",
        "background_tasks",
        "runtime_config",
        "lang",
        "theme",
        "tools",
        "plugins",
        "memory",
        "plan",
        "tab_rename",
        "tab_new",
        "approval_inbox",
        "preview",
        "fork",
        "master",
        "fork_child",
        "close",
    }
)


BUSY_MODE_BY_COMMAND: dict[str, str] = {
    "help": "allowed",
    "providers": "allowed",
    "models": "allowed",
    "provider": "read_only",
    "codex_threads": "allowed",
    "codex_thread": "allowed",
    "status": "allowed",
    "setup": "allowed",
    "update": "allowed",
    "runtime_status": "allowed",
    "tools": "allowed",
    "plugins": "allowed",
    "tab_rename": "allowed",
    "tab_new": "allowed",
    "approval_inbox": "allowed",
    "preview": "allowed",
    "fork": "allowed",
    "master": "allowed",
    "fork_child": "allowed",
    "close": "allowed",
}
