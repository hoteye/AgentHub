from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from cli.agent_cli.tools_core import tool_backend_registry
from cli.agent_cli.tools_core import tool_capabilities
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.tools_core.tool_capability_resolver import (
    WebSearchResolverInput,
    resolve_native_web_search_capability,
    resolve_web_search_capability,
)
from cli.tests.provider_boundary_test_support import provider_home_env


class ToolCapabilitiesModelTest(unittest.TestCase):
    def test_capability_snapshot_populates_checked_at_when_missing(self) -> None:
        snapshot = tool_capabilities.capability_snapshot(
            tool="web_search",
            selected_backend=tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH,
            availability="unknown",
            confidence="low",
            decision_source="fallback",
            reason="default_local_fallback",
            checked_at=None,
        )

        self.assertEqual(snapshot.tool, "web_search")
        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "unknown")
        self.assertEqual(snapshot.confidence, "low")
        self.assertEqual(snapshot.decision_source, "fallback")
        self.assertTrue(snapshot.checked_at)

    def test_probe_cache_key_uses_normalized_lookup_string(self) -> None:
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name=" OpenAI ",
            model=" GPT-5.4 ",
            wire_api=" OpenAI_Responses ",
            planner_kind=" OpenAI_Responses ",
        )

        self.assertEqual(cache_key.as_lookup_key(), "openai|gpt-5.4|openai_responses|openai_responses")


