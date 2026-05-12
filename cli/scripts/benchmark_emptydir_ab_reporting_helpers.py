from __future__ import annotations

import json
import shlex
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from cli.scripts.benchmark_emptydir_ab_layer_helpers import (
        _build_request_raw_layer,
        _build_tool_call_chain_layer,
        _build_tool_schema_layer,
        _build_workspace_side_effects_layer,
    )
    from cli.scripts.benchmark_emptydir_ab_model_io_helpers import (
        CommandResult,
        RunSummary,
        _agenthub_detail,
        _auth_snapshot,
        _codex_detail,
        _env_snapshot,
        _prompt_preview,
        _text_file_snapshot,
        _workspace_file_inventory,
        _write_json,
        _write_text,
    )
    from cli.scripts.benchmark_emptydir_ab_runtime_helpers import (
        _parse_agenthub_output,
        _parse_codex_output,
        _print_summary,
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
        RunSummary,
        _agenthub_detail,
        _auth_snapshot,
        _codex_detail,
        _env_snapshot,
        _prompt_preview,
        _text_file_snapshot,
        _workspace_file_inventory,
        _write_json,
        _write_text,
    )
    from benchmark_emptydir_ab_runtime_helpers import (  # type: ignore[no-redef]
        _parse_agenthub_output,
        _parse_codex_output,
        _print_summary,
    )


def _build_log_manifest(harness_root: Path) -> dict[str, str]:
    return {
        "agenthub_stdout": str(harness_root / "agenthub.stdout.json"),
        "agenthub_stderr": str(harness_root / "agenthub.stderr.log"),
        "codex_stdout": str(harness_root / "codex.stdout.jsonl"),
        "codex_stderr": str(harness_root / "codex.stderr.log"),
        "agenthub_debug_log_dir": str(harness_root / "agenthub_logs"),
        "codex_debug_log_dir": str(harness_root / "codex_logs"),
        "agenthub_llm_io": str(harness_root / "agenthub_logs" / "llm_io.jsonl"),
        "codex_llm_io": str(harness_root / "codex_logs" / "llm_io.jsonl"),
        "agenthub_tool_trace": str(harness_root / "agenthub_logs" / "tool_trace.jsonl"),
        "agenthub_turn_actions": str(harness_root / "agenthub_logs" / "turn_actions.jsonl"),
        "codex_turn_actions": str(harness_root / "codex_logs" / "turn_actions.jsonl"),
        "agenthub_detail": str(harness_root / "agenthub.detail.json"),
        "codex_detail": str(harness_root / "codex.detail.json"),
        "agenthub_files": str(harness_root / "agenthub.workspace.files.json"),
        "codex_files": str(harness_root / "codex.workspace.files.json"),
        "layer_request_raw": str(harness_root / "layer.request_raw.json"),
        "layer_tool_schema": str(harness_root / "layer.tool_schema.json"),
        "layer_tool_call_chain": str(harness_root / "layer.tool_call_chain.json"),
        "layer_workspace_side_effects": str(harness_root / "layer.workspace_side_effects.json"),
        "agenthub_invocation": str(harness_root / "agenthub.invocation.json"),
        "codex_invocation": str(harness_root / "codex.invocation.json"),
        "agenthub_config_snapshot": str(harness_root / "agenthub.config.snapshot.json"),
        "codex_config_snapshot": str(harness_root / "codex.config.snapshot.json"),
        "agenthub_auth_snapshot": str(harness_root / "agenthub.auth.snapshot.json"),
        "codex_auth_snapshot": str(harness_root / "codex.auth.snapshot.json"),
        "commands": str(harness_root / "commands.txt"),
    }


def _write_commands_file(
    *,
    path: Path,
    summary_path: Path,
    args: Any,
    agenthub_run: CommandResult,
    codex_run: CommandResult,
    agenthub_config_path: Path,
    agenthub_auth_path: Path,
    codex_provider_id: str,
    codex_bin: Path,
    codex_config_path: Path,
    codex_auth_path: Path,
) -> None:
    _write_text(
        path,
        "\n".join(
            [
                "agenthub:",
                shlex.join(agenthub_run.command),
                "",
                "codex:",
                shlex.join(codex_run.command),
                "",
                f"agenthub_config_mode={args.agenthub_config_mode}",
                f"agenthub_config_path={agenthub_config_path}",
                f"agenthub_auth_path={agenthub_auth_path}",
                f"agenthub_interaction_profile={args.agenthub_interaction_profile or '-'}",
                "",
                f"codex_config_mode={args.codex_config_mode}",
                f"codex_provider_id={codex_provider_id}",
                f"codex_bin={codex_bin}",
                f"codex_config_path={codex_config_path}",
                f"codex_auth_path={codex_auth_path}",
                "",
                f"summary={summary_path}",
            ]
        )
        + "\n",
    )


