#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.scripts.script_runtime_helpers import (
    apply_provider_home_override_env,
    normalize_optional_provider_home_override,
    resolve_effective_script_provider_home_dir,
)

from cli.agent_cli.acceptance_support.web_search_wave02_support import (
    DEFAULT_AGENTHUB_MAIN,
    DEFAULT_CLAUDE_BIN,
    DEFAULT_CODEX_HOME,
    DEFAULT_REPORT_ROOT,
    PROMPT_FAMILIES,
    PromptFamily,
    _agenthub_detail,
    _agenthub_parity_evidence,
    _case_report,
    _claude_detail,
    _claude_parity_evidence,
    _codex_detail,
    _codex_parity_evidence,
    _default_openai_base_url,
    _effective_web_search_mode_for_turn,
    _external_web_access_for_turn,
    _iso_now,
    _markdown_report,
    _outcome_classification,
    _selected_cases,
    _skipped_command,
    _tool_surface_contract,
    _write_json,
    _write_text,
    build_case_system_summary,
    _run_command,
)


CLI_ROOT = Path(__file__).resolve().parents[1]


def _provider_home_report_fields(provider_home: str) -> dict[str, str]:
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    return {
        "provider_home": str(
            resolve_effective_script_provider_home_dir(
                cwd=CLI_ROOT,
                provider_home=normalized_provider_home,
            )
        ),
        "provider_home_override": normalized_provider_home,
        "provider_home_source": "explicit_override" if normalized_provider_home else "runtime_default",
    }


