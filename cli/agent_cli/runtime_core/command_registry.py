from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from os.path import commonprefix
from typing import Any

from cli.agent_cli.slash_parser import split_slash_like_tokens


@dataclass(frozen=True, slots=True)
class CommandAvailability:
    # blocked: unavailable while busy
    # allowed: available while busy
    # read_only: available while busy only for read-only forms
    busy_mode: str = "blocked"


@dataclass(frozen=True, slots=True)
class CommandRegistryEntry:
    name: str
    usage: str
    description: str
    source: str
    description_key: str = ""
    availability: CommandAvailability = CommandAvailability()


def _normalize_source(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"builtin", "plugin", "workflow"}:
        return normalized
    return "plugin"


def parse_command_tokens(text_or_name: str) -> tuple[str, ...]:
    return split_slash_like_tokens(text_or_name)


def command_name_from_text(text_or_name: str) -> str | None:
    tokens = parse_command_tokens(text_or_name)
    if not tokens:
        return None
    return str(tokens[0]).strip().lower().lstrip("/") or None


def build_command_registry(
    *,
    builtin_specs: Sequence[Any],
    plugin_specs: Sequence[Mapping[str, Any]],
    builtin_busy_availability: Mapping[str, CommandAvailability],
) -> list[CommandRegistryEntry]:
    entries: list[CommandRegistryEntry] = []
    for spec in builtin_specs:
        name = str(getattr(spec, "name", "") or "").strip().lower()
        if not name:
            continue
        entries.append(
            CommandRegistryEntry(
                name=name,
                usage=str(getattr(spec, "usage", "") or ""),
                description=str(getattr(spec, "description", "") or ""),
                source="builtin",
                description_key=str(getattr(spec, "description_key", "") or ""),
                availability=builtin_busy_availability.get(name, CommandAvailability()),
            )
        )
    for item in plugin_specs:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip().lower()
        if not name:
            continue
        entries.append(
            CommandRegistryEntry(
                name=name,
                usage=str(item.get("usage") or ""),
                description=str(item.get("description") or ""),
                source=_normalize_source(str(item.get("source") or "plugin")),
                description_key=str(item.get("description_key") or ""),
                availability=CommandAvailability(),
            )
        )
    return entries


def command_registry_rows(entries: Sequence[CommandRegistryEntry]) -> list[dict[str, str]]:
    return [
        {
            "name": entry.name,
            "usage": entry.usage,
            "description": entry.description,
            "description_key": entry.description_key,
            "source": entry.source,
            "busy_mode": entry.availability.busy_mode,
        }
        for entry in entries
    ]


def command_help_text(
    entries: Sequence[CommandRegistryEntry],
    *,
    heading: str = "available commands:",
) -> str:
    lines = [heading]
    for entry in entries:
        usage = str(entry.usage or "").strip()
        description = str(entry.description or "").strip()
        if usage and description:
            lines.append(f"{usage} - {description}")
        elif usage:
            lines.append(usage)
    return "\n".join(lines)


def match_command_registry(
    prefix: str, entries: Sequence[CommandRegistryEntry]
) -> list[CommandRegistryEntry]:
    token = str(prefix or "").strip().lower().lstrip("/")
    if not token:
        return list(entries)
    startswith_matches = [entry for entry in entries if entry.name.startswith(token)]
    if startswith_matches:
        return startswith_matches
    return [entry for entry in entries if token in entry.name]


def autocomplete_command_registry(
    prefix: str, entries: Sequence[CommandRegistryEntry]
) -> str | None:
    token = str(prefix or "").strip().lower().lstrip("/")
    matches = match_command_registry(token, entries)
    if not matches:
        return None
    if len(matches) == 1:
        return f"/{matches[0].name} "
    names = [entry.name for entry in matches]
    shared_prefix = commonprefix(names)
    if shared_prefix and len(shared_prefix) > len(token):
        return f"/{shared_prefix}"
    if any(name == token for name in names):
        return f"/{token} "
    return None


def _registry_entry_by_name(
    command_name: str,
    entries: Sequence[CommandRegistryEntry],
) -> CommandRegistryEntry | None:
    normalized = str(command_name or "").strip().lower().lstrip("/")
    if not normalized:
        return None
    for entry in entries:
        if entry.name == normalized:
            return entry
    return None


def command_available_during_busy(
    text_or_name: str,
    entries: Sequence[CommandRegistryEntry],
) -> bool:
    tokens = parse_command_tokens(text_or_name)
    if not tokens:
        return False
    command_name = command_name_from_text(tokens[0])
    if command_name is None:
        return False
    entry = _registry_entry_by_name(command_name, entries)
    if entry is None:
        return False
    busy_mode = str(entry.availability.busy_mode or "").strip().lower()
    if busy_mode == "allowed":
        return True
    if busy_mode != "read_only":
        return False
    if entry.name != "provider":
        return True
    # Allow read-only provider inspect forms during busy.
    if len(tokens) == 1:
        return True
    return len(tokens) == 2 and str(tokens[1]).strip() in {"verbose", "--verbose", "-v"}
