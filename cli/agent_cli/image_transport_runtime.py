from __future__ import annotations

from typing import Any, Mapping, Sequence

from cli.agent_cli.media_content_runtime import normalized_image_detail


IMAGE_TRANSPORT_DEDICATED_TOOL_NATIVE = "dedicated_tool_native_view_image"
IMAGE_TRANSPORT_IMAGE_AWARE_FILE_READ = "image_aware_file_read"
IMAGE_TRANSPORT_ATTACHMENT_FIRST = "attachment_first_message_native"
IMAGE_TRANSPORT_TOOL_NATIVE = "tool_native_image_continuation"

VALID_IMAGE_TRANSPORT_FAMILIES = frozenset(
    {
        IMAGE_TRANSPORT_DEDICATED_TOOL_NATIVE,
        IMAGE_TRANSPORT_IMAGE_AWARE_FILE_READ,
        IMAGE_TRANSPORT_ATTACHMENT_FIRST,
        IMAGE_TRANSPORT_TOOL_NATIVE,
    }
)

IMAGE_TRANSPORT_FAMILY_TO_STATE = {
    IMAGE_TRANSPORT_DEDICATED_TOOL_NATIVE: "image_injected_tool_native",
    IMAGE_TRANSPORT_IMAGE_AWARE_FILE_READ: "image_injected_file_read",
    IMAGE_TRANSPORT_ATTACHMENT_FIRST: "image_injected_attachment",
    IMAGE_TRANSPORT_TOOL_NATIVE: "image_injected_tool_native",
}

IMAGE_AWARE_FILE_READ_TOOLS = frozenset({"read_file", "file_read", "file_search"})
ATTACHMENT_FIRST_IMAGE_TOOLS = frozenset({"user_image_input", "image_input"})


def _legacy_image_subject_from_detail(value: Any) -> str:
    detail = str(value or "").strip()
    if not detail or normalized_image_detail(detail):
        return ""
    lowered = detail.lower()
    if lowered.startswith("attachment:") or "/" in detail or "\\" in detail:
        return detail
    return ""


def normalize_image_transport_family(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in VALID_IMAGE_TRANSPORT_FAMILIES else ""


def image_transport_family_for_tool(
    *,
    tool_name: str,
    payload: Mapping[str, Any] | None = None,
    tool_surface_profile: str = "",
) -> str:
    del tool_surface_profile
    payload_map = dict(payload or {})
    explicit = normalize_image_transport_family(
        payload_map.get("image_transport_family")
        or payload_map.get("image_projection_family")
        or payload_map.get("image_projection_mode")
        or payload_map.get("projection_family")
        or payload_map.get("projection_mode")
        or ""
    )
    if explicit:
        return explicit
    normalized_tool_name = str(tool_name or payload_map.get("tool_name") or "").strip().lower()
    if normalized_tool_name == "view_image":
        return IMAGE_TRANSPORT_DEDICATED_TOOL_NATIVE
    if normalized_tool_name in IMAGE_AWARE_FILE_READ_TOOLS:
        return IMAGE_TRANSPORT_IMAGE_AWARE_FILE_READ
    if normalized_tool_name in ATTACHMENT_FIRST_IMAGE_TOOLS:
        return IMAGE_TRANSPORT_ATTACHMENT_FIRST
    return IMAGE_TRANSPORT_TOOL_NATIVE


def image_transport_family_from_output_item(
    item: Mapping[str, Any],
    images: Sequence[Mapping[str, Any]],
) -> str:
    explicit = normalize_image_transport_family(item.get("image_transport_family"))
    if explicit:
        return explicit
    call_id = str(item.get("call_id") or "").strip().lower()
    if "view_image" in call_id:
        return IMAGE_TRANSPORT_DEDICATED_TOOL_NATIVE
    subject = str(item.get("image_transport_subject") or "").strip().lower()
    if subject.startswith("attachment:"):
        return IMAGE_TRANSPORT_ATTACHMENT_FIRST
    for image in list(images or []):
        detail_subject = _legacy_image_subject_from_detail(image.get("detail")).lower()
        if detail_subject.startswith("attachment:"):
            return IMAGE_TRANSPORT_ATTACHMENT_FIRST
    return IMAGE_TRANSPORT_TOOL_NATIVE


def image_transport_subject(
    *,
    payload: Mapping[str, Any],
    output_items: Sequence[Mapping[str, Any]],
) -> str:
    for key in ("requested_path", "path", "file_path", "name"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    for entry in list(output_items or []):
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("type") or "").strip().lower() != "input_image":
            continue
        detail_subject = _legacy_image_subject_from_detail(entry.get("detail"))
        if detail_subject:
            return detail_subject
    return ""
