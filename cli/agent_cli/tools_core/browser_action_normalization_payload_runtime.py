from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.tools_core import browser_action_normalization_shared_runtime
from cli.agent_cli.tools_core import browser_action_normalization_payload_helpers_runtime


def normalize_browser_snapshot_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    requested_ref: str | None,
    browser_text_fn,
    browser_preview_text_fn,
    resolve_browser_target_fn,
) -> Dict[str, Any]:
    normalized = dict(payload)
    refs = payload.get("refs")
    ref_entries = refs if isinstance(refs, list) else []
    target_id = resolve_browser_target_fn(
        payload,
        client=client,
        action="snapshot",
        profile=profile,
        requested_target=requested_target,
    )
    if target_id:
        normalized["target_id"] = target_id
    url = browser_text_fn(normalized.get("url")) or browser_text_fn(requested_url)
    if url:
        normalized["url"] = url
    if profile and not browser_text_fn(normalized.get("profile")):
        normalized["profile"] = profile
    if requested_ref and not browser_text_fn(normalized.get("ref")):
        normalized["ref"] = requested_ref
    if not browser_text_fn(normalized.get("ref")) and ref_entries:
        first_ref = ref_entries[0]
        if isinstance(first_ref, dict):
            ref_value = browser_text_fn(first_ref.get("ref"))
            if ref_value:
                normalized["ref"] = ref_value
    normalized["ref_count"] = len(ref_entries)
    normalized["element_count"] = len(ref_entries)
    preview = browser_preview_text_fn(normalized.get("preview") or normalized.get("text"))
    if preview:
        normalized["preview"] = preview
    return normalized


def normalize_browser_console_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    browser_text_fn,
    normalize_browser_console_level_fn,
    resolve_browser_target_fn,
) -> Dict[str, Any]:
    normalized = dict(payload)
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raw_entries = payload.get("messages")
    source_entries = raw_entries if isinstance(raw_entries, list) else []
    entries: List[Dict[str, Any]] = []
    level_counts: Dict[str, int] = {}
    for item in source_entries:
        if not isinstance(item, dict):
            continue
        level = normalize_browser_console_level_fn(item.get("level") or item.get("type"))
        message = browser_text_fn(item.get("message") or item.get("text"))
        entry: Dict[str, Any] = {"level": level, "message": message}
        timestamp = item.get("timestamp")
        if timestamp is not None:
            entry["timestamp"] = timestamp
        location = item.get("location")
        if isinstance(location, dict) and location:
            entry["location"] = dict(location)
        entries.append(entry)
        level_counts[level] = level_counts.get(level, 0) + 1
    normalized.pop("messages", None)
    normalized["entries"] = entries
    normalized["count"] = len(entries)
    if entries:
        normalized.setdefault("level", entries[0]["level"])
        normalized.setdefault("message", entries[0]["message"])
    if level_counts:
        normalized["levels"] = level_counts
    target_id = resolve_browser_target_fn(
        payload,
        client=client,
        action="console",
        profile=profile,
        requested_target=requested_target,
    )
    if target_id:
        normalized["target_id"] = target_id
    if not browser_text_fn(normalized.get("url")):
        location_url = ""
        if entries:
            first_location = entries[0].get("location")
            if isinstance(first_location, dict):
                location_url = browser_text_fn(first_location.get("url"))
        normalized["url"] = location_url or browser_text_fn(requested_url)
    return normalized


def normalize_browser_requests_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    browser_text_fn,
    resolve_browser_target_fn,
) -> Dict[str, Any]:
    return browser_action_normalization_payload_helpers_runtime.normalize_browser_requests_payload(
        payload,
        client=client,
        profile=profile,
        requested_target=requested_target,
        requested_url=requested_url,
        browser_text_fn=browser_text_fn,
        resolve_browser_target_fn=resolve_browser_target_fn,
    )


def normalize_browser_artifact_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    action: str,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    requested_ref: str | None,
    browser_text_fn,
    resolve_browser_target_fn,
) -> Dict[str, Any]:
    return browser_action_normalization_payload_helpers_runtime.normalize_browser_artifact_payload(
        payload,
        client=client,
        action=action,
        profile=profile,
        requested_target=requested_target,
        requested_url=requested_url,
        requested_ref=requested_ref,
        browser_text_fn=browser_text_fn,
        resolve_browser_target_fn=resolve_browser_target_fn,
    )


