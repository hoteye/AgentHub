from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli import thread_store_replay_normalization_helpers_runtime as replay_normalization_helpers_service
from cli.agent_cli import thread_store_replay_pure_helpers_runtime as replay_pure_helpers_service
from cli.agent_cli import thread_store_replay_runtime as replay_runtime
from cli.agent_cli import thread_store_replay_mapping_runtime as replay_mapping_runtime
from cli.agent_cli.media_content_runtime import (
    input_image_items_from_output,
    normalized_image_detail,
    output_contains_image_artifacts,
)
from cli.agent_cli.models import (
    ResponseInputItem,
    RolloutItem,
    ThreadHistoryTurn,
    replay_input_items_from_turn_events,
    response_items_to_text,
    response_items_with_tool_outputs,
)

_MEDIA_OUTPUT_ITEM_TYPES = replay_normalization_helpers_service.MEDIA_OUTPUT_ITEM_TYPES


def _legacy_image_subject_from_detail(value: Any) -> str:
    return replay_normalization_helpers_service.legacy_image_subject_from_detail(
        value,
        normalized_image_detail_fn=normalized_image_detail,
    )


def _media_artifact_payload_from_input_image(item: dict[str, Any]) -> dict[str, Any]:
    return replay_normalization_helpers_service.media_artifact_payload_from_input_image(
        item,
        normalized_image_detail_fn=normalized_image_detail,
        legacy_image_subject_from_detail_fn=_legacy_image_subject_from_detail,
    )


def _artifact_payload_from_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    return replay_normalization_helpers_service.artifact_payload_from_mapping(
        payload,
        normalized_image_detail_fn=normalized_image_detail,
        legacy_image_subject_from_detail_fn=_legacy_image_subject_from_detail,
    )


