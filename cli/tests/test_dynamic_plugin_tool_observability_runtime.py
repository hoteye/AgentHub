from __future__ import annotations

from cli.agent_cli.app_server_payloads import reference_turn_payload
from cli.agent_cli.models import (
    ToolEvent,
    function_call_input_items_from_turn_events,
    response_items_with_tool_outputs,
    tool_events_to_turn_events,
    tool_output_input_items_from_turn_events,
)
from cli.agent_cli.models_turn_events_runtime import normalized_plugin_observability_from_payload
from cli.agent_cli.ui import transcript_tool_entries_runtime as transcript_runtime


def _plugin_payload(
    *,
    tool_name: str,
    provider_call_id: str,
    canonical_family: str | None = None,
    plugin_name: str = "demo_plugin",
    config_name: str = "demo_plugin@local",
    source_kind: str = "provider_tool",
    tool_capability_kind: str = "local_runtime_tool",
    tool_runtime_binding: str = "plugin_runtime",
    canonical_family_source: str = "dynamic",
    canonical_family_owner: str = "demo_plugin",
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    family_name = canonical_family or tool_name
    payload: dict[str, object] = {
        "provider_call_id": provider_call_id,
        "capability_id": f"tool.{tool_name}",
        "tool_name": tool_name,
        "plugin_name": plugin_name,
        "config_name": config_name,
        "source_kind": source_kind,
        "canonical_family": family_name,
        "canonical_family_source": canonical_family_source,
        "canonical_family_owner": canonical_family_owner,
        "tool_capability_kind": tool_capability_kind,
        "tool_runtime_binding": tool_runtime_binding,
        "canonical_family_record": {
            "canonical_family": family_name,
            "family_source": canonical_family_source,
            "family_owner": canonical_family_owner,
            "canonical_tool_names": [tool_name],
            "compatibility_aliases": [],
            "tool_capability_kind": tool_capability_kind,
            "tool_runtime_binding": tool_runtime_binding,
        },
    }
    payload.update(dict(extra or {}))
    return payload


def test_dynamic_plugin_tool_turn_events_preserve_local_runtime_observability_and_projection() -> None:
    tool_event = ToolEvent(
        name="demo_lookup",
        ok=True,
        summary="Found 2 matches",
        payload=_plugin_payload(
            tool_name="demo_lookup",
            provider_call_id="call_demo_lookup_1",
            extra={
                "result": {
                    "query": "plugin observability",
                    "matches": ["docs/a.md", "docs/b.md"],
                    "text": "docs/a.md\ndocs/b.md",
                },
                "text": "docs/a.md\ndocs/b.md",
            },
        ),
    )

    turn_events, _ = tool_events_to_turn_events([tool_event])

    started_item = turn_events[0]["item"]
    completed_item = turn_events[1]["item"]
    assert started_item["server"] == "local"
    assert started_item["call_id"] == "call_demo_lookup_1"
    assert started_item["plugin_observability"]["origin"] == "local_runtime"
    assert completed_item["status"] == "completed"
    assert completed_item["plugin_observability"]["canonical_family"] == "demo_lookup"
    assert completed_item["result"]["structured_content"]["status"] == "completed"
    assert completed_item["result"]["structured_content"]["summary"] == "Found 2 matches"
    assert completed_item["result"]["structured_content"]["plugin_capability_declaration"]["canonical_family"] == "demo_lookup"
    assert completed_item["result"]["structured_content"]["structured_payload"] == {
        "query": "plugin observability",
        "matches": ["docs/a.md", "docs/b.md"],
        "text": "docs/a.md\ndocs/b.md",
    }

    projected_items = response_items_with_tool_outputs(
        [],
        turn_events,
        tool_events=[
            ToolEvent(
                name="demo_lookup",
                ok=True,
                summary="Found 2 matches",
                payload={"provider_call_id": "call_demo_lookup_1"},
            )
        ],
    )

    assert [item["type"] for item in projected_items] == ["function_call", "function_call_output"]
    assert projected_items[0]["call_id"] == "call_demo_lookup_1"
    assert projected_items[0]["plugin_observability"]["contract"] == "dynamic_plugin_tool_v1"
    assert projected_items[1]["plugin_observability"]["origin"] == "local_runtime"


def test_dynamic_plugin_tool_turn_events_preserve_provider_native_origin_truth() -> None:
    tool_event = ToolEvent(
        name="plugin_web_search",
        ok=True,
        summary="Returned 1 result",
        payload=_plugin_payload(
            tool_name="plugin_web_search",
            provider_call_id="call_plugin_web_search_1",
            canonical_family="web_search",
            canonical_family_source="builtin",
            canonical_family_owner="builtin",
            tool_capability_kind="provider_native_tool",
            tool_runtime_binding="provider_native",
            extra={
                "result": {
                    "query": "AgentHub plugin tools",
                    "results": [{"title": "AgentHub", "url": "https://example.com/agenthub"}],
                },
            },
        ),
    )

    turn_events, _ = tool_events_to_turn_events([tool_event])
    completed_item = turn_events[1]["item"]

    assert completed_item["server"] == "provider_native"
    assert completed_item["plugin_observability"]["origin"] == "provider_native"
    projected_inputs = function_call_input_items_from_turn_events(turn_events)
    assert projected_inputs[0]["plugin_observability"]["origin"] == "provider_native"


def test_dynamic_plugin_tool_transcript_backfill_preserves_media_observability() -> None:
    tool_event = ToolEvent(
        name="plugin_view_image",
        ok=True,
        summary="Image ready",
        payload=_plugin_payload(
            tool_name="plugin_view_image",
            provider_call_id="call_plugin_view_image_1",
            canonical_family="view_image",
            tool_runtime_binding="shared_media_ingest",
            extra={
                "result": {
                    "requested_path": "diagram.png",
                    "path": "/tmp/diagram.png",
                    "image_artifacts": [
                        {
                            "path": "/tmp/diagram.png",
                            "mime_type": "image/png",
                            "size_bytes": 42,
                            "width": 10,
                            "height": 12,
                            "image_url": "data:image/png;base64,AAA",
                            "detail": "high",
                        }
                    ],
                },
            },
        ),
    )

    turn_events, _ = tool_events_to_turn_events([tool_event])
    completed_item = turn_events[1]["item"]
    transcript_event = transcript_runtime.tool_event_from_turn_tool_item(completed_item)
    assert transcript_event is not None
    assert transcript_event.payload["plugin_observability"]["tool_runtime_binding"] == "shared_media_ingest"
    assert transcript_event.payload["image_artifacts"][0]["path"] == "/tmp/diagram.png"

    projected_outputs = tool_output_input_items_from_turn_events(turn_events)
    assert projected_outputs[0]["plugin_observability"]["canonical_family"] == "view_image"
    assert projected_outputs[0]["plugin_observability"]["origin"] == "local_runtime"


def test_dynamic_plugin_tool_turn_events_fail_closed_without_canonical_structured_payload() -> None:
    tool_event = ToolEvent(
        name="broken_lookup",
        ok=True,
        summary="Lookup finished",
        payload=_plugin_payload(
            tool_name="broken_lookup",
            provider_call_id="call_broken_lookup_1",
        ),
    )

    turn_events, _ = tool_events_to_turn_events([tool_event])
    completed_item = turn_events[1]["item"]

    assert completed_item["status"] == "failed"
    assert completed_item["error"]["message"] == "dynamic plugin tool result missing canonical structured payload"
    assert completed_item["plugin_observability"]["canonical_family"] == "broken_lookup"


def test_dynamic_plugin_tool_app_server_payload_preserves_observable_contract() -> None:
    tool_event = ToolEvent(
        name="demo_lookup",
        ok=True,
        summary="Found 2 matches",
        payload=_plugin_payload(
            tool_name="demo_lookup",
            provider_call_id="call_demo_lookup_1",
            extra={
                "result": {
                    "query": "plugin observability",
                    "matches": ["docs/a.md", "docs/b.md"],
                },
            },
        ),
    )
    turn_events, _ = tool_events_to_turn_events([tool_event])

    payload = reference_turn_payload(
        {
            "turn_id": "turn_plugin_1",
            "status": {},
            "turn_events": turn_events,
        },
        include_items=True,
    )

    item = payload["items"][0]
    assert item["type"] == "mcpToolCall"
    assert item["pluginObservability"]["pluginName"] == "demo_plugin"
    assert item["pluginObservability"]["canonicalFamily"] == "demo_lookup"
    assert item["result"]["structuredContent"]["pluginObservability"]["toolRuntimeBinding"] == "plugin_runtime"
    assert item["result"]["structuredContent"]["structuredPayload"] == {
        "query": "plugin observability",
        "matches": ["docs/a.md", "docs/b.md"],
    }


def test_dynamic_plugin_tool_structured_payload_whitelist_does_not_leak_unknown_metadata_keys() -> None:
    tool_event = ToolEvent(
        name="demo_lookup",
        ok=True,
        summary="Found 2 matches",
        payload=_plugin_payload(
            tool_name="demo_lookup",
            provider_call_id="call_demo_lookup_2",
            extra={
                "result": {
                    "query": "plugin observability",
                    "matches": ["docs/a.md", "docs/b.md"],
                },
                "future_metadata_key": {"debug": True},
                "trace_id": "trace_plugin_1",
            },
        ),
    )

    turn_events, _ = tool_events_to_turn_events([tool_event])
    completed_item = turn_events[1]["item"]

    assert completed_item["status"] == "completed"
    assert completed_item["result"]["structured_content"]["structured_payload"] == {
        "query": "plugin observability",
        "matches": ["docs/a.md", "docs/b.md"],
    }


def test_dynamic_plugin_tool_provider_raw_item_compat_alias_reads_but_emits_canonical_declaration_key() -> None:
    declaration = {
        "capability_id": "tool.demo_lookup",
        "tool_name": "demo_lookup",
        "plugin_name": "demo_plugin",
        "config_name": "demo_plugin@local",
        "source_kind": "provider_tool",
        "canonical_family": "demo_lookup",
        "canonical_family_source": "dynamic",
        "canonical_family_owner": "demo_plugin",
        "tool_capability_kind": "local_runtime_tool",
        "tool_runtime_binding": "plugin_runtime",
        "canonical_family_record": {
            "canonical_family": "demo_lookup",
            "family_source": "dynamic",
            "family_owner": "demo_plugin",
            "canonical_tool_names": ["demo_lookup"],
            "compatibility_aliases": [],
            "tool_capability_kind": "local_runtime_tool",
            "tool_runtime_binding": "plugin_runtime",
        },
    }
    payload = {
        "provider_call_id": "call_demo_lookup_alias_1",
        "provider_raw_item": {"x_agenthub_plugin_capability": declaration},
        "result": {"query": "plugin observability"},
    }

    observable = normalized_plugin_observability_from_payload(payload, tool_name="demo_lookup")
    assert observable is not None
    assert observable["canonical_family"] == "demo_lookup"

    turn_events, _ = tool_events_to_turn_events(
        [
            ToolEvent(
                name="demo_lookup",
                ok=True,
                summary="Found 1 match",
                payload=payload,
            )
        ]
    )
    completed_item = turn_events[1]["item"]

    assert completed_item["status"] == "completed"
    assert completed_item["result"]["structured_content"]["plugin_capability_declaration"]["canonical_family"] == "demo_lookup"
    assert "x_agenthub_plugin_capability" not in completed_item["result"]["structured_content"]
