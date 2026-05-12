from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


GUARDED_ROOTS = (
    "cli/agent_cli/",
    "cli/scripts/",
    "cli/tests/",
    "docs/",
)

PROVIDER_INTERNAL_PREFIXES = (
    "cli/agent_cli/provider",
    "cli/agent_cli/providers/",
    "cli/agent_cli/runtime_core/provider",
)

PROVIDER_INTERNAL_FILES = {
    "cli/agent_cli/runtime_core/setup_commands.py",
    "cli/scripts/script_runtime_helpers.py",
    "cli/scripts/provider_config_boundary_guard.py",
}

PROVIDER_TEST_PREFIXES = (
    "cli/tests/test_provider",
    "cli/tests/test_agent_provider",
    "cli/tests/test_anthropic_claude_provider.py",
    "cli/tests/test_script_runtime_helpers.py",
    "cli/tests/test_provider_config_boundary_guard.py",
)

PROVIDER_CONFIG_LOCATION_DOC_ALLOWLIST = {
    "docs/AGENTHUB_UNIFIED_PROVIDER_MANAGEMENT.md",
}

LOW_LEVEL_IMPORTS = {
    "cli.agent_cli.provider": {
        "load_provider_config",
        "load_provider_management_snapshot",
        "resolve_provider_paths",
    },
    "cli.scripts.script_runtime_helpers": {
        "load_script_provider_management_snapshot",
        "resolve_script_provider_source_paths",
        "resolve_script_provider_home_dir",
        "resolve_effective_script_provider_home_dir",
    },
}

SOURCE_CONFIG_PATTERNS = (
    re.compile(r"(^|[/\\])(?:cli[/\\])?\.config[/\\](?:config\.toml|auth\.json)(?:$|[?#])"),
    re.compile(r"(^|[/\\])\.agent_cli[/\\](?:config\.toml|auth\.json)(?:$|[?#])"),
)

SOURCE_CONFIG_ENV_NAMES = {
    "AGENTHUB_PROVIDER_HOME",
    "AGENTHUB_PROVIDER_STRICT_ISOLATION",
}

DOC_SOURCE_CONFIG_PATTERNS = (
    re.compile(r"(?<![\w.-])cli[/\\]\.config(?:[/\\](?:config\.toml|auth\.json))?"),
    re.compile(r"(?<![\w.-])\.config[/\\](?:config\.toml|auth\.json)"),
    re.compile(r"(?<![\w.-])(?:~[/\\])?\.agent_cli(?:[/\\](?:config\.toml|auth\.json))?"),
    re.compile(r"(?<![\w.-])(?:~[/\\])?\.codex[/\\](?:config\.toml|auth\.json)"),
)


@dataclass(frozen=True)
class Violation:
    lineno: int
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guard provider config access behind unified provider management APIs."
    )
    parser.add_argument(
        "--root",
        default="cli",
        help="Root directory for changed-file filtering. Use '.' to include docs.",
    )
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("GITHUB_BASE_REF", ""),
        help="GitHub PR base ref (e.g. main). Optional.",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Explicit Python or Markdown file to scan. Repeatable; bypasses git diff discovery.",
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


def _is_guarded_path(path: Path, root: Path) -> bool:
    normalized = path.as_posix()
    root_text = root.as_posix().rstrip("/")
    if root_text and root_text != "." and normalized != root_text and not normalized.startswith(root_text + "/"):
        return False
    return any(normalized.startswith(prefix) for prefix in GUARDED_ROOTS)


def changed_guarded_files(root: Path, base_ref: str) -> list[Path]:
    base = diff_base(base_ref)
    diff = run_git(["diff", "--name-only", f"{base}...HEAD"])
    items = []
    for raw in diff.splitlines():
        if not raw.endswith((".py", ".md")):
            continue
        path = Path(raw)
        if _is_guarded_path(path, root):
            items.append(path)
    return sorted(set(items))


def _policy_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_provider_boundary_owner(path: Path) -> bool:
    normalized = _policy_path(path)
    if normalized in PROVIDER_INTERNAL_FILES:
        return True
    if any(normalized.startswith(prefix) for prefix in PROVIDER_INTERNAL_PREFIXES):
        return True
    return any(normalized.startswith(prefix) for prefix in PROVIDER_TEST_PREFIXES)


