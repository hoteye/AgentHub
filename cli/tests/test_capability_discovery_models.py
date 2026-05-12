from __future__ import annotations

import unittest

from cli.agent_cli.tools_core import capability_discovery_models as discovery_models
from cli.agent_cli.tools_core import tool_capabilities


class CapabilityDiscoveryModelsV1Test(unittest.TestCase):
    def test_snapshot_defaults_checked_at_and_projects_to_fact(self) -> None:
        snapshot = discovery_models.capability_snapshot(
            tool="web_search",
            selected_backend="provider_native_openai_responses_web_search",
            availability="supported",
            confidence="high",
            decision_source="static_rule",
            reason="openai_responses_native_supported",
            checked_at=None,
        )

        self.assertTrue(snapshot.checked_at)
        fact = discovery_models.capability_fact_from_snapshot(snapshot)
        self.assertEqual(fact.capability_key, "web_search")
        self.assertEqual(fact.selected_backend, snapshot.selected_backend)
        self.assertEqual(fact.availability, snapshot.availability)
        self.assertEqual(fact.confidence, snapshot.confidence)
        self.assertEqual(fact.decision_source, snapshot.decision_source)
        self.assertEqual(fact.checked_at, snapshot.checked_at)

    def test_probe_cache_key_uses_legacy_lookup_for_web_search(self) -> None:
        cache_key = discovery_models.probe_cache_key(
            provider_name=" OpenAI ",
            model=" GPT-5.4 ",
            wire_api=" OpenAI_Responses ",
            planner_kind=" OpenAI_Responses ",
            tool="web_search",
        )

        self.assertEqual(
            cache_key.as_lookup_key(), "openai|gpt-5.4|openai_responses|openai_responses"
        )

    def test_probe_cache_key_prefixes_non_default_tool(self) -> None:
        cache_key = discovery_models.probe_cache_key(
            provider_name="openai",
            model="gpt-5.4",
            wire_api="responses",
            planner_kind="openai_responses",
            tool="shell",
        )

        self.assertEqual(
            cache_key.as_lookup_key(), "shell|openai|gpt-5.4|responses|openai_responses"
        )

    def test_probe_cache_record_ttl_and_stale_behavior(self) -> None:
        record = discovery_models.probe_cache_record(
            selected_backend="local_web_search",
            availability="unsupported",
            confidence="high",
            checked_at="2026-04-12T00:00:00+00:00",
            ttl_seconds=10,
            probe_status="unsupported",
        )

        self.assertEqual(record.expires_at(), "2026-04-12T00:00:10+00:00")
        self.assertFalse(record.is_stale(now_iso="2026-04-12T00:00:05+00:00"))
        self.assertTrue(record.is_stale(now_iso="2026-04-12T00:00:11+00:00"))

    def test_coerce_probe_cache_record_supports_legacy_shape_without_tool(self) -> None:
        record = discovery_models.coerce_probe_cache_record(
            {
                "selected_backend": "local_web_search",
                "availability": "unsupported",
                "confidence": "high",
                "checked_at": "2026-04-12T00:00:00+00:00",
                "ttl_seconds": 600,
                "probe_status": "unsupported",
                "source": "probe_script",
            },
            default_tool="web_search",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.tool, "web_search")
        self.assertEqual(record.probe_status, "unsupported")

    def test_web_search_facade_keeps_backward_compat_contract(self) -> None:
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name=" OpenAI ",
            model=" GPT-5.4 ",
            wire_api=" responses ",
            planner_kind=" openai_responses ",
        )
        self.assertEqual(cache_key.as_lookup_key(), "openai|gpt-5.4|responses|openai_responses")

        value = tool_capabilities.coerce_web_search_probe_cache_value(
            {
                "selected_backend": "provider_native_openai_responses_web_search",
                "availability": "supported",
                "confidence": "high",
                "checked_at": "2026-04-12T00:00:00+00:00",
                "ttl_seconds": 600,
                "probe_status": "supported",
                "source": "probe_script",
            }
        )
        self.assertIsNotNone(value)
        assert value is not None
        self.assertEqual(value.tool, "web_search")
        self.assertEqual(value.availability, "supported")
        self.assertFalse(value.is_stale(now_iso="2026-04-12T00:05:00+00:00"))
