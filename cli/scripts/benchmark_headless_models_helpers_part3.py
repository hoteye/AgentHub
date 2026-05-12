from __future__ import annotations

SOURCE_PART = r'''        "delegated": delegated,
    }


def _profile_cost_proxy(case_results: list[dict[str, Any]], *, wall_ms: Any) -> dict[str, Any]:
    case_costs = [_case_cost_proxy(item) for item in case_results if isinstance(item, dict)]
    request_count = sum(_int_or_default(item.get("request_count")) for item in case_costs)
    child_turn_count = sum(_int_or_default(item.get("child_turn_count")) for item in case_costs)
    timeout_count = sum(_int_or_default(item.get("timeout_count")) for item in case_costs)
    fallback_count = sum(_int_or_default(item.get("fallback_count")) for item in case_costs)
    delegated_case_count = sum(1 for item in case_costs if bool(item.get("delegated")))
    wall_value = _int_or_none(wall_ms)
    delegation_wall_ms = wall_value if wall_value is not None and delegated_case_count > 0 else 0
    return {
        "request_count": request_count,
        "child_turn_count": child_turn_count,
        "timeout_count": timeout_count,
        "fallback_count": fallback_count,
        "delegated_case_count": delegated_case_count,
        "delegation_wall_ms": delegation_wall_ms,
    }


def _entry_cost_proxy(entry: dict[str, Any]) -> dict[str, int]:
    raw_cost_proxy = entry.get("cost_proxy")
    mapping = raw_cost_proxy if isinstance(raw_cost_proxy, dict) else {}
    request_count = _int_or_default(mapping.get("request_count"))
    child_turn_count = _int_or_default(mapping.get("child_turn_count"))
    timeout_count = _int_or_default(mapping.get("timeout_count"))
    fallback_count = _int_or_default(mapping.get("fallback_count"))
    delegation_wall_ms = _int_or_default(mapping.get("delegation_wall_ms"))
    if bool(entry.get("timeout")):
        timeout_count = max(timeout_count, 1)
    return {
        "request_count": request_count,
        "child_turn_count": child_turn_count,
        "timeout_count": timeout_count,
        "fallback_count": fallback_count,
        "delegation_wall_ms": delegation_wall_ms,
    }


def _cost_proxy_totals_from_summary(summary: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "request_count": sum(_int_or_default(item.get("request_count")) for item in summary),
        "child_turn_count": sum(_int_or_default(item.get("child_turn_count")) for item in summary),
        "timeout_count": sum(_int_or_default(item.get("timeout_count")) for item in summary),
        "fallback_count": sum(_int_or_default(item.get("fallback_count")) for item in summary),
        "delegation_wall_ms": sum(_int_or_default(item.get("delegation_wall_ms")) for item in summary),
    }


def _aggregate_failure_categories(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        mapping = row.get("failure_categories")
        if not isinstance(mapping, dict):
            mapping = {}
        for key, value in mapping.items():
            name = str(key or "").strip()
            if not name:
                continue
            totals[name] = int(totals.get(name) or 0) + _int_or_default(value)
        parse_error = str(row.get("parse_error") or "").strip()
        if not parse_error:
            continue
        totals["parse_error"] = int(totals.get("parse_error") or 0) + 1
        parse_error_category = _parse_error_category(row)
        totals[parse_error_category] = int(totals.get(parse_error_category) or 0) + 1
    return totals


def _aggregate_provider_matrix(summary: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    matrix: dict[str, dict[str, Any]] = {}
    for row in summary:
        provider = str(row.get("provider") or "").strip() or "-"
        model = str(row.get("model") or "").strip() or "-"
        key = f"{provider}:{model}"
        taxonomy = _failure_taxonomy_from_row(row)
        matrix[key] = {
            "provider": provider,
            "model": model,
            "runs": _int_or_default(row.get("runs")),
            "successful_runs": _int_or_default(row.get("successful_runs")),
            "cases_run": _int_or_default(row.get("cases_run")),
            "successful_cases": _int_or_default(row.get("successful_cases")),
            "success_rate": row.get("success_rate"),
            "timeout_count": _int_or_default(row.get("timeout_count")),
            "fallback_count": _int_or_default(row.get("fallback_count")),
            "request_count": _int_or_default(row.get("request_count")),
            "failure_total": sum(taxonomy.values()),
            "primary_failure_bucket": _primary_failure_bucket(taxonomy),
            "failure_taxonomy": dict(sorted(taxonomy.items())),
            "failure_taxonomy_summary": _format_failure_taxonomy(taxonomy),
        }
    return dict(sorted(matrix.items()))


def _aggregate_route_matrix(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for row in results:
        routes = row.get("routes")
        if not isinstance(routes, dict):
            continue
        for route_name, payload in routes.items():
            route_key = str(route_name or "").strip()
            if not route_key or not isinstance(payload, dict):
                continue
            provider_name = str(payload.get("provider_name") or "").strip() or "-"
            model = str(payload.get("model") or "").strip() or "-"
            target = f"{provider_name}:{model}"
            route_bucket = matrix.setdefault(route_key, {})
            route_bucket[target] = int(route_bucket.get(target) or 0) + 1
    return {
        route_name: dict(sorted(targets.items()))
        for route_name, targets in sorted(matrix.items())
    }


def _aggregate_failure_categories_by_case(summary: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for row in summary:
        provider = str(row.get("provider") or "").strip() or "-"
        model = str(row.get("model") or "").strip() or "-"
        key = f"{provider}:{model}"
        mapping = row.get("failure_categories")
        if not isinstance(mapping, dict):
            mapping = {}
        normalized: dict[str, int] = {}
        for name, value in mapping.items():
            bucket = str(name or "").strip()
            if not bucket:
                continue
            normalized[bucket] = _int_or_default(value)
        matrix[key] = dict(sorted(normalized.items()))
    return dict(sorted(matrix.items()))


def _failure_taxonomy_bucket(name: str) -> str:
    text = str(name or "").strip().lower()
    if not text:
        return "other"
    if "parse_error" in text:
        return "parse_error"
    if "timeout" in text:
        return "timeout"
    if "fallback" in text:
        return "fallback"
    if text in {"empty_response", "assistant_text_missing", "empty_result"}:
        return "empty_response"
    if "delegation" in text:
        return "delegation_contract"
    if "orchestration" in text:
        return "orchestration_contract"
    if "trace" in text:
        return "trace_contract"
    if "runtime_exception" in text:
        return "runtime_exception"
    return "other"


def _failure_taxonomy_priority(name: str) -> int:
    priority_order = {
        "delegation_contract": 0,
        "orchestration_contract": 1,
        "trace_contract": 2,
        "timeout": 3,
        "empty_response": 4,
        "fallback": 5,
        "parse_error": 6,
        "runtime_exception": 7,
        "other": 8,
    }
    return int(priority_order.get(str(name or "").strip(), 999))


def _failure_taxonomy_from_row(row: dict[str, Any]) -> dict[str, int]:
    taxonomy: dict[str, int] = {}
    mapping = row.get("failure_categories")
    if not isinstance(mapping, dict):
        mapping = {}
    for name, value in mapping.items():
        bucket = _failure_taxonomy_bucket(str(name or "").strip())
        taxonomy[bucket] = int(taxonomy.get(bucket) or 0) + _int_or_default(value)
    timeout_count = _int_or_default(row.get("timeout_count"))
    fallback_count = _int_or_default(row.get("fallback_count"))
    empty_count = _int_or_default(row.get("empty_response_count"))
    if timeout_count > 0:
        taxonomy["timeout"] = max(timeout_count, int(taxonomy.get("timeout") or 0))
    if fallback_count > 0:
        taxonomy["fallback"] = max(fallback_count, int(taxonomy.get("fallback") or 0))
    if empty_count > 0:
        taxonomy["empty_response"] = max(empty_count, int(taxonomy.get("empty_response") or 0))
    return {key: int(value) for key, value in taxonomy.items() if int(value) > 0}


def _aggregate_failure_taxonomy_by_case(summary: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {}
    for row in summary:
        provider = str(row.get("provider") or "").strip() or "-"
        model = str(row.get("model") or "").strip() or "-"
        key = f"{provider}:{model}"
        matrix[key] = dict(sorted(_failure_taxonomy_from_row(row).items()))
    return dict(sorted(matrix.items()))


def _aggregate_failure_taxonomy_totals(summary: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in summary:
        mapping = _failure_taxonomy_from_row(row)
        for name, value in mapping.items():
            totals[name] = int(totals.get(name) or 0) + _int_or_default(value)
    return dict(sorted(totals.items()))


def _primary_failure_bucket(mapping: dict[str, int]) -> str:
    if not mapping:
        return ""
    best_name = ""
    best_value = -1
    best_priority = 999
    for name, value in mapping.items():
        count = _int_or_default(value)
        priority = _failure_taxonomy_priority(name)
        if count > best_value:
            best_name = name
            best_value = count
            best_priority = priority
            continue
        if count == best_value and priority < best_priority:
            best_name = name
            best_priority = priority
    return best_name


def _format_failure_taxonomy(mapping: dict[str, int]) -> str:
    if not mapping:
        return ""
    items = sorted(
        ((str(name or "").strip(), _int_or_default(value)) for name, value in mapping.items()),
        key=lambda item: (_failure_taxonomy_priority(item[0]), item[0]),
    )
    rendered = [f"{name}:{count}" for name, count in items if name and count > 0]
    return ",".join(rendered)


def _ci_gate_from_summary(summary: list[dict[str, Any]]) -> dict[str, Any]:
    cases_run_total = sum(_int_or_default(item.get("cases_run")) for item in summary)
    successful_cases_total = sum(_int_or_default(item.get("successful_cases")) for item in summary)
    timeout_total = sum(_int_or_default(item.get("timeout_count")) for item in summary)
    fallback_total = sum(_int_or_default(item.get("fallback_count")) for item in summary)
    all_cases_successful = cases_run_total > 0 and successful_cases_total == cases_run_total
    return {
        "cases_run_total": cases_run_total,
        "successful_cases_total": successful_cases_total,
        "timeout_total": timeout_total,
        "fallback_total": fallback_total,
        "all_cases_successful": all_cases_successful,
        "reason": "all_cases_successful" if all_cases_successful else "has_failures_or_empty",
    }


def _ci_reuse_block(*, scenario: str, summary: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_scenario = str(scenario or "").strip()
    ci_gate = _ci_gate_from_summary(summary)
    ci_gate_passed = bool(ci_gate.get("all_cases_successful"))
    ci_gate_reason = str(ci_gate.get("reason") or "")
    return {
        "scenario": normalized_scenario,
        "recommended_command": CI_REUSE_RECOMMENDED_COMMANDS.get(normalized_scenario, ""),
        "ci_gate": ci_gate,
        "ci_gate_passed": ci_gate_passed,
        "ci_gate_reason": ci_gate_reason,
    }


def _parse_error_category(row: dict[str, Any]) -> str:
    stdout_preview = str(row.get("stdout_preview") or "").strip()
    stderr_text = str(row.get("stderr") or "").strip()
    parse_error_text = str(row.get("parse_error") or "").strip().lower()
    if not stdout_preview:
        return "parse_error_empty_stdout"
    combined = "\n".join(part for part in (stdout_preview, stderr_text, parse_error_text) if part).lower()
    if "traceback" in combined or "exception" in combined:
        return "parse_error_runtime_exception"
    if "error" in combined:
        return "parse_error_error_output"
    if stdout_preview.lstrip().startswith("<"):
        return "parse_error_non_json_text"
    return "parse_error_unstructured_output"


def _dry_run_live_case_payload(
    *,
    case: BenchmarkCase,
    provider_home: str,
    command: list[str],
    helper_combo: PolicyHelperCombo | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": case.provider,
        "model": case.model,
        "env": case.env_overrides(provider_home=provider_home),
        "command": command,
    }
    if helper_combo is not None:
        payload["helper_combo"] = helper_combo.as_dict()
        payload["helper_combo_id"] = helper_combo.combo_id
    return payload


def _run_multi_llm_profile(
    case: BenchmarkCase,
    *,
    timeout_seconds: float,
    provider_home: str,
) -> dict[str, Any]:
    env = dict(os.environ)
    env.update(case.env_overrides(provider_home=provider_home))
    command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_multi_llm_live_cases.py"),
        "--provider",
        case.provider,
        "--model",
        case.model,
        "--profile",
        "orchestration_smoke",
        "--strict",
    ]
    started = time.perf_counter()
    entry: dict[str, Any] = {
        "provider": case.provider,
        "model": case.model,
        "command": command,
    }
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        entry["timeout"] = True
        entry["wall_ms"] = int((time.perf_counter() - started) * 1000)
        entry["stdout_preview"] = str(exc.stdout or "").strip()[:400]
        entry["stderr"] = str(exc.stderr or "").strip()[:400]
        _attach_cost_proxy_fields(
            entry,
            {
                "request_count": 0,
                "child_turn_count": 0,
                "timeout_count": 1,
                "fallback_count": 0,
                "delegation_wall_ms": 0,
            },
'''
