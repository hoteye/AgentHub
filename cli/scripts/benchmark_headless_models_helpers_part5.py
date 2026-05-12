from __future__ import annotations

SOURCE_PART = r'''                "helper_provider": str(combo_mapping.get("provider") or ""),
                "helper_model": str(combo_mapping.get("model") or ""),
                "helper_reasoning_effort": str(combo_mapping.get("reasoning_effort") or ""),
                "helper_timeout": _int_or_default(combo_mapping.get("timeout")),
                "runs": len(rows),
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


def _print_multi_llm_table(results: list[dict[str, Any]], summary: list[dict[str, Any]]) -> None:
    print("Runs")
    print("model | cases | ok_cases | req | child_turns | fallback | timeout_hits | delegation_wall_ms | wall_ms | note")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---")
    for item in results:
        cost_proxy = _entry_cost_proxy(item)
        model_label = str(item.get("model") or "-")
        helper_combo_id = str(item.get("helper_combo_id") or "").strip()
        if helper_combo_id:
            model_label = f"{model_label}@{helper_combo_id}"
        note = ""
        if item.get("timeout"):
            note = "timeout"
        elif item.get("parse_error"):
            note = str(item.get("parse_error_category") or "parse_error")
        elif item.get("assistant_text"):
            note = str(item["assistant_text"]).replace("\n", " ")[:96]
        print(
            f"{model_label} | {item.get('cases_run', '-')} | "
            f"{item.get('successful_cases', '-')} | {cost_proxy['request_count']} | "
            f"{cost_proxy['child_turn_count']} | {cost_proxy['fallback_count']} | "
            f"{cost_proxy['timeout_count']} | {cost_proxy['delegation_wall_ms']} | "
            f"{item.get('wall_ms', '-')} | {note}"
        )

    print("\nSummary")
    print("model | successful_runs | successful_cases | req | child_turns | fallback | timeout_hits | avg_delegation_wall_ms | avg_wall_ms | timeouts")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:")
    for item in summary:
        model_label = str(item.get("model") or "-")
        helper_combo_id = str(item.get("helper_combo_id") or "").strip()
        if helper_combo_id:
            model_label = f"{model_label}@{helper_combo_id}"
        print(
            f"{model_label} | {item['successful_runs']}/{item['runs']} | "
            f"{item['successful_cases']}/{item['cases_run']} | "
            f"{item.get('request_count', 0)} | {item.get('child_turn_count', 0)} | "
            f"{item.get('fallback_count', 0)} | {item.get('timeout_count', 0)} | "
            f"{item['avg_delegation_wall_ms'] if item['avg_delegation_wall_ms'] is not None else '-'} | "
            f"{item['avg_wall_ms'] if item['avg_wall_ms'] is not None else '-'} | {item['timeouts']}"
        )


def _run_case(
    case: BenchmarkCase,
    *,
    prompt: str,
    timeout_seconds: float,
    provider_home: str,
    assistant_text_limit: int | None = 160,
) -> dict[str, Any]:
    env = dict(os.environ)
    env.update(case.env_overrides(provider_home=provider_home))
    command = [
        sys.executable,
        str(REPO_ROOT / "agent_cli" / "__main__.py"),
        "--headless",
        "--prompt",
        prompt,
        "--json",
        "--approval-policy",
        "never",
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
        return entry

    entry["exit_code"] = int(completed.returncode)
    entry["wall_ms"] = int((time.perf_counter() - started) * 1000)
    entry["stderr"] = completed.stderr.strip()[:400]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        entry["parse_error"] = f"{type(exc).__name__}: {exc}"
        entry["stdout_preview"] = completed.stdout.strip()[:400]
        return entry

    timings = payload.get("timings") or {}
    status = payload.get("status") or {}
    assistant_text = str(payload.get("assistant_text") or "")
    entry.update(
        {
            "assistant_text": assistant_text if assistant_text_limit is None else assistant_text[:assistant_text_limit],
            "assistant_text_preview": assistant_text[:160],
            "initial_model_ms": timings.get("initial_model_ms"),
            "total_ms": timings.get("total_ms"),
            "provider_runtime_state": status.get("provider_runtime_state"),
            "provider_model": status.get("provider_model"),
        }
    )
    return entry


def _heading_present(text: str, heading: str) -> bool:
    pattern = rf"(?im)^\s*#+\s*{re.escape(str(heading or '').strip())}\s*$"
    return bool(re.search(pattern, str(text or "")))


def _score_bucket(*, name: str, passed: bool, max_score: int, note: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "score": int(max_score if passed else 0),
        "max_score": int(max_score),
        "note": str(note or ""),
    }


def _code_block_count(text: str) -> int:
    return len(re.findall(r"```(?:python)?\s*", str(text or ""), flags=re.IGNORECASE))


def _coverage_bucket_score(text: str) -> tuple[int, list[str]]:
    normalized = str(text or "").lower()
    category_patterns: dict[str, tuple[str, ...]] = {
        "empty": ("empty", "空输入"),
        "single": ("single", "单区间"),
        "unsorted": ("unsorted", "out_of_order", "乱序"),
        "overlap": ("overlap", "重叠"),
        "adjacent": ("adjacent", "contiguous", "相邻"),
        "nested": ("nested", "嵌套"),
        "duplicate": ("duplicate", "重复"),
        "invalid": ("invalid", "valueerror", "非法"),
    }
    hits = [
        name
        for name, patterns in category_patterns.items()
        if any(pattern in normalized for pattern in patterns)
    ]
    if len(hits) >= 6:
        return 2, hits
    if len(hits) >= 4:
        return 1, hits
    return 0, hits


def _topo_coverage_bucket_score(text: str) -> tuple[int, list[str]]:
    normalized = str(text or "").lower()
    category_patterns: dict[str, tuple[str, ...]] = {
        "empty": ("empty", "空图"),
        "isolated": ("isolated", "孤立"),
        "stable_order": ("lexicographic", "stable", "字典序"),
        "duplicate_edge": ("duplicate", "重复边"),
        "self_loop": ("self_loop", "self-loop", "自环"),
        "cycle": ("cycle", "环"),
        "unknown_node": ("unknown", "keyerror"),
    }
    hits = [
        name
        for name, patterns in category_patterns.items()
        if any(pattern in normalized for pattern in patterns)
    ]
    if len(hits) >= 6:
        return 2, hits
    if len(hits) >= 4:
        return 1, hits
    return 0, hits


def _score_normalize_ranges_response(
    content: str,
    *,
    ability_test: AbilityTestDefinition,
) -> dict[str, Any]:
    normalized = content.lower()
    breakdown: list[dict[str, Any]] = []

    breakdown.append(
        _score_bucket(
            name="format_sections",
            passed=all(_heading_present(content, heading) for heading in ("Implementation", "Tests", "Analysis")),
            max_score=1,
            note="Require # Implementation / # Tests / # Analysis sections.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="implementation_function",
            passed="def normalize_ranges" in normalized,
            max_score=2,
            note="Require normalize_ranges function signature.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="invalid_range_guard",
            passed="valueerror" in normalized and "raise valueerror" in normalized,
            max_score=1,
            note="Require explicit ValueError for start > end.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="sorting_strategy",
            passed="sorted(" in normalized or ".sort(" in normalized,
            max_score=1,
            note="Expect sort-first O(n log n) merge strategy.",
        )
    )
    adjacency_patterns = (
        r"<=\s*[a-z_][a-z0-9_]*\s*\+\s*1",
        r"[a-z_][a-z0-9_]*\s*<=\s*[a-z_][a-z0-9_]*\s*\+\s*1",
        r"end\s*\+\s*1",
        r"last_end\s*\+\s*1",
    )
    breakdown.append(
        _score_bucket(
            name="adjacent_merge_logic",
            passed=any(re.search(pattern, normalized) for pattern in adjacency_patterns),
            max_score=2,
            note="Need explicit adjacent merge rule, e.g. start <= last_end + 1.",
        )
    )
    test_count = len(re.findall(r"(?im)^\s*def\s+test_[a-z0-9_]+\s*\(", content))
    breakdown.append(
        _score_bucket(
            name="pytest_tests_present",
            passed=_code_block_count(content) >= 1 and test_count >= 4,
            max_score=1,
            note="Expect at least one python code block and multiple pytest tests.",
        )
    )
    coverage_score, coverage_hits = _coverage_bucket_score(content)
    breakdown.append(
        {
            "name": "test_coverage_matrix",
            "passed": coverage_score >= 1,
            "score": int(coverage_score),
            "max_score": 2,
            "note": f"Detected coverage buckets: {', '.join(coverage_hits) if coverage_hits else '-'}",
        }
    )
    breakdown.append(
        _score_bucket(
            name="analysis_complexity",
            passed="o(n log n)" in normalized or "n log n" in normalized,
            max_score=1,
            note="Analysis should mention O(n log n).",
        )
    )

    score = sum(int(item.get("score") or 0) for item in breakdown)
    max_score = sum(int(item.get("max_score") or 0) for item in breakdown)
    missing = [str(item.get("name") or "") for item in breakdown if not bool(item.get("passed"))]
    return {
        "test_id": ability_test.test_id,
        "title": ability_test.title,
        "score": int(score),
        "max_score": int(max_score),
        "score_ratio": round(score / max_score, 4) if max_score > 0 else 0.0,
        "passed": score >= int(ability_test.pass_score),
        "pass_score": int(ability_test.pass_score),
        "breakdown": breakdown,
        "missing": missing,
    }


def _score_stable_topological_sort_response(
    content: str,
    *,
    ability_test: AbilityTestDefinition,
) -> dict[str, Any]:
    normalized = content.lower()
    breakdown: list[dict[str, Any]] = []

    breakdown.append(
        _score_bucket(
            name="format_sections",
            passed=all(_heading_present(content, heading) for heading in ("Implementation", "Tests", "Analysis")),
            max_score=1,
            note="Require # Implementation / # Tests / # Analysis sections.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="implementation_function",
            passed="def stable_topological_sort" in normalized,
            max_score=2,
            note="Require stable_topological_sort function signature.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="graph_bookkeeping",
            passed=("indegree" in normalized or "in_degree" in normalized) and ("adj" in normalized or "graph" in normalized),
            max_score=1,
            note="Expect adjacency + indegree bookkeeping.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="stable_tie_break",
            passed="heapq" in normalized or "heappush" in normalized or "heappop" in normalized or "sorted(" in normalized,
            max_score=2,
            note="Need deterministic lexicographic tie-break among zero indegree nodes.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="validation_errors",
            passed=("keyerror" in normalized and "valueerror" in normalized),
            max_score=1,
            note="Need KeyError for unknown node and ValueError for self-loop/cycle.",
        )
    )
    cycle_patterns = (
        "len(result) != len(nodes)",
        "len(order) != len(nodes)",
        "processed != len(nodes)",
        "raise valueerror",
    )
    breakdown.append(
        _score_bucket(
            name="cycle_detection",
            passed=any(pattern in normalized for pattern in cycle_patterns),
            max_score=1,
'''
