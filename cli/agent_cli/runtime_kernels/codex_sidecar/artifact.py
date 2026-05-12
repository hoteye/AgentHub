from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cli.agent_cli.runtime_kernels.codex_sidecar.errors import CodexSidecarProcessError

CODEX_SIDECAR_BIN_ENV = "AGENTHUB_CODEX_SIDECAR_BIN"
CODEX_SIDECAR_ALLOW_DEV_ENV = "AGENTHUB_CODEX_SIDECAR_ALLOW_DEV_FALLBACK"
CODEX_SIDECAR_TEST_BIN_ENV = "AGENTHUB_CODEX_SIDECAR_TEST_BIN"
DEFAULT_CODEX_RUNTIME_VERSION = "current"
DEFAULT_DEV_CODEX_BIN = Path(
    "/home/lyc/project/AgentHubRef/codex_ref/codex-rs/target/release/codex-app-server"
)


@dataclass(frozen=True, slots=True)
class CodexSidecarArtifact:
    path: Path
    source: str
    platform_key: str
    version: str = ""
    sha256: str = ""
    manifest: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CodexSidecarArtifactConfig:
    codex_bin: str | Path | None = None
    install_root: str | Path | None = None
    cache_root: str | Path | None = None
    runtime_version: str = DEFAULT_CODEX_RUNTIME_VERSION
    allow_cache_lookup: bool = False
    allow_path_lookup: bool = False
    allow_dev_fallback: bool = False
    dev_codex_bin: str | Path | None = None


def resolve_codex_sidecar_artifact(
    config: CodexSidecarArtifactConfig | None = None,
    *,
    env: Mapping[str, str] | None = None,
    platform_key: str | None = None,
    which: Callable[[str], str | None] | None = None,
    version_runner: Callable[[Path], str] | None = None,
) -> CodexSidecarArtifact:
    cfg = config or CodexSidecarArtifactConfig()
    env_map = env if env is not None else os.environ
    resolved_platform = platform_key or current_platform_key()
    finder = which or shutil.which
    errors: list[str] = []

    candidates = _candidate_specs(
        cfg,
        env=env_map,
        platform_key=resolved_platform,
        which=finder,
    )
    for source, candidate in candidates:
        if candidate is None:
            continue
        path = _normalized_path(candidate)
        if _is_executable_file(path):
            return _artifact_from_path(
                path,
                source=source,
                platform_key=resolved_platform,
                version_runner=version_runner,
            )
        errors.append(f"{source}: not executable or not found: {path}")

    searched = "; ".join(errors) if errors else "no candidates"
    raise CodexSidecarProcessError(f"codex sidecar binary not found ({searched})")


