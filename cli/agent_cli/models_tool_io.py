from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, TYPE_CHECKING

from cli.agent_cli import models_tool_io_normalization_helpers_runtime as _models_tool_io_normalization_helpers_runtime
from cli.agent_cli import models_tool_io_projection_helpers_runtime as _models_tool_io_projection_helpers_runtime
from cli.agent_cli import models_tool_io_pure_helpers_runtime as _models_tool_io_pure_helpers_runtime

if TYPE_CHECKING:
    from cli.agent_cli.models import ToolEvent


@dataclass(frozen=True)
class ImageArtifact:
    path: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    image_url: str
    detail: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "path": str(self.path),
            "mime_type": str(self.mime_type),
            "size_bytes": int(self.size_bytes),
            "width": int(self.width),
            "height": int(self.height),
            "image_url": str(self.image_url),
        }
        if self.detail:
            payload["detail"] = str(self.detail)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ImageArtifact":
        item = dict(payload or {})
        return cls(
            path=str(item.get("path") or ""),
            mime_type=str(item.get("mime_type") or item.get("mimeType") or ""),
            size_bytes=_safe_int(item.get("size_bytes", item.get("sizeBytes"))),
            width=_safe_int(item.get("width")),
            height=_safe_int(item.get("height")),
            image_url=str(item.get("image_url") or item.get("imageUrl") or ""),
            detail=str(item.get("detail") or "") or None,
        )


@dataclass(frozen=True)
class LocalMediaSource:
    requested_path: str
    path: str
    mime_type: str
    media_kind: str
    size_bytes: int = 0
    source_mode: str = "tool_path"
    extension: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "requested_path": str(self.requested_path),
            "path": str(self.path),
            "mime_type": str(self.mime_type),
            "media_kind": str(self.media_kind),
            "size_bytes": int(self.size_bytes),
            "source_mode": str(self.source_mode or "tool_path"),
        }
        if self.extension:
            payload["extension"] = str(self.extension)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "LocalMediaSource":
        item = dict(payload or {})
        return cls(
            requested_path=str(item.get("requested_path") or item.get("requestedPath") or ""),
            path=str(item.get("path") or ""),
            mime_type=str(item.get("mime_type") or item.get("mimeType") or ""),
            media_kind=str(item.get("media_kind") or item.get("mediaKind") or ""),
            size_bytes=_safe_int(item.get("size_bytes", item.get("sizeBytes"))),
            source_mode=str(item.get("source_mode") or item.get("sourceMode") or "tool_path") or "tool_path",
            extension=str(item.get("extension") or ""),
        )


