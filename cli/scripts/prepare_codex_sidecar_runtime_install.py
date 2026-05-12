from __future__ import annotations

import json
import os
import shutil
import stat
import tarfile
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

try:
    from .prepare_codex_sidecar_runtime_assets import release_tag
    from .prepare_codex_sidecar_runtime_io import _safe_path_label
    from .prepare_codex_sidecar_runtime_manifest import _bundle_manifest, update_root_manifest
    from .prepare_codex_sidecar_runtime_models import (
        DEFAULT_GITHUB_REPO,
        DEFAULT_RUNTIME_VERSION,
        PlatformSpec,
    )
except ImportError:
    from prepare_codex_sidecar_runtime_assets import release_tag
    from prepare_codex_sidecar_runtime_io import _safe_path_label
    from prepare_codex_sidecar_runtime_manifest import _bundle_manifest, update_root_manifest
    from prepare_codex_sidecar_runtime_models import (
        DEFAULT_GITHUB_REPO,
        DEFAULT_RUNTIME_VERSION,
        PlatformSpec,
    )


def install_runtime_bundle(
    *,
    runtime_root: Path,
    platform_spec: PlatformSpec,
    runtime_version: str,
    release_payload: Mapping[str, Any],
    source_repo: str = DEFAULT_GITHUB_REPO,
    app_server_archive: Path,
    npm_platform_archive: Path,
    bwrap_archive: Path | None = None,
    force: bool = False,
) -> Path:
    tag = release_tag(release_payload)
    version_label = _safe_path_label(runtime_version or tag or DEFAULT_RUNTIME_VERSION)
    platform_root = runtime_root / platform_spec.platform_key
    bundle_root = platform_root / version_label
    staging_root = platform_root / f".{version_label}.tmp-{os.getpid()}"
    if bundle_root.exists() and not force:
        raise FileExistsError(f"codex sidecar runtime bundle already exists: {bundle_root}")
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True)
    try:
        app_server_path = staging_root / platform_spec.app_server_binary
        copy_archive_member(
            app_server_archive,
            app_server_path,
            matcher=lambda name: _binary_member_matches(
                name,
                install_name=platform_spec.app_server_binary,
                target_triple=platform_spec.target_triple,
            ),
        )
        _chmod_executable(app_server_path)

        rg_path = staging_root / "path" / platform_spec.rg_binary
        copy_archive_member(
            npm_platform_archive,
            rg_path,
            matcher=lambda name: _archive_name(name).endswith(f"/path/{platform_spec.rg_binary}"),
        )
        _chmod_executable(rg_path)

        bwrap_path: Path | None = None
        if platform_spec.is_linux:
            if bwrap_archive is None:
                raise FileNotFoundError(f"missing bwrap archive for {platform_spec.platform_key}")
            bwrap_path = staging_root / "codex-resources" / platform_spec.bwrap_binary
            copy_archive_member(
                bwrap_archive,
                bwrap_path,
                matcher=lambda name: _binary_member_matches(
                    name,
                    install_name=platform_spec.bwrap_binary,
                    target_triple=platform_spec.target_triple,
                ),
            )
            _chmod_executable(bwrap_path)

        manifest = _bundle_manifest(
            runtime_root=runtime_root,
            bundle_root=staging_root,
            platform_spec=platform_spec,
            version_label=version_label,
            release_payload=release_payload,
            source_repo=source_repo,
            app_server_archive=app_server_archive,
            npm_platform_archive=npm_platform_archive,
            bwrap_archive=bwrap_archive,
            app_server_path=app_server_path,
            rg_path=rg_path,
            bwrap_path=bwrap_path,
        )
        (staging_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if bundle_root.exists():
            shutil.rmtree(bundle_root)
        staging_root.replace(bundle_root)
        update_root_manifest(
            runtime_root=runtime_root,
            platform_spec=platform_spec,
            version_label=version_label,
            bundle_manifest=manifest,
        )
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    return bundle_root


def copy_archive_member(
    archive_path: Path,
    target_path: Path,
    *,
    matcher: Callable[[str], bool],
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not matcher(member.name):
                    continue
                source = archive.extractfile(member)
                if source is None:
                    continue
                with source, target_path.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
                return
    elif zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not matcher(member.filename):
                    continue
                with archive.open(member) as source, target_path.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
                return
    elif matcher(archive_path.name):
        shutil.copy2(archive_path, target_path)
        return
    raise FileNotFoundError(f"matching runtime member not found in {archive_path}")


def _archive_name(value: str) -> str:
    return str(value or "").replace("\\", "/").strip("/")


def _binary_member_matches(name: str, *, install_name: str, target_triple: str) -> bool:
    member_name = Path(_archive_name(name)).name
    if member_name == install_name:
        return True
    suffix = ".exe" if install_name.endswith(".exe") else ""
    stem = install_name.removesuffix(suffix)
    return member_name == f"{stem}-{target_triple}{suffix}"


def _chmod_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
