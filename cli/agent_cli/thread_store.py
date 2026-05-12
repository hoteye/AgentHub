from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cli.agent_cli import thread_store_binding_runtime as binding_runtime
from cli.agent_cli import thread_store_helpers_runtime as helper_runtime
from cli.agent_cli import thread_store_projection_runtime as projection_runtime
from cli.agent_cli import thread_store_queries as query_helpers
from cli.agent_cli import thread_store_resume_runtime as resume_helpers
from cli.agent_cli import thread_store_runtime as thread_store_runtime_service
from cli.agent_cli import thread_store_serialization as serialization_helpers
from cli.agent_cli import thread_store_transactions as transaction_helpers
from cli.agent_cli.models import (
    PromptAttachment,
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ThreadHistoryTurn,
)
from cli.agent_cli.runtime_paths import project_local_data_dir


def _utc_now() -> str:
    return thread_store_runtime_service.utc_now()


@dataclass
class ThreadRecord:
    thread_id: str
    name: str
    created_at: str
    updated_at: str
    rollout_path: str
    cwd: str
    turn_count: int
    archived: bool = False
    last_user_text: str = ""
    last_assistant_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "rollout_path": self.rollout_path,
            "cwd": self.cwd,
            "turn_count": self.turn_count,
            "archived": self.archived,
            "last_user_text": self.last_user_text,
            "last_assistant_text": self.last_assistant_text,
        }


