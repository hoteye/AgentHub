from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def plugin_namespace_for_skill_path(
    path: str | Path,
    *,
    read_reference_manifest_fn: Callable[[Path], Any],
    read_legacy_compat_manifest_metadata_fn: Callable[[Path], Any],
    safe_resolve_fn: Callable[[Path], Path],
) -> str | None:
    current = safe_resolve_fn(Path(path))
    for ancestor in [current, *current.parents]:
        manifest = read_reference_manifest_fn(ancestor)
        if manifest is not None:
            return str(manifest.get("name") or "").strip() or ancestor.name
        legacy = read_legacy_compat_manifest_metadata_fn(ancestor)
        if legacy is not None:
            return legacy.name
    return None


def plugin_name_for_source(
    source_path: Path,
    *,
    read_reference_manifest_fn: Callable[[Path], Any],
    read_legacy_compat_manifest_metadata_fn: Callable[[Path], Any],
    plugin_store_error_type: type[Exception],
) -> str:
    reference_manifest = read_reference_manifest_fn(source_path)
    if reference_manifest is not None:
        return str(reference_manifest.get("name") or "").strip() or source_path.name
    manifest = read_legacy_compat_manifest_metadata_fn(source_path)
    if manifest is not None:
        return manifest.name
    raise plugin_store_error_type(f"missing or invalid plugin manifest: {source_path}")