def _write_run_report(
    *,
    args: Any,
    harness_root: Path,
    prompt_path: Path,
    prompt: str,
    resolved_model: str,
    resolved_reasoning_effort: str,
    codex_provider_id: str,
    codex_bin: Path,
    codex_home: Path,
    agenthub_workspace: Path,
    codex_workspace: Path,
    agenthub_config_path: Path,
    agenthub_auth_path: Path,
    codex_config_path: Path,
    codex_auth_path: Path,
    agenthub_env: dict[str, str],
    codex_env: dict[str, str],
    agenthub_run: CommandResult,
    codex_run: CommandResult,
    agenthub_validation: CommandResult | None,
    codex_validation: CommandResult | None,
) -> tuple[RunSummary, Path]:
    agenthub_assistant_text = _parse_agenthub_output(Path(agenthub_run.stdout_path))
    codex_assistant_text, codex_thread_id, codex_errors = _parse_codex_output(Path(codex_run.stdout_path))
    agenthub_detail = _agenthub_detail(Path(agenthub_run.stdout_path))
    codex_detail = _codex_detail(Path(codex_run.stdout_path))
    agenthub_inventory = _workspace_file_inventory(agenthub_workspace)
    codex_inventory = _workspace_file_inventory(codex_workspace)
    request_raw_layer = _build_request_raw_layer(
        agenthub_llm_io_path=harness_root / "agenthub_logs" / "llm_io.jsonl",
        codex_llm_io_path=harness_root / "codex_logs" / "llm_io.jsonl",
    )
    log_manifest = _build_log_manifest(harness_root)
    _write_json(
        Path(log_manifest["agenthub_invocation"]),
        {
            "name": "agenthub",
            "command": agenthub_run.command,
            "cwd": agenthub_run.cwd,
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
            "command": codex_run.command,
            "cwd": codex_run.cwd,
            "env": _env_snapshot(codex_env),
            "config_mode": args.codex_config_mode,
            "provider_id": codex_provider_id,
            "config_path": str(codex_config_path),
            "auth_path": str(codex_auth_path),
            "codex_bin": str(codex_bin),
        },
    )
    _write_json(Path(log_manifest["agenthub_detail"]), agenthub_detail)
    _write_json(Path(log_manifest["codex_detail"]), codex_detail)
    _write_json(Path(log_manifest["agenthub_files"]), agenthub_inventory)
    _write_json(Path(log_manifest["codex_files"]), codex_inventory)
    tool_schema_layer = _build_tool_schema_layer(request_raw_layer)
    tool_call_chain_layer = _build_tool_call_chain_layer(
        agenthub_detail_path=Path(log_manifest["agenthub_detail"]),
        codex_detail_path=Path(log_manifest["codex_detail"]),
        codex_turn_actions_path=Path(log_manifest["codex_turn_actions"]),
    )
    workspace_side_effects_layer = _build_workspace_side_effects_layer(
        agenthub_workspace=agenthub_workspace,
        codex_workspace=codex_workspace,
        agenthub_run=agenthub_run,
        codex_run=codex_run,
        agenthub_validation=agenthub_validation,
        codex_validation=codex_validation,
        agenthub_assistant_text=agenthub_assistant_text,
        codex_assistant_text=codex_assistant_text,
    )
    layer_summary = {
        "request_raw": dict(request_raw_layer.get("summary") or {}),
        "tool_schema": dict(tool_schema_layer.get("summary") or {}),
        "tool_call_chain": dict(tool_call_chain_layer.get("summary") or {}),
        "workspace_side_effects": dict(workspace_side_effects_layer.get("summary") or {}),
    }
    _write_json(Path(log_manifest["layer_request_raw"]), request_raw_layer)
    _write_json(Path(log_manifest["layer_tool_schema"]), tool_schema_layer)
    _write_json(Path(log_manifest["layer_tool_call_chain"]), tool_call_chain_layer)
    _write_json(Path(log_manifest["layer_workspace_side_effects"]), workspace_side_effects_layer)
    _write_json(Path(log_manifest["agenthub_config_snapshot"]), _text_file_snapshot(agenthub_config_path))
    _write_json(Path(log_manifest["codex_config_snapshot"]), _text_file_snapshot(codex_config_path))
    _write_json(Path(log_manifest["agenthub_auth_snapshot"]), _auth_snapshot(agenthub_auth_path))
    _write_json(Path(log_manifest["codex_auth_snapshot"]), _auth_snapshot(codex_auth_path))
    summary = RunSummary(
        harness_root=str(harness_root),
        prompt_path=str(prompt_path),
        prompt_preview=_prompt_preview(prompt),
        provider=args.provider,
        model=resolved_model,
        reasoning_effort=resolved_reasoning_effort,
        openai_base_url=args.openai_base_url,
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
        codex_bin=str(codex_bin),
        agenthub_run=asdict(agenthub_run),
        codex_run=asdict(codex_run),
        agenthub_validation=asdict(agenthub_validation) if agenthub_validation else None,
        codex_validation=asdict(codex_validation) if codex_validation else None,
        agenthub_assistant_text=agenthub_assistant_text,
        codex_assistant_text=codex_assistant_text,
        codex_thread_id=codex_thread_id,
        codex_errors=codex_errors,
        layer_summary=layer_summary,
        log_manifest=log_manifest,
    )
    summary_path = harness_root / "summary.json"
    _write_text(summary_path, json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n")
    _write_commands_file(
        path=harness_root / "commands.txt",
        summary_path=summary_path,
        args=args,
        agenthub_run=agenthub_run,
        codex_run=codex_run,
        agenthub_config_path=agenthub_config_path,
        agenthub_auth_path=agenthub_auth_path,
        codex_provider_id=codex_provider_id,
        codex_bin=codex_bin,
        codex_config_path=codex_config_path,
        codex_auth_path=codex_auth_path,
    )
    _print_summary(summary)
    print(f"summary_json={summary_path}")
    return summary, summary_path
