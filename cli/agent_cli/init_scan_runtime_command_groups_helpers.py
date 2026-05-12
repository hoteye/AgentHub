from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def build_command_groups_impl(
    project_root: Path,
    *,
    package_json: dict[str, Any],
    pyproject: dict[str, Any],
    cargo_toml: dict[str, Any],
    go_mod_text: str,
    make_targets: list[str],
    package_managers: list[str],
    primary_node_manager_fn: Callable[[list[str]], str],
    script_commands_fn: Callable[[str, dict[str, Any], tuple[str, ...]], list[str]],
    python_dependencies_fn: Callable[[dict[str, Any], Path], set[str]],
    python_runner_prefix_fn: Callable[[list[str]], str],
    python_command_fn: Callable[[str, str], str],
    unique_fn: Callable[[list[str]], list[str]],
) -> dict[str, list[str]]:
    build_commands: list[str] = []
    test_commands: list[str] = []
    lint_commands: list[str] = []
    format_commands: list[str] = []

    node_manager = primary_node_manager_fn(package_managers)
    scripts = package_json.get("scripts") if isinstance(package_json.get("scripts"), dict) else {}
    if isinstance(scripts, dict) and node_manager:
        build_commands.extend(script_commands_fn(node_manager, scripts, ("build", "compile")))
        test_commands.extend(script_commands_fn(node_manager, scripts, ("test", "test:unit")))
        lint_commands.extend(script_commands_fn(node_manager, scripts, ("lint", "check")))
        format_commands.extend(script_commands_fn(node_manager, scripts, ("format", "fmt")))

    python_dependencies = python_dependencies_fn(pyproject, project_root)
    if python_dependencies or pyproject or (project_root / "requirements.txt").is_file():
        runner = python_runner_prefix_fn(package_managers)
        if "pytest" in python_dependencies or (project_root / "tests").is_dir():
            test_commands.append(python_command_fn(runner, "pytest"))
        if "ruff" in python_dependencies:
            lint_commands.append(python_command_fn(runner, "ruff check ."))
            format_commands.append(python_command_fn(runner, "ruff format ."))
        if "black" in python_dependencies:
            format_commands.append(python_command_fn(runner, "black ."))
        if "mypy" in python_dependencies:
            lint_commands.append(python_command_fn(runner, "mypy ."))
        if pyproject.get("build-system"):
            build_commands.append("python -m build")

    if cargo_toml:
        build_commands.append("cargo build")
        test_commands.append("cargo test")
        lint_commands.append("cargo clippy --all-targets --all-features")
        format_commands.append("cargo fmt --check")

    if go_mod_text:
        build_commands.append("go build ./...")
        test_commands.append("go test ./...")
        format_commands.append("gofmt -w .")

    if make_targets:
        if "build" in make_targets:
            build_commands.insert(0, "make build")
        if "test" in make_targets:
            test_commands.insert(0, "make test")
        if "lint" in make_targets:
            lint_commands.insert(0, "make lint")
        if "format" in make_targets or "fmt" in make_targets:
            format_commands.insert(0, "make format" if "format" in make_targets else "make fmt")

    return {
        "build": unique_fn(build_commands),
        "test": unique_fn(test_commands),
        "lint": unique_fn(lint_commands),
        "format": unique_fn(format_commands),
    }
