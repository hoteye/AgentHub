from __future__ import annotations

import importlib.util
from pathlib import Path

RUNTIME_DATA_EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "_corpus_cache",
    "artifacts",
    "build",
    "chroma_db",
    "dist",
    "node_modules",
    "venv",
}
RUNTIME_DATA_EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo", ".sqlite3"}
RUNTIME_DATA_EXCLUDED_FILE_NAMES = {".DS_Store", "source_bundle.json"}
RUNTIME_DATA_EXCLUDED_RELATIVE_PATHS = {
    Path("psbc_policy"),
    Path("plugins/psbc_policy"),
}
PYINSTALLER_OPTIONAL_HEAVY_EXCLUDES = (
    "matplotlib",
    "numpy",
    "pandas",
    "PIL",
    "PySide6",
    "scipy",
)
CANONICAL_CLI_DYNAMIC_HIDDEN_IMPORTS = (
    "cli.agent_cli.headless",
    "cli.agent_cli.headless_entry_runtime",
    "cli.agent_cli.headless_event_runtime",
    "cli.agent_cli.headless_helpers",
    "cli.agent_cli.headless_jsonl_runtime",
    "cli.agent_cli.headless_runtime",
    "cli.agent_cli.headless_shell_projection_runtime",
    "cli.agent_cli.headless_snapshot_runtime",
    "cli.agent_cli.headless_stream_normalization_helpers_runtime",
    "cli.agent_cli.headless_stream_projection_helpers_runtime",
    "cli.agent_cli.headless_stream_pure_helpers_runtime",
    "cli.agent_cli.headless_stream_runtime",
    "cli.agent_cli.headless_stream_runtime_helpers",
    "cli.agent_cli.headless_wiring_runtime",
    "cli.agent_cli.runtime_codex_headless_contract_runtime",
)


def has_module_spec(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def maybe_add_collect(args: list[str], module_name: str) -> None:
    if has_module_spec(module_name):
        args.extend(["--collect-submodules", module_name])


def add_collect(args: list[str], module_name: str) -> None:
    args.extend(["--collect-submodules", module_name])


def maybe_add_hidden_import(args: list[str], module_name: str) -> None:
    if has_module_spec(module_name):
        args.extend(["--hidden-import", module_name])


def add_hidden_import(args: list[str], module_name: str) -> None:
    args.extend(["--hidden-import", module_name])


def _runtime_data_file_allowed(path: Path) -> bool:
    if any(
        path == excluded or excluded in path.parents
        for excluded in RUNTIME_DATA_EXCLUDED_RELATIVE_PATHS
    ):
        return False
    if any(part in RUNTIME_DATA_EXCLUDED_DIR_NAMES for part in path.parts):
        return False
    if path.name in RUNTIME_DATA_EXCLUDED_FILE_NAMES:
        return False
    if path.suffix in RUNTIME_DATA_EXCLUDED_FILE_SUFFIXES:
        return False
    return True


def _filtered_runtime_file_mappings(source: Path, dest: str) -> list[tuple[Path, str]]:
    mappings: list[tuple[Path, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if not _runtime_data_file_allowed(relative):
            continue
        mappings.append((path, str(Path(dest) / relative.parent)))
    return mappings


def canonical_cli_hidden_imports(*, cli: Path) -> list[str]:
    source_root = cli / "agent_cli"
    module_names: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(source_root).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__main__":
            continue
        if parts[-1] == "__init__":
            suffix = ".".join(parts[:-1])
        else:
            suffix = ".".join(parts)
        module_names.append("cli.agent_cli" if not suffix else f"cli.agent_cli.{suffix}")
    return module_names


def runtime_data_mappings(*, root: Path, cli: Path) -> list[tuple[Path, str]]:
    mappings: list[tuple[Path, str]] = [
        (root / "config", "config"),
        (root / "LICENSE", "."),
        (cli / "agent_cli" / "prompts", "cli/agent_cli/prompts"),
        (
            cli / "agent_cli" / "providers" / "interaction_profiles",
            "cli/agent_cli/providers/interaction_profiles",
        ),
    ]
    for relative in ("plugins", "shared", "tools", "document_tools", "workers"):
        source = root / relative
        if source.exists():
            mappings.extend(_filtered_runtime_file_mappings(source, relative))
    return [(source, dest) for source, dest in mappings if source.exists()]
