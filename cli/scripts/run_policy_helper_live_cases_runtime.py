from __future__ import annotations

import json
import os
import shutil
import statistics
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from cli.scripts.run_policy_helper_live_cases_catalog import (
    CASE_META_KEYS,
    PolicyHelperCase,
)


def _overlay_policy_helper_route(
    config: Any,
    *,
    provider: str,
    model: str,
    reasoning_effort: str,
    timeout: int,
) -> Any:
    raw_model = dict(getattr(config, "raw_model", {}) or {})
    raw_model["policy_llm_assist"] = True
    routes = dict(raw_model.get("routes") or {}) if isinstance(raw_model.get("routes"), dict) else {}
    route = dict(routes.get("policy_helper") or {}) if isinstance(routes.get("policy_helper"), dict) else {}
    if provider:
        route["provider"] = str(provider).strip()
    if model:
        route["model"] = str(model).strip()
    if reasoning_effort:
        route["reasoning_effort"] = str(reasoning_effort).strip()
    if timeout > 0:
        route["timeout"] = int(timeout)
    if route:
        routes["policy_helper"] = route
    raw_model["routes"] = routes
    return replace(config, raw_model=raw_model)


def _extract_llm_trace(log_dir: Path) -> dict[str, Any]:
    path = log_dir / "llm_io.jsonl"
    if not path.exists():
        return {"stages": [], "requests": []}
    stages: list[str] = []
    requests: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        item = json.loads(raw_line)
        stage = str(item.get("stage") or "").strip()
        if not stage:
            continue
        stages.append(stage)
        payload = item.get("payload") or {}
        request = payload.get("request") if isinstance(payload, dict) else None
        if not isinstance(request, dict):
            continue
        requests.append(
            {
                "stage": stage,
                "route_name": str(payload.get("route_name") or "").strip(),
                "route_source": str(payload.get("route_source") or "").strip(),
                "provider_name": str(payload.get("provider_name") or "").strip(),
                "base_url": str(payload.get("base_url") or "").strip(),
                "model": str(request.get("model") or "").strip(),
                "message_count": len(list(request.get("messages") or [])) if isinstance(request.get("messages"), list) else 0,
            }
        )
    return {"stages": stages, "requests": requests}


def _route_view(summary: dict[str, Any]) -> dict[str, Any]:
    routes = summary.get("routes")
    if not isinstance(routes, dict):
        return {}
    payload = routes.get("policy_helper")
    if not isinstance(payload, dict):
        return {}
    return {
        "policy_helper": {
            "provider_name": str(payload.get("provider_name") or ""),
            "model": str(payload.get("model") or ""),
            "wire_api": str(payload.get("wire_api") or ""),
            "reasoning_effort": str(payload.get("reasoning_effort") or ""),
            "timeout": payload.get("timeout"),
            "source": str(payload.get("source") or ""),
        }
    }


def _case_result(planner: Any, case: PolicyHelperCase) -> dict[str, Any]:
    if case.phase == "rewrite":
        result = planner._policy_llm_query_rewrite(case.user_text, list(case.heuristic_queries))
    elif case.phase == "rerank":
        result = planner._policy_llm_rerank(case.user_text, [dict(item) for item in case.evidence_blocks])
    elif case.phase == "extract":
        result = planner._policy_llm_extract(case.user_text, [dict(item) for item in case.evidence_blocks])
    else:
        raise RuntimeError(f"unsupported case phase: {case.phase}")
    return dict(result or {})


def _result_preview(result: dict[str, Any]) -> str:
    text = json.dumps(result or {}, ensure_ascii=False)
    return text[:240]


def _has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(_has_non_empty_value(item) for item in value)
    if isinstance(value, dict):
        return any(_has_non_empty_value(item) for item in value.values())
    return True


def _result_has_content(result: dict[str, Any]) -> bool:
    for key, value in dict(result or {}).items():
        if key in CASE_META_KEYS:
            continue
        if _has_non_empty_value(value):
            return True
    return False


def _result_meta(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result or {})
    return {
        "fallback_used": bool(payload.get("fallback_used")),
        "fallback_reason": str(payload.get("fallback_reason") or "").strip(),
        "result_state": str(payload.get("result_state") or "").strip(),
        "quality_state": str(payload.get("quality_state") or "").strip(),
    }


def _route_request_view(trace: dict[str, Any]) -> dict[str, Any]:
    requests = list(trace.get("requests") or [])
    first_request = requests[0] if requests and isinstance(requests[0], dict) else {}
    return {
        "route_name": str(first_request.get("route_name") or "").strip(),
        "route_source": str(first_request.get("route_source") or "").strip(),
        "provider_name": str(first_request.get("provider_name") or "").strip(),
        "base_url": str(first_request.get("base_url") or "").strip(),
        "model": str(first_request.get("model") or "").strip(),
        "message_count": int(first_request.get("message_count") or 0),
    }


