from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration import taskbook_catalog_db_query_builder_helpers_runtime as query_builder_helpers_runtime
from cli.agent_cli.orchestration import taskbook_catalog_db_query_runtime as query_runtime


def build_list_runs_query(
    *,
    thread_id: str,
    status: str,
    objective_query: str,
    limit: int,
) -> tuple[str, tuple[Any, ...], str, int]:
    effective_limit = query_runtime.normalized_limit(limit, default=200, maximum=1000)
    normalized_thread_id = query_runtime.normalized_text(thread_id)
    normalized_status = query_runtime.normalized_text(status)
    normalized_query = query_runtime.normalized_text(objective_query)
    normalized_query_lower = normalized_query.lower()
    token_any_expr, token_all_expr, token_count_expr, token_patterns_for_run_fields = query_builder_helpers_runtime.token_match_context(
        query_runtime=query_runtime,
        normalized_query_lower=normalized_query_lower,
        like_clauses=["LOWER(objective) LIKE ?", "LOWER(current_phase) LIKE ?"],
        fields_per_token=2,
    )
    objective_pattern = query_runtime.contains_pattern(normalized_query_lower)
    objective_prefix_pattern = query_runtime.prefix_pattern(normalized_query_lower)
    phase_pattern = query_runtime.contains_pattern(normalized_query_lower)
    phase_prefix_pattern = query_runtime.prefix_pattern(normalized_query_lower)
    query = f"""
        SELECT run_id, thread_id, objective, status, current_phase,
               taskbook_version_current, created_at, updated_at, path, token_match_count,
               objective_match_rank, objective_match_kind
        FROM (
          SELECT run_id, thread_id, objective, status, current_phase,
                 taskbook_version_current, created_at, updated_at, path,
                 CASE
                   WHEN ? = '' THEN 0
                   ELSE ({token_count_expr})
                 END AS token_match_count,
                 CASE
                   WHEN ? = '' THEN NULL
                   WHEN LOWER(objective) = ? OR LOWER(current_phase) = ? THEN 0
                   WHEN LOWER(objective) LIKE ? OR LOWER(current_phase) LIKE ? THEN 1
                   WHEN LOWER(objective) LIKE ? OR LOWER(current_phase) LIKE ? THEN 2
                   WHEN ({token_all_expr}) THEN 3
                   WHEN ({token_any_expr}) THEN 4
                   ELSE 5
                 END AS objective_match_rank,
                 CASE
                   WHEN ? = '' THEN ''
                   WHEN LOWER(objective) = ? OR LOWER(current_phase) = ? THEN 'exact'
                   WHEN LOWER(objective) LIKE ? OR LOWER(current_phase) LIKE ? THEN 'prefix'
                   WHEN LOWER(objective) LIKE ? OR LOWER(current_phase) LIKE ? THEN 'contains'
                   WHEN ({token_all_expr}) THEN 'token_all'
                   WHEN ({token_any_expr}) THEN 'token_contains'
                   ELSE 'no_match'
                 END AS objective_match_kind
          FROM orchestration_runs
          WHERE (? = '' OR thread_id = ?)
            AND (? = '' OR status = ?)
            AND (? = '' OR LOWER(objective) LIKE ? OR LOWER(current_phase) LIKE ? OR ({token_any_expr}))
        )
        ORDER BY
          CASE WHEN objective_match_rank IS NULL THEN 1 ELSE 0 END ASC,
          objective_match_rank ASC,
          token_match_count DESC,
          updated_at DESC,
          created_at DESC,
          run_id DESC
        LIMIT ?
    """
    params: tuple[Any, ...] = query_builder_helpers_runtime.build_list_runs_params(
        normalized_query_lower=normalized_query_lower,
        token_patterns_for_run_fields=token_patterns_for_run_fields,
        objective_prefix_pattern=objective_prefix_pattern,
        phase_prefix_pattern=phase_prefix_pattern,
        objective_pattern=objective_pattern,
        phase_pattern=phase_pattern,
        normalized_thread_id=normalized_thread_id,
        normalized_status=normalized_status,
        effective_limit=effective_limit,
    )
    return query, params, normalized_query, effective_limit


