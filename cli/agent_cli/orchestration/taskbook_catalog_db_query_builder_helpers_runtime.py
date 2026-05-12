from __future__ import annotations

from typing import Any


def token_match_context(
    *,
    query_runtime: Any,
    normalized_query_lower: str,
    like_clauses: list[str],
    fields_per_token: int,
) -> tuple[str, str, str, list[str]]:
    query_tokens = query_runtime.query_tokens(normalized_query_lower)
    token_patterns = [query_runtime.contains_pattern(token) for token in query_tokens]
    token_any_expr, token_all_expr, token_count_expr = query_runtime.token_match_sql(
        like_clauses=like_clauses,
        token_count=len(token_patterns),
    )
    expanded_patterns = query_runtime.expanded_token_patterns(token_patterns, fields_per_token=fields_per_token)
    return token_any_expr, token_all_expr, token_count_expr, expanded_patterns


def build_list_runs_params(
    *,
    normalized_query_lower: str,
    token_patterns_for_run_fields: list[str],
    objective_prefix_pattern: str,
    phase_prefix_pattern: str,
    objective_pattern: str,
    phase_pattern: str,
    normalized_thread_id: str,
    normalized_status: str,
    effective_limit: int,
) -> tuple[Any, ...]:
    return (
        normalized_query_lower,
        *token_patterns_for_run_fields,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        objective_prefix_pattern,
        phase_prefix_pattern,
        objective_pattern,
        phase_pattern,
        *token_patterns_for_run_fields,
        *token_patterns_for_run_fields,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        objective_prefix_pattern,
        phase_prefix_pattern,
        objective_pattern,
        phase_pattern,
        *token_patterns_for_run_fields,
        *token_patterns_for_run_fields,
        normalized_thread_id,
        normalized_thread_id,
        normalized_status,
        normalized_status,
        normalized_query_lower,
        objective_pattern,
        phase_pattern,
        *token_patterns_for_run_fields,
        effective_limit,
    )


def build_find_cards_by_owned_file_params(
    *,
    normalized_lower: str,
    suffix_posix: str,
    suffix_windows: str,
    prefix_posix: str,
    prefix_windows: str,
    normalized_run_id: str,
    normalized_status: str,
    contains_pattern: str,
    effective_limit: int,
) -> tuple[Any, ...]:
    return (
        normalized_lower,
        suffix_posix,
        suffix_windows,
        prefix_posix,
        prefix_windows,
        normalized_run_id,
        normalized_run_id,
        normalized_status,
        normalized_status,
        normalized_lower,
        contains_pattern,
        suffix_posix,
        suffix_windows,
        prefix_posix,
        effective_limit,
    )


def build_list_documents_params(
    *,
    normalized_query_lower: str,
    token_patterns_for_document_fields: list[str],
    query_prefix_pattern: str,
    query_pattern: str,
    run_id: str,
    card_id: str,
    doc_type: str,
    effective_limit: int,
) -> tuple[Any, ...]:
    return (
        normalized_query_lower,
        *token_patterns_for_document_fields,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        query_prefix_pattern,
        query_prefix_pattern,
        query_prefix_pattern,
        query_prefix_pattern,
        query_pattern,
        query_pattern,
        query_pattern,
        query_pattern,
        *token_patterns_for_document_fields,
        *token_patterns_for_document_fields,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        normalized_query_lower,
        query_prefix_pattern,
        query_prefix_pattern,
        query_prefix_pattern,
        query_prefix_pattern,
        query_pattern,
        query_pattern,
        query_pattern,
        query_pattern,
        *token_patterns_for_document_fields,
        *token_patterns_for_document_fields,
        run_id,
        card_id,
        card_id,
        doc_type,
        doc_type,
        normalized_query_lower,
        query_pattern,
        query_pattern,
        query_pattern,
        query_pattern,
        *token_patterns_for_document_fields,
        effective_limit,
    )
