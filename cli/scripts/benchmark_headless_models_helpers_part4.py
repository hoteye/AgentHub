from __future__ import annotations

SOURCE_PART = r'''        )
        return entry

    entry["exit_code"] = int(completed.returncode)
    entry["wall_ms"] = int((time.perf_counter() - started) * 1000)
    entry["stderr"] = completed.stderr.strip()[:400]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        entry["parse_error"] = f"{type(exc).__name__}: {exc}"
        entry["parse_error_category"] = _parse_error_category(
            {"parse_error": entry["parse_error"], "stdout_preview": completed.stdout.strip()[:400], "stderr": entry["stderr"]}
        )
        entry["stdout_preview"] = completed.stdout.strip()[:400]
        _attach_cost_proxy_fields(
            entry,
            {
                "request_count": 0,
                "child_turn_count": 0,
                "timeout_count": 0,
                "fallback_count": 0,
                "delegation_wall_ms": 0,
            },
        )
        return entry

    route_view = payload.get("routes") if isinstance(payload.get("routes"), dict) else {}
    case_results = [
        dict(item)
        for item in list(payload.get("cases") or [])
        if isinstance(item, dict)
    ]
    successful = [item for item in case_results if _multi_llm_case_success(item)]
    cost_proxy = _profile_cost_proxy(case_results, wall_ms=entry.get("wall_ms"))
    entry.update(
        {
            "cases_run": len(case_results),
            "successful_cases": len(successful),
            "routes": route_view,
            "summary": dict(payload.get("summary") or {}) if isinstance(payload.get("summary"), dict) else {},
            "failure_categories": dict((payload.get("summary") or {}).get("failure_categories") or {})
            if isinstance(payload.get("summary"), dict)
            else {},
            "results": case_results,
            "assistant_text": " | ".join(
                f"{item.get('name')}: {str(item.get('assistant_text') or '').replace(chr(10), ' ')[:80]}"
                for item in case_results
            )[:240],
        }
    )
    _attach_cost_proxy_fields(entry, cost_proxy)
    return entry


def _run_multi_llm_scenario(
    *,
    args: argparse.Namespace,
    cases: list[BenchmarkCase],
) -> list[dict[str, Any]]:
    timeout_seconds = float(args.timeout)
    if timeout_seconds == float(DEFAULT_TIMEOUT_SECONDS):
        timeout_seconds = float(DEFAULT_MULTI_LLM_TIMEOUT_SECONDS)
    results: list[dict[str, Any]] = []
    for case in cases:
        results.append(
            _run_multi_llm_profile(
                case,
                timeout_seconds=timeout_seconds,
                provider_home=str(args.provider_home),
            )
        )
    return results


def _summarize_multi_llm(results: list[dict[str, Any]], cases: list[BenchmarkCase]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for case in cases:
        rows = [item for item in results if item.get("provider") == case.provider and item.get("model") == case.model]
        total_profiles = len(rows)
        successful_profiles = [
            item
            for item in rows
            if not item.get("timeout")
            and not item.get("parse_error")
            and int(item.get("exit_code", 0) or 0) == 0
            and int(item.get("successful_cases", 0) or 0) == int(item.get("cases_run", 0) or -1)
            and int(item.get("cases_run", 0) or 0) > 0
        ]
        row_cost_proxies = [_entry_cost_proxy(item) for item in rows]
        wall_values = [int(item["wall_ms"]) for item in successful_profiles if isinstance(item.get("wall_ms"), int)]
        delegation_wall_values = [proxy["delegation_wall_ms"] for proxy in row_cost_proxies if proxy["delegation_wall_ms"] > 0]
        cases_run = max((int(item.get("cases_run", 0) or 0) for item in rows), default=0)
        successful_cases = max((int(item.get("successful_cases", 0) or 0) for item in rows), default=0)
        empty_response_count = sum(
            _int_or_default((item.get("summary") or {}).get("empty_response_count"))
            for item in rows
            if isinstance(item.get("summary"), dict)
        )
        summaries.append(
            {
                "provider": case.provider,
                "model": case.model,
                "runs": total_profiles,
                "successful_runs": len(successful_profiles),
                "avg_wall_ms": round(statistics.mean(wall_values), 1) if wall_values else None,
                "cases_run": cases_run,
                "successful_cases": successful_cases,
                "success_rate": round(successful_cases / cases_run, 4) if cases_run > 0 else 0.0,
                "empty_response_count": empty_response_count,
                "timeouts": sum(1 for item in rows if item.get("timeout")),
                "request_count": sum(proxy["request_count"] for proxy in row_cost_proxies),
                "child_turn_count": sum(proxy["child_turn_count"] for proxy in row_cost_proxies),
                "timeout_count": sum(proxy["timeout_count"] for proxy in row_cost_proxies),
                "fallback_count": sum(proxy["fallback_count"] for proxy in row_cost_proxies),
                "delegation_wall_ms": sum(proxy["delegation_wall_ms"] for proxy in row_cost_proxies),
                "avg_delegation_wall_ms": round(statistics.mean(delegation_wall_values), 1) if delegation_wall_values else None,
                "failure_categories": _aggregate_failure_categories(rows),
            }
        )
    return summaries


def _human_summary_from_aggregate(summary: list[dict[str, Any]], *, scenario: str) -> list[str]:
    lines: list[str] = []
    for row in summary:
        helper_combo_id = str(row.get("helper_combo_id") or "").strip()
        taxonomy = _failure_taxonomy_from_row(row)
        primary_failure_bucket = _primary_failure_bucket(taxonomy)
        failure_total = sum(taxonomy.values())
        prefix = f"{scenario}:{row.get('provider')}:{row.get('model')}"
        if helper_combo_id:
            prefix = f"{prefix} helper={helper_combo_id}"
        failure_prefix = "none"
        if failure_total > 0 and primary_failure_bucket:
            failure_prefix = f"{primary_failure_bucket}:{failure_total}"
        failure_taxonomy = _format_failure_taxonomy(taxonomy) or "-"
        lines.append(
            f"{prefix} "
            f"success={row.get('successful_cases', 0)}/{row.get('cases_run', 0)} "
            f"rate={row.get('success_rate', 0.0)} "
            f"timeout={row.get('timeout_count', 0)} "
            f"empty={row.get('empty_response_count', 0)} "
            f"failure={failure_prefix} "
            f"failure_taxonomy={failure_taxonomy} "
            f"avg_wall_ms={row.get('avg_wall_ms') if row.get('avg_wall_ms') is not None else '-'}"
        )
    return lines


def _policy_helper_case_success(case_result: dict[str, Any]) -> bool:
    if not bool(case_result.get("success")):
        return False
    if bool(case_result.get("empty_result")):
        return False
    if str(case_result.get("result_state") or "").strip() == "empty":
        return False
    requests = list((case_result.get("llm_trace") or {}).get("requests") or [])
    if not requests:
        return False
    first_request = requests[0] if isinstance(requests[0], dict) else {}
    return bool(str(first_request.get("provider_name") or "").strip()) and bool(str(first_request.get("model") or "").strip())


def _run_policy_helper_profile(
    case: BenchmarkCase,
    *,
    timeout_seconds: float,
    provider_home: str,
    helper_combo: PolicyHelperCombo,
) -> dict[str, Any]:
    helper_provider = str(helper_combo.provider or "").strip()
    helper_model = str(helper_combo.model or "").strip()
    helper_reasoning_effort = str(helper_combo.reasoning_effort or "").strip()
    helper_timeout = int(helper_combo.timeout or 0)
    env = dict(os.environ)
    env.update(case.env_overrides(provider_home=provider_home))
    command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_policy_helper_live_cases.py"),
        "--provider",
        case.provider,
        "--model",
        case.model,
        "--profile",
        "single",
    ]
    if helper_provider:
        command.extend(["--policy-helper-provider", helper_provider])
    if helper_model:
        command.extend(["--policy-helper-model", helper_model])
    if helper_reasoning_effort:
        command.extend(["--policy-helper-reasoning-effort", helper_reasoning_effort])
    if helper_timeout > 0:
        command.extend(["--policy-helper-timeout", str(helper_timeout)])
    started = time.perf_counter()
    entry: dict[str, Any] = {
        "provider": case.provider,
        "model": case.model,
        "command": command,
        "helper_combo": helper_combo.as_dict(),
        "helper_combo_id": helper_combo.combo_id,
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
        )
        return entry

    entry["exit_code"] = int(completed.returncode)
    entry["wall_ms"] = int((time.perf_counter() - started) * 1000)
    entry["stderr"] = completed.stderr.strip()[:400]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        entry["parse_error"] = f"{type(exc).__name__}: {exc}"
        entry["parse_error_category"] = _parse_error_category(
            {"parse_error": entry["parse_error"], "stdout_preview": completed.stdout.strip()[:400], "stderr": entry["stderr"]}
        )
        entry["stdout_preview"] = completed.stdout.strip()[:400]
        _attach_cost_proxy_fields(
            entry,
            {
                "request_count": 0,
                "child_turn_count": 0,
                "timeout_count": 0,
                "fallback_count": 0,
                "delegation_wall_ms": 0,
            },
        )
        return entry

    route_view = payload.get("routes") if isinstance(payload.get("routes"), dict) else {}
    report_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    case_results = [dict(item) for item in list(payload.get("cases") or []) if isinstance(item, dict)]
    if (not case_results or not route_view) and isinstance(payload.get("runs"), list):
        first_run = payload["runs"][0] if payload["runs"] and isinstance(payload["runs"][0], dict) else {}
        if not route_view and isinstance(first_run.get("routes"), dict):
            route_view = dict(first_run.get("routes") or {})
        if not case_results:
            case_results = [
                dict(item)
                for item in list(first_run.get("cases") or [])
                if isinstance(item, dict)
            ]
        if not report_summary and isinstance(first_run.get("summary"), dict):
            report_summary = dict(first_run.get("summary") or {})
    successful = [item for item in case_results if _policy_helper_case_success(item)]
    cost_proxy = _profile_cost_proxy(case_results, wall_ms=entry.get("wall_ms"))
    entry.update(
        {
            "cases_run": len(case_results),
            "successful_cases": len(successful),
            "routes": route_view,
            "report_summary": report_summary,
            "policy_helper_profile": str(payload.get("profile") or "single"),
            "summary": {
                "empty_response_count": int(report_summary.get("empty_result_count") or 0),
                "failure_categories": dict(report_summary.get("failure_categories") or {}),
            },
            "fallback_cases": int(report_summary.get("fallback_count") or 0),
            "empty_result_cases": int(report_summary.get("empty_result_count") or 0),
            "avg_case_wall_ms": report_summary.get("avg_wall_ms"),
            "results": case_results,
            "failure_categories": dict(report_summary.get("failure_categories") or {}),
            "assistant_text": " | ".join(
                f"{item.get('name')}: {str(item.get('result_preview') or '').replace(chr(10), ' ')[:80]}"
                for item in case_results
            )[:240],
        }
    )
    cost_proxy["fallback_count"] = max(cost_proxy.get("fallback_count", 0), _int_or_default(entry.get("fallback_cases")))
    _attach_cost_proxy_fields(entry, cost_proxy)
    return entry


def _run_policy_helper_scenario(
    *,
    args: argparse.Namespace,
    cases: list[BenchmarkCase],
) -> tuple[str, list[PolicyHelperCombo], list[dict[str, Any]]]:
    timeout_seconds = float(args.timeout)
    if timeout_seconds == float(DEFAULT_TIMEOUT_SECONDS):
        timeout_seconds = float(DEFAULT_MULTI_LLM_TIMEOUT_SECONDS)
    effective_profile, helper_combos = _selected_policy_helper_combos(args)
    results: list[dict[str, Any]] = []
    for case in cases:
        for helper_combo in helper_combos:
            results.append(
                _run_policy_helper_profile(
                    case,
                    timeout_seconds=timeout_seconds,
                    provider_home=str(args.provider_home),
                    helper_combo=helper_combo,
                )
            )
    return effective_profile, helper_combos, results


def _summarize_policy_helper(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in results:
        key = (
            str(item.get("provider") or "").strip(),
            str(item.get("model") or "").strip(),
            str(item.get("helper_combo_id") or "").strip(),
        )
        grouped.setdefault(key, []).append(item)

    summaries: list[dict[str, Any]] = []
    for (provider, model, helper_combo_id), rows in sorted(grouped.items()):
        successful_profiles = [
            item
            for item in rows
            if not item.get("timeout")
            and not item.get("parse_error")
            and int(item.get("exit_code", 0) or 0) == 0
            and int(item.get("successful_cases", 0) or 0) == int(item.get("cases_run", 0) or -1)
            and int(item.get("cases_run", 0) or 0) > 0
        ]
        row_cost_proxies = [_entry_cost_proxy(item) for item in rows]
        wall_values = [int(item["wall_ms"]) for item in successful_profiles if isinstance(item.get("wall_ms"), int)]
        delegation_wall_values = [proxy["delegation_wall_ms"] for proxy in row_cost_proxies if proxy["delegation_wall_ms"] > 0]
        cases_run = max((int(item.get("cases_run", 0) or 0) for item in rows), default=0)
        successful_cases = max((int(item.get("successful_cases", 0) or 0) for item in rows), default=0)
        empty_response_count = sum(
            _int_or_default((item.get("summary") or {}).get("empty_response_count"))
            for item in rows
            if isinstance(item.get("summary"), dict)
        )
        first_combo = rows[0].get("helper_combo") if rows else {}
        combo_mapping = first_combo if isinstance(first_combo, dict) else {}
        summaries.append(
            {
                "provider": provider,
                "model": model,
                "helper_combo_id": helper_combo_id,
                "helper_combo": dict(combo_mapping),
'''
