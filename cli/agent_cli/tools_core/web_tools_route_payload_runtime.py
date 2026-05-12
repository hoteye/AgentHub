from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.tools_core.project_loader import PROJECT_ROOT
from cli.agent_cli.tools_core.tool_backend_registry import (
    BACKEND_LOCAL_WEB_SEARCH,
    backend_spec_by_id,
)
from cli.agent_cli.tools_core.tools_helper_runtime import load_project_tool


def normalized_supported_modes(value: Any) -> list[str]:
    if isinstance(value, str):
        text = str(value or "").strip()
        return [text] if text else []
    if not isinstance(value, list | tuple | set):
        return []
    modes: list[str] = []
    for entry in value:
        text = str(entry or "").strip()
        if text and text not in modes:
            modes.append(text)
    return modes


def truthy_payload_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def local_web_search_tools() -> Any:
    web_search_tools_cls = (
        load_project_tool(
            "web_search_tools",
            project_root=PROJECT_ROOT,
            tools_module_file=Path(__file__).resolve(),
        )
    ).WebSearchTools
    policy_path = PROJECT_ROOT / "config" / "web_tools.toml"
    return web_search_tools_cls(policy_path=str(policy_path))


def fallback_after_native_failure_payload(
    exc: Exception,
    *,
    query: str,
    limit: int = 5,
    domains: list[str] | tuple[str, ...] | None = None,
    recency_days: int | None = None,
    market: str | None = None,
    fallback_reason: str,
) -> dict[str, Any]:
    payload = dict(
        local_web_search_tools().web_search(
            query,
            limit=limit,
            domains=list(domains or []) or None,
            recency_days=recency_days,
            market=market,
        )
        or {}
    )
    from cli.agent_cli.providers.openai_client import is_retryable_provider_error

    retryable = is_retryable_provider_error(exc)
    payload["fallback_after_native_failure"] = True
    payload["fallback_reason"] = str(fallback_reason or "").strip()
    payload["native_request_error"] = str(exc).strip() or type(exc).__name__
    payload["native_request_error_type"] = type(exc).__name__
    payload["native_request_retryable"] = retryable
    payload["search_dispatched"] = False
    payload["search_results_received"] = bool(payload.get("results"))
    payload["web_search_outcome"] = "fallback_after_native_failure"
    if payload.get("ok"):
        payload["retryable"] = False
    else:
        payload["retryable"] = bool(payload.get("retryable")) or retryable
    return payload


def looks_like_native_web_search_payload(payload: dict[str, Any]) -> bool:
    engine = str(payload.get("engine") or "").strip().lower()
    if "native_web_search" in engine and not engine.startswith("local_"):
        return True
    if list(payload.get("native_markers") or []):
        return True
    if list(payload.get("server_tool_uses") or []):
        return True
    marker_types = [
        str(entry or "").strip().lower() for entry in list(payload.get("marker_types") or [])
    ]
    if "web_search_call" in marker_types:
        return True
    response_block_types = [
        str(entry or "").strip().lower()
        for entry in list(payload.get("response_block_types") or [])
    ]
    return "server_tool_use" in response_block_types


def normalized_web_search_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(value, start=1):
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        rank_value = row.get("rank")
        try:
            rank = int(rank_value)
        except (TypeError, ValueError):
            rank = index
        row["rank"] = rank
        row["title"] = str(row.get("title") or "").strip()
        row["url"] = str(row.get("url") or "").strip()
        row["snippet"] = str(row.get("snippet") or "").strip()
        row["source_domain"] = str(row.get("source_domain") or "").strip()
        rows.append(row)
    return rows


