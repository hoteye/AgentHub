from __future__ import annotations

import base64
import mimetypes
import re
import struct
from dataclasses import dataclass
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from pathlib import Path
from typing import Callable

from cli.agent_cli.media_file_types import SUPPORTED_IMAGE_MIME_BY_EXTENSION
from cli.agent_cli.models_tool_io import (
    ImageArtifact,
    LocalMediaProbeResult,
    LocalMediaSource,
    MediaIngestResult,
)

ReadBytesFn = Callable[[Path], bytes]
DEFAULT_MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
_SVG_FORBIDDEN_DECLARATIONS = ("<!doctype", "<!entity")


@dataclass(frozen=True)
class _ImageInspection:
    mime_type: str
    width: int
    height: int


def ingest_local_image(
    path: str,
    *,
    workspace_root: str | Path | None = None,
    detail: str | None = None,
    max_size_bytes: int = DEFAULT_MAX_IMAGE_SIZE_BYTES,
    read_bytes_fn: ReadBytesFn | None = None,
) -> MediaIngestResult:
    """Read a local image and return a provider-neutral media artifact contract."""
    probe_result = probe_local_media_path(path, workspace_root=workspace_root)
    source = probe_result.source
    if not probe_result.ok or source is None:
        return MediaIngestResult.failure(
            error_code=str(probe_result.error_code or "media_probe_failed"),
            display_message=str(probe_result.display_message or "Image path probe failed."),
            requested_path=str(path or "").strip(),
            path=str(getattr(source, "path", "") or ""),
            detail=detail,
        )

    resolved = Path(source.path)
    expected_mime = SUPPORTED_IMAGE_MIME_BY_EXTENSION.get(resolved.suffix.lower())
    if not expected_mime:
        return MediaIngestResult.failure(
            error_code="unsupported_image_type",
            display_message=f"Unsupported image extension: {resolved.suffix.lower() or '(none)'}.",
            requested_path=source.requested_path,
            path=source.path,
            detail=detail,
        )
    size_bytes = int(source.size_bytes)
    if max_size_bytes > 0 and size_bytes > max_size_bytes:
        return MediaIngestResult.failure(
            error_code="image_too_large",
            display_message=(
                f"Image file is too large: {resolved} "
                f"({size_bytes} bytes > {int(max_size_bytes)} bytes)."
            ),
            requested_path=source.requested_path,
            path=source.path,
            detail=detail,
        )

    try:
        data = read_bytes_fn(resolved) if read_bytes_fn is not None else resolved.read_bytes()
    except OSError as exc:
        return MediaIngestResult.failure(
            error_code="unreadable",
            display_message=f"Image file is not readable: {exc}",
            requested_path=source.requested_path,
            path=source.path,
            detail=detail,
        )

    inspection = inspect_image_bytes(data)
    if inspection is None:
        return MediaIngestResult.failure(
            error_code="invalid_image",
            display_message=f"Image file is not a valid supported image: {resolved}",
            requested_path=source.requested_path,
            path=source.path,
            detail=detail,
        )
    if inspection.mime_type != expected_mime:
        return MediaIngestResult.failure(
            error_code="unsupported_image_type",
            display_message=(
                "Image MIME does not match its extension: "
                f"expected {expected_mime}, detected {inspection.mime_type}."
            ),
            requested_path=source.requested_path,
            path=source.path,
            detail=detail,
        )

    artifact = ImageArtifact(
        path=source.path,
        mime_type=inspection.mime_type,
        size_bytes=size_bytes if size_bytes >= 0 else len(data),
        width=inspection.width,
        height=inspection.height,
        image_url=_data_url(inspection.mime_type, data),
        detail=detail,
    )
    return MediaIngestResult.success(
        image_artifacts=[artifact],
        requested_path=source.requested_path,
        path=source.path,
        detail=detail,
    )


def probe_local_media_path(
    path: str,
    *,
    workspace_root: str | Path | None = None,
) -> LocalMediaProbeResult:
    raw_path = str(path or "").strip()
    if not raw_path:
        return LocalMediaProbeResult.failure(
            error_code="invalid_path",
            display_message="Local media path is required.",
        )

    try:
        resolved = _resolve_local_path(raw_path, workspace_root=workspace_root)
    except (OSError, RuntimeError, ValueError) as exc:
        return LocalMediaProbeResult.failure(
            error_code="invalid_path",
            display_message=f"Invalid local media path: {exc}",
        )

    base_source = LocalMediaSource(
        requested_path=raw_path,
        path=str(resolved),
        mime_type=_guess_mime_type(resolved),
        media_kind=_shared_media_kind(resolved),
        extension=resolved.suffix.lower(),
    )

    try:
        if not resolved.exists():
            return LocalMediaProbeResult.failure(
                error_code="file_not_found",
                display_message=f"Local media file does not exist: {resolved}",
                source=base_source,
            )
        if not resolved.is_file():
            return LocalMediaProbeResult.failure(
                error_code="invalid_path",
                display_message=f"Local media path is not a file: {resolved}",
                source=base_source,
            )
        size_bytes = int(resolved.stat().st_size)
    except OSError as exc:
        return LocalMediaProbeResult.failure(
            error_code="unreadable",
            display_message=f"Local media file is not readable: {exc}",
            source=base_source,
        )

    return LocalMediaProbeResult.success(
        source=LocalMediaSource(
            requested_path=base_source.requested_path,
            path=base_source.path,
            mime_type=base_source.mime_type,
            media_kind=base_source.media_kind,
            size_bytes=size_bytes,
            source_mode=base_source.source_mode,
            extension=base_source.extension,
        )
    )


