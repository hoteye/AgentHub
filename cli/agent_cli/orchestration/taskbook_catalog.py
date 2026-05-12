from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cli.agent_cli.orchestration import taskbook_catalog_db_runtime as taskbook_catalog_db_runtime_service
from cli.agent_cli.orchestration import taskbook_catalog_runtime as taskbook_catalog_runtime_service
from cli.agent_cli.runtime_paths import project_local_data_dir
from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    OrchestrationEvent,
    TaskCard,
    TaskCardState,
    TaskbookSnapshot,
)
from cli.agent_cli.orchestration.taskbook_storage import TaskbookStorage


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orchestration_runs (
  run_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL DEFAULT '',
  objective TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  current_phase TEXT NOT NULL DEFAULT '',
  taskbook_version_current INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_orchestration_runs_thread_status_updated
  ON orchestration_runs(thread_id, status, updated_at);

CREATE TABLE IF NOT EXISTS orchestration_taskbooks (
  run_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  goal TEXT NOT NULL DEFAULT '',
  success_definition_text TEXT NOT NULL DEFAULT '[]',
  critical_path_text TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, version)
);

CREATE TABLE IF NOT EXISTS orchestration_cards (
  run_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  taskbook_version INTEGER NOT NULL DEFAULT 1,
  title TEXT NOT NULL DEFAULT '',
  goal TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  attempt INTEGER NOT NULL DEFAULT 0,
  depends_on_text TEXT NOT NULL DEFAULT '[]',
  owned_files_text TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL DEFAULT '',
  spec_path TEXT NOT NULL DEFAULT '',
  state_path TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, card_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_cards_run_status_updated
  ON orchestration_cards(run_id, status, updated_at);

CREATE TABLE IF NOT EXISTS orchestration_card_files (
  run_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  file_path TEXT NOT NULL,
  PRIMARY KEY (run_id, card_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_card_files_path
  ON orchestration_card_files(file_path);

CREATE TABLE IF NOT EXISTS orchestration_results (
  run_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  result_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  modified_files_text TEXT NOT NULL DEFAULT '[]',
  reported_at TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, result_id)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_results_run_card_reported
  ON orchestration_results(run_id, card_id, reported_at);

CREATE TABLE IF NOT EXISTS orchestration_acceptance (
  run_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  acceptance_id TEXT NOT NULL,
  decision TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  reviewed_at TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, acceptance_id)
);

CREATE TABLE IF NOT EXISTS orchestration_events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  card_id TEXT NOT NULL DEFAULT '',
  event_type TEXT NOT NULL DEFAULT '',
  actor_type TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_orchestration_events_run_created
  ON orchestration_events(run_id, created_at);

CREATE TABLE IF NOT EXISTS orchestration_documents (
  document_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL DEFAULT '',
  card_id TEXT NOT NULL DEFAULT '',
  doc_type TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  path TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 0,
  checksum TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_orchestration_documents_run_card_type
  ON orchestration_documents(run_id, card_id, doc_type);
"""
def orchestration_catalog_path(*, root: Path | None = None) -> Path:
    return taskbook_catalog_runtime_service.orchestration_catalog_path(project_local_data_dir_fn=project_local_data_dir, root=root)

_json_text = taskbook_catalog_runtime_service.json_text


@dataclass(slots=True)
class TaskbookCatalog:
    db_path: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path)

    @classmethod
    def default(cls, *, root: Path | None = None) -> "TaskbookCatalog":
        return cls(orchestration_catalog_path(root=root))
    def ensure_ready(self) -> None:
        with self._lock:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    def upsert_run(self, run: ComplexTaskRun, *, path: Path | str = "") -> None:
        self.ensure_ready()
        taskbook_catalog_db_runtime_service.upsert_run(self, run, path=path)

    def upsert_taskbook(self, snapshot: TaskbookSnapshot, *, path: Path | str = "") -> None:
        self.ensure_ready()
        taskbook_catalog_db_runtime_service.upsert_taskbook(self, snapshot, path=path)

    def upsert_card(
        self,
        run_id: str,
        card: TaskCard,
        *,
        state: TaskCardState | None = None,
        spec_path: Path | str = "",
        state_path: Path | str = "",
    ) -> None:
        self.ensure_ready()
        taskbook_catalog_db_runtime_service.upsert_card(
            self,
            run_id,
            card,
            state=state,
            spec_path=spec_path,
            state_path=state_path,
        )

    def upsert_result(self, result: CardResult, *, path: Path | str = "") -> None:
        self.ensure_ready()
        taskbook_catalog_db_runtime_service.upsert_result(self, result, path=path)

    def upsert_acceptance(self, acceptance: CardAcceptance, *, path: Path | str = "") -> None:
        self.ensure_ready()
        taskbook_catalog_db_runtime_service.upsert_acceptance(self, acceptance, path=path)

    def upsert_event(self, event: OrchestrationEvent, *, path: Path | str = "") -> None:
        self.ensure_ready()
        taskbook_catalog_db_runtime_service.upsert_event(self, event, path=path)

    def upsert_document(
        self,
        *,
        document_id: str,
        run_id: str,
        card_id: str = "",
        doc_type: str,
        title: str,
        path: Path | str,
        version: int = 0,
        checksum: str = "",
        updated_at: str = "",
    ) -> None:
        self.ensure_ready()
        taskbook_catalog_db_runtime_service.upsert_document(
            self,
            document_id=document_id,
            run_id=run_id,
            card_id=card_id,
            doc_type=doc_type,
            title=title,
            path=path,
            version=version,
            checksum=checksum,
            updated_at=updated_at,
        )

    def list_runs(
        self,
        *,
        thread_id: str = "",
        status: str = "",
        objective_query: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        return taskbook_catalog_db_runtime_service.list_runs(
            self,
            thread_id=thread_id,
            status=status,
            objective_query=objective_query,
            limit=limit,
        )

    def list_cards(self, run_id: str, *, status: str = "") -> list[dict[str, Any]]:
        self.ensure_ready()
        return taskbook_catalog_db_runtime_service.list_cards(self, run_id, status=status)

    def get_card(self, run_id: str, card_id: str) -> dict[str, Any] | None:
        self.ensure_ready()
        return taskbook_catalog_db_runtime_service.get_card(self, run_id, card_id)

    def list_results(self, run_id: str, *, card_id: str = "", status: str = "") -> list[dict[str, Any]]:
        self.ensure_ready()
        return taskbook_catalog_db_runtime_service.list_results(self, run_id, card_id=card_id, status=status)

    def find_cards_by_owned_file(
        self,
        file_path: str,
        *,
        run_id: str = "",
        status: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        return taskbook_catalog_db_runtime_service.find_cards_by_owned_file(
            self,
            file_path,
            run_id=run_id,
            status=status,
            limit=limit,
        )

    def list_documents(
        self,
        run_id: str,
        *,
        card_id: str = "",
        doc_type: str = "",
        query: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        return taskbook_catalog_db_runtime_service.list_documents(
            self,
            run_id,
            card_id=card_id,
            doc_type=doc_type,
            query=query,
            limit=limit,
        )
    def rebuild_run_index(self, storage: TaskbookStorage, run_id: str) -> dict[str, int]:
        return taskbook_catalog_runtime_service.rebuild_run_index(self, storage, run_id)
