from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from cli.scripts.run_multiturn_planning_probe_case_helpers import SeedFile, ValidationCommand
    from cli.scripts.script_runtime_helpers import (
        ScriptProviderSelectionOverride,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        normalize_script_validation_command,
        resolve_model_and_reasoning_settings,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from run_multiturn_planning_probe_case_helpers import (  # type: ignore[no-redef]
        SeedFile,
        ValidationCommand,
    )
    from script_runtime_helpers import (  # type: ignore[no-redef]
        ScriptProviderSelectionOverride,
        apply_script_provider_materialization_env,
        ensure_script_import_paths,
        materialize_script_provider_fixture,
        normalize_script_validation_command,
        resolve_model_and_reasoning_settings,
    )

_SCRIPT_PATHS = ensure_script_import_paths(__file__)
CLI_ROOT = _SCRIPT_PATHS.cli_root
AGENTHUB_MAIN = CLI_ROOT / "agent_cli" / "__main__.py"

__all__ = [
    "AGENTHUB_MAIN",
    "ScriptProviderSelectionOverride",
    "_inventory",
    "_now_iso",
    "_prepare_agenthub_home",
    "_run_validation",
    "_seed_workspace",
    "_write_json",
    "_write_text",
    "apply_script_provider_materialization_env",
    "resolve_agenthub_selection",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def resolve_agenthub_selection(
    *,
    provider: str,
    model: str,
    reasoning_effort: str,
    interaction_profile: str,
) -> ScriptProviderSelectionOverride:
    resolved_model, resolved_effort = resolve_model_and_reasoning_settings(
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        catalog_cwd=CLI_ROOT,
        interaction_profile=interaction_profile,
        planner_kind="openai_responses" if str(provider).strip() == "openai" else "",
        wire_api="responses" if str(provider).strip() == "openai" else "",
    )
    return ScriptProviderSelectionOverride(
        provider_name=str(provider or "").strip(),
        model=resolved_model,
        reasoning_effort=resolved_effort,
    )


def _prepare_agenthub_home(
    target_home: Path,
    *,
    selection_override: ScriptProviderSelectionOverride | None = None,
) -> Any:
    return materialize_script_provider_fixture(
        cwd=CLI_ROOT,
        target_root=target_home,
        selection_override=selection_override,
    )


def _seed_workspace(workspace: Path, seed_files: tuple[SeedFile, ...]) -> None:
    for seed in list(seed_files or ()):
        target = workspace / seed.path
        _write_text(target, seed.content)


def _inventory(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not root.exists():
        return items
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        items.append({"path": str(path.relative_to(root)), "size": path.stat().st_size})
    return items


def _run_validation(
    *,
    workspace: Path,
    out_dir: Path,
    commands: tuple[ValidationCommand, ...],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in list(commands or ()):
        original_command = [str(part) for part in list(item.command or ())]
        effective_command = normalize_script_validation_command(item.command)
        started = time.time()
        proc = subprocess.run(
            effective_command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        elapsed = round(time.time() - started, 3)
        stdout_path = out_dir / f"{item.name}.stdout.txt"
        stderr_path = out_dir / f"{item.name}.stderr.txt"
        _write_text(stdout_path, proc.stdout)
        _write_text(stderr_path, proc.stderr)
        results.append(
            {
                "name": item.name,
                "command": original_command,
                "effective_command": effective_command,
                "returncode": int(proc.returncode),
                "elapsed_s": elapsed,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
        )
    return results
