from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cli.agent_cli.approval_contract_runtime_decision_helpers_runtime import (
    APPROVAL_DECISION_ACCEPT_FOR_SESSION,
    _normalized_token,
    normalize_approval_decision,
)


_PATCH_FILE_PREFIX = "patch-file:"
_PATCH_ROOT_PREFIX = "patch-root:"
_SHELL_PREFIX = "shell:"
_BROWSER_HOST_PREFIX = "browser-host:"


def _approval_session_store(runtime: Any) -> dict[str, dict[str, Any]]:
    store = getattr(runtime, "_approval_session_cache", None)
    if not isinstance(store, dict):
        store = {}
        setattr(runtime, "_approval_session_cache", store)
    return store


def session_approval_is_cached(
    runtime: Any,
    *,
    session_cache_keys: list[str] | None = None,
) -> bool:
    store = _approval_session_store(runtime)
    normalized_keys = [
        _normalized_token(item)
        for item in list(session_cache_keys or [])
        if _normalized_token(item)
    ]
    return bool(normalized_keys) and all(key in store for key in normalized_keys)


def browser_session_cache_keys(*, host: str | None = None) -> list[str]:
    normalized_host = _normalized_token(host).lower()
    if not normalized_host:
        return []
    return [f"{_BROWSER_HOST_PREFIX}{normalized_host}"]


def shell_session_cache_keys(
    *,
    command: str,
    cwd: str | Path | None,
    exec_mode: str,
    login: bool,
    tty: bool,
    shell: str | None,
    sandbox_permissions: str | None = None,
    additional_permissions: dict[str, Any] | None = None,
) -> list[str]:
    normalized_cwd = _normalized_token(cwd)
    if normalized_cwd:
        try:
            normalized_cwd = str(Path(normalized_cwd).expanduser().resolve())
        except OSError:
            normalized_cwd = str(Path(normalized_cwd).expanduser())
    payload = {
        "command": _normalized_token(command),
        "cwd": normalized_cwd or None,
        "exec_mode": _normalized_token(exec_mode) or "exec_once",
        "login": bool(login),
        "tty": bool(tty),
        "shell": _normalized_token(shell) or None,
        "sandbox_permissions": _normalized_token(sandbox_permissions) or None,
        "additional_permissions": (
            json.loads(json.dumps(additional_permissions, ensure_ascii=False, sort_keys=True))
            if isinstance(additional_permissions, dict)
            else None
        ),
    }
    return [f"{_SHELL_PREFIX}{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"]


def _absolute_paths_from_preview(preview: dict[str, Any], *, workspace_root: Path) -> list[Path]:
    resolved_root = workspace_root.resolve()
    paths: list[Path] = []
    changes = list(preview.get("changes") or [])
    if not changes and _normalized_token(preview.get("file_path")):
        changes = [{"path": preview.get("file_path")}]
    for change in changes:
        if not isinstance(change, dict):
            continue
        raw_path = _normalized_token(change.get("path"))
        if not raw_path:
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = resolved_root / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        paths.append(resolved)
    return paths


def _common_grant_root(paths: list[Path], *, workspace_root: Path) -> str | None:
    if not paths:
        return None
    if len(paths) == 1:
        candidate = paths[0].parent if paths[0].suffix else paths[0]
    else:
        candidate = Path(os.path.commonpath([str(item) for item in paths]))
    try:
        resolved_workspace = workspace_root.resolve()
    except OSError:
        resolved_workspace = workspace_root
    try:
        candidate.relative_to(resolved_workspace)
    except ValueError:
        return str(resolved_workspace)
    return str(candidate)


def patch_session_contract(*, preview: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    absolute_paths = _absolute_paths_from_preview(preview, workspace_root=workspace_root)
    return {
        "session_cache_keys": [f"{_PATCH_FILE_PREFIX}{path}" for path in absolute_paths],
        "grant_root": _common_grant_root(absolute_paths, workspace_root=workspace_root),
        "absolute_paths": [str(path) for path in absolute_paths],
    }


def shell_approval_is_cached(
    runtime: Any,
    *,
    command: str,
    cwd: str | Path | None,
    exec_mode: str,
    login: bool,
    tty: bool,
    shell: str | None,
    sandbox_permissions: str | None = None,
    additional_permissions: dict[str, Any] | None = None,
) -> bool:
    store = _approval_session_store(runtime)
    keys = shell_session_cache_keys(
        command=command,
        cwd=cwd,
        exec_mode=exec_mode,
        login=login,
        tty=tty,
        shell=shell,
        sandbox_permissions=sandbox_permissions,
        additional_permissions=additional_permissions,
    )
    return all(key in store for key in keys)


def patch_approval_is_cached(runtime: Any, *, preview: dict[str, Any], workspace_root: Path) -> bool:
    store = _approval_session_store(runtime)
    contract = patch_session_contract(preview=preview, workspace_root=workspace_root)
    keys = list(contract.get("session_cache_keys") or [])
    if keys and all(key in store for key in keys):
        return True
    absolute_paths = [Path(item) for item in list(contract.get("absolute_paths") or [])]
    approved_roots = [
        Path(str(key[len(_PATCH_ROOT_PREFIX) :]))
        for key in store
        if str(key).startswith(_PATCH_ROOT_PREFIX)
    ]
    for root in approved_roots:
        if all(_path_within(path, root) for path in absolute_paths):
            return True
    return False


def store_session_approval(
    runtime: Any,
    *,
    session_cache_keys: list[str] | None = None,
    grant_root: str | None = None,
    decision: Any,
) -> None:
    if str(normalize_approval_decision(decision).get("type") or "") != APPROVAL_DECISION_ACCEPT_FOR_SESSION:
        return
    store = _approval_session_store(runtime)
    payload = {"decision_type": APPROVAL_DECISION_ACCEPT_FOR_SESSION}
    for key in list(session_cache_keys or []):
        normalized_key = _normalized_token(key)
        if normalized_key:
            store[normalized_key] = dict(payload)
    normalized_root = _normalized_token(grant_root)
    if normalized_root:
        store[f"{_PATCH_ROOT_PREFIX}{normalized_root}"] = dict(payload)


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    except OSError:
        return str(path).startswith(f"{root}{os.sep}") or str(path) == str(root)
    return True


__all__ = [
    "browser_session_cache_keys",
    "patch_approval_is_cached",
    "patch_session_contract",
    "session_approval_is_cached",
    "shell_approval_is_cached",
    "shell_session_cache_keys",
    "store_session_approval",
]
