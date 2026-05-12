from __future__ import annotations

from typing import Any, Mapping


def connector_key(server_name: str) -> str:
    normalized_server_name = str(server_name or "").strip()
    return f"mcp:{normalized_server_name}" if normalized_server_name else "mcp"


def approval_scope(server_name: str) -> str:
    normalized_server_name = str(server_name or "").strip()
    return f"mcp.server:{normalized_server_name}" if normalized_server_name else ""


def approval_metadata(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "required": bool(contract.get("approval_required", True)),
        "family": str(contract.get("approval_family") or "mcp_tool_call"),
        "scope": str(contract.get("approval_scope") or ""),
    }


def call_latency_bucket(latency_ms: int) -> str:
    if latency_ms < 100:
        return "lt_100ms"
    if latency_ms < 500:
        return "100ms_500ms"
    if latency_ms < 1000:
        return "500ms_1s"
    if latency_ms < 5000:
        return "1s_5s"
    return "ge_5s"


def call_decision_outcome(result: Mapping[str, Any]) -> str:
    if bool(result.get("ok")):
        return "approved"
    error_text = " ".join(
        (
            str(result.get("error") or ""),
            str(dict(result.get("result") or {}).get("error") or ""),
        )
    ).strip().lower()
    normalized_error_text = error_text.replace("-", " ").replace("_", " ")
    if "timeout" in normalized_error_text or "timed out" in normalized_error_text:
        return "timed_out"
    if "expired" in normalized_error_text or "expire" in normalized_error_text:
        return "expired"
    return "rejected"
