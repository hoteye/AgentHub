#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

EXCLUDED_DIR_NAMES = {
    ".agent_cli",
    ".agent_cli_legacy",
    ".claude",
    ".codex",
    ".config",
    ".git",
    ".local",
    ".mypy_cache",
    ".pytest_cache",
    ".reference",
    ".ruff_cache",
    ".tmp",
    ".venv",
    ".web_automation_state",
    ".bg_teammate_smoke_repo",
    ".cleanup_backups",
    "__pycache__",
    "_corpus_cache",
    "agenthubref",
    "artifacts",
    "build",
    "chroma_db",
    "dist",
    "docs",
    "internal_policy_docs",
    "logs",
    "mobile",
    "node_modules",
    "taskboard",
    "tmp_listdir_parity_ws",
    "venv",
}
EXCLUDED_FILE_NAMES = {
    ".env",
    ".DS_Store",
    "auth.json",
    "source_bundle.json",
}
EXCLUDED_SUFFIXES = {
    ".key",
    ".pem",
    ".pfx",
    ".p12",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
}
EXCLUDED_RELATIVE_PATHS = {
    Path(".github/workflows/cli-cross-platform.yml"),
    Path(".github/workflows/governance-guards.yml"),
    Path("plugins/psbc_policy"),
    Path("runtime/codex"),
}
PUBLIC_DOC_PATHS = {
    Path("README.md"),
    Path("CHANGELOG.md"),
    Path("CONTRIBUTING.md"),
    Path("SECURITY.md"),
}
PUBLIC_OVERLAY_PATHS = {
    *PUBLIC_DOC_PATHS,
    Path(".github/workflows/test.yml"),
    Path("assets/agenthub-terminal-preview.svg"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a sanitized AgentHub tree into agenthubpublish."
    )
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument(
        "--target", default=str(Path(__file__).resolve().parents[2] / "agenthubpublish")
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def should_keep_markdown(relative: Path) -> bool:
    if relative in PUBLIC_DOC_PATHS:
        return True
    return len(relative.parts) >= 3 and relative.parts[:3] == ("cli", "agent_cli", "prompts")


def is_excluded_relative_path(relative: Path) -> bool:
    return any(
        relative == excluded or excluded in relative.parents for excluded in EXCLUDED_RELATIVE_PATHS
    )


def should_copy(relative: Path, source: Path) -> bool:
    if source.is_symlink():
        return False
    if is_excluded_relative_path(relative):
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in relative.parts):
        return False
    if source.name in EXCLUDED_FILE_NAMES:
        return False
    if source.suffix in EXCLUDED_SUFFIXES:
        return False
    if source.suffix == ".md" and not should_keep_markdown(relative):
        return False
    lower_text = str(relative).lower()
    if "pressget" in lower_text or "rustdesk" in lower_text:
        return False
    return True


def iter_candidate_files(source_root: Path):
    for dirpath, dirnames, filenames in os.walk(source_root, topdown=True, followlinks=False):
        current = Path(dirpath)
        relative_dir = current.relative_to(source_root)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not is_excluded_relative_path(relative_dir / dirname)
            and dirname not in EXCLUDED_DIR_NAMES
            and "pressget" not in str(relative_dir / dirname).lower()
            and "rustdesk" not in str(relative_dir / dirname).lower()
        ]
        for filename in sorted(filenames):
            source = current / filename
            relative = source.relative_to(source_root)
            if should_copy(relative, source):
                yield source, relative


def preserve_public_overlay(target: Path) -> dict[Path, bytes]:
    preserved: dict[Path, bytes] = {}
    for relative in PUBLIC_OVERLAY_PATHS:
        path = target / relative
        if path.is_file():
            preserved[relative] = path.read_bytes()
    return preserved


def remove_target_contents(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_sanitized_tree(source_root: Path, target_root: Path) -> list[Path]:
    copied: list[Path] = []
    for source, relative in iter_candidate_files(source_root):
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative)
    return copied


def restore_public_overlay(target: Path, preserved: dict[Path, bytes]) -> None:
    for relative, content in preserved.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def ensure_minimal_public_files(target: Path) -> None:
    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(
            "# AgentHub\n\nLocal-first multi-provider AI agent CLI.\n",
            encoding="utf-8",
        )
    for relative, text in {
        Path("CONTRIBUTING.md"): "# Contributing\n\nIssues and pull requests are welcome.\n",
        Path("SECURITY.md"): "# Security\n\nPlease report security issues privately.\n",
    }.items():
        path = target / relative
        if not path.exists():
            path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    source = safe_resolve(Path(args.source))
    target = safe_resolve(Path(args.target))
    if source == target:
        raise SystemExit("source and target must be different")
    if not (source / "cli" / "agent_cli").is_dir():
        raise SystemExit(f"source does not look like AgentHub: {source}")

    preserved = preserve_public_overlay(target)
    if args.dry_run:
        copied = [relative for _, relative in iter_candidate_files(source)]
        print(
            f"dry_run=true source={source} target={target} files={len(copied)} preserved={len(preserved)}"
        )
        return 0

    remove_target_contents(target)
    copied = copy_sanitized_tree(source, target)
    restore_public_overlay(target, preserved)
    ensure_minimal_public_files(target)
    print(
        f"updated agenthubpublish: source={source} target={target} files={len(copied)} preserved={len(preserved)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
