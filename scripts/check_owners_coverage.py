from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_SCOPES: tuple[str, ...] = (
    "/cli/",
    "/gui/",
    "/plugins/",
    "/shared/",
    "/workers/",
    "/docs/",
    "/taskboard/",
    "/.github/workflows/",
    "root governance/config files",
)

SCOPE_ALIASES: dict[str, str] = {
    "Repository root configs": "root governance/config files",
}

CODEOWNERS_SCOPE_PATHS: dict[str, tuple[str, ...]] = {
    "/cli/": ("/cli/",),
    "/gui/": ("/gui/",),
    "/plugins/": ("/plugins/",),
    "/shared/": ("/shared/",),
    "/workers/": ("/workers/",),
    "/docs/": ("/docs/",),
    "/taskboard/": ("/taskboard/",),
    "/.github/workflows/": ("/.github/workflows/",),
    # Root governance/configs do not map to one wildcard entry today.
    "root governance/config files": ("/README.md", "/OWNERS.md", "/.github/CODEOWNERS"),
}


def _normalize_scope(raw: str) -> str:
    scope = " ".join(raw.strip().split())
    if scope.startswith("`") and scope.endswith("`") and len(scope) >= 2:
        scope = scope[1:-1].strip()
    return SCOPE_ALIASES.get(scope, scope)


def _normalize_owner(raw: str) -> str:
    owner = " ".join(raw.strip().split())
    if owner.startswith("`") and owner.endswith("`") and len(owner) >= 2:
        owner = owner[1:-1].strip()
    return owner


def _parse_scope_owner_table(markdown: str, section_header: str) -> dict[str, str]:
    marker = f"{section_header}\n"
    start = markdown.find(marker)
    if start == -1:
        raise ValueError(f"missing section: {section_header}")
    tail = markdown[start + len(marker) :]
    lines = tail.splitlines()
    mapping: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if not stripped.startswith("|"):
            continue
        cols = [part.strip() for part in stripped.strip("|").split("|")]
        if len(cols) < 2:
            continue
        if cols[0].lower() == "scope":
            continue
        if set(cols[0]) <= {"-"} and set(cols[1]) <= {"-"}:
            continue
        scope = _normalize_scope(cols[0])
        owner = _normalize_owner(cols[1])
        if not scope or not owner:
            continue
        mapping[scope] = owner
    return mapping


def _parse_codeowners(text: str) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        path = parts[0]
        owners = set(parts[1:])
        if path in mapping:
            mapping[path].update(owners)
        else:
            mapping[path] = owners
    return mapping


def validate_repo(repo_root: Path) -> list[str]:
    owners_path = repo_root / "OWNERS.md"
    codeowners_path = repo_root / ".github" / "CODEOWNERS"
    blueprint_path = repo_root / "docs" / "DIRECTORY_BLUEPRINT.md"

    errors: list[str] = []
    for required_file in (owners_path, codeowners_path, blueprint_path):
        if not required_file.exists():
            errors.append(f"missing required file: {required_file.relative_to(repo_root)}")
    if errors:
        return errors

    owners_text = owners_path.read_text(encoding="utf-8")
    codeowners_text = codeowners_path.read_text(encoding="utf-8")
    blueprint_text = blueprint_path.read_text(encoding="utf-8")

    try:
        owners_scopes = _parse_scope_owner_table(owners_text, "## Directory Ownership Baseline")
    except ValueError as exc:
        return [str(exc)]
    try:
        blueprint_scopes = _parse_scope_owner_table(
            blueprint_text, "## Governance Owner Mapping Baseline"
        )
    except ValueError as exc:
        return [str(exc)]
    codeowners_map = _parse_codeowners(codeowners_text)

    for scope in REQUIRED_SCOPES:
        if scope not in owners_scopes:
            errors.append(f"OWNERS.md missing required scope: {scope}")
        if scope not in blueprint_scopes:
            errors.append(f"docs/DIRECTORY_BLUEPRINT.md missing required scope: {scope}")

    for scope in REQUIRED_SCOPES:
        owner_value = owners_scopes.get(scope)
        blueprint_value = blueprint_scopes.get(scope)
        if owner_value and blueprint_value and owner_value != blueprint_value:
            errors.append(
                "owner drift for scope "
                f"{scope}: OWNERS.md has {owner_value}, DIRECTORY_BLUEPRINT has {blueprint_value}"
            )

    for scope, paths in CODEOWNERS_SCOPE_PATHS.items():
        expected_owner = owners_scopes.get(scope)
        if not expected_owner:
            continue
        for path in paths:
            owners = codeowners_map.get(path)
            if owners is None:
                errors.append(f".github/CODEOWNERS missing required path for {scope}: {path}")
                continue
            if expected_owner not in owners:
                listed = ", ".join(sorted(owners))
                errors.append(
                    f".github/CODEOWNERS path {path} missing expected owner "
                    f"{expected_owner} (found: {listed})"
                )

    return sorted(set(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate ownership coverage and baseline drift across governance docs."
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Path to repository root. Defaults to script parent root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    errors = validate_repo(repo_root)

    if errors:
        print("[owners-guard] failed")
        for error in errors:
            print(f"[owners-guard] {error}")
        return 1

    print("[owners-guard] passed")
    print(f"[owners-guard] checked repo root: {repo_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
