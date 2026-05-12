from __future__ import annotations

from pathlib import Path
from typing import Any


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _resolved_path(value: Any) -> Path | None:
    text = _normalized_text(value)
    if not text:
        return None
    candidate = Path(text).expanduser()
    try:
        return candidate.resolve()
    except OSError:
        return candidate


def _same_path(left: Path | None, right: Path | None) -> bool:
    return left is not None and right is not None and left == right


def _is_same_or_child(path: Path | None, root: Path | None) -> bool:
    if path is None or root is None:
        return False
    return path == root or root in path.parents


def provider_source_semantics_fields(
    *,
    raw_source: Any,
    config_path: Any,
    auth_path: Any,
    selection_path: Any,
    selection_present: bool,
    user_config_path: Any = None,
    user_auth_path: Any = None,
    runtime_home: Any = None,
) -> dict[str, Any]:
    raw_source_text = _normalized_text(raw_source)
    resolved_config_path = _resolved_path(config_path)
    resolved_auth_path = _resolved_path(auth_path)
    resolved_selection_path = _resolved_path(selection_path)
    resolved_user_config_path = _resolved_path(user_config_path)
    resolved_runtime_home = _resolved_path(runtime_home)

    runtime_home_active = resolved_runtime_home is not None
    config_scope = "unknown"
    if runtime_home_active and (
        _is_same_or_child(resolved_config_path, resolved_runtime_home)
        or _is_same_or_child(resolved_auth_path, resolved_runtime_home)
    ):
        config_scope = "runtime_home"
    elif _same_path(resolved_config_path, resolved_user_config_path):
        config_scope = "user_home"
    elif raw_source_text == "project_local":
        config_scope = "project_local"
    elif raw_source_text == "agent_cli_home":
        config_scope = "user_home"

    selection_scope = "none"
    if selection_present and resolved_selection_path is not None:
        selection_scope = "custom"
        if _same_path(resolved_selection_path, resolved_user_config_path):
            selection_scope = "user_home"

    public_source = raw_source_text
    if raw_source_text == "agent_cli_home" and config_scope == "runtime_home":
        public_source = "runtime_home"
    elif raw_source_text == "agent_cli_home":
        public_source = "user_home"
    elif raw_source_text == "project_local" and config_scope == "runtime_home":
        public_source = "runtime_home"

    source_raw = raw_source_text or "-"
    if raw_source_text == "agent_cli_home" and config_scope == "runtime_home":
        source_raw = "project_local"
    payload = {
        "provider_source": public_source or raw_source_text,
        "provider_source_raw": source_raw,
        "provider_config_scope": config_scope,
        "provider_selection_scope": selection_scope,
        "provider_selection_active": bool(selection_present),
        "provider_runtime_home_active": runtime_home_active,
        "provider_runtime_home_path": str(resolved_runtime_home or ""),
    }
    if raw_source_text == public_source and source_raw == raw_source_text:
        payload.pop("provider_source_raw", None)
    return payload


__all__ = ["provider_source_semantics_fields"]
