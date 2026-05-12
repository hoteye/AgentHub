from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cli.agent_cli.tools_core import (
    tool_backend_registry,
    tool_capabilities,
    web_search_probe_cache_runtime,
)
from cli.scripts import probe_native_web_search_reporting as reporting


class NativeWebSearchProbeReportingTest(unittest.TestCase):
    def test_mode_cell_marks_downgraded_mode(self) -> None:
        self.assertEqual(
            reporting._mode_cell({"requested_mode": "cached", "effective_mode": "live"}),
            "cached->live",
        )
        self.assertEqual(
            reporting._mode_cell({"requested_mode": "live", "effective_mode": "live"}), "live"
        )

    def test_probe_cache_payload_exposes_discovery_v1_metadata(self) -> None:
        checked_at = tool_capabilities.utc_now_iso()
        payload = reporting._probe_cache_payload(
            [
                {
                    "provider_name": "openai",
                    "model": "gpt-5.4",
                    "wire_api": "responses",
                    "planner_kind": "openai_responses",
                    "transport_family": "openai_responses",
                    "status": "supported",
                    "confidence": "high",
                    "checked_at": checked_at,
                    "issue": "",
                }
            ],
            default_ttl_seconds=21600,
        )

        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name="openai",
            model="gpt-5.4",
            wire_api="responses",
            planner_kind="openai_responses",
        ).as_lookup_key()
        self.assertEqual(payload["version"], reporting.PROBE_CACHE_SCHEMA_VERSION)
        self.assertEqual(payload["tool"], reporting.PROBE_TOOL_KEY)
        self.assertEqual(payload["capability_key"], reporting.PROBE_TOOL_KEY)
        self.assertEqual(payload["entry_count"], 1)
        self.assertIn(cache_key, payload["entries"])

        cache_record = payload["entries"][cache_key]
        self.assertEqual(cache_record["tool"], "web_search")
        self.assertEqual(cache_record["capability_key"], "web_search")
        self.assertEqual(
            cache_record["selected_backend"],
            tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
        )

        coerced = tool_capabilities.coerce_web_search_probe_cache_value(cache_record)
        self.assertIsNotNone(coerced)
        assert coerced is not None
        self.assertEqual(coerced.tool, "web_search")
        self.assertEqual(coerced.probe_status, "supported")

    def test_probe_cache_payload_is_runtime_readable(self) -> None:
        checked_at = tool_capabilities.utc_now_iso()
        payload = reporting._probe_cache_payload(
            [
                {
                    "provider_name": "custom",
                    "model": "model-x",
                    "wire_api": "openai_chat",
                    "planner_kind": "openai_chat",
                    "transport_family": "openai_chat",
                    "status": "unsupported",
                    "confidence": "high",
                    "checked_at": checked_at,
                    "issue": "explicitly denied",
                }
            ],
            default_ttl_seconds=900,
        )
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name="custom",
            model="model-x",
            wire_api="openai_chat",
            planner_kind="openai_chat",
        ).as_lookup_key()

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "native_web_search_probe_cache.json"
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            entries = web_search_probe_cache_runtime.load_web_search_probe_cache_entries(cache_path)

        self.assertIn(cache_key, entries)
        self.assertEqual(entries[cache_key]["capability_key"], "web_search")

        snapshot = web_search_probe_cache_runtime.probe_cache_web_search_snapshot(
            provider_name="custom",
            model="model-x",
            wire_api="openai_chat",
            planner_kind="openai_chat",
            probe_cache_lookup=lambda lookup_key: entries.get(lookup_key.as_lookup_key()),
        )

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.decision_source, "probe_cache")
        self.assertEqual(snapshot.cache_source, "probe_script")
        self.assertEqual(snapshot.cache_key, cache_key)
        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH)
        self.assertEqual(snapshot.cache_status, "unsupported")
