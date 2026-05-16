#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

try:
    from cli.scripts.script_runtime_helpers import (
        ensure_script_import_paths,
        resolve_model_and_reasoning_settings,
        resolve_script_provider_source_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (
        ensure_script_import_paths,
        resolve_model_and_reasoning_settings,
        resolve_script_provider_source_paths,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
PROJECT_ROOT = _SCRIPT_PATHS.repo_root

REPO_ROOT = _SCRIPT_PATHS.cli_root
DEFAULT_AGENTHUB_MAIN = REPO_ROOT / "agent_cli" / "__main__.py"
DEFAULT_CODEX_REF_ROOT = Path("/home/lyc/project/AgentHubRef/codex_ref")
DEFAULT_CODEX_BIN = DEFAULT_CODEX_REF_ROOT / "codex-rs" / "target" / "debug" / "codex"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

try:
    from cli.scripts.benchmark_emptydir_ab_layer_helpers import (
        _build_request_raw_layer,
        _build_tool_call_chain_layer,
        _build_tool_schema_layer,
        _build_workspace_side_effects_layer,
    )
    from cli.scripts.benchmark_emptydir_ab_model_io_helpers import (
        CommandResult,
        _load_api_key,
        _read_prompt,
    )
    from cli.scripts.benchmark_emptydir_ab_reporting_helpers import (
        _write_run_report,
    )
    from cli.scripts.benchmark_emptydir_ab_runner_runtime import (
        _build_agenthub_command as _build_agenthub_command_impl,
    )
    from cli.scripts.benchmark_emptydir_ab_runner_runtime import (
        _build_codex_command as _build_codex_command_impl,
    )
    from cli.scripts.benchmark_emptydir_ab_runtime_helpers import (
        _build_agenthub_env,
        _build_agenthub_home,
        _build_agenthub_project_local_config,
        _build_codex_home,
        _default_codex_provider_id,
    )
    from cli.scripts.benchmark_emptydir_ab_runtime_helpers import (
        _run_command as _runtime_run_command,
    )
    from cli.scripts.benchmark_emptydir_ab_runtime_helpers import (
        _run_validation as _runtime_run_validation,
    )
    from cli.scripts.benchmark_emptydir_ab_runtime_helpers import (
        parse_args as _runtime_parse_args,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from benchmark_emptydir_ab_layer_helpers import (  # type: ignore[no-redef]
        _build_request_raw_layer,
        _build_tool_call_chain_layer,
        _build_tool_schema_layer,
        _build_workspace_side_effects_layer,
    )
    from benchmark_emptydir_ab_model_io_helpers import (  # type: ignore[no-redef]
        CommandResult,
        _load_api_key,
        _read_prompt,
    )
    from benchmark_emptydir_ab_reporting_helpers import (  # type: ignore[no-redef]
        _write_run_report,
    )
    from benchmark_emptydir_ab_runner_runtime import (  # type: ignore[no-redef]
        _build_agenthub_command as _build_agenthub_command_impl,
    )
    from benchmark_emptydir_ab_runner_runtime import (
        _build_codex_command as _build_codex_command_impl,
    )
    from benchmark_emptydir_ab_runtime_helpers import (  # type: ignore[no-redef]
        _build_agenthub_env,
        _build_agenthub_home,
        _build_agenthub_project_local_config,
        _build_codex_home,
        _default_codex_provider_id,
    )
    from benchmark_emptydir_ab_runtime_helpers import (
        _run_command as _runtime_run_command,
    )
    from benchmark_emptydir_ab_runtime_helpers import (
        _run_validation as _runtime_run_validation,
    )
    from benchmark_emptydir_ab_runtime_helpers import (
        parse_args as _runtime_parse_args,
    )

__all__ = [
    "CommandResult",
    "REPO_ROOT",
    "_agenthub_command",
    "_build_agenthub_env",
    "_build_agenthub_home",
    "_build_request_raw_layer",
    "_build_tool_call_chain_layer",
    "_build_tool_schema_layer",
    "_build_workspace_side_effects_layer",
    "_codex_command",
    "_default_codex_provider_id",
    "main",
    "parse_args",
]


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> CommandResult:
    return _runtime_run_command(
        name=name,
        command=command,
        cwd=cwd,
        env=env,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_seconds=timeout_seconds,
    )


def _run_validation(
    *,
    name: str,
    command_text: str,
    cwd: Path,
    env: dict[str, str],
    out_dir: Path,
    timeout_seconds: int,
) -> CommandResult:
    return _runtime_run_validation(
        name=name,
        command_text=command_text,
        cwd=cwd,
        env=env,
        out_dir=out_dir,
        timeout_seconds=timeout_seconds,
    )


def _agenthub_command(
    *,
    prompt: str,
    workspace: Path,
    env: dict[str, str],
    timeout_seconds: int,
    out_dir: Path,
    main_path: Path,
    network_access: str,
) -> CommandResult:
    return _build_agenthub_command_impl(
        prompt=prompt,
        workspace=workspace,
        env=env,
        timeout_seconds=timeout_seconds,
        out_dir=out_dir,
        main_path=main_path,
        network_access=network_access,
        run_command=_run_command,
        repo_root=REPO_ROOT,
    )


def _codex_command(
    *,
    prompt: str,
    workspace: Path,
    env: dict[str, str],
    timeout_seconds: int,
    out_dir: Path,
    codex_bin: Path,
) -> CommandResult:
    return _build_codex_command_impl(
        prompt=prompt,
        workspace=workspace,
        env=env,
        timeout_seconds=timeout_seconds,
        out_dir=out_dir,
        codex_bin=codex_bin,
        run_command=_run_command,
        codex_ref_root=DEFAULT_CODEX_REF_ROOT,
    )


def parse_args():
    return _runtime_parse_args(
        default_base_url=DEFAULT_BASE_URL,
        default_codex_bin=DEFAULT_CODEX_BIN,
        default_agenthub_main=DEFAULT_AGENTHUB_MAIN,
    )


def main() -> int:
    args = parse_args()
    if args.provider != "openai":
        raise SystemExit("this harness currently supports only --provider openai")
    resolved_model, resolved_reasoning_effort = resolve_model_and_reasoning_settings(
        provider=str(args.provider),
        model=str(args.model or ""),
        reasoning_effort=str(args.reasoning_effort or ""),
        catalog_cwd=REPO_ROOT,
        interaction_profile=str(args.agenthub_interaction_profile or ""),
    )

    prompt_path = Path(args.prompt_file).resolve()
    prompt = _read_prompt(prompt_path)
    source_agenthub_config_path, source_agenthub_auth_path = resolve_script_provider_source_paths(
        cwd=REPO_ROOT,
        auth_json_override=args.auth_json,
    )
    api_key = _load_api_key(source_agenthub_auth_path, args.api_key_name)
    codex_provider_id = str(args.codex_provider_id or "").strip() or _default_codex_provider_id(
        args.openai_base_url
    )
    codex_bin = Path(args.codex_bin).resolve()
    if not codex_bin.exists():
        raise SystemExit(f"missing --codex-bin target: {codex_bin}")

    harness_root = (
        Path(args.out_dir).resolve()
        if args.out_dir
        else Path(tempfile.mkdtemp(prefix="agenthub_emptydir_ab_", dir="/tmp"))
    )
    harness_root.mkdir(parents=True, exist_ok=True)
    agenthub_project_root = harness_root / "agenthub_project"
    codex_project_root = harness_root / "codex_project"
    agenthub_workspace = agenthub_project_root / "workdir"
    codex_workspace = codex_project_root / "workdir"
    agenthub_workspace.mkdir(parents=True, exist_ok=True)
    codex_workspace.mkdir(parents=True, exist_ok=True)
    if args.agenthub_config_mode == "project_local":
        agenthub_config_path, agenthub_auth_path = _build_agenthub_project_local_config(
            project_root=agenthub_project_root,
            api_key=api_key,
            provider=args.provider,
            model=resolved_model,
            reasoning_effort=resolved_reasoning_effort,
            openai_base_url=args.openai_base_url,
            interaction_profile=args.agenthub_interaction_profile,
        )
        agenthub_provider_home = agenthub_config_path.parent
        agenthub_home = harness_root / "agenthub_home"
        _build_agenthub_home(agenthub_home=agenthub_home)
    else:
        agenthub_config_path = source_agenthub_config_path
        agenthub_auth_path = source_agenthub_auth_path
        agenthub_provider_home = source_agenthub_config_path.parent
        agenthub_home = None
    if args.codex_config_mode == "ephemeral":
        codex_home = harness_root / "codex_home"
        _build_codex_home(
            codex_home,
            api_key,
            codex_provider_id,
            resolved_model,
            resolved_reasoning_effort,
            args.openai_base_url,
            codex_workspace,
        )
        codex_config_path = codex_home / "config.toml"
        codex_auth_path = codex_home / "auth.json"
    else:
        codex_home = DEFAULT_CODEX_HOME
        codex_config_path = codex_home / "config.toml"
        codex_auth_path = codex_home / "auth.json"

    common_env = os.environ.copy()
    common_env["OPENAI_API_KEY"] = api_key
    common_env["BENCH_MODEL"] = resolved_model
    if resolved_reasoning_effort:
        common_env["BENCH_REASONING_EFFORT"] = resolved_reasoning_effort
    else:
        common_env.pop("BENCH_REASONING_EFFORT", None)

    agenthub_env = _build_agenthub_env(
        common_env=common_env,
        provider=args.provider,
        model=resolved_model,
        reasoning_effort=resolved_reasoning_effort,
        openai_base_url=args.openai_base_url,
        provider_home=agenthub_provider_home,
        startup_cwd=agenthub_workspace,
        debug_log_dir=harness_root / "agenthub_logs",
        agent_cli_home=agenthub_home,
    )

    codex_env = dict(common_env)
    if args.codex_config_mode == "ephemeral":
        codex_env["CODEX_HOME"] = str(codex_home)
    codex_env["CODEX_DEBUG_LOG_DIR"] = str(harness_root / "codex_logs")

    agenthub_run = _agenthub_command(
        prompt=prompt,
        workspace=agenthub_workspace,
        env=agenthub_env,
        timeout_seconds=args.timeout_seconds,
        out_dir=harness_root,
        main_path=Path(args.agenthub_main).resolve(),
        network_access=args.agenthub_network_access,
    )
    codex_run = _codex_command(
        prompt=prompt,
        workspace=codex_workspace,
        env=codex_env,
        timeout_seconds=args.timeout_seconds,
        out_dir=harness_root,
        codex_bin=codex_bin,
    )

    agenthub_validation: CommandResult | None = None
    codex_validation: CommandResult | None = None
    if args.validate:
        agenthub_validation = _run_validation(
            name="agenthub.validate",
            command_text=args.validate,
            cwd=agenthub_workspace,
            env=agenthub_env,
            out_dir=harness_root,
            timeout_seconds=args.validation_timeout_seconds,
        )
        codex_validation = _run_validation(
            name="codex.validate",
            command_text=args.validate,
            cwd=codex_workspace,
            env=codex_env,
            out_dir=harness_root,
            timeout_seconds=args.validation_timeout_seconds,
        )

    _write_run_report(
        args=args,
        harness_root=harness_root,
        prompt_path=prompt_path,
        prompt=prompt,
        resolved_model=resolved_model,
        resolved_reasoning_effort=resolved_reasoning_effort,
        codex_provider_id=codex_provider_id,
        codex_bin=codex_bin,
        codex_home=codex_home,
        agenthub_workspace=agenthub_workspace,
        codex_workspace=codex_workspace,
        agenthub_config_path=agenthub_config_path,
        agenthub_auth_path=agenthub_auth_path,
        codex_config_path=codex_config_path,
        codex_auth_path=codex_auth_path,
        agenthub_env=agenthub_env,
        codex_env=codex_env,
        agenthub_run=agenthub_run,
        codex_run=codex_run,
        agenthub_validation=agenthub_validation,
        codex_validation=codex_validation,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
