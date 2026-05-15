from __future__ import annotations

import argparse
from dataclasses import dataclass

try:
    from cli.scripts.benchmark_claude_agenthub_emptydir_task_fixtures import build_default_tasks
    from cli.scripts.script_runtime_helpers import (
        ensure_script_import_paths,
        normalize_optional_provider_home_override,
        resolve_effective_script_provider_home_dir,
        resolve_script_provider_home_dir,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_claude_agenthub_emptydir_task_fixtures import (
        build_default_tasks,  # type: ignore[no-redef]
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        ensure_script_import_paths,
        normalize_optional_provider_home_override,
        resolve_effective_script_provider_home_dir,
        resolve_script_provider_home_dir,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)

CLI_ROOT = _SCRIPT_PATHS.cli_root
REPO_ROOT = CLI_ROOT.parent
DEFAULT_AGENTHUB_MAIN = CLI_ROOT / "agent_cli" / "__main__.py"
DEFAULT_AGENTHUB_PROVIDER_HOME = resolve_script_provider_home_dir(cwd=CLI_ROOT)
DEFAULT_AGENTHUB_PROVIDER = "anthropic"
DEFAULT_AGENTHUB_MODEL = "claude-sonnet-4-6"
DEFAULT_CLAUDE_BIN = "claude"
DEFAULT_CLAUDE_MODEL = "sonnet"
DEFAULT_CLAUDE_PERMISSION_MODE = "bypassPermissions"
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_VALIDATION_TIMEOUT_SECONDS = 180
DEFAULT_PREFLIGHT_PROMPT = "只回复：OK。不要使用任何工具。"
EXPECTED_SHORT_REPLY = "OK"
EXPECTED_SONNET_MODEL_KEY = "claude-sonnet-4-6"
EXPECTED_AGENTHUB_PROVIDER_NAME = "anthropic"


def _agenthub_provider_home_report_fields(provider_home: str) -> dict[str, str]:
    normalized_provider_home = normalize_optional_provider_home_override(provider_home)
    return {
        "agenthub_provider_home": str(
            resolve_effective_script_provider_home_dir(
                cwd=CLI_ROOT,
                provider_home=normalized_provider_home,
            )
        ),
        "agenthub_provider_home_override": normalized_provider_home,
        "agenthub_provider_home_source": (
            "explicit_override" if normalized_provider_home else "runtime_default"
        ),
    }


@dataclass(frozen=True)
class ValidationSpec:
    name: str
    command: str


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    title: str
    prompt: str
    validations: tuple[ValidationSpec, ...]
    expected_files: tuple[str, ...]


def _default_tasks() -> list[BenchmarkTask]:
    return build_default_tasks(benchmark_task_cls=BenchmarkTask, validation_spec_cls=ValidationSpec)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/benchmark_claude_agenthub_emptydir.py",
        description="Compare Claude Code and AgentHub on fixed empty-directory tasks.",
    )
    parser.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help="Task id to run. Repeat to select a subset. Defaults to all built-in tasks.",
    )
    parser.add_argument(
        "--list-tasks", action="store_true", help="List built-in task ids and exit."
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output directory. Defaults to a temp directory under /tmp.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-system task timeout in seconds. Defaults to {DEFAULT_TIMEOUT_SECONDS}.",
    )
    parser.add_argument(
        "--validation-timeout-seconds",
        type=int,
        default=DEFAULT_VALIDATION_TIMEOUT_SECONDS,
        help=f"Per-validation timeout in seconds. Defaults to {DEFAULT_VALIDATION_TIMEOUT_SECONDS}.",
    )
    parser.add_argument(
        "--task-workers",
        type=int,
        default=1,
        help="How many tasks to run concurrently. Defaults to 1.",
    )
    parser.add_argument(
        "--claude-bin",
        default=DEFAULT_CLAUDE_BIN,
        help=f"Claude Code CLI binary. Defaults to {DEFAULT_CLAUDE_BIN!r}.",
    )
    parser.add_argument(
        "--claude-model",
        default=DEFAULT_CLAUDE_MODEL,
        help=f"Claude Code model name. Defaults to {DEFAULT_CLAUDE_MODEL!r}.",
    )
    parser.add_argument(
        "--claude-permission-mode",
        default=DEFAULT_CLAUDE_PERMISSION_MODE,
        help=f"Claude Code permission mode. Defaults to {DEFAULT_CLAUDE_PERMISSION_MODE!r}.",
    )
    parser.add_argument(
        "--agenthub-main",
        default=str(DEFAULT_AGENTHUB_MAIN),
        help=f"AgentHub package entry path. Defaults to {DEFAULT_AGENTHUB_MAIN}.",
    )
    parser.add_argument(
        "--agenthub-provider-home",
        default="",
        help=(
            "Optional provider runtime home override passed via AGENTHUB_PROVIDER_HOME. "
            "Defaults to runtime-managed provider home resolution."
        ),
    )
    parser.add_argument(
        "--agenthub-provider",
        default=DEFAULT_AGENTHUB_PROVIDER,
        help=f"AgentHub provider. Defaults to {DEFAULT_AGENTHUB_PROVIDER!r}.",
    )
    parser.add_argument(
        "--agenthub-model",
        default=DEFAULT_AGENTHUB_MODEL,
        help=f"AgentHub provider model. Defaults to {DEFAULT_AGENTHUB_MODEL!r}.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write prompts and planned commands without executing either system.",
    )
    return parser


def _resolve_tasks(requested_ids: list[str] | None) -> list[BenchmarkTask]:
    all_tasks = _default_tasks()
    if not requested_ids:
        return list(all_tasks)
    by_id = {task.task_id: task for task in all_tasks}
    selected: list[BenchmarkTask] = []
    for raw in requested_ids:
        task_id = str(raw or "").strip()
        if task_id not in by_id:
            raise ValueError(f"unknown task id: {task_id}")
        if any(item.task_id == task_id for item in selected):
            continue
        selected.append(by_id[task_id])
    return selected


def _print_task_list(tasks: list[BenchmarkTask]) -> None:
    for task in tasks:
        print(f"{task.task_id}: {task.title}")
