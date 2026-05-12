from __future__ import annotations

from typing import Any, Callable


MEDIA_OUTPUT_ITEM_TYPES: frozenset[str] = frozenset(
    {"function_call_output", "custom_tool_call_output"}
)


def call_id_from_item(item: dict[str, Any]) -> str:
    return str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()


def legacy_image_subject_from_detail(
    value: Any,
    *,
    normalized_image_detail_fn: Callable[[Any], str],
) -> str:
    detail = str(value or "").strip()
    if not detail or normalized_image_detail_fn(detail):
        return ""
    lowered = detail.lower()
    if lowered.startswith("attachment:") or "/" in detail or "\\" in detail:
        return detail
    return ""


def media_artifact_payload_from_input_image(
    item: dict[str, Any],
    *,
    normalized_image_detail_fn: Callable[[Any], str],
    legacy_image_subject_from_detail_fn: Callable[[Any], str],
) -> dict[str, Any]:
    image_url = str(item.get("image_url") or item.get("imageUrl") or "").strip()
    detail = normalized_image_detail_fn(item.get("detail"))
    mime_type = ""
    if image_url.startswith("data:"):
        prefix = image_url[5:]
        mime_type = prefix.split(";", 1)[0].strip()
    return {
        "path": legacy_image_subject_from_detail_fn(item.get("detail")),
        "mime_type": mime_type,
        "size_bytes": 0,
        "width": 0,
        "height": 0,
        "image_url": image_url,
        "detail": detail,
    }


def artifact_payload_from_mapping(
    payload: dict[str, Any],
    *,
    normalized_image_detail_fn: Callable[[Any], str],
    legacy_image_subject_from_detail_fn: Callable[[Any], str],
) -> dict[str, Any]:
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    path = str(payload.get("path") or payload.get("requested_path") or "").strip()
    if not path:
        path = legacy_image_subject_from_detail_fn(payload.get("detail"))
    return {
        "path": path,
        "mime_type": str(payload.get("mime_type") or payload.get("mimeType") or "").strip(),
        "size_bytes": _safe_int(payload.get("size_bytes") or payload.get("sizeBytes")),
        "width": _safe_int(payload.get("width")),
        "height": _safe_int(payload.get("height")),
        "image_url": str(payload.get("image_url") or payload.get("imageUrl") or "").strip(),
        "detail": normalized_image_detail_fn(payload.get("detail")),
    }
