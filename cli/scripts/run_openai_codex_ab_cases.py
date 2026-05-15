#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from cli.scripts.script_runtime_helpers import (
        ensure_script_import_paths,
        resolve_model_and_reasoning_settings,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (
        ensure_script_import_paths,
        resolve_model_and_reasoning_settings,
    )

try:
    from cli.scripts.run_openai_codex_ab_cases_runtime import (
        _agenthub_provider_used,
        _bool_text,
        _case_markdown,
        _layer_path,
        _now_iso,
        _read_json,
        _run_attempt,
        _summary_excerpt,
        _workspace_inventory,
        build_report,
        run_case_attempts,
        write_report_files,
    )
    from cli.scripts.run_openai_codex_ab_cases_runtime import (
        _selected_cases as _select_cases,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_openai_codex_ab_cases_runtime import (  # type: ignore[no-redef]
        _agenthub_provider_used,
        _bool_text,
        _case_markdown,
        _layer_path,
        _now_iso,
        _read_json,
        _run_attempt,
        _summary_excerpt,
        _workspace_inventory,
        build_report,
        run_case_attempts,
        write_report_files,
    )
    from run_openai_codex_ab_cases_runtime import (
        _selected_cases as _select_cases,
    )

__all__ = [
    "CASES",
    "CLI_ROOT",
    "DEFAULT_OPENAI_BASE_URL",
    "HARNESS_PATH",
    "PROJECT_ROOT",
    "CaseSpec",
    "_agenthub_provider_used",
    "_bool_text",
    "_case_markdown",
    "_layer_path",
    "_now_iso",
    "_read_json",
    "_run_attempt",
    "_selected_cases",
    "_summary_excerpt",
    "_workspace_inventory",
    "build_parser",
    "build_report",
    "main",
    "run_case_attempts",
    "write_report_files",
]

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
PROJECT_ROOT = _SCRIPT_PATHS.repo_root

CLI_ROOT = _SCRIPT_PATHS.cli_root
HARNESS_PATH = CLI_ROOT / "scripts" / "benchmark_emptydir_ab.py"

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class CaseSpec:
    name: str
    prompt: str
    validate: str = ""


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        name="case_01_emptydir",
        prompt=(
            "当前目录中忽略以 . 开头的隐藏文件后，是否为空？"
            "如果为空，只用一句中文说明；如果不为空，列出一层文件名。"
            "不要创建或修改任何文件。"
        ),
    ),
    CaseSpec(
        name="case_02_python_hello",
        prompt=(
            "当前目录是空的。请创建一个最小 Python 项目："
            "main.py 输出 hello world，README.md 写运行方法。"
            "完成后简要说明创建了哪些文件。"
        ),
        validate="python main.py",
    ),
    CaseSpec(
        name="case_03_rg_todo",
        prompt=(
            "请在当前目录创建 sample.py，里面放两个 TODO 注释；"
            "再告诉我如何用 rg 搜到它们。不要安装额外依赖。"
        ),
        validate='rg -n "TODO" sample.py',
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/run_openai_codex_ab_cases.py",
        description="Run the fixed 3-case OpenAI gpt-5.4 Codex-vs-AgentHub empty-dir A/B harness.",
    )
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="")
    parser.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    parser.add_argument("--agenthub-interaction-profile", default="codex_openai")
    parser.add_argument(
        "--codex-provider-id",
        default="",
        help="Optional Codex provider id for ephemeral config. Defaults to harness auto-detection.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Optional case name filter. Repeat to select multiple cases.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=2,
        help="Maximum attempts per case when AgentHub falls back off provider path.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument(
        "--out-root",
        default="",
        help="Optional output directory. Defaults to a new /tmp temp directory.",
    )
    return parser


def _selected_cases(requested_names: list[str] | None) -> list[CaseSpec]:
    return _select_cases(requested_names, CASES)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    resolved_model, resolved_reasoning_effort = resolve_model_and_reasoning_settings(
        provider=str(args.provider),
        model=str(args.model or ""),
        reasoning_effort=str(args.reasoning_effort or ""),
        catalog_cwd=CLI_ROOT,
        interaction_profile=str(args.agenthub_interaction_profile or ""),
    )
    selected_cases = _selected_cases(args.cases)
    if not selected_cases:
        parser.error("no matching cases selected")

    out_root = (
        Path(args.out_root).resolve()
        if str(args.out_root or "").strip()
        else Path(tempfile.mkdtemp(prefix="agenthub_openai_codex_ab_", dir="/tmp"))
    )
    out_root.mkdir(parents=True, exist_ok=True)

    case_results = run_case_attempts(
        selected_cases=selected_cases,
        out_root=out_root,
        provider=str(args.provider),
        model=resolved_model,
        reasoning_effort=resolved_reasoning_effort,
        openai_base_url=str(args.openai_base_url),
        interaction_profile=str(args.agenthub_interaction_profile),
        codex_provider_id=str(args.codex_provider_id),
        retry_attempts=int(args.retry_attempts),
        timeout_seconds=int(args.timeout_seconds),
    )
    report = build_report(
        out_root=out_root,
        provider=str(args.provider),
        model=resolved_model,
        reasoning_effort=resolved_reasoning_effort,
        openai_base_url=str(args.openai_base_url),
        agenthub_interaction_profile=str(args.agenthub_interaction_profile),
        codex_provider_id=str(args.codex_provider_id),
        retry_attempts=int(args.retry_attempts),
        timeout_seconds=int(args.timeout_seconds),
        case_results=case_results,
    )
    report_path, report_md_path = write_report_files(report=report, out_root=out_root)

    print(
        json.dumps(
            {
                "out_root": str(out_root),
                "report_json": str(report_path),
                "report_md": str(report_md_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
