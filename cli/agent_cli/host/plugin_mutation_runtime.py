from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict

from cli.agent_cli.host.plugin_installation_state import PluginInstallationStore


_VALID_SCOPES = {"user", "project", "local", "managed"}


def _normalize_scope(scope: str | None) -> str:
    normalized = str(scope or "user").strip().lower() or "user"
    if normalized not in _VALID_SCOPES:
        raise ValueError(f"invalid plugin scope: {normalized}")
    return normalized


def _installation_store(manager: Any) -> PluginInstallationStore | None:
    store = getattr(manager, "installation_store", None)
    if isinstance(store, PluginInstallationStore):
        return store
    return None


def _record_installation(
    manager: Any,
    *,
    plugin_key: str,
    scope: str,
    installed_path: str,
    version: str,
    source_kind: str,
) -> None:
    store = _installation_store(manager)
    if store is None:
        return
    store.upsert_installation(
        plugin_key,
        scope=scope,
        install_path=installed_path,
        version=version,
        source_kind=source_kind,
    )


def _remove_installations(manager: Any, *, plugin_key: str) -> int:
    store = _installation_store(manager)
    if store is None:
        return 0
    removed = store.remove_installations(plugin_key)
    return len(removed)


def write_plugin_enabled_config(*, config_path: Path, plugin_key: str, enabled: bool) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    section_header = f'[plugins."{plugin_key}"]'
    block_pattern = re.compile(
        rf"(?ms)^(?P<header>\[plugins\.\"{re.escape(plugin_key)}\"\][ \t]*\n)(?P<body>.*?)(?=^\[|\Z)"
    )
    replacement_line = f"enabled = {'true' if enabled else 'false'}\n"
    match = block_pattern.search(existing)
    if match is None:
        prefix = existing.rstrip()
        if prefix:
            prefix += "\n\n"
        updated = prefix + section_header + "\n" + replacement_line
        config_path.write_text(updated, encoding="utf-8")
        return
    body = match.group("body")
    if re.search(r"(?m)^enabled\s*=", body):
        body = re.sub(r"(?m)^enabled\s*=.*$", replacement_line.rstrip(), body, count=1)
        body = body.rstrip() + "\n"
    else:
        body = body.rstrip()
        body = (body + "\n" if body else "") + replacement_line
    updated = existing[: match.start()] + match.group("header") + body + existing[match.end() :]
    config_path.write_text(updated, encoding="utf-8")


def remove_plugin_config_section(*, config_path: Path, plugin_key: str) -> None:
    if not config_path.exists():
        return
    existing = config_path.read_text(encoding="utf-8")
    updated = re.sub(
        rf"(?ms)\n?\[plugins\.\"{re.escape(plugin_key)}\"\][ \t]*\n.*?(?=^\[|\Z)",
        "",
        existing,
    ).strip()
    if updated:
        updated += "\n"
        config_path.write_text(updated, encoding="utf-8")
    else:
        config_path.unlink(missing_ok=True)


