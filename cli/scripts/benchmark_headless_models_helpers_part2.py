from __future__ import annotations

SOURCE_PART = r'''    reasoning_effort: str,
    timeout: int,
) -> PolicyHelperCombo:
    provider_name = str(provider or "").strip()
    model_name = str(model or "").strip()
    effort = str(reasoning_effort or "").strip() or "low"
    timeout_value = max(0, int(timeout or 0))
    if provider_name or model_name:
        combo_id = (
            f"manual_{_combo_token(provider_name or 'provider')}_"
            f"{_combo_token(model_name or 'model')}_"
            f"{_combo_token(effort)}_t{timeout_value}"
        )
        source = "manual_override"
        description = "Single-run helper override from benchmark flags."
    else:
        combo_id = f"single_main_route_{_combo_token(effort)}_t{timeout_value}"
        source = "main_route"
        description = "Single-run helper route follows main model route."
    return PolicyHelperCombo(
        combo_id=combo_id,
        provider=provider_name,
        model=model_name,
        reasoning_effort=effort,
        timeout=timeout_value,
        source=source,
        description=description,
    )


def _selected_policy_helper_combos(args: argparse.Namespace) -> tuple[str, list[PolicyHelperCombo]]:
    requested_profile = str(args.policy_helper_profile or DEFAULT_POLICY_HELPER_PROFILE).strip() or DEFAULT_POLICY_HELPER_PROFILE
    requested_combo_ids = [
        str(item or "").strip()
        for item in list(args.policy_helper_combos or [])
        if str(item or "").strip()
    ]
    helper_provider = str(args.policy_helper_provider or "").strip()
    helper_model = str(args.policy_helper_model or "").strip()
    helper_effort = str(args.policy_helper_reasoning_effort or "").strip()
    helper_timeout = int(args.policy_helper_timeout or 0)
    has_manual_override = bool(helper_provider or helper_model)

    if requested_profile == "single" or has_manual_override:
        if requested_combo_ids:
            raise argparse.ArgumentTypeError("--policy-helper-combo cannot be used with manual helper override")
        return (
            "single",
            [
                _manual_policy_helper_combo(
                    provider=helper_provider,
                    model=helper_model,
                    reasoning_effort=helper_effort,
                    timeout=helper_timeout,
                )
            ],
        )

    combo_index = _policy_helper_combo_index()
    profile_combo_ids = list(POLICY_HELPER_PROFILE_MATRIX.get(requested_profile) or ())
    if not profile_combo_ids:
        raise argparse.ArgumentTypeError(f"unsupported --policy-helper-profile {requested_profile!r}")
    if requested_combo_ids:
        unknown_ids = [combo_id for combo_id in requested_combo_ids if combo_id not in combo_index]
        if unknown_ids:
            joined = ", ".join(sorted(set(unknown_ids)))
            raise argparse.ArgumentTypeError(f"unknown --policy-helper-combo ids: {joined}")
        requested_set = set(requested_combo_ids)
        filtered_ids = [combo_id for combo_id in profile_combo_ids if combo_id in requested_set]
        if not filtered_ids:
            joined = ", ".join(requested_combo_ids)
            raise argparse.ArgumentTypeError(
                f"requested --policy-helper-combo ids are not in profile {requested_profile}: {joined}"
            )
        profile_combo_ids = filtered_ids
    return requested_profile, [combo_index[combo_id] for combo_id in profile_combo_ids]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/benchmark_headless_models.py",
        description="Unified AgentHub benchmark entrypoint across single-turn and two-turn scenarios.",
    )
    parser.add_argument(
        "--scenario",
        choices=("single_turn_headless", "two_turn_dates", "multi_llm_live_cases", "policy_helper_live_cases"),
        default=DEFAULT_SCENARIO,
        help=f"Benchmark scenario. Defaults to {DEFAULT_SCENARIO}.",
    )
    parser.add_argument(
        "--case",
        action="append",
        type=_parse_case,
        dest="cases",
        help="Benchmark case in provider:model form. Repeat to override defaults.",
    )
    parser.add_argument(
        "--ability-test",
        choices=ABILITY_TEST_CHOICES,
        default="",
        help=(
            "Run a built-in coding ability prompt with heuristic scoring. "
            "Only supported with scenario=single_turn_headless."
        ),
    )
    parser.add_argument(
        "--ability-suite",
        choices=ABILITY_SUITE_CHOICES,
        default="",
        help=(
            "Run a fixed small set of hard coding questions. "
            "Each question runs across all selected models in parallel."
        ),
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help=f"Single-turn prompt. Used by scenario=single_turn_headless. Defaults to {DEFAULT_PROMPT!r}.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Runs per model. Used by scenario=single_turn_headless. Defaults to {DEFAULT_RUNS}.",
    )
    parser.add_argument(
        "--first-prompt",
        default=DEFAULT_FIRST_PROMPT,
        help=f"First-turn prompt. Used by scenario=two_turn_dates. Defaults to {DEFAULT_FIRST_PROMPT!r}.",
    )
    parser.add_argument(
        "--second-prompt",
        default=DEFAULT_SECOND_PROMPT,
        help=f"Second-turn prompt. Used by scenario=two_turn_dates. Defaults to {DEFAULT_SECOND_PROMPT!r}.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"Timezone for scenario=two_turn_dates. Defaults to {DEFAULT_TIMEZONE}.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=(
            "Concurrent workers for independent benchmark runs. "
            f"Defaults to {DEFAULT_MAX_WORKERS}."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-run timeout in seconds. Defaults to {DEFAULT_TIMEOUT_SECONDS:g}.",
    )
    parser.add_argument(
        "--provider-home",
        default="",
        help=(
            "Optional provider runtime home override passed via AGENTHUB_PROVIDER_HOME. "
            "Defaults to runtime-managed provider home resolution."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the default table summary.",
    )
    parser.add_argument(
        "--ci-gate",
        action="store_true",
        help=(
            "Return non-zero for live-case scenarios when "
            "report.ci_reuse.ci_gate.all_cases_successful is false."
        ),
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path to write the full JSON report.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing requests.",
    )
    parser.add_argument(
        "--policy-helper-provider",
        default="",
        help="Temporary provider override for routes.policy_helper. Used by scenario=policy_helper_live_cases.",
    )
    parser.add_argument(
        "--policy-helper-model",
        default="",
        help="Temporary model override for routes.policy_helper. Used by scenario=policy_helper_live_cases.",
    )
    parser.add_argument(
        "--policy-helper-reasoning-effort",
        default="low",
        help="Temporary reasoning effort for routes.policy_helper. Used by scenario=policy_helper_live_cases.",
    )
    parser.add_argument(
        "--policy-helper-timeout",
        type=int,
        default=20,
        help="Temporary timeout for routes.policy_helper. Used by scenario=policy_helper_live_cases.",
    )
    parser.add_argument(
        "--policy-helper-profile",
        choices=POLICY_HELPER_PROFILE_CHOICES,
        default=DEFAULT_POLICY_HELPER_PROFILE,
        help=(
            "Helper combo profile for scenario=policy_helper_live_cases. "
            f"Defaults to {DEFAULT_POLICY_HELPER_PROFILE}."
        ),
    )
    parser.add_argument(
        "--policy-helper-combo",
        action="append",
        dest="policy_helper_combos",
        help="Select helper combo ids inside a policy-helper profile run. Repeat to keep multiple combos.",
    )
    return parser


def _run_two_turn_dates_scenario(args: argparse.Namespace) -> int:
    scripts_dir_text = str(SCRIPTS_DIR)
    if scripts_dir_text not in sys.path:
        sys.path.insert(0, scripts_dir_text)
    from benchmark_two_turn_multi_provider import main as two_turn_main

    forwarded_argv: list[str] = [
        "--first-prompt",
        str(args.first_prompt),
        "--second-prompt",
        str(args.second_prompt),
        "--timezone",
        str(args.timezone),
        "--timeout",
        str(args.timeout),
        "--max-workers",
        str(args.max_workers),
    ]
    provider_home_override = normalize_optional_provider_home_override(args.provider_home)
    if provider_home_override:
        forwarded_argv.extend(["--provider-home", provider_home_override])
    for case in list(args.cases or []):
        forwarded_argv.extend(["--case", f"{case.provider}:{case.model}"])
    if args.json:
        forwarded_argv.append("--json")
    if args.out:
        forwarded_argv.extend(["--out", str(args.out)])
    if args.dry_run:
        forwarded_argv.append("--dry-run")
    return int(two_turn_main(forwarded_argv))


def _multi_llm_case_success(case_result: dict[str, Any]) -> bool:
    assistant_text = str(case_result.get("assistant_text") or "").strip()
    if not assistant_text or assistant_text == "模型未返回内容。":
        return False
    tool_event_names = {
        str(name or "").strip()
        for name in list(case_result.get("tool_event_names") or [])
        if str(name or "").strip()
    }
    delegated_provider_name = str(case_result.get("delegated_provider_name") or "").strip()
    delegated_model = str(case_result.get("delegated_model") or "").strip()
    if "spawn_agent" in tool_event_names and delegated_provider_name and delegated_model:
        return True
    requests = list((case_result.get("llm_trace") or {}).get("requests") or [])
    if not requests:
        return False
    first_request = requests[0] if isinstance(requests[0], dict) else {}
    return bool(str(first_request.get("provider_name") or "").strip()) and bool(str(first_request.get("model") or "").strip())


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _int_or_default(value: Any, *, default: int = 0) -> int:
    parsed = _int_or_none(value)
    if parsed is None:
        return default
    return parsed


def _attach_cost_proxy_fields(entry: dict[str, Any], cost_proxy: dict[str, Any]) -> None:
    entry["cost_proxy"] = dict(cost_proxy)
    entry["request_count"] = _int_or_default(cost_proxy.get("request_count"))
    entry["child_turn_count"] = _int_or_default(cost_proxy.get("child_turn_count"))
    entry["timeout_count"] = _int_or_default(cost_proxy.get("timeout_count"))
    entry["fallback_count"] = _int_or_default(cost_proxy.get("fallback_count"))
    entry["delegation_wall_ms"] = _int_or_default(cost_proxy.get("delegation_wall_ms"))


def _case_cost_proxy(case_result: dict[str, Any]) -> dict[str, Any]:
    trace = case_result.get("llm_trace")
    trace_mapping = trace if isinstance(trace, dict) else {}
    requests = list(trace_mapping.get("requests") or [])
    request_count = len([item for item in requests if isinstance(item, dict)])
    stages = [str(item or "").strip().lower() for item in list(trace_mapping.get("stages") or [])]
    tool_event_names = {
        str(name or "").strip()
        for name in list(case_result.get("tool_event_names") or [])
        if str(name or "").strip()
    }
    delegated = bool(str(case_result.get("delegated_agent_id") or "").strip()) or "spawn_agent" in tool_event_names

    explicit_child_turn_count: int | None = None
    for key in ("child_turn_count", "delegated_turn_count", "wait_turn_count"):
        maybe = _int_or_none(case_result.get(key))
        if maybe is None:
            continue
        explicit_child_turn_count = max(0, maybe)
        break
    child_turn_count = explicit_child_turn_count if explicit_child_turn_count is not None else (1 if delegated else 0)

    wait_status = str(case_result.get("wait_status") or "").strip().lower()
    wait_decision = str(case_result.get("wait_decision") or "").strip().lower()
    timeout_hit = any(
        (
            "timeout" in wait_status,
            "timed_out" in wait_status,
            "timeout" in wait_decision,
            "timed_out" in wait_decision,
            bool(case_result.get("wait_timed_out")),
        )
    )
    timeout_count = 1 if timeout_hit else 0

    explicit_fallback_count: int | None = None
    for key in ("fallback_count", "followup_fallback_count", "tool_followup_fallback_count"):
        maybe = _int_or_none(case_result.get(key))
        if maybe is None:
            continue
        explicit_fallback_count = max(0, maybe)
        break
    fallback_stage_count = sum(1 for stage in stages if "fallback" in stage)
    fallback_count = explicit_fallback_count if explicit_fallback_count is not None else fallback_stage_count

    return {
        "request_count": request_count,
        "child_turn_count": child_turn_count,
        "timeout_count": timeout_count,
        "fallback_count": fallback_count,
'''
