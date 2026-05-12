from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from cli.agent_cli.providers.interaction_profile_models import (
    InteractionProfileLoadError,
    InteractionProfileSpec,
    interaction_profile_spec_from_mapping,
)

_DEFAULT_PROFILE_NAMES: tuple[str, ...] = (
    "codex_openai",
    "claude_code",
    "generic_chat",
)


def interaction_profile_root() -> Path:
    return Path(__file__).resolve().parent / "interaction_profiles"


def interaction_profile_schema_path(*, profile_root: Path | None = None) -> Path:
    root = Path(profile_root) if profile_root is not None else interaction_profile_root()
    return root / "schema" / "interaction_profile.schema.json"


def load_interaction_profile_schema(*, profile_root: Path | None = None) -> dict[str, Any]:
    path = interaction_profile_schema_path(profile_root=profile_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InteractionProfileLoadError(f"missing interaction profile schema: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InteractionProfileLoadError(f"invalid interaction profile schema JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise InteractionProfileLoadError(f"interaction profile schema must be an object: {path}")
    return payload


def _profile_filenames(profile_filenames: tuple[str, ...] | None) -> tuple[str, ...]:
    if profile_filenames:
        return tuple(profile_filenames)
    return tuple(f"{name}.toml" for name in _DEFAULT_PROFILE_NAMES)


def load_interaction_profiles(
    *,
    profile_root: Path | None = None,
    profile_filenames: tuple[str, ...] | None = None,
) -> dict[str, InteractionProfileSpec]:
    root = Path(profile_root) if profile_root is not None else interaction_profile_root()
    # Force schema load to enforce hard-error behavior if bundled schema is missing/corrupt.
    load_interaction_profile_schema(profile_root=root)

    specs: dict[str, InteractionProfileSpec] = {}
    for filename in _profile_filenames(profile_filenames):
        path = root / filename
        try:
            raw_payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise InteractionProfileLoadError(f"missing interaction profile TOML: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise InteractionProfileLoadError(f"invalid interaction profile TOML: {path}") from exc
        if not isinstance(raw_payload, dict):
            raise InteractionProfileLoadError(f"interaction profile TOML root must be a table: {path}")

        spec = interaction_profile_spec_from_mapping(raw_payload, source=str(path))
        if spec.profile in specs:
            raise InteractionProfileLoadError(f"duplicate interaction profile `{spec.profile}` from {path}")
        specs[spec.profile] = spec
    return specs


def load_bundled_interaction_profiles() -> dict[str, InteractionProfileSpec]:
    return load_interaction_profiles()


def bundled_interaction_profile_names() -> tuple[str, ...]:
    return _DEFAULT_PROFILE_NAMES


def load_bundled_interaction_profile(profile: str) -> InteractionProfileSpec:
    normalized = str(profile or "").strip()
    if not normalized:
        raise InteractionProfileLoadError("interaction profile name must not be empty")
    all_specs = load_bundled_interaction_profiles()
    item = all_specs.get(normalized)
    if item is None:
        raise InteractionProfileLoadError(f"unknown interaction profile `{normalized}`")
    return item

