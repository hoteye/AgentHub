from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core import provider_commands_status_runtime as provider_status_runtime


def _status_text(status: dict[str, Any], *keys: str) -> str:
    return provider_status_runtime.status_text(status, *keys)


def _status_bool(status: dict[str, Any], key: str) -> bool | None:
    return provider_status_runtime.status_bool(status, key)


def _infer_execution_mode(status: dict[str, Any]) -> str:
    return provider_status_runtime.infer_execution_mode(status)


def _orchestration_reason_surface(status: dict[str, Any]) -> str:
    return provider_status_runtime.orchestration_reason_surface(status)


def _orchestration_budget_surface(status: dict[str, Any]) -> str:
    return provider_status_runtime.orchestration_budget_surface(status)


def _orchestration_route_summary(status: dict[str, Any]) -> str:
    segments: list[str] = []
    for route_name in ("policy_helper", "tool_followup", "final_synthesis"):
        value = str(status.get(f"route_{route_name}") or "").strip()
        if value and value != "-":
            segments.append(f"{route_name}:{value}")
    return "; ".join(segments)


def _orchestration_delegate_summary(status: dict[str, Any]) -> str:
    segments: list[str] = []
    for role_name in ("subagent", "teammate"):
        value = str(status.get(f"delegate_{role_name}") or "").strip()
        if value and value != "-":
            segments.append(f"{role_name}:{value}")
    return "; ".join(segments)


def _orchestration_runtime_summary(status: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "delegated_workflows",
        "orchestration_runs",
        "background_tasks",
        "delegated_result_returned",
        "delegated_result_adopted",
        "background_result_returned",
        "background_result_adopted",
    ):
        value = str(status.get(key) or "").strip()
        if value and value != "-":
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def _provider_readiness_summary(status: dict[str, Any]) -> str:
    provider_ready = _status_bool(status, "provider_ready")
    availability_status = _status_text(status, "availability_status")
    availability_known = _status_bool(status, "availability_known")
    availability_health_bucket = _status_text(status, "availability_health_bucket")
    avg_latency_ms = _status_text(status, "availability_avg_latency_ms")
    last_latency_ms = _status_text(status, "availability_last_latency_ms")
    failure_count = _status_text(status, "availability_failure_count")
    consecutive_failures = _status_text(status, "availability_consecutive_failures")
    parts: list[str] = []
    if provider_ready is not None:
        parts.append(f"provider_ready={'true' if provider_ready else 'false'}")
    if availability_status:
        parts.append(f"availability={availability_status}")
    if availability_known is not None:
        parts.append(f"known={'true' if availability_known else 'false'}")
    if availability_health_bucket:
        parts.append(f"health={availability_health_bucket}")
    if avg_latency_ms:
        parts.append(f"avg_latency_ms={avg_latency_ms}")
    if last_latency_ms:
        parts.append(f"last_latency_ms={last_latency_ms}")
    if failure_count:
        parts.append(f"failure_count={failure_count}")
    if consecutive_failures:
        parts.append(f"consecutive_failures={consecutive_failures}")
    return "; ".join(parts)


def _classify_route_health(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "-":
        return "missing"
    if "availability_fallback=true" in text:
        return "degraded:fallback_main"
    if "source=missing" in text:
        return "missing"
    return "ready"


def _route_health_summary(status: dict[str, Any]) -> str:
    segments: list[str] = []
    counts = {"ready": 0, "degraded": 0, "missing": 0}
    for route_name in ("policy_helper", "tool_followup", "final_synthesis"):
        value = _status_text(status, f"route_{route_name}")
        if not value:
            continue
        health = _classify_route_health(value)
        if health.startswith("ready"):
            counts["ready"] += 1
        elif health.startswith("degraded"):
            counts["degraded"] += 1
        else:
            counts["missing"] += 1
        segments.append(f"{route_name}={health}")
    if not segments:
        return ""
    segments.append(
        f"counts=ready:{counts['ready']},degraded:{counts['degraded']},missing:{counts['missing']}"
    )
    return "; ".join(segments)
