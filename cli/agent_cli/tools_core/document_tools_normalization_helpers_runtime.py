from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(slots=True, frozen=True)
class ViewImageRequest:
    requested_path: str
    resolved_path: Path


def normalized_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(values or {})


def prepare_view_image_request(
    *,
    path: str,
    workspace_root: Path,
) -> ViewImageRequest:
    requested_path = str(path or "").strip()
    candidate = Path(requested_path).expanduser()
    resolved_path = candidate.resolve() if candidate.is_absolute() else (workspace_root / candidate).resolve()
    return ViewImageRequest(
        requested_path=requested_path,
        resolved_path=resolved_path,
    )


__all__ = [
    "ViewImageRequest",
    "normalized_mapping",
    "prepare_view_image_request",
]