def install_plugin(
    manager: Any,
    source_path: str,
    *,
    replace: bool = False,
    marketplace_name: str | None = None,
    scope: str | None = None,
) -> Dict[str, Any]:
    staging_dir, candidate_dir, source_kind, error = manager._extract_source_dir(source_path)
    try:
        if error:
            return error
        assert candidate_dir is not None
        try:
            normalized_scope = _normalize_scope(scope)
        except ValueError as exc:
            return {"ok": False, "reason": "invalid_scope", "scope": str(scope or ""), "error": str(exc)}
        if manager._compat_mode:
            plugin_name = candidate_dir.name
            target_dir = manager.plugin_root / plugin_name
            target_exists = target_dir.exists()
            if target_exists and not bool(replace):
                return {
                    "ok": False,
                    "reason": "plugin_exists",
                    "plugin_name": plugin_name,
                    "path": str(target_dir),
                }
            manager.plugin_root.mkdir(parents=True, exist_ok=True)
            if target_exists:
                shutil.rmtree(target_dir)
            shutil.copytree(candidate_dir, target_dir)
            manager.reload()
            enabled_map = manager._load_state()
            if plugin_name not in enabled_map:
                plugin_item = next((item for item in manager._plugins if item.plugin_name == plugin_name), None)
                if plugin_item is not None:
                    enabled_map[plugin_name] = bool(plugin_item.manifest.enabled_by_default)
                    manager._save_state(enabled_map)
                    manager.reload()
            return {
                "ok": True,
                "plugin_name": plugin_name,
                "installed_path": str(target_dir),
                "replaced": bool(target_exists),
                "source_kind": source_kind,
                "scope": normalized_scope,
            }
        try:
            installed = manager.store.install(
                candidate_dir,
                marketplace_name=marketplace_name,
                replace=bool(replace),
            )
        except Exception as exc:
            if "already installed" in str(exc).lower():
                return {
                    "ok": False,
                    "reason": "plugin_exists",
                    "path": str(source_path),
                    "replace": bool(replace),
                }
            raise
        plugin_id = installed["plugin_id"]
        plugin_key = plugin_id.as_key()
        write_plugin_enabled_config(config_path=manager.config_path, plugin_key=plugin_key, enabled=True)
        _record_installation(
            manager,
            plugin_key=plugin_key,
            scope=normalized_scope,
            installed_path=str(installed["installed_path"]),
            version=str(installed["plugin_version"]),
            source_kind=source_kind,
        )
        manager.reload()
        return {
            "ok": True,
            "plugin_name": plugin_id.plugin_name,
            "plugin_id": plugin_key,
            "installed_path": str(installed["installed_path"]),
            "plugin_version": installed["plugin_version"],
            "source_kind": source_kind,
            "replaced": bool(installed.get("replaced")),
            "scope": normalized_scope,
        }
    finally:
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def remove_plugin(manager: Any, plugin_name: str) -> Dict[str, Any]:
    requested = str(plugin_name or "").strip()
    if not requested:
        return {"ok": False, "reason": "plugin_name_required"}
    if manager._compat_mode:
        target_dir = manager.plugin_root / requested
        if not target_dir.exists():
            return {"ok": False, "reason": "plugin_not_found", "plugin_name": requested}
        shutil.rmtree(target_dir, ignore_errors=False)
        enabled_map = manager._load_state()
        if requested in enabled_map:
            enabled_map.pop(requested, None)
            manager._save_state(enabled_map)
        manager.reload()
        return {"ok": True, "plugin_name": requested, "removed_path": str(target_dir)}
    plugin = manager._resolve_plugin(requested)
    if plugin is None:
        return {"ok": False, "reason": "plugin_not_found", "plugin_name": requested}
    if not plugin.installed:
        return {"ok": False, "reason": "plugin_not_removable", "plugin_name": requested}
    if plugin.root.exists():
        shutil.rmtree(plugin.root, ignore_errors=False)
    if plugin.config_name:
        remove_plugin_config_section(config_path=manager.config_path, plugin_key=plugin.config_name)
        removed_count = _remove_installations(manager, plugin_key=plugin.config_name)
    else:
        removed_count = 0
    manager.reload()
    return {
        "ok": True,
        "plugin_name": plugin.plugin_name,
        "removed_path": str(plugin.root),
        "removed_installations": removed_count,
    }


def enable_plugin(manager: Any, plugin_name: str) -> Dict[str, Any]:
    requested = str(plugin_name or "").strip()
    plugin = manager._resolve_plugin(requested)
    if plugin is None:
        return {"ok": False, "reason": "plugin_not_found", "plugin_name": requested}
    if manager._compat_mode:
        enabled_map = manager._load_state()
        enabled_map[plugin.plugin_name] = True
        manager._save_state(enabled_map)
    else:
        write_plugin_enabled_config(
            config_path=manager.config_path,
            plugin_key=plugin.config_name or manager._bundled_plugin_key(plugin.plugin_name),
            enabled=True,
        )
    manager.reload()
    return {"ok": True, "plugin_name": plugin.plugin_name, "enabled": True, "plugins": manager.list_plugins()}


def disable_plugin(manager: Any, plugin_name: str) -> Dict[str, Any]:
    requested = str(plugin_name or "").strip()
    plugin = manager._resolve_plugin(requested)
    if plugin is None:
        return {"ok": False, "reason": "plugin_not_found", "plugin_name": requested}
    if manager._compat_mode:
        enabled_map = manager._load_state()
        enabled_map[plugin.plugin_name] = False
        manager._save_state(enabled_map)
    else:
        write_plugin_enabled_config(
            config_path=manager.config_path,
            plugin_key=plugin.config_name or manager._bundled_plugin_key(plugin.plugin_name),
            enabled=False,
        )
    manager.reload()
    return {"ok": True, "plugin_name": plugin.plugin_name, "enabled": False, "plugins": manager.list_plugins()}


def disable_all_plugins(manager: Any) -> Dict[str, Any]:
    disabled_names: list[str] = []
    plugins = list(getattr(manager, "_plugins", []) or [])
    if manager._compat_mode:
        enabled_map = manager._load_state()
        for plugin in plugins:
            plugin_name = str(getattr(plugin, "plugin_name", "") or "").strip()
            if not plugin_name:
                continue
            enabled_map[plugin_name] = False
            disabled_names.append(plugin_name)
        manager._save_state(enabled_map)
    else:
        for plugin in plugins:
            plugin_name = str(getattr(plugin, "plugin_name", "") or "").strip()
            if not plugin_name:
                continue
            write_plugin_enabled_config(
                config_path=manager.config_path,
                plugin_key=plugin.config_name or manager._bundled_plugin_key(plugin_name),
                enabled=False,
            )
            disabled_names.append(plugin_name)
    manager.reload()
    return {
        "ok": True,
        "disabled_count": len(disabled_names),
        "disabled_plugins": disabled_names,
        "plugins": manager.list_plugins(),
    }
