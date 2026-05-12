from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "import_boundary_guard.py"
    spec = importlib.util.spec_from_file_location("import_boundary_guard", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changed_python_files_selects_only_guarded_python_paths(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "diff_base", lambda base_ref: "base_sha")
    monkeypatch.setattr(
        module,
        "run_git",
        lambda args: "\n".join(
            [
                "cli/agent_cli/runtime_core/a.py",
                "cli/agent_cli/runtime_core/a.py",
                "cli/agent_cli/runtime_core/note.md",
                "cli/agent_cli/ui/panel.py",
                "cli/scripts/import_boundary_guard.py",
                "docs/readme.py",
            ]
        ),
    )

    changed = module.changed_python_files(root=Path("cli/agent_cli"), base_ref="main")

    assert changed == [
        Path("cli/agent_cli/runtime_core/a.py"),
        Path("cli/agent_cli/ui/panel.py"),
    ]


def test_scan_file_detects_forbidden_imports_for_runtime_core(tmp_path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.chdir(tmp_path)
    target = Path("cli/agent_cli/runtime_core/guard_demo.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "import cli.agent_cli.ui.widgets\n"
        "from cli.agent_cli.ui.status import render\n",
        encoding="utf-8",
    )

    violations = module.scan_file(target)

    assert violations == [
        (1, "cli.agent_cli.ui.widgets"),
        (2, "cli.agent_cli.ui.status"),
    ]


def test_relative_import_resolution_is_enforced_for_forbidden_targets(tmp_path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.chdir(tmp_path)
    target = Path("cli/agent_cli/runtime_core/relative_demo.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from ..ui import render\n"
        "from ..runtime_services import helper\n",
        encoding="utf-8",
    )

    source = target.read_text(encoding="utf-8")
    tree = ast.parse(source)
    from_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    resolved = [module.resolve_import(module.module_name(target), node) for node in from_nodes]
    assert resolved == ["cli.agent_cli.ui", "cli.agent_cli.runtime_services"]

    violations = module.scan_file(target)
    assert violations == [(1, "cli.agent_cli.ui")]
