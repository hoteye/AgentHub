from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.orchestration import taskbook_catalog_runtime as taskbook_catalog_runtime_service
from cli.agent_cli.orchestration import taskbook_catalog_db_helpers_runtime as db_helpers_runtime
from cli.agent_cli.orchestration import taskbook_catalog_db_query_runtime as query_runtime
from cli.agent_cli.orchestration import taskbook_catalog_db_runtime_query_builder_runtime as query_builder_runtime

def upsert_run(catalog: Any, run: Any, *, path: Path | str = "") -> None:
    with catalog._lock, catalog._connection() as conn:
        conn.execute(
            """
            INSERT INTO orchestration_runs (
              run_id, thread_id, objective, status, current_phase,
              taskbook_version_current, created_at, updated_at, path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              thread_id=excluded.thread_id,
              objective=excluded.objective,
              status=excluded.status,
              current_phase=excluded.current_phase,
              taskbook_version_current=excluded.taskbook_version_current,
              created_at=excluded.created_at,
              updated_at=excluded.updated_at,
              path=excluded.path
            """,
            (
                run.run_id,
                run.thread_id,
                run.objective,
                run.status.value,
                run.current_phase,
                int(run.taskbook_version_current),
                run.created_at,
                run.updated_at,
                str(path or ""),
            ),
        )
        conn.commit()
def upsert_taskbook(catalog: Any, snapshot: Any, *, path: Path | str = "") -> None:
    with catalog._lock, catalog._connection() as conn:
        conn.execute(
            """
            INSERT INTO orchestration_taskbooks (
              run_id, version, goal, success_definition_text, critical_path_text, created_at, path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, version) DO UPDATE SET
              goal=excluded.goal,
              success_definition_text=excluded.success_definition_text,
              critical_path_text=excluded.critical_path_text,
              created_at=excluded.created_at,
              path=excluded.path
            """,
            (
                snapshot.run_id,
                int(snapshot.version),
                snapshot.goal,
                taskbook_catalog_runtime_service.json_text(snapshot.success_definition),
                taskbook_catalog_runtime_service.json_text(snapshot.critical_path),
                snapshot.created_at,
                str(path or ""),
            ),
        )
        conn.commit()
def upsert_card(
    catalog: Any,
    run_id: str,
    card: Any,
    *,
    state: Any = None,
    spec_path: Path | str = "",
    state_path: Path | str = "",
) -> None:
    db_helpers_runtime.upsert_card_impl(
        catalog,
        run_id,
        card,
        state=state,
        spec_path=spec_path,
        state_path=state_path,
    )
def upsert_result(catalog: Any, result: Any, *, path: Path | str = "") -> None:
    with catalog._lock, catalog._connection() as conn:
        conn.execute(
            """
            INSERT INTO orchestration_results (
              run_id, card_id, result_id, status, summary, modified_files_text, reported_at, path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, result_id) DO UPDATE SET
              card_id=excluded.card_id,
              status=excluded.status,
              summary=excluded.summary,
              modified_files_text=excluded.modified_files_text,
              reported_at=excluded.reported_at,
              path=excluded.path
            """,
            (
                result.run_id,
                result.card_id,
                result.result_id,
                result.status.value,
                result.summary,
                taskbook_catalog_runtime_service.json_text(result.modified_files),
                result.reported_at,
                str(path or ""),
            ),
        )
        conn.commit()


def upsert_acceptance(catalog: Any, acceptance: Any, *, path: Path | str = "") -> None:
    with catalog._lock, catalog._connection() as conn:
        conn.execute(
            """
            INSERT INTO orchestration_acceptance (
              run_id, card_id, acceptance_id, decision, reason, reviewed_at, path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, acceptance_id) DO UPDATE SET
              card_id=excluded.card_id,
              decision=excluded.decision,
              reason=excluded.reason,
              reviewed_at=excluded.reviewed_at,
              path=excluded.path
            """,
            (
                acceptance.run_id,
                acceptance.card_id,
                acceptance.acceptance_id,
                acceptance.decision.value,
                acceptance.reason,
                acceptance.reviewed_at,
                str(path or ""),
            ),
        )
        conn.commit()


def upsert_event(catalog: Any, event: Any, *, path: Path | str = "") -> None:
    with catalog._lock, catalog._connection() as conn:
        conn.execute(
            """
            INSERT INTO orchestration_events (
              run_id, seq, card_id, event_type, actor_type, created_at, path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, seq) DO UPDATE SET
              card_id=excluded.card_id,
              event_type=excluded.event_type,
              actor_type=excluded.actor_type,
              created_at=excluded.created_at,
              path=excluded.path
            """,
            (
                event.run_id,
                int(event.seq),
                event.card_id,
                event.event_type,
                event.actor_type,
                event.created_at,
                str(path or ""),
            ),
        )
        conn.commit()


