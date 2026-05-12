from __future__ import annotations

from typing import Any, Dict, List


def input_item_text(item: Dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = str(block.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def looks_like_message_item(item: Dict[str, Any]) -> bool:
    item_type = str(item.get("type") or item.get("item_type") or "").strip()
    if item_type == "message":
        return True
    return bool("role" in item and "content" in item and not item_type)


def prelude_sections_from_item(
    item: Dict[str, Any],
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> List[str]:
    item_type = str(item.get("type") or "").strip()
    role = str(item.get("role") or "").strip().lower()
    if item_type == "reference_context_item":
        nested = item.get("item")
        if isinstance(nested, dict) and str(nested.get("item_type") or "").strip() == "workspace_context":
            return ["workspace_context"]
        return []
    if not looks_like_message_item(item):
        return []
    if role == "developer":
        return ["developer"]
    if role != "user":
        return []
    text = input_item_text(item)
    offsets: List[tuple[int, str]] = []
    workspace_offset = workspace_context_marker_offset_fn(text)
    if workspace_offset is not None:
        offsets.append((workspace_offset, "workspace_context"))
    environment_offset = environment_context_marker_offset_fn(text)
    if environment_offset is not None:
        offsets.append((environment_offset, "environment_context"))
    return [name for _, name in sorted(offsets, key=lambda entry: entry[0])]


def is_plain_user_message(
    item: Dict[str, Any],
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> bool:
    return (
        looks_like_message_item(item)
        and str(item.get("role") or "").strip().lower() == "user"
        and not prelude_sections_from_item(
            item,
            workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
            environment_context_marker_offset_fn=environment_context_marker_offset_fn,
        )
    )


def build_ordered_request_prelude_items(
    *,
    developer_item: Dict[str, Any] | None,
    environment_items: List[Dict[str, Any]] | None = None,
    workspace_reference_items: List[Dict[str, Any]] | None = None,
    workspace_message_items: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if isinstance(developer_item, dict) and developer_item:
        items.append(dict(developer_item))
    reference_items = [
        {"type": "reference_context_item", "item": dict(item)}
        for item in list(workspace_reference_items or [])
        if isinstance(item, dict) and item
    ]
    if reference_items:
        items.extend(reference_items)
    else:
        items.extend(
            dict(item)
            for item in list(workspace_message_items or [])
            if isinstance(item, dict) and item
        )
    items.extend(
        dict(item)
        for item in list(environment_items or [])
        if isinstance(item, dict) and item
    )
    return items


def request_prelude_contract(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> Dict[str, Any]:
    normalized_items = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    descriptors: List[Dict[str, Any]] = []
    section_order: List[str] = []
    for item in normalized_items:
        sections = prelude_sections_from_item(
            item,
            workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
            environment_context_marker_offset_fn=environment_context_marker_offset_fn,
        )
        section_order.extend(sections)
        nested = item.get("item")
        descriptors.append(
            {
                "type": str(item.get("type") or "").strip(),
                "role": str(item.get("role") or "").strip(),
                "item_type": str(nested.get("item_type") or "").strip() if isinstance(nested, dict) else "",
                "sections": list(sections),
            }
        )
    return {
        "item_count": len(normalized_items),
        "section_order": section_order,
        "items": descriptors,
    }


def extract_current_turn_prelude_items(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> List[Dict[str, Any]]:
    normalized_items = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    if not normalized_items:
        return []
    last_item = normalized_items[-1]
    if not is_plain_user_message(
        last_item,
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    ):
        return []
    prelude: List[Dict[str, Any]] = []
    index = len(normalized_items) - 2
    while index >= 0:
        item = normalized_items[index]
        if not prelude_sections_from_item(
            item,
            workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
            environment_context_marker_offset_fn=environment_context_marker_offset_fn,
        ):
            break
        prelude.append(item)
        index -= 1
    prelude.reverse()
    return prelude


def extract_current_turn_prelude_contract(
    items: List[Dict[str, Any]] | None,
    *,
    workspace_context_marker_offset_fn,
    environment_context_marker_offset_fn,
) -> Dict[str, Any]:
    return request_prelude_contract(
        extract_current_turn_prelude_items(
            items,
            workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
            environment_context_marker_offset_fn=environment_context_marker_offset_fn,
        ),
        workspace_context_marker_offset_fn=workspace_context_marker_offset_fn,
        environment_context_marker_offset_fn=environment_context_marker_offset_fn,
    )
