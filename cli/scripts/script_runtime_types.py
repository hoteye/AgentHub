from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScriptImportPaths:
    cli_root: Path
    repo_root: Path


@dataclass(frozen=True)
class CodexSourcePaths:
    home: Path
    config_path: Path
    auth_path: Path
    skills_dir: Path


@dataclass(frozen=True)
class ScriptProviderMaterialization:
    config_path: Path
    auth_path: Path
    agent_cli_home: Path
    provider_home: Path | None
    source_scope: str


@dataclass(frozen=True)
class ScriptProviderSelectionOverride:
    provider_name: str = ""
    model: str = ""
    reasoning_effort: str = ""


@dataclass(frozen=True)
class ScriptResolvedProviderSettings:
    provider_name: str
    model_key: str
    model: str
    reasoning_effort: str
    base_url: str
    config_path: Path
    auth_path: Path
    api_key: str
    source: str
