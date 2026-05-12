#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import ensure_script_import_paths
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import ensure_script_import_paths

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
REPO_ROOT = _SCRIPT_PATHS.repo_root

from cli.agent_cli.provider import build_planner, load_provider_config
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.runtime_policy import RuntimePolicy
from cli.agent_cli import agent_provider_selection_helpers_runtime as provider_selection_helpers_runtime
from cli.scripts.run_multi_llm_live_cases_analysis import (
    _ci_reuse_block,
    _failed_case_result,
    _failure_category,
    _report_summary,
    _runtime_provider_status,
    _validation_errors,
)
from cli.scripts.run_multi_llm_live_cases_catalog import (
    CASES,
    PROFILE_CHOICES,
    LiveCase,
)
from cli.scripts.run_multi_llm_live_cases_exec import (
    RuntimeToolExecutor,
    _delegation_view,
    _route_view,
    _run_case,
)
from cli.scripts.run_multi_llm_live_cases_runtime import overlay_multi_llm_routes


DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt_54"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_LOG_ROOT = Path("/tmp/agenthub_multi_llm_live_cases")
DEFAULT_TOOL_FOLLOWUP_PROVIDER = "glm"
DEFAULT_TOOL_FOLLOWUP_MODEL = "glm_5"
DEFAULT_TOOL_FOLLOWUP_REASONING_EFFORT = "high"
DEFAULT_TOOL_FOLLOWUP_TIMEOUT = 30
DEFAULT_FINAL_SYNTHESIS_PROVIDER = "glm"
DEFAULT_FINAL_SYNTHESIS_MODEL = "glm_5"
DEFAULT_FINAL_SYNTHESIS_REASONING_EFFORT = "high"
DEFAULT_FINAL_SYNTHESIS_TIMEOUT = 30


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/run_multi_llm_live_cases.py",
        description="Run live multi-LLM collaboration cases against the configured provider routes.",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("AGENT_CLI_PROVIDER") or DEFAULT_PROVIDER,
        help=f"Main provider selector. Defaults to {DEFAULT_PROVIDER}.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("AGENT_CLI_MODEL") or DEFAULT_MODEL,
        help=f"Main model selector. Defaults to {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.environ.get("AGENT_CLI_REASONING_EFFORT") or DEFAULT_REASONING_EFFORT,
        help=f"Main reasoning effort. Defaults to {DEFAULT_REASONING_EFFORT}.",
    )
    parser.add_argument(
        "--workspace-root",
        default=str(REPO_ROOT),
        help="Workspace root used for tool execution. Defaults to repo root.",
    )
    parser.add_argument(
        "--config-cwd",
        default=str(CLI_ROOT),
        help="Config resolution cwd. Defaults to cli/.",
    )
    parser.add_argument(
        "--log-root",
        default=str(DEFAULT_LOG_ROOT),
        help=f"Root directory for per-case llm_io logs. Defaults to {DEFAULT_LOG_ROOT}.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Run only selected case name. Repeat to select multiple cases.",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_CHOICES,
        default="all",
        help="Named case profile. Defaults to all.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Validate every selected case and return non-zero if any case fails smoke checks.",
    )
    parser.add_argument(
        "--ci-gate",
        action="store_true",
        help="Return non-zero when ci_reuse.ci_gate_passed is false.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path to write the full JSON report.",
    )
    parser.add_argument(
        "--tool-followup-provider",
        default="",
        help=(
            "Optional temporary provider override for routes.tool_followup. "
            f"If the selected model has no tool_followup route, defaults to {DEFAULT_TOOL_FOLLOWUP_PROVIDER}."
        ),
    )
    parser.add_argument(
        "--tool-followup-model",
        default="",
        help=(
            "Optional temporary model override for routes.tool_followup. "
            f"If the selected model has no tool_followup route, defaults to {DEFAULT_TOOL_FOLLOWUP_MODEL}."
        ),
    )
    parser.add_argument(
        "--tool-followup-reasoning-effort",
        default="",
        help=(
            "Optional temporary reasoning effort for routes.tool_followup. "
            f"If the selected model has no tool_followup route, defaults to {DEFAULT_TOOL_FOLLOWUP_REASONING_EFFORT}."
        ),
    )
    parser.add_argument(
        "--tool-followup-timeout",
        type=int,
        default=0,
        help=(
            "Optional temporary timeout for routes.tool_followup. "
            f"If the selected model has no tool_followup route, defaults to {DEFAULT_TOOL_FOLLOWUP_TIMEOUT}."
        ),
    )
    parser.add_argument(
        "--final-synthesis-provider",
        default="",
        help=(
            "Optional temporary provider override for routes.final_synthesis. "
            f"If the selected model has no final_synthesis route, defaults to {DEFAULT_FINAL_SYNTHESIS_PROVIDER}."
        ),
    )
    parser.add_argument(
        "--final-synthesis-model",
        default="",
        help=(
            "Optional temporary model override for routes.final_synthesis. "
            f"If the selected model has no final_synthesis route, defaults to {DEFAULT_FINAL_SYNTHESIS_MODEL}."
        ),
    )
    parser.add_argument(
        "--final-synthesis-reasoning-effort",
        default="",
        help=(
            "Optional temporary reasoning effort for routes.final_synthesis. "
            f"If the selected model has no final_synthesis route, defaults to {DEFAULT_FINAL_SYNTHESIS_REASONING_EFFORT}."
        ),
    )
    parser.add_argument(
        "--final-synthesis-timeout",
        type=int,
        default=0,
        help=(
            "Optional temporary timeout for routes.final_synthesis. "
            f"If the selected model has no final_synthesis route, defaults to {DEFAULT_FINAL_SYNTHESIS_TIMEOUT}."
        ),
    )
    return parser