def _is_provider_config_location_doc_owner(path: Path) -> bool:
    return _policy_path(path) in PROVIDER_CONFIG_LOCATION_DOC_ALLOWLIST


def _literal_provider_source_config_issue(value: str) -> str:
    text = str(value or "").strip()
    if text in SOURCE_CONFIG_ENV_NAMES:
        return f"direct provider environment access `{text}`"
    for pattern in SOURCE_CONFIG_PATTERNS:
        if pattern.search(text):
            return f"direct provider config path `{text}`"
    return ""


def _markdown_provider_source_config_issues(line: str) -> list[str]:
    issues = []
    seen = set()
    path_spans: list[tuple[int, int]] = []
    for env_name in sorted(SOURCE_CONFIG_ENV_NAMES):
        if env_name in line:
            issue = f"documents provider config environment `{env_name}`"
            issues.append(issue)
            seen.add(issue)
    for pattern in DOC_SOURCE_CONFIG_PATTERNS:
        for match in pattern.finditer(line):
            span = match.span()
            if any(start <= span[0] and span[1] <= end for start, end in path_spans):
                continue
            issue = f"documents provider config physical location `{match.group(0)}`"
            if issue not in seen:
                issues.append(issue)
                seen.add(issue)
                path_spans.append(span)
    return issues


def _scan_import_from(node: ast.ImportFrom) -> list[Violation]:
    module = str(node.module or "").strip()
    forbidden_names = LOW_LEVEL_IMPORTS.get(module)
    if not forbidden_names:
        return []
    violations: list[Violation] = []
    for alias in node.names:
        if alias.name in forbidden_names:
            violations.append(
                Violation(
                    lineno=getattr(node, "lineno", 1),
                    message=(
                        f"imports low-level provider config API `{module}.{alias.name}`; "
                        "use a unified provider facade/helper instead"
                    ),
                )
            )
    return violations


def _scan_python_file(path: Path) -> list[Violation]:
    if _is_provider_boundary_owner(path):
        return []
    source = path.read_text(encoding="utf-8-sig", errors="ignore")
    tree = ast.parse(source, filename=path.as_posix())
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            violations.extend(_scan_import_from(node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            issue = _literal_provider_source_config_issue(node.value)
            if issue:
                violations.append(
                    Violation(
                        lineno=getattr(node, "lineno", 1),
                        message=f"{issue}; use unified provider management instead",
                    )
                )
    return sorted(violations, key=lambda item: (item.lineno, item.message))


def _scan_markdown_file(path: Path) -> list[Violation]:
    if _is_provider_config_location_doc_owner(path):
        return []
    source = path.read_text(encoding="utf-8-sig", errors="ignore")
    violations: list[Violation] = []
    for offset, line in enumerate(source.splitlines(), start=1):
        for issue in _markdown_provider_source_config_issues(line):
            violations.append(
                Violation(
                    lineno=offset,
                    message=(
                        f"{issue}; keep physical path details in "
                        "docs/AGENTHUB_UNIFIED_PROVIDER_MANAGEMENT.md and use unified "
                        "provider APIs in reader-facing docs"
                    ),
                )
            )
    return sorted(violations, key=lambda item: (item.lineno, item.message))


def scan_file(path: Path) -> list[Violation]:
    if path.suffix == ".py":
        return _scan_python_file(path)
    if path.suffix == ".md":
        return _scan_markdown_file(path)
    return []


def _explicit_paths(raw_paths: list[str]) -> list[Path]:
    paths = []
    for raw in raw_paths:
        path = Path(str(raw or "").strip())
        if path.suffix in {".py", ".md"}:
            paths.append(path)
    return sorted(set(paths))


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    files = _explicit_paths(list(args.path or [])) or changed_guarded_files(
        root=root,
        base_ref=str(args.base_ref or ""),
    )
    if not files:
        print("[provider-config-guard] no changed python/markdown files under guard scope")
        return 0

    failures: list[str] = []
    for path in files:
        violations = scan_file(path)
        for violation in violations:
            failures.append(f"{path.as_posix()}:{violation.lineno} {violation.message}")

    if failures:
        print("[provider-config-guard] boundary violations:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(f"[provider-config-guard] pass on {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
