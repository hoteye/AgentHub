from __future__ import annotations

import json
import secrets
import ssl
from pathlib import Path
from urllib import error, request

try:
    from scripts.publish_gui_desktop_release_core import (
        ArtifactPlan,
        PublishError,
        build_asset_url,
        build_upload_url,
        manifest_bytes,
        release_manifest_paths,
        render_sha256_file,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from publish_gui_desktop_release_core import (  # type: ignore[no-redef]
        ArtifactPlan,
        PublishError,
        build_asset_url,
        build_upload_url,
        manifest_bytes,
        release_manifest_paths,
        render_sha256_file,
    )


def ssl_context(*, verify_tls: bool) -> ssl.SSLContext | None:
    if verify_tls:
        return None
    return ssl._create_unverified_context()


def upload_bytes(
    *,
    data: bytes,
    remote_path: str,
    upload_base_url: str,
    token: str,
    nonce: str,
    timeout_seconds: float,
    verify_tls: bool,
) -> dict[str, object]:
    url = build_upload_url(upload_base_url, remote_path, nonce)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(len(data)),
    }
    req = request.Request(url, data=data, headers=headers, method="PUT")
    try:
        with request.urlopen(req, timeout=timeout_seconds, context=ssl_context(verify_tls=verify_tls)) as response:
            payload = response.read()
            status_code = int(getattr(response, "status", 0))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise PublishError(f"Upload failed for {remote_path}: HTTP {exc.code} {body}") from exc
    except error.URLError as exc:
        raise PublishError(f"Upload failed for {remote_path}: {exc}") from exc
    if not 200 <= status_code < 300:
        raise PublishError(f"Upload failed for {remote_path}: HTTP {status_code}")
    if not payload:
        return {}
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return {"raw": payload.decode("utf-8", errors="replace")}


def upload_file(
    *,
    local_path: Path,
    remote_path: str,
    upload_base_url: str,
    token: str,
    nonce: str,
    timeout_seconds: float,
    verify_tls: bool,
) -> dict[str, object]:
    return upload_bytes(
        data=local_path.read_bytes(),
        remote_path=remote_path,
        upload_base_url=upload_base_url,
        token=token,
        nonce=nonce,
        timeout_seconds=timeout_seconds,
        verify_tls=verify_tls,
    )


def verify_url(
    *,
    url: str,
    expected_size: int | None,
    timeout_seconds: float,
    verify_tls: bool,
) -> None:
    for method in ("HEAD", "GET"):
        req = request.Request(url, method=method)
        if method == "GET":
            req.add_header("Range", "bytes=0-0")
        try:
            with request.urlopen(req, timeout=timeout_seconds, context=ssl_context(verify_tls=verify_tls)) as response:
                length_header = response.headers.get("Content-Length")
                if expected_size is not None and length_header:
                    actual_size = int(length_header)
                    if actual_size != expected_size:
                        raise PublishError(
                            f"Verification size mismatch for {url}: expected {expected_size}, got {actual_size}"
                        )
                return
        except error.HTTPError as exc:
            if method == "HEAD" and exc.code in {400, 403, 405, 501}:
                continue
            body = exc.read().decode("utf-8", errors="replace")
            raise PublishError(f"Verification failed for {url}: HTTP {exc.code} {body}") from exc
        except error.URLError as exc:
            raise PublishError(f"Verification failed for {url}: {exc}") from exc
    raise PublishError(f"Verification failed for {url}: unsupported method sequence.")


def next_nonce(seed: str | None = None) -> str:
    text = str(seed or "").strip()
    if text:
        return text
    return secrets.token_hex(8)


