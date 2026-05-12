from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.tool_specs import merged_provider_tool_specs, provider_tool_names
from cli.agent_cli.tools_core import tool_capabilities
from cli.tests.provider_boundary_test_support import PROVIDER_HOME_ENV_KEY, assert_provider_home_env


def _load_snapshot_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "snapshot_unified_tool_layer.py"
    spec = importlib.util.spec_from_file_location("snapshot_unified_tool_layer", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_function_name_from_spec_supports_native_web_search_shape() -> None:
    module = _load_snapshot_script_module()
    name = module._function_name_from_spec(
        {
            "type": "web_search",
            "external_web_access": True,
            "function": {"name": "web_search"},
        }
    )
    assert name == "web_search"


def test_alias_exposure_snapshot_defaults_to_hidden_aliases() -> None:
    module = _load_snapshot_script_module()
    snapshot = module._alias_exposure_snapshot(
        exposed_names={"grep_files", "read_file", "list_dir", "exec_command", "write_stdin", "browser"}
    )
    assert snapshot["file_tools"]["exposed_aliases"] == []
    assert snapshot["shell_tools"]["exposed_aliases"] == []
    assert snapshot["browser_tools"]["exposed_aliases"] == []
    assert snapshot["file_tools"]["alias_hidden_by_default"] is True


def test_alias_exposure_snapshot_detects_alias_override_exposure() -> None:
    module = _load_snapshot_script_module()
    snapshot = module._alias_exposure_snapshot(
        exposed_names={
            "grep_files",
            "read_file",
            "list_dir",
            "file_search",
            "exec_command",
            "write_stdin",
            "shell",
            "browser",
            "open",
        }
    )
    assert snapshot["file_tools"]["exposed_aliases"] == ["file_search"]
    assert snapshot["shell_tools"]["exposed_aliases"] == ["shell"]
    assert snapshot["browser_tools"]["exposed_aliases"] == ["open"]


def test_snapshot_case_env_overrides_omits_provider_home_when_unset() -> None:
    module = _load_snapshot_script_module()

    env = module.SnapshotCase(provider="openai", model="gpt-5.4").env_overrides()

    assert env == {
        "AGENT_CLI_PROVIDER": "openai",
        "AGENT_CLI_MODEL": "gpt-5.4",
    }


def test_snapshot_case_env_overrides_enables_strict_isolation_when_provider_home_explicit() -> None:
    module = _load_snapshot_script_module()

    env = module.SnapshotCase(provider="openai", model="gpt-5.4").env_overrides(
        provider_home="/tmp/provider-home"
    )

    assert_provider_home_env(env, "/tmp/provider-home")


def test_case_snapshot_includes_discovery_and_probe_cache_projection(tmp_path: Path) -> None:
    module = _load_snapshot_script_module()

    class _FakeConfig:
        provider_name = "openai"
        model = "gpt-5.4"
        wire_api = "responses"
        planner_kind = "openai_responses"
        base_url = "https://example.test"
        source = "test"

        @staticmethod
        def public_summary() -> dict[str, str]:
            return {
                "provider_name": "openai",
                "model": "gpt-5.4",
                "wire_api": "responses",
                "planner_kind": "openai_responses",
            }

    capability = tool_capabilities.capability_snapshot(
        tool="web_search",
        selected_backend="provider_native_openai_responses_web_search",
        availability="supported",
        confidence="high",
        decision_source="probe_cache",
        reason="probe_cache_supported",
        checked_at="2026-04-12T00:00:00+00:00",
        cache_key="openai|gpt-5.4|responses|openai_responses",
        cache_status="supported",
        cache_expires_at="2026-04-12T06:00:00+00:00",
        cache_source="probe_script",
    )
    native_capability = {
        "provider_family": "openai_responses",
        "selected_backend": "provider_native_openai_responses_web_search",
        "supports_runtime_native": True,
        "supports_main_loop_native": True,
        "supports_mixed_tools_native": True,
        "main_loop_spec_kind": "openai_responses_native",
        "native_tool_type": "web_search",
        "configurable_modes": ("disabled", "cached", "live"),
        "supported_modes": ("disabled", "cached", "live"),
        "default_mode": "live",
        "requested_mode": "cached",
        "effective_mode": "cached",
        "mode_resolution": "exact",
        "mode_source": "provider.web_search_mode",
        "mode_binding": "explicit_external_web_access",
        "mode_support_level": "explicit",
        "cached_live_distinct": True,
        "mode_fallback_semantics": "none",
        "backend_notes": "OpenAI Responses native web_search backend",
        "availability": "supported",
        "confidence": "high",
        "decision_source": "probe_cache",
        "reason": "probe_cache_supported",
        "checked_at": "2026-04-12T00:00:00+00:00",
        "cache_key": "openai|gpt-5.4|responses|openai_responses",
        "cache_status": "supported",
        "cache_expires_at": "2026-04-12T06:00:00+00:00",
        "cache_source": "probe_script",
    }
    merged_specs = [
        {
            "type": "web_search",
            "external_web_access": False,
            "function": {"name": "web_search"},
        }
    ]
    minimal_specs = [
        {
            "type": "web_search",
            "external_web_access": False,
            "function": {"name": "web_search"},
        }
    ]

    with patch("cli.agent_cli.provider.load_provider_config", return_value=_FakeConfig()):
        with patch("cli.agent_cli.host_platform.current_host_platform", return_value=object()):
            with patch("cli.agent_cli.providers.tool_specs.merged_provider_tool_specs", return_value=merged_specs):
                with patch("cli.agent_cli.providers.tool_specs.responses_minimal_provider_tool_specs", return_value=minimal_specs):
                    with patch("cli.agent_cli.providers.tool_specs.provider_tool_names", return_value=[]):
                        with patch(
                            "cli.agent_cli.tools_core.tool_capability_resolver.resolve_web_search_capability",
                            return_value=capability,
                        ):
                            with patch(
                                "cli.agent_cli.tools_core.tool_capability_resolver.resolve_native_web_search_capability",
                                return_value=SimpleNamespace(**native_capability),
                            ):
                                snapshot = module._case_snapshot(
                                    module.SnapshotCase(provider="openai", model="gpt-5.4"),
                                    provider_home=str(tmp_path),
                                )

    assert snapshot["capability_discovery_snapshot"]["web_search"]["decision_source"] == "probe_cache"
    assert snapshot["native_capability_snapshot"]["web_search"]["decision_source"] == "probe_cache"
    assert snapshot["native_capability_snapshot"]["web_search"]["effective_mode"] == "cached"
    assert snapshot["native_capability_snapshot"]["web_search"]["mode_binding"] == "explicit_external_web_access"
    assert snapshot["web_search_mode_matrix"] == {
        "backend_id": "provider_native_openai_responses_web_search",
        "configurable_modes": ["disabled", "cached", "live"],
        "supported_modes": ["disabled", "cached", "live"],
        "default_mode": "live",
        "requested_mode": "cached",
        "effective_mode": "cached",
        "mode_resolution": "exact",
        "mode_source": "provider.web_search_mode",
        "mode_binding": "explicit_external_web_access",
        "mode_support_level": "explicit",
        "cached_live_distinct": True,
        "mode_fallback_semantics": "none",
        "backend_notes": "OpenAI Responses native web_search backend",
    }
    assert snapshot["web_search_probe_cache"]["cache_key"] == "openai|gpt-5.4|responses|openai_responses"
    assert snapshot["web_search_probe_cache"]["cache_hit"] is True
    assert snapshot["web_search_probe_cache"]["cache_source"] == "probe_script"
    assert snapshot["web_search_probe_cache"]["cache_default_path"] == str(
        tmp_path / "native_web_search_probe_cache.json"
    )
    assert snapshot["provider_web_search_surface"]["merged"] == {
        "name": "web_search",
        "type": "web_search",
        "external_web_access": False,
        "function_name": "web_search",
    }


def test_case_snapshot_uses_runtime_probe_cache_path_without_provider_home_override() -> None:
    module = _load_snapshot_script_module()
    captured: dict[str, object] = {}

    class _FakeConfig:
        provider_name = "openai"
        model = "gpt-5.4"
        wire_api = "responses"
        planner_kind = "openai_responses"
        base_url = "https://example.test"
        source = "test"

        @staticmethod
        def public_summary() -> dict[str, str]:
            return {
                "provider_name": "openai",
                "model": "gpt-5.4",
                "wire_api": "responses",
                "planner_kind": "openai_responses",
            }

    capability = tool_capabilities.capability_snapshot(
        tool="web_search",
        selected_backend="provider_native_openai_responses_web_search",
        availability="supported",
        confidence="high",
        decision_source="probe_cache",
        reason="probe_cache_supported",
        checked_at="2026-04-12T00:00:00+00:00",
        cache_key="openai|gpt-5.4|responses|openai_responses",
        cache_status="supported",
        cache_expires_at="2026-04-12T06:00:00+00:00",
        cache_source="probe_script",
    )
    native_capability = {"selected_backend": "provider_native_openai_responses_web_search"}

    def _fake_load_provider_config(*, cwd, env_overrides):
        del cwd
        captured["env_overrides"] = dict(env_overrides or {})
        return _FakeConfig()

    def _fake_resolve_web_search_capability(*args, **kwargs):
        del args, kwargs
        captured["probe_cache_env"] = os.environ.get("AGENTHUB_WEB_SEARCH_PROBE_CACHE")
        captured["provider_home_env"] = os.environ.get(PROVIDER_HOME_ENV_KEY)
        return capability

    with patch.dict(os.environ, {}, clear=True):
        with patch.object(module, "resolve_effective_script_provider_home_dir", return_value=Path("/tmp/runtime-provider-home")):
            with patch("cli.agent_cli.provider.load_provider_config", side_effect=_fake_load_provider_config):
                with patch("cli.agent_cli.host_platform.current_host_platform", return_value=object()):
                    with patch("cli.agent_cli.providers.tool_specs.merged_provider_tool_specs", return_value=[]):
                        with patch("cli.agent_cli.providers.tool_specs.responses_minimal_provider_tool_specs", return_value=[]):
                            with patch("cli.agent_cli.providers.tool_specs.provider_tool_names", return_value=[]):
                                with patch(
                                    "cli.agent_cli.tools_core.tool_capability_resolver.resolve_web_search_capability",
                                    side_effect=_fake_resolve_web_search_capability,
                                ):
                                    with patch(
                                        "cli.agent_cli.tools_core.tool_capability_resolver.resolve_native_web_search_capability",
                                        return_value=SimpleNamespace(**native_capability),
                                    ):
                                        snapshot = module._case_snapshot(
                                            module.SnapshotCase(provider="openai", model="gpt-5.4"),
                                            provider_home="",
                                        )

    assert captured["env_overrides"] == {
        "AGENT_CLI_PROVIDER": "openai",
        "AGENT_CLI_MODEL": "gpt-5.4",
    }
    assert captured["provider_home_env"] is None
    assert captured["probe_cache_env"] == "/tmp/runtime-provider-home/native_web_search_probe_cache.json"
    assert snapshot["provider_home"] == "/tmp/runtime-provider-home"
    assert snapshot["provider_home_override"] == ""
    assert snapshot["provider_home_source"] == "runtime_default"
    assert snapshot["web_search_probe_cache"]["cache_default_path"] == "/tmp/runtime-provider-home/native_web_search_probe_cache.json"


def test_main_report_uses_runtime_provider_home_without_override() -> None:
    module = _load_snapshot_script_module()
    stdout = io.StringIO()

    with patch.object(module, "resolve_effective_script_provider_home_dir", return_value=Path("/tmp/runtime-provider-home")):
        with patch.object(module, "_canonical_inventory", return_value=[]):
            with patch.object(module, "_case_snapshot", return_value={"case": "openai:gpt-5.4"}):
                with patch("sys.stdout", stdout):
                    exit_code = module.main(["--case", "openai:gpt-5.4", "--json"])

    assert exit_code == 0
    report = json.loads(stdout.getvalue())
    assert report["provider_home"] == "/tmp/runtime-provider-home"
    assert report["provider_home_override"] == ""
    assert report["provider_home_source"] == "runtime_default"


def test_model_facing_tool_surface_hides_web_search_when_mode_disabled() -> None:
    host_platform = detect_host_platform(system_name="Linux", sys_platform="linux")

    enabled_names = provider_tool_names(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
        ),
        host_platform,
        plugin_manager_factory=lambda: None,
    )
    disabled_names = provider_tool_names(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
            raw_provider={"web_search_mode": "disabled"},
        ),
        host_platform,
        plugin_manager_factory=lambda: None,
    )
    disabled_specs = merged_provider_tool_specs(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test-key",
            provider_name="openai",
            planner_kind="openai_responses",
            wire_api="responses",
            raw_provider={"web_search_mode": "disabled"},
        ),
        host_platform,
        plugin_manager_factory=lambda: None,
    )

    assert "web_search" in enabled_names
    assert "web_search" not in disabled_names
    assert all(
        str(item.get("function", {}).get("name") or "").strip() != "web_search"
        for item in disabled_specs
        if isinstance(item, dict)
    )
