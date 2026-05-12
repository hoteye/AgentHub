from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cli.agent_cli.background_tasks.tasks_support_workspace_runtime import (
    prepare_stage_workspace,
    stage_workspace_ignore,
)


@dataclass(slots=True)
class _StorageStub:
    results_dir: Path
    db_path: Path | None


def test_stage_workspace_ignore_only_targets_huey_paths(tmp_path: Path) -> None:
    source_root = tmp_path / "repo"
    huey_root = source_root / "cli/.local/state/huey"
    results_dir = huey_root / "results"
    db_path = huey_root / "agenthub_huey.db"
    results_dir.mkdir(parents=True, exist_ok=True)
    db_path.write_text("sqlite", encoding="utf-8")
    storage = _StorageStub(results_dir=results_dir, db_path=db_path)

    ignore = stage_workspace_ignore(source_root, storage)

    root_ignored = ignore(str(source_root), ["cli", ".venv", ".config"])
    assert "cli" not in root_ignored
    assert root_ignored == set()

    huey_ignored = ignore(str(huey_root), ["results", "agenthub_huey.db", "other.db"])
    assert huey_ignored == {"results", "agenthub_huey.db"}


def test_prepare_stage_workspace_keeps_cli_tree_and_nested_cli_directories(tmp_path: Path) -> None:
    source_root = tmp_path / "repo"
    target_file = source_root / "cli/agent_cli/runtime_core/orchestration_commands.py"
    nested_cli_file = source_root / ".venv/lib/python3.13/site-packages/openai/cli/_api/models.py"
    huey_root = source_root / "cli/.local/state/huey"
    results_dir = huey_root / "results"
    db_path = huey_root / "agenthub_huey.db"

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("print('ok')\n", encoding="utf-8")
    nested_cli_file.parent.mkdir(parents=True, exist_ok=True)
    nested_cli_file.write_text("MODEL = 'stub'\n", encoding="utf-8")
    (results_dir / "stale.json").parent.mkdir(parents=True, exist_ok=True)
    (results_dir / "stale.json").write_text("{}", encoding="utf-8")
    db_path.write_text("sqlite", encoding="utf-8")

    storage = _StorageStub(results_dir=results_dir, db_path=db_path)
    stage_root = prepare_stage_workspace("bg_demo", source_root=source_root, storage=storage)

    assert (stage_root / "cli/agent_cli/runtime_core/orchestration_commands.py").exists()
    assert (stage_root / ".venv/lib/python3.13/site-packages/openai/cli/_api/models.py").exists()
    assert not (stage_root / "cli/.local/state/huey/results").exists()
    assert not (stage_root / "cli/.local/state/huey/agenthub_huey.db").exists()
