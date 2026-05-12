from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib import parse


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactPlan:
    local_path: Path
    archive_name: str
    stable_name: str | None
    size_bytes: int
    sha256: str
    versioned_remote_path: str
    versioned_checksum_path: str
    stable_remote_path: str | None
    stable_checksum_path: str | None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_release_version(value: str | None) -> str:
    text = str(value or "").strip()
    if text.startswith("gui-v"):
        return text[len("gui-v") :]
    if text.startswith("v"):
        return text[1:]
    return text


def join_remote_path(*parts: str) -> str:
    values = [str(part).strip("/") for part in parts if str(part or "").strip("/")]
    return "/".join(values)


def split_archive_name(filename: str) -> tuple[str, str]:
    if filename.endswith(".tar.gz"):
        return filename[: -len(".tar.gz")], ".tar.gz"
    if filename.endswith(".zip"):
        return filename[: -len(".zip")], ".zip"
    raise ValueError(f"Unsupported archive suffix for publish target: {filename}")


def stable_artifact_name(archive_name: str, version: str) -> str:
    normalized_version = normalize_release_version(version)
    if not normalized_version:
        raise ValueError("Release version is required when deriving stable artifact names.")
    base_name, suffix = split_archive_name(archive_name)
    version_token = f"-{normalized_version}-"
    if version_token not in base_name:
        raise ValueError(
            f"Archive name does not contain the normalized version token `{version_token}`: {archive_name}"
        )
    return f"{base_name.replace(version_token, '-', 1)}{suffix}"


def sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_sha256_file(*, digest: str, filename: str) -> bytes:
    return f"{digest}  {filename}\n".encode("utf-8")


def default_artifact_dir() -> Path:
    return (repo_root() / "artifacts" / "gui-desktop-releases").resolve()


def discover_artifacts(artifact_dir: Path, version: str) -> list[Path]:
    normalized_version = normalize_release_version(version)
    if not normalized_version:
        raise PublishError("Release version is required when discovering artifacts from a directory.")
    if not artifact_dir.exists():
        raise PublishError(f"Artifact directory does not exist: {artifact_dir}")
    matches: dict[str, Path] = {}
    for pattern in (f"*{normalized_version}*.tar.gz", f"*{normalized_version}*.zip"):
        for path in artifact_dir.glob(pattern):
            if path.is_file() and not path.name.endswith(".sha256"):
                matches[path.name] = path.resolve()
    return [matches[name] for name in sorted(matches)]


def resolve_artifact_paths(args) -> list[Path]:
    explicit_paths = [Path(item).expanduser().resolve() for item in args.artifact if str(item).strip()]
    if explicit_paths:
        return explicit_paths
    artifact_dir = (
        Path(args.artifact_dir).expanduser().resolve()
        if str(args.artifact_dir).strip()
        else default_artifact_dir()
    )
    return discover_artifacts(artifact_dir, args.version)


def versioned_release_prefix(*, root_prefix: str, versioned_subdir: str, version: str) -> str:
    normalized_version = normalize_release_version(version)
    if not normalized_version:
        raise PublishError("Release version is required for versioned publish paths.")
    return join_remote_path(root_prefix, versioned_subdir, f"v{normalized_version}")


def build_artifact_plan(
    *,
    local_path: Path,
    version: str,
    root_prefix: str,
    versioned_subdir: str,
    include_stable_alias: bool,
) -> ArtifactPlan:
    resolved_path = local_path.expanduser().resolve()
    if not resolved_path.exists() or not resolved_path.is_file():
        raise PublishError(f"Publish artifact not found: {resolved_path}")
    archive_name = resolved_path.name
    stable_name = stable_artifact_name(archive_name, version) if include_stable_alias else None
    version_prefix = versioned_release_prefix(
        root_prefix=root_prefix,
        versioned_subdir=versioned_subdir,
        version=version,
    )
    versioned_remote_path = join_remote_path(version_prefix, archive_name)
    stable_remote_path = join_remote_path(root_prefix, stable_name) if stable_name else None
    return ArtifactPlan(
        local_path=resolved_path,
        archive_name=archive_name,
        stable_name=stable_name,
        size_bytes=resolved_path.stat().st_size,
        sha256=sha256_digest(resolved_path),
        versioned_remote_path=versioned_remote_path,
        versioned_checksum_path=f"{versioned_remote_path}.sha256",
        stable_remote_path=stable_remote_path,
        stable_checksum_path=f"{stable_remote_path}.sha256" if stable_remote_path else None,
    )


def quote_remote_path(remote_path: str) -> str:
    return parse.quote(str(remote_path).lstrip("/"), safe="/._-")


