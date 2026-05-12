from __future__ import annotations

from pathlib import Path


_APPROVAL_POLICIES = {"never", "on-request", "on-failure", "untrusted", "unless-trusted"}
_SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}
_WEB_SEARCH_MODES = {"disabled", "cached", "live"}
_RUNTIME_CWD_SOURCES = {"runtime_cwd", "inherited"}
_WORKSPACE_ROOT_SOURCES = {"runtime_cwd", "thread_workspace", "inherited"}
_POLICY_SOURCES = {"runtime_policy", "inherited"}


def normalize_runtime_cwd(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def resolve_workspace_root(*, cwd: str, workspace_root: str | None = None) -> str:
    root, _ = resolve_workspace_root_with_source(cwd=cwd, workspace_root=workspace_root)
    return root


def resolve_workspace_root_with_source(
    *,
    cwd: str,
    workspace_root: str | None = None,
    inherited: bool = False,
) -> tuple[str, str]:
    resolved_cwd = str(Path(cwd).expanduser().resolve())
    if inherited:
        return str(Path(workspace_root or resolved_cwd).expanduser().resolve()), "inherited"
    if workspace_root is None or str(workspace_root).strip() == "":
        return resolved_cwd, "runtime_cwd"
    resolved_root = str(Path(workspace_root).expanduser().resolve())
    if resolved_root == resolved_cwd:
        return resolved_root, "runtime_cwd"
    return resolved_root, "thread_workspace"


def normalize_approval_policy(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if token in _APPROVAL_POLICIES:
        return token
    return "on-request"


def normalize_sandbox_mode(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if token in _SANDBOX_MODES:
        return token
    return "workspace-write"


def normalize_web_search_mode(value: str | None) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    if token in _WEB_SEARCH_MODES:
        return token
    return None


def normalize_network_access(value: str | bool | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if token in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return None


def normalize_runtime_cwd_source(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if token in _RUNTIME_CWD_SOURCES:
        return token
    return "runtime_cwd"


def normalize_workspace_root_source(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if token in _WORKSPACE_ROOT_SOURCES:
        return token
    return "runtime_cwd"


def normalize_policy_source(value: str | None) -> str:
    token = str(value or "").strip().lower()
    if token in _POLICY_SOURCES:
        return token
    return "runtime_policy"
