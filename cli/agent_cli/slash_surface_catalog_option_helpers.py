from __future__ import annotations

OPTION_VALUES_DATA: dict[tuple[str, str], tuple[str, ...]] = {
    ("exec_command", "login"): ("true", "false"),
    ("connect", "auth-mode"): ("api_key", "oauth", "wellknown", "none"),
    ("connect", "write"): ("user", "project"),
    ("setup", "write"): ("user", "project"),
    ("auth", "mode"): ("device_code", "browser_pkce"),
    ("auth", "daemon"): ("start", "status", "stop"),
    ("provider", "write"): ("session", "user", "project"),
    ("model", "reasoning-effort"): ("low", "medium", "high", "xhigh", "default"),
    ("model", "write"): ("session", "user", "project"),
    ("plugin_install", "scope"): ("user", "project", "local", "managed"),
    ("plugin_marketplace", "scope"): ("project", "user"),
    ("runtime_config", "permission-mode"): (
        "default",
        "plan",
        "acceptEdits",
        "dontAsk",
        "bypassPermissions",
        "accept-edits",
        "dont-ask",
        "bypass-permissions",
    ),
    ("runtime_config", "network-access"): ("enabled", "disabled"),
    ("recover_agent", "action"): ("retry_step", "resume_session", "close_session"),
    ("plugin_disable", "all"): ("all",),
    ("mcp", "approved"): ("true", "false"),
    ("github_approval_list", "status"): ("pending", "approved", "rejected"),
}

IMPLICIT_ENUMS_DATA: dict[str, dict[str, tuple[str, str | None]]] = {
    "connect": {
        "user": ("write", "user"),
        "project": ("write", "project"),
    },
    "setup": {
        "user": ("write", "user"),
        "project": ("write", "project"),
    },
    "provider": {
        "session": ("write", "session"),
        "user": ("write", "user"),
        "project": ("write", "project"),
        "verbose": ("verbose", None),
        "probe": ("probe", None),
    },
    "model": {
        "low": ("reasoning-effort", "low"),
        "medium": ("reasoning-effort", "medium"),
        "high": ("reasoning-effort", "high"),
        "xhigh": ("reasoning-effort", "xhigh"),
        "default": ("reasoning-effort", "default"),
        "session": ("write", "session"),
        "user": ("write", "user"),
        "project": ("write", "project"),
    },
    "codex_threads": {
        "archived": ("archived", None),
    },
    "plugin_disable": {
        "all": ("all", None),
    },
}

RIGHT_BOUNDARY_OPTION_COMMAND_NAMES: tuple[str, ...] = (
    "file_search",
    "web_search",
    "background_teammate",
    "policy_doc_search",
)
LEADING_OPTION_COMMAND_NAMES: tuple[str, ...] = ("background_benchmark", "background_smoke")
SECOND_POSITION_AS_PATH_COMMAND_NAMES: tuple[str, ...] = ("office_run",)
