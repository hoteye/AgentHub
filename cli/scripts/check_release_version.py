from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cli_init_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "cli" / "agent_cli" / "__init__.py"


def changelog_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "CHANGELOG.md"


def read_cli_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = _VERSION_PATTERN.search(text)
    if match is None:
        raise ValueError(f"could not find __version__ in {path}")
    return str(match.group(1) or "").strip()


def normalized_ref_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("refs/tags/"):
        return text.split("/", 2)[-1]
    return text.rsplit("/", 1)[-1]


def expected_release_tag(version: str, *, prefix: str = "cli-v") -> str:
    return f"{prefix}{str(version or '').strip()}"


def validate_release_ref(version: str, ref_name: str, *, prefix: str = "cli-v") -> None:
    normalized = normalized_ref_name(ref_name)
    expected = expected_release_tag(version, prefix=prefix)
    if normalized != expected:
        raise ValueError(f"release ref mismatch: expected {expected}, got {normalized or '<empty>'}")


def extract_changelog_section(text: str, version: str) -> str | None:
    escaped_version = re.escape(str(version or "").strip())
    if not escaped_version:
        return None
    heading_pattern = re.compile(rf"^##\s+\[?{escaped_version}\]?(?:\s+-\s+.*)?$", re.MULTILINE)
    match = heading_pattern.search(text)
    if match is None:
        return None
    start = match.end()
    next_match = re.compile(r"^##\s+", re.MULTILINE).search(text, start)
    body = text[start:next_match.start()] if next_match is not None else text[start:]
    normalized = body.strip()
    return f"{normalized}\n" if normalized else None


def write_release_notes(version: str, *, changelog: Path, output: Path) -> None:
    if not changelog.exists():
        raise ValueError(f"missing changelog: {changelog}")
    section = extract_changelog_section(changelog.read_text(encoding="utf-8"), version)
    if section is None:
        raise ValueError(f"missing changelog section for version {version} in {changelog}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(section, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate agent_cli release version and render release notes.")
    parser.add_argument("--repo-root", default="", help="Repository root override. Defaults to auto-detected root.")
    parser.add_argument("--ref-name", default="", help="Expected release ref or tag name, for example cli-v0.1.0.")
    parser.add_argument("--tag-prefix", default="cli-v", help="Release tag prefix. Defaults to cli-v.")
    parser.add_argument("--print-version", action="store_true", help="Print the discovered CLI version.")
    parser.add_argument(
        "--release-notes-out",
        default="",
        help="Write release notes for the current version by extracting the matching CHANGELOG.md section.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve() if str(args.repo_root or "").strip() else repo_root()
    version = read_cli_version(cli_init_path(root))
    if args.ref_name:
        validate_release_ref(version, args.ref_name, prefix=str(args.tag_prefix or "cli-v"))
    if args.release_notes_out:
        write_release_notes(
            version,
            changelog=changelog_path(root),
            output=Path(args.release_notes_out).resolve(),
        )
    if args.print_version:
        print(version)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"release check error: {exc}", file=sys.stderr)
        raise SystemExit(1)
