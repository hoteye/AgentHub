from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import zipfile
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_release_icon_helpers as icon_helpers  # noqa: E402
import build_release_packaging_helpers as packaging_helpers  # noqa: E402
import build_release_runtime_helpers as runtime_helpers  # noqa: E402
from build_release_runtime_helpers import (  # noqa: E402
    CANONICAL_CLI_DYNAMIC_HIDDEN_IMPORTS,
    PYINSTALLER_OPTIONAL_HEAVY_EXCLUDES,
)

_COMPAT_IMPORTED_MODULES = (
    hashlib,
    importlib,
    json,
    math,
    shutil,
    tarfile,
    time,
    zipfile,
    zlib,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cli_root() -> Path:
    return Path(__file__).resolve().parents[1]


def cli_version() -> str:
    namespace: dict[str, str] = {}
    init_path = cli_root() / "agent_cli" / "__init__.py"
    exec(init_path.read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    return parser.parse_args(argv)


def detect_platform_tag() -> str:
    return packaging_helpers.detect_platform_tag()


def codex_platform_key() -> str:
    return packaging_helpers.codex_platform_key()


def codex_binary_name(platform_key: str) -> str:
    return packaging_helpers.codex_binary_name(platform_key)


def sha256_digest(path: Path) -> str:
    return packaging_helpers.sha256_digest(path)


def probe_codex_version(path: Path, *, timeout: float = 5.0) -> str:
    return packaging_helpers.probe_codex_version(path, timeout=timeout)


def normalized_runtime_version(*, explicit_version: str, binary_version: str) -> str:
    for raw in (explicit_version, binary_version, "current"):
        text = str(raw or "").strip()
        if text:
            return _safe_path_label(text)
    return "current"


def _safe_path_label(value: str) -> str:
    return packaging_helpers._safe_path_label(value)


def has_module_spec(module_name: str) -> bool:
    return runtime_helpers.has_module_spec(module_name)


def maybe_add_collect(args: list[str], module_name: str) -> None:
    if has_module_spec(module_name):
        args.extend(["--collect-submodules", module_name])


def add_collect(args: list[str], module_name: str) -> None:
    runtime_helpers.add_collect(args, module_name)


def maybe_add_hidden_import(args: list[str], module_name: str) -> None:
    if has_module_spec(module_name):
        args.extend(["--hidden-import", module_name])


def add_hidden_import(args: list[str], module_name: str) -> None:
    runtime_helpers.add_hidden_import(args, module_name)


def add_data_arg(args: list[str], source: Path, dest: str) -> None:
    separator = ";" if os.name == "nt" else ":"
    args.extend(["--add-data", f"{source}{separator}{dest}"])


def _clamp(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    return icon_helpers._clamp(value, low=low, high=high)


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return icon_helpers._png_chunk(chunk_type, payload)


def _rgba_png_bytes(*, size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    return icon_helpers._rgba_png_bytes(size=size, pixels=pixels)


def _blend_color(
    base: tuple[int, int, int, int],
    overlay: tuple[int, int, int],
    alpha: float,
) -> tuple[int, int, int, int]:
    return icon_helpers._blend_color(base, overlay, alpha)


def _rounded_square_alpha(normalized_x: float, normalized_y: float, *, size: int) -> float:
    return icon_helpers._rounded_square_alpha(normalized_x, normalized_y, size=size)


def _distance_to_segment(
    point_x: float,
    point_y: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    return icon_helpers._distance_to_segment(point_x, point_y, start, end)


def _shape_alpha(distance: float, radius: float, *, size: int) -> float:
    return icon_helpers._shape_alpha(distance, radius, size=size)


def _agenthub_icon_pixels(size: int) -> list[tuple[int, int, int, int]]:
    return icon_helpers._agenthub_icon_pixels(size)


def _agenthub_icon_png(size: int) -> bytes:
    return icon_helpers._agenthub_icon_png(size)


def _ico_and_mask_bytes(*, size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    return icon_helpers._ico_and_mask_bytes(size=size, pixels=pixels)


def _ico_dib_bytes(*, size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    return icon_helpers._ico_dib_bytes(size=size, pixels=pixels)


def _agenthub_icon_dib(size: int) -> bytes:
    return icon_helpers._agenthub_icon_dib(size)


def build_agenthub_windows_icon_bytes() -> bytes:
    icon_sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [(size, _agenthub_icon_dib(size)) for size in icon_sizes]
    offset = 6 + 16 * len(images)
    directory_entries = []
    image_payloads = []
    for size, payload in images:
        width_byte = 0 if size >= 256 else size
        directory_entries.append(
            struct.pack("<BBBBHHII", width_byte, width_byte, 0, 0, 1, 32, len(payload), offset)
        )
        image_payloads.append(payload)
        offset += len(payload)
    return (
        struct.pack("<HHH", 0, 1, len(images))
        + b"".join(directory_entries)
        + b"".join(image_payloads)
    )


def agenthub_windows_icon_path(spec_dir: Path) -> Path:
    spec_dir.mkdir(parents=True, exist_ok=True)
    icon_path = spec_dir / "agenthub.ico"
    icon_path.write_bytes(build_agenthub_windows_icon_bytes())
    return icon_path


def _runtime_data_file_allowed(path: Path) -> bool:
    return runtime_helpers._runtime_data_file_allowed(path)


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


def canonical_cli_hidden_imports(*, cli: Path | None = None) -> list[str]:
    return runtime_helpers.canonical_cli_hidden_imports(cli=cli or cli_root())


def runtime_data_mappings(
    *, root: Path | None = None, cli: Path | None = None
) -> list[tuple[Path, str]]:
    repo_root_path = root or repo_root()
    cli_root_path = cli or cli_root()
    mappings: list[tuple[Path, str]] = [
        (repo_root_path / "config", "config"),
        (repo_root_path / "LICENSE", "."),
        (cli_root_path / "agent_cli" / "prompts", "cli/agent_cli/prompts"),
        (
            cli_root_path / "agent_cli" / "providers" / "interaction_profiles",
            "cli/agent_cli/providers/interaction_profiles",
        ),
    ]
    for relative in ("plugins", "shared", "tools", "document_tools", "workers"):
        source = repo_root_path / relative
        if source.exists():
            mappings.extend(_filtered_runtime_file_mappings(source, relative))
    return [(source, dest) for source, dest in mappings if source.exists()]


def pyinstaller_command(
    *, bundle_name: str, mode: str, dist_dir: Path, build_dir: Path, spec_dir: Path
) -> list[str]:
    root = repo_root()
    cli = cli_root()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--console",
        "--name",
        bundle_name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(root),
        "--paths",
        str(cli),
    ]
    if platform.system().lower() == "windows":
        command.extend(["--icon", str(agenthub_windows_icon_path(spec_dir))])
    command.append("--onedir" if mode == "onedir" else "--onefile")
    for module_name in PYINSTALLER_OPTIONAL_HEAVY_EXCLUDES:
        command.extend(["--exclude-module", module_name])
    for source, dest in runtime_data_mappings(root=root, cli=cli):
        add_data_arg(command, source, dest)
    add_collect(command, "cli.agent_cli")
    for module_name in CANONICAL_CLI_DYNAMIC_HIDDEN_IMPORTS:
        add_hidden_import(command, module_name)
    for package_name in (
        "textual",
        "rich",
        "openai",
        "agent_cli",
        "gateway",
        "workers",
    ):
        maybe_add_collect(command, package_name)
    for hidden in (
        "tools.office_tools",
        "tools.internal_policy_tools",
        "tools.web_search_tools",
        "workers.actions.worker",
    ):
        maybe_add_hidden_import(command, hidden)
    command.append(str(cli / "agent_cli" / "__main__.py"))
    return command


def ensure_clean(path: Path) -> None:
    packaging_helpers.ensure_clean(path)


def package_output(*, bundle_name: str, mode: str, artifact_dir: Path, dist_dir: Path) -> Path:
    return packaging_helpers.package_output(
        bundle_name=bundle_name,
        mode=mode,
        artifact_dir=artifact_dir,
        dist_dir=dist_dir,
        cli_version_func=cli_version,
        detect_platform_tag_func=detect_platform_tag,
        archive_packaged_root_func=lambda packaged_root: archive_packaged_root(
            packaged_root, artifact_dir=artifact_dir
        ),
    )


def archive_packaged_root(packaged_root: Path, *, artifact_dir: Path) -> Path:
    return packaging_helpers.archive_packaged_root(packaged_root, artifact_dir=artifact_dir)


def bundle_codex_sidecar_runtime(
    packaged_root: Path,
    *,
    codex_sidecar_bin: str | Path,
    runtime_version: str = "",
    source_revision: str = "",
    platform_key: str | None = None,
) -> Path | None:
    return packaging_helpers.bundle_codex_sidecar_runtime(
        packaged_root,
        codex_sidecar_bin=codex_sidecar_bin,
        runtime_version=runtime_version,
        source_revision=source_revision,
        platform_key=platform_key,
        codex_platform_key_func=codex_platform_key,
        probe_codex_version_func=probe_codex_version,
        normalized_runtime_version_func=normalized_runtime_version,
        codex_binary_name_func=codex_binary_name,
        sha256_digest_func=sha256_digest,
    )


def _runtime_root_manifest(runtime_root: Path) -> dict[str, object]:
    return packaging_helpers._runtime_root_manifest(runtime_root)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cli = cli_root()
    platform_tag = detect_platform_tag()
    artifact_dir = (
        Path(args.artifact_dir).resolve()
        if str(args.artifact_dir or "").strip()
        else (cli / "artifacts" / "releases").resolve()
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    build_dir = cli / "build" / "pyinstaller" / platform_tag
    dist_dir = cli / "dist" / platform_tag
    spec_dir = cli / "build" / "spec" / platform_tag
    if args.clean:
        ensure_clean(build_dir)
        ensure_clean(dist_dir)
        ensure_clean(spec_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("AGENTHUB_PROJECT_ROOT", str(repo_root()))
    command = pyinstaller_command(
        bundle_name=args.name,
        mode=args.mode,
        dist_dir=dist_dir,
        build_dir=build_dir,
        spec_dir=spec_dir,
    )
    subprocess.run(command, cwd=cli, env=env, check=True)
    archive = package_output(
        bundle_name=args.name, mode=args.mode, artifact_dir=artifact_dir, dist_dir=dist_dir
    )
    packaged_root = artifact_dir / f"{args.name}-{cli_version()}-{platform_tag}"
    if str(args.codex_sidecar_bin or "").strip():
        bundle_codex_sidecar_runtime(
            packaged_root,
            codex_sidecar_bin=args.codex_sidecar_bin,
            runtime_version=args.codex_sidecar_version,
            source_revision=args.codex_sidecar_source_revision,
        )
        archive = archive_packaged_root(packaged_root, artifact_dir=artifact_dir)
    print(str(archive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
