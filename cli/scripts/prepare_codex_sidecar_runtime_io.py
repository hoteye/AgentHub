from __future__ import annotations

import json
import shutil
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from .prepare_codex_sidecar_runtime_manifest import sha256_digest
    from .prepare_codex_sidecar_runtime_models import (
        DEFAULT_DOWNLOAD_RETRIES,
        DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        DEFAULT_RUNTIME_VERSION,
        GITHUB_API_ROOT,
        USER_AGENT,
        ReleaseAsset,
    )
except ImportError:
    from prepare_codex_sidecar_runtime_manifest import sha256_digest
    from prepare_codex_sidecar_runtime_models import (
        DEFAULT_DOWNLOAD_RETRIES,
        DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        DEFAULT_RUNTIME_VERSION,
        GITHUB_API_ROOT,
        USER_AGENT,
        ReleaseAsset,
    )


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_release_payload(
    *,
    repo: str,
    tag: str,
    token: str = "",
    opener: Callable[[urllib.request.Request], Any] | None = None,
) -> dict[str, Any]:
    normalized_tag = str(tag or "").strip() or "latest"
    if normalized_tag == "latest":
        url = f"{GITHUB_API_ROOT}/{repo}/releases/latest"
    else:
        url = f"{GITHUB_API_ROOT}/{repo}/releases/tags/{normalized_tag}"
    payload = _read_json_url(url, token=token, opener=opener)
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid GitHub release payload for {repo}@{normalized_tag}")
    return payload


def default_download_dir(*, tag: str, platform_key: str) -> Path:
    label = _safe_path_label(tag or DEFAULT_RUNTIME_VERSION)
    return repo_root() / "artifacts" / "codex_sidecar_runtime" / "downloads" / label / platform_key


def download_asset(
    asset: ReleaseAsset,
    *,
    download_dir: Path,
    token: str = "",
    force: bool = False,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
    retries: int = DEFAULT_DOWNLOAD_RETRIES,
) -> ReleaseAsset:
    download_dir.mkdir(parents=True, exist_ok=True)
    target = download_dir / asset.name
    if target.exists() and not force:
        return ReleaseAsset(
            name=asset.name,
            url=str(target),
            size=target.stat().st_size,
            sha256=sha256_digest(target),
        )
    tmp = target.with_suffix(target.suffix + ".tmp")
    attempts = max(1, int(retries) + 1)
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        if tmp.exists():
            tmp.unlink()
        request = _request(asset.url, token=token)
        try:
            with (
                urllib.request.urlopen(request, timeout=timeout) as response,
                tmp.open("wb") as handle,
            ):
                shutil.copyfileobj(response, handle)
            tmp.replace(target)
            break
        except Exception as exc:
            last_error = exc
            if tmp.exists():
                tmp.unlink()
            if attempt >= attempts:
                raise RuntimeError(
                    f"failed downloading {asset.name} after {attempts} attempts: {exc}"
                ) from exc
            time.sleep(min(2.0 * attempt, 10.0))
    if not target.exists() and last_error is not None:
        raise RuntimeError(f"failed downloading {asset.name}: {last_error}") from last_error
    return ReleaseAsset(
        name=asset.name,
        url=str(target),
        size=target.stat().st_size,
        sha256=sha256_digest(target),
    )


def _read_json_url(
    url: str,
    *,
    token: str = "",
    opener: Callable[[urllib.request.Request], Any] | None = None,
) -> Any:
    request = _request(url, token=token)
    open_fn = opener or urllib.request.urlopen
    with open_fn(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _request(url: str, *, token: str = "") -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _safe_path_label(value: str) -> str:
    label = "".join(char if char.isalnum() or char in "._-" else "-" for char in value.strip())
    label = "-".join(part for part in label.split("-") if part)
    return label[:96] or DEFAULT_RUNTIME_VERSION
