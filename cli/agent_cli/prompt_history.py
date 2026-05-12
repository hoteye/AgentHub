from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from time import time

DEFAULT_HISTORY_HOME = Path(os.environ.get("AGENT_CLI_HOME") or (Path.home() / ".agent_cli"))
HISTORY_FILENAME = "history.jsonl"


@dataclass(frozen=True, slots=True)
class StoredPromptHistoryEntry:
    session_id: str
    ts: int
    text: str


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _history_log_id(path: Path) -> int:
    try:
        stat_result = path.stat()
    except OSError:
        return 0
    inode = int(getattr(stat_result, "st_ino", 0) or 0)
    if inode > 0:
        return inode
    mtime_ns = int(getattr(stat_result, "st_mtime_ns", 0) or 0)
    if mtime_ns > 0:
        return mtime_ns
    return int(getattr(stat_result, "st_mtime", 0) or 0)


class PromptHistoryStore:
    def __init__(self, home: Path | None = None) -> None:
        self.home = _safe_resolve(Path(home) if home is not None else DEFAULT_HISTORY_HOME)
        self.path = self.home / HISTORY_FILENAME

    def metadata(self) -> tuple[int, int]:
        path = self.path
        if not path.exists():
            return (0, 0)
        count = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.rstrip("\n"):
                        count += 1
        except OSError:
            return (0, 0)
        return (_history_log_id(path), count)

    def append(self, text: str, *, session_id: str | None = None) -> bool:
        normalized = str(text or "")
        if not normalized:
            return False
        record = StoredPromptHistoryEntry(
            session_id=str(session_id or "").strip() or "default",
            ts=int(time()),
            text=normalized,
        )
        payload = json.dumps(
            {
                "session_id": record.session_id,
                "ts": record.ts,
                "text": record.text,
            },
            ensure_ascii=False,
        )
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
        except OSError:
            return False
        return True

    def lookup(self, log_id: int, offset: int) -> str | None:
        path = self.path
        if offset < 0 or not path.exists():
            return None
        current_log_id = _history_log_id(path)
        if log_id not in {0, current_log_id}:
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                visible_index = 0
                for raw_line in handle:
                    line = raw_line.rstrip("\n")
                    if not line:
                        continue
                    if visible_index != offset:
                        visible_index += 1
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        return None
                    text = str(payload.get("text") or "")
                    return text or None
        except OSError:
            return None
        return None


class PromptHistoryManager:
    def __init__(self, store: PromptHistoryStore | None = None) -> None:
        self.store = store or PromptHistoryStore()
        self.history_log_id, self.history_entry_count = self.store.metadata()
        self.local_history: list[str] = []
        self.fetched_history: dict[int, str] = {}
        self.history_cursor: int | None = None
        self.last_history_text: str | None = None

    def should_handle_navigation(self, text: str, cursor: int) -> bool:
        if self.history_entry_count == 0 and not self.local_history:
            return False
        if not text:
            return True
        if cursor not in {0, len(text)}:
            return False
        return self.last_history_text == text

    def record_local_submission(self, text: str, *, session_id: str | None = None) -> None:
        normalized = str(text or "")
        if not self._history_entry_allowed(normalized):
            return
        self.history_cursor = None
        self.last_history_text = None
        if not self.local_history or self.local_history[-1] != normalized:
            self.local_history.append(normalized)
        self.store.append(normalized, session_id=session_id)

    def sync_after_edit(self, text: str) -> None:
        if self.history_cursor is None:
            return
        if text == (self.last_history_text or ""):
            return
        self.history_cursor = None
        self.last_history_text = None

    def navigate_up(self) -> str | None:
        total_entries = self.history_entry_count + len(self.local_history)
        if total_entries <= 0:
            return None
        previous_cursor = self.history_cursor
        if self.history_cursor is None:
            next_index = total_entries - 1
        elif self.history_cursor <= 0:
            return None
        else:
            next_index = self.history_cursor - 1
        while next_index >= 0:
            entry = self._entry_at_index(next_index)
            if entry is not None:
                self.history_cursor = next_index
                return entry
            next_index -= 1
        if previous_cursor is not None:
            return None
        self.history_cursor = None
        self.last_history_text = None
        return None

    def navigate_down(self) -> str | None:
        total_entries = self.history_entry_count + len(self.local_history)
        if total_entries <= 0 or self.history_cursor is None:
            return None
        next_index = self.history_cursor + 1
        while next_index < total_entries:
            entry = self._entry_at_index(next_index)
            if entry is not None:
                self.history_cursor = next_index
                return entry
            next_index += 1
        self.history_cursor = None
        self.last_history_text = None
        return ""

    def _entry_at_index(self, index: int) -> str | None:
        if index < 0:
            return None
        if index >= self.history_entry_count:
            local_index = index - self.history_entry_count
            if local_index < 0 or local_index >= len(self.local_history):
                return None
            entry = self.local_history[local_index]
            if not self._history_entry_allowed(entry):
                return None
            self.last_history_text = entry
            return entry
        cached = self.fetched_history.get(index)
        if cached is not None:
            if not self._history_entry_allowed(cached):
                return None
            self.last_history_text = cached
            return cached
        entry = self.store.lookup(self.history_log_id, index)
        if entry is None or not self._history_entry_allowed(entry):
            return None
        self.fetched_history[index] = entry
        self.last_history_text = entry
        return entry

    @staticmethod
    def _history_entry_allowed(text: str | None) -> bool:
        normalized = str(text or "").strip()
        return bool(normalized)
