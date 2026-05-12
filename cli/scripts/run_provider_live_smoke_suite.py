#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SuiteStep:
    key: str
    label: str
    command: tuple[str, ...]
    output_path: str
    required_paths: tuple[str, ...] = ()


def _default_out_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="agenthub_provider_live_smoke_")).resolve()


def _preview_text(value: str, *, limit: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_suite_steps(
    args: argparse.Namespace, *, out_root: Path, python_executable: str | None = None
) -> list[SuiteStep]:
    repo_root = Path(str(args.repo_root or "")).expanduser().resolve()
    python_bin = str(python_executable or sys.executable)
    headless_out = out_root / "headless_provider_matrix.json"
    provider_two_turn_out = out_root / "provider_two_turn_live_smoke.json"
    previous_response_id_out_dir = out_root / "previous_response_id_rejection"
    additional_permissions_out_dir = out_root / "additional_permissions_exec_contract"
    bridged_out_dir = out_root / "request_user_input_bridged"
    steps: list[SuiteStep] = []
    if not bool(args.skip_headless_matrix):
        steps.append(
            SuiteStep(
                key="headless_provider_matrix",
                label="Headless provider matrix",
                command=(
                    python_bin,
                    str(repo_root / "cli" / "scripts" / "benchmark_headless_models.py"),
                    "--scenario",
                    "single_turn_headless",
                    "--runs",
                    "1",
                    "--max-workers",
                    "4",
                    "--timeout",
                    "60",
                    "--case",
                    "openai:gpt_54",
                    "--case",
                    "anthropic:claude-sonnet-4-6",
                    "--case",
                    "deepseek:deepseek_chat",
                    "--case",
                    "glm:glm_5",
                    "--json",
                    "--out",
                    str(headless_out),
                ),
                output_path=str(headless_out),
            )
        )
    if not bool(args.skip_provider_two_turn_continuity):
        steps.append(
            SuiteStep(
                key="provider_two_turn_continuity",
                label="Provider two-turn live continuity",
                command=(
                    python_bin,
                    str(repo_root / "cli" / "scripts" / "provider_two_turn_live_smoke.py"),
                    "--case",
                    "openai:gpt_54",
                    "--case",
                    "anthropic:claude_sonnet_46",
                    "--timeout",
                    str(float(args.provider_two_turn_timeout or 120)),
                    "--max-workers",
                    "2",
                    "--json",
                    "--out",
                    str(provider_two_turn_out),
                ),
                output_path=str(provider_two_turn_out),
            )
        )
    if not bool(args.skip_previous_response_id_rejection):
        steps.append(
            SuiteStep(
                key="previous_response_id_rejection",
                label="previous_response_id rejection live fallback",
                command=(
                    python_bin,
                    str(
                        repo_root
                        / "cli"
                        / "scripts"
                        / "previous_response_id_rejection_live_harness.py"
                    ),
                    "--auth-json",
                    str(Path(str(args.agenthub_auth or "")).expanduser().resolve()),
                    "--base-url",
                    str(args.base_url or ""),
                    "--model",
                    str(args.model or ""),
                    "--effort",
                    str(args.effort or ""),
                    "--out-dir",
                    str(previous_response_id_out_dir),
                ),
                output_path=str(previous_response_id_out_dir),
                required_paths=(str(Path(str(args.agenthub_auth or "")).expanduser().resolve()),),
            )
        )
    if not bool(args.skip_additional_permissions_exec_contract):
        steps.append(
            SuiteStep(
                key="additional_permissions_exec_contract",
                label="additional_permissions exec approval replay",
                command=(
                    python_bin,
                    str(
                        repo_root
                        / "cli"
                        / "scripts"
                        / "additional_permissions_exec_live_harness.py"
                    ),
                    "--auth-json",
                    str(Path(str(args.agenthub_auth or "")).expanduser().resolve()),
                    "--base-url",
                    str(args.base_url or ""),
                    "--model",
                    str(args.model or ""),
                    "--effort",
                    str(args.effort or ""),
                    "--out-dir",
                    str(additional_permissions_out_dir),
                ),
                output_path=str(additional_permissions_out_dir),
                required_paths=(str(Path(str(args.agenthub_auth or "")).expanduser().resolve()),),
            )
        )
    if not bool(args.skip_bridged_request_user_input):
        steps.append(
            SuiteStep(
                key="bridged_request_user_input",
                label="Bridged request_user_input A/B",
                command=(
                    python_bin,
                    str(repo_root / "cli" / "scripts" / "request_user_input_bridged_openai_ab.py"),
                    "--repo-root",
                    str(repo_root),
                    "--codex-bin",
                    str(Path(str(args.codex_bin or "")).expanduser().resolve()),
                    "--agenthub-auth",
                    str(Path(str(args.agenthub_auth or "")).expanduser().resolve()),
                    "--codex-auth",
                    str(Path(str(args.codex_auth or "")).expanduser().resolve()),
                    "--base-url",
                    str(args.base_url or ""),
                    "--model",
                    str(args.model or ""),
                    "--effort",
                    str(args.effort or ""),
                    "--runs",
                    str(int(args.bridged_runs or 1)),
                    "--out-dir",
                    str(bridged_out_dir),
                ),
                output_path=str(bridged_out_dir),
                required_paths=(
                    str(Path(str(args.codex_bin or "")).expanduser().resolve()),
                    str(Path(str(args.agenthub_auth or "")).expanduser().resolve()),
                    str(Path(str(args.codex_auth or "")).expanduser().resolve()),
                ),
            )
        )
    return steps


def run_suite_step(step: SuiteStep, *, cwd: Path, dry_run: bool = False) -> dict[str, Any]:
    missing_paths = [path for path in step.required_paths if not Path(path).exists()]
    if missing_paths:
        return {
            "key": step.key,
            "label": step.label,
            "status": "skipped",
            "reason": "missing_required_paths",
            "missing_paths": missing_paths,
            "command": list(step.command),
            "output_path": step.output_path,
        }
    if dry_run:
        return {
            "key": step.key,
            "label": step.label,
            "status": "planned",
            "command": list(step.command),
            "output_path": step.output_path,
        }
    completed = subprocess.run(
        list(step.command),
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )
    return {
        "key": step.key,
        "label": step.label,
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": int(completed.returncode),
        "command": list(step.command),
        "output_path": step.output_path,
        "stdout_preview": _preview_text(completed.stdout),
        "stderr_preview": _preview_text(completed.stderr),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the canonical AgentHub provider live smoke suite.",
    )
    parser.add_argument("--repo-root", default="/home/lyc/project/AgentHub")
    parser.add_argument("--out-root", default="")
    parser.add_argument(
        "--codex-bin", default="/home/lyc/project/AgentHubRef/codex_ref/codex-rs/target/debug/codex"
    )
    parser.add_argument(
        "--agenthub-auth", default="/home/lyc/project/AgentHub/cli/.config/auth.json"
    )
    parser.add_argument("--codex-auth", default="~/.codex/auth.json")
    parser.add_argument("--base-url", default="https://relay05.gaccode.com/codex/v1")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--bridged-runs", type=int, default=1)
    parser.add_argument("--provider-two-turn-timeout", type=float, default=120)
    parser.add_argument("--skip-headless-matrix", action="store_true")
    parser.add_argument("--skip-provider-two-turn-continuity", action="store_true")
    parser.add_argument("--skip-previous-response-id-rejection", action="store_true")
    parser.add_argument("--skip-additional-permissions-exec-contract", action="store_true")
    parser.add_argument("--skip-bridged-request-user-input", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = Path(str(args.repo_root or "")).expanduser().resolve()
    out_root = (
        Path(str(args.out_root or "")).expanduser().resolve()
        if str(args.out_root or "").strip()
        else _default_out_root()
    )
    out_root.mkdir(parents=True, exist_ok=True)
    steps = build_suite_steps(args, out_root=out_root)
    results = [
        run_suite_step(step, cwd=repo_root / "cli", dry_run=bool(args.dry_run)) for step in steps
    ]
    summary = {
        "repo_root": str(repo_root),
        "out_root": str(out_root),
        "dry_run": bool(args.dry_run),
        "steps": results,
        "counts": {
            "passed": sum(1 for item in results if item.get("status") == "passed"),
            "failed": sum(1 for item in results if item.get("status") == "failed"),
            "skipped": sum(1 for item in results if item.get("status") == "skipped"),
            "planned": sum(1 for item in results if item.get("status") == "planned"),
        },
        "step_specs": [asdict(step) for step in steps],
    }
    summary_path = out_root / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if any(item.get("status") == "failed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
