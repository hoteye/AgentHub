from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.orchestration import taskbook_catalog_runtime as taskbook_catalog_runtime_service


def upsert_card_impl(
    catalog: Any,
    run_id: str,
    card: Any,
    *,
    state: Any = None,
    spec_path: Path | str = "",
    state_path: Path | str = "",
) -> None:
    status = state.status.value if state is not None else ""
    attempt = int(state.attempt) if state is not None else 0
    updated_at = str(state.updated_at or "") if state is not None else ""
    with catalog._lock, catalog._connection() as conn:
        conn.execute(
            """
            INSERT INTO orchestration_cards (
              run_id, card_id, taskbook_version, title, goal, kind, status,
              attempt, depends_on_text, owned_files_text, updated_at, spec_path, state_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, card_id) DO UPDATE SET
              taskbook_version=excluded.taskbook_version,
              title=excluded.title,
              goal=excluded.goal,
              kind=excluded.kind,
              status=excluded.status,
              attempt=excluded.attempt,
              depends_on_text=excluded.depends_on_text,
              owned_files_text=excluded.owned_files_text,
              updated_at=excluded.updated_at,
              spec_path=excluded.spec_path,
              state_path=excluded.state_path
            """,
            (
                run_id,
                card.card_id,
                int(card.taskbook_version),
                card.title,
                card.goal,
                card.kind.value,
                status,
                attempt,
                taskbook_catalog_runtime_service.json_text(card.depends_on),
                taskbook_catalog_runtime_service.json_text(card.owned_files),
                updated_at,
                str(spec_path or ""),
                str(state_path or ""),
            ),
        )
        conn.execute(
            "DELETE FROM orchestration_card_files WHERE run_id = ? AND card_id = ?",
            (run_id, card.card_id),
        )
        for owned_file in card.owned_files:
            conn.execute(
                """
                INSERT INTO orchestration_card_files (run_id, card_id, file_path)
                VALUES (?, ?, ?)
                """,
                (run_id, card.card_id, owned_file),
            )
        conn.commit()
