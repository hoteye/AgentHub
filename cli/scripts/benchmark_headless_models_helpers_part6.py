from __future__ import annotations

SOURCE_PART = r'''            note="Expect explicit cycle/self-loop detection.",
        )
    )
    breakdown.append(
        _score_bucket(
            name="duplicate_edge_handling",
            passed="set(" in normalized or "seen_edges" in normalized or "dedup" in normalized,
            max_score=1,
            note="Duplicate edges should not double count indegree.",
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
    coverage_score, coverage_hits = _topo_coverage_bucket_score(content)
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
            passed="o((v + e) log v)" in normalized or "o((v+e)logv)" in normalized or "log v" in normalized,
            max_score=1,
            note="Analysis should mention O((V + E) log V).",
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


def _score_ability_response(
    text: str,
    *,
    ability_test: AbilityTestDefinition,
) -> dict[str, Any]:
    content = str(text or "")
    if ability_test.test_id == "normalize_ranges_py":
        return _score_normalize_ranges_response(content, ability_test=ability_test)
    if ability_test.test_id == "stable_topological_sort_py":
        return _score_stable_topological_sort_response(content, ability_test=ability_test)
    raise ValueError(f"unsupported ability test scorer: {ability_test.test_id}")


def _run_single_turn_scenario(
    *,
    args: argparse.Namespace,
    cases: list[BenchmarkCase],
    prompt_text: str,
    assistant_text_limit: int | None = 160,
    timeout_seconds: float | None = None,
) -> list[dict[str, Any]]:
    effective_timeout = float(timeout_seconds if timeout_seconds is not None else args.timeout)
    work_items: list[tuple[int, BenchmarkCase, int]] = []
    order_index = 0
    for case in cases:
        for run_index in range(1, args.runs + 1):
            work_items.append((order_index, case, run_index))
            order_index += 1

    results: list[dict[str, Any]] = []
    if args.max_workers == 1 or len(work_items) <= 1:
        for order_index, case, run_index in work_items:
            entry = _run_case(
                case,
                prompt=prompt_text,
                timeout_seconds=effective_timeout,
                provider_home=str(args.provider_home),
                assistant_text_limit=assistant_text_limit,
            )
            entry["run"] = run_index
            entry["_order"] = order_index
            results.append(entry)
    else:
        worker_count = min(int(args.max_workers), len(work_items))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_meta = {
                executor.submit(
                    _run_case,
                    case,
                    prompt=prompt_text,
                    timeout_seconds=effective_timeout,
                    provider_home=str(args.provider_home),
                    assistant_text_limit=assistant_text_limit,
                ): (order_index, run_index)
                for order_index, case, run_index in work_items
            }
            for future in as_completed(future_to_meta):
                order_index, run_index = future_to_meta[future]
                entry = future.result()
                entry["run"] = run_index
                entry["_order"] = order_index
                results.append(entry)

    results.sort(key=lambda item: int(item.get("_order", 0)))
    for item in results:
        item.pop("_order", None)
    return results


def _attach_ability_scores(
    results: list[dict[str, Any]],
    *,
    ability_test: AbilityTestDefinition,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for item in results:
        entry = dict(item)
        ability = _score_ability_response(str(entry.get("assistant_text") or ""), ability_test=ability_test)
        entry["ability_test"] = ability_test.as_dict()
        entry["ability_test_id"] = ability_test.test_id
        entry["ability_score"] = int(ability["score"])
        entry["ability_max_score"] = int(ability["max_score"])
        entry["ability_score_ratio"] = ability["score_ratio"]
        entry["ability_passed"] = bool(ability["passed"])
        entry["ability_missing"] = list(ability["missing"])
        entry["ability_breakdown"] = list(ability["breakdown"])
        scored.append(entry)
    return scored


def _result_is_successful(item: dict[str, Any]) -> bool:
    if item.get("timeout") or item.get("parse_error"):
        return False
    if int(item.get("exit_code", 0) or 0) != 0:
        return False
    if str(item.get("provider_runtime_state") or "").strip() != "ready":
        return False
    assistant_text = str(item.get("assistant_text") or "").strip()
    if not assistant_text or assistant_text == "模型未返回内容。":
        return False
    return isinstance(item.get("initial_model_ms"), int)


def _summarize_ability(
    results: list[dict[str, Any]],
    cases: list[BenchmarkCase],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in results:
        key = (
            str(item.get("provider") or "").strip(),
            str(item.get("model") or "").strip(),
            str(item.get("ability_test_id") or "").strip(),
        )
        grouped.setdefault(key, []).append(item)
    for case in cases:
        for (provider, model, ability_test_id), rows in sorted(grouped.items()):
            if provider != case.provider or model != case.model:
                continue
            ok_rows = [item for item in rows if _result_is_successful(item)]
            wall_values = [int(item["wall_ms"]) for item in ok_rows if isinstance(item.get("wall_ms"), int)]
            initial_values = [int(item["initial_model_ms"]) for item in ok_rows]
            total_values = [int(item["total_ms"]) for item in ok_rows if isinstance(item.get("total_ms"), int)]
            score_values = [int(item["ability_score"]) for item in rows if isinstance(item.get("ability_score"), int)]
            ratio_values = [float(item["ability_score_ratio"]) for item in rows if isinstance(item.get("ability_score_ratio"), (int, float))]
            pass_runs = sum(1 for item in rows if bool(item.get("ability_passed")))
            first_test = rows[0].get("ability_test") if rows else {}
            test_meta = dict(first_test) if isinstance(first_test, dict) else {}
            summaries.append(
                {
                    "provider": provider,
                    "model": model,
                    "runs": len(rows),
                    "successful_runs": len(ok_rows),
                    "pass_runs": pass_runs,
                    "ability_test_id": ability_test_id,
                    "ability_test_title": str(test_meta.get("title") or ""),
                    "ability_max_score": _int_or_default(test_meta.get("max_score")),
                    "ability_pass_score": _int_or_default(test_meta.get("pass_score")),
                    "avg_ability_score": round(statistics.mean(score_values), 2) if score_values else None,
                    "avg_ability_percent": round(statistics.mean(ratio_values) * 100.0, 2) if ratio_values else None,
                    "min_ability_score": min(score_values) if score_values else None,
                    "max_ability_score": max(score_values) if score_values else None,
                    "timeouts": sum(1 for item in rows if item.get("timeout")),
                    "avg_initial_model_ms": round(statistics.mean(initial_values), 1) if initial_values else None,
                    "avg_total_ms": round(statistics.mean(total_values), 1) if total_values else None,
                    "avg_wall_ms": round(statistics.mean(wall_values), 1) if wall_values else None,
                }
            )
    return summaries


def _summarize_ability_overall(
    results: list[dict[str, Any]],
    cases: list[BenchmarkCase],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for case in cases:
        rows = [
            item
            for item in results
            if item.get("provider") == case.provider and item.get("model") == case.model
        ]
        if not rows:
            continue
        ok_rows = [item for item in rows if _result_is_successful(item)]
        score_values = [int(item["ability_score"]) for item in rows if isinstance(item.get("ability_score"), int)]
        ratio_values = [float(item["ability_score_ratio"]) for item in rows if isinstance(item.get("ability_score_ratio"), (int, float))]
        wall_values = [int(item["wall_ms"]) for item in ok_rows if isinstance(item.get("wall_ms"), int)]
        initial_values = [int(item["initial_model_ms"]) for item in ok_rows]
        total_values = [int(item["total_ms"]) for item in ok_rows if isinstance(item.get("total_ms"), int)]
        pass_runs = sum(1 for item in rows if bool(item.get("ability_passed")))
        completed_tests = sorted(
            {
                str(item.get("ability_test_id") or "").strip()
                for item in rows
                if str(item.get("ability_test_id") or "").strip()
            }
        )
        total_max_score = sum(_int_or_default(item.get("ability_max_score")) for item in rows)
        total_score = sum(_int_or_default(item.get("ability_score")) for item in rows)
        summaries.append(
            {
                "provider": case.provider,
                "model": case.model,
                "runs": len(rows),
                "successful_runs": len(ok_rows),
                "pass_runs": pass_runs,
                "completed_tests": completed_tests,
                "completed_test_count": len(completed_tests),
                "total_ability_score": total_score,
                "total_ability_max_score": total_max_score,
                "avg_ability_score": round(statistics.mean(score_values), 2) if score_values else None,
                "avg_ability_percent": round(statistics.mean(ratio_values) * 100.0, 2) if ratio_values else None,
                "avg_initial_model_ms": round(statistics.mean(initial_values), 1) if initial_values else None,
                "avg_total_ms": round(statistics.mean(total_values), 1) if total_values else None,
                "avg_wall_ms": round(statistics.mean(wall_values), 1) if wall_values else None,
                "timeouts": sum(1 for item in rows if item.get("timeout")),
            }
        )
    return summaries


def _build_ability_matrix(summary: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for row in summary:
        test_id = str(row.get("ability_test_id") or "").strip() or "-"
        key = f"{row.get('provider')}:{row.get('model')}"
        matrix.setdefault(test_id, {})[key] = {
            "avg_ability_score": row.get("avg_ability_score"),
            "ability_max_score": row.get("ability_max_score"),
            "avg_ability_percent": row.get("avg_ability_percent"),
            "pass_runs": row.get("pass_runs"),
            "runs": row.get("runs"),
            "avg_initial_model_ms": row.get("avg_initial_model_ms"),
            "avg_wall_ms": row.get("avg_wall_ms"),
        }
    return {
        test_id: dict(sorted(rows.items()))
        for test_id, rows in sorted(matrix.items())
    }


def _run_ability_suite(
    *,
    args: argparse.Namespace,
    cases: list[BenchmarkCase],
    ability_tests: list[AbilityTestDefinition],
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for ability_test in ability_tests:
        test_results = _run_single_turn_scenario(
            args=args,
            cases=cases,
            prompt_text=ability_test.prompt,
            assistant_text_limit=None,
            timeout_seconds=timeout_seconds,
        )
        results.extend(_attach_ability_scores(test_results, ability_test=ability_test))
    return results


def _summarize(results: list[dict[str, Any]], cases: list[BenchmarkCase]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for case in cases:
        rows = [
            item
            for item in results
            if item.get("provider") == case.provider and item.get("model") == case.model
        ]
        ok_rows = [item for item in rows if _result_is_successful(item)]
        wall_values = [int(item["wall_ms"]) for item in ok_rows if isinstance(item.get("wall_ms"), int)]
        initial_values = [int(item["initial_model_ms"]) for item in ok_rows]
        total_values = [int(item["total_ms"]) for item in ok_rows if isinstance(item.get("total_ms"), int)]
        summaries.append(
            {
                "provider": case.provider,
                "model": case.model,
                "runs": len(rows),
                "successful_runs": len(ok_rows),
                "timeouts": sum(1 for item in rows if item.get("timeout")),
                "avg_initial_model_ms": round(statistics.mean(initial_values), 1) if initial_values else None,
                "avg_total_ms": round(statistics.mean(total_values), 1) if total_values else None,
                "avg_wall_ms": round(statistics.mean(wall_values), 1) if wall_values else None,
                "min_initial_model_ms": min(initial_values) if initial_values else None,
                "max_initial_model_ms": max(initial_values) if initial_values else None,
            }
        )
    return summaries


def _print_table(results: list[dict[str, Any]], summary: list[dict[str, Any]]) -> None:
    print("Runs")
    print("provider:model | run | initial_model_ms | wall_ms | state | note")
    print("--- | ---: | ---: | ---: | --- | ---")
    for item in results:
        note = ""
        if item.get("timeout"):
            note = "timeout"
        elif item.get("parse_error"):
            note = "parse_error"
        elif item.get("provider_runtime_state") and item.get("provider_runtime_state") != "ready":
            note = str(item.get("provider_runtime_state"))
        elif item.get("assistant_text"):
            note = str(item["assistant_text"]).replace("\n", " ")[:48]
        print(
            f"{item.get('provider')}:{item.get('model')} | {item.get('run')} | "
            f"{item.get('initial_model_ms', '-')} | {item.get('wall_ms', '-')} | "
            f"{item.get('provider_runtime_state', '-')} | {note}"
        )

    print("\nSummary")
    print("provider:model | successful_runs | avg_initial_model_ms | avg_wall_ms | min | max | timeouts")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---: ")
    for item in summary:
        print(
            f"{item['provider']}:{item['model']} | {item['successful_runs']}/{item['runs']} | "
            f"{item['avg_initial_model_ms'] if item['avg_initial_model_ms'] is not None else '-'} | "
            f"{item['avg_wall_ms'] if item['avg_wall_ms'] is not None else '-'} | "
            f"{item['min_initial_model_ms'] if item['min_initial_model_ms'] is not None else '-'} | "
            f"{item['max_initial_model_ms'] if item['max_initial_model_ms'] is not None else '-'} | "
            f"{item['timeouts']}"
        )
'''
