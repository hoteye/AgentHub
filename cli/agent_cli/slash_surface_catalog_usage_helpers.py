from __future__ import annotations

SURFACE_USAGE_DATA: dict[str, str] = {
    "exec_command": (
        "/exec_command <cmd> [workdir <dir>] [shell <path>] [tty] "
        "[login <true|false>] [yield-time-ms <n>] [timeout-ms <n>] [max-output-tokens <n>] "
        "[sandbox-permissions <mode>] [justification <text>] [prefix-rule <a,b>] "
        "[additional-permissions-json <json>]"
    ),
    "write_stdin": "/write_stdin <session_id> [chars] [yield-time-ms <n>] [max-output-tokens <n>]",
    "providers": "/providers [probe]",
    "connect": (
        "/connect provider <name> model <selector> [base-url <url>] "
        "[auth-mode <api_key|oauth|wellknown|none>] [api-key-env <ENV>] [user|project] [check]"
    ),
    "setup": (
        "/setup [status] [provider <name>] [api-key <secret>] "
        "[base-url <url>] [model <selector>] [user|project] [check]"
    ),
    "update": "/update [status|check|refresh|dismiss] [refresh]",
    "auth": (
        "/auth <status|login|refresh|logout> [provider <name>] [mode <device_code|browser_pkce>] "
        "[poll] [auth-code <code>] [state <state>] [token-ref <name>] [wait-callback|listen] "
        "[callback-timeout-seconds <n>] [auto] [daemon <start|status|stop>] "
        "[interval-seconds <n>] [refresh-window-seconds <n>] [managed]"
    ),
    "provider": "/provider [name]",
    "model": "/model [name]",
    "codex_threads": "/codex_threads [limit <n>] [archived]",
    "codex_thread": "/codex_thread [thread_id]",
    "codex_rollback": "/codex_rollback [turns <n>]",
    "codex_compact": "/codex_compact",
    "threads": "/threads [limit <n>]",
    "mcp_auth": "/mcp_auth <server> <token> [headers-json <json>]",
    "mcp_auth_callback": "/mcp_auth_callback <server> [token <token>] [callback-json <json>]",
    "mcp_auth_clear": "/mcp_auth_clear <server>",
    "mcp_resource": "/mcp_resource <list|read> ...",
    "mcp_resource_read": "/mcp_resource read server <server> uri <uri>",
    "mcp_tool_call": "/mcp_tool_call projected-name <name> [arguments-json <json>]",
    "mcp_channel": "/mcp channel [list] [server <server>]",
    "mcp_permission": "/mcp permission <list|respond> ...",
    "mcp_permission_respond": (
        "/mcp permission respond server <server> request-id <id> "
        "approved <true|false> [reason <text>]"
    ),
    "init": "/init [yes]",
    "orchestrate_continue": "/orchestrate_continue <run_id> [max-passes <n>] [dispatch-ready <true|false>]",
    "workflows": "/workflows [limit <n>]",
    "background_tasks": "/background_tasks [limit <n>]",
    "background_worker_start": "/background_worker_start [max-jobs <n>] [poll-interval <n>] [stale-after-seconds <n>]",
    "background_worker_stop": "/background_worker_stop [force]",
    "background_worker_run_once": "/background_worker_run_once [max-jobs <n>] [stale-after-seconds <n>]",
    "background_benchmark": "/background_benchmark [timeout-seconds <n>] [benchmark_headless_models.py args...]",
    "background_smoke": "/background_smoke [multi_llm|policy_helper] [timeout-seconds <n>] [script args...]",
    "background_teammate": (
        "/background_teammate <task> [provider <name>] [model <name>] [reasoning-effort <level>] "
        "[cwd <path>] [approval-policy <mode>] [sandbox-mode <mode>] [allowed-paths <a,b>] "
        "[blocked-paths <c,d>] [timeout-seconds <n>]"
    ),
    "memory": "/memory <list|show|preview|save|delete|debug> [args]",
    "model-route": (
        "/model-route [route] [model] [provider <name>] [reasoning-effort <low|medium|high|xhigh>] "
        "[timeout <seconds>] [clear]"
    ),
    "model_route": (
        "/model_route [route] [model] [provider <name>] [reasoning-effort <low|medium|high|xhigh>] "
        "[timeout <seconds>] [clear]"
    ),
    "delegate-model": (
        "/delegate-model [subagent|teammate] [model|inherit] [provider <name>] "
        "[reasoning-effort <low|medium|high|xhigh>] [timeout <seconds>] [clear]"
    ),
    "delegate_model": (
        "/delegate_model [subagent|teammate] [model|inherit] [provider <name>] "
        "[reasoning-effort <low|medium|high|xhigh>] [timeout <seconds>] [clear]"
    ),
    "runtime_config": (
        "/runtime_config [permission-mode <mode>] [approval-policy <mode>] [sandbox-mode <mode>] "
        "[web-search-mode <mode>] [network-access <enabled|disabled>]"
    ),
    "plugin_disable": "/plugin_disable <name|all>",
    "plugin_install": "/plugin_install <zip-or-dir> [replace] [scope <user|project|local|managed>]",
    "plugin_marketplace": "/plugin_marketplace [list|add|update|remove|install|uninstall|enable|disable|plugins] ...",
    "plugin_marketplace_add": "/plugin_marketplace add <plugin[@marketplace]> <zip-or-dir> [scope <project|user>]",
    "plugin_marketplace_update": "/plugin_marketplace update <plugin[@marketplace]> [path <zip-or-dir>] [scope <project|user>]",
    "plugin_marketplace_remove": "/plugin_marketplace remove <plugin[@marketplace]>",
    "plugin_marketplace_install": "/plugin_marketplace install <plugin[@marketplace]> [replace]",
    "plugin_marketplace_uninstall": "/plugin_marketplace uninstall <plugin|plugin@marketplace>",
    "plugin_marketplace_enable": "/plugin_marketplace enable <plugin|plugin@marketplace>",
    "plugin_marketplace_disable": "/plugin_marketplace disable <plugin|plugin@marketplace>",
    "send_input": "/send_input <agent_id> <message> [interrupt]",
    "wait_agent": "/wait_agent <agent_id> [timeout-ms <n>] [reason <wait_for_child_result>] [wait-required <true|false>]",
    "agent_workflow": "/agent_workflow <agent_id> [steps <n>] [checkpoints <n>]",
    "recover_agent": "/recover_agent <agent_id> [action <retry_step|resume_session|close_session>] [step-id <id>]",
    "approvals": "/approvals [status <status>] [limit <n>]",
    "approve": "/approve <approval_id> [mode session|rule] [note <text>] [no-resume] [resume-only]",
    "reject": "/reject <approval_id> [mode cancel] [note <text>] [no-resume] [resume-only]",
    "glob_files": "/glob_files <pattern> [path <dir>] [limit <n>]",
    "grep_files": "/grep_files <pattern> [include <glob>] [path <dir>] [limit <n>]",
    "read_file": "/read_file <file_path> [offset <line>] [limit <n>]",
    "list_dir": "/list_dir [dir_path] [offset <n>] [limit <n>] [depth <n>]",
    "file_list": "/file_list [path] [limit <n>]",
    "file_search": "/file_search <query> [path <dir>] [limit <n>]",
    "file_read": "/file_read <path> [offset <line>] [limit <n>]",
    "office_run": "/office_run <skill> <file>",
    "web_search": "/web_search <query> [limit <n>] [domains <a.com,b.com>] [recency-days <n>] [market <cc>]",
    "web_fetch": "/web_fetch <url> [max-chars <n>]",
    "browser": (
        "/browser <action> [status|start|stop|open|navigate|snapshot|screenshot|pdf|console|errors|requests|"
        "highlight|trace_start|trace_stop|cookies|storage|storage_state|act|upload|dialog] "
        "[profile <name>] [transport <local|proxy>] [tab <id>] [url <addr>] [path <rel>] [ref <id>] "
        "[kind <verb>] [paths <a,b>] [time-ms <n>] [method <verb>] [outcome <kind>]"
    ),
    "open": "/open <url-or-ref-id> [line <n>]",
    "github_issue_create": "/github_issue_create repo <owner/repo> title <text> [body <text>]",
    "github_issue_comment": "/github_issue_comment repo <owner/repo> issue-number <n> body <text>",
    "github_issue_add_labels": "/github_issue_add_labels repo <owner/repo> issue-number <n> labels <a,b>",
    "github_issue_close": "/github_issue_close repo <owner/repo> issue-number <n>",
    "github_workflow_dispatch": (
        "/github_workflow_dispatch repo <owner/repo> workflow-id <id> ref <ref> [inputs-json <json>]"
    ),
    "github_approval_list": "/github_approval_list [status <pending|approved|rejected>]",
    "github_approval_approve": (
        "/github_approval_approve approval-id <id> [decided-by <name>] [decision-note <text>]"
    ),
    "github_approval_reject": (
        "/github_approval_reject approval-id <id> [decided-by <name>] [decision-note <text>]"
    ),
    "list_mcp_resources": "/list_mcp_resources [server-name <name>]",
    "read_mcp_resource": "/read_mcp_resource server-name <name> uri <uri>",
    "policy_doc_import": (
        "/policy_doc_import path <file-or-dir> [library-root <dir>] [data-root <dir>] [no-recursive]"
    ),
    "policy_doc_list": "/policy_doc_list [limit <n>] [library-root <dir>] [data-root <dir>]",
    "policy_doc_search": "/policy_doc_search <query> [limit <n>] [library-root <dir>] [data-root <dir>]",
    "policy_doc_read": (
        "/policy_doc_read [doc-id <id> | path <file>] [max-chars <n>] [library-root <dir>] [data-root <dir>]"
    ),
}
