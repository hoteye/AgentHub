from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path


RULES: dict[str, tuple[str, ...]] = {
    "cli.agent_cli.core.": ("cli.agent_cli.ui",),
    "cli.agent_cli.runtime_core.": ("cli.agent_cli.ui",),
    "cli.agent_cli.runtime_services.": ("cli.agent_cli.ui",),
    "cli.agent_cli.background_tasks.": ("cli.agent_cli.ui",),
    "cli.agent_cli.providers.": ("cli.agent_cli.ui",),
    "cli.agent_cli.tools_core.": ("cli.agent_cli.ui",),
    "cli.agent_cli.gateway_server.": ("cli.agent_cli.ui",),
    "cli.agent_cli.ui.": ("cli.agent_cli.runtime",),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import boundary guard for changed python files."
    )
    parser.add_argument("--root", default="cli/agent_cli", help="Root package directory.")
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("GITHUB_BASE_REF", ""),
        help="GitHub PR base ref (e.g. main). Optional.",
    )
    return parser.parse_args()


def run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def diff_base(base_ref: str) -> str:
    if base_ref:
        remote_ref = f"origin/{base_ref}"
        subprocess.run(["git", "fetch", "--no-tags", "origin", base_ref], check=False)
        try:
            return run_git(["merge-base", "HEAD", remote_ref])
        except subprocess.CalledProcessError:
            pass
    try:
        return run_git(["rev-parse", "HEAD~1"])
    except subprocess.CalledProcessError:
        return run_git(["rev-parse", "HEAD"])


def changed_python_files(root: Path, base_ref: str) -> list[Path]:
    base = diff_base(base_ref)
    diff = run_git(["diff", "--name-only", f"{base}...HEAD"])
    items = []
    for raw in diff.splitlines():
        if not raw.endswith(".py"):
            continue
        path = Path(raw)
        if str(path).startswith(root.as_posix() + "/"):
            items.append(path)
    return sorted(set(items))


def module_name(path: Path) -> str:
    no_suffix = path.with_suffix("")
    return ".".join(no_suffix.parts)


def resolve_import(current_module: str, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    parts = current_module.split(".")[:-1]
    keep = len(parts) - (node.level - 1)
    if keep < 0:
        return node.module
    base = parts[:keep]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def forbidden_for(module: str) -> tuple[str, ...]:
    for owner_prefix, forbidden in RULES.items():
        if module.startswith(owner_prefix):
            return forbidden
    return ()


def is_forbidden(imported: str, forbidden: str) -> bool:
    return imported == forbidden or imported.startswith(f"{forbidden}.")


def scan_file(path: Path) -> list[tuple[int, str]]:
    module = module_name(path)
    forbidden = forbidden_for(module)
    if not forbidden:
        return []

    source = path.read_text(encoding="utf-8-sig", errors="ignore")
    tree = ast.parse(source, filename=path.as_posix())
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        imported: str | None = None
        lineno = getattr(node, "lineno", 1)
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported = alias.name
                if any(is_forbidden(imported, item) for item in forbidden):
                    violations.append((lineno, imported))
        elif isinstance(node, ast.ImportFrom):
            imported = resolve_import(module, node)
            if imported and any(is_forbidden(imported, item) for item in forbidden):
                violations.append((lineno, imported))
    return violations


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    files = changed_python_files(root=root, base_ref=args.base_ref)
    if not files:
        print("[import-guard] no changed python files under guard scope")
        return 0

    failures: list[str] = []
    for path in files:
        violations = scan_file(path)
        for lineno, imported in violations:
            failures.append(
                f"{path.as_posix()}:{lineno} imports forbidden module '{imported}'"
            )

    if failures:
        print("[import-guard] boundary violations:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(f"[import-guard] pass on {len(files)} changed files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