class ThreadStore:
    _PLANNER_HISTORY_LIMIT_MESSAGES = 24

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.rollouts_dir = self.base_dir / "rollouts"
        self.sqlite_path = self.base_dir / "threads.sqlite3"
        self._lock = threading.Lock()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.rollouts_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @classmethod
    def default(cls) -> ThreadStore:
        root = project_local_data_dir() / "threads"
        return cls(root)

    def start_thread(
        self,
        *,
        name: str | None = None,
        cwd: str | None = None,
        provider_status: dict[str, Any] | None = None,
        runtime_policy_status: dict[str, Any] | None = None,
    ) -> ThreadRecord:
        return transaction_helpers.start_thread(
            self,
            record_cls=ThreadRecord,
            name=name,
            cwd=cwd,
            provider_status=provider_status,
            runtime_policy_status=runtime_policy_status,
        )

    def list_threads(
        self,
        *,
        limit: int = 50,
        archived: bool = False,
        cwd: str | None = None,
    ) -> list[dict[str, Any]]:
        return query_helpers.list_threads(self, limit=limit, archived=archived, cwd=cwd)

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        return query_helpers.get_thread(self, thread_id)

    def append_turn(
        self,
        thread_id: str,
        response: PromptResponse,
        *,
        runtime_state: dict[str, Any] | None = None,
        update_active: bool = True,
    ) -> dict[str, Any]:
        return transaction_helpers.append_turn(
            self,
            thread_id,
            response,
            runtime_state=runtime_state,
            update_active=update_active,
        )

    def append_rollout_items(
        self,
        thread_id: str,
        items: list[dict[str, Any]],
        *,
        update_active: bool = True,
    ) -> list[dict[str, Any]]:
        return transaction_helpers.append_rollout_items(
            self,
            thread_id,
            items,
            update_active=update_active,
        )

    def append_compacted(
        self,
        thread_id: str,
        *,
        replacement_history: list[dict[str, Any]] | None = None,
        message: str = "",
        metadata: dict[str, Any] | None = None,
        update_active: bool = True,
    ) -> dict[str, Any]:
        return transaction_helpers.append_compacted(
            self,
            thread_id,
            replacement_history=replacement_history,
            message=message,
            metadata=metadata,
            update_active=update_active,
        )

    def resume_thread_from_path(self, rollout_path: str | Path) -> dict[str, Any]:
        return resume_helpers.resume_thread_from_path(self, rollout_path)

    def resume_thread_from_history(
        self,
        history: list[dict[str, Any]],
        *,
        name: str | None = None,
        cwd: str | None = None,
        provider_status: dict[str, Any] | None = None,
        runtime_policy_status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return resume_helpers.resume_thread_from_history(
            self,
            history,
            name=name,
            cwd=cwd,
            provider_status=provider_status,
            runtime_policy_status=runtime_policy_status,
        )

    def resume_thread(self, thread_id: str) -> dict[str, Any]:
        return resume_helpers.resume_thread(self, thread_id)

    def get_active_thread_id(self) -> str | None:
        return query_helpers.get_active_thread_id(self)

    def describe_thread_record(
        self,
        record: dict[str, Any] | ThreadRecord,
        *,
        status: str = "not_loaded",
        turns: list[dict[str, Any]] | None = None,
        metadata_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return query_helpers.describe_thread_record(
            self,
            record,
            status=status,
            turns=turns,
            metadata_overrides=metadata_overrides,
        )

    def describe_thread(
        self,
        thread_id: str,
        *,
        status: str = "not_loaded",
        turns: list[dict[str, Any]] | None = None,
        metadata_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return query_helpers.describe_thread(
            self,
            thread_id,
            status=status,
            turns=turns,
            metadata_overrides=metadata_overrides,
        )

    def set_active_thread_id(self, thread_id: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('active_thread_id', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (thread_id,),
            )
            conn.commit()

    def _init_schema(self) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    rollout_path TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    last_user_text TEXT NOT NULL DEFAULT '',
                    last_assistant_text TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _write_rollout_line(path: Path, payload: dict[str, Any]) -> None:
        thread_store_runtime_service.write_rollout_line(path, payload)

    @staticmethod
    def _assistant_history_text(response: PromptResponse) -> str:
        return helper_runtime.assistant_history_text(response)

    @staticmethod
    def _attachment_to_dict(item: PromptAttachment) -> dict[str, Any]:
        return item.to_dict()

    def _reference_context_items_from_response(
        self, response: PromptResponse
    ) -> list[ReferenceContextItem]:
        return projection_runtime.reference_context_items_from_response(
            response,
            reference_context_items_from_tool_event_fn=self._reference_context_items_from_tool_event,
            dedupe_reference_context_items_fn=self._dedupe_reference_context_items,
        )

    def _history_turn_from_response(
        self,
        response: PromptResponse,
        *,
        timestamp: str,
        assistant_history_text: str,
        runtime_state: dict[str, Any] | None = None,
    ) -> ThreadHistoryTurn:
        return projection_runtime.history_turn_from_response(
            response,
            timestamp=timestamp,
            assistant_history_text=assistant_history_text,
            runtime_state=runtime_state,
            canonical_turn_events_fn=lambda raw_response, response_items: self._canonical_turn_events(
                raw_response,
                response_items=response_items,
            ),
            reference_context_items_from_tool_event_fn=self._reference_context_items_from_tool_event,
            dedupe_reference_context_items_fn=self._dedupe_reference_context_items,
            attachment_to_dict_fn=self._attachment_to_dict,
            tool_event_to_dict_fn=self._tool_event_to_dict,
            activity_event_to_dict_fn=self._activity_event_to_dict,
        )

    def _rollout_causality_payload(
        self,
        response: PromptResponse,
        *,
        runtime_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return serialization_helpers.rollout_causality_payload(
            response,
            runtime_state=runtime_state,
        )

    @staticmethod
    def _canonical_turn_events(
        response: PromptResponse,
        *,
        response_items: list[ResponseInputItem],
    ) -> list[dict[str, Any]]:
        return helper_runtime.canonical_turn_events(
            response,
            response_items=response_items,
        )

    def _resolve_rollout_path(self, thread_id: str, record: dict[str, Any]) -> Path:
        return transaction_helpers.resolve_rollout_path(self, thread_id, record)

    def _normalize_record(self, record: ThreadRecord) -> ThreadRecord:
        return transaction_helpers.normalize_record(self, record)

    @staticmethod
    def _resolve_existing_rollout_path(path_text: str | Path) -> Path:
        return transaction_helpers.resolve_existing_rollout_path(path_text)

    def _ensure_thread_record_for_rollout_path(self, rollout_path: Path) -> dict[str, Any]:
        return transaction_helpers.ensure_thread_record_for_rollout_path(self, rollout_path)


binding_runtime.install_thread_store_bindings(
    ThreadStore,
    record_cls=ThreadRecord,
    utc_now_fn=_utc_now,
)
