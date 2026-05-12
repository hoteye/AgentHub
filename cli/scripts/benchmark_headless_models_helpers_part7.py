from __future__ import annotations

SOURCE_PART = r'''

def _print_ability_table(
    results: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    overall_summary: list[dict[str, Any]],
) -> None:
    print("Runs")
    print("provider:model@test | run | score | passed | initial_model_ms | wall_ms | missing")
    print("--- | ---: | ---: | --- | ---: | ---: | ---")
    for item in results:
        missing = ",".join(list(item.get("ability_missing") or [])[:3]) or "-"
        print(
            f"{item.get('provider')}:{item.get('model')}@{item.get('ability_test_id')} | {item.get('run')} | "
            f"{item.get('ability_score', '-')} / {item.get('ability_max_score', '-')} | "
            f"{'yes' if item.get('ability_passed') else 'no'} | "
            f"{item.get('initial_model_ms', '-')} | {item.get('wall_ms', '-')} | {missing}"
        )
    print("\nSummary")
    print("provider:model@test | pass_runs | avg_score | avg_percent | avg_initial_model_ms | avg_wall_ms | timeouts")
    print("--- | ---: | ---: | ---: | ---: | ---: | ---:")
    for item in summary:
        print(
            f"{item['provider']}:{item['model']}@{item['ability_test_id']} | "
            f"{item['pass_runs']}/{item['runs']} | "
            f"{item['avg_ability_score'] if item['avg_ability_score'] is not None else '-'} / {item['ability_max_score']} | "
            f"{item['avg_ability_percent'] if item['avg_ability_percent'] is not None else '-'} | "
            f"{item['avg_initial_model_ms'] if item['avg_initial_model_ms'] is not None else '-'} | "
            f"{item['avg_wall_ms'] if item['avg_wall_ms'] is not None else '-'} | "
            f"{item['timeouts']}"
        )
    if overall_summary:
        print("\nOverall")
        print("provider:model | passed_tests | total_score | avg_percent | avg_initial_model_ms | avg_wall_ms | timeouts")
        print("--- | ---: | ---: | ---: | ---: | ---: | ---:")
        for item in overall_summary:
            print(
                f"{item['provider']}:{item['model']} | "
                f"{item['pass_runs']}/{item['completed_test_count']} | "
                f"{item['total_ability_score']} / {item['total_ability_max_score']} | "
                f"{item['avg_ability_percent'] if item['avg_ability_percent'] is not None else '-'} | "
                f"{item['avg_initial_model_ms'] if item['avg_initial_model_ms'] is not None else '-'} | "
                f"{item['avg_wall_ms'] if item['avg_wall_ms'] is not None else '-'} | "
                f"{item['timeouts']}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_workers <= 0:
        parser.error("--max-workers must be greater than zero")
    if (str(args.ability_test or "").strip() or str(args.ability_suite or "").strip()) and str(args.scenario or "").strip() != "single_turn_headless":
        parser.error("--ability-test and --ability-suite can only be used with scenario=single_turn_headless")
    if str(args.scenario or "").strip() == "two_turn_dates":
        return _run_two_turn_dates_scenario(args)
    if str(args.scenario or "").strip() == "multi_llm_live_cases":
        if args.timeout <= 0:
            parser.error("--timeout must be greater than zero")
        cases = list(args.cases or _default_multi_llm_cases())
        effective_timeout = float(args.timeout)
        if effective_timeout == float(DEFAULT_TIMEOUT_SECONDS):
            effective_timeout = float(DEFAULT_MULTI_LLM_TIMEOUT_SECONDS)
        if args.dry_run:
            dry_run_cases = [
                _dry_run_live_case_payload(
                    case=case,
                    provider_home=str(args.provider_home),
                    command=[
                        sys.executable,
                        str(SCRIPTS_DIR / "run_multi_llm_live_cases.py"),
                        "--provider",
                        case.provider,
                        "--model",
                        case.model,
                        "--profile",
                        "orchestration_smoke",
                        "--strict",
                    ],
                )
                for case in cases
            ]
            report = {
                "scenario": "multi_llm_live_cases",
                "dry_run": True,
                **_provider_home_report_fields(str(args.provider_home)),
                "timeout_seconds": effective_timeout,
                "cases": dry_run_cases,
                "results": [],
                "summary": [],
                "cost_proxy_totals": _cost_proxy_totals_from_summary([]),
                "failure_categories": {},
                "failure_taxonomy_by_case": {},
                "failure_taxonomy_totals": {},
                "human_summary": [],
                "fixed_provider_matrix": [dict(item) for item in DEFAULT_FIXED_PROVIDER_MATRIX],
            }
            report["ci_reuse"] = _ci_reuse_block(scenario="multi_llm_live_cases", summary=[])
            if args.out:
                Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print("Dry run")
                for item in dry_run_cases:
                    print(f"- {item['provider']}:{item['model']}")
            if args.ci_gate and not bool((((report.get("ci_reuse") or {}).get("ci_gate") or {}).get("all_cases_successful"))):
                return 2
            return 0
        results = _run_multi_llm_scenario(args=args, cases=cases)
        summary = _summarize_multi_llm(results, cases)
        report = {
            "scenario": "multi_llm_live_cases",
            **_provider_home_report_fields(str(args.provider_home)),
            "timeout_seconds": effective_timeout,
            "cases": [{"provider": case.provider, "model": case.model} for case in cases],
            "results": results,
            "summary": summary,
            "cost_proxy_totals": _cost_proxy_totals_from_summary(summary),
            "failure_categories": _aggregate_failure_categories(summary),
            "provider_matrix": _aggregate_provider_matrix(summary),
            "route_matrix": _aggregate_route_matrix(results),
            "failure_buckets_by_case": _aggregate_failure_categories_by_case(summary),
            "failure_taxonomy_by_case": _aggregate_failure_taxonomy_by_case(summary),
            "failure_taxonomy_totals": _aggregate_failure_taxonomy_totals(summary),
            "human_summary": _human_summary_from_aggregate(summary, scenario="multi_llm_live_cases"),
            "fixed_provider_matrix": [dict(item) for item in DEFAULT_FIXED_PROVIDER_MATRIX],
        }
        report["ci_reuse"] = _ci_reuse_block(scenario="multi_llm_live_cases", summary=summary)
        if args.out:
            Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_multi_llm_table(results, summary)
        if args.ci_gate and not bool((((report.get("ci_reuse") or {}).get("ci_gate") or {}).get("all_cases_successful"))):
            return 2
        return 0
    if str(args.scenario or "").strip() == "policy_helper_live_cases":
        if args.timeout <= 0:
            parser.error("--timeout must be greater than zero")
        cases = list(args.cases or _default_policy_helper_cases())
        effective_timeout = float(args.timeout)
        if effective_timeout == float(DEFAULT_TIMEOUT_SECONDS):
            effective_timeout = float(DEFAULT_MULTI_LLM_TIMEOUT_SECONDS)
        if args.dry_run:
            try:
                effective_profile, helper_combos = _selected_policy_helper_combos(args)
            except argparse.ArgumentTypeError as exc:
                parser.error(str(exc))
            dry_run_cases = [
                _dry_run_live_case_payload(
                    case=case,
                    provider_home=str(args.provider_home),
                    helper_combo=helper_combo,
                    command=(
                        [
                            sys.executable,
                            str(SCRIPTS_DIR / "run_policy_helper_live_cases.py"),
                            "--provider",
                            case.provider,
                            "--model",
                            case.model,
                            "--profile",
                            "single",
                        ]
                        + (["--policy-helper-provider", str(helper_combo.provider)] if str(helper_combo.provider or "").strip() else [])
                        + (["--policy-helper-model", str(helper_combo.model)] if str(helper_combo.model or "").strip() else [])
                        + (
                            ["--policy-helper-reasoning-effort", str(helper_combo.reasoning_effort)]
                            if str(helper_combo.reasoning_effort or "").strip()
                            else []
                        )
                        + (["--policy-helper-timeout", str(int(helper_combo.timeout or 0))] if int(helper_combo.timeout or 0) > 0 else [])
                    ),
                )
                for case in cases
                for helper_combo in helper_combos
            ]
            report = {
                "scenario": "policy_helper_live_cases",
                "dry_run": True,
                **_provider_home_report_fields(str(args.provider_home)),
                "timeout_seconds": effective_timeout,
                "policy_helper_profile": str(effective_profile or ""),
                "policy_helper_override": {
                    "provider": str(args.policy_helper_provider or ""),
                    "model": str(args.policy_helper_model or ""),
                    "reasoning_effort": str(args.policy_helper_reasoning_effort or ""),
                    "timeout": int(args.policy_helper_timeout or 0),
                }
                if str(effective_profile or "").strip() == "single"
                else {"provider": "", "model": "", "reasoning_effort": "", "timeout": 0},
                "policy_helper_combos": [combo.as_dict() for combo in helper_combos],
                "policy_helper_combo_catalog": [combo.as_dict() for combo in POLICY_HELPER_COMBO_CATALOG],
                "policy_helper_profile_matrix": {key: list(value) for key, value in POLICY_HELPER_PROFILE_MATRIX.items()},
                "cases": dry_run_cases,
                "results": [],
                "summary": [],
                "cost_proxy_totals": _cost_proxy_totals_from_summary([]),
                "failure_categories": {},
                "failure_taxonomy_by_case": {},
                "failure_taxonomy_totals": {},
                "human_summary": [],
                "fixed_provider_matrix": [dict(item) for item in DEFAULT_FIXED_PROVIDER_MATRIX],
            }
            report["ci_reuse"] = _ci_reuse_block(scenario="policy_helper_live_cases", summary=[])
            if args.out:
                Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print("Dry run")
                for item in dry_run_cases:
                    helper_combo_id = str(item.get("helper_combo_id") or "").strip()
                    suffix = f"@{helper_combo_id}" if helper_combo_id else ""
                    print(f"- {item['provider']}:{item['model']}{suffix}")
            if args.ci_gate and not bool((((report.get("ci_reuse") or {}).get("ci_gate") or {}).get("all_cases_successful"))):
                return 2
            return 0
        try:
            effective_profile, helper_combos, results = _run_policy_helper_scenario(args=args, cases=cases)
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
        summary = _summarize_policy_helper(results)
        summary_failure_categories = _aggregate_failure_categories(summary)
        manual_override_payload = {
            "provider": str(args.policy_helper_provider or ""),
            "model": str(args.policy_helper_model or ""),
            "reasoning_effort": str(args.policy_helper_reasoning_effort or ""),
            "timeout": int(args.policy_helper_timeout or 0),
        }
        if str(effective_profile or "").strip() != "single":
            manual_override_payload = {
                "provider": "",
                "model": "",
                "reasoning_effort": "",
                "timeout": 0,
            }
        report = {
            "scenario": "policy_helper_live_cases",
            **_provider_home_report_fields(str(args.provider_home)),
            "timeout_seconds": effective_timeout,
            "policy_helper_profile": str(effective_profile or ""),
            "policy_helper_override": manual_override_payload,
            "policy_helper_combos": [combo.as_dict() for combo in helper_combos],
            "policy_helper_combo_catalog": [combo.as_dict() for combo in POLICY_HELPER_COMBO_CATALOG],
            "policy_helper_profile_matrix": {
                key: list(value)
                for key, value in POLICY_HELPER_PROFILE_MATRIX.items()
            },
            "cases": [{"provider": case.provider, "model": case.model} for case in cases],
            "results": results,
            "summary": summary,
            "cost_proxy_totals": _cost_proxy_totals_from_summary(summary),
            "failure_categories": summary_failure_categories,
            "provider_matrix": _aggregate_provider_matrix(summary),
            "route_matrix": _aggregate_route_matrix(results),
            "failure_buckets_by_case": _aggregate_failure_categories_by_case(summary),
            "failure_taxonomy_by_case": _aggregate_failure_taxonomy_by_case(summary),
            "failure_taxonomy_totals": _aggregate_failure_taxonomy_totals(summary),
            "human_summary": _human_summary_from_aggregate(summary, scenario="policy_helper_live_cases"),
            "fixed_provider_matrix": [dict(item) for item in DEFAULT_FIXED_PROVIDER_MATRIX],
        }
        report["ci_reuse"] = _ci_reuse_block(scenario="policy_helper_live_cases", summary=summary)
        if args.out:
            Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_multi_llm_table(results, summary)
        if args.ci_gate and not bool((((report.get("ci_reuse") or {}).get("ci_gate") or {}).get("all_cases_successful"))):
            return 2
        return 0
    if args.runs <= 0:
        parser.error("--runs must be greater than zero")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        ability_suite, ability_tests = _selected_ability_tests(
            ability_test_id=str(args.ability_test or ""),
            ability_suite_id=str(args.ability_suite or ""),
        )
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    primary_ability_test = ability_tests[0] if len(ability_tests) == 1 else None
    prompt_text = primary_ability_test.prompt if primary_ability_test is not None else args.prompt
    effective_single_turn_timeout = float(args.timeout)
    if ability_tests and effective_single_turn_timeout == float(DEFAULT_TIMEOUT_SECONDS):
        effective_single_turn_timeout = float(DEFAULT_ABILITY_TIMEOUT_SECONDS)
    cases = list(args.cases or _default_cases())
    if args.dry_run:
        payload = {
            "scenario": "single_turn_headless",
            "cwd": str(REPO_ROOT),
            **_provider_home_report_fields(str(args.provider_home)),
            "prompt": prompt_text,
            "runs": args.runs,
            "max_workers": args.max_workers,
            "timeout": effective_single_turn_timeout,
            "ability_test": primary_ability_test.as_dict() if primary_ability_test is not None else None,
            "ability_suite": ability_suite.as_dict() if ability_suite is not None else None,
            "ability_tests": [item.as_dict() for item in ability_tests],
            "cases": [
                {
                    "provider": case.provider,
                    "model": case.model,
                    "env": case.env_overrides(provider_home=str(args.provider_home)),
                    "command": [
                        sys.executable,
                        str(REPO_ROOT / "agent_cli" / "__main__.py"),
                        "--headless",
                        "--prompt",
                        prompt_text,
                        "--json",
                        "--approval-policy",
                        "never",
                    ],
                }
                for case in cases
            ],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Dry run")
            for item in payload["cases"]:
                print(f"- {item['provider']}:{item['model']}")
        return 0

    if ability_tests:
        results = _run_ability_suite(
            args=args,
            cases=cases,
            ability_tests=ability_tests,
            timeout_seconds=effective_single_turn_timeout,
        )
        summary = _summarize_ability(results, cases)
        overall_summary = _summarize_ability_overall(results, cases)
    else:
        results = _run_single_turn_scenario(
            args=args,
            cases=cases,
            prompt_text=prompt_text,
            assistant_text_limit=160,
            timeout_seconds=effective_single_turn_timeout,
        )
        summary = _summarize(results, cases)
        overall_summary = []
    report = {
        "scenario": "single_turn_headless",
        **_provider_home_report_fields(str(args.provider_home)),
        "prompt": prompt_text,
        "runs": args.runs,
        "max_workers": args.max_workers,
        "timeout_seconds": effective_single_turn_timeout,
        "ability_test": primary_ability_test.as_dict() if primary_ability_test is not None else None,
        "ability_suite": ability_suite.as_dict() if ability_suite is not None else None,
        "ability_tests": [item.as_dict() for item in ability_tests],
'''
