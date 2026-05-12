from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from cli.agent_cli.memory_store_runtime import agent_cli_home, safe_resolve
from cli.agent_cli.providers.availability_projection import get_availability_registry
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry


_STATE_FILENAME = "provider_availability_state.json"
_STATE_PATH_ATTRS = (
    "_provider_availability_state_path",
    "provider_availability_state_path",
)


def provider_availability_state_path(*, base_dir: Path | None = None) -> Path:
    root = safe_resolve(Path(base_dir) if base_dir is not None else agent_cli_home())
    return root / _STATE_FILENAME


def load_persisted_availability_registry(*, path: Path | None = None) -> AvailabilityRegistry:
    resolved_path = Path(path) if path is not None else provider_availability_state_path()
    payload = _read_json_dict(resolved_path)
    return AvailabilityRegistry.from_payload(payload)


def persist_availability_registry(
    registry: AvailabilityRegistry,
    *,
    path: Path | None = None,
) -> Path:
    resolved_path = Path(path) if path is not None else provider_availability_state_path()
    _write_json_atomic(resolved_path, registry.to_payload())
    return resolved_path


def persist_availability_registry_for_owner(owner: Any) -> bool:
    registry = get_availability_registry(owner)
    if not isinstance(registry, AvailabilityRegistry):
        return False
    resolved_path = _state_path_from_owner(owner)
    if resolved_path is None:
        return False
    try:
        persist_availability_registry(registry, path=resolved_path)
    except Exception:
        return False
    return True


def _state_path_from_owner(owner: Any) -> Path | None:
    for attr_name in _STATE_PATH_ATTRS:
        value = getattr(owner, attr_name, None)
        if value in (None, ""):
            continue
        return Path(value)
    return None


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


__all__ = [
    "load_persisted_availability_registry",
    "persist_availability_registry",
    "persist_availability_registry_for_owner",
    "provider_availability_state_path",
]
