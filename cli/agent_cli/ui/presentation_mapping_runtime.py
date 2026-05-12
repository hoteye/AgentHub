from __future__ import annotations

from pathlib import Path
from typing import Mapping


def message_text(
    *,
    messages: Mapping[str, Mapping[str, str]],
    key: str,
    locale: str,
    default_locale: str,
    kwargs: Mapping[str, object],
) -> str:
    localized = messages.get(str(key), {})
    template = localized.get(locale) or localized.get(default_locale) or str(key)
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def presentation_home_candidates(*, agent_cli_home: Path, legacy_compat_home: Path) -> list[Path]:
    return [agent_cli_home / "config.toml", legacy_compat_home / "config.toml"]


def presentation_config(
    cwd: str | Path | None,
    *,
    presentation_home_candidates_fn,
    presentation_project_paths_fn,
    read_toml_mapping_fn,
    merge_nested_mappings_fn,
) -> dict[str, object]:
    merged: dict[str, object] = {}
    for candidate in presentation_home_candidates_fn():
        if candidate.exists():
            merged = merge_nested_mappings_fn(merged, read_toml_mapping_fn(candidate))
            break
    for candidate in presentation_project_paths_fn(cwd):
        merged = merge_nested_mappings_fn(merged, read_toml_mapping_fn(candidate))
    return merged