def canonical_web_search_source_evidence(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_rows: list[dict[str, Any]] = []
    for entry in list(results or []):
        if not isinstance(entry, dict):
            continue
        evidence_rows.append(
            {
                "rank": entry.get("rank"),
                "title": str(entry.get("title") or "").strip(),
                "url": str(entry.get("url") or "").strip(),
                "source_domain": str(entry.get("source_domain") or "").strip(),
            }
        )
    return evidence_rows


def normalized_web_search_result_count(
    payload: dict[str, Any], *, results: list[dict[str, Any]]
) -> int:
    count_value = payload.get("result_count", payload.get("count"))
    try:
        normalized_count = int(count_value)
    except (TypeError, ValueError):
        normalized_count = 0
    if results:
        normalized_count = max(normalized_count, len(results))
    return max(normalized_count, 0)


def canonical_web_search_error_code(payload: dict[str, Any]) -> str:
    for key in ("error_code", "issue", "error"):
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    errors = payload.get("errors")
    if isinstance(errors, list):
        for entry in errors:
            text = str(entry or "").strip()
            if text:
                return text
    return ""


def canonical_web_search_display_message(payload: dict[str, Any], *, ok: bool) -> str:
    if ok:
        for key in ("assistant_text", "text", "summary_text"):
            text = str(payload.get(key) or "").strip()
            if text:
                return text
        return ""
    for key in ("display_message", "error", "issue", "assistant_text", "text", "summary_text"):
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    error_code = canonical_web_search_error_code(payload)
    if error_code:
        return error_code
    return "Web search failed."


def canonicalize_web_search_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(payload or {})
    results = normalized_web_search_results(normalized.get("results"))
    if results:
        normalized["results"] = results
    elif not isinstance(normalized.get("results"), list):
        normalized["results"] = []

    ok = bool(normalized.get("ok"))
    explicit_search_dispatched = truthy_payload_flag(
        normalized.get("search_dispatched", normalized.get("native_dispatch_happened"))
    )
    explicit_search_results_received = truthy_payload_flag(
        normalized.get("search_results_received", normalized.get("usable_results_received"))
    )
    fallback_after_native_failure = bool(
        truthy_payload_flag(normalized.get("fallback_after_native_failure"))
    )
    search_dispatched = (
        explicit_search_dispatched
        if explicit_search_dispatched is not None
        else bool(
            list(normalized.get("native_markers") or [])
            or list(normalized.get("server_tool_uses") or [])
            or list(normalized.get("issued_queries") or [])
            or "web_search_call"
            in [
                str(entry or "").strip().lower()
                for entry in list(normalized.get("marker_types") or [])
            ]
            or "server_tool_use"
            in [
                str(entry or "").strip().lower()
                for entry in list(normalized.get("response_block_types") or [])
            ]
        )
    )
    search_results_received = (
        explicit_search_results_received
        if explicit_search_results_received is not None
        else bool(results)
    )
    native_interrupted = bool(
        truthy_payload_flag(normalized.get("native_interrupted"))
        if truthy_payload_flag(normalized.get("native_interrupted")) is not None
        else (
            looks_like_native_web_search_payload(normalized)
            and search_dispatched
            and not search_results_received
            and not fallback_after_native_failure
            and not ok
        )
    )
    result_count = normalized_web_search_result_count(normalized, results=results)
    source_evidence = canonical_web_search_source_evidence(results)
    normalized["status"] = "success" if ok else "error"
    normalized["result_count"] = result_count
    normalized["count"] = result_count
    normalized["source_evidence"] = source_evidence
    normalized["search_dispatched"] = search_dispatched
    normalized["search_results_received"] = search_results_received
    normalized["native_interrupted"] = native_interrupted
    normalized["fallback_after_native_failure"] = fallback_after_native_failure
    normalized["web_search_outcome"] = str(normalized.get("web_search_outcome") or "").strip() or (
        "fallback_after_native_failure"
        if fallback_after_native_failure
        else (
            "native_interrupted"
            if native_interrupted
            else (
                "search_results_received"
                if search_results_received
                else (
                    "search_dispatched"
                    if search_dispatched
                    else "provider_error_without_search" if not ok else ""
                )
            )
        )
    )
    normalized["display_message"] = canonical_web_search_display_message(normalized, ok=ok)
    if not ok:
        normalized["error_code"] = canonical_web_search_error_code(normalized)
        normalized["retryable"] = bool(normalized.get("retryable")) or bool(
            normalized.get("native_request_retryable")
        )
    elif fallback_after_native_failure:
        normalized["retryable"] = False
    return normalized


def native_web_search_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from cli.agent_cli.providers.anthropic_native_web_search_runtime import (
        native_web_search_payload,
    )

    try:
        return dict(native_web_search_payload(*args, **kwargs) or {})
    except Exception as exc:
        return fallback_after_native_failure_payload(
            exc,
            query=str(kwargs.get("query") or "").strip(),
            limit=int(kwargs.get("limit") or 5),
            domains=kwargs.get("domains"),
            recency_days=kwargs.get("recency_days"),
            market=kwargs.get("market"),
            fallback_reason="anthropic_native_request_failed",
        )


def openai_native_web_search_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from cli.agent_cli.providers.openai_native_web_search_runtime import (
        native_web_search_payload,
    )

    try:
        return dict(native_web_search_payload(*args, **kwargs) or {})
    except Exception as exc:
        return fallback_after_native_failure_payload(
            exc,
            query=str(kwargs.get("query") or "").strip(),
            limit=int(kwargs.get("limit") or 5),
            domains=kwargs.get("domains"),
            recency_days=kwargs.get("recency_days"),
            market=kwargs.get("market"),
            fallback_reason="openai_native_request_failed",
        )


def provider_config_value(
    *,
    provider_config: Any | None,
    provider_config_factory: Callable[[], Any] | None,
) -> Any | None:
    if provider_config is not None:
        return provider_config
    if not callable(provider_config_factory):
        return None
    try:
        return provider_config_factory()
    except Exception:
        return None


def probe_cache_lookup_from_config(config: Any | None) -> Callable[[Any], Any] | None:
    if config is None:
        return None
    lookup = getattr(config, "web_search_probe_cache_lookup", None)
    if callable(lookup):
        return lookup
    cache_entries = getattr(config, "web_search_probe_cache_entries", None)
    if isinstance(cache_entries, dict):

        def _lookup(cache_key: Any) -> Any:
            key_value = ""
            if hasattr(cache_key, "as_lookup_key"):
                try:
                    key_value = str(cache_key.as_lookup_key() or "").strip()
                except Exception:
                    key_value = ""
            if not key_value:
                key_value = str(cache_key or "").strip()
            return cache_entries.get(key_value)

        return _lookup
    return None


def resolve_native_web_search_capability(config: Any) -> Any:
    from cli.agent_cli.providers.tool_specs import resolve_native_web_search_capability

    try:
        return resolve_native_web_search_capability(config)
    except Exception:
        return None


def annotate_web_search_payload(
    payload: dict[str, Any] | None,
    *,
    route: dict[str, Any],
    effective_backend_id: str,
    execution_path: str,
    fallback_reason: str,
    backend_spec_by_id_fn: Callable[..., Any] = backend_spec_by_id,
) -> dict[str, Any]:
    merged = canonicalize_web_search_payload(payload)
    resolved_effective_backend_id = effective_backend_id
    resolved_execution_path = execution_path
    resolved_fallback_reason = str(merged.get("fallback_reason") or fallback_reason or "").strip()
    if bool(merged.get("fallback_after_native_failure")):
        resolved_effective_backend_id = BACKEND_LOCAL_WEB_SEARCH
        resolved_execution_path = "local_fallback"
    effective_spec = backend_spec_by_id_fn(resolved_effective_backend_id)
    merged["fallback_reason"] = resolved_fallback_reason
    merged["web_search_route"] = {
        **route,
        "effective_backend_id": resolved_effective_backend_id,
        "effective_backend_kind": str(getattr(effective_spec, "backend_kind", "") or "").strip()
        or "unknown",
        "execution_path": resolved_execution_path,
        "fallback_reason": resolved_fallback_reason,
    }
    return merged