def build_find_cards_by_owned_file_query(
    *,
    file_path: str,
    run_id: str,
    status: str,
    limit: int,
) -> tuple[str, tuple[Any, ...], str, int] | None:
    normalized = query_runtime.normalized_text(file_path)
    if not normalized:
        return None
    normalized_lower = normalized.lower()
    contains_pattern = query_runtime.contains_pattern(normalized_lower)
    prefix_posix = query_runtime.prefix_pattern(normalized_lower)
    prefix_windows = query_runtime.prefix_pattern(normalized_lower.replace("/", "\\"))
    suffix_posix = f"%/{normalized_lower}"
    suffix_windows = f"%\\{normalized_lower}"
    effective_limit = query_runtime.normalized_limit(limit, default=200, maximum=1000)
    normalized_run_id = query_runtime.normalized_text(run_id)
    normalized_status = query_runtime.normalized_text(status)
    query = """
        WITH matched_files AS (
          SELECT
            c.run_id,
            c.card_id,
            c.taskbook_version,
            c.title,
            c.goal,
            c.kind,
            c.status,
            c.attempt,
            c.depends_on_text,
            c.owned_files_text,
            c.updated_at,
            c.spec_path,
            c.state_path,
            f.file_path AS matched_file_path,
            LENGTH(f.file_path) AS matched_file_length,
            CASE
              WHEN LOWER(f.file_path) = ? THEN 0
              WHEN LOWER(f.file_path) LIKE ? OR LOWER(f.file_path) LIKE ? THEN 1
              WHEN LOWER(f.file_path) LIKE ? OR LOWER(f.file_path) LIKE ? THEN 2
              ELSE 3
            END AS file_match_rank
          FROM orchestration_cards AS c
          INNER JOIN orchestration_card_files AS f
            ON f.run_id = c.run_id
           AND f.card_id = c.card_id
          WHERE (? = '' OR c.run_id = ?)
            AND (? = '' OR c.status = ?)
            AND (
              LOWER(f.file_path) = ?
              OR LOWER(f.file_path) LIKE ?
              OR LOWER(f.file_path) LIKE ?
              OR LOWER(f.file_path) LIKE ?
              OR LOWER(f.file_path) LIKE ?
            )
        ),
        ranked_cards AS (
          SELECT
            run_id,
            card_id,
            taskbook_version,
            title,
            goal,
            kind,
            status,
            attempt,
            depends_on_text,
            owned_files_text,
            updated_at,
            spec_path,
            state_path,
            matched_file_path,
            file_match_rank,
            CASE
              WHEN file_match_rank = 0 THEN 'exact'
              WHEN file_match_rank = 1 THEN 'suffix'
              WHEN file_match_rank = 2 THEN 'prefix_or_contains'
              ELSE 'contains'
            END AS file_match_kind,
            ROW_NUMBER() OVER (
              PARTITION BY run_id, card_id
              ORDER BY file_match_rank ASC, matched_file_length ASC, matched_file_path ASC
            ) AS file_row
          FROM matched_files
        )
        SELECT
          run_id,
          card_id,
          taskbook_version,
          title,
          goal,
          kind,
          status,
          attempt,
          depends_on_text,
          owned_files_text,
          updated_at,
          spec_path,
          state_path,
          matched_file_path,
          file_match_rank,
          file_match_kind
        FROM ranked_cards
        WHERE file_row = 1
        ORDER BY file_match_rank ASC, updated_at DESC, card_id ASC
        LIMIT ?
    """
    params: tuple[Any, ...] = query_builder_helpers_runtime.build_find_cards_by_owned_file_params(
        normalized_lower=normalized_lower,
        suffix_posix=suffix_posix,
        suffix_windows=suffix_windows,
        prefix_posix=prefix_posix,
        prefix_windows=prefix_windows,
        normalized_run_id=normalized_run_id,
        normalized_status=normalized_status,
        contains_pattern=contains_pattern,
        effective_limit=effective_limit,
    )
    return query, params, normalized, effective_limit


