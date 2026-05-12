from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.agent_cli.tools_core import (
    tool_backend_registry,
    tool_capabilities,
    web_search_probe_cache_runtime,
)
from cli.tests.provider_boundary_test_support import provider_home_env


class WebSearchProbeCacheRuntimeTest(unittest.TestCase):
    def test_default_path_prefers_explicit_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AGENTHUB_WEB_SEARCH_PROBE_CACHE": "/tmp/custom-probe-cache.json",
                **provider_home_env("/tmp/provider-home"),
            },
            clear=False,
        ):
            path = web_search_probe_cache_runtime.default_web_search_probe_cache_path()
        self.assertEqual(path, Path("/tmp/custom-probe-cache.json"))

    def test_default_path_uses_provider_home_when_explicit_missing(self) -> None:
        with patch.dict(
            os.environ,
            provider_home_env("/tmp/provider-home"),
            clear=False,
        ):
            path = web_search_probe_cache_runtime.default_web_search_probe_cache_path()
        self.assertEqual(path, Path("/tmp/provider-home/native_web_search_probe_cache.json"))

    def test_load_entries_supports_nested_probe_cache_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "native_web_search_probe_cache.json"
            expected_key = "foo|bar|openai_chat|openai_chat"
            cache_path.write_text(
                json.dumps(
                    {
                        "probe_cache": {
                            "entries": {
                                expected_key: {
                                    "selected_backend": tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH,
                                    "availability": "unknown",
                                    "confidence": "low",
                                    "checked_at": tool_capabilities.utc_now_iso(),
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            entries = web_search_probe_cache_runtime.load_web_search_probe_cache_entries(cache_path)
        self.assertIn(expected_key, entries)

    def test_default_lookup_reads_entry_using_default_env_path(self) -> None:
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name="custom",
            model="model-x",
            wire_api="openai_chat",
            planner_kind="openai_chat",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "native_web_search_probe_cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "entries": {
                            cache_key.as_lookup_key(): {
                                "selected_backend": tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH,
                                "availability": "unsupported",
                                "confidence": "high",
                                "checked_at": tool_capabilities.utc_now_iso(),
                                "ttl_seconds": 600,
                                "probe_status": "unsupported",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"AGENTHUB_WEB_SEARCH_PROBE_CACHE": str(cache_path)},
                clear=False,
            ):
                loaded = web_search_probe_cache_runtime.default_web_search_probe_cache_lookup(
                    cache_key
                )
        self.assertIsInstance(loaded, dict)
        self.assertEqual(loaded.get("availability"), "unsupported")

    def test_probe_cache_snapshot_returns_none_for_stale_entry(self) -> None:
        snapshot = web_search_probe_cache_runtime.probe_cache_web_search_snapshot(
            provider_name="foo",
            model="bar",
            wire_api="openai_chat",
            planner_kind="openai_chat",
            probe_cache_lookup=lambda _: {
                "selected_backend": tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH,
                "availability": "unknown",
                "confidence": "low",
                "checked_at": "2000-01-01T00:00:00+00:00",
                "ttl_seconds": 60,
                "probe_status": "unknown",
            },
        )
        self.assertIsNone(snapshot)
