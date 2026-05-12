from __future__ import annotations

import argparse
import compileall
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import zipfile


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def gui_root() -> Path:
    return repo_root() / "gui"


def detect_platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
    }
    machine = aliases.get(machine, machine)
    return f"{system}-{machine}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a portable Electron desktop bundle for AgentHub GUI.")
    parser.add_argument("--name", default="agenthub-gui-desktop", help="Bundle base name.")
    parser.add_argument(
        "--version",
        default=os.environ.get("AGENTHUB_GUI_RELEASE_VERSION", ""),
        help="Optional release version used in bundle/archive naming.",
    )
    parser.add_argument("--artifact-dir", default="", help="Output directory for the bundle archive.")
    parser.add_argument("--clean", action="store_true", help="Remove previous bundle staging output before building.")
    parser.add_argument("--skip-build", action="store_true", help="Skip `pnpm build` and reuse current gui/dist.")
    parser.add_argument(
        "--obfuscation-level",
        choices=("none", "minimal"),
        default=os.environ.get("AGENTHUB_GUI_OBFUSCATION_LEVEL", "none"),
        help="Optional release hardening level. `minimal` compiles selected Python runtime trees to sourceless `.pyc` files.",
    )
    return parser.parse_args(argv)


def run(command: list[str], *, cwd: Path) -> None:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    subprocess.run(command, cwd=cwd, env=env, check=True)


def resolve_electron_dist() -> Path:
    pnpm_root = gui_root() / "node_modules" / ".pnpm"
    matches = sorted(pnpm_root.glob("electron@*/node_modules/electron/dist"))
    if not matches:
        raise FileNotFoundError("Could not locate Electron dist directory. Run `cd gui && pnpm desktop:prepare` first.")
    return matches[-1]


def normalize_release_version(value: str | None) -> str:
    text = str(value or "").strip()
    if text.startswith("gui-v"):
        return text[len("gui-v") :]
    if text.startswith("v"):
        return text[1:]
    return text


def bundle_directory_name(*, base_name: str, version: str, platform_tag: str) -> str:
    normalized_version = normalize_release_version(version)
    if normalized_version:
        return f"{base_name}-{normalized_version}-{platform_tag}"
    return f"{base_name}-{platform_tag}"


def archive_suffix(system_name: str | None = None) -> str:
    system = str(system_name or platform.system()).lower()
    return ".zip" if system == "windows" else ".tar.gz"


def legacy_pyc_path(source_path: Path) -> Path:
    return source_path.with_suffix(".pyc")


def minimal_obfuscation_targets(bundle_root: Path) -> list[Path]:
    candidates = [
        bundle_root / "cli",
        bundle_root / "shared",
        bundle_root / "workers",
        bundle_root / "tools",
        bundle_root / "document_tools",
        bundle_root / "gateway",
    ]
    return [path for path in candidates if path.exists()]


def compile_sourceless_python_tree(root: Path) -> dict[str, int]:
    compiled = compileall.compile_dir(
        str(root),
        force=True,
        quiet=1,
        legacy=True,
        optimize=1,
    )
    if not compiled:
        raise RuntimeError(f"Failed to compile Python tree for minimal obfuscation: {root}")
    removed = 0
    retained = 0
    for source_path in sorted(root.rglob("*.py")):
        pyc_path = legacy_pyc_path(source_path)
        if pyc_path.exists():
            source_path.unlink()
            removed += 1
        else:
            retained += 1
    return {
        "compiled_root_count": 1,
        "python_sources_removed": removed,
        "python_sources_retained": retained,
    }


def apply_minimal_obfuscation(bundle_root: Path) -> dict[str, int]:
    summary = {
        "compiled_root_count": 0,
        "python_sources_removed": 0,
        "python_sources_retained": 0,
    }
    for target in minimal_obfuscation_targets(bundle_root):
        target_summary = compile_sourceless_python_tree(target)
        for key, value in target_summary.items():
            summary[key] += int(value or 0)
    return summary


def unix_launcher_text() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for candidate in \
  "${SCRIPT_DIR}/gui/electron-dist/electron" \
  "${SCRIPT_DIR}/gui/electron-dist/Electron.app/Contents/MacOS/Electron"; do
  if [[ -x "${candidate}" ]]; then
    export AGENTHUB_PROJECT_ROOT="${SCRIPT_DIR}"
    exec "${candidate}" "${SCRIPT_DIR}/gui/electron/main.mjs"
  fi