def upsert_document(
    catalog: Any,
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
    with catalog._lock, catalog._connection() as conn:
        conn.execute(
            """
            INSERT INTO orchestration_documents (
              document_id, run_id, card_id, doc_type, title, path, version, checksum, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
              run_id=excluded.run_id,
              card_id=excluded.card_id,
              doc_type=excluded.doc_type,
              title=excluded.title,
              path=excluded.path,
              version=excluded.version,
              checksum=excluded.checksum,
              updated_at=excluded.updated_at
            """,
            (
                document_id,
                run_id,
                card_id,
                doc_type,
                title,
                str(path or ""),
                int(version),
                checksum,
                updated_at,
            ),
        )
        conn.commit()


def list_runs(
    catalog: Any,
    *,
    thread_id: str = "",
    status: str = "",
    objective_query: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    query, params, normalized_query, effective_limit = query_builder_runtime.build_list_runs_query(
        thread_id=thread_id,
        status=status,
        objective_query=objective_query,
        limit=limit,
    )
    with catalog._lock, catalog._connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return query_runtime.ranking_rows_with_analytics(
        [dict(row) for row in rows],
        kind_key="objective_match_kind",
        rank_key="objective_match_rank",
        query_text=normalized_query,
        query_scope="objective",
        effective_limit=effective_limit,
    )


def list_cards(catalog: Any, run_id: str, *, status: str = "") -> list[dict[str, Any]]:
    with catalog._lock, catalog._connection() as conn:
        rows = conn.execute(
            """
            SELECT run_id, card_id, taskbook_version, title, goal, kind, status,
                   attempt, depends_on_text, owned_files_text, updated_at, spec_path, state_path
            FROM orchestration_cards
            WHERE run_id = ?
              AND (? = '' OR status = ?)
            ORDER BY card_id ASC
            """,
            (run_id, status, status),
        ).fetchall()
    return [dict(row) for row in rows]


def get_card(catalog: Any, run_id: str, card_id: str) -> dict[str, Any] | None:
    with catalog._lock, catalog._connection() as conn:
        row = conn.execute(
            """
            SELECT run_id, card_id, taskbook_version, title, goal, kind, status,
                   attempt, depends_on_text, owned_files_text, updated_at, spec_path, state_path
            FROM orchestration_cards
            WHERE run_id = ? AND card_id = ?
            """,
            (run_id, card_id),
        ).fetchone()
    return dict(row) if row is not None else None


def list_results(catalog: Any, run_id: str, *, card_id: str = "", status: str = "") -> list[dict[str, Any]]:
    with catalog._lock, catalog._connection() as conn:
        rows = conn.execute(
            """
            SELECT run_id, card_id, result_id, status, summary, modified_files_text, reported_at, path
            FROM orchestration_results
            WHERE run_id = ?
              AND (? = '' OR card_id = ?)
              AND (? = '' OR status = ?)
            ORDER BY reported_at DESC, result_id DESC
            """,
            (run_id, card_id, card_id, status, status),
        ).fetchall()
    return [dict(row) for row in rows]


def find_cards_by_owned_file(
    catalog: Any,
    file_path: str,
    *,
    run_id: str = "",
    status: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    query_context = query_builder_runtime.build_find_cards_by_owned_file_query(
        file_path=file_path,
        run_id=run_id,
        status=status,
        limit=limit,
    )
    if query_context is None:
        return []
    query, params, normalized, effective_limit = query_context
    with catalog._lock, catalog._connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return query_runtime.ranking_rows_with_analytics(
        [dict(row) for row in rows],
        kind_key="file_match_kind",
        rank_key="file_match_rank",
        query_text=normalized,
        query_scope="owned_file",
        effective_limit=effective_limit,
    )


def list_documents(
    catalog: Any,
    run_id: str,
    *,
    card_id: str = "",
    doc_type: str = "",
    query: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    sql, params, normalized_query, effective_limit = query_builder_runtime.build_list_documents_query(
        run_id=run_id,
        card_id=card_id,
        doc_type=doc_type,
        query_text=query,
        limit=limit,
    )
    with catalog._lock, catalog._connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return query_runtime.ranking_rows_with_analytics(
        [dict(row) for row in rows],
        kind_key="query_match_kind",
        rank_key="query_match_rank",
        query_text=normalized_query,
        query_scope="document_query",
        effective_limit=effective_limit,
    )
