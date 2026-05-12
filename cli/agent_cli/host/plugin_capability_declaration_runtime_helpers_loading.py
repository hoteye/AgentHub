from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tomllib

from cli.agent_cli.host import plugin_capability_declaration_runtime_helpers_normalization as _normalization
from cli.agent_cli.host import plugin_capability_declaration_runtime_helpers_pure as _pure

_DECLARATION_FILE_CANDIDATES: tuple[str, ...] = (
    "capabilities.toml",
    "capabilities.json",
    ".agent_cli_legacy-plugin/capabilities.toml",
    ".agent_cli_legacy-plugin/capabilities.json",
)


def _read_json_payload(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_toml_payload(path: Path) -> Any:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _extract_capabilities_list(payload: Any) -> Any:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        capabilities = payload.get("capabilities")
        if isinstance(capabilities, list):
            return capabilities
    return None


def load_plugin_capability_declarations_impl(
    plugin_root: Path,
    *,
    strict: bool = False,
) -> Any:
    runtime = _pure.declaration_runtime()
    resolved_root = Path(plugin_root).expanduser()
    for relative_path in _DECLARATION_FILE_CANDIDATES:
        path = resolved_root / relative_path
        if not path.is_file():
            continue
        try:
            if path.suffix.lower() == ".toml":
                payload = _read_toml_payload(path)
            else:
                payload = _read_json_payload(path)
        except Exception as exc:
            if strict:
                raise ValueError(f"failed to parse capability declaration file `{path}`: {exc}") from exc
            return runtime.PluginCapabilityDeclarationLoadResult(
                declarations=(),
                errors=(f"failed to parse capability declaration file `{path}`: {exc}",),
                source_path=str(path),
            )
        normalized = _normalization.normalize_plugin_capability_declarations_impl(
            _extract_capabilities_list(payload),
            strict=strict,
        )
        return runtime.PluginCapabilityDeclarationLoadResult(
            declarations=normalized.declarations,
            errors=normalized.errors,
            source_path=str(path),
        )
    return runtime.PluginCapabilityDeclarationLoadResult(declarations=(), errors=(), source_path="")
