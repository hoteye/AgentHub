from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


_UNSUPPORTED_ERROR_MARKERS = (
    "unsupported_tool",
    "unknown tool",
    "unknown_tool_type",
    "invalid tool",
    "invalid tools",
    "tool type",
    "web_search is not supported",
    "web search is not supported",
    "not support web_search",
    "does not support tools of type",
    "unknown variant 'web_search'",
    "unknown variant `web_search`",
    "expected `function`",
    "expected 'function'",
)
_CHAT_NATIVE_DENIAL_MARKERS = (
    "don't have access to a native web_search tool",
    "do not have access to a native web_search tool",
    "i don't have access to a native web_search tool",
    "i do not have access to a native web_search tool",
    "i don't have access to web_search",
    "i do not have access to web_search",
    "i don't have access to a web_search tool",
    "i do not have access to a web_search tool",
    "web_search tool is not available",
    "web search tool is not available",
    "native web_search tool is not available",
    "native web search tool is not available",
    "tool is not available in my current environment",
    "i cannot perform web searches directly",
    "i cannot perform this search or any web searches",
    "no native web search capability",
)


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".strip()


def _unsupported_error(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return any(marker in normalized for marker in _UNSUPPORTED_ERROR_MARKERS)


def _classify_probe_exception(exc: Exception) -> tuple[str, str]:
    error_text = _error_text(exc)
    if _unsupported_error(error_text):
        return "unsupported", error_text
    return "error", error_text


def _response_text_preview(value: Any, *, max_chars: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _chat_completions_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise RuntimeError("missing base_url for chat-completions probe")
    if normalized.endswith("/chat/completions"):
        return normalized
    return normalized + "/chat/completions"


def _http_json_post(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {str(api_key or '').strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"url error: {exc.reason}") from exc
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid json response: {exc}") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("non-object json response from provider")
    return decoded


def _probe_openai_responses(
    config,
    *,
    query: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    from cli.agent_cli.providers.openai_native_web_search_runtime import native_web_search_payload

    payload = native_web_search_payload(
        config,
        query=str(query or "").strip(),
        limit=3,
    )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    native_markers = [str(item) for item in list(payload.get("native_markers") or []) if str(item).strip()]
    issued_queries = [str(item) for item in list(payload.get("issued_queries") or []) if str(item).strip()]
    supported = bool(payload.get("search_dispatched"))
    return {
        "status": "supported" if supported else "unknown",
        "confidence": "high" if supported else "low",
        "transport_family": "openai_responses",
        "request_tool_types": ["web_search"],
        "response_id": str(payload.get("response_id") or "").strip(),
        "elapsed_ms": int(payload.get("elapsed_ms") or elapsed_ms),
        "marker_types": [str(item) for item in list(payload.get("marker_types") or []) if str(item).strip()],
        "native_markers": native_markers,
        "query_used": issued_queries[0] if issued_queries else "",
        "queries_used": issued_queries,
        "output_preview": _response_text_preview(payload.get("text")),
        "issue": str(payload.get("issue") or "").strip(),
        "requested_mode": str(payload.get("requested_mode") or "").strip(),
        "effective_mode": str(payload.get("effective_mode") or "").strip(),
        "external_web_access": bool(payload.get("external_web_access")),
        "web_search_outcome": str(payload.get("web_search_outcome") or "").strip(),
        "search_results_received": bool(payload.get("search_results_received")),
    }


def _probe_anthropic_messages(
    config,
    *,
    query: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    del timeout_seconds
    from cli.agent_cli.providers.anthropic_native_web_search_runtime import native_web_search_payload

    started_at = time.perf_counter()
    payload = native_web_search_payload(config, query=query, limit=3)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    marker_types = [str(item) for item in list(payload.get("response_block_types") or []) if str(item).strip()]
    server_tool_uses = [str(item) for item in list(payload.get("server_tool_uses") or []) if str(item).strip()]
    supported = bool(server_tool_uses and "web_search_tool_result" in marker_types)
    return {
        "status": "supported" if supported else "unknown",
        "confidence": "high" if supported else "low",
        "transport_family": "anthropic_messages",
        "request_tool_types": ["web_search_20250305"],
        "response_id": str(payload.get("response_id") or "").strip(),
        "elapsed_ms": int(payload.get("elapsed_ms") or elapsed_ms),
        "marker_types": marker_types,
        "native_markers": server_tool_uses,
        "query_used": str((list(payload.get("issued_queries") or []) or [""])[0] or "").strip(),
        "queries_used": [str(item) for item in list(payload.get("issued_queries") or []) if str(item).strip()],
        "output_preview": _response_text_preview(payload.get("text")),
        "issue": "" if supported else "response accepted but anthropic native markers were incomplete",
    }


def _probe_openai_chat(
    config,
    *,
    query: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    from cli.agent_cli.host_platform import current_host_platform
    from cli.agent_cli.providers.openai_client import build_openai_client
    from cli.agent_cli.providers.tool_specs import merged_provider_tool_specs

    native_spec = next(
        (
            dict(item)
            for item in merged_provider_tool_specs(
                config,
                current_host_platform(),
                plugin_manager_factory=lambda: None,
            )
            if isinstance(item, dict) and str(item.get("type") or "").strip() == "web_search"
        ),
        None,
    )
    if native_spec is None:
        return {
            "status": "no_probe_adapter",
            "confidence": "high",
            "transport_family": "openai_chat",
            "request_tool_types": [],
            "response_id": "",
            "elapsed_ms": 0,
            "marker_types": [],
            "native_markers": [],
            "query_used": "",
            "queries_used": [],
            "output_preview": "",
            "issue": "no native web_search tool spec available for this chat-completions provider",
        }

    client = build_openai_client(config)
    started_at = time.perf_counter()
    response = client.chat.completions.create(
        model=str(config.model or "").strip(),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are running a capability probe for native web search. "
                    "Use the native web_search tool exactly once if it is available. "
                    "After the search completes, reply exactly with: probe_ok"
                ),
            },
            {
                "role": "user",
                "content": f'Search the web for the exact query: "{str(query or "").strip()}"',
            },
        ],
        tools=[native_spec],
        tool_choice="auto",
        timeout=float(timeout_seconds),
        stream=False,
    )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    choice = response.choices[0]
    message = choice.message
    content = str(getattr(message, "content", "") or "").strip()
    tool_calls = list(getattr(message, "tool_calls", []) or [])
    normalized_content = content.lower().replace("`", "")
    denied = any(marker in normalized_content for marker in _CHAT_NATIVE_DENIAL_MARKERS)
    marker_types = ["accepted_native_web_search_spec"]
    if tool_calls:
        marker_types.append("tool_calls")
    return {
        "status": "unsupported" if denied else "unknown",
        "confidence": "medium" if denied else "low",
        "transport_family": "openai_chat",
        "request_tool_types": [str(native_spec.get("type") or "").strip()],
        "response_id": str(getattr(response, "id", "") or "").strip(),
        "elapsed_ms": elapsed_ms,
        "marker_types": marker_types,
        "native_markers": [],
        "query_used": str(query or "").strip(),
        "queries_used": [str(query or "").strip()] if str(query or "").strip() else [],
        "output_preview": _response_text_preview(content),
        "issue": (
            "provider explicitly denied native web_search access in the response"
            if denied
            else "request was accepted but chat-completions response exposed no explicit native-search marker"
        ),
    }


def _probe_deepseek_openai_chat(
    config,
    *,
    query: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        response = _http_json_post(
            url=_chat_completions_url(str(config.base_url or "")),
            api_key=str(config.api_key or ""),
            payload={
                "model": str(config.model or "").strip(),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are running a capability probe for native web search. "
                            "Use the native web_search tool exactly once if it is available. "
                            "After the search completes, reply exactly with: probe_ok"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f'Search the web for the exact query: "{str(query or "").strip()}"',
                    },
                ],
                "tools": [{"type": "web_search"}],
                "tool_choice": "auto",
                "stream": False,
            },
            timeout_seconds=float(timeout_seconds),
        )
    except Exception as exc:
        status, issue = _classify_probe_exception(exc)
        if status == "unsupported":
            return {
                "status": "unsupported",
                "confidence": "high",
                "transport_family": "openai_chat",
                "request_tool_types": ["web_search"],
                "response_id": "",
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "marker_types": ["api_rejected_native_web_search_spec"],
                "native_markers": [],
                "query_used": str(query or "").strip(),
                "queries_used": [str(query or "").strip()] if str(query or "").strip() else [],
                "output_preview": "",
                "issue": issue,
            }
        raise
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    choices = list(response.get("choices") or []) if isinstance(response, dict) else []
    message = dict(choices[0].get("message") or {}) if choices else {}
    content = str(message.get("content") or "").strip()
    tool_calls = list(message.get("tool_calls") or []) if isinstance(message, dict) else []
    normalized_content = content.lower().replace("`", "")
    denied = any(marker in normalized_content for marker in _CHAT_NATIVE_DENIAL_MARKERS)
    accepted = bool(response)
    return {
        "status": "unsupported" if denied else ("unknown" if accepted else "error"),
        "confidence": "medium" if denied else ("low" if accepted else "high"),
        "transport_family": "openai_chat",
        "request_tool_types": ["web_search"],
        "response_id": str(response.get("id") or "").strip(),
        "elapsed_ms": elapsed_ms,
        "marker_types": ["accepted_native_web_search_spec"] + (["tool_calls"] if tool_calls else []),
        "native_markers": [],
        "query_used": str(query or "").strip(),
        "queries_used": [str(query or "").strip()] if str(query or "").strip() else [],
        "output_preview": _response_text_preview(content),
        "issue": (
            "provider explicitly denied native web_search access in the response"
            if denied
            else "provider accepted native web_search probe payload but exposed no explicit native-search marker"
        ),
    }


def _probe_with_loaded_config(
    config,
    *,
    query: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    wire_api = str(config.wire_api or "").strip().lower()
    planner_kind = str(config.planner_kind or "").strip().lower()
    provider_name = str(config.provider_name or "").strip().lower()
    if wire_api == "anthropic_messages" or planner_kind == "anthropic_messages":
        return _probe_anthropic_messages(config, query=query, timeout_seconds=timeout_seconds)
    if wire_api in {"responses", "openai_responses"} or planner_kind == "openai_responses":
        return _probe_openai_responses(config, query=query, timeout_seconds=timeout_seconds)
    if provider_name == "deepseek" and (wire_api in {"openai_chat", "chat_completions"} or planner_kind in {"openai_chat", "deepseek_reasoner"}):
        return _probe_deepseek_openai_chat(config, query=query, timeout_seconds=timeout_seconds)
    if wire_api in {"openai_chat", "chat_completions"} or planner_kind in {"openai_chat", "deepseek_reasoner"}:
        return _probe_openai_chat(config, query=query, timeout_seconds=timeout_seconds)
    return {
        "status": "no_probe_adapter",
        "confidence": "high",
        "transport_family": wire_api or planner_kind or "unknown",
        "request_tool_types": [],
        "response_id": "",
        "elapsed_ms": 0,
        "marker_types": [],
        "native_markers": [],
        "query_used": "",
        "queries_used": [],
        "output_preview": "",
        "issue": f"no native web_search probe adapter for wire_api={wire_api or '-'} planner_kind={planner_kind or '-'}",
    }