def inspect_image_bytes(data: bytes) -> _ImageInspection | None:
    if not data:
        return None
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            size = _png_size(data)
            return _inspection("image/png", size)
        if data.startswith((b"GIF87a", b"GIF89a")):
            size = _gif_size(data)
            return _inspection("image/gif", size)
        if data.startswith(b"\xff\xd8"):
            size = _jpeg_size(data)
            return _inspection("image/jpeg", size)
        if data.startswith(b"BM"):
            size = _bmp_size(data)
            return _inspection("image/bmp", size)
        if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
            size = _webp_size(data)
            return _inspection("image/webp", size)
        svg_size = _svg_size(data)
        if svg_size is not None:
            return _inspection("image/svg+xml", svg_size)
    except (struct.error, UnicodeDecodeError, ElementTree.ParseError, DefusedXmlException, ValueError, IndexError):
        return None
    return None


def _resolve_local_path(path: str, *, workspace_root: str | Path | None) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    root = Path(workspace_root).expanduser() if workspace_root is not None else Path.cwd()
    return (root / candidate).resolve(strict=False)


def _guess_mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return str(guessed or "application/octet-stream")


def _shared_media_kind(path: Path) -> str:
    # Probe-time coarse bucket used before any tool-specific extraction runs.
    suffix = path.suffix.lower()
    mime_type = _guess_mime_type(path).lower()
    if suffix in SUPPORTED_IMAGE_MIME_BY_EXTENSION or mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("text/"):
        return "document"
    if mime_type in {
        "application/json",
        "application/pdf",
        "application/x-ipynb+json",
        "application/xml",
    }:
        return "document"
    if suffix in {
        ".json",
        ".md",
        ".markdown",
        ".txt",
        ".rst",
        ".csv",
        ".tsv",
        ".yaml",
        ".yml",
        ".toml",
        ".pdf",
        ".ipynb",
    }:
        return "document"
    return "binary"


def _inspection(mime_type: str, size: tuple[int, int] | None) -> _ImageInspection | None:
    if size is None:
        return None
    width, height = size
    if width <= 0 or height <= 0:
        return None
    return _ImageInspection(mime_type=mime_type, width=int(width), height=int(height))


def _data_url(mime_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _gif_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10:
        return None
    return struct.unpack("<HH", data[6:10])


def _bmp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 26:
        return None
    width = struct.unpack("<i", data[18:22])[0]
    height = abs(struct.unpack("<i", data[22:26])[0])
    return width, height


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while index < len(data):
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return None
        marker = data[index]
        index += 1
        if marker in {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        if segment_length < 2 or index + segment_length > len(data):
            return None
        if marker in sof_markers:
            if segment_length < 7:
                return None
            height = struct.unpack(">H", data[index + 3 : index + 5])[0]
            width = struct.unpack(">H", data[index + 5 : index + 7])[0]
            return width, height
        index += segment_length
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    chunk_type = data[12:16]
    if chunk_type == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk_type == b"VP8L" and len(data) >= 25:
        b0, b1, b2, b3 = data[21:25]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return width, height
    if chunk_type == b"VP8 " and len(data) >= 30:
        start = 20
        if data[start + 3 : start + 6] != b"\x9d\x01\x2a":
            return None
        width = struct.unpack("<H", data[start + 6 : start + 8])[0] & 0x3FFF
        height = struct.unpack("<H", data[start + 8 : start + 10])[0] & 0x3FFF
        return width, height
    return None


def _svg_size(data: bytes) -> tuple[int, int] | None:
    text = data.decode("utf-8", errors="strict").strip()
    if not text:
        return None
    lowered = text.lower()
    if any(token in lowered for token in _SVG_FORBIDDEN_DECLARATIONS):
        raise ValueError("unsafe svg declaration")
    root = ElementTree.fromstring(text)
    if not str(root.tag).lower().endswith("svg"):
        return None
    width = _svg_length_to_int(root.attrib.get("width"))
    height = _svg_length_to_int(root.attrib.get("height"))
    if width and height:
        return width, height
    view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if view_box:
        values = [float(item) for item in re.split(r"[\s,]+", view_box.strip()) if item]
        if len(values) == 4:
            return int(round(values[2])), int(round(values[3]))
    return None


def _svg_length_to_int(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("%"):
        return None
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        return None
    return int(round(float(match.group(1))))
