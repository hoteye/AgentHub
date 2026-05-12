from __future__ import annotations

from typing import Any

_RANKING_WEIGHT_PROFILE = "v1"
_RANKING_ANALYTICS_VERSION = "v1"


def normalized_limit(limit: int, *, default: int, maximum: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, maximum)


def contains_pattern(value: str) -> str:
    return f"%{value}%"


def prefix_pattern(value: str) -> str:
    return f"{value}%"


def normalized_text(value: Any) -> str:
    return str(value or "").strip()


def query_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for token in str(value or "").split():
        item = token.strip().lower()
        if len(item) < 2:
            continue
        if item in seen:
            continue
        seen.add(item)
        tokens.append(item)
    return tokens


def token_match_sql(
    *,
    like_clauses: list[str],
    token_count: int,
) -> tuple[str, str, str]:
    per_token_expr = " OR ".join(like_clauses)
    token_any_expr = " OR ".join([per_token_expr] * token_count) or "0"
    token_all_expr = " AND ".join([f"({per_token_expr})"] * token_count) or "0"
    token_count_expr = " + ".join([f"CASE WHEN {per_token_expr} THEN 1 ELSE 0 END"] * token_count) or "0"
    return token_any_expr, token_all_expr, token_count_expr


def expanded_token_patterns(token_patterns: list[str], *, fields_per_token: int) -> list[str]:
    return [pattern for pattern in token_patterns for _ in range(fields_per_token)]


def token_match_count_from_row(row: dict[str, Any]) -> int:
    value = row.get("token_match_count")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def ranking_quality_score(*, rank_value: int, token_match_count: int, query_token_count: int) -> float:
    rank_base = {
        0: 100.0,
        1: 90.0,
        2: 75.0,
        3: 60.0,
        4: 45.0,
        5: 0.0,
    }.get(rank_value, 0.0)
    if query_token_count <= 0:
        return round(rank_base, 3)
    coverage_ratio = max(0.0, min(1.0, float(token_match_count) / float(query_token_count)))
    return round(rank_base + (coverage_ratio * 20.0), 3)


def ranking_rows_with_analytics(
    rows: list[dict[str, Any]],
    *,
    kind_key: str,
    rank_key: str,
    query_text: str,
    query_scope: str,
    effective_limit: int,
) -> list[dict[str, Any]]:
    total = len(rows)
    tokens = query_tokens(query_text.lower())
    query_token_count = len(tokens)
    query_tokens_text = ",".join(tokens)
    kind_counts: dict[str, int] = {}
    for row in rows:
        kind = normalized_text(row.get(kind_key)) or "none"
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    kind_counts_text = ",".join(f"{kind}:{kind_counts[kind]}" for kind in sorted(kind_counts.keys()))
    kind_order: list[str] = sorted(kind_counts.keys(), key=lambda kind: (-kind_counts[kind], kind))
    kind_position = {kind: index for index, kind in enumerate(kind_order, start=1)}
    kind_seen: dict[str, int] = {}
    scope_summary = (
        f"scope={query_scope};query={'present' if query_text else 'empty'};"
        f"tokens={query_token_count};total={total};limit={effective_limit};kinds={kind_counts_text or 'none'}"
    )

    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item = dict(row)
        primary_kind = normalized_text(item.get(kind_key)) or "none"
        kind_seen[primary_kind] = int(kind_seen.get(primary_kind) or 0) + 1
        item["ranking_query_text"] = query_text
        item["ranking_query_scope"] = query_scope
        item["ranking_result_index"] = index
        item["ranking_result_total"] = total
        item["ranking_effective_limit"] = effective_limit
        item["ranking_primary_match_kind"] = primary_kind
        item["ranking_primary_match_kind_count"] = kind_counts.get(primary_kind, 0)
        item["ranking_match_kind_counts"] = kind_counts_text
        item["ranking_kind_position"] = int(kind_position.get(primary_kind) or 0)
        item["ranking_kind_result_index"] = int(kind_seen.get(primary_kind) or 0)
        item["ranking_query_token_count"] = query_token_count
        item["ranking_query_tokens"] = query_tokens_text
        item["ranking_scope_summary"] = scope_summary
        rank_value = -1
        if rank_key:
            try:
                rank_value = int(item.get(rank_key))
            except (TypeError, ValueError):
                rank_value = -1
            item["ranking_primary_match_rank"] = rank_value
        token_match_count = token_match_count_from_row(item)
        item["ranking_token_match_count"] = token_match_count
        item["ranking_weight_profile"] = _RANKING_WEIGHT_PROFILE
        item["ranking_quality_score"] = ranking_quality_score(
            rank_value=rank_value,
            token_match_count=token_match_count,
            query_token_count=query_token_count,
        )
        if item["ranking_quality_score"] >= 100.0:
            analytics_rank_bucket = "high"
        elif item["ranking_quality_score"] >= 80.0:
            analytics_rank_bucket = "medium"
        else:
            analytics_rank_bucket = "low"
        item["ranking_analytics_version"] = _RANKING_ANALYTICS_VERSION
        item["ranking_analytics_rank_bucket"] = analytics_rank_bucket
        if query_token_count > 0:
            coverage_ratio = round(token_match_count / float(query_token_count), 3)
            item["ranking_token_coverage_ratio"] = coverage_ratio
            item["ranking_quality_summary"] = (
                f"kind={primary_kind};rank={rank_value};"
                f"token_coverage={token_match_count}/{query_token_count};"
                f"coverage_ratio={coverage_ratio};"
                f"weight_profile={_RANKING_WEIGHT_PROFILE};"
                f"quality_score={item['ranking_quality_score']}"
            )
        else:
            item["ranking_token_coverage_ratio"] = None
            item["ranking_quality_summary"] = (
                f"kind={primary_kind};rank={rank_value};token_coverage=0/0;"
                f"weight_profile={_RANKING_WEIGHT_PROFILE};"
                f"quality_score={item['ranking_quality_score']}"
            )
        item["ranking_analytics_summary"] = (
            f"scope={query_scope};version={_RANKING_ANALYTICS_VERSION};"
            f"rank_bucket={analytics_rank_bucket};"
            f"position={index}/{total};"
            f"kind_position={item['ranking_kind_result_index']}/{item['ranking_primary_match_kind_count']};"
            f"query_tokens={query_token_count};"
            f"token_matches={token_match_count};"
            f"quality_score={item['ranking_quality_score']};"
            f"weight_profile={_RANKING_WEIGHT_PROFILE}"
        )
        enriched.append(item)
    return enriched
