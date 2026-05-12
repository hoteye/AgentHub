#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from cli.scripts.script_runtime_helpers import (
        apply_provider_home_override_env,
        ensure_script_import_paths,
        resolve_script_provider_source_paths,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from script_runtime_helpers import (  # type: ignore[no-redef]
        apply_provider_home_override_env,
        ensure_script_import_paths,
        resolve_script_provider_source_paths,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)

try:
    from cli.scripts.command_execution_wave03_ab_config_helpers import (
        CLI_ROOT,
        DEFAULT_AGENTHUB_MAIN,
        DEFAULT_BASE_URL,
        DEFAULT_CODEX_HOME,
        DEFAULT_CODEX_REF_ROOT,
        ROOT,
        _build_agenthub_env,
        _build_agenthub_project_local_config,
        _build_codex_home,
        _default_codex_provider_id,
        _is_official_openai_base_url,
        _prepare_agenthub_config,
        _prepare_codex_config,
    )
    from cli.scripts.command_execution_wave03_ab_model_helpers import (
        DEFAULT_PROMPT,
        SNAPSHOT_ENV_KEYS,
        AgentHubConfigSelection,
        CommandResult,
        RunSummary,
        _auth_snapshot,
        _env_snapshot,
        _load_api_key,
        _now_iso,
        _prompt_preview,
        _text_file_snapshot,
        _workspace_file_inventory,
        _write_json,
        _write_text,
    )
    from cli.scripts.command_execution_wave03_ab_reporting_helpers import (
        _build_log_manifest,
        _commands_text,
        _summary_markdown,
        _system_payload as _reporting_system_payload,
    )
    from cli.scripts.command_execution_wave03_ab_runtime_helpers import (
        _build_agenthub_command,
        _build_codex_command,
        _parse_agenthub_output,
        _parse_codex_output,
        _run_command,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from command_execution_wave03_ab_config_helpers import (  # type: ignore[no-redef]
        CLI_ROOT,
        DEFAULT_AGENTHUB_MAIN,
        DEFAULT_BASE_URL,
        DEFAULT_CODEX_HOME,
        DEFAULT_CODEX_REF_ROOT,
        ROOT,
        _build_agenthub_env,
        _build_agenthub_project_local_config,
        _build_codex_home,
        _default_codex_provider_id,
        _is_official_openai_base_url,
        _prepare_agenthub_config,
        _prepare_codex_config,
    )
    from command_execution_wave03_ab_model_helpers import (  # type: ignore[no-redef]
        DEFAULT_PROMPT,
        SNAPSHOT_ENV_KEYS,
        AgentHubConfigSelection,
        CommandResult,
        RunSummary,
        _auth_snapshot,
        _env_snapshot,
        _load_api_key,
        _now_iso,
        _prompt_preview,
        _text_file_snapshot,
        _workspace_file_inventory,
        _write_json,
        _write_text,
    )
    from command_execution_wave03_ab_reporting_helpers import (  # type: ignore[no-redef]
        _build_log_manifest,
        _commands_text,
        _summary_markdown,
        _system_payload as _reporting_system_payload,
    )
    from command_execution_wave03_ab_runtime_helpers import (  # type: ignore[no-redef]
        _build_agenthub_command,
        _build_codex_command,
        _parse_agenthub_output,
        _parse_codex_output,
        _run_command,
    )


def _system_payload(
    *,
    system_name: str,
    command: list[str],
    cwd: Path,
    workspace: Path,
    env: dict[str, str],
    out_dir: Path,
    timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    return _reporting_system_payload(
        system_name=system_name,
        command=command,
        cwd=cwd,
        workspace=workspace,
        env=env,
        out_dir=out_dir,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
        run_command=_run_command,
        parse_agenthub_output=_parse_agenthub_output,
        parse_codex_output=_parse_codex_output,
        workspace_file_inventory=_workspace_file_inventory,
    )


def _load_run_api_key(*, auth_json: Path, key_name: str, dry_run: bool) -> str:
    try:
        return _load_api_key(auth_json, key_name)
    except SystemExit:
        if not dry_run:
            raise
        return f"dry-run-{key_name.lower()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python cli/scripts/command_execution_wave03_ab.py",
        description="Run a focused command-execution A/B between AgentHub and Codex.",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--openai-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--api-key-name", default="OPENAI_API_KEY")
    parser.add_argument("--auth-json", default="")
    parser.add_argument("--agenthub-main", default=str(DEFAULT_AGENTHUB_MAIN))
    parser.add_argument("--agenthub-config-mode", choices=("home", "project_local"), default="home")
    parser.add_argument("--agenthub-interaction-profile", default="codex_openai")
    parser.add_argument("--codex-config-mode", choices=("home", "ephemeral"), default="home")
    parser.add_argument("--codex-provider-id", default="")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = (
        Path(args.out_dir).resolve()
        if str(args.out_dir or "").strip()
        else Path(tempfile.mkdtemp(prefix="command_exec_wave03_ab_", dir="/tmp"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    source_agenthub_config_path, source_agenthub_auth_path = resolve_script_provider_source_paths(
        cwd=CLI_ROOT,
        auth_json_override=args.auth_json,
    )
    api_key = _load_run_api_key(
        auth_json=source_agenthub_auth_path,
        key_name=args.api_key_name,
        dry_run=bool(args.dry_run),
    )
    codex_provider_id = str(args.codex_provider_id or "").strip() or _default_codex_provider_id(args.openai_base_url)

    agenthub_project_root = out_dir / "agenthub_project"
    agenthub_workspace = agenthub_project_root / "workdir"
    codex_workspace = out_dir / "codex_workspace"
    agenthub_workspace.mkdir(parents=True, exist_ok=True)
    codex_workspace.mkdir(parents=True, exist_ok=True)

    agenthub_config = _prepare_agenthub_config(
        harness_root=out_dir,
        source_config_path=source_agenthub_config_path,
        source_auth_path=source_agenthub_auth_path,
        api_key=api_key,
        config_mode=args.agenthub_config_mode,
        provider_id=codex_provider_id,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        openai_base_url=args.openai_base_url,
        interaction_profile=args.agenthub_interaction_profile,
    )
    agenthub_config_path = agenthub_config.config_path
    agenthub_auth_path = agenthub_config.auth_path
    codex_config_path, codex_auth_path, codex_home = _prepare_codex_config(
        harness_root=out_dir,
        api_key=api_key,
        config_mode=args.codex_config_mode,
        provider_id=codex_provider_id,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        openai_base_url=args.openai_base_url,
    )

    common_env = os.environ.copy()
    common_env["OPENAI_API_KEY"] = api_key
    common_env["BENCH_MODEL"] = args.model
    common_env["BENCH_REASONING_EFFORT"] = args.reasoning_effort

    agenthub_env = _build_agenthub_env(
        common_env=common_env,
        openai_base_url=args.openai_base_url,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        provider_home=agenthub_config.provider_home,
        startup_cwd=agenthub_workspace,
        agent_cli_home=agenthub_config.agent_cli_home,
    )

    codex_env = dict(common_env)
    if args.codex_config_mode == "ephemeral":
        codex_env["CODEX_HOME"] = str(codex_home)
    if codex_provider_id and codex_provider_id != "openai":
        codex_env["CODEX_PROVIDER_OVERRIDE"] = codex_provider_id

    agenthub_report = _system_payload(
        system_name="agenthub",
        command=_build_agenthub_command(prompt=args.prompt, main_path=Path(args.agenthub_main).resolve()),
        cwd=CLI_ROOT,
        workspace=agenthub_workspace,
        env=agenthub_env,
        out_dir=out_dir,
        timeout_seconds=max(int(args.timeout_seconds), 1),
        dry_run=bool(args.dry_run),
    )
    codex_report = _system_payload(
        system_name="codex",
        command=_build_codex_command(
            prompt=args.prompt,
            workspace=codex_workspace,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
        ),
        cwd=codex_workspace if args.dry_run else DEFAULT_CODEX_REF_ROOT,
        workspace=codex_workspace,
        env=codex_env,
        out_dir=out_dir,
        timeout_seconds=max(int(args.timeout_seconds), 1),
        dry_run=bool(args.dry_run),
    )

    log_manifest = _build_log_manifest(out_dir)
    _write_json(
        Path(log_manifest["agenthub_invocation"]),
        {
            "name": "agenthub",
            "command": agenthub_report["run"]["command"],
            "cwd": agenthub_report["run"]["cwd"],
            "env": _env_snapshot(agenthub_env),
            "config_mode": args.agenthub_config_mode,
            "config_path": str(agenthub_config_path),
            "auth_path": str(agenthub_auth_path),
            "interaction_profile": str(args.agenthub_interaction_profile or ""),
        },
    )
    _write_json(
        Path(log_manifest["codex_invocation"]),
        {
            "name": "codex",
            "command": codex_report["run"]["command"],
            "cwd": codex_report["run"]["cwd"],
            "env": _env_snapshot(codex_env),
            "config_mode": args.codex_config_mode,
            "provider_id": codex_provider_id,
            "config_path": str(codex_config_path),
            "auth_path": str(codex_auth_path),
        },
    )
    _write_json(Path(log_manifest["agenthub_config_snapshot"]), _text_file_snapshot(agenthub_config_path))
    _write_json(Path(log_manifest["codex_config_snapshot"]), _text_file_snapshot(codex_config_path))
    _write_json(Path(log_manifest["agenthub_auth_snapshot"]), _auth_snapshot(agenthub_auth_path))
    _write_json(Path(log_manifest["codex_auth_snapshot"]), _auth_snapshot(codex_auth_path))
    _write_json(Path(log_manifest["agenthub_workspace_files"]), agenthub_report["workspace_files"])
    _write_json(Path(log_manifest["codex_workspace_files"]), codex_report["workspace_files"])

    summary = RunSummary(
        harness_root=str(out_dir),
        prompt_preview=_prompt_preview(args.prompt),
        dry_run=bool(args.dry_run),
        openai_base_url=args.openai_base_url,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        agenthub_config_mode=args.agenthub_config_mode,
        agenthub_config_path=str(agenthub_config_path),
        agenthub_auth_path=str(agenthub_auth_path),
        agenthub_interaction_profile=str(args.agenthub_interaction_profile or ""),
        codex_config_mode=args.codex_config_mode,
        codex_provider_id=codex_provider_id,
        codex_config_path=str(codex_config_path),
        codex_auth_path=str(codex_auth_path),
        agenthub_workspace=str(agenthub_workspace),
        codex_workspace=str(codex_workspace),
        codex_home=str(codex_home),
        agenthub_run=agenthub_report["run"],
        codex_run=codex_report["run"],
        log_manifest=log_manifest,
    )

    report = {
        "schema_version": "command_execution_wave03_ab_v2",
        "started_at": agenthub_report["run"]["started_at"],
        "ended_at": _now_iso(),
        "prompt": args.prompt,
        "prompt_preview": _prompt_preview(args.prompt),
        "dry_run": bool(args.dry_run),
        "out_dir": str(out_dir),
        "openai_base_url": args.openai_base_url,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "agenthub_config_mode": args.agenthub_config_mode,
        "agenthub_interaction_profile": str(args.agenthub_interaction_profile or ""),
        "codex_config_mode": args.codex_config_mode,
        "codex_provider_id": codex_provider_id,
        "systems": {"agenthub": agenthub_report, "codex": codex_report},
        "log_manifest": log_manifest,
    }
    _write_json(Path(log_manifest["report_json"]), report)
    _write_json(Path(log_manifest["summary_json"]), asdict(summary))
    _write_text(Path(log_manifest["summary_md"]), _summary_markdown(report))
    _write_text(
        Path(log_manifest["commands"]),
        _commands_text(
            agenthub_command=agenthub_report["run"]["command"],
            codex_command=codex_report["run"]["command"],
            agenthub_config_mode=args.agenthub_config_mode,
            agenthub_config_path=agenthub_config_path,
            agenthub_auth_path=agenthub_auth_path,
            agenthub_interaction_profile=str(args.agenthub_interaction_profile or ""),
            codex_config_mode=args.codex_config_mode,
            codex_provider_id=codex_provider_id,
            codex_config_path=codex_config_path,
            codex_auth_path=codex_auth_path,
            summary_json=log_manifest["summary_json"],
            report_json=log_manifest["report_json"],
        ),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"harness_root={out_dir}")
        print(f"agenthub_exit={agenthub_report['run']['exit_code']}")
        print(f"codex_exit={codex_report['run']['exit_code']}")
        print(f"summary_json={log_manifest['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