def resolve_codex_sidecar_test_binary(
    *,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    if _running_frozen_release():
        return None
    env_map = env if env is not None else os.environ
    candidate = _nonempty(env_map.get(CODEX_SIDECAR_TEST_BIN_ENV))
    if not candidate:
        return None
    path = _normalized_path(candidate)
    if _is_executable_file(path):
        return path
    raise CodexSidecarProcessError(f"codex sidecar test binary not found: {path}")


def codex_sidecar_external_binary_allowed() -> bool:
    return not _running_frozen_release()


def codex_sidecar_artifact_available(
    config: CodexSidecarArtifactConfig | None = None,
    *,
    env: Mapping[str, str] | None = None,
    platform_key: str | None = None,
    which: Callable[[str], str | None] | None = None,
) -> bool:
    cfg = config or CodexSidecarArtifactConfig()
    env_map = env if env is not None else os.environ
    resolved_platform = platform_key or current_platform_key()
    finder = which or shutil.which
    for _source, candidate in _candidate_specs(
        cfg,
        env=env_map,
        platform_key=resolved_platform,
        which=finder,
    ):
        if candidate is None:
            continue
        if _is_executable_file(_normalized_path(candidate)):
            return True
    return False


def current_platform_key() -> str:
    system = platform.system().strip().lower()
    machine = platform.machine().strip().lower()
    arch = _normalized_arch(machine)
    if system == "darwin":
        return f"macos-{arch}"
    if system == "windows":
        return f"windows-{arch}"
    return f"linux-{arch}"


def codex_binary_name(platform_key: str) -> str:
    return "codex-app-server.exe" if platform_key.startswith("windows-") else "codex-app-server"


def bundled_codex_binary_path(
    install_root: str | Path,
    *,
    platform_key: str,
    runtime_version: str = DEFAULT_CODEX_RUNTIME_VERSION,
) -> Path:
    return (
        Path(install_root).expanduser()
        / "runtime"
        / "codex"
        / platform_key
        / runtime_version
        / codex_binary_name(platform_key)
    )


def bundled_codex_runtime_root(install_root: str | Path) -> Path:
    return Path(install_root).expanduser() / "runtime" / "codex"


def cached_codex_binary_path(
    cache_root: str | Path,
    *,
    platform_key: str,
    runtime_version: str = DEFAULT_CODEX_RUNTIME_VERSION,
) -> Path:
    return (
        Path(cache_root).expanduser()
        / "runtimes"
        / "codex"
        / platform_key
        / runtime_version
        / codex_binary_name(platform_key)
    )


def cached_codex_runtime_root(cache_root: str | Path) -> Path:
    return Path(cache_root).expanduser() / "runtimes" / "codex"


def file_sha256(path: Path) -> str:
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
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip().splitlines()[0:1][0].strip()


def _candidate_specs(
    config: CodexSidecarArtifactConfig,
    *,
    env: Mapping[str, str],
    platform_key: str,
    which: Callable[[str], str | None],
) -> Sequence[tuple[str, str | Path | None]]:
    install_roots = (
        [Path(config.install_root).expanduser()]
        if config.install_root is not None
        else _default_install_roots()
    )
    cache_root = config.cache_root or _default_cache_root()
    runtime_version = config.runtime_version or DEFAULT_CODEX_RUNTIME_VERSION
    allow_dev = not _running_frozen_release() and (
        config.allow_dev_fallback or _env_truthy(env.get(CODEX_SIDECAR_ALLOW_DEV_ENV))
    )

    candidates: list[tuple[str, str | Path | None]] = []
    if allow_dev:
        candidates.extend(
            [
                ("env", _nonempty(env.get(CODEX_SIDECAR_BIN_ENV))),
                ("config", config.codex_bin),
            ]
        )
    for install_root in install_roots:
        resolved_runtime_version = _resolved_runtime_version(
            bundled_codex_runtime_root(install_root),
            platform_key=platform_key,
            requested_version=runtime_version,
        )
        candidates.append(
            (
                "bundled",
                bundled_codex_binary_path(
                    install_root,
                    platform_key=platform_key,
                    runtime_version=resolved_runtime_version,
                ),
            )
        )
    if config.allow_cache_lookup:
        resolved_cache_runtime_version = _resolved_runtime_version(
            cached_codex_runtime_root(cache_root),
            platform_key=platform_key,
            requested_version=runtime_version,
        )
        candidates.append(
            (
                "cache",
                cached_codex_binary_path(
                    cache_root,
                    platform_key=platform_key,
                    runtime_version=resolved_cache_runtime_version,
                ),
            )
        )
    if allow_dev:
        path_codex_app_server = (
            which(codex_binary_name(platform_key)) if config.allow_path_lookup else None
        )
        candidates.extend(
            [
                ("path", path_codex_app_server),
                ("dev", config.dev_codex_bin or DEFAULT_DEV_CODEX_BIN),
            ]
        )
    return tuple(candidates)


def _running_frozen_release() -> bool:
    return bool(getattr(sys, "frozen", False))


def _default_install_roots() -> list[Path]:
    roots: list[Path] = []
    raw_pyinstaller_root = str(getattr(sys, "_MEIPASS", "") or "").strip()
    if raw_pyinstaller_root:
        roots.append(Path(raw_pyinstaller_root).expanduser())
    raw_executable = str(sys.executable or "").strip()
    if raw_executable:
        roots.append(Path(raw_executable).expanduser().parent)
    try:
        roots.append(Path(__file__).resolve().parents[4])
    except IndexError:
        pass
    return _unique_paths(roots)


def _resolved_runtime_version(
    runtime_root: Path,
    *,
    platform_key: str,
    requested_version: str,
) -> str:
    requested = str(requested_version or DEFAULT_CODEX_RUNTIME_VERSION).strip()
    if requested and requested != DEFAULT_CODEX_RUNTIME_VERSION:
        return requested
    manifest = _read_json(runtime_root / "manifest.json")
    if not isinstance(manifest, dict):
        return requested or DEFAULT_CODEX_RUNTIME_VERSION
    platform_entry = manifest.get("platforms")
    if isinstance(platform_entry, dict):
        raw_platform = platform_entry.get(platform_key)
        if isinstance(raw_platform, dict):
            version = _nonempty(str(raw_platform.get("defaultVersion") or ""))
            if version:
                return version
    version = _nonempty(str(manifest.get("defaultVersion") or ""))
    return version or requested or DEFAULT_CODEX_RUNTIME_VERSION


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _unique_paths(paths: Sequence[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path.expanduser())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(path)
    return unique


def _artifact_from_path(
    path: Path,
    *,
    source: str,
    platform_key: str,
    version_runner: Callable[[Path], str] | None = None,
) -> CodexSidecarArtifact:
    resolved = path.expanduser().resolve(strict=False)
    manifest = _bundle_manifest_for_binary(resolved)
    runner = version_runner or probe_codex_version
    version = _manifest_version(manifest) or runner(resolved)
    return CodexSidecarArtifact(
        path=resolved,
        source=source,
        platform_key=platform_key,
        version=version,
        sha256=file_sha256(resolved),
        manifest=manifest if isinstance(manifest, dict) else {},
    )


def _bundle_manifest_for_binary(path: Path) -> dict[str, object]:
    payload = _read_json(path.parent / "manifest.json")
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _manifest_version(manifest: Mapping[str, object]) -> str:
    for key in ("codexVersion", "sourceTag", "version"):
        value = _nonempty(str(manifest.get(key) or ""))
        if value:
            return value
    return ""


def _normalized_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _is_executable_file(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _nonempty(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _env_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _default_cache_root() -> Path:
    return Path(os.environ.get("AGENTHUB_HOME") or Path.home() / ".agenthub")


def _normalized_arch(machine: str) -> str:
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    return machine or "unknown"
