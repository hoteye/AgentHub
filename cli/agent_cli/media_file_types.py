from __future__ import annotations

from pathlib import Path, PureWindowsPath


SUPPORTED_IMAGE_MIME_BY_EXTENSION: dict[str, str] = {
    ".apng": "image/png",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def normalized_path_suffix(path_text: str | Path) -> str:
    raw_path = str(path_text or "").strip()
    if not raw_path:
        return ""
    display_path = PureWindowsPath(raw_path) if "\\" in raw_path else Path(raw_path)
    return display_path.suffix.lower()


def is_supported_image_path_candidate(path_text: str | Path) -> bool:
    return normalized_path_suffix(path_text) in SUPPORTED_IMAGE_MIME_BY_EXTENSION
