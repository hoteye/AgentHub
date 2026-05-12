from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch

from cli.tests.provider_boundary_test_support import assert_provider_home_env


def _load_probe_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "probe_native_web_search_multi_provider.py"
    spec = importlib.util.spec_from_file_location("probe_native_web_search_multi_provider", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_probe_case_env_overrides_omits_provider_home_when_unset() -> None:
    module = _load_probe_script_module()

    env = module.ProbeCase(provider="openai", model="gpt-5.4").env_overrides()

    assert env == {
        "AGENT_CLI_PROVIDER": "openai",
        "AGENT_CLI_MODEL": "gpt-5.4",
    }


def test_probe_case_env_overrides_enables_strict_isolation_when_provider_home_explicit() -> None:
    module = _load_probe_script_module()

    env = module.ProbeCase(provider="openai", model="gpt-5.4").env_overrides(
        provider_home="/tmp/provider-home"
    )

    assert_provider_home_env(env, "/tmp/provider-home")


def test_common_worker_command_omits_provider_home_when_unset() -> None:
    module = _load_probe_script_module()

    command = module._common_worker_command(
        module.ProbeCase(provider="openai", model="gpt-5.4"),
        query="probe",
        timeout_seconds=5.0,
        provider_home="",
    )

    assert "--provider-home" not in command


def test_worker_uses_unified_provider_management_snapshot(tmp_path: Path) -> None:
    module = _load_probe_script_module()
    stdout = io.StringIO()
    config = SimpleNamespace(
        provider_name="openai",
        wire_api="responses",
        planner_kind="openai_responses",
        base_url="https://relay.example/v1",
        source="project_local",
        model="gpt-5.4",
    )
    snapshot = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=tmp_path / "config.toml",
            auth_path=tmp_path / "auth.json",
            used_project_local=True,
        ),
        selected_config=config,
    )
    capability = SimpleNamespace(
        configurable_modes=("disabled", "cached", "live"),
        supported_modes=("disabled", "cached", "live"),
        requested_mode="live",
        effective_mode="live",
        mode_resolution="backend_default",
        mode_source="backend_default",
        mode_binding="explicit_external_web_access",
        mode_support_level="explicit",
        cached_live_distinct=True,
        mode_fallback_semantics="none",
        backend_notes="",
        main_loop_spec_kind="native",
        native_tool_type="web_search",
    )

    def _fake_snapshot(*, cwd, env_overrides):
        assert cwd == module.CLI_ROOT
        assert env_overrides["AGENT_CLI_PROVIDER"] == "openai"
        assert env_overrides["AGENT_CLI_MODEL"] == "gpt-5.4"
        assert_provider_home_env(env_overrides, tmp_path)
        return snapshot

    with patch("cli.scripts.script_runtime_helpers.load_script_provider_management_snapshot", side_effect=_fake_snapshot):
        with patch("cli.agent_cli.providers.tool_specs.resolve_native_web_search_capability", return_value=capability):
            with patch.object(
                module,
                "_probe_with_loaded_config",
                return_value={
                    "status": "supported",
                    "confidence": "high",
                    "transport_family": "openai_responses",
                    "elapsed_ms": 12,
                    "request_tool_types": ["web_search"],
                    "marker_types": ["web_search_call"],
                    "native_markers": ["web_search_call"],
                },
            ):
                with patch("sys.stdout", stdout):
                    exit_code = module._run_worker(
                        SimpleNamespace(
                            provider="openai",
                            model="gpt-5.4",
                            query="probe",
                            timeout=5.0,
                            provider_home=str(tmp_path),
                        )
                    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["provider_snapshot_source"] == "selected_config"
    assert payload["config_path"] == str(tmp_path / "config.toml")
    assert payload["auth_path"] == str(tmp_path / "auth.json")
    assert payload["used_project_local"] is True
    assert payload["base_url"] == "https://relay.example/v1"
    assert payload["source"] == "project_local"


def test_openai_responses_probe_reuses_runtime_native_web_search_payload() -> None:
    from cli.scripts.probe_native_web_search_backend_probes import _probe_openai_responses

    config = SimpleNamespace(provider_name="openai", model="gpt-5.4")

    def _fake_native_payload(received_config, *, query: str, limit: int):
        assert received_config is config
        assert query == "agenthub probe"
        assert limit == 3
        return {
            "response_id": "resp_123",
            "elapsed_ms": 23,
            "marker_types": ["web_search_call", "message"],
            "native_markers": ["web_search_call"],
            "issued_queries": ["agenthub probe"],
            "text": "probe_ok",
            "issue": "",
            "requested_mode": "cached",
            "effective_mode": "cached",
            "external_web_access": False,
            "web_search_outcome": "search_results_received",
            "search_dispatched": True,
            "search_results_received": True,
        }

    with patch(
        "cli.agent_cli.providers.openai_native_web_search_runtime.native_web_search_payload",
        side_effect=_fake_native_payload,
    ):
        payload = _probe_openai_responses(config, query="agenthub probe", timeout_seconds=5.0)

    assert payload["status"] == "supported"
    assert payload["request_tool_types"] == ["web_search"]
    assert payload["native_markers"] == ["web_search_call"]
    assert payload["requested_mode"] == "cached"
    assert payload["effective_mode"] == "cached"
    assert payload["external_web_access"] is False
    assert payload["search_results_received"] is True


def test_worker_preserves_capability_fields_when_probe_request_errors(tmp_path: Path) -> None:
    module = _load_probe_script_module()
    stdout = io.StringIO()
    snapshot = SimpleNamespace(
        resolution=SimpleNamespace(
            config_path=tmp_path / "config.toml",
            auth_path=tmp_path / "auth.json",
            used_project_local=True,
        ),
        selected_config=SimpleNamespace(
            provider_name="openai",
            wire_api="responses",
            planner_kind="openai_responses",
            base_url="https://gaccode.com/codex/v1",
            source="env",
            model="gpt-5.4",
        ),
    )
    capability = SimpleNamespace(
        configurable_modes=("disabled", "cached", "live"),
        supported_modes=("disabled", "cached", "live"),
        requested_mode="cached",
        effective_mode="cached",
        mode_resolution="backend_default",
        mode_source="backend_default",
        mode_binding="explicit_external_web_access",
        mode_support_level="explicit",
        cached_live_distinct=True,
        mode_fallback_semantics="none",
        backend_notes="",
        main_loop_spec_kind="native",
        native_tool_type="web_search",
    )

    with patch("cli.scripts.script_runtime_helpers.load_script_provider_management_snapshot", return_value=snapshot):
        with patch("cli.agent_cli.providers.tool_specs.resolve_native_web_search_capability", return_value=capability):
            with patch.object(module, "_probe_with_loaded_config", side_effect=RuntimeError("connection reset")):
                with patch("sys.stdout", stdout):
                    exit_code = module._run_worker(
                        SimpleNamespace(
                            provider="openai",
                            model="gpt-5.4",
                            query="probe",
                            timeout=5.0,
                            provider_home=str(tmp_path),
                        )
                    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["status"] == "error"
    assert payload["error_scope"] == "native_web_search_probe_request"
    assert payload["request_tool_types"] == ["web_search"]
    assert payload["requested_mode"] == "cached"
    assert payload["effective_mode"] == "cached"
    assert payload["supported_modes"] == ["disabled", "cached", "live"]
    assert payload["native_tool_type"] == "web_search"


def test_main_uses_runtime_provider_home_without_override() -> None:
    module = _load_probe_script_module()
    stdout = io.StringIO()

    def _fake_run_case_subprocess(case, *, query: str, timeout_seconds: float, provider_home: str):
        del query, timeout_seconds
        assert provider_home == ""
        return {
            "case": case.label,
            "provider": case.provider,
            "model": case.model,
            "status": "supported",
            "confidence": "high",
            "checked_at": "2026-04-12T00:00:00+00:00",
            "configurable_modes": ["disabled", "cached", "live"],
            "supported_modes": ["disabled", "cached", "live"],
            "requested_mode": "live",
            "effective_mode": "live",
            "mode_resolution": "backend_default",
            "mode_source": "backend_default",
            "mode_binding": "explicit_external_web_access",
            "mode_support_level": "explicit",
            "cached_live_distinct": True,
            "mode_fallback_semantics": "none",
            "transport_family": "openai_responses",
            "elapsed_ms": 42,
        }

    with patch.object(module, "_run_case_subprocess", side_effect=_fake_run_case_subprocess):
        with patch.object(
            module,
            "resolve_effective_script_provider_home_dir",
            return_value=Path("/tmp/runtime-provider-home"),
        ):
            with patch("sys.stdout", stdout):
                exit_code = module.main(
                    [
                        "--case",
                        "openai:gpt-5.4",
                        "--max-workers",
                        "1",
                        "--json",
                    ]
                )

    assert exit_code == 0
    report = json.loads(stdout.getvalue())
    assert report["provider_home"] == "/tmp/runtime-provider-home"
    assert report["provider_home_override"] == ""
    assert report["provider_home_source"] == "runtime_default"
    assert report["probe_cache_default_path"] == "/tmp/runtime-provider-home/native_web_search_probe_cache.json"


def test_main_writes_report_and_cache_out_with_same_probe_cache_payload(tmp_path: Path) -> None:
    module = _load_probe_script_module()
    report_path = tmp_path / "probe_report.json"
    cache_path = tmp_path / "probe_cache.json"

    def _fake_run_case_subprocess(case, *, query: str, timeout_seconds: float, provider_home: str):
        del query, timeout_seconds, provider_home
        return {
            "case": case.label,
            "provider": case.provider,
            "model": case.model,
            "provider_name": case.provider,
            "wire_api": "responses",
            "planner_kind": "openai_responses",
            "status": "supported",
            "confidence": "high",
            "checked_at": "2026-04-12T00:00:00+00:00",
            "configurable_modes": ["disabled", "cached", "live"],
            "supported_modes": ["disabled", "cached", "live"],
            "requested_mode": "live",
            "effective_mode": "live",
            "mode_resolution": "backend_default",
            "mode_source": "backend_default",
            "mode_binding": "explicit_external_web_access",
            "mode_support_level": "explicit",
            "cached_live_distinct": True,
            "mode_fallback_semantics": "none",
            "transport_family": "openai_responses",
            "elapsed_ms": 42,
        }

    with patch.object(module, "_run_case_subprocess", side_effect=_fake_run_case_subprocess):
        exit_code = module.main(
            [
                "--case",
                "openai:gpt-5.4",
                "--provider-home",
                str(tmp_path),
                "--out",
                str(report_path),
                "--cache-out",
                str(cache_path),
                "--max-workers",
                "1",
            ]
        )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert report["version"] == "native_web_search_probe_report/v1"
    assert report["probe_cache_schema_version"] == "web_search_probe_cache/v1"
    assert report["tool"] == "web_search"
    assert report["generated_at"]
    assert report["provider_home"] == str(tmp_path)
    assert report["provider_home_override"] == str(tmp_path)
    assert report["provider_home_source"] == "explicit_override"
    assert report["probe_cache_default_filename"] == "native_web_search_probe_cache.json"
    assert report["probe_cache_default_path"] == str(tmp_path / "native_web_search_probe_cache.json")
    assert report["results"][0]["supported_modes"] == ["disabled", "cached", "live"]
    assert report["results"][0]["mode_binding"] == "explicit_external_web_access"
    assert report["results"][0]["mode_support_level"] == "explicit"
    assert report["results"][0]["cached_live_distinct"] is True

    assert report["probe_cache"] == cache_payload
    assert cache_payload["version"] == "web_search_probe_cache/v1"
    assert cache_payload["entry_count"] == 1
    entry = cache_payload["entries"]["openai|gpt-5.4|responses|openai_responses"]
    assert entry["tool"] == "web_search"
    assert entry["capability_key"] == "web_search"
