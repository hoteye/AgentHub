from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from cli.agent_cli.host.plugin_store_runtime import DEFAULT_MARKETPLACE_NAME


_VALID_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_VALID_SCOPES = {"project", "user"}
_SOURCE_METADATA_RESERVED_KEYS = {"source_type", "last_checked", "cache_path"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_token(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if not _VALID_TOKEN_RE.fullmatch(normalized):
        raise ValueError(f"invalid {field_name}: {normalized}")
    return normalized


def _infer_source_type(source: str) -> str:
    source_path = Path(str(source or "").strip()).expanduser()
    source_suffix = source_path.suffix.lower()
    if source_path.exists():
        if source_path.is_dir():
            return "directory"
        if source_suffix == ".zip":
            return "zip"
        if source_path.is_file():
            return "file"
    if source_suffix == ".zip":
        return "zip"
    if source_suffix:
        return "file"
    return "path"


def _resolved_cache_path(source: str) -> str:
    source_path = Path(str(source or "").strip()).expanduser()
    try:
        resolved = source_path.resolve()
    except OSError:
        resolved = source_path
    return str(resolved)


def _split_source_metadata(value: Any) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    if not isinstance(value, dict):
        return (None, None, None, {})
    source_type = str(value.get("source_type") or "").strip() or None
    last_checked = str(value.get("last_checked") or "").strip() or None
    cache_path = str(value.get("cache_path") or "").strip() or None
    extras: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key or "").strip()
        if not normalized_key or normalized_key in _SOURCE_METADATA_RESERVED_KEYS:
            continue
        extras[normalized_key] = item
    return (source_type, last_checked, cache_path, extras)


def _build_source_metadata(
    source: str,
    *,
    last_checked: str,
    source_type: str | None = None,
    cache_path: str | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_type": str(source_type or "").strip() or _infer_source_type(source),
        "last_checked": str(last_checked or "").strip() or _now_iso(),
        "cache_path": str(cache_path or "").strip() or _resolved_cache_path(source),
    }
    for key, item in dict(extras or {}).items():
        normalized_key = str(key or "").strip()
        if not normalized_key or normalized_key in _SOURCE_METADATA_RESERVED_KEYS:
            continue
        payload[normalized_key] = item
    return payload


def parse_plugin_key(plugin_key: str, *, default_marketplace: str = DEFAULT_MARKETPLACE_NAME) -> tuple[str, str]:
    normalized = str(plugin_key or "").strip()
    if not normalized:
        raise ValueError("plugin key is required")
    if "@" in normalized:
        plugin_name, marketplace_name = normalized.rsplit("@", 1)
    else:
        plugin_name, marketplace_name = normalized, default_marketplace
    return (
        _validate_token(plugin_name, field_name="plugin name"),
        _validate_token(marketplace_name, field_name="marketplace name"),
    )


@dataclass(frozen=True, slots=True)
class PluginMarketplaceEntry:
    plugin_name: str
    marketplace_name: str
    source: str
    scope: str = "project"
    metadata: dict[str, Any] = field(default_factory=dict)
    source_metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now_iso)

    @property
    def plugin_key(self) -> str:
        return f"{self.plugin_name}@{self.marketplace_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name,
            "marketplace_name": self.marketplace_name,
            "source": self.source,
            "scope": self.scope,
            "metadata": dict(self.metadata or {}),
            "source_metadata": dict(self.source_metadata or {}),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PluginMarketplaceEntry":
        plugin_name = _validate_token(payload.get("plugin_name"), field_name="plugin name")
        marketplace_name = _validate_token(payload.get("marketplace_name"), field_name="marketplace name")
        source = str(payload.get("source") or "").strip()
        if not source:
            raise ValueError("source is required")
        scope = str(payload.get("scope") or "project").strip().lower()
        if scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope: {scope}")
        metadata_value = payload.get("metadata")
        metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
        updated_at = str(payload.get("updated_at") or "").strip() or _now_iso()
        source_type, last_checked, cache_path, source_metadata_extras = _split_source_metadata(
            payload.get("source_metadata")
        )
        return cls(
            plugin_name=plugin_name,
            marketplace_name=marketplace_name,
            source=source,
            scope=scope,
            metadata=metadata,
            source_metadata=_build_source_metadata(
                source,
                last_checked=last_checked or updated_at,
                source_type=source_type,
                cache_path=cache_path,
                extras=source_metadata_extras,
            ),
            updated_at=updated_at,
        )


class PluginMarketplaceStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve()

    @classmethod
    def from_reference_home(cls, reference_home: Path, *, filename: str = "plugin_marketplace.json") -> "PluginMarketplaceStore":
        return cls(Path(reference_home).expanduser().resolve() / filename)

    def list_entries(self, *, marketplace_name: str | None = None) -> list[PluginMarketplaceEntry]:
        entries = self._read_entries()
        if marketplace_name is None:
            return entries
        normalized_marketplace = _validate_token(marketplace_name, field_name="marketplace name")
        return [item for item in entries if item.marketplace_name == normalized_marketplace]

    def get_entry(self, plugin_key: str) -> PluginMarketplaceEntry | None:
        plugin_name, marketplace_name = parse_plugin_key(plugin_key)
        for entry in self._read_entries():
            if entry.plugin_name == plugin_name and entry.marketplace_name == marketplace_name:
                return entry
        return None

    def add_entry(
        self,
        plugin_key: str,
        *,
        source: str,
        scope: str = "project",
        metadata: dict[str, Any] | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> PluginMarketplaceEntry:
        plugin_name, marketplace_name = parse_plugin_key(plugin_key)
        if self.get_entry(f"{plugin_name}@{marketplace_name}") is not None:
            raise ValueError(f"plugin marketplace entry already exists: {plugin_name}@{marketplace_name}")
        entry = self._build_entry(
            plugin_name=plugin_name,
            marketplace_name=marketplace_name,
            source=source,
            scope=scope,
            metadata=metadata,
            source_metadata=source_metadata,
        )
        entries = self._read_entries()
        entries.append(entry)
        self._write_entries(entries)
        return entry

    def update_entry(
        self,
        plugin_key: str,
        *,
        source: str | None = None,
        scope: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> PluginMarketplaceEntry:
        plugin_name, marketplace_name = parse_plugin_key(plugin_key)
        entries = self._read_entries()
        updated: PluginMarketplaceEntry | None = None
        next_entries: list[PluginMarketplaceEntry] = []
        for entry in entries:
            if entry.plugin_name == plugin_name and entry.marketplace_name == marketplace_name:
                default_source_metadata = dict(entry.source_metadata or {})
                if source is not None and source_metadata is None:
                    for key in _SOURCE_METADATA_RESERVED_KEYS:
                        default_source_metadata.pop(key, None)
                updated = self._build_entry(
                    plugin_name=plugin_name,
                    marketplace_name=marketplace_name,
                    source=source if source is not None else entry.source,
                    scope=scope if scope is not None else entry.scope,
                    metadata=metadata if metadata is not None else dict(entry.metadata or {}),
                    source_metadata=(
                        source_metadata
                        if source_metadata is not None
                        else default_source_metadata
                    ),
                )
                next_entries.append(updated)
            else:
                next_entries.append(entry)
        if updated is None:
            raise ValueError(f"plugin marketplace entry not found: {plugin_name}@{marketplace_name}")
        self._write_entries(next_entries)
        return updated

    def remove_entry(self, plugin_key: str) -> PluginMarketplaceEntry | None:
        plugin_name, marketplace_name = parse_plugin_key(plugin_key)
        entries = self._read_entries()
        removed: PluginMarketplaceEntry | None = None
        next_entries: list[PluginMarketplaceEntry] = []
        for entry in entries:
            if removed is None and entry.plugin_name == plugin_name and entry.marketplace_name == marketplace_name:
                removed = entry
                continue
            next_entries.append(entry)
        if removed is None:
            return None
        self._write_entries(next_entries)
        return removed

    def resolve_source(self, plugin_key: str, *, cwd: str | Path | None = None) -> Path:
        entry = self.get_entry(plugin_key)
        if entry is None:
            raise ValueError(f"plugin marketplace entry not found: {plugin_key}")
        source = Path(entry.source).expanduser()
        if not source.is_absolute():
            base = Path(cwd) if cwd is not None else Path.cwd()
            source = base.expanduser() / source
        resolved = source.resolve()
        if not resolved.exists():
            raise ValueError(f"plugin source does not exist: {resolved}")
        return resolved

    def _read_entries(self) -> list[PluginMarketplaceEntry]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"failed to load plugin marketplace store: {self.path} ({exc})") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"invalid plugin marketplace store payload: {self.path}")
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError(f"invalid plugin marketplace entries payload: {self.path}")
        entries: list[PluginMarketplaceEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            entries.append(PluginMarketplaceEntry.from_dict(raw))
        return entries

    def _write_entries(self, entries: list[PluginMarketplaceEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": [
                entry.to_dict()
                for entry in sorted(entries, key=lambda item: (item.marketplace_name, item.plugin_name))
            ],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _build_entry(
        *,
        plugin_name: str,
        marketplace_name: str,
        source: str,
        scope: str,
        metadata: dict[str, Any] | None,
        source_metadata: dict[str, Any] | None,
    ) -> PluginMarketplaceEntry:
        source_text = str(source or "").strip()
        if not source_text:
            raise ValueError("source is required")
        normalized_scope = str(scope or "project").strip().lower()
        if normalized_scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope: {normalized_scope}")
        updated_at = _now_iso()
        source_type, _last_checked, cache_path, source_metadata_extras = _split_source_metadata(source_metadata)
        return PluginMarketplaceEntry(
            plugin_name=plugin_name,
            marketplace_name=marketplace_name,
            source=source_text,
            scope=normalized_scope,
            metadata=dict(metadata or {}),
            source_metadata=_build_source_metadata(
                source_text,
                last_checked=updated_at,
                source_type=source_type,
                cache_path=cache_path,
                extras=source_metadata_extras,
            ),
            updated_at=updated_at,
        )
