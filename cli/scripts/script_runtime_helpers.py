from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from cli.scripts import script_runtime_helpers_provider_runtime as provider_runtime
    from cli.scripts.script_runtime_types import (
        CodexSourcePaths,
        ScriptImportPaths,
        ScriptProviderMaterialization,
        ScriptProviderSelectionOverride,
        ScriptResolvedProviderSettings,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    import script_runtime_helpers_provider_runtime as provider_runtime  # type: ignore[no-redef]
    from script_runtime_types import (  # type: ignore[no-redef]
        CodexSourcePaths,
        ScriptImportPaths,
        ScriptProviderMaterialization,
        ScriptProviderSelectionOverride,
        ScriptResolvedProviderSettings,
    )


def _discover_cli_root(script_path: Path) -> Path:
    for candidate in script_path.parents:
        if candidate.name == "cli":
            return candidate
    return script_path.parents[1]


def ensure_script_import_paths(script_file: str | Path) -> ScriptImportPaths:
    script_path = Path(script_file).resolve()
    cli_root = _discover_cli_root(script_path)
    repo_root = cli_root.parent
    for candidate in (str(repo_root), str(cli_root)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    return ScriptImportPaths(cli_root=cli_root, repo_root=repo_root)


def load_script_provider_management_snapshot(
    *,
    cwd: str | Path,
    env_overrides: dict[str, str | None] | None = None,
):
    from cli.agent_cli import provider as provider_module

    return provider_module.load_provider_management_snapshot(
        cwd=cwd,
        env_overrides=env_overrides,
    )


def resolve_script_provider_source_paths(
    *,
    cwd: str | Path,
    auth_json_override: str | Path | None = None,
) -> tuple[Path, Path]:
    snapshot = load_script_provider_management_snapshot(cwd=cwd)
    auth_path = (
        Path(auth_json_override).resolve() if auth_json_override else snapshot.resolution.auth_path
    )
    return snapshot.resolution.config_path, auth_path


def resolve_script_provider_home_dir(
    *,
    cwd: str | Path,
) -> Path:
    snapshot = load_script_provider_management_snapshot(cwd=cwd)
    return snapshot.resolution.config_path.parent


def normalize_optional_provider_home_override(
    provider_home: str | Path | None,
) -> str:
    text = str(provider_home or "").strip()
    if not text:
        return ""
    return str(Path(text).expanduser().resolve())


def resolve_effective_script_provider_home_dir(
    *,
    cwd: str | Path,
    provider_home: str | Path | None = None,
) -> Path:
    normalized_override = normalize_optional_provider_home_override(provider_home)
    if normalized_override:
        return Path(normalized_override)
    return resolve_script_provider_home_dir(cwd=cwd)


def _selected_or_resolution_path(
    *,
    selected_config: object | None,
    selected_attr: str,
    fallback_path: str | Path,
) -> Path:
    selected_value = (
        str(getattr(selected_config, selected_attr, "") or "").strip()
        if selected_config is not None
        else ""
    )
    raw_path = selected_value or str(fallback_path)
    return Path(raw_path).expanduser().resolve()


def _provider_selection_env_overrides(
    *,
    provider: str = "",
    model: str = "",
    reasoning_effort: str = "",
    base_url: str = "",
    env_overrides: dict[str, str | None] | None = None,
) -> dict[str, str | None]:
    merged: dict[str, str | None] = dict(env_overrides or {})
    if str(provider or "").strip():
        merged["AGENT_CLI_PROVIDER"] = str(provider).strip()
    if str(model or "").strip():
        merged["AGENT_CLI_MODEL"] = str(model).strip()
    if str(reasoning_effort or "").strip():
        merged["AGENT_CLI_REASONING_EFFORT"] = str(reasoning_effort).strip()
    if str(base_url or "").strip():
        merged["AGENT_CLI_BASE_URL"] = str(base_url).strip()
    return merged


def resolve_script_provider_run_settings(
    *,
    cwd: str | Path,
    provider: str = "",
    model: str = "",
    reasoning_effort: str = "",
    base_url: str = "",
    default_base_url: str = "",
    env_overrides: dict[str, str | None] | None = None,
    catalog_cwd: str | Path | None = None,
    interaction_profile: str = "",
    planner_kind: str = "openai_responses",
    wire_api: str = "responses",
) -> ScriptResolvedProviderSettings:
    selection_env = _provider_selection_env_overrides(
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        base_url=base_url,
        env_overrides=env_overrides,
    )
    snapshot = load_script_provider_management_snapshot(
        cwd=cwd,
        env_overrides=selection_env,
    )
    selected_config = getattr(snapshot, "selected_config", None)
    if selected_config is None:
        raise SystemExit("provider management snapshot returned no selected_config")

    provider_name = str(getattr(selected_config, "provider_name", "") or "").strip()
    requested_provider = str(provider or "").strip()
    if requested_provider:
        provider_name = requested_provider
    if not provider_name:
        raise SystemExit("unable to resolve provider from provider management snapshot")

    requested_model = str(model or "").strip()
    selected_model_key = str(getattr(selected_config, "model_key", "") or "").strip()
    selected_model = str(getattr(selected_config, "model", "") or "").strip()
    agenthub_model = requested_model or selected_model_key or selected_model

    selected_reasoning = str(getattr(selected_config, "reasoning_effort", "") or "").strip()
    resolved_model, resolved_effort = resolve_model_and_reasoning_settings(
        provider=provider_name,
        model=agenthub_model,
        reasoning_effort=str(reasoning_effort or "").strip() or selected_reasoning,
        catalog_cwd=catalog_cwd or cwd,
        interaction_profile=interaction_profile,
        planner_kind=planner_kind,
        wire_api=wire_api,
    )
    resolved_base_url = (
        str(base_url or "").strip()
        or str(getattr(selected_config, "base_url", "") or "").strip()
        or str(default_base_url or "").strip()
    )
    config_path = _selected_or_resolution_path(
        selected_config=selected_config,
        selected_attr="config_path",
        fallback_path=snapshot.resolution.config_path,
    )
    auth_path = _selected_or_resolution_path(
        selected_config=selected_config,
        selected_attr="auth_path",
        fallback_path=snapshot.resolution.auth_path,
    )
    return ScriptResolvedProviderSettings(
        provider_name=provider_name,
        model_key=agenthub_model,
        model=resolved_model,
        reasoning_effort=resolved_effort or selected_reasoning,
        base_url=resolved_base_url,
        config_path=config_path,
        auth_path=auth_path,
        api_key=str(getattr(selected_config, "api_key", "") or "").strip(),
        source=str(getattr(selected_config, "source", "") or "").strip(),
    )


def apply_provider_home_override_env(
    env: dict[str, str],
    *,
    provider_home: str | Path | None = None,
    strict_isolation_when_explicit: bool = True,
) -> dict[str, str]:
    normalized_override = normalize_optional_provider_home_override(provider_home)
    env.pop("AGENTHUB_PROVIDER_HOME", None)
    env.pop("AGENTHUB_PROVIDER_STRICT_ISOLATION", None)
    if normalized_override:
        env["AGENTHUB_PROVIDER_HOME"] = normalized_override
        if strict_isolation_when_explicit:
            env["AGENTHUB_PROVIDER_STRICT_ISOLATION"] = "true"
    return env


def _normalized_provider_home_from_env_overrides(
    env_overrides: dict[str, str | None] | None,
) -> str:
    return provider_runtime._normalized_provider_home_from_env_overrides(
        env_overrides,
        normalize_provider_home_override=normalize_optional_provider_home_override,
    )


def _quoted_toml_string(value: str) -> str:
    return provider_runtime._quoted_toml_string(value)


def _upsert_root_toml_string_key(existing: str, *, key: str, value: str) -> str:
    return provider_runtime._upsert_root_toml_string_key(existing, key=key, value=value)


def _resolved_selection_values(
    selected_config: object | None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> tuple[str, str, str]:
    return provider_runtime._resolved_selection_values(
        selected_config,
        selection_override=selection_override,
    )


def _selection_toml_text(
    selected_config: object | None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> str:
    return provider_runtime._selection_toml_text(
        selected_config,
        selection_override=selection_override,
    )


def _apply_selection_override_to_config_text(
    existing_text: str,
    *,
    selected_config: object | None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> str:
    return provider_runtime._apply_selection_override_to_config_text(
        existing_text,
        selected_config=selected_config,
        selection_override=selection_override,
    )


def _copy_if_exists(source: Path, target: Path) -> None:
    provider_runtime._copy_if_exists(source, target)


def _copy_claude_home_if_exists(*, source_home: Path, target_home: Path) -> None:
    provider_runtime._copy_claude_home_if_exists(source_home=source_home, target_home=target_home)


def _selected_api_key_env_name(selected_config: object | None) -> str:
    return provider_runtime._selected_api_key_env_name(selected_config)


def _materialize_selected_api_key(auth_path: Path, selected_config: object | None) -> None:
    provider_runtime._materialize_selected_api_key(auth_path, selected_config)


def _materialize_auth_data(auth_path: Path, auth_data: object) -> None:
    provider_runtime._materialize_auth_data(auth_path, auth_data)


def materialize_script_provider_fixture(
    *,
    cwd: str | Path,
    target_root: str | Path,
    env_overrides: dict[str, str | None] | None = None,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> ScriptProviderMaterialization:
    return provider_runtime.materialize_script_provider_fixture(
        cwd=cwd,
        target_root=target_root,
        load_provider_management_snapshot=load_script_provider_management_snapshot,
        normalize_provider_home_override=normalize_optional_provider_home_override,
        normalized_provider_home_from_env_overrides=_normalized_provider_home_from_env_overrides,
        copy_if_exists=_copy_if_exists,
        copy_claude_home_if_exists=_copy_claude_home_if_exists,
        materialize_auth_data=_materialize_auth_data,
        materialize_selected_api_key=_materialize_selected_api_key,
        selection_toml_text=_selection_toml_text,
        apply_selection_override_to_config_text=_apply_selection_override_to_config_text,
        env_overrides=env_overrides,
        selection_override=selection_override,
    )


def apply_script_provider_materialization_env(
    env: dict[str, str],
    *,
    fixture: ScriptProviderMaterialization,
) -> dict[str, str]:
    env.pop("AGENT_CLI_HOME", None)
    apply_provider_home_override_env(env, provider_home=fixture.provider_home)
    env["AGENT_CLI_HOME"] = str(fixture.agent_cli_home)
    return env


def normalize_script_validation_command(command: list[str] | tuple[str, ...]) -> list[str]:
    parts = [str(part) for part in list(command or ())]
    if not parts:
        return []
    executable_name = Path(parts[0]).name
    if executable_name in {"pytest", "pytest3"}:
        return [sys.executable, "-m", "pytest", *parts[1:]]
    return parts


def resolve_codex_source_paths(
    *,
    home_override: str | Path | None = None,
) -> CodexSourcePaths:
    explicit_home = str(home_override or "").strip()
    env_home = str(os.environ.get("CODEX_HOME") or "").strip()
    if explicit_home:
        home = Path(explicit_home).expanduser().resolve()
    elif env_home:
        home = Path(env_home).expanduser().resolve()
    else:
        home = (Path.home() / ".codex").resolve()
    return CodexSourcePaths(
        home=home,
        config_path=home / "config.toml",
        auth_path=home / "auth.json",
        skills_dir=home / "skills",
    )


def resolve_model_and_reasoning_settings(
    *,
    provider: str,
    model: str,
    reasoning_effort: str,
    catalog_cwd: str | Path,
    interaction_profile: str = "",
    planner_kind: str = "openai_responses",
    wire_api: str = "responses",
) -> tuple[str, str]:
    from cli.agent_cli import provider as provider_module
    from cli.agent_cli import provider_catalog_runtime as provider_catalog_runtime_lib

    catalog = provider_module.load_provider_catalog(cwd=catalog_cwd)
    profile = provider_catalog_runtime_lib.model_catalog_reasoning_profile(
        catalog=catalog,
        provider_name=provider,
        model=model,
        interaction_profile=interaction_profile,
        planner_kind=planner_kind,
        wire_api=wire_api,
    )
    resolved_model = str(profile.get("model_id") or "").strip() or str(model or "").strip()
    if not resolved_model:
        raise SystemExit(f"unable to resolve model for provider `{provider}`")
    supported_reasoning_efforts = tuple(profile.get("supported_reasoning_efforts") or ())
    normalized_reasoning_effort = str(reasoning_effort or "").strip().lower()
    if normalized_reasoning_effort:
        if not supported_reasoning_efforts:
            raise SystemExit(f"model `{resolved_model}` does not support reasoning_effort")
        if normalized_reasoning_effort not in supported_reasoning_efforts:
            choices = ", ".join(supported_reasoning_efforts)
            raise SystemExit(
                f"unsupported reasoning_effort `{normalized_reasoning_effort}` for model `{resolved_model}`; expected one of: {choices}"
            )
        return resolved_model, normalized_reasoning_effort
    return resolved_model, str(profile.get("default_reasoning_effort") or "").strip().lower()
