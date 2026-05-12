from __future__ import annotations

# ruff: noqa: E402,F401,I001

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import time
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from prepare_codex_sidecar_runtime_assets import (
    _app_server_asset_name,
    _release_asset_map,
    _require_asset,
    release_tag,
    release_version,
    select_assets,
)
from prepare_codex_sidecar_runtime_install import (
    _archive_name,
    _binary_member_matches,
    _chmod_executable,
    copy_archive_member,
    install_runtime_bundle,
)
from prepare_codex_sidecar_runtime_io import (
    _read_json_url,
    _request,
    _safe_path_label,
    default_download_dir,
    download_asset,
    load_release_payload,
    repo_root,
)
from prepare_codex_sidecar_runtime_manifest import (
    _asset_manifest,
    _bundle_manifest,
    sha256_digest,
    update_root_manifest,
)
from prepare_codex_sidecar_runtime_models import (
    DEFAULT_DOWNLOAD_RETRIES,
    DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
    DEFAULT_GITHUB_REPO,
    DEFAULT_RUNTIME_VERSION,
    GITHUB_API_ROOT,
    PLATFORM_SPECS,
    USER_AGENT,
    PlatformSpec,
    ReleaseAsset,
    SelectedAssets,
)


def current_platform_key() -> str:
    system = platform.system().strip().lower()
    machine = platform.machine().strip().lower()
    arch_aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
    }
    arch = arch_aliases.get(machine, machine or "unknown")
    if system == "darwin":
        return f"macos-{arch if arch != 'aarch64' else 'arm64'}"
    if system == "windows":
        return f"windows-{arch}"
    return f"linux-{arch}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare an AgentHub Codex sidecar runtime bundle from official "
            "OpenAI Codex GitHub release artifacts."
        )
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_GITHUB_REPO,
        help="GitHub repository in owner/name form. Defaults to openai/codex.",
    )
    parser.add_argument(
        "--tag",
        default="latest",
        help="GitHub release tag, such as rust-v0.129.0. Use latest by default.",
    )
    parser.add_argument(
        "--platform-key",
        default=current_platform_key(),
        choices=tuple(sorted(PLATFORM_SPECS)),
        help="AgentHub runtime platform key.",
    )
    parser.add_argument(
        "--runtime-root",
        default=str(repo_root() / "runtime" / "codex"),
        help="Runtime root where platform/version bundles are installed.",
    )
    parser.add_argument(
        "--runtime-version",
        default="",
        help="Runtime bundle version label. Defaults to the release tag.",
    )
    parser.add_argument(
        "--download-dir",
        default="",
        help="Directory used to cache downloaded release assets.",
    )
    parser.add_argument(
        "--github-token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing an optional GitHub token.",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing runtime bundle.")
    parser.add_argument(
        "--force-downloads",
        action="store_true",
        help="Re-download release assets even when cached files already exist.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the plan without downloading."
    )
    parser.add_argument("--print-json", action="store_true", help="Print result as JSON.")
    parser.add_argument(
        "--download-timeout",
        type=float,
        default=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        help="Per-asset download timeout in seconds.",
    )
    parser.add_argument(
        "--download-retries",
        type=int,
        default=DEFAULT_DOWNLOAD_RETRIES,
        help="Number of retries after an asset download failure.",
    )
    return parser.parse_args(argv)


def build_plan(
    *,
    release_payload: Mapping[str, Any],
    platform_spec: PlatformSpec,
    runtime_root: Path,
    runtime_version: str,
    download_dir: Path,
) -> dict[str, Any]:
    assets = select_assets(release_payload, platform_spec)
    version_label = _safe_path_label(runtime_version or release_tag(release_payload))
    return {
        "tag": release_tag(release_payload),
        "codex_version": release_version(release_payload),
        "platform_key": platform_spec.platform_key,
        "target": platform_spec.target_triple,
        "runtime_root": str(runtime_root),
        "bundle_root": str(runtime_root / platform_spec.platform_key / version_label),
        "download_dir": str(download_dir),
        "assets": {
            "app_server": assets.app_server.name,
            "npm_platform": assets.npm_platform.name,
            "bwrap": assets.bwrap.name if assets.bwrap else None,
        },
    }


def prepare_runtime(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get(str(args.github_token_env or "")) or ""
    platform_spec = PLATFORM_SPECS[str(args.platform_key)]
    release_payload = load_release_payload(repo=str(args.repo), tag=str(args.tag), token=token)
    tag = release_tag(release_payload)
    runtime_root = Path(args.runtime_root).expanduser().resolve()
    download_dir = (
        Path(args.download_dir).expanduser().resolve()
        if str(args.download_dir or "").strip()
        else default_download_dir(tag=tag, platform_key=platform_spec.platform_key)
    )
    runtime_version = str(args.runtime_version or "").strip() or tag
    plan = build_plan(
        release_payload=release_payload,
        platform_spec=platform_spec,
        runtime_root=runtime_root,
        runtime_version=runtime_version,
        download_dir=download_dir,
    )
    if args.dry_run:
        return {"ok": True, "dry_run": True, **plan}

    selected = select_assets(release_payload, platform_spec)
    app_server_asset = download_asset(
        selected.app_server,
        download_dir=download_dir,
        token=token,
        force=bool(args.force_downloads),
        timeout=float(args.download_timeout),
        retries=int(args.download_retries),
    )
    npm_platform_asset = download_asset(
        selected.npm_platform,
        download_dir=download_dir,
        token=token,
        force=bool(args.force_downloads),
        timeout=float(args.download_timeout),
        retries=int(args.download_retries),
    )
    bwrap_asset = (
        download_asset(
            selected.bwrap,
            download_dir=download_dir,
            token=token,
            force=bool(args.force_downloads),
            timeout=float(args.download_timeout),
            retries=int(args.download_retries),
        )
        if selected.bwrap is not None
        else None
    )
    bundle_root = install_runtime_bundle(
        runtime_root=runtime_root,
        platform_spec=platform_spec,
        runtime_version=runtime_version,
        release_payload=release_payload,
        source_repo=str(args.repo),
        app_server_archive=Path(app_server_asset.url),
        npm_platform_archive=Path(npm_platform_asset.url),
        bwrap_archive=Path(bwrap_asset.url) if bwrap_asset is not None else None,
        force=bool(args.force),
    )
    return {
        "ok": True,
        **plan,
        "bundle_root": str(bundle_root),
        "manifest": str(bundle_root / "manifest.json"),
        "root_manifest": str(runtime_root / "manifest.json"),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = prepare_runtime(args)
    except Exception as exc:
        if getattr(args, "print_json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.print_json or args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"bundle_root={result['bundle_root']}")
        print(f"manifest={result['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
