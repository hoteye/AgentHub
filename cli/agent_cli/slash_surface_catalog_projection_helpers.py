from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence


def project_surface_usage(entries: Mapping[str, str]) -> dict[str, str]:
    return {str(command_name): str(usage_text) for command_name, usage_text in entries.items()}


def project_keyword_map(entries: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, str]]:
    projected: dict[str, dict[str, str]] = {}
    for command_name, keyword_entries in entries.items():
        projected[str(command_name)] = {
            str(keyword_name): str(surface_name)
            for keyword_name, surface_name in keyword_entries.items()
        }
    return projected


def project_option_value_map(
    entries: Mapping[tuple[str, str], Sequence[str]]
) -> dict[tuple[str, str], tuple[str, ...]]:
    projected: dict[tuple[str, str], tuple[str, ...]] = {}
    for (command_name, keyword_name), values in entries.items():
        projected[(str(command_name), str(keyword_name))] = tuple(str(value) for value in values)
    return projected


def project_implicit_enum_map(
    entries: Mapping[str, Mapping[str, tuple[str, str | None]]]
) -> dict[str, dict[str, tuple[str, str | None]]]:
    projected: dict[str, dict[str, tuple[str, str | None]]] = {}
    for command_name, implicit_entries in entries.items():
        projected[str(command_name)] = {
            str(token): (str(keyword_name), None if value is None else str(value))
            for token, (keyword_name, value) in implicit_entries.items()
        }
    return projected


def project_command_name_set(command_names: Iterable[str]) -> frozenset[str]:
    return frozenset(str(command_name) for command_name in command_names)