def build_list_documents_query(
    *,
    run_id: str,
    card_id: str,
    doc_type: str,
    query_text: str,
    limit: int,
) -> tuple[str, tuple[Any, ...], str, int]:
    effective_limit = query_runtime.normalized_limit(limit, default=200, maximum=1000)
    normalized_query = query_runtime.normalized_text(query_text)
    normalized_query_lower = normalized_query.lower()
    token_any_expr, token_all_expr, token_count_expr, token_patterns_for_document_fields = query_builder_helpers_runtime.token_match_context(
        query_runtime=query_runtime,
        normalized_query_lower=normalized_query_lower,
        like_clauses=["LOWER(title) LIKE ?", "LOWER(path) LIKE ?", "LOWER(doc_type) LIKE ?", "LOWER(card_id) LIKE ?"],
        fields_per_token=4,
    )
    query_pattern = query_runtime.contains_pattern(normalized_query_lower)
    query_prefix_pattern = query_runtime.prefix_pattern(normalized_query_lower)
    query = f"""
        SELECT
          document_id,
          run_id,
          card_id,
          doc_type,
          title,
          path,
          version,
          checksum,
          updated_at,
          token_match_count,
          query_match_rank,
          query_match_kind
        FROM (
          SELECT
            document_id,
            run_id,
            card_id,
            doc_type,
            title,
            path,
            version,
            checksum,
            updated_at,
            CASE
              WHEN ? = '' THEN 0
              ELSE ({token_count_expr})
            END AS token_match_count,
            CASE
              WHEN ? = '' THEN NULL
              WHEN LOWER(title) = ? OR LOWER(path) = ? OR LOWER(doc_type) = ? OR LOWER(card_id) = ? THEN 0
              WHEN LOWER(title) LIKE ? OR LOWER(path) LIKE ? OR LOWER(doc_type) LIKE ? OR LOWER(card_id) LIKE ? THEN 1
              WHEN LOWER(title) LIKE ? OR LOWER(path) LIKE ? OR LOWER(doc_type) LIKE ? OR LOWER(card_id) LIKE ? THEN 2
              WHEN ({token_all_expr}) THEN 3
              WHEN ({token_any_expr}) THEN 4
              ELSE 5
            END AS query_match_rank,
            CASE
              WHEN ? = '' THEN ''
              WHEN LOWER(title) = ? OR LOWER(path) = ? OR LOWER(doc_type) = ? OR LOWER(card_id) = ? THEN 'exact'
              WHEN LOWER(title) LIKE ? OR LOWER(path) LIKE ? OR LOWER(doc_type) LIKE ? OR LOWER(card_id) LIKE ? THEN 'prefix'
              WHEN LOWER(title) LIKE ? OR LOWER(path) LIKE ? OR LOWER(doc_type) LIKE ? OR LOWER(card_id) LIKE ? THEN 'contains'
              WHEN ({token_all_expr}) THEN 'token_all'
              WHEN ({token_any_expr}) THEN 'token_contains'
              ELSE 'no_match'
            END AS query_match_kind
          FROM orchestration_documents
          WHERE run_id = ?
            AND (? = '' OR card_id = ?)
            AND (? = '' OR doc_type = ?)
            AND (? = '' OR LOWER(title) LIKE ? OR LOWER(path) LIKE ? OR LOWER(doc_type) LIKE ? OR LOWER(card_id) LIKE ? OR ({token_any_expr}))
        )
        ORDER BY
          CASE WHEN query_match_rank IS NULL THEN 1 ELSE 0 END ASC,
          query_match_rank ASC,
          token_match_count DESC,
          updated_at DESC,
          doc_type ASC,
          card_id ASC,
          title ASC
        LIMIT ?
    """
    params: tuple[Any, ...] = query_builder_helpers_runtime.build_list_documents_params(
        normalized_query_lower=normalized_query_lower,
        token_patterns_for_document_fields=token_patterns_for_document_fields,
        query_prefix_pattern=query_prefix_pattern,
        query_pattern=query_pattern,
        run_id=run_id,
        card_id=card_id,
        doc_type=doc_type,
        effective_limit=effective_limit,
    )
    return query, params, normalized_query, effective_limit