def normalize_browser_act_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    requested_ref: str | None,
    requested_start_ref: str | None,
    requested_end_ref: str | None,
    requested_kind: str | None,
    requested_width: int | None,
    requested_height: int | None,
    requested_values: list[str] | None,
    requested_fields: list[dict[str, Any]] | None,
    browser_text_fn,
    normalize_browser_act_kind_fn,
    resolve_browser_target_fn,
) -> Dict[str, Any]:
    normalized = dict(payload)
    kind = (
        normalize_browser_act_kind_fn(normalized.get("kind"))
        or normalize_browser_act_kind_fn(requested_kind)
        or "act"
    )
    normalized["operation"] = "act"
    normalized["action"] = kind
    target_id = resolve_browser_target_fn(
        payload,
        client=client,
        action="act",
        profile=profile,
        requested_target=requested_target,
    )
    if target_id:
        normalized["target_id"] = target_id
    url = browser_text_fn(normalized.get("url")) or browser_text_fn(requested_url)
    if url:
        normalized["url"] = url
    if profile and not browser_text_fn(normalized.get("profile")):
        normalized["profile"] = profile
    if requested_ref and not browser_text_fn(normalized.get("ref")):
        normalized["ref"] = requested_ref
    if requested_start_ref and not browser_text_fn(normalized.get("start_ref")):
        normalized["start_ref"] = requested_start_ref
    if requested_end_ref and not browser_text_fn(normalized.get("end_ref")):
        normalized["end_ref"] = requested_end_ref
    if requested_width is not None and normalized.get("width") is None:
        normalized["width"] = int(requested_width)
    if requested_height is not None and normalized.get("height") is None:
        normalized["height"] = int(requested_height)
    if requested_values and normalized.get("count") is None and kind in {"select"}:
        normalized["count"] = len(requested_values)
    if requested_fields and normalized.get("count") is None and kind in {"fill"}:
        normalized["count"] = len(requested_fields)
    return normalized


def normalize_browser_payload(
    payload: Dict[str, Any],
    *,
    client: Any,
    action: str,
    profile: str | None,
    requested_target: str | None,
    requested_url: str | None,
    requested_ref: str | None,
    requested_start_ref: str | None = None,
    requested_end_ref: str | None = None,
    requested_kind: str | None = None,
    requested_width: int | None = None,
    requested_height: int | None = None,
    requested_values: list[str] | None = None,
    requested_fields: list[dict[str, Any]] | None = None,
    requested_paths: list[str] | None = None,
    requested_input_ref: str | None = None,
    requested_accept: bool | None = None,
    requested_prompt_text: str | None = None,
    browser_text_fn=None,
    browser_preview_text_fn=None,
    normalize_browser_act_kind_fn=None,
    normalize_browser_console_level_fn=None,
    resolve_browser_target_fn=None,
) -> Dict[str, Any]:
    normalized = dict(payload)
    normalized["action"] = action
    if action == "act":
        return normalize_browser_act_payload(
            normalized,
            client=client,
            profile=profile,
            requested_target=requested_target,
            requested_url=requested_url,
            requested_ref=requested_ref,
            requested_start_ref=requested_start_ref,
            requested_end_ref=requested_end_ref,
            requested_kind=requested_kind,
            requested_width=requested_width,
            requested_height=requested_height,
            requested_values=requested_values,
            requested_fields=requested_fields,
            browser_text_fn=browser_text_fn,
            normalize_browser_act_kind_fn=normalize_browser_act_kind_fn,
            resolve_browser_target_fn=resolve_browser_target_fn,
        )
    if action == "snapshot":
        return normalize_browser_snapshot_payload(
            normalized,
            client=client,
            profile=profile,
            requested_target=requested_target,
            requested_url=requested_url,
            requested_ref=requested_ref,
            browser_text_fn=browser_text_fn,
            browser_preview_text_fn=browser_preview_text_fn,
            resolve_browser_target_fn=resolve_browser_target_fn,
        )
    if action in {"console", "errors"}:
        return normalize_browser_console_payload(
            normalized,
            client=client,
            profile=profile,
            requested_target=requested_target,
            requested_url=requested_url,
            browser_text_fn=browser_text_fn,
            normalize_browser_console_level_fn=normalize_browser_console_level_fn,
            resolve_browser_target_fn=resolve_browser_target_fn,
        )
    if action == "requests":
        return normalize_browser_requests_payload(
            normalized,
            client=client,
            profile=profile,
            requested_target=requested_target,
            requested_url=requested_url,
            browser_text_fn=browser_text_fn,
            resolve_browser_target_fn=resolve_browser_target_fn,
        )
    if action in {"screenshot", "pdf", "download", "wait_download"}:
        return normalize_browser_artifact_payload(
            normalized,
            client=client,
            action=action,
            profile=profile,
            requested_target=requested_target,
            requested_url=requested_url,
            requested_ref=requested_ref,
            browser_text_fn=browser_text_fn,
            resolve_browser_target_fn=resolve_browser_target_fn,
        )
    return browser_action_normalization_shared_runtime.normalize_browser_fallback_payload(
        normalized,
        action=action,
        requested_target=requested_target,
        requested_url=requested_url,
        requested_ref=requested_ref,
        requested_paths=requested_paths,
        requested_input_ref=requested_input_ref,
        requested_accept=requested_accept,
        requested_prompt_text=requested_prompt_text,
        browser_text_fn=browser_text_fn,
    )
