from __future__ import annotations

from typing import Any, Iterable, Mapping


class SchemaValidationError(ValueError):
    """Raised when lightweight schema validation fails."""


def ensure_mapping(value: Any, *, field_name: str = "value") -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    raise SchemaValidationError(f"{field_name} must be a mapping")


def coerce_str_mapping(value: Any, *, field_name: str = "value") -> dict[str, str]:
    mapping = ensure_mapping(value, field_name=field_name)
    return {str(key): str(item) for key, item in mapping.items()}


def require_keys(
    value: Any,
    required_keys: Iterable[str],
    *,
    field_name: str = "value",
) -> dict[str, Any]:
    mapping = ensure_mapping(value, field_name=field_name)
    missing = [str(key) for key in required_keys if str(key) not in mapping]
    if missing:
        raise SchemaValidationError(f"{field_name} missing required keys: {', '.join(missing)}")
    return mapping


def pick_keys(value: Any, allowed_keys: Iterable[str], *, field_name: str = "value") -> dict[str, Any]:
    mapping = ensure_mapping(value, field_name=field_name)
    allowed = {str(key) for key in allowed_keys}
    return {key: item for key, item in mapping.items() if key in allowed}