def _build_agenthub_env(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    env["AGENT_CLI_PROVIDER"] = str(args.provider)
    env["AGENT_CLI_MODEL"] = str(args.model)
    env["AGENT_CLI_REASONING_EFFORT"] = str(args.reasoning_effort)
    apply_provider_home_override_env(env, provider_home=args.provider_home)
    if str(args.openai_base_url or "").strip():
        env["OPENAI_BASE_URL"] = str(args.openai_base_url)
        env["AGENT_CLI_BASE_URL"] = str(args.openai_base_url)
    return env


def _build_codex_env(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    if args.codex_home:
        env["CODEX_HOME"] = str(Path(args.codex_home).resolve())
    return env


def _build_agenthub_command(case: PromptFamily, args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(Path(args.agenthub_main).resolve()),
        "--headless",
        "--json",
        "--approval-policy",
        "never",
        "--sandbox-mode",
        str(args.sandbox_mode),
        "--web-search-mode",
        str(args.web_search_mode),
        "--prompt",
        case.prompt,
    ]


def _build_codex_command(case: PromptFamily, args: argparse.Namespace) -> list[str]:
    command = [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        str(args.sandbox_mode),
        "-C",
        str(Path(args.workdir).resolve()),
        "-m",
        str(args.model),
    ]
    if str(args.reasoning_effort or "").strip():
        command.extend(["-c", f'model_reasoning_effort="{args.reasoning_effort}"'])
    if str(args.codex_provider_id or "").strip():
        command.extend(["-c", f'model_provider="{args.codex_provider_id}"'])
    command.append(case.prompt)
    return command


def _build_claude_command(case: PromptFamily, args: argparse.Namespace) -> list[str]:
    return [
        str(args.claude_bin),
        "-p",
        "--output-format",
        "json",
        "--model",
        str(args.claude_model),
        "--permission-mode",
        str(args.claude_permission_mode),
        case.prompt,
    ]


def _parity_evidence(system: str, detail: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if system == "agenthub":
        return _agenthub_parity_evidence(detail, args)
    if system == "codex":
        return _codex_parity_evidence(detail, args)
    return _claude_parity_evidence(detail)


def _observable_execution_path(system: str, parity_evidence: dict[str, Any]) -> dict[str, Any]:
    if system == "agenthub":
        codex = dict(parity_evidence.get("codex_comparable") or {})
        agenthub = dict(parity_evidence.get("agenthub") or {})
        return {
            "web_search_call_seen": bool(codex.get("web_search_call_seen")),
            "effective_backend_id": str(agenthub.get("effective_backend_id") or "").strip(),
            "execution_path": str(agenthub.get("execution_path") or "").strip(),
            "turn_search_phase": str(agenthub.get("turn_search_phase") or "").strip(),
            "fallback_reason": str(agenthub.get("fallback_reason") or "").strip(),
        }
    if system == "codex":
        codex = dict(parity_evidence.get("codex_comparable") or {})
        return {
            "web_search_call_seen": bool(codex.get("web_search_call_seen")),
            "action_families": list(codex.get("action_families") or []),
            "external_web_access": codex.get("external_web_access"),
        }
    claude = dict(parity_evidence.get("claude_comparable") or {})
    return {
        "server_tool_use_seen": bool(claude.get("server_tool_use_seen")),
        "web_search_tool_result_seen": bool(claude.get("web_search_tool_result_seen")),
        "web_search_requests": int(claude.get("web_search_requests") or 0),
        "observation_mode": str(claude.get("observation_mode") or "").strip(),
    }


def _request_contract(system: str, args: argparse.Namespace, parity_evidence: dict[str, Any]) -> dict[str, Any]:
    stream_complete_truth: dict[str, Any] = {}
    if system == "agenthub":
        stream_complete_truth = dict((parity_evidence.get("agenthub") or {}).get("stream_complete_truth") or {})
    elif system == "codex":
        stream_complete_truth = dict((parity_evidence.get("codex_comparable") or {}).get("stream_complete_truth") or {})
    else:
        stream_complete_truth = dict((parity_evidence.get("claude_comparable") or {}).get("stream_complete_truth") or {})
    effective_mode = _effective_web_search_mode_for_turn(args.web_search_mode, args.sandbox_mode)
    return {
        "reasoning_effort": str(args.reasoning_effort),
        "web_search_mode": str(args.web_search_mode),
        "sandbox_mode": str(args.sandbox_mode),
        "effective_web_search_mode": effective_mode,
        "external_web_access": _external_web_access_for_turn(args.web_search_mode, args.sandbox_mode),
        "tool_surface": _tool_surface_contract(system),
        "stream_complete_truth": stream_complete_truth,
    }


def _run_case_for_system(
    *,
    system: str,
    case: PromptFamily,
    args: argparse.Namespace,
    out_root: Path,
) -> dict[str, Any]:
    case_root = out_root / case.case_id / system
    case_root.mkdir(parents=True, exist_ok=True)
    stdout_path = case_root / "stdout.json"
    stderr_path = case_root / "stderr.log"
    if system not in set(case.applicability):
        result = _skipped_command(
            system=system,
            command=[],
            cwd=Path(args.workdir).resolve(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            reason="not_applicable_for_case",
        )
    elif args.dry_run:
        command = (
            _build_agenthub_command(case, args)
            if system == "agenthub"
            else _build_codex_command(case, args)
            if system == "codex"
            else _build_claude_command(case, args)
        )
        result = _skipped_command(
            system=system,
            command=command,
            cwd=Path(args.workdir).resolve(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            reason="dry_run",
        )
    else:
        command = (
            _build_agenthub_command(case, args)
            if system == "agenthub"
            else _build_codex_command(case, args)
            if system == "codex"
            else _build_claude_command(case, args)
        )
        env = (
            _build_agenthub_env(args)
            if system == "agenthub"
            else _build_codex_env(args)
            if system == "codex"
            else dict(os.environ)
        )
        cwd = CLI_ROOT if system == "agenthub" else Path(args.workdir).resolve()
        result = _run_command(
            system=system,
            command=command,
            cwd=cwd,
            env=env,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_seconds=int(args.timeout_seconds),
        )
    detail = (
        _agenthub_detail(stdout_path)
        if system == "agenthub"
        else _codex_detail(stdout_path)
        if system == "codex"
        else _claude_detail(stdout_path)
    )
    summary = build_case_system_summary(
        system=system,
        case=case,
        detail=detail,
        result=result,
        args=args,
        detail_path=case_root / "detail.json",
    )
    summary["request_contract"] = _request_contract(system, args, summary["parity_evidence"])
    summary["observable_execution_path"] = _observable_execution_path(system, summary["parity_evidence"])
    summary["outcome_classification"] = _outcome_classification(
        system,
        run=summary["run"],
        answer_quality=summary["answer_quality"],
        parity_evidence=summary["parity_evidence"],
    )
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/web_search_wave02_acceptance.py",
        description="Run the Web Search Wave 02 live acceptance bundle across AgentHub, Codex, and optional Claude-style lanes.",
    )
    parser.add_argument("--case", action="append", dest="cases", help="Optional case id filter.")
    parser.add_argument("--out-dir", default="", help="Output directory. Defaults to /tmp bundle root.")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument(
        "--provider-home",
        default="",
        help=(
            "Optional provider runtime home override passed via AGENTHUB_PROVIDER_HOME. "
            "Defaults to runtime-managed provider home resolution."
        ),
    )
    parser.add_argument("--openai-base-url", default=_default_openai_base_url())
    parser.add_argument("--agenthub-main", default=str(DEFAULT_AGENTHUB_MAIN))
    parser.add_argument("--workdir", default=str(CLI_ROOT))
    parser.add_argument("--web-search-mode", default="live", choices=("disabled", "cached", "live"))
    parser.add_argument("--sandbox-mode", default="danger-full-access", choices=("read-only", "workspace-write", "danger-full-access"))
    parser.add_argument("--codex-home", default=str(DEFAULT_CODEX_HOME))
    parser.add_argument("--codex-provider-id", default="openai")
    parser.add_argument("--claude-bin", default=DEFAULT_CLAUDE_BIN)
    parser.add_argument("--claude-model", default="sonnet")
    parser.add_argument("--claude-permission-mode", default="bypassPermissions")
    parser.add_argument("--include-claude", action="store_true", help="Actually run the Claude-style lane when applicable.")
    parser.add_argument("--dry-run", action="store_true", help="Plan commands and report structure without executing them.")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    selected_cases = _selected_cases(args.cases)
    if not selected_cases:
        raise SystemExit("no matching cases selected")
    out_dir = (
        Path(args.out_dir).resolve()
        if str(args.out_dir or "").strip()
        else Path(tempfile.mkdtemp(prefix="agenthub_web_search_wave02_", dir=str(DEFAULT_REPORT_ROOT.parent)))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    report_cases: list[dict[str, Any]] = []
    for case in selected_cases:
        systems_to_run = ["agenthub", "codex"]
        if "claude" in case.applicability:
            systems_to_run.append("claude")
        system_rows: list[dict[str, Any]] = []
        for system in systems_to_run:
            if system == "claude" and not args.include_claude:
                row = _run_case_for_system(
                    system=system,
                    case=case,
                    args=argparse.Namespace(**{**vars(args), "dry_run": True}),
                    out_root=out_dir,
                )
                if row["run"]["skip_reason"] == "dry_run":
                    row["run"]["skip_reason"] = "claude_lane_not_requested"
                    row["run"]["skipped"] = True
                    row["outcome_classification"] = {
                        "classification": "not_run",
                        "reason": "claude_lane_not_requested",
                        "inferred": False,
                    }
                system_rows.append(row)
                continue
            system_rows.append(_run_case_for_system(system=system, case=case, args=args, out_root=out_dir))
        report_cases.append(_case_report(case, system_rows, args))
    report = {
        "suite": "web_search_wave02_live_acceptance",
        "contract_version": "wave03_task_k_parity_contract_v1",
        "generated_at": _iso_now(),
        "out_dir": str(out_dir),
        **_provider_home_report_fields(str(args.provider_home or "")),
        "provider": str(args.provider),
        "model": str(args.model),
        "reasoning_effort": str(args.reasoning_effort),
        "web_search_mode": str(args.web_search_mode),
        "dry_run": bool(args.dry_run),
        "cases": report_cases,
    }
    json_path = out_dir / "web_search_wave02_acceptance.report.json"
    md_path = out_dir / "web_search_wave02_acceptance.report.md"
    _write_json(json_path, report)
    _write_text(md_path, _markdown_report(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"out_dir={out_dir}")
        print(f"json_report={json_path}")
        print(f"markdown_report={md_path}")
        print(f"cases={','.join(case.case_id for case in selected_cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
