#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import ensure_script_import_paths
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import ensure_script_import_paths

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
REPO_ROOT = _SCRIPT_PATHS.repo_root

# ruff: noqa: E402,I001
from cli.agent_cli.provider import build_planner, load_provider_config
from cli.scripts.run_policy_helper_live_cases_catalog import (
    POLICY_HELPER_COMBO_CATALOG,
    POLICY_HELPER_PROFILE_MATRIX,
    PROFILE_CHOICES,
    PolicyHelperCase,
    PolicyHelperCombo,
)
from cli.scripts.run_policy_helper_live_cases_runtime import (
    _aggregate_profile_summary,
    _overlay_policy_helper_route,
    _report_summary,
    _route_view,
    _run_case,
)
from cli.scripts.run_policy_helper_live_cases_selection import (
    _selected_cases,
    _selected_helper_combos,
)


DEFAULT_PROVIDER = "glm"
DEFAULT_MODEL = "glm_5"
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_LOG_ROOT = Path("/tmp/agenthub_policy_helper_live_cases")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/run_policy_helper_live_cases.py",
        description="Run live policy_helper rewrite/rerank/extract cases against a chat-completions planner.",
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
        default="single",
        help="Helper combo profile. Defaults to single.",
    )
    parser.add_argument(
        "--helper-combo",
        action="append",
        dest="helper_combos",
        help="Select helper combo id inside a profile run. Repeat to keep multiple combos.",
    )
    parser.add_argument(
        "--policy-helper-provider",
        default="",
        help="Optional temporary provider override for routes.policy_helper. Used by profile=single.",
    )
    parser.add_argument(
        "--policy-helper-model",
        default="",
        help="Optional temporary model override for routes.policy_helper. Used by profile=single.",
    )
    parser.add_argument(
        "--policy-helper-reasoning-effort",
        default="low",
        help="Temporary reasoning effort for routes.policy_helper. Used by profile=single.",
    )
    parser.add_argument(
        "--policy-helper-timeout",
        type=int,
        default=20,
        help="Temporary timeout for routes.policy_helper. Used by profile=single.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional path to write the full JSON report.",
    )
    return parser


