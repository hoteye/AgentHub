from __future__ import annotations

from typing import Any


def _compact_argument_map(arguments: dict[str, Any] | None) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in dict(arguments or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compact[key] = value
    return compact


def _query_from_search_queries(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    for entry in value:
        text = str(entry or "").strip()
        if text:
            return text
    return ""


def _query_from_action(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    direct = str(value.get("query") or "").strip()
    if direct:
        return direct
    return _query_from_search_queries(value.get("queries"))


def _query_from_server_tool_input(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("query", "search_query"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def looks_like_web_search_result_payload(arguments: Any) -> bool:
    if not isinstance(arguments, dict):
        return False
    keys = {str(key).strip().lower() for key in arguments.keys()}
    if "web_search_route" in keys:
        return True
    if "query" not in keys:
        return False
    if "action" in keys and isinstance(arguments.get("action"), dict):
        return True
    if "input" in keys and isinstance(arguments.get("input"), dict):
        return True
    return bool(
        keys.intersection(
            {
                "ok",
                "results",
                "count",
                "result_count",
                "source_evidence",
                "error",
                "error_code",
                "errors",
                "display_message",
                "engine",
                "issued_queries",
                "native_markers",
                "server_tool_uses",
                "response_block_types",
            }
        )
    )


def derived_web_search_arguments_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(payload or {})
    query = (
        str(normalized.get("query") or "").strip()
        or _query_from_action(normalized.get("action"))
        or _query_from_server_tool_input(normalized.get("input"))
        or _query_from_search_queries(normalized.get("issued_queries"))
    )
    domains = normalized.get("requested_domains")
    if not isinstance(domains, list):
        domains = normalized.get("applied_domains")
    if not isinstance(domains, list):
        domains = normalized.get("domains")
    if not isinstance(domains, list):
        domains = None
    compact: dict[str, Any] = {}
    for key, value in {
        "query": query or None,
        "limit": normalized.get("limit"),
        "domains": domains,
        "recency_days": (
            normalized.get("applied_recency_days")
            if "applied_recency_days" in normalized
            else normalized.get("recency_days")
        ),
        "market": normalized.get("market"),
    }.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compact[key] = value
    return compact


def derived_web_search_arguments_from_mcp_item(item: dict[str, Any]) -> dict[str, Any]:
    arguments = item.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    structured_content: dict[str, Any] = {}
    result = item.get("result")
    if isinstance(result, dict):
        structured_content = dict(result.get("structured_content") or {})
    payload = {
        "query": structured_content.get("query") or arguments.get("query"),
        "limit": structured_content.get("limit") if "limit" in structured_content else arguments.get("limit"),
        "domains": arguments.get("domains"),
        "requested_domains": structured_content.get("requested_domains"),
        "applied_domains": structured_content.get("applied_domains"),
        "recency_days": arguments.get("recency_days"),
        "applied_recency_days": (
            structured_content.get("applied_recency_days")
            if "applied_recency_days" in structured_content
            else arguments.get("recency_days")
        ),
        "market": structured_content.get("market") if "market" in structured_content else arguments.get("market"),
    }
    return derived_web_search_arguments_from_payload(payload)


def normalized_web_search_mcp_call_arguments(item: dict[str, Any]) -> Any:
    arguments = item.get("arguments")
    if str(item.get("tool") or "").strip() != "web_search":
        return arguments
    if looks_like_web_search_result_payload(arguments):
        derived = derived_web_search_arguments_from_mcp_item(item)
        if derived:
            return derived
    if arguments is None:
        derived = derived_web_search_arguments_from_mcp_item(item)
        if derived:
            return derived
    return arguments


def response_input_item_from_web_search_turn_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if str(item.get("type") or "").strip().lower() != "web_search_call":
        return None
    action = item.get("action")
    payload: dict[str, Any] = {"type": "web_search_call"}
    item_id = str(item.get("id") or "").strip()
    if item_id:
        payload["id"] = item_id
    status = str(item.get("status") or "").strip()
    if status:
        payload["status"] = status
    if isinstance(action, dict) and action:
        payload["action"] = dict(action)
        return payload
    query = derived_web_search_arguments_from_payload(item).get("query")
    if query:
        payload["action"] = {
            "type": "search",
            "query": query,
            "queries": [query],
        }
        return payload
    return payload if len(payload) > 1 else None
