from __future__ import annotations

from collections.abc import Mapping


def _required_text(mapping: Mapping[str, object], key: str) -> str:
    value = _optional_text(mapping, key)
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_text(mapping: Mapping[str, object], key: str) -> str | None:
    value = mapping.get(key)
    text = str(value or "").strip()
    return text or None


def _optional_int(mapping: Mapping[str, object], key: str) -> int | None:
    value = mapping.get(key)
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(mapping: Mapping[str, object], key: str) -> bool | None:
    value = mapping.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")


def _optional_list(mapping: Mapping[str, object], key: str) -> list[str] | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return [str(item) for item in value]


def _optional_dict_list(mapping: Mapping[str, object], key: str) -> list[dict[str, object]] | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be a list of objects")
    return [dict(item) for item in value]


def _required_dict_list(mapping: Mapping[str, object], key: str) -> list[dict[str, object]]:
    value = _optional_dict_list(mapping, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _required_text_list(mapping: Mapping[str, object], key: str) -> list[str]:
    value = _optional_list(mapping, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _required_dict(mapping: Mapping[str, object], key: str) -> dict[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return dict(value)
