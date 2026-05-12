from __future__ import annotations

import argparse
import json
import os

try:
    from scripts.publish_gui_desktop_release_core import (
        ArtifactPlan,
        PublishError,
        build_artifact_plan,
        build_asset_url,
        build_release_manifest_payload,
        build_upload_url,
        default_artifact_dir,
        discover_artifacts,
        join_remote_path,
        manifest_bytes,
        normalize_release_version,
        quote_remote_path,
        release_manifest_paths,
        release_summary_text,
        render_sha256_file,
        repo_root,
        resolve_artifact_paths,
        sha256_digest,
        split_archive_name,
        stable_artifact_name,
        versioned_release_prefix,
    )
    from scripts.publish_gui_desktop_release_network import (
        next_nonce,
        ssl_context,
        upload_bytes,
        upload_file,
        upload_release_artifacts,
        upload_release_manifest,
        verify_url,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from publish_gui_desktop_release_core import (  # type: ignore[no-redef]
        ArtifactPlan,
        PublishError,
        build_artifact_plan,
        build_asset_url,
        build_release_manifest_payload,
        build_upload_url,
        default_artifact_dir,
        discover_artifacts,
        join_remote_path,
        manifest_bytes,
        normalize_release_version,
        quote_remote_path,
        release_manifest_paths,
        release_summary_text,
        render_sha256_file,
        repo_root,
        resolve_artifact_paths,
        sha256_digest,
        split_archive_name,
        stable_artifact_name,
        versioned_release_prefix,
    )
    from publish_gui_desktop_release_network import (  # type: ignore[no-redef]
        next_nonce,
        ssl_context,
        upload_bytes,
        upload_file,
        upload_release_artifacts,
        upload_release_manifest,
        verify_url,
    )


DEFAULT_ROOT_PREFIX = "downloads"
DEFAULT_VERSIONED_SUBDIR = "gui"
DEFAULT_UPLOAD_TOKEN_ENV = "AGENTHUB_GUI_PUBLISH_BEARER_TOKEN"
DEFAULT_UPLOAD_BASE_URL = os.environ.get("AGENTHUB_GUI_PUBLISH_UPLOAD_BASE_URL", "https://dl.pressget.cn:8443")
DEFAULT_SOURCE_BASE_URL = os.environ.get("AGENTHUB_GUI_PUBLISH_SOURCE_BASE_URL", DEFAULT_UPLOAD_BASE_URL)
DEFAULT_PUBLIC_BASE_URL = os.environ.get("AGENTHUB_GUI_PUBLIC_BASE_URL", "https://pressget.cn")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish locally built AgentHub GUI desktop bundles to the dl.pressget.cn source node.",
    )
    parser.add_argument(
        "--version",
        default=os.environ.get("AGENTHUB_GUI_RELEASE_VERSION", ""),
        help="Release version. Accepts `1.2.3`, `v1.2.3`, or `gui-v1.2.3`.",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Built archive to publish. May be passed multiple times.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="",
        help="Directory to scan when `--artifact` is omitted. Defaults to `artifacts/gui-desktop-releases/`.",
    )
    parser.add_argument("--root-prefix", default=DEFAULT_ROOT_PREFIX, help="Remote root prefix on the download node.")
    parser.add_argument(
        "--versioned-subdir",
        default=DEFAULT_VERSIONED_SUBDIR,
        help="Subdirectory used for versioned release snapshots.",
    )
    parser.add_argument("--upload-base-url", default=DEFAULT_UPLOAD_BASE_URL, help="Upload API base URL.")
    parser.add_argument(
        "--source-base-url",
        default=DEFAULT_SOURCE_BASE_URL,
        help="Direct source-node download base URL used for verification.",
    )
    parser.add_argument(
        "--public-base-url",
        default=DEFAULT_PUBLIC_BASE_URL,
        help="Public proxy base URL used for end-user verification.",
    )
    parser.add_argument(
        "--token-env",
        default=DEFAULT_UPLOAD_TOKEN_ENV,
        help="Environment variable name that contains the upload bearer token.",
    )
    parser.add_argument(
        "--nonce",
        default="",
        help="Optional fixed nonce. If omitted, a random nonce is generated per upload.",
    )
    parser.add_argument(
        "--manifest-name",
        default="release-manifest.json",
        help="Remote manifest filename stored under the versioned and latest manifest paths.",
    )
    parser.add_argument(
        "--skip-stable-alias",
        action="store_true",
        help="Do not upload stable top-level aliases such as `downloads/agenthub-gui-desktop-linux-x86_64.tar.gz`.",
    )
    parser.add_argument("--skip-source-verify", action="store_true", help="Skip verification against the source node.")
    parser.add_argument("--skip-public-verify", action="store_true", help="Skip verification against the public proxy.")
    parser.add_argument(
        "--verify-source-tls",
        action="store_true",
        help="Verify source-node TLS certificates. Disabled by default because the source node is self-signed.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    normalized_version = normalize_release_version(args.version)
    if not normalized_version:
        raise PublishError("Missing release version. Pass `--version` or set `AGENTHUB_GUI_RELEASE_VERSION`.")

    token = str(os.environ.get(args.token_env, "")).strip()
    if not token:
        raise PublishError(
            f"Missing upload token. Set `{args.token_env}` in the local shell or an ignored `.secrets/*.env` file."
        )

    artifact_paths = resolve_artifact_paths(args)
    if not artifact_paths:
        raise PublishError("No publish artifacts were found. Build locally first or pass explicit `--artifact` paths.")

    artifact_plans = [
        build_artifact_plan(
            local_path=path,
            version=normalized_version,
            root_prefix=args.root_prefix,
            versioned_subdir=args.versioned_subdir,
            include_stable_alias=not args.skip_stable_alias,
        )
        for path in artifact_paths
    ]

    upload_release_artifacts(
        artifact_plans=artifact_plans,
        upload_base_url=args.upload_base_url,
        source_base_url=args.source_base_url,
        public_base_url=args.public_base_url,
        token=token,
        timeout_seconds=args.timeout_seconds,
        verify_source_tls=args.verify_source_tls,
        verify_source=not args.skip_source_verify,
        verify_public=not args.skip_public_verify,
        nonce_seed=args.nonce,
    )

    payload = build_release_manifest_payload(
        version=normalized_version,
        artifact_plans=artifact_plans,
        root_prefix=args.root_prefix,
        versioned_subdir=args.versioned_subdir,
        source_base_url=args.source_base_url,
        public_base_url=args.public_base_url,
        manifest_name=args.manifest_name,
    )
    upload_release_manifest(
        payload=payload,
        upload_base_url=args.upload_base_url,
        source_base_url=args.source_base_url,
        public_base_url=args.public_base_url,
        token=token,
        timeout_seconds=args.timeout_seconds,
        verify_source_tls=args.verify_source_tls,
        verify_source=not args.skip_source_verify,
        verify_public=not args.skip_public_verify,
        nonce_seed=args.nonce,
        root_prefix=args.root_prefix,
        versioned_subdir=args.versioned_subdir,
        version=normalized_version,
        manifest_name=args.manifest_name,
    )

    print(release_summary_text(payload))
    print()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