def _media_records_from_tool_events(tool_events: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in list(tool_events or []):
        payload = dict(getattr(event, "payload", None) or {})
        artifacts = payload.get("image_artifacts")
        if not isinstance(artifacts, list):
            continue
        call_id = str(payload.get("provider_call_id") or payload.get("call_id") or "").strip()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            record = replay_pure_helpers_service.record_from_media_payload(
                _artifact_payload_from_mapping(artifact),
                evidence="image_ready",
                call_id=call_id,
            )
            records.append(record)
    return records


def _media_records_from_output_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in list(items or []):
        item_type = str(item.get("type") or "").strip().lower()
        if item_type not in _MEDIA_OUTPUT_ITEM_TYPES:
            continue
        call_id = replay_normalization_helpers_service.call_id_from_item(item)
        path_hint = str(item.get("image_transport_subject") or "").strip()
        for output_image in input_image_items_from_output(item.get("output")):
            payload = _media_artifact_payload_from_input_image(output_image)
            if path_hint:
                payload["path"] = path_hint
            records.append(
                replay_pure_helpers_service.record_from_media_payload(
                    payload,
                    evidence="image_injected",
                    call_id=call_id,
                )
            )
    return records


def _explicit_media_output_items_by_call_id(turn: ThreadHistoryTurn) -> dict[str, dict[str, Any]]:
    explicit: dict[str, dict[str, Any]] = {}
    turn_events = [dict(item) for item in list(turn.turn_events or []) if isinstance(item, dict)]
    for event in turn_events:
        if str(event.get("type") or "").strip() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if item_type not in _MEDIA_OUTPUT_ITEM_TYPES:
            continue
        call_id = replay_normalization_helpers_service.call_id_from_item(item)
        if not call_id:
            continue
        output_images = input_image_items_from_output(item.get("output"))
        if not output_images:
            continue
        normalized = ResponseInputItem.from_dict(item).to_dict()
        normalized["output"] = output_images
        explicit[call_id] = normalized
    for raw_item in list(turn.response_items or []):
        item = raw_item.to_dict() if hasattr(raw_item, "to_dict") else dict(raw_item or {})
        item_type = str(item.get("type") or "").strip().lower()
        if item_type not in _MEDIA_OUTPUT_ITEM_TYPES:
            continue
        call_id = replay_normalization_helpers_service.call_id_from_item(item)
        if not call_id or call_id in explicit:
            continue
        output_images = input_image_items_from_output(item.get("output"))
        if not output_images:
            continue
        normalized = ResponseInputItem.from_dict(item).to_dict()
        normalized["output"] = output_images
        explicit[call_id] = normalized
    return explicit


def _dedupe_media_replay_items(
    turn: ThreadHistoryTurn,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    explicit_output_by_call_id = _explicit_media_output_items_by_call_id(turn)
    deduped: list[dict[str, Any]] = []
    seen_media_output_signatures: set[tuple[str, str, tuple[str, ...]]] = set()
    seen_handles: set[str] = set()
    for raw in list(items or []):
        if not isinstance(raw, dict):
            continue
        normalized = ResponseInputItem.from_dict(raw).to_dict()
        item_type = str(normalized.get("type") or "").strip().lower()
        if item_type not in _MEDIA_OUTPUT_ITEM_TYPES:
            deduped.append(normalized)
            continue
        call_id = replay_normalization_helpers_service.call_id_from_item(normalized)
        candidate = explicit_output_by_call_id.get(call_id, normalized)
        input_images = input_image_items_from_output(candidate.get("output"))
        if input_images:
            unique_images: list[dict[str, Any]] = []
            handles: list[str] = []
            path_hint = str(candidate.get("image_transport_subject") or "").strip()
            for image_item in input_images:
                payload = _media_artifact_payload_from_input_image(image_item)
                if path_hint:
                    payload["path"] = path_hint
                handle = replay_pure_helpers_service.media_artifact_handle(payload)
                if handle in seen_handles:
                    continue
                seen_handles.add(handle)
                handles.append(handle)
                unique_images.append(image_item)
            if not unique_images:
                continue
            media_signature = (item_type, call_id, tuple(handles))
            if media_signature in seen_media_output_signatures:
                continue
            seen_media_output_signatures.add(media_signature)
            replay_item = dict(candidate)
            replay_item["output"] = unique_images
            deduped.append(replay_item)
            continue
        if output_contains_image_artifacts(candidate.get("output")):
            # image_ready evidence is persisted separately; only replay explicit input_image injections.
            continue
        deduped.append(candidate)
    return deduped


def _dedupe_bounded_media_replay_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Once multiple provider turns are flattened into a bounded replay tail, there
    # is no single authoritative source turn for explicit media outputs. At that
    # point we intentionally dedupe only by media handle to avoid re-injecting the
    # same image data URL multiple times across resumed turns.
    return _dedupe_media_replay_items(
        ThreadHistoryTurn(
            turn_events=[],
            response_items=[],
            tool_events=[],
        ),
        items,
    )


def media_artifact_persistence_state_from_turn(turn: ThreadHistoryTurn) -> dict[str, Any]:
    response_items = [
        item.to_dict() if hasattr(item, "to_dict") else dict(item or {})
        for item in list(turn.response_items or [])
    ]
    turn_event_items = [
        dict(event.get("item") or {})
        for event in list(turn.turn_events or [])
        if isinstance(event, dict)
        and str(event.get("type") or "").strip() == "item.completed"
        and isinstance(event.get("item"), dict)
    ]
    ready_records = _media_records_from_tool_events(list(turn.tool_events or []))
    injected_records = _media_records_from_output_items(turn_event_items)
    injected_records.extend(_media_records_from_output_items(response_items))
    records = replay_pure_helpers_service.sorted_unique_records([*ready_records, *injected_records])
    return replay_pure_helpers_service.media_artifact_persistence_state(records)


def merge_media_artifact_persistence_state(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    existing_payload = dict(existing or {})
    incoming_payload = dict(incoming or {})
    existing_records = [
        dict(record)
        for record in list(existing_payload.get("records") or [])
        if isinstance(record, dict)
    ]
    incoming_records = [
        dict(record)
        for record in list(incoming_payload.get("records") or [])
        if isinstance(record, dict)
    ]
    records = replay_pure_helpers_service.sorted_unique_records([*existing_records, *incoming_records])
    return replay_pure_helpers_service.media_artifact_persistence_state(records)


def planner_turn_response_replay_items(turn: ThreadHistoryTurn) -> list[dict[str, Any]]:
    replay_items = replay_runtime.planner_turn_response_replay_items(
        turn,
        replay_input_items_from_turn_events_fn=replay_input_items_from_turn_events,
        response_items_with_tool_outputs_fn=response_items_with_tool_outputs,
        response_items_to_text_fn=response_items_to_text,
    )
    return _dedupe_media_replay_items(turn, replay_items)


def planner_input_items_from_turns(
    turns: list[ThreadHistoryTurn],
    *,
    fallback_history: list[dict[str, str]] | None = None,
    planner_history_limit: int,
    planner_input_items_from_history_fn: Callable[..., list[dict[str, Any]]],
    turn_used_provider_fn: Callable[[ThreadHistoryTurn], bool],
) -> list[dict[str, Any]]:
    segments: list[list[dict[str, Any]]] = [
        [item]
        for item in planner_input_items_from_history_fn(
            list(fallback_history or []),
            planner_history_limit=planner_history_limit,
        )
    ]
    for turn in list(turns or []):
        if not turn_used_provider_fn(turn):
            continue
        turn_segment: list[dict[str, Any]] = []
        user_text = str(turn.user_text or "").strip()
        if user_text:
            turn_segment.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                }
            )
        turn_segment.extend(planner_turn_response_replay_items(turn))
        segments.append(turn_segment)
    bounded = replay_mapping_runtime.bounded_turn_segment_tail(
        segments,
        planner_history_limit=planner_history_limit,
    )
    return _dedupe_bounded_media_replay_items(bounded)


def planner_input_items_from_rollout_items(
    rollout_items: list[dict[str, Any]],
    *,
    fallback_history: list[dict[str, str]] | None = None,
    planner_history_limit: int,
    turn_used_provider_fn: Callable[[ThreadHistoryTurn], bool],
    compacted_replacement_history_fn: Callable[..., list[dict[str, str]]],
    planner_input_items_from_history_fn: Callable[..., list[dict[str, Any]]],
    planner_turn_context_replay_items_fn: Callable[[Any | None], list[dict[str, Any]]],
    planner_input_items_from_turns_fn: Callable[..., list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    item_segments: list[list[dict[str, Any]]] = []
    legacy_items: list[dict[str, Any]] = []
    pending_turn_context: Any | None = None
    saw_turn = False
    for raw in list(rollout_items or []):
        if not isinstance(raw, dict):
            continue
        rollout_item = RolloutItem.from_dict(raw)
        if rollout_item.item_type == "compacted":
            replacement_history = compacted_replacement_history_fn(
                rollout_item.payload,
                existing_history=list(fallback_history or []),
            )
            item_segments = [
                [item]
                for item in planner_input_items_from_history_fn(
                    replacement_history,
                    planner_history_limit=planner_history_limit,
                )
            ]
            legacy_items = []
            pending_turn_context = None
            saw_turn = False
            continue
        if rollout_item.item_type == "turn_context":
            pending_turn_context = rollout_item.turn_context
            continue
        if rollout_item.item_type == "response_item":
            if str(rollout_item.payload.get("scope") or "").strip() == "turn_context":
                continue
            normalized_item = replay_mapping_runtime.response_input_item_from_rollout_payload(
                rollout_item.payload,
                response_input_item_from_dict_fn=ResponseInputItem.from_dict,
            )
            if normalized_item is not None and not saw_turn:
                legacy_items.append(normalized_item)
            continue
        if rollout_item.item_type != "turn" or rollout_item.turn is None:
            continue
        saw_turn = True
        if not turn_used_provider_fn(rollout_item.turn):
            pending_turn_context = None
            continue
        turn_segment: list[dict[str, Any]] = []
        turn_segment.extend(planner_turn_context_replay_items_fn(pending_turn_context))
        pending_turn_context = None
        user_text = str(rollout_item.turn.user_text or "").strip()
        if user_text:
            turn_segment.append(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                }
            )
        turn_segment.extend(planner_turn_response_replay_items(rollout_item.turn))
        item_segments.append(turn_segment)
    if item_segments:
        bounded = replay_mapping_runtime.bounded_turn_segment_tail(
            item_segments,
            planner_history_limit=planner_history_limit,
        )
        return _dedupe_bounded_media_replay_items(bounded)
    if legacy_items:
        return legacy_items[-planner_history_limit:]
    return planner_input_items_from_turns_fn(
        turns=[],
        fallback_history=fallback_history,
        planner_history_limit=planner_history_limit,
        turn_used_provider_fn=turn_used_provider_fn,
    )
