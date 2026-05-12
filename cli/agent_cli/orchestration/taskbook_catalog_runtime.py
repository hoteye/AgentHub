from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    OrchestrationEvent,
    TaskbookSnapshot,
)


def orchestration_catalog_path(*, project_local_data_dir_fn: Any, root: Path | None = None) -> Path:
    return (Path(root) if root is not None else project_local_data_dir_fn() / "orchestration") / "orchestration_catalog.sqlite3"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _file_checksum(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(payload).hexdigest()


def _file_updated_at(path: Path, fallback: str = "") -> str:
    try:
        stat = path.stat()
    except OSError:
        return fallback
    return datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat().replace("+00:00", "Z")


def rebuild_run_index(catalog: Any, storage: Any, run_id: str) -> dict[str, int]:
    catalog.ensure_ready()
    storage.ensure_run_layout(run_id)
    run = storage.read_run(run_id)
    taskbooks_dir = storage.taskbooks_dir(run_id)
    taskbook_paths = sorted(taskbooks_dir.glob("taskbook_v*.json")) if taskbooks_dir.exists() else []
    card_ids = storage.list_card_ids(run_id)
    events_dir = storage.events_dir(run_id)
    event_paths = sorted(events_dir.glob("*.json")) if events_dir.exists() else []

    with catalog._lock, catalog._connection() as conn:
        conn.execute("DELETE FROM orchestration_taskbooks WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM orchestration_cards WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM orchestration_card_files WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM orchestration_results WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM orchestration_acceptance WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM orchestration_events WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM orchestration_documents WHERE run_id = ?", (run_id,))
        conn.commit()

    if isinstance(run, ComplexTaskRun):
        catalog.upsert_run(run, path=storage.run_file_path(run_id))

    for taskbook_path in taskbook_paths:
        snapshot = TaskbookSnapshot.from_dict(read_json_mapping(taskbook_path))
        if snapshot is not None:
            catalog.upsert_taskbook(snapshot, path=taskbook_path)

    card_count = 0
    result_count = 0
    acceptance_count = 0
    card_title_by_id: dict[str, str] = {}
    for card_id in card_ids:
        card = storage.read_card_spec(run_id, card_id)
        state = storage.read_card_state(run_id, card_id)
        if card is None:
            continue
        card_title_by_id[card_id] = str(card.title or "")
        catalog.upsert_card(
            run_id,
            card,
            state=state,
            spec_path=storage.card_spec_path(run_id, card_id),
            state_path=storage.card_state_path(run_id, card_id),
        )
        card_count += 1
        results_dir = storage.card_results_dir(run_id, card_id)
        result_paths = sorted(results_dir.glob("*.json")) if results_dir.exists() else []
        for result_path in result_paths:
            result = CardResult.from_dict(read_json_mapping(result_path))
            catalog.upsert_result(result, path=result_path)
            result_count += 1
        acceptance_dir = storage.card_acceptance_dir(run_id, card_id)
        acceptance_paths = sorted(acceptance_dir.glob("*.json")) if acceptance_dir.exists() else []
        for acceptance_path in acceptance_paths:
            acceptance = CardAcceptance.from_dict(read_json_mapping(acceptance_path))
            catalog.upsert_acceptance(acceptance, path=acceptance_path)
            acceptance_count += 1

    for event_path in event_paths:
        event = OrchestrationEvent.from_dict(read_json_mapping(event_path))
        catalog.upsert_event(event, path=event_path)

    run_updated_at = str(run.updated_at if isinstance(run, ComplexTaskRun) else "")
    run_version = int(run.taskbook_version_current) if isinstance(run, ComplexTaskRun) else 0
    projections_dir = storage.run_dir(run_id) / "projections"
    projection_taskbook = projections_dir / "taskbook.md"
    if projection_taskbook.exists():
        catalog.upsert_document(
            document_id=f"{run_id}:projection:taskbook",
            run_id=run_id,
            doc_type="projection_taskbook",
            title="taskbook",
            path=projection_taskbook,
            version=run_version,
            checksum=_file_checksum(projection_taskbook),
            updated_at=_file_updated_at(projection_taskbook, fallback=run_updated_at),
        )
    cards_projection_dir = projections_dir / "cards"
    card_projection_paths = sorted(cards_projection_dir.glob("*.md")) if cards_projection_dir.exists() else []
    for card_projection in card_projection_paths:
        card_id = card_projection.stem
        card_title = card_title_by_id.get(card_id) or card_id
        catalog.upsert_document(
            document_id=f"{run_id}:projection:{card_id}",
            run_id=run_id,
            card_id=card_id,
            doc_type="projection_card",
            title=card_title,
            path=card_projection,
            version=run_version,
            checksum=_file_checksum(card_projection),
            updated_at=_file_updated_at(card_projection, fallback=run_updated_at),
        )

    return {
        "runs": 1 if isinstance(run, ComplexTaskRun) else 0,
        "taskbooks": len(taskbook_paths),
        "cards": card_count,
        "results": result_count,
        "acceptance": acceptance_count,
        "events": len(event_paths),
    }
