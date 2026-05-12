from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli.runtime_paths import project_local_data_dir
from cli.agent_cli.ui.tab_task_run import TabRole

SCHEMA_VERSION = 1
MANIFEST_FILENAME = "tui_tab_sessions.json"


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def migrate_tab_session_manifest_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw_version = payload.get("schema_version", SCHEMA_VERSION)
    try:
        schema_version = int(raw_version)
    except (TypeError, ValueError):
        return None
    if schema_version == SCHEMA_VERSION:
        migrated = dict(payload)
        migrated["schema_version"] = SCHEMA_VERSION
        return migrated
    return None


def _normalize_role(value: Any) -> TabRole:
    role = str(value or "").strip()
    if role in {"master", "child"}:
        return role  # type: ignore[return-value]
    return "standalone"


@dataclass(slots=True)
class TabSessionManifestTab:
    tab_id: str
    thread_id: str
    engine: str = "agenthub_python"
    kernel_session_id: str = ""
    thread_name: str = ""
    title: str = ""
    custom_label: str = ""
    prompt_text: str = ""
    prompt_cursor_position: int = 0
    cwd: str = ""
    provider_name: str = ""
    provider_model: str = ""
    forked_from_tab_id: str = ""
    forked_from_thread_id: str = ""
    fork_mode: str = ""
    role: TabRole = "standalone"
    parent_tab_id: str = ""
    scroll_x: int = 0
    scroll_y: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TabSessionManifestTab | None:
        tab_id = str(payload.get("tab_id") or "").strip()
        thread_id = str(payload.get("thread_id") or "").strip()
        if not tab_id or not thread_id:
            return None
        prompt_text = str(payload.get("prompt_text") or "")
        raw_cursor = payload.get("prompt_cursor_position")
        try:
            cursor = int(raw_cursor)
        except (TypeError, ValueError):
            cursor = len(prompt_text)
        cursor = max(0, min(cursor, len(prompt_text)))
        return cls(
            tab_id=tab_id,
            thread_id=thread_id,
            engine=_normalize_engine(payload.get("engine")),
            kernel_session_id=str(payload.get("kernel_session_id") or "").strip(),
            thread_name=str(payload.get("thread_name") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            custom_label=str(payload.get("custom_label") or "").strip(),
            prompt_text=prompt_text,
            prompt_cursor_position=cursor,
            cwd=str(payload.get("cwd") or "").strip(),
            provider_name=str(payload.get("provider_name") or "").strip(),
            provider_model=str(payload.get("provider_model") or "").strip(),
            forked_from_tab_id=str(payload.get("forked_from_tab_id") or "").strip(),
            forked_from_thread_id=str(payload.get("forked_from_thread_id") or "").strip(),
            fork_mode=str(payload.get("fork_mode") or "").strip(),
            role=_normalize_role(payload.get("role")),
            parent_tab_id=str(payload.get("parent_tab_id") or "").strip(),
            scroll_x=max(0, _safe_int(payload.get("scroll_x"))),
            scroll_y=max(0, _safe_int(payload.get("scroll_y"))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "thread_id": self.thread_id,
            "engine": _normalize_engine(self.engine),
            "kernel_session_id": self.kernel_session_id,
            "thread_name": self.thread_name,
            "title": self.title,
            "custom_label": self.custom_label,
            "prompt_text": self.prompt_text,
            "prompt_cursor_position": max(
                0,
                min(int(self.prompt_cursor_position), len(self.prompt_text)),
            ),
            "cwd": self.cwd,
            "provider_name": self.provider_name,
            "provider_model": self.provider_model,
            "forked_from_tab_id": self.forked_from_tab_id,
            "forked_from_thread_id": self.forked_from_thread_id,
            "fork_mode": self.fork_mode,
            "role": _normalize_role(self.role),
            "parent_tab_id": self.parent_tab_id,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
        }


@dataclass(slots=True)
class TabSessionManifest:
    active_tab_id: str
    tab_order: list[str]
    tabs: list[TabSessionManifestTab] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TabSessionManifest | None:
        payload = migrate_tab_session_manifest_payload(payload) or {}
        if not payload:
            return None
        tabs = [
            tab
            for item in list(payload.get("tabs") or [])
            if isinstance(item, dict)
            for tab in [TabSessionManifestTab.from_dict(item)]
            if tab is not None
        ]
        if not tabs:
            return None
        tab_ids = {tab.tab_id for tab in tabs}
        tab_order = [
            str(item or "").strip()
            for item in list(payload.get("tab_order") or [])
            if str(item or "").strip() in tab_ids
        ]
        for tab in tabs:
            if tab.tab_id not in tab_order:
                tab_order.append(tab.tab_id)
        active_tab_id = str(payload.get("active_tab_id") or "").strip()
        if active_tab_id not in tab_ids:
            active_tab_id = tab_order[0]
        return cls(
            active_tab_id=active_tab_id,
            tab_order=tab_order,
            tabs=tabs,
        )

    def to_dict(self) -> dict[str, Any]:
        tab_ids = {tab.tab_id for tab in self.tabs}
        tab_order = [tab_id for tab_id in self.tab_order if tab_id in tab_ids]
        for tab in self.tabs:
            if tab.tab_id not in tab_order:
                tab_order.append(tab.tab_id)
        active_tab_id = self.active_tab_id if self.active_tab_id in tab_ids else ""
        if not active_tab_id and tab_order:
            active_tab_id = tab_order[0]
        return {
            "schema_version": self.schema_version,
            "active_tab_id": active_tab_id,
            "tab_order": tab_order,
            "tabs": [tab.to_dict() for tab in self.tabs],
        }


def tab_manifest_path_for_runtime(runtime: Any) -> Path:
    thread_store = getattr(runtime, "thread_store", None)
    base_dir = getattr(thread_store, "base_dir", None)
    if base_dir is not None:
        return Path(base_dir).expanduser().resolve(strict=False).parent / MANIFEST_FILENAME
    return project_local_data_dir() / MANIFEST_FILENAME


def _normalize_engine(value: Any) -> str:
    engine = str(value or "").strip()
    if engine == "codex_sidecar":
        return "codex_sidecar"
    return "agenthub_python"


def tab_manifest_enabled_for_runtime(runtime: Any) -> bool:
    return bool(getattr(runtime, "tui_tab_manifest_enabled", False))


def load_tab_session_manifest(path: Path) -> TabSessionManifest | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return TabSessionManifest.from_dict(payload)


def save_tab_session_manifest(path: Path, manifest: TabSessionManifest) -> None:
    payload = manifest.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)
