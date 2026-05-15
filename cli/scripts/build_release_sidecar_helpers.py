from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import build_release_packaging_helpers as packaging_helpers


def bundle_codex_sidecar_runtime(
    packaged_root: Path,
    *,
    codex_sidecar_bin: str | Path,
    runtime_version: str = "",
    source_revision: str = "",
    platform_key: str | None = None,
    codex_platform_key_func: Callable[[], str],
    probe_codex_version_func: Callable[[Path], str],
    normalized_runtime_version_func: Callable[..., str],
    codex_binary_name_func: Callable[[str], str],
    sha256_digest_func: Callable[[Path], str],
) -> Path | None:
    return packaging_helpers.bundle_codex_sidecar_runtime(
        packaged_root,
        codex_sidecar_bin=codex_sidecar_bin,
        runtime_version=runtime_version,
        source_revision=source_revision,
        platform_key=platform_key,
        codex_platform_key_func=codex_platform_key_func,
        probe_codex_version_func=probe_codex_version_func,
        normalized_runtime_version_func=normalized_runtime_version_func,
        codex_binary_name_func=codex_binary_name_func,
        sha256_digest_func=sha256_digest_func,
    )


def bundle_codex_sidecar_runtime_root(
    packaged_root: Path,
    *,
    runtime_root: str | Path,
    runtime_version: str = "",
    platform_key: str | None = None,
    codex_platform_key_func: Callable[[], str],
    codex_binary_name_func: Callable[[str], str],
    sha256_digest_func: Callable[[Path], str],
) -> Path | None:
    return packaging_helpers.bundle_codex_sidecar_runtime_root(
        packaged_root,
        runtime_root=runtime_root,
        runtime_version=runtime_version,
        platform_key=platform_key,
        codex_platform_key_func=codex_platform_key_func,
        codex_binary_name_func=codex_binary_name_func,
        sha256_digest_func=sha256_digest_func,
    )


def bundle_codex_sidecar_runtime_bundle(
    packaged_root: Path,
    *,
    runtime_bundle: str | Path,
    runtime_version: str = "",
    platform_key: str | None = None,
    codex_platform_key_func: Callable[[], str],
    codex_binary_name_func: Callable[[str], str],
    sha256_digest_func: Callable[[Path], str],
) -> Path | None:
    return packaging_helpers.bundle_codex_sidecar_runtime_bundle(
        packaged_root,
        runtime_bundle=runtime_bundle,
        runtime_version=runtime_version,
        platform_key=platform_key,
        codex_platform_key_func=codex_platform_key_func,
        codex_binary_name_func=codex_binary_name_func,
        sha256_digest_func=sha256_digest_func,
    )


def _runtime_root_manifest(runtime_root: Path) -> dict[str, object]:
    return packaging_helpers._runtime_root_manifest(runtime_root)


def bundle_requested_codex_sidecar_runtime(
    packaged_root: Path,
    *,
    codex_sidecar_bin: str | Path,
    codex_sidecar_runtime_bundle: str | Path,
    codex_sidecar_runtime_root: str | Path,
    runtime_version: str,
    source_revision: str,
    has_arg_value_func: Callable[[object], bool],
    bundle_codex_sidecar_runtime_func: Callable[..., Path | None],
    bundle_codex_sidecar_runtime_bundle_func: Callable[..., Path | None],
    bundle_codex_sidecar_runtime_root_func: Callable[..., Path | None],
) -> bool:
    if has_arg_value_func(codex_sidecar_bin):
        bundle_codex_sidecar_runtime_func(
            packaged_root,
            codex_sidecar_bin=codex_sidecar_bin,
            runtime_version=runtime_version,
            source_revision=source_revision,
        )
        return True
    if has_arg_value_func(codex_sidecar_runtime_bundle):
        bundle_codex_sidecar_runtime_bundle_func(
            packaged_root,
            runtime_bundle=codex_sidecar_runtime_bundle,
            runtime_version=runtime_version,
        )
        return True
    if has_arg_value_func(codex_sidecar_runtime_root):
        bundle_codex_sidecar_runtime_root_func(
            packaged_root,
            runtime_root=codex_sidecar_runtime_root,
            runtime_version=runtime_version,
        )
        return True
    return False
