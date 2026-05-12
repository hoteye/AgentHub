from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, List


_PLUGIN_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+@[A-Za-z0-9_-]+$")
_VALID_SCOPES = {"user", "project", "local", "managed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_plugin_key(plugin_key: str) -> str:
    normalized = str(plugin_key or "").strip()
    if not _PLUGIN_KEY_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid plugin key `{normalized}`; expected <plugin>@<marketplace>")
    return normalized


def _normalize_scope(scope: str | None) -> str:
    normalized = str(scope or "user").strip().lower() or "user"
    if normalized not in _VALID_SCOPES:
        raise ValueError(f"invalid plugin scope: {normalized}")
    return normalized


@dataclass(frozen=True, slots=True)
class PluginInstallationEntry:
    scope: str
    install_path: str
    version: str = "local"
    source_kind: str = "dir"
    installed_at: str = field(default_factory=_now_iso)
    last_updated: str = field(default_factory=_now_iso)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PluginInstallationEntry":
        scope = _normalize_scope(str(payload.get("scope") or "user"))
        install_path = str(payload.get("installPath") or payload.get("install_path") or "").strip()
        if not install_path:
            raise ValueError("install path is required")
        version = str(payload.get("version") or "local").strip() or "local"
        source_kind = str(payload.get("sourceKind") or payload.get("source_kind") or "dir").strip() or "dir"
        installed_at = str(payload.get("installedAt") or payload.get("installed_at") or "").strip() or _now_iso()
        last_updated = str(payload.get("lastUpdated") or payload.get("last_updated") or "").strip() or installed_at
        return cls(
            scope=scope,
            install_path=install_path,
            version=version,
            source_kind=source_kind,
            installed_at=installed_at,
            last_updated=last_updated,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "installPath": self.install_path,
            "version": self.version,
            "sourceKind": self.source_kind,
            "installedAt": self.installed_at,
            "lastUpdated": self.last_updated,
        }


class PluginInstallationStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve()

    @classmethod
    def from_reference_home(
        cls,
        reference_home: Path,
        *,
        relative_file: str = "plugins/installed_plugins.json",
    ) -> "PluginInstallationStore":
        return cls(Path(reference_home).expanduser().resolve() / relative_file)

    def list_installations(self, plugin_key: str | None = None) -> Dict[str, List[PluginInstallationEntry]]:
        all_items = self._read()
        if plugin_key is None:
            return all_items
        normalized_key = _normalize_plugin_key(plugin_key)
        return {normalized_key: list(all_items.get(normalized_key, []))}

    def has_installation(self, plugin_key: str, *, scope: str | None = None) -> bool:
        normalized_key = _normalize_plugin_key(plugin_key)
        items = self._read().get(normalized_key, [])
        if scope is None:
            return bool(items)
        normalized_scope = _normalize_scope(scope)
        return any(item.scope == normalized_scope for item in items)

    def upsert_installation(
        self,
        plugin_key: str,
        *,
        scope: str,
        install_path: str,
        version: str = "local",
        source_kind: str = "dir",
    ) -> PluginInstallationEntry:
        normalized_key = _normalize_plugin_key(plugin_key)
        normalized_scope = _normalize_scope(scope)
        normalized_path = str(install_path or "").strip()
        if not normalized_path:
            raise ValueError("install path is required")
        now = _now_iso()
        normalized_version = str(version or "").strip() or "local"
        normalized_source_kind = str(source_kind or "").strip() or "dir"
        state = self._read()
        entries = list(state.get(normalized_key, []))
        next_entries: List[PluginInstallationEntry] = []
        updated = False
        result_entry: PluginInstallationEntry | None = None
        for entry in entries:
            if entry.scope == normalized_scope:
                result_entry = PluginInstallationEntry(
                    scope=normalized_scope,
                    install_path=normalized_path,
                    version=normalized_version,
                    source_kind=normalized_source_kind,
                    installed_at=entry.installed_at,
                    last_updated=now,
                )
                next_entries.append(result_entry)
                updated = True
                continue
            next_entries.append(entry)
        if not updated:
            result_entry = PluginInstallationEntry(
                scope=normalized_scope,
                install_path=normalized_path,
                version=normalized_version,
                source_kind=normalized_source_kind,
                installed_at=now,
                last_updated=now,
            )
            next_entries.append(result_entry)
        state[normalized_key] = sorted(next_entries, key=lambda item: item.scope)
        self._write(state)
        assert result_entry is not None
        return result_entry

    def remove_installations(
        self,
        plugin_key: str,
        *,
        scope: str | None = None,
    ) -> List[PluginInstallationEntry]:
        normalized_key = _normalize_plugin_key(plugin_key)
        state = self._read()
        entries = list(state.get(normalized_key, []))
        if not entries:
            return []
        if scope is None:
            state.pop(normalized_key, None)
            self._write(state)
            return entries
        normalized_scope = _normalize_scope(scope)
        kept: List[PluginInstallationEntry] = []
        removed: List[PluginInstallationEntry] = []
        for item in entries:
            if item.scope == normalized_scope:
                removed.append(item)
            else:
                kept.append(item)
        if kept:
            state[normalized_key] = kept
        else:
            state.pop(normalized_key, None)
        self._write(state)
        return removed

    def _read(self) -> Dict[str, List[PluginInstallationEntry]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        raw_plugins = payload.get("plugins")
        if not isinstance(raw_plugins, dict):
            return {}
        result: Dict[str, List[PluginInstallationEntry]] = {}
        for key, raw_entries in raw_plugins.items():
            try:
                normalized_key = _normalize_plugin_key(str(key or ""))
            except ValueError:
                continue
            if not isinstance(raw_entries, list):
                continue
            parsed_entries: List[PluginInstallationEntry] = []
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict):
                    continue
                try:
                    parsed_entries.append(PluginInstallationEntry.from_dict(raw_entry))
                except ValueError:
                    continue
            if parsed_entries:
                result[normalized_key] = sorted(parsed_entries, key=lambda item: item.scope)
        return result

    def _write(self, state: Dict[str, List[PluginInstallationEntry]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "plugins": {
                key: [entry.to_dict() for entry in entries]
                for key, entries in sorted(state.items(), key=lambda item: item[0])
            },
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = [
    "PluginInstallationEntry",
    "PluginInstallationStore",
]
