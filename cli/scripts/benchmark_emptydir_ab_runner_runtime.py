from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

try:
    from cli.scripts.benchmark_emptydir_ab_model_io_helpers import CommandResult
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_emptydir_ab_model_io_helpers import CommandResult  # type: ignore[no-redef]


def _build_agenthub_command(
    *,
    prompt: str,
    workspace: Path,
    env: dict[str, str],
    timeout_seconds: int,
    out_dir: Path,
    main_path: Path,
    network_access: str,
    run_command: Callable[..., CommandResult],
    repo_root: Path,
) -> CommandResult:
    command = [
        sys.executable,
        str(main_path),
        "--headless",
        "--json",
        "--approval-policy",
        "never",
        "--sandbox-mode",
        "workspace-write",
        "--network-access",
        network_access,
        "--prompt",
        prompt,
    ]
    return run_command(
        name="agenthub",
        command=command,
        cwd=repo_root,
        env=env,
        stdout_path=out_dir / "agenthub.stdout.json",
        stderr_path=out_dir / "agenthub.stderr.log",
        timeout_seconds=timeout_seconds,
    )


def _build_codex_command(
    *,
    prompt: str,
    workspace: Path,
    env: dict[str, str],
    timeout_seconds: int,
    out_dir: Path,
    codex_bin: Path,
    run_command: Callable[..., CommandResult],
    codex_ref_root: Path,
) -> CommandResult:
    command = [
        str(codex_bin),
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "-C",
        str(workspace),
        "-m",
        env["BENCH_MODEL"],
    ]
    provider_override = str(env.get("CODEX_PROVIDER_OVERRIDE") or "").strip()
    if provider_override:
        command.extend(["-c", f'model_provider="{provider_override}"'])
    reasoning_effort = str(env.get("BENCH_REASONING_EFFORT") or "").strip()
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append(prompt)
    return run_command(
        name="codex",
        command=command,
        cwd=codex_ref_root,
        env=env,
        stdout_path=out_dir / "codex.stdout.jsonl",
        stderr_path=out_dir / "codex.stderr.log",
        timeout_seconds=timeout_seconds,
    )
