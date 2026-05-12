from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

try:
    from .prepare_codex_sidecar_runtime_models import PlatformSpec, ReleaseAsset, SelectedAssets
except ImportError:
    from prepare_codex_sidecar_runtime_models import PlatformSpec, ReleaseAsset, SelectedAssets


def release_tag(payload: Mapping[str, Any]) -> str:
    return str(payload.get("tag_name") or "").strip()


def release_version(payload: Mapping[str, Any]) -> str:
    tag = release_tag(payload)
    tag_match = re.search(r"v(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)", tag)
    if tag_match:
        return tag_match.group(1)
    for raw_asset in payload.get("assets") or []:
        if not isinstance(raw_asset, Mapping):
            continue
        asset_name = str(raw_asset.get("name") or "")
        asset_match = re.fullmatch(
            r"codex-npm-(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\.tgz", asset_name
        )
        if asset_match:
            return asset_match.group(1)
    raise RuntimeError(f"cannot infer Codex version from release tag `{tag or '-'}`")


def select_assets(payload: Mapping[str, Any], spec: PlatformSpec) -> SelectedAssets:
    version = release_version(payload)
    app_asset_name = _app_server_asset_name(spec)
    npm_asset_name = f"codex-npm-{spec.npm_platform}-{version}.tgz"
    bwrap_asset_name = f"bwrap-{spec.target_triple}.tar.gz" if spec.is_linux else ""

    assets = _release_asset_map(payload)
    app_server = _require_asset(assets, app_asset_name)
    npm_platform = _require_asset(assets, npm_asset_name)
    bwrap = _require_asset(assets, bwrap_asset_name) if bwrap_asset_name else None
    return SelectedAssets(app_server=app_server, npm_platform=npm_platform, bwrap=bwrap)


def _release_asset_map(payload: Mapping[str, Any]) -> dict[str, ReleaseAsset]:
    result: dict[str, ReleaseAsset] = {}
    for raw in payload.get("assets") or []:
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("name") or "").strip()
        url = str(raw.get("browser_download_url") or "").strip()
        if not name or not url:
            continue
        try:
            size = int(raw.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        result[name] = ReleaseAsset(name=name, url=url, size=size)
    return result


def _require_asset(assets: Mapping[str, ReleaseAsset], name: str) -> ReleaseAsset:
    asset = assets.get(name)
    if asset is None:
        available = ", ".join(sorted(assets)[:20])
        raise RuntimeError(f"missing release asset `{name}`; available sample: {available}")
    return asset


def _app_server_asset_name(spec: PlatformSpec) -> str:
    suffix = ".exe" if spec.is_windows else ""
    return f"codex-app-server-{spec.target_triple}{suffix}.tar.gz"