@dataclass(frozen=True)
class LocalMediaProbeResult:
    ok: bool
    source: LocalMediaSource | None = None
    error_code: str = ""
    display_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": bool(self.ok)}
        if self.source is not None:
            payload["source"] = self.source.to_dict()
        if not self.ok:
            payload["error_code"] = str(self.error_code or "media_probe_failed")
            payload["display_message"] = str(self.display_message or "Local media probe failed.")
        return payload

    @classmethod
    def success(cls, *, source: LocalMediaSource) -> "LocalMediaProbeResult":
        return cls(ok=True, source=source)

    @classmethod
    def failure(
        cls,
        *,
        error_code: str,
        display_message: str,
        source: LocalMediaSource | None = None,
    ) -> "LocalMediaProbeResult":
        return cls(
            ok=False,
            source=source,
            error_code=str(error_code or "media_probe_failed"),
            display_message=str(display_message or "Local media probe failed."),
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "LocalMediaProbeResult":
        item = dict(payload or {})
        raw_source = item.get("source")
        source = LocalMediaSource.from_dict(raw_source) if isinstance(raw_source, dict) else None
        return cls(
            ok=bool(item.get("ok")),
            source=source,
            error_code=str(item.get("error_code") or item.get("errorCode") or ""),
            display_message=str(item.get("display_message") or item.get("displayMessage") or ""),
        )


@dataclass(frozen=True)
class MediaIngestResult:
    ok: bool
    image_artifacts: tuple[ImageArtifact, ...] = field(default_factory=tuple)
    error_code: str = ""
    display_message: str = ""
    requested_path: str = ""
    path: str = ""
    detail: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"ok": bool(self.ok)}
        if self.ok:
            payload["image_artifacts"] = [artifact.to_dict() for artifact in self.image_artifacts]
        else:
            payload["error_code"] = str(self.error_code or "media_ingest_failed")
            payload["display_message"] = str(self.display_message or "Image ingest failed.")
        if self.requested_path:
            payload["requested_path"] = str(self.requested_path)
        if self.path:
            payload["path"] = str(self.path)
        if self.detail:
            payload["detail"] = str(self.detail)
        return payload

    @classmethod
    def success(
        cls,
        *,
        image_artifacts: List[ImageArtifact] | tuple[ImageArtifact, ...],
        requested_path: str = "",
        path: str = "",
        detail: str | None = None,
    ) -> "MediaIngestResult":
        return cls(
            ok=True,
            image_artifacts=tuple(image_artifacts or ()),
            requested_path=str(requested_path or ""),
            path=str(path or ""),
            detail=detail,
        )

    @classmethod
    def failure(
        cls,
        *,
        error_code: str,
        display_message: str,
        requested_path: str = "",
        path: str = "",
        detail: str | None = None,
    ) -> "MediaIngestResult":
        return cls(
            ok=False,
            error_code=str(error_code or "media_ingest_failed"),
            display_message=str(display_message or "Image ingest failed."),
            requested_path=str(requested_path or ""),
            path=str(path or ""),
            detail=detail,
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "MediaIngestResult":
        item = dict(payload or {})
        artifacts = tuple(
            ImageArtifact.from_dict(raw)
            for raw in list(item.get("image_artifacts") or [])
            if isinstance(raw, dict)
        )
        return cls(
            ok=bool(item.get("ok")),
            image_artifacts=artifacts,
            error_code=str(item.get("error_code") or ""),
            display_message=str(item.get("display_message") or ""),
            requested_path=str(item.get("requested_path") or ""),
            path=str(item.get("path") or ""),
            detail=str(item.get("detail") or "") or None,
        )


_safe_int = _models_tool_io_pure_helpers_runtime.safe_int
_shell_action_from_payload = _models_tool_io_pure_helpers_runtime.shell_action_from_payload
_compact_argument_map = _models_tool_io_pure_helpers_runtime.compact_argument_map
_first_change_path = _models_tool_io_pure_helpers_runtime.first_change_path

_normalized_tool_events = _models_tool_io_normalization_helpers_runtime.normalized_tool_events
_tool_event_call_id = _models_tool_io_normalization_helpers_runtime.tool_event_call_id
_tool_event_provider_item_type = _models_tool_io_normalization_helpers_runtime.tool_event_provider_item_type
_tool_event_provider_raw_item = _models_tool_io_normalization_helpers_runtime.tool_event_provider_raw_item
_derived_function_call_arguments_from_payload = (
    _models_tool_io_normalization_helpers_runtime.derived_function_call_arguments_from_payload
)
_effective_function_call_name = _models_tool_io_normalization_helpers_runtime.effective_function_call_name
_tool_event_function_call_arguments = _models_tool_io_normalization_helpers_runtime.tool_event_function_call_arguments
_normalized_web_search_turn_item_arguments = (
    _models_tool_io_normalization_helpers_runtime.normalized_web_search_turn_item_arguments
)

_normalized_provider_tool_input_item = _models_tool_io_projection_helpers_runtime.normalized_provider_tool_input_item
_shell_output_blocks_from_payload = _models_tool_io_projection_helpers_runtime.shell_output_blocks_from_payload
_normalized_provider_tool_output_item = _models_tool_io_projection_helpers_runtime.normalized_provider_tool_output_item
_function_call_input_items_from_tool_events_projection = (
    _models_tool_io_projection_helpers_runtime.function_call_input_items_from_tool_events_projection
)
_tool_output_input_items_from_tool_events_projection = (
    _models_tool_io_projection_helpers_runtime.tool_output_input_items_from_tool_events_projection
)


def function_call_input_items_from_tool_events(
    tool_events: List[ToolEvent] | List[Dict[str, Any]] | None,
) -> List[Dict[str, Any]]:
    return _function_call_input_items_from_tool_events_projection(tool_events)


def tool_output_input_items_from_tool_events(
    tool_events: List[ToolEvent] | List[Dict[str, Any]] | None,
) -> List[Dict[str, Any]]:
    return _tool_output_input_items_from_tool_events_projection(tool_events)
