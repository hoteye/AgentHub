from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_types import (
        ScriptProviderMaterialization,
        ScriptProviderSelectionOverride,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_types import (  # type: ignore[no-redef]
        ScriptProviderMaterialization,
        ScriptProviderSelectionOverride,
    )


def _normalized_provider_home_from_env_overrides(
    env_overrides: dict[str, str | None] | None,
    *,
    normalize_provider_home_override: Callable[[str | Path | None], str],
) -> str:
    if env_overrides is not None and "AGENTHUB_PROVIDER_HOME" in env_overrides:
        return normalize_provider_home_override(env_overrides.get("AGENTHUB_PROVIDER_HOME"))
    return normalize_provider_home_override(os.environ.get("AGENTHUB_PROVIDER_HOME"))


def _quoted_toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def _upsert_root_toml_string_key(existing: str, *, key: str, value: str) -> str:
    from cli.agent_cli import provider_catalog_runtime as provider_catalog_runtime_lib

    return provider_catalog_runtime_lib.upsert_root_toml_string_key(existing, key=key, value=value)


def _resolved_selection_values(
    selected_config: object | None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> tuple[str, str, str]:
    provider_name = ""
    model = ""
    reasoning_effort = ""
    if selected_config is not None:
        provider_name = str(getattr(selected_config, "provider_name", "") or "").strip()
        model_key = str(getattr(selected_config, "model_key", "") or "").strip()
        model = model_key or str(getattr(selected_config, "model", "") or "").strip()
        reasoning_effort = str(getattr(selected_config, "reasoning_effort", "") or "").strip()
    if selection_override is not None:
        override_provider = str(selection_override.provider_name or "").strip()
        override_model = str(selection_override.model or "").strip()
        override_effort = str(selection_override.reasoning_effort or "").strip()
        if override_provider:
            provider_name = override_provider
        if override_model:
            model = override_model
        if override_effort:
            reasoning_effort = override_effort
    return provider_name, model, reasoning_effort


def _selection_toml_text(
    selected_config: object | None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> str:
    provider_name, model, reasoning_effort = _resolved_selection_values(
        selected_config,
        selection_override=selection_override,
    )
    lines: list[str] = []
    if provider_name:
        lines.append(f"model_provider = {_quoted_toml_string(provider_name)}")
    if model:
        lines.append(f"model = {_quoted_toml_string(model)}")
    if reasoning_effort:
        lines.append(f"model_reasoning_effort = {_quoted_toml_string(reasoning_effort)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _apply_selection_override_to_config_text(
    existing_text: str,
    *,
    selected_config: object | None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> str:
    provider_name, model, reasoning_effort = _resolved_selection_values(
        selected_config,
        selection_override=selection_override,
    )
    updated = str(existing_text or "")
    if provider_name:
        updated = _upsert_root_toml_string_key(updated, key="model_provider", value=provider_name)
    if model:
        updated = _upsert_root_toml_string_key(updated, key="model", value=model)
    if reasoning_effort:
        updated = _upsert_root_toml_string_key(
            updated, key="model_reasoning_effort", value=reasoning_effort
        )
    return updated


def _copy_if_exists(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, target)


def _copy_claude_home_if_exists(*, source_home: Path, target_home: Path) -> None:
    for relative_path in (
        Path(".claude") / "settings.json",
        Path(".claude") / "config.json",
        Path(".claude.json"),
    ):
        _copy_if_exists(source_home / relative_path, target_home / relative_path)


def _selected_api_key_env_name(selected_config: object | None) -> str:
    if selected_config is None:
        return ""
    raw_provider = getattr(selected_config, "raw_provider", None)
    provider_block = raw_provider if isinstance(raw_provider, dict) else {}
    auth_block = provider_block.get("auth")
    auth_mapping = auth_block if isinstance(auth_block, dict) else {}
    for value in (
        provider_block.get("api_key_env"),
        provider_block.get("auth_key_name"),
        auth_mapping.get("env_var"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    provider_name = str(getattr(selected_config, "provider_name", "") or "").strip()
    if provider_name:
        return f"{provider_name.upper().replace('-', '_')}_API_KEY"
    return ""


def _materialize_selected_api_key(auth_path: Path, selected_config: object | None) -> None:
    api_key = str(getattr(selected_config, "api_key", "") or "").strip()
    key_name = _selected_api_key_env_name(selected_config)
    if not api_key or not key_name:
        return
    payload: dict[str, Any] = {}
    if auth_path.exists():
        try:
            loaded = json.loads(auth_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        payload = dict(loaded) if isinstance(loaded, dict) else {}
    payload[key_name] = api_key
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _materialize_auth_data(auth_path: Path, auth_data: object) -> None:
    if not isinstance(auth_data, dict) or not auth_data:
        return
    payload: dict[str, Any] = {}
    if auth_path.exists():
        try:
            loaded = json.loads(auth_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        payload = dict(loaded) if isinstance(loaded, dict) else {}
    payload.update(dict(auth_data))
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def materialize_script_provider_fixture(
    *,
    cwd: str | Path,
    target_root: str | Path,
    load_provider_management_snapshot: Callable[..., object],
    normalize_provider_home_override: Callable[[str | Path | None], str],
    normalized_provider_home_from_env_overrides: (
        Callable[[dict[str, str | None] | None], str] | None
    ) = None,
    copy_if_exists: Callable[[Path, Path], None] = _copy_if_exists,
    copy_claude_home_if_exists: Callable[..., None] = _copy_claude_home_if_exists,
    materialize_auth_data: Callable[[Path, object], None] = _materialize_auth_data,
    materialize_selected_api_key: Callable[
        [Path, object | None], None
    ] = _materialize_selected_api_key,
    selection_toml_text: Callable[..., str] = _selection_toml_text,
    apply_selection_override_to_config_text: Callable[..., str] = (
        _apply_selection_override_to_config_text
    ),
    env_overrides: dict[str, str | None] | None = None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> ScriptProviderMaterialization:
    snapshot = load_provider_management_snapshot(
        cwd=cwd,
        env_overrides=env_overrides,
    )
    source_config_path = Path(snapshot.resolution.config_path).resolve()
    source_auth_path = Path(snapshot.resolution.auth_path).resolve()
    target_root_path = Path(target_root).expanduser().resolve()
    normalize_from_env = normalized_provider_home_from_env_overrides or (
        lambda overrides: _normalized_provider_home_from_env_overrides(
            overrides,
            normalize_provider_home_override=normalize_provider_home_override,
        )
    )
    explicit_provider_home = normalize_from_env(env_overrides)
    source_scope = (
        "runtime_home"
        if explicit_provider_home or bool(getattr(snapshot.resolution, "used_project_local", False))
        else "user_home"
    )
    if source_scope == "runtime_home":
        provider_home = target_root_path / "provider_home"
        agent_cli_home = target_root_path / "agent_cli_home"
        copy_if_exists(source_config_path, provider_home / "config.toml")
        copy_if_exists(source_auth_path, provider_home / "auth.json")
        copy_claude_home_if_exists(source_home=source_config_path.parent, target_home=provider_home)
        materialize_auth_data(provider_home / "auth.json", getattr(snapshot, "auth_data", None))
        materialize_selected_api_key(
            provider_home / "auth.json",
            getattr(snapshot, "selected_config", None),
        )
        agent_cli_home.mkdir(parents=True, exist_ok=True)
        selection_text = selection_toml_text(
            getattr(snapshot, "selected_config", None),
            selection_override=selection_override,
        )
        if selection_text:
            (agent_cli_home / "config.toml").write_text(selection_text, encoding="utf-8")
        return ScriptProviderMaterialization(
            config_path=provider_home / "config.toml",
            auth_path=provider_home / "auth.json",
            agent_cli_home=agent_cli_home,
            provider_home=provider_home,
            source_scope=source_scope,
        )

    agent_cli_home = target_root_path
    copy_if_exists(source_config_path, agent_cli_home / "config.toml")
    copy_if_exists(source_auth_path, agent_cli_home / "auth.json")
    materialize_auth_data(agent_cli_home / "auth.json", getattr(snapshot, "auth_data", None))
    materialize_selected_api_key(
        agent_cli_home / "auth.json",
        getattr(snapshot, "selected_config", None),
    )
    if selection_override is not None:
        config_path = agent_cli_home / "config.toml"
        existing_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        updated_text = apply_selection_override_to_config_text(
            existing_text,
            selected_config=getattr(snapshot, "selected_config", None),
            selection_override=selection_override,
        )
        config_path.write_text(updated_text, encoding="utf-8")
    return ScriptProviderMaterialization(
        config_path=agent_cli_home / "config.toml",
        auth_path=agent_cli_home / "auth.json",
        agent_cli_home=agent_cli_home,
        provider_home=None,
        source_scope=source_scope,
    )
