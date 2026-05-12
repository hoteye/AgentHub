from __future__ import annotations

# ruff: noqa: F401,I001

import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli.provider import load_provider_management_snapshot
from cli.agent_cli.provider_catalog_toml_runtime import quoted_toml_string
from cli.agent_cli.providers.config.catalog import (
    ModelCatalogEntry,
    ProviderCatalog,
    ProviderCatalogEntry,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection_io import (
    _chmod_private,
    _prepare_isolated_projected_config,
    _projected_codex_home,
    _remove_file_if_exists,
    _write_json_secret_if_changed,
    _write_text_if_changed,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection_models import (
    CODEX_API_KEY_ENV,
    CODEX_AUTH_JSON_API_KEY,
    CODEX_HOME_ENV,
    DEFAULT_PROJECTED_CODEX_HOME_DIR,
    DEFAULT_SCRUBBED_AUTH_ENV_KEYS,
    CodexSidecarProjectedConfig,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection_provider import (
    _BUILT_IN_CODEX_PROVIDER_IDS,
    _auth_store_value,
    _codex_provider_id,
    _normalized_scrubbed_env_keys,
    _project_auth_json,
    _project_provider_block,
    _provider_env_key,
    _provider_env_keys,
    _provider_needs_custom_codex_id,
    _requires_openai_auth,
    _sidecar_scrub_env_keys,
    _slug,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection_selection import (
    _find_model,
    _selected_model_entry,
    _selected_provider_name,
)
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection_toml import (
    _toml_bare_or_quoted_key,
    _toml_inline_table,
    _toml_key_value,
    _toml_scalar,
    _toml_string,
    render_codex_config_toml,
)
from cli.agent_cli.runtime_paths import agent_cli_home


def prepare_codex_sidecar_projected_config(
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    provider_home: Path | None = None,
    snapshot_loader: Callable[..., Any] = load_provider_management_snapshot,
    allow_external_codex_home: bool = False,
) -> CodexSidecarProjectedConfig | None:
    env_map = env if env is not None else os.environ
    explicit_codex_home = str(env_map.get(CODEX_HOME_ENV) or "").strip()
    if allow_external_codex_home and explicit_codex_home:
        codex_home = Path(explicit_codex_home).expanduser()
        return CodexSidecarProjectedConfig(
            codex_home=codex_home,
            config_path=codex_home / "config.toml",
            env={CODEX_HOME_ENV: str(codex_home)},
            scrubbed_env_keys=DEFAULT_SCRUBBED_AUTH_ENV_KEYS,
            generated=False,
        )
    base_home = provider_home or agent_cli_home()
    codex_home = _projected_codex_home(base_home)
    config_path = codex_home / "config.toml"
    try:
        snapshot = snapshot_loader(cwd=cwd)
    except Exception:
        return _prepare_isolated_projected_config(codex_home=codex_home, config_path=config_path)
    catalog = getattr(snapshot, "catalog", None)
    if not isinstance(catalog, ProviderCatalog):
        return _prepare_isolated_projected_config(codex_home=codex_home, config_path=config_path)
    toml_data = dict(getattr(snapshot, "toml_data", {}) or {})
    auth_data = dict(getattr(snapshot, "auth_data", {}) or {})
    projection = project_codex_config_from_catalog(
        catalog=catalog,
        toml_data=toml_data,
        auth_data=auth_data,
        env=env_map,
        source_config_path=str(
            getattr(getattr(snapshot, "resolution", None), "config_path", "") or ""
        ),
        source_auth_path=str(getattr(getattr(snapshot, "resolution", None), "auth_path", "") or ""),
    )
    if projection is None:
        return _prepare_isolated_projected_config(codex_home=codex_home, config_path=config_path)
    rendered = render_codex_config_toml(projection)
    auth_path = codex_home / "auth.json"
    auth_payload = dict(projection.get("auth_json", {}))
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_if_changed(config_path, rendered)
        if auth_payload:
            _write_json_secret_if_changed(auth_path, auth_payload)
        else:
            _remove_file_if_exists(auth_path)
    except OSError:
        return None
    projected_env = {CODEX_HOME_ENV: str(codex_home)}
    scrubbed_env_keys = _normalized_scrubbed_env_keys(projection.get("scrubbed_env_keys", ()))
    return CodexSidecarProjectedConfig(
        codex_home=codex_home,
        config_path=config_path,
        auth_path=auth_path if auth_payload else None,
        env=projected_env,
        provider_name=projection["agenthub_provider_name"],
        model=projection["model"],
        codex_provider_id=projection["codex_provider_id"],
        source_config_path=projection.get("source_config_path", ""),
        source_auth_path=projection.get("source_auth_path", ""),
        auth_key_names=tuple(sorted(str(key) for key in auth_payload if str(key).strip())),
        scrubbed_env_keys=scrubbed_env_keys,
        generated=True,
    )


def project_codex_config_from_catalog(
    *,
    catalog: ProviderCatalog,
    toml_data: Mapping[str, Any],
    auth_data: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    source_config_path: str = "",
    source_auth_path: str = "",
) -> dict[str, Any] | None:
    provider_name = _selected_provider_name(catalog=catalog, toml_data=toml_data)
    if not provider_name:
        return None
    provider = catalog.providers.get(provider_name)
    if provider is None:
        return None
    model_entry = _selected_model_entry(
        catalog=catalog,
        provider_name=provider_name,
        toml_data=toml_data,
    )
    model = str(getattr(model_entry, "model_id", "") or toml_data.get("model") or "").strip()
    if not model:
        return None
    codex_provider_id = _codex_provider_id(provider_name, provider)
    auth_projection = _project_auth_json(provider, auth_data=auth_data)
    return {
        "model": model,
        "model_provider": codex_provider_id,
        "codex_provider_id": codex_provider_id,
        "agenthub_provider_name": provider_name,
        "provider": _project_provider_block(
            provider_name,
            provider,
            uses_codex_auth=bool(auth_projection),
        ),
        "auth_json": auth_projection,
        "scrubbed_env_keys": _sidecar_scrub_env_keys(provider),
        "source_config_path": source_config_path,
        "source_auth_path": source_auth_path,
    }


def merge_sidecar_projected_env(
    *,
    base_env: Mapping[str, str] | None = None,
    projection: CodexSidecarProjectedConfig | None = None,
) -> dict[str, str]:
    env = {str(key): str(value) for key, value in dict(base_env or {}).items()}
    if projection is not None:
        env.update({str(key): str(value) for key, value in projection.env.items()})
    return env
