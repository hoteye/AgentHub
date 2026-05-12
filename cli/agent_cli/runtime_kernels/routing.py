from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_kernels.base import KernelEngine
from cli.agent_cli.runtime_kernels.codex_sidecar.artifact import (
    codex_sidecar_artifact_available,
)
from cli.agent_cli.runtime_paths import agent_cli_home, project_local_data_dir

CODEX_SIDECAR_DEFAULT_FOR_OPENAI_ENV = "AGENTHUB_CODEX_SIDECAR_DEFAULT_FOR_OPENAI"
CODEX_SIDECAR_ENGINE_ENV = "AGENTHUB_RUNTIME_ENGINE"
OPENAI_CODEX_PROVIDER_NAMES = frozenset({"openai", "codex", "openai_codex"})


def normalize_kernel_engine(
    value: Any, *, default: KernelEngine | None = None
) -> KernelEngine | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        return default
    if normalized in {"python", "agenthub", "agenthub_python"}:
        return "agenthub_python"
    if normalized in {"codex", "sidecar", "codex_sidecar", "openai", "openai_codex"}:
        return "codex_sidecar"
    return default


def codex_sidecar_default_for_openai_enabled(
    *,
    env: Mapping[str, str] | None = None,
    config_paths: list[Path] | None = None,
) -> bool:
    env_map = env if env is not None else os.environ
    raw_env = str(env_map.get(CODEX_SIDECAR_DEFAULT_FOR_OPENAI_ENV) or "").strip()
    if raw_env:
        return _truthy(raw_env)
    for path in config_paths if config_paths is not None else _default_config_paths():
        payload = _read_toml(path)
        value = _nested_lookup(
            payload,
            ("runtime_kernels", "codex_sidecar", "default_for_openai"),
        )
        if value is not None:
            return _truthy(value)
    return False


def openai_codex_provider_status(status: Mapping[str, Any]) -> bool:
    provider_name = (
        str(
            status.get("provider_public_name")
            or status.get("provider_name")
            or status.get("provider_route_name")
            or ""
        )
        .strip()
        .lower()
    )
    if provider_name not in OPENAI_CODEX_PROVIDER_NAMES:
        return False
    planner = (
        str(status.get("provider_planner") or status.get("planner_kind") or "").strip().lower()
    )
    wire_api = str(status.get("wire_api") or status.get("provider_wire_api") or "").strip().lower()
    tools = str(status.get("provider_tools") or "").strip().lower()
    profile = (
        str(status.get("interaction_profile") or status.get("tool_surface_profile") or "")
        .strip()
        .lower()
    )
    return (
        planner in {"", "-", "openai_responses"}
        or wire_api in {"responses", "openai_responses"}
        or "responses" in tools
        or profile == "codex_openai"
    )


def runtime_provider_status(runtime: Any) -> dict[str, Any]:
    agent = getattr(runtime, "agent", None)
    status_getter = getattr(agent, "provider_status", None)
    if not callable(status_getter):
        return {}
    try:
        return dict(status_getter() or {})
    except Exception:
        return {}


def runtime_provider_config_status(runtime: Any) -> dict[str, Any]:
    agent = getattr(runtime, "agent", None)
    planner = getattr(agent, "_planner", None)
    config = getattr(agent, "_provider_config", None) or getattr(planner, "config", None)
    if config is None:
        return {}
    raw_provider = getattr(config, "raw_provider", None)
    raw_provider_map = raw_provider if isinstance(raw_provider, Mapping) else {}
    return {
        "provider_name": str(getattr(config, "provider_name", "") or "").strip(),
        "provider_public_name": str(getattr(config, "provider_name", "") or "").strip(),
        "provider_planner": str(getattr(config, "planner_kind", "") or "").strip(),
        "provider_model": str(
            getattr(config, "model", "") or getattr(config, "model_key", "") or ""
        ).strip(),
        "wire_api": str(
            getattr(config, "wire_api", "") or raw_provider_map.get("wire_api") or ""
        ).strip(),
        "interaction_profile": str(
            getattr(config, "interaction_profile", "")
            or raw_provider_map.get("interaction_profile")
            or ""
        ).strip(),
    }


def select_new_tab_engine(
    runtime: Any,
    *,
    explicit_engine: KernelEngine | None = None,
    env: Mapping[str, str] | None = None,
    config_paths: list[Path] | None = None,
    artifact_available_fn=codex_sidecar_artifact_available,
) -> KernelEngine:
    if explicit_engine is not None:
        return explicit_engine
    env_map = env if env is not None else os.environ
    env_engine = normalize_kernel_engine(env_map.get(CODEX_SIDECAR_ENGINE_ENV))
    if env_engine is not None:
        return env_engine
    if not codex_sidecar_default_for_openai_enabled(env=env_map, config_paths=config_paths):
        return "agenthub_python"
    provider_status = runtime_provider_status(runtime)
    provider_config_status = runtime_provider_config_status(runtime)
    if not (
        openai_codex_provider_status(provider_status)
        or openai_codex_provider_status(provider_config_status)
    ):
        return "agenthub_python"
    try:
        if not bool(artifact_available_fn()):
            return "agenthub_python"
    except Exception:
        return "agenthub_python"
    return "codex_sidecar"


def sidecar_provider_hint_lines(status: Mapping[str, Any]) -> list[str]:
    if str(status.get("provider_source") or "").strip() == "codex_sidecar":
        return [
            "runtime_kernel=codex_sidecar",
            f"codex_sidecar_source={str(status.get('codex_sidecar_source') or '-').strip() or '-'}",
        ]
    if not openai_codex_provider_status(status):
        return []
    return [
        "openai_codex_runtime=codex_sidecar_available",
        "openai_codex_note=OpenAI/Codex tabs can use /tab_new openai or --engine codex_sidecar",
    ]


def _default_config_paths() -> list[Path]:
    paths = [
        project_local_data_dir() / "config.toml",
        agent_cli_home() / "config.toml",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path.expanduser())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(path)
    return unique


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _nested_lookup(payload: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        if key not in current:
            return None
        current = current[key]
    return current


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}
