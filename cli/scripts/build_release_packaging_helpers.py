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
from collections.abc import Callable, Mapping
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


def bundle_codex_sidecar_runtime_root(
    packaged_root: Path,
    *,
    runtime_root: str | Path,
    runtime_version: str = "",
    platform_key: str | None = None,
    codex_platform_key_func: Callable[[], str] = codex_platform_key,
    codex_binary_name_func: Callable[[str], str] = codex_binary_name,
    sha256_digest_func: Callable[[Path], str] = sha256_digest,
) -> Path | None:
    source_runtime_root = Path(runtime_root).expanduser()
    if not str(runtime_root or "").strip():
        return None
    if not source_runtime_root.is_dir():
        raise FileNotFoundError(f"codex sidecar runtime root not found: {source_runtime_root}")
    resolved_platform = platform_key or codex_platform_key_func()
    version_label = _resolved_runtime_version(
        source_runtime_root,
        platform_key=resolved_platform,
        requested_version=runtime_version,
    )
    source_bundle_root = source_runtime_root / resolved_platform / version_label
    return bundle_codex_sidecar_runtime_bundle(
        packaged_root,
        runtime_bundle=source_bundle_root,
        runtime_version=version_label,
        platform_key=resolved_platform,
        codex_binary_name_func=codex_binary_name_func,
        sha256_digest_func=sha256_digest_func,
    )


def bundle_codex_sidecar_runtime_bundle(
    packaged_root: Path,
    *,
    runtime_bundle: str | Path,
    runtime_version: str = "",
    platform_key: str | None = None,
    codex_platform_key_func: Callable[[], str] = codex_platform_key,
    codex_binary_name_func: Callable[[str], str] = codex_binary_name,
    sha256_digest_func: Callable[[Path], str] = sha256_digest,
) -> Path | None:
    source_bundle_root = Path(runtime_bundle).expanduser()
    if not str(runtime_bundle or "").strip():
        return None
    if not source_bundle_root.is_dir():
        raise FileNotFoundError(f"codex sidecar runtime bundle not found: {source_bundle_root}")
    resolved_platform = platform_key or codex_platform_key_func()
    manifest = _read_json(source_bundle_root / "manifest.json")
    version_label = _safe_path_label(
        str(runtime_version or "").strip()
        or _manifest_version(manifest)
        or source_bundle_root.name
        or "current"
    )
    binary_name = codex_binary_name_func(resolved_platform)
    source_binary = source_bundle_root / binary_name
    if not source_binary.is_file():
        raise FileNotFoundError(
            f"codex sidecar binary not found in runtime bundle: {source_binary}"
        )

    runtime_root = packaged_root / "runtime" / "codex"
    target_bundle_root = runtime_root / resolved_platform / version_label
    if target_bundle_root.exists():
        shutil.rmtree(target_bundle_root)
    target_bundle_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_bundle_root, target_bundle_root)

    target = target_bundle_root / binary_name
    if os.name != "nt":
        for executable in _runtime_executable_paths(target_bundle_root, manifest, binary_name):
            if executable.exists():
                executable.chmod(executable.stat().st_mode | 0o755)
    digest = sha256_digest_func(target)

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


def _resolved_runtime_version(
    runtime_root: Path,
    *,
    platform_key: str,
    requested_version: str,
) -> str:
    requested = str(requested_version or "").strip()
    if requested and requested != "current":
        return _safe_path_label(requested)
    manifest = _read_json(runtime_root / "manifest.json")
    platforms = manifest.get("platforms") if isinstance(manifest, Mapping) else None
    if isinstance(platforms, Mapping):
        platform_entry = platforms.get(platform_key)
        if isinstance(platform_entry, Mapping):
            version = str(platform_entry.get("defaultVersion") or "").strip()
            if version:
                return _safe_path_label(version)
    if isinstance(manifest, Mapping):
        version = str(manifest.get("defaultVersion") or "").strip()
        if version:
            return _safe_path_label(version)
    return _safe_path_label(requested or "current")


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _manifest_version(manifest: Mapping[str, object]) -> str:
    for key in ("version", "sourceTag", "codexVersion"):
        value = str(manifest.get(key) or "").strip()
        if value:
            return value
    return ""


def _runtime_executable_paths(
    bundle_root: Path,
    manifest: Mapping[str, object],
    binary_name: str,
) -> list[Path]:
    paths = [bundle_root / binary_name]
    files = manifest.get("files")
    if isinstance(files, Mapping):
        for key in ("appServer", "rg", "bwrap"):
            value = str(files.get(key) or "").strip()
            if value:
                paths.append(bundle_root / value)
    resources = manifest.get("resources")
    if isinstance(resources, Mapping):
        for key in ("path", "bwrap"):
            value = str(resources.get(key) or "").strip()
            if value:
                paths.append(bundle_root / value)
    return _unique_paths(paths)


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        marker = str(path)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(path)
    return unique


def _runtime_root_manifest(runtime_root: Path) -> dict[str, object]:
    manifest_path = runtime_root / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}