def _run_combo(
    *,
    base_config: Any,
    config_cwd: str,
    main_provider: str,
    main_model: str,
    main_reasoning_effort: str,
    combo: PolicyHelperCombo,
    selected_cases: list[PolicyHelperCase],
    log_root: Path,
) -> dict[str, Any]:
    config = _overlay_policy_helper_route(
        base_config,
        provider=str(combo.provider or "").strip(),
        model=str(combo.model or "").strip(),
        reasoning_effort=str(combo.reasoning_effort or "").strip(),
        timeout=int(combo.timeout or 0),
    )
    planner = build_planner(config, cwd=str(config_cwd))
    planner_kind = str(getattr(getattr(planner, "config", None), "planner_kind", "") or "")
    if not all(
        hasattr(planner, name)
        for name in ("_policy_llm_query_rewrite", "_policy_llm_rerank", "_policy_llm_extract")
    ):
        raise SystemExit(
            f"policy_helper live cases require a chat-completions planner with policy helper hooks; got planner_kind={planner_kind or '-'}"
        )
    planner_summary = planner.public_summary()
    routes = _route_view(planner_summary)
    case_results = [
        {
            **_run_case(planner, case=case, log_root=log_root),
            "helper_combo_id": combo.combo_id,
        }
        for case in selected_cases
    ]
    return {
        "helper_combo": combo.as_dict(),
        "planner_summary": planner_summary,
        "routes": routes,
        "recommended_baseline": {
            "main": {
                "provider": str(main_provider),
                "model": str(main_model),
                "reasoning_effort": str(main_reasoning_effort),
            },
            "policy_helper": dict(routes.get("policy_helper") or {}),
            "reason": "live_policy_helper_cases",
            "helper_combo": combo.as_dict(),
        },
        "cases": case_results,
        "summary": _report_summary(case_results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    selected = _selected_cases(args.cases)
    if not selected:
        parser.error("no matching cases selected")
    try:
        selected_combos = _selected_helper_combos(
            profile=str(args.profile or "single"),
            helper_combos=list(args.helper_combos or []),
            policy_helper_provider=str(args.policy_helper_provider or "").strip(),
            policy_helper_model=str(args.policy_helper_model or "").strip(),
            policy_helper_reasoning_effort=str(args.policy_helper_reasoning_effort or "").strip(),
            policy_helper_timeout=int(args.policy_helper_timeout or 0),
        )
    except ValueError as exc:
        parser.error(str(exc))

    base_config = load_provider_config(
        cwd=str(args.config_cwd),
        env_overrides={
            "AGENT_CLI_PROVIDER": str(args.provider),
            "AGENT_CLI_MODEL": str(args.model),
            "AGENT_CLI_REASONING_EFFORT": str(args.reasoning_effort),
        },
    )
    if base_config is None:
        raise SystemExit("failed to resolve main provider config")

    log_root = Path(str(args.log_root)).resolve()
    log_root.mkdir(parents=True, exist_ok=True)
    run_reports = [
        _run_combo(
            base_config=base_config,
            config_cwd=str(args.config_cwd),
            main_provider=str(args.provider),
            main_model=str(args.model),
            main_reasoning_effort=str(args.reasoning_effort),
            combo=combo,
            selected_cases=selected,
            log_root=log_root if len(selected_combos) == 1 else (log_root / combo.combo_id),
        )
        for combo in selected_combos
    ]
    profile_summary = (
        dict(run_reports[0].get("summary") or {})
        if len(run_reports) == 1
        else _aggregate_profile_summary(run_reports)
    )

    report = {
        "provider": str(args.provider),
        "model": str(args.model),
        "reasoning_effort": str(args.reasoning_effort),
        "config_cwd": str(Path(str(args.config_cwd)).resolve()),
        "profile": str(args.profile or "single"),
        "helper_combos": [combo.as_dict() for combo in selected_combos],
        "runs": run_reports,
        "summary": profile_summary,
    }
    if len(run_reports) == 1:
        single = run_reports[0]
        report.update(
            {
                "helper_combo": dict(single.get("helper_combo") or {}),
                "planner_summary": dict(single.get("planner_summary") or {}),
                "routes": dict(single.get("routes") or {}),
                "recommended_baseline": dict(single.get("recommended_baseline") or {}),
                "cases": list(single.get("cases") or []),
            }
        )
    else:
        report["matrix_summary"] = {
            str(run.get("helper_combo", {}).get("combo_id") or ""): dict(run.get("summary") or {})
            for run in run_reports
        }
        report["failure_categories"] = dict(profile_summary.get("failure_categories") or {})

    if len(selected_combos) > 1 and (
        str(args.policy_helper_provider or "").strip()
        or str(args.policy_helper_model or "").strip()
    ):
        parser.error(
            "--policy-helper-provider/--policy-helper-model are only valid when --profile=single"
        )

    if str(args.profile or "single").strip() == "single":
        report["policy_helper_override"] = {
            "provider": str(args.policy_helper_provider or "").strip(),
            "model": str(args.policy_helper_model or "").strip(),
            "reasoning_effort": str(args.policy_helper_reasoning_effort or "").strip(),
            "timeout": int(args.policy_helper_timeout or 0),
        }
    else:
        report["policy_helper_override"] = {
            "provider": "",
            "model": "",
            "reasoning_effort": "",
            "timeout": 0,
        }

    report["helper_combo_catalog"] = [combo.as_dict() for combo in POLICY_HELPER_COMBO_CATALOG]
    if str(args.profile or "single").strip() != "single":
        report["profile_combo_matrix"] = {
            key: list(value) for key, value in POLICY_HELPER_PROFILE_MATRIX.items()
        }

    if not run_reports:
        report["summary"] = _report_summary([])

    if len(run_reports) == 1 and not report.get("routes"):
        report["routes"] = {}
    if len(run_reports) == 1 and "planner_summary" not in report:
        report["planner_summary"] = {}
    if len(run_reports) == 1 and "cases" not in report:
        report["cases"] = []
    if len(run_reports) == 1 and "recommended_baseline" not in report:
        report["recommended_baseline"] = {}
    if len(run_reports) == 1 and "helper_combo" not in report:
        report["helper_combo"] = {}

    if len(run_reports) > 1:
        # Keep top-level route/case placeholders explicit for matrix consumers.
        report["routes"] = {}
        report["cases"] = []
        report["recommended_baseline"] = {}
        report["planner_summary"] = {}

    if str(args.profile or "single").strip() == "single" and run_reports:
        report["matrix_summary"] = {
            str(run_reports[0].get("helper_combo", {}).get("combo_id") or ""): dict(
                run_reports[0].get("summary") or {}
            )
        }
        report["failure_categories"] = dict(
            (report.get("summary") or {}).get("failure_categories") or {}
        )

    if str(args.profile or "single").strip() == "single" and not report.get("helper_combo"):
        report["helper_combo"] = selected_combos[0].as_dict() if selected_combos else {}

    if str(args.profile or "single").strip() != "single":
        report["helper_combo"] = {}

    if str(args.profile or "single").strip() == "single":
        report["summary"] = (
            dict(run_reports[0].get("summary") or {}) if run_reports else _report_summary([])
        )
        report["failure_categories"] = dict(
            (report.get("summary") or {}).get("failure_categories") or {}
        )

    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        out_path = Path(str(args.out)).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
