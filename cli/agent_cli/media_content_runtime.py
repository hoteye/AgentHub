from __future__ import annotations

import json
from typing import Any, Callable

from cli.agent_cli.models_tool_io import MediaIngestResult

InputImageItemNormalizer = Callable[[dict[str, Any]], dict[str, Any] | None]
VALID_IMAGE_DETAILS = frozenset({"auto", "low", "high", "original"})


def jsonish_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[:1] not in {"{", "["}:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def normalized_image_detail(value: Any) -> str:
    detail = str(value or "").strip().lower()
    return detail if detail in VALID_IMAGE_DETAILS else ""


def _is_supported_input_image_url(value: Any) -> bool:
    image_url = str(value or "").strip()
    if not image_url:
        return False
    lowered = image_url.lower()
    if lowered.startswith("data:"):
        return lowered.startswith("data:image/")
    return lowered.startswith("http://") or lowered.startswith("https://")


def normalized_input_image_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    image_url = str(payload.get("image_url") or payload.get("imageUrl") or "").strip()
    if not _is_supported_input_image_url(image_url):
        return None
    item: dict[str, Any] = {
        "type": "input_image",
        "image_url": image_url,
    }
    detail = normalized_image_detail(payload.get("detail"))
    if detail:
        item["detail"] = detail
    return item


def input_image_item_from_image_block(payload: dict[str, Any]) -> dict[str, Any] | None:
    normalized = normalized_input_image_item(payload)
    if normalized is not None:
        return normalized
    source = payload.get("source")
    if not isinstance(source, dict):
        return None
    source_type = str(source.get("type") or "").strip().lower()
    detail = normalized_image_detail(payload.get("detail") or source.get("detail"))
    if source_type == "base64":
        data = str(source.get("data") or "").strip()
        if not data:
            return None
        media_type = str(
            source.get("media_type")
            or source.get("mime_type")
            or payload.get("media_type")
            or payload.get("mime_type")
            or "image/png"
        ).strip()
        if not media_type:
            media_type = "image/png"
        image_item = {"image_url": f"data:{media_type};base64,{data}"}
        if detail:
            image_item["detail"] = detail
        return normalized_input_image_item(image_item)
    if source_type in {"url", "image_url"}:
        image_url = str(source.get("url") or source.get("image_url") or "").strip()
        if image_url:
            image_item = {"image_url": image_url}
            if detail:
                image_item["detail"] = detail
            return normalized_input_image_item(image_item)
    if source_type == "data_url":
        image_url = str(source.get("data_url") or "").strip()
        if image_url:
            image_item = {"image_url": image_url}
            if detail:
                image_item["detail"] = detail
            return normalized_input_image_item(image_item)
    return None


def input_image_item_from_artifact(artifact: Any) -> dict[str, Any] | None:
    if isinstance(artifact, dict):
        return normalized_input_image_item(artifact)
    image_url = str(getattr(artifact, "image_url", "") or "").strip()
    detail = normalized_image_detail(getattr(artifact, "detail", ""))
    payload: dict[str, Any] = {
        "image_url": image_url,
    }
    if detail:
        payload["detail"] = detail
    return normalized_input_image_item(payload)


def media_ingest_result_from_output(output: Any) -> MediaIngestResult | None:
    parsed_output = jsonish_value(output)
    if isinstance(parsed_output, MediaIngestResult):
        return parsed_output
    if not isinstance(parsed_output, dict):
        return None
    if "ok" not in parsed_output and "image_artifacts" not in parsed_output:
        return None
    if "ok" not in parsed_output and isinstance(parsed_output.get("image_artifacts"), list):
        normalized = dict(parsed_output)
        normalized["ok"] = True
        parsed_output = normalized
    return MediaIngestResult.from_dict(parsed_output)


def normalize_image_content_items_from_list(
    items: list[Any],
    *,
    image_item_normalizer: InputImageItemNormalizer = normalized_input_image_item,
) -> list[dict[str, Any]] | None:
    normalized_items: list[dict[str, Any]] = []
    has_image = False
    for entry in items:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or entry.get("item_type") or "").strip().lower()
        if entry_type in {"input_text", "text", "output_text"}:
            text = str(entry.get("text") or "")
            if text:
                normalized_items.append({"type": "input_text", "text": text})
            continue
        if entry_type not in {"input_image", "image"}:
            continue
        normalized = image_item_normalizer(entry)
        if normalized is None:
            continue
        has_image = True
        normalized_items.append(normalized)
    return normalized_items if has_image else None


def nested_image_content_items(
    payload: dict[str, Any],
    *,
    image_item_normalizer: InputImageItemNormalizer = normalized_input_image_item,
) -> list[dict[str, Any]] | None:
    candidates: list[list[Any]] = []
    content = payload.get("content")
    if isinstance(content, list):
        candidates.append(content)
    for key in ("result", "tool_result", "structured_content"):
        nested = payload.get(key)
        if not isinstance(nested, dict):
            continue
        nested_content = nested.get("content")
        if isinstance(nested_content, list):
            candidates.append(nested_content)
    for candidate in candidates:
        normalized = normalize_image_content_items_from_list(
            candidate,
            image_item_normalizer=image_item_normalizer,
        )
        if normalized is not None:
            return normalized
    return None


def image_content_items_from_output(
    output: Any,
    *,
    image_item_normalizer: InputImageItemNormalizer = normalized_input_image_item,
) -> list[dict[str, Any]] | None:
    parsed_output = jsonish_value(output)
    if isinstance(parsed_output, list):
        return normalize_image_content_items_from_list(
            parsed_output,
            image_item_normalizer=image_item_normalizer,
        )
    if isinstance(parsed_output, dict):
        direct_image = image_item_normalizer(parsed_output)
        if direct_image is not None:
            return [direct_image]
        nested_content = nested_image_content_items(
            parsed_output,
            image_item_normalizer=image_item_normalizer,
        )
        if nested_content is not None:
            return nested_content
    media_result = media_ingest_result_from_output(parsed_output)
    if media_result is None or not media_result.ok or not media_result.image_artifacts:
        return None
    items: list[dict[str, Any]] = []
    for artifact in list(media_result.image_artifacts or ()):
        normalized = input_image_item_from_artifact(artifact)
        if normalized is not None:
            items.append(normalized)
    return items or None


def input_image_items_from_output(output: Any) -> list[dict[str, Any]]:
    parsed = jsonish_value(output)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type") or entry.get("item_type") or "").strip().lower() != "input_image":
            continue
        normalized = normalized_input_image_item(entry)
        if normalized is not None:
            items.append(normalized)
    return items


def output_contains_image_artifacts(output: Any) -> bool:
    parsed = jsonish_value(output)
    if isinstance(parsed, dict):
        artifacts = parsed.get("image_artifacts")
        return isinstance(artifacts, list) and bool(artifacts)
    return False
