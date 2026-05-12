from __future__ import annotations

from typing import Any, Callable, Dict


PROBE_STREAM_MODE = "noop_turn_event_callback"
PROBE_TRANSPORT = "real_provider_send"


def provider_public_name_from_config(
    config: Any,
    *,
    public_provider_name_fn: Callable[..., str],
) -> str:
    return (
        public_provider_name_fn(
            provider_name=str(getattr(config, "provider_name", "") or "").strip(),
            model=str(getattr(config, "model", "") or "").strip(),
            base_url=str(getattr(config, "base_url", "") or "").strip(),
            planner_kind=str(getattr(config, "planner_kind", "") or "").strip(),
        )
        or str(getattr(config, "provider_name", "") or "").strip()
    )


def probe_not_configured_payload(
    *,
    selected_provider: str,
    selected_model: str,
) -> Dict[str, Any]:
    return {
        "provider_name": selected_provider,
        "provider_public_name": selected_provider,
        "provider_model": selected_model,
        "provider_planner_kind": "",
        "probe_status": "unavailable",
        "probe_ok": False,
        "probe_failure_code": "provider_not_configured",
        "probe_failure_reason": "provider configuration could not be resolved",
        "probe_latency_ms": 0,
        "probe_transport": PROBE_TRANSPORT,
        "probe_stream_mode": PROBE_STREAM_MODE,
        "probe_response_preview": "",
    }


def probe_success_payload(
    config: Any,
    *,
    intent: Any,
    latency_ms: int,
    public_provider_name_fn: Callable[..., str],
) -> Dict[str, Any]:
    return {
        "provider_name": str(getattr(config, "provider_name", "") or "").strip(),
        "provider_public_name": provider_public_name_from_config(
            config,
            public_provider_name_fn=public_provider_name_fn,
        ),
        "provider_model": str(getattr(config, "model", "") or "").strip(),
        "provider_planner_kind": str(getattr(config, "planner_kind", "") or "").strip(),
        "probe_status": "available",
        "probe_ok": True,
        "probe_failure_code": "",
        "probe_failure_reason": "",
        "probe_latency_ms": latency_ms,
        "probe_transport": PROBE_TRANSPORT,
        "probe_stream_mode": PROBE_STREAM_MODE,
        "probe_response_preview": str(getattr(intent, "assistant_text", "") or "").strip(),
    }


def probe_failure_payload(
    config: Any,
    *,
    selected_provider: str,
    selected_model: str,
    exc: Exception,
    latency_ms: int,
    public_provider_name_fn: Callable[..., str],
) -> Dict[str, Any]:
    return {
        "provider_name": str(getattr(config, "provider_name", "") or selected_provider).strip(),
        "provider_public_name": provider_public_name_from_config(
            config,
            public_provider_name_fn=public_provider_name_fn,
        ),
        "provider_model": str(getattr(config, "model", "") or selected_model).strip(),
        "provider_planner_kind": str(getattr(config, "planner_kind", "") or "").strip(),
        "probe_status": "unavailable",
        "probe_ok": False,
        "probe_failure_code": type(exc).__name__.lower() or "provider_error",
        "probe_failure_reason": f"{type(exc).__name__}: {exc}",
        "probe_latency_ms": latency_ms,
        "probe_transport": PROBE_TRANSPORT,
        "probe_stream_mode": PROBE_STREAM_MODE,
        "probe_response_preview": "",
    }


def active_provider_identity(
    agent: Any,
    *,
    public_provider_name_fn: Callable[..., str],
    session_provider_env_overrides_fn: Callable[[Any], Dict[str, str | None]],
) -> tuple[str, str]:
    active_provider_name = ""
    active_provider_public_name = ""
    if getattr(agent, "_planner", None) is not None:
        try:
            summary = dict(agent._planner.public_summary() or {})
        except Exception:
            summary = {}
        active_provider_name = str(summary.get("provider_name") or "").strip()
        active_provider_public_name = (
            public_provider_name_fn(
                provider_name=active_provider_name,
                model=str(summary.get("model") or ""),
                base_url=str(summary.get("base_url") or ""),
                planner_kind=str(summary.get("planner_kind") or ""),
            )
            or active_provider_name
        )
    if not active_provider_name:
        active_provider_name = str(
            session_provider_env_overrides_fn(agent).get("AGENT_CLI_PROVIDER") or ""
        ).strip()
    if not active_provider_public_name:
        active_provider_public_name = public_provider_name_fn(provider_name=active_provider_name) or active_provider_name
    return active_provider_name, active_provider_public_name