class ToolBackendRegistryTest(unittest.TestCase):
    def test_web_search_backends_include_native_and_local_variants(self) -> None:
        backends = tool_backend_registry.web_search_backends()
        backend_ids = {item.backend_id for item in backends}

        self.assertIn(tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH, backend_ids)
        self.assertIn(tool_backend_registry.BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH, backend_ids)
        self.assertIn(tool_backend_registry.BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH, backend_ids)
        self.assertIn(tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH, backend_ids)
        by_id = {backend.backend_id: backend for backend in backends}

        openai = by_id[tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH]
        self.assertEqual(openai.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(openai.supported_modes, ("disabled", "cached", "live"))
        self.assertEqual(openai.default_mode, "cached")
        self.assertEqual(openai.mode_binding, "explicit_external_web_access")
        self.assertEqual(openai.mode_support_level, "explicit")
        self.assertEqual(openai.provider_names, ("openai", "reference"))
        self.assertTrue(openai.cached_live_distinct)

        anthropic = by_id[tool_backend_registry.BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH]
        self.assertEqual(anthropic.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(anthropic.supported_modes, ("disabled", "live"))
        self.assertEqual(anthropic.mode_binding, "native_live_only")
        self.assertEqual(anthropic.mode_support_level, "best_effort")
        self.assertFalse(anthropic.cached_live_distinct)

        glm = by_id[tool_backend_registry.BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH]
        self.assertEqual(glm.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(glm.supported_modes, ("disabled", "live"))
        self.assertEqual(glm.mode_binding, "provider_specific_live_only")
        self.assertEqual(glm.mode_support_level, "best_effort")
        self.assertFalse(glm.cached_live_distinct)

        local = by_id[tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH]
        self.assertEqual(local.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(local.supported_modes, ("disabled", "live"))
        self.assertEqual(local.mode_binding, "local_live_only")
        self.assertEqual(local.mode_support_level, "fallback_only")
        self.assertFalse(local.cached_live_distinct)

        for backend in (anthropic, glm, local):
            self.assertEqual(backend.default_mode, "live")
        for backend in backends:
            self.assertTrue(backend.mode_binding)
            self.assertTrue(backend.mode_fallback_semantics)

    def test_backend_spec_lookup_returns_match_or_none(self) -> None:
        self.assertIsNotNone(
            tool_backend_registry.backend_spec_by_id(
                tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH
            )
        )
        self.assertIsNone(tool_backend_registry.backend_spec_by_id("missing_backend"))


class WebSearchCapabilityResolverTest(unittest.TestCase):
    def test_resolve_openai_openai_responses_as_native_supported(self) -> None:
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="openai",
                model="gpt-5.4",
                planner_kind="openai_responses",
            )
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "supported")
        self.assertEqual(snapshot.confidence, "high")
        self.assertEqual(snapshot.decision_source, "static_rule")

    def test_resolve_openai_responses_planner_without_whitelisted_provider_name(self) -> None:
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="google_oauth_probe",
                model="gpt-5-codex",
                planner_kind="openai_responses",
                wire_api="",
            )
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "supported")
        self.assertEqual(snapshot.confidence, "high")
        self.assertEqual(snapshot.decision_source, "static_rule")

    def test_resolve_openai_responses_wire_api_without_whitelisted_provider_name(self) -> None:
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="custom_openai_proxy",
                model="gpt-5.4",
                planner_kind="openai_chat",
                wire_api="responses",
            )
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "supported")
        self.assertEqual(snapshot.confidence, "high")
        self.assertEqual(snapshot.decision_source, "static_rule")

    def test_resolve_native_web_search_capability_unifies_openai_runtime_and_main_loop_flags(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
            )
        )

        self.assertEqual(capability.provider_family, "openai_responses")
        self.assertEqual(
            capability.selected_backend,
            tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
        )
        self.assertTrue(capability.supports_runtime_native)
        self.assertFalse(capability.supports_main_loop_native)
        self.assertEqual(capability.main_loop_spec_kind, "function")
        self.assertEqual(capability.native_tool_type, "web_search")
        self.assertEqual(capability.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(capability.supported_modes, ("disabled", "cached", "live"))
        self.assertEqual(capability.default_mode, "cached")
        self.assertEqual(capability.requested_mode, "cached")
        self.assertEqual(capability.effective_mode, "cached")
        self.assertEqual(capability.mode_resolution, "backend_default")
        self.assertEqual(capability.mode_source, "backend_default")
        self.assertEqual(capability.mode_binding, "explicit_external_web_access")
        self.assertEqual(capability.mode_support_level, "explicit")
        self.assertTrue(capability.cached_live_distinct)

    def test_resolve_native_web_search_capability_defaults_to_live_for_danger_full_access(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_provider={"sandbox_mode": "danger-full-access"},
            )
        )

        self.assertEqual(capability.default_mode, "cached")
        self.assertEqual(capability.requested_mode, "cached")
        self.assertEqual(capability.effective_mode, "live")
        self.assertEqual(capability.mode_resolution, "sandbox_promoted")
        self.assertEqual(capability.mode_source, "backend_default")

    def test_resolve_native_web_search_capability_exposes_openai_main_loop_only_with_opt_in(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_model={"native_web_search_mixed_tools": True},
            )
        )

        self.assertTrue(capability.supports_runtime_native)
        self.assertTrue(capability.supports_main_loop_native)
        self.assertEqual(capability.main_loop_spec_kind, "openai_responses_native")

    def test_resolve_native_web_search_capability_reads_provider_mode_override(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_provider={"web_search_mode": "cached"},
            )
        )

        self.assertEqual(capability.requested_mode, "cached")
        self.assertEqual(capability.effective_mode, "cached")
        self.assertEqual(capability.mode_resolution, "exact")
        self.assertEqual(capability.mode_source, "provider.web_search_mode")

    def test_resolve_native_web_search_capability_promotes_cached_to_live_for_danger_full_access(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_provider={"web_search_mode": "cached", "sandbox_mode": "danger-full-access"},
            )
        )

        self.assertEqual(capability.requested_mode, "cached")
        self.assertEqual(capability.effective_mode, "live")
        self.assertEqual(capability.mode_resolution, "sandbox_promoted")
        self.assertEqual(capability.mode_source, "provider.web_search_mode")

    def test_resolve_native_web_search_capability_reads_legacy_bool_override_as_mode(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_provider={"external_web_access": False},
            )
        )

        self.assertEqual(capability.requested_mode, "cached")
        self.assertEqual(capability.effective_mode, "cached")
        self.assertEqual(capability.mode_resolution, "exact")
        self.assertEqual(capability.mode_source, "provider.external_web_access")

    def test_resolve_native_web_search_capability_prefers_model_mode_override(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
                raw_model={"web_search_mode": "disabled"},
                raw_provider={"web_search_mode": "cached"},
            )
        )

        self.assertEqual(capability.requested_mode, "disabled")
        self.assertEqual(capability.effective_mode, "disabled")
        self.assertEqual(capability.mode_resolution, "exact")
        self.assertEqual(capability.mode_source, "model.web_search_mode")
        self.assertFalse(capability.supports_runtime_native)
        self.assertFalse(capability.supports_main_loop_native)
        self.assertFalse(capability.supports_mixed_tools_native)
        self.assertEqual(capability.main_loop_spec_kind, "function")
        self.assertEqual(capability.native_tool_type, "")

    def test_resolve_claude_anthropic_messages_as_native_supported(self) -> None:
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="claude",
                model="claude-3-7-sonnet",
                planner_kind="anthropic_messages",
            )
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "supported")
        self.assertEqual(snapshot.confidence, "high")
        self.assertEqual(snapshot.decision_source, "static_rule")

    def test_resolve_native_web_search_capability_keeps_generic_anthropic_wire_compat_off_runtime_native(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="glm-5",
                api_key="sk-test",
                provider_name="glm-claude-mode",
                planner_kind="anthropic_messages",
                wire_api="anthropic_messages",
            )
        )

        self.assertEqual(capability.provider_family, "anthropic")
        self.assertEqual(
            capability.selected_backend,
            tool_backend_registry.BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
        )
        self.assertFalse(capability.supports_runtime_native)
        self.assertEqual(capability.main_loop_spec_kind, "function")

    def test_resolve_native_web_search_capability_downgrades_anthropic_cached_mode_to_live(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="claude-sonnet-4-6",
                api_key="sk-test",
                provider_name="anthropic",
                planner_kind="anthropic_messages",
                wire_api="anthropic_messages",
                raw_provider={"web_search_mode": "cached"},
            )
        )

        self.assertEqual(capability.provider_family, "anthropic")
        self.assertEqual(
            capability.selected_backend,
            tool_backend_registry.BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
        )
        self.assertEqual(capability.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(capability.supported_modes, ("disabled", "live"))
        self.assertEqual(capability.requested_mode, "cached")
        self.assertEqual(capability.effective_mode, "live")
        self.assertEqual(capability.mode_resolution, "downgraded")
        self.assertEqual(capability.mode_binding, "native_live_only")
        self.assertEqual(capability.mode_support_level, "best_effort")
        self.assertFalse(capability.cached_live_distinct)
        self.assertEqual(capability.mode_fallback_semantics, "cached_requests_downgrade_to_live")

    def test_resolve_deepseek_as_unsupported_with_local_fallback(self) -> None:
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="deepseek",
                model="deepseek-chat",
                planner_kind="deepseek_chat",
            )
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "unsupported")
        self.assertEqual(snapshot.confidence, "high")
        self.assertEqual(snapshot.decision_source, "static_rule")

    def test_resolve_native_web_search_capability_marks_deepseek_as_local_fallback_only(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                wire_api="openai_chat",
                raw_provider={"web_search_mode": "cached"},
            )
        )

        self.assertEqual(capability.provider_family, "local")
        self.assertEqual(capability.selected_backend, tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH)
        self.assertEqual(capability.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(capability.supported_modes, ("disabled", "live"))
        self.assertEqual(capability.requested_mode, "cached")
        self.assertEqual(capability.effective_mode, "live")
        self.assertEqual(capability.mode_resolution, "downgraded")
        self.assertEqual(capability.mode_binding, "local_live_only")
        self.assertEqual(capability.mode_support_level, "fallback_only")
        self.assertFalse(capability.cached_live_distinct)

    def test_resolve_glm_uses_conservative_local_fallback(self) -> None:
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="glm",
                model="glm-4.5",
                planner_kind="openai_chat",
            )
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "unknown")
        self.assertEqual(snapshot.confidence, "low")
        self.assertEqual(snapshot.decision_source, "fallback")

    def test_resolve_native_web_search_capability_marks_glm_as_main_loop_only(self) -> None:
        capability = resolve_native_web_search_capability(
            ProviderConfig(
                model="glm-5",
                api_key="sk-test",
                provider_name="glm",
                planner_kind="openai_chat",
                wire_api="openai_chat",
            )
        )

        self.assertEqual(capability.provider_family, "glm")
        self.assertEqual(capability.selected_backend, tool_backend_registry.BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH)
        self.assertFalse(capability.supports_runtime_native)
        self.assertTrue(capability.supports_main_loop_native)
        self.assertEqual(capability.main_loop_spec_kind, "glm_native")
        self.assertEqual(capability.configurable_modes, ("disabled", "cached", "live"))
        self.assertEqual(capability.supported_modes, ("disabled", "live"))
        self.assertEqual(capability.mode_binding, "provider_specific_live_only")
        self.assertEqual(capability.mode_support_level, "best_effort")
        self.assertFalse(capability.cached_live_distinct)

    def test_resolve_uses_probe_cache_for_unknown_provider(self) -> None:
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name="foo",
            model="bar-1",
            wire_api="openai_chat",
            planner_kind="openai_chat",
        )
        cache_entries = {
            cache_key.as_lookup_key(): {
                "selected_backend": tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH,
                "availability": "unsupported",
                "confidence": "high",
                "checked_at": tool_capabilities.utc_now_iso(),
                "ttl_seconds": 600,
                "reason": "probe_report_native_unsupported",
                "probe_status": "unsupported",
                "source": "probe_script",
            }
        }
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="foo",
                model="bar-1",
                wire_api="openai_chat",
                planner_kind="openai_chat",
            ),
            probe_cache_lookup=lambda key: cache_entries.get(key.as_lookup_key()),
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "unsupported")
        self.assertEqual(snapshot.confidence, "high")
        self.assertEqual(snapshot.decision_source, "probe_cache")
        self.assertEqual(snapshot.cache_key, cache_key.as_lookup_key())
        self.assertEqual(snapshot.cache_status, "unsupported")
        self.assertTrue(snapshot.cache_expires_at)
        self.assertEqual(snapshot.cache_source, "probe_script")

    def test_resolve_ignores_stale_probe_cache(self) -> None:
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name="foo",
            model="bar-1",
            wire_api="openai_chat",
            planner_kind="openai_chat",
        )
        cache_entries = {
            cache_key.as_lookup_key(): {
                "selected_backend": tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
                "availability": "supported",
                "confidence": "high",
                "checked_at": "2000-01-01T00:00:00+00:00",
                "ttl_seconds": 60,
                "probe_status": "supported",
            }
        }
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="foo",
                model="bar-1",
                wire_api="openai_chat",
                planner_kind="openai_chat",
            ),
            probe_cache_lookup=lambda key: cache_entries.get(key.as_lookup_key()),
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "unknown")
        self.assertEqual(snapshot.confidence, "low")
        self.assertEqual(snapshot.decision_source, "fallback")

    def test_deepseek_static_rule_beats_probe_cache_override(self) -> None:
        cache_entries = {
            "deepseek|deepseek-chat|openai_chat|deepseek_chat": {
                "selected_backend": tool_backend_registry.BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
                "availability": "supported",
                "confidence": "high",
                "checked_at": tool_capabilities.utc_now_iso(),
                "ttl_seconds": 600,
                "probe_status": "supported",
            }
        }
        snapshot = resolve_web_search_capability(
            WebSearchResolverInput(
                provider_name="deepseek",
                model="deepseek-chat",
                wire_api="openai_chat",
                planner_kind="deepseek_chat",
            ),
            probe_cache_lookup=lambda key: cache_entries.get(key.as_lookup_key()),
        )

        self.assertEqual(snapshot.selected_backend, tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH)
        self.assertEqual(snapshot.availability, "unsupported")
        self.assertEqual(snapshot.confidence, "high")
        self.assertEqual(snapshot.decision_source, "static_rule")

    def test_resolve_uses_default_probe_cache_file_when_env_is_configured(self) -> None:
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name="custom",
            model="model-x",
            wire_api="openai_chat",
            planner_kind="openai_chat",
        )
        cache_payload = {
            "version": "web_search_probe_cache/v1",
            "entries": {
                cache_key.as_lookup_key(): {
                    "selected_backend": tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH,
                    "availability": "unsupported",
                    "confidence": "high",
                    "checked_at": tool_capabilities.utc_now_iso(),
                    "ttl_seconds": 600,
                    "reason": "probe_report_native_unsupported",
                    "probe_status": "unsupported",
                    "source": "probe_script",
                }
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, "native_web_search_probe_cache.json")
            with open(cache_path, "w", encoding="utf-8") as handle:
                json.dump(cache_payload, handle)
            with patch.dict(os.environ, {"AGENTHUB_WEB_SEARCH_PROBE_CACHE": cache_path}, clear=False):
                snapshot = resolve_web_search_capability(
                    WebSearchResolverInput(
                        provider_name="custom",
                        model="model-x",
                        wire_api="openai_chat",
                        planner_kind="openai_chat",
                    )
                )

        self.assertEqual(snapshot.decision_source, "probe_cache")
        self.assertEqual(snapshot.cache_key, cache_key.as_lookup_key())
        self.assertEqual(snapshot.cache_source, "probe_script")

    def test_resolve_uses_provider_home_default_probe_cache_path(self) -> None:
        cache_key = tool_capabilities.web_search_probe_cache_key(
            provider_name="custom",
            model="model-y",
            wire_api="openai_chat",
            planner_kind="openai_chat",
        )
        cache_payload = {
            "version": "web_search_probe_cache/v1",
            "entries": {
                cache_key.as_lookup_key(): {
                    "selected_backend": tool_backend_registry.BACKEND_LOCAL_WEB_SEARCH,
                    "availability": "unsupported",
                    "confidence": "high",
                    "checked_at": tool_capabilities.utc_now_iso(),
                    "ttl_seconds": 600,
                    "reason": "probe_report_native_unsupported",
                    "probe_status": "unsupported",
                    "source": "probe_script",
                }
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = os.path.join(temp_dir, tool_capabilities.DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME)
            with open(cache_path, "w", encoding="utf-8") as handle:
                json.dump(cache_payload, handle)
            with patch.dict(os.environ, provider_home_env(temp_dir), clear=False):
                snapshot = resolve_web_search_capability(
                    WebSearchResolverInput(
                        provider_name="custom",
                        model="model-y",
                        wire_api="openai_chat",
                        planner_kind="openai_chat",
                    )
                )

        self.assertEqual(snapshot.decision_source, "probe_cache")
        self.assertEqual(snapshot.cache_key, cache_key.as_lookup_key())
        self.assertEqual(snapshot.cache_source, "probe_script")