def build_asset_url(base_url: str, remote_path: str) -> str:
    parts = parse.urlsplit(base_url.rstrip("/"))
    base_path = parts.path.rstrip("/")
    full_path = f"{base_path}/{quote_remote_path(remote_path)}" if base_path else f"/{quote_remote_path(remote_path)}"
    return parse.urlunsplit((parts.scheme, parts.netloc, full_path, "", ""))


def build_upload_url(base_url: str, remote_path: str, nonce: str) -> str:
    parts = parse.urlsplit(base_url.rstrip("/"))
    base_path = parts.path.rstrip("/")
    upload_path = (
        f"{base_path}/upload/{quote_remote_path(remote_path)}"
        if base_path
        else f"/upload/{quote_remote_path(remote_path)}"
    )
    query = parse.urlencode({"nonce": nonce})
    return parse.urlunsplit((parts.scheme, parts.netloc, upload_path, query, ""))


def release_manifest_paths(
    *,
    root_prefix: str,
    versioned_subdir: str,
    version: str,
    manifest_name: str,
) -> tuple[str, str]:
    normalized_version = normalize_release_version(version)
    if not normalized_version:
        raise PublishError("Release version is required for release manifest paths.")
    versioned_path = join_remote_path(root_prefix, versioned_subdir, f"v{normalized_version}", manifest_name)
    latest_path = join_remote_path(root_prefix, versioned_subdir, "latest", manifest_name)
    return versioned_path, latest_path


def build_release_manifest_payload(
    *,
    version: str,
    artifact_plans: list[ArtifactPlan],
    root_prefix: str,
    versioned_subdir: str,
    source_base_url: str,
    public_base_url: str,
    manifest_name: str,
) -> dict[str, object]:
    versioned_manifest_path, latest_manifest_path = release_manifest_paths(
        root_prefix=root_prefix,
        versioned_subdir=versioned_subdir,
        version=version,
        manifest_name=manifest_name,
    )
    return {
        "distribution_kind": "gui_desktop_download_distribution",
        "version": normalize_release_version(version),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "root_prefix": str(root_prefix).strip("/"),
        "versioned_subdir": str(versioned_subdir).strip("/"),
        "release_manifest": {
            "versioned_path": versioned_manifest_path,
            "versioned_source_url": build_asset_url(source_base_url, versioned_manifest_path),
            "versioned_public_url": build_asset_url(public_base_url, versioned_manifest_path),
            "latest_path": latest_manifest_path,
            "latest_source_url": build_asset_url(source_base_url, latest_manifest_path),
            "latest_public_url": build_asset_url(public_base_url, latest_manifest_path),
        },
        "artifacts": [
            {
                "archive_name": plan.archive_name,
                "stable_name": plan.stable_name,
                "size_bytes": plan.size_bytes,
                "sha256": plan.sha256,
                "versioned": {
                    "artifact_path": plan.versioned_remote_path,
                    "artifact_source_url": build_asset_url(source_base_url, plan.versioned_remote_path),
                    "artifact_public_url": build_asset_url(public_base_url, plan.versioned_remote_path),
                    "checksum_path": plan.versioned_checksum_path,
                    "checksum_source_url": build_asset_url(source_base_url, plan.versioned_checksum_path),
                    "checksum_public_url": build_asset_url(public_base_url, plan.versioned_checksum_path),
                },
                "stable": (
                    {
                        "artifact_path": plan.stable_remote_path,
                        "artifact_source_url": build_asset_url(source_base_url, plan.stable_remote_path or ""),
                        "artifact_public_url": build_asset_url(public_base_url, plan.stable_remote_path or ""),
                        "checksum_path": plan.stable_checksum_path,
                        "checksum_source_url": build_asset_url(source_base_url, plan.stable_checksum_path or ""),
                        "checksum_public_url": build_asset_url(public_base_url, plan.stable_checksum_path or ""),
                    }
                    if plan.stable_remote_path and plan.stable_checksum_path
                    else None
                ),
            }
            for plan in artifact_plans
        ],
    }


def manifest_bytes(payload: dict[str, object]) -> bytes:
    return f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n".encode("utf-8")


def release_summary_text(payload: dict[str, object]) -> str:
    lines = [
        f"Published AgentHub GUI desktop release {payload['version']}",
        f"Manifest: {payload['release_manifest']['versioned_public_url']}",
        f"Latest manifest: {payload['release_manifest']['latest_public_url']}",
    ]
    for artifact in payload["artifacts"]:
        lines.append(f"- {artifact['archive_name']}")
        lines.append(f"  versioned: {artifact['versioned']['artifact_public_url']}")
        if artifact["stable"]:
            lines.append(f"  stable: {artifact['stable']['artifact_public_url']}")
    return "\n".join(lines)
