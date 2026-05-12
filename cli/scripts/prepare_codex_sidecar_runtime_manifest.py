from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from .prepare_codex_sidecar_runtime_assets import release_tag, release_version
    from .prepare_codex_sidecar_runtime_models import PlatformSpec
except ImportError:
    from prepare_codex_sidecar_runtime_assets import release_tag, release_version
    from prepare_codex_sidecar_runtime_models import PlatformSpec


def update_root_manifest(
    *,
    runtime_root: Path,
    platform_spec: PlatformSpec,
    version_label: str,
    bundle_manifest: Mapping[str, Any],
) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    manifest_path = runtime_root / "manifest.json"
    try:
        root_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        root_manifest = {}
    if not isinstance(root_manifest, dict):
        root_manifest = {}
    root_manifest.setdefault("name", "agenthub-codex-sidecar-runtimes")
    root_manifest["defaultVersion"] = version_label
    platforms = root_manifest.setdefault("platforms", {})
    if not isinstance(platforms, dict):
        platforms = {}
        root_manifest["platforms"] = platforms
    sha256 = str(bundle_manifest.get("sha256") or "")
    binary = platform_spec.app_server_binary
    platforms[platform_spec.platform_key] = {
        "defaultVersion": version_label,
        "binary": str((Path(platform_spec.platform_key) / version_label / binary).as_posix()),
        "manifest": str(
            (Path(platform_spec.platform_key) / version_label / "manifest.json").as_posix()
        ),
        "sha256": sha256,
    }
    manifest_path.write_text(
        json.dumps(root_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_manifest(
    *,
    runtime_root: Path,
    bundle_root: Path,
    platform_spec: PlatformSpec,
    version_label: str,
    release_payload: Mapping[str, Any],
    source_repo: str,
    app_server_archive: Path,
    npm_platform_archive: Path,
    bwrap_archive: Path | None,
    app_server_path: Path,
    rg_path: Path,
    bwrap_path: Path | None,
) -> dict[str, Any]:
    assets: dict[str, Any] = {
        "app_server_archive": _asset_manifest(app_server_archive),
        "npm_platform_archive": _asset_manifest(npm_platform_archive),
    }
    if bwrap_archive is not None:
        assets["bwrap_archive"] = _asset_manifest(bwrap_archive)
    resources: dict[str, str] = {
        "path": str((Path("path") / platform_spec.rg_binary).as_posix()),
    }
    if bwrap_path is not None:
        resources["bwrap"] = str((Path("codex-resources") / platform_spec.bwrap_binary).as_posix())
    return {
        "name": "codex-ref-sidecar",
        "source": "github-release",
        "sourceRepo": source_repo,
        "sourceTag": release_tag(release_payload),
        "version": version_label,
        "codexVersion": release_version(release_payload),
        "platform": platform_spec.platform_key,
        "target": platform_spec.target_triple,
        "binary": platform_spec.app_server_binary,
        "entrypoint": platform_spec.app_server_binary,
        "protocol": "app-server",
        "transport": ["stdio"],
        "args": ["--listen", "stdio://"],
        "pathEntries": ["path"],
        "resources": resources,
        "assets": assets,
        "sha256": sha256_digest(app_server_path),
        "files": {
            "appServer": str(app_server_path.relative_to(bundle_root).as_posix()),
            "rg": str(rg_path.relative_to(bundle_root).as_posix()),
            **(
                {"bwrap": str(bwrap_path.relative_to(bundle_root).as_posix())}
                if bwrap_path is not None
                else {}
            ),
        },
        "builtAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _asset_manifest(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_digest(path),
    }