done

echo "Electron runtime not found inside bundle." >&2
exit 1
"""


def windows_cmd_launcher_text() -> str:
    return """@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "ELECTRON_EXE=%SCRIPT_DIR%gui\\electron-dist\\electron.exe"

if not exist "%ELECTRON_EXE%" (
  echo Electron runtime not found inside bundle. 1>&2
  exit /b 1
)

set "AGENTHUB_PROJECT_ROOT=%SCRIPT_DIR%"
"%ELECTRON_EXE%" "%SCRIPT_DIR%gui\\electron\\main.mjs"
exit /b %ERRORLEVEL%
"""


def windows_ps1_launcher_text() -> str:
    return """$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Candidates = @(
    (Join-Path $ScriptDir "gui\\electron-dist\\electron.exe"),
    (Join-Path $ScriptDir "gui\\electron-dist\\Electron.app\\Contents\\MacOS\\Electron"),
    (Join-Path $ScriptDir "gui\\electron-dist\\electron")
)

foreach ($Candidate in $Candidates) {
    if (Test-Path $Candidate) {
        $env:AGENTHUB_PROJECT_ROOT = $ScriptDir
        & $Candidate (Join-Path $ScriptDir "gui\\electron\\main.mjs")
        exit $LASTEXITCODE
    }
}

throw "Electron runtime not found inside bundle."
"""


def copy_path(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def write_launchers(bundle_root: Path) -> None:
    unix_launcher = bundle_root / "start_gui_desktop.sh"
    unix_launcher.write_text(unix_launcher_text(), encoding="utf-8")
    unix_launcher.chmod(0o755)

    cmd_launcher = bundle_root / "start_gui_desktop.cmd"
    cmd_launcher.write_text(windows_cmd_launcher_text(), encoding="utf-8")

    ps1_launcher = bundle_root / "start_gui_desktop.ps1"
    ps1_launcher.write_text(windows_ps1_launcher_text(), encoding="utf-8")


def write_bundle_readme(
    bundle_root: Path,
    *,
    version: str,
    archive_name: str,
    obfuscation_level: str,
) -> None:
    version_line = f"- bundle version: `{normalize_release_version(version)}`\n" if normalize_release_version(version) else ""
    obfuscation_line = f"- obfuscation level: `{str(obfuscation_level or 'none').strip() or 'none'}`\n"
    readme = bundle_root / "README_DESKTOP_BUNDLE.md"
    readme.write_text(
        f"""# AgentHub GUI Desktop Bundle

This bundle contains:

- prebuilt `gui/dist`
- Electron desktop shell
- local GUI bridge launcher
- bundled AgentHub runtime directories required by the GUI bridge
{version_line}- release archive name: `{archive_name}`
{obfuscation_line}

Run:

Linux or macOS:

```bash
./start_gui_desktop.sh
```

Windows Command Prompt:

```bat
start_gui_desktop.cmd
```

Windows PowerShell:

```powershell
./start_gui_desktop.ps1
```

Current prerequisites:

- Python 3 available on PATH, or an existing repo `.venv`
- system libraries required by Electron on Linux

Current scope:

- desktop shell and local bridge startup are bundled for Linux, macOS, and Windows
- this is a portable desktop bundle, not a finished native installer
- packaging still does not include a Python runtime or Playwright/browser dependencies
- `minimal` obfuscation currently converts selected host/runtime Python trees into sourceless `.pyc` files
- plugin source files remain present because the current plugin loader still resolves `manifest.py` and related plugin modules by file path
""",
        encoding="utf-8",
    )


def write_bundle_manifest(
    bundle_root: Path,
    *,
    bundle_name: str,
    version: str,
    platform_tag: str,
    archive_name: str,
    obfuscation_level: str,
    obfuscation_summary: dict[str, int] | None = None,
) -> None:
    payload = {
        "distribution_kind": "portable_bundle",
        "bundle_name": bundle_name,
        "version": normalize_release_version(version),
        "platform_tag": platform_tag,
        "archive_name": archive_name,
        "archive_format": archive_suffix().lstrip("."),
        "obfuscation_level": str(obfuscation_level or "none").strip() or "none",
        "obfuscation_summary": dict(obfuscation_summary or {}),
        "launchers": [
            "start_gui_desktop.sh",
            "start_gui_desktop.cmd",
            "start_gui_desktop.ps1",
        ],
        "prerequisites": {
            "python_required": True,
            "native_installer": False,
        },
        "release_posture": {
            "intended_distribution": "closed_trial_before_open_source_decision",
            "plugin_source_files_retained": True,
        },
    }
    manifest_path = bundle_root / "release-manifest.json"
    manifest_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def package_bundle(bundle_root: Path, artifact_dir: Path) -> Path:
    archive_path = artifact_dir / f"{bundle_root.name}{archive_suffix()}"
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle_root.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(bundle_root.parent)))
        return archive_path
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(bundle_root, arcname=bundle_root.name)
    return archive_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    gui = gui_root()
    artifact_dir = (
        Path(args.artifact_dir).resolve()
        if str(args.artifact_dir or "").strip()
        else (root / "artifacts" / "gui-desktop-releases").resolve()
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    run(["pnpm", "desktop:prepare"], cwd=gui)
    if not args.skip_build:
        run(["pnpm", "build"], cwd=gui)

    platform_tag = detect_platform_tag()
    bundle_root_name = bundle_directory_name(
        base_name=args.name,
        version=args.version,
        platform_tag=platform_tag,
    )
    bundle_root = artifact_dir / bundle_root_name
    if args.clean and bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    electron_dist = resolve_electron_dist()

    copy_map = [
        (root / "gui" / "dist", bundle_root / "gui" / "dist"),
        (root / "gui" / "electron", bundle_root / "gui" / "electron"),
        (electron_dist, bundle_root / "gui" / "electron-dist"),
        (root / "gui" / "README.md", bundle_root / "gui" / "README.md"),
        (root / "cli" / "__init__.py", bundle_root / "cli" / "__init__.py"),
        (root / "cli" / "agent_cli", bundle_root / "cli" / "agent_cli"),
        (root / "cli" / "scripts" / "start_gui_bridge.sh", bundle_root / "cli" / "scripts" / "start_gui_bridge.sh"),
        (root / "cli" / "scripts" / "start_gui_bridge.ps1", bundle_root / "cli" / "scripts" / "start_gui_bridge.ps1"),
        (root / "shared", bundle_root / "shared"),
        (root / "plugins", bundle_root / "plugins"),
        (root / "workers", bundle_root / "workers"),
        (root / "config", bundle_root / "config"),
        (root / "gateway", bundle_root / "gateway"),
        (root / "tools", bundle_root / "tools"),
        (root / "document_tools", bundle_root / "document_tools"),
        (root / "README.md", bundle_root / "README.md"),
        (root / "docs" / "GUI_ACCEPTANCE_RUNBOOK.md", bundle_root / "docs" / "GUI_ACCEPTANCE_RUNBOOK.md"),
        (root / "docs" / "GUI_DESKTOP_INSTALL_AND_RUN.md", bundle_root / "docs" / "GUI_DESKTOP_INSTALL_AND_RUN.md"),
    ]
    for source, destination in copy_map:
        if source.exists():
            copy_path(source, destination)

    obfuscation_level = str(args.obfuscation_level or "none").strip() or "none"
    obfuscation_summary: dict[str, int] = {}
    if obfuscation_level == "minimal":
        obfuscation_summary = apply_minimal_obfuscation(bundle_root)

    archive_name = f"{bundle_root.name}{archive_suffix()}"
    write_launchers(bundle_root)
    write_bundle_readme(
        bundle_root,
        version=args.version,
        archive_name=archive_name,
        obfuscation_level=obfuscation_level,
    )
    write_bundle_manifest(
        bundle_root,
        bundle_name=args.name,
        version=args.version,
        platform_tag=platform_tag,
        archive_name=archive_name,
        obfuscation_level=obfuscation_level,
        obfuscation_summary=obfuscation_summary,
    )

    archive_path = package_bundle(bundle_root, artifact_dir)
    print(str(archive_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