def upload_release_artifacts(
    *,
    artifact_plans: list[ArtifactPlan],
    upload_base_url: str,
    source_base_url: str,
    public_base_url: str,
    token: str,
    timeout_seconds: float,
    verify_source_tls: bool,
    verify_source: bool,
    verify_public: bool,
    nonce_seed: str,
) -> None:
    for plan in artifact_plans:
        upload_file(
            local_path=plan.local_path,
            remote_path=plan.versioned_remote_path,
            upload_base_url=upload_base_url,
            token=token,
            nonce=next_nonce(nonce_seed),
            timeout_seconds=timeout_seconds,
            verify_tls=verify_source_tls,
        )
        upload_bytes(
            data=render_sha256_file(digest=plan.sha256, filename=plan.archive_name),
            remote_path=plan.versioned_checksum_path,
            upload_base_url=upload_base_url,
            token=token,
            nonce=next_nonce(nonce_seed),
            timeout_seconds=timeout_seconds,
            verify_tls=verify_source_tls,
        )
        if plan.stable_remote_path and plan.stable_checksum_path and plan.stable_name:
            upload_file(
                local_path=plan.local_path,
                remote_path=plan.stable_remote_path,
                upload_base_url=upload_base_url,
                token=token,
                nonce=next_nonce(nonce_seed),
                timeout_seconds=timeout_seconds,
                verify_tls=verify_source_tls,
            )
            upload_bytes(
                data=render_sha256_file(digest=plan.sha256, filename=plan.stable_name),
                remote_path=plan.stable_checksum_path,
                upload_base_url=upload_base_url,
                token=token,
                nonce=next_nonce(nonce_seed),
                timeout_seconds=timeout_seconds,
                verify_tls=verify_source_tls,
            )
        if verify_source:
            verify_url(
                url=build_asset_url(source_base_url, plan.versioned_remote_path),
                expected_size=plan.size_bytes,
                timeout_seconds=timeout_seconds,
                verify_tls=verify_source_tls,
            )
            verify_url(
                url=build_asset_url(source_base_url, plan.versioned_checksum_path),
                expected_size=len(render_sha256_file(digest=plan.sha256, filename=plan.archive_name)),
                timeout_seconds=timeout_seconds,
                verify_tls=verify_source_tls,
            )
            if plan.stable_remote_path and plan.stable_checksum_path and plan.stable_name:
                verify_url(
                    url=build_asset_url(source_base_url, plan.stable_remote_path),
                    expected_size=plan.size_bytes,
                    timeout_seconds=timeout_seconds,
                    verify_tls=verify_source_tls,
                )
                verify_url(
                    url=build_asset_url(source_base_url, plan.stable_checksum_path),
                    expected_size=len(render_sha256_file(digest=plan.sha256, filename=plan.stable_name)),
                    timeout_seconds=timeout_seconds,
                    verify_tls=verify_source_tls,
                )
        if verify_public:
            verify_url(
                url=build_asset_url(public_base_url, plan.versioned_remote_path),
                expected_size=plan.size_bytes,
                timeout_seconds=timeout_seconds,
                verify_tls=True,
            )
            verify_url(
                url=build_asset_url(public_base_url, plan.versioned_checksum_path),
                expected_size=len(render_sha256_file(digest=plan.sha256, filename=plan.archive_name)),
                timeout_seconds=timeout_seconds,
                verify_tls=True,
            )
            if plan.stable_remote_path and plan.stable_checksum_path and plan.stable_name:
                verify_url(
                    url=build_asset_url(public_base_url, plan.stable_remote_path),
                    expected_size=plan.size_bytes,
                    timeout_seconds=timeout_seconds,
                    verify_tls=True,
                )
                verify_url(
                    url=build_asset_url(public_base_url, plan.stable_checksum_path),
                    expected_size=len(render_sha256_file(digest=plan.sha256, filename=plan.stable_name)),
                    timeout_seconds=timeout_seconds,
                    verify_tls=True,
                )


def upload_release_manifest(
    *,
    payload: dict[str, object],
    upload_base_url: str,
    source_base_url: str,
    public_base_url: str,
    token: str,
    timeout_seconds: float,
    verify_source_tls: bool,
    verify_source: bool,
    verify_public: bool,
    nonce_seed: str,
    root_prefix: str,
    versioned_subdir: str,
    version: str,
    manifest_name: str,
) -> None:
    versioned_manifest_path, latest_manifest_path = release_manifest_paths(
        root_prefix=root_prefix,
        versioned_subdir=versioned_subdir,
        version=version,
        manifest_name=manifest_name,
    )
    payload_bytes = manifest_bytes(payload)
    for remote_path in (versioned_manifest_path, latest_manifest_path):
        upload_bytes(
            data=payload_bytes,
            remote_path=remote_path,
            upload_base_url=upload_base_url,
            token=token,
            nonce=next_nonce(nonce_seed),
            timeout_seconds=timeout_seconds,
            verify_tls=verify_source_tls,
        )
        if verify_source:
            verify_url(
                url=build_asset_url(source_base_url, remote_path),
                expected_size=len(payload_bytes),
                timeout_seconds=timeout_seconds,
                verify_tls=verify_source_tls,
            )
        if verify_public:
            verify_url(
                url=build_asset_url(public_base_url, remote_path),
                expected_size=len(payload_bytes),
                timeout_seconds=timeout_seconds,
                verify_tls=True,
            )
