from __future__ import annotations

import struct
from pathlib import Path

import pytest

from cli.agent_cli.models_tool_io import (
    ImageArtifact,
    LocalMediaProbeResult,
    LocalMediaSource,
    MediaIngestResult,
)
from cli.agent_cli.tools_core.media_ingest_runtime import (
    DEFAULT_MAX_IMAGE_SIZE_BYTES,
    ingest_local_image,
    inspect_image_bytes,
    probe_local_media_path,
)


def _png_bytes(*, width: int = 2, height: int = 3) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _gif_bytes(*, width: int = 5, height: int = 7) -> bytes:
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00"


def test_ingest_local_image_returns_required_image_artifact_contract(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(_png_bytes(width=11, height=13))

    result = ingest_local_image("sample.png", workspace_root=tmp_path, detail="low")

    assert result.ok is True
    assert result.error_code == ""
    assert len(result.image_artifacts) == 1
    artifact = result.image_artifacts[0]
    assert artifact.path == str(image_path.resolve())
    assert artifact.mime_type == "image/png"
    assert artifact.size_bytes == image_path.stat().st_size
    assert artifact.width == 11
    assert artifact.height == 13
    assert artifact.detail == "low"
    assert artifact.image_url.startswith("data:image/png;base64,")

    wire = result.to_dict()
    assert wire["ok"] is True
    assert set(wire["image_artifacts"][0]) == {
        "path",
        "mime_type",
        "size_bytes",
        "width",
        "height",
        "image_url",
        "detail",
    }


def test_media_ingest_result_roundtrip_preserves_success_contract() -> None:
    artifact = ImageArtifact(
        path="/tmp/a.png",
        mime_type="image/png",
        size_bytes=12,
        width=1,
        height=2,
        image_url="data:image/png;base64,AAA",
        detail="high",
    )

    result = MediaIngestResult.from_dict(
        MediaIngestResult.success(
            image_artifacts=[artifact],
            requested_path="a.png",
            path="/tmp/a.png",
            detail="high",
        ).to_dict()
    )

    assert result.ok is True
    assert result.requested_path == "a.png"
    assert result.path == "/tmp/a.png"
    assert result.image_artifacts == (artifact,)


def test_probe_local_media_path_returns_shared_transport_agnostic_source_for_text_document(tmp_path: Path) -> None:
    doc_path = tmp_path / "notes.md"
    doc_path.write_text("# Notes\nalpha", encoding="utf-8")

    result = probe_local_media_path("notes.md", workspace_root=tmp_path)

    assert result.ok is True
    assert result.source is not None
    assert result.source.requested_path == "notes.md"
    assert result.source.path == str(doc_path.resolve())
    assert result.source.source_mode == "tool_path"
    assert result.source.extension == ".md"
    assert result.source.mime_type == "text/markdown"
    assert result.source.media_kind == "document"
    assert result.source.size_bytes == doc_path.stat().st_size


def test_local_media_probe_roundtrip_preserves_source_contract() -> None:
    source = LocalMediaSource(
        requested_path="notes.md",
        path="/tmp/notes.md",
        mime_type="text/markdown",
        media_kind="document",
        size_bytes=42,
        extension=".md",
    )

    result = LocalMediaProbeResult.from_dict(LocalMediaProbeResult.success(source=source).to_dict())

    assert result.ok is True
    assert result.source == source


@pytest.mark.parametrize(
    ("path", "expected_code"),
    [
        ("", "invalid_path"),
        ("missing.png", "file_not_found"),
    ],
)
def test_ingest_local_image_reports_path_failures(tmp_path: Path, path: str, expected_code: str) -> None:
    result = ingest_local_image(path, workspace_root=tmp_path)

    assert result.ok is False
    assert result.error_code == expected_code
    failure = result.to_dict()
    assert failure["error_code"] == expected_code
    assert failure["display_message"]


def test_ingest_local_image_rejects_unsupported_extension(tmp_path: Path) -> None:
    text_path = tmp_path / "sample.txt"
    text_path.write_bytes(_png_bytes())

    result = ingest_local_image("sample.txt", workspace_root=tmp_path)

    assert result.ok is False
    assert result.error_code == "unsupported_image_type"
    assert "Unsupported image extension" in result.display_message


def test_ingest_local_image_rejects_mime_extension_mismatch(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(_gif_bytes())

    result = ingest_local_image("sample.png", workspace_root=tmp_path)

    assert result.ok is False
    assert result.error_code == "unsupported_image_type"
    assert "detected image/gif" in result.display_message


def test_ingest_local_image_reports_unreadable_file(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(_png_bytes())

    def denied(_: Path) -> bytes:
        raise PermissionError("permission denied")

    result = ingest_local_image("sample.png", workspace_root=tmp_path, read_bytes_fn=denied)

    assert result.ok is False
    assert result.error_code == "unreadable"
    assert "permission denied" in result.display_message


def test_ingest_local_image_reports_invalid_image_bytes(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"not an image")

    result = ingest_local_image("sample.png", workspace_root=tmp_path)

    assert result.ok is False
    assert result.error_code == "invalid_image"
    assert result.image_artifacts == ()


def test_ingest_local_image_rejects_images_over_size_limit(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(_png_bytes() + b"x" * 32)

    result = ingest_local_image("sample.png", workspace_root=tmp_path, max_size_bytes=16)

    assert DEFAULT_MAX_IMAGE_SIZE_BYTES > 16
    assert result.ok is False
    assert result.error_code == "image_too_large"
    assert "too large" in result.display_message


def test_inspect_image_bytes_accepts_svg_viewbox() -> None:
    inspection = inspect_image_bytes(b'<svg viewBox="0 0 32 24" xmlns="http://www.w3.org/2000/svg"></svg>')

    assert inspection is not None
    assert inspection.mime_type == "image/svg+xml"
    assert inspection.width == 32
    assert inspection.height == 24


def test_inspect_image_bytes_rejects_svg_doctype_payloads() -> None:
    inspection = inspect_image_bytes(
        b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg width="8" height="6"></svg>'
    )

    assert inspection is None