def _selected_cases(names: list[str] | None, *, profile: str = "all") -> list[LiveCase]:
    selected = list(CASES)
    normalized_profile = str(profile or "all").strip() or "all"
    if normalized_profile != "all":
        selected = [case for case in selected if normalized_profile in set(case.profiles)]
    if not names:
        return selected
    requested = {str(name or "").strip() for name in list(names or []) if str(name or "").strip()}
    return [case for case in selected if case.name in requested]


def _route_override_payloads_from_config(config: Any) -> dict[str, dict[str, Any]]:
    raw_model = dict(getattr(config, "raw_model", {}) or {})
    raw_routes = dict(raw_model.get("routes") or {}) if isinstance(raw_model.get("routes"), dict) else {}
    overrides: dict[str, dict[str, Any]] = {}
    for route_name in ("tool_followup", "final_synthesis"):
        route = dict(raw_routes.get(route_name) or {}) if isinstance(raw_routes.get(route_name), dict) else {}
        if not route:
            continue
        payload: dict[str, Any] = {}
        if str(route.get("provider") or "").strip():
            payload["provider"] = str(route.get("provider") or "").strip()
        if str(route.get("model") or "").strip():
            payload["model"] = str(route.get("model") or "").strip()
        if str(route.get("reasoning_effort") or "").strip():
            payload["reasoning_effort"] = str(route.get("reasoning_effort") or "").strip()
        if int(route.get("timeout") or 0) > 0:
            payload["timeout"] = int(route.get("timeout") or 0)
        if payload:
            overrides[route_name] = payload
    return overrides


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    selected = _selected_cases(args.cases, profile=str(args.profile or "all"))
    if not selected:
        parser.error("no matching cases selected")

    os.environ["AGENT_CLI_PROVIDER"] = str(args.provider)
    os.environ["AGENT_CLI_MODEL"] = str(args.model)
    os.environ["AGENT_CLI_REASONING_EFFORT"] = str(args.reasoning_effort)

    planner: Any | None = None
    runtime: AgentCliRuntime | None = None
    case_results: list[dict[str, Any]] = []
    try:
        config = load_provider_config(
            cwd=str(args.config_cwd),
            env_overrides={
                "AGENT_CLI_PROVIDER": str(args.provider),
                "AGENT_CLI_MODEL": str(args.model),
                "AGENT_CLI_REASONING_EFFORT": str(args.reasoning_effort),
            },
        )
        config = overlay_multi_llm_routes(
            config,
            default_tool_followup_provider=DEFAULT_TOOL_FOLLOWUP_PROVIDER,
            default_tool_followup_model=DEFAULT_TOOL_FOLLOWUP_MODEL,
            default_tool_followup_reasoning_effort=DEFAULT_TOOL_FOLLOWUP_REASONING_EFFORT,
            default_tool_followup_timeout=DEFAULT_TOOL_FOLLOWUP_TIMEOUT,
            default_final_synthesis_provider=DEFAULT_FINAL_SYNTHESIS_PROVIDER,
            default_final_synthesis_model=DEFAULT_FINAL_SYNTHESIS_MODEL,
            default_final_synthesis_reasoning_effort=DEFAULT_FINAL_SYNTHESIS_REASONING_EFFORT,
            default_final_synthesis_timeout=DEFAULT_FINAL_SYNTHESIS_TIMEOUT,
            tool_followup_provider=str(args.tool_followup_provider or "").strip(),
            tool_followup_model=str(args.tool_followup_model or "").strip(),
            tool_followup_reasoning_effort=str(args.tool_followup_reasoning_effort or "").strip(),
            tool_followup_timeout=int(args.tool_followup_timeout or 0),
            final_synthesis_provider=str(args.final_synthesis_provider or "").strip(),
            final_synthesis_model=str(args.final_synthesis_model or "").strip(),
            final_synthesis_reasoning_effort=str(args.final_synthesis_reasoning_effort or "").strip(),
            final_synthesis_timeout=int(args.final_synthesis_timeout or 0),
        )
        planner = build_planner(config, cwd=str(args.config_cwd))
        if hasattr(planner, "reference_parity_enabled"):
            # This harness validates synthetic post-tool followup/synthesis behavior.
            planner.reference_parity_enabled = False
        runtime = AgentCliRuntime(
            runtime_policy=RuntimePolicy.normalized(
                approval_policy="never",
                sandbox_mode="danger-full-access",
                web_search_mode="disabled",
                network_access_enabled=True,
            )
        )
        runtime.set_cwd(str(args.workspace_root))
        route_overrides = _route_override_payloads_from_config(config)
        if route_overrides:
            provider_selection_helpers_runtime.set_session_route_overrides(
                runtime.agent,
                route_overrides,
            )
        executor = RuntimeToolExecutor(runtime)

        log_root = (
            Path(str(args.log_root)).resolve()
            / f"{str(args.provider or '').strip() or 'provider'}_{str(args.model or '').strip() or 'model'}"
        )
        log_root.mkdir(parents=True, exist_ok=True)
        resolved_workspace_root = str(Path(str(args.workspace_root)).resolve())
        runtime_status = _runtime_provider_status(runtime)
        for case in selected:
            try:
                case_results.append(
                    _run_case(
                        planner,
                        executor,
                        runtime,
                        case=case,
                        workspace_root=resolved_workspace_root,
                        log_root=log_root,
                    )
                )
            except Exception as exc:
                case_results.append(
                    _failed_case_result(
                        case,
                        error_code="case_execution_failure",
                        error_message=str(exc),
                        runtime_provider_status=runtime_status,
                    )
                )
    except Exception as exc:
        case_results = [
            _failed_case_result(
                case,
                error_code="bootstrap_failure",
                error_message=str(exc),
            )
            for case in selected
        ]

    case_lookup = {case.name: case for case in selected}
    failed_cases: list[str] = []
    successful_cases: list[str] = []
    for case_result in case_results:
        case_name = str(case_result.get("name") or "").strip()
        case = case_lookup.get(case_name)
        preset_errors = [
            str(item or "").strip()
            for item in list(case_result.get("validation_errors") or [])
            if str(item or "").strip()
        ]
        if bool(case_result.get("__fatal_error__")):
            errors = preset_errors or ["case_execution_failure"]
        else:
            computed_errors = _validation_errors(case, case_result) if case is not None else ["unknown_case"]
            errors = list(dict.fromkeys([*preset_errors, *computed_errors]))
        case_result["validation_errors"] = errors
        case_result["passed"] = not errors
        case_result["failure_category"] = _failure_category(errors, case_result)
        if errors:
            failed_cases.append(case_name)
        else:
            successful_cases.append(case_name)

    planner_summary = planner.public_summary() if planner is not None else {}
    report = {
        "provider": str(args.provider),
        "model": str(args.model),
        "reasoning_effort": str(args.reasoning_effort),
        "profile": str(args.profile),
        "strict": bool(args.strict),
        "workspace_root": str(Path(str(args.workspace_root)).resolve()),
        "config_cwd": str(Path(str(args.config_cwd)).resolve()),
        "planner_summary": planner_summary,
        "routes": _route_view(planner_summary),
        "delegation": _delegation_view(planner_summary),
        "runtime_provider_status": _runtime_provider_status(runtime),
        "cases": case_results,
        "selected_cases": [case.name for case in selected],
        "successful_cases": successful_cases,
        "failed_cases": failed_cases,
        "passed": not failed_cases,
        "summary": _report_summary(case_results),
    }
    report["ci_reuse"] = _ci_reuse_block(
        profile=str(args.profile or "all"),
        strict=bool(args.strict),
        selected_case_names=[case.name for case in selected],
        summary=dict(report.get("summary") or {}),
    )

    output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(output)
    if args.out:
        out_path = Path(str(args.out)).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    if args.ci_gate and not bool((report.get("ci_reuse") or {}).get("ci_gate_passed")):
        return 2
    if args.strict and failed_cases:
        return 1
    if any(str(item.get("failure_category") or "") == "bootstrap_failure" for item in case_results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