def _report_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = len(cases)
    success_count = sum(1 for item in cases if bool(item.get("success")))
    empty_result_count = sum(1 for item in cases if bool(item.get("empty_result")))
    fallback_count = sum(1 for item in cases if bool(item.get("fallback_used")))
    request_count = sum(int(item.get("request_count") or 0) for item in cases)
    wall_values = [int(item.get("wall_ms") or 0) for item in cases if int(item.get("wall_ms") or 0) > 0]
    phase_summary: dict[str, Any] = {}
    for phase in sorted({str(item.get("phase") or "").strip() for item in cases if str(item.get("phase") or "").strip()}):
        phase_cases = [item for item in cases if str(item.get("phase") or "").strip() == phase]
        phase_wall_values = [int(item.get("wall_ms") or 0) for item in phase_cases if int(item.get("wall_ms") or 0) > 0]
        phase_summary[phase] = {
            "cases": len(phase_cases),
            "success_count": sum(1 for item in phase_cases if bool(item.get("success"))),
            "fallback_count": sum(1 for item in phase_cases if bool(item.get("fallback_used"))),
            "empty_result_count": sum(1 for item in phase_cases if bool(item.get("empty_result"))),
            "avg_wall_ms": round(statistics.mean(phase_wall_values), 1) if phase_wall_values else None,
        }
    failure_categories: dict[str, int] = {}
    for item in cases:
        category = str(item.get("failure_category") or "").strip() or "unknown"
        if category in {"none", ""}:
            continue
        failure_categories[category] = int(failure_categories.get(category) or 0) + 1
    human_summary = [
        (
            f"policy-helper live cases success {success_count}/{total_cases} "
            f"(empty={empty_result_count}, fallback={fallback_count})"
        )
    ]
    if failure_categories:
        top_failures = ", ".join(f"{name}:{count}" for name, count in sorted(failure_categories.items()))
        human_summary.append(f"failure categories: {top_failures}")
    return {
        "total_cases": total_cases,
        "success_count": success_count,
        "success_rate": round(success_count / total_cases, 4) if total_cases else 0.0,
        "empty_result_count": empty_result_count,
        "empty_result_rate": round(empty_result_count / total_cases, 4) if total_cases else 0.0,
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_count / total_cases, 4) if total_cases else 0.0,
        "request_count": request_count,
        "avg_wall_ms": round(statistics.mean(wall_values), 1) if wall_values else None,
        "phase_summary": phase_summary,
        "failure_categories": failure_categories,
        "human_summary": human_summary,
    }


def _failure_category(*, success: bool, empty_result: bool, route_request: dict[str, Any], result_meta: dict[str, Any]) -> str:
    if success:
        return "none"
    if empty_result:
        return "empty_response"
    if not str(route_request.get("provider_name") or "").strip() or not str(route_request.get("model") or "").strip():
        return "missing_trace_request"
    if bool(result_meta.get("fallback_used")):
        return "fallback_response"
    quality_state = str(result_meta.get("quality_state") or "").strip().lower()
    if quality_state in {"low_quality", "insufficient"}:
        return "low_quality"
    return "validation_error"


def _run_case(
    planner: Any,
    *,
    case: PolicyHelperCase,
    log_root: Path,
) -> dict[str, Any]:
    case_log_dir = log_root / case.name
    if case_log_dir.exists():
        shutil.rmtree(case_log_dir)
    case_log_dir.mkdir(parents=True, exist_ok=True)

    previous_log_dir = os.environ.get("AGENTHUB_DEBUG_LOG_DIR")
    os.environ["AGENTHUB_DEBUG_LOG_DIR"] = str(case_log_dir)
    started = time.perf_counter()
    try:
        result = _case_result(planner, case)
    finally:
        if previous_log_dir is None:
            os.environ.pop("AGENTHUB_DEBUG_LOG_DIR", None)
        else:
            os.environ["AGENTHUB_DEBUG_LOG_DIR"] = previous_log_dir

    wall_ms = int((time.perf_counter() - started) * 1000)
    trace = _extract_llm_trace(case_log_dir)
    requests = list(trace.get("requests") or [])
    route_request = _route_request_view(trace)
    meta = _result_meta(result)
    empty_result = not _result_has_content(result)
    success = (
        not empty_result
        and bool(route_request.get("provider_name"))
        and bool(route_request.get("model"))
        and len(requests) > 0
    )
    failure_category = _failure_category(
        success=success,
        empty_result=empty_result,
        route_request=route_request,
        result_meta=meta,
    )
    return {
        "name": case.name,
        "phase": case.phase,
        "user_text": case.user_text,
        "result": result,
        "result_preview": _result_preview(result),
        "success": success,
        "empty_result": empty_result,
        "wall_ms": wall_ms,
        "request_count": len(requests),
        "trace_stages": list(trace.get("stages") or []),
        "route_request": route_request,
        "failure_category": failure_category,
        **meta,
        "llm_trace": trace,
        "log_dir": str(case_log_dir),
    }


def _aggregate_profile_summary(run_reports: list[dict[str, Any]]) -> dict[str, Any]:
    all_cases: list[dict[str, Any]] = []
    combo_summary: dict[str, Any] = {}
    for run in run_reports:
        combo = dict(run.get("helper_combo") or {})
        combo_id = str(combo.get("combo_id") or "").strip() or "unknown_combo"
        run_summary = dict(run.get("summary") or {})
        combo_summary[combo_id] = {
            "helper_combo": combo,
            **run_summary,
        }
        for case in list(run.get("cases") or []):
            if not isinstance(case, dict):
                continue
            item = dict(case)
            item["helper_combo_id"] = combo_id
            all_cases.append(item)
    summary = _report_summary(all_cases)
    summary["combo_count"] = len(combo_summary)
    summary["combo_summary"] = combo_summary
    human_summary = list(summary.get("human_summary") or [])
    human_summary.insert(0, f"profile matrix combos={len(combo_summary)}")
    summary["human_summary"] = human_summary
    return summary
