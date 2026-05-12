from __future__ import annotations

from typing import Any


def models_refresh_unavailable_text(*, error: Any) -> str:
    return f"models_refresh\nstatus=provider_catalog_unavailable\nerror={error}"


def models_refresh_usage_error(*, error: str) -> str:
    return f"Usage: /models_refresh [provider]\nerror={error}"


def models_refresh_header_lines(*, provider_filter: str, cache_path: Any) -> list[str]:
    return [
        "models_refresh",
        f"provider_filter={provider_filter or '-'}",
        f"cache_path={cache_path}",
    ]


def models_refresh_skipped_line(*, display_name: str, ttl_seconds: int) -> str:
    return (
        f"- {display_name}: status=skipped, reason=no_catalog_endpoint, "
        f"model_count=0, ttl_seconds={ttl_seconds}"
    )


def models_refresh_fallback_line(
    *,
    display_name: str,
    error: Any,
    model_count: int,
    ttl_seconds: int,
) -> str:
    return (
        f"- {display_name}: status=fallback_cached, error={error}, "
        f"model_count={model_count}, ttl_seconds={ttl_seconds}"
    )


def models_refresh_result_line(
    *,
    display_name: str,
    status: str,
    cache_hit: bool,
    model_count: int,
    ttl_seconds: int,
    error_text: str,
) -> str:
    suffix = f", error={error_text}" if error_text else ""
    return (
        f"- {display_name}: status={status}, cache_hit={'true' if cache_hit else 'false'}, "
        f"model_count={model_count}, ttl_seconds={ttl_seconds}{suffix}"
    )


def models_refresh_summary_lines(
    *,
    providers: int,
    refreshed: int,
    fallback_cached: int,
    skipped: int,
) -> list[str]:
    return [
        f"providers={providers}",
        f"providers_refreshed={refreshed}",
        f"providers_fallback_cached={fallback_cached}",
        f"providers_skipped={skipped}",
    ]


def models_cache_status_unavailable_text(*, error: Any) -> str:
    return f"models_cache_status\nstatus=provider_catalog_unavailable\nerror={error}"


def models_cache_status_usage_error(*, error: str) -> str:
    return f"Usage: /models_cache_status [provider]\nerror={error}"


def models_cache_status_header_lines(*, provider_filter: str, cache_path: Any) -> list[str]:
    return [
        "models_cache_status",
        f"provider_filter={provider_filter or '-'}",
        f"cache_path={cache_path}",
    ]


def models_cache_status_line(
    *,
    display_name: str,
    freshness: str,
    ttl_seconds: int,
    ttl_remaining_seconds: int,
    model_count: int,
    has_endpoint: bool,
) -> str:
    return (
        f"- {display_name}: freshness={freshness}, ttl_seconds={ttl_seconds}, "
        f"ttl_remaining_seconds={ttl_remaining_seconds}, model_count={model_count}, "
        f"catalog_endpoint={'true' if has_endpoint else 'false'}"
    )


def models_cache_status_summary_lines(*, providers: int) -> list[str]:
    return [f"providers={providers}"]


__all__ = [
    "models_cache_status_header_lines",
    "models_cache_status_line",
    "models_cache_status_summary_lines",
    "models_cache_status_unavailable_text",
    "models_cache_status_usage_error",
    "models_refresh_fallback_line",
    "models_refresh_header_lines",
    "models_refresh_result_line",
    "models_refresh_skipped_line",
    "models_refresh_summary_lines",
    "models_refresh_unavailable_text",
    "models_refresh_usage_error",
]
