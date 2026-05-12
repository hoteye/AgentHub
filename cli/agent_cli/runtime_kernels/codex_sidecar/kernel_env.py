from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.artifact import CodexSidecarArtifact
from cli.agent_cli.runtime_kernels.codex_sidecar.config_projection import (
    CODEX_HOME_ENV,
    DEFAULT_SCRUBBED_AUTH_ENV_KEYS,
    CodexSidecarProjectedConfig,
)


def _sidecar_runtime_env(
    *,
    artifact: CodexSidecarArtifact | None,
    extra_env: Mapping[str, str] | None,
    scrubbed_env_keys: tuple[str, ...] = (),
) -> dict[str, str]:
    env = {str(key): str(value) for key, value in dict(extra_env or {}).items()}
    for key in scrubbed_env_keys:
        env.pop(str(key), None)
    path_entries = _sidecar_artifact_path_entries(artifact)
    if not path_entries:
        return env
    base_path = env.get("PATH") or os.environ.get("PATH") or ""
    next_parts = [str(path) for path in path_entries]
    if base_path:
        next_parts.append(base_path)
    env["PATH"] = os.pathsep.join(next_parts)
    return env


def _sidecar_scrubbed_env_keys(
    projection: CodexSidecarProjectedConfig | None,
) -> tuple[str, ...]:
    keys: list[str] = []
    for raw_key in (
        *(projection.scrubbed_env_keys if projection is not None else ()),
        *DEFAULT_SCRUBBED_AUTH_ENV_KEYS,
    ):
        key = str(raw_key or "").strip()
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _sidecar_inherited_remove_env_keys(scrubbed_env_keys: tuple[str, ...]) -> tuple[str, ...]:
    keys: list[str] = []
    for raw_key in (CODEX_HOME_ENV, *scrubbed_env_keys):
        key = str(raw_key or "").strip()
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _sidecar_artifact_path_entries(artifact: CodexSidecarArtifact | None) -> list[Path]:
    if artifact is None:
        return []
    bundle_root = artifact.path.parent
    manifest = dict(artifact.manifest or {})
    entries: list[Path] = []
    for raw_entry in _manifest_path_entries(manifest):
        candidate = bundle_root / raw_entry
        if candidate.is_dir():
            entries.append(candidate.resolve(strict=False))
    for raw_resource in _manifest_resource_paths(manifest):
        candidate = bundle_root / raw_resource
        directory = candidate if candidate.is_dir() else candidate.parent
        if directory.is_dir():
            entries.append(directory.resolve(strict=False))
    return _unique_paths(entries)


def _manifest_path_entries(manifest: Mapping[str, Any]) -> list[Path]:
    raw_entries = manifest.get("pathEntries")
    if not isinstance(raw_entries, list):
        return []
    return [
        Path(str(raw_entry or "").strip())
        for raw_entry in raw_entries
        if str(raw_entry or "").strip()
    ]


def _manifest_resource_paths(manifest: Mapping[str, Any]) -> list[Path]:
    resources = manifest.get("resources")
    if not isinstance(resources, Mapping):
        return []
    paths: list[Path] = []
    for key in ("path", "bwrap"):
        raw_entry = str(resources.get(key) or "").strip()
        if raw_entry:
            paths.append(Path(raw_entry))
    return paths


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(path)
    return unique
