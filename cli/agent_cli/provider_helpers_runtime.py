from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any, Dict, List

from cli.agent_cli import provider_catalog_runtime as _provider_catalog_runtime
from cli.agent_cli import provider_prelude_helpers as _provider_prelude_helpers


def build_ordered_request_prelude_items(
    *,
    developer_item: Dict[str, Any] | None,
    environment_items: List[Dict[str, Any]] | None = None,
    workspace_reference_items: List[Dict[str, Any]] | None = None,
    workspace_message_items: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    return _provider_prelude_helpers.build_ordered_request_prelude_items(
        developer_item=developer_item,
        environment_items=environment_items,
        workspace_reference_items=workspace_reference_items,
        workspace_message_items=workspace_message_items,
    )


def request_prelude_contract(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> Dict[str, Any]:
    return _provider_prelude_helpers.request_prelude_contract(
        items,
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    )


def extract_current_turn_prelude_items(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> List[Dict[str, Any]]:
    return _provider_prelude_helpers.extract_current_turn_prelude_items(
        items,
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    )


def extract_current_turn_prelude_contract(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> Dict[str, Any]:
    return _provider_prelude_helpers.extract_current_turn_prelude_contract(
        items,
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    )


def upsert_root_toml_string_key(existing: str, *, key: str, value: str) -> str:
    return _provider_catalog_runtime.upsert_root_toml_string_key(existing, key=key, value=value)


def read_user_model_selection_toml(
    *,
    config_paths: tuple[Path, ...],
    read_toml_fn,
    selection_keys: tuple[str, ...],
) -> Dict[str, Any]:
    return _provider_catalog_runtime.read_user_model_selection_toml(
        config_paths=config_paths,
        read_toml_fn=read_toml_fn,
        selection_keys=selection_keys,
    )


def slugify_model_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip()).strip("_").lower() or "model"


def ensure_project_provider_bootstrap(
    *,
    project_provider_layout_fn,
    ensure_project_provider_bootstrap_fn,
    agent_cli_config_toml,
    agent_cli_auth_json,
    legacy_compat_config_toml,
    legacy_compat_auth_json,
    claude_settings_json,
    claude_config_json,
    claude_state_json,
) -> None:
    _provider_catalog_runtime.ensure_project_provider_bootstrap(
        project_provider_layout_fn=project_provider_layout_fn,
        ensure_project_provider_bootstrap_fn=ensure_project_provider_bootstrap_fn,
        agent_cli_config_toml=agent_cli_config_toml,
        agent_cli_auth_json=agent_cli_auth_json,
        legacy_compat_config_toml=legacy_compat_config_toml,
        legacy_compat_auth_json=legacy_compat_auth_json,
        claude_settings_json=claude_settings_json,
        claude_config_json=claude_config_json,
        claude_state_json=claude_state_json,
    )


def home_provider_paths(
    *,
    ensure_project_provider_bootstrap_fn,
    project_provider_layout_fn,
    agent_cli_config_toml,
    agent_cli_auth_json,
    legacy_compat_config_toml,
    legacy_compat_auth_json,
) -> tuple[Path, Path, bool]:
    return _provider_catalog_runtime.home_provider_paths(
        ensure_project_provider_bootstrap_fn=ensure_project_provider_bootstrap_fn,
        project_provider_layout_fn=project_provider_layout_fn,
        agent_cli_config_toml=agent_cli_config_toml,
        agent_cli_auth_json=agent_cli_auth_json,
        legacy_compat_config_toml=legacy_compat_config_toml,
        legacy_compat_auth_json=legacy_compat_auth_json,
    )


def project_claude_home_dir(*, project_provider_layout_fn) -> Path | None:
    return _provider_catalog_runtime.project_claude_home_dir(
        project_provider_layout_fn=project_provider_layout_fn,
    )


def quote_arg(value: Any) -> str:
    return shlex.quote(str(value))
