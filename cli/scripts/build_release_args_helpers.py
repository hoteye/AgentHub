from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build portable executable releases for AgentHub CLI."
    )
    parser.add_argument("--name", default="agenthub-cli", help="Executable base name.")
    parser.add_argument(
        "--mode", choices=("onedir", "onefile"), default="onedir", help="PyInstaller bundle mode."
    )
    parser.add_argument(
        "--clean", action="store_true", help="Remove previous build/dist outputs before building."
    )
    parser.add_argument(
        "--artifact-dir", default="", help="Output directory for packaged archives."
    )
    parser.add_argument(
        "--codex-sidecar-bin",
        default="",
        help=(
            "Optional Codex ref sidecar binary to bundle under "
            "runtime/codex/<platform>/<version>/."
        ),
    )
    parser.add_argument(
        "--codex-sidecar-version",
        default="",
        help="Runtime bundle version label. Defaults to the binary --version output or 'current'.",
    )
    parser.add_argument(
        "--codex-sidecar-source-revision",
        default="",
        help="Optional Codex ref source revision recorded in the runtime manifest.",
    )
    parser.add_argument(
        "--codex-sidecar-runtime-root",
        default="",
        help=(
            "Optional prepared Codex runtime root to bundle, for example runtime/codex. "
            "Copies the current platform/version bundle including codex-app-server, rg, "
            "bwrap, and manifests."
        ),
    )
    parser.add_argument(
        "--codex-sidecar-runtime-bundle",
        default="",
        help=(
            "Optional prepared Codex runtime bundle directory to copy directly, for "
            "example runtime/codex/linux-x86_64/rust-v0.129.0."
        ),
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def normalized_runtime_version(
    *,
    explicit_version: str,
    binary_version: str,
    safe_path_label_func: Callable[[str], str],
) -> str:
    for raw in (explicit_version, binary_version, "current"):
        text = str(raw or "").strip()
        if text:
            return safe_path_label_func(text)
    return "current"


def release_artifact_dir(raw_artifact_dir: object, *, cli: Path) -> Path:
    if str(raw_artifact_dir or "").strip():
        return Path(raw_artifact_dir).resolve()
    return (cli / "artifacts" / "releases").resolve()


def release_output_dirs(*, cli: Path, platform_tag: str) -> tuple[Path, Path, Path]:
    return (
        cli / "build" / "pyinstaller" / platform_tag,
        cli / "dist" / platform_tag,
        cli / "build" / "spec" / platform_tag,
    )


def has_arg_value(value: object) -> bool:
    return bool(str(value or "").strip())
