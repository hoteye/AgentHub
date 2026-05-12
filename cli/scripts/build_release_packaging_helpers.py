from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import time
import zipfile
from collections.abc import Callable
from pathlib import Path


def detect_platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    machine = aliases.get(machine, machine)
    return f"{system}-{machine}"


def codex_platform_key() -> str:
    system = platform.system().strip().lower()
    machine = platform.machine().strip().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
    }
    arch = aliases.get(machine, machine or "unknown")
    if system == "darwin":
        return f"macos-{arch}"
    if system == "windows":
        return f"windows-{arch}"
    return f"linux-{arch}"


def codex_binary_name(platform_key: str) -> str:
    return "codex-app-server.exe" if platform_key.startswith("windows-") else "codex-app-server"


def sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_codex_version(path: Path, *, timeout: float = 5.0) -> str:
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip().splitlines()[0:1][0].strip()


def normalized_runtime_version(*, explicit_version: str, binary_version: str) -> str:
    for raw in (explicit_version, binary_version, "current"):
        text = str(raw or "").strip()
        if text:
            return _safe_path_label(text)
    return "current"


def _safe_path_label(value: str) -> str:
    label = "".join(char if char.isalnum() or char in "._-" else "-" for char in value.strip())
    label = "-".join(part for part in label.split("-") if part)
    return label[:96] or "current"


def ensure_clean(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def package_output(
    *,
    bundle_name: str,
    mode: str,
    artifact_dir: Path,
    dist_dir: Path,
    cli_version_func: Callable[[], str],
    detect_platform_tag_func: Callable[[], str],
    archive_packaged_root_func: Callable[[Path], Path],
) -> Path:
    version = cli_version_func()
    platform_tag = detect_platform_tag_func()
    bundle_dir = dist_dir / bundle_name
    if mode == "onefile":
        executable = bundle_dir.with_suffix(
            ".exe" if platform.system().lower() == "windows" else ""
        )
        packaged_root = artifact_dir / f"{bundle_name}-{version}-{platform_tag}"
        if packaged_root.exists():
            shutil.rmtree(packaged_root)
        packaged_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(executable, packaged_root / executable.name)
    else:
        packaged_root = artifact_dir / f"{bundle_name}-{version}-{platform_tag}"
        if packaged_root.exists():
            shutil.rmtree(packaged_root)
        shutil.copytree(bundle_dir, packaged_root)
    return archive_packaged_root_func(packaged_root)


def archive_packaged_root(packaged_root: Path, *, artifact_dir: Path) -> Path:
    if platform.system().lower() == "windows":
        archive_path = artifact_dir / f"{packaged_root.name}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(packaged_root.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(packaged_root.parent)))
        return archive_path
    archive_path = artifact_dir / f"{packaged_root.name}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(packaged_root, arcname=packaged_root.name)
    return archive_path


def bundle_codex_sidecar_runtime(
    packaged_root: Path,
    *,
    codex_sidecar_bin: str | Path,
    runtime_version: str = "",
    source_revision: str = "",
    platform_key: str | None = None,
    codex_platform_key_func: Callable[[], str] = codex_platform_key,
    probe_codex_version_func: Callable[[Path], str] = probe_codex_version,
    normalized_runtime_version_func: Callable[..., str] = normalized_runtime_version,
    codex_binary_name_func: Callable[[str], str] = codex_binary_name,
    sha256_digest_func: Callable[[Path], str] = sha256_digest,
) -> Path | None:
    source = Path(codex_sidecar_bin).expanduser()
    if not str(codex_sidecar_bin or "").strip():
        return None
    if not source.is_file():
        raise FileNotFoundError(f"codex sidecar binary not found: {source}")
    resolved_platform = platform_key or codex_platform_key_func()
    binary_version = probe_codex_version_func(source)
    version_label = normalized_runtime_version_func(
        explicit_version=runtime_version,
        binary_version=binary_version,
    )
    runtime_root = packaged_root / "runtime" / "codex"
    bundle_root = runtime_root / resolved_platform / version_label
    bundle_root.mkdir(parents=True, exist_ok=True)
    binary_name = codex_binary_name_func(resolved_platform)
    target = bundle_root / binary_name
    shutil.copy2(source, target)
    if os.name != "nt":
        target.chmod(target.stat().st_mode | 0o755)
    digest = sha256_digest_func(target)
    manifest = {
        "name": "codex-ref-sidecar",
        "version": version_label,
        "platform": resolved_platform,
        "binary": binary_name,
        "sourceRevision": str(source_revision or "").strip(),
        "binaryVersion": binary_version,
        "protocol": "app-server",
        "transport": ["stdio"],
        "entrypoint": binary_name,
        "args": ["--listen", "stdio://"],
        "sha256": digest,
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (bundle_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    root_manifest = _runtime_root_manifest(runtime_root)
    root_manifest.setdefault("name", "agenthub-codex-sidecar-runtimes")
    root_manifest["defaultVersion"] = version_label
    platforms = root_manifest.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        root_manifest["platforms"] = platforms
    platforms[resolved_platform] = {
        "defaultVersion": version_label,
        "binary": str((Path(resolved_platform) / version_label / binary_name).as_posix()),
        "manifest": str((Path(resolved_platform) / version_label / "manifest.json").as_posix()),
        "sha256": digest,
    }
    (runtime_root / "manifest.json").write_text(
        json.dumps(root_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _runtime_root_manifest(runtime_root: Path) -> dict[str, object]:
    manifest_path = runtime_root / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}
