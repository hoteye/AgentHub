from __future__ import annotations

from cli.agent_cli.web_search_argument_projection_runtime import (
    derived_web_search_arguments_from_mcp_item,
    derived_web_search_arguments_from_payload,
    looks_like_web_search_result_payload,
    normalized_web_search_mcp_call_arguments,
    response_input_item_from_web_search_turn_item,
)


def test_looks_like_web_search_result_payload_accepts_route_metadata_shape() -> None:
    assert looks_like_web_search_result_payload({"web_search_route": {"selected_backend_id": "x"}}) is True
    assert looks_like_web_search_result_payload({"query": "weather", "ok": True, "results": []}) is True
    assert looks_like_web_search_result_payload({"query": "weather"}) is False


def test_derived_web_search_arguments_from_payload_prefers_canonical_domain_and_recency_fields() -> None:
    assert derived_web_search_arguments_from_payload(
        {
            "query": "beijing weather",
            "limit": 5,
            "requested_domains": ["weather.com"],
            "applied_recency_days": 2,
            "market": "cn",
        }
    ) == {
        "query": "beijing weather",
        "limit": 5,
        "domains": ["weather.com"],
        "recency_days": 2,
        "market": "cn",
    }


def test_derived_web_search_arguments_from_mcp_item_uses_structured_content_with_argument_fallback() -> None:
    item = {
        "arguments": {
            "query": "fallback query",
            "domains": ["fallback.example"],
            "recency_days": 7,
        },
        "result": {
            "structured_content": {
                "query": "resolved query",
                "applied_domains": ["resolved.example"],
                "applied_recency_days": 1,
                "market": "us",
            }
        },
    }
    assert derived_web_search_arguments_from_mcp_item(item) == {
        "query": "resolved query",
        "domains": ["resolved.example"],
        "recency_days": 1,
        "market": "us",
    }


def test_looks_like_web_search_result_payload_accepts_degraded_native_shape_without_results() -> None:
    assert looks_like_web_search_result_payload(
        {
            "query": "北京天气",
            "error_code": "native_web_search_call_missing",
            "native_markers": [],
            "engine": "openai_native_web_search",
        }
    ) is True


def test_derived_web_search_arguments_from_payload_reads_native_and_server_tool_query_shapes() -> None:
    assert derived_web_search_arguments_from_payload(
        {
            "action": {
                "type": "search",
                "queries": ["北京天气", "上海天气"],
            }
        }
    ) == {"query": "北京天气"}
    assert derived_web_search_arguments_from_payload(
        {
            "input": {"search_query": "北京时间"},
            "requested_domains": ["time.example.com"],
        }
    ) == {
        "query": "北京时间",
        "domains": ["time.example.com"],
    }


def test_normalized_web_search_mcp_call_arguments_replaces_result_shaped_arguments() -> None:
    item = {
        "tool": "web_search",
        "arguments": {
            "query": "北京天气",
            "engine": "openai_native_web_search",
            "error_code": "native_web_search_call_missing",
        },
        "result": {
            "structured_content": {
                "query": "北京天气",
                "requested_domains": ["weather.example.com"],
            }
        },
    }

    assert normalized_web_search_mcp_call_arguments(item) == {
        "query": "北京天气",
        "domains": ["weather.example.com"],
    }


def test_response_input_item_from_web_search_turn_item_restores_native_followup_item() -> None:
    assert response_input_item_from_web_search_turn_item(
        {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "completed",
            "query": "北京天气",
        }
    ) == {
        "type": "web_search_call",
        "id": "ws_1",
        "status": "completed",
        "action": {
            "type": "search",
            "query": "北京天气",
            "queries": ["北京天气"],
        },
    }
