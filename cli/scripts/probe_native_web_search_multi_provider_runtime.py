from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.scripts.probe_native_web_search_backend_probes import (
    _classify_probe_exception,
    _probe_with_loaded_config,
)
from cli.scripts.probe_native_web_search_cases import ProbeCase
from cli.scripts.script_runtime_helpers import (
    normalize_optional_provider_home_override,
    resolve_effective_script_provider_home_dir,
)

CLI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CLI_ROOT.parent


def ensure_import_paths() -> None:
    for candidate in (str(REPO_ROOT), str(CLI_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


def provider_home_report_fields(
    provider_home: str,
    *,
    cwd: Path = CLI_ROOT,
    resolve_provider_home_dir: Callable[..., Path] = resolve_effective_script_provider_home_dir,
) -> dict[str, str]:
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    return {
        "provider_home": str(
            resolve_provider_home_dir(
                cwd=cwd,
                provider_home=normalized_provider_home,
            )
        ),
        "provider_home_override": normalized_provider_home,
        "provider_home_source": (
            "explicit_override" if normalized_provider_home else "runtime_default"
        ),
    }


def _native_capability_fields(native_capability: Any) -> dict[str, Any]:
    return {
        "configurable_modes": list(getattr(native_capability, "configurable_modes", ()) or []),
        "supported_modes": list(getattr(native_capability, "supported_modes", ()) or []),
        "requested_mode": str(getattr(native_capability, "requested_mode", "") or "").strip(),
        "effective_mode": str(getattr(native_capability, "effective_mode", "") or "").strip(),
        "mode_resolution": str(getattr(native_capability, "mode_resolution", "") or "").strip(),
        "mode_source": str(getattr(native_capability, "mode_source", "") or "").strip(),
        "mode_binding": str(getattr(native_capability, "mode_binding", "") or "").strip(),
        "mode_support_level": str(
            getattr(native_capability, "mode_support_level", "") or ""
        ).strip(),
        "cached_live_distinct": bool(getattr(native_capability, "cached_live_distinct", False)),
        "mode_fallback_semantics": str(
            getattr(native_capability, "mode_fallback_semantics", "") or ""
        ).strip(),
        "backend_notes": str(getattr(native_capability, "backend_notes", "") or "").strip(),
        "main_loop_spec_kind": str(
            getattr(native_capability, "main_loop_spec_kind", "") or ""
        ).strip(),
        "native_tool_type": str(getattr(native_capability, "native_tool_type", "") or "").strip(),
    }


def _set_capability_defaults(payload: dict[str, Any]) -> None:
    for key, default in {
        "requested_mode": "",
        "effective_mode": "",
        "configurable_modes": [],
        "supported_modes": [],
        "mode_resolution": "",
        "mode_source": "",
        "mode_binding": "",
        "mode_support_level": "",
        "cached_live_distinct": False,
        "mode_fallback_semantics": "",
        "backend_notes": "",
        "main_loop_spec_kind": "",
        "native_tool_type": "",
    }.items():
        payload.setdefault(key, default)


def run_worker(
    args: Any,
    *,
    cli_root: Path = CLI_ROOT,
    import_paths_ensurer: Callable[[], None] = ensure_import_paths,
    provider_home_reporter: Callable[[str], dict[str, str]] = provider_home_report_fields,
    probe_runner: Callable[..., dict[str, Any]] = _probe_with_loaded_config,
    classify_probe_exception: Callable[[Exception], tuple[str, str]] = _classify_probe_exception,
) -> int:
    import_paths_ensurer()
    from cli.agent_cli.providers.tool_specs import resolve_native_web_search_capability
    from cli.agent_cli.tools_core.tool_capabilities import utc_now_iso
    from cli.scripts.script_runtime_helpers import load_script_provider_management_snapshot

    case = ProbeCase(provider=str(args.provider).strip(), model=str(args.model).strip())
    if not case.provider or not case.model:
        raise SystemExit("worker requires --provider and --model")
    started_at = time.perf_counter()
    payload: dict[str, Any] = {
        "case": case.label,
        "provider": case.provider,
        "model": case.model,
        "query": str(args.query or "").strip(),
        "checked_at": utc_now_iso(),
        **provider_home_reporter(str(args.provider_home or "")),
    }
    try:
        provider_home_override = normalize_optional_provider_home_override(args.provider_home)
        snapshot = load_script_provider_management_snapshot(
            cwd=cli_root,
            env_overrides=case.env_overrides(provider_home=provider_home_override),
        )
        resolution = snapshot.resolution
        config = snapshot.selected_config
        payload.update(
            {
                "config_path": str(getattr(resolution, "config_path", "") or ""),
                "auth_path": str(getattr(resolution, "auth_path", "") or ""),
                "used_project_local": bool(getattr(resolution, "used_project_local", False)),
                "provider_snapshot_source": "selected_config",
            }
        )
        if config is None:
            payload.update(
                {
                    "status": "error",
                    "confidence": "high",
                    "issue": "provider management snapshot returned no selected_config",
                    "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                }
            )
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        payload.update(
            {
                "provider_name": str(config.provider_name or "").strip(),
                "wire_api": str(config.wire_api or "").strip(),
                "planner_kind": str(config.planner_kind or "").strip(),
                "base_url": str(config.base_url or "").strip(),
                "source": str(config.source or "").strip(),
            }
        )
        native_capability = resolve_native_web_search_capability(config)
        payload.update(_native_capability_fields(native_capability))
        probe_payload = probe_runner(
            config,
            query=str(args.query or "").strip(),
            timeout_seconds=float(args.timeout),
        )
        payload.update(probe_payload)
        payload["elapsed_ms"] = int(
            probe_payload.get("elapsed_ms") or int((time.perf_counter() - started_at) * 1000)
        )
    except Exception as exc:
        status, error_text = classify_probe_exception(exc)
        payload.update(
            {
                "status": status,
                "confidence": "high" if status == "unsupported" else "medium",
                "issue": error_text,
                "error_scope": "native_web_search_probe_request",
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                "checked_at": utc_now_iso(),
                "marker_types": [],
                "native_markers": [],
                "request_tool_types": payload.get("request_tool_types") or ["web_search"],
                "response_id": "",
                "output_preview": "",
                "query_used": "",
                "queries_used": [],
            }
        )
        _set_capability_defaults(payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0
